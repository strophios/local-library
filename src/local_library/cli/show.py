"""Show command - display document details."""

# pattern: Imperative Shell

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from local_library.core import Library, LookupError

console = Console()
err_console = Console(stderr=True)


def show(
    doc_id: Annotated[str, typer.Argument(help="Document ID (full or partial UUID)")],
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
) -> None:
    """Show details for a specific document.

    Supports partial UUID matching - if the prefix uniquely identifies
    a document, it will be shown.
    """
    try:
        with Library() as lib:
            doc = lib.get(doc_id)
    except LookupError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1)

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
