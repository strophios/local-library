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


# Author extraction constants
_AUTHOR_SEARCH_LINES = 50  # Search first N lines for author block
_AUTHOR_MIN_CONFIDENCE = 0.3


@dataclass(frozen=True)
class _AuthorCandidate:
    """Internal candidate for author extraction."""

    name: str
    score: float
    reasoning: str


def _clean_author_name(name: str) -> str:
    """Clean a raw author name string.

    Removes:
    - Superscript affiliation markers (¹²³ etc)
    - Email addresses
    - Parenthetical affiliations
    - Leading/trailing punctuation
    """
    # Remove superscript numbers and symbols
    name = re.sub(r"[¹²³⁴⁵⁶⁷⁸⁹⁰*†‡§]", "", name)

    # Remove email addresses
    name = re.sub(r"<[^>]+>", "", name)
    name = re.sub(r"\S+@\S+\.\S+", "", name)

    # Remove parenthetical content (affiliations)
    name = re.sub(r"\([^)]*\)", "", name)

    # Remove common affiliation patterns
    name = re.sub(r"\b(?:PhD|MD|Prof\.?|Dr\.?)\b", "", name, flags=re.IGNORECASE)

    # Clean up whitespace and punctuation
    name = re.sub(r"\s+", " ", name)
    name = name.strip(" ,;:")

    return name


def _split_author_string(text: str) -> list[str]:
    """Split a string containing multiple authors into individual names.

    Handles:
    - Comma separation: "John Smith, Jane Doe"
    - 'and' separation: "John Smith and Jane Doe"
    - Semicolon separation: "Smith, John; Doe, Jane"
    - Oxford comma: "John, Jane, and Bob"
    """
    # Normalize 'and' to comma (but not when part of name like "Anderson")
    text = re.sub(r"\s+and\s+", ", ", text, flags=re.IGNORECASE)

    # Try semicolon first (often indicates "Last, First" format)
    if ";" in text:
        parts = [p.strip() for p in text.split(";")]
    else:
        parts = [p.strip() for p in text.split(",")]

    # Filter out empty parts and clean each name
    names = []
    common_institutions = {"mit", "stanford", "harvard", "yale", "princeton", "berkeley", "cornell"}
    for part in parts:
        cleaned = _clean_author_name(part)
        # Skip if too short to be a name or if it looks like a number/date
        if len(cleaned) >= 3 and not cleaned.isdigit():
            # Skip common institution names
            if cleaned.lower() not in common_institutions:
                names.append(cleaned)

    return names


def _is_likely_author_line(line: str) -> tuple[bool, float, str]:
    """Check if a line likely contains author names.

    Returns:
        Tuple of (is_likely, confidence, reasoning)
    """
    line_lower = line.lower().strip()

    # Skip empty lines
    if not line_lower:
        return False, 0.0, "empty line"

    # Skip if too long (likely paragraph)
    if len(line) > 200:
        return False, 0.0, "too long for author line"

    # Skip if starts with common non-author patterns
    skip_patterns = [
        r"^abstract[\s:.]",
        r"^introduction",
        r"^keywords?[\s:.]",
        r"^\d+\.",  # Numbered list
        r"^#",  # Markdown header
        r"^table\s",
        r"^figure\s",
        r"^acknowledgment",
        r"^department\s",
        r"^university\s",
        r"^institute\s",
    ]
    for pattern in skip_patterns:
        if re.match(pattern, line_lower):
            return False, 0.0, f"matches skip pattern: {pattern}"

    # Likely affiliation/institutional line (not authors)
    # But be careful: "Smith, John" might have institution after
    affiliation_keywords = ["university", "institute", "department", "college", "laboratory", "lab"]
    is_likely_affiliation = any(kw in line_lower for kw in affiliation_keywords)
    if is_likely_affiliation and "," not in line:
        # Institution line without a comma (not "Name, Institution" format)
        return False, 0.0, "likely affiliation line"

    # Positive signals
    score = 0.3
    reasons = []

    # "by" prefix is strong signal
    if re.match(r"^by\s+", line_lower):
        score += 0.3
        reasons.append("'by' prefix")

    # Contains "and" between what look like names
    if re.search(r"\b[A-Z][a-z]+\s+and\s+[A-Z][a-z]+", line):
        score += 0.2
        reasons.append("name and name pattern")

    # Contains comma-separated capitalized words (names)
    cap_words = re.findall(r"\b[A-Z][a-z]+", line)
    if len(cap_words) >= 2:
        score += 0.1
        reasons.append(f"{len(cap_words)} capitalized words")

    # Contains email (author line often has emails)
    if "@" in line:
        score += 0.15
        reasons.append("contains email")

    # Superscript markers suggest author affiliations
    if re.search(r"[¹²³⁴⁵⁶⁷⁸⁹⁰*†‡]", line):
        score += 0.15
        reasons.append("affiliation markers")

    # Academic name format: "Last, First"
    if re.search(r"[A-Z][a-z]+,\s*[A-Z]\.", line):
        score += 0.2
        reasons.append("academic format")

    # Negative signals
    # Too many numbers suggests not an author line
    digits = sum(1 for c in line if c.isdigit())
    if digits > 5:
        score -= 0.2

    # Contains date-like patterns
    if re.search(r"\b\d{4}\b", line):
        score -= 0.1

    # Contains volume/issue patterns
    if re.search(r"\bvol|issue|pp\.", line_lower):
        score -= 0.3

    # Penalize lines with institution keywords (unless it's a name match)
    if is_likely_affiliation:
        score -= 0.15

    score = max(0.0, min(1.0, score))
    reasoning = "; ".join(reasons) if reasons else "base heuristics"

    return score >= 0.3, score, reasoning


def _find_author_block(text: str) -> tuple[list[str], float, str]:
    """Find the author block in document text.

    Strategies (in order):
    1. Look for "by" prefix
    2. Look for lines between title and "Abstract"
    3. Look for lines with author-like patterns

    Returns:
        Tuple of (author_lines, confidence, reasoning)
    """
    lines = text.split("\n")[:_AUTHOR_SEARCH_LINES]

    # Strategy 1: Look for "by" prefix
    for i, line in enumerate(lines):
        if re.match(r"^\s*by\s+", line, re.IGNORECASE):
            # Extract the rest of the line and possibly next line
            author_text = re.sub(r"^\s*by\s+", "", line, flags=re.IGNORECASE)
            # Check if continues to next line
            if i + 1 < len(lines) and not lines[i + 1].strip().startswith(
                ("Abstract", "Introduction", "#")
            ):
                next_line = lines[i + 1].strip()
                if next_line and not _is_likely_author_line(next_line)[0]:
                    pass  # Don't extend
                elif next_line:
                    author_text += ", " + next_line
            return [author_text], 0.8, "'by' prefix detected"

    # Strategy 2: Look for lines between title and Abstract
    abstract_idx = None
    title_end_idx = 0

    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if stripped.startswith("abstract"):
            abstract_idx = i
            break
        # Track where title might end (first blank line after content)
        if i > 0 and not stripped and lines[i - 1].strip():
            if title_end_idx == 0:
                title_end_idx = i

    if abstract_idx and title_end_idx > 0 and abstract_idx > title_end_idx:
        # Lines between title and abstract
        potential_lines = []
        for i in range(title_end_idx, abstract_idx):
            line = lines[i].strip()
            if line:
                is_likely, score, _ = _is_likely_author_line(line)
                if is_likely or score > 0.2:
                    potential_lines.append(line)
        if potential_lines:
            return potential_lines, 0.6, "between title and abstract"

    # Strategy 3: Look for author-like patterns in first lines
    author_lines = []
    best_score = 0.0

    for line in lines[1:15]:  # Skip first line (likely title)
        stripped = line.strip()
        if not stripped:
            continue

        is_likely, score, reasoning = _is_likely_author_line(stripped)
        if is_likely:
            author_lines.append(stripped)
            best_score = max(best_score, score)

    if author_lines:
        return author_lines, best_score * 0.8, "author-like patterns"

    return [], 0.0, "no author block found"


def _parse_author_name(name: str) -> str:
    """Parse an author name into normalized format.

    Uses nameparser library for robust name parsing.
    Returns format: "Family, Given" for CSL-JSON compatibility.
    """
    from nameparser import HumanName

    # Clean the name first
    name = _clean_author_name(name)

    if not name:
        return ""

    # Use nameparser for robust parsing
    parsed = HumanName(name)

    # Build normalized format
    if parsed.last:
        if parsed.first:
            return f"{parsed.last}, {parsed.first}"
        return parsed.last
    elif parsed.first:
        return parsed.first

    # Fallback: return cleaned original
    return name


def extract_authors(markdown_text: str) -> tuple[FieldExtraction, ...]:
    """Extract author names from markdown text.

    Detects author block using multiple strategies:
    1. "by" keyword prefix
    2. Lines between title and Abstract
    3. Lines with author-like patterns (names, emails, affiliations)

    Args:
        markdown_text: Marker-produced markdown content

    Returns:
        Tuple of FieldExtraction objects, one per detected author
    """
    # Handle empty input
    if not markdown_text or not markdown_text.strip():
        return ()

    # Find author block
    author_lines, block_confidence, block_reasoning = _find_author_block(markdown_text)

    if not author_lines:
        return ()

    # Extract individual authors from the block
    authors: list[FieldExtraction] = []

    for line in author_lines:
        names = _split_author_string(line)

        for name in names:
            parsed = _parse_author_name(name)
            if parsed and len(parsed) >= 3:
                # Confidence combines block confidence and name quality
                name_confidence = block_confidence

                # Boost confidence for well-formed names
                if "," in parsed:  # Has family, given format
                    name_confidence = min(1.0, name_confidence + 0.1)

                authors.append(
                    FieldExtraction(
                        value=parsed,
                        confidence=round(name_confidence, 2),
                        source="heuristic",
                        alternatives=(),
                        reasoning=block_reasoning,
                    )
                )

    return tuple(authors)


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
