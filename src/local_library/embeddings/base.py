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
            raise ValueError(f"embedding must be 768-dimensional, got shape {self.embedding.shape}")

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


@dataclass(frozen=True)
class SearchResult:
    """A single search result with score and provenance metadata.

    Returned by all Retriever implementations. Frozen for immutability.

    Attributes:
        chunk: The matched chunk of text
        score: Relevance score (higher = more relevant). RRF score for hybrid,
               converted distance for vector, BM25 rank for FTS.
        doc_title: Document title for display (None if metadata unavailable)
        doc_citekey: Citekey for citation reference (None if not set)
        search_methods: Which search methods contributed to this result
    """

    chunk: Chunk
    score: float
    doc_title: str | None
    doc_citekey: str | None
    search_methods: frozenset[str]


@runtime_checkable
class Retriever(Protocol):
    """Protocol for searching document chunks by content.

    Implementations wrap one or more search backends (vector similarity,
    full-text search, or a hybrid combination) and return ranked results.
    """

    def retrieve(
        self,
        query: str,
        k: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Search for chunks matching a query.

        Args:
            query: Natural language search query
            k: Maximum number of results to return
            doc_ids: Optional document ID filter (search only these documents)

        Returns:
            List of SearchResult objects, sorted by score descending
        """
        ...


@runtime_checkable
class Reranker(Protocol):
    """Scores (query, result) pairs and returns reranked results."""

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        k: int = 10,
    ) -> list[SearchResult]:
        """Rerank results for the given query, returning top-k."""
        ...
