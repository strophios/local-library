# pattern: Imperative Shell
"""Tests for synthetic document annotation parsing."""
from __future__ import annotations

from tests.extraction.synthetic.annotations import (
    parse_annotations,
    strip_annotations,
)


class TestParseAnnotations:
    """Test parsing of feature annotations from source markdown."""

    def test_parses_single_region(self):
        text = (
            "Some text before.\n"
            "\n"
            "<!-- feature: heading-h2 id:section-intro -->\n"
            "## Introduction\n"
            "<!-- /feature -->\n"
            "\n"
            "Some text after.\n"
        )
        regions = parse_annotations(text)
        assert len(regions) == 1
        assert regions[0].feature_type == "heading-h2"
        assert regions[0].region_id == "section-intro"
        assert regions[0].content == "## Introduction"

    def test_parses_multiple_regions(self):
        text = (
            "<!-- feature: heading-h1 id:title -->\n"
            "# Main Title\n"
            "<!-- /feature -->\n"
            "\n"
            "Body text.\n"
            "\n"
            "<!-- feature: table-simple id:data-table -->\n"
            "| A | B |\n"
            "|---|---|\n"
            "| 1 | 2 |\n"
            "<!-- /feature -->\n"
        )
        regions = parse_annotations(text)
        assert len(regions) == 2
        assert regions[0].feature_type == "heading-h1"
        assert regions[1].feature_type == "table-simple"

    def test_multiline_content(self):
        text = (
            "<!-- feature: dense-prose id:intro-para -->\n"
            "This is a paragraph that spans\n"
            "multiple lines and contains\n"
            "realistic prose content.\n"
            "<!-- /feature -->\n"
        )
        regions = parse_annotations(text)
        assert len(regions) == 1
        expected = (
            "This is a paragraph that spans\n"
            "multiple lines and contains\n"
            "realistic prose content."
        )
        assert regions[0].content == expected

    def test_no_annotations_returns_empty(self):
        text = "Just plain markdown with no annotations.\n"
        regions = parse_annotations(text)
        assert regions == []

    def test_preserves_region_order(self):
        text = (
            "<!-- feature: heading-h1 id:first -->\n"
            "# First\n"
            "<!-- /feature -->\n"
            "<!-- feature: heading-h2 id:second -->\n"
            "## Second\n"
            "<!-- /feature -->\n"
            "<!-- feature: heading-h3 id:third -->\n"
            "### Third\n"
            "<!-- /feature -->\n"
        )
        regions = parse_annotations(text)
        ids = [r.region_id for r in regions]
        assert ids == ["first", "second", "third"]

    def test_nested_markdown_formatting_preserved(self):
        text = (
            "<!-- feature: display-math id:equation -->\n"
            "$$E = \\sum_{i=1}^{n} w_i \\cdot f(x_i)$$\n"
            "<!-- /feature -->\n"
        )
        regions = parse_annotations(text)
        assert "$$E = \\sum_{i=1}^{n}" in regions[0].content


class TestStripAnnotations:
    """Test stripping annotations from source markdown for PDF generation."""

    def test_strips_annotation_tags(self):
        text = (
            "Before.\n"
            "\n"
            "<!-- feature: heading-h2 id:intro -->\n"
            "## Introduction\n"
            "<!-- /feature -->\n"
            "\n"
            "After.\n"
        )
        stripped = strip_annotations(text)
        assert "<!-- feature:" not in stripped
        assert "<!-- /feature -->" not in stripped
        assert "## Introduction" in stripped
        assert "Before." in stripped
        assert "After." in stripped

    def test_preserves_non_annotation_html_comments(self):
        text = (
            "<!-- This is a regular comment -->\n"
            "<!-- feature: heading-h1 id:title -->\n"
            "# Title\n"
            "<!-- /feature -->\n"
        )
        stripped = strip_annotations(text)
        assert "<!-- This is a regular comment -->" in stripped
        assert "<!-- feature:" not in stripped

    def test_roundtrip_content_preserved(self):
        content_lines = [
            "# Title",
            "",
            "Some prose here.",
            "",
            "| A | B |",
            "|---|---|",
            "| 1 | 2 |",
        ]
        annotated = (
            "<!-- feature: heading-h1 id:title -->\n"
            "# Title\n"
            "<!-- /feature -->\n"
            "\n"
            "Some prose here.\n"
            "\n"
            "<!-- feature: table-simple id:tbl -->\n"
            "| A | B |\n"
            "|---|---|\n"
            "| 1 | 2 |\n"
            "<!-- /feature -->\n"
        )
        stripped = strip_annotations(annotated)
        for line in content_lines:
            assert line in stripped
