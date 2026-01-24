"""Unit tests for models module."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from local_library.core.models import (
    AcquisitionResult,
    AddResult,
    Document,
    DocumentStatus,
    ExtractionResult,
    FieldExtraction,
    MetadataResult,
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
        before = datetime.now(timezone.utc)
        doc = Document.create_pending("/path/to/file.pdf", "abc123", "/storage/ab/c1/abc123.pdf")
        after = datetime.now(timezone.utc)

        assert before <= doc.created_at <= after
        assert doc.created_at == doc.updated_at

    def test_create_pending_stores_paths(self) -> None:
        """create_pending should store original and storage paths."""
        doc = Document.create_pending("/original/path.pdf", "hash123", "/storage/ha/sh/hash123.pdf")

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


class TestFieldExtraction:
    """Tests for FieldExtraction dataclass."""

    def test_field_extraction_is_frozen(self) -> None:
        """FieldExtraction should be immutable."""
        field = FieldExtraction(
            value="Test Title",
            confidence=0.85,
            source="heuristic",
            alternatives=("Alt Title",),
            reasoning="First line of document",
        )

        with pytest.raises(AttributeError):
            field.value = "Changed"  # type: ignore[misc]

    def test_field_extraction_with_none_value(self) -> None:
        """FieldExtraction should allow None value for missing fields."""
        field = FieldExtraction(
            value=None,
            confidence=0.0,
            source="heuristic",
            alternatives=(),
            reasoning="No candidates found",
        )

        assert field.value is None
        assert field.confidence == 0.0

    def test_field_extraction_confidence_bounds(self) -> None:
        """FieldExtraction confidence should be between 0.0 and 1.0."""
        # Valid bounds
        low = FieldExtraction(
            value="x", confidence=0.0, source="heuristic", alternatives=(), reasoning=""
        )
        high = FieldExtraction(
            value="x", confidence=1.0, source="heuristic", alternatives=(), reasoning=""
        )

        assert low.confidence == 0.0
        assert high.confidence == 1.0


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


class TestMetadataResult:
    """Tests for MetadataResult dataclass."""

    def test_stores_required_fields(self) -> None:
        """MetadataResult should store csl_json and citekey."""
        csl = {"type": "article-journal", "title": "Test Article"}
        result = MetadataResult(csl_json=csl, citekey="Smith2020Test")

        assert result.csl_json == csl
        assert result.citekey == "Smith2020Test"

    def test_optional_fields_have_defaults(self) -> None:
        """Optional fields should default to None or empty tuples."""
        csl = {"type": "book", "title": "Test Book"}
        result = MetadataResult(csl_json=csl, citekey="Author2021")

        assert result.title is None
        assert result.authors is None
        assert result.issued_date is None
        assert result.validation_warnings == ()
        assert result.author_list == ()

    def test_metadata_result_is_frozen(self) -> None:
        """MetadataResult should be immutable."""
        csl = {"type": "article", "title": "Test"}
        result = MetadataResult(csl_json=csl, citekey="Test2020")

        with pytest.raises(AttributeError):
            result.citekey = "NewKey"  # type: ignore[misc]

    def test_create_factory_converts_lists_to_tuples(self) -> None:
        """create() factory should convert lists to tuples for immutability."""
        csl = {"type": "article-journal", "title": "Test"}
        result = MetadataResult.create(
            csl_json=csl,
            citekey="Smith2020",
            title="Test Article",
            authors="Smith, J.",
            validation_warnings=["missing abstract"],
            author_list=["Smith, John"],
        )

        assert isinstance(result.validation_warnings, tuple)
        assert result.validation_warnings == ("missing abstract",)
        assert isinstance(result.author_list, tuple)
        assert result.author_list == ("Smith, John",)

    def test_create_factory_handles_none_lists(self) -> None:
        """create() factory should handle None for list parameters."""
        csl = {"type": "book"}
        result = MetadataResult.create(csl_json=csl, citekey="Test2020")

        assert result.validation_warnings == ()
        assert result.author_list == ()

    def test_stores_extracted_fields(self) -> None:
        """MetadataResult should store all extracted indexed fields."""
        csl = {
            "type": "article-journal",
            "title": "Attention Is All You Need",
            "author": [{"family": "Vaswani", "given": "A."}],
            "issued": {"date-parts": [[2017]]},
        }
        result = MetadataResult.create(
            csl_json=csl,
            citekey="Vaswani2017Attention",
            title="Attention Is All You Need",
            authors="Vaswani, A.",
            issued_date="2017",
            author_list=["Vaswani, A."],
        )

        assert result.title == "Attention Is All You Need"
        assert result.authors == "Vaswani, A."
        assert result.issued_date == "2017"
        assert result.author_list == ("Vaswani, A.",)
