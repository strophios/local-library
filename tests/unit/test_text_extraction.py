"""Tests for text-based metadata extraction."""

from __future__ import annotations

from local_library.ingestion.text_extraction import extract_title


class TestAuthorExtraction:
    """Tests for author extraction from markdown text."""

    def test_extract_authors_single_author(self) -> None:
        """Single author should be extracted correctly."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Machine Learning Fundamentals

        John Smith
        Department of Computer Science

        Abstract: This paper presents...
        """

        result = extract_authors(text)

        assert len(result) == 1
        assert result[0].value is not None
        # Should have family name
        assert "Smith" in result[0].value

    def test_extract_authors_multiple_authors_comma_separated(self) -> None:
        """Multiple comma-separated authors should be extracted."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Research Paper Title

        John Smith, Jane Doe, Bob Wilson
        University Research Lab

        Abstract...
        """

        result = extract_authors(text)

        assert len(result) == 3
        names = [r.value for r in result]
        assert any("Smith" in n for n in names if n)
        assert any("Doe" in n for n in names if n)
        assert any("Wilson" in n for n in names if n)

    def test_extract_authors_with_and_separator(self) -> None:
        """Authors separated by 'and' should be extracted."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Title Here

        John Smith and Jane Doe

        Introduction...
        """

        result = extract_authors(text)

        assert len(result) == 2

    def test_extract_authors_after_by_keyword(self) -> None:
        """Authors prefixed with 'by' should be detected."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Understanding Neural Networks

        by John Smith

        This tutorial explains...
        """

        result = extract_authors(text)

        assert len(result) >= 1
        assert any("Smith" in (r.value or "") for r in result)

    def test_extract_authors_before_abstract(self) -> None:
        """Authors appearing before 'Abstract' should be detected."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Paper Title

        Alice Johnson
        Bob Smith

        Abstract

        This paper discusses...
        """

        result = extract_authors(text)

        assert len(result) >= 2

    def test_extract_authors_with_affiliations_inline(self) -> None:
        """Authors with inline affiliations should have names extracted."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Research Title

        John Smith (MIT), Jane Doe (Stanford)

        Abstract...
        """

        result = extract_authors(text)

        assert len(result) == 2
        # Affiliations should be stripped
        assert "MIT" not in (result[0].value or "")
        assert "Stanford" not in (result[1].value or "")

    def test_extract_authors_with_email(self) -> None:
        """Author lines with emails should extract names only."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Title

        John Smith <john@example.com>

        Content...
        """

        result = extract_authors(text)

        assert len(result) >= 1
        assert "example.com" not in (result[0].value or "")

    def test_extract_authors_empty_text_returns_empty(self) -> None:
        """Empty text should return empty list."""
        from local_library.ingestion.text_extraction import extract_authors

        result = extract_authors("")

        assert result == ()

    def test_extract_authors_no_authors_found(self) -> None:
        """Text without detectable authors should return empty list."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Technical Specification

        1. Introduction
        2. Requirements
        3. Implementation
        """

        result = extract_authors(text)

        # Might return empty or low-confidence results
        assert all(r.confidence < 0.5 for r in result) if result else True

    def test_extract_authors_returns_field_extractions(self) -> None:
        """Each author should be a FieldExtraction with confidence."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Title

        John Smith, Jane Doe

        Content...
        """

        result = extract_authors(text)

        for author in result:
            assert hasattr(author, "value")
            assert hasattr(author, "confidence")
            assert hasattr(author, "source")
            assert author.source == "heuristic"

    def test_extract_authors_handles_initials(self) -> None:
        """Authors with initials should be parsed correctly."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Research Paper

        J. Smith, A.B. Johnson

        Abstract...
        """

        result = extract_authors(text)

        assert len(result) >= 2

    def test_extract_authors_academic_format(self) -> None:
        """Academic format (Last, First) should be handled."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Journal Article

        Smith, John; Doe, Jane; Wilson, Robert

        Abstract...
        """

        result = extract_authors(text)

        assert len(result) == 3

    def test_extract_authors_superscript_affiliations(self) -> None:
        """Superscript affiliation markers should be stripped."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Paper Title

        John Smith¹, Jane Doe², Bob Wilson¹

        ¹MIT, ²Stanford

        Abstract...
        """

        result = extract_authors(text)

        assert len(result) == 3
        # Superscripts should be removed
        assert "¹" not in (result[0].value or "")


class TestDateExtraction:
    """Tests for publication date extraction from markdown text."""

    def test_extract_date_explicit_published(self) -> None:
        """Date with 'Published:' label should be extracted."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Research Paper

        Published: January 15, 2023

        Abstract...
        """

        result = extract_date(text)

        assert result.value == "2023"
        assert result.confidence >= 0.8

    def test_extract_date_copyright_notice(self) -> None:
        """Copyright year should be extracted."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Technical Report

        © 2022 IEEE

        Abstract...
        """

        result = extract_date(text)

        assert result.value == "2022"
        assert result.confidence >= 0.7

    def test_extract_date_copyright_word(self) -> None:
        """'Copyright 2021' pattern should be detected."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Document Title

        Copyright 2021 ACM

        Introduction...
        """

        result = extract_date(text)

        assert result.value == "2021"

    def test_extract_date_iso_format(self) -> None:
        """ISO date format (2023-05-15) should be extracted."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Report

        Date: 2023-05-15

        Content...
        """

        result = extract_date(text)

        assert result.value == "2023"
        assert result.confidence >= 0.7

    def test_extract_date_standalone_year(self) -> None:
        """Standalone year in header area should be extracted."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Paper Title

        John Smith
        2020

        Abstract...
        """

        result = extract_date(text)

        assert result.value == "2020"
        # Lower confidence for standalone year
        assert result.confidence >= 0.4
        assert result.confidence < 0.8

    def test_extract_date_rejects_future_years(self) -> None:
        """Years in the far future should be rejected or low confidence."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Predictions for 2050

        By 2100, climate change will...
        """

        result = extract_date(text)

        # Should not pick 2050 or 2100 as publication date
        if result.value:
            assert int(result.value) <= 2030 or result.confidence < 0.3

    def test_extract_date_rejects_old_years(self) -> None:
        """Very old years (pre-1900) should be low confidence unless explicit."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Analysis of 1776 Events

        Historical analysis of events in 1776...
        """

        result = extract_date(text)

        # Should not confidently pick 1776 as publication date
        if result.value == "1776":
            assert result.confidence < 0.5

    def test_extract_date_prefers_header_area(self) -> None:
        """Years in header area should be preferred over body."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Paper Title

        Published: 2022

        In 2010, researchers discovered...
        Later in 2015, this was confirmed...
        """

        result = extract_date(text)

        assert result.value == "2022"

    def test_extract_date_multiple_formats(self) -> None:
        """Should handle multiple date formats."""
        from local_library.ingestion.text_extraction import extract_date

        formats = [
            ("January 2023", "2023"),
            ("Jan. 2023", "2023"),
            ("01/2023", "2023"),
            ("2023-01", "2023"),
            ("March 15, 2022", "2022"),
        ]

        for date_str, expected_year in formats:
            text = f"Title\n\nPublished: {date_str}\n\nContent..."
            result = extract_date(text)
            assert result.value == expected_year, f"Failed for format: {date_str}"

    def test_extract_date_empty_text_returns_none(self) -> None:
        """Empty text should return None with zero confidence."""
        from local_library.ingestion.text_extraction import extract_date

        result = extract_date("")

        assert result.value is None
        assert result.confidence == 0.0

    def test_extract_date_no_date_found(self) -> None:
        """Text without dates should return None."""
        from local_library.ingestion.text_extraction import extract_date

        text = """A Document Without Dates

        This paper discusses various topics
        without mentioning any specific years.
        """

        result = extract_date(text)

        assert result.value is None
        assert result.confidence == 0.0

    def test_extract_date_returns_field_extraction(self) -> None:
        """Result should be a proper FieldExtraction."""
        from local_library.ingestion.text_extraction import extract_date

        text = "Title\n\n2023\n\nContent"

        result = extract_date(text)

        assert hasattr(result, "value")
        assert hasattr(result, "confidence")
        assert hasattr(result, "source")
        assert result.source == "heuristic"


class TestTitleExtraction:
    """Tests for title extraction from markdown text."""

    def test_extract_title_from_first_line(self) -> None:
        """Title should be extracted from isolated first line."""
        text = """The Impact of Climate Change on Biodiversity

        This paper examines the relationship between global warming
        and species extinction rates across multiple ecosystems.
        """

        result = extract_title(text)

        assert result.value == "The Impact of Climate Change on Biodiversity"
        assert result.confidence >= 0.7
        assert result.source == "heuristic"

    def test_extract_title_skips_blank_lines(self) -> None:
        """Extractor should skip leading blank lines."""
        text = """

        Machine Learning in Healthcare

        Abstract: This study presents a novel approach...
        """

        result = extract_title(text)

        assert result.value == "Machine Learning in Healthcare"

    def test_extract_title_from_markdown_header(self) -> None:
        """Title should be extracted from markdown # header."""
        text = """# A Survey of Natural Language Processing

        ## Introduction

        Natural language processing has seen remarkable advances...
        """

        result = extract_title(text)

        assert result.value == "A Survey of Natural Language Processing"
        assert result.confidence >= 0.7  # Headers give high confidence

    def test_extract_title_prefers_header_over_plain_text(self) -> None:
        """Markdown headers should be preferred over plain text."""
        text = """Journal of Computer Science
        Volume 42, Issue 3

        # Deep Learning for Image Recognition

        Abstract...
        """

        result = extract_title(text)

        # Should pick the header, not "Journal of Computer Science"
        assert result.value == "Deep Learning for Image Recognition"

    def test_extract_title_handles_multiline_title(self) -> None:
        """Titles spanning multiple lines should be joined."""
        text = """Understanding the Long-Term Effects of
        Monetary Policy on Economic Growth

        John Smith, Jane Doe
        University of Economics
        """

        result = extract_title(text)

        # Should join the two lines
        assert result.value is not None
        assert "Long-Term Effects" in result.value
        assert "Economic Growth" in result.value

    def test_extract_title_confidence_from_isolation(self) -> None:
        """Isolated titles (followed by blank line) should have higher confidence."""
        # Well-isolated title
        text_isolated = """Learning Algorithms

        Volume 5, Issue 2

        Abstract: This paper presents...
        """

        # Non-isolated title (runs into next line)
        text_run_on = """Learning Algorithms
        Volume 5, Issue 2
        Abstract: This paper presents...
        """

        result_isolated = extract_title(text_isolated)
        result_run_on = extract_title(text_run_on)

        # Isolated should have higher confidence (not affected by metadata penalization)
        assert result_isolated.confidence >= result_run_on.confidence

    def test_extract_title_rejects_too_short(self) -> None:
        """Very short lines should not be considered titles."""
        text = """A

        This is the actual title of the document

        And here is some content...
        """

        result = extract_title(text)

        # Should not pick "A" as title
        assert result.value != "A"
        assert len(result.value or "") > 5

    def test_extract_title_rejects_too_long(self) -> None:
        """Very long lines (likely paragraphs) should not be titles."""
        long_line = (
            "This is a very long line that goes on and on and contains way too many "
            "words to be a reasonable title for any academic paper or technical "
            "document because titles are supposed to be concise and informative not "
            "rambling paragraphs of text that nobody wants to read."
        )
        text = f"""{long_line}

        Actual Document Title

        Here is the content...
        """

        result = extract_title(text)

        # Should pick the shorter line
        assert result.value == "Actual Document Title"

    def test_extract_title_empty_text_returns_none(self) -> None:
        """Empty text should return None value with zero confidence."""
        result = extract_title("")

        assert result.value is None
        assert result.confidence == 0.0
        assert "empty" in result.reasoning.lower() or "no" in result.reasoning.lower()

    def test_extract_title_whitespace_only_returns_none(self) -> None:
        """Whitespace-only text should return None value."""
        result = extract_title("   \n\n   \t\t\n   ")

        assert result.value is None
        assert result.confidence == 0.0

    def test_extract_title_provides_alternatives(self) -> None:
        """Extraction should provide alternative candidates."""
        text = """Document Processing Systems

        A Comprehensive Guide

        Introduction to the field...
        """

        result = extract_title(text)

        # Should have considered both candidates
        assert len(result.alternatives) >= 1

    def test_extract_title_reasoning_explains_choice(self) -> None:
        """Reasoning should explain why this title was chosen."""
        text = """# Important Research Finding

        Some content here...
        """

        result = extract_title(text)

        # Reasoning should mention why (e.g., "markdown header", "first line")
        assert len(result.reasoning) > 0
        assert "header" in result.reasoning.lower() or "first" in result.reasoning.lower()
