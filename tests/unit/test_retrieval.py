"""Tests for retrieval: FTS5 search, retrievers, and hybrid fusion."""

# pattern: Imperative Shell

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest

from local_library.core.errors import FTSQueryError
from local_library.core.storage import get_connection, init_schema
from local_library.core.vec_extension import is_vec_available
from local_library.embeddings.base import Chunk, ChunkEmbedding
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
def temp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory."""
    return tmp_path


@pytest.fixture
def storage(temp_dir: Path) -> EmbeddingStorage:
    """Provide an EmbeddingStorage with initialized schema."""
    db_path = temp_dir / "test.db"
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
