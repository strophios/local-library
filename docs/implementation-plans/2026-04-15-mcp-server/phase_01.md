# MCP Server Implementation Plan

**Goal:** Build a working MCP server exposing the local-library document corpus to Claude Code via 4 read-only tools over stdio transport using FastMCP

**Architecture:** FastMCP server wrapping existing Library API. Functional Core formatters (pure markdown rendering) + Imperative Shell server (Library lifecycle, MCP protocol). Module-level Library instance created once at startup, shared across tool calls. Models load lazily on first use.

**Tech Stack:** mcp (FastMCP framework), Python, existing Library/Retriever/SearchResult types

**Scope:** 3 phases from original design (full implementation)

**Codebase verified:** 2026-04-15

**Design plan:** `docs/design-plans/2026-04-15-mcp-server.md`

---

## Phase 1: Server Scaffold + Search Tool

**Goal:** A working MCP server with `search_library` tool that Claude Code can discover and call.

<!-- START_SUBCOMPONENT_A (tasks 1) -->
<!-- START_TASK_1 -->
### Task 1: Add mcp dependency, create package scaffold, entry point, and .mcp.json

**Type:** Infrastructure

**Files:**
- Modify: `pyproject.toml:11-23` (dependencies), `pyproject.toml:37-38` (scripts)
- Create: `src/local_library/mcp/__init__.py`
- Create: `src/local_library/mcp/server.py`
- Create: `src/local_library/mcp/formatters.py`
- Create: `.mcp.json`

**Step 1: Add mcp dependency to pyproject.toml**

In the `[project.dependencies]` list (lines 11-23), add `"mcp>=1.27.0",` maintaining alphabetical order.

In `[project.scripts]` (line 37-38), add: `local-library-mcp = "local_library.mcp.server:main"`

**Step 2: Create package files**

Create `src/local_library/mcp/__init__.py`:
```python
"""MCP server module — exposes the document library to Claude Code."""
```

Create `src/local_library/mcp/formatters.py`:
```python
"""Markdown formatters for MCP tool responses."""

# pattern: Functional Core
```

Create `src/local_library/mcp/server.py`:
```python
"""MCP server — wraps Library API for Claude Code integration."""

# pattern: Imperative Shell

import logging
import sys

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("local-library")


def main() -> None:
    """Entry point for the MCP server."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.info("Starting local-library MCP server")
    mcp.run(transport="stdio")
```

Create `.mcp.json` at project root:
```json
{
  "mcpServers": {
    "local-library": {
      "command": "uv",
      "args": ["run", "local-library-mcp"]
    }
  }
}
```

**Step 3: Verify operationally**

Run: `uv sync --extra dev`
Expected: Installs without errors (`mcp` package resolved and installed)

Run: `uv run python -c "from local_library.mcp.server import main; print('OK')"`
Expected: Prints `OK`

Run: `timeout 3 uv run local-library-mcp 2>/dev/null; echo "exit: $?"`
Expected: Server starts and times out (exit code 124) or exits cleanly. No crash on startup.

**Step 4: Commit**
```bash
git add pyproject.toml uv.lock src/local_library/mcp/__init__.py src/local_library/mcp/server.py src/local_library/mcp/formatters.py .mcp.json
git commit -m "feat(mcp): add package scaffold, mcp dependency, and entry point"
```
<!-- END_TASK_1 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Write formatter tests

**Type:** Functionality (test-first)

**Files:**
- Create: `tests/unit/test_mcp_formatters.py`

**Reference files for executor:**
- `src/local_library/embeddings/base.py:14-73` — Chunk dataclass fields
- `src/local_library/embeddings/base.py:169-188` — SearchResult dataclass fields

**Step 1: Write failing tests**

Create `tests/unit/test_mcp_formatters.py`:
```python
"""Tests for MCP markdown formatters."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

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
        chunk=_make_chunk(
            doc_id=doc_id, chunk_index=chunk_index, text=text, section=section
        ),
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_mcp_formatters.py -v`
Expected: ImportError — `format_search_results` etc. not yet defined in `formatters.py`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement formatters

**Type:** Functionality (make tests pass)

**Files:**
- Modify: `src/local_library/mcp/formatters.py`

**Step 1: Implement formatters.py**

Write the full `formatters.py`:
```python
"""Markdown formatters for MCP tool responses."""

# pattern: Functional Core

from local_library.embeddings.base import SearchResult


def format_search_results(results: list[SearchResult], query: str) -> str:
    """Format search results as markdown.

    Produces numbered results with citekeys, scores, section headers,
    chunk indices, and blockquoted text excerpts.

    Args:
        results: Search results sorted by score descending
        query: Original search query (used in empty results message)

    Returns:
        Markdown-formatted results string
    """
    if not results:
        return format_empty_results(query)

    # Count unique documents for header
    doc_ids = {r.chunk.doc_id for r in results}

    lines = [
        f"### Results ({len(results)} chunks from {len(doc_ids)} documents)",
        "",
    ]

    for i, r in enumerate(results, start=1):
        # Source identifier: prefer @citekey, fall back to title, then UUID prefix
        if r.doc_citekey:
            source = f"**@{r.doc_citekey}**"
        elif r.doc_title:
            source = f"**{r.doc_title}**"
        else:
            source = f"**{str(r.chunk.doc_id)[:8]}**"

        # Title in italics when citekey is the primary identifier
        title_part = f" | *{r.doc_title}*" if r.doc_citekey and r.doc_title else ""

        lines.append(f"{i}. {source} | score: {r.score:.3f}{title_part}")

        # Section header
        if r.chunk.section:
            lines.append(f"   Section: {r.chunk.section}")

        # Chunk index (labeled for follow-up get_document_text calls)
        lines.append(f"   Chunk {r.chunk.chunk_index}")

        # Chunk text as blockquote, truncated to ~300 chars
        text = r.chunk.text.strip()
        if len(text) > 300:
            text = text[:297] + "..."

        for text_line in text.split("\n"):
            lines.append(f"   > {text_line}")

        lines.append("")  # Blank line between results

    return "\n".join(lines)


def format_user_error(message: str) -> str:
    """Format a user-facing error with the standard prefix.

    User-facing errors indicate infrastructure problems that Claude should
    report to the user rather than attempting to work around.

    Args:
        message: Error description

    Returns:
        Prefixed error string
    """
    return f"\u26a0 USER-FACING ERROR: {message}"


def format_tool_error(message: str) -> str:
    """Format a tool-level error.

    Tool-level errors are things Claude can handle or work around,
    like document-not-found with fuzzy match suggestions.

    Args:
        message: Error description

    Returns:
        Prefixed error string
    """
    return f"Error: {message}"


def format_empty_results(query: str) -> str:
    """Format a helpful message when search returns no results.

    Args:
        query: The original search query

    Returns:
        Suggestion string for improving the search
    """
    return (
        f'No results found for "{query}". '
        "Try different search terms, broader keywords, "
        'or use mode="fts" for exact keyword matching.'
    )
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_mcp_formatters.py -v`
Expected: All tests pass

**Step 3: Commit**
```bash
git add src/local_library/mcp/formatters.py tests/unit/test_mcp_formatters.py
git commit -m "feat(mcp): add search result and error formatters with tests"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Implement search_library tool in server.py

**Type:** Functionality (Imperative Shell)

**Files:**
- Modify: `src/local_library/mcp/server.py`

**Reference files for executor:**
- `src/local_library/cli/search.py:97-131` — Reference search implementation (how CLI calls retriever, handles errors)
- `src/local_library/cli/utils.py:92-125` — `resolve_identifier()` function and `LibraryProtocol`
- `src/local_library/core/library.py:101-116` — Library constructor (use `embed_on_add=False`)
- `src/local_library/core/library.py:236-293` — `get_retriever(mode, rerank)` signature
- `src/local_library/core/errors.py` — Error types: LookupError, EmbeddingError, FTSQueryError
- `src/local_library/core/vec_extension.py` — `is_vec_available()` function

**Step 1: Implement full server.py**

Replace `src/local_library/mcp/server.py` with:
```python
"""MCP server — wraps Library API for Claude Code integration."""

# pattern: Imperative Shell

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from local_library.cli.utils import resolve_identifier
from local_library.core.errors import EmbeddingError, FTSQueryError, LookupError
from local_library.core.library import Library
from local_library.core.vec_extension import is_vec_available
from local_library.mcp.formatters import (
    format_search_results,
    format_tool_error,
    format_user_error,
)

logger = logging.getLogger(__name__)

# Valid search modes
VALID_MODES = ("hybrid", "vector", "fts")

# FastMCP application
mcp = FastMCP("local-library")

# Library instance (created in main(), shared across tool calls)
_library: Library | None = None


@mcp.tool(
    description=(
        "Search the document library using semantic and keyword search. "
        "Returns markdown with ranked results including citekeys, scores, "
        "section headers, and chunk text. Use chunk indices for follow-up "
        "get_document_text calls. "
        "Errors prefixed with 'USER-FACING ERROR' should be reported to "
        "the user rather than worked around."
    )
)
def search_library(
    query: str,
    limit: int = 10,
    mode: str = "hybrid",
    doc_id: str | None = None,
    no_rerank: bool = False,
) -> str:
    """Search the document library.

    Args:
        query: Search query string (natural language or keywords)
        limit: Maximum results to return (1-100, default 10)
        mode: Search mode — "hybrid" (default), "vector", or "fts"
        doc_id: Optional UUID or @citekey to scope search to one document
        no_rerank: Disable cross-encoder reranking (default: False)
    """
    assert _library is not None, "Library not initialized"

    # Validate and clamp limit
    limit = max(1, min(limit, 100))

    # Validate mode
    if mode not in VALID_MODES:
        return format_tool_error(
            f"invalid mode: {mode}. Expected one of: {', '.join(VALID_MODES)}"
        )

    # Check sqlite-vec availability (required for vector and hybrid modes, not FTS)
    if mode != "fts" and not is_vec_available():
        return format_user_error(
            "Vector search unavailable. The sqlite-vec extension is not loaded. "
            "This significantly impacts search quality. Please inform the user "
            "and suggest running `uv run local-library search` from the terminal "
            "to diagnose. You can still search using mode='fts' for keyword matching."
        )

    try:
        # Resolve document filter if provided
        doc_ids = None
        if doc_id:
            doc = resolve_identifier(doc_id, _library)
            doc_ids = [doc.id]

        # Get retriever and search
        retriever = _library.get_retriever(mode=mode, rerank=not no_rerank)
        results = retriever.retrieve(query, k=limit, doc_ids=doc_ids)

        return format_search_results(results, query)

    except LookupError as e:
        suggestions = e.details.get("suggestions", [])
        if suggestions:
            suggestion_text = ", ".join(f"@{s}" for s in suggestions)
            return format_tool_error(
                f"{e.message}. Did you mean {suggestion_text}?"
            )
        return format_tool_error(e.message)
    except EmbeddingError as e:
        return format_user_error(str(e))
    except FTSQueryError as e:
        return format_tool_error(
            f"{e.message}. Try a different search query or use mode='vector'."
        )


def main() -> None:
    """Entry point for the MCP server."""
    global _library

    # Configure all logging to stderr (stdout reserved for JSON-RPC protocol)
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Suppress HuggingFace tokenizer parallelism warning
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    logger.info("Starting local-library MCP server")

    # Create Library instance (read-only, no embed-on-add)
    _library = Library(embed_on_add=False)

    try:
        mcp.run(transport="stdio")
    finally:
        if _library is not None:
            _library.close()
            logger.info("Library closed")
```

**Step 2: Verify import succeeds**

Run: `uv run python -c "from local_library.mcp.server import search_library; print('OK')"`
Expected: Prints `OK`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Write server tool tests

**Type:** Functionality (verify tool behavior)

**Files:**
- Create: `tests/unit/test_mcp_server.py`

**Reference files for executor:**
- `tests/unit/test_cli_search.py` — Reference for how CLI search is tested with mocked Library
- `src/local_library/core/errors.py` — Error constructors: `ErrorType(message, ErrorCode.CODE, details={})`

**Step 1: Write server tests**

Create `tests/unit/test_mcp_server.py`:
```python
"""Tests for MCP server tool functions."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from local_library.core.errors import EmbeddingError, ErrorCode, FTSQueryError, LookupError
from local_library.embeddings.base import Chunk, SearchResult
from local_library.mcp.server import search_library


def _make_chunk(doc_id=None, chunk_index=0, text="Sample text.", section="Intro"):
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


def _make_result(score=0.95, doc_citekey="Author2023", doc_title="Test Doc", **kwargs):
    """Create a SearchResult for testing."""
    chunk_kwargs = {k: v for k, v in kwargs.items() if k in ("doc_id", "chunk_index", "text", "section")}
    return SearchResult(
        chunk=_make_chunk(**chunk_kwargs),
        score=score,
        doc_title=doc_title,
        doc_citekey=doc_citekey,
        search_methods=frozenset(["hybrid"]),
    )


class TestSearchLibrary:
    """Tests for the search_library tool function."""

    @pytest.fixture(autouse=True)
    def setup_mock_library(self):
        """Provide mock Library and retriever for all tests."""
        self.mock_library = MagicMock()
        self.mock_retriever = MagicMock()
        self.mock_library.get_retriever.return_value = self.mock_retriever

        with patch("local_library.mcp.server._library", self.mock_library):
            yield

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_basic_search_returns_formatted_markdown(self, _mock_vec) -> None:
        """Basic search returns markdown with citekey and score."""
        self.mock_retriever.retrieve.return_value = [_make_result()]
        result = search_library("machine learning")
        assert "@Author2023" in result
        assert "Results" in result

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_limit_clamped_to_100(self, _mock_vec) -> None:
        """Limit above 100 is clamped."""
        self.mock_retriever.retrieve.return_value = []
        search_library("query", limit=200)
        _, kwargs = self.mock_retriever.retrieve.call_args
        assert kwargs["k"] == 100

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_limit_minimum_is_1(self, _mock_vec) -> None:
        """Limit below 1 is clamped to 1."""
        self.mock_retriever.retrieve.return_value = []
        search_library("query", limit=-5)
        _, kwargs = self.mock_retriever.retrieve.call_args
        assert kwargs["k"] == 1

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_invalid_mode_returns_tool_error(self, _mock_vec) -> None:
        """Invalid mode returns Error: prefix."""
        result = search_library("query", mode="invalid")
        assert result.startswith("Error: ")
        assert "invalid" in result

    @patch("local_library.mcp.server.is_vec_available", return_value=False)
    def test_vec_unavailable_returns_user_error_for_hybrid(self, _mock_vec) -> None:
        """Missing sqlite-vec returns USER-FACING ERROR for hybrid mode."""
        result = search_library("query")
        assert "USER-FACING ERROR" in result

    @patch("local_library.mcp.server.is_vec_available", return_value=False)
    def test_fts_mode_works_without_vec(self, _mock_vec) -> None:
        """FTS mode works even without sqlite-vec."""
        self.mock_retriever.retrieve.return_value = []
        result = search_library("query", mode="fts")
        assert "USER-FACING ERROR" not in result

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_mode_forwarded_to_retriever(self, _mock_vec) -> None:
        """Mode parameter forwarded to get_retriever."""
        self.mock_retriever.retrieve.return_value = []
        search_library("query", mode="fts")
        self.mock_library.get_retriever.assert_called_with(mode="fts", rerank=True)

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_no_rerank_disables_reranking(self, _mock_vec) -> None:
        """no_rerank=True passes rerank=False to get_retriever."""
        self.mock_retriever.retrieve.return_value = []
        search_library("query", no_rerank=True)
        self.mock_library.get_retriever.assert_called_with(mode="hybrid", rerank=False)

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    @patch("local_library.mcp.server.resolve_identifier")
    def test_doc_id_resolved_and_passed(self, mock_resolve, _mock_vec) -> None:
        """doc_id is resolved via resolve_identifier and passed as doc_ids."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_resolve.return_value = mock_doc
        self.mock_retriever.retrieve.return_value = []

        search_library("query", doc_id="@Author2023")
        mock_resolve.assert_called_once_with("@Author2023", self.mock_library)
        _, kwargs = self.mock_retriever.retrieve.call_args
        assert kwargs["doc_ids"] == [mock_doc.id]

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    @patch("local_library.mcp.server.resolve_identifier")
    def test_lookup_error_includes_suggestions(self, mock_resolve, _mock_vec) -> None:
        """LookupError with suggestions formats them with @ prefix."""
        mock_resolve.side_effect = LookupError(
            "citekey not found: Auth2023",
            ErrorCode.NOT_FOUND,
            details={"citekey": "Auth2023", "suggestions": ["Author2023", "AuthorB2023"]},
        )
        result = search_library("query", doc_id="@Auth2023")
        assert result.startswith("Error: ")
        assert "@Author2023" in result
        assert "@AuthorB2023" in result

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_embedding_error_returns_user_error(self, _mock_vec) -> None:
        """EmbeddingError returns USER-FACING ERROR."""
        self.mock_library.get_retriever.side_effect = EmbeddingError(
            "model load failed", ErrorCode.EMBEDDING_MODEL_LOAD_FAILED
        )
        result = search_library("query")
        assert "USER-FACING ERROR" in result

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_fts_query_error_suggests_vector_mode(self, _mock_vec) -> None:
        """FTSQueryError returns tool error suggesting vector mode."""
        self.mock_retriever.retrieve.side_effect = FTSQueryError(
            "query syntax error", ErrorCode.EMBEDDING_FTS_QUERY_SYNTAX
        )
        result = search_library("query")
        assert result.startswith("Error: ")
        assert "vector" in result.lower()

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_empty_results_returns_helpful_message(self, _mock_vec) -> None:
        """Empty results returns helpful suggestion, not error."""
        self.mock_retriever.retrieve.return_value = []
        result = search_library("obscure query")
        assert "no results" in result.lower()
        assert "obscure query" in result
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_mcp_server.py -v`
Expected: All tests pass

**Step 3: Run full unit test suite**

Run: `uv run pytest tests/unit/ --tb=short -q`
Expected: All 1014+ tests pass (existing + new MCP tests)

**Step 4: Commit**
```bash
git add src/local_library/mcp/server.py tests/unit/test_mcp_server.py
git commit -m "feat(mcp): implement search_library tool with tests"
```
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_TASK_6 -->
### Task 6: Create mcp/CLAUDE.md domain documentation

**Type:** Infrastructure

**Files:**
- Create: `src/local_library/mcp/CLAUDE.md`

**Reference files for executor:**
- `src/local_library/embeddings/CLAUDE.md` — Example domain CLAUDE.md format
- `src/local_library/cli/CLAUDE.md` — Another example (note boundary rules)

**Step 1: Create CLAUDE.md**

Create `src/local_library/mcp/CLAUDE.md`:
```markdown
# MCP Server Domain

Last verified: 2026-04-15

## Purpose

Exposes the document library to Claude Code via MCP (Model Context Protocol) tools over stdio transport using the FastMCP framework. Wraps the existing Library API without adding new data models or capabilities. All tools are read-only.

## Contracts

- **Exposes**: MCP tools (search_library; show_document, list_documents, get_document_text planned for Phase 2)
- **Guarantees**:
  - All tools return markdown with consistent, parseable structure
  - Citekeys appear after `@`, scores labeled, chunk indices labeled
  - Error convention: `⚠ USER-FACING ERROR:` prefix for infrastructure errors (Claude should inform user); `Error:` prefix for tool-level errors (Claude can handle or work around)
  - Empty search results are not errors — tool returns suggestions
  - Library instance created once at startup, shared across tool calls
  - Models load lazily on first use (~2-5s one-time for embedder)
  - All logging to stderr; stdout reserved for JSON-RPC protocol
- **Expects**: Library API available; sqlite-vec for search features (graceful error when unavailable)

## Dependencies

- **Uses**: `core.Library` (orchestrator), `core.models` (Document, DocumentStatus, EmbeddingStatus), `core.errors` (LookupError, EmbeddingError, FTSQueryError), `core.vec_extension` (is_vec_available), `cli.utils` (resolve_identifier, suggest_citekeys), `embeddings.base` (SearchResult, Chunk, Retriever)
- **Used by**: Claude Code (via MCP protocol over stdio)
- **Boundary**: MCP MUST NOT be imported by core, embeddings, ingestion, or rag. CLI may import from MCP for shared utilities if needed.

## Key Decisions

- **Functional Core / Imperative Shell**: formatters.py is Functional Core (pure markdown rendering, no I/O). server.py is Imperative Shell (Library lifecycle, MCP protocol, I/O)
- **No RAG tool**: Claude Code is the LLM — it uses search_library to retrieve chunks and synthesizes answers directly, avoiding latency and context isolation of nested LLM calls
- **Module-level Library**: Library instance stored as module-level variable in server.py; created in main() before mcp.run(), closed in finally block
- **Markdown-only returns**: No JSON output option — one format reduces per-call decision overhead for Claude
- **Identifier resolution via cli.utils**: Reuses resolve_identifier() from CLI for UUID/@citekey parsing and fuzzy match suggestions
- **Sync tool functions**: Library API is synchronous; FastMCP handles threading for async event loop

## Invariants

- Tool functions never raise exceptions to MCP protocol — all errors caught and returned as formatted strings
- USER-FACING ERROR prefix only for infrastructure problems (sqlite-vec unavailable, model load failure, empty corpus)
- Tool-level errors always include actionable suggestions where possible
- Library instance is never None during tool execution (assert in each tool function)

## Key Files

- `server.py` — FastMCP app, tool definitions, Library lifecycle, logging setup (Imperative Shell)
- `formatters.py` — Markdown rendering functions: format_search_results, format_user_error, format_tool_error, format_empty_results (Functional Core)

## Gotchas

- stdout is reserved for JSON-RPC protocol — never use print() in tool functions; use logger (configured to stderr)
- Library created with `embed_on_add=False` since MCP server is read-only
- `resolve_identifier()` raises LookupError on unknown identifiers — catch in tool functions
- `FTSQueryError` inherits from `EmbeddingError` — catch FTSQueryError before EmbeddingError in exception handlers
- First search call triggers embedder model loading (~2-5s); subsequent calls are fast
- `TOKENIZERS_PARALLELISM` env var set to "false" to suppress HuggingFace warning in forked process
```

**Step 2: Run ruff to check formatting**

Run: `uv run ruff check src/local_library/mcp/`
Expected: No lint errors

Run: `uv run ruff format --check src/local_library/mcp/`
Expected: Already formatted (or format if needed)

**Step 3: Run full test suite to confirm nothing broken**

Run: `uv run pytest tests/unit/ --tb=short -q`
Expected: All tests pass

**Step 4: Commit**
```bash
git add src/local_library/mcp/CLAUDE.md
git commit -m "docs(mcp): add domain CLAUDE.md with contracts and conventions"
```
<!-- END_TASK_6 -->

---

**Phase 1 complete when:**
- `uv run local-library-mcp` starts the server without crashing
- `search_library` tool registered with FastMCP and callable
- Formatter unit tests pass (format_search_results, error helpers)
- Server tool tests pass (parameter validation, error handling, mock Library integration)
- Full unit test suite still passes (no regressions)
- CLAUDE.md documents contracts and gotchas
