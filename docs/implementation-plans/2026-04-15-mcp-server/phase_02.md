# MCP Server Implementation Plan — Phase 2

**Goal:** Complete the tool surface with document metadata, listing, and text retrieval tools.

**Codebase verified:** 2026-04-15

---

## Phase 2: Document Tools

<!-- START_SUBCOMPONENT_A (tasks 1) -->
<!-- START_TASK_1 -->
### Task 1: Add public chunk access methods to Library

**Type:** Functionality

**Files:**
- Modify: `src/local_library/core/library.py` (add after `get_all_citekeys` around line 878)
- Modify: `tests/unit/test_library.py` (add tests for new methods)

**Reference files for executor:**
- `src/local_library/core/library.py:219-234` — `_get_embedding_storage()` private method
- `src/local_library/embeddings/storage.py:290-339` — `get_chunks_by_document()` and `get_chunk_count()`
- `src/local_library/embeddings/base.py:14-73` — Chunk dataclass

**Step 1: Write failing tests**

Add to `tests/unit/test_library.py` a new test class `TestLibraryChunkAccess`. Key behaviors to test:
- `get_chunk_count()` returns 0 for unembedded documents
- `get_chunks()` returns empty list for unembedded documents
- `get_chunk_count()` returns 0 when sqlite-vec unavailable (graceful degradation)
- `get_chunks()` returns empty list when sqlite-vec unavailable

Note: The executor should adapt these tests to use the existing test fixtures and patterns from `test_library.py`. The exact fixture names and setup depend on what's available.

Run: `uv run pytest tests/unit/test_library.py::TestLibraryChunkAccess -v`
Expected: AttributeError — methods don't exist yet

**Step 2: Implement methods in Library**

Add to `src/local_library/core/library.py` in the Query Operations section (after `get_all_citekeys` around line 878):

```python
def get_chunk_count(self, doc_id: UUID) -> int:
    """Get number of chunks for a document.

    Returns 0 if sqlite-vec is unavailable or document has no chunks.

    Args:
        doc_id: Document UUID

    Returns:
        Number of chunks
    """
    storage = self._get_embedding_storage()
    if storage is None:
        return 0
    return storage.get_chunk_count(doc_id)

def get_chunks(
    self,
    doc_id: UUID,
    start: int | None = None,
    end: int | None = None,
) -> "list[Chunk]":
    """Get chunks for a document, optionally by index range.

    Returns empty list if sqlite-vec is unavailable or document has no chunks.

    Args:
        doc_id: Document UUID
        start: Optional start chunk index (0-based, inclusive)
        end: Optional end chunk index (inclusive)

    Returns:
        List of Chunk objects ordered by chunk_index
    """
    storage = self._get_embedding_storage()
    if storage is None:
        return []
    chunks = storage.get_chunks_by_document(doc_id)
    if start is not None or end is not None:
        s = start or 0
        e = (end + 1) if end is not None else len(chunks)
        chunks = [c for c in chunks if s <= c.chunk_index < e]
    return chunks
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_library.py::TestLibraryChunkAccess -v`
Expected: Tests pass

**Step 4: Commit**
```bash
git add src/local_library/core/library.py tests/unit/test_library.py
git commit -m "feat(core): add public chunk access methods to Library"
```
<!-- END_TASK_1 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Write Phase 2 formatter tests

**Type:** Functionality (test-first)

**Files:**
- Modify: `tests/unit/test_mcp_formatters.py`

**Reference files for executor:**
- `src/local_library/core/models.py:33-81` — Document dataclass fields
- `src/local_library/core/models.py:16-31` — DocumentStatus, EmbeddingStatus enums
- `src/local_library/embeddings/base.py:14-73` — Chunk dataclass

**Step 1: Add test helpers and formatter tests**

Add to `tests/unit/test_mcp_formatters.py`. First, add a `_make_document` helper and import the new formatters:

```python
from local_library.core.models import Document, DocumentStatus, EmbeddingStatus
from local_library.mcp.formatters import (
    format_document,
    format_document_list,
    format_document_text,
    # ... existing imports ...
)


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
        output = format_document_text(
            doc, text=text, chunks=None, total_chunks=10
        )
        assert "Full Document" in output
        assert "Some content here." in output

    def test_long_doc_without_range_shows_preview(self) -> None:
        """Long doc without range shows header + first chunks + instructions."""
        doc = _make_document()
        chunks = [
            _make_chunk(chunk_index=i, text=f"Chunk {i} text.", section=f"Section {i}")
            for i in range(20)
        ]
        output = format_document_text(
            doc, text=None, chunks=chunks, total_chunks=200
        )
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
            doc, text=None, chunks=chunks, total_chunks=200,
            start_chunk=10, end_chunk=14,
        )
        assert "Chunk 10 text." in output
        assert "Chunk 14 text." in output
        assert "10" in output  # Start index shown

    def test_includes_document_header(self) -> None:
        """Output includes document identification."""
        doc = _make_document(citekey="Author2023", title="Test Paper")
        output = format_document_text(
            doc, text="Content", chunks=None, total_chunks=5
        )
        assert "@Author2023" in output or "Test Paper" in output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_mcp_formatters.py::TestFormatDocument -v`
Expected: ImportError — `format_document` not yet defined

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement Phase 2 formatters

**Type:** Functionality (make tests pass)

**Files:**
- Modify: `src/local_library/mcp/formatters.py`

**Reference files for executor:**
- `src/local_library/cli/show.py:44-95` — CLI show output format (for field reference)
- `src/local_library/cli/list.py:100-153` — CLI list table format
- `src/local_library/core/models.py:33-81` — Document fields

**Step 1: Add Phase 2 formatters to formatters.py**

Add the following imports and functions to `src/local_library/mcp/formatters.py`:

```python
from local_library.core.models import Document
from local_library.embeddings.base import Chunk, SearchResult


def format_document(doc: Document, chunk_count: int) -> str:
    """Format document metadata as markdown.

    Shows citekey, title, authors, date, status, embedding status,
    chunk count, CSL-JSON metadata fields, and original path.

    Args:
        doc: Document to format
        chunk_count: Number of chunks for this document

    Returns:
        Markdown-formatted document metadata
    """
    # Header: prefer @citekey, fall back to title or UUID
    if doc.citekey:
        header = f"## @{doc.citekey}"
    elif doc.title:
        header = f"## {doc.title}"
    else:
        header = f"## Document {doc.id}"

    lines = [header, ""]

    if doc.title:
        lines.append(f"**Title:** {doc.title}")
    if doc.authors:
        lines.append(f"**Authors:** {doc.authors}")
    if doc.issued_date:
        lines.append(f"**Date:** {doc.issued_date}")

    lines.append(f"**Status:** {doc.status.value}")
    lines.append(f"**Embedding status:** {doc.embedding_status.value}")
    lines.append(f"**Chunks:** {chunk_count}")

    # CSL-JSON metadata fields (if available)
    if doc.csl_json:
        lines.append("")
        lines.append("### Metadata")
        csl_fields = [
            ("type", "Type"),
            ("publisher", "Publisher"),
            ("container-title", "Journal/Book"),
            ("volume", "Volume"),
            ("issue", "Issue"),
            ("page", "Pages"),
            ("DOI", "DOI"),
            ("URL", "URL"),
            ("ISBN", "ISBN"),
            ("ISSN", "ISSN"),
            ("abstract", "Abstract"),
        ]
        for key, label in csl_fields:
            if key in doc.csl_json and doc.csl_json[key]:
                value = doc.csl_json[key]
                if isinstance(value, str) and len(value) > 300:
                    value = value[:297] + "..."
                lines.append(f"- **{label}:** {value}")

    lines.append("")
    lines.append(f"**Original path:** {doc.original_path}")

    return "\n".join(lines)


def format_document_list(docs: list[Document], total: int) -> str:
    """Format document listing as markdown table.

    Args:
        docs: Documents to display (already sliced to limit)
        total: Total number of documents (for "showing X of Y" header)

    Returns:
        Markdown table string
    """
    if not docs:
        return "No documents in the library."

    showing = len(docs)
    if showing < total:
        header = f"### Documents (showing {showing} of {total:,})"
    else:
        header = f"### Documents ({total:,} total)"

    lines = [
        header,
        "",
        "| Citekey | Title | Authors | Status | Embeddings |",
        "|---------|-------|---------|--------|------------|",
    ]

    for doc in docs:
        citekey = f"@{doc.citekey}" if doc.citekey else ""
        title = doc.title or ""
        if len(title) > 40:
            title = title[:37] + "..."
        authors = doc.authors or ""
        if len(authors) > 25:
            authors = authors[:22] + "..."

        lines.append(
            f"| {citekey} | {title} | {authors} "
            f"| {doc.status.value} | {doc.embedding_status.value} |"
        )

    return "\n".join(lines)


def format_document_text(
    doc: Document,
    text: str | None,
    chunks: list[Chunk] | None,
    total_chunks: int,
    start_chunk: int | None = None,
    end_chunk: int | None = None,
) -> str:
    """Format document text content as markdown.

    Three modes:
    - Short doc (text provided): returns full extracted markdown
    - Long doc with range (chunks provided, start/end set): chunk subset
    - Long doc preview (chunks provided, no range): header + first chunks + instructions

    Args:
        doc: Document metadata
        text: Full extracted markdown (for short docs)
        chunks: Chunk objects (for long docs)
        total_chunks: Total number of chunks in document
        start_chunk: Start of requested range (if range mode)
        end_chunk: End of requested range (if range mode)

    Returns:
        Markdown-formatted document text
    """
    # Document identification header
    if doc.citekey:
        doc_header = f"## @{doc.citekey}"
    elif doc.title:
        doc_header = f"## {doc.title}"
    else:
        doc_header = f"## Document {doc.id}"

    # Short document: return full text
    if text is not None:
        lines = [doc_header, f"*{total_chunks} chunks*", "", text]
        return "\n".join(lines)

    # Long document with chunk range
    if chunks and (start_chunk is not None or end_chunk is not None):
        s = start_chunk if start_chunk is not None else 0
        e = end_chunk if end_chunk is not None else chunks[-1].chunk_index
        lines = [doc_header, f"*Chunks {s}\u2013{e} of {total_chunks} total*", ""]
        for chunk in chunks:
            if chunk.section:
                lines.append(f"### {chunk.section}")
            lines.append(f"*[Chunk {chunk.chunk_index}]*")
            lines.append("")
            lines.append(chunk.text)
            lines.append("")
        return "\n".join(lines)

    # Long document preview (no range specified)
    if chunks:
        sections = []
        seen = set()
        for chunk in chunks:
            if chunk.section and chunk.section not in seen:
                sections.append(chunk.section)
                seen.add(chunk.section)

        lines = [doc_header, f"*{total_chunks} chunks total*", ""]
        if sections:
            lines.append("### Sections")
            for section in sections:
                lines.append(f"- {section}")
            lines.append("")
        lines.append(f"### Preview (first {len(chunks)} chunks)")
        lines.append("")
        for chunk in chunks:
            if chunk.section:
                lines.append(f"**{chunk.section}**")
            lines.append(f"*[Chunk {chunk.chunk_index}]*")
            lines.append("")
            lines.append(chunk.text)
            lines.append("")
        lines.append("---")
        lines.append(
            f"Document has {total_chunks} chunks. To read a specific section, "
            f"call `get_document_text` with `start_chunk` and `end_chunk` parameters "
            f"(0-based, inclusive). Example: start_chunk=20, end_chunk=40"
        )
        return "\n".join(lines)

    # Fallback: no text or chunks available
    return f"{doc_header}\n\nNo text content available for this document."
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_mcp_formatters.py -v`
Expected: All tests pass (Phase 1 + Phase 2)

**Step 3: Commit**
```bash
git add src/local_library/mcp/formatters.py tests/unit/test_mcp_formatters.py
git commit -m "feat(mcp): add document, listing, and text formatters with tests"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Implement show_document and list_documents tools

**Type:** Functionality (Imperative Shell)

**Files:**
- Modify: `src/local_library/mcp/server.py`

**Reference files for executor:**
- `src/local_library/cli/show.py` — Reference show implementation
- `src/local_library/cli/list.py` — Reference list implementation
- `src/local_library/core/models.py:16-31` — DocumentStatus enum values
- `src/local_library/core/library.py:993-1002` — Library.list() signature

**Step 1: Add imports and show_document tool**

Add to `server.py` imports:
```python
from local_library.core.models import DocumentStatus
from local_library.mcp.formatters import format_document, format_document_list
```

Add `show_document` tool after `search_library`:

```python
@mcp.tool(
    description=(
        "Show metadata for a specific document. Returns citekey, title, "
        "authors, date, status, embedding status, chunk count, and "
        "CSL-JSON metadata fields. Accepts UUID (full or partial) or "
        "@citekey identifier. On identifier miss, returns fuzzy match "
        "suggestions. "
        "Errors prefixed with 'USER-FACING ERROR' should be reported to "
        "the user rather than worked around."
    )
)
def show_document(doc_id: str) -> str:
    """Show metadata for a specific document.

    Args:
        doc_id: UUID (full or partial) or @citekey identifier
    """
    assert _library is not None, "Library not initialized"

    try:
        doc = resolve_identifier(doc_id, _library)
        chunk_count = _library.get_chunk_count(doc.id)
        return format_document(doc, chunk_count)

    except LookupError as e:
        suggestions = e.details.get("suggestions", [])
        if suggestions:
            suggestion_text = ", ".join(f"@{s}" for s in suggestions)
            return format_tool_error(
                f"No document found matching '{doc_id}'. "
                f"Did you mean {suggestion_text}?"
            )
        return format_tool_error(f"No document found matching '{doc_id}'.")
```

**Step 2: Add list_documents tool**

Add to `server.py`:

```python
VALID_STATUSES = ("ready", "failed", "needs_review", "pending")


@mcp.tool(
    description=(
        "List documents in the library. Returns a markdown table with "
        "citekey, title, authors, status, and embedding status. "
        "Errors prefixed with 'USER-FACING ERROR' should be reported to "
        "the user rather than worked around."
    )
)
def list_documents(
    status: str | None = None,
    limit: int = 20,
) -> str:
    """List documents in the library.

    Args:
        status: Optional filter — "ready", "failed", "needs_review", or "pending"
        limit: Maximum results to return (1-100, default 20)
    """
    assert _library is not None, "Library not initialized"

    # Validate and clamp limit
    limit = max(1, min(limit, 100))

    # Validate and parse status filter
    status_filter = None
    if status:
        if status.lower() not in VALID_STATUSES:
            return format_tool_error(
                f"invalid status: {status}. "
                f"Expected one of: {', '.join(VALID_STATUSES)}"
            )
        status_filter = DocumentStatus(status.lower())

    try:
        all_docs = _library.list(status=status_filter)
        total = len(all_docs)
        displayed = all_docs[:limit]
        return format_document_list(displayed, total)
    except Exception as e:
        logger.exception("Error listing documents")
        return format_user_error(f"Failed to list documents: {e}")
```

**Step 3: Verify import**

Run: `uv run python -c "from local_library.mcp.server import show_document, list_documents; print('OK')"`
Expected: Prints `OK`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Implement get_document_text tool

**Type:** Functionality (Imperative Shell)

**Files:**
- Modify: `src/local_library/mcp/server.py`

**Reference files for executor:**
- `src/local_library/core/models.py:33-81` — Document.extracted_path field
- `src/local_library/core/library.py` — Library.get_chunk_count(), Library.get_chunks() (added in Task 1)

**Step 1: Add get_document_text tool**

Add to `server.py` imports:
```python
from pathlib import Path
from local_library.mcp.formatters import format_document_text
```

Add constants and tool:

```python
# Threshold for "short" documents (full text returned)
SHORT_DOC_THRESHOLD = 50
# Number of chunks to show in preview mode
PREVIEW_CHUNK_COUNT = 20


@mcp.tool(
    description=(
        "Get the extracted text content of a document. Short documents "
        "(<50 chunks) return full text. Long documents without a chunk "
        "range return a preview with section outline and instructions "
        "for requesting specific ranges. Specify start_chunk and "
        "end_chunk (0-based, inclusive) for a specific section. "
        "Errors prefixed with 'USER-FACING ERROR' should be reported to "
        "the user rather than worked around."
    )
)
def get_document_text(
    doc_id: str,
    start_chunk: int | None = None,
    end_chunk: int | None = None,
) -> str:
    """Get extracted text content of a document.

    Args:
        doc_id: UUID (full or partial) or @citekey identifier
        start_chunk: Optional 0-based chunk index to start from
        end_chunk: Optional chunk index to end at (inclusive)
    """
    assert _library is not None, "Library not initialized"

    try:
        doc = resolve_identifier(doc_id, _library)
    except LookupError as e:
        suggestions = e.details.get("suggestions", [])
        if suggestions:
            suggestion_text = ", ".join(f"@{s}" for s in suggestions)
            return format_tool_error(
                f"No document found matching '{doc_id}'. "
                f"Did you mean {suggestion_text}?"
            )
        return format_tool_error(f"No document found matching '{doc_id}'.")

    # Check that extracted text exists
    if not doc.extracted_path:
        return format_tool_error(
            f"No extracted text available for @{doc.citekey or doc_id}. "
            f"Document status: {doc.status.value}"
        )

    total_chunks = _library.get_chunk_count(doc.id)

    # Short document: return full extracted markdown
    if total_chunks < SHORT_DOC_THRESHOLD:
        try:
            text = Path(doc.extracted_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return format_tool_error(
                f"Extracted file not found at {doc.extracted_path}. "
                "The file may have been moved or deleted."
            )
        return format_document_text(
            doc, text=text, chunks=None, total_chunks=total_chunks
        )

    # Long document with range: return chunk subset
    if start_chunk is not None or end_chunk is not None:
        s = start_chunk if start_chunk is not None else 0
        e = end_chunk if end_chunk is not None else total_chunks - 1

        if s < 0 or e < 0:
            return format_tool_error("Chunk indices must be non-negative.")
        if s > e:
            return format_tool_error(
                f"start_chunk ({s}) must be <= end_chunk ({e})."
            )
        if s >= total_chunks:
            return format_tool_error(
                f"start_chunk ({s}) out of range. "
                f"Document has {total_chunks} chunks (0-{total_chunks - 1})."
            )

        chunks = _library.get_chunks(doc.id, start=s, end=e)
        return format_document_text(
            doc, text=None, chunks=chunks, total_chunks=total_chunks,
            start_chunk=s, end_chunk=min(e, total_chunks - 1),
        )

    # Long document without range: preview mode
    chunks = _library.get_chunks(doc.id, start=0, end=PREVIEW_CHUNK_COUNT - 1)
    return format_document_text(
        doc, text=None, chunks=chunks, total_chunks=total_chunks
    )
```

**Step 2: Verify import**

Run: `uv run python -c "from local_library.mcp.server import get_document_text; print('OK')"`
Expected: Prints `OK`

<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_TASK_6 -->
### Task 6: Write server tests for Phase 2 tools

**Type:** Functionality (verify tool behavior)

**Files:**
- Modify: `tests/unit/test_mcp_server.py`

**Reference files for executor:**
- `tests/unit/test_cli_search.py` — Reference mock patterns
- `src/local_library/core/errors.py` — Error constructors

**Step 1: Add Phase 2 tool tests**

Add to `tests/unit/test_mcp_server.py`. Import the new tools and add helper:

```python
from local_library.core.models import Document, DocumentStatus, EmbeddingStatus
from local_library.mcp.server import show_document, list_documents, get_document_text


def _make_document(citekey="Author2023", title="Test Doc", status=DocumentStatus.READY):
    """Create a mock Document for testing."""
    doc = MagicMock(spec=Document)
    doc.id = uuid4()
    doc.citekey = citekey
    doc.title = title
    doc.authors = "Test Author"
    doc.issued_date = "2023"
    doc.status = status
    doc.embedding_status = EmbeddingStatus.CURRENT
    doc.original_path = "/path/to/doc.pdf"
    doc.extracted_path = "/path/to/extracted.md"
    doc.csl_json = {"type": "article-journal", "title": title}
    doc.content_hash = "abc123"
    doc.storage_path = "/storage/ab/cd/abc123.pdf"
    doc.created_at = datetime(2023, 6, 15, tzinfo=timezone.utc)
    doc.updated_at = datetime(2023, 6, 15, tzinfo=timezone.utc)
    doc.error_message = None
    doc.error_code = None
    return doc


class TestShowDocument:
    """Tests for show_document tool."""

    @pytest.fixture(autouse=True)
    def setup_mock_library(self):
        self.mock_library = MagicMock()
        with patch("local_library.mcp.server._library", self.mock_library):
            yield

    @patch("local_library.mcp.server.resolve_identifier")
    def test_returns_document_metadata(self, mock_resolve) -> None:
        """Returns formatted document metadata."""
        doc = _make_document(citekey="Bourdieu1984")
        mock_resolve.return_value = doc
        self.mock_library.get_chunk_count.return_value = 100
        result = show_document("@Bourdieu1984")
        assert "@Bourdieu1984" in result

    @patch("local_library.mcp.server.resolve_identifier")
    def test_not_found_returns_error_with_suggestions(self, mock_resolve) -> None:
        """Missing document returns suggestions."""
        mock_resolve.side_effect = LookupError(
            "not found", ErrorCode.NOT_FOUND,
            details={"suggestions": ["Author2023"]},
        )
        result = show_document("@Auth2023")
        assert "Error: " in result
        assert "@Author2023" in result


class TestListDocuments:
    """Tests for list_documents tool."""

    @pytest.fixture(autouse=True)
    def setup_mock_library(self):
        self.mock_library = MagicMock()
        with patch("local_library.mcp.server._library", self.mock_library):
            yield

    def test_returns_document_table(self) -> None:
        """Returns markdown table of documents."""
        docs = [_make_document(citekey=f"Author{i}") for i in range(3)]
        self.mock_library.list.return_value = docs
        result = list_documents()
        assert "|" in result
        assert "@Author0" in result

    def test_invalid_status_returns_error(self) -> None:
        """Invalid status filter returns tool error."""
        result = list_documents(status="bogus")
        assert result.startswith("Error: ")

    def test_limit_clamped(self) -> None:
        """Limit clamped to 100."""
        docs = [_make_document() for _ in range(5)]
        self.mock_library.list.return_value = docs
        result = list_documents(limit=200)
        assert "|" in result

    def test_status_filter_forwarded(self) -> None:
        """Status filter forwarded to Library.list()."""
        self.mock_library.list.return_value = []
        list_documents(status="ready")
        self.mock_library.list.assert_called_with(status=DocumentStatus.READY)


class TestGetDocumentText:
    """Tests for get_document_text tool."""

    @pytest.fixture(autouse=True)
    def setup_mock_library(self):
        self.mock_library = MagicMock()
        with patch("local_library.mcp.server._library", self.mock_library):
            yield

    @patch("local_library.mcp.server.resolve_identifier")
    @patch("local_library.mcp.server.Path")
    def test_short_doc_returns_full_text(self, mock_path_cls, mock_resolve) -> None:
        """Short doc (<50 chunks) returns full extracted text."""
        doc = _make_document()
        mock_resolve.return_value = doc
        self.mock_library.get_chunk_count.return_value = 10
        mock_path_cls.return_value.read_text.return_value = "# Full content"
        result = get_document_text("@Author2023")
        assert "Full content" in result

    @patch("local_library.mcp.server.resolve_identifier")
    def test_long_doc_without_range_shows_preview(self, mock_resolve) -> None:
        """Long doc without range shows preview with instructions."""
        doc = _make_document()
        mock_resolve.return_value = doc
        self.mock_library.get_chunk_count.return_value = 200
        self.mock_library.get_chunks.return_value = [
            _make_chunk(chunk_index=i, text=f"Preview {i}")
            for i in range(20)
        ]
        result = get_document_text("@Author2023")
        assert "200" in result
        assert "Preview 0" in result

    @patch("local_library.mcp.server.resolve_identifier")
    def test_long_doc_with_range_returns_chunks(self, mock_resolve) -> None:
        """Long doc with range returns specific chunks."""
        doc = _make_document()
        mock_resolve.return_value = doc
        self.mock_library.get_chunk_count.return_value = 200
        self.mock_library.get_chunks.return_value = [
            _make_chunk(chunk_index=i, text=f"Content {i}")
            for i in range(10, 15)
        ]
        result = get_document_text("@Author2023", start_chunk=10, end_chunk=14)
        assert "Content 10" in result

    @patch("local_library.mcp.server.resolve_identifier")
    def test_no_extracted_path_returns_error(self, mock_resolve) -> None:
        """Doc without extracted_path returns tool error."""
        doc = _make_document()
        doc.extracted_path = None
        mock_resolve.return_value = doc
        result = get_document_text("@Author2023")
        assert "Error: " in result

    @patch("local_library.mcp.server.resolve_identifier")
    def test_invalid_range_returns_error(self, mock_resolve) -> None:
        """start_chunk > end_chunk returns tool error."""
        doc = _make_document()
        mock_resolve.return_value = doc
        self.mock_library.get_chunk_count.return_value = 200
        result = get_document_text("@Author2023", start_chunk=20, end_chunk=10)
        assert "Error: " in result
```

**Step 2: Run all tests**

Run: `uv run pytest tests/unit/test_mcp_server.py -v`
Expected: All tests pass

Run: `uv run pytest tests/unit/ --tb=short -q`
Expected: Full suite passes

**Step 3: Commit**
```bash
git add src/local_library/mcp/server.py tests/unit/test_mcp_server.py
git commit -m "feat(mcp): add show_document, list_documents, get_document_text tools with tests"
```
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Update CLAUDE.md files

**Type:** Infrastructure

**Files:**
- Modify: `src/local_library/mcp/CLAUDE.md`
- Modify: `src/local_library/core/CLAUDE.md` (document new public methods)

**Step 1: Update mcp/CLAUDE.md**

Update the Contracts section to reflect all 4 tools as implemented:
- Change "show_document, list_documents, get_document_text planned for Phase 2" to list all 4 tools as implemented
- Add invariants for the new tools (identifier resolution, file reading, chunk range validation)
- Add gotchas for get_document_text file reading and the short/long doc threshold

**Step 2: Update core/CLAUDE.md**

Add the new public methods to the Contracts and Key Decisions sections:
- `Library.get_chunk_count(doc_id) -> int` — returns 0 if sqlite-vec unavailable
- `Library.get_chunks(doc_id, start, end) -> list[Chunk]` — returns empty list if sqlite-vec unavailable, supports index-range filtering

**Step 3: Run lint and tests**

Run: `uv run ruff check src/local_library/mcp/`
Run: `uv run ruff format --check src/local_library/mcp/`
Run: `uv run pytest tests/unit/ --tb=short -q`
Expected: All pass

**Step 4: Commit**
```bash
git add src/local_library/mcp/CLAUDE.md src/local_library/core/CLAUDE.md
git commit -m "docs: update CLAUDE.md files for Phase 2 MCP tools and Library chunk methods"
```
<!-- END_TASK_7 -->

---

**Phase 2 complete when:**
- All 4 tools work: `search_library`, `show_document`, `list_documents`, `get_document_text`
- `get_document_text` correctly handles short docs (full text), long docs with range (chunk subset), and long docs without range (preview + instructions)
- Formatters have unit tests for all output functions
- Error convention tested for both tiers (user-facing and tool-level)
- Library has public `get_chunk_count()` and `get_chunks()` methods
- Full unit test suite passes
