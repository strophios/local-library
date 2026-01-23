# Phase 2: Ground Truth Loading

**Goal:** Load and normalize Zotero metadata as ground truth for comparison.

**Codebase verification findings:**
- ✓ `ZoteroItem` dataclass at `zotero.py:65-96` has `csl_json: dict[str, Any]` field
- ✓ CSL-JSON author format: `{"family": "Smith", "given": "John"}` or `{"literal": "Organization"}`
- ✓ CSL-JSON date format: `{"date-parts": [[2023, 5, 15]]}` or `{"date-parts": [[2023]]}`
- ✓ `ZoteroReader.get_item(citekey)` returns `ZoteroItem` with full metadata
- ✓ Existing normalization patterns in `metadata.py:188-246`

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add normalization helper functions

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add imports and normalization functions**

Add after the existing imports in `tests/extraction/conftest.py`:

```python
from dataclasses import dataclass


def _normalize_title(title: str) -> str:
    """Normalize title for comparison.

    Strips whitespace and converts to lowercase for case-insensitive
    comparison. Preserves internal whitespace for word matching.

    Args:
        title: Raw title string from CSL-JSON

    Returns:
        Normalized title (stripped, lowercased)
    """
    return title.strip().lower()


def _normalize_author_name(author: dict) -> str:
    """Normalize a single author entry to "Family, Given" format.

    Handles both personal names (family/given) and organizational names (literal).

    Args:
        author: Single author dict from CSL-JSON author array

    Returns:
        Normalized name string: "Family, Given" or literal name
    """
    if "literal" in author:
        # Organizational author
        return author["literal"].strip()

    family = author.get("family", "").strip()
    given = author.get("given", "").strip()

    if family and given:
        return f"{family}, {given}"
    elif family:
        return family
    elif given:
        return given
    else:
        return ""


def _normalize_authors(authors: list[dict]) -> tuple[str, ...]:
    """Normalize author list for comparison.

    Converts all authors to "Family, Given" format and sorts alphabetically
    for order-independent comparison.

    Args:
        authors: Author array from CSL-JSON

    Returns:
        Tuple of normalized author names, sorted alphabetically
    """
    normalized = [_normalize_author_name(a) for a in authors]
    # Filter out empty strings from malformed entries
    normalized = [n for n in normalized if n]
    # Sort for order-independent comparison
    return tuple(sorted(normalized))


def _extract_year(issued: dict | None) -> str | None:
    """Extract publication year from CSL-JSON issued field.

    CSL-JSON date format: {"date-parts": [[2023, 5, 15]]} or {"date-parts": [[2023]]}
    The first element of date-parts[0] is the year.

    Args:
        issued: The "issued" field from CSL-JSON, or None

    Returns:
        Year as string (e.g., "2023") or None if not available
    """
    if not issued:
        return None

    date_parts = issued.get("date-parts")
    if not date_parts or not date_parts[0]:
        return None

    year = date_parts[0][0]
    if year is None:
        return None

    return str(year)
```

**Step 2: Verify normalization functions work**

Run: `uv run python -c "
from tests.extraction.conftest import _normalize_title, _normalize_authors, _extract_year

# Test title normalization
assert _normalize_title('  Hello World  ') == 'hello world'

# Test author normalization
authors = [{'family': 'Smith', 'given': 'John'}, {'literal': 'WHO'}]
assert _normalize_authors(authors) == ('Smith, John', 'WHO')

# Test year extraction
assert _extract_year({'date-parts': [[2023, 5, 15]]}) == '2023'
assert _extract_year(None) is None

print('All normalization tests passed')
"`
Expected: `All normalization tests passed`

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add normalization helpers for ground truth comparison"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create GroundTruth dataclass

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add GroundTruth dataclass**

Add to `tests/extraction/conftest.py` after the normalization functions from Task 1:

```python


@dataclass(frozen=True)
class GroundTruth:
    """Ground truth metadata for a single document.

    Normalized from CSL-JSON for consistent comparison against extracted metadata.
    All fields use normalized string forms suitable for comparison.

    Attributes:
        citekey: BetterBibTeX citation key (lookup key)
        title: Document title, stripped and lowercased
        authors: Tuple of author names in "Family, Given" format, sorted
        issued_year: Publication year as string, or None if not available
    """

    citekey: str
    title: str
    authors: tuple[str, ...]
    issued_year: str | None

    @classmethod
    def from_csl_json(cls, citekey: str, csl_json: dict) -> "GroundTruth":
        """Create GroundTruth from CSL-JSON metadata.

        Normalizes:
        - Title: stripped, lowercased
        - Authors: "Family, Given" format, sorted alphabetically
        - Year: extracted from date-parts[0][0]

        Args:
            citekey: The citation key for this item
            csl_json: CSL-JSON metadata dictionary

        Returns:
            Normalized GroundTruth instance
        """
        title = _normalize_title(csl_json.get("title", ""))
        authors = _normalize_authors(csl_json.get("author", []))
        issued_year = _extract_year(csl_json.get("issued"))

        return cls(
            citekey=citekey,
            title=title,
            authors=authors,
            issued_year=issued_year,
        )
```

**Step 2: Verify the dataclass is syntactically correct**

Run: `uv run python -c "from tests.extraction.conftest import GroundTruth; print('OK')"`
Expected: Will fail (normalization functions not yet defined) - this is expected

**Step 3: Commit partial progress**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add GroundTruth dataclass for ground truth metadata"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add normalization helper functions

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add normalization functions before the GroundTruth class**

Insert these functions after the imports but before the `GroundTruth` dataclass:

```python


def _normalize_title(title: str) -> str:
    """Normalize title for comparison.

    Strips whitespace and converts to lowercase for case-insensitive
    comparison. Preserves internal whitespace for word matching.

    Args:
        title: Raw title string from CSL-JSON

    Returns:
        Normalized title (stripped, lowercased)
    """
    return title.strip().lower()


def _normalize_author_name(author: dict) -> str:
    """Normalize a single author entry to "Family, Given" format.

    Handles both personal names (family/given) and organizational names (literal).

    Args:
        author: Single author dict from CSL-JSON author array

    Returns:
        Normalized name string: "Family, Given" or literal name
    """
    if "literal" in author:
        # Organizational author
        return author["literal"].strip()

    family = author.get("family", "").strip()
    given = author.get("given", "").strip()

    if family and given:
        return f"{family}, {given}"
    elif family:
        return family
    elif given:
        return given
    else:
        return ""


def _normalize_authors(authors: list[dict]) -> tuple[str, ...]:
    """Normalize author list for comparison.

    Converts all authors to "Family, Given" format and sorts alphabetically
    for order-independent comparison.

    Args:
        authors: Author array from CSL-JSON

    Returns:
        Tuple of normalized author names, sorted alphabetically
    """
    normalized = [_normalize_author_name(a) for a in authors]
    # Filter out empty strings from malformed entries
    normalized = [n for n in normalized if n]
    # Sort for order-independent comparison
    return tuple(sorted(normalized))


def _extract_year(issued: dict | None) -> str | None:
    """Extract publication year from CSL-JSON issued field.

    CSL-JSON date format: {"date-parts": [[2023, 5, 15]]} or {"date-parts": [[2023]]}
    The first element of date-parts[0] is the year.

    Args:
        issued: The "issued" field from CSL-JSON, or None

    Returns:
        Year as string (e.g., "2023") or None if not available
    """
    if not issued:
        return None

    date_parts = issued.get("date-parts")
    if not date_parts or not date_parts[0]:
        return None

    year = date_parts[0][0]
    if year is None:
        return None

    return str(year)
```

**Step 2: Verify normalization functions work**

Run: `uv run python -c "
from tests.extraction.conftest import _normalize_title, _normalize_authors, _extract_year

# Test title normalization
assert _normalize_title('  Hello World  ') == 'hello world'

# Test author normalization
authors = [{'family': 'Smith', 'given': 'John'}, {'literal': 'WHO'}]
assert _normalize_authors(authors) == ('Smith, John', 'WHO')

# Test year extraction
assert _extract_year({'date-parts': [[2023, 5, 15]]}) == '2023'
assert _extract_year(None) is None

print('All normalization tests passed')
"`
Expected: `All normalization tests passed`

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add normalization helpers for ground truth comparison"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add ground_truth fixture

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add ground_truth fixture**

Append to `tests/extraction/conftest.py`:

```python


@pytest.fixture(scope="session")
def ground_truth(
    zotero_reader: ZoteroReader,
    golden_set_pdfs: list[tuple[Path, str]],
) -> dict[str, GroundTruth]:
    """Load ground truth metadata for all golden set documents.

    Looks up each citekey in Zotero and normalizes the CSL-JSON metadata
    for comparison. Documents without Zotero entries are skipped with a
    warning.

    Args:
        zotero_reader: Session-scoped ZoteroReader
        golden_set_pdfs: List of (path, citekey) tuples from golden set

    Returns:
        Dictionary mapping citekey to GroundTruth
    """
    import warnings

    from local_library.core.errors import ZoteroError

    truth: dict[str, GroundTruth] = {}

    for _pdf_path, citekey in golden_set_pdfs:
        try:
            item = zotero_reader.get_item(citekey)
            truth[citekey] = GroundTruth.from_csl_json(citekey, item.csl_json)
        except ZoteroError as e:
            warnings.warn(
                f"Could not load ground truth for {citekey}: {e}",
                stacklevel=2,
            )

    if not truth:
        pytest.skip("No ground truth could be loaded from Zotero")

    return truth
```

**Step 2: Verify fixture is discoverable**

Run: `uv run pytest tests/extraction/ --collect-only --fixtures 2>&1 | grep ground_truth`
Expected: Shows `ground_truth` fixture listed

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add ground_truth fixture for loading Zotero metadata"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Verify Phase 2 completion

**Files:**
- None (verification only)

**Step 1: Verify GroundTruth can be created from CSL-JSON**

Run: `uv run python -c "
from tests.extraction.conftest import GroundTruth

# Simulate CSL-JSON data
csl_json = {
    'title': 'Attention Is All You Need',
    'author': [
        {'family': 'Vaswani', 'given': 'Ashish'},
        {'family': 'Shazeer', 'given': 'Noam'},
    ],
    'issued': {'date-parts': [[2017]]}
}

gt = GroundTruth.from_csl_json('Vaswani2017', csl_json)
print(f'Citekey: {gt.citekey}')
print(f'Title: {gt.title}')
print(f'Authors: {gt.authors}')
print(f'Year: {gt.issued_year}')

assert gt.citekey == 'Vaswani2017'
assert gt.title == 'attention is all you need'
assert gt.authors == ('Shazeer, Noam', 'Vaswani, Ashish')  # Sorted!
assert gt.issued_year == '2017'
print('GroundTruth creation verified')
"`
Expected: Shows the normalized values and `GroundTruth creation verified`

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

**Phase 2 complete when:**
- `GroundTruth` dataclass exists with `from_csl_json()` classmethod
- Normalization functions handle title, authors, and year extraction
- `ground_truth` fixture can load metadata from ZoteroReader
- All code passes ruff check
<!-- END_TASK_4 -->
