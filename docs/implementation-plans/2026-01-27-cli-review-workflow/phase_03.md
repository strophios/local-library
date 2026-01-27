## Phase 3: Open Command

**Goal:** View document files (markdown and/or PDF)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create `cli/open.py` with editor detection

**Files:**
- Create: `src/local_library/cli/open.py`

**Step 1: Write the failing test**

Create `tests/unit/test_cli_open.py`:

```python
"""Unit tests for open command."""

import os
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core.models import DocumentStatus

runner = CliRunner()


@pytest.fixture
def mock_library_open():
    """Provide a mock Library for open command testing."""
    with patch("local_library.cli.open.Library") as mock_lib_cls:
        mock_lib = MagicMock()
        mock_lib_cls.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib_cls.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_lib


class TestFindEditor:
    """Tests for editor detection logic."""

    def test_find_editor_nvim(self) -> None:
        """Should prefer nvim if available."""
        from local_library.cli.open import find_editor

        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: f"/usr/bin/{x}" if x == "nvim" else None
            editor = find_editor()
            assert editor == "/usr/bin/nvim"

    def test_find_editor_vim_fallback(self) -> None:
        """Should fall back to vim if nvim not available."""
        from local_library.cli.open import find_editor

        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: "/usr/bin/vim" if x == "vim" else None
            editor = find_editor()
            assert editor == "/usr/bin/vim"

    def test_find_editor_env_fallback(self) -> None:
        """Should use $EDITOR if nvim/vim not available."""
        from local_library.cli.open import find_editor

        with (
            patch("shutil.which", return_value=None),
            patch.dict(os.environ, {"EDITOR": "/usr/bin/nano"}),
        ):
            editor = find_editor()
            assert editor == "/usr/bin/nano"

    def test_find_editor_none(self) -> None:
        """Should return None if no editor found."""
        from local_library.cli.open import find_editor

        with (
            patch("shutil.which", return_value=None),
            patch.dict(os.environ, {}, clear=True),
        ):
            # Remove EDITOR if present
            os.environ.pop("EDITOR", None)
            editor = find_editor()
            assert editor is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_open.py::TestFindEditor -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'local_library.cli.open'`

**Step 3: Write minimal implementation**

Create `src/local_library/cli/open.py`:

```python
"""Open command - open document files for viewing."""

# pattern: Imperative Shell

import os
import shutil
import subprocess
from typing import Annotated

import typer
from rich.console import Console

from local_library.cli.utils import resolve_identifier
from local_library.core import Library, LookupError

console = Console()
err_console = Console(stderr=True)


def find_editor() -> str | None:
    """Find an editor to use for markdown files.

    Preference order: nvim > vim > $EDITOR

    Returns:
        Path to editor, or None if not found
    """
    # Try nvim first
    nvim_path = shutil.which("nvim")
    if nvim_path:
        return nvim_path

    # Try vim
    vim_path = shutil.which("vim")
    if vim_path:
        return vim_path

    # Fall back to $EDITOR
    return os.environ.get("EDITOR")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_open.py::TestFindEditor -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/open.py tests/unit/test_cli_open.py
git commit -m "feat(cli): add open command with editor detection

Prefers nvim > vim > \$EDITOR for markdown files."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement open command with --pdf and --both flags

**Files:**
- Modify: `src/local_library/cli/open.py`
- Modify: `src/local_library/cli/main.py` (register command)

**Step 1: Write the failing test**

Add to `tests/unit/test_cli_open.py`:

```python
class TestOpenCommand:
    """Tests for open command."""

    def test_open_markdown_default(self, mock_library_open: MagicMock) -> None:
        """open command should open markdown by default."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = "/path/to/doc.md"
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.READY

        mock_library_open.get.return_value = mock_doc

        with (
            patch("local_library.cli.open.find_editor", return_value="/usr/bin/nvim"),
            patch("local_library.cli.open.subprocess.run") as mock_run,
        ):
            result = runner.invoke(app, ["open", "12345678"])

            assert result.exit_code == 0
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "/usr/bin/nvim" in call_args
            assert "/path/to/doc.md" in call_args

    def test_open_pdf_flag(self, mock_library_open: MagicMock) -> None:
        """open --pdf should open PDF in system viewer."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = "/path/to/doc.md"
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.READY

        mock_library_open.get.return_value = mock_doc

        with patch("local_library.cli.open.subprocess.Popen") as mock_popen:
            result = runner.invoke(app, ["open", "--pdf", "12345678"])

            assert result.exit_code == 0
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]
            assert "open" in call_args
            assert "/path/to/doc.pdf" in call_args

    def test_open_both_flag(self, mock_library_open: MagicMock) -> None:
        """open --both should open PDF then markdown."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = "/path/to/doc.md"
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.READY

        mock_library_open.get.return_value = mock_doc

        with (
            patch("local_library.cli.open.find_editor", return_value="/usr/bin/nvim"),
            patch("local_library.cli.open.subprocess.Popen") as mock_popen,
            patch("local_library.cli.open.subprocess.run") as mock_run,
        ):
            result = runner.invoke(app, ["open", "--both", "12345678"])

            assert result.exit_code == 0
            # PDF opened first (non-blocking)
            mock_popen.assert_called_once()
            # Markdown opened second (blocking)
            mock_run.assert_called_once()

    def test_open_citekey_lookup(self, mock_library_open: MagicMock) -> None:
        """open @citekey should use citekey lookup."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = "/path/to/doc.md"
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.READY

        mock_library_open.get_by_citekey.return_value = mock_doc
        mock_library_open.get_all_citekeys.return_value = ["Smith2023"]

        with (
            patch("local_library.cli.open.find_editor", return_value="/usr/bin/nvim"),
            patch("local_library.cli.open.subprocess.run"),
        ):
            result = runner.invoke(app, ["open", "@Smith2023"])

            assert result.exit_code == 0
            mock_library_open.get_by_citekey.assert_called_once_with("Smith2023")

    def test_open_no_extracted_path(self, mock_library_open: MagicMock) -> None:
        """open should error if no markdown available."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = None
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.PENDING

        mock_library_open.get.return_value = mock_doc

        result = runner.invoke(app, ["open", "12345678"])

        assert result.exit_code == 1
        assert "no extracted markdown" in result.output.lower()

    def test_open_no_editor_found(self, mock_library_open: MagicMock) -> None:
        """open should error if no editor found."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = "/path/to/doc.md"
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.READY

        mock_library_open.get.return_value = mock_doc

        with patch("local_library.cli.open.find_editor", return_value=None):
            result = runner.invoke(app, ["open", "12345678"])

            assert result.exit_code == 1
            assert "no editor found" in result.output.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_open.py::TestOpenCommand -v`
Expected: FAIL (open command not implemented yet)

**Step 3: Write minimal implementation**

Update `src/local_library/cli/open.py`:

```python
"""Open command - open document files for viewing."""

# pattern: Imperative Shell

import os
import shutil
import subprocess
from typing import Annotated

import typer
from rich.console import Console

from local_library.cli.utils import resolve_identifier
from local_library.core import Library, LookupError

console = Console()
err_console = Console(stderr=True)


def find_editor() -> str | None:
    """Find an editor to use for markdown files.

    Preference order: nvim > vim > $EDITOR

    Returns:
        Path to editor, or None if not found
    """
    # Try nvim first
    nvim_path = shutil.which("nvim")
    if nvim_path:
        return nvim_path

    # Try vim
    vim_path = shutil.which("vim")
    if vim_path:
        return vim_path

    # Fall back to $EDITOR
    return os.environ.get("EDITOR")


def _open_pdf(path: str) -> None:
    """Open PDF in system viewer (non-blocking).

    Args:
        path: Path to PDF file
    """
    # macOS: use 'open' command
    subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _open_markdown(path: str, editor: str) -> None:
    """Open markdown in editor (blocking).

    Args:
        path: Path to markdown file
        editor: Path to editor executable
    """
    subprocess.run([editor, path], check=False)


def open_doc(
    identifier: Annotated[
        str, typer.Argument(help="Document ID (UUID or @citekey)")
    ],
    pdf: Annotated[
        bool,
        typer.Option("--pdf", "-p", help="Open PDF instead of markdown"),
    ] = False,
    both: Annotated[
        bool,
        typer.Option("--both", "-b", help="Open both PDF and markdown"),
    ] = False,
) -> None:
    """Open a document for viewing.

    By default, opens the extracted markdown in your editor (nvim > vim > $EDITOR).
    Use --pdf to open the PDF in your system viewer instead.
    Use --both to open both (PDF first, then markdown).

    Supports both UUID (full or partial) and @citekey identifiers.
    """
    try:
        with Library() as lib:
            doc = resolve_identifier(identifier, lib)
    except LookupError as e:
        err_console.print(f"[red]error:[/red] {e.message}")
        if "suggestions" in e.details and e.details["suggestions"]:
            err_console.print("[dim]Did you mean:[/dim]")
            for suggestion in e.details["suggestions"]:
                err_console.print(f"  [cyan]@{suggestion}[/cyan]")
        raise typer.Exit(code=1) from None

    # Handle PDF mode
    if pdf:
        _open_pdf(doc.storage_path)
        console.print(f"[green]Opened PDF:[/green] {doc.storage_path}")
        return

    # For markdown or both mode, check if extracted path exists
    if not doc.extracted_path:
        err_console.print(
            f"[red]error:[/red] no extracted markdown for document {doc.id}"
        )
        err_console.print("[dim]Document may still be processing or extraction failed.[/dim]")
        raise typer.Exit(code=1) from None

    # Find editor
    editor = find_editor()
    if not editor:
        err_console.print("[red]error:[/red] no editor found")
        err_console.print(
            "[dim]Install nvim/vim or set $EDITOR environment variable.[/dim]"
        )
        raise typer.Exit(code=1) from None

    # Handle both mode
    if both:
        _open_pdf(doc.storage_path)
        console.print(f"[green]Opened PDF:[/green] {doc.storage_path}")

    # Open markdown (blocking)
    _open_markdown(doc.extracted_path, editor)
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
from local_library.cli import show as show_cmd

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


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_open.py::TestOpenCommand -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/open.py src/local_library/cli/main.py tests/unit/test_cli_open.py
git commit -m "feat(cli): implement open command with PDF and markdown support

Opens markdown in nvim/vim/\$EDITOR by default.
--pdf opens in system viewer, --both opens both.
Supports @citekey lookup with suggestions on miss."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update mock_library fixture for open command

**Files:**
- Modify: `tests/unit/test_cli.py` (update fixture to include open)

**Step 1: Verify open tests work with current setup**

The open command tests use a separate fixture (`mock_library_open`). To ensure consistency across CLI tests, update the main `mock_library` fixture to also patch `local_library.cli.open.Library`.

**Step 2: Update the fixture**

Update `tests/unit/test_cli.py` fixture:

```python
@pytest.fixture
def mock_library():
    """Provide a mock Library for CLI testing."""
    with (
        patch("local_library.cli.add.Library") as mock_add,
        patch("local_library.cli.list.Library") as mock_list,
        patch("local_library.cli.show.Library") as mock_show,
        patch("local_library.cli.delete.Library") as mock_delete,
        patch("local_library.cli.open.Library") as mock_open,
    ):
        mock_lib = MagicMock()
        mock_add.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_add.return_value.__exit__ = MagicMock(return_value=False)
        mock_list.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_list.return_value.__exit__ = MagicMock(return_value=False)
        mock_show.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_show.return_value.__exit__ = MagicMock(return_value=False)
        mock_delete.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_delete.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        yield mock_lib
```

**Step 3: Run all CLI tests**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/test_cli_open.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add tests/unit/test_cli.py
git commit -m "test(cli): update mock_library fixture for open command"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

**Phase complete when:** `open @citekey` opens markdown, `--pdf` opens PDF, `--both` opens both.
