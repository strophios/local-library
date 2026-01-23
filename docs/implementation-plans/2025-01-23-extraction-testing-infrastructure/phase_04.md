# Phase 4: Accuracy Metrics and Comparison Functions

**Goal:** Implement comparison logic for metadata accuracy measurement.

**Codebase verification findings:**
- ✓ `difflib` in stdlib provides `SequenceMatcher` for string similarity
- ✓ Normalization patterns already established in Phase 2 for titles/authors
- ✓ Design specifies: title (normalized string similarity), authors (set-based), year (exact match)

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->
<!-- START_TASK_1 -->
### Task 1: Add title similarity comparison function

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add title_similarity function**

Add to `tests/extraction/conftest.py` after the existing normalization functions:

```python


def title_similarity(extracted: str, expected: str) -> float:
    """Calculate similarity between extracted and expected titles.

    Uses SequenceMatcher ratio for normalized string comparison.
    Both strings are normalized (stripped, lowercased) before comparison.

    Args:
        extracted: Title extracted from document
        expected: Ground truth title from Zotero

    Returns:
        Similarity score from 0.0 (no match) to 1.0 (exact match)
    """
    from difflib import SequenceMatcher

    # Normalize both for comparison
    norm_extracted = _normalize_title(extracted)
    norm_expected = _normalize_title(expected)

    if not norm_expected:
        # Can't compare against empty ground truth
        return 0.0

    if not norm_extracted:
        # No extracted title means no match
        return 0.0

    return SequenceMatcher(None, norm_extracted, norm_expected).ratio()
```

**Step 2: Test the function**

Run: `uv run python -c "
from tests.extraction.conftest import title_similarity

# Exact match
assert title_similarity('Hello World', 'Hello World') == 1.0

# Case insensitive
assert title_similarity('HELLO WORLD', 'hello world') == 1.0

# Similar but not exact
score = title_similarity('Attention Is All You Need', 'Attention is All You Need!')
assert 0.9 < score < 1.0, f'Expected high similarity, got {score}'

# Very different
score = title_similarity('Completely Different', 'Nothing Similar')
assert score < 0.5, f'Expected low similarity, got {score}'

# Empty handling
assert title_similarity('', 'Expected') == 0.0
assert title_similarity('Extracted', '') == 0.0

print('title_similarity tests passed')
"`
Expected: `title_similarity tests passed`

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add title_similarity comparison function"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add author match score function

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add author_match_score function**

Add to `tests/extraction/conftest.py`:

```python


def author_match_score(
    extracted: tuple[str, ...],
    expected: tuple[str, ...],
) -> float:
    """Calculate match score between extracted and expected authors.

    Uses set-based Jaccard similarity: |intersection| / |union|.
    Authors are normalized to "Family, Given" format and compared
    case-insensitively.

    Args:
        extracted: Tuple of extracted author names
        expected: Tuple of ground truth author names

    Returns:
        Match score from 0.0 (no overlap) to 1.0 (perfect match)
    """
    if not expected:
        # Can't compare against empty ground truth
        return 0.0 if extracted else 1.0  # Empty expected, empty extracted = match

    if not extracted:
        # No extracted authors means no match
        return 0.0

    # Normalize to lowercase for comparison
    extracted_set = {a.lower() for a in extracted}
    expected_set = {a.lower() for a in expected}

    intersection = extracted_set & expected_set
    union = extracted_set | expected_set

    if not union:
        return 1.0  # Both empty after normalization

    return len(intersection) / len(union)
```

**Step 2: Test the function**

Run: `uv run python -c "
from tests.extraction.conftest import author_match_score

# Perfect match (same order)
assert author_match_score(
    ('Smith, John', 'Doe, Jane'),
    ('Smith, John', 'Doe, Jane')
) == 1.0

# Perfect match (different order - set based)
assert author_match_score(
    ('Doe, Jane', 'Smith, John'),
    ('Smith, John', 'Doe, Jane')
) == 1.0

# Case insensitive
assert author_match_score(
    ('SMITH, JOHN',),
    ('Smith, John',)
) == 1.0

# Partial match (1 of 2)
score = author_match_score(
    ('Smith, John',),
    ('Smith, John', 'Doe, Jane')
)
assert 0.4 < score < 0.6, f'Expected ~0.5 (Jaccard), got {score}'

# No match
score = author_match_score(
    ('Different, Author',),
    ('Smith, John',)
)
assert score == 0.0, f'Expected 0.0, got {score}'

# Empty handling
assert author_match_score((), ('Smith, John',)) == 0.0
assert author_match_score(('Smith, John',), ()) == 0.0
assert author_match_score((), ()) == 1.0

print('author_match_score tests passed')
"`
Expected: `author_match_score tests passed`

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add author_match_score comparison function"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add year matching function

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add year_matches function**

Add to `tests/extraction/conftest.py`:

```python


def year_matches(extracted: str | None, expected: str | None) -> bool:
    """Check if extracted year matches expected year.

    Simple exact string match after normalization. Both values are
    converted to strings and stripped before comparison.

    Args:
        extracted: Year extracted from document (or None)
        expected: Ground truth year from Zotero (or None)

    Returns:
        True if years match, False otherwise
    """
    if expected is None:
        # No ground truth year - can't verify
        return True  # Assume match if we have nothing to compare against

    if extracted is None:
        # Expected a year but didn't extract one
        return False

    # Normalize to strings and strip
    extracted_str = str(extracted).strip()
    expected_str = str(expected).strip()

    return extracted_str == expected_str
```

**Step 2: Test the function**

Run: `uv run python -c "
from tests.extraction.conftest import year_matches

# Exact match
assert year_matches('2023', '2023') is True

# String vs int normalization
assert year_matches(2023, '2023') is True
assert year_matches('2023', 2023) is True

# Mismatch
assert year_matches('2022', '2023') is False

# None handling
assert year_matches(None, '2023') is False  # Expected but missing
assert year_matches('2023', None) is True   # No ground truth to compare
assert year_matches(None, None) is True     # Both None is OK

print('year_matches tests passed')
"`
Expected: `year_matches tests passed`

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add year_matches comparison function"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add DocumentResult dataclass

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add DocumentResult dataclass for capturing per-document outcomes**

Add to `tests/extraction/conftest.py` (near the GroundTruth dataclass):

```python


@dataclass
class DocumentResult:
    """Captures extraction and comparison results for a single document.

    Used for diagnostic reporting to show which documents passed/failed
    and why. Not frozen because results are built incrementally.

    Attributes:
        citekey: Document identifier
        extraction_success: Whether extraction completed without error
        extraction_error: Error message if extraction failed
        title_similarity: Score from title comparison (0.0-1.0)
        author_score: Score from author comparison (0.0-1.0)
        year_match: Whether year matched ground truth
        extracted_title: Title found in extracted text (if any)
        extracted_authors: Authors found in extracted text (if any)
        extracted_year: Year found in extracted text (if any)
    """

    citekey: str
    extraction_success: bool = False
    extraction_error: str | None = None
    title_similarity: float = 0.0
    author_score: float = 0.0
    year_match: bool = False
    extracted_title: str | None = None
    extracted_authors: tuple[str, ...] | None = None
    extracted_year: str | None = None

    def passed_title(self, threshold: float = 0.9) -> bool:
        """Check if title similarity meets threshold."""
        return self.extraction_success and self.title_similarity >= threshold

    def passed_authors(self, threshold: float = 0.7) -> bool:
        """Check if author score meets threshold."""
        return self.extraction_success and self.author_score >= threshold

    def passed_year(self) -> bool:
        """Check if year matched."""
        return self.extraction_success and self.year_match

    def passed_all(
        self,
        title_threshold: float = 0.9,
        author_threshold: float = 0.7,
    ) -> bool:
        """Check if all metadata fields passed their thresholds."""
        return (
            self.passed_title(title_threshold)
            and self.passed_authors(author_threshold)
            and self.passed_year()
        )
```

**Step 2: Test the dataclass**

Run: `uv run python -c "
from tests.extraction.conftest import DocumentResult

# Create a successful result
result = DocumentResult(
    citekey='Test2023',
    extraction_success=True,
    title_similarity=0.95,
    author_score=0.8,
    year_match=True,
)

assert result.passed_title() is True
assert result.passed_authors() is True
assert result.passed_year() is True
assert result.passed_all() is True

# Create a partial failure
result2 = DocumentResult(
    citekey='Test2024',
    extraction_success=True,
    title_similarity=0.5,  # Below threshold
    author_score=0.8,
    year_match=True,
)

assert result2.passed_title() is False
assert result2.passed_all() is False

# Create extraction failure
result3 = DocumentResult(
    citekey='Test2025',
    extraction_success=False,
    extraction_error='File not found',
)

assert result3.passed_all() is False

print('DocumentResult tests passed')
"`
Expected: `DocumentResult tests passed`

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add DocumentResult dataclass for test outcomes"
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_5 -->
### Task 5: Verify Phase 4 completion

**Files:**
- None (verification only)

**Step 1: Verify all comparison functions are importable**

Run: `uv run python -c "
from tests.extraction.conftest import (
    title_similarity,
    author_match_score,
    year_matches,
    DocumentResult,
    GroundTruth,
)
print('All comparison functions importable')
"`
Expected: `All comparison functions importable`

**Step 2: Run ruff to check code quality**

Run: `uv run ruff check tests/extraction/conftest.py`
Expected: No errors

Run: `uv run ruff format tests/extraction/conftest.py`
Expected: File formatted

**Step 3: Commit any formatting changes**

```bash
git add tests/extraction/conftest.py
git commit -m "style: apply ruff formatting to extraction conftest" --allow-empty
```

**Phase 4 complete when:**
- `title_similarity()` function computes normalized string similarity
- `author_match_score()` function computes Jaccard set similarity
- `year_matches()` function computes exact year match
- `DocumentResult` dataclass captures per-document outcomes with threshold checks
- All code passes ruff check
<!-- END_TASK_5 -->
