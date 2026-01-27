# CLI Review Workflow Implementation Plan

**Goal:** Implement CLI-based workflow for reviewing and correcting metadata in documents flagged as NEEDS_REVIEW

**Architecture:** Centralized identifier resolution with `@citekey` convention, enhanced list command with pagination, editor-based metadata editing with validation loops

**Tech Stack:** Python, Typer/Rich CLI, SQLite, CSL-JSON validation

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-01-27

---

## Phase 1: Identifier Resolution Infrastructure

**Goal:** Centralized identifier resolution with citekey support and suggestions

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->
<!-- START_TASK_1 -->
### Task 1: Add `get_all_citekeys()` to storage layer

**Files:**
- Modify: `src/local_library/core/storage.py:323` (after `get_document_by_citekey`)

**Step 1: Write the failing test**

Create test in `tests/unit/test_storage.py`:

```python
def test_get_all_citekeys_returns_non_null_citekeys(db_conn: sqlite3.Connection) -> None:
    """get_all_citekeys should return only documents with citekeys."""
    from local_library.core.storage import create_document, get_all_citekeys

    # Create documents with and without citekeys
    create_document(
        db_conn,
        original_path="/path/doc1.pdf",
        content_hash="hash1",
        storage_path="/storage/doc1.pdf",
        citekey="Smith2023",
    )
    create_document(
        db_conn,
        original_path="/path/doc2.pdf",
        content_hash="hash2",
        storage_path="/storage/doc2.pdf",
        citekey=None,  # No citekey
    )
    create_document(
        db_conn,
        original_path="/path/doc3.pdf",
        content_hash="hash3",
        storage_path="/storage/doc3.pdf",
        citekey="Jones2024",
    )

    citekeys = get_all_citekeys(db_conn)

    assert sorted(citekeys) == ["Jones2024", "Smith2023"]


def test_get_all_citekeys_empty_library(db_conn: sqlite3.Connection) -> None:
    """get_all_citekeys should return empty list for empty library."""
    from local_library.core.storage import get_all_citekeys

    citekeys = get_all_citekeys(db_conn)

    assert citekeys == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_storage.py::test_get_all_citekeys_returns_non_null_citekeys -v`
Expected: FAIL with `ImportError: cannot import name 'get_all_citekeys'`

**Step 3: Write minimal implementation**

Add to `src/local_library/core/storage.py` after `get_document_by_citekey()` (around line 323):

```python
def get_all_citekeys(conn: sqlite3.Connection) -> list[str]:
    """Get all non-null citekeys in the library.

    Args:
        conn: Database connection

    Returns:
        List of citekeys (excludes documents without citekeys)
    """
    cursor = conn.execute(
        "SELECT citekey FROM documents WHERE citekey IS NOT NULL ORDER BY citekey"
    )
    return [row[0] for row in cursor.fetchall()]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storage.py::test_get_all_citekeys_returns_non_null_citekeys tests/unit/test_storage.py::test_get_all_citekeys_empty_library -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/core/storage.py tests/unit/test_storage.py
git commit -m "feat(storage): add get_all_citekeys for citekey suggestions

Supports the CLI review workflow by enabling citekey lookup with
suggestions on miss."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create `cli/utils.py` with Levenshtein distance helper

**Files:**
- Create: `src/local_library/cli/utils.py`

**Step 1: Write the failing test**

Create `tests/unit/test_cli_utils.py`:

```python
"""Unit tests for CLI utilities."""

import pytest

from local_library.cli.utils import levenshtein_distance


class TestLevenshteinDistance:
    """Tests for Levenshtein distance calculation."""

    def test_identical_strings(self) -> None:
        """Identical strings have distance 0."""
        assert levenshtein_distance("test", "test") == 0

    def test_empty_strings(self) -> None:
        """Empty string comparisons."""
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("abc", "") == 3
        assert levenshtein_distance("", "abc") == 3

    def test_single_insertion(self) -> None:
        """Single character insertion."""
        assert levenshtein_distance("test", "tests") == 1

    def test_single_deletion(self) -> None:
        """Single character deletion."""
        assert levenshtein_distance("tests", "test") == 1

    def test_single_substitution(self) -> None:
        """Single character substitution."""
        assert levenshtein_distance("test", "tent") == 1

    def test_multiple_edits(self) -> None:
        """Multiple edits needed."""
        assert levenshtein_distance("kitten", "sitting") == 3

    def test_case_sensitive(self) -> None:
        """Distance is case-sensitive."""
        assert levenshtein_distance("Test", "test") == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_utils.py::TestLevenshteinDistance -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'local_library.cli.utils'`

**Step 3: Write minimal implementation**

Create `src/local_library/cli/utils.py`:

```python
"""CLI utility functions."""

# pattern: Functional Core


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein (edit) distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Minimum number of single-character edits (insertions, deletions,
        substitutions) to transform s1 into s2
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost is 0 if characters match, 1 otherwise
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_utils.py::TestLevenshteinDistance -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/utils.py tests/unit/test_cli_utils.py
git commit -m "feat(cli): add Levenshtein distance utility

Pure function for calculating edit distance, used for fuzzy matching
suggestions when citekey lookup fails."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add `suggest_citekeys()` function

**Files:**
- Modify: `src/local_library/cli/utils.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cli_utils.py`:

```python
from local_library.cli.utils import suggest_citekeys


class TestSuggestCitekeys:
    """Tests for citekey suggestion generation."""

    def test_prefix_match_prioritized(self) -> None:
        """Prefix matches should appear first."""
        all_citekeys = ["Smith2023", "Smith2024", "Jones2023", "Smithson2023"]
        suggestions = suggest_citekeys("Smith", all_citekeys, max_suggestions=3)

        # Prefix matches first
        assert suggestions[0] in ["Smith2023", "Smith2024"]
        assert suggestions[1] in ["Smith2023", "Smith2024"]

    def test_levenshtein_fallback(self) -> None:
        """When no prefix match, use Levenshtein distance."""
        all_citekeys = ["Smith2023", "Jones2023", "Brown2023"]
        suggestions = suggest_citekeys("Smyth2023", all_citekeys, max_suggestions=3)

        # Smith2023 should be suggested (distance 1 from Smyth2023)
        assert "Smith2023" in suggestions

    def test_max_distance_respected(self) -> None:
        """Suggestions beyond max_distance should be excluded."""
        all_citekeys = ["AAAA", "BBBB", "CCCC"]
        suggestions = suggest_citekeys("ZZZZ", all_citekeys, max_suggestions=3, max_distance=3)

        # All have distance 4, should return empty
        assert suggestions == []

    def test_empty_citekeys(self) -> None:
        """Empty citekey list returns empty suggestions."""
        suggestions = suggest_citekeys("Smith", [], max_suggestions=3)
        assert suggestions == []

    def test_max_suggestions_limit(self) -> None:
        """Should not return more than max_suggestions."""
        all_citekeys = [f"Smith202{i}" for i in range(10)]
        suggestions = suggest_citekeys("Smith", all_citekeys, max_suggestions=3)

        assert len(suggestions) <= 3
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_utils.py::TestSuggestCitekeys -v`
Expected: FAIL with `ImportError: cannot import name 'suggest_citekeys'`

**Step 3: Write minimal implementation**

Add to `src/local_library/cli/utils.py`:

```python
def suggest_citekeys(
    query: str,
    all_citekeys: list[str],
    max_suggestions: int = 3,
    max_distance: int = 3,
) -> list[str]:
    """Generate citekey suggestions for a failed lookup.

    Prioritizes prefix matches, then falls back to Levenshtein distance.

    Args:
        query: The citekey that wasn't found (without @ prefix)
        all_citekeys: All available citekeys in the library
        max_suggestions: Maximum number of suggestions to return
        max_distance: Maximum Levenshtein distance for fuzzy matches

    Returns:
        List of suggested citekeys, prefix matches first
    """
    if not all_citekeys:
        return []

    # First: prefix matches
    prefix_matches = [ck for ck in all_citekeys if ck.startswith(query)]

    if len(prefix_matches) >= max_suggestions:
        return prefix_matches[:max_suggestions]

    # Second: Levenshtein distance for remaining slots
    remaining_slots = max_suggestions - len(prefix_matches)
    non_prefix = [ck for ck in all_citekeys if ck not in prefix_matches]

    # Calculate distances and filter
    with_distances = [
        (ck, levenshtein_distance(query, ck))
        for ck in non_prefix
    ]
    within_threshold = [
        (ck, dist) for ck, dist in with_distances if dist <= max_distance
    ]
    within_threshold.sort(key=lambda x: x[1])

    fuzzy_matches = [ck for ck, _ in within_threshold[:remaining_slots]]

    return prefix_matches + fuzzy_matches
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_utils.py::TestSuggestCitekeys -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/utils.py tests/unit/test_cli_utils.py
git commit -m "feat(cli): add suggest_citekeys for fuzzy matching

Prioritizes prefix matches over Levenshtein distance for better UX
when user makes typos in citekey lookups."
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add `resolve_identifier()` function and Library methods

**Files:**
- Modify: `src/local_library/cli/utils.py`
- Modify: `src/local_library/core/library.py:510` (after `get()` method)

**Step 1: Write the failing test**

Add to `tests/unit/test_cli_utils.py`:

```python
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from local_library.core import ErrorCode, LookupError
from local_library.core.models import Document, DocumentStatus
from local_library.cli.utils import resolve_identifier


def _make_mock_document(
    doc_id: str = "12345678-1234-1234-1234-123456789abc",
    citekey: str | None = "Smith2023",
) -> MagicMock:
    """Create a mock Document for testing."""
    mock = MagicMock(spec=Document)
    mock.id = UUID(doc_id)
    mock.citekey = citekey
    mock.status = DocumentStatus.READY
    return mock


class TestResolveIdentifier:
    """Tests for identifier resolution."""

    def test_uuid_lookup(self) -> None:
        """UUID without @ prefix uses Library.get()."""
        mock_lib = MagicMock()
        mock_doc = _make_mock_document()
        mock_lib.get.return_value = mock_doc

        result = resolve_identifier("12345678", mock_lib)

        assert result == mock_doc
        mock_lib.get.assert_called_once_with("12345678")

    def test_citekey_lookup_with_at_prefix(self) -> None:
        """@citekey syntax uses citekey lookup."""
        mock_lib = MagicMock()
        mock_doc = _make_mock_document()
        mock_lib.get_by_citekey.return_value = mock_doc

        result = resolve_identifier("@Smith2023", mock_lib)

        assert result == mock_doc
        mock_lib.get_by_citekey.assert_called_once_with("Smith2023")

    def test_citekey_not_found_with_suggestions(self) -> None:
        """Citekey miss should raise LookupError with suggestions."""
        mock_lib = MagicMock()
        mock_lib.get_by_citekey.return_value = None
        mock_lib.get_all_citekeys.return_value = ["Smith2023", "Smith2024", "Jones2023"]

        with pytest.raises(LookupError) as exc_info:
            resolve_identifier("@Smth2023", mock_lib)

        assert exc_info.value.code == ErrorCode.NOT_FOUND
        assert "Smth2023" in exc_info.value.message
        # Should have suggestions in details
        assert "suggestions" in exc_info.value.details

    def test_citekey_not_found_no_suggestions(self) -> None:
        """Citekey miss with no close matches has empty suggestions."""
        mock_lib = MagicMock()
        mock_lib.get_by_citekey.return_value = None
        mock_lib.get_all_citekeys.return_value = ["AAAA", "BBBB"]

        with pytest.raises(LookupError) as exc_info:
            resolve_identifier("@ZZZZCompletely2023Different", mock_lib)

        assert exc_info.value.code == ErrorCode.NOT_FOUND
        # No close matches, suggestions may be empty
        assert exc_info.value.details.get("suggestions", []) == []

    def test_uuid_not_found_passthrough(self) -> None:
        """UUID miss should pass through Library.get() exception."""
        mock_lib = MagicMock()
        mock_lib.get.side_effect = LookupError("document not found", ErrorCode.NOT_FOUND)

        with pytest.raises(LookupError) as exc_info:
            resolve_identifier("nonexistent", mock_lib)

        assert exc_info.value.code == ErrorCode.NOT_FOUND
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_utils.py::TestResolveIdentifier -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_identifier'`

**Step 3a: Add Library methods (prerequisite)**

Add imports to `src/local_library/core/library.py` (update the existing import from storage):

```python
from local_library.core.storage import (
    # ... existing imports ...
    get_document_by_citekey,
    get_all_citekeys,
)
```

Add methods after `get()` method (around line 510):

```python
def get_by_citekey(self, citekey: str) -> Document | None:
    """Get a document by citekey.

    Args:
        citekey: Citation key to look up

    Returns:
        Document if found, None otherwise
    """
    return get_document_by_citekey(self._conn, citekey)

def get_all_citekeys(self) -> list[str]:
    """Get all citekeys in the library.

    Returns:
        List of all non-null citekeys
    """
    return get_all_citekeys(self._conn)
```

**Step 3b: Add resolve_identifier to cli/utils.py**

Update pattern comment at top of `src/local_library/cli/utils.py`:

```python
"""CLI utility functions."""

# pattern: Mixed (Functional Core utilities + Imperative Shell resolve_identifier)

from typing import TYPE_CHECKING, Protocol

from local_library.core import ErrorCode, LookupError
from local_library.core.models import Document

if TYPE_CHECKING:
    from local_library.core import Library


class LibraryProtocol(Protocol):
    """Protocol for Library methods used by resolve_identifier."""

    def get(self, doc_id: str) -> Document: ...
    def get_by_citekey(self, citekey: str) -> Document | None: ...
    def get_all_citekeys(self) -> list[str]: ...
```

Add the function after `suggest_citekeys()`:

```python
def resolve_identifier(identifier: str, library: LibraryProtocol) -> Document:
    """Resolve a document identifier (UUID or @citekey) to a Document.

    Args:
        identifier: Either a UUID (full or partial) or @citekey
        library: Library instance for lookups

    Returns:
        The resolved Document

    Raises:
        LookupError: If document not found, with suggestions for citekey misses
    """
    if identifier.startswith("@"):
        # Citekey lookup
        citekey = identifier[1:]  # Strip @ prefix
        doc = library.get_by_citekey(citekey)

        if doc is not None:
            return doc

        # Not found - generate suggestions
        all_citekeys = library.get_all_citekeys()
        suggestions = suggest_citekeys(citekey, all_citekeys)

        raise LookupError(
            f"citekey not found: {citekey}",
            ErrorCode.NOT_FOUND,
            details={"citekey": citekey, "suggestions": suggestions},
        )

    # UUID lookup - delegate to Library.get() which handles partial matching
    return library.get(identifier)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_utils.py::TestResolveIdentifier -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/utils.py src/local_library/core/library.py tests/unit/test_cli_utils.py
git commit -m "feat(cli): add resolve_identifier for unified lookup

Centralizes UUID vs @citekey resolution logic. Generates suggestions
on citekey miss using prefix matching and Levenshtein distance.

Also exposes get_by_citekey and get_all_citekeys via Library class."
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->

---

**Phase complete when:** `resolve_identifier()` correctly routes UUID vs `@citekey`, returns Document or raises LookupError with suggestions.
