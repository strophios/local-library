# Phase 2: Library JSON Parsing

**Goal:** Load and query CSL-JSON metadata from Better BibTeX export.

**Codebase verification findings:**
- JSON parsing is standard Python (json module)
- CSL-JSON structure: array of objects, each with `id` field matching citekey
- Better BibTeX exports include `citation-key` field in each item
- Error handling pattern established in Phase 1 (ZoteroError with error codes)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add LibraryJsonParser Class

**Files:**
- Modify: `src/local_library/ingestion/zotero.py`

**Step 1: Add imports for JSON parsing**

Update the imports at the top of `src/local_library/ingestion/zotero.py`:

```python
"""Zotero library data access.

Provides read-only access to Zotero library data by coordinating:
- CSL-JSON metadata from Better BibTeX export (library.json)
- Citekey-to-itemID mapping from Better BibTeX SQLite database
- Attachment paths from Zotero's main SQLite database
"""

# pattern: Mixed (unavoidable)
# Reason: JSON file I/O cannot be separated from parsing logic without
# introducing unnecessary complexity. The class encapsulates file access.

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
import json

from local_library.core.errors import ErrorCode, ZoteroError
```

**Step 2: Add the LibraryJsonParser class after ZoteroItem**

Add the following class after the ZoteroItem dataclass:

```python
class LibraryJsonParser:
    """Parses and indexes CSL-JSON metadata from Better BibTeX export.

    Loads library.json (exported by Better BibTeX) and builds an index
    for efficient citekey-based lookup. Metadata is cached in memory
    after first load.

    The expected format is a JSON array of CSL-JSON objects, where each
    object has a `citation-key` field added by Better BibTeX.
    """

    def __init__(self, library_json_path: Path) -> None:
        """Initialize parser with path to library.json.

        Args:
            library_json_path: Path to Better BibTeX CSL-JSON export

        Raises:
            ZoteroError: If file doesn't exist (ZOTERO_LIBRARY_JSON_NOT_FOUND)
        """
        self._path = library_json_path
        self._index: dict[str, dict[str, Any]] | None = None

        if not self._path.exists():
            raise ZoteroError(
                message=f"library.json not found: {library_json_path}",
                code=ErrorCode.ZOTERO_LIBRARY_JSON_NOT_FOUND,
                details={"path": str(library_json_path)},
            )

    def _load(self) -> None:
        """Load and index the library JSON file.

        Builds a dictionary mapping citekey -> CSL-JSON metadata.

        Raises:
            ZoteroError: If JSON parsing fails (ZOTERO_LIBRARY_JSON_PARSE_ERROR)
        """
        try:
            with open(self._path, encoding="utf-8") as f:
                items = json.load(f)
        except json.JSONDecodeError as e:
            raise ZoteroError(
                message=f"failed to parse library.json: {e}",
                code=ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR,
                details={"path": str(self._path), "error": str(e)},
            ) from e
        except OSError as e:
            raise ZoteroError(
                message=f"failed to read library.json: {e}",
                code=ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR,
                details={"path": str(self._path), "error": str(e)},
            ) from e

        if not isinstance(items, list):
            raise ZoteroError(
                message="library.json must contain a JSON array",
                code=ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR,
                details={"path": str(self._path), "type": type(items).__name__},
            )

        self._index = {}
        for item in items:
            # Better BibTeX adds citation-key to each item
            citekey = item.get("citation-key") or item.get("id")
            if citekey:
                self._index[citekey] = item

    def _ensure_loaded(self) -> dict[str, dict[str, Any]]:
        """Ensure index is loaded, loading if necessary."""
        if self._index is None:
            self._load()
        assert self._index is not None  # for type checker
        return self._index

    def get_metadata(self, citekey: str) -> dict[str, Any] | None:
        """Get CSL-JSON metadata for a citekey.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            CSL-JSON metadata dictionary, or None if not found
        """
        index = self._ensure_loaded()
        return index.get(citekey)

    def has_citekey(self, citekey: str) -> bool:
        """Check if a citekey exists in the library.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            True if citekey exists, False otherwise
        """
        index = self._ensure_loaded()
        return citekey in index

    def list_citekeys(self) -> Iterator[str]:
        """Iterate over all citekeys in the library.

        Yields:
            Citation keys in arbitrary order
        """
        index = self._ensure_loaded()
        yield from index.keys()

    def refresh(self) -> None:
        """Clear cache and reload from disk on next access.

        Call this after Better BibTeX has re-exported the library.
        """
        self._index = None
```

**Step 3: Verify the file is importable**

Run: `uv run python -c "from local_library.ingestion.zotero import LibraryJsonParser; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add src/local_library/ingestion/zotero.py
git commit -m "$(cat <<'EOF'
feat(zotero): add LibraryJsonParser for CSL-JSON metadata access

Parses Better BibTeX CSL-JSON export and builds citekey index.
Supports lazy loading, citekey lookup, existence check, iteration,
and cache refresh.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write Unit Tests for LibraryJsonParser - Happy Path

**Files:**
- Modify: `tests/unit/test_zotero.py`

**Step 1: Add imports and fixtures**

Add the following imports at the top of `tests/unit/test_zotero.py`:

```python
"""Unit tests for Zotero data models and parsers."""

import json
from pathlib import Path

import pytest

from local_library.core.errors import ErrorCode, ZoteroError
from local_library.ingestion.zotero import (
    LibraryJsonParser,
    ZoteroAttachment,
    ZoteroItem,
)
```

**Step 2: Add LibraryJsonParser test fixtures and happy path tests**

Add the following test class after TestZoteroItem:

```python
class TestLibraryJsonParser:
    """Tests for LibraryJsonParser class."""

    @pytest.fixture
    def sample_library_json(self) -> list[dict]:
        """Provide sample CSL-JSON library data."""
        return [
            {
                "id": "smith2023",
                "citation-key": "smith2023",
                "type": "article-journal",
                "title": "A Sample Paper",
                "author": [{"family": "Smith", "given": "John"}],
                "issued": {"date-parts": [[2023]]},
            },
            {
                "id": "jones2022",
                "citation-key": "jones2022",
                "type": "book",
                "title": "A Sample Book",
                "author": [{"family": "Jones", "given": "Jane"}],
                "issued": {"date-parts": [[2022]]},
            },
        ]

    @pytest.fixture
    def library_json_file(
        self, temp_dir: Path, sample_library_json: list[dict]
    ) -> Path:
        """Create a temporary library.json file."""
        path = temp_dir / "library.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sample_library_json, f)
        return path

    def test_get_metadata_returns_csl_json(
        self, library_json_file: Path, sample_library_json: list[dict]
    ) -> None:
        """get_metadata should return CSL-JSON for valid citekey."""
        parser = LibraryJsonParser(library_json_file)

        metadata = parser.get_metadata("smith2023")

        assert metadata is not None
        assert metadata["title"] == "A Sample Paper"
        assert metadata["type"] == "article-journal"

    def test_get_metadata_returns_none_for_unknown(
        self, library_json_file: Path
    ) -> None:
        """get_metadata should return None for unknown citekey."""
        parser = LibraryJsonParser(library_json_file)

        metadata = parser.get_metadata("nonexistent")

        assert metadata is None

    def test_has_citekey_returns_true_for_existing(
        self, library_json_file: Path
    ) -> None:
        """has_citekey should return True for existing citekey."""
        parser = LibraryJsonParser(library_json_file)

        assert parser.has_citekey("smith2023") is True
        assert parser.has_citekey("jones2022") is True

    def test_has_citekey_returns_false_for_missing(
        self, library_json_file: Path
    ) -> None:
        """has_citekey should return False for missing citekey."""
        parser = LibraryJsonParser(library_json_file)

        assert parser.has_citekey("nonexistent") is False

    def test_list_citekeys_yields_all_keys(
        self, library_json_file: Path
    ) -> None:
        """list_citekeys should yield all citekeys."""
        parser = LibraryJsonParser(library_json_file)

        keys = set(parser.list_citekeys())

        assert keys == {"smith2023", "jones2022"}

    def test_lazy_loading(self, library_json_file: Path) -> None:
        """Parser should not load until first access."""
        parser = LibraryJsonParser(library_json_file)

        # Not loaded yet
        assert parser._index is None

        # Triggers load
        _ = parser.get_metadata("smith2023")

        # Now loaded
        assert parser._index is not None

    def test_refresh_clears_cache(self, library_json_file: Path) -> None:
        """refresh should clear the cache for reload on next access."""
        parser = LibraryJsonParser(library_json_file)

        # Load data
        _ = parser.get_metadata("smith2023")
        assert parser._index is not None

        # Refresh
        parser.refresh()
        assert parser._index is None

        # Access triggers reload
        _ = parser.get_metadata("smith2023")
        assert parser._index is not None
```

**Step 3: Run the tests**

Run: `uv run pytest tests/unit/test_zotero.py::TestLibraryJsonParser -v`
Expected: All 7 tests pass

**Step 4: Commit**

```bash
git add tests/unit/test_zotero.py
git commit -m "$(cat <<'EOF'
test(zotero): add unit tests for LibraryJsonParser happy path

Tests get_metadata, has_citekey, list_citekeys, lazy loading,
and cache refresh functionality.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write Unit Tests for LibraryJsonParser - Error Cases

**Files:**
- Modify: `tests/unit/test_zotero.py`

**Step 1: Add error case tests to TestLibraryJsonParser class**

Add the following test methods to the TestLibraryJsonParser class:

```python
    def test_raises_error_for_missing_file(self, temp_dir: Path) -> None:
        """Parser should raise error if library.json doesn't exist."""
        missing_path = temp_dir / "nonexistent.json"

        with pytest.raises(ZoteroError) as exc_info:
            LibraryJsonParser(missing_path)

        assert exc_info.value.code == ErrorCode.ZOTERO_LIBRARY_JSON_NOT_FOUND
        assert "nonexistent.json" in str(exc_info.value)

    def test_raises_error_for_invalid_json(self, temp_dir: Path) -> None:
        """Parser should raise error for malformed JSON."""
        bad_json = temp_dir / "bad.json"
        bad_json.write_text("{ not valid json }", encoding="utf-8")

        parser = LibraryJsonParser(bad_json)

        with pytest.raises(ZoteroError) as exc_info:
            parser.get_metadata("anything")

        assert exc_info.value.code == ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR

    def test_raises_error_for_non_array_json(self, temp_dir: Path) -> None:
        """Parser should raise error if JSON is not an array."""
        object_json = temp_dir / "object.json"
        object_json.write_text('{"not": "an array"}', encoding="utf-8")

        parser = LibraryJsonParser(object_json)

        with pytest.raises(ZoteroError) as exc_info:
            parser.get_metadata("anything")

        assert exc_info.value.code == ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR
        assert "array" in str(exc_info.value).lower()

    def test_handles_items_without_citation_key(self, temp_dir: Path) -> None:
        """Parser should use 'id' field if 'citation-key' is missing."""
        items = [
            {
                "id": "fallback-id",
                "type": "article",
                "title": "No Citation Key",
            }
        ]
        json_file = temp_dir / "library.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(items, f)

        parser = LibraryJsonParser(json_file)

        # Should find by 'id' field
        metadata = parser.get_metadata("fallback-id")
        assert metadata is not None
        assert metadata["title"] == "No Citation Key"

    def test_handles_empty_library(self, temp_dir: Path) -> None:
        """Parser should handle empty library array."""
        empty_json = temp_dir / "empty.json"
        empty_json.write_text("[]", encoding="utf-8")

        parser = LibraryJsonParser(empty_json)

        assert parser.has_citekey("anything") is False
        assert list(parser.list_citekeys()) == []
```

**Step 2: Run all LibraryJsonParser tests**

Run: `uv run pytest tests/unit/test_zotero.py::TestLibraryJsonParser -v`
Expected: All 12 tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_zotero.py
git commit -m "$(cat <<'EOF'
test(zotero): add error case tests for LibraryJsonParser

Tests missing file, invalid JSON, non-array JSON, missing citation-key
fallback to id, and empty library handling.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

**Phase 2 Done When:**
- LibraryJsonParser class created with lazy loading
- get_metadata, has_citekey, list_citekeys, refresh methods work
- Error cases handled with appropriate ZoteroError codes
- All tests pass: `uv run pytest tests/unit/test_zotero.py::TestLibraryJsonParser -v`
