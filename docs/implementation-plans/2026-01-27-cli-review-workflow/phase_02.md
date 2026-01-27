## Phase 2: Enhanced List Command

**Goal:** Improved table display with new columns and pagination

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Update list command columns and add NEEDS_REVIEW styling

**Files:**
- Modify: `src/local_library/cli/list.py:62-87`

**Step 1: Write the failing test**

Add to `tests/unit/test_cli.py`:

```python
class TestListCommandEnhanced:
    """Tests for enhanced list command features."""

    def test_list_shows_citekey_column(self, mock_library: MagicMock) -> None:
        """list command should display citekey column."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.citekey = "Smith2023"
        mock_doc.title = "Test Document"
        mock_doc.authors = "John Smith"
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.content_hash = "abcd1234"
        mock_doc.created_at = None

        mock_library.list.return_value = [mock_doc]

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "Smith2023" in result.output
        assert "Test Document" in result.output

    def test_list_shows_needs_review_status(self, mock_library: MagicMock) -> None:
        """list command should handle NEEDS_REVIEW status."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.NEEDS_REVIEW
        mock_doc.citekey = "Smith2023"
        mock_doc.title = "Test Document"
        mock_doc.authors = "John Smith"
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.content_hash = "abcd1234"
        mock_doc.created_at = None

        mock_library.list.return_value = [mock_doc]

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "needs_review" in result.output

    def test_list_filter_needs_review(self, mock_library: MagicMock) -> None:
        """list command should filter by needs_review status."""
        mock_library.list.return_value = []

        result = runner.invoke(app, ["list", "--status", "needs_review"])

        assert result.exit_code == 0
        mock_library.list.assert_called_once_with(status=DocumentStatus.NEEDS_REVIEW)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py::TestListCommandEnhanced -v`
Expected: FAIL (citekey not displayed, title not displayed)

**Step 3: Write minimal implementation**

Modify `src/local_library/cli/list.py`:

```python
"""List command - list documents in the library."""

# pattern: Imperative Shell

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from local_library.core import DocumentStatus, Library

console = Console()


def _truncate(text: str | None, max_length: int) -> str:
    """Truncate text with ellipsis if too long."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def list_docs(
    status: Annotated[
        str | None,
        typer.Option(
            "--status", "-s", help="Filter by status (pending, ready, failed, needs_review)"
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
) -> None:
    """List all documents in the library.

    Displays documents in a table format by default, or as JSON with --json.
    Use --status to filter by document status.
    """
    # Parse status filter
    status_filter: DocumentStatus | None = None
    if status:
        try:
            status_filter = DocumentStatus(status.lower())
        except ValueError:
            console.print(f"[red]error:[/red] invalid status '{status}'")
            console.print("[dim]valid values: pending, ready, failed, needs_review[/dim]")
            raise typer.Exit(code=1) from None

    with Library() as lib:
        docs = lib.list(status=status_filter)

    if json_output:
        output = [
            {
                "id": str(doc.id),
                "citekey": doc.citekey,
                "status": doc.status.value,
                "title": doc.title,
                "authors": doc.authors,
                "original_path": doc.original_path,
                "content_hash": doc.content_hash[:12] + "...",
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in docs
        ]
        console.print(json.dumps(output, indent=2))
    else:
        if not docs:
            console.print("[dim]No documents found.[/dim]")
            return

        table = Table(title="Documents")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Citekey", style="blue", no_wrap=True)
        table.add_column("Status", style="magenta")
        table.add_column("Title")
        table.add_column("Authors")

        status_style = {
            DocumentStatus.PENDING: "yellow",
            DocumentStatus.READY: "green",
            DocumentStatus.FAILED: "red",
            DocumentStatus.NEEDS_REVIEW: "yellow bold",
        }

        for doc in docs:
            short_id = str(doc.id)[:8]
            style = status_style.get(doc.status, "white")

            table.add_row(
                short_id,
                doc.citekey or "",
                f"[{style}]{doc.status.value}[/{style}]",
                _truncate(doc.title, 40),
                _truncate(doc.authors, 25),
            )

        console.print(table)
        console.print(f"\n[dim]{len(docs)} document(s)[/dim]")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py::TestListCommandEnhanced tests/unit/test_cli.py::TestListCommand -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/list.py tests/unit/test_cli.py
git commit -m "feat(cli): update list columns to show citekey, title, authors

Replaces Original Path and Hash columns with Citekey, Title, and Authors.
Adds NEEDS_REVIEW status styling (yellow bold) and filter support."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add pagination with --limit and --all flags

**Files:**
- Modify: `src/local_library/cli/list.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cli.py`:

```python
class TestListCommandPagination:
    """Tests for list command pagination."""

    def test_list_default_limit(self, mock_library: MagicMock) -> None:
        """list command should default to 15 rows."""
        # Create 20 mock documents
        mock_docs = []
        for i in range(20):
            mock_doc = MagicMock()
            mock_doc.id = f"1234567{i}-1234-1234-1234-123456789abc"
            mock_doc.status = DocumentStatus.READY
            mock_doc.citekey = f"Author202{i}"
            mock_doc.title = f"Document {i}"
            mock_doc.authors = f"Author {i}"
            mock_doc.original_path = f"/path/doc{i}.pdf"
            mock_doc.content_hash = f"hash{i:04d}"
            mock_doc.created_at = None
            mock_docs.append(mock_doc)

        mock_library.list.return_value = mock_docs

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        # Should show hint about more items
        assert "Showing 15 of 20" in result.output
        assert "--all" in result.output

    def test_list_custom_limit(self, mock_library: MagicMock) -> None:
        """list command should respect --limit flag."""
        mock_docs = []
        for i in range(10):
            mock_doc = MagicMock()
            mock_doc.id = f"1234567{i}-1234-1234-1234-123456789abc"
            mock_doc.status = DocumentStatus.READY
            mock_doc.citekey = f"Author202{i}"
            mock_doc.title = f"Document {i}"
            mock_doc.authors = f"Author {i}"
            mock_doc.original_path = f"/path/doc{i}.pdf"
            mock_doc.content_hash = f"hash{i:04d}"
            mock_doc.created_at = None
            mock_docs.append(mock_doc)

        mock_library.list.return_value = mock_docs

        result = runner.invoke(app, ["list", "--limit", "5"])

        assert result.exit_code == 0
        assert "Showing 5 of 10" in result.output

    def test_list_no_pagination_when_under_limit(self, mock_library: MagicMock) -> None:
        """list command should not show pagination hint when under limit."""
        mock_docs = []
        for i in range(5):
            mock_doc = MagicMock()
            mock_doc.id = f"1234567{i}-1234-1234-1234-123456789abc"
            mock_doc.status = DocumentStatus.READY
            mock_doc.citekey = f"Author202{i}"
            mock_doc.title = f"Document {i}"
            mock_doc.authors = f"Author {i}"
            mock_doc.original_path = f"/path/doc{i}.pdf"
            mock_doc.content_hash = f"hash{i:04d}"
            mock_doc.created_at = None
            mock_docs.append(mock_doc)

        mock_library.list.return_value = mock_docs

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        # Should just show count, no "Showing X of Y"
        assert "5 document(s)" in result.output
        assert "Showing" not in result.output
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py::TestListCommandPagination -v`
Expected: FAIL (no --limit flag, no pagination hint)

**Step 3: Write minimal implementation**

Update `src/local_library/cli/list.py` to add pagination:

```python
"""List command - list documents in the library."""

# pattern: Imperative Shell

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from local_library.core import DocumentStatus, Library

console = Console()

DEFAULT_LIMIT = 15


def _truncate(text: str | None, max_length: int) -> str:
    """Truncate text with ellipsis if too long."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def list_docs(
    status: Annotated[
        str | None,
        typer.Option(
            "--status", "-s", help="Filter by status (pending, ready, failed, needs_review)"
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-n", help="Maximum number of rows to display"),
    ] = None,
    show_all: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show all documents in pager"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
) -> None:
    """List all documents in the library.

    Displays documents in a table format by default, or as JSON with --json.
    Use --status to filter by document status.

    By default, shows up to 15 documents. Use --limit to change this,
    or --all to show all documents in a pager.
    """
    # Parse status filter
    status_filter: DocumentStatus | None = None
    if status:
        try:
            status_filter = DocumentStatus(status.lower())
        except ValueError:
            console.print(f"[red]error:[/red] invalid status '{status}'")
            console.print("[dim]valid values: pending, ready, failed, needs_review[/dim]")
            raise typer.Exit(code=1) from None

    with Library() as lib:
        docs = lib.list(status=status_filter)

    total_count = len(docs)

    if json_output:
        output = [
            {
                "id": str(doc.id),
                "citekey": doc.citekey,
                "status": doc.status.value,
                "title": doc.title,
                "authors": doc.authors,
                "original_path": doc.original_path,
                "content_hash": doc.content_hash[:12] + "...",
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in docs
        ]
        console.print(json.dumps(output, indent=2))
        return

    if not docs:
        console.print("[dim]No documents found.[/dim]")
        return

    # Determine display limit
    if show_all:
        display_limit = total_count
    elif limit is not None:
        display_limit = limit
    else:
        display_limit = DEFAULT_LIMIT

    # Build table
    table = Table(title="Documents")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Citekey", style="blue", no_wrap=True)
    table.add_column("Status", style="magenta")
    table.add_column("Title")
    table.add_column("Authors")

    status_style = {
        DocumentStatus.PENDING: "yellow",
        DocumentStatus.READY: "green",
        DocumentStatus.FAILED: "red",
        DocumentStatus.NEEDS_REVIEW: "yellow bold",
    }

    for doc in docs[:display_limit]:
        short_id = str(doc.id)[:8]
        style = status_style.get(doc.status, "white")

        table.add_row(
            short_id,
            doc.citekey or "",
            f"[{style}]{doc.status.value}[/{style}]",
            _truncate(doc.title, 40),
            _truncate(doc.authors, 25),
        )

    # Output with pager if showing all
    if show_all:
        with console.pager():
            console.print(table)
            console.print(f"\n[dim]{total_count} document(s)[/dim]")
    else:
        console.print(table)
        if total_count > display_limit:
            console.print(
                f"\n[dim]Showing {display_limit} of {total_count} items. "
                f"Use --all to see all.[/dim]"
            )
        else:
            console.print(f"\n[dim]{total_count} document(s)[/dim]")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py::TestListCommandPagination tests/unit/test_cli.py::TestListCommand tests/unit/test_cli.py::TestListCommandEnhanced -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/list.py tests/unit/test_cli.py
git commit -m "feat(cli): add pagination to list command

Default limit of 15 rows with hint showing total count.
--limit/-n for custom row count, --all/-a for pager mode."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update JSON output to include new fields

**Files:**
- Modify: `src/local_library/cli/list.py` (already done in Task 1)

This was already handled in Task 1 when updating the columns. The JSON output now includes `citekey`, `title`, and `authors`. Verify with existing tests.

**Step 1: Verify JSON output tests pass**

Run: `uv run pytest tests/unit/test_cli.py::TestListCommand -v`
Expected: PASS

No additional changes needed - commit already made in Task 2.
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

**Phase complete when:** List shows new columns (ID, Citekey, Status, Title, Authors), respects row limits, `--all` opens system pager.
