# Phase 4: Citekey to ItemID Resolution

**Goal:** Map Better BibTeX citekeys to Zotero item identifiers.

**External research findings:**
- Better BibTeX stores citekeys in `better-bibtex.sqlite` in a `citationkey` table
- The table maps `itemID` (Zotero's internal ID) to `citationKey` (the citekey string)
- Schema has evolved across versions; recent versions use a dedicated table
- Some citekeys may also be "pinned" in Zotero's extra field, but BBT database is authoritative

**Codebase verification findings:**
- DatabaseManager from Phase 3 provides connection to `better-bibtex.sqlite`
- ZoteroError with ZOTERO_CITEKEY_NOT_IN_BBT code available for lookup failures

**Design note:** This phase adds a `BbtKeyMapper` class that queries the Better BibTeX
database to resolve citekeys to (itemID, itemKey) tuples. The itemKey is Zotero's
8-character stable key (e.g., "ABCD1234") which is needed for path resolution.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add BbtKeyMapper Class

**Files:**
- Modify: `src/local_library/ingestion/zotero.py`

**Step 1: Add the BbtKeyMapper class after DatabaseManager**

Add the following class after the DatabaseManager class in `src/local_library/ingestion/zotero.py`:

```python
class BbtKeyMapper:
    """Maps Better BibTeX citekeys to Zotero item identifiers.

    Queries the Better BibTeX SQLite database to resolve citekeys to
    Zotero's internal itemID and stable itemKey.

    The BBT database schema includes a `citationkey` table that maps
    itemID to citationKey. We join with Zotero's items table to get
    the stable itemKey (8-character alphanumeric key).
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        """Initialize with database manager.

        Args:
            db_manager: DatabaseManager providing access to BBT and Zotero databases
        """
        self._db_manager = db_manager

    def lookup(self, citekey: str) -> tuple[int, str]:
        """Resolve a citekey to Zotero item identifiers.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            Tuple of (itemID, itemKey) where:
            - itemID: Zotero's internal numeric ID (used for database joins)
            - itemKey: Zotero's 8-character stable key (used for storage paths)

        Raises:
            ZoteroError: If citekey not found (ZOTERO_CITEKEY_NOT_IN_BBT)
        """
        bbt_conn = self._db_manager.get_connection(DatabaseManager.BBT_DB)
        zotero_conn = self._db_manager.get_connection(DatabaseManager.ZOTERO_DB)

        # Query BBT for itemID
        cursor = bbt_conn.execute(
            "SELECT itemID FROM citationkey WHERE citationKey = ?",
            (citekey,),
        )
        row = cursor.fetchone()

        if row is None:
            raise ZoteroError(
                message=f"citekey not found in Better BibTeX: {citekey}",
                code=ErrorCode.ZOTERO_CITEKEY_NOT_IN_BBT,
                details={"citekey": citekey},
            )

        item_id = row["itemID"]

        # Query Zotero for itemKey
        cursor = zotero_conn.execute(
            "SELECT key FROM items WHERE itemID = ?",
            (item_id,),
        )
        row = cursor.fetchone()

        if row is None:
            # This shouldn't happen if BBT and Zotero are in sync
            raise ZoteroError(
                message=f"itemID {item_id} from BBT not found in Zotero database",
                code=ErrorCode.ZOTERO_ITEM_NOT_FOUND,
                details={"citekey": citekey, "item_id": item_id},
            )

        return (item_id, row["key"])

    def has_citekey(self, citekey: str) -> bool:
        """Check if a citekey exists in Better BibTeX.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            True if citekey exists, False otherwise
        """
        bbt_conn = self._db_manager.get_connection(DatabaseManager.BBT_DB)

        cursor = bbt_conn.execute(
            "SELECT 1 FROM citationkey WHERE citationKey = ? LIMIT 1",
            (citekey,),
        )
        return cursor.fetchone() is not None
```

**Step 2: Verify the file is importable**

Run: `uv run python -c "from local_library.ingestion.zotero import BbtKeyMapper; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/local_library/ingestion/zotero.py
git commit -m "$(cat <<'EOF'
feat(zotero): add BbtKeyMapper for citekey-to-itemID resolution

Queries Better BibTeX database to resolve citekeys to Zotero's
itemID (for database joins) and itemKey (for storage paths).
Handles missing citekeys with appropriate error codes.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write Unit Tests for BbtKeyMapper - Happy Path

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
    BbtKeyMapper,
    DatabaseManager,
    LibraryJsonParser,
    ZoteroAttachment,
    ZoteroItem,
)
```

**Step 2: Add BbtKeyMapper test class**

Add the following test class after TestDatabaseManager:

```python
class TestBbtKeyMapper:
    """Tests for BbtKeyMapper class."""

    @pytest.fixture
    def zotero_dir_with_citekeys(self, temp_dir: Path) -> Path:
        """Create mock Zotero directory with BBT citekey data."""
        zotero_path = temp_dir / "Zotero"
        zotero_path.mkdir()

        # Create zotero.sqlite with items table
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("""
            CREATE TABLE items (
                itemID INTEGER PRIMARY KEY,
                key TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO items (itemID, key) VALUES (100, 'SMITH001')")
        conn.execute("INSERT INTO items (itemID, key) VALUES (200, 'JONES002')")
        conn.execute("INSERT INTO items (itemID, key) VALUES (300, 'BROWN003')")
        conn.commit()
        conn.close()

        # Create better-bibtex.sqlite with citationkey table
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("""
            CREATE TABLE citationkey (
                itemID INTEGER PRIMARY KEY,
                citationKey TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO citationkey VALUES (100, 'smith2023')")
        conn.execute("INSERT INTO citationkey VALUES (200, 'jones2022')")
        # Note: itemID 300 has no citekey in BBT
        conn.commit()
        conn.close()

        return zotero_path

    @pytest.fixture
    def db_manager(self, zotero_dir_with_citekeys: Path) -> DatabaseManager:
        """Provide DatabaseManager for tests."""
        manager = DatabaseManager(zotero_dir_with_citekeys)
        yield manager
        manager.close()

    def test_lookup_returns_item_ids(self, db_manager: DatabaseManager) -> None:
        """lookup should return (itemID, itemKey) tuple."""
        mapper = BbtKeyMapper(db_manager)

        item_id, item_key = mapper.lookup("smith2023")

        assert item_id == 100
        assert item_key == "SMITH001"

    def test_lookup_different_citekey(self, db_manager: DatabaseManager) -> None:
        """lookup should work for different citekeys."""
        mapper = BbtKeyMapper(db_manager)

        item_id, item_key = mapper.lookup("jones2022")

        assert item_id == 200
        assert item_key == "JONES002"

    def test_has_citekey_returns_true_for_existing(
        self, db_manager: DatabaseManager
    ) -> None:
        """has_citekey should return True for existing citekey."""
        mapper = BbtKeyMapper(db_manager)

        assert mapper.has_citekey("smith2023") is True
        assert mapper.has_citekey("jones2022") is True

    def test_has_citekey_returns_false_for_missing(
        self, db_manager: DatabaseManager
    ) -> None:
        """has_citekey should return False for missing citekey."""
        mapper = BbtKeyMapper(db_manager)

        assert mapper.has_citekey("nonexistent") is False
```

**Step 3: Run the tests**

Run: `uv run pytest tests/unit/test_zotero.py::TestBbtKeyMapper -v`
Expected: All 4 tests pass

**Step 4: Commit**

```bash
git add tests/unit/test_zotero.py
git commit -m "$(cat <<'EOF'
test(zotero): add unit tests for BbtKeyMapper happy path

Tests lookup returning (itemID, itemKey) tuple and has_citekey
checking existence in Better BibTeX database.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write Unit Tests for BbtKeyMapper - Error Cases

**Files:**
- Modify: `tests/unit/test_zotero.py`

**Step 1: Add error case tests to TestBbtKeyMapper class**

Add the following test methods to the TestBbtKeyMapper class:

```python
    def test_lookup_raises_for_missing_citekey(
        self, db_manager: DatabaseManager
    ) -> None:
        """lookup should raise error for citekey not in BBT."""
        mapper = BbtKeyMapper(db_manager)

        with pytest.raises(ZoteroError) as exc_info:
            mapper.lookup("nonexistent")

        assert exc_info.value.code == ErrorCode.ZOTERO_CITEKEY_NOT_IN_BBT
        assert "nonexistent" in str(exc_info.value)

    def test_lookup_raises_for_orphaned_bbt_entry(
        self, temp_dir: Path
    ) -> None:
        """lookup should raise if BBT entry points to missing Zotero item."""
        # Create Zotero dir with mismatched data
        zotero_path = temp_dir / "ZoteroOrphan"
        zotero_path.mkdir()

        # Zotero DB without itemID 999
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
        conn.execute("INSERT INTO items VALUES (1, 'REAL0001')")
        conn.commit()
        conn.close()

        # BBT DB with orphaned reference to itemID 999
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("CREATE TABLE citationkey (itemID INTEGER, citationKey TEXT)")
        conn.execute("INSERT INTO citationkey VALUES (999, 'orphan2023')")
        conn.commit()
        conn.close()

        manager = DatabaseManager(zotero_path)
        mapper = BbtKeyMapper(manager)

        try:
            with pytest.raises(ZoteroError) as exc_info:
                mapper.lookup("orphan2023")

            assert exc_info.value.code == ErrorCode.ZOTERO_ITEM_NOT_FOUND
        finally:
            manager.close()

    def test_lookup_is_case_sensitive(self, db_manager: DatabaseManager) -> None:
        """Citekey lookup should be case-sensitive."""
        mapper = BbtKeyMapper(db_manager)

        # smith2023 exists, SMITH2023 does not
        assert mapper.has_citekey("smith2023") is True
        assert mapper.has_citekey("SMITH2023") is False
        assert mapper.has_citekey("Smith2023") is False
```

**Step 2: Run all BbtKeyMapper tests**

Run: `uv run pytest tests/unit/test_zotero.py::TestBbtKeyMapper -v`
Expected: All 7 tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_zotero.py
git commit -m "$(cat <<'EOF'
test(zotero): add error case tests for BbtKeyMapper

Tests missing citekey error, orphaned BBT entry error, and
case-sensitive citekey matching.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

**Phase 4 Done When:**
- BbtKeyMapper resolves citekeys to (itemID, itemKey) tuples
- Appropriate errors raised for missing citekeys and orphaned entries
- All tests pass: `uv run pytest tests/unit/test_zotero.py::TestBbtKeyMapper -v`
