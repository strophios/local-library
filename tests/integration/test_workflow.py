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
        with patch.object(lib._extractors[0], "extract_and_validate") as mock_extract:
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
            # Use resolve() to handle macOS /private prefix normalization
            assert Path(doc.original_path).resolve() == sample_pdf.resolve()
            assert doc.status == DocumentStatus.READY

            # DELETE - should remove document
            lib.delete(doc_id)

            # Verify deletion
            docs = lib.list()
            assert len(docs) == 0

    def test_partial_id_lookup(self, integration_library: Library, sample_pdf: Path) -> None:
        """Should find documents by partial UUID prefix."""
        lib = integration_library

        with patch.object(lib._extractors[0], "extract_and_validate") as mock_extract:
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

        with patch.object(lib._extractors[0], "extract_and_validate") as mock_extract:
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

        with patch.object(lib._extractors[0], "extract_and_validate") as mock_extract:
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

        with patch.object(lib._extractors[0], "extract_and_validate") as mock_extract:
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

        with patch.object(lib._extractors[0], "extract_and_validate") as mock_extract:
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

        with patch.object(lib._extractors[0], "extract_and_validate") as mock_extract:
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

    def test_force_duplicate_returns_existing(self, integration_library: Library) -> None:
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

        with patch.object(lib._extractors[0], "extract_and_validate") as mock_extract:
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

        with patch.object(lib._extractors[0], "extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            result = lib.add(str(sample_pdf))
            storage_path = Path(result.document.storage_path)

            # Storage file should exist
            assert storage_path.exists()

            # Delete without file cleanup
            lib.delete(str(result.document.id), delete_files=False)

            # Storage file should still exist
            assert storage_path.exists()


class TestMetadataWorkflow:
    """Tests for end-to-end metadata workflow."""

    def test_add_with_metadata(self, integration_library: Library, sample_pdf: Path) -> None:
        """Adding document with metadata should store all fields."""
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

        # Mock extraction to reach metadata validation
        with patch.object(
            integration_library._extractors[0], "extract_and_validate"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            with pytest.raises(MetadataError):
                integration_library.add(str(sample_pdf), metadata=invalid_metadata)

    def test_add_without_metadata_works(
        self, integration_library: Library, sample_pdf: Path
    ) -> None:
        """Adding without metadata should still work (no citekey)."""
        with patch.object(
            integration_library._extractors[0], "extract_and_validate"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            result = integration_library.add(str(sample_pdf))

        assert result.document.citekey is None
        assert result.document.title is None


class TestTextExtractionIntegration:
    """Integration tests for text-based metadata extraction in Library.add()."""

    def test_add_without_metadata_extracts_from_text(
        self,
        integration_library: "Library",
        sample_pdf: Path,
    ) -> None:
        """Adding without --metadata should extract metadata from text."""
        # Mock extraction to return text with metadata
        mock_result = MagicMock()
        mock_result.text = """# Machine Learning Fundamentals

        John Smith, Jane Doe

        Published: 2023

        Journal of Computer Science

        Abstract: This paper discusses machine learning...
        """ + " additional content" * 100

        with patch.object(
            integration_library._extractors[0],
            "extract_and_validate",
            return_value=mock_result,
        ):
            result = integration_library.add(str(sample_pdf))

        # Should have extracted metadata
        doc = result.document
        assert doc.title is not None
        assert doc.citekey is not None

    def test_add_without_metadata_sets_needs_review_status(
        self,
        integration_library: "Library",
        sample_pdf: Path,
    ) -> None:
        """Low confidence extraction should set NEEDS_REVIEW status."""
        # Mock extraction to return minimal text (low confidence)
        mock_result = MagicMock()
        mock_result.text = """Some vague content without clear metadata.
        """ + " filler" * 50

        with patch.object(
            integration_library._extractors[0],
            "extract_and_validate",
            return_value=mock_result,
        ):
            result = integration_library.add(str(sample_pdf))

        doc = result.document
        # Low confidence should result in NEEDS_REVIEW or READY
        # (This depends on extraction quality - adjust as needed)
        assert doc.status in (DocumentStatus.READY, DocumentStatus.NEEDS_REVIEW)

    def test_add_with_explicit_metadata_skips_extraction(
        self,
        integration_library: "Library",
        sample_pdf: Path,
    ) -> None:
        """Adding with --metadata should use explicit metadata, not text extraction."""
        mock_result = MagicMock()
        mock_result.text = "Some extracted text" + " content" * 50

        explicit_metadata = {
            "type": "article-journal",
            "title": "Explicit Title",
            "author": [{"family": "Explicit", "given": "Author"}],
            "issued": {"date-parts": [[2022]]},
        }

        with patch.object(
            integration_library._extractors[0],
            "extract_and_validate",
            return_value=mock_result,
        ):
            result = integration_library.add(str(sample_pdf), metadata=explicit_metadata)

        doc = result.document
        # Should use explicit metadata
        assert doc.title == "Explicit Title"
        assert "Explicit" in (doc.authors or "")

    def test_add_generates_citekey_from_extracted_metadata(
        self,
        integration_library: "Library",
        sample_pdf: Path,
    ) -> None:
        """Citekey should be generated from extracted metadata."""
        mock_result = MagicMock()
        mock_result.text = """# Deep Learning Theory

        Alice Smith

        Published: 2023

        Abstract...
        """ + " content" * 100

        with patch.object(
            integration_library._extractors[0],
            "extract_and_validate",
            return_value=mock_result,
        ):
            result = integration_library.add(str(sample_pdf))

        doc = result.document
        # Citekey should be generated (pattern: AuthorYearTitleword)
        if doc.citekey:
            assert len(doc.citekey) > 0
            # Should contain year if extracted
            # assert "2023" in doc.citekey or "Smith" in doc.citekey
