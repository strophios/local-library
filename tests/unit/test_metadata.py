"""Unit tests for metadata processing."""

from typing import Any, cast

import pytest

from local_library.core.errors import ErrorCode, MetadataError
from local_library.core.models import MetadataResult
from local_library.ingestion.metadata import MetadataHandler


class TestMetadataHandlerValidation:
    """Tests for MetadataHandler.validate()."""

    @pytest.fixture
    def handler(self) -> MetadataHandler:
        """Provide a MetadataHandler instance."""
        return MetadataHandler()

    def test_valid_minimal_article(self, handler: MetadataHandler) -> None:
        """Minimal valid CSL-JSON should pass validation."""
        csl_json = {"type": "article-journal", "title": "Test Article"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True
        # May have warnings for missing optional fields
        assert not any(i for i in issues if not i.startswith("warning:"))

    def test_valid_complete_article(self, handler: MetadataHandler) -> None:
        """Complete article with all common fields should pass."""
        csl_json = {
            "type": "article-journal",
            "title": "Attention Is All You Need",
            "author": [
                {"family": "Vaswani", "given": "Ashish"},
                {"family": "Shazeer", "given": "Noam"},
            ],
            "issued": {"date-parts": [[2017]]},
            "container-title": "Advances in Neural Information Processing Systems",
            "volume": "30",
            "DOI": "10.48550/arXiv.1706.03762",
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True

    def test_valid_book(self, handler: MetadataHandler) -> None:
        """Valid book entry should pass."""
        csl_json = {
            "type": "book",
            "title": "The Art of Computer Programming",
            "author": [{"family": "Knuth", "given": "Donald E."}],
            "issued": {"date-parts": [[1968]]},
            "publisher": "Addison-Wesley",
            "ISBN": "978-0-201-89683-1",
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True

    def test_valid_chapter(self, handler: MetadataHandler) -> None:
        """Valid chapter entry should pass."""
        csl_json = {
            "type": "chapter",
            "title": "A Chapter Title",
            "author": [{"family": "Author", "given": "Test"}],
            "container-title": "Book Title",
            "editor": [{"family": "Editor", "given": "An"}],
            "issued": {"date-parts": [[2020]]},
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True

    def test_valid_webpage(self, handler: MetadataHandler) -> None:
        """Valid webpage entry should pass."""
        csl_json = {
            "type": "webpage",
            "title": "Example Webpage",
            "URL": "https://example.com/page",
            "accessed": {"date-parts": [[2024, 1, 15]]},
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True

    def test_valid_with_literal_author(self, handler: MetadataHandler) -> None:
        """Author with literal name (organization) should pass."""
        csl_json = {
            "type": "report",
            "title": "Annual Report 2023",
            "author": [{"literal": "World Health Organization"}],
            "issued": {"date-parts": [[2023]]},
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True


class TestMetadataHandlerValidationFailures:
    """Tests for MetadataHandler validation failures."""

    @pytest.fixture
    def handler(self) -> MetadataHandler:
        """Provide a MetadataHandler instance."""
        return MetadataHandler()

    def test_missing_type_is_fatal(self, handler: MetadataHandler) -> None:
        """Missing 'type' field should fail validation."""
        csl_json = {"title": "Test Article"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is False
        assert any("type" in i for i in issues)

    def test_invalid_type_value_is_fatal(self, handler: MetadataHandler) -> None:
        """Invalid 'type' value should fail validation."""
        csl_json = {"type": "not-a-valid-type", "title": "Test"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is False
        assert any("invalid item type" in i for i in issues)

    def test_type_not_string_is_fatal(self, handler: MetadataHandler) -> None:
        """Non-string 'type' should fail validation."""
        csl_json: dict[str, Any] = {"type": 123, "title": "Test"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is False
        assert any("must be string" in i for i in issues)


class TestMetadataHandlerWarnings:
    """Tests for validation warnings (non-fatal issues)."""

    @pytest.fixture
    def handler(self) -> MetadataHandler:
        """Provide a MetadataHandler instance."""
        return MetadataHandler()

    def test_missing_title_is_warning(self, handler: MetadataHandler) -> None:
        """Missing title should produce warning but pass validation."""
        csl_json = {"type": "article-journal"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True
        assert any("title" in i and "warning" in i for i in issues)

    def test_missing_author_is_warning(self, handler: MetadataHandler) -> None:
        """Missing author should produce warning but pass validation."""
        csl_json = {"type": "article-journal", "title": "Test"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True
        assert any("author" in i and "warning" in i for i in issues)

    def test_missing_issued_is_warning(self, handler: MetadataHandler) -> None:
        """Missing issued date should produce warning but pass validation."""
        csl_json = {
            "type": "article-journal",
            "title": "Test",
            "author": [{"family": "Test", "given": "A."}],
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True
        assert any("issued" in i and "warning" in i for i in issues)


class TestMetadataHandlerProcess:
    """Tests for MetadataHandler.process()."""

    @pytest.fixture
    def handler(self) -> MetadataHandler:
        """Provide a MetadataHandler instance."""
        return MetadataHandler()

    def test_process_returns_metadata_result(self, handler: MetadataHandler) -> None:
        """process() should return MetadataResult."""
        csl_json = {"type": "article-journal", "title": "Test Article"}

        result = handler.process(csl_json)

        assert isinstance(result, MetadataResult)
        assert result.csl_json == csl_json

    def test_process_extracts_title(self, handler: MetadataHandler) -> None:
        """process() should extract title for indexing."""
        csl_json = {"type": "book", "title": "The Great Book"}

        result = handler.process(csl_json)

        assert result.title == "The Great Book"

    def test_process_extracts_authors(self, handler: MetadataHandler) -> None:
        """process() should extract and format authors."""
        csl_json = {
            "type": "article-journal",
            "title": "Test",
            "author": [
                {"family": "Smith", "given": "John"},
                {"family": "Jones", "given": "Mary Ann"},
            ],
        }

        result = handler.process(csl_json)

        assert result.authors is not None
        assert "Smith" in result.authors
        assert "Jones" in result.authors
        assert len(result.author_list) == 2

    def test_process_extracts_literal_author(self, handler: MetadataHandler) -> None:
        """process() should handle literal/organizational authors."""
        csl_json = {
            "type": "report",
            "title": "Report",
            "author": [{"literal": "United Nations"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "United Nations"
        assert result.author_list == ("United Nations",)

    def test_process_extracts_issued_year(self, handler: MetadataHandler) -> None:
        """process() should extract year-only date."""
        csl_json = {
            "type": "book",
            "title": "Test",
            "issued": {"date-parts": [[2020]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "2020"

    def test_process_extracts_issued_full_date(self, handler: MetadataHandler) -> None:
        """process() should extract full date as ISO format."""
        csl_json = {
            "type": "article-journal",
            "title": "Test",
            "issued": {"date-parts": [[2020, 6, 15]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "2020-06-15"

    def test_process_uses_provided_citekey(self, handler: MetadataHandler) -> None:
        """process() should use provided citekey if given."""
        csl_json = {"type": "article-journal", "title": "Test"}

        result = handler.process(csl_json, citekey="CustomKey2020")

        assert result.citekey == "CustomKey2020"

    def test_process_generates_citekey_if_not_provided(self, handler: MetadataHandler) -> None:
        """process() should generate citekey if not provided."""
        csl_json = {"type": "article-journal", "title": "Test"}

        result = handler.process(csl_json)

        assert result.citekey is not None
        assert len(result.citekey) > 0

    def test_process_raises_for_invalid_csl(self, handler: MetadataHandler) -> None:
        """process() should raise MetadataError for invalid CSL-JSON."""
        csl_json = {"title": "No type field"}  # Missing required 'type'

        with pytest.raises(MetadataError) as exc_info:
            handler.process(csl_json)

        assert cast(MetadataError, exc_info.value).code == ErrorCode.METADATA_INVALID_SCHEMA

    def test_process_raises_for_invalid_citekey(self, handler: MetadataHandler) -> None:
        """process() should raise MetadataError for invalid citekey format."""
        csl_json = {"type": "article-journal", "title": "Test"}

        with pytest.raises(MetadataError) as exc_info:
            handler.process(csl_json, citekey="invalid key with spaces")

        assert cast(MetadataError, exc_info.value).code == ErrorCode.METADATA_CITEKEY_INVALID

    def test_process_collects_warnings(self, handler: MetadataHandler) -> None:
        """process() should collect validation warnings in result."""
        csl_json = {"type": "article-journal"}  # Missing title, author, issued

        result = handler.process(csl_json)

        assert len(result.validation_warnings) > 0
        assert any("title" in w for w in result.validation_warnings)

    def test_process_handles_empty_author_list(self, handler: MetadataHandler) -> None:
        """process() should handle empty author list gracefully."""
        csl_json = {
            "type": "article-journal",
            "title": "Test",
            "author": [],  # Empty author list
        }

        result = handler.process(csl_json)

        assert result.authors is None
        assert result.author_list == ()

    def test_process_rejects_empty_date_parts(self, handler: MetadataHandler) -> None:
        """process() should reject empty date-parts array (invalid CSL-JSON)."""
        csl_json = {
            "type": "article-journal",
            "title": "Test",
            "issued": {"date-parts": []},  # Empty date-parts array is invalid
        }

        with pytest.raises(MetadataError) as exc_info:
            handler.process(csl_json)

        assert cast(MetadataError, exc_info.value).code == ErrorCode.METADATA_INVALID_SCHEMA

    def test_process_rejects_empty_inner_date_parts(self, handler: MetadataHandler) -> None:
        """process() should reject empty inner date-parts array (invalid CSL-JSON)."""
        csl_json = {
            "type": "article-journal",
            "title": "Test",
            "issued": {"date-parts": [[]]},  # Inner array is empty (invalid)
        }

        with pytest.raises(MetadataError) as exc_info:
            handler.process(csl_json)

        assert cast(MetadataError, exc_info.value).code == ErrorCode.METADATA_INVALID_SCHEMA

    def test_process_extracts_issued_year_month(self, handler: MetadataHandler) -> None:
        """process() should extract year-month date format."""
        csl_json = {
            "type": "article-journal",
            "title": "Test",
            "issued": {"date-parts": [[2020, 6]]},  # Year and month only
        }

        result = handler.process(csl_json)

        assert result.issued_date == "2020-06"
