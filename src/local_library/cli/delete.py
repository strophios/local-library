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
                console.print("[yellow]About to delete:[/yellow]")
                console.print(f"  ID: {doc.id}")
                console.print(f"  Path: {doc.original_path}")
                console.print(f"  Status: {doc.status.value}")

                if not keep_files:
                    console.print("  [dim]Files will be deleted from disk[/dim]")

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
        raise typer.Exit(code=1) from None

    if json_output:
        console.print(json.dumps({"deleted": str(doc.id), "files_deleted": not keep_files}))
    else:
        console.print(f"[green]deleted[/green]: {doc.id}")
