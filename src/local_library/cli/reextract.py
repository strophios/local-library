"""Reextract command - re-run text extraction on existing documents."""

# pattern: Imperative Shell

from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from local_library.cli.utils import resolve_identifier
from local_library.core import Library
from local_library.core.errors import ExtractionError, LookupError
from local_library.core.models import DocumentStatus

console = Console()
err_console = Console(stderr=True)


def reextract(
    identifier: Annotated[
        str | None,
        typer.Argument(
            help="Document ID (UUID or @citekey) to re-extract. Omit for --all."
        ),
    ] = None,
    all_docs: Annotated[
        bool,
        typer.Option("--all", "-a", help="Re-extract all READY/NEEDS_REVIEW documents"),
    ] = False,
) -> None:
    """Re-run text extraction on existing documents.

    Re-runs the extraction pipeline (Marker + cleanup) on stored PDFs,
    overwrites extracted markdown, and marks embeddings as STALE.
    Does not modify metadata. Use `embed --pending` afterward to
    re-embed with the new text.

    Examples:

        # Re-extract a single document
        local-library reextract abc123
        local-library reextract @Smith2023

        # Re-extract all documents
        local-library reextract --all

        # Re-extract all, then re-embed
        local-library reextract --all && local-library embed --pending
    """
    if identifier and all_docs:
        err_console.print("[red]error:[/red] cannot specify identifier with --all")
        raise typer.Exit(code=1)

    if not identifier and not all_docs:
        err_console.print("[red]error:[/red] must specify identifier or --all")
        raise typer.Exit(code=1)

    try:
        with Library(embed_on_add=False) as lib:
            if identifier:
                _reextract_single(lib, identifier)
            else:
                _reextract_all(lib)
    except LookupError as e:
        err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None
    except ExtractionError as e:
        err_console.print(f"[red]error:[/red] extraction failed: {e.message}")
        raise typer.Exit(code=1) from None


def _reextract_single(lib: Library, identifier: str) -> None:
    """Re-extract a single document."""
    doc = resolve_identifier(identifier, lib)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        label = doc.citekey or str(doc.id)[:8]
        progress.add_task(f"Re-extracting {label}...")
        updated = lib.reextract(str(doc.id))

    console.print(f"[green]re-extracted[/green]: {updated.id}")
    if updated.citekey:
        console.print(f"  [dim]citekey:[/dim] {updated.citekey}")
    console.print(f"  [dim]embeddings:[/dim] {updated.embedding_status.value}")
    console.print("[dim]run 'local-library embed --pending' to re-embed[/dim]")


def _reextract_all(lib: Library) -> None:
    """Re-extract all eligible documents."""
    from local_library.core.storage import list_documents

    # Get all READY and NEEDS_REVIEW documents
    docs = list_documents(lib.conn, status=DocumentStatus.READY)
    docs += list_documents(lib.conn, status=DocumentStatus.NEEDS_REVIEW)

    if not docs:
        console.print("[dim]no documents to re-extract[/dim]")
        return

    results = {"success": 0, "failed": 0}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Re-extracting {len(docs)} documents...", total=len(docs)
        )

        for i, doc in enumerate(docs):
            try:
                lib.reextract(str(doc.id))
                results["success"] += 1
            except Exception as e:  # noqa: BLE001
                results["failed"] += 1
                label = doc.citekey or str(doc.id)[:8]
                err_console.print(f"[dim]failed: {label}: {e}[/dim]")

            progress.update(task, completed=i + 1)

    console.print(f"[green]re-extracted[/green]: {results['success']} documents")
    if results["failed"] > 0:
        console.print(f"[yellow]failed[/yellow]: {results['failed']} documents")
    console.print("[dim]run 'local-library embed --pending' to re-embed[/dim]")
