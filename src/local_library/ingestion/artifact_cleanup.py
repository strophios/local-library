"""Content artifact removal for extraction output.

Removes non-content artifacts from Marker-produced markdown:
1. Non-Latin script OCR hallucinations (CJK, Arabic, Thai, Devanagari)
2. Marker image description noise (logos, seals) with content preservation
3. Repeated watermark/DRM lines
4. Publisher boilerplate (JSTOR, ResearchGate, etc.)

These passes address content quality (removing things that shouldn't be there),
distinct from markdown_cleanup.py which addresses formatting (dehyphenation,
paragraph reflow, HTML coercion). Artifact removal runs first so that
formatting passes operate on clean content.
"""

# pattern: Functional Core (pure transformation, no I/O)

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Unicode ranges for targeted scripts (OCR hallucination sources).
# Greek/Coptic (U+0370-03FF) and Cyrillic (U+0400-04FF) are deliberately
# excluded — both appear legitimately in English academic text.
_NON_LATIN_PATTERN = re.compile(
    r"["
    r"\u4e00-\u9fff"  # CJK Unified Ideographs
    r"\u3400-\u4dbf"  # CJK Extension A
    r"\U00020000-\U0002a6df"  # CJK Extension B
    r"\u0600-\u06ff"  # Arabic
    r"\u0e00-\u0e7f"  # Thai
    r"\u0900-\u097f"  # Devanagari
    r"]"
)

_NON_LATIN_THRESHOLD = 4

# Marker image description pattern: "Image /page/N/Type/M description: ..."
_IMAGE_DESC_PATTERN = re.compile(r"^Image /page/\d+/\w+/\d+ description:\s*(.*)$")

# Keywords indicating a noise image description (logo, seal, etc.)
_NOISE_KEYWORDS = frozenset(
    {
        "logo",
        "seal",
        "icon",
        "watermark",
        "decorative",
        "cover art",
        "book cover",
    }
)

_MIN_DESCRIPTION_LENGTH = 20


def clean_artifacts(text: str) -> str:
    """Remove content artifacts from extraction output. Never raises.

    Applies four passes in order:
    1. Non-Latin script filtering (CJK/Arabic/Thai/Devanagari hallucinations)
    2. Image description reformatting (noise removal, content blockquoting)
    3. Repeated watermark removal (DRM/header/footer lines)
    4. Publisher boilerplate stripping (JSTOR, ResearchGate, BePress, etc.)

    Each pass is independently fault-tolerant. Pass ordering is load-bearing:
    non-Latin first (cheapest, removes garbage before other passes inspect),
    image descriptions before watermarks (avoids miscounting), boilerplate
    last (operates on document head after earlier passes may have removed lines).
    """
    try:
        text = _filter_non_latin_scripts(text)
        text = _reformat_image_descriptions(text)
        text = _remove_repeated_watermarks(text)
        text = _strip_publisher_boilerplate(text)
    except Exception:
        logger.warning("artifact cleanup failed unexpectedly", exc_info=True)
    return text


def _filter_non_latin_scripts(text: str) -> str:
    """Remove lines containing 4+ characters from targeted script blocks.

    Targets CJK, Arabic, Thai, and Devanagari — scripts that appear as OCR
    hallucinations in English academic papers. Greek and Cyrillic are exempt
    since they appear legitimately in academic text (math, transliterations).

    Characters need not be consecutive; total count per line is checked.
    """
    try:
        lines = text.split("\n")
        filtered = []
        for line in lines:
            targeted_chars = _NON_LATIN_PATTERN.findall(line)
            if len(targeted_chars) >= _NON_LATIN_THRESHOLD:
                logger.debug("removed non-Latin artifact line: %s", line[:80])
                continue
            filtered.append(line)
        return "\n".join(filtered)
    except Exception:
        logger.warning("non-Latin script filtering failed", exc_info=True)
        return text


def _is_noise_description(description: str) -> bool:
    """Check if an image description is noise (logo, seal, etc.)."""
    desc_lower = description.lower()
    if len(description) < _MIN_DESCRIPTION_LENGTH:
        return True
    return any(keyword in desc_lower for keyword in _NOISE_KEYWORDS)


def _reformat_image_descriptions(text: str) -> str:
    """Reformat Marker image descriptions: remove noise, blockquote content.

    Marker inserts lines like:
        Image /page/3/Figure/1 description: A bar graph showing...

    Noise descriptions (logos, seals, icons, short text) are removed.
    Substantive descriptions are reformatted as markdown blockquotes:
        > [Figure] A bar graph showing...
    """
    try:
        lines = text.split("\n")
        result = []
        for line in lines:
            match = _IMAGE_DESC_PATTERN.match(line.strip())
            if not match:
                result.append(line)
                continue

            description = match.group(1).strip()
            if _is_noise_description(description):
                logger.debug("removed noise image description: %s", description[:60])
                continue

            result.append(f"> [Figure] {description}")

        return "\n".join(result)
    except Exception:
        logger.warning("image description reformatting failed", exc_info=True)
        return text


_WATERMARK_THRESHOLD = 3

# Structural line patterns that legitimately repeat (headings, list items, etc.)
_STRUCTURAL_PREFIX = re.compile(r"^\s*(#{1,6}\s|[-*+]\s|\d+\.\s|[>|])")


def _remove_repeated_watermarks(text: str) -> str:
    """Remove lines that appear 3+ times in the document.

    Repeated identical lines (after whitespace normalization) are almost
    certainly watermarks, DRM notices, or headers/footers that Marker
    extracted as body text. Structural markdown lines (headings, list items,
    blockquotes, table rows) are exempt since they legitimately repeat.
    """
    try:
        lines = text.split("\n")

        # Count occurrences of each non-empty, non-structural line
        counts: dict[str, int] = {}
        for line in lines:
            normalized = line.strip()
            if not normalized:
                continue
            if _STRUCTURAL_PREFIX.match(normalized):
                continue
            key = re.sub(r"\s+", " ", normalized)
            counts[key] = counts.get(key, 0) + 1

        watermarks = {key for key, count in counts.items() if count >= _WATERMARK_THRESHOLD}

        if not watermarks:
            return text

        logger.debug("detected %d repeated watermark pattern(s)", len(watermarks))

        filtered = []
        for line in lines:
            normalized = re.sub(r"\s+", " ", line.strip())
            if normalized in watermarks:
                continue
            filtered.append(line)

        return "\n".join(filtered)
    except Exception:
        logger.warning("repeated watermark removal failed", exc_info=True)
        return text


# ---------------------------------------------------------------------------
# Pass 4: Publisher Boilerplate Stripping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoilerplateRule:
    """A rule for detecting publisher/repository boilerplate.

    This catalog is expected to grow as new publisher patterns are encountered
    during corpus scaling. Add new rules by appending to BOILERPLATE_RULES.
    """

    name: str
    indicators: tuple[str, ...]
    description: str


# Catalog of known publisher boilerplate patterns. Each rule's indicators are
# matched case-insensitively against lines in the document head.
# To add a new publisher: append a BoilerplateRule with indicator substrings
# that reliably distinguish boilerplate from real content.
BOILERPLATE_RULES: tuple[BoilerplateRule, ...] = (
    BoilerplateRule(
        name="jstor",
        indicators=(
            "your use of the jstor archive",
            "jstor is a not-for-profit",
            "collaborating with jstor",
        ),
        description="JSTOR access/terms preamble",
    ),
    BoilerplateRule(
        name="researchgate",
        indicators=(
            "see discussions, stats",
            "researchgate.net/publication",
        ),
        description="ResearchGate cover page metadata",
    ),
    BoilerplateRule(
        name="bepress",
        indicators=(
            "this paper can be downloaded free of charge",
            "this open-access article is brought to you",
            "electronic copy available at",
        ),
        description="BePress/SSRN/institutional repository download notices",
    ),
)

_BOILERPLATE_SCAN_LINES = 50


def _strip_publisher_boilerplate(text: str) -> str:
    """Remove known publisher/repository boilerplate from document head.

    Scans the first ~50 lines for patterns matching known publishers
    (JSTOR, ResearchGate, BePress/SSRN). Lines matching any indicator are
    removed. Only operates on the document head to avoid false positives
    in body text that legitimately discusses these platforms.
    """
    try:
        lines = text.split("\n")

        if not lines:
            return text

        # Build set of all indicator strings (lowercased)
        all_indicators = []
        for rule in BOILERPLATE_RULES:
            all_indicators.extend(rule.indicators)

        # Determine scan boundary
        scan_end = min(len(lines), _BOILERPLATE_SCAN_LINES)

        # Find which lines in the head region match boilerplate
        boilerplate_line_indices: set[int] = set()
        for i in range(scan_end):
            line_lower = lines[i].lower()
            if any(indicator in line_lower for indicator in all_indicators):
                boilerplate_line_indices.add(i)

        if not boilerplate_line_indices:
            return text

        # Remove matched lines and contiguous blank/metadata lines around them.
        # Strategy: find the highest boilerplate line index, then remove
        # everything from the start up to and including that line, plus any
        # trailing blank lines. This handles the common case where boilerplate
        # is a contiguous block at the document head.
        #
        # Also remove individual scattered boilerplate lines (e.g., a URL line
        # between real content lines).
        max_boilerplate_idx = max(boilerplate_line_indices)

        # Check if boilerplate is concentrated at the head (all matched lines
        # are before any substantial non-boilerplate content)
        first_content_idx = None
        for i in range(scan_end):
            if i in boilerplate_line_indices:
                continue
            stripped = lines[i].strip()
            if not stripped:
                continue
            # A line that's not boilerplate and not blank — is it content?
            # Heuristic: JSTOR URLs (jstor.org, http://), citation counts,
            # and short metadata fragments are not real content.
            if _is_metadata_fragment(stripped):
                boilerplate_line_indices.add(i)
                continue
            first_content_idx = i
            break

        if first_content_idx is not None and first_content_idx > max_boilerplate_idx:
            # All boilerplate is before first content — remove the head block
            # including any interleaved blank lines
            result_lines = lines[first_content_idx:]
        else:
            # Boilerplate is scattered — remove only matched lines
            result_lines = [
                line for i, line in enumerate(lines) if i not in boilerplate_line_indices
            ]

        # Strip leading blank lines from result
        while result_lines and not result_lines[0].strip():
            result_lines.pop(0)

        return "\n".join(result_lines)
    except Exception:
        logger.warning("publisher boilerplate stripping failed", exc_info=True)
        return text


def _is_metadata_fragment(line: str) -> bool:
    """Check if a line is likely metadata rather than real content.

    Used during boilerplate stripping to identify non-content lines
    interspersed with boilerplate (URLs, citation counts, dates, etc.).
    """
    stripped = line.strip()

    # Bare URLs
    if re.match(r"^https?://", stripped):
        return True
    # Just a year (e.g., "2004")
    if re.match(r"^\d{4}$", stripped):
        return True
    # Citation/read counts (e.g., "42", "1,337")
    if re.match(r"^[\d,]+$", stripped):
        return True
    # Known metadata labels
    if stripped in ("CITATIONS", "READS", "REFERENCES"):
        return True
    # ResearchGate project links
    if "View project" in stripped:
        return True

    return False
