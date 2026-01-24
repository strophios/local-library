# Phase 2: Title Extraction

**Goal:** Extract document title from markdown with confidence scoring.

This phase implements the first field extractor, establishing patterns for candidate generation, scoring, and confidence calculation that will be reused in subsequent phases.

**Reference documentation:**
- `src/local_library/core/CLAUDE.md` - Core domain contracts
- `src/local_library/ingestion/CLAUDE.md` - Ingestion domain contracts

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->

<!-- START_TASK_1 -->
### Task 1: Create text_extraction module with TitleExtractor stub

**Files:**
- Create: `src/local_library/ingestion/text_extraction.py`

**Step 1: Create the module file**

Create `src/local_library/ingestion/text_extraction.py`:

```python
"""Text-based metadata extraction from Marker-produced markdown.

This module implements heuristic extraction of bibliographic metadata
from PDF text content. Each field has an independent extractor that
produces a FieldExtraction result with confidence scoring.

Pattern: Functional Core (pure extraction functions)
"""

from local_library.core.models import FieldExtraction


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
    # Placeholder - will be implemented in subsequent tasks
    return FieldExtraction(
        value=None,
        confidence=0.0,
        source="heuristic",
        alternatives=(),
        reasoning="not yet implemented",
    )
```

**Step 2: Verify module imports correctly**

Run:
```bash
uv run python -c "from local_library.ingestion.text_extraction import extract_title; print('OK')"
```

Expected: "OK"

**Step 3: Commit**

```bash
git add src/local_library/ingestion/text_extraction.py
git commit -m "$(cat <<'EOF'
feat(ingestion): create text_extraction module with TitleExtractor stub

Establishes module structure for M3b metadata extraction.
Extract functions are pure (Functional Core pattern).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write tests for title candidate generation

**Files:**
- Create: `tests/unit/test_text_extraction.py`

**Step 1: Create test file with candidate generation tests**

Create `tests/unit/test_text_extraction.py`:

```python
"""Tests for text-based metadata extraction."""

from __future__ import annotations

import pytest


class TestTitleExtraction:
    """Tests for title extraction from markdown text."""

    def test_extract_title_from_first_line(self) -> None:
        """Title should be extracted from isolated first line."""
        from local_library.ingestion.text_extraction import extract_title

        text = """The Impact of Climate Change on Biodiversity

        This paper examines the relationship between global warming
        and species extinction rates across multiple ecosystems.
        """

        result = extract_title(text)

        assert result.value == "The Impact of Climate Change on Biodiversity"
        assert result.confidence >= 0.7
        assert result.source == "heuristic"

    def test_extract_title_skips_blank_lines(self) -> None:
        """Extractor should skip leading blank lines."""
        from local_library.ingestion.text_extraction import extract_title

        text = """

        Machine Learning in Healthcare

        Abstract: This study presents a novel approach...
        """

        result = extract_title(text)

        assert result.value == "Machine Learning in Healthcare"

    def test_extract_title_from_markdown_header(self) -> None:
        """Title should be extracted from markdown # header."""
        from local_library.ingestion.text_extraction import extract_title

        text = """# A Survey of Natural Language Processing

        ## Introduction

        Natural language processing has seen remarkable advances...
        """

        result = extract_title(text)

        assert result.value == "A Survey of Natural Language Processing"
        assert result.confidence >= 0.8  # Headers give high confidence

    def test_extract_title_prefers_header_over_plain_text(self) -> None:
        """Markdown headers should be preferred over plain text."""
        from local_library.ingestion.text_extraction import extract_title

        text = """Journal of Computer Science
        Volume 42, Issue 3

        # Deep Learning for Image Recognition

        Abstract...
        """

        result = extract_title(text)

        # Should pick the header, not "Journal of Computer Science"
        assert result.value == "Deep Learning for Image Recognition"

    def test_extract_title_handles_multiline_title(self) -> None:
        """Titles spanning multiple lines should be joined."""
        from local_library.ingestion.text_extraction import extract_title

        text = """Understanding the Long-Term Effects of
        Monetary Policy on Economic Growth

        John Smith, Jane Doe
        University of Economics
        """

        result = extract_title(text)

        # Should join the two lines
        assert "Long-Term Effects" in result.value
        assert "Economic Growth" in result.value

    def test_extract_title_confidence_from_isolation(self) -> None:
        """Isolated titles (followed by blank line) should have higher confidence."""
        from local_library.ingestion.text_extraction import extract_title

        # Well-isolated title
        text_isolated = """Neural Networks for Pattern Recognition

        Abstract: This paper presents...
        """

        # Non-isolated title
        text_run_on = """Neural Networks for Pattern Recognition
        Abstract: This paper presents...
        """

        result_isolated = extract_title(text_isolated)
        result_run_on = extract_title(text_run_on)

        # Isolated should have higher confidence
        assert result_isolated.confidence > result_run_on.confidence

    def test_extract_title_rejects_too_short(self) -> None:
        """Very short lines should not be considered titles."""
        from local_library.ingestion.text_extraction import extract_title

        text = """A

        This is the actual title of the document

        And here is some content...
        """

        result = extract_title(text)

        # Should not pick "A" as title
        assert result.value != "A"
        assert len(result.value or "") > 5

    def test_extract_title_rejects_too_long(self) -> None:
        """Very long lines (likely paragraphs) should not be titles."""
        from local_library.ingestion.text_extraction import extract_title

        text = """This is a very long line that goes on and on and contains way too many words to be a reasonable title for any academic paper or technical document because titles are supposed to be concise and informative not rambling paragraphs of text that nobody wants to read.

        Actual Document Title

        Here is the content...
        """

        result = extract_title(text)

        # Should pick the shorter line
        assert result.value == "Actual Document Title"

    def test_extract_title_empty_text_returns_none(self) -> None:
        """Empty text should return None value with zero confidence."""
        from local_library.ingestion.text_extraction import extract_title

        result = extract_title("")

        assert result.value is None
        assert result.confidence == 0.0
        assert "empty" in result.reasoning.lower() or "no" in result.reasoning.lower()

    def test_extract_title_whitespace_only_returns_none(self) -> None:
        """Whitespace-only text should return None value."""
        from local_library.ingestion.text_extraction import extract_title

        result = extract_title("   \n\n   \t\t\n   ")

        assert result.value is None
        assert result.confidence == 0.0

    def test_extract_title_provides_alternatives(self) -> None:
        """Extraction should provide alternative candidates."""
        from local_library.ingestion.text_extraction import extract_title

        text = """Document Processing Systems

        A Comprehensive Guide

        Introduction to the field...
        """

        result = extract_title(text)

        # Should have considered both candidates
        assert len(result.alternatives) >= 1

    def test_extract_title_reasoning_explains_choice(self) -> None:
        """Reasoning should explain why this title was chosen."""
        from local_library.ingestion.text_extraction import extract_title

        text = """# Important Research Finding

        Some content here...
        """

        result = extract_title(text)

        # Reasoning should mention why (e.g., "markdown header", "first line")
        assert len(result.reasoning) > 0
        assert "header" in result.reasoning.lower() or "first" in result.reasoning.lower()
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestTitleExtraction -v
```

Expected: Most tests FAIL (stub returns None with 0 confidence)

**Step 3: Commit test file**

```bash
git add tests/unit/test_text_extraction.py
git commit -m "$(cat <<'EOF'
test(text_extraction): add title extraction test cases

Covers first-line extraction, markdown headers, multiline titles,
isolation-based confidence, length bounds, and edge cases.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement title candidate generation

**Files:**
- Modify: `src/local_library/ingestion/text_extraction.py`

**Step 1: Implement candidate generation helpers**

Update `src/local_library/ingestion/text_extraction.py`:

```python
"""Text-based metadata extraction from Marker-produced markdown.

This module implements heuristic extraction of bibliographic metadata
from PDF text content. Each field has an independent extractor that
produces a FieldExtraction result with confidence scoring.

Pattern: Functional Core (pure extraction functions)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from local_library.core.models import FieldExtraction


# Title extraction constants
_TITLE_MIN_LENGTH = 10  # Minimum characters for a valid title
_TITLE_MAX_LENGTH = 300  # Maximum characters for a valid title
_TITLE_SEARCH_WORDS = 300  # Search first N words for title candidates
_TITLE_MIN_CONFIDENCE = 0.3  # Minimum confidence to return a title


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
```

**Step 2: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestTitleExtraction -v
```

Expected: Most tests PASS. Some edge cases may need adjustment.

**Step 3: Fix any failing tests**

If tests fail, adjust either the implementation or the test expectations based on what makes sense for the use case. The key behaviors to preserve:

- Empty/whitespace input returns None with 0 confidence
- Markdown headers are preferred over plain text
- Position matters (earlier is better)
- Isolation (blank line after) increases confidence
- Very short (<10 chars) and very long (>300 chars) lines are rejected

**Step 4: Commit**

```bash
git add src/local_library/ingestion/text_extraction.py
git commit -m "$(cat <<'EOF'
feat(text_extraction): implement title candidate generation and scoring

Extracts title candidates from markdown headers and first content lines.
Scores based on position, isolation, length, and formatting signals.
Confidence derived from candidate margin.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Run full test suite and lint

**Files:**
- All modified files

**Step 1: Run all unit tests**

Run:
```bash
uv run pytest tests/unit/ -v
```

Expected: All tests PASS

**Step 2: Run linting**

Run:
```bash
uv run ruff check src/local_library/ingestion/text_extraction.py
uv run ruff format src/local_library/ingestion/text_extraction.py
```

Expected: No errors (or auto-fixed)

**Step 3: Commit any formatting fixes**

If formatting changes were made:
```bash
git add src/local_library/ingestion/text_extraction.py
git commit -m "$(cat <<'EOF'
style(text_extraction): apply ruff formatting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

---

## Phase 2 Completion Checklist

- [ ] `text_extraction.py` module created
- [ ] `extract_title()` function implemented
- [ ] Title candidate generation working
- [ ] Confidence scoring based on multiple signals
- [ ] All title extraction tests pass
- [ ] Linting passes
