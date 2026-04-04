# pattern: Imperative Shell
"""Tests for region alignment between source annotations and extracted text."""

from __future__ import annotations

from tests.extraction.synthetic.alignment import (
    align_regions,
    find_heading_anchors,
    fuzzy_find_region,
)
from tests.extraction.synthetic.annotations import AnnotatedRegion


class TestFindHeadingAnchors:
    """Test heading anchor detection in extracted text."""

    def test_finds_exact_heading(self):
        extracted = "# Introduction\n\nSome body text.\n\n## Methods\n\nMore text.\n"
        anchors = find_heading_anchors(extracted)
        assert len(anchors) == 2
        assert anchors[0].text == "# Introduction"
        assert anchors[1].text == "## Methods"

    def test_records_line_positions(self):
        extracted = "Preamble.\n\n# Title\n\nBody.\n\n## Section\n"
        anchors = find_heading_anchors(extracted)
        assert anchors[0].char_offset == extracted.index("# Title")
        assert anchors[1].char_offset == extracted.index("## Section")

    def test_no_headings_returns_empty(self):
        extracted = "Just plain text.\nNo headings here.\n"
        anchors = find_heading_anchors(extracted)
        assert anchors == []

    def test_ignores_headings_inside_code_blocks(self):
        extracted = "# Real Heading\n\n```\n# Not a heading\n```\n\nText.\n"
        anchors = find_heading_anchors(extracted)
        assert len(anchors) == 1
        assert anchors[0].text == "# Real Heading"


class TestFuzzyFindRegion:
    """Test fuzzy substring matching for region content in extracted text."""

    def test_exact_match(self):
        source_content = "This is the target text."
        extracted = "Before.\n\nThis is the target text.\n\nAfter.\n"
        result = fuzzy_find_region(source_content, extracted)
        assert result is not None
        assert result.similarity >= 0.95

    def test_near_match_with_ocr_errors(self):
        source_content = "The extracted results show improvement."
        extracted = "Before.\n\nThe extracled resuits show irnprovement.\n\nAfter.\n"
        result = fuzzy_find_region(source_content, extracted)
        assert result is not None
        assert result.similarity > 0.5

    def test_no_match_returns_none(self):
        source_content = "Completely unrelated content here."
        extracted = "Something totally different about another topic entirely.\n"
        result = fuzzy_find_region(source_content, extracted)
        # These texts share little in common; expect low similarity or no match
        # (rapidfuzz's Indel ratio scores slightly higher than SequenceMatcher
        # on strings with shared function words)
        assert result is None or result.similarity < 0.50

    def test_respects_search_window(self):
        source_content = "Target text."
        extracted = "A" * 5000 + "\n\nTarget text.\n\n" + "B" * 5000
        result = fuzzy_find_region(source_content, extracted, search_start=4900, search_end=5100)
        assert result is not None
        assert result.similarity >= 0.95

    def test_handles_multiline_content(self):
        source_content = "First line of a paragraph\nthat continues on a second line."
        # After reflow, Marker may join these into one line
        extracted = "First line of a paragraph that continues on a second line.\n"
        result = fuzzy_find_region(source_content, extracted)
        assert result is not None
        assert result.similarity > 0.8

    def test_partial_match_shorter_than_source(self):
        """When extraction drops part of a region, match should be shorter."""
        source_content = (
            "This is a long paragraph. The second sentence adds detail. The third wraps it up."
        )
        # Extraction only got the first sentence
        extracted = "This is a long paragraph.\n\nSome other text here.\n"
        result = fuzzy_find_region(source_content, extracted)
        assert result is not None
        # Should match the partial content
        assert result.coverage < 1.0
        assert result.coverage > 0.3

    def test_respects_excluded_ranges(self):
        """Already-claimed text should not be matched again."""
        source_content = "Shared text appears here."
        extracted = "Shared text appears here.\n\nOther content.\n"
        # Exclude the range where the text lives
        result = fuzzy_find_region(source_content, extracted, excluded_ranges=[(0, 30)])
        # Should not match the excluded range
        assert result is None or result.char_offset >= 30

    def test_handles_markdown_formatting_in_extracted(self):
        """Fuzzy match should work when extracted text has markdown formatting."""
        source_content = "Section Title"
        extracted = "# Section Title\n\nBody text here."
        result = fuzzy_find_region(source_content, extracted)
        assert result is not None, "Should find match despite markdown in extracted"
        # matched_text should contain the actual words, not the markdown marker
        assert "Section" in result.matched_text
        assert "Title" in result.matched_text
        # Should not start with markdown characters
        assert not result.matched_text.startswith("#")

    def test_handles_bold_formatting_in_extracted(self):
        """Fuzzy match should work with bold/italic formatting."""
        source_content = "Important concept"
        extracted = "This is **important concept** to understand.\n"
        result = fuzzy_find_region(source_content, extracted)
        assert result is not None, "Should find match despite markdown formatting"
        assert "important" in result.matched_text.lower()
        assert "concept" in result.matched_text.lower()


class TestAlignRegions:
    """Test full alignment pipeline: annotations + extracted text -> aligned regions."""

    def test_aligns_simple_document(self):
        regions = [
            AnnotatedRegion("heading-h1", "title", "# Introduction"),
            AnnotatedRegion("dense-prose", "body", "This is the body paragraph with real content."),
        ]
        extracted = (
            "# Introduction\n\n"
            "This is the body paragraph with real content.\n\n"
            "Some extra text at the end.\n"
        )
        result = align_regions(regions, extracted)
        assert len(result.aligned) == 2
        assert len(result.failures) == 0
        assert result.aligned[0].region.region_id == "title"
        assert result.aligned[1].region.region_id == "body"

    def test_records_alignment_failures(self):
        regions = [
            AnnotatedRegion("heading-h1", "title", "# Introduction"),
            AnnotatedRegion("table-simple", "missing-table", "| A | B |\n|---|---|\n| 1 | 2 |"),
        ]
        extracted = "# Introduction\n\nThe table was lost during extraction.\n"
        result = align_regions(regions, extracted)
        assert len(result.aligned) == 1
        assert len(result.failures) == 1
        assert result.failures[0].region_id == "missing-table"

    def test_exclusive_claiming_prevents_double_match(self):
        """Two regions should not match the same extracted text."""
        regions = [
            AnnotatedRegion("dense-prose", "region-a", "The shared text appears in the document."),
            AnnotatedRegion("dense-prose", "region-b", "The shared text appears in the document."),
        ]
        extracted = "The shared text appears in the document.\n\nOther stuff.\n"
        result = align_regions(regions, extracted)
        # First region claims the text; second should fail or match elsewhere
        assert len(result.aligned) >= 1
        # The key invariant: no two aligned regions overlap
        if len(result.aligned) == 2:
            ranges = [(a.char_offset, a.char_offset + len(a.matched_text)) for a in result.aligned]
            assert not _ranges_overlap(ranges[0], ranges[1])

    def test_partial_match_records_coverage(self):
        """Partial extraction should be reflected in coverage score."""
        regions = [
            AnnotatedRegion(
                "dense-prose",
                "truncated",
                "First sentence here. Second sentence here. Third sentence here.",
            ),
        ]
        # Only first sentence extracted
        extracted = "First sentence here.\n\nUnrelated text follows.\n"
        result = align_regions(regions, extracted)
        assert len(result.aligned) == 1
        assert result.aligned[0].coverage < 1.0

    def test_uses_heading_proximity_for_ordering(self):
        regions = [
            AnnotatedRegion("dense-prose", "intro-text", "Introduction content here."),
            AnnotatedRegion("dense-prose", "methods-text", "Methods content here."),
        ]
        extracted = (
            "# Introduction\n\nIntroduction content here.\n\n# Methods\n\nMethods content here.\n\n"
        )
        result = align_regions(regions, extracted)
        assert len(result.aligned) == 2
        for aligned in result.aligned:
            assert aligned.similarity > 0.8

    def test_empty_extracted_text_all_failures(self):
        regions = [
            AnnotatedRegion("heading-h1", "title", "# Title"),
        ]
        result = align_regions(regions, "")
        assert len(result.aligned) == 0
        assert len(result.failures) == 1


def _ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Check if two (start, end) ranges overlap."""
    return a[0] < b[1] and b[0] < a[1]
