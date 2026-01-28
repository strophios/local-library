"""Unit tests for Library orchestration."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from local_library.core.errors import AcquisitionError, ErrorCode, ExtractionError, LookupError
from local_library.core.library import Library
from local_library.core.models import DocumentStatus
from local_library.ingestion.file import FileAcquirer
from local_library.ingestion.pdf import PdfExtractor


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

    def test_default_acquirers_includes_file_acquirer(self, temp_dir: Path) -> None:
        """Library should have FileAcquirer in default acquirers list."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        ) as lib:
            assert len(lib._acquirers) == 1
            assert isinstance(lib._acquirers[0], FileAcquirer)

    def test_default_extractors_includes_pdf_extractor(self, temp_dir: Path) -> None:
        """Library should have PdfExtractor in default extractors list."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        ) as lib:
            assert len(lib._extractors) == 1
            assert isinstance(lib._extractors[0], PdfExtractor)

    def test_custom_acquirers_override_defaults(self, temp_dir: Path) -> None:
        """Library should use custom acquirers when provided."""
        custom_acquirer = FileAcquirer()  # Could be any ContentAcquirer

        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            acquirers=[custom_acquirer],
        ) as lib:
            assert lib._acquirers == [custom_acquirer]

    def test_custom_extractors_override_defaults(self, temp_dir: Path) -> None:
        """Library should use custom extractors when provided."""
        custom_extractor = PdfExtractor(lazy_load=True)  # Could be any ContentExtractor

        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            extractors=[custom_extractor],
        ) as lib:
            assert lib._extractors == [custom_extractor]

    def test_empty_acquirers_list_is_valid(self, temp_dir: Path) -> None:
        """Library should accept empty acquirers list (all sources will fail)."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            acquirers=[],
        ) as lib:
            assert lib._acquirers == []

    def test_empty_extractors_list_is_valid(self, temp_dir: Path) -> None:
        """Library should accept empty extractors list (all extractions will fail)."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            extractors=[],
        ) as lib:
            assert lib._extractors == []


class TestLibraryDispatch:
    """Tests for Library dispatch methods."""

    @pytest.fixture
    def library(self, temp_dir: Path) -> Library:
        """Provide an initialized Library for testing."""
        return Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
        )

    def test_find_acquirer_returns_handler_for_pdf(self, library: Library, temp_dir: Path) -> None:
        """_find_acquirer should return handler for supported PDF path."""
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test")

        acquirer = library._find_acquirer(str(pdf_path))

        assert acquirer is not None
        assert acquirer.can_handle(str(pdf_path))

    def test_find_acquirer_raises_for_unsupported_source(self, library: Library) -> None:
        """_find_acquirer should raise for unsupported source type."""
        with pytest.raises(AcquisitionError) as exc_info:
            library._find_acquirer("https://example.com/doc.html")

        assert exc_info.value.code == ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE

    def test_find_extractor_returns_handler_for_pdf(self, library: Library, temp_dir: Path) -> None:
        """_find_extractor should return handler for PDF file."""
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test")

        extractor = library._find_extractor(pdf_path)

        assert extractor is not None
        assert extractor.can_handle(pdf_path)

    def test_find_extractor_raises_for_unsupported_format(
        self, library: Library, temp_dir: Path
    ) -> None:
        """_find_extractor should raise for unsupported file format."""
        txt_path = temp_dir / "test.txt"
        txt_path.write_text("plain text")

        with pytest.raises(ExtractionError) as exc_info:
            library._find_extractor(txt_path)

        assert exc_info.value.code == ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT


class TestLibraryAdd:
    """Tests for Library.add() method."""

    @pytest.fixture
    def library(self, temp_dir: Path) -> Library:
        """Provide an initialized Library for testing."""
        return Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
        )

    @pytest.fixture
    def sample_pdf(self, temp_dir: Path) -> Path:
        """Create a sample PDF file for testing."""
        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content for extraction")
        return pdf_path

    def test_add_unsupported_source_raises(self, library: Library) -> None:
        """add() should raise for sources no acquirer can handle."""
        # URL is not handled by FileAcquirer
        with pytest.raises(AcquisitionError) as exc_info:
            library.add("https://example.com/doc.pdf")

        assert exc_info.value.code == ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE

    def test_add_unsupported_format_raises(self, library: Library, temp_dir: Path) -> None:
        """add() should raise for unsupported file formats."""
        txt_file = temp_dir / "test.txt"
        txt_file.write_text("test")

        with pytest.raises(ExtractionError) as exc_info:
            library.add(str(txt_file))

        assert exc_info.value.code == ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT

    def test_add_nonexistent_file_raises(self, library: Library) -> None:
        """add() should raise for nonexistent file."""
        with pytest.raises(AcquisitionError) as exc_info:
            library.add("/nonexistent/path.pdf")

        assert exc_info.value.code == ErrorCode.ACQUISITION_FILE_NOT_FOUND

    def test_add_nonexistent_with_force_creates_failed_record(self, library: Library) -> None:
        """add() with force=True should create failed record for inaccessible files."""
        result = library.add("/nonexistent/path.pdf", force=True)

        assert result.document is not None
        assert result.document.status == DocumentStatus.FAILED
        assert result.is_duplicate is False

    def test_add_duplicate_path_returns_existing(self, library: Library, sample_pdf: Path) -> None:
        """add() should return existing record for duplicate path."""
        # Mock the extractor to avoid loading Marker
        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content" * 20)

            # First add
            result1 = library.add(str(sample_pdf))
            assert result1.is_duplicate is False

            # Second add of same path
            result2 = library.add(str(sample_pdf))
            assert result2.is_duplicate is True
            assert result2.duplicate_reason == "path"
            assert result2.document.id == result1.document.id

    def test_add_duplicate_hash_returns_existing(self, library: Library, temp_dir: Path) -> None:
        """add() should return existing record for duplicate content hash."""
        # Create two files with identical content
        content = b"%PDF-1.4 identical content"
        file1 = temp_dir / "file1.pdf"
        file2 = temp_dir / "file2.pdf"
        file1.write_bytes(content)
        file2.write_bytes(content)

        # Mock the extractor
        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content" * 20)

            # First add
            result1 = library.add(str(file1))
            assert result1.is_duplicate is False

            # Second add of different file with same content
            result2 = library.add(str(file2))
            assert result2.is_duplicate is True
            assert result2.duplicate_reason == "hash"

    def test_add_unsupported_content_type_creates_failed_record(self, temp_dir: Path) -> None:
        """add() should create failed record when no extractor can handle content."""
        # Create library with empty extractors list
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            extractors=[],  # No extractors - nothing can be extracted
        )

        # Create a file that can be acquired but not extracted
        txt_file = temp_dir / "test.txt"
        txt_file.write_text("test content")

        with pytest.raises(ExtractionError) as exc_info:
            library.add(str(txt_file))

        assert exc_info.value.code == ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT

        # Verify a failed record was created
        docs = library.list(status=DocumentStatus.FAILED)
        assert len(docs) == 1
        assert docs[0].error_code == ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT.value

        # Verify the storage file was preserved
        storage_path = Path(docs[0].storage_path)
        assert storage_path.exists()

        library.close()

    def test_add_preserves_file_when_no_extractor_available(self, temp_dir: Path) -> None:
        """add() should preserve acquired file even when extraction fails."""
        # Create library with no extractors
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            extractors=[],
        )

        # Create file
        pdf_file = temp_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")

        try:
            library.add(str(pdf_file))
        except ExtractionError:
            pass  # Expected

        # File should exist in storage
        docs = library.list()
        assert len(docs) == 1
        storage_file = Path(docs[0].storage_path)
        assert storage_file.exists()
        assert storage_file.read_bytes() == b"%PDF-1.4 content"

        library.close()


class TestLibraryGet:
    """Tests for Library.get() method."""

    @pytest.fixture
    def library_with_doc(self, temp_dir: Path) -> tuple[Library, str]:
        """Provide a Library with one document added."""
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
        )

        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")

        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
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
            text_extraction_enabled=False,
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

        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
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

        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
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
            text_extraction_enabled=False,
        )

        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")

        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content" * 20)
            result = library.add(str(pdf_path))

        return library, str(result.document.id), Path(result.document.storage_path)

    def test_delete_removes_document(self, library_with_doc: tuple[Library, str, Path]) -> None:
        """delete() should remove document from database."""
        library, doc_id, _ = library_with_doc

        result = library.delete(doc_id)

        assert result is True
        with pytest.raises(LookupError):
            library.get(doc_id)

    def test_delete_removes_files(self, library_with_doc: tuple[Library, str, Path]) -> None:
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


class TestLibraryPdfLLMConfiguration:
    """Tests for Library PDF LLM extraction configuration."""

    def test_pdf_llm_enabled_default_false(self, temp_dir: Path) -> None:
        """Library should default to pdf_llm_enabled=False."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        ) as lib:
            # Check the default PdfExtractor was created with llm_enabled=False
            assert len(lib._extractors) == 1
            assert isinstance(lib._extractors[0], PdfExtractor)
            assert lib._extractors[0]._llm_enabled is False

    def test_pdf_llm_enabled_passed_to_extractor(self, temp_dir: Path) -> None:
        """Library should pass pdf_llm_enabled=True to PdfExtractor."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            pdf_llm_enabled=True,
        ) as lib:
            # Check the PdfExtractor was created with llm_enabled=True
            assert len(lib._extractors) == 1
            assert isinstance(lib._extractors[0], PdfExtractor)
            assert lib._extractors[0]._llm_enabled is True

    def test_custom_extractors_not_affected_by_pdf_llm_enabled(
        self, temp_dir: Path
    ) -> None:
        """Custom extractors should not be affected by pdf_llm_enabled."""
        # Create a custom extractor with llm_enabled=False
        custom_extractor = PdfExtractor(lazy_load=True, llm_enabled=False)

        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            extractors=[custom_extractor],
            pdf_llm_enabled=True,  # Should be ignored
        ) as lib:
            # Custom extractor should be used as-is
            assert lib._extractors == [custom_extractor]
            assert lib._extractors[0]._llm_enabled is False
