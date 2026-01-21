# Phase 2: Core Models and Errors

## Goal
Define data structures and exception hierarchy for the PDF RAG pipeline.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create error module with exception hierarchy

**Files:**
- Create: `src/local_library/core/errors.py`

**Step 1: Create the error module with error codes and exceptions**

```python
"""Custom exceptions with error codes for programmatic handling."""

# pattern: Functional Core

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Machine-parseable error codes for categorizing failures."""

    # Acquisition errors
    ACQUISITION_FILE_NOT_FOUND = "ACQUISITION_FILE_NOT_FOUND"
    ACQUISITION_FILE_NOT_READABLE = "ACQUISITION_FILE_NOT_READABLE"
    ACQUISITION_INVALID_FORMAT = "ACQUISITION_INVALID_FORMAT"
    ACQUISITION_COPY_FAILED = "ACQUISITION_COPY_FAILED"

    # Extraction errors
    EXTRACTION_MARKER_CRASH = "EXTRACTION_MARKER_CRASH"
    EXTRACTION_TIMEOUT = "EXTRACTION_TIMEOUT"
    EXTRACTION_EMPTY_OUTPUT = "EXTRACTION_EMPTY_OUTPUT"

    # Quality validation errors
    QUALITY_LOW_PRINTABLE = "QUALITY_LOW_PRINTABLE"
    QUALITY_TOO_SHORT = "QUALITY_TOO_SHORT"
    QUALITY_GARBLED_OUTPUT = "QUALITY_GARBLED_OUTPUT"

    # Storage errors
    STORAGE_DATABASE_ERROR = "STORAGE_DATABASE_ERROR"
    STORAGE_WRITE_FAILED = "STORAGE_WRITE_FAILED"

    # Lookup errors
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"


class LocalLibraryError(Exception):
    """Base exception for all local-library errors."""

    def __init__(
        self,
        message: str,
        code: ErrorCode,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


class AcquisitionError(LocalLibraryError):
    """Error during content acquisition (file access, copying)."""

    pass


class ExtractionError(LocalLibraryError):
    """Error during content extraction (Marker processing)."""

    pass


class QualityError(LocalLibraryError):
    """Error when extracted content fails quality validation."""

    pass


class StorageError(LocalLibraryError):
    """Error during database or file storage operations."""

    pass


class LookupError(LocalLibraryError):
    """Error when looking up records (not found, ambiguous match)."""

    pass
```

**Step 2: Verify module is importable and exceptions work**

Run: `uv run python -c "from local_library.core.errors import AcquisitionError, ErrorCode; e = AcquisitionError('test', ErrorCode.ACQUISITION_FILE_NOT_FOUND); print(e)"`

Expected: `[ACQUISITION_FILE_NOT_FOUND] test`

**Step 3: Commit**

```bash
git add src/local_library/core/errors.py
git commit -m "feat: add error module with exception hierarchy and error codes

- ErrorCode enum for machine-parseable error categorization
- LocalLibraryError base with message, code, and details
- Specific exceptions: Acquisition, Extraction, Quality, Storage, Lookup

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create tests for error module

**Files:**
- Create: `tests/unit/test_errors.py`

**Step 1: Create the test file**

```python
"""Unit tests for error module."""

import pytest

from local_library.core.errors import (
    AcquisitionError,
    ErrorCode,
    ExtractionError,
    LocalLibraryError,
    LookupError,
    QualityError,
    StorageError,
)


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_error_code_is_string(self) -> None:
        """ErrorCode values should be strings for JSON serialization."""
        assert isinstance(ErrorCode.ACQUISITION_FILE_NOT_FOUND.value, str)
        assert ErrorCode.ACQUISITION_FILE_NOT_FOUND.value == "ACQUISITION_FILE_NOT_FOUND"

    def test_all_error_codes_have_string_values(self) -> None:
        """All error codes should have matching string values."""
        for code in ErrorCode:
            assert code.value == code.name


class TestLocalLibraryError:
    """Tests for base exception class."""

    def test_exception_stores_message_and_code(self) -> None:
        """Exception should store message and error code."""
        error = LocalLibraryError("test message", ErrorCode.NOT_FOUND)

        assert error.message == "test message"
        assert error.code == ErrorCode.NOT_FOUND
        assert error.details == {}

    def test_exception_stores_details(self) -> None:
        """Exception should store optional details dict."""
        details = {"path": "/some/path", "size": 1024}
        error = LocalLibraryError("test", ErrorCode.NOT_FOUND, details=details)

        assert error.details == details

    def test_str_format_includes_code(self) -> None:
        """String representation should include error code."""
        error = LocalLibraryError("file missing", ErrorCode.ACQUISITION_FILE_NOT_FOUND)

        assert str(error) == "[ACQUISITION_FILE_NOT_FOUND] file missing"

    def test_exception_is_catchable(self) -> None:
        """Exception should be catchable as Exception."""
        with pytest.raises(Exception):
            raise LocalLibraryError("test", ErrorCode.NOT_FOUND)


class TestSpecificExceptions:
    """Tests for specific exception subclasses."""

    def test_acquisition_error_inherits_from_base(self) -> None:
        """AcquisitionError should inherit from LocalLibraryError."""
        error = AcquisitionError("file not found", ErrorCode.ACQUISITION_FILE_NOT_FOUND)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, AcquisitionError)

    def test_extraction_error_inherits_from_base(self) -> None:
        """ExtractionError should inherit from LocalLibraryError."""
        error = ExtractionError("marker crashed", ErrorCode.EXTRACTION_MARKER_CRASH)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, ExtractionError)

    def test_quality_error_inherits_from_base(self) -> None:
        """QualityError should inherit from LocalLibraryError."""
        error = QualityError("output too short", ErrorCode.QUALITY_TOO_SHORT)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, QualityError)

    def test_storage_error_inherits_from_base(self) -> None:
        """StorageError should inherit from LocalLibraryError."""
        error = StorageError("database error", ErrorCode.STORAGE_DATABASE_ERROR)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, StorageError)

    def test_lookup_error_inherits_from_base(self) -> None:
        """LookupError should inherit from LocalLibraryError."""
        error = LookupError("not found", ErrorCode.NOT_FOUND)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, LookupError)

    def test_can_catch_specific_exception(self) -> None:
        """Should be able to catch specific exception types."""
        with pytest.raises(AcquisitionError):
            raise AcquisitionError("test", ErrorCode.ACQUISITION_FILE_NOT_FOUND)

    def test_can_catch_as_base_exception(self) -> None:
        """Should be able to catch specific exceptions as base type."""
        with pytest.raises(LocalLibraryError):
            raise AcquisitionError("test", ErrorCode.ACQUISITION_FILE_NOT_FOUND)
```

**Step 2: Create tests directory structure**

Run: `mkdir -p tests/unit`

**Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_errors.py -v`

Expected: All tests pass (approximately 11 tests)

**Step 4: Commit**

```bash
git add tests/unit/
git commit -m "test: add unit tests for error module

- Tests for ErrorCode enum string values
- Tests for LocalLibraryError message, code, details storage
- Tests for exception inheritance hierarchy
- Tests for catchability patterns

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Create models module with dataclasses

**Files:**
- Create: `src/local_library/core/models.py`

**Step 1: Create the models module**

```python
"""Data models for documents and operation results."""

# pattern: Functional Core

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


class DocumentStatus(str, Enum):
    """Lifecycle status of a document record."""

    PENDING = "pending"  # Created, not yet processed
    READY = "ready"  # Extraction complete, searchable
    FAILED = "failed"  # Extraction failed, needs retry or manual intervention


@dataclass(frozen=True)
class Document:
    """A document record in the library.

    Represents a PDF (or future content type) that has been ingested.
    Tracks the document through its lifecycle from acquisition to extraction.
    """

    id: UUID
    original_path: str  # Path where the document was originally located
    content_hash: str  # SHA-256 hash of file contents
    storage_path: str  # Path in content-addressable storage
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime

    # Nullable fields - populated after extraction or metadata processing
    extracted_path: str | None = None  # Path to extracted markdown
    citekey: str | None = None  # BetterBibTeX-style citation key
    csl_json: dict[str, Any] | None = None  # Bibliographic metadata

    # Error tracking for failed documents
    error_message: str | None = None
    error_code: str | None = None

    @classmethod
    def create_pending(
        cls,
        original_path: str,
        content_hash: str,
        storage_path: str,
    ) -> "Document":
        """Create a new pending document record."""
        now = datetime.utcnow()
        return cls(
            id=uuid4(),
            original_path=original_path,
            content_hash=content_hash,
            storage_path=storage_path,
            status=DocumentStatus.PENDING,
            created_at=now,
            updated_at=now,
        )


@dataclass(frozen=True)
class AcquisitionResult:
    """Result of acquiring content from a source.

    Returned by ContentAcquirer implementations after successfully
    copying/downloading content to a temporary location.
    """

    content_hash: str  # SHA-256 hash of acquired content
    temp_path: Path  # Temporary location of acquired file
    original_path: str  # Original source path/URL

    # Optional metadata discovered during acquisition
    file_size: int = 0
    mime_type: str | None = None


@dataclass
class ExtractionResult:
    """Result of extracting content from a document.

    Returned by ContentExtractor implementations after processing
    a document (e.g., PDF to markdown conversion).
    """

    text: str  # Extracted text content (markdown)
    metadata: dict[str, Any] = field(default_factory=dict)  # Document metadata
    images: list[bytes] = field(default_factory=list)  # Extracted images (optional)
    page_count: int = 0

    # Quality metrics
    character_count: int = 0
    printable_ratio: float = 0.0

    def validate(self, min_length: int = 100, min_printable_ratio: float = 0.8) -> bool:
        """Check if extraction result meets quality thresholds.

        Args:
            min_length: Minimum character count for valid extraction
            min_printable_ratio: Minimum ratio of printable characters (0.0-1.0)

        Returns:
            True if extraction passes quality checks, False otherwise
        """
        if self.character_count < min_length:
            return False
        if self.printable_ratio < min_printable_ratio:
            return False
        return True

    @classmethod
    def from_text(cls, text: str, metadata: dict[str, Any] | None = None) -> "ExtractionResult":
        """Create an ExtractionResult from extracted text, computing quality metrics."""
        char_count = len(text)
        printable_count = sum(1 for c in text if c.isprintable() or c.isspace())
        printable_ratio = printable_count / char_count if char_count > 0 else 0.0

        return cls(
            text=text,
            metadata=metadata or {},
            character_count=char_count,
            printable_ratio=printable_ratio,
        )


@dataclass(frozen=True)
class AddResult:
    """Result of adding a document to the library.

    Supports idempotent add operations - duplicate detection returns
    existing records rather than erroring.
    """

    document: Document
    is_duplicate: bool = False  # True if returning existing record
    duplicate_reason: str | None = None  # "path" or "hash" if duplicate
```

**Step 2: Verify module is importable**

Run: `uv run python -c "from local_library.core.models import Document, DocumentStatus; d = Document.create_pending('/test.pdf', 'abc123', '/storage/ab/c1/abc123.pdf'); print(d.status)"`

Expected: `DocumentStatus.PENDING`

**Step 3: Commit**

```bash
git add src/local_library/core/models.py
git commit -m "feat: add core models for documents and operation results

- Document: frozen dataclass with lifecycle status, content hash, paths
- DocumentStatus: pending/ready/failed enum
- AcquisitionResult: content hash, temp path, original path
- ExtractionResult: text, metadata, quality validation
- AddResult: idempotent add support with duplicate detection

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create tests for models module

**Files:**
- Create: `tests/unit/test_models.py`

**Step 1: Create the test file**

```python
"""Unit tests for models module."""

from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest

from local_library.core.models import (
    AcquisitionResult,
    AddResult,
    Document,
    DocumentStatus,
    ExtractionResult,
)


class TestDocumentStatus:
    """Tests for DocumentStatus enum."""

    def test_status_values_are_strings(self) -> None:
        """Status values should be lowercase strings."""
        assert DocumentStatus.PENDING.value == "pending"
        assert DocumentStatus.READY.value == "ready"
        assert DocumentStatus.FAILED.value == "failed"


class TestDocument:
    """Tests for Document dataclass."""

    def test_create_pending_generates_uuid(self) -> None:
        """create_pending should generate a unique UUID."""
        doc = Document.create_pending("/path/to/file.pdf", "abc123", "/storage/ab/c1/abc123.pdf")

        assert isinstance(doc.id, UUID)

    def test_create_pending_sets_status_to_pending(self) -> None:
        """create_pending should set status to PENDING."""
        doc = Document.create_pending("/path/to/file.pdf", "abc123", "/storage/ab/c1/abc123.pdf")

        assert doc.status == DocumentStatus.PENDING

    def test_create_pending_sets_timestamps(self) -> None:
        """create_pending should set created_at and updated_at."""
        before = datetime.utcnow()
        doc = Document.create_pending("/path/to/file.pdf", "abc123", "/storage/ab/c1/abc123.pdf")
        after = datetime.utcnow()

        assert before <= doc.created_at <= after
        assert doc.created_at == doc.updated_at

    def test_create_pending_stores_paths(self) -> None:
        """create_pending should store original and storage paths."""
        doc = Document.create_pending(
            "/original/path.pdf", "hash123", "/storage/ha/sh/hash123.pdf"
        )

        assert doc.original_path == "/original/path.pdf"
        assert doc.storage_path == "/storage/ha/sh/hash123.pdf"
        assert doc.content_hash == "hash123"

    def test_nullable_fields_default_to_none(self) -> None:
        """Nullable fields should default to None."""
        doc = Document.create_pending("/path.pdf", "hash", "/storage/path.pdf")

        assert doc.extracted_path is None
        assert doc.citekey is None
        assert doc.csl_json is None
        assert doc.error_message is None
        assert doc.error_code is None

    def test_document_is_frozen(self) -> None:
        """Document should be immutable (frozen dataclass)."""
        doc = Document.create_pending("/path.pdf", "hash", "/storage/path.pdf")

        with pytest.raises(AttributeError):
            doc.status = DocumentStatus.READY  # type: ignore[misc]


class TestAcquisitionResult:
    """Tests for AcquisitionResult dataclass."""

    def test_stores_required_fields(self) -> None:
        """AcquisitionResult should store hash, temp path, and original path."""
        result = AcquisitionResult(
            content_hash="abc123",
            temp_path=Path("/tmp/file.pdf"),
            original_path="/original/file.pdf",
        )

        assert result.content_hash == "abc123"
        assert result.temp_path == Path("/tmp/file.pdf")
        assert result.original_path == "/original/file.pdf"

    def test_optional_fields_have_defaults(self) -> None:
        """Optional fields should have sensible defaults."""
        result = AcquisitionResult(
            content_hash="abc123",
            temp_path=Path("/tmp/file.pdf"),
            original_path="/original/file.pdf",
        )

        assert result.file_size == 0
        assert result.mime_type is None

    def test_acquisition_result_is_frozen(self) -> None:
        """AcquisitionResult should be immutable."""
        result = AcquisitionResult(
            content_hash="abc123",
            temp_path=Path("/tmp/file.pdf"),
            original_path="/original/file.pdf",
        )

        with pytest.raises(AttributeError):
            result.content_hash = "new_hash"  # type: ignore[misc]


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_from_text_computes_character_count(self) -> None:
        """from_text should compute character count."""
        result = ExtractionResult.from_text("Hello, World!")

        assert result.character_count == 13

    def test_from_text_computes_printable_ratio(self) -> None:
        """from_text should compute printable character ratio."""
        result = ExtractionResult.from_text("Hello")

        assert result.printable_ratio == 1.0

    def test_from_text_handles_empty_text(self) -> None:
        """from_text should handle empty text without division by zero."""
        result = ExtractionResult.from_text("")

        assert result.character_count == 0
        assert result.printable_ratio == 0.0

    def test_validate_passes_for_good_content(self) -> None:
        """validate should return True for content meeting thresholds."""
        result = ExtractionResult.from_text("x" * 200)

        assert result.validate(min_length=100, min_printable_ratio=0.8) is True

    def test_validate_fails_for_short_content(self) -> None:
        """validate should return False for content below min_length."""
        result = ExtractionResult.from_text("short")

        assert result.validate(min_length=100, min_printable_ratio=0.8) is False

    def test_validate_fails_for_low_printable_ratio(self) -> None:
        """validate should return False for content with too many non-printable chars."""
        # Create text with many non-printable characters
        text = "Hello" + "\x00" * 100  # null bytes are not printable
        result = ExtractionResult.from_text(text)

        assert result.validate(min_length=10, min_printable_ratio=0.8) is False

    def test_from_text_accepts_metadata(self) -> None:
        """from_text should accept optional metadata dict."""
        metadata = {"title": "Test Document", "author": "Test Author"}
        result = ExtractionResult.from_text("Content", metadata=metadata)

        assert result.metadata == metadata


class TestAddResult:
    """Tests for AddResult dataclass."""

    def test_stores_document(self) -> None:
        """AddResult should store the document."""
        doc = Document.create_pending("/path.pdf", "hash", "/storage/path.pdf")
        result = AddResult(document=doc)

        assert result.document == doc

    def test_is_duplicate_defaults_to_false(self) -> None:
        """is_duplicate should default to False."""
        doc = Document.create_pending("/path.pdf", "hash", "/storage/path.pdf")
        result = AddResult(document=doc)

        assert result.is_duplicate is False
        assert result.duplicate_reason is None

    def test_can_indicate_duplicate_by_path(self) -> None:
        """AddResult should support indicating duplicate by path."""
        doc = Document.create_pending("/path.pdf", "hash", "/storage/path.pdf")
        result = AddResult(document=doc, is_duplicate=True, duplicate_reason="path")

        assert result.is_duplicate is True
        assert result.duplicate_reason == "path"

    def test_can_indicate_duplicate_by_hash(self) -> None:
        """AddResult should support indicating duplicate by hash."""
        doc = Document.create_pending("/path.pdf", "hash", "/storage/path.pdf")
        result = AddResult(document=doc, is_duplicate=True, duplicate_reason="hash")

        assert result.is_duplicate is True
        assert result.duplicate_reason == "hash"
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_models.py -v`

Expected: All tests pass (approximately 20 tests)

**Step 3: Commit**

```bash
git add tests/unit/test_models.py
git commit -m "test: add unit tests for models module

- Tests for DocumentStatus enum values
- Tests for Document creation, timestamps, immutability
- Tests for AcquisitionResult fields and immutability
- Tests for ExtractionResult quality validation and metrics
- Tests for AddResult duplicate detection support

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

---

<!-- START_TASK_5 -->
### Task 5: Update core module exports

**Files:**
- Modify: `src/local_library/core/__init__.py`

**Step 1: Update the init file to export public API**

```python
"""Core module - models, storage, orchestration."""

from local_library.core.errors import (
    AcquisitionError,
    ErrorCode,
    ExtractionError,
    LocalLibraryError,
    LookupError,
    QualityError,
    StorageError,
)
from local_library.core.models import (
    AcquisitionResult,
    AddResult,
    Document,
    DocumentStatus,
    ExtractionResult,
)

__all__ = [
    # Errors
    "ErrorCode",
    "LocalLibraryError",
    "AcquisitionError",
    "ExtractionError",
    "QualityError",
    "StorageError",
    "LookupError",
    # Models
    "DocumentStatus",
    "Document",
    "AcquisitionResult",
    "ExtractionResult",
    "AddResult",
]
```

**Step 2: Verify imports work from core module**

Run: `uv run python -c "from local_library.core import Document, ErrorCode, AcquisitionError; print('All exports available')"`

Expected: `All exports available`

**Step 3: Run all tests to verify nothing broke**

Run: `uv run pytest tests/ -v`

Expected: All tests pass

**Step 4: Commit**

```bash
git add src/local_library/core/__init__.py
git commit -m "feat: export public API from core module

- Export all error types and ErrorCode enum
- Export all model types

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_5 -->

---

**Phase 2 Definition of Done:**
- Models can be instantiated (`Document.create_pending()` works)
- Exceptions can be raised with codes (`AcquisitionError("msg", ErrorCode.X)`)
- All tests pass
