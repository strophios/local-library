"""nomic-embed-text-v1.5 embedding computation via sentence-transformers."""

# pattern: Imperative Shell (requires model loading and GPU/CPU inference)

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from local_library.core.errors import EmbeddingError, ErrorCode
from local_library.embeddings.base import Chunk, ChunkEmbedding


class NomicEmbedder:
    """Embedder using nomic-embed-text-v1.5 via sentence-transformers.

    Computes 768-dimensional embeddings with task-specific prefixes:
    - 'search_document:' for document chunks (RAG indexing)
    - 'search_query:' for user queries (RAG retrieval)

    Attributes:
        model_name: HuggingFace model identifier
        batch_size: Number of texts to embed at once
        normalize: Whether to L2-normalize embeddings
        device: Computation device ('cuda', 'cpu', or None for auto)
    """

    # nomic-embed-text requires task prefixes for optimal performance
    DOCUMENT_PREFIX = "search_document: "
    QUERY_PREFIX = "search_query: "

    def __init__(
        self,
        model_name: str = "nomic-ai/nomic-embed-text-v1.5",
        batch_size: int = 32,
        normalize: bool = True,
        device: str | None = None,
        lazy_load: bool = True,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        """Initialize the embedder.

        Args:
            model_name: HuggingFace model identifier
                       (default: nomic-ai/nomic-embed-text-v1.5)
            batch_size: Texts per batch (default: 32)
            normalize: L2-normalize embeddings (default: True, recommended for RAG)
            device: Computation device (None for auto-detection)
            lazy_load: Defer model loading until first embed call (default: True)
            progress_callback: Optional callback(current, total) for progress tracking
        """
        self.model_name = model_name
        self.batch_size = batch_size
        self.normalize = normalize
        self.device = device
        self.progress_callback = progress_callback

        self._model = None
        if not lazy_load:
            self._load_model()

    def _load_model(self) -> None:
        """Load the sentence-transformers model.

        Raises:
            EmbeddingError: If model loading fails
        """
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self.model_name,
                trust_remote_code=True,  # Required for nomic models
                device=self.device,
            )
        except ImportError as e:
            raise EmbeddingError(
                "sentence-transformers not installed",
                ErrorCode.EMBEDDING_MODEL_LOAD_FAILED,
            ) from e
        except Exception as e:
            raise EmbeddingError(
                f"failed to load embedding model: {e}",
                ErrorCode.EMBEDDING_MODEL_LOAD_FAILED,
                details={"model_name": self.model_name},
            ) from e

    def embed_chunks(self, chunks: list[Chunk]) -> list[ChunkEmbedding]:
        """Compute embeddings for document chunks.

        Uses 'search_document:' prefix for RAG indexing.

        Args:
            chunks: Chunks to embed

        Returns:
            ChunkEmbedding objects with 768-dimensional vectors

        Raises:
            EmbeddingError: If embedding computation fails
        """
        if not chunks:
            return []

        self._load_model()

        try:
            # Prepend document prefix to each chunk
            texts = [self.DOCUMENT_PREFIX + chunk.text for chunk in chunks]

            # Compute embeddings
            embeddings = self._model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=self.normalize,
                show_progress_bar=False,  # We handle progress ourselves
                convert_to_numpy=True,
            )

            # Report progress if callback provided
            if self.progress_callback:
                self.progress_callback(len(chunks), len(chunks))

            # Wrap in ChunkEmbedding objects
            results = []
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                chunk_emb = ChunkEmbedding(
                    chunk=chunk,
                    embedding=embedding.astype(np.float32),
                )
                results.append(chunk_emb)

            return results

        except Exception as e:
            raise EmbeddingError(
                f"failed to compute chunk embeddings: {e}",
                ErrorCode.EMBEDDING_COMPUTATION_FAILED,
                details={"chunk_count": len(chunks)},
            ) from e

    def embed_query(self, query: str) -> NDArray[np.float32]:
        """Compute embedding for a search query.

        Uses 'search_query:' prefix for RAG retrieval.

        Args:
            query: Search query text

        Returns:
            768-dimensional embedding vector

        Raises:
            EmbeddingError: If embedding computation fails
        """
        self._load_model()

        try:
            # Prepend query prefix
            text = self.QUERY_PREFIX + query

            # Compute embedding
            embedding = self._model.encode(
                text,
                normalize_embeddings=self.normalize,
                convert_to_numpy=True,
            )

            return embedding.astype(np.float32)

        except Exception as e:
            raise EmbeddingError(
                f"failed to compute query embedding: {e}",
                ErrorCode.EMBEDDING_COMPUTATION_FAILED,
            ) from e

    def embed_texts(self, texts: list[str], prefix: str = "") -> NDArray[np.float32]:
        """Compute embeddings for arbitrary texts.

        Lower-level method for custom use cases. For standard RAG,
        prefer embed_chunks() and embed_query().

        Args:
            texts: Texts to embed
            prefix: Optional prefix to prepend to all texts

        Returns:
            Array of shape (len(texts), 768)

        Raises:
            EmbeddingError: If embedding computation fails
        """
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, 768)

        self._load_model()

        try:
            # Apply prefix if provided
            if prefix:
                texts = [prefix + t for t in texts]

            embeddings = self._model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=self.normalize,
                show_progress_bar=False,
                convert_to_numpy=True,
            )

            return embeddings.astype(np.float32)

        except Exception as e:
            raise EmbeddingError(
                f"failed to compute embeddings: {e}",
                ErrorCode.EMBEDDING_COMPUTATION_FAILED,
                details={"text_count": len(texts)},
            ) from e

    @property
    def is_loaded(self) -> bool:
        """Check if model is currently loaded."""
        return self._model is not None

    @property
    def embedding_dimension(self) -> int:
        """Get the embedding dimension (always 768 for nomic-embed-text-v1.5)."""
        return 768
