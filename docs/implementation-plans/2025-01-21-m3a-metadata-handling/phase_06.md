# Phase 6: Pipeline Integration

**Goal:** Wire MetadataHandler into Library.add() and CLI.

**Dependencies:** Phases 1-5

**Done when:** `local-library add paper.pdf --metadata meta.json` works end-to-end, validation errors display clearly, documents stored with metadata queryable.

---

<!-- START_TASK_1 -->
### Task 1: Add MetadataHandler to Library class

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Add imports**

Add to the imports at the top of `library.py`:

```python
from local_library.core.errors import (
    AcquisitionError,
    ErrorCode,
    ExtractionError,
    LookupError,
    MetadataError,
    QualityError,
)
```

Also add:

```python
from local_library.core.storage import (
    create_document,
    delete_document,
    get_connection,
    get_document_by_hash,
    get_document_by_id,
    get_document_by_path,
    get_documents_by_partial_id,
    get_unique_citekey,
    init_schema,
    list_documents,
    update_document_metadata,
    update_document_status,
)
from local_library.ingestion.metadata import MetadataHandler
```

**Step 2: Add MetadataHandler to __init__**

Update the `__init__` method to instantiate MetadataHandler (around line 77, after extractor initialization):

```python
        # Initialize metadata handler
        self._metadata_handler = MetadataHandler()
```

**Step 3: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "feat(library): instantiate MetadataHandler in Library

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update Library.add() to accept and process metadata

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Update add() method signature**

Update the `add` method signature (around line 155):

```python
    def add(
        self,
        source: str,
        force: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> AddResult:
        """Add a document to the library.

        The add pipeline:
        1. Check if acquirer can handle the source
        2. Validate the source (unless force=True for inaccessible files)
        3. Check for duplicate by original path
        4. Acquire content and compute hash
        5. Check for duplicate by content hash
        6. Move to content-addressable storage
        7. Create database record
        8. Extract text content
        9. Process metadata (if provided)
        10. Update record status

        Args:
            source: Path to the source file
            force: If True, create failed record for inaccessible files
            metadata: Optional CSL-JSON metadata dict

        Returns:
            AddResult containing the document and duplicate status

        Raises:
            AcquisitionError: If source is invalid and force=False
            ExtractionError: If extraction fails (record created with failed status)
            MetadataError: If metadata validation fails
        """
```

**Step 2: Add metadata processing after extraction**

Update the extraction section (around lines 236-270) to include metadata processing:

```python
        # Extract text content
        try:
            extractor = self._find_extractor(storage_path)
            result = extractor.extract_and_validate(storage_path)

            # Write extracted markdown
            extracted_path = compute_storage_path(
                doc.content_hash,
                ".md",
                self._extracted_dir,
            )
            extracted_path.parent.mkdir(parents=True, exist_ok=True)
            extracted_path.write_text(result.text, encoding="utf-8")

            # Update record to ready
            doc = update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.READY,
                extracted_path=str(extracted_path),
            )

            # Process metadata if provided
            if metadata:
                doc = self._process_metadata(doc, metadata)

        except (ExtractionError, QualityError) as e:
            # Update record to failed
            doc = update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.FAILED,
                error_message=e.message,
                error_code=e.code.value,
            )
            # Re-raise so caller knows extraction failed
            raise

        return AddResult(document=doc)
```

**Step 3: Add _process_metadata method**

Add after the `_create_failed_record` method (around line 321):

```python
    def _process_metadata(
        self, doc: Document, metadata: dict[str, Any]
    ) -> Document:
        """Process and store metadata for a document.

        Args:
            doc: The document to update
            metadata: CSL-JSON metadata dict

        Returns:
            Updated document with metadata

        Raises:
            MetadataError: If metadata validation fails
        """
        # Process metadata through handler
        result = self._metadata_handler.process(metadata)

        # Get unique citekey (handle collisions)
        unique_citekey = get_unique_citekey(self._conn, result.citekey)

        # Update document with metadata
        return update_document_metadata(
            self._conn,
            doc.id,
            citekey=unique_citekey,
            csl_json=result.csl_json,
            title=result.title,
            authors=result.authors,
            issued_date=result.issued_date,
        )
```

**Step 4: Add typing import if not present**

Ensure `from typing import Any` is in the imports at the top of the file.

**Step 5: Verify compilation**

Run:
```bash
uv run python -c "from local_library.core.library import Library; print('OK')"
```

Expected: `OK`

**Step 6: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "feat(library): integrate MetadataHandler into add() pipeline

Accepts optional metadata parameter, validates CSL-JSON,
generates unique citekey, stores indexed fields.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add --metadata flag to CLI add command

**Files:**
- Modify: `src/local_library/cli/add.py`

**Step 1: Update imports**

Update imports at the top of `add.py`:

```python
import json
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
```

**Step 2: Update add function signature**

Update the `add` function signature:

```python
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
    """
```

**Step 3: Load and pass metadata**

Update the main logic to load and pass metadata:

```python
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

    try:
        with Library() as lib:
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
```

**Step 4: Update JSON output to include metadata fields**

Update the JSON output section (around lines 54-65):

```python
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
```

**Step 5: Update core __init__.py exports**

Check `src/local_library/core/__init__.py` and ensure `MetadataError` is exported:

```python
from local_library.core.errors import (
    AcquisitionError,
    ErrorCode,
    ExtractionError,
    LocalLibraryError,
    LookupError,
    MetadataError,
    QualityError,
    StorageError,
)
```

**Step 6: Verify CLI works**

Run:
```bash
uv run local-library add --help
```

Expected: Should show `--metadata` / `-m` option in help.

**Step 7: Commit**

```bash
git add src/local_library/cli/add.py src/local_library/core/__init__.py
git commit -m "feat(cli): add --metadata flag to add command

Accepts path to CSL-JSON file for bibliographic metadata.
Shows citekey and title in output when metadata provided.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Write integration tests for metadata pipeline

**Files:**
- Modify: `tests/integration/test_workflow.py`

**Step 1: Add metadata workflow tests**

Add to `tests/integration/test_workflow.py`:

```python


class TestMetadataWorkflow:
    """Tests for end-to-end metadata workflow."""

    def test_add_with_metadata(
        self, integration_library: Library, sample_pdf: Path
    ) -> None:
        """Adding document with metadata should store all fields."""
        from unittest.mock import MagicMock, patch

        metadata = {
            "type": "article-journal",
            "title": "Attention Is All You Need",
            "author": [
                {"family": "Vaswani", "given": "Ashish"},
                {"family": "Shazeer", "given": "Noam"},
            ],
            "issued": {"date-parts": [[2017]]},
        }

        # Mock extraction to avoid loading Marker
        with patch.object(
            integration_library._extractors[0], "extract_and_validate"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            result = integration_library.add(str(sample_pdf), metadata=metadata)

        assert result.document.citekey == "Vaswani2017Attention"
        assert result.document.title == "Attention Is All You Need"
        assert result.document.authors == "Vaswani, A.; Shazeer, N."
        assert result.document.issued_date == "2017"
        assert result.document.csl_json == metadata

    def test_add_with_metadata_citekey_collision(
        self, integration_library: Library, multiple_pdfs: list[Path]
    ) -> None:
        """Multiple documents with same generated citekey should get suffixes."""
        from unittest.mock import MagicMock, patch

        metadata = {
            "type": "article-journal",
            "title": "Test Article",
            "author": [{"family": "Smith", "given": "John"}],
            "issued": {"date-parts": [[2020]]},
        }

        with patch.object(
            integration_library._extractors[0], "extract_and_validate"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            result1 = integration_library.add(str(multiple_pdfs[0]), metadata=metadata)
            result2 = integration_library.add(str(multiple_pdfs[1]), metadata=metadata)

        assert result1.document.citekey == "Smith2020Test"
        assert result2.document.citekey == "Smith2020Testa"

    def test_add_with_invalid_metadata_raises(
        self, integration_library: Library, sample_pdf: Path
    ) -> None:
        """Invalid metadata should raise MetadataError."""
        from local_library.core.errors import MetadataError

        invalid_metadata = {"title": "No type field"}  # Missing required 'type'

        with pytest.raises(MetadataError):
            integration_library.add(str(sample_pdf), metadata=invalid_metadata)

    def test_add_without_metadata_works(
        self, integration_library: Library, sample_pdf: Path
    ) -> None:
        """Adding without metadata should still work (no citekey)."""
        from unittest.mock import MagicMock, patch

        with patch.object(
            integration_library._extractors[0], "extract_and_validate"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            result = integration_library.add(str(sample_pdf))

        assert result.document.citekey is None
        assert result.document.title is None
```

**Step 2: Run integration tests**

Run:
```bash
uv run pytest tests/integration/test_workflow.py::TestMetadataWorkflow -v
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add tests/integration/test_workflow.py
git commit -m "test(integration): add metadata workflow tests

Tests end-to-end metadata processing, citekey collision handling,
invalid metadata rejection, and operation without metadata.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Write CLI integration tests for --metadata flag

**Files:**
- Modify: `tests/integration/test_cli_integration.py`

**Step 1: Add CLI metadata tests**

Add to `tests/integration/test_cli_integration.py`:

```python


class TestAddWithMetadata:
    """Tests for add command with --metadata flag."""

    def test_add_with_metadata_file(
        self, temp_dir: Path, sample_pdf: Path
    ) -> None:
        """add --metadata should process metadata file."""
        from typer.testing import CliRunner
        from unittest.mock import patch, MagicMock
        import json

        from local_library.cli.main import app

        # Create metadata file
        metadata = {
            "type": "book",
            "title": "Test Book",
            "author": [{"family": "Author", "given": "Test"}],
            "issued": {"date-parts": [[2023]]},
        }
        metadata_file = temp_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata))

        runner = CliRunner()

        with patch("local_library.core.library.PdfExtractor") as MockExtractor:
            mock_extractor = MagicMock()
            mock_extractor.can_handle.return_value = True
            mock_extractor.extract_and_validate.return_value = MagicMock(
                text="Extracted " * 30
            )
            MockExtractor.return_value = mock_extractor

            result = runner.invoke(
                app,
                ["add", str(sample_pdf), "--metadata", str(metadata_file)],
            )

        assert result.exit_code == 0
        assert "added" in result.stdout or "Author2023Test" in result.stdout

    def test_add_with_invalid_json_file(self, temp_dir: Path, sample_pdf: Path) -> None:
        """add --metadata with invalid JSON should fail."""
        from typer.testing import CliRunner

        from local_library.cli.main import app

        # Create invalid JSON file
        invalid_file = temp_dir / "invalid.json"
        invalid_file.write_text("not valid json {")

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["add", str(sample_pdf), "--metadata", str(invalid_file)],
        )

        assert result.exit_code == 1
        assert "invalid JSON" in result.stdout or "error" in result.stdout

    def test_add_with_invalid_metadata_schema(
        self, temp_dir: Path, sample_pdf: Path
    ) -> None:
        """add --metadata with invalid CSL-JSON should fail."""
        from typer.testing import CliRunner
        from unittest.mock import patch, MagicMock
        import json

        from local_library.cli.main import app

        # Create metadata with missing required 'type'
        metadata = {"title": "Missing Type Field"}
        metadata_file = temp_dir / "bad_metadata.json"
        metadata_file.write_text(json.dumps(metadata))

        runner = CliRunner()

        with patch("local_library.core.library.PdfExtractor") as MockExtractor:
            mock_extractor = MagicMock()
            mock_extractor.can_handle.return_value = True
            mock_extractor.extract_and_validate.return_value = MagicMock(
                text="Extracted " * 30
            )
            MockExtractor.return_value = mock_extractor

            result = runner.invoke(
                app,
                ["add", str(sample_pdf), "--metadata", str(metadata_file)],
            )

        assert result.exit_code == 1
        assert "metadata" in result.stdout.lower() or "error" in result.stdout.lower()
```

**Step 2: Run CLI integration tests**

Run:
```bash
uv run pytest tests/integration/test_cli_integration.py::TestAddWithMetadata -v
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add tests/integration/test_cli_integration.py
git commit -m "test(cli): add integration tests for --metadata flag

Tests valid metadata file, invalid JSON, and invalid CSL-JSON schema.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Update existing tests for new add() signature

**Files:**
- Modify: `tests/unit/test_library.py`
- Modify: `tests/unit/test_cli.py`

**Step 1: Check and update test_library.py**

If any tests call `lib.add()` without the new parameter, they should continue to work since `metadata=None` is the default. Verify by running:

```bash
uv run pytest tests/unit/test_library.py -v
```

If there are failures related to the new signature, update the mock return values or test assertions.

**Step 2: Check and update test_cli.py**

Run:
```bash
uv run pytest tests/unit/test_cli.py -v
```

If there are failures, update accordingly.

**Step 3: Commit any fixes**

```bash
git add tests/unit/test_library.py tests/unit/test_cli.py
git commit -m "fix(tests): update existing tests for new add() signature

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Run full test suite and verify Phase 6 complete

**Files:** None (verification only)

**Step 1: Run full test suite**

Run:
```bash
uv run pytest -v
```

Expected: All tests pass.

**Step 2: Verify lint passes**

Run:
```bash
uv run ruff check src/local_library/ tests/
```

Expected: No errors.

**Step 3: Manual verification (optional)**

Create a test metadata file and try the command manually:

```bash
# Create test metadata file
echo '{"type": "book", "title": "Test Book", "author": [{"family": "Test", "given": "Author"}], "issued": {"date-parts": [[2024]]}}' > /tmp/test_meta.json

# Try adding a PDF with metadata (if you have a test PDF)
# uv run local-library add /path/to/test.pdf --metadata /tmp/test_meta.json --json
```

**Step 4: Commit phase completion**

```bash
git add -A
git commit -m "chore: Phase 6 complete - pipeline integration

M3a metadata handling milestone complete:
- CSL-JSON validation with jsonschema
- BetterBibTeX-style citekey generation
- Indexed field extraction (title, authors, date)
- Database schema with migration
- CLI --metadata flag integration

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_7 -->

---

## Phase 6 Completion Criteria

- [ ] MetadataHandler instantiated in Library.__init__()
- [ ] Library.add() accepts optional metadata parameter
- [ ] Metadata processed after extraction, before final status update
- [ ] Citekey collision handled via get_unique_citekey()
- [ ] CLI add command has --metadata flag
- [ ] Invalid JSON file produces clear error
- [ ] Invalid CSL-JSON schema produces MetadataError
- [ ] JSON output includes citekey, title, authors, issued_date
- [ ] Human output shows citekey and title when metadata provided
- [ ] All tests pass (unit + integration)
- [ ] End-to-end workflow: `local-library add file.pdf --metadata meta.json` works
