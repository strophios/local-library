"""Markdown-aware text chunking for embedding."""

# pattern: Functional Core (pure transformation, no I/O)

from uuid import UUID

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from local_library.core.errors import EmbeddingError, ErrorCode
from local_library.embeddings.base import Chunk


class MarkdownChunker:
    """Section-aware markdown chunker.

    Splits markdown documents in two stages:
    1. MarkdownHeaderTextSplitter - splits by headers (##, ###) preserving structure
    2. RecursiveCharacterTextSplitter - further splits large sections by character count

    The result is chunks that respect document structure while staying within
    size limits suitable for embedding models.

    Attributes:
        chunk_size: Target characters per chunk (default: 1500, ~375 tokens)
        chunk_overlap: Characters of overlap between chunks (default: 200, ~50 tokens)
    """

    # Default headers to split on (## and ### are most common in extracted markdown)
    DEFAULT_HEADERS = [
        ("#", "H1"),
        ("##", "H2"),
        ("###", "H3"),
        ("####", "H4"),
    ]

    def __init__(
        self,
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
        headers_to_split_on: list[tuple[str, str]] | None = None,
    ) -> None:
        """Initialize the chunker.

        Args:
            chunk_size: Target characters per chunk (default: 1500)
                       ~375 tokens at 4 chars/token average
            chunk_overlap: Characters of overlap (default: 200)
                          ~50 tokens, roughly 13% overlap
            headers_to_split_on: List of (header_marker, metadata_key) tuples
                                Default: [("#", "H1"), ("##", "H2"), ...]
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.headers_to_split_on = headers_to_split_on or self.DEFAULT_HEADERS

        # Initialize LangChain splitters
        self._header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on,
            strip_headers=False,  # Keep headers in text for context
        )

        self._char_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    def chunk(self, doc_id: UUID, text: str) -> list[Chunk]:
        """Split markdown text into chunks.

        Two-stage splitting:
        1. Split by markdown headers to preserve section structure
        2. Further split large sections by character count

        Args:
            doc_id: Document UUID to associate with chunks
            text: Markdown text to chunk

        Returns:
            List of Chunk objects in document order

        Raises:
            EmbeddingError: If chunking fails
        """
        if not text or not text.strip():
            return []

        try:
            # Stage 1: Split by headers
            header_docs = self._header_splitter.split_text(text)

            if not header_docs:
                # No headers found - treat entire text as one section
                header_docs = [type("Doc", (), {"page_content": text, "metadata": {}})()]

            # Stage 2: Further split large sections, preserving metadata
            final_docs = self._char_splitter.split_documents(header_docs)

            # Convert to Chunk objects
            chunks: list[Chunk] = []
            for i, doc in enumerate(final_docs):
                # Build section string from header metadata
                section = self._build_section_string(doc.metadata)

                chunk = Chunk.create(
                    doc_id=doc_id,
                    chunk_index=i,
                    text=doc.page_content,
                    section=section,
                )
                chunks.append(chunk)

            return chunks

        except Exception as e:
            raise EmbeddingError(
                f"failed to chunk document: {e}",
                ErrorCode.EMBEDDING_CHUNK_FAILED,
                details={"doc_id": str(doc_id)},
            ) from e

    def _build_section_string(self, metadata: dict) -> str:
        """Build section string from header metadata.

        Combines header levels into a path-like string.

        Args:
            metadata: Dict with H1, H2, H3, H4 keys from header splitter

        Returns:
            Section string like "Introduction > Background > Methods"
        """
        parts = []
        for key in ["H1", "H2", "H3", "H4"]:
            if key in metadata and metadata[key]:
                parts.append(metadata[key])
        return " > ".join(parts) if parts else ""


def estimate_token_count(text: str, chars_per_token: float = 4.0) -> int:
    """Estimate token count from character count.

    Uses a simple heuristic based on average characters per token.
    For English text with nomic-embed-text, ~4 chars/token is typical.

    Args:
        text: Text to estimate
        chars_per_token: Average characters per token (default: 4.0)

    Returns:
        Estimated token count
    """
    return int(len(text) / chars_per_token)
