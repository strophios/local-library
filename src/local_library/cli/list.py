"""List command - list documents in the library."""

# pattern: Imperative Shell

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from local_library.core import DocumentStatus, Library

console = Console()

DEFAULT_LIMIT = 15


def _truncate(text: str | None, max_length: int) -> str:
    """Truncate text with ellipsis if too long."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def list_docs(
    status: Annotated[
        str | None,
        typer.Option(
            "--status", "-s", help="Filter by status (pending, ready, failed, needs_review)"
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-n", help="Maximum number of rows to display"),
    ] = None,
    show_all: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show all documents in pager"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
) -> None:
    """List all documents in the library.

    Displays documents in a table format by default, or as JSON with --json.
    Use --status to filter by document status.

    By default, shows up to 15 documents. Use --limit to change this,
    or --all to show all documents in a pager.
    """
    # Parse status filter
    status_filter: DocumentStatus | None = None
    if status:
        try:
            status_filter = DocumentStatus(status.lower())
        except ValueError:
            console.print(f"[red]error:[/red] invalid status '{status}'")
            console.print("[dim]valid values: pending, ready, failed, needs_review[/dim]")
            raise typer.Exit(code=1) from None

    with Library() as lib:
        docs = lib.list(status=status_filter)

    total_count = len(docs)

    if json_output:
        output = [
            {
                "id": str(doc.id),
                "citekey": doc.citekey,
                "status": doc.status.value,
                "title": doc.title,
                "authors": doc.authors,
                "original_path": doc.original_path,
                "content_hash": doc.content_hash[:12] + "...",
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in docs
        ]
        console.print(json.dumps(output, indent=2))
        return

    if not docs:
        console.print("[dim]No documents found.[/dim]")
        return

    # Determine display limit
    if show_all:
        display_limit = total_count
    elif limit is not None:
        display_limit = limit
    else:
        display_limit = DEFAULT_LIMIT

    # Build table
    table = Table(title="Documents")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Citekey", style="blue", no_wrap=True)
    table.add_column("Status", style="magenta")
    table.add_column("Title")
    table.add_column("Authors")

    status_style = {
        DocumentStatus.PENDING: "yellow",
        DocumentStatus.READY: "green",
        DocumentStatus.FAILED: "red",
        DocumentStatus.NEEDS_REVIEW: "yellow bold",
    }

    for doc in docs[:display_limit]:
        short_id = str(doc.id)[:8]
        style = status_style.get(doc.status, "white")

        table.add_row(
            short_id,
            doc.citekey or "",
            f"[{style}]{doc.status.value}[/{style}]",
            _truncate(doc.title, 40),
            _truncate(doc.authors, 25),
        )

    # Output with pager if showing all
    if show_all:
        with console.pager():
            console.print(table)
            console.print(f"\n[dim]{total_count} document(s)[/dim]")
    else:
        console.print(table)
        if total_count > display_limit:
            console.print(
                f"\n[dim]Showing {display_limit} of {total_count} items. "
                f"Use --all to see all.[/dim]"
            )
        else:
            console.print(f"\n[dim]{total_count} document(s)[/dim]")
