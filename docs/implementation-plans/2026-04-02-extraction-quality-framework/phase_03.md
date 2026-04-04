## Phase 3: Region Alignment

**Goal:** Map annotated source regions to corresponding locations in Marker-extracted output, handling partial matches and preventing error aggregation.

**Key design decisions:**
- **Variable-length matching**: Matched text can be shorter than source (captures partial extraction honestly)
- **Exclusive claiming**: Once extracted text is aligned to a region, it's excluded from future matches (prevents double-counting and runaway error aggregation)
- **Alignment failure as data**: Regions that can't be found are recorded as failures, not bad matches

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Write alignment tests

**Files:**
- Create: `tests/unit/test_alignment.py`

**Step 1: Write failing tests**

```python
# pattern: Imperative Shell
"""Tests for region alignment between source annotations and extracted text."""
from __future__ import annotations

import pytest

from tests.extraction.synthetic.alignment import (
    AlignedRegion,
    AlignmentResult,
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
        assert result is None or result.similarity < 0.3

    def test_respects_search_window(self):
        source_content = "Target text."
        extracted = "A" * 5000 + "\n\nTarget text.\n\n" + "B" * 5000
        result = fuzzy_find_region(
            source_content, extracted, search_start=4900, search_end=5100
        )
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
            "This is a long paragraph that has multiple sentences. "
            "The second sentence adds detail. The third wraps it up."
        )
        # Extraction only got the first sentence
        extracted = "Before.\n\nThis is a long paragraph that has multiple sentences.\n\nAfter.\n"
        result = fuzzy_find_region(source_content, extracted)
        assert result is not None
        # Should match the partial content, not grab "After."
        assert "After" not in result.matched_text
        assert result.coverage < 1.0
        assert result.coverage > 0.3

    def test_respects_excluded_ranges(self):
        """Already-claimed text should not be matched again."""
        source_content = "Shared text appears here."
        extracted = "Shared text appears here.\n\nOther content.\n"
        # Exclude the range where the text lives
        result = fuzzy_find_region(
            source_content, extracted, excluded_ranges=[(0, 30)]
        )
        # Should not match the excluded range
        assert result is None or result.char_offset >= 30


class TestAlignRegions:
    """Test full alignment pipeline: annotations + extracted text -> aligned regions."""

    def test_aligns_simple_document(self):
        regions = [
            AnnotatedRegion("heading-h1", "title", "# Introduction"),
            AnnotatedRegion(
                "dense-prose", "body",
                "This is the body paragraph with real content."
            ),
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
            AnnotatedRegion(
                "table-simple", "missing-table",
                "| A | B |\n|---|---|\n| 1 | 2 |"
            ),
        ]
        extracted = "# Introduction\n\nThe table was lost during extraction.\n"
        result = align_regions(regions, extracted)
        assert len(result.aligned) == 1
        assert len(result.failures) == 1
        assert result.failures[0].region_id == "missing-table"

    def test_exclusive_claiming_prevents_double_match(self):
        """Two regions should not match the same extracted text."""
        regions = [
            AnnotatedRegion(
                "dense-prose", "region-a",
                "The shared text appears in the document."
            ),
            AnnotatedRegion(
                "dense-prose", "region-b",
                "The shared text appears in the document."
            ),
        ]
        extracted = "The shared text appears in the document.\n\nOther stuff.\n"
        result = align_regions(regions, extracted)
        # First region claims the text; second should fail or match elsewhere
        assert len(result.aligned) >= 1
        # The key invariant: no two aligned regions overlap
        if len(result.aligned) == 2:
            ranges = [
                (a.char_offset, a.char_offset + len(a.matched_text))
                for a in result.aligned
            ]
            assert not _ranges_overlap(ranges[0], ranges[1])

    def test_partial_match_records_coverage(self):
        """Partial extraction should be reflected in coverage score."""
        regions = [
            AnnotatedRegion(
                "dense-prose", "truncated",
                "First sentence here. Second sentence here. Third sentence here."
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
            "# Introduction\n\n"
            "Introduction content here.\n\n"
            "# Methods\n\n"
            "Methods content here.\n\n"
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_alignment.py -v`
Expected: ImportError — `tests.extraction.synthetic.alignment` does not exist

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement alignment module

**Files:**
- Create: `tests/extraction/synthetic/alignment.py`

**Step 1: Implement the module**

Key design features:
- **Variable-length matching**: Tries windows from 50% to 110% of source word count, picks best (similarity × coverage) score
- **Exclusive claiming**: `align_regions` tracks claimed character ranges; `fuzzy_find_region` accepts `excluded_ranges` to skip already-matched text
- **Coverage tracking**: `AlignedRegion.coverage` records what fraction of the source region was matched (matched word count / source word count)

```python
# pattern: Functional Core
"""Region alignment between source annotations and Marker-extracted output.

Aligns annotated source regions to their corresponding locations in extracted
text using a two-phase strategy:
  1. Heading anchors: Find heading lines in extracted text to establish position
  2. Fuzzy content matching: Within anchor neighborhoods, find best substring match

Design principles:
- Variable-length matching: Matches can be shorter than source (partial extraction)
- Exclusive claiming: Matched text is excluded from subsequent region searches
- Alignment failure as data: Missing regions recorded explicitly, not force-matched
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from tests.extraction.synthetic.annotations import AnnotatedRegion
from tests.extraction.synthetic.metrics import normalize_text

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_CODE_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_MIN_SIMILARITY = 0.3  # Below this, consider alignment failed
_MIN_WINDOW_FRAC = 0.5  # Smallest window as fraction of source word count
_MAX_WINDOW_FRAC = 1.1  # Largest window as fraction of source word count


@dataclass(frozen=True)
class HeadingAnchor:
    """A heading found in extracted text, used as positional anchor."""

    text: str
    level: int
    char_offset: int


@dataclass(frozen=True)
class FuzzyMatch:
    """Result of fuzzy substring matching."""

    matched_text: str
    char_offset: int
    similarity: float
    coverage: float  # Fraction of source content matched (0-1)


@dataclass(frozen=True)
class AlignedRegion:
    """A source region successfully aligned to extracted text."""

    region: AnnotatedRegion
    matched_text: str
    char_offset: int
    similarity: float
    coverage: float  # Fraction of source content found in extraction


@dataclass(frozen=True)
class AlignmentFailure:
    """A source region that could not be aligned."""

    region_id: str
    feature_type: str
    reason: str


@dataclass(frozen=True)
class AlignmentResult:
    """Complete alignment result for a document."""

    aligned: list[AlignedRegion] = field(default_factory=list)
    failures: list[AlignmentFailure] = field(default_factory=list)


def find_heading_anchors(extracted: str) -> list[HeadingAnchor]:
    """Find all headings in extracted text with their character positions.

    Skips headings inside code blocks (fenced with ``` or ~~~).

    Args:
        extracted: Full extracted markdown text.

    Returns:
        List of HeadingAnchor in document order.
    """
    anchors: list[HeadingAnchor] = []
    in_code_block = False
    char_pos = 0

    for line in extracted.split("\n"):
        fence_match = _CODE_FENCE_RE.match(line.strip())
        if fence_match:
            in_code_block = not in_code_block
        elif not in_code_block:
            heading_match = _HEADING_RE.match(line.strip())
            if heading_match:
                level = len(heading_match.group(1))
                anchors.append(
                    HeadingAnchor(
                        text=line.strip(),
                        level=level,
                        char_offset=char_pos,
                    )
                )
        char_pos += len(line) + 1  # +1 for newline

    return anchors


def _is_excluded(offset: int, length: int, excluded: list[tuple[int, int]]) -> bool:
    """Check if a range overlaps with any excluded range."""
    end = offset + length
    return any(offset < ex_end and ex_start < end for ex_start, ex_end in excluded)


def fuzzy_find_region(
    source_content: str,
    extracted: str,
    search_start: int = 0,
    search_end: int | None = None,
    min_similarity: float = _MIN_SIMILARITY,
    excluded_ranges: list[tuple[int, int]] | None = None,
) -> FuzzyMatch | None:
    """Find the best fuzzy match for source content within extracted text.

    Uses variable-length sliding window: tries windows from 50% to 110% of
    source word count to handle partial extraction. Scores by
    (similarity * coverage) to prefer high-fidelity partial matches over
    low-fidelity full-length matches.

    Args:
        source_content: The annotated region's content from source markdown.
        extracted: Full extracted markdown text to search within.
        search_start: Character offset to start searching from.
        search_end: Character offset to stop searching at. None = end of text.
        min_similarity: Minimum similarity threshold. Below this, returns None.
        excluded_ranges: Character ranges already claimed by other regions.

    Returns:
        FuzzyMatch if a sufficiently similar region found, None otherwise.
    """
    if not source_content.strip() or not extracted.strip():
        return None

    excluded = excluded_ranges or []
    search_region = extracted[search_start:search_end]
    if not search_region.strip():
        return None

    norm_source = normalize_text(source_content)
    norm_extracted = normalize_text(search_region)

    if not norm_source or not norm_extracted:
        return None

    source_words = norm_source.split()
    extracted_words = norm_extracted.split()
    n_source = len(source_words)

    if not extracted_words or not source_words:
        return None

    # Try variable window sizes: 50% to 110% of source word count
    min_window = max(1, int(n_source * _MIN_WINDOW_FRAC))
    max_window = min(len(extracted_words), int(n_source * _MAX_WINDOW_FRAC) + 1)

    best_score = 0.0  # Combined similarity * coverage
    best_match: FuzzyMatch | None = None

    for window_size in range(min_window, max_window + 1):
        for i in range(max(1, len(extracted_words) - window_size + 1)):
            candidate_words = extracted_words[i : i + window_size]
            candidate = " ".join(candidate_words)

            similarity = SequenceMatcher(None, norm_source, candidate).ratio()
            if similarity < min_similarity:
                continue

            coverage = min(1.0, len(candidate_words) / n_source)
            combined = similarity * coverage

            # Map word position back to approximate char offset in search_region
            prefix = " ".join(extracted_words[:i])
            char_offset_in_region = len(prefix) + (1 if prefix else 0)
            abs_offset = search_start + char_offset_in_region

            # Check exclusion
            candidate_char_len = len(candidate)
            if _is_excluded(abs_offset, candidate_char_len, excluded):
                continue

            if combined > best_score:
                best_score = combined
                # Get actual text from the un-normalized search region
                # Use word boundaries for cleaner extraction
                raw_words = search_region.split()
                raw_start = i
                raw_end = min(i + window_size, len(raw_words))
                raw_text = " ".join(raw_words[raw_start:raw_end]).strip()

                best_match = FuzzyMatch(
                    matched_text=raw_text,
                    char_offset=abs_offset,
                    similarity=similarity,
                    coverage=coverage,
                )

    return best_match


def align_regions(
    regions: list[AnnotatedRegion],
    extracted: str,
) -> AlignmentResult:
    """Align annotated source regions to positions in extracted text.

    Two-phase strategy:
      1. Find heading anchors in extracted text
      2. For each source region, search near the appropriate anchor

    Enforces exclusive claiming: once text is matched to a region, it's
    excluded from consideration for subsequent regions. This prevents
    double-counting and error aggregation from overlapping matches.

    Args:
        regions: Annotated regions from source markdown (from parse_annotations).
        extracted: Full Marker-extracted markdown text (after cleanup passes).

    Returns:
        AlignmentResult with aligned regions and failures.
    """
    if not extracted.strip():
        return AlignmentResult(
            aligned=[],
            failures=[
                AlignmentFailure(
                    region_id=r.region_id,
                    feature_type=r.feature_type,
                    reason="extracted text is empty",
                )
                for r in regions
            ],
        )

    anchors = find_heading_anchors(extracted)
    aligned: list[AlignedRegion] = []
    failures: list[AlignmentFailure] = []
    claimed_ranges: list[tuple[int, int]] = []

    for region in regions:
        # Determine search window based on heading anchors
        search_start, search_end = _compute_search_window(
            region, anchors, len(extracted)
        )

        match = fuzzy_find_region(
            region.content,
            extracted,
            search_start=search_start,
            search_end=search_end,
            excluded_ranges=claimed_ranges,
        )

        # Fallback: search full document if windowed search failed
        if match is None and (search_start > 0 or search_end < len(extracted)):
            match = fuzzy_find_region(
                region.content,
                extracted,
                excluded_ranges=claimed_ranges,
            )

        if match is not None:
            aligned.append(
                AlignedRegion(
                    region=region,
                    matched_text=match.matched_text,
                    char_offset=match.char_offset,
                    similarity=match.similarity,
                    coverage=match.coverage,
                )
            )
            # Claim this range so subsequent regions can't match it
            claimed_ranges.append(
                (match.char_offset, match.char_offset + len(match.matched_text))
            )
        else:
            failures.append(
                AlignmentFailure(
                    region_id=region.region_id,
                    feature_type=region.feature_type,
                    reason="no sufficiently similar region found in extracted text",
                )
            )

    return AlignmentResult(aligned=aligned, failures=failures)


def _compute_search_window(
    region: AnnotatedRegion,
    anchors: list[HeadingAnchor],
    text_length: int,
) -> tuple[int, int]:
    """Determine the search window for a region based on heading anchors.

    If the region content starts with a heading, tries to find the matching
    anchor and constrains search to the section between that anchor and the
    next one. Otherwise, searches the full text.

    Args:
        region: The annotated region to find a window for.
        anchors: Heading anchors found in extracted text.
        text_length: Total length of extracted text.

    Returns:
        (search_start, search_end) character offsets.
    """
    if not anchors:
        return 0, text_length

    first_line = region.content.split("\n")[0].strip()
    heading_match = _HEADING_RE.match(first_line)

    if heading_match:
        heading_text = normalize_text(heading_match.group(2))
        best_anchor = None
        best_sim = 0.0
        for anchor in anchors:
            anchor_heading = _HEADING_RE.match(anchor.text)
            if not anchor_heading:
                continue
            anchor_text = normalize_text(anchor_heading.group(2))
            sim = SequenceMatcher(None, heading_text, anchor_text).ratio()
            if sim > best_sim:
                best_sim = sim
                best_anchor = anchor

        if best_anchor and best_sim > 0.5:
            anchor_idx = anchors.index(best_anchor)
            start = best_anchor.char_offset
            end = (
                anchors[anchor_idx + 1].char_offset
                if anchor_idx + 1 < len(anchors)
                else text_length
            )
            return start, end

    return 0, text_length
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_alignment.py -v`
Expected: All tests pass

Note: The variable-length matching and exclusion logic is the most complex part of this framework. If any tests fail, focus on the `fuzzy_find_region` function — the window sizing and word-to-char offset mapping are the likeliest sources of issues. Debug by adding logging and inspecting which windows score highest.

**Step 3: Commit**

```bash
git add tests/extraction/synthetic/alignment.py tests/unit/test_alignment.py
git commit -m "feat: add region alignment with partial matching and exclusive claiming"
```

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
