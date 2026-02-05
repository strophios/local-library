"""Add command - add documents to the library."""

# pattern: Imperative Shell

import json
import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from local_library.core import (
    AcquisitionError,
    ExtractionError,
    Library,
    MetadataError,
    QualityError,
)

console = Console()
err_console = Console(stderr=True)


def check_api_key_available(
    env_var: str,
    feature_name: str,
    json_output: bool,
) -> bool:
    """Check if an API key environment variable is available.

    Args:
        env_var: Name of the environment variable to check
        feature_name: Human-readable name of the feature (for warning message)
        json_output: Whether to format warning as JSON

    Returns:
        True if the key is available, False otherwise (with warning output)
    """
    if os.environ.get(env_var):
        return True

    if json_output:
        err_console.print(
            json.dumps(
                {
                    "warning": f"{env_var} not set, {feature_name} disabled",
                }
            )
        )
    else:
        err_console.print(f"[yellow]warning:[/yellow] {env_var} not set, {feature_name} disabled")
    return False


def add(
    path: Annotated[Path, typer.Argument(help="Path to the document file")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Create failed record for inaccessible files"),
    ] = False,
    metadata_path: Annotated[
        Path | None,
        typer.Option(
            "--metadata",
            "-m",
            help="Path to CSL-JSON metadata file",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    llm: Annotated[
        bool,
        typer.Option(
            "--llm",
            help="Use LLM fallback for low-confidence metadata extraction",
        ),
    ] = False,
    llm_model: Annotated[
        str,
        typer.Option(
            "--llm-model",
            help="LLM model for fallback (default: gemini-2.0-flash)",
        ),
    ] = "gemini/gemini-2.0-flash",
    llm_extract: Annotated[
        bool,
        typer.Option(
            "--llm-extract",
            help="Enable Marker LLM extraction (tables, math, images). Requires GEMINI_API_KEY.",
        ),
    ] = False,
    skip_embed: Annotated[
        bool,
        typer.Option(
            "--skip-embed",
            help="Skip automatic embedding after extraction",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
) -> None:
    """Add a document to the library.

    Copies the file to managed storage, extracts text content, and creates
    a database record. Duplicates are detected by path and content hash.

    Optionally provide CSL-JSON metadata with --metadata for bibliographic
    information like title, authors, and publication date.

    By default, documents are automatically embedded after extraction for
    semantic search. Use --skip-embed to disable this (useful for batch
    operations where you'll run `local-library embed --pending` afterwards).
    """
    # Load metadata if provided
    metadata = None
    if metadata_path:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            if json_output:
                err_console.print(json.dumps({"error": f"invalid JSON in metadata file: {e}"}))
            else:
                err_console.print(f"[red]error:[/red] invalid JSON in metadata file: {e}")
            raise typer.Exit(code=1) from None

    # Early validation of API keys for LLM features
    effective_llm = llm
    effective_llm_extract = llm_extract

    if llm or llm_extract:
        if not check_api_key_available("GEMINI_API_KEY", "LLM features", json_output):
            effective_llm = False
            effective_llm_extract = False

    try:
        with Library(
            text_extraction_llm_enabled=effective_llm,
            text_extraction_llm_model=llm_model,
            pdf_llm_enabled=effective_llm_extract,
            embed_on_add=not skip_embed,
        ) as lib:
            result = lib.add(str(path), force=force, metadata=metadata)
    except AcquisitionError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None
    except MetadataError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] metadata validation failed: {e.message}")
        raise typer.Exit(code=1) from None
    except (ExtractionError, QualityError) as e:
        # Document was created but extraction failed
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[yellow]warning:[/yellow] extraction failed: {e.message}")
            err_console.print("[dim]Document created with status 'failed'[/dim]")
        raise typer.Exit(code=2) from None

    doc = result.document

    if json_output:
        output = {
            "id": str(doc.id),
            "status": doc.status.value,
            "original_path": doc.original_path,
            "storage_path": doc.storage_path,
            "content_hash": doc.content_hash,
            "citekey": doc.citekey,
            "title": doc.title,
            "authors": doc.authors,
            "issued_date": doc.issued_date,
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
            if doc.citekey:
                console.print(f"  [dim]citekey:[/dim] {doc.citekey}")
            if doc.title:
                console.print(f"  [dim]title:[/dim] {doc.title}")
            console.print(f"  [dim]path:[/dim] {doc.storage_path}")
