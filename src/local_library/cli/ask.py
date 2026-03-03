"""Ask command - query the library using RAG."""

# pattern: Imperative Shell

import json
from typing import Annotated, Any
from uuid import UUID

import typer
from rich.console import Console
from rich.live import Live
from rich.text import Text

from local_library.cli.utils import resolve_identifier
from local_library.core import Library
from local_library.core.errors import EmbeddingError, LLMError, LookupError, RAGError
from local_library.core.models import RAGResponse
from local_library.core.vec_extension import is_vec_available

console = Console()
err_console = Console(stderr=True)

VALID_MODES = ("hybrid", "vector", "fts")


def ask(
    question: Annotated[
        str,
        typer.Argument(help="Question to ask about your library"),
    ],
    model: Annotated[
        str | None,
        typer.Option("--model", help="LLM model for answer generation"),
    ] = None,
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="Retrieval mode: hybrid, vector, or fts"),
    ] = "hybrid",
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum number of context chunks"),
    ] = 10,
    doc_id: Annotated[
        str | None,
        typer.Option("--doc", "-d", help="Scope to a document (UUID or @citekey)"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON (implies --no-stream)"),
    ] = False,
    no_stream: Annotated[
        bool,
        typer.Option("--no-stream", help="Disable streaming (wait for full answer)"),
    ] = False,
) -> None:
    """Ask a question and get a RAG-generated answer from your library.

    Retrieves relevant document chunks and generates an answer with source
    citations. By default, the answer streams token-by-token.

    Examples:

        # Basic question
        local-library ask "What is attention in transformers?"

        # Use a specific model
        local-library ask "Summarize the findings" --model anthropic/claude-3-haiku

        # Search only within a specific document
        local-library ask "What methods were used?" --doc @Smith2023

        # Get structured JSON output
        local-library ask "What are the key results?" --json
    """
    if not is_vec_available():
        if json_output:
            err_console.print(json.dumps({"error": "sqlite-vec extension not available"}))
        else:
            err_console.print("[red]error:[/red] sqlite-vec extension not available")
            err_console.print("[dim]Install sqlite-vec to enable ask features[/dim]")
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

    # JSON implies no-stream (must collect full response for structured output)
    if json_output:
        no_stream = True

    lib_kwargs: dict[str, Any] = {"embed_on_add": False}
    if model:
        lib_kwargs["rag_model"] = model

    try:
        with Library(**lib_kwargs) as lib:
            # Resolve document scope if provided
            doc_ids: list[UUID] | None = None
            if doc_id:
                doc = resolve_identifier(doc_id, lib)
                doc_ids = [doc.id]

            if no_stream:
                response = lib.query(
                    question, mode=mode, limit=limit, doc_ids=doc_ids,
                )
                if json_output:
                    _output_json(response)
                else:
                    _output_answer(response)
            else:
                _stream_answer(lib, question, mode=mode, limit=limit, doc_ids=doc_ids)

    except (LookupError, EmbeddingError, RAGError, LLMError) as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None
    except KeyboardInterrupt:
        err_console.print("\n[dim]interrupted[/dim]")
        raise typer.Exit(code=130) from None


def _stream_answer(
    lib: Library,
    question: str,
    mode: str,
    limit: int,
    doc_ids: list[UUID] | None,
) -> None:
    """Stream answer tokens with Rich Live display."""
    console.print("[dim]Searching...[/dim]")

    stream = lib.query_stream(question, mode=mode, limit=limit, doc_ids=doc_ids)

    accumulated = ""
    try:
        with Live(Text(""), console=console, refresh_per_second=10) as live:
            for token in stream:
                accumulated += token
                live.update(Text(accumulated))
    except KeyboardInterrupt:
        # Graceful Ctrl+C: show what we have so far
        if accumulated:
            console.print(Text(accumulated))
        err_console.print("\n[dim]interrupted[/dim]")
        raise typer.Exit(code=130) from None

    # Print final answer (Live clears on exit)
    console.print()
    console.print(accumulated)

    # Sources footer
    response = stream.to_response()
    _print_sources(response)


def _output_answer(response: RAGResponse) -> None:
    """Print non-streaming answer with sources footer."""
    console.print(response.answer)
    _print_sources(response)


def _print_sources(response: RAGResponse) -> None:
    """Print sources footer from RAGResponse."""
    if not response.context_chunks:
        return

    # Deduplicate by citekey (or doc_id if citekey is None), preserving order
    seen: dict[str, tuple[str | None, str | None]] = {}
    for chunk in response.context_chunks:
        # Use citekey as grouping key, fallback to doc_id string if None
        key = chunk.doc_citekey or str(chunk.chunk.doc_id)
        if key not in seen:
            seen[key] = (chunk.doc_citekey, chunk.doc_title)

    console.print()
    console.print("[bold]Sources:[/bold]")
    for citekey, title in seen.values():
        label = f"[@{citekey}]" if citekey else "[unknown source]"
        title_str = f'  "{title}"' if title else ""
        console.print(f"  {label}{title_str}")


def _output_json(response: RAGResponse) -> None:
    """Output RAGResponse as JSON."""
    # Aggregate sources: deduplicate by citekey (or doc_id if None), count chunks per source
    source_map: dict[str, dict[str, Any]] = {}
    for chunk in response.context_chunks:
        # Use citekey as grouping key, fallback to doc_id string if None
        key = chunk.doc_citekey or str(chunk.chunk.doc_id)
        if key not in source_map:
            source_map[key] = {
                "citekey": chunk.doc_citekey,
                "title": chunk.doc_title,
                "doc_id": str(chunk.chunk.doc_id),
                "chunks_used": 0,
            }
        source_map[key]["chunks_used"] += 1

    output = {
        "question": response.question,
        "answer": response.answer,
        "model": response.model,
        "retrieval_mode": response.retrieval_mode,
        "sources": list(source_map.values()),
    }
    console.print(json.dumps(output, indent=2))
