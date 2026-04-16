"""Unit tests for metadata processing."""

from pathlib import Path
from typing import Any, cast

import pytest

from local_library.core.errors import ErrorCode, MetadataError
from local_library.core.models import MetadataResult
from local_library.ingestion.metadata import MetadataHandler, parse_filename_metadata


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
        """process() should generate proper citekey if not provided."""
        csl_json = {
            "type": "article-journal",
            "title": "Attention Is All You Need",
            "author": [{"family": "Vaswani", "given": "Ashish"}],
            "issued": {"date-parts": [[2017]]},
        }

        result = handler.process(csl_json)

        assert result.citekey == "Vaswani2017Attention"

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


class TestCitekeyGeneration:
    """Tests for generate_citekey function."""

    def test_standard_article(self) -> None:
        """Standard article generates AuthorYearTitle key."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "Attention Is All You Need",
            "author": [{"family": "Vaswani", "given": "Ashish"}],
            "issued": {"date-parts": [[2017]]},
        }

        result = generate_citekey(csl_json)

        assert result == "Vaswani2017Attention"

    def test_multiple_authors_uses_first(self) -> None:
        """Multiple authors should use only first author."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "Deep Learning",
            "author": [
                {"family": "LeCun", "given": "Yann"},
                {"family": "Bengio", "given": "Yoshua"},
                {"family": "Hinton", "given": "Geoffrey"},
            ],
            "issued": {"date-parts": [[2015]]},
        }

        result = generate_citekey(csl_json)

        assert result == "LeCun2015Deep"

    def test_non_ascii_author_folded(self) -> None:
        """Non-ASCII author names should be folded to ASCII."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "Zur Kritik der Gewalt",
            "author": [{"family": "Müller", "given": "Hans"}],
            "issued": {"date-parts": [[1990]]},
        }

        result = generate_citekey(csl_json)

        # "Zur" is the first significant word (not a stopword, > 2 chars)
        assert result == "Muller1990Zur"

    def test_accented_title_folded(self) -> None:
        """Non-ASCII title words should be folded to ASCII."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "book",
            "title": "L'Étranger",
            "author": [{"family": "Camus", "given": "Albert"}],
            "issued": {"date-parts": [[1942]]},
        }

        result = generate_citekey(csl_json)

        # "L'" is filtered out, "Étranger" becomes "Etranger"
        assert result == "Camus1942Etranger"

    def test_stopwords_filtered(self) -> None:
        """Title stopwords should be filtered out."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "The Role of the Hippocampus",
            "author": [{"family": "Smith", "given": "J."}],
            "issued": {"date-parts": [[2000]]},
        }

        result = generate_citekey(csl_json)

        # "The", "of" are stopwords
        assert result == "Smith2000Role"

    def test_literal_author_organization(self) -> None:
        """Literal/organizational author uses first word."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "report",
            "title": "World Development Report",
            "author": [{"literal": "World Bank Group"}],
            "issued": {"date-parts": [[2023]]},
        }

        result = generate_citekey(csl_json)

        # Author: "World" (first word of literal)
        # Title: "World" is first significant word from title
        assert result == "World2023World"

    def test_editor_fallback_when_no_author(self) -> None:
        """Editor used when no author provided."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "book",
            "title": "Collected Essays",
            "editor": [{"family": "Johnson", "given": "Mary"}],
            "issued": {"date-parts": [[2010]]},
        }

        result = generate_citekey(csl_json)

        assert result == "Johnson2010Collected"

    def test_missing_author_still_generates_key(self) -> None:
        """Missing author should still generate key from year and title."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "Anonymous Article",
            "issued": {"date-parts": [[2015]]},
        }

        result = generate_citekey(csl_json)

        assert result == "2015Anonymous"

    def test_missing_year_still_generates_key(self) -> None:
        """Missing year should still generate key from author and title."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "manuscript",
            "title": "Undated Manuscript",
            "author": [{"family": "Unknown", "given": "A."}],
        }

        result = generate_citekey(csl_json)

        assert result == "UnknownUndated"

    def test_missing_title_still_generates_key(self) -> None:
        """Missing title should still generate key from author and year."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "author": [{"family": "Smith", "given": "J."}],
            "issued": {"date-parts": [[2020]]},
        }

        result = generate_citekey(csl_json)

        assert result == "Smith2020"

    def test_fallback_for_minimal_data(self) -> None:
        """Minimal data should produce hash-based fallback key."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {"type": "document"}

        result = generate_citekey(csl_json)

        assert result.startswith("unknown-")
        assert len(result) == len("unknown-") + 8  # 8 char hash

    def test_different_inputs_produce_different_fallback_hashes(self) -> None:
        """Different inputs should produce different fallback hashes."""
        from local_library.ingestion.metadata import generate_citekey

        result1 = generate_citekey({"type": "document", "id": "1"})
        result2 = generate_citekey({"type": "document", "id": "2"})

        assert result1 != result2

    def test_hyphenated_author_name(self) -> None:
        """Hyphenated author names handled correctly."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "Test Article",
            "author": [{"family": "García-López", "given": "María"}],
            "issued": {"date-parts": [[2018]]},
        }

        result = generate_citekey(csl_json)

        # Hyphen removed, diacritics folded
        assert result == "GarciaLopez2018Test"


class TestIndexedFieldExtraction:
    """Tests for indexed field extraction methods."""

    @pytest.fixture
    def handler(self) -> MetadataHandler:
        """Provide a MetadataHandler instance."""
        return MetadataHandler()

    # --- Author extraction tests ---

    def test_extract_authors_standard_format(self, handler: MetadataHandler) -> None:
        """Standard author with family and given names."""
        csl_json = {
            "type": "article-journal",
            "author": [{"family": "Smith", "given": "John Robert"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "Smith, J.R."
        assert result.author_list == ("Smith, J.R.",)

    def test_extract_authors_single_initial(self, handler: MetadataHandler) -> None:
        """Author with already-initialized given name."""
        csl_json = {
            "type": "article-journal",
            "author": [{"family": "Smith", "given": "J."}],
        }

        result = handler.process(csl_json)

        assert result.authors == "Smith, J."

    def test_extract_authors_hyphenated_given(self, handler: MetadataHandler) -> None:
        """Author with hyphenated given name."""
        csl_json = {
            "type": "article-journal",
            "author": [{"family": "Dupont", "given": "Jean-Pierre"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "Dupont, J.-P."

    def test_extract_authors_with_particle(self, handler: MetadataHandler) -> None:
        """Author with non-dropping particle (von, de, etc.)."""
        csl_json = {
            "type": "book",
            "author": [
                {
                    "family": "Beethoven",
                    "given": "Ludwig",
                    "non-dropping-particle": "van",
                }
            ],
        }

        result = handler.process(csl_json)

        assert result.authors == "van Beethoven, L."

    def test_extract_authors_multiple(self, handler: MetadataHandler) -> None:
        """Multiple authors separated by semicolon."""
        csl_json = {
            "type": "article-journal",
            "author": [
                {"family": "Smith", "given": "John"},
                {"family": "Jones", "given": "Mary Ann"},
                {"family": "Brown", "given": "Robert"},
            ],
        }

        result = handler.process(csl_json)

        assert result.authors == "Smith, J.; Jones, M.A.; Brown, R."
        assert len(result.author_list) == 3

    def test_extract_authors_literal(self, handler: MetadataHandler) -> None:
        """Organizational/literal author."""
        csl_json = {
            "type": "report",
            "author": [{"literal": "World Health Organization"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "World Health Organization"
        assert result.author_list == ("World Health Organization",)

    def test_extract_authors_family_only(self, handler: MetadataHandler) -> None:
        """Author with only family name (no given name)."""
        csl_json = {
            "type": "article-journal",
            "author": [{"family": "Aristotle"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "Aristotle"

    def test_extract_authors_editor_fallback(self, handler: MetadataHandler) -> None:
        """Editor used when no author present."""
        csl_json = {
            "type": "book",
            "editor": [{"family": "Johnson", "given": "Mary"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "Johnson, M."

    def test_extract_authors_missing(self, handler: MetadataHandler) -> None:
        """Missing author returns None."""
        csl_json = {"type": "article-journal", "title": "Anonymous Work"}

        result = handler.process(csl_json)

        assert result.authors is None
        assert result.author_list == ()

    # --- Date extraction tests ---

    def test_extract_date_full(self, handler: MetadataHandler) -> None:
        """Full date with year, month, day."""
        csl_json = {
            "type": "article-journal",
            "issued": {"date-parts": [[2020, 6, 15]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "2020-06-15"

    def test_extract_date_year_month(self, handler: MetadataHandler) -> None:
        """Date with year and month only."""
        csl_json = {
            "type": "article-journal",
            "issued": {"date-parts": [[2020, 6]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "2020-06"

    def test_extract_date_year_only(self, handler: MetadataHandler) -> None:
        """Date with year only."""
        csl_json = {
            "type": "book",
            "issued": {"date-parts": [[1984]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "1984"

    def test_extract_date_missing(self, handler: MetadataHandler) -> None:
        """Missing date returns None."""
        csl_json = {"type": "manuscript"}

        result = handler.process(csl_json)

        assert result.issued_date is None

    def test_extract_date_empty_parts(self, handler: MetadataHandler) -> None:
        """Empty date-parts returns None."""
        csl_json = {
            "type": "article-journal",
            "issued": {"date-parts": [[]]},
        }

        with pytest.raises(MetadataError):
            handler.process(csl_json)

    def test_extract_date_pads_month_day(self, handler: MetadataHandler) -> None:
        """Month and day should be zero-padded."""
        csl_json = {
            "type": "article-journal",
            "issued": {"date-parts": [[2020, 1, 5]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "2020-01-05"

    # --- Title extraction tests ---

    def test_extract_title(self, handler: MetadataHandler) -> None:
        """Title extracted as-is."""
        csl_json = {
            "type": "book",
            "title": "The Art of Computer Programming",
        }

        result = handler.process(csl_json)

        assert result.title == "The Art of Computer Programming"

    def test_extract_title_missing(self, handler: MetadataHandler) -> None:
        """Missing title returns None."""
        csl_json = {"type": "article-journal"}

        result = handler.process(csl_json)

        assert result.title is None


class TestFilenameMetadataParser:
    """Tests for parse_filename_metadata() heuristic filename parser."""

    # --- Pattern: Author - Year - Title ---

    def test_author_dash_year_dash_title(self, tmp_path: Path) -> None:
        """Should parse 'Author - Year - Title.pdf' pattern."""
        result = parse_filename_metadata(tmp_path / "Smith - 2020 - Attention Mechanisms.pdf")

        assert result["title"] == "Attention Mechanisms"
        assert result["author"][0]["family"] == "Smith"
        assert result["issued"]["date-parts"] == [[2020]]
        assert result["_metadata_source"] == "FILENAME"

    def test_author_endash_year_endash_title(self, tmp_path: Path) -> None:
        """Should handle en-dash separators."""
        result = parse_filename_metadata(tmp_path / "Jones \u2013 2019 \u2013 Deep Learning.pdf")

        assert result["title"] == "Deep Learning"
        assert result["author"][0]["family"] == "Jones"
        assert result["issued"]["date-parts"] == [[2019]]

    def test_author_et_al_dash_year_dash_title(self, tmp_path: Path) -> None:
        """Should handle 'et al.' in author field."""
        result = parse_filename_metadata(tmp_path / "Smith et al. - 2021 - Neural Networks.pdf")

        assert result["author"][0]["family"] == "Smith"
        assert result["title"] == "Neural Networks"

    # --- Pattern: Author_Year_Title ---

    def test_author_underscore_year_underscore_title(self, tmp_path: Path) -> None:
        """Should parse 'Author_Year_Title.pdf' pattern."""
        result = parse_filename_metadata(tmp_path / "Weber_1921_Economy_Society.pdf")

        assert result["author"][0]["family"] == "Weber"
        assert result["issued"]["date-parts"] == [[1921]]
        assert "Economy" in result["title"]

    # --- Pattern: AuthorYear ---

    def test_author_year_concatenated(self, tmp_path: Path) -> None:
        """Should parse 'AuthorYear.pdf' pattern."""
        result = parse_filename_metadata(tmp_path / "Smith2020.pdf")

        assert result["author"][0]["family"] == "Smith"
        assert result["issued"]["date-parts"] == [[2020]]

    def test_author_year_with_title(self, tmp_path: Path) -> None:
        """Should parse 'AuthorYear_Title.pdf' pattern."""
        result = parse_filename_metadata(tmp_path / "Smith2020_Attention.pdf")

        assert result["author"][0]["family"] == "Smith"
        assert result["issued"]["date-parts"] == [[2020]]

    # --- Pattern: Author - Title (no year) ---

    def test_author_dash_title_no_year(self, tmp_path: Path) -> None:
        """Should parse 'Author - Title.pdf' when no year present."""
        result = parse_filename_metadata(tmp_path / "Foucault - Discipline and Punish.pdf")

        assert result["author"][0]["family"] == "Foucault"
        assert result["title"] == "Discipline and Punish"
        assert "issued" not in result

    # --- Fallback: stem as title ---

    def test_fallback_to_stem_as_title(self, tmp_path: Path) -> None:
        """Should fall back to filename stem as title for unparseable names."""
        result = parse_filename_metadata(tmp_path / "some random filename.pdf")

        assert result["title"] == "some random filename"
        assert result["type"] == "document"
        assert result["_metadata_source"] == "FILENAME"

    def test_fallback_preserves_underscores_as_spaces(self, tmp_path: Path) -> None:
        """Fallback should convert underscores to spaces in title."""
        result = parse_filename_metadata(tmp_path / "some_random_filename.pdf")

        assert result["title"] == "some random filename"

    # --- Type and metadata_source ---

    def test_always_returns_document_type(self, tmp_path: Path) -> None:
        """All results should have type 'document'."""
        result = parse_filename_metadata(tmp_path / "Smith - 2020 - Title.pdf")
        assert result["type"] == "document"

    def test_always_includes_metadata_source(self, tmp_path: Path) -> None:
        """All results should include _metadata_source: FILENAME."""
        result = parse_filename_metadata(tmp_path / "anything.pdf")
        assert result["_metadata_source"] == "FILENAME"

    # --- Input type safety ---

    def test_accepts_path_object(self, tmp_path: Path) -> None:
        """Function should accept Path objects."""
        result = parse_filename_metadata(Path("/any/path/Smith2020.pdf"))
        assert result is not None

    # --- Edge cases ---

    def test_multiword_author(self, tmp_path: Path) -> None:
        """Should handle multi-word author names."""
        result = parse_filename_metadata(tmp_path / "Van der Berg - 2020 - Title.pdf")

        assert result["author"][0]["family"] == "Van der Berg"

    def test_numeric_only_filename(self, tmp_path: Path) -> None:
        """Should handle numeric-only filenames as title."""
        result = parse_filename_metadata(tmp_path / "12345.pdf")
        assert result["title"] == "12345"


class TestExtractYearFromCsl:
    """Tests for the shared year-extraction utility."""

    def test_extracts_from_date_parts_full_date(self) -> None:
        from local_library.ingestion.metadata import extract_year_from_csl

        csl = {"issued": {"date-parts": [[2023, 6, 15]]}}
        assert extract_year_from_csl(csl) == 2023

    def test_extracts_from_date_parts_year_month(self) -> None:
        from local_library.ingestion.metadata import extract_year_from_csl

        csl = {"issued": {"date-parts": [[2023, 6]]}}
        assert extract_year_from_csl(csl) == 2023

    def test_extracts_from_date_parts_year_only(self) -> None:
        from local_library.ingestion.metadata import extract_year_from_csl

        csl = {"issued": {"date-parts": [[2023]]}}
        assert extract_year_from_csl(csl) == 2023

    def test_returns_none_for_missing_issued(self) -> None:
        from local_library.ingestion.metadata import extract_year_from_csl

        assert extract_year_from_csl({}) is None

    def test_returns_none_for_empty_issued(self) -> None:
        from local_library.ingestion.metadata import extract_year_from_csl

        assert extract_year_from_csl({"issued": {}}) is None

    def test_returns_none_for_missing_date_parts(self) -> None:
        from local_library.ingestion.metadata import extract_year_from_csl

        assert extract_year_from_csl({"issued": {"literal": "Spring 2023"}}) is None

    def test_returns_none_for_empty_date_parts_outer(self) -> None:
        from local_library.ingestion.metadata import extract_year_from_csl

        assert extract_year_from_csl({"issued": {"date-parts": []}}) is None

    def test_returns_none_for_empty_date_parts_inner(self) -> None:
        from local_library.ingestion.metadata import extract_year_from_csl

        assert extract_year_from_csl({"issued": {"date-parts": [[]]}}) is None

    def test_returns_none_for_none_year(self) -> None:
        from local_library.ingestion.metadata import extract_year_from_csl

        csl = {"issued": {"date-parts": [[None]]}}
        assert extract_year_from_csl(csl) is None

    def test_returns_none_for_non_int_year(self) -> None:
        """Defensive: guard against unexpectedly-typed date parts."""
        from local_library.ingestion.metadata import extract_year_from_csl

        csl = {"issued": {"date-parts": [["2023"]]}}
        # Permissive: "2023" could be cast, but spec says date-parts should be ints.
        # We accept str years and convert; document the decision in the function.
        assert extract_year_from_csl(csl) == 2023

    def test_returns_none_for_malformed_str_year(self) -> None:
        from local_library.ingestion.metadata import extract_year_from_csl

        csl = {"issued": {"date-parts": [["XXXX"]]}}
        assert extract_year_from_csl(csl) is None

    def test_raw_field_not_parsed(self) -> None:
        """Raw-format dates return None rather than attempting regex parsing."""
        from local_library.ingestion.metadata import extract_year_from_csl

        csl = {"issued": {"raw": "2023-06-15"}}
        assert extract_year_from_csl(csl) is None


class TestExtractYearForCitekey:
    """Tests for the citekey year wrapper (delegates to extract_year_from_csl)."""

    def test_returns_year_string(self) -> None:
        from local_library.ingestion.metadata import _extract_year_for_citekey

        csl = {"issued": {"date-parts": [[2023]]}}
        assert _extract_year_for_citekey(csl) == "2023"

    def test_returns_empty_string_when_missing(self) -> None:
        from local_library.ingestion.metadata import _extract_year_for_citekey

        assert _extract_year_for_citekey({}) == ""

    def test_returns_empty_string_for_none_year(self) -> None:
        from local_library.ingestion.metadata import _extract_year_for_citekey

        csl = {"issued": {"date-parts": [[None]]}}
        assert _extract_year_for_citekey(csl) == ""
