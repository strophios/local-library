# Phase 7: CLI Commands

## Goal
Implement user-facing command-line interface with Typer and Rich.

---

<!-- START_TASK_1 -->
### Task 1: Create CLI main module with shared context

**Files:**
- Create: `src/local_library/cli/__init__.py`
- Create: `src/local_library/cli/main.py`

**Step 1: Create the CLI package init**

```python
"""CLI module - command-line interface."""
```

**Step 2: Create the main CLI entry point**

```python
"""CLI entry point with Typer app and shared context."""

# pattern: Imperative Shell

import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from local_library.core import Library

# Create Typer app
app = typer.Typer(
    name="local-library",
    help="Personal knowledge management for local documents.",
    add_completion=False,
)

# Rich consoles for output
console = Console()
err_console = Console(stderr=True)


def get_library() -> Library:
    """Get a Library instance with default paths."""
    return Library()


def error(message: str, code: int = 1) -> None:
    """Print error message to stderr and exit."""
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code=code)


# Import and register subcommands
from local_library.cli import add as add_cmd
from local_library.cli import delete as delete_cmd
from local_library.cli import list as list_cmd
from local_library.cli import show as show_cmd

app.command(name="add")(add_cmd.add)
app.command(name="list")(list_cmd.list_docs)
app.command(name="show")(show_cmd.show)
app.command(name="delete")(delete_cmd.delete)


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
```

**Step 3: Verify package is importable**

Run: `uv run python -c "from local_library.cli.main import app; print('CLI app loaded')"`

Expected: `CLI app loaded` (may show import errors for subcommands not yet created)

**Step 4: Commit**

```bash
git add src/local_library/cli/__init__.py src/local_library/cli/main.py
git commit -m "feat: add CLI main module with Typer app

- Typer app with shared console context
- get_library() helper for Library instances
- error() helper for stderr output and exit codes
- Registers add, list, show, delete subcommands

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Create add command

**Files:**
- Create: `src/local_library/cli/add.py`

**Step 1: Create the add command**

```python
"""Add command - add documents to the library."""

# pattern: Imperative Shell

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from local_library.core import AcquisitionError, ExtractionError, Library, QualityError

console = Console()
err_console = Console(stderr=True)


def add(
    path: Annotated[Path, typer.Argument(help="Path to the document file")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Create failed record for inaccessible files"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
) -> None:
    """Add a document to the library.

    Copies the file to managed storage, extracts text content, and creates
    a database record. Duplicates are detected by path and content hash.
    """
    try:
        with Library() as lib:
            result = lib.add(str(path), force=force)
    except AcquisitionError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1)
    except (ExtractionError, QualityError) as e:
        # Document was created but extraction failed
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[yellow]warning:[/yellow] extraction failed: {e.message}")
            err_console.print(f"[dim]Document created with status 'failed'[/dim]")
        raise typer.Exit(code=2)

    doc = result.document

    if json_output:
        output = {
            "id": str(doc.id),
            "status": doc.status.value,
            "original_path": doc.original_path,
            "storage_path": doc.storage_path,
            "content_hash": doc.content_hash,
            "is_duplicate": result.is_duplicate,
        }
        if result.is_duplicate:
            output["duplicate_reason"] = result.duplicate_reason
        console.print(json.dumps(output, indent=2))
    else:
        if result.is_duplicate:
            console.print(f"[yellow]duplicate[/yellow] ({result.duplicate_reason}): {doc.id}")
        else:
            console.print(f"[green]added[/green]: {doc.id}")
            console.print(f"  [dim]status:[/dim] {doc.status.value}")
            console.print(f"  [dim]path:[/dim] {doc.storage_path}")
```

**Step 2: Verify command is importable**

Run: `uv run python -c "from local_library.cli.add import add; print('add command loaded')"`

Expected: `add command loaded`

**Step 3: Commit**

```bash
git add src/local_library/cli/add.py
git commit -m "feat: add 'add' CLI command

- Add documents with path argument
- --force flag for inaccessible files
- --json flag for JSON output
- Duplicate detection feedback
- Proper exit codes (1=acquisition error, 2=extraction error)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Create list command

**Files:**
- Create: `src/local_library/cli/list.py`

**Step 1: Create the list command**

```python
"""List command - list documents in the library."""

# pattern: Imperative Shell

import json
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from local_library.core import DocumentStatus, Library

console = Console()


def list_docs(
    status: Annotated[
        Optional[str],
        typer.Option("--status", "-s", help="Filter by status (pending, ready, failed)"),
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
            console.print(f"[dim]valid values: pending, ready, failed[/dim]")
            raise typer.Exit(code=1)

    with Library() as lib:
        docs = lib.list(status=status_filter)

    if json_output:
        output = [
            {
                "id": str(doc.id),
                "status": doc.status.value,
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
        table.add_column("Status", style="magenta")
        table.add_column("Original Path")
        table.add_column("Hash", style="dim")

        for doc in docs:
            # Use first 8 chars of UUID and hash for display
            short_id = str(doc.id)[:8]
            short_hash = doc.content_hash[:8]

            status_style = {
                DocumentStatus.PENDING: "yellow",
                DocumentStatus.READY: "green",
                DocumentStatus.FAILED: "red",
            }.get(doc.status, "white")

            table.add_row(
                short_id,
                f"[{status_style}]{doc.status.value}[/{status_style}]",
                doc.original_path,
                short_hash,
            )

        console.print(table)
        console.print(f"\n[dim]{len(docs)} document(s)[/dim]")
```

**Step 2: Verify command is importable**

Run: `uv run python -c "from local_library.cli.list import list_docs; print('list command loaded')"`

Expected: `list command loaded`

**Step 3: Commit**

```bash
git add src/local_library/cli/list.py
git commit -m "feat: add 'list' CLI command

- Rich table display by default
- --status filter (pending, ready, failed)
- --json flag for JSON output
- Truncated IDs and hashes for readability

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Create show command

**Files:**
- Create: `src/local_library/cli/show.py`

**Step 1: Create the show command**

```python
"""Show command - display document details."""

# pattern: Imperative Shell

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from local_library.core import Library, LookupError

console = Console()
err_console = Console(stderr=True)


def show(
    doc_id: Annotated[str, typer.Argument(help="Document ID (full or partial UUID)")],
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
) -> None:
    """Show details for a specific document.

    Supports partial UUID matching - if the prefix uniquely identifies
    a document, it will be shown.
    """
    try:
        with Library() as lib:
            doc = lib.get(doc_id)
    except LookupError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1)

    if json_output:
        output = {
            "id": str(doc.id),
            "status": doc.status.value,
            "original_path": doc.original_path,
            "storage_path": doc.storage_path,
            "extracted_path": doc.extracted_path,
            "content_hash": doc.content_hash,
            "citekey": doc.citekey,
            "error_code": doc.error_code,
            "error_message": doc.error_message,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        }
        console.print(json.dumps(output, indent=2))
    else:
        status_style = {
            "pending": "yellow",
            "ready": "green",
            "failed": "red",
        }.get(doc.status.value, "white")

        lines = [
            f"[bold]ID:[/bold] {doc.id}",
            f"[bold]Status:[/bold] [{status_style}]{doc.status.value}[/{status_style}]",
            f"[bold]Original:[/bold] {doc.original_path}",
            f"[bold]Storage:[/bold] {doc.storage_path}",
        ]

        if doc.extracted_path:
            lines.append(f"[bold]Extracted:[/bold] {doc.extracted_path}")

        lines.append(f"[bold]Hash:[/bold] {doc.content_hash}")

        if doc.citekey:
            lines.append(f"[bold]Citekey:[/bold] {doc.citekey}")

        if doc.created_at:
            lines.append(f"[bold]Created:[/bold] {doc.created_at.isoformat()}")

        if doc.updated_at:
            lines.append(f"[bold]Updated:[/bold] {doc.updated_at.isoformat()}")

        if doc.error_message:
            lines.append(f"[bold red]Error:[/bold red] {doc.error_message}")
            if doc.error_code:
                lines.append(f"[bold red]Error Code:[/bold red] {doc.error_code}")

        content = "\n".join(lines)
        panel = Panel(content, title="Document", border_style="blue")
        console.print(panel)
```

**Step 2: Verify command is importable**

Run: `uv run python -c "from local_library.cli.show import show; print('show command loaded')"`

Expected: `show command loaded`

**Step 3: Commit**

```bash
git add src/local_library/cli/show.py
git commit -m "feat: add 'show' CLI command

- Display document details in Rich panel
- Partial UUID matching support
- --json flag for JSON output
- Error details shown for failed documents

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_4 -->

---

<!-- START_TASK_5 -->
### Task 5: Create delete command

**Files:**
- Create: `src/local_library/cli/delete.py`

**Step 1: Create the delete command**

```python
"""Delete command - remove documents from the library."""

# pattern: Imperative Shell

import json
from typing import Annotated

import typer
from rich.console import Console

from local_library.core import Library, LookupError

console = Console()
err_console = Console(stderr=True)


def delete(
    doc_id: Annotated[str, typer.Argument(help="Document ID (full or partial UUID)")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
    keep_files: Annotated[
        bool,
        typer.Option("--keep-files", help="Keep storage files, only delete database record"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
) -> None:
    """Delete a document from the library.

    By default, deletes both the database record and the storage files.
    Use --keep-files to preserve the files on disk.
    Use --force to skip the confirmation prompt.
    """
    try:
        with Library() as lib:
            # First get the document to confirm it exists and show details
            doc = lib.get(doc_id)

            # Confirmation prompt unless --force
            if not force and not json_output:
                console.print(f"[yellow]About to delete:[/yellow]")
                console.print(f"  ID: {doc.id}")
                console.print(f"  Path: {doc.original_path}")
                console.print(f"  Status: {doc.status.value}")

                if not keep_files:
                    console.print(f"  [dim]Files will be deleted from disk[/dim]")

                confirmed = typer.confirm("Continue?")
                if not confirmed:
                    console.print("[dim]Cancelled.[/dim]")
                    raise typer.Exit(code=0)

            # Perform deletion
            lib.delete(doc_id, delete_files=not keep_files)

    except LookupError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1)

    if json_output:
        console.print(json.dumps({"deleted": str(doc.id), "files_deleted": not keep_files}))
    else:
        console.print(f"[green]deleted[/green]: {doc.id}")
```

**Step 2: Verify command is importable**

Run: `uv run python -c "from local_library.cli.delete import delete; print('delete command loaded')"`

Expected: `delete command loaded`

**Step 3: Commit**

```bash
git add src/local_library/cli/delete.py
git commit -m "feat: add 'delete' CLI command

- Delete documents by full or partial UUID
- Confirmation prompt by default
- --force flag to skip confirmation
- --keep-files flag to preserve storage files
- --json flag for JSON output

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_5 -->

---

<!-- START_TASK_6 -->
### Task 6: Create CLI tests

**Files:**
- Create: `tests/unit/test_cli.py`

**Step 1: Create the CLI test file**

```python
"""Unit tests for CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core.models import AddResult, Document, DocumentStatus

runner = CliRunner()


@pytest.fixture
def mock_library():
    """Provide a mock Library for CLI testing."""
    with patch("local_library.cli.add.Library") as mock_add, \
         patch("local_library.cli.list.Library") as mock_list, \
         patch("local_library.cli.show.Library") as mock_show, \
         patch("local_library.cli.delete.Library") as mock_delete:

        mock_lib = MagicMock()
        mock_add.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_add.return_value.__exit__ = MagicMock(return_value=False)
        mock_list.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_list.return_value.__exit__ = MagicMock(return_value=False)
        mock_show.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_show.return_value.__exit__ = MagicMock(return_value=False)
        mock_delete.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_delete.return_value.__exit__ = MagicMock(return_value=False)

        yield mock_lib


class TestAddCommand:
    """Tests for the add command."""

    def test_add_success(self, mock_library: MagicMock, temp_dir: Path) -> None:
        """add command should succeed for valid files."""
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.storage_path = "/storage/12/34/1234.pdf"
        mock_doc.original_path = str(pdf_path)
        mock_doc.content_hash = "abcd1234"

        mock_library.add.return_value = AddResult(document=mock_doc)

        result = runner.invoke(app, ["add", str(pdf_path)])

        assert result.exit_code == 0
        assert "added" in result.output

    def test_add_duplicate_shows_warning(self, mock_library: MagicMock, temp_dir: Path) -> None:
        """add command should indicate duplicates."""
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.storage_path = "/storage/test.pdf"
        mock_doc.original_path = str(pdf_path)
        mock_doc.content_hash = "abcd1234"

        mock_library.add.return_value = AddResult(
            document=mock_doc,
            is_duplicate=True,
            duplicate_reason="path",
        )

        result = runner.invoke(app, ["add", str(pdf_path)])

        assert result.exit_code == 0
        assert "duplicate" in result.output

    def test_add_json_output(self, mock_library: MagicMock, temp_dir: Path) -> None:
        """add command with --json should output JSON."""
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.storage_path = "/storage/test.pdf"
        mock_doc.original_path = str(pdf_path)
        mock_doc.content_hash = "abcd1234"

        mock_library.add.return_value = AddResult(document=mock_doc)

        result = runner.invoke(app, ["add", "--json", str(pdf_path)])

        assert result.exit_code == 0
        assert '"id"' in result.output


class TestListCommand:
    """Tests for the list command."""

    def test_list_empty(self, mock_library: MagicMock) -> None:
        """list command should handle empty library."""
        mock_library.list.return_value = []

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "No documents" in result.output

    def test_list_with_documents(self, mock_library: MagicMock) -> None:
        """list command should display documents."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.content_hash = "abcd1234"
        mock_doc.created_at = None

        mock_library.list.return_value = [mock_doc]

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "12345678" in result.output

    def test_list_filter_by_status(self, mock_library: MagicMock) -> None:
        """list command should accept --status filter."""
        mock_library.list.return_value = []

        result = runner.invoke(app, ["list", "--status", "ready"])

        assert result.exit_code == 0
        mock_library.list.assert_called_once_with(status=DocumentStatus.READY)

    def test_list_invalid_status(self, mock_library: MagicMock) -> None:
        """list command should reject invalid status."""
        result = runner.invoke(app, ["list", "--status", "invalid"])

        assert result.exit_code == 1
        assert "invalid status" in result.output


class TestShowCommand:
    """Tests for the show command."""

    def test_show_document(self, mock_library: MagicMock) -> None:
        """show command should display document details."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.status.value = "ready"
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.storage_path = "/storage/doc.pdf"
        mock_doc.extracted_path = "/extracted/doc.md"
        mock_doc.content_hash = "abcd1234"
        mock_doc.citekey = None
        mock_doc.error_message = None
        mock_doc.error_code = None
        mock_doc.created_at = None
        mock_doc.updated_at = None

        mock_library.get.return_value = mock_doc

        result = runner.invoke(app, ["show", "12345678"])

        assert result.exit_code == 0
        assert "12345678" in result.output

    def test_show_not_found(self, mock_library: MagicMock) -> None:
        """show command should handle not found."""
        from local_library.core import ErrorCode, LookupError

        mock_library.get.side_effect = LookupError(
            "document not found", ErrorCode.NOT_FOUND
        )

        result = runner.invoke(app, ["show", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output


class TestDeleteCommand:
    """Tests for the delete command."""

    def test_delete_with_force(self, mock_library: MagicMock) -> None:
        """delete command with --force should skip confirmation."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.status.value = "ready"
        mock_doc.original_path = "/path/to/doc.pdf"

        mock_library.get.return_value = mock_doc
        mock_library.delete.return_value = True

        result = runner.invoke(app, ["delete", "--force", "12345678"])

        assert result.exit_code == 0
        assert "deleted" in result.output

    def test_delete_not_found(self, mock_library: MagicMock) -> None:
        """delete command should handle not found."""
        from local_library.core import ErrorCode, LookupError

        mock_library.get.side_effect = LookupError(
            "document not found", ErrorCode.NOT_FOUND
        )

        result = runner.invoke(app, ["delete", "--force", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py -v`

Expected: All tests pass (approximately 12 tests)

**Step 3: Commit**

```bash
git add tests/unit/test_cli.py
git commit -m "test: add unit tests for CLI commands

- Tests for add command (success, duplicate, JSON)
- Tests for list command (empty, with docs, status filter)
- Tests for show command (display, not found)
- Tests for delete command (force, not found)
- Mock-based testing with CliRunner

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_6 -->

---

<!-- START_TASK_7 -->
### Task 7: Verify CLI integration

**Files:**
- No new files

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`

Expected: All tests pass

**Step 2: Verify CLI help works**

Run: `uv run local-library --help`

Expected: Shows help with add, list, show, delete commands

Run: `uv run local-library add --help`

Expected: Shows add command help with --force and --json options

**Step 3: Run all quality checks**

Run: `uv run ruff check src/ tests/`

Expected: No linting errors

Run: `uv run ruff format --check src/ tests/`

Expected: No formatting issues

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: verify CLI integration

All CLI commands working:
- local-library add <path> [--force] [--json]
- local-library list [--status] [--json]
- local-library show <id> [--json]
- local-library delete <id> [--force] [--keep-files] [--json]

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_7 -->

---

**Phase 7 Definition of Done:**
- All CLI commands work (add, list, show, delete)
- Rich output displays correctly (tables, panels, colors)
- --json produces valid JSON for all commands
- Error messages go to stderr with appropriate exit codes
- CLI integration tests pass
