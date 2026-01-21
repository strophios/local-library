# Phase 6: Library Orchestration

## Goal
Implement pipeline coordination with duplicate handling and --force support.

---

<!-- START_TASK_1 -->
### Task 1: Create Library orchestration class

**Files:**
- Create: `src/local_library/core/library.py`

**Step 1: Create the Library class**

```python
"""Library orchestration - coordinates acquisition, extraction, and storage."""

# pattern: Imperative Shell

import shutil
import sqlite3
import tempfile
from pathlib import Path
from uuid import UUID

from local_library.config import (
    ensure_directories,
    get_database_path,
    get_extracted_dir,
    get_storage_dir,
)
from local_library.core.errors import (
    AcquisitionError,
    ErrorCode,
    ExtractionError,
    LookupError,
    QualityError,
)
from local_library.core.models import AddResult, Document, DocumentStatus
from local_library.core.storage import (
    create_document,
    delete_document,
    get_connection,
    get_document_by_hash,
    get_document_by_id,
    get_document_by_path,
    get_documents_by_partial_id,
    init_schema,
    list_documents,
    update_document_status,
)
from local_library.ingestion.base import compute_storage_path
from local_library.ingestion.file import FileAcquirer
from local_library.ingestion.pdf import PdfExtractor


class Library:
    """Orchestrates document acquisition, extraction, and storage.

    The Library is the main entry point for all document operations.
    It coordinates the acquirer, extractor, and storage layers.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        storage_dir: Path | None = None,
        extracted_dir: Path | None = None,
    ) -> None:
        """Initialize the library.

        Args:
            db_path: Path to SQLite database (default: platformdirs user data)
            storage_dir: Directory for content-addressable storage (default: platformdirs)
            extracted_dir: Directory for extracted markdown (default: platformdirs)
        """
        # Use defaults from config if not specified
        self._db_path = db_path or get_database_path()
        self._storage_dir = storage_dir or get_storage_dir()
        self._extracted_dir = extracted_dir or get_extracted_dir()

        # Initialize components
        self._acquirer = FileAcquirer()
        self._extractor = PdfExtractor(lazy_load=True)

        # Ensure directories exist
        ensure_directories()

        # Initialize database
        self._conn = get_connection(self._db_path)
        init_schema(self._conn)

    @property
    def conn(self) -> sqlite3.Connection:
        """Get the database connection."""
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> "Library":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    # --- Add Pipeline ---

    def add(self, source: str, force: bool = False) -> AddResult:
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
        9. Update record status

        Args:
            source: Path to the source file
            force: If True, create failed record for inaccessible files

        Returns:
            AddResult containing the document and duplicate status

        Raises:
            AcquisitionError: If source is invalid and force=False
            ExtractionError: If extraction fails (record created with failed status)
        """
        # Check if we can handle this source
        if not self._acquirer.can_handle(source):
            raise AcquisitionError(
                f"unsupported source type: {source}",
                ErrorCode.ACQUISITION_INVALID_FORMAT,
                details={"source": source},
            )

        # Validate source (unless force mode)
        try:
            self._acquirer.validate(source)
        except AcquisitionError as e:
            if force:
                # Create failed record for inaccessible file
                return self._create_failed_record(source, e)
            raise

        # Check for duplicate by original path
        existing = get_document_by_path(self._conn, source)
        if existing:
            return AddResult(
                document=existing,
                is_duplicate=True,
                duplicate_reason="path",
            )

        # Acquire content to temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            acquisition = self._acquirer.acquire(source, temp_path)

            # Check for duplicate by content hash
            existing = get_document_by_hash(self._conn, acquisition.content_hash)
            if existing:
                return AddResult(
                    document=existing,
                    is_duplicate=True,
                    duplicate_reason="hash",
                )

            # Compute storage path and move file
            source_path = Path(source)
            storage_path = compute_storage_path(
                acquisition.content_hash,
                source_path.suffix.lower(),
                self._storage_dir,
            )
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(acquisition.temp_path), str(storage_path))

            # Create database record
            doc = create_document(
                self._conn,
                original_path=acquisition.original_path,
                content_hash=acquisition.content_hash,
                storage_path=str(storage_path),
            )

        # Extract text content
        try:
            result = self._extractor.extract_and_validate(storage_path)

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

    def _create_failed_record(
        self, source: str, error: AcquisitionError
    ) -> AddResult:
        """Create a failed record for an inaccessible file.

        Used when --force is specified for files that can't be accessed.

        Args:
            source: Original source path
            error: The acquisition error that occurred

        Returns:
            AddResult with failed document
        """
        # Generate a placeholder hash from the path
        import hashlib

        placeholder_hash = hashlib.sha256(source.encode()).hexdigest()

        # Check if we already have a failed record for this path
        existing = get_document_by_path(self._conn, source)
        if existing:
            return AddResult(
                document=existing,
                is_duplicate=True,
                duplicate_reason="path",
            )

        # Create placeholder storage path (file won't exist)
        storage_path = compute_storage_path(
            placeholder_hash,
            Path(source).suffix.lower() or ".pdf",
            self._storage_dir,
        )

        # Create record with failed status
        doc = create_document(
            self._conn,
            original_path=source,
            content_hash=placeholder_hash,
            storage_path=str(storage_path),
        )

        doc = update_document_status(
            self._conn,
            doc.id,
            DocumentStatus.FAILED,
            error_message=error.message,
            error_code=error.code.value,
        )

        return AddResult(document=doc)

    # --- Query Operations ---

    def get(self, doc_id: str) -> Document:
        """Get a document by ID (supports partial UUID matching).

        Args:
            doc_id: Full or partial UUID

        Returns:
            The matching document

        Raises:
            LookupError: If no document found or multiple matches for partial ID
        """
        # Try as full UUID first
        try:
            full_uuid = UUID(doc_id)
            doc = get_document_by_id(self._conn, full_uuid)
            if doc:
                return doc
        except ValueError:
            pass  # Not a valid UUID, try partial match

        # Try partial match
        matches = get_documents_by_partial_id(self._conn, doc_id)

        if len(matches) == 0:
            raise LookupError(
                f"document not found: {doc_id}",
                ErrorCode.NOT_FOUND,
                details={"id": doc_id},
            )

        if len(matches) > 1:
            raise LookupError(
                f"ambiguous ID prefix: {doc_id} matches {len(matches)} documents",
                ErrorCode.AMBIGUOUS_MATCH,
                details={"id": doc_id, "match_count": len(matches)},
            )

        return matches[0]

    def list(self, status: DocumentStatus | None = None) -> list[Document]:
        """List all documents, optionally filtered by status.

        Args:
            status: Filter by status if provided

        Returns:
            List of documents, ordered by created_at descending
        """
        return list_documents(self._conn, status=status)

    def delete(self, doc_id: str, delete_files: bool = True) -> bool:
        """Delete a document and optionally its files.

        Args:
            doc_id: Full or partial UUID
            delete_files: If True, also delete storage and extracted files

        Returns:
            True if document was deleted

        Raises:
            LookupError: If document not found
        """
        doc = self.get(doc_id)

        if delete_files:
            # Delete storage file
            storage_path = Path(doc.storage_path)
            if storage_path.exists():
                storage_path.unlink()

            # Delete extracted file
            if doc.extracted_path:
                extracted_path = Path(doc.extracted_path)
                if extracted_path.exists():
                    extracted_path.unlink()

        return delete_document(self._conn, doc.id)
```

**Step 2: Verify module is importable**

Run: `uv run python -c "from local_library.core.library import Library; print('Library loaded')"`

Expected: `Library loaded`

**Step 3: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "feat: add Library orchestration class

- add(): full pipeline with duplicate detection and idempotent behavior
- get(): lookup by full or partial UUID
- list(): list all documents with optional status filter
- delete(): remove document and optionally its files
- --force support for creating failed records
- Context manager support for clean resource management

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Create tests for Library orchestration

**Files:**
- Create: `tests/unit/test_library.py`

**Step 1: Create the test file**

```python
"""Unit tests for Library orchestration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from local_library.core.errors import AcquisitionError, ErrorCode, LookupError
from local_library.core.library import Library
from local_library.core.models import DocumentStatus


class TestLibraryInit:
    """Tests for Library initialization."""

    def test_creates_database(self, temp_dir: Path) -> None:
        """Library should create database on init."""
        db_path = temp_dir / "test.db"

        with Library(
            db_path=db_path,
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        ) as lib:
            assert db_path.exists()

    def test_context_manager_closes_connection(self, temp_dir: Path) -> None:
        """Library should close connection on context exit."""
        db_path = temp_dir / "test.db"

        with Library(
            db_path=db_path,
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        ) as lib:
            conn = lib.conn

        # Connection should be closed after context exit
        # Attempting to use it should fail
        with pytest.raises(Exception):
            conn.execute("SELECT 1")


class TestLibraryAdd:
    """Tests for Library.add() method."""

    @pytest.fixture
    def library(self, temp_dir: Path) -> Library:
        """Provide an initialized Library for testing."""
        return Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        )

    @pytest.fixture
    def sample_pdf(self, temp_dir: Path) -> Path:
        """Create a sample PDF file for testing."""
        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content for extraction")
        return pdf_path

    def test_add_unsupported_format_raises(self, library: Library, temp_dir: Path) -> None:
        """add() should raise for unsupported file formats."""
        txt_file = temp_dir / "test.txt"
        txt_file.write_text("test")

        with pytest.raises(AcquisitionError) as exc_info:
            library.add(str(txt_file))

        assert exc_info.value.code == ErrorCode.ACQUISITION_INVALID_FORMAT

    def test_add_nonexistent_file_raises(self, library: Library) -> None:
        """add() should raise for nonexistent file."""
        with pytest.raises(AcquisitionError) as exc_info:
            library.add("/nonexistent/path.pdf")

        assert exc_info.value.code == ErrorCode.ACQUISITION_FILE_NOT_FOUND

    def test_add_nonexistent_with_force_creates_failed_record(
        self, library: Library
    ) -> None:
        """add() with force=True should create failed record for inaccessible files."""
        result = library.add("/nonexistent/path.pdf", force=True)

        assert result.document is not None
        assert result.document.status == DocumentStatus.FAILED
        assert result.is_duplicate is False

    def test_add_duplicate_path_returns_existing(
        self, library: Library, sample_pdf: Path
    ) -> None:
        """add() should return existing record for duplicate path."""
        # Mock the extractor to avoid loading Marker
        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content" * 20)

            # First add
            result1 = library.add(str(sample_pdf))
            assert result1.is_duplicate is False

            # Second add of same path
            result2 = library.add(str(sample_pdf))
            assert result2.is_duplicate is True
            assert result2.duplicate_reason == "path"
            assert result2.document.id == result1.document.id

    def test_add_duplicate_hash_returns_existing(
        self, library: Library, temp_dir: Path
    ) -> None:
        """add() should return existing record for duplicate content hash."""
        # Create two files with identical content
        content = b"%PDF-1.4 identical content"
        file1 = temp_dir / "file1.pdf"
        file2 = temp_dir / "file2.pdf"
        file1.write_bytes(content)
        file2.write_bytes(content)

        # Mock the extractor
        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content" * 20)

            # First add
            result1 = library.add(str(file1))
            assert result1.is_duplicate is False

            # Second add of different file with same content
            result2 = library.add(str(file2))
            assert result2.is_duplicate is True
            assert result2.duplicate_reason == "hash"


class TestLibraryGet:
    """Tests for Library.get() method."""

    @pytest.fixture
    def library_with_doc(self, temp_dir: Path) -> tuple[Library, str]:
        """Provide a Library with one document added."""
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        )

        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")

        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content" * 20)
            result = library.add(str(pdf_path))

        return library, str(result.document.id)

    def test_get_by_full_id(self, library_with_doc: tuple[Library, str]) -> None:
        """get() should find document by full UUID."""
        library, doc_id = library_with_doc

        doc = library.get(doc_id)

        assert str(doc.id) == doc_id

    def test_get_by_partial_id(self, library_with_doc: tuple[Library, str]) -> None:
        """get() should find document by partial UUID prefix."""
        library, doc_id = library_with_doc
        partial_id = doc_id[:8]

        doc = library.get(partial_id)

        assert str(doc.id) == doc_id

    def test_get_not_found_raises(self, library_with_doc: tuple[Library, str]) -> None:
        """get() should raise LookupError for nonexistent ID."""
        library, _ = library_with_doc

        with pytest.raises(LookupError) as exc_info:
            library.get("nonexistent-id")

        assert exc_info.value.code == ErrorCode.NOT_FOUND


class TestLibraryList:
    """Tests for Library.list() method."""

    @pytest.fixture
    def library(self, temp_dir: Path) -> Library:
        """Provide an initialized Library."""
        return Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        )

    def test_list_empty_returns_empty(self, library: Library) -> None:
        """list() should return empty list when no documents."""
        docs = library.list()

        assert docs == []

    def test_list_returns_all_documents(self, library: Library, temp_dir: Path) -> None:
        """list() should return all documents."""
        # Create two PDFs
        pdf1 = temp_dir / "doc1.pdf"
        pdf2 = temp_dir / "doc2.pdf"
        pdf1.write_bytes(b"%PDF-1.4 content one")
        pdf2.write_bytes(b"%PDF-1.4 content two")

        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content" * 20)
            library.add(str(pdf1))
            library.add(str(pdf2))

        docs = library.list()

        assert len(docs) == 2

    def test_list_filters_by_status(self, library: Library, temp_dir: Path) -> None:
        """list() should filter by status when provided."""
        # Create one successful and one failed document
        pdf1 = temp_dir / "success.pdf"
        pdf1.write_bytes(b"%PDF-1.4 success content")

        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content" * 20)
            library.add(str(pdf1))

        # Create failed record
        library.add("/nonexistent/failed.pdf", force=True)

        ready_docs = library.list(status=DocumentStatus.READY)
        failed_docs = library.list(status=DocumentStatus.FAILED)

        assert len(ready_docs) == 1
        assert len(failed_docs) == 1
        assert ready_docs[0].status == DocumentStatus.READY
        assert failed_docs[0].status == DocumentStatus.FAILED


class TestLibraryDelete:
    """Tests for Library.delete() method."""

    @pytest.fixture
    def library_with_doc(self, temp_dir: Path) -> tuple[Library, str, Path]:
        """Provide a Library with one document and its storage path."""
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        )

        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")

        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content" * 20)
            result = library.add(str(pdf_path))

        return library, str(result.document.id), Path(result.document.storage_path)

    def test_delete_removes_document(
        self, library_with_doc: tuple[Library, str, Path]
    ) -> None:
        """delete() should remove document from database."""
        library, doc_id, _ = library_with_doc

        result = library.delete(doc_id)

        assert result is True
        with pytest.raises(LookupError):
            library.get(doc_id)

    def test_delete_removes_files(
        self, library_with_doc: tuple[Library, str, Path]
    ) -> None:
        """delete() should remove storage files by default."""
        library, doc_id, storage_path = library_with_doc
        assert storage_path.exists()

        library.delete(doc_id, delete_files=True)

        assert not storage_path.exists()

    def test_delete_keeps_files_when_requested(
        self, library_with_doc: tuple[Library, str, Path]
    ) -> None:
        """delete() should keep files when delete_files=False."""
        library, doc_id, storage_path = library_with_doc
        assert storage_path.exists()

        library.delete(doc_id, delete_files=False)

        assert storage_path.exists()

    def test_delete_not_found_raises(self, library_with_doc: tuple[Library, str, Path]) -> None:
        """delete() should raise LookupError for nonexistent ID."""
        library, _, _ = library_with_doc

        with pytest.raises(LookupError) as exc_info:
            library.delete("nonexistent")

        assert exc_info.value.code == ErrorCode.NOT_FOUND
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_library.py -v`

Expected: All tests pass (approximately 18 tests)

**Step 3: Commit**

```bash
git add tests/unit/test_library.py
git commit -m "test: add unit tests for Library orchestration

- Tests for initialization and context management
- Tests for add() pipeline with duplicates and force mode
- Tests for get() with full and partial ID lookup
- Tests for list() with status filtering
- Tests for delete() with file cleanup options

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Update core module exports

**Files:**
- Modify: `src/local_library/core/__init__.py`

**Step 1: Add Library to exports**

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
from local_library.core.library import Library
from local_library.core.models import (
    AcquisitionResult,
    AddResult,
    Document,
    DocumentStatus,
    ExtractionResult,
)
from local_library.core.storage import (
    create_document,
    delete_document,
    get_connection,
    get_document_by_hash,
    get_document_by_id,
    get_document_by_path,
    get_documents_by_partial_id,
    init_schema,
    list_documents,
    transaction,
    update_document_status,
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
    # Storage
    "get_connection",
    "init_schema",
    "transaction",
    "create_document",
    "get_document_by_id",
    "get_document_by_hash",
    "get_document_by_path",
    "get_documents_by_partial_id",
    "list_documents",
    "update_document_status",
    "delete_document",
    # Orchestration
    "Library",
]
```

**Step 2: Verify imports work**

Run: `uv run python -c "from local_library.core import Library; print('Library exported')"`

Expected: `Library exported`

**Step 3: Run all tests**

Run: `uv run pytest tests/ -v`

Expected: All tests pass

**Step 4: Commit**

```bash
git add src/local_library/core/__init__.py
git commit -m "feat: export Library from core module

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_3 -->

---

**Phase 6 Definition of Done:**
- Full add pipeline works (acquire → extract → store)
- Duplicates return existing record (idempotent behavior)
- --force creates failed records for inaccessible files
- All orchestration tests pass
