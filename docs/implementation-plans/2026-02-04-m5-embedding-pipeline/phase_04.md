## Phase 4: Embedding Computation

**Goal:** nomic-embed-text-v1.5 integration via sentence-transformers.

This phase implements `NomicEmbedder` that wraps sentence-transformers for computing 768-dimensional embeddings. The embedder handles task prefixes (`search_document:` for chunks, `search_query:` for queries) and supports lazy model loading.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create NomicEmbedder implementation

**Files:**
- Create: `src/local_library/embeddings/nomic.py`

**Step 1: Create the nomic embedder module**

Create `src/local_library/embeddings/nomic.py`:

```python
"""nomic-embed-text-v1.5 embedding computation via sentence-transformers."""

# pattern: Imperative Shell (requires model loading and GPU/CPU inference)

from typing import Callable

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
            for chunk, embedding in zip(chunks, embeddings):
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
```

**Step 2: Verify the embedder imports**

Run: `uv run python -c "
from local_library.embeddings.nomic import NomicEmbedder
print('NomicEmbedder imported successfully')
embedder = NomicEmbedder(lazy_load=True)
print(f'Lazy loaded: {not embedder.is_loaded}')
print(f'Embedding dimension: {embedder.embedding_dimension}')
"
`

Expected:
```
NomicEmbedder imported successfully
Lazy loaded: True
Embedding dimension: 768
```

**Step 3: Commit**

```bash
git add src/local_library/embeddings/nomic.py
git commit -m "feat(embeddings): add NomicEmbedder with sentence-transformers integration"
```
<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Add NomicEmbedder to module exports

**Files:**
- Modify: `src/local_library/embeddings/__init__.py`

**Step 1: Add lazy import for NomicEmbedder**

Add this elif clause after the estimate_token_count import:

```python
    elif name == "NomicEmbedder":
        from local_library.embeddings.nomic import NomicEmbedder

        return NomicEmbedder
```

And update `__all__`:

```python
__all__ = [
    # Protocols
    "Chunker",
    "Embedder",
    # Data models
    "Chunk",
    "ChunkEmbedding",
    # Implementations
    "MarkdownChunker",
    "NomicEmbedder",
    # Utilities
    "estimate_token_count",
]
```

**Step 2: Verify imports work**

Run: `uv run python -c "
from local_library.embeddings import NomicEmbedder
print(f'NomicEmbedder: {NomicEmbedder}')
"
`

Expected: Import succeeds without error

**Step 3: Commit**

```bash
git add src/local_library/embeddings/__init__.py
git commit -m "feat(embeddings): export NomicEmbedder from module"
```
<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Add unit tests for NomicEmbedder

**Files:**
- Create: `tests/unit/test_nomic_embedder.py`

**Step 1: Create test file**

Create `tests/unit/test_nomic_embedder.py`:

```python
"""Unit tests for NomicEmbedder.

Note: Tests that require actual model loading are marked with @pytest.mark.slow
and can be skipped in CI with `pytest -m "not slow"`.
"""

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
        mock_model.encode = MagicMock(
            return_value=np.random.randn(768).astype(np.float32)
        )

        embedder_with_mock.embed_query("What is machine learning?")

        call_args = mock_model.encode.call_args
        text = call_args[0][0]  # First positional arg
        assert text == "search_query: What is machine learning?"

    def test_embed_query_returns_1d_array(
        self, embedder_with_mock: NomicEmbedder, mock_model
    ) -> None:
        """embed_query should return a 1D array of shape (768,)."""
        mock_model.encode = MagicMock(
            return_value=np.random.randn(768).astype(np.float32)
        )

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

    def test_embeddings_are_float32(
        self, embedder_with_mock: NomicEmbedder
    ) -> None:
        """All returned embeddings should be float32."""
        chunks = [Chunk.create(uuid4(), 0, "Test")]

        results = embedder_with_mock.embed_chunks(chunks)

        assert results[0].embedding.dtype == np.float32


class TestNomicEmbedderErrorHandling:
    """Tests for error handling."""

    def test_model_load_failure_raises_embedding_error(self) -> None:
        """Failed model loading should raise EmbeddingError."""
        with patch(
            "local_library.embeddings.nomic.SentenceTransformer",
            side_effect=Exception("Model not found"),
        ):
            embedder = NomicEmbedder(lazy_load=True)

            with pytest.raises(EmbeddingError) as exc_info:
                embedder._load_model()

            assert exc_info.value.code == ErrorCode.EMBEDDING_MODEL_LOAD_FAILED

    def test_encode_failure_raises_embedding_error(self) -> None:
        """Failed encoding should raise EmbeddingError."""
        embedder = NomicEmbedder(lazy_load=True)
        mock_model = MagicMock()
        mock_model.encode = MagicMock(side_effect=Exception("CUDA out of memory"))
        embedder._model = mock_model

        chunks = [Chunk.create(uuid4(), 0, "Test")]

        with pytest.raises(EmbeddingError) as exc_info:
            embedder.embed_chunks(chunks)

        assert exc_info.value.code == ErrorCode.EMBEDDING_COMPUTATION_FAILED


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

    def test_normalized_embeddings_have_unit_norm(
        self, real_embedder: NomicEmbedder
    ) -> None:
        """Normalized embeddings should have L2 norm close to 1."""
        embedding = real_embedder.embed_query("Test query")

        norm = np.linalg.norm(embedding)
        assert abs(norm - 1.0) < 0.01  # Allow small floating point error

    def test_similar_texts_have_similar_embeddings(
        self, real_embedder: NomicEmbedder
    ) -> None:
        """Semantically similar texts should have similar embeddings."""
        emb1 = real_embedder.embed_query("machine learning algorithms")
        emb2 = real_embedder.embed_query("ML models and algorithms")
        emb3 = real_embedder.embed_query("cooking recipes for dinner")

        # Cosine similarity (for normalized vectors, this is just dot product)
        sim_related = np.dot(emb1, emb2)
        sim_unrelated = np.dot(emb1, emb3)

        # Related queries should be more similar
        assert sim_related > sim_unrelated
```

**Step 2: Add pytest marker for slow tests**

Update `pyproject.toml` to add the slow marker. Find the markers list and add:

```toml
    "slow: Slow tests that load ML models or process large data",
```

**Step 3: Run the tests (skip slow ones)**

Run: `uv run pytest tests/unit/test_nomic_embedder.py -v -m "not slow"`
Expected: All non-slow tests pass

**Step 4: Commit**

```bash
git add tests/unit/test_nomic_embedder.py pyproject.toml
git commit -m "test: add unit tests for NomicEmbedder with mock and integration tests"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

## Phase 4 Verification

After completing all tasks, verify the phase is complete:

**Run all Phase 4 tests (excluding slow):**
```bash
uv run pytest tests/unit/test_nomic_embedder.py -v -m "not slow"
```

**Verify embedder works with mock:**
```bash
uv run python -c "
from uuid import uuid4
import numpy as np
from local_library.embeddings import NomicEmbedder, Chunk

# Create embedder with lazy loading
embedder = NomicEmbedder(lazy_load=True)
print(f'Embedder created, model loaded: {embedder.is_loaded}')

# Mock the model for testing without download
from unittest.mock import MagicMock
mock_model = MagicMock()
mock_model.encode = lambda texts, **kw: np.random.randn(
    len(texts) if isinstance(texts, list) else 1, 768
).astype(np.float32)
embedder._model = mock_model

# Test chunk embedding
chunks = [
    Chunk.create(uuid4(), 0, 'First document chunk'),
    Chunk.create(uuid4(), 1, 'Second document chunk'),
]
results = embedder.embed_chunks(chunks)
print(f'Embedded {len(results)} chunks')
print(f'First embedding shape: {results[0].embedding.shape}')

# Test query embedding
query_emb = embedder.embed_query('What is machine learning?')
print(f'Query embedding shape: {query_emb.shape}')
"
```

**Done when:**
- NomicEmbedder implements Embedder protocol
- `embed_chunks()` applies `search_document:` prefix
- `embed_query()` applies `search_query:` prefix
- Lazy loading defers model load until first use
- All tests pass (non-slow)
- Module exports work via lazy imports
