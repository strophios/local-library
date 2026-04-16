"""Tests for MCP markdown formatters."""

from datetime import datetime, timezone
from uuid import uuid4

from local_library.core.models import Document, DocumentStatus, EmbeddingStatus
from local_library.embeddings.base import Chunk, SearchResult
from local_library.mcp.formatters import (
    format_document,
    format_document_list,
    format_document_text,
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


def _make_document(
    citekey="Author2023",
    title="Test Document",
    authors="Jane Author",
    issued_date="2023",
    status=DocumentStatus.READY,
    embedding_status=EmbeddingStatus.CURRENT,
    csl_json=None,
    extracted_path="/path/to/extracted.md",
    original_path="/path/to/original.pdf",
):
    """Create a Document for testing."""
    return Document(
        id=uuid4(),
        original_path=original_path,
        content_hash="abc123def456",
        storage_path="/storage/ab/cd/abc123.pdf",
        status=status,
        created_at=datetime(2023, 6, 15, tzinfo=timezone.utc),
        updated_at=datetime(2023, 6, 15, tzinfo=timezone.utc),
        extracted_path=extracted_path,
        citekey=citekey,
        title=title,
        authors=authors,
        issued_date=issued_date,
        csl_json=csl_json or {"type": "article-journal", "title": title},
        embedding_status=embedding_status,
    )


class TestFormatDocument:
    """Tests for format_document."""

    def test_includes_citekey(self) -> None:
        """Citekey appears with @ prefix."""
        doc = _make_document(citekey="Bourdieu1984")
        output = format_document(doc, chunk_count=100)
        assert "@Bourdieu1984" in output

    def test_includes_title(self) -> None:
        """Title appears in output."""
        doc = _make_document(title="Distinction")
        output = format_document(doc, chunk_count=0)
        assert "Distinction" in output

    def test_includes_authors(self) -> None:
        """Authors appear in output."""
        doc = _make_document(authors="Pierre Bourdieu")
        output = format_document(doc, chunk_count=0)
        assert "Pierre Bourdieu" in output

    def test_includes_date(self) -> None:
        """Issued date appears in output."""
        doc = _make_document(issued_date="1984")
        output = format_document(doc, chunk_count=0)
        assert "1984" in output

    def test_includes_status(self) -> None:
        """Document status appears."""
        doc = _make_document(status=DocumentStatus.READY)
        output = format_document(doc, chunk_count=0)
        assert "ready" in output.lower()

    def test_includes_embedding_status(self) -> None:
        """Embedding status appears."""
        doc = _make_document(embedding_status=EmbeddingStatus.CURRENT)
        output = format_document(doc, chunk_count=0)
        assert "current" in output.lower()

    def test_includes_chunk_count(self) -> None:
        """Chunk count appears."""
        doc = _make_document()
        output = format_document(doc, chunk_count=1987)
        assert "1987" in output

    def test_includes_original_path(self) -> None:
        """Original file path appears."""
        doc = _make_document(original_path="/docs/paper.pdf")
        output = format_document(doc, chunk_count=0)
        assert "/docs/paper.pdf" in output

    def test_includes_csl_json_type(self) -> None:
        """CSL-JSON type field appears."""
        doc = _make_document(csl_json={"type": "book", "title": "Test"})
        output = format_document(doc, chunk_count=0)
        assert "book" in output.lower()

    def test_missing_citekey_handled(self) -> None:
        """Document without citekey doesn't crash."""
        doc = _make_document(citekey=None)
        output = format_document(doc, chunk_count=0)
        assert str(doc.id) in output or "Document" in output


class TestFormatDocumentList:
    """Tests for format_document_list."""

    def test_header_shows_counts(self) -> None:
        """Header shows displayed vs total count."""
        docs = [_make_document() for _ in range(3)]
        output = format_document_list(docs, total=100)
        assert "3" in output
        assert "100" in output

    def test_includes_citekeys(self) -> None:
        """Each document's citekey appears."""
        docs = [_make_document(citekey="A2023"), _make_document(citekey="B2024")]
        output = format_document_list(docs, total=2)
        assert "@A2023" in output
        assert "@B2024" in output

    def test_includes_status(self) -> None:
        """Status column appears."""
        docs = [_make_document(status=DocumentStatus.READY)]
        output = format_document_list(docs, total=1)
        assert "ready" in output.lower()

    def test_empty_list(self) -> None:
        """Empty document list returns helpful message."""
        output = format_document_list([], total=0)
        assert "no documents" in output.lower() or "empty" in output.lower()

    def test_table_format(self) -> None:
        """Output uses markdown table format."""
        docs = [_make_document()]
        output = format_document_list(docs, total=1)
        assert "|" in output  # Markdown table delimiter


class TestFormatDocumentText:
    """Tests for format_document_text."""

    def test_short_doc_returns_full_text(self) -> None:
        """Short document (<50 chunks) returns full text."""
        doc = _make_document()
        text = "# Full Document\n\nSome content here."
        output = format_document_text(doc, text=text, chunks=None, total_chunks=10)
        assert "Full Document" in output
        assert "Some content here." in output

    def test_long_doc_without_range_shows_preview(self) -> None:
        """Long doc without range shows header + first chunks + instructions."""
        doc = _make_document()
        chunks = [
            _make_chunk(chunk_index=i, text=f"Chunk {i} text.", section=f"Section {i}")
            for i in range(20)
        ]
        output = format_document_text(doc, text=None, chunks=chunks, total_chunks=200)
        assert "200" in output  # Total chunk count
        assert "Chunk 0 text." in output  # First chunk present
        assert "get_document_text" in output.lower() or "range" in output.lower()

    def test_long_doc_with_range_shows_chunks(self) -> None:
        """Long doc with range shows specified chunks."""
        doc = _make_document()
        chunks = [
            _make_chunk(chunk_index=i, text=f"Chunk {i} text.", section="Methods")
            for i in range(10, 15)
        ]
        output = format_document_text(
            doc,
            text=None,
            chunks=chunks,
            total_chunks=200,
            start_chunk=10,
            end_chunk=14,
        )
        assert "Chunk 10 text." in output
        assert "Chunk 14 text." in output
        assert "10" in output  # Start index shown

    def test_includes_document_header(self) -> None:
        """Output includes document identification."""
        doc = _make_document(citekey="Author2023", title="Test Paper")
        output = format_document_text(doc, text="Content", chunks=None, total_chunks=5)
        assert "@Author2023" in output or "Test Paper" in output
