# Library List Filters Implementation Plan

**Goal:** Add richer filter parameters (`year`, `year_missing`, `author_contains`, `title_contains`, `citekey_prefix`) to `Library.list()`, the CLI `list` command, and the MCP `list_documents` tool, backed by a new derived `issued_year INTEGER` column populated at write time. Schema migration v3→v4 with auto-migration on startup.

**Architecture:** Denormalized indexed column following the existing precedent (title, authors, issued_date already extracted from CSL-JSON at write time). New shared utility `extract_year_from_csl()` in `metadata.py` consumed by both the existing citekey year extraction and the new MetadataResult field. Dynamic WHERE clause construction in `storage.list_documents()` with LIKE escaping for safe substring matching.

**Tech Stack:** SQLite (existing), Typer (CLI flags), FastMCP (tool parameters), pytest (tests)

**Scope:** 1 phase from the design plan (full implementation).

**Codebase verified:** 2026-04-16

**Design plan:** `docs/design-plans/2026-04-16-library-list-filters.md`

---

## Phase 1: Schema Migration + Filter Expansion

**Goal:** Ship the full filter surface with schema v4 migration, backfill, write-path integration, and updated consumers (CLI, MCP).

### Codebase verification findings

- ✓ `SCHEMA_VERSION = 3` at `src/local_library/core/storage.py:19`
- ✓ Migration framework exists: `migrate_schema()` at line 180, `_migrate_v1_to_v2()` at line 204, `_migrate_v2_to_v3()` at line 227. Auto-run by `init_schema()` (called on every Library startup).
- ✓ `StorageError` class exists at `src/local_library/core/errors.py:109`; convention `STORAGE_*` for ErrorCode values (STORAGE_DATABASE_ERROR, STORAGE_WRITE_FAILED at lines 32-33). `SCHEMA_MIGRATION_FAILED` does not exist — add it.
- ✗ Discrepancy from design: **no `_extract_indexed_fields()` function exists**. Indexed field extraction is inline in `Library.update_metadata()` (lines 1097-1121) and delegated to `MetadataHandler.process()` (result has title/authors/issued_date) in the other two write paths.
- ✓ Three write paths all converge on `update_document_metadata()` in `storage.py:590`:
  1. `Library._process_metadata()` (line 869) — uses `MetadataResult`
  2. `Library._attempt_metadata_upgrade()` (line 575) — uses `MetadataResult`
  3. `Library.update_metadata()` (line 1069+) — inline extraction
- ✓ `MetadataResult` dataclass is populated by `MetadataHandler.process()` at `metadata.py:552-560` with fields title, authors, issued_date (and internal author_list, validation_warnings).
- ✓ Existing `_extract_year_for_citekey()` at `metadata.py:228-246` handles CSL-JSON issued field edge cases (None guards at multiple levels) and returns a year string or "".
- ✓ `_extract_issued_date()` at `metadata.py:696-734` normalizes to ISO format (YYYY, YYYY-MM, YYYY-MM-DD). The inline extraction in `update_metadata` is inconsistent — stores just year — but this pre-existing inconsistency is out of scope for this work.
- ✓ Document dataclass in `models.py:47-95` has `issued_date` but no `issued_year`. Field order matters for storage row unpacking.
- ✓ Current `list_documents()` SQL at `storage.py:494-514` builds WHERE clause conditionally on a single `status` parameter.
- ✓ Tests exist in `tests/unit/test_storage.py` (for storage layer) and `tests/unit/test_library.py` (for Library orchestrator). Test pattern uses real SQLite in temp directories via the `temp_dir` fixture (`tests/conftest.py`), not mocks.
- ✓ No existing migration tests. This work establishes the precedent pattern.
- ✓ CLI tests for `list` do not exist yet (`tests/unit/test_cli_list.py` is absent). Other CLI tests use Typer's `CliRunner` + mocked Library (see `tests/unit/test_cli_search.py:19-29` for the pattern).
- ✓ MCP tests in `tests/unit/test_mcp_server.py` — `TestListDocuments` class already exists with 4 tests; extend it.
- ✓ No `pytest-timeout` plugin installed — tests must rely on being fast.
- ✓ `issued_date` text column values are heterogeneous: paths 1 and 2 produce ISO format via `_extract_issued_date()`, path 3 produces just year via inline logic. Backfill GLOB pattern `'[0-9][0-9][0-9][0-9]*'` handles both.

---

<!-- START_TASK_1 -->
### Task 1: Schema v4 migration with SCHEMA_MIGRATION_FAILED error code

**Type:** Infrastructure + Functionality (functionality task — write test for migration, then implement)

**Files:**
- Modify: `src/local_library/core/errors.py` (add `SCHEMA_MIGRATION_FAILED` ErrorCode)
- Modify: `src/local_library/core/storage.py` (bump `SCHEMA_VERSION`, update `SCHEMA_TABLES`/`SCHEMA_INDEXES`, add `_migrate_v3_to_v4()`, update `migrate_schema()` dispatcher, enhance migration logging)
- Create: `tests/unit/test_storage.py` test class `TestSchemaMigrationV3ToV4` (in existing file)

**Reference files for executor:**
- `src/local_library/core/errors.py:9-71` — ErrorCode enum structure; STORAGE_* existing codes at lines 32-33
- `src/local_library/core/storage.py:19` — SCHEMA_VERSION constant
- `src/local_library/core/storage.py:21-68` — SCHEMA_TABLES (documents table definition at lines 26-43), SCHEMA_INDEXES (list including `idx_documents_issued_date` at line 64)
- `src/local_library/core/storage.py:147-178` — `init_schema()` (calls `migrate_schema()` at line 174 automatically)
- `src/local_library/core/storage.py:180-201` — `migrate_schema()` dispatcher pattern
- `src/local_library/core/storage.py:204-225` — `_migrate_v1_to_v2()` (adds title/authors/issued_date columns, pattern to follow for issued_year)
- `src/local_library/core/storage.py:227-263` — `_migrate_v2_to_v3()` (another migration example with schema_version UPDATE at end)
- `tests/unit/test_storage.py` — existing test patterns (real SQLite via `temp_dir` fixture from `tests/conftest.py`)

**Step 1: Add `SCHEMA_MIGRATION_FAILED` ErrorCode**

In `src/local_library/core/errors.py`, locate the STORAGE_* codes (around lines 32-33):

```python
STORAGE_DATABASE_ERROR = "STORAGE_DATABASE_ERROR"
STORAGE_WRITE_FAILED = "STORAGE_WRITE_FAILED"
```

Add immediately after:

```python
STORAGE_MIGRATION_FAILED = "STORAGE_MIGRATION_FAILED"
```

**Step 2: Write failing migration test**

Add to `tests/unit/test_storage.py`. If the file has no `TestSchemaMigration` content, append this class at the end (adjust imports at the top of the file if missing):

```python
import sqlite3
from pathlib import Path

import pytest

from local_library.core.storage import (
    SCHEMA_VERSION,
    get_connection,
    init_schema,
    migrate_schema,
)


class TestSchemaMigrationV3ToV4:
    """Tests for the v3 → v4 migration adding issued_year column."""

    def _create_v3_database(self, db_path: Path) -> sqlite3.Connection:
        """Create a database at schema v3 with representative issued_date values."""
        conn = get_connection(db_path)
        # Create v1 schema, then migrate forward to v3 so we exercise the real
        # migration chain (avoids duplicating v3 DDL here).
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            );
            INSERT OR IGNORE INTO schema_version (version) VALUES (1);

            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                original_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                extracted_path TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                citekey TEXT,
                csl_json TEXT,
                error_message TEXT,
                error_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        # Run migrations up to v3 (exercises v1→v2 and v2→v3 real code)
        migrate_schema(conn, target_version=3)
        return conn

    def _insert_doc(
        self,
        conn: sqlite3.Connection,
        doc_id: str,
        issued_date: str | None,
    ) -> None:
        """Insert a minimal document row with a given issued_date."""
        conn.execute(
            """
            INSERT INTO documents (
                id, original_path, content_hash, storage_path,
                status, issued_date, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'ready', ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
            """,
            (doc_id, f"/tmp/{doc_id}.pdf", doc_id, f"ab/cd/{doc_id}.pdf", issued_date),
        )
        conn.commit()

    def test_migration_adds_issued_year_column(self, temp_dir: Path) -> None:
        """After migration, documents table has an issued_year INTEGER column."""
        conn = self._create_v3_database(temp_dir / "test.db")

        # Verify v3 state: no issued_year column
        cols_v3 = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
        assert "issued_year" not in cols_v3

        # Run migration to current version (should be 4 after this task)
        migrate_schema(conn)

        cols_v4 = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
        assert "issued_year" in cols_v4

    def test_migration_creates_issued_year_index(self, temp_dir: Path) -> None:
        """Migration creates idx_documents_issued_year index."""
        conn = self._create_v3_database(temp_dir / "test.db")
        migrate_schema(conn)
        indexes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='documents'"
        )}
        assert "idx_documents_issued_year" in indexes

    def test_migration_bumps_schema_version_to_4(self, temp_dir: Path) -> None:
        """After migration, schema_version row is 4."""
        conn = self._create_v3_database(temp_dir / "test.db")
        migrate_schema(conn)
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == 4

    def test_migration_backfills_iso_date(self, temp_dir: Path) -> None:
        """Migration extracts year from ISO-format issued_date."""
        conn = self._create_v3_database(temp_dir / "test.db")
        self._insert_doc(conn, "doc1", "2023-06-15")
        migrate_schema(conn)
        year = conn.execute("SELECT issued_year FROM documents WHERE id = 'doc1'").fetchone()[0]
        assert year == 2023

    def test_migration_backfills_year_only(self, temp_dir: Path) -> None:
        """Migration extracts year from year-only issued_date."""
        conn = self._create_v3_database(temp_dir / "test.db")
        self._insert_doc(conn, "doc1", "1984")
        migrate_schema(conn)
        year = conn.execute("SELECT issued_year FROM documents WHERE id = 'doc1'").fetchone()[0]
        assert year == 1984

    def test_migration_nulls_year_for_missing_date(self, temp_dir: Path) -> None:
        """Documents with NULL issued_date get NULL issued_year."""
        conn = self._create_v3_database(temp_dir / "test.db")
        self._insert_doc(conn, "doc1", None)
        migrate_schema(conn)
        year = conn.execute("SELECT issued_year FROM documents WHERE id = 'doc1'").fetchone()[0]
        assert year is None

    def test_migration_nulls_year_for_malformed_date(self, temp_dir: Path) -> None:
        """Non-numeric issued_date values yield NULL issued_year."""
        conn = self._create_v3_database(temp_dir / "test.db")
        self._insert_doc(conn, "doc1", "Spring 2023")
        self._insert_doc(conn, "doc2", "XXXX")
        migrate_schema(conn)
        rows = {
            row[0]: row[1]
            for row in conn.execute("SELECT id, issued_year FROM documents")
        }
        assert rows["doc1"] is None
        assert rows["doc2"] is None

    def test_init_schema_auto_migrates_v3_to_v4(self, temp_dir: Path) -> None:
        """init_schema() auto-runs the v3→v4 migration."""
        conn = self._create_v3_database(temp_dir / "test.db")
        # Explicitly verify v3 starting state
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == 3
        # Call init_schema (fresh invocation) which should auto-migrate
        init_schema(conn)
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == SCHEMA_VERSION  # 4 after this task
```

Note the test imports. If `temp_dir` isn't already imported via conftest auto-discovery, no import is needed — pytest picks it up from `tests/conftest.py`.

**Note:** If `migrate_schema()` doesn't currently accept a `target_version` parameter, the test that runs migrations up to v3 will need adjustment. Check the current signature at `storage.py:180` and pass-through appropriately. If the signature is `migrate_schema(conn)` only (no target), remove the `target_version=3` argument from the test helper and have the helper just call `migrate_schema(conn)` which will go to whatever the current version is — then hand-insert documents AFTER confirming we're at v3 (i.e., keep `SCHEMA_VERSION` at 3 in the fixture setup). A cleaner alternative: the fixture manually inserts the v3 state into the documents table (all columns v3 has) and sets `schema_version = 3` explicitly, skipping the migration chain. Pick whichever approach matches the existing `migrate_schema` signature.

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_storage.py::TestSchemaMigrationV3ToV4 -v`

Expected: Tests fail with either `AssertionError` (SCHEMA_VERSION still 3, no issued_year column) or `AttributeError` / `sqlite3.OperationalError` depending on exact failure. The important thing is they fail *cleanly* — not with a setup error.

**Step 4: Bump SCHEMA_VERSION and add schema pieces**

In `src/local_library/core/storage.py`, change line 19:

```python
SCHEMA_VERSION = 4
```

Add `idx_documents_issued_year` to the `SCHEMA_INDEXES` list. Locate the list (around lines 58-66) and add:

```python
"CREATE INDEX IF NOT EXISTS idx_documents_issued_year ON documents(issued_year);",
```

Add the `issued_year INTEGER` column to the `documents` CREATE TABLE inside `SCHEMA_TABLES` (around lines 26-43). Insert the new column after `issued_date`:

```sql
issued_date TEXT,
issued_year INTEGER,
error_message TEXT,
```

This ensures newly-created databases (which skip migrations entirely) also get the column. For existing databases, the migration (next step) handles it.

**Step 5: Implement `_migrate_v3_to_v4()`**

In `src/local_library/core/storage.py`, immediately after `_migrate_v2_to_v3()` (line ~263), add:

```python
def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Migrate schema from v3 to v4.

    Adds a derived `issued_year INTEGER` column to `documents` for
    efficient year-based filtering. Backfills from the existing
    `issued_date` text column using SQLite's SUBSTR + CAST with a
    GLOB guard to skip malformed values.

    Args:
        conn: SQLite connection in a transaction.

    Raises:
        StorageError: If the migration steps fail.
    """
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN issued_year INTEGER;")
        conn.execute(
            """
            UPDATE documents
            SET issued_year = CAST(SUBSTR(issued_date, 1, 4) AS INTEGER)
            WHERE issued_date IS NOT NULL
              AND issued_date GLOB '[0-9][0-9][0-9][0-9]*';
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_issued_year "
            "ON documents(issued_year);"
        )
    except sqlite3.Error as e:
        raise StorageError(
            f"failed to migrate schema from v3 to v4: {e}",
            ErrorCode.STORAGE_MIGRATION_FAILED,
            details={"from_version": 3, "to_version": 4},
        ) from e
```

Ensure the `StorageError` and `ErrorCode` imports at the top of `storage.py` already exist (they should — other migrations and storage functions use them). Verify with `grep -n "StorageError\|ErrorCode" src/local_library/core/storage.py | head -5`.

**Step 6: Register the migration in `migrate_schema()`**

In `src/local_library/core/storage.py`, locate `migrate_schema()` (around line 180). Find the existing chain that dispatches to `_migrate_v1_to_v2()` and `_migrate_v2_to_v3()`. Add a third branch:

```python
# (after the v2→v3 branch)
if current_version < 4:
    logger.info("migrating database from schema v3 to v4...")
    _migrate_v3_to_v4(conn)
    conn.execute("UPDATE schema_version SET version = 4;")
    conn.commit()
    logger.info("database migration complete (now at schema v4)")
    current_version = 4
```

Pattern-match on the existing v1→v2 / v2→v3 branches — adopt their exact logging, version-update, and commit style. If those branches already include the `logger.info(...)` calls, this one should too; if they don't, add them here and leave the others alone (we only need user-facing visibility for the current migration).

**Step 7: Enhance migration start/success/failure logging if not already present**

Around the top of `migrate_schema()`, add an informational log line that fires when migrations are actually needed:

```python
if current_version < SCHEMA_VERSION:
    logger.info(
        "migrating database from schema v%d to v%d...",
        current_version,
        SCHEMA_VERSION,
    )
```

If the existing code already logs this, leave it alone. The goal: users running the library after an upgrade see a clear message explaining any startup delay.

**Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storage.py::TestSchemaMigrationV3ToV4 -v`

Expected: All 8 tests pass.

**Step 9: Run full unit suite to confirm no regressions**

Run: `uv run pytest tests/unit/ --tb=short -q`

Expected: 1173 tests pass (baseline) + 8 new = 1181 pass.

**Step 10: Lint**

Run: `uv run ruff check src/local_library/core/ tests/unit/test_storage.py`
Run: `uv run ruff format --check src/local_library/core/ tests/unit/test_storage.py`

Expected: Clean.

**Step 11: Commit**

```bash
git add src/local_library/core/errors.py src/local_library/core/storage.py tests/unit/test_storage.py
git commit -m "$(cat <<'EOF'
feat(storage): schema v4 migration adds issued_year column

Adds derived `issued_year INTEGER` column to `documents` populated at
write time from csl_json["issued"]. Migration backfills from
`issued_date` text column using GLOB guard to skip malformed values.
Adds `idx_documents_issued_year` index and `SCHEMA_MIGRATION_FAILED`
ErrorCode. Migration runs automatically via init_schema() on Library
startup with informational logging.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Shared `extract_year_from_csl()` utility in `metadata.py`

**Type:** Functionality (TDD — test-first)

**Files:**
- Modify: `src/local_library/ingestion/metadata.py` (add `extract_year_from_csl()`, refactor `_extract_year_for_citekey()` to use it)
- Modify: `tests/unit/test_metadata.py` (add `TestExtractYearFromCsl` class)

**Reference files for executor:**
- `src/local_library/ingestion/metadata.py:228-246` — existing `_extract_year_for_citekey()` (shape to preserve)
- `src/local_library/ingestion/metadata.py:696-734` — existing `_extract_issued_date()` (reference for CSL shape handling)
- `tests/unit/test_metadata.py` — existing test file; follow the existing class-based `TestMetadataHandlerValidation`-style pattern

**Step 1: Write failing tests**

Add to `tests/unit/test_metadata.py`:

```python
from local_library.ingestion.metadata import extract_year_from_csl


class TestExtractYearFromCsl:
    """Tests for the shared year-extraction utility."""

    def test_extracts_from_date_parts_full_date(self) -> None:
        csl = {"issued": {"date-parts": [[2023, 6, 15]]}}
        assert extract_year_from_csl(csl) == 2023

    def test_extracts_from_date_parts_year_month(self) -> None:
        csl = {"issued": {"date-parts": [[2023, 6]]}}
        assert extract_year_from_csl(csl) == 2023

    def test_extracts_from_date_parts_year_only(self) -> None:
        csl = {"issued": {"date-parts": [[2023]]}}
        assert extract_year_from_csl(csl) == 2023

    def test_returns_none_for_missing_issued(self) -> None:
        assert extract_year_from_csl({}) is None

    def test_returns_none_for_empty_issued(self) -> None:
        assert extract_year_from_csl({"issued": {}}) is None

    def test_returns_none_for_missing_date_parts(self) -> None:
        assert extract_year_from_csl({"issued": {"literal": "Spring 2023"}}) is None

    def test_returns_none_for_empty_date_parts_outer(self) -> None:
        assert extract_year_from_csl({"issued": {"date-parts": []}}) is None

    def test_returns_none_for_empty_date_parts_inner(self) -> None:
        assert extract_year_from_csl({"issued": {"date-parts": [[]]}}) is None

    def test_returns_none_for_none_year(self) -> None:
        csl = {"issued": {"date-parts": [[None]]}}
        assert extract_year_from_csl(csl) is None

    def test_returns_none_for_non_int_year(self) -> None:
        """Defensive: guard against unexpectedly-typed date parts."""
        csl = {"issued": {"date-parts": [["2023"]]}}
        # Permissive: "2023" could be cast, but spec says date-parts should be ints.
        # We accept str years and convert; document the decision in the function.
        assert extract_year_from_csl(csl) == 2023

    def test_returns_none_for_malformed_str_year(self) -> None:
        csl = {"issued": {"date-parts": [["XXXX"]]}}
        assert extract_year_from_csl(csl) is None

    def test_raw_field_not_parsed(self) -> None:
        """Raw-format dates return None rather than attempting regex parsing."""
        csl = {"issued": {"raw": "2023-06-15"}}
        assert extract_year_from_csl(csl) is None
```

Also add tests verifying `_extract_year_for_citekey()` still works correctly after the refactor (it should — behavior should be unchanged):

```python
class TestExtractYearForCitekey:
    """Tests for the citekey year wrapper (delegates to extract_year_from_csl)."""

    def test_returns_year_string(self) -> None:
        from local_library.ingestion.metadata import _extract_year_for_citekey
        csl = {"issued": {"date-parts": [[2023]]}}
        assert _extract_year_for_citekey(csl) == "2023"

    def test_returns_empty_string_when_missing(self) -> None:
        from local_library.ingestion.metadata import _extract_year_for_citekey
        assert _extract_year_for_citekey({}) == ""

    def test_returns_empty_string_for_none_year(self) -> None:
        from local_library.ingestion.metadata import _extract_year_for_citekey
        csl = {"issued": {"date-parts": [[None]]}}
        assert _extract_year_for_citekey(csl) == ""
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_metadata.py::TestExtractYearFromCsl tests/unit/test_metadata.py::TestExtractYearForCitekey -v`

Expected: `ImportError: cannot import name 'extract_year_from_csl'` or similar (function doesn't exist yet).

**Step 3: Implement `extract_year_from_csl()`**

In `src/local_library/ingestion/metadata.py`, add this function at module level (above `_extract_year_for_citekey()`, around line 225):

```python
def extract_year_from_csl(csl_json: dict[str, Any]) -> int | None:
    """Extract the publication year from a CSL-JSON blob as an integer.

    Handles the standard `issued.date-parts` shape:
    - {"date-parts": [[2023, 6, 15]]} → 2023
    - {"date-parts": [[2023]]} → 2023

    Other shapes ({"literal": "..."}, {"raw": "..."}) return None
    rather than attempting ambiguous regex parsing. String-typed year
    values in date-parts are accepted (some callers produce these) and
    converted if numeric.

    Args:
        csl_json: CSL-JSON metadata dictionary.

    Returns:
        Year as integer, or None if not extractable.
    """
    issued = csl_json.get("issued")
    if not issued:
        return None
    date_parts = issued.get("date-parts")
    if not date_parts or not date_parts[0]:
        return None
    year = date_parts[0][0]
    if year is None:
        return None
    if isinstance(year, int):
        return year
    if isinstance(year, str):
        try:
            return int(year)
        except ValueError:
            return None
    return None
```

**Step 4: Refactor `_extract_year_for_citekey()` to use the new utility**

Replace the body of `_extract_year_for_citekey()` (lines 228-246) with:

```python
def _extract_year_for_citekey(csl_json: dict[str, Any]) -> str:
    """Extract year from issued date for citekey generation.

    Returns:
        Four-digit year string, or empty string if not available.
    """
    year = extract_year_from_csl(csl_json)
    return str(year) if year is not None else ""
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_metadata.py -v`

Expected: All new `TestExtractYearFromCsl` and `TestExtractYearForCitekey` tests pass, plus existing tests in the file continue to pass.

**Step 6: Lint**

Run: `uv run ruff check src/local_library/ingestion/metadata.py tests/unit/test_metadata.py`
Run: `uv run ruff format --check src/local_library/ingestion/metadata.py tests/unit/test_metadata.py`

Expected: Clean.

**Step 7: Commit**

```bash
git add src/local_library/ingestion/metadata.py tests/unit/test_metadata.py
git commit -m "$(cat <<'EOF'
refactor(metadata): add extract_year_from_csl shared utility

Consolidates CSL-JSON year parsing into a single well-tested function
consumed by the existing citekey year extraction. Returns int | None
for clean comparison at SQL indexing layer. Preserves existing
_extract_year_for_citekey behavior (now a thin wrapper).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add `issued_year` to `MetadataResult` and `MetadataHandler.process()`

**Type:** Functionality (TDD — test-first)

**Files:**
- Modify: `src/local_library/core/models.py` (add `issued_year` to MetadataResult dataclass)
- Modify: `src/local_library/ingestion/metadata.py` (populate issued_year in `MetadataHandler.process()`)
- Modify: `tests/unit/test_metadata.py` (extend `TestMetadataHandler*` tests)

**Reference files for executor:**
- `src/local_library/core/models.py` — search for `MetadataResult` dataclass definition (likely frozen dataclass with `create` classmethod)
- `src/local_library/ingestion/metadata.py:547-560` — the `process()` method that builds MetadataResult
- `tests/unit/test_metadata.py` — existing MetadataHandler tests to extend

**Step 1: Locate and inspect `MetadataResult`**

Run: `grep -n "class MetadataResult\|def create" src/local_library/core/models.py`

Read the MetadataResult definition to understand its field order and whether it uses `@dataclass(frozen=True)` or similar. Note the exact line numbers for surgical modification.

**Step 2: Write failing test**

Add to `tests/unit/test_metadata.py` in the appropriate `TestMetadataHandler*` class (likely `TestMetadataHandlerValidation` or similar):

```python
class TestMetadataHandlerIssuedYear:
    """Tests for issued_year extraction in MetadataHandler.process()."""

    def test_process_populates_issued_year_from_date_parts(self) -> None:
        from local_library.ingestion.metadata import MetadataHandler
        handler = MetadataHandler()
        csl = {
            "type": "article-journal",
            "title": "Test",
            "author": [{"family": "Smith", "given": "J"}],
            "issued": {"date-parts": [[2023, 6, 15]]},
        }
        result = handler.process(csl)
        assert result.issued_year == 2023

    def test_process_issued_year_none_for_missing_date(self) -> None:
        from local_library.ingestion.metadata import MetadataHandler
        handler = MetadataHandler()
        csl = {
            "type": "article-journal",
            "title": "Test",
            "author": [{"family": "Smith", "given": "J"}],
        }
        result = handler.process(csl)
        assert result.issued_year is None

    def test_process_issued_year_none_for_literal_date(self) -> None:
        from local_library.ingestion.metadata import MetadataHandler
        handler = MetadataHandler()
        csl = {
            "type": "article-journal",
            "title": "Test",
            "author": [{"family": "Smith", "given": "J"}],
            "issued": {"literal": "Spring 2023"},
        }
        result = handler.process(csl)
        assert result.issued_year is None
```

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_metadata.py::TestMetadataHandlerIssuedYear -v`

Expected: `AttributeError` — `MetadataResult` has no attribute `issued_year`.

**Step 4: Add `issued_year` to `MetadataResult`**

In `src/local_library/core/models.py`, locate the `MetadataResult` dataclass definition (from Step 1). Add `issued_year: int | None = None` as a field. Place it immediately after `issued_date` for logical grouping.

If `MetadataResult` has a `@classmethod def create(...)`, add `issued_year: int | None = None` as a keyword argument to it and assign it to the created instance.

Example (adapt to the actual code):

```python
@dataclass(frozen=True)
class MetadataResult:
    csl_json: dict[str, Any]
    citekey: str
    title: str | None = None
    authors: str | None = None
    issued_date: str | None = None
    issued_year: int | None = None  # ← NEW
    validation_warnings: tuple[str, ...] = ()
    # (other fields)

    @classmethod
    def create(
        cls,
        csl_json: dict[str, Any],
        citekey: str,
        title: str | None = None,
        authors: str | None = None,
        issued_date: str | None = None,
        issued_year: int | None = None,  # ← NEW
        validation_warnings: Sequence[str] = (),
        # ... other args
    ) -> "MetadataResult":
        return cls(
            csl_json=csl_json,
            citekey=citekey,
            title=title,
            authors=authors,
            issued_date=issued_date,
            issued_year=issued_year,  # ← NEW
            validation_warnings=tuple(validation_warnings),
            # ... other assignments
        )
```

**Step 5: Populate `issued_year` in `MetadataHandler.process()`**

In `src/local_library/ingestion/metadata.py`, locate the `process()` method (around line 547). After the existing indexed-field extraction (lines 547-550), add:

```python
issued_date = self._extract_issued_date(csl_json)
issued_year = extract_year_from_csl(csl_json)  # ← NEW
```

Then pass `issued_year=issued_year` to `MetadataResult.create()` (line 552-560):

```python
return MetadataResult.create(
    csl_json=csl_json,
    citekey=citekey,
    title=title,
    authors=authors,
    issued_date=issued_date,
    issued_year=issued_year,  # ← NEW
    validation_warnings=warnings,
    author_list=author_list,
)
```

Add the `extract_year_from_csl` import at the top of `metadata.py` if `extract_year_from_csl` is module-level in the same file (it is, from Task 2, so no extra import needed).

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_metadata.py -v`

Expected: New tests pass, all existing tests continue to pass.

**Step 7: Lint**

Run: `uv run ruff check src/local_library/core/models.py src/local_library/ingestion/metadata.py tests/unit/test_metadata.py`
Run: `uv run ruff format --check src/local_library/core/models.py src/local_library/ingestion/metadata.py tests/unit/test_metadata.py`

Expected: Clean.

**Step 8: Commit**

```bash
git add src/local_library/core/models.py src/local_library/ingestion/metadata.py tests/unit/test_metadata.py
git commit -m "$(cat <<'EOF'
feat(metadata): add issued_year to MetadataResult

Extends MetadataResult with issued_year: int | None and populates it
in MetadataHandler.process() via the shared extract_year_from_csl
utility. Downstream write paths (_process_metadata,
_attempt_metadata_upgrade) will wire this through the storage layer in
subsequent tasks.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Add `issued_year` to Document model and storage write path

**Type:** Functionality (TDD — test-first)

**Files:**
- Modify: `src/local_library/core/models.py` (add `issued_year` to Document)
- Modify: `src/local_library/core/storage.py` (update `update_document_metadata()` signature, row-unpacking helper)
- Modify: `tests/unit/test_storage.py` (tests for issued_year read/write)

**Reference files for executor:**
- `src/local_library/core/models.py:47-95` — Document dataclass (field order matters for row unpacking)
- `src/local_library/core/storage.py:590-671` — `update_document_metadata()` signature and SQL
- `src/local_library/core/storage.py` — search for the helper that converts rows to Document (likely `_row_to_document()` or similar); every SELECT must include `issued_year` and the conversion must handle it

**Step 1: Find the row-to-Document conversion helper**

Run: `grep -n "Document(\|def _row_to\|def _to_document\|def get_document_by" src/local_library/core/storage.py | head -20`

Identify the function(s) that unpack rows into Document instances, and which SELECT statements would need `issued_year` added to the column list.

**Step 2: Write failing test**

Add to `tests/unit/test_storage.py`:

```python
class TestUpdateDocumentMetadataIssuedYear:
    """Tests for writing issued_year through update_document_metadata."""

    def test_update_persists_issued_year(self, temp_dir: Path) -> None:
        """update_document_metadata writes issued_year to the database."""
        from uuid import uuid4
        from local_library.core.storage import (
            get_connection, init_schema, create_document, update_document_metadata,
            get_document,
        )

        conn = get_connection(temp_dir / "test.db")
        init_schema(conn)
        doc_id = uuid4()
        create_document(
            conn,
            id=doc_id,
            original_path="/tmp/test.pdf",
            content_hash="abc123",
            storage_path="ab/cd/abc123.pdf",
        )

        update_document_metadata(
            conn,
            doc_id,
            issued_date="2023",
            issued_year=2023,
        )

        doc = get_document(conn, doc_id)
        assert doc.issued_year == 2023

    def test_update_preserves_issued_year_on_none(self, temp_dir: Path) -> None:
        """Passing issued_year=None does not overwrite an existing value (COALESCE)."""
        from uuid import uuid4
        from local_library.core.storage import (
            get_connection, init_schema, create_document, update_document_metadata,
            get_document,
        )

        conn = get_connection(temp_dir / "test.db")
        init_schema(conn)
        doc_id = uuid4()
        create_document(
            conn,
            id=doc_id,
            original_path="/tmp/test.pdf",
            content_hash="abc123",
            storage_path="ab/cd/abc123.pdf",
        )
        update_document_metadata(conn, doc_id, issued_date="2023", issued_year=2023)
        # Second update with issued_year=None should NOT clear the year
        update_document_metadata(conn, doc_id, title="New Title")
        doc = get_document(conn, doc_id)
        assert doc.issued_year == 2023
```

Adjust argument names in the test (e.g., `id=` vs `doc_id=`) to match the actual `create_document` signature — verify with `grep -n "def create_document" src/local_library/core/storage.py`.

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_storage.py::TestUpdateDocumentMetadataIssuedYear -v`

Expected: `TypeError: update_document_metadata() got an unexpected keyword argument 'issued_year'` or equivalent.

**Step 4: Add `issued_year` to Document dataclass**

In `src/local_library/core/models.py`, locate the Document dataclass definition (around lines 47-95). Add the field:

```python
issued_year: int | None = None
```

Place it **immediately after** `issued_date` (around line 68) for logical grouping. Verify the field order by reading a chunk of the dataclass first — the ORDER MATTERS if Document is used in positional construction elsewhere (check with `grep -rn "Document(" src/local_library/ tests/ | head`).

**Step 5: Update `update_document_metadata()` signature**

In `src/local_library/core/storage.py:590`, update the function:

```python
def update_document_metadata(
    conn: sqlite3.Connection,
    doc_id: UUID,
    citekey: str | None = None,
    csl_json: dict[str, Any] | None = None,
    title: str | None = None,
    authors: str | None = None,
    issued_date: str | None = None,
    issued_year: int | None = None,  # ← NEW
) -> Document:
```

In the SQL UPDATE statement (around lines 631-635), add the new column:

```python
UPDATE documents
SET citekey = COALESCE(?, citekey),
    csl_json = COALESCE(?, csl_json),
    title = COALESCE(?, title),
    authors = COALESCE(?, authors),
    issued_date = COALESCE(?, issued_date),
    issued_year = COALESCE(?, issued_year),
    updated_at = ?
WHERE id = ?
```

Add `issued_year` to the parameter tuple passed to `conn.execute(...)` in the matching position. Serialize `csl_json` via `json.dumps(...)` (the existing pattern). For `issued_year`, pass it directly as an int (SQLite handles INTEGER natively).

**Step 6: Update row-to-Document helper**

Wherever rows are converted to Document instances (found in Step 1), add `issued_year` to:
- The SELECT column list (every SELECT that produces a full Document)
- The Document constructor call (positional or keyword)

If the helper uses a dict-style construction (e.g., `Document(**row_dict)`), ensure the row_factory includes `issued_year`. If it's positional, update both the SELECT and the Document call consistently.

Common locations to check with `grep -n "SELECT .* FROM documents" src/local_library/core/storage.py` — every match needs `issued_year` added to its column list to keep Document construction consistent.

**Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storage.py -v`

Expected: New tests pass; existing tests pass (since Document dataclass change with default-None preserves backward compatibility).

**Step 8: Run full suite**

Run: `uv run pytest tests/unit/ --tb=short -q`

Expected: All tests pass. If any fail due to Document positional construction assuming old field order, fix those call sites to use keyword arguments.

**Step 9: Lint**

Run: `uv run ruff check src/local_library/core/ tests/unit/test_storage.py`
Run: `uv run ruff format --check src/local_library/core/ tests/unit/test_storage.py`

**Step 10: Commit**

```bash
git add src/local_library/core/models.py src/local_library/core/storage.py tests/unit/test_storage.py
git commit -m "$(cat <<'EOF'
feat(storage): wire issued_year through Document and update path

Adds issued_year: int | None to the Document dataclass and accepts it
as a keyword in update_document_metadata. SQL UPDATE uses COALESCE
pattern consistent with other indexed fields. SELECT column lists
updated for Document reconstruction.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Wire `issued_year` through Library write paths

**Type:** Functionality (TDD — test-first)

**Files:**
- Modify: `src/local_library/core/library.py` (3 write-path sites)
- Modify: `tests/unit/test_library.py` (add integration-style tests for each write path)

**Reference files for executor:**
- `src/local_library/core/library.py:869-904` — `_process_metadata()` (passes result to update_document_metadata)
- `src/local_library/core/library.py:575-650` — `_attempt_metadata_upgrade()` (passes result to update_document_metadata)
- `src/local_library/core/library.py:1069-1136` — `update_metadata()` (has inline extraction)

**Step 1: Write failing tests**

Add to `tests/unit/test_library.py`:

```python
class TestLibraryIssuedYearWritePaths:
    """Tests that issued_year is persisted through all three Library write paths."""

    def test_add_with_explicit_metadata_persists_issued_year(
        self, temp_dir: Path
    ) -> None:
        """Library.add() with explicit CSL-JSON metadata populates issued_year."""
        from local_library.core.library import Library

        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
            embed_on_add=False,
        ) as library:
            pdf_path = temp_dir / "test.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test content")

            metadata = {
                "type": "article-journal",
                "title": "Test Paper",
                "author": [{"family": "Smith", "given": "J"}],
                "issued": {"date-parts": [[2023, 6, 15]]},
            }

            with patch.object(library._extractors[0], "extract_and_validate") as mock_ext:
                mock_ext.return_value = MagicMock(text="content " * 20)
                result = library.add(str(pdf_path), metadata=metadata)

            doc = library.get(str(result.document.id))
            assert doc.issued_year == 2023

    def test_update_metadata_persists_issued_year(self, temp_dir: Path) -> None:
        """Library.update_metadata() populates issued_year from inline extraction."""
        from local_library.core.library import Library

        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
            embed_on_add=False,
        ) as library:
            pdf_path = temp_dir / "test.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test content")

            with patch.object(library._extractors[0], "extract_and_validate") as mock_ext:
                mock_ext.return_value = MagicMock(text="content " * 20)
                result = library.add(str(pdf_path))

            # Update metadata with a new CSL-JSON that has an issued year
            new_csl = {
                "type": "article-journal",
                "title": "Updated Title",
                "author": [{"family": "Smith"}],
                "issued": {"date-parts": [[1984]]},
            }
            library.update_metadata(result.document.id, csl_json=new_csl)

            doc = library.get(str(result.document.id))
            assert doc.issued_year == 1984
```

Adapt constructor kwargs to match actual Library signature — verify with `grep -n "def __init__" src/local_library/core/library.py`.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_library.py::TestLibraryIssuedYearWritePaths -v`

Expected: Tests fail — `doc.issued_year` is always `None` because no write path populates it yet.

**Step 3: Wire issued_year through `_process_metadata()`**

In `src/local_library/core/library.py:869-904`, locate the `update_document_metadata(...)` call (around line 896-904) and add `issued_year=result.issued_year`:

```python
return update_document_metadata(
    self._conn,
    doc.id,
    citekey=unique_citekey,
    csl_json=result.csl_json,
    title=result.title,
    authors=result.authors,
    issued_date=result.issued_date,
    issued_year=result.issued_year,  # ← NEW
)
```

**Step 4: Wire issued_year through `_attempt_metadata_upgrade()`**

In `src/local_library/core/library.py:575-650`, locate the `update_document_metadata(...)` call (around line 624-632) and add `issued_year=result.issued_year`:

```python
doc = update_document_metadata(
    self._conn,
    doc.id,
    citekey=unique_citekey,
    csl_json=result.csl_json,
    title=result.title,
    authors=result.authors,
    issued_date=result.issued_date,
    issued_year=result.issued_year,  # ← NEW
)
```

**Step 5: Wire issued_year through `update_metadata()` (inline extraction)**

In `src/local_library/core/library.py:1097-1136`, the inline extraction currently reads:

```python
issued_date = None

if csl_json:
    # ... existing extraction ...
    if "issued" in csl_json:
        issued = csl_json["issued"]
        if "date-parts" in issued and issued["date-parts"]:
            date_parts = issued["date-parts"][0]
            if date_parts:
                issued_date = str(date_parts[0])  # Year
```

Add `issued_year` extraction using the shared utility. At the top of the function (near the existing `issued_date = None` initializer), add:

```python
issued_year = None
```

In the `if csl_json:` branch, after the existing `issued_date` extraction, add:

```python
from local_library.ingestion.metadata import extract_year_from_csl
issued_year = extract_year_from_csl(csl_json)
```

Prefer placing the `from ... import extract_year_from_csl` at the top of `library.py` with the other ingestion imports for cleanliness. Run `grep -n "from local_library.ingestion" src/local_library/core/library.py` to find the import block and add it there.

Then pass `issued_year` to `update_document_metadata()` at line 1128:

```python
return update_document_metadata(
    self._conn,
    doc_id,
    citekey=citekey,
    csl_json=csl_json,
    title=title,
    authors=authors,
    issued_date=issued_date,
    issued_year=issued_year,  # ← NEW
)
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_library.py::TestLibraryIssuedYearWritePaths -v`

Expected: New tests pass.

**Step 7: Run full suite**

Run: `uv run pytest tests/unit/ --tb=short -q`

Expected: All tests pass.

**Step 8: Lint**

Run: `uv run ruff check src/local_library/core/library.py tests/unit/test_library.py`
Run: `uv run ruff format --check src/local_library/core/library.py tests/unit/test_library.py`

**Step 9: Commit**

```bash
git add src/local_library/core/library.py tests/unit/test_library.py
git commit -m "$(cat <<'EOF'
feat(library): populate issued_year in all write paths

Wires MetadataResult.issued_year through _process_metadata and
_attempt_metadata_upgrade, and adds extract_year_from_csl call to the
inline extraction in update_metadata. All three paths now consistently
populate the new issued_year column on writes.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-7) -->
<!-- START_TASK_6 -->
### Task 6: Expand `list_documents()` storage query with filter support

**Type:** Functionality (TDD — test-first)

**Files:**
- Modify: `src/local_library/core/storage.py` (extend `list_documents()`, add `_escape_like()` helper)
- Modify: `tests/unit/test_storage.py` (add filter tests)

**Reference files for executor:**
- `src/local_library/core/storage.py:494-514` — current `list_documents()` implementation
- SQLite LIKE operator with ESCAPE clause: `LIKE ? ESCAPE '\\'` in the query, with `%` and `_` escaped as `\%` and `\_` in the parameter

**Step 1: Write failing tests**

Add to `tests/unit/test_storage.py`:

```python
class TestListDocumentsFilters:
    """Tests for list_documents() with new filter parameters."""

    @pytest.fixture
    def seeded_conn(self, temp_dir: Path) -> sqlite3.Connection:
        """Create a connection with a few documents varying in year/author/title/citekey."""
        from uuid import uuid4
        from local_library.core.storage import (
            get_connection, init_schema, create_document, update_document_metadata,
        )
        conn = get_connection(temp_dir / "test.db")
        init_schema(conn)

        docs = [
            # (citekey, title, authors, issued_year)
            ("Zippel2023", "Analytical Methods", "Adam Zippel; Jane Doe", 2023),
            ("Zippel2019", "Computational Approaches", "Adam Zippel", 2019),
            ("Smith2023", "Machine Learning", "John Smith", 2023),
            ("Jones2020", "Statistical Theory", "Mary Jones", 2020),
            ("Noyear", "Untitled Work", "Anonymous", None),
            ("BourdieuPasseron1970", "Reproduction", "Pierre Bourdieu; Jean-Claude Passeron", 1970),
        ]
        for citekey, title, authors, year in docs:
            doc_id = uuid4()
            create_document(
                conn, id=doc_id,
                original_path=f"/tmp/{citekey}.pdf",
                content_hash=citekey,
                storage_path=f"ab/cd/{citekey}.pdf",
            )
            update_document_metadata(
                conn, doc_id,
                citekey=citekey,
                title=title,
                authors=authors,
                issued_year=year,
            )
        return conn

    def test_filter_by_year(self, seeded_conn: sqlite3.Connection) -> None:
        from local_library.core.storage import list_documents
        results = list_documents(seeded_conn, year=2023)
        assert {d.citekey for d in results} == {"Zippel2023", "Smith2023"}

    def test_filter_year_missing(self, seeded_conn: sqlite3.Connection) -> None:
        from local_library.core.storage import list_documents
        results = list_documents(seeded_conn, year_missing=True)
        assert [d.citekey for d in results] == ["Noyear"]

    def test_filter_year_and_year_missing_mutually_exclusive(
        self, seeded_conn: sqlite3.Connection
    ) -> None:
        from local_library.core.storage import list_documents
        with pytest.raises(ValueError, match="mutually exclusive"):
            list_documents(seeded_conn, year=2023, year_missing=True)

    def test_filter_author_contains_case_insensitive(
        self, seeded_conn: sqlite3.Connection
    ) -> None:
        from local_library.core.storage import list_documents
        results = list_documents(seeded_conn, author_contains="zippel")
        assert {d.citekey for d in results} == {"Zippel2023", "Zippel2019"}

    def test_filter_author_contains_partial(self, seeded_conn: sqlite3.Connection) -> None:
        from local_library.core.storage import list_documents
        results = list_documents(seeded_conn, author_contains="Jane")
        assert {d.citekey for d in results} == {"Zippel2023"}

    def test_filter_title_contains(self, seeded_conn: sqlite3.Connection) -> None:
        from local_library.core.storage import list_documents
        results = list_documents(seeded_conn, title_contains="Method")
        # "Analytical Methods" contains "Method" (case-insensitive)
        assert {d.citekey for d in results} == {"Zippel2023"}

    def test_filter_citekey_prefix(self, seeded_conn: sqlite3.Connection) -> None:
        from local_library.core.storage import list_documents
        results = list_documents(seeded_conn, citekey_prefix="Bourdieu")
        assert {d.citekey for d in results} == {"BourdieuPasseron1970"}

    def test_filter_citekey_prefix_case_insensitive(
        self, seeded_conn: sqlite3.Connection
    ) -> None:
        from local_library.core.storage import list_documents
        results = list_documents(seeded_conn, citekey_prefix="zippel")
        assert {d.citekey for d in results} == {"Zippel2023", "Zippel2019"}

    def test_filters_combine_with_and(self, seeded_conn: sqlite3.Connection) -> None:
        from local_library.core.storage import list_documents
        results = list_documents(seeded_conn, year=2023, author_contains="Zippel")
        assert {d.citekey for d in results} == {"Zippel2023"}

    def test_like_wildcard_in_input_is_escaped(
        self, seeded_conn: sqlite3.Connection
    ) -> None:
        """Percent signs in user input don't act as wildcards."""
        from local_library.core.storage import list_documents
        # '%' shouldn't match everything
        results = list_documents(seeded_conn, author_contains="%")
        assert results == []
        # '_' shouldn't act as single-char wildcard
        results = list_documents(seeded_conn, author_contains="_")
        assert results == []

    def test_no_filters_returns_all(self, seeded_conn: sqlite3.Connection) -> None:
        from local_library.core.storage import list_documents
        results = list_documents(seeded_conn)
        assert len(results) == 6

    def test_empty_string_filter_returns_all(
        self, seeded_conn: sqlite3.Connection
    ) -> None:
        """Empty string for *_contains filter is treated as no filter."""
        from local_library.core.storage import list_documents
        results = list_documents(seeded_conn, author_contains="")
        # Empty string is falsy — treated as no filter
        assert len(results) == 6
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_storage.py::TestListDocumentsFilters -v`

Expected: `TypeError: list_documents() got an unexpected keyword argument 'year'` (or similar).

**Step 3: Add `_escape_like()` helper and extend `list_documents()`**

In `src/local_library/core/storage.py`, locate `list_documents()` (around line 494-514). Add the helper function ABOVE it (or in a private helpers block) and replace the implementation:

```python
def _escape_like(value: str) -> str:
    """Escape special LIKE characters (%, _, \\) for literal matching.

    Args:
        value: Raw user input.

    Returns:
        Value with SQL LIKE metacharacters escaped.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_documents(
    conn: sqlite3.Connection,
    status: DocumentStatus | None = None,
    year: int | None = None,
    year_missing: bool = False,
    author_contains: str | None = None,
    title_contains: str | None = None,
    citekey_prefix: str | None = None,
) -> list[Document]:
    """List documents with optional filtering.

    Filters combine with AND semantics. Substring filters
    (author_contains, title_contains) use case-insensitive LIKE with
    metacharacter escaping to prevent accidental wildcard injection.
    citekey_prefix uses case-insensitive prefix match.

    Args:
        conn: Database connection.
        status: Exact status match (DocumentStatus enum).
        year: Exact year match against issued_year column.
        year_missing: If True, filter to issued_year IS NULL. Mutually
            exclusive with year.
        author_contains: Case-insensitive substring match on authors column.
        title_contains: Case-insensitive substring match on title column.
        citekey_prefix: Case-insensitive prefix match on citekey column.

    Returns:
        List of Document objects ordered by created_at DESC.

    Raises:
        ValueError: If both year and year_missing are provided.
    """
    if year is not None and year_missing:
        raise ValueError(
            "year and year_missing are mutually exclusive filters"
        )

    predicates: list[str] = []
    params: list[Any] = []

    if status is not None:
        predicates.append("status = ?")
        params.append(status.value)

    if year_missing:
        predicates.append("issued_year IS NULL")
    elif year is not None:
        predicates.append("issued_year = ?")
        params.append(year)

    if author_contains:
        predicates.append("LOWER(authors) LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(author_contains.lower())}%")

    if title_contains:
        predicates.append("LOWER(title) LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(title_contains.lower())}%")

    if citekey_prefix:
        predicates.append("LOWER(citekey) LIKE ? ESCAPE '\\'")
        params.append(f"{_escape_like(citekey_prefix.lower())}%")

    where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
    # Keep column order consistent with existing SELECT in this module
    # (executor: copy the existing column list from the original function body)
    query = f"SELECT <existing-columns> FROM documents{where} ORDER BY created_at DESC"

    rows = conn.execute(query, params).fetchall()
    return [<row_to_document>(row) for row in rows]
```

**Executor note:** The `<existing-columns>` and `<row_to_document>` placeholders must be replaced with the actual SELECT column list and row-conversion helper from the original `list_documents()` body. Read the original (lines 494-514) carefully and preserve everything except the WHERE construction.

Ensure `Any` is imported (`from typing import Any` — check existing imports).

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storage.py::TestListDocumentsFilters -v`

Expected: All 12 tests pass.

**Step 5: Run full suite**

Run: `uv run pytest tests/unit/ --tb=short -q`

Expected: All tests pass (existing list_documents callers unaffected since all new params default).

**Step 6: Lint**

Run: `uv run ruff check src/local_library/core/storage.py tests/unit/test_storage.py`
Run: `uv run ruff format --check src/local_library/core/storage.py tests/unit/test_storage.py`

**Step 7: Commit**

```bash
git add src/local_library/core/storage.py tests/unit/test_storage.py
git commit -m "$(cat <<'EOF'
feat(storage): add filter parameters to list_documents()

Adds year, year_missing, author_contains, title_contains, and
citekey_prefix to list_documents(). Filters combine with AND.
Substring filters use case-insensitive LIKE with metacharacter
escaping (%, _, \\) to prevent accidental wildcard injection.
Raises ValueError when year and year_missing are both provided.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Expand `Library.list()` signature with filter parameters

**Type:** Functionality (TDD — test-first)

**Files:**
- Modify: `src/local_library/core/library.py:1138-1147` (Library.list)
- Modify: `tests/unit/test_library.py` (filter pass-through tests)

**Reference files for executor:**
- `src/local_library/core/library.py:1138-1147` — current `Library.list()` implementation

**Step 1: Write failing tests**

Add to `tests/unit/test_library.py`:

```python
class TestLibraryListFilters:
    """Tests that Library.list() passes filters through to storage layer."""

    def test_year_filter_forwarded(self, temp_dir: Path) -> None:
        from local_library.core.library import Library
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            embed_on_add=False,
        ) as library:
            with patch(
                "local_library.core.library.list_documents"
            ) as mock_list:
                mock_list.return_value = []
                library.list(year=2023)
                mock_list.assert_called_once_with(
                    library._conn,
                    status=None,
                    year=2023,
                    year_missing=False,
                    author_contains=None,
                    title_contains=None,
                    citekey_prefix=None,
                )

    def test_mutual_exclusion_raises_value_error(self, temp_dir: Path) -> None:
        from local_library.core.library import Library
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            embed_on_add=False,
        ) as library:
            with pytest.raises(ValueError, match="mutually exclusive"):
                library.list(year=2023, year_missing=True)

    def test_multiple_filters_combined(self, temp_dir: Path) -> None:
        from local_library.core.library import Library
        from local_library.core.models import DocumentStatus
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            embed_on_add=False,
        ) as library:
            with patch(
                "local_library.core.library.list_documents"
            ) as mock_list:
                mock_list.return_value = []
                library.list(
                    status=DocumentStatus.READY,
                    year=2023,
                    author_contains="Zippel",
                )
                args, kwargs = mock_list.call_args
                assert kwargs["status"] == DocumentStatus.READY
                assert kwargs["year"] == 2023
                assert kwargs["author_contains"] == "Zippel"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_library.py::TestLibraryListFilters -v`

Expected: `TypeError: list() got an unexpected keyword argument 'year'`.

**Step 3: Update `Library.list()`**

In `src/local_library/core/library.py:1138-1147`, replace the method with:

```python
def list(
    self,
    status: DocumentStatus | None = None,
    year: int | None = None,
    year_missing: bool = False,
    author_contains: str | None = None,
    title_contains: str | None = None,
    citekey_prefix: str | None = None,
) -> list[Document]:
    """List documents with optional filtering.

    All filters are optional and combine with AND semantics.

    Args:
        status: Exact status match (DocumentStatus enum).
        year: Exact match against issued_year. Mutually exclusive with year_missing.
        year_missing: If True, return only documents with no extractable year.
        author_contains: Case-insensitive substring match on authors.
        title_contains: Case-insensitive substring match on title.
        citekey_prefix: Case-insensitive prefix match on citekey.

    Returns:
        List of Document objects ordered by created_at DESC.

    Raises:
        ValueError: If year and year_missing are both provided.
    """
    return list_documents(
        self._conn,
        status=status,
        year=year,
        year_missing=year_missing,
        author_contains=author_contains,
        title_contains=title_contains,
        citekey_prefix=citekey_prefix,
    )
```

The ValueError is raised by `list_documents()` itself (Task 6), so Library.list doesn't need its own check — just passes through.

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_library.py::TestLibraryListFilters -v`

Expected: All 3 tests pass.

**Step 5: Run full suite**

Run: `uv run pytest tests/unit/ --tb=short -q`

Expected: All pass.

**Step 6: Lint**

Run: `uv run ruff check src/local_library/core/library.py tests/unit/test_library.py`
Run: `uv run ruff format --check src/local_library/core/library.py tests/unit/test_library.py`

**Step 7: Commit**

```bash
git add src/local_library/core/library.py tests/unit/test_library.py
git commit -m "$(cat <<'EOF'
feat(library): add filter parameters to Library.list()

Exposes year, year_missing, author_contains, title_contains, and
citekey_prefix to callers of Library.list(). All filters pass through
to storage.list_documents() where AND semantics and escaping are
handled. Mutual exclusion of year/year_missing enforced at storage
layer.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_SUBCOMPONENT_D (tasks 8-9) -->
<!-- START_TASK_8 -->
### Task 8: Expand CLI `list` command with filter flags

**Type:** Functionality (TDD — test-first)

**Files:**
- Modify: `src/local_library/cli/list.py` (add flags, parsing, help text)
- Create: `tests/unit/test_cli_list.py` (new file following existing CLI test pattern)

**Reference files for executor:**
- `src/local_library/cli/list.py:28-100` — current `list_docs` function (Typer command)
- `tests/unit/test_cli_search.py:1-50` — CliRunner + mocked Library pattern
- `tests/unit/test_cli_ask.py` — another CLI test example
- The command currently accepts `--status`, `--limit`, `--all`, `--json` flags

**Step 1: Write failing tests**

Create `tests/unit/test_cli_list.py`:

```python
"""Tests for the CLI list command filter flags."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app

runner = CliRunner()


@pytest.fixture
def mock_library_for_list():
    """Provide a mock Library for list CLI testing."""
    with patch("local_library.cli.list.Library") as mock_cls:
        mock_lib = MagicMock()
        mock_lib.list.return_value = []
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_lib


class TestCliListFilters:
    def test_year_flag(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--year", "2023"])
        assert result.exit_code == 0
        _, kwargs = mock_library_for_list.list.call_args
        assert kwargs.get("year") == 2023

    def test_year_missing_flag(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--year-missing"])
        assert result.exit_code == 0
        _, kwargs = mock_library_for_list.list.call_args
        assert kwargs.get("year_missing") is True

    def test_year_and_year_missing_mutually_exclusive(
        self, mock_library_for_list
    ) -> None:
        result = runner.invoke(app, ["list", "--year", "2023", "--year-missing"])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower() or (
            "cannot" in result.output.lower() and "both" in result.output.lower()
        )

    def test_author_contains_flag(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--author-contains", "Zippel"])
        assert result.exit_code == 0
        _, kwargs = mock_library_for_list.list.call_args
        assert kwargs.get("author_contains") == "Zippel"

    def test_title_contains_flag(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--title-contains", "Methods"])
        assert result.exit_code == 0
        _, kwargs = mock_library_for_list.list.call_args
        assert kwargs.get("title_contains") == "Methods"

    def test_citekey_prefix_flag(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--citekey-prefix", "Bourdieu"])
        assert result.exit_code == 0
        _, kwargs = mock_library_for_list.list.call_args
        assert kwargs.get("citekey_prefix") == "Bourdieu"

    def test_help_mentions_new_flags(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--help"])
        assert result.exit_code == 0
        # Just check that flag names appear in help output
        assert "--year" in result.output
        assert "--author-contains" in result.output
        assert "--title-contains" in result.output
        assert "--citekey-prefix" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli_list.py -v`

Expected: Tests fail — flags don't exist, or `No such option: --year`.

**Step 3: Add flags to CLI list command**

In `src/local_library/cli/list.py:28-100`, extend the `list_docs` function signature:

```python
from typing import Annotated

import typer


def list_docs(
    status: Annotated[
        str | None,
        typer.Option("--status", help="Filter by status (ready, failed, needs_review, pending)"),
    ] = None,
    year: Annotated[
        int | None,
        typer.Option("--year", help="Filter by publication year (e.g., 2023)"),
    ] = None,
    year_missing: Annotated[
        bool,
        typer.Option("--year-missing", help="Show only documents with no extractable year"),
    ] = False,
    author_contains: Annotated[
        str | None,
        typer.Option("--author-contains", help="Filter authors containing TEXT (case-insensitive)"),
    ] = None,
    title_contains: Annotated[
        str | None,
        typer.Option("--title-contains", help="Filter titles containing TEXT (case-insensitive)"),
    ] = None,
    citekey_prefix: Annotated[
        str | None,
        typer.Option("--citekey-prefix", help="Filter citekeys starting with TEXT (case-insensitive)"),
    ] = None,
    limit: Annotated[...] = None,  # existing
    show_all: Annotated[...] = False,  # existing
    json_output: Annotated[...] = False,  # existing
) -> None:
```

Enforce mutual exclusion early (before opening the Library) with a CLI-friendly error:

```python
if year is not None and year_missing:
    typer.echo(
        "Error: --year and --year-missing are mutually exclusive.",
        err=True,
    )
    raise typer.Exit(code=2)
```

In the body of the function, when calling `lib.list(...)`, pass the new filters through:

```python
docs = lib.list(
    status=status_filter,
    year=year,
    year_missing=year_missing,
    author_contains=author_contains,
    title_contains=title_contains,
    citekey_prefix=citekey_prefix,
)
```

Preserve the existing `--status` parsing (to DocumentStatus enum) and all existing behavior (pagination, `--json`, etc.).

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_list.py -v`

Expected: All 7 tests pass.

**Step 5: Run full suite**

Run: `uv run pytest tests/unit/ --tb=short -q`

Expected: All tests pass.

**Step 6: Manual smoke test**

Run: `uv run local-library list --help`

Expected: Help text displays all new flags with useful descriptions. Visually inspect.

**Step 7: Lint**

Run: `uv run ruff check src/local_library/cli/list.py tests/unit/test_cli_list.py`
Run: `uv run ruff format --check src/local_library/cli/list.py tests/unit/test_cli_list.py`

**Step 8: Commit**

```bash
git add src/local_library/cli/list.py tests/unit/test_cli_list.py
git commit -m "$(cat <<'EOF'
feat(cli): add filter flags to local-library list

Adds --year, --year-missing, --author-contains, --title-contains, and
--citekey-prefix flags. Filters combine with AND, passed through to
Library.list(). Mutual exclusion of --year and --year-missing produces
a clear CLI error with exit code 2.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_8 -->

<!-- START_TASK_9 -->
### Task 9: Expand MCP `list_documents` tool with filter parameters

**Type:** Functionality (TDD — test-first)

**Files:**
- Modify: `src/local_library/mcp/server.py` (extend `list_documents` tool)
- Modify: `tests/unit/test_mcp_server.py` (extend `TestListDocuments` class)

**Reference files for executor:**
- `src/local_library/mcp/server.py:158-189` — current `list_documents` tool definition
- `tests/unit/test_mcp_server.py` — existing `TestListDocuments` class

**Step 1: Write failing tests**

Add to the existing `TestListDocuments` class in `tests/unit/test_mcp_server.py`:

```python
def test_year_parameter_forwarded(self) -> None:
    """year parameter is forwarded to Library.list()."""
    self.mock_library.list.return_value = []
    list_documents(year=2023)
    _, kwargs = self.mock_library.list.call_args
    assert kwargs.get("year") == 2023

def test_year_missing_parameter_forwarded(self) -> None:
    """year_missing parameter is forwarded to Library.list()."""
    self.mock_library.list.return_value = []
    list_documents(year_missing=True)
    _, kwargs = self.mock_library.list.call_args
    assert kwargs.get("year_missing") is True

def test_author_contains_forwarded(self) -> None:
    self.mock_library.list.return_value = []
    list_documents(author_contains="Zippel")
    _, kwargs = self.mock_library.list.call_args
    assert kwargs.get("author_contains") == "Zippel"

def test_title_contains_forwarded(self) -> None:
    self.mock_library.list.return_value = []
    list_documents(title_contains="Methods")
    _, kwargs = self.mock_library.list.call_args
    assert kwargs.get("title_contains") == "Methods"

def test_citekey_prefix_forwarded(self) -> None:
    self.mock_library.list.return_value = []
    list_documents(citekey_prefix="Bourdieu")
    _, kwargs = self.mock_library.list.call_args
    assert kwargs.get("citekey_prefix") == "Bourdieu"

def test_year_and_year_missing_returns_tool_error(self) -> None:
    """Mutual exclusion surfaces as a tool-level error to Claude."""
    result = list_documents(year=2023, year_missing=True)
    assert result.startswith("Error: ")
    assert "mutually exclusive" in result.lower()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_mcp_server.py::TestListDocuments -v`

Expected: Tests fail — new params don't exist on `list_documents`.

**Step 3: Extend the MCP tool**

In `src/local_library/mcp/server.py:158-189`, replace the `list_documents` tool:

```python
@mcp.tool(
    description=(
        "List documents in the library with optional filtering. Returns a "
        "markdown table with citekey, title, authors, status, and embedding "
        "status. Filters combine with AND semantics. Filter options: "
        "status (ready/failed/needs_review/pending), year (e.g., 2023), "
        "year_missing (documents with no extractable year), author_contains "
        "(case-insensitive substring match on authors), title_contains "
        "(case-insensitive substring match on titles), citekey_prefix "
        "(case-insensitive prefix match on citekeys). "
        "Errors prefixed with 'USER-FACING ERROR' should be reported to the "
        "user rather than worked around."
    )
)
def list_documents(
    status: str | None = None,
    year: int | None = None,
    year_missing: bool = False,
    author_contains: str | None = None,
    title_contains: str | None = None,
    citekey_prefix: str | None = None,
    limit: int = 20,
) -> str:
    """List documents in the library with optional filters.

    Args:
        status: One of "ready", "failed", "needs_review", "pending".
        year: Filter to documents issued in the given year.
        year_missing: Filter to documents with no extractable year
            (mutually exclusive with year).
        author_contains: Case-insensitive substring match on authors.
        title_contains: Case-insensitive substring match on titles.
        citekey_prefix: Case-insensitive prefix match on citekeys.
        limit: Maximum results to return (1-100, default 20).
    """
    assert _library is not None, "Library not initialized"

    # Clamp limit
    limit = max(1, min(limit, 100))

    # Validate status filter (existing)
    status_filter = None
    if status:
        if status.lower() not in VALID_STATUSES:
            return format_tool_error(
                f"invalid status: {status}. "
                f"Expected one of: {', '.join(VALID_STATUSES)}"
            )
        status_filter = DocumentStatus(status.lower())

    try:
        all_docs = _library.list(
            status=status_filter,
            year=year,
            year_missing=year_missing,
            author_contains=author_contains,
            title_contains=title_contains,
            citekey_prefix=citekey_prefix,
        )
        total = len(all_docs)
        displayed = all_docs[:limit]
        return format_document_list(displayed, total)
    except ValueError as e:
        # Mutual exclusion or similar filter validation errors
        return format_tool_error(str(e))
    except Exception as e:
        logger.exception("Error listing documents")
        return format_user_error(f"Failed to list documents: {e}")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_mcp_server.py::TestListDocuments -v`

Expected: All existing + new tests pass.

**Step 5: Run full suite**

Run: `uv run pytest tests/unit/ --tb=short -q`

Expected: All tests pass.

**Step 6: Lint**

Run: `uv run ruff check src/local_library/mcp/server.py tests/unit/test_mcp_server.py`
Run: `uv run ruff format --check src/local_library/mcp/server.py tests/unit/test_mcp_server.py`

**Step 7: Commit**

```bash
git add src/local_library/mcp/server.py tests/unit/test_mcp_server.py
git commit -m "$(cat <<'EOF'
feat(mcp): add filter parameters to list_documents tool

Adds year, year_missing, author_contains, title_contains, and
citekey_prefix parameters to the MCP list_documents tool. Tool
description enumerates all filters so Claude sees what's queryable.
Mutual exclusion of year/year_missing surfaces as a tool-level error
to keep the server from crashing on bad parameter combinations.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_9 -->
<!-- END_SUBCOMPONENT_D -->

<!-- START_TASK_10 -->
### Task 10: Documentation updates

**Type:** Infrastructure

**Files:**
- Modify: `CLAUDE.md` (root — Commands section)
- Modify: `src/local_library/core/CLAUDE.md` (Library.list contract, freshness date)
- Modify: `src/local_library/cli/CLAUDE.md` (new list flags, freshness date)
- Modify: `src/local_library/mcp/CLAUDE.md` (list_documents tool contract, freshness date)

**Step 1: Update root `CLAUDE.md` Commands section**

Locate the `uv run local-library list ...` entries (around line 220-225 based on the existing layout). Add entries for the new flags, mirroring the style of existing entries:

```markdown
- `uv run local-library list --year 2023` - Filter by publication year
- `uv run local-library list --year-missing` - Show documents with no extractable year
- `uv run local-library list --author-contains Zippel` - Filter authors (case-insensitive substring)
- `uv run local-library list --title-contains methods` - Filter titles (case-insensitive substring)
- `uv run local-library list --citekey-prefix Bourdieu` - Filter citekeys (case-insensitive prefix)
```

**Step 2: Update `core/CLAUDE.md`**

Update `Last verified:` at the top to 2026-04-16.

In the `Contracts > Guarantees` section, find the `Library.list(...)` entry (if present) or add:

```markdown
- Library.list(status, year, year_missing, author_contains, title_contains, citekey_prefix)
  returns documents matching all provided filters (AND semantics). `year` and
  `year_missing` are mutually exclusive; passing both raises ValueError. Substring
  filters (`author_contains`, `title_contains`) are case-insensitive with LIKE
  metacharacter escaping. `citekey_prefix` is case-insensitive prefix match.
```

In the `Key Files` section, update the `library.py` line to mention the expanded list signature.

In `Key Decisions`, add a bullet:

```markdown
- **Denormalized `issued_year` column**: `documents.issued_year INTEGER` added in schema v4.
  Populated at write time from `csl_json["issued"]` via `extract_year_from_csl()` in
  `metadata.py`. Index `idx_documents_issued_year` enables efficient year-equality
  queries. NULL when year is unextractable; the `year_missing` filter surfaces these
  records for review.
```

**Step 3: Update `cli/CLAUDE.md`**

Update `Last verified:` to 2026-04-16.

In the `list` command entry, document the new flags. Follow the exact format of existing command entries in this file.

**Step 4: Update `mcp/CLAUDE.md`**

Update `Last verified:` to 2026-04-16.

In the tool contracts section, update the `list_documents` entry:

```markdown
- `list_documents(status, year, year_missing, author_contains, title_contains, citekey_prefix, limit)`:
  markdown table of documents matching provided filters. Filters combine with AND.
  `year` and `year_missing` are mutually exclusive (returns tool-level error if both
  provided). Substring filters (`author_contains`, `title_contains`) are
  case-insensitive substring matches. `citekey_prefix` is case-insensitive prefix.
```

In the `Dependencies > Uses` line, add `core.models (DocumentStatus)` if it isn't already listed (it should be from the MCP work).

**Step 5: Lint**

Run: `uv run ruff check src/local_library/`

Expected: Clean.

**Step 6: Run full suite one final time**

Run: `uv run pytest tests/unit/ --tb=short -q`

Expected: All tests pass (should be around 1173 baseline + ~35-40 new tests).

**Step 7: Commit**

```bash
git add CLAUDE.md src/local_library/core/CLAUDE.md src/local_library/cli/CLAUDE.md src/local_library/mcp/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document list filter expansion and issued_year column

Updates root CLAUDE.md Commands section with new list filter flags.
Updates core/CLAUDE.md with Library.list() expanded contract and
issued_year denormalization decision. Updates cli/CLAUDE.md with new
list flags. Updates mcp/CLAUDE.md with list_documents tool contract
for the new filter parameters.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_10 -->

---

**Phase 1 complete when:**
- Schema is at v4 with `issued_year` column and index
- `_migrate_v3_to_v4()` runs automatically via `init_schema()` with informational logging
- `extract_year_from_csl()` shared utility consumed by `_extract_year_for_citekey` and `MetadataHandler`
- `MetadataResult` carries `issued_year`; all three Library write paths populate it
- `Library.list()` accepts five new filter parameters; `list_documents()` builds dynamic WHERE with LIKE escaping
- CLI `list` command exposes all filter flags with help text
- MCP `list_documents` tool exposes all filter parameters with updated tool description
- Migration, filter, and integration tests pass (~35-40 new tests)
- Full unit suite passes (baseline 1173 + new tests, no regressions)
- CLAUDE.md files updated with freshness date 2026-04-16
