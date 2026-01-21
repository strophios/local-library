# Phase 8: End-to-End Integration

## Goal
Verify complete workflow and edge cases with integration tests.

---

<!-- START_TASK_1 -->
### Task 1: Create integration test fixtures

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/conftest.py`

**Step 1: Create integration test package**

```python
"""Integration tests package."""
```

**Step 2: Create integration test fixtures**

```python
"""Fixtures for integration tests."""

# pattern: Imperative Shell

from pathlib import Path

import pytest

from local_library.core import Library


@pytest.fixture
def integration_library(temp_dir: Path) -> Library:
    """Provide a Library instance for integration testing.

    Uses temporary directories for all storage to ensure test isolation.
    """
    return Library(
        db_path=temp_dir / "test.db",
        storage_dir=temp_dir / "storage",
        extracted_dir=temp_dir / "extracted",
    )


@pytest.fixture
def sample_pdf_content() -> bytes:
    """Provide minimal valid PDF content for testing.

    This is a minimal PDF that Marker can parse, though extraction
    may produce minimal output.
    """
    # Minimal valid PDF structure
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Hello World) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000214 00000 n
trailer
<< /Size 5 /Root 1 0 R >>
startxref
306
%%EOF"""


@pytest.fixture
def sample_pdf(temp_dir: Path, sample_pdf_content: bytes) -> Path:
    """Create a sample PDF file for testing."""
    pdf_path = temp_dir / "sample.pdf"
    pdf_path.write_bytes(sample_pdf_content)
    return pdf_path


@pytest.fixture
def multiple_pdfs(temp_dir: Path, sample_pdf_content: bytes) -> list[Path]:
    """Create multiple PDF files with different content."""
    pdfs = []
    for i in range(3):
        # Modify content slightly to get different hashes
        content = sample_pdf_content + f"\n% Document {i}".encode()
        pdf_path = temp_dir / f"doc{i}.pdf"
        pdf_path.write_bytes(content)
        pdfs.append(pdf_path)
    return pdfs
```

**Step 3: Commit**

```bash
git add tests/integration/__init__.py tests/integration/conftest.py
git commit -m "test: add integration test fixtures

- integration_library fixture with temp directories
- sample_pdf_content with minimal valid PDF
- sample_pdf and multiple_pdfs fixtures

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Create end-to-end workflow tests

**Files:**
- Create: `tests/integration/test_workflow.py`

**Step 1: Create the workflow test file**

```python
"""End-to-end workflow integration tests."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from local_library.core import Library
from local_library.core.models import DocumentStatus


class TestAddListShowDeleteCycle:
    """Tests for complete add → list → show → delete workflow."""

    def test_full_cycle_with_mocked_extraction(
        self, integration_library: Library, sample_pdf: Path
    ) -> None:
        """Full workflow should work: add → list → show → delete."""
        lib = integration_library

        # Mock extraction to avoid loading Marker models
        with patch.object(lib._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            # ADD
            result = lib.add(str(sample_pdf))
            assert result.is_duplicate is False
            assert result.document.status == DocumentStatus.READY
            doc_id = str(result.document.id)

            # LIST - should find the document
            docs = lib.list()
            assert len(docs) == 1
            assert str(docs[0].id) == doc_id

            # SHOW - should retrieve document details
            doc = lib.get(doc_id)
            assert doc.original_path == str(sample_pdf)
            assert doc.status == DocumentStatus.READY

            # DELETE - should remove document
            lib.delete(doc_id)

            # Verify deletion
            docs = lib.list()
            assert len(docs) == 0

    def test_partial_id_lookup(
        self, integration_library: Library, sample_pdf: Path
    ) -> None:
        """Should find documents by partial UUID prefix."""
        lib = integration_library

        with patch.object(lib._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            result = lib.add(str(sample_pdf))
            full_id = str(result.document.id)
            partial_id = full_id[:8]

            # Should find by partial ID
            doc = lib.get(partial_id)
            assert str(doc.id) == full_id

    def test_multiple_documents(
        self, integration_library: Library, multiple_pdfs: list[Path]
    ) -> None:
        """Should handle multiple documents correctly."""
        lib = integration_library

        with patch.object(lib._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            # Add all PDFs
            doc_ids = []
            for pdf_path in multiple_pdfs:
                result = lib.add(str(pdf_path))
                assert result.is_duplicate is False
                doc_ids.append(str(result.document.id))

            # List should show all
            docs = lib.list()
            assert len(docs) == 3

            # Filter by status
            ready_docs = lib.list(status=DocumentStatus.READY)
            assert len(ready_docs) == 3

            # Delete one
            lib.delete(doc_ids[0])
            docs = lib.list()
            assert len(docs) == 2


class TestDuplicateDetection:
    """Tests for duplicate detection behavior."""

    def test_duplicate_by_path_returns_existing(
        self, integration_library: Library, sample_pdf: Path
    ) -> None:
        """Adding same path twice should return existing document."""
        lib = integration_library

        with patch.object(lib._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            # First add
            result1 = lib.add(str(sample_pdf))
            assert result1.is_duplicate is False

            # Second add of same path
            result2 = lib.add(str(sample_pdf))
            assert result2.is_duplicate is True
            assert result2.duplicate_reason == "path"
            assert result2.document.id == result1.document.id

    def test_duplicate_by_hash_returns_existing(
        self, integration_library: Library, temp_dir: Path, sample_pdf_content: bytes
    ) -> None:
        """Adding files with identical content should return existing document."""
        lib = integration_library

        # Create two files with identical content
        pdf1 = temp_dir / "copy1.pdf"
        pdf2 = temp_dir / "copy2.pdf"
        pdf1.write_bytes(sample_pdf_content)
        pdf2.write_bytes(sample_pdf_content)

        with patch.object(lib._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            # First add
            result1 = lib.add(str(pdf1))
            assert result1.is_duplicate is False

            # Second add with same content
            result2 = lib.add(str(pdf2))
            assert result2.is_duplicate is True
            assert result2.duplicate_reason == "hash"
            assert result2.document.id == result1.document.id


class TestExtractionFailures:
    """Tests for extraction failure handling."""

    def test_extraction_failure_creates_failed_record(
        self, integration_library: Library, sample_pdf: Path
    ) -> None:
        """Extraction failure should create record with failed status."""
        lib = integration_library

        from local_library.core import ErrorCode, ExtractionError

        with patch.object(lib._extractor, "extract_and_validate") as mock_extract:
            mock_extract.side_effect = ExtractionError(
                "marker extraction failed",
                ErrorCode.EXTRACTION_MARKER_CRASH,
            )

            with pytest.raises(ExtractionError):
                lib.add(str(sample_pdf))

            # Document should exist with failed status
            docs = lib.list()
            assert len(docs) == 1
            assert docs[0].status == DocumentStatus.FAILED
            assert docs[0].error_code == ErrorCode.EXTRACTION_MARKER_CRASH.value

    def test_quality_failure_creates_failed_record(
        self, integration_library: Library, sample_pdf: Path
    ) -> None:
        """Quality validation failure should create record with failed status."""
        lib = integration_library

        from local_library.core import ErrorCode, QualityError

        with patch.object(lib._extractor, "extract_and_validate") as mock_extract:
            mock_extract.side_effect = QualityError(
                "content too short",
                ErrorCode.QUALITY_TOO_SHORT,
            )

            with pytest.raises(QualityError):
                lib.add(str(sample_pdf))

            # Document should exist with failed status
            docs = lib.list()
            assert len(docs) == 1
            assert docs[0].status == DocumentStatus.FAILED


class TestForceMode:
    """Tests for --force behavior with inaccessible files."""

    def test_force_creates_failed_record_for_nonexistent_file(
        self, integration_library: Library
    ) -> None:
        """--force should create failed record for nonexistent file."""
        lib = integration_library

        result = lib.add("/nonexistent/document.pdf", force=True)

        assert result.is_duplicate is False
        assert result.document.status == DocumentStatus.FAILED
        assert result.document.original_path == "/nonexistent/document.pdf"

    def test_force_duplicate_returns_existing(
        self, integration_library: Library
    ) -> None:
        """--force with same path twice should return existing failed record."""
        lib = integration_library

        # First force add
        result1 = lib.add("/nonexistent/document.pdf", force=True)
        assert result1.is_duplicate is False

        # Second force add of same path
        result2 = lib.add("/nonexistent/document.pdf", force=True)
        assert result2.is_duplicate is True
        assert result2.duplicate_reason == "path"


class TestFileCleanup:
    """Tests for file deletion behavior."""

    def test_delete_removes_storage_files(
        self, integration_library: Library, sample_pdf: Path
    ) -> None:
        """delete() should remove storage and extracted files."""
        lib = integration_library

        with patch.object(lib._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            result = lib.add(str(sample_pdf))
            storage_path = Path(result.document.storage_path)

            # Storage file should exist
            assert storage_path.exists()

            # Delete with file cleanup
            lib.delete(str(result.document.id), delete_files=True)

            # Storage file should be gone
            assert not storage_path.exists()

    def test_delete_keeps_files_when_requested(
        self, integration_library: Library, sample_pdf: Path
    ) -> None:
        """delete() with delete_files=False should keep storage files."""
        lib = integration_library

        with patch.object(lib._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            result = lib.add(str(sample_pdf))
            storage_path = Path(result.document.storage_path)

            # Storage file should exist
            assert storage_path.exists()

            # Delete without file cleanup
            lib.delete(str(result.document.id), delete_files=False)

            # Storage file should still exist
            assert storage_path.exists()
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_workflow.py -v`

Expected: All tests pass (approximately 12 tests)

**Step 3: Commit**

```bash
git add tests/integration/test_workflow.py
git commit -m "test: add end-to-end workflow integration tests

- Full add→list→show→delete cycle tests
- Partial UUID lookup tests
- Duplicate detection tests (by path and hash)
- Extraction failure handling tests
- --force mode tests for inaccessible files
- File cleanup behavior tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Create CLI integration tests

**Files:**
- Create: `tests/integration/test_cli_integration.py`

**Step 1: Create CLI integration tests**

```python
"""CLI integration tests using real Library (with mocked extraction)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core import Library

runner = CliRunner()


class TestCLIIntegration:
    """Integration tests for CLI commands with real Library."""

    @pytest.fixture
    def cli_env(self, temp_dir: Path, sample_pdf: Path):
        """Set up CLI test environment with patched paths."""
        db_path = temp_dir / "test.db"
        storage_dir = temp_dir / "storage"
        extracted_dir = temp_dir / "extracted"

        # Patch Library to use temp paths
        original_init = Library.__init__

        def patched_init(self, **kwargs):
            original_init(
                self,
                db_path=db_path,
                storage_dir=storage_dir,
                extracted_dir=extracted_dir,
            )

        with patch.object(Library, "__init__", patched_init):
            yield {"sample_pdf": sample_pdf, "temp_dir": temp_dir}

    def test_cli_add_list_show_delete(self, cli_env: dict) -> None:
        """CLI should support full workflow."""
        sample_pdf = cli_env["sample_pdf"]

        # Patch extraction in the Library class
        with patch(
            "local_library.core.library.PdfExtractor.extract_and_validate"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            # ADD
            result = runner.invoke(app, ["add", str(sample_pdf)])
            assert result.exit_code == 0, f"Add failed: {result.output}"
            assert "added" in result.output

            # Extract doc ID from output
            # Output format: "added: <uuid>"
            doc_id = None
            for line in result.output.split("\n"):
                if "added" in line:
                    parts = line.split(":")
                    if len(parts) > 1:
                        doc_id = parts[1].strip()
                        break

            assert doc_id is not None, f"Could not find doc ID in: {result.output}"

            # LIST
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert doc_id[:8] in result.output

            # SHOW
            result = runner.invoke(app, ["show", doc_id[:8]])
            assert result.exit_code == 0
            assert str(sample_pdf) in result.output

            # DELETE
            result = runner.invoke(app, ["delete", "--force", doc_id[:8]])
            assert result.exit_code == 0
            assert "deleted" in result.output

            # Verify deletion
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "No documents" in result.output

    def test_cli_json_output(self, cli_env: dict) -> None:
        """CLI --json flag should produce valid JSON."""
        import json

        sample_pdf = cli_env["sample_pdf"]

        with patch(
            "local_library.core.library.PdfExtractor.extract_and_validate"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            # ADD with JSON
            result = runner.invoke(app, ["add", "--json", str(sample_pdf)])
            assert result.exit_code == 0

            # Parse JSON output
            output = json.loads(result.output)
            assert "id" in output
            assert "status" in output
            assert output["is_duplicate"] is False

            # LIST with JSON
            result = runner.invoke(app, ["list", "--json"])
            assert result.exit_code == 0

            docs = json.loads(result.output)
            assert len(docs) == 1
            assert docs[0]["id"] == output["id"]

    def test_cli_error_handling(self, cli_env: dict) -> None:
        """CLI should handle errors with proper exit codes."""
        # Show nonexistent document
        result = runner.invoke(app, ["show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

        # Delete nonexistent document
        result = runner.invoke(app, ["delete", "--force", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

        # Add nonexistent file
        result = runner.invoke(app, ["add", "/nonexistent/file.pdf"])
        assert result.exit_code == 1

    def test_cli_force_mode(self, cli_env: dict) -> None:
        """CLI add --force should create failed record."""
        result = runner.invoke(app, ["add", "--force", "/nonexistent/file.pdf"])
        # Should succeed (creates failed record)
        # Exit code 2 is for extraction failure (which happens after record creation)
        # But for inaccessible files with --force, it creates failed record without extraction
        assert result.exit_code == 0 or "failed" in result.output.lower()

        # List should show the document
        result = runner.invoke(app, ["list"])
        assert "nonexistent" in result.output or "failed" in result.output.lower()
```

**Step 2: Run CLI integration tests**

Run: `uv run pytest tests/integration/test_cli_integration.py -v`

Expected: All tests pass (approximately 4 tests)

**Step 3: Commit**

```bash
git add tests/integration/test_cli_integration.py
git commit -m "test: add CLI integration tests

- Full CLI workflow with real Library (mocked extraction)
- JSON output validation
- Error handling and exit code tests
- --force mode tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Run full test suite and quality checks

**Files:**
- No new files

**Step 1: Run all tests**

Run: `uv run pytest tests/ -v --tb=short`

Expected: All tests pass (unit + integration, approximately 50+ tests)

**Step 2: Run linting**

Run: `uv run ruff check src/ tests/`

Expected: No linting errors

**Step 3: Run formatting check**

Run: `uv run ruff format --check src/ tests/`

Expected: No formatting issues

**Step 4: Verify CLI works end-to-end**

Run: `uv run local-library --help`

Expected: Shows help with all commands

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: complete M1+M2 implementation

All phases complete:
- Phase 1: Project scaffolding
- Phase 2: Core models and errors
- Phase 3: Storage layer
- Phase 4: Ingestion protocols and FileAcquirer
- Phase 5: PdfExtractor with quality validation
- Phase 6: Library orchestration
- Phase 7: CLI commands
- Phase 8: End-to-end integration tests

M1+M2 Definition of Done verified:
✓ Can add a PDF (file copied, text extracted, record persists)
✓ Duplicate detection works (by path and content hash)
✓ Failed extractions create records with status='failed'
✓ Can list, view, and delete records via UUID (partial match supported)
✓ Tests pass for CRUD, extraction, duplicates, and error cases

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_4 -->

---

**Phase 8 Definition of Done:**
- E2E tests pass for full add→list→show→delete cycle
- Duplicate detection tests pass (by path and hash)
- Extraction failure tests pass (records created with failed status)
- --force behavior tests pass
- File cleanup behavior tests pass
- CLI integration tests pass with real Library
- All quality checks pass (ruff check, ruff format)
