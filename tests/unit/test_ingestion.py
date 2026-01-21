"""Unit tests for ingestion module."""

from pathlib import Path

import pytest

from local_library.core.errors import AcquisitionError, ErrorCode
from local_library.ingestion.base import (
    ContentAcquirer,
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

    def test_cannot_handle_unsupported_extension(
        self, acquirer: FileAcquirer, temp_dir: Path
    ) -> None:
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

    def test_acquire_copies_file(
        self, acquirer: FileAcquirer, sample_pdf: Path, temp_dir: Path
    ) -> None:
        """acquire should copy file to destination."""
        dest_dir = temp_dir / "dest"
        result = acquirer.acquire(str(sample_pdf), dest_dir)

        assert result.temp_path.exists()
        assert result.temp_path.read_bytes() == sample_pdf.read_bytes()

    def test_acquire_computes_correct_hash(
        self, acquirer: FileAcquirer, sample_pdf: Path, temp_dir: Path
    ) -> None:
        """acquire should compute correct SHA-256 hash."""
        dest_dir = temp_dir / "dest"
        result = acquirer.acquire(str(sample_pdf), dest_dir)

        expected_hash = compute_file_hash(sample_pdf)
        assert result.content_hash == expected_hash

    def test_acquire_returns_original_path(
        self, acquirer: FileAcquirer, sample_pdf: Path, temp_dir: Path
    ) -> None:
        """acquire should return resolved original path."""
        dest_dir = temp_dir / "dest"
        result = acquirer.acquire(str(sample_pdf), dest_dir)

        assert result.original_path == str(sample_pdf.resolve())

    def test_acquire_returns_file_size(
        self, acquirer: FileAcquirer, sample_pdf: Path, temp_dir: Path
    ) -> None:
        """acquire should return correct file size."""
        dest_dir = temp_dir / "dest"
        result = acquirer.acquire(str(sample_pdf), dest_dir)

        assert result.file_size == sample_pdf.stat().st_size

    def test_acquire_creates_dest_directory(
        self, acquirer: FileAcquirer, sample_pdf: Path, temp_dir: Path
    ) -> None:
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
