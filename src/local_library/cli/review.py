"""Review command - combined open + update workflow."""

# pattern: Imperative Shell

import subprocess
import tempfile
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.prompt import Confirm

from local_library.cli.open import find_editor
from local_library.cli.update import (
    _check_citekey_regeneration,
    build_editable_json,
    insert_errors_as_comments,
    parse_edited_json,
    validate_edited_json,
)
from local_library.cli.utils import resolve_identifier
from local_library.core import Library, LookupError
from local_library.core.models import Document, DocumentStatus
from local_library.core.storage import get_connection, get_unique_citekey
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
    identifier: Annotated[str, typer.Argument(help="Document ID (UUID or @citekey)")],
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
        err_console.print("[dim]Install nvim/vim or set $EDITOR environment variable.[/dim]")
        raise typer.Exit(code=1) from None

    try:
        with Library() as lib:
            doc = resolve_identifier(identifier, lib)

            # Check for extracted markdown
            if not doc.extracted_path:
                err_console.print(f"[red]error:[/red] no extracted markdown for document {doc.id}")
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
