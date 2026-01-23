# Phase 5: Metadata Extraction Accuracy Tests

**Goal:** Test infrastructure for M3b metadata extraction validation.

**Codebase verification findings:**
- ✓ Comparison functions from Phase 4 are available
- ✓ Ground truth loading from Phase 2 is available
- ✓ Design specifies: TITLE_THRESHOLD=0.9, AUTHOR_THRESHOLD=0.7
- ✓ M3b extraction logic does not exist yet - tests should skip/placeholder until implemented

**Note:** These tests are infrastructure for M3b. Until M3b implements actual metadata extraction from PDF content, the tests will skip with appropriate messages. The structure is in place so that when M3b adds extraction logic, the tests will automatically start running.

---

<!-- START_TASK_1 -->
### Task 1: Create metadata extraction test file

**Files:**
- Create: `tests/extraction/test_metadata_extraction.py`

**Step 1: Create the test file with imports and constants**

Create `tests/extraction/test_metadata_extraction.py`:

```python
# pattern: Imperative Shell
"""Tests for metadata extraction accuracy validation.

Validates that metadata extracted from PDF content matches ground truth
from Zotero. This is the M3b validation infrastructure.

Until M3b implements actual metadata extraction heuristics, these tests
will skip. Once extraction logic exists, tests automatically validate
against the golden set.

Accuracy thresholds:
- Title: 0.9 (90% similarity)
- Authors: 0.7 (70% Jaccard overlap)
- Year: exact match
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from local_library.ingestion.pdf import PdfExtractor

    from tests.extraction.conftest import GroundTruth

# Accuracy thresholds for M3b validation
TITLE_THRESHOLD = 0.9
AUTHOR_THRESHOLD = 0.7
```

**Step 2: Verify the file is syntactically correct**

Run: `uv run python -c "import tests.extraction.test_metadata_extraction; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add tests/extraction/test_metadata_extraction.py
git commit -m "feat(tests): create metadata extraction accuracy test file"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add placeholder extraction function

**Files:**
- Modify: `tests/extraction/test_metadata_extraction.py`

**Step 1: Add placeholder function that will be replaced by M3b**

Add to `tests/extraction/test_metadata_extraction.py`:

```python


def extract_metadata_from_text(text: str) -> dict:
    """Extract bibliographic metadata from document text.

    PLACEHOLDER: This function will be implemented in M3b.
    For now, returns empty dict to indicate no extraction capability.

    When M3b is implemented, this should:
    - Extract title from first lines / header patterns
    - Extract authors from author line patterns
    - Extract year from date patterns

    Args:
        text: Extracted text content from PDF

    Returns:
        Dict with keys: title, authors, year (all optional)
        Empty dict indicates extraction not yet implemented.
    """
    # TODO(M3b): Implement actual extraction heuristics
    # See design doc for planned approach:
    # - Title: first non-empty line, header patterns
    # - Authors: "by X, Y" patterns, affiliation proximity
    # - Year: copyright lines, date patterns
    return {}


def _extraction_implemented() -> bool:
    """Check if M3b metadata extraction is implemented.

    Returns True when extract_metadata_from_text returns actual data.
    Used to skip tests until M3b is complete.
    """
    # Test with sample text that would clearly have metadata
    sample = "Title: Test Document\nBy John Smith\n2023"
    result = extract_metadata_from_text(sample)
    return bool(result)  # Non-empty dict means implemented
```

**Step 2: Verify the placeholder returns empty**

Run: `uv run python -c "
from tests.extraction.test_metadata_extraction import (
    extract_metadata_from_text,
    _extraction_implemented,
)

result = extract_metadata_from_text('Some text')
assert result == {}, f'Expected empty dict, got {result}'

assert _extraction_implemented() is False, 'Should not be implemented yet'

print('Placeholder function works correctly')
"`
Expected: `Placeholder function works correctly`

**Step 3: Commit**

```bash
git add tests/extraction/test_metadata_extraction.py
git commit -m "feat(tests): add placeholder extraction function for M3b"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add TestMetadataExtraction class with title test

**Files:**
- Modify: `tests/extraction/test_metadata_extraction.py`

**Step 1: Add the test class with title accuracy test**

Add to `tests/extraction/test_metadata_extraction.py`:

```python


@pytest.mark.extraction
class TestMetadataExtraction:
    """Tests for M3b metadata extraction accuracy.

    These tests compare extracted metadata against Zotero ground truth.
    Until M3b implements extraction, tests skip with informative messages.
    """

    @pytest.fixture(autouse=True)
    def _check_extraction_implemented(self) -> None:
        """Skip all tests if M3b extraction is not yet implemented."""
        if not _extraction_implemented():
            pytest.skip(
                "M3b metadata extraction not yet implemented. "
                "Implement extract_metadata_from_text() to enable these tests."
            )

    @pytest.mark.parametrize(
        "pdf_path,citekey",
        [],  # Populated by pytest_generate_tests in conftest.py
        indirect=False,
    )
    def test_title_accuracy(
        self,
        pdf_path: Path,
        citekey: str,
        pdf_extractor: PdfExtractor,
        ground_truth: dict[str, GroundTruth],
    ) -> None:
        """Extracted title should match ground truth with ≥90% similarity.

        Title extraction is the primary metadata signal for identification.
        High accuracy is required for reliable matching.
        """
        from tests.extraction.conftest import title_similarity

        if citekey not in ground_truth:
            pytest.skip(f"No ground truth available for {citekey}")

        # Extract text and metadata
        result = pdf_extractor.extract(pdf_path)
        metadata = extract_metadata_from_text(result.text)

        extracted_title = metadata.get("title", "")
        expected_title = ground_truth[citekey].title

        similarity = title_similarity(extracted_title, expected_title)

        assert similarity >= TITLE_THRESHOLD, (
            f"Title accuracy for {citekey}: {similarity:.2%} "
            f"(threshold: {TITLE_THRESHOLD:.0%})\n"
            f"  Extracted: {extracted_title!r}\n"
            f"  Expected:  {expected_title!r}"
        )
```

**Step 2: Verify test is discovered**

Run: `uv run pytest tests/extraction/test_metadata_extraction.py --collect-only 2>&1 | head -20`
Expected: Shows test collection (tests will skip when run due to extraction not implemented)

**Step 3: Commit**

```bash
git add tests/extraction/test_metadata_extraction.py
git commit -m "feat(tests): add title accuracy test for M3b validation"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add author accuracy test

**Files:**
- Modify: `tests/extraction/test_metadata_extraction.py`

**Step 1: Add author accuracy test to TestMetadataExtraction class**

Add to the `TestMetadataExtraction` class:

```python

    @pytest.mark.parametrize(
        "pdf_path,citekey",
        [],  # Populated by pytest_generate_tests in conftest.py
        indirect=False,
    )
    def test_author_accuracy(
        self,
        pdf_path: Path,
        citekey: str,
        pdf_extractor: PdfExtractor,
        ground_truth: dict[str, GroundTruth],
    ) -> None:
        """Extracted authors should match ground truth with ≥70% overlap.

        Author extraction is more challenging due to varied formats.
        A lower threshold accounts for partial matches and ordering variations.
        """
        from tests.extraction.conftest import author_match_score

        if citekey not in ground_truth:
            pytest.skip(f"No ground truth available for {citekey}")

        # Extract text and metadata
        result = pdf_extractor.extract(pdf_path)
        metadata = extract_metadata_from_text(result.text)

        extracted_authors = tuple(metadata.get("authors", []))
        expected_authors = ground_truth[citekey].authors

        score = author_match_score(extracted_authors, expected_authors)

        assert score >= AUTHOR_THRESHOLD, (
            f"Author accuracy for {citekey}: {score:.2%} "
            f"(threshold: {AUTHOR_THRESHOLD:.0%})\n"
            f"  Extracted: {extracted_authors}\n"
            f"  Expected:  {expected_authors}"
        )
```

**Step 2: Verify test is discovered**

Run: `uv run pytest tests/extraction/test_metadata_extraction.py --collect-only 2>&1 | grep "test_author"`
Expected: Shows `test_author_accuracy` tests

**Step 3: Commit**

```bash
git add tests/extraction/test_metadata_extraction.py
git commit -m "feat(tests): add author accuracy test for M3b validation"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add year accuracy test

**Files:**
- Modify: `tests/extraction/test_metadata_extraction.py`

**Step 1: Add year accuracy test to TestMetadataExtraction class**

Add to the `TestMetadataExtraction` class:

```python

    @pytest.mark.parametrize(
        "pdf_path,citekey",
        [],  # Populated by pytest_generate_tests in conftest.py
        indirect=False,
    )
    def test_year_accuracy(
        self,
        pdf_path: Path,
        citekey: str,
        pdf_extractor: PdfExtractor,
        ground_truth: dict[str, GroundTruth],
    ) -> None:
        """Extracted year should exactly match ground truth.

        Year extraction should be reliable when present in document.
        Missing ground truth years are considered passing.
        """
        from tests.extraction.conftest import year_matches

        if citekey not in ground_truth:
            pytest.skip(f"No ground truth available for {citekey}")

        gt = ground_truth[citekey]

        # Skip if no ground truth year to compare
        if gt.issued_year is None:
            pytest.skip(f"No ground truth year for {citekey}")

        # Extract text and metadata
        result = pdf_extractor.extract(pdf_path)
        metadata = extract_metadata_from_text(result.text)

        extracted_year = metadata.get("year")

        assert year_matches(extracted_year, gt.issued_year), (
            f"Year mismatch for {citekey}\n"
            f"  Extracted: {extracted_year!r}\n"
            f"  Expected:  {gt.issued_year!r}"
        )
```

**Step 2: Verify test is discovered**

Run: `uv run pytest tests/extraction/test_metadata_extraction.py --collect-only 2>&1 | grep "test_year"`
Expected: Shows `test_year_accuracy` tests

**Step 3: Commit**

```bash
git add tests/extraction/test_metadata_extraction.py
git commit -m "feat(tests): add year accuracy test for M3b validation"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Verify Phase 5 completion

**Files:**
- None (verification only)

**Step 1: Verify all tests are discoverable**

Run: `uv run pytest tests/extraction/test_metadata_extraction.py --collect-only`
Expected: Shows collection of parametrized tests for title, author, and year

**Step 2: Verify tests skip appropriately**

Run: `uv run pytest tests/extraction/test_metadata_extraction.py -v 2>&1 | head -20`
Expected: Tests should skip with message about M3b not being implemented

**Step 3: Run ruff to check code quality**

Run: `uv run ruff check tests/extraction/test_metadata_extraction.py`
Expected: No errors

Run: `uv run ruff format tests/extraction/test_metadata_extraction.py`
Expected: File formatted

**Step 4: Commit any formatting changes**

```bash
git add tests/extraction/test_metadata_extraction.py
git commit -m "style: apply ruff formatting to metadata extraction tests" --allow-empty
```

**Phase 5 complete when:**
- `test_metadata_extraction.py` exists with `TestMetadataExtraction` class
- Tests for title, author, and year accuracy are discoverable
- Tests skip with informative message until M3b is implemented
- `extract_metadata_from_text()` placeholder is ready for M3b implementation
- All code passes ruff check
<!-- END_TASK_6 -->
