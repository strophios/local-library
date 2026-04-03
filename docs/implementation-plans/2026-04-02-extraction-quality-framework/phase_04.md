## Phase 4: Structural Validators

**Goal:** Feature-specific validation functions for structural fidelity scoring.

**Convention:** All validators are pure functions (Functional Core) that never raise. Unknown input returns a default score. Dispatch by feature type prefix via `validate_region()`.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Write structural validator tests

**Files:**
- Create: `tests/unit/test_structural_validators.py`

**Step 1: Write failing tests**

```python
# pattern: Imperative Shell
"""Tests for feature-specific structural fidelity validators."""
from __future__ import annotations

import pytest

from tests.extraction.synthetic.validators import (
    StructuralScore,
    validate_heading,
    validate_table,
    validate_list,
    validate_math_display,
    validate_math_inline,
    validate_footnote,
    validate_blockquote,
    validate_code_block,
    validate_region,
)


class TestValidateHeading:
    """Test heading structural validation."""

    def test_exact_heading_match(self):
        score = validate_heading("## Methods", "## Methods")
        assert score.detected is True
        assert score.level_accuracy == 1.0

    def test_heading_detected_wrong_level(self):
        score = validate_heading("## Methods", "### Methods")
        assert score.detected is True
        assert score.level_accuracy == 0.0

    def test_heading_detected_as_bold(self):
        """Heading extracted as bold text, not a heading."""
        score = validate_heading("## Methods", "**Methods**")
        assert score.detected is False

    def test_heading_off_by_one_level(self):
        score = validate_heading("## Methods", "# Methods")
        assert score.detected is True
        assert score.level_accuracy == 0.0  # Wrong level

    def test_empty_extracted(self):
        score = validate_heading("## Methods", "")
        assert score.detected is False


class TestValidateTable:
    """Test table structural validation."""

    def test_table_preserved(self):
        source = "| A | B |\n|---|---|\n| 1 | 2 |"
        extracted = "| A | B |\n|---|---|\n| 1 | 2 |"
        score = validate_table(source, extracted)
        assert score.detected is True
        assert score.column_accuracy == 1.0

    def test_table_lost_becomes_text(self):
        source = "| A | B |\n|---|---|\n| 1 | 2 |"
        extracted = "A B\n1 2"
        score = validate_table(source, extracted)
        assert score.detected is False

    def test_table_wrong_column_count(self):
        source = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
        extracted = "| A | B |\n|---|---|\n| 1 | 2 |"
        score = validate_table(source, extracted)
        assert score.detected is True
        assert score.column_accuracy < 1.0

    def test_empty_extracted(self):
        source = "| A | B |\n|---|---|\n| 1 | 2 |"
        score = validate_table(source, "")
        assert score.detected is False


class TestValidateList:
    """Test list structural validation."""

    def test_unordered_list_preserved(self):
        source = "- Item 1\n- Item 2\n- Item 3"
        extracted = "- Item 1\n- Item 2\n- Item 3"
        score = validate_list(source, extracted)
        assert score.detected is True
        assert score.item_count_accuracy == 1.0

    def test_ordered_list_preserved(self):
        source = "1. First\n2. Second\n3. Third"
        extracted = "1. First\n2. Second\n3. Third"
        score = validate_list(source, extracted)
        assert score.detected is True

    def test_list_lost(self):
        source = "- Item 1\n- Item 2\n- Item 3"
        extracted = "Item 1 Item 2 Item 3"
        score = validate_list(source, extracted)
        assert score.detected is False

    def test_nested_list(self):
        source = "- Item 1\n  - Sub item\n- Item 2"
        extracted = "- Item 1\n  - Sub item\n- Item 2"
        score = validate_list(source, extracted)
        assert score.detected is True
        assert score.max_depth >= 2


class TestValidateMathDisplay:
    """Test display math structural validation."""

    def test_latex_block_preserved(self):
        source = "$$E = mc^2$$"
        extracted = "$$E = mc^2$$"
        score = validate_math_display(source, extracted)
        assert score.detected is True

    def test_latex_lost(self):
        source = "$$E = mc^2$$"
        extracted = "E = mc2"
        score = validate_math_display(source, extracted)
        assert score.detected is False

    def test_single_dollar_not_display(self):
        source = "$$E = mc^2$$"
        extracted = "$E = mc^2$"
        # Single dollar is inline math, not display — still detected as math
        score = validate_math_display(source, extracted)
        assert score.detected is True  # Math detected, even if style changed


class TestValidateMathInline:
    """Test inline math structural validation."""

    def test_inline_math_preserved(self):
        source = "where $x > 0$ holds"
        extracted = "where $x > 0$ holds"
        score = validate_math_inline(source, extracted)
        assert score.detected is True

    def test_inline_math_lost(self):
        source = "where $x > 0$ holds"
        extracted = "where x > 0 holds"
        score = validate_math_inline(source, extracted)
        assert score.detected is False


class TestValidateFootnote:
    """Test footnote structural validation."""

    def test_footnote_marker_preserved(self):
        source = "Text with a footnote[1] reference."
        extracted = "Text with a footnote[1] reference."
        score = validate_footnote(source, extracted)
        assert score.detected is True

    def test_footnote_marker_lost(self):
        source = "Text with a footnote[1] reference."
        extracted = "Text with a footnote reference."
        score = validate_footnote(source, extracted)
        assert score.detected is False


class TestValidateBlockquote:
    """Test blockquote structural validation."""

    def test_blockquote_preserved(self):
        source = "> This is a quoted passage."
        extracted = "> This is a quoted passage."
        score = validate_blockquote(source, extracted)
        assert score.detected is True

    def test_blockquote_lost(self):
        source = "> This is a quoted passage."
        extracted = "This is a quoted passage."
        score = validate_blockquote(source, extracted)
        assert score.detected is False


class TestValidateCodeBlock:
    """Test code block structural validation."""

    def test_fenced_code_preserved(self):
        source = "```python\nprint('hello')\n```"
        extracted = "```python\nprint('hello')\n```"
        score = validate_code_block(source, extracted)
        assert score.detected is True

    def test_code_block_lost(self):
        source = "```python\nprint('hello')\n```"
        extracted = "print('hello')"
        score = validate_code_block(source, extracted)
        assert score.detected is False


class TestValidateRegion:
    """Test dispatch to correct validator based on feature type."""

    def test_dispatches_heading(self):
        score = validate_region("heading-h2", "## Title", "## Title")
        assert score.detected is True

    def test_dispatches_table(self):
        source = "| A |\n|---|\n| 1 |"
        score = validate_region("table-simple", source, source)
        assert score.detected is True

    def test_unknown_feature_returns_default(self):
        score = validate_region("unknown-type", "text", "text")
        # Should not crash; returns a score with detected=None (unknown)
        assert score is not None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_structural_validators.py -v`
Expected: ImportError — `tests.extraction.synthetic.validators` does not exist

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement structural validators

**Files:**
- Create: `tests/extraction/synthetic/validators.py`

**Step 1: Implement the module**

```python
# pattern: Functional Core
"""Feature-specific structural fidelity validators.

Each validator takes source and extracted text for a specific region,
and evaluates whether the structural intent was preserved. Validators
are pure functions that never raise — they return a StructuralScore
with detected=False on any unexpected input.

Validators are dispatched by feature type via validate_region().
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ValidatorFn = Callable[[str, str], "StructuralScore"]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\|.+\|$", re.MULTILINE)
_TABLE_SEP_RE = re.compile(r"^\|[-:| ]+\|$", re.MULTILINE)
_LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s", re.MULTILINE)
_DISPLAY_MATH_RE = re.compile(r"\$\$.+?\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$).+?(?<!\$)\$(?!\$)")
_FOOTNOTE_RE = re.compile(r"\[\d+\]")
_BLOCKQUOTE_RE = re.compile(r"^>\s", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^(`{3,}|~{3,})", re.MULTILINE)


@dataclass(frozen=True)
class StructuralScore:
    """Result of structural validation for a single region.

    Attributes:
        detected: Whether the structural element was found. None if
            the feature type is unknown (no validator available).
        details: Feature-specific metrics (e.g., level_accuracy for
            headings, column_accuracy for tables).
    """

    detected: bool | None = None
    details: dict[str, float] = field(default_factory=dict)

    @property
    def level_accuracy(self) -> float:
        return self.details.get("level_accuracy", 0.0)

    @property
    def column_accuracy(self) -> float:
        return self.details.get("column_accuracy", 0.0)

    @property
    def item_count_accuracy(self) -> float:
        return self.details.get("item_count_accuracy", 0.0)

    @property
    def max_depth(self) -> int:
        return int(self.details.get("max_depth", 0))


def validate_heading(source: str, extracted: str) -> StructuralScore:
    """Validate heading detection and level accuracy.

    Args:
        source: Source heading text (e.g., "## Methods").
        extracted: Corresponding extracted text.

    Returns:
        StructuralScore with detected and level_accuracy.
    """
    try:
        source_match = _HEADING_RE.search(source)
        if not source_match:
            return StructuralScore(detected=False)

        source_level = len(source_match.group(1))

        extracted_match = _HEADING_RE.search(extracted)
        if not extracted_match:
            return StructuralScore(detected=False)

        extracted_level = len(extracted_match.group(1))
        level_acc = 1.0 if source_level == extracted_level else 0.0

        return StructuralScore(
            detected=True,
            details={"level_accuracy": level_acc},
        )
    except Exception:
        logger.warning("heading validation failed", exc_info=True)
        return StructuralScore(detected=False)


def validate_table(source: str, extracted: str) -> StructuralScore:
    """Validate table detection and column count accuracy.

    Args:
        source: Source table markdown.
        extracted: Corresponding extracted text.

    Returns:
        StructuralScore with detected and column_accuracy.
    """
    try:
        if not extracted.strip():
            return StructuralScore(detected=False)

        source_rows = _TABLE_ROW_RE.findall(source)
        extracted_rows = _TABLE_ROW_RE.findall(extracted)

        if not extracted_rows:
            return StructuralScore(detected=False)

        # Count columns from first data row
        source_cols = len(source_rows[0].split("|")) - 2 if source_rows else 0
        extracted_cols = (
            len(extracted_rows[0].split("|")) - 2 if extracted_rows else 0
        )

        col_acc = (
            1.0
            if source_cols == extracted_cols
            else (
                min(source_cols, extracted_cols) / max(source_cols, extracted_cols)
                if max(source_cols, extracted_cols) > 0
                else 0.0
            )
        )

        return StructuralScore(
            detected=True,
            details={"column_accuracy": col_acc},
        )
    except Exception:
        logger.warning("table validation failed", exc_info=True)
        return StructuralScore(detected=False)


def validate_list(source: str, extracted: str) -> StructuralScore:
    """Validate list detection, item count, and nesting depth.

    Args:
        source: Source list markdown.
        extracted: Corresponding extracted text.

    Returns:
        StructuralScore with detected, item_count_accuracy, max_depth.
    """
    try:
        source_items = _LIST_ITEM_RE.findall(source)
        extracted_items = _LIST_ITEM_RE.findall(extracted)

        if not extracted_items:
            return StructuralScore(detected=False)

        source_count = len(source_items)
        extracted_count = len(extracted_items)
        count_acc = (
            min(source_count, extracted_count) / max(source_count, extracted_count)
            if max(source_count, extracted_count) > 0
            else 0.0
        )

        # Compute max nesting depth from indentation
        def _max_depth(items: list[tuple[str, str]]) -> int:
            if not items:
                return 0
            depths = set()
            for indent, _marker in items:
                depths.add(len(indent))
            return len(depths)

        depth = _max_depth(extracted_items)

        return StructuralScore(
            detected=True,
            details={
                "item_count_accuracy": count_acc,
                "max_depth": float(depth),
            },
        )
    except Exception:
        logger.warning("list validation failed", exc_info=True)
        return StructuralScore(detected=False)


def validate_math_display(source: str, extracted: str) -> StructuralScore:
    """Validate display math ($$...$$) detection.

    Also accepts single-dollar math ($...$) as detected, since the math
    content survived even if the display/inline distinction was lost.

    Args:
        source: Source text containing display math.
        extracted: Corresponding extracted text.

    Returns:
        StructuralScore with detected.
    """
    try:
        has_display = bool(_DISPLAY_MATH_RE.search(extracted))
        has_inline = bool(_INLINE_MATH_RE.search(extracted))
        detected = has_display or has_inline
        return StructuralScore(detected=detected)
    except Exception:
        logger.warning("display math validation failed", exc_info=True)
        return StructuralScore(detected=False)


def validate_math_inline(source: str, extracted: str) -> StructuralScore:
    """Validate inline math ($...$) detection.

    Args:
        source: Source text containing inline math.
        extracted: Corresponding extracted text.

    Returns:
        StructuralScore with detected.
    """
    try:
        detected = bool(_INLINE_MATH_RE.search(extracted))
        return StructuralScore(detected=detected)
    except Exception:
        logger.warning("inline math validation failed", exc_info=True)
        return StructuralScore(detected=False)


def validate_footnote(source: str, extracted: str) -> StructuralScore:
    """Validate footnote marker detection.

    Args:
        source: Source text containing footnote markers [N].
        extracted: Corresponding extracted text.

    Returns:
        StructuralScore with detected.
    """
    try:
        source_markers = _FOOTNOTE_RE.findall(source)
        extracted_markers = _FOOTNOTE_RE.findall(extracted)
        detected = len(extracted_markers) > 0 if source_markers else False
        return StructuralScore(detected=detected)
    except Exception:
        logger.warning("footnote validation failed", exc_info=True)
        return StructuralScore(detected=False)


def validate_blockquote(source: str, extracted: str) -> StructuralScore:
    """Validate blockquote detection.

    Args:
        source: Source text with blockquote markers.
        extracted: Corresponding extracted text.

    Returns:
        StructuralScore with detected.
    """
    try:
        detected = bool(_BLOCKQUOTE_RE.search(extracted))
        return StructuralScore(detected=detected)
    except Exception:
        logger.warning("blockquote validation failed", exc_info=True)
        return StructuralScore(detected=False)


def validate_code_block(source: str, extracted: str) -> StructuralScore:
    """Validate fenced code block detection.

    Args:
        source: Source text with code fences.
        extracted: Corresponding extracted text.

    Returns:
        StructuralScore with detected.
    """
    try:
        fences = _CODE_FENCE_RE.findall(extracted)
        # Need at least 2 fences (open + close) to count as detected
        detected = len(fences) >= 2
        return StructuralScore(detected=detected)
    except Exception:
        logger.warning("code block validation failed", exc_info=True)
        return StructuralScore(detected=False)


# Dispatch map: feature type prefix -> validator function
_VALIDATORS: dict[str, ValidatorFn] = {
    "heading": validate_heading,
    "table": validate_table,
    "list": validate_list,
    "nested-list": validate_list,
    "display-math": validate_math_display,
    "inline-math": validate_math_inline,
    "footnote": validate_footnote,
    "blockquote": validate_blockquote,
    "code-block": validate_code_block,
}


def validate_region(
    feature_type: str, source: str, extracted: str
) -> StructuralScore:
    """Dispatch to the appropriate validator based on feature type.

    Matches on prefix: "heading-h2" matches "heading", "table-complex"
    matches "table", etc. Unknown feature types return StructuralScore
    with detected=None.

    Args:
        feature_type: Feature type string from annotation.
        source: Source region content.
        extracted: Corresponding extracted region content.

    Returns:
        StructuralScore from the appropriate validator.
    """
    for prefix, validator in _VALIDATORS.items():
        if feature_type.startswith(prefix):
            return validator(source, extracted)

    # Unknown feature type — no structural validator available
    return StructuralScore(detected=None)
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_structural_validators.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/extraction/synthetic/validators.py tests/unit/test_structural_validators.py
git commit -m "feat: add structural fidelity validators for extraction quality"
```

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
