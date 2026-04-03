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
    if search_end is None:
        search_end = len(extracted)
    search_region = extracted[search_start:search_end]
    if not search_region.strip():
        return None

    norm_source = normalize_text(source_content)
    if not norm_source:
        return None

    source_words = norm_source.split()
    n_source = len(source_words)

    if not source_words:
        return None

    # Work with raw words to avoid index mismatch issues
    raw_words = search_region.split()
    if not raw_words:
        return None

    # Try variable window sizes: 50% to 110% of source word count
    min_window = max(1, int(n_source * _MIN_WINDOW_FRAC))
    max_window = min(len(raw_words), int(n_source * _MAX_WINDOW_FRAC) + 1)

    best_score = 0.0  # Combined similarity * coverage
    best_match: FuzzyMatch | None = None

    for window_size in range(min_window, max_window + 1):
        for i in range(len(raw_words) - window_size + 1):
            candidate_words = raw_words[i : i + window_size]
            raw_text = " ".join(candidate_words)

            # Normalize for comparison, but keep raw text for extraction
            norm_candidate = normalize_text(raw_text)
            if not norm_candidate:
                continue

            similarity = SequenceMatcher(None, norm_source, norm_candidate).ratio()
            if similarity < min_similarity:
                continue

            coverage = min(1.0, len(candidate_words) / n_source)
            combined = similarity * coverage

            # Compute character offset from raw word position
            prefix_raw = " ".join(raw_words[:i])
            char_offset_in_region = len(prefix_raw) + (1 if prefix_raw else 0)
            abs_offset = search_start + char_offset_in_region

            # Check exclusion
            if _is_excluded(abs_offset, len(raw_text), excluded):
                continue

            if combined > best_score:
                best_score = combined
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
        search_start, search_end = _compute_search_window(region, anchors, len(extracted))

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
            claimed_ranges.append((match.char_offset, match.char_offset + len(match.matched_text)))
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
