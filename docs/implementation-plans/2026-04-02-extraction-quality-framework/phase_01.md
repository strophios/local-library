# Extraction Quality Framework Implementation Plan

**Goal:** Build a regression-tracking quality measurement system for the Marker extraction pipeline using annotated synthetic documents.

**Architecture:** Annotated synthetic academic papers compiled into PDFs across 4 noise tiers, extracted via Marker + cleanup pipeline, scored per-region on semantic (CER/WER) and structural fidelity, with regression tracking against an explicitly promoted baseline.

**Tech Stack:** Marker (extraction), rapidfuzz (edit distance), PyMuPDF (PDF rendering), Pillow (image degradation), pypandoc-binary (markdown→PDF), Rich (reporting)

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-04-02

**Reference files:**
- `tests/extraction/conftest.py` — pytest fixture patterns and marker registration
- `tests/eval/retrieval_eval.py` — metric function patterns (Functional Core)
- `src/local_library/ingestion/pdf.py` — PdfExtractor interface
- `src/local_library/ingestion/artifact_cleanup.py` — `clean_artifacts(text: str) -> str`
- `src/local_library/ingestion/markdown_cleanup.py` — `cleanup_markdown(text: str) -> str`
- `src/local_library/core/library.py:504-653` — add() orchestration showing cleanup ordering

---

## Phase 1: Annotation Parser and Metrics

**Goal:** Core infrastructure for parsing annotated markdown and computing quality scores.

<!-- START_SUBCOMPONENT_A (tasks 1) -->
<!-- START_TASK_1 -->
### Task 1: Create directory structure and add dependencies

**Files:**
- Create: `tests/extraction/synthetic/__init__.py`
- Create: `tests/extraction/synthetic/sources/.gitkeep`
- Create: `tests/extraction/synthetic/fixtures/.gitkeep`
- Create: `tests/extraction/synthetic/results/.gitkeep`
- Modify: `pyproject.toml:25-30` (add rapidfuzz to dev deps)
- Modify: `pyproject.toml:63-71` (add extraction_quality marker)

**Step 1: Create directories and __init__.py**

```
tests/extraction/synthetic/
├── __init__.py
├── sources/.gitkeep
├── fixtures/.gitkeep
└── results/.gitkeep
```

`__init__.py` is empty.

**Step 2: Add rapidfuzz to dev dependencies**

In `pyproject.toml` lines 25-30, add `rapidfuzz>=3.0.0`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
    "rapidfuzz>=3.0.0",
    "ruff>=0.8.0",
]
```

**Step 3: Add extraction_quality marker**

In `pyproject.toml` lines 63-71, add marker:

```toml
markers = [
    "unit: Unit tests (substeps)",
    "stage: Full pipeline stage tests",
    "contract: Transition/contract tests",
    "integration: End-to-end integration tests",
    "extraction: PDF extraction quality and accuracy tests",
    "extraction_quality: Synthetic document extraction quality benchmarks",
    "embedding: Embedding pipeline tests requiring sqlite-vec",
    "slow: Slow tests that load ML models or process large data",
]
```

**Step 4: Install and verify**

Run: `uv sync --extra dev`
Expected: rapidfuzz installs successfully

**Step 5: Commit**

```bash
git add tests/extraction/synthetic/ pyproject.toml
git commit -m "chore: scaffold synthetic extraction test directory and add rapidfuzz dep"
```
<!-- END_TASK_1 -->
<!-- END_SUBCOMPONENT_A -->

---

<!-- START_SUBCOMPONENT_B (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Write annotation parser tests

**Files:**
- Create: `tests/unit/test_annotations.py`

**Step 1: Write failing tests for annotation parsing**

```python
# pattern: Imperative Shell
"""Tests for synthetic document annotation parsing."""
from __future__ import annotations

import pytest

from tests.extraction.synthetic.annotations import (
    AnnotatedRegion,
    parse_annotations,
    strip_annotations,
)


class TestParseAnnotations:
    """Test parsing of feature annotations from source markdown."""

    def test_parses_single_region(self):
        text = (
            "Some text before.\n"
            "\n"
            "<!-- feature: heading-h2 id:section-intro -->\n"
            "## Introduction\n"
            "<!-- /feature -->\n"
            "\n"
            "Some text after.\n"
        )
        regions = parse_annotations(text)
        assert len(regions) == 1
        assert regions[0].feature_type == "heading-h2"
        assert regions[0].region_id == "section-intro"
        assert regions[0].content == "## Introduction"

    def test_parses_multiple_regions(self):
        text = (
            "<!-- feature: heading-h1 id:title -->\n"
            "# Main Title\n"
            "<!-- /feature -->\n"
            "\n"
            "Body text.\n"
            "\n"
            "<!-- feature: table-simple id:data-table -->\n"
            "| A | B |\n"
            "|---|---|\n"
            "| 1 | 2 |\n"
            "<!-- /feature -->\n"
        )
        regions = parse_annotations(text)
        assert len(regions) == 2
        assert regions[0].feature_type == "heading-h1"
        assert regions[1].feature_type == "table-simple"

    def test_multiline_content(self):
        text = (
            "<!-- feature: dense-prose id:intro-para -->\n"
            "This is a paragraph that spans\n"
            "multiple lines and contains\n"
            "realistic prose content.\n"
            "<!-- /feature -->\n"
        )
        regions = parse_annotations(text)
        assert len(regions) == 1
        expected = (
            "This is a paragraph that spans\n"
            "multiple lines and contains\n"
            "realistic prose content."
        )
        assert regions[0].content == expected

    def test_no_annotations_returns_empty(self):
        text = "Just plain markdown with no annotations.\n"
        regions = parse_annotations(text)
        assert regions == []

    def test_preserves_region_order(self):
        text = (
            "<!-- feature: heading-h1 id:first -->\n"
            "# First\n"
            "<!-- /feature -->\n"
            "<!-- feature: heading-h2 id:second -->\n"
            "## Second\n"
            "<!-- /feature -->\n"
            "<!-- feature: heading-h3 id:third -->\n"
            "### Third\n"
            "<!-- /feature -->\n"
        )
        regions = parse_annotations(text)
        ids = [r.region_id for r in regions]
        assert ids == ["first", "second", "third"]

    def test_nested_markdown_formatting_preserved(self):
        text = (
            "<!-- feature: display-math id:equation -->\n"
            "$$E = \\sum_{i=1}^{n} w_i \\cdot f(x_i)$$\n"
            "<!-- /feature -->\n"
        )
        regions = parse_annotations(text)
        assert "$$E = \\sum_{i=1}^{n}" in regions[0].content


class TestStripAnnotations:
    """Test stripping annotations from source markdown for PDF generation."""

    def test_strips_annotation_tags(self):
        text = (
            "Before.\n"
            "\n"
            "<!-- feature: heading-h2 id:intro -->\n"
            "## Introduction\n"
            "<!-- /feature -->\n"
            "\n"
            "After.\n"
        )
        stripped = strip_annotations(text)
        assert "<!-- feature:" not in stripped
        assert "<!-- /feature -->" not in stripped
        assert "## Introduction" in stripped
        assert "Before." in stripped
        assert "After." in stripped

    def test_preserves_non_annotation_html_comments(self):
        text = (
            "<!-- This is a regular comment -->\n"
            "<!-- feature: heading-h1 id:title -->\n"
            "# Title\n"
            "<!-- /feature -->\n"
        )
        stripped = strip_annotations(text)
        assert "<!-- This is a regular comment -->" in stripped
        assert "<!-- feature:" not in stripped

    def test_roundtrip_content_preserved(self):
        content_lines = [
            "# Title",
            "",
            "Some prose here.",
            "",
            "| A | B |",
            "|---|---|",
            "| 1 | 2 |",
        ]
        annotated = (
            "<!-- feature: heading-h1 id:title -->\n"
            "# Title\n"
            "<!-- /feature -->\n"
            "\n"
            "Some prose here.\n"
            "\n"
            "<!-- feature: table-simple id:tbl -->\n"
            "| A | B |\n"
            "|---|---|\n"
            "| 1 | 2 |\n"
            "<!-- /feature -->\n"
        )
        stripped = strip_annotations(annotated)
        for line in content_lines:
            assert line in stripped
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_annotations.py -v`
Expected: ImportError — `tests.extraction.synthetic.annotations` does not exist

---

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement annotation parser

**Files:**
- Create: `tests/extraction/synthetic/annotations.py`

**Step 1: Implement the module**

```python
# pattern: Functional Core
"""Parse and strip feature annotations from synthetic source markdown.

Annotations are HTML comments marking feature regions for quality measurement:
    <!-- feature: heading-h2 id:section-intro -->
    ## Introduction
    <!-- /feature -->

This module provides:
- parse_annotations(): Extract annotated regions with metadata
- strip_annotations(): Remove annotation markers, preserving content
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_OPEN_TAG = re.compile(
    r"^<!-- feature: (?P<feature_type>\S+) id:(?P<region_id>\S+) -->$"
)
_CLOSE_TAG = re.compile(r"^<!-- /feature -->$")


@dataclass(frozen=True)
class AnnotatedRegion:
    """A region of source markdown annotated with a feature type."""

    feature_type: str
    region_id: str
    content: str


def parse_annotations(text: str) -> list[AnnotatedRegion]:
    """Extract annotated regions from source markdown.

    Args:
        text: Source markdown containing feature annotation comments.

    Returns:
        List of AnnotatedRegion in document order.
    """
    regions: list[AnnotatedRegion] = []
    lines = text.split("\n")

    current_type: str | None = None
    current_id: str | None = None
    content_lines: list[str] = []

    for line in lines:
        if current_type is None:
            match = _OPEN_TAG.match(line.strip())
            if match:
                current_type = match.group("feature_type")
                current_id = match.group("region_id")
                content_lines = []
        else:
            if _CLOSE_TAG.match(line.strip()):
                content = "\n".join(content_lines).strip()
                regions.append(
                    AnnotatedRegion(
                        feature_type=current_type,
                        region_id=current_id,  # type: ignore[arg-type]
                        content=content,
                    )
                )
                current_type = None
                current_id = None
                content_lines = []
            else:
                content_lines.append(line)

    return regions


def strip_annotations(text: str) -> str:
    """Remove annotation markers from source markdown, preserving content.

    Strips only feature annotation tags. Other HTML comments are preserved.

    Args:
        text: Source markdown with annotation comments.

    Returns:
        Markdown with annotation tags removed, content intact.
    """
    lines = text.split("\n")
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        if _OPEN_TAG.match(stripped) or _CLOSE_TAG.match(stripped):
            continue
        output.append(line)

    return "\n".join(output)
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_annotations.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/extraction/synthetic/annotations.py tests/unit/test_annotations.py
git commit -m "feat: add annotation parser for synthetic extraction tests"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_B -->

---

<!-- START_SUBCOMPONENT_C (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Write metrics tests

**Files:**
- Create: `tests/unit/test_extraction_metrics.py`

**Step 1: Write failing tests for CER and WER**

```python
# pattern: Imperative Shell
"""Tests for extraction quality metrics (CER, WER)."""
from __future__ import annotations

import pytest

from tests.extraction.synthetic.metrics import (
    character_error_rate,
    word_error_rate,
    normalize_text,
)


class TestNormalizeText:
    """Test text normalization for metric computation."""

    def test_strips_markdown_formatting(self):
        assert normalize_text("**bold** and *italic*") == "bold and italic"

    def test_collapses_whitespace(self):
        assert normalize_text("word   word\n\nword") == "word word word"

    def test_lowercases(self):
        assert normalize_text("Hello WORLD") == "hello world"

    def test_strips_heading_markers(self):
        assert normalize_text("## Section Title") == "section title"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_preserves_alphanumeric_content(self):
        assert normalize_text("Section 3.2: Results") == "section 3.2: results"


class TestCharacterErrorRate:
    """Test CER computation."""

    def test_identical_strings(self):
        assert character_error_rate("hello world", "hello world") == 0.0

    def test_single_substitution(self):
        # "the" vs "tbe" — 1 char substitution over 3 chars
        cer = character_error_rate("the", "tbe")
        assert abs(cer - 1.0 / 3.0) < 1e-6

    def test_insertion(self):
        # "cat" vs "cart" — 1 insertion over 3 reference chars
        cer = character_error_rate("cat", "cart")
        assert abs(cer - 1.0 / 3.0) < 1e-6

    def test_deletion(self):
        # "cart" vs "cat" — 1 deletion over 4 reference chars
        cer = character_error_rate("cart", "cat")
        assert abs(cer - 1.0 / 4.0) < 1e-6

    def test_empty_reference_returns_zero(self):
        assert character_error_rate("", "") == 0.0

    def test_empty_reference_nonempty_hypothesis(self):
        # Edge case: no reference to compare against
        assert character_error_rate("", "abc") == 0.0

    def test_completely_wrong(self):
        # All characters wrong
        cer = character_error_rate("abc", "xyz")
        assert cer == 1.0

    def test_normalizes_before_comparing(self):
        # Formatting differences shouldn't count as errors
        cer = character_error_rate("**bold text**", "bold text")
        assert cer == 0.0


class TestWordErrorRate:
    """Test WER computation."""

    def test_identical_strings(self):
        assert word_error_rate("hello world", "hello world") == 0.0

    def test_single_word_substitution(self):
        # 1 word wrong out of 3
        wer = word_error_rate("the big cat", "the big dog")
        assert abs(wer - 1.0 / 3.0) < 1e-6

    def test_word_insertion(self):
        # "the cat" vs "the big cat" — 1 insertion over 2 reference words
        wer = word_error_rate("the cat", "the big cat")
        assert abs(wer - 1.0 / 2.0) < 1e-6

    def test_word_merge(self):
        # "of the" vs "ofthe" — 2 reference words become 1 wrong word
        wer = word_error_rate("of the", "ofthe")
        assert wer > 0.0

    def test_empty_reference(self):
        assert word_error_rate("", "") == 0.0

    def test_normalizes_before_comparing(self):
        wer = word_error_rate("## Section Title", "section title")
        assert wer == 0.0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_extraction_metrics.py -v`
Expected: ImportError — `tests.extraction.synthetic.metrics` does not exist

---

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Implement metrics module

**Files:**
- Create: `tests/extraction/synthetic/metrics.py`

**Step 1: Implement CER, WER, and normalization**

```python
# pattern: Functional Core
"""Extraction quality metrics: Character Error Rate and Word Error Rate.

Follows the metric function pattern from tests/eval/retrieval_eval.py:
pure functions with NumPy-style docstrings, no I/O.
"""
from __future__ import annotations

import re

from rapidfuzz.distance import Levenshtein


_MARKDOWN_FORMATTING = re.compile(
    r"(?:"
    r"\*{1,3}|"       # bold/italic markers
    r"_{1,3}|"        # underscore bold/italic
    r"#{1,6}\s|"      # heading markers
    r"`{1,3}|"        # code markers
    r"~~"             # strikethrough
    r")"
)
_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize text for metric comparison.

    Strips markdown formatting, collapses whitespace, lowercases.
    Used before CER/WER computation so formatting differences
    don't count as errors.

    Args:
        text: Raw markdown text.

    Returns:
        Normalized plain text.
    """
    result = _MARKDOWN_FORMATTING.sub("", text)
    result = _WHITESPACE.sub(" ", result)
    return result.strip().lower()


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate between reference and hypothesis.

    CER = edit_distance(ref, hyp) / len(ref)

    Both strings are normalized before comparison. Formatting differences
    (markdown markers, whitespace, case) are not counted as errors.

    Args:
        reference: Ground truth text (source markdown content).
        hypothesis: Extracted text to evaluate.

    Returns:
        CER in [0, inf). 0.0 means perfect match.
        Returns 0.0 if reference is empty.
    """
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)

    if not ref:
        return 0.0

    distance = Levenshtein.distance(ref, hyp)
    return distance / len(ref)


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate between reference and hypothesis.

    WER = edit_distance(ref_words, hyp_words) / len(ref_words)

    Both strings are normalized before comparison. Word-level edit
    distance captures merge/split errors common in OCR output.

    Args:
        reference: Ground truth text (source markdown content).
        hypothesis: Extracted text to evaluate.

    Returns:
        WER in [0, inf). 0.0 means perfect match.
        Returns 0.0 if reference is empty.
    """
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)

    ref_words = ref.split()
    hyp_words = hyp.split()

    if not ref_words:
        return 0.0

    distance = Levenshtein.distance(ref_words, hyp_words)
    return distance / len(ref_words)
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_extraction_metrics.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/extraction/synthetic/metrics.py tests/unit/test_extraction_metrics.py
git commit -m "feat: add CER and WER metrics for extraction quality measurement"
```
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_C -->

---

<!-- START_TASK_6 -->
### Task 6: Add pytest infrastructure for extraction_quality marker

**Files:**
- Create: `tests/extraction/synthetic/conftest.py`

**Step 1: Create conftest with marker registration and skip logic**

Follow the pattern from `tests/extraction/conftest.py` lines 31-78.

**Important: conftest hierarchy.** This file lives under `tests/extraction/synthetic/` which means the parent `tests/extraction/conftest.py` also applies. The parent has its own `pytest_addoption` and `pytest_collection_modifyitems` hooks. Pytest merges `addoption` hooks from parent/child conftest files, and both `collection_modifyitems` hooks run. The parent's hook skips tests with `"extraction" in item.keywords` — this uses exact key lookup in pytest's Keywords mapping, so `extraction_quality` (a different key) is NOT matched. However, the parent's `_apply_manifest_markers` function accesses golden set fixtures. Guard against this by ensuring the synthetic tests don't trigger manifest marker application.

```python
# pattern: Imperative Shell
"""Pytest configuration for synthetic extraction quality tests.

Registers the extraction_quality marker and provides --run-extraction-quality
flag to opt into these slow tests.

NOTE: This conftest sits under tests/extraction/, so the parent conftest.py
also applies. The parent's pytest_collection_modifyitems skips tests marked
with "extraction" (exact key match) — our "extraction_quality" marker is a
different key and is NOT affected. Verified via --collect-only.
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --run-extraction-quality flag."""
    parser.addoption(
        "--run-extraction-quality",
        action="store_true",
        default=False,
        help="Run synthetic extraction quality benchmark tests",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip extraction_quality tests unless --run-extraction-quality is set."""
    if config.getoption("--run-extraction-quality"):
        return

    skip_marker = pytest.mark.skip(
        reason="need --run-extraction-quality option to run"
    )
    for item in items:
        if "extraction_quality" in item.keywords:
            item.add_marker(skip_marker)
```

**Step 2: Verify marker registration AND conftest hierarchy**

Run: `uv run pytest --markers | grep extraction_quality`
Expected: Shows `extraction_quality` marker description

Run: `uv run pytest tests/extraction/synthetic/ --run-extraction-quality --collect-only 2>&1 | head -20`
Expected: Tests are collected without errors from parent conftest. If parent conftest causes errors (e.g., trying to load golden set fixtures), the synthetic tests need to be moved to `tests/synthetic_extraction/` to avoid conftest inheritance.

**Step 3: Commit**

```bash
git add tests/extraction/synthetic/conftest.py
git commit -m "feat: add pytest infrastructure for extraction_quality marker"
```
<!-- END_TASK_6 -->
