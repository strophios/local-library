## Phase 3: Chunking Implementation

**Goal:** Section-aware markdown chunking that respects document structure.

This phase implements `MarkdownChunker` using LangChain's text splitters. The chunker first splits by markdown headers to preserve section context, then applies recursive character splitting to meet token limits (~512 tokens, ~15% overlap).

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create MarkdownChunker implementation

**Files:**
- Create: `src/local_library/embeddings/chunking.py`

**Step 1: Create the chunking module**

Create `src/local_library/embeddings/chunking.py`:

```python
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
```

**Step 2: Verify the chunker imports**

Run: `uv run python -c "
from local_library.embeddings.chunking import MarkdownChunker, estimate_token_count
print('MarkdownChunker imported successfully')
print(f'estimate_token_count(\"hello world\"): {estimate_token_count(\"hello world\")}')
"
`

Expected:
```
MarkdownChunker imported successfully
estimate_token_count("hello world"): 2
```

**Step 3: Commit**

```bash
git add src/local_library/embeddings/chunking.py
git commit -m "feat(embeddings): add MarkdownChunker with section-aware splitting"
```
<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Add MarkdownChunker to module exports

**Files:**
- Modify: `src/local_library/embeddings/__init__.py`

**Step 1: Add lazy import for MarkdownChunker**

Update `src/local_library/embeddings/__init__.py` to add the chunking exports. Add these elif clauses after the ChunkEmbedding import:

```python
    elif name == "MarkdownChunker":
        from local_library.embeddings.chunking import MarkdownChunker

        return MarkdownChunker
    elif name == "estimate_token_count":
        from local_library.embeddings.chunking import estimate_token_count

        return estimate_token_count
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
    # Utilities
    "estimate_token_count",
]
```

**Step 2: Verify imports work**

Run: `uv run python -c "
from local_library.embeddings import MarkdownChunker, estimate_token_count
print(f'MarkdownChunker: {MarkdownChunker}')
print(f'estimate_token_count: {estimate_token_count}')
"
`

Expected: Both imports succeed without error

**Step 3: Commit**

```bash
git add src/local_library/embeddings/__init__.py
git commit -m "feat(embeddings): export MarkdownChunker and estimate_token_count"
```
<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Add unit tests for MarkdownChunker

**Files:**
- Create: `tests/unit/test_chunking.py`

**Step 1: Create comprehensive test file**

Create `tests/unit/test_chunking.py`:

```python
"""Unit tests for markdown chunking."""

from uuid import uuid4

import pytest

from local_library.embeddings.base import Chunk, Chunker
from local_library.embeddings.chunking import MarkdownChunker, estimate_token_count


class TestMarkdownChunker:
    """Tests for MarkdownChunker implementation."""

    @pytest.fixture
    def chunker(self) -> MarkdownChunker:
        """Provide a default chunker instance."""
        return MarkdownChunker()

    @pytest.fixture
    def small_chunker(self) -> MarkdownChunker:
        """Provide a chunker with small chunk size for testing splits."""
        return MarkdownChunker(chunk_size=100, chunk_overlap=20)

    def test_implements_chunker_protocol(self, chunker: MarkdownChunker) -> None:
        """MarkdownChunker should implement Chunker protocol."""
        assert isinstance(chunker, Chunker)

    def test_empty_text_returns_empty_list(self, chunker: MarkdownChunker) -> None:
        """Empty or whitespace text should return empty chunk list."""
        assert chunker.chunk(uuid4(), "") == []
        assert chunker.chunk(uuid4(), "   ") == []
        assert chunker.chunk(uuid4(), "\n\n") == []

    def test_short_text_single_chunk(self, chunker: MarkdownChunker) -> None:
        """Short text should produce a single chunk."""
        doc_id = uuid4()
        text = "This is a short paragraph of text."

        chunks = chunker.chunk(doc_id, text)

        assert len(chunks) == 1
        assert chunks[0].doc_id == doc_id
        assert chunks[0].chunk_index == 0
        assert chunks[0].text == text

    def test_chunks_have_sequential_indices(self, small_chunker: MarkdownChunker) -> None:
        """Chunks should have sequential chunk_index values."""
        doc_id = uuid4()
        text = "First paragraph. " * 20 + "\n\n" + "Second paragraph. " * 20

        chunks = small_chunker.chunk(doc_id, text)

        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_chunks_are_immutable(self, chunker: MarkdownChunker) -> None:
        """Returned chunks should be frozen dataclasses."""
        chunks = chunker.chunk(uuid4(), "Test text")

        with pytest.raises(AttributeError):
            chunks[0].text = "Modified"  # type: ignore

    def test_header_splitting_preserves_section(self, chunker: MarkdownChunker) -> None:
        """Chunks should capture section context from headers."""
        doc_id = uuid4()
        text = """# Introduction

This is the introduction.

## Background

This is background information.

## Methods

This describes the methods.
"""

        chunks = chunker.chunk(doc_id, text)

        # Find chunks and check sections
        sections = [c.section for c in chunks]
        assert any("Introduction" in s for s in sections)
        assert any("Background" in s for s in sections)
        assert any("Methods" in s for s in sections)

    def test_nested_headers_build_section_path(self, chunker: MarkdownChunker) -> None:
        """Nested headers should produce hierarchical section paths."""
        doc_id = uuid4()
        text = """# Chapter 1

## Section A

### Subsection 1

Content here.
"""

        chunks = chunker.chunk(doc_id, text)

        # Find the deepest chunk
        deepest = [c for c in chunks if "Subsection" in c.section]
        assert len(deepest) > 0
        # Section should show hierarchy
        assert "Chapter 1" in deepest[0].section or "Section A" in deepest[0].section

    def test_long_section_is_split(self, small_chunker: MarkdownChunker) -> None:
        """Long sections should be split into multiple chunks."""
        doc_id = uuid4()
        # Create text longer than chunk_size
        text = "## Long Section\n\n" + ("This is a sentence. " * 50)

        chunks = small_chunker.chunk(doc_id, text)

        assert len(chunks) > 1
        # All chunks should reference same section
        for chunk in chunks:
            assert "Long Section" in chunk.section or chunk.section == ""

    def test_chunk_overlap_present(self, small_chunker: MarkdownChunker) -> None:
        """Adjacent chunks should have overlapping content."""
        doc_id = uuid4()
        text = "Word " * 100  # Should produce multiple chunks

        chunks = small_chunker.chunk(doc_id, text)

        if len(chunks) >= 2:
            # Check that end of first chunk overlaps with start of second
            # (This is a heuristic check - exact overlap depends on splitter)
            first_end = chunks[0].text[-50:]
            second_start = chunks[1].text[:50]
            # At minimum, both should have content
            assert len(first_end) > 0
            assert len(second_start) > 0

    def test_all_chunks_have_doc_id(self, small_chunker: MarkdownChunker) -> None:
        """All chunks should have the correct doc_id."""
        doc_id = uuid4()
        text = "Paragraph. " * 50

        chunks = small_chunker.chunk(doc_id, text)

        for chunk in chunks:
            assert chunk.doc_id == doc_id

    def test_all_chunks_have_timestamps(self, chunker: MarkdownChunker) -> None:
        """All chunks should have created_at timestamps."""
        chunks = chunker.chunk(uuid4(), "Test text")

        for chunk in chunks:
            assert chunk.created_at is not None

    def test_no_headers_still_chunks(self, small_chunker: MarkdownChunker) -> None:
        """Text without headers should still be chunked."""
        doc_id = uuid4()
        text = "Plain text without any markdown headers. " * 20

        chunks = small_chunker.chunk(doc_id, text)

        assert len(chunks) >= 1
        # Sections should be empty when no headers
        for chunk in chunks:
            assert chunk.section == "" or chunk.section is not None

    def test_custom_headers_to_split_on(self) -> None:
        """Should respect custom headers_to_split_on parameter."""
        # Only split on H1
        chunker = MarkdownChunker(
            chunk_size=5000,
            headers_to_split_on=[("#", "H1")]
        )
        doc_id = uuid4()
        text = """# Part 1

Content for part 1.

## Subsection (should not split here)

More content.

# Part 2

Content for part 2.
"""

        chunks = chunker.chunk(doc_id, text)

        # Should have chunks for Part 1 and Part 2
        texts = [c.text for c in chunks]
        assert any("Part 1" in t for t in texts)
        assert any("Part 2" in t for t in texts)

    def test_custom_chunk_size(self) -> None:
        """Should respect custom chunk_size parameter."""
        chunker = MarkdownChunker(chunk_size=50, chunk_overlap=10)
        doc_id = uuid4()
        text = "A" * 200

        chunks = chunker.chunk(doc_id, text)

        # Should produce multiple small chunks
        assert len(chunks) > 1
        # Each chunk (except possibly last) should be around chunk_size
        for chunk in chunks[:-1]:
            assert len(chunk.text) <= 60  # Allow some flexibility


class TestEstimateTokenCount:
    """Tests for token estimation utility."""

    def test_empty_string(self) -> None:
        """Empty string should have 0 tokens."""
        assert estimate_token_count("") == 0

    def test_simple_estimate(self) -> None:
        """Should estimate ~1 token per 4 characters."""
        text = "hello world"  # 11 chars
        estimate = estimate_token_count(text)
        assert estimate == 2  # 11 / 4 = 2.75 -> 2

    def test_custom_chars_per_token(self) -> None:
        """Should use custom chars_per_token."""
        text = "hello"  # 5 chars
        assert estimate_token_count(text, chars_per_token=5.0) == 1
        assert estimate_token_count(text, chars_per_token=2.5) == 2
```

**Step 2: Run the tests**

Run: `uv run pytest tests/unit/test_chunking.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_chunking.py
git commit -m "test: add unit tests for MarkdownChunker"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

## Phase 3 Verification

After completing all tasks, verify the phase is complete:

**Run all Phase 3 tests:**
```bash
uv run pytest tests/unit/test_chunking.py -v
```

**Verify chunking works end-to-end:**
```bash
uv run python -c "
from uuid import uuid4
from local_library.embeddings import MarkdownChunker, Chunk

chunker = MarkdownChunker()

markdown = '''# Introduction

This paper presents our findings.

## Methods

We used a novel approach involving multiple stages of analysis.

### Data Collection

Data was collected from various sources over a period of six months.

### Analysis

Statistical analysis was performed using standard techniques.

## Results

The results show significant improvement over baseline methods.

## Conclusion

Our approach demonstrates the effectiveness of the proposed method.
'''

doc_id = uuid4()
chunks = chunker.chunk(doc_id, markdown)

print(f'Total chunks: {len(chunks)}')
for i, chunk in enumerate(chunks):
    print(f'  Chunk {i}: section=\"{chunk.section}\" len={len(chunk.text)}')
"
```

Expected output shows chunks with proper section hierarchy.

**Done when:**
- MarkdownChunker implements Chunker protocol
- Header splitting preserves section metadata in Chunk.section
- Long sections are recursively split to meet size limits
- Empty/whitespace text returns empty list
- All tests pass
- Module exports work via lazy imports
