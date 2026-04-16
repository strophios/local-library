# MCP Server Implementation Plan — Phase 3

**Goal:** Verified end-to-end behavior, documentation, and any fixes from real usage.

**Codebase verified:** 2026-04-15

---

## Phase 3: Integration Testing and Polish

<!-- START_TASK_1 -->
### Task 1: stdout discipline audit test

**Type:** Functionality

**Files:**
- Create: `tests/unit/test_mcp_stdout.py`

**Reference files for executor:**
- `src/local_library/mcp/server.py` — main() function with logging setup
- `src/local_library/core/library.py:101-134` — Library constructor

**Why this matters:** The MCP stdio transport reserves stdout exclusively for JSON-RPC protocol messages. If Library initialization, model loading, or tool execution writes to stdout (via print(), logging misconfiguration, or third-party library output), it corrupts the protocol and breaks the MCP connection. This test catches stdout pollution before it reaches production.

**Step 1: Write stdout audit test**

Create `tests/unit/test_mcp_stdout.py`:

```python
"""Tests that MCP server components don't write to stdout.

The stdio transport reserves stdout for JSON-RPC protocol messages.
Any stdout output from Library, formatters, or tool functions would
corrupt the protocol stream.
"""

import io
import sys
from unittest.mock import MagicMock, patch

import pytest

from local_library.mcp.formatters import (
    format_document,
    format_document_list,
    format_document_text,
    format_empty_results,
    format_search_results,
    format_tool_error,
    format_user_error,
)


class TestFormatterStdoutDiscipline:
    """Verify formatters never write to stdout."""

    def test_format_search_results_no_stdout(self) -> None:
        """format_search_results produces no stdout output."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_search_results([], "test query")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == "", f"Unexpected stdout: {captured.getvalue()!r}"

    def test_format_user_error_no_stdout(self) -> None:
        """format_user_error produces no stdout output."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_user_error("test error")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""

    def test_format_tool_error_no_stdout(self) -> None:
        """format_tool_error produces no stdout output."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_tool_error("test error")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""

    def test_format_empty_results_no_stdout(self) -> None:
        """format_empty_results produces no stdout output."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_empty_results("test query")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""

    def test_format_document_no_stdout(self) -> None:
        """format_document produces no stdout output."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from local_library.core.models import Document, DocumentStatus, EmbeddingStatus

        doc = Document(
            id=uuid4(), original_path="/p.pdf", content_hash="abc",
            storage_path="/s/abc.pdf", status=DocumentStatus.READY,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_document(doc, chunk_count=0)
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""

    def test_format_document_list_no_stdout(self) -> None:
        """format_document_list produces no stdout output."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_document_list([], total=0)
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""

    def test_format_document_text_no_stdout(self) -> None:
        """format_document_text produces no stdout output."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from local_library.core.models import Document, DocumentStatus, EmbeddingStatus

        doc = Document(
            id=uuid4(), original_path="/p.pdf", content_hash="abc",
            storage_path="/s/abc.pdf", status=DocumentStatus.READY,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_document_text(doc, text="content", chunks=None, total_chunks=1)
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""


class TestToolFunctionStdoutDiscipline:
    """Verify tool functions don't write to stdout when called."""

    @pytest.fixture(autouse=True)
    def setup_mock_library(self):
        """Mock Library so tools can execute without real database."""
        self.mock_library = MagicMock()
        self.mock_retriever = MagicMock()
        self.mock_library.get_retriever.return_value = self.mock_retriever
        self.mock_retriever.retrieve.return_value = []
        self.mock_library.list.return_value = []
        self.mock_library.get_chunk_count.return_value = 0

        with patch("local_library.mcp.server._library", self.mock_library):
            yield

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_search_library_no_stdout(self, _mock_vec) -> None:
        """search_library produces no stdout output."""
        from local_library.mcp.server import search_library

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            search_library("test query")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == "", f"Unexpected stdout: {captured.getvalue()!r}"

    def test_list_documents_no_stdout(self) -> None:
        """list_documents produces no stdout output."""
        from local_library.mcp.server import list_documents

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            list_documents()
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == "", f"Unexpected stdout: {captured.getvalue()!r}"

    @patch("local_library.mcp.server.resolve_identifier")
    def test_show_document_no_stdout(self, mock_resolve) -> None:
        """show_document produces no stdout output."""
        from local_library.mcp.server import show_document

        mock_doc = MagicMock()
        mock_doc.id = MagicMock()
        mock_doc.citekey = "Test2023"
        mock_doc.title = "Test"
        mock_doc.authors = None
        mock_doc.issued_date = None
        mock_doc.status = MagicMock(value="ready")
        mock_doc.embedding_status = MagicMock(value="current")
        mock_doc.csl_json = None
        mock_doc.original_path = "/test.pdf"
        mock_resolve.return_value = mock_doc

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            show_document("@Test2023")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == "", f"Unexpected stdout: {captured.getvalue()!r}"

    @patch("local_library.mcp.server.resolve_identifier")
    def test_get_document_text_no_stdout(self, mock_resolve) -> None:
        """get_document_text produces no stdout output."""
        from local_library.mcp.server import get_document_text

        mock_doc = MagicMock()
        mock_doc.extracted_path = None  # Triggers error path (simplest)
        mock_doc.citekey = "Test2023"
        mock_doc.status = MagicMock(value="ready")
        mock_resolve.return_value = mock_doc

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            get_document_text("@Test2023")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == "", f"Unexpected stdout: {captured.getvalue()!r}"
```

**Step 2: Run tests**

Run: `uv run pytest tests/unit/test_mcp_stdout.py -v`
Expected: All pass (formatters and tools return strings, don't print)

**Step 3: Commit**
```bash
git add tests/unit/test_mcp_stdout.py
git commit -m "test(mcp): add stdout discipline audit tests"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: End-to-end verification in Claude Code

**Type:** Infrastructure (manual verification — SKIP DURING AUTOMATED EXECUTION)

**⚠ EXECUTOR NOTE:** This task requires manual testing outside the implementation session. The execution agent should **skip this task** and mark it as deferred. It will be performed by the user after the branch is complete.

**Why this can't be automated:** MCP tool discovery, real corpus search, model loading latency, and protocol correctness all require a live Claude Code session connected to the MCP server subprocess. Unit tests (Phase 1-2) verify tool logic with mocked Library; this task verifies the full stack works end-to-end.

**Files:** None created — this is a post-implementation testing checklist

**Post-implementation verification steps (for user):**

1. **Server startup**: Run `uv run local-library-mcp` from the project root. Verify it starts without errors on stderr. Stop with Ctrl+C.

2. **Tool discovery**: In a new Claude Code session with this project open, verify that `.mcp.json` is detected and the `local-library` MCP server starts. Check that Claude Code can see the 4 tools (`search_library`, `show_document`, `list_documents`, `get_document_text`).

3. **Search tool**: Ask Claude Code to search the library for a topic. Verify:
   - Results return with citekeys, scores, section headers, chunk text
   - Scores are formatted to 3 decimal places
   - Results are numbered sequentially
   - Empty results return helpful suggestion

4. **Show document**: Ask Claude Code to show details for a specific citekey. Verify:
   - Metadata displays correctly (title, authors, date, status)
   - Chunk count appears
   - CSL-JSON fields appear
   - Invalid citekey returns fuzzy suggestions

5. **List documents**: Ask Claude Code to list documents. Verify:
   - Markdown table renders correctly
   - "Showing X of Y" header is accurate
   - Status filter works

6. **Get document text**: Test with a short and long document:
   - Short doc: full text returned
   - Long doc without range: preview + section outline + instructions
   - Long doc with range: specific chunks returned

7. **Model loading latency**: On first search after server start, note the ~2-5s delay for embedder loading. Verify subsequent searches are fast.

8. **Error handling**: Test error cases:
   - Invalid search mode → tool error
   - Nonexistent citekey → fuzzy suggestions
   - Search when sqlite-vec is unavailable → user-facing error (if testable)

**Record any issues found.** If fixes are needed, implement them as additional commits on the `mcp-server` branch.

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update project CLAUDE.md with MCP server information

**Type:** Infrastructure

**Files:**
- Modify: `CLAUDE.md` (project root)

**Step 1: Add MCP server to Commands section**

Add to the Commands section in `CLAUDE.md`:

```markdown
- `uv run local-library-mcp` - Start the MCP server (stdio transport, for Claude Code integration)
```

**Step 2: Add MCP server to Package Structure**

Add `mcp/` to the package structure tree:

```
├── mcp/                 # MCP server for Claude Code integration
│   ├── server.py        # FastMCP app, tool definitions, Library lifecycle (Imperative Shell)
│   ├── formatters.py    # Markdown rendering functions (Functional Core)
│   └── CLAUDE.md        # Domain contracts
```

**Step 3: Add MCP server note to Architectural Layers**

In the Interface layer (layer 5), add MCP alongside CLI:

```
5. **Interface**: CLI, MCP server, (later) daemon, Neovim plugin, HTTP API
```

**Step 4: Add reference to domain CLAUDE.md list**

Add `src/local_library/mcp/CLAUDE.md` to the list of domain contract files.

**Step 5: Commit**
```bash
git add CLAUDE.md
git commit -m "docs: add MCP server to project CLAUDE.md"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Final verification and lint

**Type:** Infrastructure

**Step 1: Run full linting**

Run: `uv run ruff check src/local_library/mcp/`
Expected: No errors

Run: `uv run ruff format --check src/local_library/mcp/`
Expected: All files formatted

**Step 2: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests pass (original 1014 + new MCP tests)

**Step 3: Verify MCP package structure**

Run: `ls -la src/local_library/mcp/`
Expected:
```
__init__.py
CLAUDE.md
formatters.py
server.py
```

**Step 4: Verify entry point**

Run: `uv run python -c "from local_library.mcp.server import mcp; print(f'Tools: {len(mcp._tool_manager._tools) if hasattr(mcp, \"_tool_manager\") else \"check manually\"}')"` 
Expected: Shows 4 tools (or verify manually that all 4 tool functions are registered)

**Step 5: Commit any final fixes**

If any issues found, fix and commit.
<!-- END_TASK_4 -->

---

**Phase 3 complete when:**
- stdout audit tests pass (formatters and tools don't write to stdout)
- End-to-end verification completed in Claude Code
- Project CLAUDE.md updated with MCP server information
- All linting passes
- Full unit test suite passes
- No stdout corruption observed during real usage
