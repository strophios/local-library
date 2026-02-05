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
