# pattern: Functional Core
"""Region alignment between source annotations and Marker-extracted output.

Aligns annotated source regions to their corresponding locations in extracted
text using a three-phase strategy:
  1. Heading scaffold: Match heading regions first to establish section boundaries
  2. Seed-and-expand: For each non-heading region, find a seed match via
     partial_ratio_alignment, then expand outward to capture the full region
  3. Ordered cursor: Process regions in document order, advancing a cursor
     to avoid redundant backward searches

Design principles:
- Variable-length matching: Matches can be shorter than source (partial extraction)
- Exclusive claiming: Matched text is excluded from subsequent region searches
- Alignment failure as data: Missing regions recorded explicitly, not force-matched
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from rapidfuzz.fuzz import partial_ratio_alignment
from rapidfuzz.fuzz import ratio as rapidfuzz_ratio

from tests.extraction.synthetic.annotations import AnnotatedRegion
from tests.extraction.synthetic.metrics import normalize_text

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_CODE_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_MIN_SIMILARITY = 0.3  # Below this, consider alignment failed
_SEED_WORD_COUNT = 20  # Words to use for seed matching
_EXPAND_STEP_WORDS = 5  # Words to add per expansion step
_EXPAND_PATIENCE = 3  # Stop after this many consecutive score decreases


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


def _word_boundaries(text: str) -> list[tuple[int, int]]:
    """Compute (start, end) character positions for each whitespace-split word.

    This allows mapping between word indices and character offsets in the
    original text without repeated string joins.
    """
    boundaries: list[tuple[int, int]] = []
    pos = 0
    for word in text.split():
        idx = text.index(word, pos)
        boundaries.append((idx, idx + len(word)))
        pos = idx + len(word)
    return boundaries


def _seed_find(
    norm_source: str,
    raw_search_text: str,
    seed_word_count: int = _SEED_WORD_COUNT,
) -> tuple[int, int] | None:
    """Find approximate position of source content in raw search text using a seed.

    Takes the first N words of the normalized source as a seed and uses
    partial_ratio_alignment to locate it directly in the raw search text.
    Searching raw text avoids the need to map between normalized and raw
    character positions — partial_ratio_alignment is fuzzy enough to handle
    formatting differences (markdown markers, whitespace, case).

    Args:
        norm_source: Normalized source content.
        raw_search_text: Raw (unnormalized) text to search within.
        seed_word_count: Number of words for the seed substring.

    Returns:
        (start, end) character span of seed in raw_search_text, or None.
    """
    source_words = norm_source.split()
    if not source_words:
        return None

    # Use first N words as seed (or all words if source is short)
    n_seed = min(seed_word_count, len(source_words))
    seed = " ".join(source_words[:n_seed])

    if not seed or not raw_search_text:
        return None

    result = partial_ratio_alignment(seed, raw_search_text, score_cutoff=40.0)
    if result is None:
        return None

    return result.dest_start, result.dest_end


def _char_offset_to_word_index(
    char_offset: int,
    word_bounds: list[tuple[int, int]],
) -> int:
    """Find the word index containing or nearest to a character offset."""
    for i, (start, end) in enumerate(word_bounds):
        if start >= char_offset:
            return i
        if start <= char_offset < end:
            return i
    return len(word_bounds) - 1


def _expand_match(
    norm_source: str,
    raw_words: list[str],
    word_bounds: list[tuple[int, int]],
    seed_start: int,
    seed_end: int,
    step_words: int = _EXPAND_STEP_WORDS,
    patience: int = _EXPAND_PATIENCE,
) -> tuple[int, int] | None:
    """Expand outward from a seed position to find the best-matching window.

    Starting from the word span covering the seed match, tries progressively
    larger windows. Stops when the score degrades for `patience` consecutive
    expansions.

    Args:
        norm_source: Normalized source content to match against.
        raw_words: Whitespace-split words of the raw search region.
        word_bounds: Character boundaries for each word in the search region.
        seed_start: Character offset of seed match start in raw search region.
        seed_end: Character offset of seed match end in raw search region.
        step_words: Words to add per expansion step.
        patience: Stop after this many consecutive score decreases.

    Returns:
        (best_word_start, best_word_end) indices into raw_words, or None.
    """
    if not raw_words or not word_bounds:
        return None

    # Map seed character span to word indices
    start_word = _char_offset_to_word_index(seed_start, word_bounds)

    # Initial window: start at seed position, extend to approximate source length.
    # The seed tells us WHERE the region starts; the source word count tells us
    # HOW BIG it should be. This avoids the expansion phase needing to grow from
    # a tiny seed span to a full paragraph.
    source_word_count = len(norm_source.split())
    best_start = start_word
    best_end = min(start_word + source_word_count, len(raw_words))

    # Score initial window (seed span)
    candidate = " ".join(raw_words[best_start:best_end])
    norm_candidate = normalize_text(candidate)
    best_score = rapidfuzz_ratio(norm_source, norm_candidate) / 100.0 if norm_candidate else 0.0

    # Expand outward in both directions
    consecutive_declines = 0
    expand_start = best_start
    expand_end = best_end

    for _ in range(50):  # Safety limit
        new_start = max(0, expand_start - step_words)
        new_end = min(len(raw_words), expand_end + step_words)

        if new_start == expand_start and new_end == expand_end:
            break  # Can't expand further

        expand_start = new_start
        expand_end = new_end

        candidate = " ".join(raw_words[expand_start:expand_end])
        norm_candidate = normalize_text(candidate)
        if not norm_candidate:
            continue

        score = rapidfuzz_ratio(norm_source, norm_candidate) / 100.0

        if score > best_score:
            best_score = score
            best_start = expand_start
            best_end = expand_end
            consecutive_declines = 0
        else:
            consecutive_declines += 1
            if consecutive_declines >= patience:
                break

    # Contract inward: trim edges that don't improve the score.
    # After expansion, the window may include trailing/leading noise.
    # Try trimming from each end independently.
    improved = True
    while improved:
        improved = False
        # Try trimming from the end
        if best_end - best_start > 1:
            candidate = " ".join(raw_words[best_start : best_end - 1])
            norm_candidate = normalize_text(candidate)
            if norm_candidate:
                score = rapidfuzz_ratio(norm_source, norm_candidate) / 100.0
                if score > best_score:
                    best_score = score
                    best_end -= 1
                    improved = True
        # Try trimming from the start
        if best_end - best_start > 1:
            candidate = " ".join(raw_words[best_start + 1 : best_end])
            norm_candidate = normalize_text(candidate)
            if norm_candidate:
                score = rapidfuzz_ratio(norm_source, norm_candidate) / 100.0
                if score > best_score:
                    best_score = score
                    best_start += 1
                    improved = True

    if best_score < _MIN_SIMILARITY:
        return None

    return best_start, best_end


def fuzzy_find_region(
    source_content: str,
    extracted: str,
    search_start: int = 0,
    search_end: int | None = None,
    min_similarity: float = _MIN_SIMILARITY,
    excluded_ranges: list[tuple[int, int]] | None = None,
) -> FuzzyMatch | None:
    """Find the best fuzzy match for source content within extracted text.

    Uses seed-and-expand strategy:
      1. Find approximate location via partial_ratio_alignment on a seed
      2. Expand outward from seed to capture the full matching region
      3. Score the final match for similarity and coverage

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

    raw_words = search_region.split()
    if not raw_words:
        return None

    word_bounds = _word_boundaries(search_region)

    # Phase 1: Seed — find approximate location in raw text
    seed_span = _seed_find(norm_source, search_region)
    if seed_span is None:
        return None

    # Phase 2: Expand — grow window from seed position
    seed_start, seed_end = seed_span
    expansion = _expand_match(
        norm_source,
        raw_words,
        word_bounds,
        seed_start,
        seed_end,
    )
    if expansion is None:
        return None

    word_start, word_end = expansion
    matched_text = " ".join(raw_words[word_start:word_end])

    # Compute character offset in the full extracted text
    if word_bounds and word_start < len(word_bounds):
        char_offset_in_region = word_bounds[word_start][0]
    else:
        char_offset_in_region = 0
    abs_offset = search_start + char_offset_in_region

    # Check exclusion
    if _is_excluded(abs_offset, len(matched_text), excluded):
        return None

    # Final scoring
    norm_matched = normalize_text(matched_text)
    similarity = rapidfuzz_ratio(norm_source, norm_matched) / 100.0 if norm_matched else 0.0
    if similarity < min_similarity:
        return None

    matched_word_count = word_end - word_start
    coverage = min(1.0, matched_word_count / n_source) if n_source > 0 else 0.0

    return FuzzyMatch(
        matched_text=matched_text,
        char_offset=abs_offset,
        similarity=similarity,
        coverage=coverage,
    )


def align_regions(
    regions: list[AnnotatedRegion],
    extracted: str,
) -> AlignmentResult:
    """Align annotated source regions to positions in extracted text.

    Three-phase strategy:
      1. Heading scaffold: match heading regions first via heading anchors
      2. Section assignment: non-heading regions search within their section
      3. Ordered cursor: regions processed in order, cursor advances forward

    Enforces exclusive claiming: once text is matched to a region, it's
    excluded from consideration for subsequent regions.

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

    # Phase 1: Build heading scaffold — match heading regions to anchors
    heading_regions: list[tuple[int, AnnotatedRegion]] = []
    non_heading_regions: list[tuple[int, AnnotatedRegion]] = []

    for idx, region in enumerate(regions):
        first_line = region.content.split("\n")[0].strip()
        if _HEADING_RE.match(first_line):
            heading_regions.append((idx, region))
        else:
            non_heading_regions.append((idx, region))

    # Match headings to anchors (fast — short strings)
    matched_headings: dict[int, HeadingAnchor] = {}  # anchor index → source region index
    heading_results: dict[int, AlignedRegion | AlignmentFailure] = {}
    claimed_ranges: list[tuple[int, int]] = []

    for region_idx, region in heading_regions:
        heading_text = region.content.split("\n")[0].strip()
        heading_match = _HEADING_RE.match(heading_text)
        if not heading_match:
            continue

        norm_heading = normalize_text(heading_match.group(2))
        best_anchor = None
        best_anchor_idx = -1
        best_sim = 0.0

        for anchor_idx, anchor in enumerate(anchors):
            anchor_match = _HEADING_RE.match(anchor.text)
            if not anchor_match:
                continue
            norm_anchor = normalize_text(anchor_match.group(2))
            sim = rapidfuzz_ratio(norm_heading, norm_anchor) / 100.0
            if sim > best_sim:
                best_sim = sim
                best_anchor = anchor
                best_anchor_idx = anchor_idx

        if best_anchor and best_sim > 0.5:
            # Find the actual heading line in extracted text
            line_end = (
                extracted.index("\n", best_anchor.char_offset)
                if "\n" in extracted[best_anchor.char_offset :]
                else len(extracted)
            )
            matched_text = extracted[best_anchor.char_offset : line_end].strip()

            heading_results[region_idx] = AlignedRegion(
                region=region,
                matched_text=matched_text,
                char_offset=best_anchor.char_offset,
                similarity=best_sim,
                coverage=1.0,
            )
            claimed_ranges.append((best_anchor.char_offset, line_end))
            matched_headings[best_anchor_idx] = best_anchor
        else:
            heading_results[region_idx] = AlignmentFailure(
                region_id=region.region_id,
                feature_type=region.feature_type,
                reason="no matching heading anchor found in extracted text",
            )

    # Phase 2: Build section boundaries from matched headings
    # Sections are spans between consecutive heading anchors
    section_bounds = _build_section_bounds(anchors, len(extracted))

    # Phase 3: Match non-heading regions within sections, using cursor
    cursor = 0  # Advances forward as regions are matched

    for region_idx, region in non_heading_regions:
        # Determine which section this region belongs to based on its position
        # relative to heading regions in the source document
        section_start, section_end = _find_section_for_region(
            region_idx, heading_regions, heading_results, section_bounds, len(extracted)
        )

        # Start search from cursor or section start, whichever is further forward
        search_start = max(cursor, section_start)
        search_end = section_end

        match = fuzzy_find_region(
            region.content,
            extracted,
            search_start=search_start,
            search_end=search_end,
            excluded_ranges=claimed_ranges,
        )

        # Fallback 1: try full section (cursor may have overshot)
        if match is None and search_start > section_start:
            match = fuzzy_find_region(
                region.content,
                extracted,
                search_start=section_start,
                search_end=section_end,
                excluded_ranges=claimed_ranges,
            )

        # Fallback 2: try full document
        if match is None:
            match = fuzzy_find_region(
                region.content,
                extracted,
                excluded_ranges=claimed_ranges,
            )

        if match is not None:
            heading_results[region_idx] = AlignedRegion(
                region=region,
                matched_text=match.matched_text,
                char_offset=match.char_offset,
                similarity=match.similarity,
                coverage=match.coverage,
            )
            claimed_ranges.append((match.char_offset, match.char_offset + len(match.matched_text)))
            cursor = match.char_offset + len(match.matched_text)
        else:
            heading_results[region_idx] = AlignmentFailure(
                region_id=region.region_id,
                feature_type=region.feature_type,
                reason="no sufficiently similar region found in extracted text",
            )

    # Reassemble results in original region order
    aligned: list[AlignedRegion] = []
    failures: list[AlignmentFailure] = []
    for idx in range(len(regions)):
        result = heading_results.get(idx)
        if isinstance(result, AlignedRegion):
            aligned.append(result)
        elif isinstance(result, AlignmentFailure):
            failures.append(result)

    return AlignmentResult(aligned=aligned, failures=failures)


def _build_section_bounds(
    anchors: list[HeadingAnchor],
    text_length: int,
) -> list[tuple[int, int]]:
    """Build section boundaries from heading anchors.

    Each section spans from one heading to the next. The first section
    starts at 0 (before any heading), and the last extends to end of text.

    Returns:
        List of (start, end) character offset tuples.
    """
    if not anchors:
        return [(0, text_length)]

    bounds: list[tuple[int, int]] = []
    # Section before first heading
    if anchors[0].char_offset > 0:
        bounds.append((0, anchors[0].char_offset))

    # Sections between headings
    for i, anchor in enumerate(anchors):
        start = anchor.char_offset
        end = anchors[i + 1].char_offset if i + 1 < len(anchors) else text_length
        bounds.append((start, end))

    return bounds


def _find_section_for_region(
    region_idx: int,
    heading_regions: list[tuple[int, AnnotatedRegion]],
    heading_results: dict[int, AlignedRegion | AlignmentFailure],
    section_bounds: list[tuple[int, int]],
    text_length: int,
) -> tuple[int, int]:
    """Determine search bounds for a non-heading region based on surrounding headings.

    Finds the nearest preceding and following heading regions (by source order)
    that were successfully matched, and returns the span between them.

    Args:
        region_idx: Index of the non-heading region in the original region list.
        heading_regions: List of (index, region) for heading regions.
        heading_results: Results of heading matching phase.
        section_bounds: Section boundaries from heading anchors.
        text_length: Total length of extracted text.

    Returns:
        (search_start, search_end) character offsets.
    """
    # Find nearest preceding matched heading
    preceding_end = 0
    following_start = text_length

    for h_idx, _h_region in heading_regions:
        result = heading_results.get(h_idx)
        if isinstance(result, AlignedRegion):
            if h_idx < region_idx:
                preceding_end = max(preceding_end, result.char_offset)
            elif h_idx > region_idx:
                following_start = min(following_start, result.char_offset)

    return preceding_end, following_start
