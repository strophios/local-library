"""Unit tests for NomicEmbedder.

Note: Tests that require actual model loading are marked with @pytest.mark.slow
and can be skipped in CI with `pytest -m "not slow"`.
"""

# pattern: N/A (test file)

from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from local_library.core.errors import EmbeddingError, ErrorCode
from local_library.embeddings.base import Chunk, ChunkEmbedding, Embedder
from local_library.embeddings.nomic import NomicEmbedder


class TestNomicEmbedderProtocol:
    """Tests for protocol compliance and basic properties."""

    def test_implements_embedder_protocol(self) -> None:
        """NomicEmbedder should implement Embedder protocol."""
        embedder = NomicEmbedder(lazy_load=True)
        assert isinstance(embedder, Embedder)

    def test_lazy_load_defers_model_loading(self) -> None:
        """With lazy_load=True, model should not load until first embed."""
        embedder = NomicEmbedder(lazy_load=True)
        assert not embedder.is_loaded

    def test_embedding_dimension_is_768(self) -> None:
        """embedding_dimension should always be 768."""
        embedder = NomicEmbedder(lazy_load=True)
        assert embedder.embedding_dimension == 768

    def test_default_prefixes(self) -> None:
        """Should have correct task prefixes."""
        assert NomicEmbedder.DOCUMENT_PREFIX == "search_document: "
        assert NomicEmbedder.QUERY_PREFIX == "search_query: "


class TestNomicEmbedderWithMocks:
    """Tests using mocked sentence-transformers."""

    @pytest.fixture
    def mock_model(self):
        """Provide a mock SentenceTransformer."""
        model = MagicMock()
        # encode() returns numpy arrays of shape (n, 768)
        model.encode = MagicMock(
            side_effect=lambda texts, **kwargs: np.random.randn(
                len(texts) if isinstance(texts, list) else 1, 768
            ).astype(np.float32)
        )
        return model

    @pytest.fixture
    def embedder_with_mock(self, mock_model):
        """Provide an embedder with mocked model."""
        embedder = NomicEmbedder(lazy_load=True)
        embedder._model = mock_model
        return embedder

    def test_embed_chunks_returns_chunk_embeddings(
        self, embedder_with_mock: NomicEmbedder, mock_model
    ) -> None:
        """embed_chunks should return ChunkEmbedding objects."""
        chunks = [
            Chunk.create(uuid4(), 0, "First chunk"),
            Chunk.create(uuid4(), 1, "Second chunk"),
        ]

        results = embedder_with_mock.embed_chunks(chunks)

        assert len(results) == 2
        assert all(isinstance(r, ChunkEmbedding) for r in results)

    def test_embed_chunks_preserves_chunk_association(
        self, embedder_with_mock: NomicEmbedder
    ) -> None:
        """Each ChunkEmbedding should reference its source chunk."""
        doc_id = uuid4()
        chunks = [
            Chunk.create(doc_id, 0, "Chunk A"),
            Chunk.create(doc_id, 1, "Chunk B"),
        ]

        results = embedder_with_mock.embed_chunks(chunks)

        assert results[0].chunk == chunks[0]
        assert results[1].chunk == chunks[1]

    def test_embed_chunks_applies_document_prefix(
        self, embedder_with_mock: NomicEmbedder, mock_model
    ) -> None:
        """embed_chunks should prepend 'search_document: ' to texts."""
        chunks = [Chunk.create(uuid4(), 0, "Test text")]

        embedder_with_mock.embed_chunks(chunks)

        # Check the texts passed to encode()
        call_args = mock_model.encode.call_args
        texts = call_args[0][0]  # First positional arg
        assert texts[0] == "search_document: Test text"

    def test_embed_query_applies_query_prefix(
        self, embedder_with_mock: NomicEmbedder, mock_model
    ) -> None:
        """embed_query should prepend 'search_query: ' to text."""
        # For single text, encode returns shape (768,)
        mock_model.encode = MagicMock(return_value=np.random.randn(768).astype(np.float32))

        embedder_with_mock.embed_query("What is machine learning?")

        call_args = mock_model.encode.call_args
        text = call_args[0][0]  # First positional arg
        assert text == "search_query: What is machine learning?"

    def test_embed_query_returns_1d_array(
        self, embedder_with_mock: NomicEmbedder, mock_model
    ) -> None:
        """embed_query should return a 1D array of shape (768,)."""
        mock_model.encode = MagicMock(return_value=np.random.randn(768).astype(np.float32))

        result = embedder_with_mock.embed_query("Test query")

        assert result.shape == (768,)
        assert result.dtype == np.float32

    def test_embed_chunks_empty_list(self, embedder_with_mock: NomicEmbedder) -> None:
        """embed_chunks with empty list should return empty list."""
        results = embedder_with_mock.embed_chunks([])
        assert results == []

    def test_embed_texts_with_custom_prefix(
        self, embedder_with_mock: NomicEmbedder, mock_model
    ) -> None:
        """embed_texts should apply custom prefix to all texts."""
        embedder_with_mock.embed_texts(["text1", "text2"], prefix="clustering: ")

        call_args = mock_model.encode.call_args
        texts = call_args[0][0]
        assert texts == ["clustering: text1", "clustering: text2"]

    def test_embed_texts_empty_list(self, embedder_with_mock: NomicEmbedder) -> None:
        """embed_texts with empty list should return empty array."""
        result = embedder_with_mock.embed_texts([])
        assert result.shape == (0, 768)

    def test_embeddings_are_float32(self, embedder_with_mock: NomicEmbedder) -> None:
        """All returned embeddings should be float32."""
        chunks = [Chunk.create(uuid4(), 0, "Test")]

        results = embedder_with_mock.embed_chunks(chunks)

        assert results[0].embedding.dtype == np.float32


class TestNomicEmbedderErrorHandling:
    """Tests for error handling."""

    def test_model_load_failure_raises_embedding_error(self) -> None:
        """Failed model loading should raise EmbeddingError."""
        with patch(
            "sentence_transformers.SentenceTransformer",
            side_effect=Exception("Model not found"),
        ):
            embedder = NomicEmbedder(lazy_load=True)

            with pytest.raises(EmbeddingError) as exc_info:
                embedder._load_model()

            error = exc_info.value
            assert isinstance(error, EmbeddingError)  # Type guard
            assert error.code == ErrorCode.EMBEDDING_MODEL_LOAD_FAILED

    def test_encode_failure_raises_embedding_error(self) -> None:
        """Failed encoding should raise EmbeddingError."""
        embedder = NomicEmbedder(lazy_load=True)
        mock_model = MagicMock()
        mock_model.encode = MagicMock(side_effect=Exception("CUDA out of memory"))
        embedder._model = mock_model

        chunks = [Chunk.create(uuid4(), 0, "Test")]

        with pytest.raises(EmbeddingError) as exc_info:
            embedder.embed_chunks(chunks)

        error = exc_info.value
        assert isinstance(error, EmbeddingError)  # Type guard
        assert error.code == ErrorCode.EMBEDDING_COMPUTATION_FAILED


# Mark slow tests that actually load the model
@pytest.mark.slow
class TestNomicEmbedderIntegration:
    """Integration tests that load the actual model.

    These tests are slow and download ~262 MB on first run.
    Skip with: pytest -m "not slow"
    """

    @pytest.fixture(scope="class")
    def real_embedder(self):
        """Provide a real embedder (shared across tests in class)."""
        return NomicEmbedder(lazy_load=False)

    def test_real_embedding_shape(self, real_embedder: NomicEmbedder) -> None:
        """Real embeddings should have correct shape."""
        chunks = [Chunk.create(uuid4(), 0, "This is a test document about machine learning.")]

        results = real_embedder.embed_chunks(chunks)

        assert len(results) == 1
        assert results[0].embedding.shape == (768,)

    def test_real_query_embedding(self, real_embedder: NomicEmbedder) -> None:
        """Real query embedding should have correct shape."""
        embedding = real_embedder.embed_query("What is machine learning?")

        assert embedding.shape == (768,)

    def test_normalized_embeddings_have_unit_norm(self, real_embedder: NomicEmbedder) -> None:
        """Normalized embeddings should have L2 norm close to 1."""
        embedding = real_embedder.embed_query("Test query")

        norm = np.linalg.norm(embedding)
        assert abs(norm - 1.0) < 0.01  # Allow small floating point error

    def test_similar_texts_have_similar_embeddings(self, real_embedder: NomicEmbedder) -> None:
        """Semantically similar texts should have similar embeddings."""
        emb1 = real_embedder.embed_query("machine learning algorithms")
        emb2 = real_embedder.embed_query("ML models and algorithms")
        emb3 = real_embedder.embed_query("cooking recipes for dinner")

        # Cosine similarity (for normalized vectors, this is just dot product)
        sim_related = np.dot(emb1, emb2)
        sim_unrelated = np.dot(emb1, emb3)

        # Related queries should be more similar
        assert sim_related > sim_unrelated
