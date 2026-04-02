"""Tests for markdown cleanup post-processing."""

from __future__ import annotations

from unittest.mock import patch

from local_library.ingestion.markdown_cleanup import (
    _coerce_html,
    _dehyphenate,
    _is_structural_line,
    _load_word_set,
    _reflow_paragraphs,
    _should_remove_hyphen,
    cleanup_markdown,
)

# ===================================================================
# Phase 1: HTML Coercion
# ===================================================================


class TestHtmlCoercion:
    """Tests for _coerce_html pass."""

    def test_italic_tags(self) -> None:
        assert _coerce_html("<i>italic</i>") == "*italic*"
        assert _coerce_html("<em>emphasized</em>") == "*emphasized*"

    def test_bold_tags(self) -> None:
        assert _coerce_html("<b>bold</b>") == "**bold**"
        assert _coerce_html("<strong>strong</strong>") == "**strong**"

    def test_footnote_superscript(self) -> None:
        """Digit-only superscripts become bracketed footnote markers."""
        assert _coerce_html("text<sup>1</sup>") == "text[1]"
        assert _coerce_html("text<sup>12.</sup>") == "text[12]"
        assert _coerce_html("text<sup>3</sup> more") == "text[3] more"

    def test_math_superscript(self) -> None:
        """Non-digit superscripts are stripped but content kept (no brackets).
        Digit-only sups always become footnote markers since Marker uses
        LaTeX for math, not HTML <sup>."""
        assert _coerce_html("x<sup>2</sup>") == "x[2]"
        assert _coerce_html("x<sup>n+1</sup>") == "xn+1"

    def test_br_variants(self) -> None:
        assert _coerce_html("a<br>b") == "a b"
        assert _coerce_html("a<br/>b") == "a b"
        assert _coerce_html("a<br />b") == "a b"
        assert _coerce_html("a<BR>b") == "a b"

    def test_remaining_tags_stripped(self) -> None:
        assert _coerce_html("<span>text</span>") == "text"
        assert _coerce_html("<div>block</div>") == "block"
        assert _coerce_html("a<sub>2</sub>") == "a2"

    def test_empty_input(self) -> None:
        assert _coerce_html("") == ""

    def test_no_html_passthrough(self) -> None:
        text = "This is plain markdown with *emphasis* and **bold**."
        assert _coerce_html(text) == text

    def test_multiline_tag_content(self) -> None:
        assert _coerce_html("<i>line one\nline two</i>") == "*line one\nline two*"

    def test_nested_tags(self) -> None:
        """Bold inside italic - outer tags converted, inner stripped."""
        result = _coerce_html("<i><b>bold italic</b></i>")
        assert "bold italic" in result

    def test_mixed_html_and_markdown(self) -> None:
        text = "This has <i>html italic</i> and *md italic*."
        result = _coerce_html(text)
        assert result == "This has *html italic* and *md italic*."

    def test_stray_angle_bracket_does_not_gobble_content(self) -> None:
        """A stray < from OCR or editorial notation must not strip cross-line content.

        Without the newline guard in step 6's regex, a stray < matches
        everything until the next > (potentially pages away), destroying
        content. This occurred with German Winkelklammern notation in
        Marx1968, stripping 49% of the document.
        """
        text = "Before <) stray bracket\n\nImportant content\n\nMore content"
        result = _coerce_html(text)
        assert "Important content" in result
        assert "More content" in result

    def test_stray_angle_bracket_stripped_within_line(self) -> None:
        """Stray angle bracket content within a single line is still stripped."""
        text = "Text with <stray> more text"
        result = _coerce_html(text)
        assert result == "Text with  more text"


class TestCleanupMarkdownComposition:
    """Tests for the top-level cleanup_markdown function."""

    def test_empty_string(self) -> None:
        assert cleanup_markdown("") == ""

    def test_plain_markdown_unchanged(self) -> None:
        text = "# Heading\n\nA paragraph.\n\n- list item\n"
        assert cleanup_markdown(text) == text

    def test_composes_html_coercion(self) -> None:
        result = cleanup_markdown("<b>bold</b> text")
        assert "**bold**" in result

    def test_never_raises(self) -> None:
        """cleanup_markdown should return input if all passes fail."""
        with patch(
            "local_library.ingestion.markdown_cleanup._coerce_html",
            side_effect=RuntimeError("boom"),
        ):
            result = cleanup_markdown("some text")
            assert result == "some text"


# ===================================================================
# Phase 2: Dehyphenation
# ===================================================================


class TestWordSet:
    """Tests for word set loading."""

    def test_load_word_set_returns_frozenset(self) -> None:
        result = _load_word_set()
        assert isinstance(result, frozenset)

    def test_load_word_set_fallback_on_missing_file(self) -> None:
        """Returns empty frozenset when dict file unavailable."""
        import local_library.ingestion.markdown_cleanup as mod

        original = mod._WORD_SET
        try:
            mod._WORD_SET = None  # Force reload
            with patch("builtins.open", side_effect=OSError("no file")):
                result = _load_word_set()
                assert result == frozenset()
        finally:
            mod._WORD_SET = original


class TestShouldRemoveHyphen:
    """Tests for _should_remove_hyphen validation."""

    def test_joined_in_dictionary(self) -> None:
        """Known joined word → remove hyphen."""
        with patch(
            "local_library.ingestion.markdown_cleanup._load_word_set",
            return_value=frozenset(["experiences", "determination"]),
        ):
            assert _should_remove_hyphen("experi", "ences") is True

    def test_hyphenated_in_dictionary(self) -> None:
        """Known hyphenated word → keep hyphen."""
        with patch(
            "local_library.ingestion.markdown_cleanup._load_word_set",
            return_value=frozenset(["self-determination"]),
        ):
            assert _should_remove_hyphen("self", "determination") is False

    def test_suffix_fallback(self) -> None:
        """Common suffix triggers removal when no dict match."""
        with patch(
            "local_library.ingestion.markdown_cleanup._load_word_set",
            return_value=frozenset(),
        ):
            assert _should_remove_hyphen("implementa", "tion") is True
            assert _should_remove_hyphen("develop", "ment") is True
            assert _should_remove_hyphen("process", "ing") is True

    def test_default_keeps_hyphen(self) -> None:
        """No match → conservative default keeps hyphen."""
        with patch(
            "local_library.ingestion.markdown_cleanup._load_word_set",
            return_value=frozenset(),
        ):
            assert _should_remove_hyphen("foo", "bar") is False


class TestDehyphenation:
    """Tests for _dehyphenate pass."""

    def test_simple_dehyphenation(self) -> None:
        """Word split across lines is rejoined."""
        with patch(
            "local_library.ingestion.markdown_cleanup._load_word_set",
            return_value=frozenset(["experiences"]),
        ):
            result = _dehyphenate("experi-\nences are important")
            assert result == "experiences are important"

    def test_compound_preservation(self) -> None:
        """Known compound words keep their hyphen."""
        with patch(
            "local_library.ingestion.markdown_cleanup._load_word_set",
            return_value=frozenset(["self-determination"]),
        ):
            result = _dehyphenate("self-\ndetermination is key")
            assert result == "self-determination is key"

    def test_uppercase_continuation_skipped(self) -> None:
        """Uppercase continuation is not matched (proper nouns, e.g., Smith-Jones)."""
        result = _dehyphenate("Smith-\nJones wrote a paper")
        # Regex requires lowercase after newline, so this should be unchanged
        assert result == "Smith-\nJones wrote a paper"

    def test_no_hyphen_passthrough(self) -> None:
        text = "No hyphens here.\nJust normal lines."
        assert _dehyphenate(text) == text

    def test_multiple_dehyphenations(self) -> None:
        """Multiple hyphenated words in one text."""
        with patch(
            "local_library.ingestion.markdown_cleanup._load_word_set",
            return_value=frozenset(["experiences", "important"]),
        ):
            result = _dehyphenate("experi-\nences are impor-\ntant")
            assert result == "experiences are important"

    def test_whitespace_after_newline(self) -> None:
        """Handles indentation after newline."""
        with patch(
            "local_library.ingestion.markdown_cleanup._load_word_set",
            return_value=frozenset(["experiences"]),
        ):
            result = _dehyphenate("experi-\n  ences are important")
            assert result == "experiences are important"


# ===================================================================
# Phase 3: Paragraph Reflow
# ===================================================================


class TestIsStructuralLine:
    """Tests for _is_structural_line."""

    def test_empty_line(self) -> None:
        assert _is_structural_line("") is True
        assert _is_structural_line("   ") is True

    def test_heading(self) -> None:
        assert _is_structural_line("# Heading") is True
        assert _is_structural_line("## Subheading") is True
        assert _is_structural_line("### Level 3") is True

    def test_unordered_list(self) -> None:
        assert _is_structural_line("- item") is True
        assert _is_structural_line("* item") is True
        assert _is_structural_line("+ item") is True

    def test_ordered_list(self) -> None:
        assert _is_structural_line("1. item") is True
        assert _is_structural_line("42. item") is True

    def test_code_fence(self) -> None:
        assert _is_structural_line("```python") is True
        assert _is_structural_line("~~~") is True

    def test_table_row(self) -> None:
        assert _is_structural_line("| col1 | col2 |") is True

    def test_blockquote(self) -> None:
        assert _is_structural_line("> quote") is True

    def test_horizontal_rule(self) -> None:
        assert _is_structural_line("---") is True
        assert _is_structural_line("***") is True
        assert _is_structural_line("___") is True

    def test_plain_text_not_structural(self) -> None:
        assert _is_structural_line("This is plain text.") is False
        assert _is_structural_line("Another line of text.") is False


class TestParagraphReflow:
    """Tests for _reflow_paragraphs pass."""

    def test_wrapped_lines_joined(self) -> None:
        text = "This is a long sentence that was\nwrapped at the PDF column width."
        result = _reflow_paragraphs(text)
        assert result == "This is a long sentence that was wrapped at the PDF column width."

    def test_paragraph_boundaries_preserved(self) -> None:
        text = "First paragraph line one\nline two.\n\nSecond paragraph."
        result = _reflow_paragraphs(text)
        assert "First paragraph line one line two." in result
        assert "\n\n" in result
        assert "Second paragraph." in result

    def test_headings_preserved(self) -> None:
        text = "# Heading\n\nParagraph text\ncontinues here."
        result = _reflow_paragraphs(text)
        assert result.startswith("# Heading\n")
        assert "Paragraph text continues here." in result

    def test_list_items_preserved(self) -> None:
        text = "- First item\n- Second item\n- Third item"
        result = _reflow_paragraphs(text)
        assert "- First item\n- Second item\n- Third item" in result

    def test_code_block_content_untouched(self) -> None:
        text = "```python\ndef foo():\n    return 42\n```"
        result = _reflow_paragraphs(text)
        assert "def foo():" in result
        assert "    return 42" in result

    def test_table_rows_preserved(self) -> None:
        text = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = _reflow_paragraphs(text)
        assert result == text

    def test_blockquotes_preserved(self) -> None:
        text = "> First line\n> Second line"
        result = _reflow_paragraphs(text)
        assert "> First line\n> Second line" in result

    def test_mixed_document(self) -> None:
        text = (
            "# Title\n"
            "\n"
            "This is a paragraph that\n"
            "spans multiple lines.\n"
            "\n"
            "- list item one\n"
            "- list item two\n"
            "\n"
            "```\n"
            "code here\n"
            "more code\n"
            "```\n"
            "\n"
            "Another paragraph."
        )
        result = _reflow_paragraphs(text)
        assert "# Title" in result
        assert "This is a paragraph that spans multiple lines." in result
        assert "- list item one" in result
        assert "- list item two" in result
        assert "code here\nmore code" in result
        assert "Another paragraph." in result

    def test_multiple_spaces_collapsed(self) -> None:
        text = "word   with  spaces\ncontinues."
        result = _reflow_paragraphs(text)
        # Extra spaces in buffer lines are collapsed on flush
        assert "  " not in result

    def test_horizontal_rule_preserved(self) -> None:
        text = "Text above\n---\nText below"
        result = _reflow_paragraphs(text)
        assert "---" in result


# ===================================================================
# Phase 5: End-to-End Tests
# ===================================================================


class TestEndToEndCleanup:
    """Integration tests for the full cleanup pipeline."""

    def test_realistic_marker_output(self) -> None:
        """Multi-artifact document: HTML + hyphens + wrapping + structure."""
        marker_output = (
            "# Introduction\n"
            "\n"
            "This study examines the <i>relationship</i> between\n"
            "cognitive develop-\n"
            "ment and <b>educational</b> outcomes across\n"
            "multiple populations.<sup>1</sup>\n"
            "\n"
            "## Methods\n"
            "\n"
            "The experi-\n"
            "mental design followed standard\n"
            "protocols for data collec-\n"
            "tion and analysis.\n"
            "\n"
            "- Sample size: 500\n"
            "- Duration: 12 months\n"
            "\n"
            "```python\n"
            "def analyze(data):\n"
            "    return stats.test(data)\n"
            "```\n"
            "\n"
            "| Group | N | Mean |\n"
            "|-------|---|------|\n"
            "| A     | 250 | 3.4 |\n"
        )

        with patch(
            "local_library.ingestion.markdown_cleanup._load_word_set",
            return_value=frozenset(["development", "experimental", "collection"]),
        ):
            result = cleanup_markdown(marker_output)

        # HTML converted
        assert "<i>" not in result
        assert "<b>" not in result
        assert "<sup>" not in result
        assert "*relationship*" in result
        assert "**educational**" in result
        assert "[1]" in result

        # Dehyphenation
        assert "development" in result
        assert "experimental" in result
        assert "collection" in result

        # Reflow: paragraph lines joined
        assert "This study examines" in result
        # Wrapped paragraph lines should be joined into longer lines
        # (skip code blocks which have their own formatting)
        in_code = False
        for line in result.split("\n"):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code = not in_code
                continue
            if in_code or not stripped or _is_structural_line(line):
                continue
            # Paragraph lines should be longer than typical column width
            assert len(stripped) > 30, f"Short paragraph line: {stripped!r}"

        # Structure preserved
        assert "# Introduction" in result
        assert "## Methods" in result
        assert "- Sample size: 500" in result
        assert "- Duration: 12 months" in result
        assert "def analyze(data):" in result
        assert "| Group | N | Mean |" in result

    def test_latex_preservation(self) -> None:
        """LaTeX math expressions pass through unchanged."""
        text = "The formula $x^2 + y^2 = z^2$ is well known.\n\n$$\\int_0^1 f(x) dx$$"
        result = cleanup_markdown(text)
        assert "$x^2 + y^2 = z^2$" in result
        assert "$$\\int_0^1 f(x) dx$$" in result

    def test_idempotency(self) -> None:
        """Applying cleanup twice produces the same result as once."""
        text = (
            "# Title\n"
            "\n"
            "This is a <b>bold</b> statement about\n"
            "the impor-\n"
            "tance of testing.\n"
            "\n"
            "- item one\n"
            "- item two\n"
        )
        with patch(
            "local_library.ingestion.markdown_cleanup._load_word_set",
            return_value=frozenset(["importance"]),
        ):
            first_pass = cleanup_markdown(text)
            second_pass = cleanup_markdown(first_pass)
            assert first_pass == second_pass
