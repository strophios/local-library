"""Tests for text-based metadata extraction."""

from __future__ import annotations

from local_library.ingestion.text_extraction import extract_title


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
