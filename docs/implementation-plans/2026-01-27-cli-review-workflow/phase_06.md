## Phase 6: Review Command (Optional)

**Goal:** Convenience command combining open + update

---

<!-- START_TASK_1 -->
### Task 1: Implement review command

**Files:**
- Create: `src/local_library/cli/review.py`
- Modify: `src/local_library/cli/main.py` (register command)

**Step 1: Write the failing test**

Create `tests/unit/test_cli_review.py`:

```python
"""Unit tests for review command."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core.models import DocumentStatus

runner = CliRunner()


@pytest.fixture
def mock_library_review():
    """Provide a mock Library for review command testing."""
    with patch("local_library.cli.review.Library") as mock_lib_cls:
        mock_lib = MagicMock()
        mock_lib_cls.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib_cls.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_lib


class TestReviewCommand:
    """Tests for review command."""

    def test_review_opens_pdf_then_markdown_then_update(
        self, mock_library_review: MagicMock
    ) -> None:
        """review should open PDF (non-blocking), markdown (blocking), then update."""
        mock_doc = MagicMock()
        mock_doc.id = UUID("12345678-1234-1234-1234-123456789abc")
        mock_doc.status = DocumentStatus.NEEDS_REVIEW
        mock_doc.citekey = "Smith2023"
        mock_doc.csl_json = {"type": "article", "title": "Test"}
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.storage_path = "/storage/doc.pdf"
        mock_doc.extracted_path = "/extracted/doc.md"
        mock_doc.content_hash = "abc123"
        mock_doc.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_doc.updated_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
        mock_doc.title = "Test"
        mock_doc.authors = "Smith"
        mock_doc.issued_date = "2023"

        mock_library_review.get.return_value = mock_doc
        mock_library_review.get_all_citekeys.return_value = ["Smith2023"]

        call_order = []

        def track_popen(*args, **kwargs):
            call_order.append("pdf_open")
            return MagicMock()

        def track_run_markdown(*args, **kwargs):
            call_order.append("markdown_open")

        def track_run_editor(*args, **kwargs):
            call_order.append("editor_open")

        # Mock to return empty file (abort update)
        with (
            patch("local_library.cli.review.find_editor", return_value="/usr/bin/nvim"),
            patch("local_library.cli.review._open_pdf", side_effect=track_popen),
            patch("local_library.cli.review._open_markdown", side_effect=track_run_markdown),
            patch("local_library.cli.review._run_update_workflow", return_value=None),
        ):
            result = runner.invoke(app, ["review", "12345678"])

            assert result.exit_code == 0
            # PDF should open before markdown
            assert call_order == ["pdf_open", "markdown_open"]

    def test_review_no_extracted_path(self, mock_library_review: MagicMock) -> None:
        """review should error if no markdown available."""
        mock_doc = MagicMock()
        mock_doc.id = UUID("12345678-1234-1234-1234-123456789abc")
        mock_doc.extracted_path = None
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.PENDING

        mock_library_review.get.return_value = mock_doc

        result = runner.invoke(app, ["review", "12345678"])

        assert result.exit_code == 1
        assert "no extracted markdown" in result.output.lower()

    def test_review_citekey_lookup(self, mock_library_review: MagicMock) -> None:
        """review @citekey should use citekey lookup."""
        mock_doc = MagicMock()
        mock_doc.id = UUID("12345678-1234-1234-1234-123456789abc")
        mock_doc.status = DocumentStatus.NEEDS_REVIEW
        mock_doc.citekey = "Smith2023"
        mock_doc.csl_json = {"type": "article", "title": "Test"}
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.storage_path = "/storage/doc.pdf"
        mock_doc.extracted_path = "/extracted/doc.md"
        mock_doc.content_hash = "abc123"
        mock_doc.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_doc.updated_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
        mock_doc.title = "Test"
        mock_doc.authors = "Smith"
        mock_doc.issued_date = "2023"

        mock_library_review.get_by_citekey.return_value = mock_doc
        mock_library_review.get_all_citekeys.return_value = ["Smith2023"]

        with (
            patch("local_library.cli.review.find_editor", return_value="/usr/bin/nvim"),
            patch("local_library.cli.review._open_pdf"),
            patch("local_library.cli.review._open_markdown"),
            patch("local_library.cli.review._run_update_workflow", return_value=None),
        ):
            result = runner.invoke(app, ["review", "@Smith2023"])

            assert result.exit_code == 0
            mock_library_review.get_by_citekey.assert_called_once_with("Smith2023")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'local_library.cli.review'`

**Step 3: Write minimal implementation**

Create `src/local_library/cli/review.py`:

```python
"""Review command - combined open + update workflow."""

# pattern: Imperative Shell

import json
import subprocess
import tempfile
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.prompt import Confirm

from local_library.cli.open import find_editor
from local_library.cli.update import (
    build_editable_json,
    insert_errors_as_comments,
    parse_edited_json,
    validate_edited_json,
    _check_citekey_regeneration,
)
from local_library.cli.utils import resolve_identifier
from local_library.core import Library, LookupError
from local_library.core.models import Document, DocumentStatus
from local_library.ingestion.metadata import MetadataHandler

console = Console()
err_console = Console(stderr=True)


def _open_pdf(path: str) -> None:
    """Open PDF in system viewer (non-blocking)."""
    subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _open_markdown(path: str, editor: str) -> None:
    """Open markdown in editor (blocking)."""
    subprocess.run([editor, path], check=False)


def _run_update_workflow(
    doc: Document,
    lib: Any,
    editor: str,
    all_citekeys: list[str],
) -> None:
    """Run the update workflow after viewing files.

    This is extracted to allow mocking in tests.
    """
    # Build initial JSON
    json_content = build_editable_json(doc)

    # Edit loop
    while True:
        # Write to temp file and open editor
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
        ) as f:
            f.write(json_content)
            temp_path = f.name

        subprocess.run([editor, temp_path], check=False)

        # Read edited content
        with open(temp_path) as f:
            edited_content = f.read()

        # Parse
        try:
            parsed = parse_edited_json(edited_content)
        except ValueError as e:
            json_content = insert_errors_as_comments(edited_content, [str(e)])
            continue

        # Check for abort
        if parsed is None:
            console.print("[yellow]Update aborted.[/yellow]")
            return

        # Validate
        errors = validate_edited_json(parsed, doc.citekey, all_citekeys)
        if errors:
            json_content = insert_errors_as_comments(edited_content, errors)
            continue

        # Valid - break out of loop
        break

    # Check if citekey should be regenerated
    new_citekey = parsed.get("citekey")
    new_csl = parsed.get("csl_json")
    if _check_citekey_regeneration(doc.csl_json, new_csl, doc.citekey, new_citekey):
        if Confirm.ask(
            "Author/title/year changed. Regenerate citekey?",
            default=False,
        ):
            handler = MetadataHandler()
            new_citekey = handler.generate_citekey(new_csl)
            if new_citekey in all_citekeys and new_citekey != doc.citekey:
                from local_library.core.storage import get_unique_citekey, get_connection

                conn = get_connection()
                new_citekey = get_unique_citekey(conn, new_citekey)
            console.print(f"[dim]New citekey: {new_citekey}[/dim]")

    # Apply updates
    lib.update_metadata(
        doc.id,
        status=DocumentStatus(parsed["status"]),
        citekey=new_citekey,
        csl_json=new_csl,
    )

    console.print(f"[green]Updated document {doc.id}[/green]")


def review(
    identifier: Annotated[
        str, typer.Argument(help="Document ID (UUID or @citekey)")
    ],
) -> None:
    """Review a document: open files then edit metadata.

    Opens the PDF in your system viewer (non-blocking), then opens the
    extracted markdown in your editor (blocking). After you close the
    markdown, launches the metadata editor for corrections.

    This is a convenience command combining:
      open --both <id>
      update <id>

    Supports both UUID (full or partial) and @citekey identifiers.
    """
    # Find editor first
    editor = find_editor()
    if not editor:
        err_console.print("[red]error:[/red] no editor found")
        err_console.print(
            "[dim]Install nvim/vim or set $EDITOR environment variable.[/dim]"
        )
        raise typer.Exit(code=1) from None

    try:
        with Library() as lib:
            doc = resolve_identifier(identifier, lib)

            # Check for extracted markdown
            if not doc.extracted_path:
                err_console.print(
                    f"[red]error:[/red] no extracted markdown for document {doc.id}"
                )
                err_console.print(
                    "[dim]Document may still be processing or extraction failed.[/dim]"
                )
                raise typer.Exit(code=1) from None

            all_citekeys = lib.get_all_citekeys()

            # Step 1: Open PDF (non-blocking)
            _open_pdf(doc.storage_path)
            console.print(f"[green]Opened PDF:[/green] {doc.storage_path}")

            # Step 2: Open markdown (blocking)
            _open_markdown(doc.extracted_path, editor)

            # Step 3: Run update workflow
            _run_update_workflow(doc, lib, editor, all_citekeys)

    except LookupError as e:
        err_console.print(f"[red]error:[/red] {e.message}")
        if "suggestions" in e.details and e.details["suggestions"]:
            err_console.print("[dim]Did you mean:[/dim]")
            for suggestion in e.details["suggestions"]:
                err_console.print(f"  [cyan]@{suggestion}[/cyan]")
        raise typer.Exit(code=1) from None
```

Register in `src/local_library/cli/main.py`:

```python
"""CLI entry point with Typer app and shared context."""

# pattern: Imperative Shell

import typer

from local_library.cli import add as add_cmd
from local_library.cli import delete as delete_cmd
from local_library.cli import list as list_cmd
from local_library.cli import open as open_cmd
from local_library.cli import review as review_cmd
from local_library.cli import show as show_cmd
from local_library.cli import update as update_cmd

# Create Typer app
app = typer.Typer(
    name="local-library",
    help="Personal knowledge management for local documents.",
    add_completion=False,
)

# Register subcommands
app.command(name="add")(add_cmd.add)
app.command(name="list")(list_cmd.list_docs)
app.command(name="show")(show_cmd.show)
app.command(name="delete")(delete_cmd.delete)
app.command(name="open")(open_cmd.open_doc)
app.command(name="update")(update_cmd.update)
app.command(name="review")(review_cmd.review)


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_review.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/review.py src/local_library/cli/main.py tests/unit/test_cli_review.py
git commit -m "feat(cli): add review command for combined workflow

Convenience command that opens PDF (non-blocking), markdown (blocking),
then launches update workflow for metadata corrections.
Supports @citekey lookup with suggestions on miss."
```
<!-- END_TASK_1 -->

---

**Phase complete when:** `review @citekey` opens both files then launches update.
