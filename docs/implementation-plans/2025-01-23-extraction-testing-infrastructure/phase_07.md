# Phase 7: Optional Manifest Integration

**Goal:** Add manifest support for categories, expected failures, and filtering.

**Codebase verification findings:**
- ✓ pytest markers can be dynamically added via `pytest_collection_modifyitems`
- ✓ JSON parsing available via stdlib `json` module
- ✓ Design specifies manifest as optional enrichment (tests work without it)

---

<!-- START_TASK_1 -->
### Task 1: Create empty manifest file

**Files:**
- Create: `tests/extraction/golden_set_manifest.json`

**Step 1: Create initial manifest with schema documentation**

Create `tests/extraction/golden_set_manifest.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$comment": "Optional manifest for golden set enrichment. Tests work without this file.",
  "documents": {},
  "categories": {
    "academic": "Academic papers with standard formatting",
    "technical": "Technical documentation and reports",
    "historical": "Older documents that may have OCR challenges",
    "multilingual": "Documents with non-English content"
  }
}
```

The manifest structure:
- `documents`: Object mapping citekey to document metadata
- `categories`: Object defining available category names and descriptions

Each document entry can have:
```json
{
  "citekey": {
    "category": "academic",
    "expected_failures": ["title", "authors"],
    "notes": "Optional notes about this document"
  }
}
```

**Step 2: Verify the JSON is valid**

Run: `uv run python -c "import json; json.load(open('tests/extraction/golden_set_manifest.json')); print('Valid JSON')"`
Expected: `Valid JSON`

**Step 3: Commit**

```bash
git add tests/extraction/golden_set_manifest.json
git commit -m "feat(tests): add empty golden set manifest with schema"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add ManifestEntry and manifest loading

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add ManifestEntry dataclass**

Add to `tests/extraction/conftest.py` (near other dataclasses):

```python


@dataclass(frozen=True)
class ManifestEntry:
    """Enrichment data for a single document from the manifest.

    Attributes:
        citekey: Document identifier
        category: Category for filtering (e.g., "academic", "technical")
        expected_failures: Fields expected to fail (for xfail marking)
        notes: Human-readable notes about this document
    """

    citekey: str
    category: str | None = None
    expected_failures: tuple[str, ...] = ()
    notes: str | None = None

    @classmethod
    def from_dict(cls, citekey: str, data: dict) -> "ManifestEntry":
        """Create ManifestEntry from manifest dict entry.

        Args:
            citekey: The document's citation key
            data: Dict from manifest with category, expected_failures, notes

        Returns:
            ManifestEntry instance
        """
        return cls(
            citekey=citekey,
            category=data.get("category"),
            expected_failures=tuple(data.get("expected_failures", [])),
            notes=data.get("notes"),
        )
```

**Step 2: Add manifest loading function**

Add to `tests/extraction/conftest.py`:

```python


MANIFEST_PATH = Path(__file__).parent / "golden_set_manifest.json"


def load_manifest() -> dict[str, ManifestEntry]:
    """Load optional manifest for golden set enrichment.

    Returns empty dict if manifest doesn't exist or is invalid.
    Never raises - manifest is optional enrichment.

    Returns:
        Dict mapping citekey to ManifestEntry
    """
    import json

    if not MANIFEST_PATH.exists():
        return {}

    try:
        with open(MANIFEST_PATH) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    documents = data.get("documents", {})
    return {
        citekey: ManifestEntry.from_dict(citekey, entry)
        for citekey, entry in documents.items()
    }
```

**Step 3: Test manifest loading**

Run: `uv run python -c "
from tests.extraction.conftest import load_manifest, ManifestEntry

manifest = load_manifest()
assert isinstance(manifest, dict)
print(f'Loaded manifest with {len(manifest)} entries')
print('Manifest loading works')
"`
Expected: `Loaded manifest with 0 entries` and `Manifest loading works`

**Step 4: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add ManifestEntry dataclass and manifest loading"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add golden_set_manifest fixture

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add golden_set_manifest fixture**

Add to `tests/extraction/conftest.py`:

```python


@pytest.fixture(scope="session")
def golden_set_manifest() -> dict[str, ManifestEntry]:
    """Load manifest for golden set enrichment.

    Returns empty dict if manifest doesn't exist. Tests should
    handle missing manifest entries gracefully.

    Returns:
        Dict mapping citekey to ManifestEntry
    """
    return load_manifest()
```

**Step 2: Verify fixture is discoverable**

Run: `uv run pytest tests/extraction/ --collect-only --fixtures 2>&1 | grep golden_set_manifest`
Expected: Shows `golden_set_manifest` fixture listed

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add golden_set_manifest fixture"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add category marker hook

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add pytest_collection_modifyitems hook for category markers**

Add to `tests/extraction/conftest.py`:

```python


def pytest_collection_modifyitems(
    config: pytest.Config,  # noqa: ARG001
    items: list[pytest.Item],
) -> None:
    """Add markers based on manifest categories and expected failures.

    For each test item:
    - Adds category marker if document has category in manifest
    - Adds xfail marker if test field is in expected_failures

    This enables filtering by category: pytest -m "academic"
    And proper handling of known failures: expected failures show as xfail.
    """
    manifest = load_manifest()

    for item in items:
        # Extract citekey from test parameters if present
        citekey = None
        if hasattr(item, "callspec") and "citekey" in item.callspec.params:
            citekey = item.callspec.params["citekey"]

        if citekey is None or citekey not in manifest:
            continue

        entry = manifest[citekey]

        # Add category marker if present
        if entry.category:
            item.add_marker(pytest.mark.extraction_category(entry.category))

        # Add xfail marker if this test's field is in expected_failures
        test_name = item.name.lower()
        for field in entry.expected_failures:
            if field in test_name:
                reason = f"Known failure: {field} extraction for {citekey}"
                if entry.notes:
                    reason += f" ({entry.notes})"
                item.add_marker(pytest.mark.xfail(reason=reason))
```

**Step 2: Test that hook doesn't break collection**

Run: `uv run pytest tests/extraction/ --collect-only`
Expected: Collection completes without errors

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add pytest hook for manifest-based markers"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add example manifest entries

**Files:**
- Modify: `tests/extraction/golden_set_manifest.json`

**Step 1: Add sample entries to demonstrate usage**

Update `tests/extraction/golden_set_manifest.json` with example entries:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$comment": "Optional manifest for golden set enrichment. Tests work without this file.",
  "documents": {
    "_example_entry": {
      "category": "academic",
      "expected_failures": [],
      "notes": "This is an example entry. Remove underscore prefix for real entries."
    }
  },
  "categories": {
    "academic": "Academic papers with standard formatting",
    "technical": "Technical documentation and reports",
    "historical": "Older documents that may have OCR challenges",
    "multilingual": "Documents with non-English content",
    "complex": "Documents with complex layouts (multi-column, tables)"
  }
}
```

**Step 2: Verify the JSON is valid**

Run: `uv run python -c "import json; json.load(open('tests/extraction/golden_set_manifest.json')); print('Valid JSON')"`
Expected: `Valid JSON`

**Step 3: Commit**

```bash
git add tests/extraction/golden_set_manifest.json
git commit -m "docs(tests): add example manifest entries with documentation"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Verify Phase 7 completion

**Files:**
- None (verification only)

**Step 1: Verify manifest components are importable**

Run: `uv run python -c "
from tests.extraction.conftest import (
    ManifestEntry,
    load_manifest,
    MANIFEST_PATH,
)
print(f'Manifest path: {MANIFEST_PATH}')
print(f'Manifest exists: {MANIFEST_PATH.exists()}')
print('Manifest components importable')
"`
Expected: Shows path, existence, and `Manifest components importable`

**Step 2: Verify manifest loading works**

Run: `uv run python -c "
from tests.extraction.conftest import load_manifest

manifest = load_manifest()
print(f'Loaded {len(manifest)} manifest entries')

# Test entry parsing
from tests.extraction.conftest import ManifestEntry
entry = ManifestEntry.from_dict('test', {
    'category': 'academic',
    'expected_failures': ['title'],
    'notes': 'Test note'
})
assert entry.category == 'academic'
assert entry.expected_failures == ('title',)
print('Manifest parsing verified')
"`
Expected: Shows loaded entries count and `Manifest parsing verified`

**Step 3: Verify tests still work without real manifest entries**

Run: `uv run pytest tests/extraction/ --collect-only`
Expected: Collection completes (tests work without manifest)

**Step 4: Run ruff to check all code**

Run: `uv run ruff check tests/extraction/`
Expected: No errors

Run: `uv run ruff format tests/extraction/`
Expected: Files formatted

**Step 5: Commit any formatting changes**

```bash
git add tests/extraction/
git commit -m "style: apply ruff formatting to extraction tests" --allow-empty
```

**Phase 7 complete when:**
- `golden_set_manifest.json` exists with schema and example entries
- `ManifestEntry` dataclass parses manifest entries
- `load_manifest()` loads manifest or returns empty dict if missing
- `golden_set_manifest` fixture provides session-scoped access
- `pytest_collection_modifyitems` hook adds category and xfail markers
- Tests work without manifest (empty dict returned)
- All code passes ruff check
<!-- END_TASK_6 -->
