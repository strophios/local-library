# Phase 6: Public API Integration

**Goal:** Wire everything together into the public `ZoteroReader` interface.

**Codebase verification findings:**
- All internal components from Phases 1-5 are available:
  - `ZoteroAttachment`, `ZoteroItem` dataclasses
  - `LibraryJsonParser` for CSL-JSON metadata
  - `DatabaseManager` for SQLite access with copy-if-locked
  - `BbtKeyMapper` for citekey resolution
  - `AttachmentResolver` for attachment path resolution
- Context manager pattern used elsewhere in codebase (Library class)

**Design note:** ZoteroReader orchestrates the internal components to provide:
- `get_item(citekey)` - Returns complete ZoteroItem with metadata + attachments
- `list_citekeys()` - Iterates all citekeys from library.json
- `has_item(citekey)` - Existence check
- Context manager protocol for resource cleanup

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->

<!-- START_TASK_1 -->
### Task 1: Add ZoteroReader Class

**Files:**
- Modify: `src/local_library/ingestion/zotero.py`

**Step 1: Add the ZoteroReader class at the end of the file**

Add the following class after AttachmentResolver in `src/local_library/ingestion/zotero.py`:

```python
class ZoteroReader:
    """Read-only access to Zotero library data.

    Coordinates three data sources to provide complete item data:
    - library.json (CSL-JSON export from Better BibTeX) for metadata
    - better-bibtex.sqlite for citekey-to-itemID mapping
    - zotero.sqlite for attachment paths

    Usage:
        with ZoteroReader(zotero_dir) as reader:
            for citekey in reader.list_citekeys():
                item = reader.get_item(citekey)
                print(f"{citekey}: {item.csl_json.get('title')}")
                for att in item.pdf_attachments():
                    print(f"  - {att.path}")

    The reader serves as a data source for Library.add() rather than
    implementing ContentAcquirer. Future batch import will iterate
    list_citekeys() and call Library.add() for each.
    """

    def __init__(
        self,
        zotero_dir: Path,
        library_json_path: Path | None = None,
        temp_dir: Path | None = None,
    ) -> None:
        """Initialize Zotero reader.

        Args:
            zotero_dir: Path to Zotero profile directory containing databases
                        and storage/ folder
            library_json_path: Path to Better BibTeX CSL-JSON export.
                              Defaults to zotero_dir/library.json
            temp_dir: Directory for temporary database copies when locked.
                     Uses system temp if None.

        Raises:
            ZoteroError: If zotero_dir doesn't exist (ZOTERO_DIR_NOT_FOUND)
            ZoteroError: If library.json doesn't exist (ZOTERO_LIBRARY_JSON_NOT_FOUND)
        """
        self._zotero_dir = zotero_dir

        # Determine library.json path
        if library_json_path is None:
            library_json_path = zotero_dir / "library.json"
        self._library_json_path = library_json_path

        # Initialize components
        self._json_parser = LibraryJsonParser(library_json_path)
        self._db_manager = DatabaseManager(zotero_dir, temp_dir=temp_dir)
        self._key_mapper = BbtKeyMapper(self._db_manager)
        self._attachment_resolver = AttachmentResolver(self._db_manager, zotero_dir)

    def get_item(self, citekey: str) -> ZoteroItem:
        """Get complete item data for a citekey.

        Combines CSL-JSON metadata with resolved attachment paths.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            ZoteroItem with metadata and attachments

        Raises:
            ZoteroError: If citekey not found in library.json (ZOTERO_ITEM_NOT_FOUND)
            ZoteroError: If citekey not in BBT database (ZOTERO_CITEKEY_NOT_IN_BBT)
        """
        # Get metadata from library.json
        metadata = self._json_parser.get_metadata(citekey)
        if metadata is None:
            raise ZoteroError(
                message=f"item not found in library.json: {citekey}",
                code=ErrorCode.ZOTERO_ITEM_NOT_FOUND,
                details={"citekey": citekey, "source": "library.json"},
            )

        # Resolve citekey to Zotero IDs
        item_id, item_key = self._key_mapper.lookup(citekey)

        # Get attachments
        attachments = self._attachment_resolver.get_attachments(item_id)

        return ZoteroItem(
            citekey=citekey,
            csl_json=metadata,
            attachments=attachments,
            zotero_key=item_key,
            item_id=item_id,
        )

    def list_citekeys(self) -> Iterator[str]:
        """Iterate over all citekeys in the library.

        Yields citekeys from library.json. Note that some citekeys
        may not be in the BBT database if the export is newer than
        the database.

        Yields:
            Citation keys in arbitrary order
        """
        return self._json_parser.list_citekeys()

    def has_item(self, citekey: str) -> bool:
        """Check if a citekey exists in the library.

        Checks library.json only (fast). Does not verify BBT database
        or attachments.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            True if citekey exists in library.json
        """
        return self._json_parser.has_citekey(citekey)

    def refresh(self) -> None:
        """Reload library.json from disk.

        Call this after Better BibTeX has re-exported the library.
        Database connections are not affected (they reflect current
        database state on each query).
        """
        self._json_parser.refresh()

    def close(self) -> None:
        """Close all database connections and clean up resources."""
        self._db_manager.close()

    def __enter__(self) -> "ZoteroReader":
        """Enter context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit context manager, closing resources."""
        self.close()
```

**Step 2: Update the module's `__all__` export list (if using one)**

At the top of the file after imports, add or update:

```python
__all__ = [
    "ZoteroAttachment",
    "ZoteroItem",
    "ZoteroReader",
]
```

**Step 3: Verify the file is importable**

Run: `uv run python -c "from local_library.ingestion.zotero import ZoteroReader; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add src/local_library/ingestion/zotero.py
git commit -m "$(cat <<'EOF'
feat(zotero): add ZoteroReader public API class

Orchestrates LibraryJsonParser, DatabaseManager, BbtKeyMapper, and
AttachmentResolver to provide:
- get_item(citekey) -> ZoteroItem with metadata + attachments
- list_citekeys() -> iterate all citekeys
- has_item(citekey) -> existence check
- Context manager protocol for resource cleanup

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write Unit Tests for ZoteroReader - Happy Path

**Files:**
- Modify: `tests/unit/test_zotero.py`

**Step 1: Update imports**

Update the imports at the top of `tests/unit/test_zotero.py`:

```python
"""Unit tests for Zotero data models, parsers, and database access."""

import json
import sqlite3
from pathlib import Path

import pytest

from local_library.core.errors import ErrorCode, ZoteroError
from local_library.ingestion.zotero import (
    AttachmentResolver,
    BbtKeyMapper,
    DatabaseManager,
    LibraryJsonParser,
    ZoteroAttachment,
    ZoteroItem,
    ZoteroReader,
)
```

**Step 2: Add ZoteroReader test class with fixtures**

Add the following test class after TestAttachmentResolver:

```python
class TestZoteroReader:
    """Tests for ZoteroReader public API."""

    @pytest.fixture
    def complete_zotero_dir(self, temp_dir: Path) -> Path:
        """Create a complete mock Zotero directory with all required data."""
        zotero_path = temp_dir / "Zotero"
        zotero_path.mkdir()

        # Create library.json (CSL-JSON export)
        library_json = [
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
            },
        ]
        with open(zotero_path / "library.json", "w") as f:
            json.dump(library_json, f)

        # Create zotero.sqlite
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
        conn.execute("INSERT INTO items VALUES (100, 'SMITH001')")  # Parent
        conn.execute("INSERT INTO items VALUES (101, 'ATTACH01')")  # Attachment
        conn.execute("INSERT INTO items VALUES (200, 'JONES001')")  # Parent (no att)
        conn.execute("""
            CREATE TABLE itemAttachments (
                itemID INTEGER, sourceItemID INTEGER,
                linkMode INTEGER, contentType TEXT, path TEXT
            )
        """)
        conn.execute("""
            INSERT INTO itemAttachments VALUES
            (101, 100, 0, 'application/pdf', 'storage:paper.pdf')
        """)
        conn.commit()
        conn.close()

        # Create better-bibtex.sqlite
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("CREATE TABLE citationkey (itemID INTEGER, citationKey TEXT)")
        conn.execute("INSERT INTO citationkey VALUES (100, 'smith2023')")
        conn.execute("INSERT INTO citationkey VALUES (200, 'jones2022')")
        conn.commit()
        conn.close()

        # Create storage with attachment file
        storage_dir = zotero_path / "storage" / "ATTACH01"
        storage_dir.mkdir(parents=True)
        (storage_dir / "paper.pdf").write_bytes(b"%PDF-1.4 test content")

        return zotero_path

    def test_get_item_returns_complete_item(
        self, complete_zotero_dir: Path
    ) -> None:
        """get_item should return ZoteroItem with metadata and attachments."""
        with ZoteroReader(complete_zotero_dir) as reader:
            item = reader.get_item("smith2023")

        assert item.citekey == "smith2023"
        assert item.csl_json["title"] == "A Sample Paper"
        assert item.zotero_key == "SMITH001"
        assert item.item_id == 100
        assert len(item.attachments) == 1
        assert item.attachments[0].content_type == "application/pdf"

    def test_get_item_without_attachments(
        self, complete_zotero_dir: Path
    ) -> None:
        """get_item should work for items without attachments."""
        with ZoteroReader(complete_zotero_dir) as reader:
            item = reader.get_item("jones2022")

        assert item.citekey == "jones2022"
        assert item.csl_json["title"] == "A Sample Book"
        assert len(item.attachments) == 0

    def test_list_citekeys_returns_all(
        self, complete_zotero_dir: Path
    ) -> None:
        """list_citekeys should yield all citekeys from library.json."""
        with ZoteroReader(complete_zotero_dir) as reader:
            keys = set(reader.list_citekeys())

        assert keys == {"smith2023", "jones2022"}

    def test_has_item_returns_true_for_existing(
        self, complete_zotero_dir: Path
    ) -> None:
        """has_item should return True for existing citekeys."""
        with ZoteroReader(complete_zotero_dir) as reader:
            assert reader.has_item("smith2023") is True
            assert reader.has_item("jones2022") is True

    def test_has_item_returns_false_for_missing(
        self, complete_zotero_dir: Path
    ) -> None:
        """has_item should return False for missing citekeys."""
        with ZoteroReader(complete_zotero_dir) as reader:
            assert reader.has_item("nonexistent") is False

    def test_context_manager_cleanup(
        self, complete_zotero_dir: Path
    ) -> None:
        """Context manager should close connections on exit."""
        reader = ZoteroReader(complete_zotero_dir)
        reader.__enter__()

        # Access something to open connections
        _ = reader.get_item("smith2023")
        assert len(reader._db_manager._connections) > 0

        reader.__exit__(None, None, None)

        # Connections should be closed
        assert len(reader._db_manager._connections) == 0
```

**Step 3: Run the tests**

Run: `uv run pytest tests/unit/test_zotero.py::TestZoteroReader -v`
Expected: All 6 tests pass

**Step 4: Commit**

```bash
git add tests/unit/test_zotero.py
git commit -m "$(cat <<'EOF'
test(zotero): add unit tests for ZoteroReader happy path

Tests get_item with/without attachments, list_citekeys, has_item,
and context manager cleanup.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write Unit Tests for ZoteroReader - Error Cases

**Files:**
- Modify: `tests/unit/test_zotero.py`

**Step 1: Add error case tests to TestZoteroReader class**

Add the following test methods to the TestZoteroReader class:

```python
    def test_raises_for_missing_zotero_dir(self, temp_dir: Path) -> None:
        """ZoteroReader should raise error if Zotero directory missing."""
        missing_dir = temp_dir / "nonexistent"

        with pytest.raises(ZoteroError) as exc_info:
            ZoteroReader(missing_dir)

        assert exc_info.value.code == ErrorCode.ZOTERO_DIR_NOT_FOUND

    def test_raises_for_missing_library_json(self, temp_dir: Path) -> None:
        """ZoteroReader should raise error if library.json missing."""
        zotero_dir = temp_dir / "ZoteroNoJson"
        zotero_dir.mkdir()

        # Create databases but no library.json
        (zotero_dir / "zotero.sqlite").touch()
        (zotero_dir / "better-bibtex.sqlite").touch()

        with pytest.raises(ZoteroError) as exc_info:
            ZoteroReader(zotero_dir)

        assert exc_info.value.code == ErrorCode.ZOTERO_LIBRARY_JSON_NOT_FOUND

    def test_get_item_raises_for_unknown_citekey(
        self, complete_zotero_dir: Path
    ) -> None:
        """get_item should raise error for citekey not in library.json."""
        with ZoteroReader(complete_zotero_dir) as reader:
            with pytest.raises(ZoteroError) as exc_info:
                reader.get_item("nonexistent")

        assert exc_info.value.code == ErrorCode.ZOTERO_ITEM_NOT_FOUND

    def test_get_item_raises_for_citekey_not_in_bbt(
        self, complete_zotero_dir: Path
    ) -> None:
        """get_item should raise error if citekey in JSON but not BBT database."""
        # Add citekey to library.json but not to BBT database
        library_json_path = complete_zotero_dir / "library.json"
        with open(library_json_path) as f:
            items = json.load(f)
        items.append({
            "id": "orphan2023",
            "citation-key": "orphan2023",
            "type": "article",
            "title": "Orphaned Item",
        })
        with open(library_json_path, "w") as f:
            json.dump(items, f)

        with ZoteroReader(complete_zotero_dir) as reader:
            # Force reload to pick up new item
            reader.refresh()

            with pytest.raises(ZoteroError) as exc_info:
                reader.get_item("orphan2023")

        assert exc_info.value.code == ErrorCode.ZOTERO_CITEKEY_NOT_IN_BBT

    def test_custom_library_json_path(self, complete_zotero_dir: Path) -> None:
        """ZoteroReader should accept custom library.json path."""
        # Move library.json to custom location
        custom_path = complete_zotero_dir / "exports" / "my_library.json"
        custom_path.parent.mkdir()
        (complete_zotero_dir / "library.json").rename(custom_path)

        with ZoteroReader(
            complete_zotero_dir, library_json_path=custom_path
        ) as reader:
            assert reader.has_item("smith2023") is True

    def test_refresh_reloads_library_json(
        self, complete_zotero_dir: Path
    ) -> None:
        """refresh should reload library.json from disk."""
        with ZoteroReader(complete_zotero_dir) as reader:
            # Initial state
            assert reader.has_item("new2024") is False

            # Add new item to library.json
            library_json_path = complete_zotero_dir / "library.json"
            with open(library_json_path) as f:
                items = json.load(f)
            items.append({
                "id": "new2024",
                "citation-key": "new2024",
                "type": "article",
                "title": "New Item",
            })
            with open(library_json_path, "w") as f:
                json.dump(items, f)

            # Still cached - not visible
            assert reader.has_item("new2024") is False

            # After refresh - visible
            reader.refresh()
            assert reader.has_item("new2024") is True
```

**Step 2: Run all ZoteroReader tests**

Run: `uv run pytest tests/unit/test_zotero.py::TestZoteroReader -v`
Expected: All 12 tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_zotero.py
git commit -m "$(cat <<'EOF'
test(zotero): add error case tests for ZoteroReader

Tests missing directory/library.json errors, unknown citekey,
citekey not in BBT, custom library.json path, and refresh behavior.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Run Full Test Suite and Final Verification

**Files:**
- None (verification only)

**Step 1: Run all Zotero tests**

Run: `uv run pytest tests/unit/test_zotero.py -v`
Expected: All tests pass (ZoteroAttachment, ZoteroItem, LibraryJsonParser, DatabaseManager, BbtKeyMapper, AttachmentResolver, ZoteroReader)

**Step 2: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests pass (including existing tests)

**Step 3: Run linting and type checking**

Run: `uv run ruff check src/local_library/ingestion/zotero.py`
Expected: No linting errors

Run: `uv run ruff format --check src/local_library/ingestion/zotero.py tests/unit/test_zotero.py`
Expected: Files are formatted correctly (or format them if needed)

**Step 4: Verify module exports**

Run:
```bash
uv run python -c "
from local_library.ingestion.zotero import ZoteroReader, ZoteroItem, ZoteroAttachment
from local_library.core.errors import ZoteroError, ErrorCode
print('All exports available')
print(f'ErrorCode.ZOTERO_DIR_NOT_FOUND = {ErrorCode.ZOTERO_DIR_NOT_FOUND.value}')
"
```
Expected: Prints confirmation and error code value

**Step 5: Create final commit for Phase 6 completion**

```bash
git add -A
git status
```

If there are any uncommitted changes, commit them:

```bash
git commit -m "$(cat <<'EOF'
chore(zotero): complete M4 ZoteroReader implementation

All phases complete:
- Phase 1: Data model (ZoteroAttachment, ZoteroItem) and error codes
- Phase 2: Library JSON parsing (LibraryJsonParser)
- Phase 3: Database connection handling (DatabaseManager with copy-if-locked)
- Phase 4: Citekey to ItemID resolution (BbtKeyMapper)
- Phase 5: Attachment resolution (AttachmentResolver)
- Phase 6: Public API (ZoteroReader)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

---

**Phase 6 Done When:**
- ZoteroReader class wires all components together
- get_item, list_citekeys, has_item, refresh, close methods work
- Context manager protocol implemented
- All unit tests pass
- Full test suite passes
- Linting passes

**Milestone M4 Complete When:**
- All 6 phases implemented and tested
- Can retrieve CSL-JSON metadata for any item by citekey
- Can retrieve all PDF attachment paths for any item by citekey
- Gracefully handles edge cases: items without attachments, missing files, locked databases
- All tests pass: `uv run pytest -v`
