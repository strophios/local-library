"""Unit tests for embedding data models and protocols."""

from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pytest

from local_library.embeddings.base import Chunk, ChunkEmbedding, Chunker, Embedder


class TestChunk:
    """Tests for Chunk dataclass."""

    def test_create_chunk_with_factory(self) -> None:
        """Chunk.create should generate ID and timestamp."""
        doc_id = uuid4()
        chunk = Chunk.create(
            doc_id=doc_id,
            chunk_index=0,
            text="Test content",
            section="Introduction",
        )

        assert chunk.doc_id == doc_id
        assert chunk.chunk_index == 0
        assert chunk.text == "Test content"
        assert chunk.section == "Introduction"
        assert chunk.chunk_id is not None
        assert len(chunk.chunk_id) == 36  # UUID format
        assert chunk.created_at is not None

    def test_chunk_is_frozen(self) -> None:
        """Chunk should be immutable."""
        chunk = Chunk.create(uuid4(), 0, "Test")

        with pytest.raises(AttributeError):
            chunk.text = "Modified"  # type: ignore

    def test_chunk_optional_position_fields(self) -> None:
        """Chunk should accept optional char_start and char_end."""
        chunk = Chunk.create(
            doc_id=uuid4(),
            chunk_index=0,
            text="Test",
            char_start=100,
            char_end=200,
        )

        assert chunk.char_start == 100
        assert chunk.char_end == 200

    def test_chunk_default_section_is_empty(self) -> None:
        """Chunk.create should default section to empty string."""
        chunk = Chunk.create(uuid4(), 0, "Test")

        assert chunk.section == ""

    def test_chunk_created_at_is_utc(self) -> None:
        """Chunk.create should set UTC timestamp."""
        before = datetime.now(timezone.utc)
        chunk = Chunk.create(uuid4(), 0, "Test")
        after = datetime.now(timezone.utc)

        assert before <= chunk.created_at <= after


class TestChunkEmbedding:
    """Tests for ChunkEmbedding dataclass."""

    def test_chunk_embedding_stores_vector(self) -> None:
        """ChunkEmbedding should store chunk and embedding."""
        chunk = Chunk.create(uuid4(), 0, "Test")
        embedding = np.random.randn(768).astype(np.float32)

        chunk_emb = ChunkEmbedding(chunk=chunk, embedding=embedding)

        assert chunk_emb.chunk == chunk
        assert np.array_equal(chunk_emb.embedding, embedding)

    def test_chunk_embedding_convenience_properties(self) -> None:
        """ChunkEmbedding should provide chunk_id and doc_id properties."""
        doc_id = uuid4()
        chunk = Chunk.create(doc_id, 0, "Test")
        embedding = np.random.randn(768).astype(np.float32)

        chunk_emb = ChunkEmbedding(chunk=chunk, embedding=embedding)

        assert chunk_emb.chunk_id == chunk.chunk_id
        assert chunk_emb.doc_id == doc_id

    def test_chunk_embedding_validates_dimensions(self) -> None:
        """ChunkEmbedding should reject non-768-dimensional vectors."""
        chunk = Chunk.create(uuid4(), 0, "Test")
        wrong_embedding = np.random.randn(512).astype(np.float32)

        with pytest.raises(ValueError, match="768-dimensional"):
            ChunkEmbedding(chunk=chunk, embedding=wrong_embedding)

    def test_chunk_embedding_is_frozen(self) -> None:
        """ChunkEmbedding should be immutable."""
        chunk = Chunk.create(uuid4(), 0, "Test")
        embedding = np.random.randn(768).astype(np.float32)
        chunk_emb = ChunkEmbedding(chunk=chunk, embedding=embedding)

        with pytest.raises(AttributeError):
            chunk_emb.embedding = np.zeros(768)  # type: ignore


class TestProtocols:
    """Tests for Chunker and Embedder protocols."""

    def test_chunker_is_runtime_checkable(self) -> None:
        """Chunker protocol should support isinstance checks."""

        class MockChunker:
            def chunk(self, doc_id, text):
                return []

        assert isinstance(MockChunker(), Chunker)

    def test_embedder_is_runtime_checkable(self) -> None:
        """Embedder protocol should support isinstance checks."""

        class MockEmbedder:
            def embed_chunks(self, chunks):
                return []

            def embed_query(self, query):
                return np.zeros(768, dtype=np.float32)

        assert isinstance(MockEmbedder(), Embedder)

    def test_non_conforming_class_not_chunker(self) -> None:
        """Class without chunk method should not be Chunker."""

        class NotAChunker:
            pass

        assert not isinstance(NotAChunker(), Chunker)

    def test_non_conforming_class_not_embedder(self) -> None:
        """Class without embed methods should not be Embedder."""

        class NotAnEmbedder:
            def embed_chunks(self, chunks):
                return []
            # Missing embed_query

        assert not isinstance(NotAnEmbedder(), Embedder)
