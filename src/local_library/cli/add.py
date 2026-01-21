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
