# Phase 5: PdfExtractor with Quality Validation

## Goal
Implement PDF extraction via Marker with output quality checking.

---

<!-- START_TASK_1 -->
### Task 1: Create PdfExtractor implementation

**Files:**
- Create: `src/local_library/ingestion/pdf.py`

**Step 1: Create the PdfExtractor implementation**

```python
"""PDF extraction implementation using Marker."""

# pattern: Imperative Shell

from pathlib import Path
from typing import Any

from local_library.core.errors import ErrorCode, ExtractionError, QualityError
from local_library.core.models import ExtractionResult


class PdfExtractor:
    """Extractor for PDF files using Marker neural extraction.

    Marker converts PDFs to markdown with good formatting preservation.
    Models are loaded once at instantiation and reused for all extractions.
    """

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {".pdf"}

    # Quality thresholds
    DEFAULT_MIN_LENGTH = 100
    DEFAULT_MIN_PRINTABLE_RATIO = 0.8

    def __init__(self, lazy_load: bool = True) -> None:
        """Initialize the PDF extractor.

        Args:
            lazy_load: If True, defer model loading until first extraction.
                       If False, load models immediately.
        """
        self._converter: Any = None
        self._lazy_load = lazy_load

        if not lazy_load:
            self._ensure_models_loaded()

    def _ensure_models_loaded(self) -> None:
        """Load Marker models if not already loaded."""
        if self._converter is not None:
            return

        try:
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict

            self._converter = PdfConverter(artifact_dict=create_model_dict())
        except ImportError as e:
            raise ExtractionError(
                f"marker-pdf not installed or import failed: {e}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
            ) from e
        except Exception as e:
            raise ExtractionError(
                f"failed to load Marker models: {e}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
            ) from e

    def can_handle(self, file_path: Path) -> bool:
        """Check if this extractor can handle the given file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if this extractor can handle the file (PDF)
        """
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text content from PDF using Marker.

        Args:
            file_path: Path to the PDF file

        Returns:
            ExtractionResult with extracted markdown text

        Raises:
            ExtractionError: If extraction fails
        """
        if not file_path.exists():
            raise ExtractionError(
                f"file not found: {file_path}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
                details={"path": str(file_path)},
            )

        self._ensure_models_loaded()

        try:
            from marker.output import text_from_rendered

            # Run extraction
            rendered = self._converter(str(file_path))
            text, metadata, images = text_from_rendered(rendered)

        except Exception as e:
            raise ExtractionError(
                f"marker extraction failed: {e}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
                details={"path": str(file_path)},
            ) from e

        if not text or not text.strip():
            raise ExtractionError(
                "extraction produced empty output",
                ErrorCode.EXTRACTION_EMPTY_OUTPUT,
                details={"path": str(file_path)},
            )

        # Build result with quality metrics
        result = ExtractionResult.from_text(
            text=text,
            metadata=metadata if isinstance(metadata, dict) else {},
        )

        # Store images as bytes if available
        if images:
            result = ExtractionResult(
                text=result.text,
                metadata=result.metadata,
                images=[img if isinstance(img, bytes) else b"" for img in images],
                page_count=len(images) if images else 0,
                character_count=result.character_count,
                printable_ratio=result.printable_ratio,
            )

        return result

    def extract_and_validate(
        self,
        file_path: Path,
        min_length: int | None = None,
        min_printable_ratio: float | None = None,
    ) -> ExtractionResult:
        """Extract text and validate quality.

        Convenience method that combines extraction with quality validation.

        Args:
            file_path: Path to the PDF file
            min_length: Minimum character count (default: 100)
            min_printable_ratio: Minimum printable ratio (default: 0.8)

        Returns:
            ExtractionResult if extraction passes quality checks

        Raises:
            ExtractionError: If extraction fails
            QualityError: If extraction fails quality validation
        """
        min_length = min_length or self.DEFAULT_MIN_LENGTH
        min_printable_ratio = min_printable_ratio or self.DEFAULT_MIN_PRINTABLE_RATIO

        result = self.extract(file_path)

        if result.character_count < min_length:
            raise QualityError(
                f"extracted content too short: {result.character_count} chars (min: {min_length})",
                ErrorCode.QUALITY_TOO_SHORT,
                details={
                    "path": str(file_path),
                    "character_count": result.character_count,
                    "min_length": min_length,
                },
            )

        if result.printable_ratio < min_printable_ratio:
            raise QualityError(
                f"low printable character ratio: {result.printable_ratio:.2%} (min: {min_printable_ratio:.0%})",
                ErrorCode.QUALITY_LOW_PRINTABLE,
                details={
                    "path": str(file_path),
                    "printable_ratio": result.printable_ratio,
                    "min_printable_ratio": min_printable_ratio,
                },
            )

        return result
```

**Step 2: Verify module is importable (note: actual extraction requires models)**

Run: `uv run python -c "from local_library.ingestion.pdf import PdfExtractor; print('PdfExtractor loaded')"`

Expected: `PdfExtractor loaded`

**Step 3: Commit**

```bash
git add src/local_library/ingestion/pdf.py
git commit -m "feat: implement PdfExtractor using Marker for PDF extraction

- Lazy model loading by default (defer until first extraction)
- can_handle() checks for .pdf extension
- extract() runs Marker and returns ExtractionResult
- extract_and_validate() combines extraction with quality checks
- Proper error handling for Marker failures

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Create tests for PdfExtractor

**Files:**
- Create: `tests/unit/test_pdf_extractor.py`

**Step 1: Create the test file**

Note: These tests use mocking for Marker to avoid loading heavy ML models in unit tests. Integration tests with real PDFs would be in a separate test file.

```python
"""Unit tests for PDF extractor module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from local_library.core.errors import ErrorCode, ExtractionError, QualityError
from local_library.core.models import ExtractionResult
from local_library.ingestion.base import ContentExtractor
from local_library.ingestion.pdf import PdfExtractor


class TestPdfExtractor:
    """Tests for PdfExtractor class."""

    @pytest.fixture
    def extractor(self) -> PdfExtractor:
        """Provide a PdfExtractor with lazy loading."""
        return PdfExtractor(lazy_load=True)

    @pytest.fixture
    def sample_pdf(self, temp_dir: Path) -> Path:
        """Create a sample PDF file for testing."""
        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")
        return pdf_path

    # --- can_handle tests ---

    def test_can_handle_pdf_file(self, extractor: PdfExtractor, sample_pdf: Path) -> None:
        """can_handle should return True for PDF files."""
        assert extractor.can_handle(sample_pdf) is True

    def test_can_handle_uppercase_extension(self, extractor: PdfExtractor, temp_dir: Path) -> None:
        """can_handle should handle uppercase extensions."""
        pdf_path = temp_dir / "sample.PDF"
        pdf_path.write_bytes(b"%PDF-1.4")

        assert extractor.can_handle(pdf_path) is True

    def test_cannot_handle_non_pdf(self, extractor: PdfExtractor, temp_dir: Path) -> None:
        """can_handle should return False for non-PDF files."""
        txt_path = temp_dir / "sample.txt"
        txt_path.write_text("test")

        assert extractor.can_handle(txt_path) is False

    # --- extract tests (mocked) ---

    def test_extract_returns_extraction_result(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract should return ExtractionResult with text."""
        mock_converter = MagicMock()
        mock_rendered = MagicMock()
        mock_converter.return_value = mock_rendered

        with patch("local_library.ingestion.pdf.PdfConverter", return_value=mock_converter):
            with patch("local_library.ingestion.pdf.create_model_dict", return_value={}):
                with patch(
                    "local_library.ingestion.pdf.text_from_rendered",
                    return_value=("Extracted markdown content", {"title": "Test"}, []),
                ):
                    # Need to reload the extractor to use mocked imports
                    extractor._converter = mock_converter
                    result = extractor.extract(sample_pdf)

        assert isinstance(result, ExtractionResult)
        assert "Extracted markdown content" in result.text

    def test_extract_raises_for_nonexistent_file(
        self, extractor: PdfExtractor, temp_dir: Path
    ) -> None:
        """extract should raise ExtractionError for nonexistent file."""
        nonexistent = temp_dir / "nonexistent.pdf"

        with pytest.raises(ExtractionError) as exc_info:
            extractor.extract(nonexistent)

        assert exc_info.value.code == ErrorCode.EXTRACTION_MARKER_CRASH

    def test_extract_raises_for_empty_output(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract should raise ExtractionError for empty extraction."""
        mock_converter = MagicMock()
        mock_converter.return_value = MagicMock()

        with patch(
            "local_library.ingestion.pdf.text_from_rendered",
            return_value=("", {}, []),
        ):
            extractor._converter = mock_converter

            with pytest.raises(ExtractionError) as exc_info:
                extractor.extract(sample_pdf)

            assert exc_info.value.code == ErrorCode.EXTRACTION_EMPTY_OUTPUT

    # --- extract_and_validate tests ---

    def test_extract_and_validate_passes_for_good_content(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should pass for content meeting thresholds."""
        mock_converter = MagicMock()
        mock_converter.return_value = MagicMock()

        good_content = "x" * 200  # Well above min_length

        with patch(
            "local_library.ingestion.pdf.text_from_rendered",
            return_value=(good_content, {}, []),
        ):
            extractor._converter = mock_converter
            result = extractor.extract_and_validate(sample_pdf)

        assert result.character_count >= 100

    def test_extract_and_validate_raises_for_short_content(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should raise QualityError for short content."""
        mock_converter = MagicMock()
        mock_converter.return_value = MagicMock()

        short_content = "short"  # Below min_length

        with patch(
            "local_library.ingestion.pdf.text_from_rendered",
            return_value=(short_content, {}, []),
        ):
            extractor._converter = mock_converter

            with pytest.raises(QualityError) as exc_info:
                extractor.extract_and_validate(sample_pdf)

            assert exc_info.value.code == ErrorCode.QUALITY_TOO_SHORT

    def test_extract_and_validate_raises_for_low_printable(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should raise QualityError for garbled output."""
        mock_converter = MagicMock()
        mock_converter.return_value = MagicMock()

        # Content with many non-printable characters
        garbled_content = "Hello" + "\x00" * 200

        with patch(
            "local_library.ingestion.pdf.text_from_rendered",
            return_value=(garbled_content, {}, []),
        ):
            extractor._converter = mock_converter

            with pytest.raises(QualityError) as exc_info:
                extractor.extract_and_validate(sample_pdf)

            assert exc_info.value.code == ErrorCode.QUALITY_LOW_PRINTABLE

    def test_extract_and_validate_uses_custom_thresholds(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should respect custom thresholds."""
        mock_converter = MagicMock()
        mock_converter.return_value = MagicMock()

        content = "x" * 50  # Would fail default min_length=100

        with patch(
            "local_library.ingestion.pdf.text_from_rendered",
            return_value=(content, {}, []),
        ):
            extractor._converter = mock_converter

            # Should pass with custom lower threshold
            result = extractor.extract_and_validate(
                sample_pdf, min_length=10, min_printable_ratio=0.5
            )

            assert result.character_count == 50


class TestProtocolConformance:
    """Tests that PdfExtractor conforms to ContentExtractor protocol."""

    def test_pdf_extractor_conforms_to_protocol(self) -> None:
        """PdfExtractor should satisfy ContentExtractor protocol."""
        extractor = PdfExtractor(lazy_load=True)

        # runtime_checkable allows isinstance checks
        assert isinstance(extractor, ContentExtractor)
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_pdf_extractor.py -v`

Expected: All tests pass (approximately 10 tests)

**Step 3: Commit**

```bash
git add tests/unit/test_pdf_extractor.py
git commit -m "test: add unit tests for PdfExtractor

- Tests for can_handle() extension checking
- Tests for extract() with mocked Marker
- Tests for extract_and_validate() quality thresholds
- Tests for protocol conformance

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Update ingestion module exports

**Files:**
- Modify: `src/local_library/ingestion/__init__.py`

**Step 1: Add PdfExtractor to exports**

```python
"""Ingestion module - content acquisition and extraction."""

from local_library.ingestion.base import (
    ContentAcquirer,
    ContentExtractor,
    compute_storage_path,
)
from local_library.ingestion.file import FileAcquirer, compute_file_hash
from local_library.ingestion.pdf import PdfExtractor

__all__ = [
    # Protocols
    "ContentAcquirer",
    "ContentExtractor",
    # Utilities
    "compute_storage_path",
    "compute_file_hash",
    # Implementations
    "FileAcquirer",
    "PdfExtractor",
]
```

**Step 2: Verify imports work**

Run: `uv run python -c "from local_library.ingestion import PdfExtractor, ContentExtractor; print('All exports available')"`

Expected: `All exports available`

**Step 3: Run all tests**

Run: `uv run pytest tests/ -v`

Expected: All tests pass

**Step 4: Commit**

```bash
git add src/local_library/ingestion/__init__.py
git commit -m "feat: export PdfExtractor from ingestion module

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_3 -->

---

**Phase 5 Definition of Done:**
- PDFs extract to markdown via Marker
- Quality validation catches garbage output (short content, low printable ratio)
- Extraction errors are properly raised with error codes
- All extractor tests pass
