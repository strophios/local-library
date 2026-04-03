# pattern: Imperative Shell
"""Tests for feature-specific structural fidelity validators."""

from __future__ import annotations

from tests.extraction.synthetic.validators import (
    validate_blockquote,
    validate_code_block,
    validate_footnote,
    validate_heading,
    validate_list,
    validate_math_display,
    validate_math_inline,
    validate_region,
    validate_table,
)


class TestValidateHeading:
    """Test heading structural validation."""

    def test_exact_heading_match(self):
        score = validate_heading("## Methods", "## Methods")
        assert score.detected is True
        assert score.level_accuracy == 1.0

    def test_heading_detected_wrong_level(self):
        score = validate_heading("## Methods", "### Methods")
        assert score.detected is True
        assert score.level_accuracy == 0.0

    def test_heading_detected_as_bold(self):
        """Heading extracted as bold text, not a heading."""
        score = validate_heading("## Methods", "**Methods**")
        assert score.detected is False

    def test_heading_off_by_one_level(self):
        score = validate_heading("## Methods", "# Methods")
        assert score.detected is True
        assert score.level_accuracy == 0.0  # Wrong level

    def test_empty_extracted(self):
        score = validate_heading("## Methods", "")
        assert score.detected is False


class TestValidateTable:
    """Test table structural validation."""

    def test_table_preserved(self):
        source = "| A | B |\n|---|---|\n| 1 | 2 |"
        extracted = "| A | B |\n|---|---|\n| 1 | 2 |"
        score = validate_table(source, extracted)
        assert score.detected is True
        assert score.column_accuracy == 1.0

    def test_table_lost_becomes_text(self):
        source = "| A | B |\n|---|---|\n| 1 | 2 |"
        extracted = "A B\n1 2"
        score = validate_table(source, extracted)
        assert score.detected is False

    def test_table_wrong_column_count(self):
        source = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
        extracted = "| A | B |\n|---|---|\n| 1 | 2 |"
        score = validate_table(source, extracted)
        assert score.detected is True
        assert score.column_accuracy < 1.0

    def test_empty_extracted(self):
        source = "| A | B |\n|---|---|\n| 1 | 2 |"
        score = validate_table(source, "")
        assert score.detected is False


class TestValidateList:
    """Test list structural validation."""

    def test_unordered_list_preserved(self):
        source = "- Item 1\n- Item 2\n- Item 3"
        extracted = "- Item 1\n- Item 2\n- Item 3"
        score = validate_list(source, extracted)
        assert score.detected is True
        assert score.item_count_accuracy == 1.0

    def test_ordered_list_preserved(self):
        source = "1. First\n2. Second\n3. Third"
        extracted = "1. First\n2. Second\n3. Third"
        score = validate_list(source, extracted)
        assert score.detected is True

    def test_list_lost(self):
        source = "- Item 1\n- Item 2\n- Item 3"
        extracted = "Item 1 Item 2 Item 3"
        score = validate_list(source, extracted)
        assert score.detected is False

    def test_nested_list(self):
        source = "- Item 1\n  - Sub item\n- Item 2"
        extracted = "- Item 1\n  - Sub item\n- Item 2"
        score = validate_list(source, extracted)
        assert score.detected is True
        assert score.max_depth >= 2


class TestValidateMathDisplay:
    """Test display math structural validation."""

    def test_latex_block_preserved(self):
        source = "$$E = mc^2$$"
        extracted = "$$E = mc^2$$"
        score = validate_math_display(source, extracted)
        assert score.detected is True

    def test_latex_lost(self):
        source = "$$E = mc^2$$"
        extracted = "E = mc2"
        score = validate_math_display(source, extracted)
        assert score.detected is False

    def test_single_dollar_not_display(self):
        source = "$$E = mc^2$$"
        extracted = "$E = mc^2$"
        # Single dollar is inline math, not display — still detected as math
        score = validate_math_display(source, extracted)
        assert score.detected is True  # Math detected, even if style changed


class TestValidateMathInline:
    """Test inline math structural validation."""

    def test_inline_math_preserved(self):
        source = "where $x > 0$ holds"
        extracted = "where $x > 0$ holds"
        score = validate_math_inline(source, extracted)
        assert score.detected is True

    def test_inline_math_lost(self):
        source = "where $x > 0$ holds"
        extracted = "where x > 0 holds"
        score = validate_math_inline(source, extracted)
        assert score.detected is False


class TestValidateFootnote:
    """Test footnote structural validation."""

    def test_footnote_marker_preserved(self):
        source = "Text with a footnote[1] reference."
        extracted = "Text with a footnote[1] reference."
        score = validate_footnote(source, extracted)
        assert score.detected is True

    def test_footnote_marker_lost(self):
        source = "Text with a footnote[1] reference."
        extracted = "Text with a footnote reference."
        score = validate_footnote(source, extracted)
        assert score.detected is False


class TestValidateBlockquote:
    """Test blockquote structural validation."""

    def test_blockquote_preserved(self):
        source = "> This is a quoted passage."
        extracted = "> This is a quoted passage."
        score = validate_blockquote(source, extracted)
        assert score.detected is True

    def test_blockquote_lost(self):
        source = "> This is a quoted passage."
        extracted = "This is a quoted passage."
        score = validate_blockquote(source, extracted)
        assert score.detected is False


class TestValidateCodeBlock:
    """Test code block structural validation."""

    def test_fenced_code_preserved(self):
        source = "```python\nprint('hello')\n```"
        extracted = "```python\nprint('hello')\n```"
        score = validate_code_block(source, extracted)
        assert score.detected is True

    def test_code_block_lost(self):
        source = "```python\nprint('hello')\n```"
        extracted = "print('hello')"
        score = validate_code_block(source, extracted)
        assert score.detected is False


class TestValidateRegion:
    """Test dispatch to correct validator based on feature type."""

    def test_dispatches_heading(self):
        score = validate_region("heading-h2", "## Title", "## Title")
        assert score.detected is True

    def test_dispatches_table(self):
        source = "| A |\n|---|\n| 1 |"
        score = validate_region("table-simple", source, source)
        assert score.detected is True

    def test_unknown_feature_returns_default(self):
        score = validate_region("unknown-type", "text", "text")
        # Should not crash; returns a score with detected=None (unknown)
        assert score is not None
