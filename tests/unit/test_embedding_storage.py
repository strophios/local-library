"""Unit tests for embedding storage operations."""

import sqlite3
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from local_library.core.models import DocumentStatus, EmbeddingStatus
from local_library.core.storage import (
    create_document,
    get_connection,
    get_document_by_id,
    init_schema,
    update_document_status,
)
from local_library.core.vec_extension import is_vec_available
from local_library.embeddings.base import Chunk, ChunkEmbedding
from local_library.embeddings.storage import (
    EmbeddingStorage,
    get_documents_needing_embedding,
    update_embedding_status,
)

# Skip all tests in this module if sqlite-vec is not available
pytestmark = pytest.mark.skipif(
    not is_vec_available(),
    reason="sqlite-vec extension not available",
)


@pytest.fixture
def db_conn(temp_dir: Path) -> sqlite3.Connection:
    """Provide an initialized database connection for testing."""
    db_path = temp_dir / "test.db"
    conn = get_connection(db_path)
    init_schema(conn)
    return conn


@pytest.fixture
def storage(db_conn: sqlite3.Connection) -> EmbeddingStorage:
    """Provide an EmbeddingStorage instance."""
    return EmbeddingStorage(db_conn)


@pytest.fixture
def sample_doc(db_conn: sqlite3.Connection) -> tuple:
    """Create a sample document and return (doc, doc_id)."""
    doc = create_document(db_conn, "/test.pdf", "hash123", "/storage/hash123.pdf")
    update_document_status(
        db_conn, doc.id, DocumentStatus.READY, extracted_path="/extracted/hash123.md"
    )
    return doc, doc.id


def make_chunk_embedding(doc_id, index: int = 0, text: str = "Test text") -> ChunkEmbedding:
    """Helper to create a ChunkEmbedding."""
    chunk = Chunk.create(doc_id, index, text)
    embedding = np.random.randn(768).astype(np.float32)
    return ChunkEmbedding(chunk=chunk, embedding=embedding)


class TestEmbeddingStorage:
    """Tests for EmbeddingStorage class."""

    def test_store_single_embedding(self, storage: EmbeddingStorage, sample_doc) -> None:
        """Should store a single chunk and embedding."""
        _, doc_id = sample_doc
        emb = make_chunk_embedding(doc_id)

        storage.store_embeddings([emb])

        assert storage.get_chunk_count(doc_id) == 1

    def test_store_multiple_embeddings(self, storage: EmbeddingStorage, sample_doc) -> None:
        """Should store multiple chunks and embeddings."""
        _, doc_id = sample_doc
        embeddings = [
            make_chunk_embedding(doc_id, 0, "First chunk"),
            make_chunk_embedding(doc_id, 1, "Second chunk"),
            make_chunk_embedding(doc_id, 2, "Third chunk"),
        ]

        storage.store_embeddings(embeddings)

        assert storage.get_chunk_count(doc_id) == 3

    def test_store_empty_list(self, storage: EmbeddingStorage) -> None:
        """Storing empty list should not raise."""
        storage.store_embeddings([])  # Should not raise

    def test_get_chunks_by_document(self, storage: EmbeddingStorage, sample_doc) -> None:
        """Should retrieve chunks in order."""
        _, doc_id = sample_doc
        embeddings = [
            make_chunk_embedding(doc_id, 0, "First"),
            make_chunk_embedding(doc_id, 1, "Second"),
        ]
        storage.store_embeddings(embeddings)

        chunks = storage.get_chunks_by_document(doc_id)

        assert len(chunks) == 2
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1
        assert chunks[0].text == "First"
        assert chunks[1].text == "Second"

    def test_has_embeddings_true(self, storage: EmbeddingStorage, sample_doc) -> None:
        """has_embeddings should return True when embeddings exist."""
        _, doc_id = sample_doc
        storage.store_embeddings([make_chunk_embedding(doc_id)])

        assert storage.has_embeddings(doc_id) is True

    def test_has_embeddings_false(self, storage: EmbeddingStorage) -> None:
        """has_embeddings should return False when no embeddings."""
        assert storage.has_embeddings(uuid4()) is False

    def test_delete_by_document(self, storage: EmbeddingStorage, sample_doc) -> None:
        """Should delete all chunks for a document."""
        _, doc_id = sample_doc
        embeddings = [
            make_chunk_embedding(doc_id, 0, "First"),
            make_chunk_embedding(doc_id, 1, "Second"),
        ]
        storage.store_embeddings(embeddings)

        deleted = storage.delete_by_document(doc_id)

        assert deleted == 2
        assert storage.get_chunk_count(doc_id) == 0

    def test_delete_nonexistent_document(self, storage: EmbeddingStorage) -> None:
        """Deleting nonexistent document should return 0."""
        deleted = storage.delete_by_document(uuid4())
        assert deleted == 0


class TestVectorSearch:
    """Tests for vector similarity search."""

    def test_search_returns_results(self, storage: EmbeddingStorage, sample_doc) -> None:
        """search_similar should return matching chunks."""
        _, doc_id = sample_doc

        # Store a chunk with known embedding
        chunk = Chunk.create(doc_id, 0, "Machine learning is fascinating")
        embedding = np.random.randn(768).astype(np.float32)
        storage.store_embeddings([ChunkEmbedding(chunk=chunk, embedding=embedding)])

        # Search with the same embedding
        results = storage.search_similar(embedding, limit=10)

        assert len(results) == 1
        assert results[0][0].chunk_id == chunk.chunk_id

    def test_search_returns_distance(self, storage: EmbeddingStorage, sample_doc) -> None:
        """search_similar should return distance for each result."""
        _, doc_id = sample_doc
        chunk = Chunk.create(doc_id, 0, "Test")
        embedding = np.random.randn(768).astype(np.float32)
        storage.store_embeddings([ChunkEmbedding(chunk=chunk, embedding=embedding)])

        results = storage.search_similar(embedding, limit=10)

        _, distance = results[0]
        assert isinstance(distance, float)
        # Same vector should have very small distance
        assert distance < 0.01

    def test_search_respects_limit(self, storage: EmbeddingStorage, sample_doc) -> None:
        """search_similar should respect limit parameter."""
        _, doc_id = sample_doc
        embeddings = [make_chunk_embedding(doc_id, i, f"Chunk {i}") for i in range(10)]
        storage.store_embeddings(embeddings)

        query = np.random.randn(768).astype(np.float32)
        results = storage.search_similar(query, limit=5)

        assert len(results) == 5

    def test_search_filter_by_doc_ids(
        self, storage: EmbeddingStorage, db_conn: sqlite3.Connection
    ) -> None:
        """search_similar should filter by doc_ids when provided."""
        # Create two documents
        doc1 = create_document(db_conn, "/test1.pdf", "hash1", "/storage/1.pdf")
        doc2 = create_document(db_conn, "/test2.pdf", "hash2", "/storage/2.pdf")

        # Store embeddings for both
        storage.store_embeddings([make_chunk_embedding(doc1.id, 0, "Doc 1 chunk")])
        storage.store_embeddings([make_chunk_embedding(doc2.id, 0, "Doc 2 chunk")])

        query = np.random.randn(768).astype(np.float32)

        # Search only in doc1
        results = storage.search_similar(query, limit=10, doc_ids=[doc1.id])

        assert len(results) == 1
        assert results[0][0].doc_id == doc1.id

    def test_search_empty_database(self, storage: EmbeddingStorage) -> None:
        """search_similar on empty database should return empty list."""
        query = np.random.randn(768).astype(np.float32)
        results = storage.search_similar(query, limit=10)

        assert results == []


class TestEmbeddingStatusFunctions:
    """Tests for embedding status helper functions."""

    def test_update_embedding_status(self, db_conn: sqlite3.Connection, sample_doc) -> None:
        """update_embedding_status should update document's embedding_status."""
        doc, doc_id = sample_doc

        update_embedding_status(db_conn, doc_id, EmbeddingStatus.CURRENT)

        updated = get_document_by_id(db_conn, doc_id)
        assert updated is not None, "Document should exist"
        assert updated.embedding_status == EmbeddingStatus.CURRENT

    def test_get_documents_needing_embedding_pending(self, db_conn: sqlite3.Connection) -> None:
        """Should return documents with PENDING embedding status."""
        # Create a READY document (default embedding_status is PENDING)
        doc = create_document(db_conn, "/test.pdf", "hash123", "/storage/hash123.pdf")
        update_document_status(
            db_conn, doc.id, DocumentStatus.READY, extracted_path="/extracted/test.md"
        )

        doc_ids = get_documents_needing_embedding(db_conn)

        assert doc.id in doc_ids

    def test_get_documents_needing_embedding_excludes_current(
        self, db_conn: sqlite3.Connection
    ) -> None:
        """Should exclude documents with CURRENT embedding status."""
        doc = create_document(db_conn, "/test.pdf", "hash123", "/storage/hash123.pdf")
        update_document_status(
            db_conn, doc.id, DocumentStatus.READY, extracted_path="/extracted/test.md"
        )
        update_embedding_status(db_conn, doc.id, EmbeddingStatus.CURRENT)

        doc_ids = get_documents_needing_embedding(db_conn)

        assert doc.id not in doc_ids

    def test_get_documents_needing_embedding_excludes_non_ready(
        self, db_conn: sqlite3.Connection
    ) -> None:
        """Should exclude documents that are not READY status."""
        # Create a PENDING document (not ready for embedding)
        doc = create_document(db_conn, "/test.pdf", "hash123", "/storage/hash123.pdf")
        # Status is PENDING, not READY

        doc_ids = get_documents_needing_embedding(db_conn)

        assert doc.id not in doc_ids
