"""Search command - search documents by content."""

# pattern: Imperative Shell

import json
from typing import Annotated
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table

from local_library.cli.utils import resolve_identifier
from local_library.core import Library
from local_library.core.errors import EmbeddingError, FTSQueryError, LookupError
from local_library.core.vec_extension import is_vec_available
from local_library.embeddings.base import SearchResult

console = Console()
err_console = Console(stderr=True)

VALID_MODES = ("hybrid", "vector", "fts")


def _truncate(text: str, max_length: int) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def search(
    query: Annotated[
        str,
        typer.Argument(help="Search query (natural language or keywords)"),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum number of results"),
    ] = 10,
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="Search mode: hybrid, vector, or fts"),
    ] = "hybrid",
    doc_id: Annotated[
        str | None,
        typer.Option("--doc", "-d", help="Limit search to a specific document (UUID or @citekey)"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output results as JSON"),
    ] = False,
) -> None:
    """Search documents by content using semantic and keyword search.

    Uses hybrid search (vector + full-text) by default. Vector search captures
    semantic similarity; full-text search captures exact keyword matches.
    Results are ranked by relevance.

    Examples:

        # Basic search
        local-library search "machine learning"

        # Keyword-only search
        local-library search "Smith 2023" --mode fts

        # Search within a specific document
        local-library search "neural networks" --doc @Author2023

        # Get more results as JSON
        local-library search "climate change" --limit 20 --json
    """
    if not is_vec_available():
        if json_output:
            err_console.print(json.dumps({"error": "sqlite-vec extension not available"}))
        else:
            err_console.print("[red]error:[/red] sqlite-vec extension not available")
            err_console.print("[dim]Install sqlite-vec to enable search features[/dim]")
        raise typer.Exit(code=1)

    if mode not in VALID_MODES:
        if json_output:
            err_console.print(
                json.dumps({"error": f"invalid mode: {mode} (expected hybrid, vector, or fts)"})
            )
        else:
            err_console.print(
                f"[red]error:[/red] invalid mode: {mode} (expected hybrid, vector, or fts)"
            )
        raise typer.Exit(code=1)

    try:
        with Library(embed_on_add=False) as lib:
            # Resolve document filter if provided
            doc_ids: list[UUID] | None = None
            if doc_id:
                doc = resolve_identifier(doc_id, lib)
                doc_ids = [doc.id]

            retriever = lib.get_retriever(mode=mode)
            results = retriever.retrieve(query, k=limit, doc_ids=doc_ids)

            if json_output:
                _output_json(results)
            else:
                _output_table(results, query, mode)

    except LookupError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None
    except FTSQueryError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
            err_console.print("[dim]Try simplifying your query or using --mode vector[/dim]")
        raise typer.Exit(code=1) from None
    except EmbeddingError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None


def _output_json(results: list[SearchResult]) -> None:
    """Output search results as JSON."""
    output = []
    for r in results:
        output.append(
            {
                "chunk_id": r.chunk.chunk_id,
                "doc_id": str(r.chunk.doc_id),
                "chunk_index": r.chunk.chunk_index,
                "score": round(r.score, 6),
                "section": r.chunk.section,
                "doc_title": r.doc_title,
                "doc_citekey": r.doc_citekey,
                "search_methods": sorted(r.search_methods),
                "text": r.chunk.text,
            }
        )
    print(json.dumps(output, indent=2))


def _output_table(results: list[SearchResult], query: str, mode: str) -> None:
    """Output search results as a Rich table."""
    if not results:
        console.print(f'[dim]no results for[/dim] "{query}"')
        return

    table = Table(title=f'Search: "{query}" ({mode}, {len(results)} results)')
    table.add_column("#", style="dim", width=3)
    table.add_column("Score", width=8)
    table.add_column("Source", width=30)
    table.add_column("Section", width=25, style="dim")
    table.add_column("Methods", width=10)
    table.add_column("Text", ratio=1)

    for i, r in enumerate(results, start=1):
        # Format source as citekey or title
        source = r.doc_citekey or _truncate(r.doc_title or str(r.chunk.doc_id)[:8], 28)

        # Format section with truncation if needed
        section = _truncate(r.chunk.section, 23) if r.chunk.section else ""

        # Format methods
        methods = ",".join(sorted(r.search_methods))

        # Format text preview
        text_preview = _truncate(r.chunk.text.replace("\n", " "), 80)

        table.add_row(
            str(i),
            f"{r.score:.4f}",
            source,
            section,
            methods,
            text_preview,
        )

    console.print(table)
