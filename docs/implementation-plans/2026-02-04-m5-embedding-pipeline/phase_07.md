## Phase 7: CLI Command

**Goal:** `local-library embed` command and --skip-embed flags.

This phase adds the CLI interface for embedding operations: an `embed` command for manual embedding/re-embedding, and `--skip-embed` flags on `add` and `zotero import` to disable automatic embedding.

---

<!-- START_TASK_1 -->
### Task 1: Create embed CLI command

**Files:**
- Create: `src/local_library/cli/embed.py`

**Step 1: Create the embed command module**

Create `src/local_library/cli/embed.py`:

```python
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
```

**Step 2: Verify the module imports**

Run: `uv run python -c "from local_library.cli.embed import embed; print('embed command imported')"`
Expected: `embed command imported`

**Step 3: Commit**

```bash
git add src/local_library/cli/embed.py
git commit -m "feat(cli): add embed command for manual embedding operations"
```
<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Register embed command in main.py

**Files:**
- Modify: `src/local_library/cli/main.py`

**Step 1: Add import for embed command**

After line 14 (`from local_library.cli import zotero as zotero_cmd`), add:

```python
from local_library.cli import embed as embed_cmd
```

**Step 2: Register the embed command**

After line 30 (`app.command(name="review")(review_cmd.review)`), add:

```python
app.command(name="embed")(embed_cmd.embed)
```

**Step 3: Verify the command is registered**

Run: `uv run local-library --help`
Expected: Output includes `embed` command in the list

**Step 4: Commit**

```bash
git add src/local_library/cli/main.py
git commit -m "feat(cli): register embed command in main CLI"
```
<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Add --skip-embed flag to add command

**Files:**
- Modify: `src/local_library/cli/add.py`

**Step 1: Add skip_embed parameter**

After line 93 (the `llm_extract` option), add:

```python
    skip_embed: Annotated[
        bool,
        typer.Option(
            "--skip-embed",
            help="Skip automatic embedding after extraction",
        ),
    ] = False,
```

**Step 2: Pass embed_on_add to Library**

Update the Library instantiation (around line 129) to include embed_on_add:

```python
        with Library(
            text_extraction_llm_enabled=effective_llm,
            text_extraction_llm_model=llm_model,
            pdf_llm_enabled=effective_llm_extract,
            embed_on_add=not skip_embed,
        ) as lib:
```

**Step 3: Update docstring**

Add to the docstring:

```
    By default, documents are automatically embedded after extraction for
    semantic search. Use --skip-embed to disable this (useful for batch
    operations where you'll run `local-library embed --pending` afterwards).
```

**Step 4: Verify the flag works**

Run: `uv run local-library add --help`
Expected: Output includes `--skip-embed` option

**Step 5: Commit**

```bash
git add src/local_library/cli/add.py
git commit -m "feat(cli): add --skip-embed flag to add command"
```
<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Add --skip-embed flag to zotero import command

**Files:**
- Modify: `src/local_library/cli/zotero.py`

First, let me check the current zotero.py structure:

**Step 1: Add skip_embed parameter to import_items function**

Find the `import_items` function and add the parameter after the existing parameters:

```python
    skip_embed: Annotated[
        bool,
        typer.Option(
            "--skip-embed",
            help="Skip automatic embedding (run `local-library embed --pending` afterwards)",
        ),
    ] = False,
```

**Step 2: Pass embed_on_add to Library**

Find where Library is instantiated in the import_items function and add `embed_on_add=not skip_embed`.

**Step 3: Update docstring**

Add to the docstring:

```
    Use --skip-embed for large imports and run `local-library embed --pending`
    afterwards for batch embedding.
```

**Step 4: Verify the flag works**

Run: `uv run local-library zotero import --help`
Expected: Output includes `--skip-embed` option

**Step 5: Commit**

```bash
git add src/local_library/cli/zotero.py
git commit -m "feat(cli): add --skip-embed flag to zotero import command"
```
<!-- END_TASK_4 -->

---

<!-- START_TASK_5 -->
### Task 5: Add CLI tests for embed command

**Files:**
- Create: `tests/unit/test_cli_embed.py`

**Step 1: Create test file**

Create `tests/unit/test_cli_embed.py`:

```python
"""Unit tests for embed CLI command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core.vec_extension import is_vec_available

runner = CliRunner()


class TestEmbedCommandHelp:
    """Tests for embed command help and arguments."""

    def test_embed_help(self) -> None:
        """embed --help should show usage information."""
        result = runner.invoke(app, ["embed", "--help"])

        assert result.exit_code == 0
        assert "Compute and store embeddings" in result.output
        assert "--pending" in result.output
        assert "--all" in result.output
        assert "--force" in result.output
        assert "--dry-run" in result.output

    def test_embed_no_args_fails(self) -> None:
        """embed without args should fail with helpful error."""
        with patch("local_library.cli.embed.is_vec_available", return_value=True):
            result = runner.invoke(app, ["embed"])

        assert result.exit_code == 1
        assert "must specify identifier, --pending, or --all" in result.output

    def test_embed_identifier_with_pending_fails(self) -> None:
        """embed with both identifier and --pending should fail."""
        with patch("local_library.cli.embed.is_vec_available", return_value=True):
            result = runner.invoke(app, ["embed", "abc123", "--pending"])

        assert result.exit_code == 1
        assert "cannot specify identifier with --pending or --all" in result.output


@pytest.mark.skipif(not is_vec_available(), reason="sqlite-vec not available")
class TestEmbedCommandExecution:
    """Tests for embed command execution."""

    def test_embed_single_document_dry_run(self, temp_dir: Path) -> None:
        """embed --dry-run should show what would be embedded."""
        from local_library.core.library import Library
        from local_library.core.models import DocumentStatus
        from local_library.core.storage import create_document, update_document_status

        # Set up a document
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            embed_on_add=False,
        ) as lib:
            doc = create_document(
                lib.conn, "/test.pdf", "hash123", str(temp_dir / "storage/hash123.pdf")
            )
            extracted = temp_dir / "extracted/hash123.md"
            extracted.parent.mkdir(parents=True, exist_ok=True)
            extracted.write_text("# Test")
            update_document_status(
                lib.conn, doc.id, DocumentStatus.READY, extracted_path=str(extracted)
            )
            doc_id = str(doc.id)

        # Run with mocked Library pointing to same db
        with patch("local_library.cli.embed.Library") as MockLibrary:
            mock_lib = MagicMock()
            mock_lib.__enter__ = MagicMock(return_value=mock_lib)
            mock_lib.__exit__ = MagicMock(return_value=False)
            mock_lib.get.return_value = MagicMock(
                id=doc_id,
                citekey=None,
                embedding_status=MagicMock(value="pending"),
            )
            MockLibrary.return_value = mock_lib

            result = runner.invoke(app, ["embed", doc_id[:8], "--dry-run"])

        assert result.exit_code == 0
        assert "dry run" in result.output

    def test_embed_pending_dry_run(self) -> None:
        """embed --pending --dry-run should show count."""
        with patch("local_library.cli.embed.Library") as MockLibrary:
            mock_lib = MagicMock()
            mock_lib.__enter__ = MagicMock(return_value=mock_lib)
            mock_lib.__exit__ = MagicMock(return_value=False)
            mock_lib.conn = MagicMock()
            MockLibrary.return_value = mock_lib

            with patch(
                "local_library.cli.embed.get_documents_needing_embedding",
                return_value=[],
            ):
                result = runner.invoke(app, ["embed", "--pending", "--dry-run"])

        assert result.exit_code == 0
        assert "would embed 0 documents" in result.output


class TestEmbedVecUnavailable:
    """Tests for when sqlite-vec is not available."""

    def test_embed_without_vec_fails(self) -> None:
        """embed should fail gracefully when sqlite-vec unavailable."""
        with patch("local_library.cli.embed.is_vec_available", return_value=False):
            result = runner.invoke(app, ["embed", "--pending"])

        assert result.exit_code == 1
        assert "sqlite-vec extension not available" in result.output


class TestAddSkipEmbed:
    """Tests for --skip-embed flag on add command."""

    def test_add_has_skip_embed_flag(self) -> None:
        """add --help should show --skip-embed option."""
        result = runner.invoke(app, ["add", "--help"])

        assert result.exit_code == 0
        assert "--skip-embed" in result.output


class TestZoteroImportSkipEmbed:
    """Tests for --skip-embed flag on zotero import command."""

    def test_zotero_import_has_skip_embed_flag(self) -> None:
        """zotero import --help should show --skip-embed option."""
        result = runner.invoke(app, ["zotero", "import", "--help"])

        assert result.exit_code == 0
        assert "--skip-embed" in result.output
```

**Step 2: Run the tests**

Run: `uv run pytest tests/unit/test_cli_embed.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_cli_embed.py
git commit -m "test: add CLI tests for embed command and --skip-embed flags"
```
<!-- END_TASK_5 -->

---

<!-- START_TASK_6 -->
### Task 6: Update cli/CLAUDE.md with embed command

**Files:**
- Modify: `src/local_library/cli/CLAUDE.md`

**Step 1: Update Exposes section**

Add to "Exposes": `embed command`

**Step 2: Update Guarantees section**

Add:
- `embed command requires sqlite-vec; fails gracefully with helpful error if unavailable`
- `--skip-embed flag available on add and zotero import for batch workflows`

**Step 3: Update Key Files section**

Add:
- `embed.py` - Embed command with --pending, --all, --force, --dry-run options

**Step 4: Update Key Decisions section**

Add:
- `**Embedding CLI**: embed command supports single doc (identifier), batch (--pending), and full re-embed (--all --force); graceful failure when sqlite-vec unavailable`
- `**Skip embed flags**: --skip-embed on add/import enables two-phase workflow: extract all → embed all`

**Step 5: Update Last verified date**

Change to: `Last verified: 2026-02-04`

**Step 6: Commit**

```bash
git add src/local_library/cli/CLAUDE.md
git commit -m "docs: update cli/CLAUDE.md with embed command documentation"
```
<!-- END_TASK_6 -->

---

## Phase 7 Verification

After completing all tasks, verify the phase is complete:

**Run all Phase 7 tests:**
```bash
uv run pytest tests/unit/test_cli_embed.py -v
```

**Verify CLI commands work:**
```bash
# Check embed command help
uv run local-library embed --help

# Check add has --skip-embed
uv run local-library add --help | grep skip-embed

# Check zotero import has --skip-embed
uv run local-library zotero import --help | grep skip-embed
```

**Test dry-run (doesn't require documents):**
```bash
uv run local-library embed --pending --dry-run
```

**Done when:**
- `local-library embed` command works with identifier, --pending, --all options
- `local-library add --skip-embed` disables automatic embedding
- `local-library zotero import --skip-embed` disables automatic embedding
- Helpful error when sqlite-vec unavailable
- All tests pass
- CLAUDE.md updated
