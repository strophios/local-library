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
    identifier: Annotated[str, typer.Argument(help="Document ID (UUID or @citekey)")],
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
        err_console.print(f"[red]error:[/red] no extracted markdown for document {doc.id}")
        err_console.print("[dim]Document may still be processing or extraction failed.[/dim]")
        raise typer.Exit(code=1) from None

    # Find editor
    editor = find_editor()
    if not editor:
        err_console.print("[red]error:[/red] no editor found")
        err_console.print("[dim]Install nvim/vim or set $EDITOR environment variable.[/dim]")
        raise typer.Exit(code=1) from None

    # Handle both mode
    if both:
        _open_pdf(doc.storage_path)
        console.print(f"[green]Opened PDF:[/green] {doc.storage_path}")

    # Open markdown (blocking)
    _open_markdown(doc.extracted_path, editor)
