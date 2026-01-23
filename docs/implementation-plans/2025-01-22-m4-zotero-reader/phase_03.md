# Phase 3: Database Connection Handling

**Goal:** Safe read-only access to Zotero SQLite databases with copy-if-locked fallback.

**Codebase verification findings:**
- Python sqlite3 module in stdlib supports URI mode for read-only connections
- Zotero locks its SQLite databases while running (WAL mode with exclusive locks)
- Better BibTeX database: `better-bibtex.sqlite` in Zotero profile directory
- Zotero database: `zotero.sqlite` in Zotero profile directory
- Existing storage.py uses `get_connection()` pattern but for read-write access

**Design note:** This phase creates a `DatabaseManager` internal class that handles:
1. Read-only connection via SQLite URI mode (`?mode=ro`)
2. Detection of locked databases (SQLITE_BUSY error)
3. Copy-if-locked fallback to temporary directory
4. Connection caching and cleanup

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add DatabaseManager Class

**Files:**
- Modify: `src/local_library/ingestion/zotero.py`

**Step 1: Add imports for database handling**

Update the imports at the top of `src/local_library/ingestion/zotero.py`:

```python
"""Zotero library data access.

Provides read-only access to Zotero library data by coordinating:
- CSL-JSON metadata from Better BibTeX export (library.json)
- Citekey-to-itemID mapping from Better BibTeX SQLite database
- Attachment paths from Zotero's main SQLite database
"""

# pattern: Mixed (unavoidable)
# Reason: File/database I/O cannot be separated from parsing logic without
# introducing unnecessary complexity. Classes encapsulate external access.

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
import json
import shutil
import sqlite3
import tempfile

from local_library.core.errors import ErrorCode, ZoteroError
```

**Step 2: Add the DatabaseManager class after LibraryJsonParser**

Add the following class after the LibraryJsonParser class:

```python
class DatabaseManager:
    """Manages read-only access to Zotero SQLite databases.

    Handles database locking (when Zotero is running) by copying to a
    temporary location. Provides connection caching and cleanup.

    SQLite databases are opened in read-only mode via URI to prevent
    accidental writes.
    """

    # Database filenames in Zotero profile directory
    ZOTERO_DB = "zotero.sqlite"
    BBT_DB = "better-bibtex.sqlite"

    def __init__(self, zotero_dir: Path, temp_dir: Path | None = None) -> None:
        """Initialize database manager.

        Args:
            zotero_dir: Path to Zotero profile directory containing databases
            temp_dir: Directory for temporary database copies (uses system temp if None)

        Raises:
            ZoteroError: If zotero_dir doesn't exist (ZOTERO_DIR_NOT_FOUND)
        """
        if not zotero_dir.exists():
            raise ZoteroError(
                message=f"zotero directory not found: {zotero_dir}",
                code=ErrorCode.ZOTERO_DIR_NOT_FOUND,
                details={"path": str(zotero_dir)},
            )

        self._zotero_dir = zotero_dir
        self._temp_dir = temp_dir
        self._connections: dict[str, sqlite3.Connection] = {}
        self._temp_copies: list[Path] = []  # Track for cleanup
        self._managed_temp_dir: tempfile.TemporaryDirectory | None = None

    def _get_temp_dir(self) -> Path:
        """Get or create temporary directory for database copies."""
        if self._temp_dir is not None:
            self._temp_dir.mkdir(parents=True, exist_ok=True)
            return self._temp_dir

        # Create managed temp dir if not provided
        if self._managed_temp_dir is None:
            self._managed_temp_dir = tempfile.TemporaryDirectory(
                prefix="zotero_reader_"
            )
        return Path(self._managed_temp_dir.name)

    def _copy_to_temp(self, db_path: Path) -> Path:
        """Copy database to temporary location.

        Args:
            db_path: Path to the database file

        Returns:
            Path to the temporary copy

        Raises:
            ZoteroError: If copy fails (ZOTERO_DATABASE_ERROR)
        """
        temp_dir = self._get_temp_dir()
        temp_path = temp_dir / db_path.name

        try:
            shutil.copy2(db_path, temp_path)
        except OSError as e:
            raise ZoteroError(
                message=f"failed to copy database: {e}",
                code=ErrorCode.ZOTERO_DATABASE_ERROR,
                details={"source": str(db_path), "dest": str(temp_path), "error": str(e)},
            ) from e

        self._temp_copies.append(temp_path)
        return temp_path

    def _open_readonly(self, db_path: Path) -> sqlite3.Connection:
        """Open database in read-only mode.

        Uses SQLite URI mode to enforce read-only access.

        Args:
            db_path: Path to the database file

        Returns:
            Read-only database connection

        Raises:
            ZoteroError: If database is locked (ZOTERO_DATABASE_LOCKED) or
                        other error (ZOTERO_DATABASE_ERROR)
        """
        # SQLite URI format for read-only access
        uri = f"file:{db_path}?mode=ro"

        try:
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            # Test that we can actually read
            conn.execute("SELECT 1")
            return conn
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg or "busy" in error_msg:
                raise ZoteroError(
                    message=f"database is locked: {db_path}",
                    code=ErrorCode.ZOTERO_DATABASE_LOCKED,
                    details={"path": str(db_path), "error": str(e)},
                ) from e
            raise ZoteroError(
                message=f"database error: {e}",
                code=ErrorCode.ZOTERO_DATABASE_ERROR,
                details={"path": str(db_path), "error": str(e)},
            ) from e

    def get_connection(self, db_name: str) -> sqlite3.Connection:
        """Get a connection to a Zotero database.

        Attempts to open the database directly in read-only mode.
        If the database is locked (Zotero is running), copies to
        a temporary location and opens the copy.

        Connections are cached for reuse within a session.

        Args:
            db_name: Database filename (e.g., "zotero.sqlite" or "better-bibtex.sqlite")

        Returns:
            Read-only database connection

        Raises:
            ZoteroError: If database doesn't exist (ZOTERO_DATABASE_NOT_FOUND)
                        or access fails (ZOTERO_DATABASE_ERROR)
        """
        # Return cached connection if available
        if db_name in self._connections:
            return self._connections[db_name]

        db_path = self._zotero_dir / db_name

        if not db_path.exists():
            raise ZoteroError(
                message=f"database not found: {db_path}",
                code=ErrorCode.ZOTERO_DATABASE_NOT_FOUND,
                details={"path": str(db_path), "db_name": db_name},
            )

        try:
            # Try direct read-only access first
            conn = self._open_readonly(db_path)
        except ZoteroError as e:
            if e.code != ErrorCode.ZOTERO_DATABASE_LOCKED:
                raise
            # Database is locked, copy to temp and retry
            temp_path = self._copy_to_temp(db_path)
            conn = self._open_readonly(temp_path)

        self._connections[db_name] = conn
        return conn

    def close(self) -> None:
        """Close all connections and clean up temporary files."""
        for conn in self._connections.values():
            try:
                conn.close()
            except Exception:
                pass  # Best effort cleanup
        self._connections.clear()

        # Clean up temp copies
        for temp_path in self._temp_copies:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
        self._temp_copies.clear()

        # Clean up managed temp dir
        if self._managed_temp_dir is not None:
            try:
                self._managed_temp_dir.cleanup()
            except Exception:
                pass
            self._managed_temp_dir = None
```

**Step 3: Verify the file is importable**

Run: `uv run python -c "from local_library.ingestion.zotero import DatabaseManager; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add src/local_library/ingestion/zotero.py
git commit -m "$(cat <<'EOF'
feat(zotero): add DatabaseManager for read-only SQLite access

Manages connections to zotero.sqlite and better-bibtex.sqlite with:
- Read-only access via SQLite URI mode
- Copy-if-locked fallback when Zotero is running
- Connection caching for session reuse
- Proper cleanup of temp files and connections

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write Unit Tests for DatabaseManager - Happy Path

**Files:**
- Modify: `tests/unit/test_zotero.py`

**Step 1: Add imports for database testing**

Update the imports at the top of `tests/unit/test_zotero.py`:

```python
"""Unit tests for Zotero data models, parsers, and database access."""

import json
import sqlite3
from pathlib import Path

import pytest

from local_library.core.errors import ErrorCode, ZoteroError
from local_library.ingestion.zotero import (
    DatabaseManager,
    LibraryJsonParser,
    ZoteroAttachment,
    ZoteroItem,
)
```

**Step 2: Add DatabaseManager happy path tests**

Add the following test class after TestLibraryJsonParser:

```python
class TestDatabaseManager:
    """Tests for DatabaseManager class."""

    @pytest.fixture
    def zotero_dir(self, temp_dir: Path) -> Path:
        """Create a mock Zotero directory with test databases."""
        # Create directory structure
        zotero_path = temp_dir / "Zotero"
        zotero_path.mkdir()

        # Create minimal zotero.sqlite
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO items (itemID) VALUES (1)")
        conn.commit()
        conn.close()

        # Create minimal better-bibtex.sqlite
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("CREATE TABLE citationkey (itemID INTEGER, citationKey TEXT)")
        conn.execute("INSERT INTO citationkey VALUES (1, 'smith2023')")
        conn.commit()
        conn.close()

        return zotero_path

    def test_get_connection_returns_readonly_connection(
        self, zotero_dir: Path
    ) -> None:
        """get_connection should return a readable connection."""
        manager = DatabaseManager(zotero_dir)

        try:
            conn = manager.get_connection("zotero.sqlite")

            # Should be able to read
            cursor = conn.execute("SELECT itemID FROM items")
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["itemID"] == 1
        finally:
            manager.close()

    def test_connection_is_cached(self, zotero_dir: Path) -> None:
        """get_connection should return cached connection on subsequent calls."""
        manager = DatabaseManager(zotero_dir)

        try:
            conn1 = manager.get_connection("zotero.sqlite")
            conn2 = manager.get_connection("zotero.sqlite")

            assert conn1 is conn2
        finally:
            manager.close()

    def test_can_access_both_databases(self, zotero_dir: Path) -> None:
        """Manager should provide access to both Zotero and BBT databases."""
        manager = DatabaseManager(zotero_dir)

        try:
            zotero_conn = manager.get_connection("zotero.sqlite")
            bbt_conn = manager.get_connection("better-bibtex.sqlite")

            # Verify we can read from both
            zotero_rows = zotero_conn.execute("SELECT * FROM items").fetchall()
            bbt_rows = bbt_conn.execute("SELECT * FROM citationkey").fetchall()

            assert len(zotero_rows) == 1
            assert len(bbt_rows) == 1
        finally:
            manager.close()

    def test_close_clears_connections(self, zotero_dir: Path) -> None:
        """close should clear all cached connections."""
        manager = DatabaseManager(zotero_dir)

        _ = manager.get_connection("zotero.sqlite")
        assert len(manager._connections) == 1

        manager.close()

        assert len(manager._connections) == 0

    def test_row_factory_enables_column_access(self, zotero_dir: Path) -> None:
        """Connections should use Row factory for column name access."""
        manager = DatabaseManager(zotero_dir)

        try:
            conn = manager.get_connection("zotero.sqlite")
            cursor = conn.execute("SELECT itemID FROM items")
            row = cursor.fetchone()

            # Should be able to access by column name
            assert row["itemID"] == 1
        finally:
            manager.close()
```

**Step 3: Run the tests**

Run: `uv run pytest tests/unit/test_zotero.py::TestDatabaseManager -v`
Expected: All 5 tests pass

**Step 4: Commit**

```bash
git add tests/unit/test_zotero.py
git commit -m "$(cat <<'EOF'
test(zotero): add unit tests for DatabaseManager happy path

Tests connection retrieval, caching, access to both databases,
cleanup, and Row factory for column name access.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write Unit Tests for DatabaseManager - Error Cases and Copy-if-Locked

**Files:**
- Modify: `tests/unit/test_zotero.py`

**Step 1: Add error case tests to TestDatabaseManager class**

Add the following test methods to the TestDatabaseManager class:

```python
    def test_raises_error_for_missing_directory(self, temp_dir: Path) -> None:
        """Manager should raise error if Zotero directory doesn't exist."""
        missing_dir = temp_dir / "nonexistent"

        with pytest.raises(ZoteroError) as exc_info:
            DatabaseManager(missing_dir)

        assert exc_info.value.code == ErrorCode.ZOTERO_DIR_NOT_FOUND

    def test_raises_error_for_missing_database(self, zotero_dir: Path) -> None:
        """Manager should raise error if requested database doesn't exist."""
        manager = DatabaseManager(zotero_dir)

        try:
            with pytest.raises(ZoteroError) as exc_info:
                manager.get_connection("nonexistent.sqlite")

            assert exc_info.value.code == ErrorCode.ZOTERO_DATABASE_NOT_FOUND
        finally:
            manager.close()

    def test_copy_if_locked_creates_temp_copy(self, zotero_dir: Path) -> None:
        """Manager should copy database to temp if locked."""
        manager = DatabaseManager(zotero_dir)

        # Simulate locked database by holding an exclusive lock
        db_path = zotero_dir / "zotero.sqlite"
        locking_conn = sqlite3.connect(db_path, isolation_level="EXCLUSIVE")
        locking_conn.execute("BEGIN EXCLUSIVE")

        try:
            # Should fall back to copy
            conn = manager.get_connection("zotero.sqlite")

            # Should still be able to read (from copy)
            cursor = conn.execute("SELECT itemID FROM items")
            rows = cursor.fetchall()
            assert len(rows) == 1

            # Temp copy should have been created
            assert len(manager._temp_copies) == 1
        finally:
            locking_conn.close()
            manager.close()

    def test_custom_temp_dir_is_used(self, zotero_dir: Path, temp_dir: Path) -> None:
        """Manager should use provided temp_dir for copies."""
        custom_temp = temp_dir / "custom_temp"
        custom_temp.mkdir()
        manager = DatabaseManager(zotero_dir, temp_dir=custom_temp)

        # Simulate locked database
        db_path = zotero_dir / "zotero.sqlite"
        locking_conn = sqlite3.connect(db_path, isolation_level="EXCLUSIVE")
        locking_conn.execute("BEGIN EXCLUSIVE")

        try:
            _ = manager.get_connection("zotero.sqlite")

            # Check copy is in custom temp dir
            assert len(manager._temp_copies) == 1
            assert manager._temp_copies[0].parent == custom_temp
        finally:
            locking_conn.close()
            manager.close()

    def test_close_removes_temp_copies(self, zotero_dir: Path) -> None:
        """close should remove temporary database copies."""
        manager = DatabaseManager(zotero_dir)

        # Simulate locked database
        db_path = zotero_dir / "zotero.sqlite"
        locking_conn = sqlite3.connect(db_path, isolation_level="EXCLUSIVE")
        locking_conn.execute("BEGIN EXCLUSIVE")

        try:
            _ = manager.get_connection("zotero.sqlite")
            temp_path = manager._temp_copies[0]
            assert temp_path.exists()

            manager.close()

            # Temp copy should be removed
            assert not temp_path.exists()
        finally:
            locking_conn.close()
```

**Step 2: Run all DatabaseManager tests**

Run: `uv run pytest tests/unit/test_zotero.py::TestDatabaseManager -v`
Expected: All 10 tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_zotero.py
git commit -m "$(cat <<'EOF'
test(zotero): add error case and copy-if-locked tests for DatabaseManager

Tests missing directory/database errors, copy-if-locked fallback when
database is locked, custom temp directory usage, and cleanup of temp copies.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

**Phase 3 Done When:**
- DatabaseManager class handles read-only SQLite access
- Copy-if-locked fallback works when databases are locked
- Connection caching and cleanup implemented
- All tests pass: `uv run pytest tests/unit/test_zotero.py::TestDatabaseManager -v`
