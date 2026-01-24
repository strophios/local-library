"""Text-based metadata extraction from Marker-produced markdown.

This module implements heuristic extraction of bibliographic metadata
from PDF text content. Each field has an independent extractor that
produces a FieldExtraction result with confidence scoring.
"""

# pattern: Functional Core

from __future__ import annotations

import re
from dataclasses import dataclass

from local_library.core.models import FieldExtraction

# Title extraction constants
_TITLE_MIN_LENGTH = 10  # Minimum characters for a valid title
_TITLE_MAX_LENGTH = 300  # Maximum characters for a valid title
_TITLE_SEARCH_WORDS = 300  # Search first N words for title candidates


@dataclass(frozen=True)
class _TitleCandidate:
    """Internal candidate for title extraction."""

    text: str
    score: float
    reasoning: str
    is_header: bool = False
    is_isolated: bool = False


def _get_header_lines(text: str) -> list[tuple[str, int]]:
    """Extract markdown header lines with their positions.

    Returns:
        List of (header_text, line_number) tuples
    """
    headers: list[tuple[str, int]] = []
    for i, line in enumerate(text.split("\n")):
        # Match # headers (level 1-3)
        match = re.match(r"^#{1,3}\s+(.+)$", line.strip())
        if match:
            header_text = match.group(1).strip()
            if _TITLE_MIN_LENGTH <= len(header_text) <= _TITLE_MAX_LENGTH:
                headers.append((header_text, i))
    return headers


def _get_first_content_lines(text: str, max_words: int = _TITLE_SEARCH_WORDS) -> list[str]:
    """Get first non-empty lines up to max_words total.

    Joins consecutive non-blank lines that might form a multiline title.
    Stops at blank lines or when word count is reached.

    Returns:
        List of content line groups (multiline titles joined)
    """
    lines = text.split("\n")
    content_groups: list[str] = []
    current_group: list[str] = []
    word_count = 0

    for line in lines:
        stripped = line.strip()

        # Skip markdown headers (handled separately)
        if stripped.startswith("#"):
            if current_group:
                content_groups.append(" ".join(current_group))
                current_group = []
            continue

        if not stripped:
            # Blank line ends current group
            if current_group:
                content_groups.append(" ".join(current_group))
                current_group = []
            continue

        # Check if we've exceeded word limit
        line_words = len(stripped.split())
        if word_count + line_words > max_words:
            break

        word_count += line_words
        current_group.append(stripped)

        # If line is long enough to be standalone, end group
        if len(stripped) > 60:
            content_groups.append(" ".join(current_group))
            current_group = []

    # Don't forget final group
    if current_group:
        content_groups.append(" ".join(current_group))

    return content_groups


def _is_likely_metadata_line(text: str) -> bool:
    """Check if line is likely metadata rather than title.

    Detects journal names, volume/issue, author affiliations, etc.
    """
    text_lower = text.lower()

    # Journal/publication patterns
    if re.search(r"\bvol(?:ume)?\.?\s*\d+", text_lower):
        return True
    if re.search(r"\bissue\s*\d+", text_lower):
        return True
    if re.search(r"\bpp\.?\s*\d+", text_lower):
        return True

    # Date patterns at start
    if re.match(r"^\d{4}\s|^\w+\s+\d{4}", text):
        return True

    # Email/URL patterns
    if "@" in text or "http" in text_lower:
        return True

    # University/institution patterns (often author affiliations)
    if re.search(r"\buniversity\b|\binstitute\b|\bdepartment\b", text_lower):
        return True

    return False


def _score_title_candidate(
    text: str,
    position: int,
    is_header: bool,
    is_isolated: bool,
    total_candidates: int,
) -> tuple[float, str]:
    """Score a title candidate based on multiple signals.

    Args:
        text: The candidate text
        position: Position in document (0 = first)
        is_header: Whether this is a markdown header
        is_isolated: Whether followed by blank line
        total_candidates: Total number of candidates

    Returns:
        Tuple of (score, reasoning)
    """
    score = 0.5  # Base score
    reasons: list[str] = []

    # Header bonus (strong signal)
    if is_header:
        score += 0.3
        reasons.append("markdown header")

    # Position bonus (earlier is better)
    if position == 0:
        score += 0.15
        reasons.append("first content")
    elif position == 1:
        score += 0.05

    # Isolation bonus
    if is_isolated:
        score += 0.1
        reasons.append("isolated line")

    # Length preference (moderate length is better)
    length = len(text)
    if 30 <= length <= 150:
        score += 0.1
        reasons.append("good length")
    elif length < 20:
        score -= 0.1
    elif length > 200:
        score -= 0.1

    # Capitalization bonus (title case or all caps for short)
    words = text.split()
    if len(words) >= 3:
        cap_words = sum(1 for w in words if w[0].isupper())
        if cap_words / len(words) >= 0.7:
            score += 0.05
            reasons.append("title case")

    # Penalize likely metadata
    if _is_likely_metadata_line(text):
        score -= 0.3
        reasons.append("likely metadata")

    # Clamp score
    score = max(0.0, min(1.0, score))

    reasoning = "; ".join(reasons) if reasons else "base score"
    return score, reasoning


def _generate_title_candidates(text: str) -> list[_TitleCandidate]:
    """Generate title candidates from document text.

    Considers:
    - Markdown headers (high priority)
    - First non-empty lines (position priority)
    - Multiline titles (joined consecutive lines)

    Returns:
        List of candidates sorted by score (highest first)
    """
    candidates: list[_TitleCandidate] = []
    lines = text.split("\n")

    # Get markdown headers
    headers = _get_header_lines(text)
    for header_text, line_num in headers:
        # Check if header is isolated (next line is blank or another header)
        is_isolated = (
            line_num + 1 >= len(lines)
            or not lines[line_num + 1].strip()
            or lines[line_num + 1].strip().startswith("#")
        )

        score, reasoning = _score_title_candidate(
            header_text,
            position=0 if line_num < 5 else 1,  # Early headers get position bonus
            is_header=True,
            is_isolated=is_isolated,
            total_candidates=len(headers),
        )

        candidates.append(
            _TitleCandidate(
                text=header_text,
                score=score,
                reasoning=reasoning,
                is_header=True,
                is_isolated=is_isolated,
            )
        )

    # Get first content lines
    content_lines = _get_first_content_lines(text)
    for i, content in enumerate(content_lines):
        # Skip if too short or too long
        if not (_TITLE_MIN_LENGTH <= len(content) <= _TITLE_MAX_LENGTH):
            continue

        # Check isolation (was followed by blank line during extraction)
        is_isolated = True  # Content groups are isolated by definition

        score, reasoning = _score_title_candidate(
            content,
            position=i,
            is_header=False,
            is_isolated=is_isolated,
            total_candidates=len(content_lines),
        )

        candidates.append(
            _TitleCandidate(
                text=content,
                score=score,
                reasoning=reasoning,
                is_header=False,
                is_isolated=is_isolated,
            )
        )

    # Sort by score descending
    candidates.sort(key=lambda c: c.score, reverse=True)

    return candidates


def extract_title(markdown_text: str) -> FieldExtraction:
    """Extract document title from markdown text.

    Analyzes the first ~300 words of the document to identify the title.
    Uses multiple signals: position, isolation, length, capitalization.
    Confidence is derived from candidate margin (gap between top candidate
    and runner-up) plus signal strength.

    Args:
        markdown_text: Marker-produced markdown content

    Returns:
        FieldExtraction with extracted title, confidence, and reasoning
    """
    # Handle empty input
    if not markdown_text or not markdown_text.strip():
        return FieldExtraction(
            value=None,
            confidence=0.0,
            source="heuristic",
            alternatives=(),
            reasoning="no text content to extract title from",
        )

    # Generate candidates
    candidates = _generate_title_candidates(markdown_text)

    if not candidates:
        return FieldExtraction(
            value=None,
            confidence=0.0,
            source="heuristic",
            alternatives=(),
            reasoning="no valid title candidates found",
        )

    # Select best candidate
    best = candidates[0]

    # Calculate confidence from candidate margin
    if len(candidates) >= 2:
        margin = best.score - candidates[1].score
        # Large margin increases confidence, small margin decreases it
        confidence = best.score * (0.7 + 0.3 * min(margin * 3, 1.0))
    else:
        # Single candidate: use score directly with slight penalty
        confidence = best.score * 0.9

    # Build alternatives list (up to 3)
    alternatives = tuple(c.text for c in candidates[1:4])

    # Build reasoning
    reasoning = best.reasoning

    return FieldExtraction(
        value=best.text,
        confidence=round(confidence, 2),
        source="heuristic",
        alternatives=alternatives,
        reasoning=reasoning,
    )
