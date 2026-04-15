"""Zotero commands - import from and interact with Zotero library."""

# pattern: Imperative Shell

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from local_library.core import (
    AcquisitionError,
    ExtractionError,
    Library,
    MetadataError,
    QualityError,
)
from local_library.core.errors import ZoteroError
from local_library.ingestion.zotero import ZoteroReader

# Create Zotero command group
app = typer.Typer(
    name="zotero",
    help="Commands for interacting with Zotero library.",
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)

# Batch size for Library recreation during import.
# Defensive measure against resource accumulation in Marker's native code
# (PyTorch, multiprocessing). After this many extractions, the Library is
# closed and recreated to release resources. Set conservatively high since
# the primary crash issue (Rich + Marker conflict) is handled separately.
EXTRACTION_BATCH_SIZE = 50


def _make_console_progress_callback(
    target_console: Console,
) -> Callable[[str, float, dict[str, Any]], None]:
    """Create a progress callback that prints to a Rich console.

    Used when the Rich progress bar is stopped during extraction.
    Prints pre-check, heartbeat, completion, and fallback events.

    Args:
        target_console: Rich Console instance for output.

    Returns:
        Progress callback function.
    """

    def callback(message: str, elapsed: float, context: dict[str, Any]) -> None:
        event = context.get("event", "")
        file_name = context.get("file_name", "")

        if event == "precheck_complete":
            pages = context.get("page_count", "?")
            has_text = context.get("has_text", False)
            timeout = context.get("timeout", "?")
            text_flag = "text" if has_text else "image-only"
            target_console.print(
                f"  [dim]pre-check: {pages} pages, {text_flag}, timeout {timeout}s[/dim]"
            )
        elif event == "extraction_progress":
            device = context.get("device", "?")
            mins, secs = divmod(int(elapsed), 60)
            target_console.print(
                f"  [dim]extracting {file_name} on {device}... {mins}m {secs:02d}s elapsed[/dim]"
            )
        elif event == "extraction_complete":
            duration = context.get("duration", elapsed)
            mins, secs = divmod(int(duration), 60)
            target_console.print(f"  [dim]extracted in {mins}m {secs:02d}s[/dim]")
        elif event == "extraction_fallback":
            target_console.print(f"  [yellow]using pdftext fallback for {file_name}[/yellow]")

    return callback


def get_default_zotero_dir() -> Path | None:
    """Get the default Zotero data directory based on environment or platform.

    Checks ZOTERO_DIR environment variable first, then falls back to
    platform-specific default locations.

    Returns:
        Path to Zotero directory if found, None otherwise
    """
    # Check environment variable first
    if env_dir := os.environ.get("ZOTERO_DIR"):
        return Path(env_dir).expanduser()

    # Platform-specific defaults
    import sys

    if sys.platform == "darwin":
        # macOS: ~/Zotero is the default for Zotero 7
        default = Path.home() / "Zotero"
        if default.exists():
            return default
    elif sys.platform.startswith("linux"):
        # Linux: ~/Zotero
        default = Path.home() / "Zotero"
        if default.exists():
            return default
    elif sys.platform == "win32":
        # Windows: typically in user profile
        default = Path.home() / "Zotero"
        if default.exists():
            return default

    return None


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


@app.command(name="import")
def import_from_zotero(
    citekeys_arg: Annotated[
        list[str] | None,
        typer.Argument(
            help="Specific citekeys to import (e.g., Smith2023). "
            "If omitted, imports all matching items.",
        ),
    ] = None,
    zotero_dir: Annotated[
        Path | None,
        typer.Option(
            "--zotero-dir",
            "-z",
            help="Path to Zotero data directory. Defaults to ~/Zotero or ZOTERO_DIR env var.",
            envvar="ZOTERO_DIR",
        ),
    ] = None,
    library_json: Annotated[
        Path | None,
        typer.Option(
            "--library-json",
            help="Path to Better BibTeX library.json export.",
        ),
    ] = None,
    library_id: Annotated[
        int | None,
        typer.Option(
            "--library",
            "-l",
            help="Library ID to import from (1 = personal). Defaults to personal library.",
        ),
    ] = None,
    all_libraries: Annotated[
        bool,
        typer.Option(
            "--all-libraries",
            help="Import from all libraries (personal and groups). Overrides --library.",
        ),
    ] = False,
    collection: Annotated[
        str | None,
        typer.Option(
            "--collection",
            "-c",
            help="Import only items from this collection (case-sensitive name).",
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            "-n",
            help="Maximum number of items to import.",
            min=1,
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview what would be imported without making changes.",
        ),
    ] = False,
    continue_on_error: Annotated[
        bool,
        typer.Option(
            "--continue-on-error",
            help="Continue importing after individual item failures.",
        ),
    ] = False,
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
            help="Skip automatic embedding (run `local-library embed --pending` afterwards)",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output results as JSON."),
    ] = False,
) -> None:
    """Import documents from Zotero library.

    Iterates through Zotero items, finds PDF attachments, and imports them
    with their CSL-JSON metadata. Existing documents (by citekey or content
    hash) are automatically skipped.

    Pass specific citekeys as arguments to import individual items:

        local-library zotero import Smith2023 Jones2022

    Omit citekeys to import all matching items (filtered by --library/--collection).

    Use --skip-embed for large imports and run `local-library embed --pending`
    afterwards for batch embedding.
    """
    # Resolve Zotero directory
    effective_zotero_dir = zotero_dir or get_default_zotero_dir()
    if effective_zotero_dir is None:
        if json_output:
            err_console.print(
                json.dumps(
                    {"error": "Zotero directory not found. Use --zotero-dir or set ZOTERO_DIR."}
                )
            )
        else:
            err_console.print(
                "[red]error:[/red] Zotero directory not found. "
                "Use --zotero-dir or set ZOTERO_DIR environment variable."
            )
        raise typer.Exit(code=1)

    if not effective_zotero_dir.exists():
        if json_output:
            err_console.print(
                json.dumps({"error": f"Zotero directory not found: {effective_zotero_dir}"})
            )
        else:
            err_console.print(
                f"[red]error:[/red] Zotero directory not found: {effective_zotero_dir}"
            )
        raise typer.Exit(code=1)

    # Early validation of API key for LLM features
    effective_llm_extract = llm_extract
    if llm_extract:
        if not check_api_key_available("GEMINI_API_KEY", "LLM extraction", json_output):
            effective_llm_extract = False

    # Open Zotero reader
    try:
        reader = ZoteroReader(
            effective_zotero_dir,
            library_json_path=library_json,
        )
    except ZoteroError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None

    # Determine which library to import from
    # Default to personal library (ID=1) unless --all-libraries is set
    effective_library_id: int | None = None
    if not all_libraries:
        effective_library_id = library_id if library_id is not None else 1

    # Show which library we're importing from
    if not json_output and effective_library_id is not None:
        if effective_library_id == 1:
            console.print("[dim]Importing from: My Library[/dim]")
        else:
            console.print(f"[dim]Importing from: Library {effective_library_id}[/dim]")

    # Get citekeys to process
    try:
        if citekeys_arg:
            # Explicit citekeys provided — strip leading @ if present
            citekeys = [ck.lstrip("@") for ck in citekeys_arg]
        elif collection:
            citekeys = list(reader.list_citekeys_in_collection(collection))
            # Filter by library if specified
            if effective_library_id is not None:
                library_citekeys = set(reader.list_citekeys_in_library(effective_library_id))
                citekeys = [ck for ck in citekeys if ck in library_citekeys]
        elif effective_library_id is not None:
            citekeys = list(reader.list_citekeys_in_library(effective_library_id))
        else:
            citekeys = list(reader.list_citekeys())
    except ZoteroError as e:
        reader.close()
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None

    # Apply limit
    if limit:
        citekeys = citekeys[:limit]

    if not citekeys:
        reader.close()
        if json_output:
            console.print(json.dumps({"message": "No items to import", "total": 0}))
        else:
            console.print("[dim]No items to import[/dim]")
        return

    # Dry run: just show what would be imported
    if dry_run:
        reader.close()
        _handle_dry_run(
            reader, citekeys, collection, json_output, effective_zotero_dir, library_json
        )
        return

    # Import items
    _import_items(
        reader=reader,
        citekeys=citekeys,
        continue_on_error=continue_on_error,
        llm_extract=effective_llm_extract,
        skip_embed=skip_embed,
        json_output=json_output,
    )


def _handle_dry_run(
    reader: ZoteroReader,
    citekeys: list[str],
    collection: str | None,
    json_output: bool,
    zotero_dir: Path,
    library_json: Path | None,
) -> None:
    """Handle dry-run mode: show what would be imported."""
    # Re-open reader for dry-run analysis
    try:
        with ZoteroReader(zotero_dir, library_json_path=library_json) as reader:
            with Library() as lib:
                existing_citekeys = set(lib.get_all_citekeys())

            would_import = []
            would_skip = []
            no_pdf = []

            for citekey in citekeys:
                # Check if already exists
                if citekey in existing_citekeys:
                    would_skip.append(citekey)
                    continue

                # Check for PDF
                try:
                    item = reader.get_item(citekey)
                    pdfs = item.pdf_attachments()
                    if not pdfs:
                        no_pdf.append(citekey)
                    else:
                        would_import.append(citekey)
                except ZoteroError:
                    no_pdf.append(citekey)

            if json_output:
                console.print(
                    json.dumps(
                        {
                            "dry_run": True,
                            "collection": collection,
                            "total": len(citekeys),
                            "would_import": len(would_import),
                            "would_skip_existing": len(would_skip),
                            "no_pdf": len(no_pdf),
                            "items": {
                                "import": would_import,
                                "skip": would_skip,
                                "no_pdf": no_pdf,
                            },
                        },
                        indent=2,
                    )
                )
            else:
                console.print("[bold]Dry run summary:[/bold]")
                console.print(f"  Total items: {len(citekeys)}")
                console.print(f"  [green]Would import:[/green] {len(would_import)}")
                console.print(f"  [yellow]Already exists:[/yellow] {len(would_skip)}")
                console.print(f"  [dim]No PDF attachment:[/dim] {len(no_pdf)}")

                if would_import and len(would_import) <= 20:
                    console.print("\n[bold]Items to import:[/bold]")
                    for ck in would_import:
                        console.print(f"  @{ck}")
    except ZoteroError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None


def _import_items(
    reader: ZoteroReader,
    citekeys: list[str],
    continue_on_error: bool,
    llm_extract: bool,
    skip_embed: bool,
    json_output: bool,
) -> None:
    """Import items from Zotero with progress tracking.

    Uses batched Library creation to prevent memory accumulation in Marker's
    native code. After EXTRACTION_BATCH_SIZE extractions, the Library is
    closed and recreated to release PyTorch/multiprocessing resources.
    """
    stats = {
        "added": 0,
        "skipped_existing": 0,
        "skipped_duplicate": 0,
        "skipped_no_pdf": 0,
        "failed": 0,
    }
    failures: list[dict] = []

    try:
        # Get existing citekeys (quick operation, no extraction)
        with Library() as lib:
            existing_citekeys = set(lib.get_all_citekeys())

        # Progress display for non-JSON mode
        if json_output:
            _import_items_json(
                reader,
                citekeys,
                existing_citekeys,
                llm_extract,
                skip_embed,
                continue_on_error,
                stats,
                failures,
            )
        else:
            _import_items_rich(
                reader,
                citekeys,
                existing_citekeys,
                llm_extract,
                skip_embed,
                continue_on_error,
                stats,
                failures,
            )
    finally:
        reader.close()

    # Output summary
    if json_output:
        output = {
            "summary": stats,
            "total": sum(stats.values()),
        }
        if failures:
            output["failures"] = failures
        console.print(json.dumps(output, indent=2))
    else:
        console.print()
        console.print("[bold]Import complete:[/bold]")
        console.print(f"  [green]Added:[/green] {stats['added']}")
        if stats["skipped_existing"]:
            console.print(f"  [yellow]Skipped (exists):[/yellow] {stats['skipped_existing']}")
        if stats["skipped_duplicate"]:
            console.print(f"  [yellow]Skipped (duplicate):[/yellow] {stats['skipped_duplicate']}")
        if stats["skipped_no_pdf"]:
            console.print(f"  [dim]Skipped (no PDF):[/dim] {stats['skipped_no_pdf']}")
        if stats["failed"]:
            console.print(f"  [red]Failed:[/red] {stats['failed']}")
            for f in failures[:5]:
                console.print(f"    @{f['citekey']}: {f['error']}")
            if len(failures) > 5:
                console.print(f"    ... and {len(failures) - 5} more")


def _import_items_rich(
    reader: ZoteroReader,
    citekeys: list[str],
    existing_citekeys: set[str],
    llm_extract: bool,
    skip_embed: bool,
    continue_on_error: bool,
    stats: dict,
    failures: list,
) -> None:
    """Import items with Rich progress bar.

    Creates a new Library every EXTRACTION_BATCH_SIZE items to prevent
    memory accumulation in Marker's native code.

    IMPORTANT: Rich's progress bar must be stopped during PDF extraction.
    Marker uses multiprocessing which conflicts with Rich's terminal state
    on macOS, causing Objective-C runtime errors ("bad weak table") or
    heap corruption. We stop the progress bar before extraction and
    restart it after.
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Importing...", total=len(citekeys))

        lib: Library | None = None
        items_since_restart = 0

        try:
            for citekey in citekeys:
                progress.update(task, description=f"@{citekey[:20]}...")

                # Create or recreate Library as needed
                if lib is None or items_since_restart >= EXTRACTION_BATCH_SIZE:
                    if lib is not None:
                        lib.close()
                    progress_cb = _make_console_progress_callback(console)
                    lib = Library(
                        pdf_llm_enabled=llm_extract,
                        embed_on_add=not skip_embed,
                        progress_callback=progress_cb,
                    )
                    items_since_restart = 0

                # Check if this item will need extraction (not a skip)
                will_extract = citekey not in existing_citekeys and _item_has_pdf(reader, citekey)

                # Stop progress bar during extraction to avoid conflict with
                # Marker's multiprocessing on macOS
                if will_extract:
                    progress.stop()

                result = _process_single_item(
                    reader, citekey, existing_citekeys, lib, continue_on_error, stats, failures
                )

                # Restart progress bar after extraction
                if will_extract:
                    progress.start()

                # Only count items that actually triggered extraction
                if result == "extracted":
                    items_since_restart += 1

                if result == "abort":
                    break

                progress.advance(task)
        finally:
            if lib is not None:
                lib.close()


def _import_items_json(
    reader: ZoteroReader,
    citekeys: list[str],
    existing_citekeys: set[str],
    llm_extract: bool,
    skip_embed: bool,
    continue_on_error: bool,
    stats: dict,
    failures: list,
) -> None:
    """Import items in JSON mode (no progress display).

    Creates a new Library every EXTRACTION_BATCH_SIZE items to prevent
    memory accumulation in Marker's native code.
    """
    lib: Library | None = None
    items_since_restart = 0

    try:
        for citekey in citekeys:
            # Create or recreate Library as needed
            if lib is None or items_since_restart >= EXTRACTION_BATCH_SIZE:
                if lib is not None:
                    lib.close()
                lib = Library(pdf_llm_enabled=llm_extract, embed_on_add=not skip_embed)
                items_since_restart = 0

            result = _process_single_item(
                reader, citekey, existing_citekeys, lib, continue_on_error, stats, failures
            )

            # Only count items that actually triggered extraction
            if result == "extracted":
                items_since_restart += 1

            if result == "abort":
                break
    finally:
        if lib is not None:
            lib.close()


def _item_has_pdf(reader: ZoteroReader, citekey: str) -> bool:
    """Check if a Zotero item has a PDF attachment that exists.

    Used to determine if extraction will be needed (for progress bar handling).
    """
    try:
        item = reader.get_item(citekey)
        pdfs = item.pdf_attachments()
        return bool(pdfs) and pdfs[0].path.exists()
    except ZoteroError:
        return False


def _process_single_item(
    reader: ZoteroReader,
    citekey: str,
    existing_citekeys: set[str],
    lib: Library,
    continue_on_error: bool,
    stats: dict,
    failures: list,
) -> str:
    """Process a single Zotero item for import.

    Returns:
        "continue" - item processed without extraction (skipped or duplicate)
        "extracted" - PDF extraction was performed (counts toward batch limit)
        "abort" - error occurred and should stop processing
    """
    # Skip if citekey already exists
    if citekey in existing_citekeys:
        stats["skipped_existing"] += 1
        return "continue"

    # Get item from Zotero
    try:
        item = reader.get_item(citekey)
    except ZoteroError as e:
        stats["failed"] += 1
        failures.append({"citekey": citekey, "error": e.message})
        if not continue_on_error:
            return "abort"
        return "continue"

    # Find first PDF attachment
    pdfs = item.pdf_attachments()
    if not pdfs:
        stats["skipped_no_pdf"] += 1
        return "continue"

    pdf = pdfs[0]

    # Check if PDF exists
    if not pdf.path.exists():
        stats["failed"] += 1
        failures.append({"citekey": citekey, "error": f"PDF not found: {pdf.path}"})
        if not continue_on_error:
            return "abort"
        return "continue"

    # Import the PDF with metadata, preserving Zotero's citekey
    try:
        result = lib.add(str(pdf.path), metadata=item.csl_json, citekey=citekey)

        if result.is_duplicate:
            stats["skipped_duplicate"] += 1
            return "continue"  # No extraction happened
        else:
            stats["added"] += 1
            existing_citekeys.add(citekey)  # Track newly added
            return "extracted"  # Extraction was performed

    except (AcquisitionError, MetadataError) as e:
        stats["failed"] += 1
        failures.append({"citekey": citekey, "error": e.message})
        if not continue_on_error:
            return "abort"
        return "continue"
    except (ExtractionError, QualityError) as e:
        # Document was created but extraction failed - still counts as extraction attempt
        stats["failed"] += 1
        failures.append({"citekey": citekey, "error": f"extraction failed: {e.message}"})
        if not continue_on_error:
            return "abort"
        return "extracted"  # Extraction was attempted (counts toward batch limit)


@app.command(name="libraries")
def list_libraries(
    zotero_dir: Annotated[
        Path | None,
        typer.Option(
            "--zotero-dir",
            "-z",
            help="Path to Zotero data directory.",
            envvar="ZOTERO_DIR",
        ),
    ] = None,
    library_json: Annotated[
        Path | None,
        typer.Option(
            "--library-json",
            help="Path to Better BibTeX library.json export.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON."),
    ] = False,
) -> None:
    """List all Zotero libraries (personal and groups)."""
    # Resolve Zotero directory
    effective_zotero_dir = zotero_dir or get_default_zotero_dir()
    if effective_zotero_dir is None:
        if json_output:
            err_console.print(
                json.dumps(
                    {"error": "Zotero directory not found. Use --zotero-dir or set ZOTERO_DIR."}
                )
            )
        else:
            err_console.print(
                "[red]error:[/red] Zotero directory not found. "
                "Use --zotero-dir or set ZOTERO_DIR environment variable."
            )
        raise typer.Exit(code=1)

    try:
        with ZoteroReader(effective_zotero_dir, library_json_path=library_json) as reader:
            libraries = reader.list_libraries()

            if json_output:
                output = [
                    {
                        "library_id": lib.library_id,
                        "type": lib.library_type,
                        "name": lib.name,
                        "editable": lib.editable,
                    }
                    for lib in libraries
                ]
                console.print(json.dumps(output, indent=2))
            else:
                if not libraries:
                    console.print("[dim]No libraries found[/dim]")
                    return

                console.print(f"[bold]Libraries ({len(libraries)}):[/bold]")
                for lib in libraries:
                    if lib.is_personal():
                        type_indicator = "[green]personal[/green]"
                    else:
                        type_indicator = "[blue]group[/blue]"
                    console.print(f"  {lib.library_id}: {lib.name} ({type_indicator})")
    except ZoteroError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None


@app.command(name="collections")
def list_collections(
    zotero_dir: Annotated[
        Path | None,
        typer.Option(
            "--zotero-dir",
            "-z",
            help="Path to Zotero data directory.",
            envvar="ZOTERO_DIR",
        ),
    ] = None,
    library_json: Annotated[
        Path | None,
        typer.Option(
            "--library-json",
            help="Path to Better BibTeX library.json export.",
        ),
    ] = None,
    library_id: Annotated[
        int | None,
        typer.Option(
            "--library",
            "-l",
            help="Filter to collections in this library (1 = personal). Defaults to personal.",
        ),
    ] = None,
    all_libraries: Annotated[
        bool,
        typer.Option(
            "--all-libraries",
            help="Show collections from all libraries.",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON."),
    ] = False,
) -> None:
    """List collections in the Zotero library."""
    # Resolve Zotero directory
    effective_zotero_dir = zotero_dir or get_default_zotero_dir()
    if effective_zotero_dir is None:
        if json_output:
            err_console.print(
                json.dumps(
                    {"error": "Zotero directory not found. Use --zotero-dir or set ZOTERO_DIR."}
                )
            )
        else:
            err_console.print(
                "[red]error:[/red] Zotero directory not found. "
                "Use --zotero-dir or set ZOTERO_DIR environment variable."
            )
        raise typer.Exit(code=1)

    # Determine library filter
    effective_library_id: int | None = None
    if not all_libraries:
        effective_library_id = library_id if library_id is not None else 1

    try:
        with ZoteroReader(effective_zotero_dir, library_json_path=library_json) as reader:
            collections = reader.list_collections(library_id=effective_library_id)

            if json_output:
                output = [
                    {
                        "name": c.name,
                        "key": c.key,
                        "library_id": c.library_id,
                        "top_level": c.is_top_level(),
                    }
                    for c in collections
                ]
                console.print(json.dumps(output, indent=2))
            else:
                if not collections:
                    console.print("[dim]No collections found[/dim]")
                    return

                lib_note = "" if all_libraries else " (personal library)"
                console.print(f"[bold]Collections ({len(collections)}){lib_note}:[/bold]")
                for c in collections:
                    prefix = "  " if c.is_top_level() else "    "
                    console.print(f"{prefix}{c.name}")
    except ZoteroError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None
