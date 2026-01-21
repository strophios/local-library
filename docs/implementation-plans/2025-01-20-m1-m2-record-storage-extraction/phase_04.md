# Phase 4: Ingestion Protocols and FileAcquirer

## Goal
Implement acquisition abstraction and local file handling with protocol-based extensibility.

---

<!-- START_TASK_1 -->
### Task 1: Create protocol definitions

**Files:**
- Create: `src/local_library/ingestion/base.py`

**Step 1: Create the base module with protocol definitions**

```python
"""Protocol definitions for content acquisition and extraction."""

# pattern: Functional Core

from pathlib import Path
from typing import Protocol, runtime_checkable

from local_library.core.models import AcquisitionResult, ExtractionResult


@runtime_checkable
class ContentAcquirer(Protocol):
    """Protocol for acquiring content from various sources.

    Implementations handle specific source types (local files, URLs, etc.)
    and copy content to a temporary location for processing.
    """

    def can_handle(self, source: str) -> bool:
        """Check if this acquirer can handle the given source.

        Args:
            source: Source identifier (path, URL, etc.)

        Returns:
            True if this acquirer can handle the source
        """
        ...

    def validate(self, source: str) -> None:
        """Validate that the source is accessible and valid.

        Args:
            source: Source identifier to validate

        Raises:
            AcquisitionError: If source is invalid or inaccessible
        """
        ...

    def acquire(self, source: str, dest_dir: Path) -> AcquisitionResult:
        """Acquire content from source to destination directory.

        Copies/downloads the content and computes its hash.

        Args:
            source: Source identifier (path, URL, etc.)
            dest_dir: Directory to place the acquired file

        Returns:
            AcquisitionResult with hash, temp path, and metadata

        Raises:
            AcquisitionError: If acquisition fails
        """
        ...


@runtime_checkable
class ContentExtractor(Protocol):
    """Protocol for extracting text content from files.

    Implementations handle specific file formats (PDF, DOCX, etc.)
    and convert them to markdown text.
    """

    def can_handle(self, file_path: Path) -> bool:
        """Check if this extractor can handle the given file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if this extractor can handle the file
        """
        ...

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text content from file.

        Args:
            file_path: Path to the file to extract

        Returns:
            ExtractionResult with extracted text and metadata

        Raises:
            ExtractionError: If extraction fails
        """
        ...


def compute_storage_path(content_hash: str, extension: str, base_dir: Path) -> Path:
    """Compute content-addressable storage path.

    Uses Git-style layout: ab/cd/abcd1234...ext

    Args:
        content_hash: SHA-256 hash of the content
        extension: File extension (e.g., ".pdf")
        base_dir: Base directory for storage

    Returns:
        Full path for storing the file
    """
    # Git-style: first 2 chars / next 2 chars / full hash
    prefix1 = content_hash[:2]
    prefix2 = content_hash[2:4]
    filename = f"{content_hash}{extension}"

    return base_dir / prefix1 / prefix2 / filename
```

**Step 2: Verify module is importable**

Run: `uv run python -c "from local_library.ingestion.base import ContentAcquirer, ContentExtractor, compute_storage_path; print('Protocols loaded')"`

Expected: `Protocols loaded`

**Step 3: Commit**

```bash
git add src/local_library/ingestion/base.py
git commit -m "feat: add protocol definitions for acquirers and extractors

- ContentAcquirer protocol: can_handle, validate, acquire
- ContentExtractor protocol: can_handle, extract
- compute_storage_path() for content-addressable layout

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Implement FileAcquirer

**Files:**
- Create: `src/local_library/ingestion/file.py`

**Step 1: Create the FileAcquirer implementation**

```python
"""Local file acquisition implementation."""

# pattern: Imperative Shell

import hashlib
import shutil
from pathlib import Path

from local_library.core.errors import AcquisitionError, ErrorCode
from local_library.core.models import AcquisitionResult


class FileAcquirer:
    """Acquirer for local filesystem files.

    Validates file existence and readability, copies to destination,
    and computes SHA-256 content hash.
    """

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {".pdf"}

    def can_handle(self, source: str) -> bool:
        """Check if source is a local file path with supported extension.

        Args:
            source: Source path to check

        Returns:
            True if source is a local file path with supported extension
        """
        try:
            path = Path(source)
            # Check it's a file path (not URL) with supported extension
            return path.suffix.lower() in self.SUPPORTED_EXTENSIONS
        except (ValueError, OSError):
            return False

    def validate(self, source: str) -> None:
        """Validate that file exists and is readable.

        Args:
            source: Path to the file

        Raises:
            AcquisitionError: If file doesn't exist or isn't readable
        """
        path = Path(source)

        if not path.exists():
            raise AcquisitionError(
                f"file not found: {source}",
                ErrorCode.ACQUISITION_FILE_NOT_FOUND,
                details={"path": source},
            )

        if not path.is_file():
            raise AcquisitionError(
                f"not a file: {source}",
                ErrorCode.ACQUISITION_INVALID_FORMAT,
                details={"path": source},
            )

        # Check readability by attempting to open
        try:
            with open(path, "rb") as f:
                f.read(1)  # Read 1 byte to verify access
        except PermissionError as e:
            raise AcquisitionError(
                f"file not readable: {source}",
                ErrorCode.ACQUISITION_FILE_NOT_READABLE,
                details={"path": source},
            ) from e
        except OSError as e:
            raise AcquisitionError(
                f"cannot access file: {source}: {e}",
                ErrorCode.ACQUISITION_FILE_NOT_READABLE,
                details={"path": source},
            ) from e

        # Validate extension
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise AcquisitionError(
                f"unsupported file type: {path.suffix}",
                ErrorCode.ACQUISITION_INVALID_FORMAT,
                details={"path": source, "extension": path.suffix},
            )

    def acquire(self, source: str, dest_dir: Path) -> AcquisitionResult:
        """Copy file to destination and compute hash.

        Args:
            source: Path to the source file
            dest_dir: Directory to copy the file to

        Returns:
            AcquisitionResult with hash and temp path

        Raises:
            AcquisitionError: If copy fails
        """
        source_path = Path(source).resolve()

        # Compute hash while copying
        hasher = hashlib.sha256()
        file_size = 0

        # Determine destination filename (preserve extension)
        temp_filename = f"acquired{source_path.suffix}"
        temp_path = dest_dir / temp_filename

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)

            with open(source_path, "rb") as src_file:
                with open(temp_path, "wb") as dst_file:
                    while chunk := src_file.read(8192):
                        hasher.update(chunk)
                        dst_file.write(chunk)
                        file_size += len(chunk)

        except OSError as e:
            raise AcquisitionError(
                f"failed to copy file: {e}",
                ErrorCode.ACQUISITION_COPY_FAILED,
                details={"source": source, "dest": str(temp_path)},
            ) from e

        content_hash = hasher.hexdigest()

        return AcquisitionResult(
            content_hash=content_hash,
            temp_path=temp_path,
            original_path=str(source_path),
            file_size=file_size,
            mime_type="application/pdf",  # For now, only PDFs supported
        )


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file.

    Args:
        file_path: Path to the file

    Returns:
        Hex-encoded SHA-256 hash
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()
```

**Step 2: Verify FileAcquirer works**

Run: `uv run python -c "
from local_library.ingestion.file import FileAcquirer
from pathlib import Path
import tempfile

# Create a test PDF file
with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    test_file = tmpdir / 'test.pdf'
    test_file.write_bytes(b'%PDF-1.4 test content')

    acquirer = FileAcquirer()
    print(f'can_handle: {acquirer.can_handle(str(test_file))}')

    acquirer.validate(str(test_file))
    print('validate: passed')

    result = acquirer.acquire(str(test_file), tmpdir / 'acquired')
    print(f'hash: {result.content_hash[:16]}...')
    print(f'temp_path exists: {result.temp_path.exists()}')
"`

Expected:
```
can_handle: True
validate: passed
hash: <16-char-prefix>...
temp_path exists: True
```

**Step 3: Commit**

```bash
git add src/local_library/ingestion/file.py
git commit -m "feat: implement FileAcquirer for local file acquisition

- can_handle() checks for supported extensions
- validate() checks existence, is_file, readability
- acquire() copies file and computes SHA-256 hash
- compute_file_hash() utility function

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Create tests for protocols and FileAcquirer

**Files:**
- Create: `tests/unit/test_ingestion.py`

**Step 1: Create the test file**

```python
"""Unit tests for ingestion module."""

from pathlib import Path

import pytest

from local_library.core.errors import AcquisitionError, ErrorCode
from local_library.ingestion.base import (
    ContentAcquirer,
    ContentExtractor,
    compute_storage_path,
)
from local_library.ingestion.file import FileAcquirer, compute_file_hash


class TestComputeStoragePath:
    """Tests for compute_storage_path function."""

    def test_creates_nested_directory_structure(self, temp_dir: Path) -> None:
        """compute_storage_path should create ab/cd/abcd... structure."""
        content_hash = "abcdef1234567890"
        path = compute_storage_path(content_hash, ".pdf", temp_dir)

        assert path == temp_dir / "ab" / "cd" / "abcdef1234567890.pdf"

    def test_preserves_extension(self, temp_dir: Path) -> None:
        """compute_storage_path should preserve file extension."""
        path = compute_storage_path("abc123", ".txt", temp_dir)

        assert path.suffix == ".txt"

    def test_uses_full_hash_in_filename(self, temp_dir: Path) -> None:
        """compute_storage_path should use full hash in filename."""
        full_hash = "a" * 64  # SHA-256 length
        path = compute_storage_path(full_hash, ".pdf", temp_dir)

        assert path.name == f"{'a' * 64}.pdf"


class TestFileAcquirer:
    """Tests for FileAcquirer class."""

    @pytest.fixture
    def acquirer(self) -> FileAcquirer:
        """Provide a FileAcquirer instance."""
        return FileAcquirer()

    @pytest.fixture
    def sample_pdf(self, temp_dir: Path) -> Path:
        """Create a sample PDF file for testing."""
        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content for hashing")
        return pdf_path

    # --- can_handle tests ---

    def test_can_handle_pdf_file(self, acquirer: FileAcquirer, sample_pdf: Path) -> None:
        """can_handle should return True for PDF files."""
        assert acquirer.can_handle(str(sample_pdf)) is True

    def test_can_handle_uppercase_extension(self, acquirer: FileAcquirer, temp_dir: Path) -> None:
        """can_handle should handle uppercase extensions."""
        pdf_path = temp_dir / "sample.PDF"
        pdf_path.write_bytes(b"%PDF-1.4")

        assert acquirer.can_handle(str(pdf_path)) is True

    def test_cannot_handle_unsupported_extension(self, acquirer: FileAcquirer, temp_dir: Path) -> None:
        """can_handle should return False for unsupported extensions."""
        txt_path = temp_dir / "sample.txt"
        txt_path.write_text("test")

        assert acquirer.can_handle(str(txt_path)) is False

    def test_cannot_handle_no_extension(self, acquirer: FileAcquirer, temp_dir: Path) -> None:
        """can_handle should return False for files without extension."""
        no_ext = temp_dir / "sample"
        no_ext.write_text("test")

        assert acquirer.can_handle(str(no_ext)) is False

    # --- validate tests ---

    def test_validate_existing_file(self, acquirer: FileAcquirer, sample_pdf: Path) -> None:
        """validate should pass for existing readable file."""
        acquirer.validate(str(sample_pdf))  # Should not raise

    def test_validate_nonexistent_file(self, acquirer: FileAcquirer) -> None:
        """validate should raise for nonexistent file."""
        with pytest.raises(AcquisitionError) as exc_info:
            acquirer.validate("/nonexistent/path.pdf")

        assert exc_info.value.code == ErrorCode.ACQUISITION_FILE_NOT_FOUND

    def test_validate_directory(self, acquirer: FileAcquirer, temp_dir: Path) -> None:
        """validate should raise for directory path."""
        with pytest.raises(AcquisitionError) as exc_info:
            acquirer.validate(str(temp_dir))

        assert exc_info.value.code == ErrorCode.ACQUISITION_INVALID_FORMAT

    def test_validate_unsupported_extension(self, acquirer: FileAcquirer, temp_dir: Path) -> None:
        """validate should raise for unsupported extension."""
        txt_path = temp_dir / "sample.txt"
        txt_path.write_text("test")

        with pytest.raises(AcquisitionError) as exc_info:
            acquirer.validate(str(txt_path))

        assert exc_info.value.code == ErrorCode.ACQUISITION_INVALID_FORMAT

    # --- acquire tests ---

    def test_acquire_copies_file(self, acquirer: FileAcquirer, sample_pdf: Path, temp_dir: Path) -> None:
        """acquire should copy file to destination."""
        dest_dir = temp_dir / "dest"
        result = acquirer.acquire(str(sample_pdf), dest_dir)

        assert result.temp_path.exists()
        assert result.temp_path.read_bytes() == sample_pdf.read_bytes()

    def test_acquire_computes_correct_hash(self, acquirer: FileAcquirer, sample_pdf: Path, temp_dir: Path) -> None:
        """acquire should compute correct SHA-256 hash."""
        dest_dir = temp_dir / "dest"
        result = acquirer.acquire(str(sample_pdf), dest_dir)

        expected_hash = compute_file_hash(sample_pdf)
        assert result.content_hash == expected_hash

    def test_acquire_returns_original_path(self, acquirer: FileAcquirer, sample_pdf: Path, temp_dir: Path) -> None:
        """acquire should return resolved original path."""
        dest_dir = temp_dir / "dest"
        result = acquirer.acquire(str(sample_pdf), dest_dir)

        assert result.original_path == str(sample_pdf.resolve())

    def test_acquire_returns_file_size(self, acquirer: FileAcquirer, sample_pdf: Path, temp_dir: Path) -> None:
        """acquire should return correct file size."""
        dest_dir = temp_dir / "dest"
        result = acquirer.acquire(str(sample_pdf), dest_dir)

        assert result.file_size == sample_pdf.stat().st_size

    def test_acquire_creates_dest_directory(self, acquirer: FileAcquirer, sample_pdf: Path, temp_dir: Path) -> None:
        """acquire should create destination directory if needed."""
        dest_dir = temp_dir / "nested" / "dest"
        assert not dest_dir.exists()

        result = acquirer.acquire(str(sample_pdf), dest_dir)

        assert dest_dir.exists()
        assert result.temp_path.exists()


class TestComputeFileHash:
    """Tests for compute_file_hash function."""

    def test_computes_sha256(self, temp_dir: Path) -> None:
        """compute_file_hash should compute SHA-256 hash."""
        test_file = temp_dir / "test.txt"
        test_file.write_bytes(b"test content")

        hash_value = compute_file_hash(test_file)

        # SHA-256 is 64 hex chars
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_same_content_same_hash(self, temp_dir: Path) -> None:
        """compute_file_hash should return same hash for identical content."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"
        content = b"identical content"

        file1.write_bytes(content)
        file2.write_bytes(content)

        assert compute_file_hash(file1) == compute_file_hash(file2)

    def test_different_content_different_hash(self, temp_dir: Path) -> None:
        """compute_file_hash should return different hash for different content."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"

        file1.write_bytes(b"content one")
        file2.write_bytes(b"content two")

        assert compute_file_hash(file1) != compute_file_hash(file2)


class TestProtocolConformance:
    """Tests that implementations conform to protocols."""

    def test_file_acquirer_conforms_to_protocol(self) -> None:
        """FileAcquirer should satisfy ContentAcquirer protocol."""
        acquirer = FileAcquirer()

        # runtime_checkable allows isinstance checks
        assert isinstance(acquirer, ContentAcquirer)
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_ingestion.py -v`

Expected: All tests pass (approximately 18 tests)

**Step 3: Commit**

```bash
git add tests/unit/test_ingestion.py
git commit -m "test: add unit tests for ingestion module

- Tests for compute_storage_path() layout
- Tests for FileAcquirer can_handle, validate, acquire
- Tests for compute_file_hash()
- Tests for protocol conformance

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Update ingestion module exports

**Files:**
- Modify: `src/local_library/ingestion/__init__.py`

**Step 1: Update the init file to export public API**

```python
"""Ingestion module - content acquisition and extraction."""

from local_library.ingestion.base import (
    ContentAcquirer,
    ContentExtractor,
    compute_storage_path,
)
from local_library.ingestion.file import FileAcquirer, compute_file_hash

__all__ = [
    # Protocols
    "ContentAcquirer",
    "ContentExtractor",
    # Utilities
    "compute_storage_path",
    "compute_file_hash",
    # Implementations
    "FileAcquirer",
]
```

**Step 2: Verify imports work**

Run: `uv run python -c "from local_library.ingestion import FileAcquirer, ContentAcquirer, compute_storage_path; print('All ingestion exports available')"`

Expected: `All ingestion exports available`

**Step 3: Run all tests**

Run: `uv run pytest tests/ -v`

Expected: All tests pass

**Step 4: Commit**

```bash
git add src/local_library/ingestion/__init__.py
git commit -m "feat: export public API from ingestion module

- Export protocols: ContentAcquirer, ContentExtractor
- Export utilities: compute_storage_path, compute_file_hash
- Export implementations: FileAcquirer

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_4 -->

---

**Phase 4 Definition of Done:**
- FileAcquirer can validate paths (existence, readability, extension)
- FileAcquirer can copy files to content-addressable locations
- FileAcquirer computes SHA-256 hashes
- All acquirer tests pass
