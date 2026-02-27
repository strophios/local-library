"""Tests for retrieval: FTS5 search, retrievers, and hybrid fusion."""

# pattern: Imperative Shell

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
    VectorRetriever,
    _lookup_doc_metadata,
)
from local_library.embeddings.storage import EmbeddingStorage

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

    def test_raises_fts_query_error_on_bad_syntax(self, storage: EmbeddingStorage) -> None:
        """search_fts raises FTSQueryError for malformed FTS5 queries."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings(
            [
                make_chunk_embedding(doc_id, 0, "Some text"),
            ]
        )

        with pytest.raises(FTSQueryError):
            storage.search_fts('"unbalanced quote')

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
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Some text about machine learning"),
        ])

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
        storage.store_embeddings([
            make_chunk_embedding(doc_id, i, f"Chunk number {i}")
            for i in range(5)
        ])

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
        storage.store_embeddings([
            make_chunk_embedding(doc_id_1, 0, "Content in doc one"),
            make_chunk_embedding(doc_id_2, 0, "Content in doc two"),
        ])

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
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Python programming language features"),
        ])

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
        storage.store_embeddings([
            make_chunk_embedding(doc_id, i, f"Chunk {i} about searchable keyword")
            for i in range(5)
        ])

        retriever = FTSRetriever(storage)
        results = retriever.retrieve("keyword", k=2)

        assert len(results) <= 2

    def test_filters_by_doc_ids(self, storage: EmbeddingStorage) -> None:
        """retrieve() filters by document IDs when provided."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()
        _create_test_document(storage._conn, doc_id_1)
        _create_test_document(storage._conn, doc_id_2)
        storage.store_embeddings([
            make_chunk_embedding(doc_id_1, 0, "Searchable term in doc one"),
            make_chunk_embedding(doc_id_2, 0, "Searchable term in doc two"),
        ])

        retriever = FTSRetriever(storage)
        results = retriever.retrieve("Searchable", doc_ids=[doc_id_1])

        assert len(results) == 1
        assert results[0].chunk.doc_id == doc_id_1

    def test_raises_fts_query_error(self, storage: EmbeddingStorage) -> None:
        """retrieve() propagates FTSQueryError for bad syntax."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Some text"),
        ])

        retriever = FTSRetriever(storage)
        with pytest.raises(FTSQueryError):
            retriever.retrieve('"unbalanced')

    def test_empty_results(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns empty list for no matches."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Some text"),
        ])

        retriever = FTSRetriever(storage)
        results = retriever.retrieve("xylophone")

        assert results == []
