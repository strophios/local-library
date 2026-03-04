"""Post-processing cleanup for Marker-produced markdown.

Applies three composable passes to clean extraction artifacts:
1. HTML coercion — converts HTML tags to markdown equivalents
2. Dehyphenation — rejoins words split across lines
3. Paragraph reflow — joins non-semantic linebreaks into proper paragraphs

Pass ordering is load-bearing: HTML coercion first (can change line structure
via <br>), dehyphenation second (needs word-\n patterns before reflow erases
them), reflow last (needs cleanest input).
"""

# pattern: Functional Core (pure transformation, no I/O)

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def cleanup_markdown(text: str) -> str:
    """Compose all three cleanup passes. Never raises.

    Applies HTML coercion, dehyphenation, and paragraph reflow in order.
    Each pass is independently fault-tolerant — if any pass fails, it
    returns its input unchanged.

    Args:
        text: Raw Marker-produced markdown

    Returns:
        Cleaned markdown text
    """
    try:
        text = _coerce_html(text)
        text = _dehyphenate(text)
        text = _reflow_paragraphs(text)
    except Exception:
        logger.warning("markdown cleanup failed unexpectedly", exc_info=True)
    return text


# ---------------------------------------------------------------------------
# Pass 1: HTML Coercion
# ---------------------------------------------------------------------------


def _coerce_html(text: str) -> str:
    """Convert HTML tags to markdown equivalents.

    Applied in order:
    1. <i>/<em> → *...*
    2. <b>/<strong> → **...**
    3. <sup>N.</sup> (digit sequences, optional dot) → [N] footnote markers
    4. Remaining <sup> → strip tags, keep text
    5. <br>/<br/> → space
    6. Any remaining HTML tags → strip tags, keep text
    """
    try:
        # 1. Italic: <i>...</i> and <em>...</em>
        text = re.sub(r"<(?:i|em)>(.*?)</(?:i|em)>", r"*\1*", text, flags=re.DOTALL)

        # 2. Bold: <b>...</b> and <strong>...</strong>
        text = re.sub(r"<(?:b|strong)>(.*?)</(?:b|strong)>", r"**\1**", text, flags=re.DOTALL)

        # 3. Footnote superscripts: <sup>N.</sup> or <sup>N</sup> where N is digits
        #    In Marker output, math superscripts use LaTeX ($x^2$), not HTML,
        #    so digit-only <sup> tags are reliably footnote markers.
        text = re.sub(r"<sup>(\d+)\.?</sup>", r"[\1]", text)

        # 4. Remaining superscripts: strip tags, keep content (e.g., x<sup>2</sup> → x2)
        text = re.sub(r"<sup>(.*?)</sup>", r"\1", text, flags=re.DOTALL)

        # 5. Line breaks: <br>, <br/>, <br /> → space
        text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)

        # 6. Any remaining HTML tags → strip tags, keep text content
        text = re.sub(r"<[^>]+>", "", text)

    except Exception:
        logger.warning("HTML coercion failed", exc_info=True)

    return text


# ---------------------------------------------------------------------------
# Pass 2: Dehyphenation
# ---------------------------------------------------------------------------

# Common suffixes that indicate the hyphen is a line-break artifact
_COMMON_SUFFIXES = (
    "tion",
    "sion",
    "ment",
    "ness",
    "ing",
    "ence",
    "ance",
    "ous",
    "ious",
    "ious",
    "able",
    "ible",
    "ful",
    "less",
    "ity",
    "ive",
    "ally",
    "ately",
    "ment",
    "ly",
    "al",
    "ual",
    "ure",
    "ous",
    "er",
    "ed",
    "es",
    "ize",
    "ise",
    "ory",
    "ary",
)

_WORD_SET: frozenset[str] | None = None


def _load_word_set() -> frozenset[str]:
    """Load /usr/share/dict/words lazily. Returns frozenset() if unavailable."""
    global _WORD_SET  # noqa: PLW0603
    if _WORD_SET is not None:
        return _WORD_SET
    try:
        with open("/usr/share/dict/words") as f:
            _WORD_SET = frozenset(line.strip().lower() for line in f if line.strip())
    except OSError:
        logger.debug(
            "/usr/share/dict/words not available; dehyphenation will use suffix heuristic only"
        )
        _WORD_SET = frozenset()
    return _WORD_SET


def _should_remove_hyphen(word_before: str, word_after: str) -> bool:
    """Decide whether to remove a hyphen between two word fragments.

    Strategy (conservative — default keeps hyphen):
    1. If joined form (no hyphen) in word set → remove
    2. If hyphenated form in word set → keep
    3. If word_after matches common suffix → remove
    4. Default → keep
    """
    words = _load_word_set()

    joined = (word_before + word_after).lower()
    hyphenated = (word_before + "-" + word_after).lower()

    # 1. Joined form is a known word → remove hyphen
    if words and joined in words:
        return True

    # 2. Hyphenated form is a known word → keep hyphen
    if words and hyphenated in words:
        return False

    # 3. Suffix heuristic: if continuation starts with common suffix → remove
    word_after_lower = word_after.lower()
    for suffix in _COMMON_SUFFIXES:
        if word_after_lower.startswith(suffix):
            return True

    # 4. Default: keep hyphen (conservative)
    return False


def _dehyphenate_match(match: re.Match[str]) -> str:
    """Callback for dehyphenation regex substitution."""
    word_before = match.group(1)
    word_after = match.group(2)

    if _should_remove_hyphen(word_before, word_after):
        # Remove hyphen and join
        return word_before + word_after
    else:
        # Keep hyphen, but still join lines (remove the newline)
        return word_before + "-" + word_after


def _dehyphenate(text: str) -> str:
    """Rejoin words split across lines by hyphenation.

    Detects word-\\n followed by lowercase continuation. Always joins lines
    (removes newline). Removes hyphen only if validated by word list or
    suffix heuristic.
    """
    try:
        # Match: word fragment, hyphen, newline, optional whitespace, lowercase continuation
        text = re.sub(r"(\w+)-\n\s*([a-z]\w*)", _dehyphenate_match, text)
    except Exception:
        logger.warning("dehyphenation failed", exc_info=True)

    return text


# ---------------------------------------------------------------------------
# Pass 3: Paragraph Reflow
# ---------------------------------------------------------------------------


def _is_structural_line(line: str) -> bool:
    """Check if a line is structural markdown that should not be joined.

    Structural lines are preserved as-is (never joined with adjacent lines):
    - Empty/blank lines (paragraph boundaries)
    - Headings (#)
    - List items (-, *, +, 1.)
    - Code fence markers (```, ~~~)
    - Table rows (|)
    - Blockquotes (>)
    - Horizontal rules (---, ***, ___)
    """
    stripped = line.strip()

    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if re.match(r"^[-*+]\s", stripped):
        return True
    if re.match(r"^\d+\.\s", stripped):
        return True
    if stripped.startswith("```") or stripped.startswith("~~~"):
        return True
    if stripped.startswith("|"):
        return True
    if stripped.startswith(">"):
        return True
    if re.match(r"^[-*_]{3,}\s*$", stripped):
        return True

    return False


def _reflow_paragraphs(text: str) -> str:
    """Join non-semantic linebreaks into proper paragraphs.

    Line-by-line state machine. Tracks code block state. Buffers consecutive
    plain-text lines and joins them with spaces on flush.
    """
    try:
        lines = text.split("\n")
        output: list[str] = []
        buffer: list[str] = []
        in_code_block = False

        def flush_buffer() -> None:
            if buffer:
                joined = " ".join(buffer)
                # Collapse multiple spaces
                joined = re.sub(r"  +", " ", joined)
                output.append(joined)
                buffer.clear()

        for line in lines:
            stripped = line.strip()

            # Code fence toggle
            if stripped.startswith("```") or stripped.startswith("~~~"):
                flush_buffer()
                in_code_block = not in_code_block
                output.append(line)
                continue

            # Inside code block: emit as-is
            if in_code_block:
                output.append(line)
                continue

            # Structural line: flush buffer and emit as-is
            if _is_structural_line(line):
                flush_buffer()
                output.append(line)
                continue

            # Plain text: accumulate in buffer
            buffer.append(stripped)

        # Flush remaining buffer
        flush_buffer()

        text = "\n".join(output)

    except Exception:
        logger.warning("paragraph reflow failed", exc_info=True)

    return text
