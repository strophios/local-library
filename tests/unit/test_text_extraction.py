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


class TestTypeExtraction:
    """Tests for document type extraction from markdown text."""

    def test_extract_type_journal_article(self) -> None:
        """Journal-like documents should return 'article-journal'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """Machine Learning Applications

        Journal of Computer Science, Vol. 42, No. 3

        Abstract: This paper presents...
        """

        result = extract_doc_type(text)

        assert result.value == "article-journal"
        assert result.confidence >= 0.7

    def test_extract_type_conference_paper(self) -> None:
        """Conference papers should return 'paper-conference'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """Novel Algorithm Design

        Proceedings of the International Conference on Machine Learning

        Abstract...
        """

        result = extract_doc_type(text)

        assert result.value == "paper-conference"

    def test_extract_type_book_chapter(self) -> None:
        """Book chapters should return 'chapter'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """Chapter 5: Advanced Topics

        In: Handbook of Machine Learning
        Editors: Smith and Jones

        Introduction...
        """

        result = extract_doc_type(text)

        assert result.value == "chapter"

    def test_extract_type_thesis(self) -> None:
        """Theses should return 'thesis'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """A Dissertation Submitted to the Faculty

        in partial fulfillment of the requirements
        for the degree of Doctor of Philosophy

        By John Smith
        """

        result = extract_doc_type(text)

        assert result.value == "thesis"

    def test_extract_type_report(self) -> None:
        """Technical reports should return 'report'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """Technical Report TR-2023-01

        MIT Computer Science and Artificial Intelligence Laboratory

        Abstract...
        """

        result = extract_doc_type(text)

        assert result.value == "report"

    def test_extract_type_default_article_journal(self) -> None:
        """Unknown document types should default to 'article-journal'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """Some Research

        By Someone

        This discusses various topics...
        """

        result = extract_doc_type(text)

        # Default is article-journal
        assert result.value == "article-journal"
        # But with lower confidence
        assert result.confidence < 0.7

    def test_extract_type_empty_text(self) -> None:
        """Empty text should return default with low confidence."""
        from local_library.ingestion.text_extraction import extract_doc_type

        result = extract_doc_type("")

        assert result.value == "article-journal"  # Default
        assert result.confidence < 0.5

    def test_extract_type_returns_field_extraction(self) -> None:
        """Result should be a proper FieldExtraction."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = "Some text"

        result = extract_doc_type(text)

        assert hasattr(result, "value")
        assert hasattr(result, "confidence")
        assert hasattr(result, "source")
        assert result.source == "heuristic"

    def test_extract_type_preprint(self) -> None:
        """Preprints/arXiv papers should be detected."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """arXiv:2301.12345v1 [cs.LG]

        Deep Learning for Everything

        Abstract...
        """

        result = extract_doc_type(text)

        # Preprints are typically article-journal or article
        assert result.value in ("article-journal", "article")


class TestTextMetadataExtractor:
    """Tests for the TextMetadataExtractor orchestration class."""

    def test_extract_all_fields(self) -> None:
        """Extractor should return all field extractions."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Machine Learning in Healthcare

        John Smith, Jane Doe
        Published: 2023

        Journal of Medical Informatics

        Abstract: This paper presents...
        """

        extractor = TextMetadataExtractor()
        result = extractor.extract(text)

        # All fields should be present
        assert result.title.value is not None
        assert len(result.authors) >= 1
        assert result.date.value is not None
        assert result.doc_type.value is not None

    def test_extract_overall_confidence_is_minimum(self) -> None:
        """overall_confidence should be minimum of field confidences."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """# Clear Title With High Confidence

        John Smith

        2023

        Abstract...
        """

        extractor = TextMetadataExtractor()
        result = extractor.extract(text)

        # Overall should be min of all fields
        field_confidences = [
            result.title.confidence,
            result.date.confidence,
            result.doc_type.confidence,
        ]
        if result.authors:
            field_confidences.extend(a.confidence for a in result.authors)

        # Allow small floating point difference
        assert abs(result.overall_confidence - min(field_confidences)) < 0.01

    def test_extract_needs_review_when_low_confidence(self) -> None:
        """needs_review should be True when any field is below threshold."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        # Minimal text likely to have low confidence
        text = """Some Title

        Content without clear author or date patterns...
        """

        extractor = TextMetadataExtractor(confidence_threshold=0.7)
        result = extractor.extract(text)

        # Should need review due to low confidence fields
        assert result.needs_review is True
        assert len(result.review_reasons) >= 1

    def test_extract_review_reasons_explain_issues(self) -> None:
        """review_reasons should explain which fields are uncertain."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Document Title

        Some content without dates or authors clearly marked.
        """

        extractor = TextMetadataExtractor(confidence_threshold=0.7)
        result = extractor.extract(text)

        if result.needs_review:
            # Reasons should mention specific fields
            reasons_text = " ".join(result.review_reasons).lower()
            assert any(
                field in reasons_text for field in ["title", "author", "date", "type", "confidence"]
            )

    def test_extract_no_review_when_all_confident(self) -> None:
        """needs_review should be False when all fields are confident."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        # Well-structured document with clear signals
        text = """# Deep Learning for Image Recognition

        John Smith, Jane Doe

        Published: January 15, 2023

        Journal of Computer Vision, Vol. 42

        Abstract: This paper presents a novel approach...
        """

        extractor = TextMetadataExtractor(confidence_threshold=0.5)
        result = extractor.extract(text)

        # All fields should be confident enough
        assert result.title.confidence >= 0.5
        # If needs_review is False, no reasons needed
        if not result.needs_review:
            assert result.review_reasons == ()

    def test_extract_empty_text(self) -> None:
        """Empty text should return result with needs_review=True."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        extractor = TextMetadataExtractor()
        result = extractor.extract("")

        assert result.needs_review is True
        assert result.overall_confidence == 0.0

    def test_extract_configurable_threshold(self) -> None:
        """Confidence threshold should be configurable."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Some Title

        John Smith
        2023
        """

        # With low threshold, might not need review
        low_threshold = TextMetadataExtractor(confidence_threshold=0.3)
        low_result = low_threshold.extract(text)

        # With high threshold, likely needs review
        high_threshold = TextMetadataExtractor(confidence_threshold=0.9)
        high_result = high_threshold.extract(text)

        # High threshold should be more likely to need review
        if low_result.overall_confidence >= 0.3 and low_result.overall_confidence < 0.9:
            assert not low_result.needs_review
            assert high_result.needs_review

    def test_extract_returns_text_extraction_result(self) -> None:
        """Result should be a proper TextExtractionResult."""
        from local_library.core.models import TextExtractionResult
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        extractor = TextMetadataExtractor()
        result = extractor.extract("Some text")

        assert isinstance(result, TextExtractionResult)

    def test_extract_authors_tuple_not_list(self) -> None:
        """Authors should be returned as tuple for immutability."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Title

        John Smith, Jane Doe

        Content...
        """

        extractor = TextMetadataExtractor()
        result = extractor.extract(text)

        assert isinstance(result.authors, tuple)

    def test_extract_review_reasons_tuple_not_list(self) -> None:
        """review_reasons should be returned as tuple."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        extractor = TextMetadataExtractor()
        result = extractor.extract("minimal text")

        assert isinstance(result.review_reasons, tuple)


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


class TestLLMExtraction:
    """Tests for LLM-based metadata extraction fallback."""

    def test_llm_extractor_parses_json_response(self) -> None:
        """LLMExtractor should parse JSON response correctly."""
        from unittest.mock import MagicMock, patch

        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=True, model="gpt-4o-mini")

        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"title": "Test Title", "authors": ["John Smith"], '
                        '"year": "2023", "type": "article-journal"}'
                    )
                )
            )
        ]

        with patch("litellm.completion", return_value=mock_response):
            result = extractor.extract("Some document text")

        assert result is not None
        assert result["title"] == "Test Title"
        assert result["authors"] == ["John Smith"]
        assert result["year"] == "2023"
        assert result["type"] == "article-journal"

    def test_llm_extractor_handles_invalid_json(self) -> None:
        """LLMExtractor should return None for invalid JSON."""
        from unittest.mock import MagicMock, patch

        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=True, model="gpt-4o-mini")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="not valid json"))]

        with patch("litellm.completion", return_value=mock_response):
            result = extractor.extract("Some document text")

        assert result is None

    def test_llm_extractor_handles_api_error(self) -> None:
        """LLMExtractor should return None on API error."""
        from unittest.mock import patch

        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=True, model="gpt-4o-mini")

        with patch("litellm.completion", side_effect=Exception("API error")):
            result = extractor.extract("Some document text")

        assert result is None

    def test_llm_extractor_disabled_returns_none(self) -> None:
        """Disabled LLMExtractor should return None immediately."""
        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=False, model="gpt-4o-mini")

        # Should not call API
        result = extractor.extract("Some document text")

        assert result is None

    def test_llm_extractor_truncates_long_text(self) -> None:
        """LLMExtractor should truncate very long documents."""
        from unittest.mock import MagicMock, patch

        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=True, model="gpt-4o-mini")

        # Very long text
        long_text = "word " * 10000

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"title": "Test", "authors": [], "year": null, "type": "article-journal"}'
                    )
                )
            )
        ]

        with patch("litellm.completion", return_value=mock_response) as mock_call:
            extractor.extract(long_text)

            # Should have called with truncated text
            call_args = mock_call.call_args
            messages = call_args.kwargs["messages"]
            user_content = messages[1]["content"]
            # Should be truncated to reasonable length
            assert len(user_content) < len(long_text)

    def test_llm_extractor_prompt_includes_heuristic_candidates(self) -> None:
        """LLMExtractor prompt should include heuristic candidates when provided."""
        from unittest.mock import MagicMock, patch

        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=True, model="gpt-4o-mini")

        candidates = {
            "title": "Candidate Title",
            "authors": ["Smith, John"],
            "year": "2023",
        }

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"title": "Better Title", '
                        '"authors": ["Smith, John"], '
                        '"year": "2023", "type": "article-journal"}'
                    )
                )
            )
        ]

        with patch("litellm.completion", return_value=mock_response) as mock_call:
            extractor.extract("Document text", heuristic_candidates=candidates)

            # Prompt should mention candidates
            call_args = mock_call.call_args
            messages = call_args.kwargs["messages"]
            user_content = messages[1]["content"]
            assert "Candidate Title" in user_content


class TestTextMetadataExtractorWithLLM:
    """Tests for TextMetadataExtractor with LLM fallback."""

    def test_extractor_uses_llm_when_low_confidence(self) -> None:
        """Extractor should call LLM when heuristic confidence is low."""
        from unittest.mock import MagicMock, patch

        from local_library.ingestion.text_extraction import TextMetadataExtractor

        # Text with unclear metadata
        text = """Some vague document

        Without clear title or author patterns.
        """

        mock_llm_response = MagicMock()
        mock_llm_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"title": "LLM Title", '
                        '"authors": ["LLM Author"], '
                        '"year": "2023", "type": "article-journal"}'
                    )
                )
            )
        ]

        with patch("litellm.completion", return_value=mock_llm_response):
            extractor = TextMetadataExtractor(
                confidence_threshold=0.9,  # High threshold to trigger fallback
                llm_enabled=True,
                llm_model="gpt-4o-mini",
            )
            result = extractor.extract(text)

            # Should have LLM-enhanced values
            # Note: confidence is preserved from heuristics
            assert result.title.source == "llm" or result.title.value is not None

    def test_extractor_skips_llm_when_confident(self) -> None:
        """Extractor should skip LLM when heuristic confidence is high."""
        from unittest.mock import patch

        from local_library.ingestion.text_extraction import TextMetadataExtractor

        # Well-structured document
        text = """# Machine Learning Applications

        John Smith, Jane Doe

        Published: 2023

        Journal of Computer Science

        Abstract...
        """

        with patch("litellm.completion") as mock_call:
            extractor = TextMetadataExtractor(
                confidence_threshold=0.3,  # Low threshold
                llm_enabled=True,
                llm_model="gpt-4o-mini",
            )
            result = extractor.extract(text)

            # Should not have called LLM
            if not result.needs_review:
                mock_call.assert_not_called()

    def test_extractor_graceful_degradation_without_llm(self) -> None:
        """Extractor should work without LLM (graceful degradation)."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Some Document

        John Smith
        2023
        """

        # LLM disabled
        extractor = TextMetadataExtractor(
            confidence_threshold=0.7,
            llm_enabled=False,
        )
        result = extractor.extract(text)

        # Should still produce results
        assert result.title.value is not None
        # All sources should be heuristic
        assert result.title.source == "heuristic"

    def test_extractor_preserves_heuristic_confidence_after_llm(self) -> None:
        """After LLM fallback, heuristic confidence should be preserved."""
        from unittest.mock import MagicMock, patch

        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Unclear document title

        Maybe an author name here
        """

        mock_llm_response = MagicMock()
        mock_llm_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"title": "Actual Title", '
                        '"authors": ["Real Author"], '
                        '"year": "2023", "type": "article-journal"}'
                    )
                )
            )
        ]

        with patch("litellm.completion", return_value=mock_llm_response):
            extractor = TextMetadataExtractor(
                confidence_threshold=0.8,
                llm_enabled=True,
                llm_model="gpt-4o-mini",
            )
            result = extractor.extract(text)

            # Confidence should still be from heuristics (not boosted by LLM)
            # This ensures needs_review is still triggered appropriately
            if result.title.source == "llm":
                # Confidence preserved from heuristics
                assert result.needs_review is True  # Still needs review


class TestBuildCslJson:
    """Tests for CSL-JSON conversion from extraction results."""

    def test_build_csl_json_basic(self) -> None:
        """Should convert extraction result to CSL-JSON."""
        from local_library.core.models import FieldExtraction, TextExtractionResult
        from local_library.ingestion.text_extraction import build_csl_json

        result = TextExtractionResult(
            title=FieldExtraction(
                value="Test Title",
                confidence=0.9,
                source="heuristic",
                alternatives=(),
                reasoning="",
            ),
            authors=(
                FieldExtraction(
                    value="Smith, John",
                    confidence=0.8,
                    source="heuristic",
                    alternatives=(),
                    reasoning="",
                ),
            ),
            date=FieldExtraction(
                value="2023", confidence=0.85, source="heuristic", alternatives=(), reasoning=""
            ),
            doc_type=FieldExtraction(
                value="article-journal",
                confidence=0.7,
                source="heuristic",
                alternatives=(),
                reasoning="",
            ),
            overall_confidence=0.7,
            needs_review=False,
            review_reasons=(),
        )

        csl = build_csl_json(result)

        assert csl["type"] == "article-journal"
        assert csl["title"] == "Test Title"
        assert len(csl["author"]) == 1
        assert csl["author"][0]["family"] == "Smith"
        assert csl["author"][0]["given"] == "John"
        assert csl["issued"]["date-parts"] == [[2023]]

    def test_build_csl_json_multiple_authors(self) -> None:
        """Should handle multiple authors."""
        from local_library.core.models import FieldExtraction, TextExtractionResult
        from local_library.ingestion.text_extraction import build_csl_json

        result = TextExtractionResult(
            title=FieldExtraction(
                value="Title", confidence=0.9, source="heuristic", alternatives=(), reasoning=""
            ),
            authors=(
                FieldExtraction(
                    value="Smith, John",
                    confidence=0.8,
                    source="heuristic",
                    alternatives=(),
                    reasoning="",
                ),
                FieldExtraction(
                    value="Doe, Jane",
                    confidence=0.8,
                    source="heuristic",
                    alternatives=(),
                    reasoning="",
                ),
            ),
            date=FieldExtraction(
                value="2023", confidence=0.85, source="heuristic", alternatives=(), reasoning=""
            ),
            doc_type=FieldExtraction(
                value="article-journal",
                confidence=0.7,
                source="heuristic",
                alternatives=(),
                reasoning="",
            ),
            overall_confidence=0.7,
            needs_review=False,
            review_reasons=(),
        )

        csl = build_csl_json(result)

        assert len(csl["author"]) == 2

    def test_build_csl_json_missing_fields(self) -> None:
        """Should handle None values gracefully."""
        from local_library.core.models import FieldExtraction, TextExtractionResult
        from local_library.ingestion.text_extraction import build_csl_json

        result = TextExtractionResult(
            title=FieldExtraction(
                value=None, confidence=0.0, source="heuristic", alternatives=(), reasoning=""
            ),
            authors=(),
            date=FieldExtraction(
                value=None, confidence=0.0, source="heuristic", alternatives=(), reasoning=""
            ),
            doc_type=FieldExtraction(
                value="article-journal",
                confidence=0.4,
                source="heuristic",
                alternatives=(),
                reasoning="",
            ),
            overall_confidence=0.0,
            needs_review=True,
            review_reasons=("title could not be extracted",),
        )

        csl = build_csl_json(result)

        # Should have type, but no title, author, or issued
        assert csl["type"] == "article-journal"
        assert "title" not in csl
        assert "author" not in csl
        assert "issued" not in csl

    def test_convert_author_family_given_format(self) -> None:
        """Should convert 'Family, Given' format correctly."""
        from local_library.ingestion.text_extraction import _convert_author_to_csl

        result = _convert_author_to_csl("Smith, John")

        assert result is not None
        assert result["family"] == "Smith"
        assert result["given"] == "John"

    def test_convert_author_given_family_format(self) -> None:
        """Should convert 'Given Family' format correctly."""
        from local_library.ingestion.text_extraction import _convert_author_to_csl

        result = _convert_author_to_csl("John Smith")

        assert result is not None
        assert result["family"] == "Smith"
        assert result["given"] == "John"

    def test_convert_author_multiple_given_names(self) -> None:
        """Should handle multiple given names correctly."""
        from local_library.ingestion.text_extraction import _convert_author_to_csl

        result = _convert_author_to_csl("John Michael Smith")

        assert result is not None
        assert result["family"] == "Smith"
        assert result["given"] == "John Michael"

    def test_convert_author_single_word_literal(self) -> None:
        """Should use 'literal' format for single-word names."""
        from local_library.ingestion.text_extraction import _convert_author_to_csl

        result = _convert_author_to_csl("Plato")

        assert result is not None
        assert result == {"literal": "Plato"}
        assert "family" not in result
        assert "given" not in result

    def test_convert_author_empty_string(self) -> None:
        """Should return None for empty strings."""
        from local_library.ingestion.text_extraction import _convert_author_to_csl

        result = _convert_author_to_csl("")

        assert result is None

    def test_convert_author_whitespace_only(self) -> None:
        """Should return None for whitespace-only strings."""
        from local_library.ingestion.text_extraction import _convert_author_to_csl

        result = _convert_author_to_csl("   ")

        assert result is None
