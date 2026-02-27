## Phase 6: CLI Search Command

**Goal:** User-facing search interface.

**Components:**
- `cli/search.py` — search command with `--limit`, `--mode`, `--doc`, `--json` flags
- Command registration in `cli/main.py`
- Rich table output for human-readable results
- CLI unit tests in `tests/unit/test_cli_search.py`

**Dependencies:** Phase 5 (Library integration)

<!-- START_TASK_1 -->
### Task 1: Create CLI search command

**Files:**
- Create: `src/local_library/cli/search.py`

**Context files for the executor:**
- Read `src/local_library/cli/embed.py` for CLI command pattern (Typer annotations, Library context, error handling)
- Read `src/local_library/cli/list.py` for Rich Table pattern and `_truncate()` helper
- Read `src/local_library/cli/utils.py` for `resolve_identifier()`
- Read `src/local_library/cli/CLAUDE.md` for CLI contracts
- Read `src/local_library/embeddings/base.py` for SearchResult dataclass

**Step 1: Create search.py**

Create `src/local_library/cli/search.py`:

```python
"""Search command - search documents by content."""

# pattern: Imperative Shell

import json
from typing import Annotated
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table

from local_library.cli.utils import resolve_identifier
from local_library.core import Library
from local_library.core.errors import EmbeddingError, FTSQueryError, LookupError
from local_library.core.vec_extension import is_vec_available

console = Console()
err_console = Console(stderr=True)

VALID_MODES = ("hybrid", "vector", "fts")


def _truncate(text: str, max_length: int) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def search(
    query: Annotated[
        str,
        typer.Argument(help="Search query (natural language or keywords)"),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum number of results"),
    ] = 10,
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="Search mode: hybrid, vector, or fts"),
    ] = "hybrid",
    doc_id: Annotated[
        str | None,
        typer.Option("--doc", "-d", help="Limit search to a specific document (UUID or @citekey)"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output results as JSON"),
    ] = False,
) -> None:
    """Search documents by content using semantic and keyword search.

    Uses hybrid search (vector + full-text) by default. Vector search captures
    semantic similarity; full-text search captures exact keyword matches.
    Results are ranked by relevance.

    Examples:

        # Basic search
        local-library search "machine learning"

        # Keyword-only search
        local-library search "Smith 2023" --mode fts

        # Search within a specific document
        local-library search "neural networks" --doc @Author2023

        # Get more results as JSON
        local-library search "climate change" --limit 20 --json
    """
    if not is_vec_available():
        if json_output:
            err_console.print(json.dumps({"error": "sqlite-vec extension not available"}))
        else:
            err_console.print("[red]error:[/red] sqlite-vec extension not available")
            err_console.print("[dim]Install sqlite-vec to enable search features[/dim]")
        raise typer.Exit(code=1)

    if mode not in VALID_MODES:
        if json_output:
            err_console.print(
                json.dumps({"error": f"invalid mode: {mode} (expected hybrid, vector, or fts)"})
            )
        else:
            err_console.print(
                f"[red]error:[/red] invalid mode: {mode} (expected hybrid, vector, or fts)"
            )
        raise typer.Exit(code=1)

    try:
        with Library(embed_on_add=False) as lib:
            # Resolve document filter if provided
            doc_ids: list[UUID] | None = None
            if doc_id:
                doc = resolve_identifier(doc_id, lib)
                doc_ids = [doc.id]

            retriever = lib.get_retriever(mode=mode)
            results = retriever.retrieve(query, k=limit, doc_ids=doc_ids)

            if json_output:
                _output_json(results)
            else:
                _output_table(results, query, mode)

    except LookupError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None
    except FTSQueryError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
            err_console.print("[dim]Try simplifying your query or using --mode vector[/dim]")
        raise typer.Exit(code=1) from None
    except EmbeddingError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None


def _output_json(results) -> None:
    """Output search results as JSON."""
    output = []
    for r in results:
        output.append({
            "chunk_id": r.chunk.chunk_id,
            "doc_id": str(r.chunk.doc_id),
            "chunk_index": r.chunk.chunk_index,
            "score": round(r.score, 6),
            "doc_title": r.doc_title,
            "doc_citekey": r.doc_citekey,
            "search_methods": sorted(r.search_methods),
            "text": r.chunk.text,
        })
    console.print(json.dumps(output, indent=2))


def _output_table(results, query: str, mode: str) -> None:
    """Output search results as a Rich table."""
    if not results:
        console.print(f"[dim]no results for[/dim] \"{query}\"")
        return

    table = Table(title=f"Search: \"{query}\" ({mode}, {len(results)} results)")
    table.add_column("#", style="dim", width=3)
    table.add_column("Score", width=8)
    table.add_column("Source", width=30)
    table.add_column("Methods", width=10)
    table.add_column("Text", ratio=1)

    for i, r in enumerate(results, start=1):
        # Format source as citekey or title
        source = r.doc_citekey or _truncate(r.doc_title or str(r.chunk.doc_id)[:8], 28)

        # Format methods
        methods = ",".join(sorted(r.search_methods))

        # Format text preview
        text_preview = _truncate(r.chunk.text.replace("\n", " "), 80)

        table.add_row(
            str(i),
            f"{r.score:.4f}",
            source,
            methods,
            text_preview,
        )

    console.print(table)
```

**Step 2: Verify file created**

Run: `uv run python -c "from local_library.cli.search import search; print(search)"`
Expected: Import succeeds

**Step 3: Commit**

```bash
git add src/local_library/cli/search.py
git commit -m "feat(cli): add search command implementation"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write CLI search command tests

**Files:**
- Create: `tests/unit/test_cli_search.py`

**Context files for the executor:**
- Read `tests/unit/test_cli.py` for existing CLI test patterns (mock_library fixture, CliRunner, app import)
- Read `src/local_library/cli/search.py` for the command being tested
- Read `src/local_library/cli/CLAUDE.md` for CLI contracts

**Step 1: Create test file**

Create `tests/unit/test_cli_search.py`:

```python
"""Unit tests for the CLI search command."""

# pattern: Imperative Shell

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core.errors import (
    EmbeddingError,
    ErrorCode,
    FTSQueryError,
    LookupError,
)

runner = CliRunner()


@pytest.fixture
def mock_search_library():
    """Provide a mock Library for search CLI testing."""
    with patch("local_library.cli.search.Library") as mock_cls:
        mock_lib = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_lib


@pytest.fixture
def mock_vec_available():
    """Patch is_vec_available to return True."""
    with patch("local_library.cli.search.is_vec_available", return_value=True):
        yield


def _make_mock_result(
    text: str = "Sample text",
    score: float = 0.5,
    title: str | None = "Test Doc",
    citekey: str | None = "Test2023",
    methods: frozenset[str] | None = None,
) -> MagicMock:
    """Create a mock SearchResult."""
    if methods is None:
        methods = frozenset({"vector", "fts"})
    result = MagicMock()
    result.chunk.chunk_id = str(uuid4())
    result.chunk.doc_id = uuid4()
    result.chunk.chunk_index = 0
    result.chunk.text = text
    result.score = score
    result.doc_title = title
    result.doc_citekey = citekey
    result.search_methods = methods
    return result


class TestSearchCommand:
    """Tests for the search command."""

    def test_basic_search(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search command returns results in table format."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            _make_mock_result(text="Machine learning result", score=0.8)
        ]
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "machine learning"])

        assert result.exit_code == 0
        assert "machine learning" in result.output.lower() or "Search" in result.output
        mock_search_library.get_retriever.assert_called_once_with(mode="hybrid")

    def test_json_output(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --json outputs valid JSON with expected schema."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            _make_mock_result(
                text="Test text",
                score=0.75,
                title="My Doc",
                citekey="Key2023",
                methods=frozenset({"vector"}),
            )
        ]
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "test", "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        item = parsed[0]
        assert "chunk_id" in item
        assert "doc_id" in item
        assert "score" in item
        assert "doc_title" in item
        assert "doc_citekey" in item
        assert "search_methods" in item
        assert "text" in item

    def test_mode_vector(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --mode vector uses vector retriever."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "query", "--mode", "vector"])

        assert result.exit_code == 0
        mock_search_library.get_retriever.assert_called_once_with(mode="vector")

    def test_mode_fts(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --mode fts uses FTS retriever."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "query", "--mode", "fts"])

        assert result.exit_code == 0
        mock_search_library.get_retriever.assert_called_once_with(mode="fts")

    def test_invalid_mode_rejected(self, mock_vec_available) -> None:
        """search --mode invalid exits with error."""
        result = runner.invoke(app, ["search", "query", "--mode", "invalid"])

        assert result.exit_code == 1

    def test_limit_parameter(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --limit passes k parameter to retriever."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "query", "--limit", "5"])

        assert result.exit_code == 0
        mock_retriever.retrieve.assert_called_once()
        call_kwargs = mock_retriever.retrieve.call_args
        assert call_kwargs.kwargs.get("k") == 5 or call_kwargs[1].get("k") == 5

    def test_doc_filter(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --doc resolves identifier and passes doc_ids."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_search_library.get_by_citekey.return_value = mock_doc

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "query", "--doc", "@Author2023"])

        assert result.exit_code == 0
        mock_retriever.retrieve.assert_called_once()
        call_kwargs = mock_retriever.retrieve.call_args
        doc_ids = call_kwargs.kwargs.get("doc_ids") or call_kwargs[1].get("doc_ids")
        assert doc_ids is not None
        assert mock_doc.id in doc_ids

    def test_empty_results(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search with no results shows appropriate message."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "nonexistent"])

        assert result.exit_code == 0
        assert "no results" in result.output.lower()

    def test_vec_unavailable(self) -> None:
        """search exits with error when sqlite-vec not available."""
        with patch("local_library.cli.search.is_vec_available", return_value=False):
            result = runner.invoke(app, ["search", "query"])

        assert result.exit_code == 1

    def test_fts_query_error(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search handles FTSQueryError gracefully."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = FTSQueryError(
            "invalid FTS5 query syntax",
            ErrorCode.EMBEDDING_FTS_QUERY_SYNTAX,
            details={"query": '"unbalanced'},
        )
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", '"unbalanced'])

        assert result.exit_code == 1

    def test_embedding_error(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search handles EmbeddingError gracefully."""
        mock_search_library.get_retriever.side_effect = EmbeddingError(
            "sqlite-vec extension not available",
            ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE,
        )

        result = runner.invoke(app, ["search", "query"])

        assert result.exit_code == 1

    def test_lookup_error_for_doc_filter(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --doc with unknown identifier shows error."""
        mock_search_library.get_by_citekey.return_value = None
        mock_search_library.get_all_citekeys.return_value = []

        result = runner.invoke(app, ["search", "query", "--doc", "@Unknown"])

        assert result.exit_code == 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli_search.py -v --tb=short 2>&1 | head -20`
Expected: Tests fail because search command isn't registered in main.py yet (or pass if Task 1 already done)

**Step 3: Run tests after Task 1 is complete to verify they pass**

Run: `uv run pytest tests/unit/test_cli_search.py -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/unit/test_cli_search.py
git commit -m "test(cli): add unit tests for search command"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Register search command in main.py

**Files:**
- Modify: `src/local_library/cli/main.py`

**Step 1: Add import**

Add to imports (after existing CLI imports, around line 15):

```python
from local_library.cli import search as search_cmd
```

**Step 2: Register command**

Add after the embed command registration (after line 32):

```python
app.command(name="search")(search_cmd.search)
```

**Step 3: Verify command is registered**

Run: `uv run local-library search --help`
Expected: Shows search command help with --limit, --mode, --doc, --json options

**Step 4: Run all CLI tests**

Run: `uv run pytest tests/unit/test_cli_search.py tests/unit/test_cli.py -v --tb=short`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/local_library/cli/main.py
git commit -m "feat(cli): register search command in CLI"
```
<!-- END_TASK_3 -->
