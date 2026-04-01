"""Tests for retrieval: FTS5 search, retrievers, and hybrid fusion."""

# pattern: Imperative Shell

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import numpy as np
import pytest

from local_library.core.errors import FTSQueryError
from local_library.core.storage import get_connection, init_schema
from local_library.core.vec_extension import is_vec_available
from local_library.embeddings.base import Chunk, ChunkEmbedding, Retriever, SearchResult
from local_library.embeddings.retrieval import (
    FTSRetriever,
    HybridRetriever,
    VectorRetriever,
    _lookup_doc_metadata,
    _rrf_fuse,
)
from local_library.embeddings.storage import EmbeddingStorage, _sanitize_fts_query

pytestmark = pytest.mark.skipif(
    not is_vec_available(),
    reason="sqlite-vec extension not available",
)


def make_chunk_embedding(doc_id: UUID, index: int = 0, text: str = "Test text") -> ChunkEmbedding:
    """Create a ChunkEmbedding with random vector for testing."""
    chunk = Chunk.create(doc_id, index, text)
    embedding = np.random.randn(768).astype(np.float32)
    return ChunkEmbedding(chunk=chunk, embedding=embedding)


def _create_test_document(conn: sqlite3.Connection, doc_id: UUID) -> None:
    """Insert a minimal document record for foreign key satisfaction."""
    conn.execute(
        """
        INSERT INTO documents (id, original_path, content_hash, storage_path,
                               extracted_path, status, embedding_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'ready', 'current', ?, ?)
        """,
        (
            str(doc_id),
            "/fake/path.pdf",
            "fakehash" + str(doc_id)[:8],
            "fa/ke/fakehash.pdf",
            "/fake/extracted.md",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


@pytest.fixture
def storage(tmp_path: Path) -> EmbeddingStorage:
    """Provide an EmbeddingStorage with initialized schema."""
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_schema(conn)
    return EmbeddingStorage(conn)


class TestSanitizeFtsQuery:
    """Tests for FTS5 query sanitization."""

    def test_query_with_trailing_question_mark(self) -> None:
        """Query with trailing ? is stripped."""
        query = "What makes transformer models so effective?"
        result = _sanitize_fts_query(query)
        assert "?" not in result
        assert "transformer" in result
        assert "models" in result
        assert "effective" in result

    def test_query_with_multiple_punctuation(self) -> None:
        """Query with multiple punctuation marks is cleaned."""
        query = "Machine learning: How? And why!?!"
        result = _sanitize_fts_query(query)
        assert "?" not in result
        assert "!" not in result
        assert ":" not in result
        # Should contain the core words
        assert "Machine" in result
        assert "learning" in result

    def test_query_with_only_punctuation_raises_error(self) -> None:
        """Query that becomes empty after sanitization raises FTSQueryError."""
        query = "?!.,;:"
        with pytest.raises(FTSQueryError):
            _sanitize_fts_query(query)

    def test_balanced_quotes_preserved(self) -> None:
        """Balanced quotes are preserved for phrase matching."""
        query = '"state of the art" embeddings'
        result = _sanitize_fts_query(query)
        assert '"state of the art"' in result
        assert "embeddings" in result

    def test_unbalanced_quotes_stripped(self) -> None:
        """Unbalanced quotes are removed."""
        query = 'What is "natural language processing'
        result = _sanitize_fts_query(query)
        assert '"' not in result
        assert "natural" in result
        assert "language" in result
        assert "processing" in result

    def test_normal_alphanumeric_query_or_joined(self) -> None:
        """Normal alphanumeric query gets OR-joined."""
        query = "machine learning algorithms"
        result = _sanitize_fts_query(query)
        assert result == "machine OR learning OR algorithms"

    def test_hyphens_between_words_replaced_with_spaces(self) -> None:
        """Hyphens between words are replaced with spaces.

        FTS5's unicode61 tokenizer splits on hyphens when indexing, so
        the indexed tokens are already separate words. But FTS5's query
        parser interprets hyphens as the NOT operator, so 'actor-network'
        becomes 'actor NOT network'. Replacing hyphens with spaces makes
        the query match the indexed tokens correctly.
        """
        query = "state-of-the-art deep-learning"
        result = _sanitize_fts_query(query)
        assert "-" not in result
        assert "state" in result
        assert "art" in result
        assert "deep" in result
        assert "learning" in result

    def test_hyphenated_query_no_fts_column_error(self) -> None:
        """Queries with hyphens must not produce FTS5 column filter syntax.

        Without this fix, 'actor-network theory' causes FTS5 to interpret
        'network' as a column name, raising 'no such column: network'.
        """
        query = "How does actor-network theory work?"
        result = _sanitize_fts_query(query)
        assert "-" not in result
        assert "actor" in result
        assert "network" in result
        assert "theory" in result

    def test_apostrophes_removed(self) -> None:
        """Apostrophes/single quotes are removed (FTS5 string delimiter)."""
        query = "the worker's condition"
        result = _sanitize_fts_query(query)
        assert "'" not in result
        assert "worker" in result
        assert "condition" in result

    def test_standalone_plus_sign_removed(self) -> None:
        """Standalone + operators are removed."""
        query = "machine + learning"
        result = _sanitize_fts_query(query)
        assert "+" not in result
        assert "machine" in result
        assert "learning" in result

    def test_standalone_minus_sign_removed(self) -> None:
        """Standalone - operators are removed."""
        query = "neural - networks"
        result = _sanitize_fts_query(query)
        assert "-" not in result  # Standalone - is removed
        assert "neural" in result
        assert "networks" in result

    def test_multiple_spaces_collapsed(self) -> None:
        """Multiple consecutive spaces are collapsed (OR-joined output)."""
        query = "machine   learning    algorithms"
        result = _sanitize_fts_query(query)
        assert result == "machine OR learning OR algorithms"

    def test_leading_trailing_whitespace_stripped(self) -> None:
        """Leading and trailing whitespace is removed."""
        query = "   machine learning   "
        result = _sanitize_fts_query(query)
        assert result == "machine OR learning"

    def test_parentheses_removed(self) -> None:
        """Parentheses are removed."""
        query = "transformers (attention mechanism)"
        result = _sanitize_fts_query(query)
        assert "(" not in result
        assert ")" not in result
        assert "transformers" in result
        assert "attention" in result
        assert "mechanism" in result

    def test_square_brackets_removed(self) -> None:
        """Square brackets are removed."""
        query = "retrieval [augmented] generation"
        result = _sanitize_fts_query(query)
        assert "[" not in result
        assert "]" not in result
        assert "retrieval" in result
        assert "augmented" in result
        assert "generation" in result

    def test_braces_removed(self) -> None:
        """Curly braces are removed."""
        query = "data {science} methods"
        result = _sanitize_fts_query(query)
        assert "{" not in result
        assert "}" not in result
        assert "data" in result
        assert "science" in result
        assert "methods" in result

    def test_special_chars_removed(self) -> None:
        """Special characters like ^, ~, \\ are removed."""
        query = "regex^pattern~test\\backslash"
        result = _sanitize_fts_query(query)
        assert "^" not in result
        assert "~" not in result
        assert "\\" not in result
        assert "regex" in result
        assert "pattern" in result
        assert "test" in result
        assert "backslash" in result

    def test_commas_and_semicolons_removed(self) -> None:
        """Commas and semicolons are removed."""
        query = "natural language; processing, analysis"
        result = _sanitize_fts_query(query)
        assert ";" not in result
        assert "," not in result
        assert "natural" in result
        assert "language" in result
        assert "processing" in result
        assert "analysis" in result

    def test_stop_words_removed(self) -> None:
        """Common stop words are removed from queries.

        FTS5 uses implicit AND by default, so stop words like 'what', 'is',
        'the' overly constrain the match — every word must appear in the chunk.
        Removing stop words lets FTS5 focus on content-bearing terms.
        """
        query = "What is the role of social identity in intergroup behavior"
        result = _sanitize_fts_query(query)
        # Stop words removed (check raw terms, not OR-joined output)
        terms = [t for t in result.split() if t != "OR"]
        for stop in ["what", "is", "the", "of", "in"]:
            assert stop not in [t.lower() for t in terms]
        # Content words preserved
        for word in ["role", "social", "identity", "intergroup", "behavior"]:
            assert word in result.lower()

    def test_stop_word_removal_case_insensitive(self) -> None:
        """Stop words are removed regardless of case."""
        query = "The Role Of Identity"
        result = _sanitize_fts_query(query)
        assert "role" in result.lower()
        assert "identity" in result.lower()
        for stop in ["the", "of"]:
            assert stop not in result.lower().split()

    def test_query_of_only_stop_words_raises_error(self) -> None:
        """Query containing only stop words raises FTSQueryError."""
        query = "what is the"
        with pytest.raises(FTSQueryError):
            _sanitize_fts_query(query)

    def test_stop_words_not_removed_from_quoted_phrases(self) -> None:
        """Stop words inside quoted phrases are preserved.

        Quoted strings in FTS5 are phrase matches — the exact sequence
        matters, so stop words must stay to preserve phrase semantics.
        """
        query = '"state of the art" embeddings'
        result = _sanitize_fts_query(query)
        assert '"state of the art"' in result
        assert "embeddings" in result

    def test_terms_joined_with_or(self) -> None:
        """Non-quoted terms are joined with OR for disjunctive BM25 matching.

        FTS5 defaults to implicit AND, but natural language queries need
        disjunctive matching — BM25 naturally ranks multi-term matches
        higher without requiring ALL terms to appear.
        """
        query = "social identity intergroup behavior"
        result = _sanitize_fts_query(query)
        assert result == "social OR identity OR intergroup OR behavior"

    def test_or_mode_with_quoted_phrase(self) -> None:
        """Quoted phrases and OR terms coexist correctly."""
        query = '"state of the art" embeddings retrieval'
        result = _sanitize_fts_query(query)
        assert '"state of the art"' in result
        assert "OR" in result
        assert "embeddings" in result
        assert "retrieval" in result

    def test_single_content_word_no_or(self) -> None:
        """Single remaining term has no OR operator."""
        query = "What is embeddings?"
        result = _sanitize_fts_query(query)
        assert result == "embeddings"
        assert "OR" not in result

    def test_real_world_query_example(self) -> None:
        """Real-world example: natural language question with punctuation."""
        query = "What makes transformer models so effective?"
        result = _sanitize_fts_query(query)
        assert "transformer" in result
        assert "models" in result
        assert "effective" in result
        assert "OR" in result


class TestSearchFts:
    """Tests for EmbeddingStorage.search_fts()."""

    def test_basic_keyword_match(self, storage: EmbeddingStorage) -> None:
        """search_fts returns chunks matching keyword query."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Machine learning algorithms for classification"),
                make_chunk_embedding(doc_id, 1, "Database indexing and query optimization"),
                make_chunk_embedding(doc_id, 2, "Neural network training with backpropagation"),
            ]
        )

        results = storage.search_fts("machine learning")

        assert len(results) >= 1
        texts = [chunk.text for chunk, _ in results]
        assert any("Machine learning" in t for t in texts)

    def test_returns_chunk_and_score_tuples(self, storage: EmbeddingStorage) -> None:
        """search_fts returns list of (Chunk, float) tuples."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Python programming language"),
            ]
        )

        results = storage.search_fts("Python")

        assert len(results) == 1
        chunk, score = results[0]
        assert isinstance(chunk, Chunk)
        assert isinstance(score, float)

    def test_bm25_scores_are_negative(self, storage: EmbeddingStorage) -> None:
        """BM25 scores from FTS5 are negative (lower = better match)."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Python programming language"),
            ]
        )

        results = storage.search_fts("Python")

        assert len(results) == 1
        _, score = results[0]
        assert score < 0

    def test_respects_limit(self, storage: EmbeddingStorage) -> None:
        """search_fts respects the limit parameter."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, i, f"Document about topic {i} with common keyword")
                for i in range(5)
            ]
        )

        results = storage.search_fts("keyword", limit=2)

        assert len(results) <= 2

    def test_filters_by_doc_ids(self, storage: EmbeddingStorage) -> None:
        """search_fts filters results to specified document IDs."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()
        _create_test_document(storage._conn, doc_id_1)
        _create_test_document(storage._conn, doc_id_2)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id_1, 0, "Python programming in doc one"),
                make_chunk_embedding(doc_id_2, 0, "Python programming in doc two"),
            ]
        )

        results = storage.search_fts("Python", doc_ids=[doc_id_1])

        assert len(results) == 1
        chunk, _ = results[0]
        assert chunk.doc_id == doc_id_1

    def test_empty_results_for_no_match(self, storage: EmbeddingStorage) -> None:
        """search_fts returns empty list when no chunks match."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Machine learning algorithms"),
            ]
        )

        results = storage.search_fts("xylophone")

        assert results == []

    def test_raises_fts_query_error_on_only_punctuation(self, storage: EmbeddingStorage) -> None:
        """search_fts raises FTSQueryError when query becomes empty after sanitization."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Some text"),
            ]
        )

        # Query that becomes empty after sanitization
        with pytest.raises(FTSQueryError):
            storage.search_fts("?!.,;:")

    def test_reconstructs_chunk_correctly(self, storage: EmbeddingStorage) -> None:
        """search_fts returns Chunk objects with all fields populated."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Specific searchable content here"),
            ]
        )

        results = storage.search_fts("searchable")

        assert len(results) == 1
        chunk, _ = results[0]
        assert chunk.doc_id == doc_id
        assert chunk.chunk_index == 0
        assert "searchable" in chunk.text
        assert isinstance(chunk.created_at, datetime)

    def test_sanitizes_query_with_punctuation(self, storage: EmbeddingStorage) -> None:
        """search_fts sanitizes queries with punctuation before searching."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Machine learning classification"),
            ]
        )

        # Query with trailing punctuation (would cause FTS5 error without sanitization)
        results = storage.search_fts("machine learning?")

        assert len(results) >= 1
        texts = [chunk.text for chunk, _ in results]
        assert any("Machine learning" in t for t in texts)

    def test_query_becomes_empty_after_sanitization_raises_error(
        self, storage: EmbeddingStorage
    ) -> None:
        """search_fts raises FTSQueryError if sanitization results in empty string."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Some text"),
            ]
        )

        # Query that becomes empty after sanitization
        with pytest.raises(FTSQueryError) as exc_info:
            storage.search_fts("?!.,;:")

        assert "empty" in str(exc_info.value).lower()


class TestLookupDocMetadata:
    """Tests for the _lookup_doc_metadata helper function."""

    def test_returns_title_and_citekey(self, storage: EmbeddingStorage) -> None:
        """Helper returns dict mapping doc_id to (title, citekey)."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("Test Title", "Smith2023", str(doc_id)),
        )
        storage._conn.commit()

        result = _lookup_doc_metadata(storage._conn, {doc_id})

        assert doc_id in result
        title, citekey = result[doc_id]
        assert title == "Test Title"
        assert citekey == "Smith2023"

    def test_returns_none_for_missing_metadata(self, storage: EmbeddingStorage) -> None:
        """Helper returns (None, None) when title/citekey not set."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)

        result = _lookup_doc_metadata(storage._conn, {doc_id})

        assert doc_id in result
        title, citekey = result[doc_id]
        assert title is None
        assert citekey is None

    def test_empty_input_returns_empty_dict(self, storage: EmbeddingStorage) -> None:
        """Helper returns empty dict for empty input."""
        result = _lookup_doc_metadata(storage._conn, set())
        assert result == {}

    def test_batch_lookup_multiple_docs(self, storage: EmbeddingStorage) -> None:
        """Helper fetches metadata for multiple documents in one query."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()
        _create_test_document(storage._conn, doc_id_1)
        _create_test_document(storage._conn, doc_id_2)
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("Doc One", "Author2023a", str(doc_id_1)),
        )
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("Doc Two", "Author2023b", str(doc_id_2)),
        )
        storage._conn.commit()

        result = _lookup_doc_metadata(storage._conn, {doc_id_1, doc_id_2})

        assert len(result) == 2
        assert result[doc_id_1] == ("Doc One", "Author2023a")
        assert result[doc_id_2] == ("Doc Two", "Author2023b")


class TestVectorRetriever:
    """Tests for VectorRetriever."""

    def test_satisfies_retriever_protocol(self, storage: EmbeddingStorage) -> None:
        """VectorRetriever satisfies the Retriever protocol."""
        embedder = MagicMock()
        retriever = VectorRetriever(storage, embedder)
        assert isinstance(retriever, Retriever)

    def test_returns_search_results(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns list of SearchResult with vector method."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("Test Doc", "Test2023", str(doc_id)),
        )
        storage._conn.commit()
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Some text about machine learning"),
            ]
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        retriever = VectorRetriever(storage, mock_embedder)
        results = retriever.retrieve("machine learning", k=5)

        assert len(results) >= 1
        result = results[0]
        assert isinstance(result, SearchResult)
        assert result.doc_title == "Test Doc"
        assert result.doc_citekey == "Test2023"
        assert "vector" in result.search_methods
        assert isinstance(result.score, float)  # Score is a number

    def test_respects_k_parameter(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns at most k results."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [make_chunk_embedding(doc_id, i, f"Chunk number {i}") for i in range(5)]
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        retriever = VectorRetriever(storage, mock_embedder)
        results = retriever.retrieve("query", k=2)

        assert len(results) <= 2

    def test_passes_doc_ids_filter(self, storage: EmbeddingStorage) -> None:
        """retrieve() filters by document IDs when provided."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()
        _create_test_document(storage._conn, doc_id_1)
        _create_test_document(storage._conn, doc_id_2)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id_1, 0, "Content in doc one"),
                make_chunk_embedding(doc_id_2, 0, "Content in doc two"),
            ]
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        retriever = VectorRetriever(storage, mock_embedder)
        results = retriever.retrieve("content", k=10, doc_ids=[doc_id_1])

        for result in results:
            assert result.chunk.doc_id == doc_id_1

    def test_empty_results(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns empty list when no embeddings exist."""
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        retriever = VectorRetriever(storage, mock_embedder)
        results = retriever.retrieve("nonexistent query")

        assert results == []


class TestFTSRetriever:
    """Tests for FTSRetriever."""

    def test_satisfies_retriever_protocol(self, storage: EmbeddingStorage) -> None:
        """FTSRetriever satisfies the Retriever protocol."""
        retriever = FTSRetriever(storage)
        assert isinstance(retriever, Retriever)

    def test_returns_search_results(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns list of SearchResult with fts method."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("FTS Doc", "FTS2023", str(doc_id)),
        )
        storage._conn.commit()
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Python programming language features"),
            ]
        )

        retriever = FTSRetriever(storage)
        results = retriever.retrieve("Python programming")

        assert len(results) >= 1
        result = results[0]
        assert isinstance(result, SearchResult)
        assert result.doc_title == "FTS Doc"
        assert result.doc_citekey == "FTS2023"
        assert "fts" in result.search_methods
        assert result.score > 0  # Negated BM25 score

    def test_respects_k_parameter(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns at most k results."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, i, f"Chunk {i} about searchable keyword")
                for i in range(5)
            ]
        )

        retriever = FTSRetriever(storage)
        results = retriever.retrieve("keyword", k=2)

        assert len(results) <= 2

    def test_filters_by_doc_ids(self, storage: EmbeddingStorage) -> None:
        """retrieve() filters by document IDs when provided."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()
        _create_test_document(storage._conn, doc_id_1)
        _create_test_document(storage._conn, doc_id_2)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id_1, 0, "Searchable term in doc one"),
                make_chunk_embedding(doc_id_2, 0, "Searchable term in doc two"),
            ]
        )

        retriever = FTSRetriever(storage)
        results = retriever.retrieve("Searchable", doc_ids=[doc_id_1])

        assert len(results) == 1
        assert results[0].chunk.doc_id == doc_id_1

    def test_raises_fts_query_error(self, storage: EmbeddingStorage) -> None:
        """retrieve() propagates FTSQueryError when query becomes empty after sanitization."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Some text"),
            ]
        )

        retriever = FTSRetriever(storage)
        with pytest.raises(FTSQueryError):
            retriever.retrieve("?!.,;:")

    def test_empty_results(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns empty list for no matches."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Some text"),
            ]
        )

        retriever = FTSRetriever(storage)
        results = retriever.retrieve("xylophone")

        assert results == []


class TestRrfFuse:
    """Tests for the _rrf_fuse pure function (Functional Core)."""

    def _make_result(
        self,
        chunk_id: str,
        score: float,
        method: str,
        doc_id: UUID | None = None,
    ) -> SearchResult:
        """Helper to create SearchResult for fusion tests."""
        if doc_id is None:
            doc_id = uuid4()
        chunk = Chunk.create(doc_id, 0, f"Text for {chunk_id}")
        # Override chunk_id for deterministic testing
        chunk = Chunk(
            chunk_id=chunk_id,
            doc_id=chunk.doc_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            section=chunk.section,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            created_at=chunk.created_at,
        )
        return SearchResult(
            chunk=chunk,
            score=score,
            doc_title=None,
            doc_citekey=None,
            search_methods=frozenset({method}),
        )

    def test_empty_inputs(self) -> None:
        """RRF with empty lists returns empty list."""
        result = _rrf_fuse([], [], k=10)
        assert result == []

    def test_single_list_vector_only(self) -> None:
        """RRF with only vector results returns them re-scored."""
        vector_results = [
            self._make_result("a", 0.9, "vector"),
            self._make_result("b", 0.8, "vector"),
        ]
        fused = _rrf_fuse(vector_results, [], k=10)

        assert len(fused) == 2
        assert fused[0].chunk.chunk_id == "a"
        assert fused[1].chunk.chunk_id == "b"
        assert fused[0].score > fused[1].score

    def test_single_list_fts_only(self) -> None:
        """RRF with only FTS results returns them re-scored."""
        fts_results = [
            self._make_result("x", 5.0, "fts"),
            self._make_result("y", 3.0, "fts"),
        ]
        fused = _rrf_fuse([], fts_results, k=10)

        assert len(fused) == 2
        assert fused[0].chunk.chunk_id == "x"
        assert fused[1].chunk.chunk_id == "y"

    def test_overlapping_results_merge(self) -> None:
        """Chunks appearing in both lists get combined scores and methods."""
        doc_id = uuid4()
        vector_results = [
            self._make_result("shared", 0.9, "vector", doc_id=doc_id),
            self._make_result("vec_only", 0.7, "vector"),
        ]
        fts_results = [
            self._make_result("shared", 5.0, "fts", doc_id=doc_id),
            self._make_result("fts_only", 3.0, "fts"),
        ]
        fused = _rrf_fuse(vector_results, fts_results, k=10)

        shared_result = next(r for r in fused if r.chunk.chunk_id == "shared")
        assert shared_result.search_methods == frozenset({"vector", "fts"})

        # Shared result should rank highest (gets RRF score from both lists)
        assert fused[0].chunk.chunk_id == "shared"

    def test_respects_k_limit(self) -> None:
        """RRF returns at most k results."""
        vector_results = [self._make_result(f"v{i}", 1.0 - i * 0.1, "vector") for i in range(5)]
        fts_results = [self._make_result(f"f{i}", 5.0 - i, "fts") for i in range(5)]
        fused = _rrf_fuse(vector_results, fts_results, k=3)

        assert len(fused) == 3

    def test_sorted_by_score_descending(self) -> None:
        """Fused results are sorted by RRF score descending."""
        vector_results = [
            self._make_result("a", 0.9, "vector"),
            self._make_result("b", 0.5, "vector"),
        ]
        fts_results = [
            self._make_result("c", 5.0, "fts"),
            self._make_result("b", 3.0, "fts"),
        ]
        fused = _rrf_fuse(vector_results, fts_results, k=10)

        scores = [r.score for r in fused]
        assert scores == sorted(scores, reverse=True)

    def test_rrf_k_parameter(self) -> None:
        """Different rrf_k values change scores but not rank order."""
        vector_results = [
            self._make_result("a", 0.9, "vector"),
            self._make_result("b", 0.5, "vector"),
        ]
        fused_60 = _rrf_fuse(vector_results, [], k=10, rrf_k=60)
        fused_10 = _rrf_fuse(vector_results, [], k=10, rrf_k=10)

        # Same order
        assert [r.chunk.chunk_id for r in fused_60] == [r.chunk.chunk_id for r in fused_10]
        # Different scores
        assert fused_60[0].score != fused_10[0].score

    def test_weights_affect_scoring(self) -> None:
        """Non-equal weights change relative contribution of each list."""
        doc_id = uuid4()
        vector_results = [self._make_result("a", 0.9, "vector", doc_id=doc_id)]
        fts_results = [self._make_result("a", 5.0, "fts", doc_id=doc_id)]

        fused_equal = _rrf_fuse(
            vector_results,
            fts_results,
            k=10,
            vector_weight=1.0,
            fts_weight=1.0,
        )
        fused_vector_heavy = _rrf_fuse(
            vector_results,
            fts_results,
            k=10,
            vector_weight=2.0,
            fts_weight=0.5,
        )

        # Scores differ when weights change
        assert fused_equal[0].score != fused_vector_heavy[0].score

    def test_preserves_metadata(self) -> None:
        """Fused results preserve doc_title and doc_citekey from original results."""
        doc_id = uuid4()
        chunk = Chunk.create(doc_id, 0, "Text")
        chunk = Chunk(
            chunk_id="meta_test",
            doc_id=chunk.doc_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            section=chunk.section,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            created_at=chunk.created_at,
        )
        vector_results = [
            SearchResult(
                chunk=chunk,
                score=0.9,
                doc_title="My Title",
                doc_citekey="Key2023",
                search_methods=frozenset({"vector"}),
            )
        ]
        fused = _rrf_fuse(vector_results, [], k=10)

        assert fused[0].doc_title == "My Title"
        assert fused[0].doc_citekey == "Key2023"


class TestHybridRetriever:
    """Tests for HybridRetriever."""

    def test_satisfies_retriever_protocol(self, storage: EmbeddingStorage) -> None:
        """HybridRetriever satisfies the Retriever protocol."""
        mock_embedder = MagicMock()
        vector_ret = VectorRetriever(storage, mock_embedder)
        fts_ret = FTSRetriever(storage)
        hybrid = HybridRetriever(vector_ret, fts_ret)
        assert isinstance(hybrid, Retriever)

    def test_returns_fused_results(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns results from both vector and FTS search."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("Hybrid Doc", "Hybrid2023", str(doc_id)),
        )
        storage._conn.commit()
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Machine learning classification algorithms"),
            ]
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        vector_ret = VectorRetriever(storage, mock_embedder)
        fts_ret = FTSRetriever(storage)
        hybrid = HybridRetriever(vector_ret, fts_ret)
        results = hybrid.retrieve("machine learning")

        assert len(results) >= 1
        result = results[0]
        assert isinstance(result, SearchResult)
        # The result should come from at least one method
        assert len(result.search_methods) >= 1

    def test_falls_back_to_vector_on_fts_error(
        self, storage: EmbeddingStorage, caplog: pytest.LogCaptureFixture
    ) -> None:
        """HybridRetriever falls back to vector-only when FTS raises FTSQueryError."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Some text content"),
            ]
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        vector_ret = VectorRetriever(storage, mock_embedder)
        fts_ret = FTSRetriever(storage)
        hybrid = HybridRetriever(vector_ret, fts_ret)

        # Query that becomes empty after sanitization (causes FTS error)
        with caplog.at_level(logging.WARNING):
            results = hybrid.retrieve("?!.,;:")

        # Should still get vector results
        assert len(results) >= 1
        for r in results:
            assert r.search_methods == frozenset({"vector"})

        # Should log a warning
        fts_logged = any(
            "FTS" in record.message or "fts" in record.message.lower() for record in caplog.records
        )
        assert fts_logged

    def test_respects_k_parameter(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns at most k results."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [make_chunk_embedding(doc_id, i, f"Chunk {i} with searchable terms") for i in range(10)]
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        vector_ret = VectorRetriever(storage, mock_embedder)
        fts_ret = FTSRetriever(storage)
        hybrid = HybridRetriever(vector_ret, fts_ret)
        results = hybrid.retrieve("searchable", k=3)

        assert len(results) <= 3

    def test_passes_doc_ids_filter(self, storage: EmbeddingStorage) -> None:
        """retrieve() passes doc_ids filter to both sub-retrievers."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()
        _create_test_document(storage._conn, doc_id_1)
        _create_test_document(storage._conn, doc_id_2)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id_1, 0, "Content about Python programming"),
                make_chunk_embedding(doc_id_2, 0, "Content about Python programming"),
            ]
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        vector_ret = VectorRetriever(storage, mock_embedder)
        fts_ret = FTSRetriever(storage)
        hybrid = HybridRetriever(vector_ret, fts_ret)
        results = hybrid.retrieve("Python", k=10, doc_ids=[doc_id_1])

        for result in results:
            assert result.chunk.doc_id == doc_id_1
