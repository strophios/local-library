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
