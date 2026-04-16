"""Tests for MCP markdown formatters."""

from datetime import datetime, timezone
from uuid import uuid4

from local_library.embeddings.base import Chunk, SearchResult
from local_library.mcp.formatters import (
    format_empty_results,
    format_search_results,
    format_tool_error,
    format_user_error,
)


def _make_chunk(
    doc_id=None,
    chunk_index=0,
    text="Sample chunk text for testing.",
    section="Introduction",
):
    """Create a Chunk for testing."""
    return Chunk(
        chunk_id=str(uuid4()),
        doc_id=doc_id or uuid4(),
        chunk_index=chunk_index,
        text=text,
        section=section,
        char_start=0,
        char_end=len(text),
        created_at=datetime.now(timezone.utc),
    )


def _make_result(
    doc_id=None,
    chunk_index=0,
    text="Sample chunk text for testing.",
    section="Introduction",
    score=0.95,
    doc_title="Test Document",
    doc_citekey="Author2023",
    search_methods=None,
):
    """Create a SearchResult for testing."""
    return SearchResult(
        chunk=_make_chunk(doc_id=doc_id, chunk_index=chunk_index, text=text, section=section),
        score=score,
        doc_title=doc_title,
        doc_citekey=doc_citekey,
        search_methods=frozenset(search_methods or ["hybrid"]),
    )


class TestFormatSearchResults:
    """Tests for format_search_results."""

    def test_empty_results_returns_no_results_message(self) -> None:
        """Empty result list returns helpful message with query."""
        result = format_search_results([], "machine learning")
        assert "no results" in result.lower()
        assert "machine learning" in result

    def test_single_result_includes_citekey(self) -> None:
        """Single result displays citekey with @ prefix."""
        results = [_make_result(doc_citekey="Bourdieu1984")]
        output = format_search_results(results, "social space")
        assert "@Bourdieu1984" in output

    def test_single_result_includes_score(self) -> None:
        """Score appears formatted to 3 decimal places."""
        results = [_make_result(score=0.99712)]
        output = format_search_results(results, "query")
        assert "0.997" in output

    def test_single_result_includes_title(self) -> None:
        """Document title appears in the output."""
        results = [_make_result(doc_title="Distinction")]
        output = format_search_results(results, "query")
        assert "Distinction" in output

    def test_single_result_includes_section(self) -> None:
        """Section header appears in output."""
        results = [_make_result(section="Chapter 2")]
        output = format_search_results(results, "query")
        assert "Chapter 2" in output

    def test_single_result_includes_chunk_index(self) -> None:
        """Chunk index appears for follow-up context retrieval."""
        results = [_make_result(chunk_index=42)]
        output = format_search_results(results, "query")
        assert "42" in output

    def test_single_result_includes_chunk_text_as_blockquote(self) -> None:
        """Chunk text appears in blockquote format."""
        results = [_make_result(text="The social space is constructed.")]
        output = format_search_results(results, "query")
        assert "The social space is constructed." in output
        assert "> " in output

    def test_header_shows_chunk_and_document_counts(self) -> None:
        """Header shows total chunk count and unique document count."""
        doc_id = uuid4()
        results = [
            _make_result(doc_id=doc_id, chunk_index=0, doc_citekey="A2023"),
            _make_result(doc_id=doc_id, chunk_index=1, doc_citekey="A2023"),
            _make_result(doc_citekey="B2024"),
        ]
        output = format_search_results(results, "query")
        header = output.split("\n")[0]
        assert "3" in header  # 3 chunks
        assert "2" in header  # 2 documents

    def test_result_without_citekey_uses_title(self) -> None:
        """When citekey is None, falls back to title."""
        results = [_make_result(doc_citekey=None, doc_title="Untitled Work")]
        output = format_search_results(results, "query")
        assert "Untitled Work" in output

    def test_results_numbered_sequentially(self) -> None:
        """Results numbered 1, 2, 3."""
        results = [_make_result(score=0.9), _make_result(score=0.8)]
        output = format_search_results(results, "query")
        assert "1." in output
        assert "2." in output

    def test_long_text_truncated(self) -> None:
        """Text longer than 300 chars is truncated with ellipsis."""
        long_text = "A" * 500
        results = [_make_result(text=long_text)]
        output = format_search_results(results, "query")
        assert "..." in output
        assert len(long_text) != output.count("A")


class TestFormatUserError:
    """Tests for format_user_error."""

    def test_includes_user_facing_prefix(self) -> None:
        """Includes USER-FACING ERROR prefix and warning symbol."""
        result = format_user_error("sqlite-vec unavailable")
        assert "USER-FACING ERROR" in result
        assert "\u26a0" in result

    def test_includes_message(self) -> None:
        """Includes the error message text."""
        result = format_user_error("specific error message")
        assert "specific error message" in result


class TestFormatToolError:
    """Tests for format_tool_error."""

    def test_starts_with_error_prefix(self) -> None:
        """Starts with Error: prefix."""
        result = format_tool_error("not found")
        assert result.startswith("Error: ")

    def test_includes_message(self) -> None:
        """Includes the error message text."""
        result = format_tool_error("document xyz not found")
        assert "document xyz not found" in result


class TestFormatEmptyResults:
    """Tests for format_empty_results."""

    def test_includes_query(self) -> None:
        """Includes the original query."""
        result = format_empty_results("machine learning")
        assert "machine learning" in result

    def test_suggests_alternatives(self) -> None:
        """Suggests trying different terms or modes."""
        result = format_empty_results("test query")
        lower = result.lower()
        assert "try" in lower or "different" in lower or "suggest" in lower
