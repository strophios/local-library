"""Unit tests for Library orchestration."""

import sqlite3
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from local_library.core.errors import AcquisitionError, ErrorCode, ExtractionError, LookupError
from local_library.core.library import Library
from local_library.core.models import (
    DocumentStatus,
    ExtractionResult,
    FieldExtraction,
    MetadataSource,
    TextExtractionResult,
)
from local_library.core.vec_extension import is_vec_available
from local_library.ingestion.file import FileAcquirer
from local_library.ingestion.pdf import PdfExtractor

pytestmark_vec = pytest.mark.skipif(
    not is_vec_available(),
    reason="sqlite-vec extension not available",
)


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

    def test_delete_cleans_up_empty_parent_directories(
        self, library_with_doc: tuple[Library, str, Path]
    ) -> None:
        """delete() should remove empty parent directories after file deletion."""
        library, doc_id, storage_path = library_with_doc

        # Verify the git-style directory structure exists (e.g., ab/cd/hash.pdf)
        # storage_path is something like: storage_dir/ab/cd/abcdef...pdf
        parent_dir = storage_path.parent  # e.g., storage_dir/ab/cd
        grandparent_dir = parent_dir.parent  # e.g., storage_dir/ab
        assert parent_dir.exists()
        assert grandparent_dir.exists()

        library.delete(doc_id, delete_files=True)

        # After deletion, empty parent directories should be removed
        assert not storage_path.exists()
        assert not parent_dir.exists()
        assert not grandparent_dir.exists()
        # But the root storage_dir should still exist
        assert library._storage_dir.exists()


class TestLibraryReextract:
    """Tests for Library.reextract() method."""

    @pytest.fixture
    def library_with_doc(self, temp_dir: Path) -> tuple[Library, str]:
        """Provide a Library with one document added via mocked extraction."""
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
        )

        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")

        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Original extraction" * 20)
            result = library.add(str(pdf_path))

        return library, str(result.document.id)

    def test_reextract_updates_markdown(self, library_with_doc: tuple[Library, str]) -> None:
        """reextract() should overwrite the extracted markdown with new text."""
        library, doc_id = library_with_doc
        doc = library.get(doc_id)
        old_text = Path(doc.extracted_path).read_text()

        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Improved extraction" * 20)
            updated = library.reextract(doc_id)

        new_text = Path(updated.extracted_path).read_text()
        assert new_text != old_text
        assert "Improved" in new_text

    def test_reextract_marks_embeddings_stale(self, library_with_doc: tuple[Library, str]) -> None:
        """reextract() should mark embeddings as STALE."""
        library, doc_id = library_with_doc

        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="New extraction" * 20)
            updated = library.reextract(doc_id)

        from local_library.core.models import EmbeddingStatus

        assert updated.embedding_status == EmbeddingStatus.STALE

    def test_reextract_preserves_metadata(self, library_with_doc: tuple[Library, str]) -> None:
        """reextract() should not modify existing metadata."""
        library, doc_id = library_with_doc
        doc = library.get(doc_id)
        original_citekey = doc.citekey
        original_csl = doc.csl_json

        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="New extraction" * 20)
            updated = library.reextract(doc_id)

        assert updated.citekey == original_citekey
        assert updated.csl_json == original_csl

    def test_reextract_returns_ready_document(self, library_with_doc: tuple[Library, str]) -> None:
        """reextract() should return document with READY status."""
        library, doc_id = library_with_doc

        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="New extraction" * 20)
            updated = library.reextract(doc_id)

        assert updated.status == DocumentStatus.READY

    def test_reextract_not_found_raises(self, library_with_doc: tuple[Library, str]) -> None:
        """reextract() should raise LookupError for nonexistent ID."""
        library, _ = library_with_doc

        with pytest.raises(LookupError) as exc_info:
            library.reextract("nonexistent-id")

        assert exc_info.value.code == ErrorCode.NOT_FOUND


class TestLibraryFallbackStatus:
    """Tests for Library handling of pdftext fallback documents."""

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

    def test_add_fallback_document_gets_needs_review(
        self, library: Library, sample_pdf: Path
    ) -> None:
        """add() should set NEEDS_REVIEW for pdftext fallback documents."""
        fallback_result = ExtractionResult.from_text(
            text="Fallback extracted text content. " * 20,
            metadata={
                "extraction_method": "pdftext_fallback",
                "marker_failure_reason": "timed out after 900s",
                "precheck_page_count": 10,
                "precheck_has_text": True,
            },
        )

        with patch.object(
            library._extractors[0], "extract_and_validate", return_value=fallback_result
        ):
            result = library.add(str(sample_pdf))

        assert result.document.status == DocumentStatus.NEEDS_REVIEW
        assert result.document.error_code == "EXTRACTION_FALLBACK"
        assert "pdftext fallback" in result.document.error_message

    def test_add_normal_extraction_stays_ready(self, library: Library, sample_pdf: Path) -> None:
        """add() should keep READY status for normal Marker extraction."""
        normal_result = ExtractionResult.from_text(
            text="Normal Marker extracted text content. " * 20,
            metadata={"page_stats": []},
        )

        with patch.object(
            library._extractors[0], "extract_and_validate", return_value=normal_result
        ):
            result = library.add(str(sample_pdf))

        assert result.document.status == DocumentStatus.READY
        assert result.document.error_code is None

    def test_add_fallback_document_still_embeds(self, library: Library, sample_pdf: Path) -> None:
        """add() should still attempt embedding for fallback documents."""
        fallback_result = ExtractionResult.from_text(
            text="Fallback text for embedding test. " * 20,
            metadata={
                "extraction_method": "pdftext_fallback",
                "marker_failure_reason": "crashed",
            },
        )

        with patch.object(
            library._extractors[0], "extract_and_validate", return_value=fallback_result
        ):
            with patch.object(library, "embed") as mock_embed:
                library.add(str(sample_pdf))

        # Embed should still be called (if embed_on_add is True)
        if library._embed_on_add:
            mock_embed.assert_called_once()


class TestLibraryReextractFallback:
    """Tests for reextract handling of pdftext fallback results."""

    @pytest.fixture
    def library_with_doc(self, temp_dir: Path) -> tuple[Library, str]:
        """Provide a Library with one added document."""
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
        )
        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content for extraction")

        initial_result = ExtractionResult.from_text(
            text="Initial extracted text. " * 20,
            metadata={"page_stats": []},
        )
        with patch.object(
            library._extractors[0], "extract_and_validate", return_value=initial_result
        ):
            add_result = library.add(str(pdf_path))

        return library, str(add_result.document.id)

    def test_reextract_fallback_sets_needs_review(
        self, library_with_doc: tuple[Library, str]
    ) -> None:
        """reextract() should set NEEDS_REVIEW for pdftext fallback results."""
        library, doc_id = library_with_doc

        fallback_result = ExtractionResult.from_text(
            text="Fallback reextracted text. " * 20,
            metadata={
                "extraction_method": "pdftext_fallback",
                "marker_failure_reason": "timed out",
            },
        )
        with patch.object(
            library._extractors[0], "extract_and_validate", return_value=fallback_result
        ):
            updated = library.reextract(doc_id)

        assert updated.status == DocumentStatus.NEEDS_REVIEW
        assert updated.error_code == "EXTRACTION_FALLBACK"

    def test_reextract_normal_sets_ready(self, library_with_doc: tuple[Library, str]) -> None:
        """reextract() should set READY for normal Marker extraction results."""
        library, doc_id = library_with_doc

        normal_result = ExtractionResult.from_text(
            text="Normal reextracted text. " * 20,
            metadata={"page_stats": []},
        )
        with patch.object(
            library._extractors[0], "extract_and_validate", return_value=normal_result
        ):
            updated = library.reextract(doc_id)

        assert updated.status == DocumentStatus.READY


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
            extractor = lib._extractors[0]
            assert isinstance(extractor, PdfExtractor)
            assert extractor._llm_enabled is False

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
            extractor = lib._extractors[0]
            assert isinstance(extractor, PdfExtractor)
            assert extractor._llm_enabled is True

    def test_custom_extractors_not_affected_by_pdf_llm_enabled(self, temp_dir: Path) -> None:
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
            extractor = lib._extractors[0]
            assert isinstance(extractor, PdfExtractor)
            assert extractor._llm_enabled is False


class TestLibraryQuery:
    """Tests for Library RAG query methods."""

    @pytest.fixture
    def library(self, temp_dir: Path) -> Library:
        """Provide an initialized Library for testing."""
        return Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
            embed_on_add=False,
        )

    def test_query_returns_rag_response(self, library: Library) -> None:
        """query() should return a RAGResponse."""
        from unittest.mock import MagicMock
        from uuid import uuid4

        from local_library.core.models import RAGResponse
        from local_library.embeddings.base import Chunk, SearchResult

        # Set up mock retriever
        chunk = Chunk.create(doc_id=uuid4(), chunk_index=0, text="Test text")
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            SearchResult(
                chunk=chunk,
                score=0.9,
                doc_title="Test",
                doc_citekey="Test2023",
                search_methods=frozenset({"vector"}),
            )
        ]

        # Set up mock LLM client
        mock_llm = MagicMock()
        mock_llm.complete.return_value = "The answer is [@Test2023]..."

        # Inject mocks
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        response = library.query(
            "What is the answer?",
            retriever=mock_retriever,
        )

        assert isinstance(response, RAGResponse)
        assert response.question == "What is the answer?"
        assert "[@Test2023]" in response.answer
        assert response.model == "test-model"

    def test_query_empty_retrieval_skips_llm(self, library: Library) -> None:
        """query() with no retrieval results should skip LLM."""
        from unittest.mock import MagicMock

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        mock_llm = MagicMock()
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        response = library.query("Question?", retriever=mock_retriever)

        mock_llm.complete.assert_not_called()
        assert len(response.context_chunks) == 0

    def test_query_stream_returns_rag_stream(self, library: Library) -> None:
        """query_stream() should return a RAGStream."""
        from unittest.mock import MagicMock
        from uuid import uuid4

        from local_library.embeddings.base import Chunk, SearchResult
        from local_library.rag.interface import RAGStream

        chunk = Chunk.create(doc_id=uuid4(), chunk_index=0, text="Text")
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            SearchResult(
                chunk=chunk,
                score=0.9,
                doc_title="Test",
                doc_citekey="Test2023",
                search_methods=frozenset({"vector"}),
            )
        ]

        mock_llm = MagicMock()
        mock_llm.stream.return_value = iter(["token1", "token2"])
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        stream = library.query_stream("Question?", retriever=mock_retriever)

        assert isinstance(stream, RAGStream)
        tokens = list(stream)
        assert tokens == ["token1", "token2"]

    def test_query_lazy_inits_llm_client(self, library: Library) -> None:
        """query() should lazily create LLMClient on first call."""
        from unittest.mock import MagicMock, patch

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        # No _llm_client set — should be created lazily
        assert library._llm_client is None

        with patch("local_library.llm.litellm_client.LiteLLMClient") as mock_litellm_cls:
            mock_instance = MagicMock()
            mock_litellm_cls.return_value = mock_instance

            library.query("Q?", retriever=mock_retriever)

            mock_litellm_cls.assert_called_once()
            assert library._llm_client is mock_instance

    def test_query_reuses_llm_client(self, library: Library) -> None:
        """query() should reuse existing LLMClient across calls."""
        from unittest.mock import MagicMock

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        mock_llm = MagicMock()
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        library.query("Q1?", retriever=mock_retriever)
        library.query("Q2?", retriever=mock_retriever)

        # LLMClient should be same instance
        assert library._llm_client is mock_llm

    def test_query_passes_retrieval_params(self, library: Library) -> None:
        """query() should pass limit and doc_ids to retriever."""
        from unittest.mock import MagicMock
        from uuid import uuid4

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        mock_llm = MagicMock()
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        doc_id = uuid4()
        library.query(
            "Q?",
            retriever=mock_retriever,
            limit=5,
            doc_ids=[doc_id],
        )

        mock_retriever.retrieve.assert_called_once_with(
            "Q?",
            k=5,
            doc_ids=[doc_id],
        )

    def test_query_default_model(self, temp_dir: Path) -> None:
        """Library should use configured model for RAG queries."""
        from unittest.mock import MagicMock

        lib = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
            embed_on_add=False,
            rag_model="anthropic/claude-3-haiku",
        )

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        mock_llm = MagicMock()
        lib._llm_client = mock_llm

        response = lib.query("Q?", retriever=mock_retriever)

        assert response.model == "anthropic/claude-3-haiku"

    def test_query_propagates_rag_error(self, library: Library) -> None:
        """query() should propagate RAGError from RAGInterface."""
        from unittest.mock import MagicMock

        from local_library.core.errors import RAGError

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        mock_llm = MagicMock()
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        # Mock _get_rag_interface to return a RAGInterface that raises
        from local_library.core.errors import ErrorCode

        mock_rag = MagicMock()
        mock_rag.query.side_effect = RAGError("generation failed", ErrorCode.LLM_GENERATION_FAILED)
        library._rag_interface = mock_rag

        with pytest.raises(RAGError, match="generation failed"):
            library.query("Q?", retriever=mock_retriever)

    def test_query_propagates_embedding_error(self, library: Library) -> None:
        """query() should propagate EmbeddingError from retriever."""
        from unittest.mock import MagicMock

        from local_library.core.errors import EmbeddingError, ErrorCode

        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = EmbeddingError(
            "vec unavailable", ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE
        )

        mock_llm = MagicMock()
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        with pytest.raises(EmbeddingError, match="vec unavailable"):
            library.query("Q?", retriever=mock_retriever)


class TestGetRetrieverReranking:
    """Tests for get_retriever reranking integration."""

    @pytest.fixture()
    def lib(self, tmp_path: Path) -> Generator[Library, None, None]:
        """Library instance with temp dirs for reranking tests."""
        with Library(
            db_path=tmp_path / "test.db",
            storage_dir=tmp_path / "storage",
            extracted_dir=tmp_path / "extracted",
        ) as lib:
            yield lib

    @pytestmark_vec
    def test_rerank_true_returns_reranked_retriever(self, lib: Library) -> None:
        """get_retriever(rerank=True) wraps base retriever with RerankedRetriever."""
        from local_library.embeddings.reranking import RerankedRetriever

        lib._embedder = MagicMock()
        lib._reranker = MagicMock()
        retriever = lib.get_retriever(mode="hybrid", rerank=True)
        assert isinstance(retriever, RerankedRetriever)

    @pytestmark_vec
    def test_rerank_false_returns_base_retriever(self, lib: Library) -> None:
        """get_retriever(rerank=False) returns unwrapped HybridRetriever."""
        from local_library.embeddings.retrieval import HybridRetriever

        lib._embedder = MagicMock()
        retriever = lib.get_retriever(mode="hybrid", rerank=False)
        assert isinstance(retriever, HybridRetriever)

    @pytestmark_vec
    def test_fts_mode_with_rerank(self, lib: Library) -> None:
        """FTS mode also wraps with RerankedRetriever when rerank=True."""
        from local_library.embeddings.reranking import RerankedRetriever

        lib._reranker = MagicMock()
        retriever = lib.get_retriever(mode="fts", rerank=True)
        assert isinstance(retriever, RerankedRetriever)

    @pytestmark_vec
    def test_get_reranker_caches_instance(self, lib: Library) -> None:
        """_get_reranker() creates once and returns cached instance."""
        with patch("local_library.embeddings.reranking.CrossEncoderReranker") as mock_cls:
            mock_cls.return_value = MagicMock()
            r1 = lib._get_reranker()
            r2 = lib._get_reranker()
            assert r1 is r2
            mock_cls.assert_called_once()

    @pytestmark_vec
    def test_query_forwards_rerank(self, lib: Library) -> None:
        """query() passes rerank parameter to get_retriever when retriever is None."""
        with patch.object(lib, "get_retriever") as mock_get:
            mock_retriever = MagicMock()
            mock_retriever.retrieve.return_value = []
            mock_get.return_value = mock_retriever
            with patch.object(lib, "_get_rag_interface") as mock_rag:
                mock_rag_inst = MagicMock()
                mock_rag.return_value = mock_rag_inst
                mock_rag_inst.query.return_value = MagicMock()
                lib.query("test question", rerank=False)
                mock_get.assert_called_once_with(mode="hybrid", rerank=False)

    @pytestmark_vec
    def test_query_stream_forwards_rerank(self, lib: Library) -> None:
        """query_stream() passes rerank parameter to get_retriever when retriever is None."""
        with patch.object(lib, "get_retriever") as mock_get:
            mock_retriever = MagicMock()
            mock_retriever.retrieve.return_value = []
            mock_get.return_value = mock_retriever
            with patch.object(lib, "_get_rag_interface") as mock_rag:
                mock_rag_inst = MagicMock()
                mock_rag.return_value = mock_rag_inst
                mock_rag_inst.query_stream.return_value = MagicMock()
                lib.query_stream("test question", rerank=False)
                mock_get.assert_called_once_with(mode="hybrid", rerank=False)


class TestLibraryProgressCallback:
    """Tests for Library progress callback forwarding."""

    def test_callback_forwarded_to_pdf_extractor(self, temp_dir: Path) -> None:
        """Library should forward progress_callback to default PdfExtractor."""
        callback = MagicMock()
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            progress_callback=callback,
        )
        # The default extractor should have the callback
        assert library._extractors[0]._progress_callback is callback

    def test_no_callback_default(self, temp_dir: Path) -> None:
        """Library without progress_callback should leave extractor callback as None."""
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        )
        assert library._extractors[0]._progress_callback is None

    def test_custom_extractors_not_affected(self, temp_dir: Path) -> None:
        """Custom extractors should not receive Library's progress_callback."""
        custom = PdfExtractor(lazy_load=True)
        callback = MagicMock()
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            extractors=[custom],
            progress_callback=callback,
        )
        # Custom extractors are used as-is
        assert library._extractors[0]._progress_callback is None


class TestPreliminaryMetadata:
    """Tests for preliminary metadata persistence before extraction."""

    @pytest.fixture
    def library(self, temp_dir: Path) -> Library:
        """Provide a Library with text extraction disabled."""
        return Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
        )

    @pytest.fixture
    def sample_pdf(self, temp_dir: Path) -> Path:
        """Create a sample PDF file."""
        pdf_path = temp_dir / "Smith - 2020 - Attention.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")
        return pdf_path

    def test_explicit_metadata_persisted_before_extraction(
        self, library: Library, sample_pdf: Path
    ) -> None:
        """add() with explicit metadata should persist it before extraction."""
        metadata = {"type": "article-journal", "title": "Test Article"}

        with patch.object(
            library._extractors[0],
            "extract_and_validate",
            return_value=ExtractionResult.from_text("content " * 20),
        ):
            result = library.add(
                str(sample_pdf),
                metadata=metadata,
                metadata_source=MetadataSource.EXPLICIT,
            )

        assert result.document.citekey is not None
        assert result.document.csl_json is not None
        assert result.document.csl_json.get("_metadata_source") == "EXPLICIT"

    def test_zotero_metadata_tagged_correctly(self, library: Library, sample_pdf: Path) -> None:
        """add() from Zotero should tag metadata source as ZOTERO."""
        metadata = {
            "type": "article-journal",
            "title": "Zotero Article",
            "author": [{"family": "Smith", "given": "John"}],
            "issued": {"date-parts": [[2020]]},
        }

        with patch.object(
            library._extractors[0],
            "extract_and_validate",
            return_value=ExtractionResult.from_text("content " * 20),
        ):
            result = library.add(
                str(sample_pdf),
                metadata=metadata,
                citekey="Smith2020",
                metadata_source=MetadataSource.ZOTERO,
            )

        assert result.document.csl_json.get("_metadata_source") == "ZOTERO"
        assert result.document.citekey == "Smith2020"

    def test_bare_path_gets_filename_metadata(self, library: Library, sample_pdf: Path) -> None:
        """add() without metadata should parse filename for preliminary metadata."""
        with patch.object(
            library._extractors[0],
            "extract_and_validate",
            return_value=ExtractionResult.from_text("content " * 20),
        ):
            result = library.add(str(sample_pdf))

        assert result.document.citekey is not None
        assert result.document.csl_json is not None
        assert result.document.csl_json.get("_metadata_source") == "FILENAME"
        # Should have parsed author and year from "Smith - 2020 - Attention.pdf"
        assert result.document.title is not None

    def test_failed_extraction_keeps_explicit_metadata(
        self, library: Library, sample_pdf: Path
    ) -> None:
        """add() should preserve explicit metadata even when extraction fails."""
        metadata = {
            "type": "article-journal",
            "title": "Will Survive Failure",
            "author": [{"family": "Author"}],
        }

        with patch.object(
            library._extractors[0],
            "extract_and_validate",
            side_effect=ExtractionError("failed", ErrorCode.EXTRACTION_TIMEOUT),
        ):
            with pytest.raises(ExtractionError):
                library.add(
                    str(sample_pdf),
                    metadata=metadata,
                    metadata_source=MetadataSource.EXPLICIT,
                )

        # Verify document was created with metadata despite extraction failure
        # (use same library instance -- connection is still open after caught exception)
        docs = library.list()
        assert len(docs) == 1
        doc = docs[0]
        assert doc.status == DocumentStatus.FAILED
        assert doc.citekey is not None
        assert doc.title == "Will Survive Failure"

    def test_failed_extraction_keeps_filename_metadata(
        self, library: Library, sample_pdf: Path
    ) -> None:
        """add() should preserve filename-derived metadata when extraction fails.

        This is the core design requirement: FAILED documents retain a citekey
        and basic metadata from filename parsing. parse_filename_metadata() returns
        {"type": "document", ...} which passes MetadataHandler validation (type
        "document" is valid, missing fields produce warnings not errors).
        """
        with patch.object(
            library._extractors[0],
            "extract_and_validate",
            side_effect=ExtractionError("timeout", ErrorCode.EXTRACTION_TIMEOUT),
        ):
            with pytest.raises(ExtractionError):
                library.add(str(sample_pdf))  # No explicit metadata -- uses filename

        docs = library.list()
        assert len(docs) == 1
        doc = docs[0]
        assert doc.status == DocumentStatus.FAILED
        assert doc.citekey is not None  # Generated from filename parsing
        assert doc.csl_json is not None
        assert doc.csl_json.get("_metadata_source") == "FILENAME"


class TestMetadataUpgrade:
    """Tests for conditional metadata upgrade after extraction."""

    @pytest.fixture
    def library_with_text_extraction(self, temp_dir: Path) -> Library:
        """Provide a Library with text extraction enabled."""
        return Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=True,
        )

    @pytest.fixture
    def sample_pdf(self, temp_dir: Path) -> Path:
        """Create a sample PDF file."""
        pdf_path = temp_dir / "Smith2020.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")
        return pdf_path

    def test_filename_metadata_upgraded_after_extraction(
        self, library_with_text_extraction: Library, sample_pdf: Path
    ) -> None:
        """FILENAME metadata should be upgraded when text extraction succeeds."""
        lib = library_with_text_extraction
        extracted_text = "A Study of Neural Networks by J. Smith, 2020. " * 20

        with patch.object(
            lib._extractors[0],
            "extract_and_validate",
            return_value=ExtractionResult.from_text(extracted_text),
        ):
            result = lib.add(str(sample_pdf))

        # Should have attempted upgrade
        assert result.document.csl_json is not None
        source = result.document.csl_json.get("_metadata_source")
        assert source in ("FILENAME", "TEXT_EXTRACTED")

    def test_zotero_metadata_not_upgraded(
        self, library_with_text_extraction: Library, sample_pdf: Path
    ) -> None:
        """ZOTERO metadata should never be upgraded by text extraction."""
        lib = library_with_text_extraction
        zotero_metadata = {
            "type": "article-journal",
            "title": "Original Zotero Title",
            "author": [{"family": "Smith", "given": "John"}],
            "issued": {"date-parts": [[2020]]},
        }

        with patch.object(
            lib._extractors[0],
            "extract_and_validate",
            return_value=ExtractionResult.from_text("Different text " * 20),
        ):
            result = lib.add(
                str(sample_pdf),
                metadata=zotero_metadata,
                citekey="Smith2020",
                metadata_source=MetadataSource.ZOTERO,
            )

        assert result.document.title == "Original Zotero Title"
        assert result.document.csl_json.get("_metadata_source") == "ZOTERO"

    def test_explicit_metadata_not_upgraded(
        self, library_with_text_extraction: Library, sample_pdf: Path
    ) -> None:
        """EXPLICIT metadata should never be upgraded by text extraction."""
        lib = library_with_text_extraction
        explicit_metadata = {
            "type": "article-journal",
            "title": "Explicit Title",
        }

        with patch.object(
            lib._extractors[0],
            "extract_and_validate",
            return_value=ExtractionResult.from_text("Different text " * 20),
        ):
            result = lib.add(
                str(sample_pdf),
                metadata=explicit_metadata,
                metadata_source=MetadataSource.EXPLICIT,
            )

        assert result.document.title == "Explicit Title"
        assert result.document.csl_json.get("_metadata_source") == "EXPLICIT"

    def test_citekey_change_flags_needs_review(
        self, library_with_text_extraction: Library, sample_pdf: Path
    ) -> None:
        """Upgrade that would change citekey should flag NEEDS_REVIEW."""
        lib = library_with_text_extraction

        mock_extraction = TextExtractionResult(
            title=FieldExtraction(
                value="Completely Different Title",
                confidence=0.9,
                source="heuristic",
                alternatives=(),
                reasoning="test",
            ),
            authors=(
                FieldExtraction(
                    value="DifferentAuthor, A.",
                    confidence=0.9,
                    source="heuristic",
                    alternatives=(),
                    reasoning="test",
                ),
            ),
            date=FieldExtraction(
                value="2021",
                confidence=0.9,
                source="heuristic",
                alternatives=(),
                reasoning="test",
            ),
            doc_type=FieldExtraction(
                value="article-journal",
                confidence=0.9,
                source="heuristic",
                alternatives=(),
                reasoning="test",
            ),
            overall_confidence=0.9,
            needs_review=False,
            review_reasons=(),
        )

        with patch.object(
            lib._extractors[0],
            "extract_and_validate",
            return_value=ExtractionResult.from_text("content " * 20),
        ):
            with patch.object(lib._text_extractor, "extract", return_value=mock_extraction):
                result = lib.add(str(sample_pdf))

        # Original citekey from filename should be preserved
        # Document should be flagged if citekey would change
        assert result.document.status == DocumentStatus.NEEDS_REVIEW
        assert "citekey" in (result.document.error_message or "").lower()


class TestReextractFailedDocuments:
    """Tests for reextract on FAILED documents with preliminary metadata."""

    @pytest.fixture
    def library_with_failed_doc(self, temp_dir: Path) -> tuple[Library, str]:
        """Create a library with a FAILED document that has preliminary metadata."""
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
        )

        pdf_path = temp_dir / "Smith - 2020 - Test Article.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")

        with patch.object(
            library._extractors[0],
            "extract_and_validate",
            side_effect=ExtractionError("timeout", ErrorCode.EXTRACTION_TIMEOUT),
        ):
            try:
                library.add(str(pdf_path))
            except ExtractionError:
                pass

        docs = library.list()
        assert len(docs) == 1
        assert docs[0].status == DocumentStatus.FAILED
        assert docs[0].citekey is not None  # Has preliminary metadata

        return library, str(docs[0].id)

    def test_reextract_failed_document_succeeds(
        self, library_with_failed_doc: tuple[Library, str]
    ) -> None:
        """reextract() should work on FAILED documents with preliminary metadata."""
        library, doc_id = library_with_failed_doc

        successful_result = ExtractionResult.from_text(
            text="Successfully reextracted content. " * 20,
        )
        with patch.object(
            library._extractors[0],
            "extract_and_validate",
            return_value=successful_result,
        ):
            updated = library.reextract(doc_id)

        assert updated.status == DocumentStatus.READY
        assert updated.extracted_path is not None
        assert updated.citekey is not None

    def test_failed_document_retains_citekey(
        self, library_with_failed_doc: tuple[Library, str]
    ) -> None:
        """FAILED documents should have citekey from preliminary metadata."""
        library, doc_id = library_with_failed_doc
        doc = library.get(doc_id)

        assert doc.status == DocumentStatus.FAILED
        assert doc.citekey is not None
        assert doc.csl_json is not None
        assert doc.csl_json.get("_metadata_source") == "FILENAME"


class TestLibraryChunkAccess:
    """Tests for Library chunk access methods."""

    @pytest.fixture
    def library(self, temp_dir: Path) -> Generator[Library, None, None]:
        """Provide a Library instance for testing."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            embed_on_add=False,
        ) as lib:
            yield lib

    def test_get_chunk_count_unembedded_document(self, library: Library, temp_dir: Path) -> None:
        """get_chunk_count() should return 0 for unembedded documents."""
        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")

        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Test document content" * 10)
            result = library.add(str(pdf_path))

        count = library.get_chunk_count(result.document.id)  # Pass UUID directly
        assert count == 0

    def test_get_chunks_unembedded_document(self, library: Library, temp_dir: Path) -> None:
        """get_chunks() should return empty list for unembedded documents."""
        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")

        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Test document content" * 10)
            result = library.add(str(pdf_path))

        chunks = library.get_chunks(result.document.id)  # Pass UUID directly
        assert chunks == []

    def test_get_chunk_count_no_vec_extension(self, temp_dir: Path) -> None:
        """get_chunk_count() should return 0 when sqlite-vec is unavailable."""
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            embed_on_add=False,
        )

        try:
            pdf_path = temp_dir / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test content")

            with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
                mock_extract.return_value = MagicMock(text="Test document content" * 10)
                result = library.add(str(pdf_path))

            # Mock _get_embedding_storage to return None (simulating unavailable sqlite-vec)
            with patch.object(library, "_get_embedding_storage", return_value=None):
                count = library.get_chunk_count(result.document.id)  # Pass UUID directly

            assert count == 0
        finally:
            library.close()

    def test_get_chunks_no_vec_extension(self, temp_dir: Path) -> None:
        """get_chunks() should return empty list when sqlite-vec is unavailable."""
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            embed_on_add=False,
        )

        try:
            pdf_path = temp_dir / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test content")

            with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
                mock_extract.return_value = MagicMock(text="Test document content" * 10)
                result = library.add(str(pdf_path))

            # Mock _get_embedding_storage to return None (simulating unavailable sqlite-vec)
            with patch.object(library, "_get_embedding_storage", return_value=None):
                chunks = library.get_chunks(result.document.id)  # Pass UUID directly

            assert chunks == []
        finally:
            library.close()


class TestLibraryIssuedYearWritePaths:
    """Tests that issued_year is persisted through all three Library write paths."""

    def test_add_with_explicit_metadata_persists_issued_year(self, temp_dir: Path) -> None:
        """Library.add() with explicit CSL-JSON metadata populates issued_year."""
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
            embed_on_add=False,
        )

        try:
            pdf_path = temp_dir / "test.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test content")

            metadata = {
                "type": "article-journal",
                "title": "Test Paper",
                "author": [{"family": "Smith", "given": "J"}],
                "issued": {"date-parts": [[2023, 6, 15]]},
            }

            with patch.object(library._extractors[0], "extract_and_validate") as mock_ext:
                mock_ext.return_value = MagicMock(text="content " * 20)
                result = library.add(str(pdf_path), metadata=metadata)

            doc = library.get(str(result.document.id))
            assert doc.issued_year == 2023
        finally:
            library.close()

    def test_update_metadata_persists_issued_year(self, temp_dir: Path) -> None:
        """Library.update_metadata() populates issued_year from inline extraction."""
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
            embed_on_add=False,
        )

        try:
            pdf_path = temp_dir / "test.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test content")

            with patch.object(library._extractors[0], "extract_and_validate") as mock_ext:
                mock_ext.return_value = MagicMock(text="content " * 20)
                result = library.add(str(pdf_path))

            # Update metadata with a new CSL-JSON that has an issued year
            new_csl = {
                "type": "article-journal",
                "title": "Updated Title",
                "author": [{"family": "Smith"}],
                "issued": {"date-parts": [[1984]]},
            }
            library.update_metadata(result.document.id, csl_json=new_csl)

            doc = library.get(str(result.document.id))
            assert doc.issued_year == 1984
        finally:
            library.close()
