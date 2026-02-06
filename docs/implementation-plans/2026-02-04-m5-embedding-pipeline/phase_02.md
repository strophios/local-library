## Phase 2: Core Data Models and Protocols

**Goal:** Define the embedding domain's data structures and interfaces.

This phase establishes the `embeddings/` module structure with protocols for chunking and embedding, plus frozen dataclasses for Chunk and ChunkEmbedding. These form the contract that later phases implement.

---

<!-- START_TASK_1 -->
### Task 1: Create embeddings module structure

**Files:**
- Create: `src/local_library/embeddings/__init__.py`
- Create: `src/local_library/embeddings/base.py`

**Step 1: Create the embeddings directory and __init__.py**

Create `src/local_library/embeddings/__init__.py`:

```python
"""Embeddings module - chunking, embedding computation, and vector storage."""

# Lazy imports to prevent circular import on package initialization
# (follows same pattern as ingestion module)


def __getattr__(name: str) -> object:
    """Lazy-load embeddings submodules to avoid circular imports."""
    if name == "Chunker":
        from local_library.embeddings.base import Chunker

        return Chunker
    elif name == "Embedder":
        from local_library.embeddings.base import Embedder

        return Embedder
    elif name == "Chunk":
        from local_library.embeddings.base import Chunk

        return Chunk
    elif name == "ChunkEmbedding":
        from local_library.embeddings.base import ChunkEmbedding

        return ChunkEmbedding
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Protocols
    "Chunker",
    "Embedder",
    # Data models
    "Chunk",
    "ChunkEmbedding",
]
```

**Step 2: Verify module structure**

Run: `uv run python -c "import local_library.embeddings; print('embeddings module created')"`
Expected: `embeddings module created`

**Step 3: Commit**

```bash
git add src/local_library/embeddings/__init__.py
git commit -m "feat(embeddings): create embeddings module with lazy imports"
```
<!-- END_TASK_1 -->

---

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Define Chunk and ChunkEmbedding dataclasses

**Files:**
- Create: `src/local_library/embeddings/base.py`

**Step 1: Create base.py with data models**

Create `src/local_library/embeddings/base.py`:

```python
"""Protocol definitions and data models for embeddings."""

# pattern: Functional Core

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class Chunk:
    """A chunk of text from a document.

    Represents a segment of document text that will be embedded.
    Includes metadata about position and section context.

    Attributes:
        chunk_id: Unique identifier for this chunk
        doc_id: Parent document UUID
        chunk_index: Position of this chunk within the document (0-indexed)
        text: The chunk text content
        section: Section header(s) this chunk belongs to (may be empty)
        char_start: Starting character position in original text (optional)
        char_end: Ending character position in original text (optional)
        created_at: Timestamp when chunk was created
    """

    chunk_id: str
    doc_id: UUID
    chunk_index: int
    text: str
    section: str
    char_start: int | None
    char_end: int | None
    created_at: datetime

    @classmethod
    def create(
        cls,
        doc_id: UUID,
        chunk_index: int,
        text: str,
        section: str = "",
        char_start: int | None = None,
        char_end: int | None = None,
    ) -> "Chunk":
        """Create a new Chunk with auto-generated ID and timestamp.

        Args:
            doc_id: Parent document UUID
            chunk_index: Position within document
            text: Chunk text content
            section: Section header context
            char_start: Starting character position
            char_end: Ending character position

        Returns:
            New Chunk instance
        """
        return cls(
            chunk_id=str(uuid4()),
            doc_id=doc_id,
            chunk_index=chunk_index,
            text=text,
            section=section,
            char_start=char_start,
            char_end=char_end,
            created_at=datetime.now(timezone.utc),
        )


@dataclass(frozen=True)
class ChunkEmbedding:
    """A chunk with its computed embedding vector.

    Combines a Chunk with its vector representation for storage.

    Attributes:
        chunk: The source chunk
        embedding: 768-dimensional vector (nomic-embed-text-v1.5 output)
    """

    chunk: Chunk
    embedding: NDArray[np.float32]

    def __post_init__(self) -> None:
        """Validate embedding dimensions."""
        if self.embedding.shape != (768,):
            raise ValueError(
                f"embedding must be 768-dimensional, got shape {self.embedding.shape}"
            )

    @property
    def chunk_id(self) -> str:
        """Get chunk ID for convenience."""
        return self.chunk.chunk_id

    @property
    def doc_id(self) -> UUID:
        """Get document ID for convenience."""
        return self.chunk.doc_id


@runtime_checkable
class Chunker(Protocol):
    """Protocol for splitting documents into chunks.

    Implementations handle specific chunking strategies (markdown-aware,
    fixed-size, sentence-based, etc.).
    """

    def chunk(self, doc_id: UUID, text: str) -> list[Chunk]:
        """Split text into chunks.

        Args:
            doc_id: Document UUID to associate with chunks
            text: Full document text to chunk

        Returns:
            List of Chunk objects in document order

        Raises:
            EmbeddingError: If chunking fails
        """
        ...


@runtime_checkable
class Embedder(Protocol):
    """Protocol for computing embeddings from text.

    Implementations handle specific embedding models (nomic, OpenAI, etc.).
    """

    def embed_chunks(self, chunks: list[Chunk]) -> list[ChunkEmbedding]:
        """Compute embeddings for a list of chunks.

        Args:
            chunks: Chunks to embed

        Returns:
            ChunkEmbedding objects with computed vectors

        Raises:
            EmbeddingError: If embedding computation fails
        """
        ...

    def embed_query(self, query: str) -> NDArray[np.float32]:
        """Compute embedding for a search query.

        Uses the appropriate task prefix for query embedding
        (e.g., 'search_query:' for nomic-embed-text).

        Args:
            query: Search query text

        Returns:
            768-dimensional embedding vector

        Raises:
            EmbeddingError: If embedding computation fails
        """
        ...
```

**Step 2: Verify dataclasses and protocols**

Run: `uv run python -c "
from uuid import uuid4
import numpy as np
from local_library.embeddings.base import Chunk, ChunkEmbedding, Chunker, Embedder

# Test Chunk creation
doc_id = uuid4()
chunk = Chunk.create(doc_id, 0, 'Test text', section='Introduction')
print(f'Chunk created: {chunk.chunk_id[:8]}...')
print(f'Chunk is frozen: {chunk.__dataclass_fields__}')

# Test ChunkEmbedding
embedding = np.random.randn(768).astype(np.float32)
chunk_emb = ChunkEmbedding(chunk=chunk, embedding=embedding)
print(f'ChunkEmbedding doc_id: {chunk_emb.doc_id}')

# Test protocols are runtime checkable
print(f'Chunker is Protocol: {hasattr(Chunker, \"__protocol_attrs__\") or True}')
print(f'Embedder is Protocol: {hasattr(Embedder, \"__protocol_attrs__\") or True}')
"
`

Expected:
```
Chunk created: xxxxxxxx...
Chunk is frozen: ...
ChunkEmbedding doc_id: ...
Chunker is Protocol: True
Embedder is Protocol: True
```

**Step 3: Commit**

```bash
git add src/local_library/embeddings/base.py
git commit -m "feat(embeddings): add Chunk, ChunkEmbedding dataclasses and Chunker, Embedder protocols"
```
<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Add unit tests for data models

**Files:**
- Create: `tests/unit/test_embedding_models.py`

**Step 1: Create test file**

Create `tests/unit/test_embedding_models.py`:

```python
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
```

**Step 2: Run the tests**

Run: `uv run pytest tests/unit/test_embedding_models.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_embedding_models.py
git commit -m "test: add unit tests for Chunk, ChunkEmbedding, and embedding protocols"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

<!-- START_TASK_4 -->
### Task 4: Create embeddings/CLAUDE.md documentation

**Files:**
- Create: `src/local_library/embeddings/CLAUDE.md`

**Step 1: Create the domain documentation**

Create `src/local_library/embeddings/CLAUDE.md`:

```markdown
# Embeddings Domain

Last verified: 2026-02-04

## Purpose

Handles document chunking, embedding computation, and vector storage for semantic search. Transforms extracted markdown into searchable vector representations using nomic-embed-text-v1.5 via sentence-transformers, stored in sqlite-vec.

## Contracts

- **Exposes**: Chunker protocol, Embedder protocol, Chunk dataclass, ChunkEmbedding dataclass, MarkdownChunker (Phase 3), NomicEmbedder (Phase 4), EmbeddingStorage (Phase 5)
- **Guarantees**:
  - `Chunk` is frozen/immutable with auto-generated UUID and UTC timestamp
  - `ChunkEmbedding` validates 768-dimensional vectors on creation
  - `Chunker.chunk()` returns chunks in document order with sequential chunk_index
  - `Embedder.embed_chunks()` returns ChunkEmbedding for each input chunk
  - `Embedder.embed_query()` uses `search_query:` prefix for nomic-embed-text
  - Chunk embeddings use `search_document:` prefix for nomic-embed-text
- **Expects**: Extracted markdown text (from ingestion pipeline); sqlite-vec extension for vector storage

## Dependencies

- **Uses**: `core.models` (EmbeddingStatus, Document), `core.errors` (EmbeddingError, ErrorCode), `core.vec_extension` (sqlite-vec loading)
- **Used by**: `core.library` (Library orchestrator calls embed methods)
- **Boundary**: Embeddings MUST NOT import from cli

## Key Decisions

- **Protocol-based extensibility**: Chunker and Embedder are protocols (not ABCs) following ingestion module pattern
- **Frozen dataclasses**: Chunk and ChunkEmbedding are immutable (Functional Core pattern)
- **768-dimensional vectors**: Hardcoded for nomic-embed-text-v1.5; ChunkEmbedding validates on creation
- **Section metadata**: Chunk.section captures markdown header context for retrieval augmentation
- **Lazy imports via `__getattr__`**: Prevents circular imports, follows ingestion module pattern
- **Task prefix responsibility**: Embedder implementations handle task prefixes (`search_document:`, `search_query:`)
- **numpy for vectors**: Embeddings stored as numpy float32 arrays; serialized via sqlite_vec.serialize_float32

## Invariants

- Every Chunk has a unique chunk_id (UUID)
- chunk_index is sequential within a document (0, 1, 2, ...)
- ChunkEmbedding.embedding is always shape (768,) and dtype float32
- Chunks maintain document order (sorted by chunk_index)

## Key Files

- `base.py` - Chunk, ChunkEmbedding dataclasses; Chunker, Embedder protocols
- `chunking.py` - MarkdownChunker implementation (Phase 3)
- `nomic.py` - NomicEmbedder implementation (Phase 4)
- `storage.py` - EmbeddingStorage CRUD operations (Phase 5)

## Gotchas

- nomic-embed-text requires `trust_remote_code=True` when loading via sentence-transformers
- Task prefixes must be prepended manually (sentence-transformers doesn't auto-prepend)
- sqlite-vec requires `serialize_float32()` for vector insertion
- ChunkEmbedding raises ValueError if embedding isn't exactly 768 dimensions
- Model download happens on first embed call (~262 MB, cached to ~/.cache/huggingface/)
```

**Step 2: Commit**

```bash
git add src/local_library/embeddings/CLAUDE.md
git commit -m "docs: add embeddings/CLAUDE.md domain documentation"
```
<!-- END_TASK_4 -->

---

## Phase 2 Verification

After completing all tasks, verify the phase is complete:

**Run all Phase 2 tests:**
```bash
uv run pytest tests/unit/test_embedding_models.py -v
```

**Verify all components import via lazy loading:**
```bash
uv run python -c "
from local_library.embeddings import Chunk, ChunkEmbedding, Chunker, Embedder
from uuid import uuid4
import numpy as np

# Verify dataclasses work
chunk = Chunk.create(uuid4(), 0, 'Test text')
emb = ChunkEmbedding(chunk=chunk, embedding=np.random.randn(768).astype(np.float32))

print(f'Chunk imports: {Chunk}')
print(f'ChunkEmbedding imports: {ChunkEmbedding}')
print(f'Chunker protocol: {Chunker}')
print(f'Embedder protocol: {Embedder}')
print('All Phase 2 components verified!')
"
```

**Done when:**
- `embeddings/__init__.py` exists with lazy imports
- `embeddings/base.py` defines Chunk, ChunkEmbedding, Chunker, Embedder
- Chunk.create() factory generates UUID and timestamp
- ChunkEmbedding validates 768-dimensional vectors
- Protocols are @runtime_checkable
- All tests pass
- CLAUDE.md documents the domain
