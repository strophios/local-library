"""Embed command - compute and store embeddings for documents."""

# pattern: Imperative Shell

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from local_library.cli.utils import resolve_identifier
from local_library.core import Library
from local_library.core.errors import EmbeddingError, LookupError
from local_library.core.models import EmbeddingStatus
from local_library.core.vec_extension import is_vec_available

console = Console()
err_console = Console(stderr=True)


def embed(
    identifier: Annotated[
        str | None,
        typer.Argument(help="Document ID (UUID or @citekey) to embed. Omit for --pending or --all."),
    ] = None,
    pending: Annotated[
        bool,
        typer.Option("--pending", "-p", help="Embed all documents with PENDING or STALE status"),
    ] = False,
    all_docs: Annotated[
        bool,
        typer.Option("--all", "-a", help="Re-embed all READY documents (use with --force)"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Re-embed even if embeddings already exist"),
    ] = False,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", "-b", help="Embedding batch size"),
    ] = 32,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be embedded without doing it"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
) -> None:
    """Compute and store embeddings for documents.

    Embeddings enable semantic search over document content. Each document's
    extracted text is split into chunks and converted to 768-dimensional
    vectors using nomic-embed-text-v1.5.

    Examples:

        # Embed a single document
        local-library embed abc123
        local-library embed @Smith2023

        # Embed all pending documents
        local-library embed --pending

        # Re-embed all documents
        local-library embed --all --force

        # Dry run to see what would be embedded
        local-library embed --pending --dry-run
    """
    # Check sqlite-vec availability
    if not is_vec_available():
        if json_output:
            err_console.print(json.dumps({"error": "sqlite-vec extension not available"}))
        else:
            err_console.print("[red]error:[/red] sqlite-vec extension not available")
            err_console.print("[dim]Install sqlite-vec to enable embedding features[/dim]")
        raise typer.Exit(code=1)

    # Validate arguments
    if identifier and (pending or all_docs):
        if json_output:
            err_console.print(json.dumps({"error": "cannot specify identifier with --pending or --all"}))
        else:
            err_console.print("[red]error:[/red] cannot specify identifier with --pending or --all")
        raise typer.Exit(code=1)

    if not identifier and not pending and not all_docs:
        if json_output:
            err_console.print(json.dumps({"error": "must specify identifier, --pending, or --all"}))
        else:
            err_console.print("[red]error:[/red] must specify identifier, --pending, or --all")
        raise typer.Exit(code=1)

    try:
        with Library(embedding_batch_size=batch_size, embed_on_add=False) as lib:
            if identifier:
                # Single document embedding
                _embed_single(lib, identifier, force, dry_run, json_output)
            else:
                # Batch embedding
                _embed_batch(lib, all_docs, force, dry_run, json_output)
    except LookupError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None
    except EmbeddingError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None


def _embed_single(
    lib: Library,
    identifier: str,
    force: bool,
    dry_run: bool,
    json_output: bool,
) -> None:
    """Embed a single document."""
    doc = resolve_identifier(lib, identifier)

    if dry_run:
        if json_output:
            console.print(json.dumps({
                "dry_run": True,
                "id": str(doc.id),
                "citekey": doc.citekey,
                "embedding_status": doc.embedding_status.value,
                "would_embed": force or doc.embedding_status != EmbeddingStatus.CURRENT,
            }))
        else:
            status = doc.embedding_status.value
            action = "would re-embed" if force else "would embed"
            if doc.embedding_status == EmbeddingStatus.CURRENT and not force:
                action = "already current, skipping"
            console.print(f"[dim]dry run:[/dim] {action}")
            console.print(f"  [dim]id:[/dim] {doc.id}")
            if doc.citekey:
                console.print(f"  [dim]citekey:[/dim] {doc.citekey}")
            console.print(f"  [dim]status:[/dim] {status}")
        return

    chunk_count = lib.embed(str(doc.id), force=force)

    if json_output:
        console.print(json.dumps({
            "id": str(doc.id),
            "citekey": doc.citekey,
            "chunks_embedded": chunk_count,
            "embedding_status": "current",
        }))
    else:
        if chunk_count > 0:
            console.print(f"[green]embedded[/green]: {doc.id}")
            console.print(f"  [dim]chunks:[/dim] {chunk_count}")
            if doc.citekey:
                console.print(f"  [dim]citekey:[/dim] {doc.citekey}")
        else:
            console.print(f"[yellow]no chunks[/yellow]: {doc.id}")
            console.print("  [dim]document may be empty or very short[/dim]")


def _embed_batch(
    lib: Library,
    all_docs: bool,
    force: bool,
    dry_run: bool,
    json_output: bool,
) -> None:
    """Embed multiple documents."""
    from local_library.core.models import DocumentStatus
    from local_library.core.storage import list_documents
    from local_library.embeddings.storage import get_documents_needing_embedding

    # Get documents to embed
    if all_docs and force:
        docs = list_documents(lib.conn, status=DocumentStatus.READY)
        doc_ids = [doc.id for doc in docs]
    else:
        doc_ids = get_documents_needing_embedding(lib.conn)

    if dry_run:
        if json_output:
            console.print(json.dumps({
                "dry_run": True,
                "documents_to_embed": len(doc_ids),
                "mode": "all" if all_docs else "pending",
            }))
        else:
            console.print(f"[dim]dry run:[/dim] would embed {len(doc_ids)} documents")
        return

    if not doc_ids:
        if json_output:
            console.print(json.dumps({"embedded": 0, "failed": 0, "chunks": 0}))
        else:
            console.print("[dim]no documents need embedding[/dim]")
        return

    # Embed with progress
    results = {"embedded": 0, "failed": 0, "chunks": 0}

    if json_output:
        # No progress bar for JSON output
        for doc_id in doc_ids:
            try:
                chunk_count = lib.embed(str(doc_id), force=force)
                results["embedded"] += 1
                results["chunks"] += chunk_count
            except Exception:
                results["failed"] += 1

        console.print(json.dumps(results))
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Embedding {len(doc_ids)} documents...", total=len(doc_ids))

            for i, doc_id in enumerate(doc_ids):
                try:
                    chunk_count = lib.embed(str(doc_id), force=force)
                    results["embedded"] += 1
                    results["chunks"] += chunk_count
                except Exception as e:
                    results["failed"] += 1

                progress.update(task, completed=i + 1)

        console.print(f"[green]embedded[/green]: {results['embedded']} documents ({results['chunks']} chunks)")
        if results["failed"] > 0:
            console.print(f"[yellow]failed[/yellow]: {results['failed']} documents")
