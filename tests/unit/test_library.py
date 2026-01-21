"""Unit tests for Library orchestration."""

import sqlite3
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
        ):
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
        with pytest.raises(sqlite3.ProgrammingError):
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
