## Phase 5: Existing Command Updates

**Goal:** Retrofit `show` and `delete` to use centralized resolver

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Update show command to use resolve_identifier

**Files:**
- Modify: `src/local_library/cli/show.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cli.py`:

```python
class TestShowCommandCitekey:
    """Tests for show command with citekey support."""

    def test_show_by_citekey(self, mock_library: MagicMock) -> None:
        """show @citekey should use citekey lookup."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.storage_path = "/storage/doc.pdf"
        mock_doc.extracted_path = "/extracted/doc.md"
        mock_doc.content_hash = "abcd1234"
        mock_doc.citekey = "Smith2023"
        mock_doc.error_message = None
        mock_doc.error_code = None
        mock_doc.created_at = None
        mock_doc.updated_at = None

        mock_library.get_by_citekey.return_value = mock_doc
        mock_library.get_all_citekeys.return_value = ["Smith2023"]

        result = runner.invoke(app, ["show", "@Smith2023"])

        assert result.exit_code == 0
        assert "12345678" in result.output
        mock_library.get_by_citekey.assert_called_once_with("Smith2023")

    def test_show_citekey_not_found_with_suggestions(self, mock_library: MagicMock) -> None:
        """show @citekey should show suggestions on miss."""
        mock_library.get_by_citekey.return_value = None
        mock_library.get_all_citekeys.return_value = ["Smith2023", "Smith2024"]

        result = runner.invoke(app, ["show", "@Smth2023"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()
        # Should suggest similar citekeys
        assert "Smith2023" in result.output or "Did you mean" in result.output
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py::TestShowCommandCitekey -v`
Expected: FAIL (show doesn't support @citekey yet)

**Step 3: Write minimal implementation**

Update `src/local_library/cli/show.py`:

```python
"""Show command - display document details."""

# pattern: Imperative Shell

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from local_library.cli.utils import resolve_identifier
from local_library.core import Library, LookupError

console = Console()
err_console = Console(stderr=True)


def show(
    identifier: Annotated[str, typer.Argument(help="Document ID (UUID or @citekey)")],
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
) -> None:
    """Show details for a specific document.

    Supports both UUID (full or partial) and @citekey identifiers.
    """
    try:
        with Library() as lib:
            doc = resolve_identifier(identifier, lib)
    except LookupError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
            if "suggestions" in e.details and e.details["suggestions"]:
                err_console.print("[dim]Did you mean:[/dim]")
                for suggestion in e.details["suggestions"]:
                    err_console.print(f"  [cyan]@{suggestion}[/cyan]")
        raise typer.Exit(code=1) from None

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
            "needs_review": "yellow bold",
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

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py::TestShowCommandCitekey tests/unit/test_cli.py::TestShowCommand -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/show.py tests/unit/test_cli.py
git commit -m "feat(cli): add @citekey support to show command

Uses resolve_identifier for unified UUID/@citekey lookup.
Shows suggestions on citekey miss.
Adds NEEDS_REVIEW status styling."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update delete command to use resolve_identifier

**Files:**
- Modify: `src/local_library/cli/delete.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cli.py`:

```python
class TestDeleteCommandCitekey:
    """Tests for delete command with citekey support."""

    def test_delete_by_citekey(self, mock_library: MagicMock) -> None:
        """delete @citekey should use citekey lookup."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.original_path = "/path/to/doc.pdf"

        mock_library.get_by_citekey.return_value = mock_doc
        mock_library.get_all_citekeys.return_value = ["Smith2023"]
        mock_library.delete.return_value = True

        result = runner.invoke(app, ["delete", "--force", "@Smith2023"])

        assert result.exit_code == 0
        assert "deleted" in result.output.lower()
        mock_library.get_by_citekey.assert_called_once_with("Smith2023")

    def test_delete_citekey_not_found_with_suggestions(self, mock_library: MagicMock) -> None:
        """delete @citekey should show suggestions on miss."""
        mock_library.get_by_citekey.return_value = None
        mock_library.get_all_citekeys.return_value = ["Smith2023", "Smith2024"]

        result = runner.invoke(app, ["delete", "--force", "@Smth2023"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py::TestDeleteCommandCitekey -v`
Expected: FAIL (delete doesn't support @citekey yet)

**Step 3: Write minimal implementation**

Update `src/local_library/cli/delete.py`:

```python
"""Delete command - remove documents from the library."""

# pattern: Imperative Shell

import json
from typing import Annotated

import typer
from rich.console import Console

from local_library.cli.utils import resolve_identifier
from local_library.core import Library, LookupError

console = Console()
err_console = Console(stderr=True)


def delete(
    identifier: Annotated[str, typer.Argument(help="Document ID (UUID or @citekey)")],
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

    Supports both UUID (full or partial) and @citekey identifiers.

    By default, deletes both the database record and the storage files.
    Use --keep-files to preserve the files on disk.
    Use --force to skip the confirmation prompt.
    """
    try:
        with Library() as lib:
            # First get the document to confirm it exists and show details
            doc = resolve_identifier(identifier, lib)

            # Confirmation prompt unless --force
            if not force and not json_output:
                console.print("[yellow]About to delete:[/yellow]")
                console.print(f"  ID: {doc.id}")
                console.print(f"  Path: {doc.original_path}")
                console.print(f"  Status: {doc.status.value}")
                if doc.citekey:
                    console.print(f"  Citekey: {doc.citekey}")

                if not keep_files:
                    console.print("  [dim]Files will be deleted from disk[/dim]")

                confirmed = typer.confirm("Continue?")
                if not confirmed:
                    console.print("[dim]Cancelled.[/dim]")
                    raise typer.Exit(code=0)

            # Perform deletion using doc.id (UUID)
            lib.delete(str(doc.id), delete_files=not keep_files)

    except LookupError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
            if "suggestions" in e.details and e.details["suggestions"]:
                err_console.print("[dim]Did you mean:[/dim]")
                for suggestion in e.details["suggestions"]:
                    err_console.print(f"  [cyan]@{suggestion}[/cyan]")
        raise typer.Exit(code=1) from None

    if json_output:
        console.print(json.dumps({"deleted": str(doc.id), "files_deleted": not keep_files}))
    else:
        console.print(f"[green]deleted[/green]: {doc.id}")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py::TestDeleteCommandCitekey tests/unit/test_cli.py::TestDeleteCommand -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/delete.py tests/unit/test_cli.py
git commit -m "feat(cli): add @citekey support to delete command

Uses resolve_identifier for unified UUID/@citekey lookup.
Shows suggestions on citekey miss.
Shows citekey in confirmation prompt."
```
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

**Phase complete when:** `show @citekey` and `delete @citekey` work with suggestions on miss.
