# Phase 5: Database Schema Update

**Goal:** Add indexed columns to documents table and implement citekey collision handling.

**Dependencies:** Phases 1-4

**Done when:** Schema migrated, CRUD operations work with new columns, citekey collisions handled correctly.

---

<!-- START_TASK_1 -->
### Task 1: Add indexed columns to schema

**Files:**
- Modify: `src/local_library/core/storage.py`

**Step 1: Update SCHEMA_VERSION**

Update line 17:
```python
SCHEMA_VERSION = 2
```

**Step 2: Update SCHEMA with new columns**

Update the documents table in the SCHEMA string (around lines 24-37) to add the new columns:

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    extracted_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    citekey TEXT,
    csl_json TEXT,
    title TEXT,
    authors TEXT,
    issued_date TEXT,
    error_message TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_original_path ON documents(original_path);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_citekey ON documents(citekey);
CREATE INDEX IF NOT EXISTS idx_documents_title ON documents(title);
CREATE INDEX IF NOT EXISTS idx_documents_issued_date ON documents(issued_date);
"""
```

**Step 3: Add migration function**

Add after `init_schema()` function (around line 101):

```python


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Migrate database schema to current version.

    Handles incremental migrations from older schema versions.

    Args:
        conn: Database connection
    """
    cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
    row = cursor.fetchone()
    current_version = row["version"] if row else 0

    if current_version < 2:
        # Migration to v2: Add indexed metadata columns
        _migrate_v1_to_v2(conn)

    # Update schema version
    conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
    conn.commit()


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate from schema v1 to v2: add indexed metadata columns.

    Adds title, authors, issued_date columns and their indexes.
    """
    # Check if columns already exist (idempotent)
    cursor = conn.execute("PRAGMA table_info(documents)")
    existing_columns = {row["name"] for row in cursor.fetchall()}

    if "title" not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN title TEXT")
    if "authors" not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN authors TEXT")
    if "issued_date" not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN issued_date TEXT")

    # Create indexes (IF NOT EXISTS makes this idempotent)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_title ON documents(title)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_issued_date ON documents(issued_date)")

    conn.commit()
```

**Step 4: Update init_schema to call migration**

Update `init_schema()` to call migration after creating tables:

```python
def init_schema(conn: sqlite3.Connection) -> None:
    """Initialize the database schema.

    Creates tables and indexes if they don't exist.
    Safe to call multiple times (idempotent).
    Automatically migrates from older schema versions.

    Args:
        conn: Database connection
    """
    conn.executescript(SCHEMA)

    # Check/set schema version
    cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    elif row["version"] < SCHEMA_VERSION:
        # Need to migrate
        migrate_schema(conn)
```

**Step 5: Verify schema creation**

Run:
```bash
uv run python -c "
import sqlite3
from pathlib import Path
import tempfile
from local_library.core.storage import get_connection, init_schema

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / 'test.db'
    conn = get_connection(db_path)
    init_schema(conn)

    cursor = conn.execute('PRAGMA table_info(documents)')
    columns = [row[1] for row in cursor.fetchall()]
    print('Columns:', columns)
    assert 'title' in columns
    assert 'authors' in columns
    assert 'issued_date' in columns
    print('Schema OK')
"
```

Expected: `Schema OK` with all columns listed.

**Step 6: Commit**

```bash
git add src/local_library/core/storage.py
git commit -m "feat(storage): add indexed metadata columns to schema

Adds title, authors, issued_date columns with indexes.
Includes migration from schema v1 to v2.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update Document model for new fields

**Files:**
- Modify: `src/local_library/core/models.py`

**Step 1: Update Document dataclass**

Add the new fields to the Document dataclass (around lines 37-44):

```python
    # Nullable fields - populated after extraction or metadata processing
    extracted_path: str | None = None  # Path to extracted markdown
    citekey: str | None = None  # BetterBibTeX-style citation key
    csl_json: dict[str, Any] | None = None  # Bibliographic metadata
    title: str | None = None  # Extracted title for search
    authors: str | None = None  # Formatted author string for search
    issued_date: str | None = None  # ISO date or year for search

    # Error tracking for failed documents
    error_message: str | None = None
    error_code: str | None = None
```

**Step 2: Verify model works**

Run:
```bash
uv run python -c "
from local_library.core.models import Document
doc = Document.create_pending('/path.pdf', 'hash', '/storage.pdf')
print(f'title: {doc.title}, authors: {doc.authors}, issued_date: {doc.issued_date}')
"
```

Expected: `title: None, authors: None, issued_date: None`

**Step 3: Commit**

```bash
git add src/local_library/core/models.py
git commit -m "feat(core): add indexed metadata fields to Document model

Adds title, authors, issued_date fields for search indexing.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update _row_to_document for new fields

**Files:**
- Modify: `src/local_library/core/storage.py`

**Step 1: Update _row_to_document function**

Update the `_row_to_document` function (around lines 104-123) to include the new fields:

```python
def _row_to_document(row: sqlite3.Row) -> Document:
    """Convert a database row to a Document object."""
    csl_json = None
    if row["csl_json"]:
        csl_json = json.loads(row["csl_json"])

    return Document(
        id=UUID(row["id"]),
        original_path=row["original_path"],
        content_hash=row["content_hash"],
        storage_path=row["storage_path"],
        extracted_path=row["extracted_path"],
        status=DocumentStatus(row["status"]),
        citekey=row["citekey"],
        csl_json=csl_json,
        title=row["title"],
        authors=row["authors"],
        issued_date=row["issued_date"],
        error_message=row["error_message"],
        error_code=row["error_code"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
```

**Step 2: Commit**

```bash
git add src/local_library/core/storage.py
git commit -m "feat(storage): update _row_to_document for indexed fields

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Implement update_document_metadata function

**Files:**
- Modify: `src/local_library/core/storage.py`

**Step 1: Add update_document_metadata function**

Add after `update_document_status` function (around line 349):

```python


def update_document_metadata(
    conn: sqlite3.Connection,
    doc_id: UUID,
    citekey: str | None = None,
    csl_json: dict[str, Any] | None = None,
    title: str | None = None,
    authors: str | None = None,
    issued_date: str | None = None,
) -> Document:
    """Update a document's metadata fields.

    Args:
        conn: Database connection
        doc_id: Document UUID
        citekey: Citation key
        csl_json: Full CSL-JSON metadata
        title: Extracted title
        authors: Formatted author string
        issued_date: ISO date or year

    Returns:
        Updated Document

    Raises:
        LookupError: If document not found
        StorageError: If database operation fails
    """
    now = datetime.now(timezone.utc)

    # Serialize csl_json if provided
    csl_json_str = json.dumps(csl_json) if csl_json else None

    try:
        cursor = conn.execute(
            """
            UPDATE documents
            SET citekey = ?, csl_json = ?, title = ?, authors = ?,
                issued_date = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                citekey,
                csl_json_str,
                title,
                authors,
                issued_date,
                now.isoformat(),
                str(doc_id),
            ),
        )
        conn.commit()

        if cursor.rowcount == 0:
            raise LookupError(
                f"document not found: {doc_id}",
                ErrorCode.NOT_FOUND,
                details={"doc_id": str(doc_id)},
            )

        doc = get_document_by_id(conn, doc_id)
        if doc is None:
            raise LookupError(
                f"document not found after update: {doc_id}",
                ErrorCode.NOT_FOUND,
            )
        return doc

    except sqlite3.Error as e:
        raise StorageError(
            f"failed to update document metadata: {e}",
            ErrorCode.STORAGE_DATABASE_ERROR,
            details={"doc_id": str(doc_id)},
        ) from e
```

**Step 2: Verify function works**

Run:
```bash
uv run python -c "
import tempfile
from pathlib import Path
from local_library.core.storage import (
    get_connection, init_schema, create_document,
    update_document_metadata, get_document_by_id
)

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / 'test.db'
    conn = get_connection(db_path)
    init_schema(conn)

    doc = create_document(conn, '/test.pdf', 'abc123', '/storage/ab/c1/abc123.pdf')
    print(f'Created: {doc.id}, title={doc.title}')

    updated = update_document_metadata(
        conn, doc.id,
        citekey='Smith2020Test',
        title='Test Article',
        authors='Smith, J.',
        issued_date='2020'
    )
    print(f'Updated: citekey={updated.citekey}, title={updated.title}')
"
```

Expected: Shows created document with None title, then updated with metadata.

**Step 3: Commit**

```bash
git add src/local_library/core/storage.py
git commit -m "feat(storage): add update_document_metadata function

Updates citekey, csl_json, title, authors, issued_date fields.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Implement citekey collision detection

**Files:**
- Modify: `src/local_library/core/storage.py`

**Step 1: Add get_document_by_citekey function**

Add after `get_document_by_path` function (around line 236):

```python


def get_document_by_citekey(conn: sqlite3.Connection, citekey: str) -> Document | None:
    """Get a document by its citekey.

    Args:
        conn: Database connection
        citekey: Citation key to look up

    Returns:
        Document if found, None otherwise
    """
    cursor = conn.execute(
        "SELECT * FROM documents WHERE citekey = ?",
        (citekey,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_document(row)


def get_unique_citekey(conn: sqlite3.Connection, base_citekey: str) -> str:
    """Get a unique citekey, adding suffix if necessary.

    If base_citekey exists, tries base_citekey + 'a', 'b', 'c', etc.

    Args:
        conn: Database connection
        base_citekey: Desired citekey

    Returns:
        Unique citekey (may be base_citekey or with suffix)
    """
    # Check if base key is available
    if get_document_by_citekey(conn, base_citekey) is None:
        return base_citekey

    # Try suffixes a-z
    for suffix in "abcdefghijklmnopqrstuvwxyz":
        candidate = f"{base_citekey}{suffix}"
        if get_document_by_citekey(conn, candidate) is None:
            return candidate

    # If all a-z exhausted, use numeric suffix
    counter = 1
    while True:
        candidate = f"{base_citekey}{counter}"
        if get_document_by_citekey(conn, candidate) is None:
            return candidate
        counter += 1
```

**Step 2: Verify collision detection works**

Run:
```bash
uv run python -c "
import tempfile
from pathlib import Path
from local_library.core.storage import (
    get_connection, init_schema, create_document,
    update_document_metadata, get_unique_citekey
)

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / 'test.db'
    conn = get_connection(db_path)
    init_schema(conn)

    # Create first document
    doc1 = create_document(conn, '/test1.pdf', 'hash1', '/storage/ha/sh/hash1.pdf')
    key1 = get_unique_citekey(conn, 'Smith2020Test')
    update_document_metadata(conn, doc1.id, citekey=key1)
    print(f'Doc 1: {key1}')

    # Create second with same base key
    doc2 = create_document(conn, '/test2.pdf', 'hash2', '/storage/ha/sh/hash2.pdf')
    key2 = get_unique_citekey(conn, 'Smith2020Test')
    update_document_metadata(conn, doc2.id, citekey=key2)
    print(f'Doc 2: {key2}')

    # Third
    doc3 = create_document(conn, '/test3.pdf', 'hash3', '/storage/ha/sh/hash3.pdf')
    key3 = get_unique_citekey(conn, 'Smith2020Test')
    update_document_metadata(conn, doc3.id, citekey=key3)
    print(f'Doc 3: {key3}')
"
```

Expected:
```
Doc 1: Smith2020Test
Doc 2: Smith2020Testa
Doc 3: Smith2020Testb
```

**Step 3: Commit**

```bash
git add src/local_library/core/storage.py
git commit -m "feat(storage): add citekey collision detection

get_document_by_citekey for lookup, get_unique_citekey for
generating unique keys with a/b/c suffixes.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Write tests for storage updates

**Files:**
- Modify: `tests/unit/test_storage.py`

**Step 1: Add tests for new storage functions**

Add to `tests/unit/test_storage.py`:

```python


class TestMetadataStorage:
    """Tests for metadata storage functions."""

    def test_update_document_metadata(self, db_conn: sqlite3.Connection) -> None:
        """update_document_metadata should update all metadata fields."""
        from local_library.core.storage import (
            create_document,
            get_document_by_id,
            update_document_metadata,
        )

        doc = create_document(db_conn, "/test.pdf", "hash123", "/storage/path.pdf")

        updated = update_document_metadata(
            db_conn,
            doc.id,
            citekey="Smith2020Test",
            csl_json={"type": "article-journal", "title": "Test"},
            title="Test Article",
            authors="Smith, J.",
            issued_date="2020",
        )

        assert updated.citekey == "Smith2020Test"
        assert updated.csl_json == {"type": "article-journal", "title": "Test"}
        assert updated.title == "Test Article"
        assert updated.authors == "Smith, J."
        assert updated.issued_date == "2020"

    def test_update_document_metadata_partial(self, db_conn: sqlite3.Connection) -> None:
        """update_document_metadata should allow partial updates."""
        from local_library.core.storage import create_document, update_document_metadata

        doc = create_document(db_conn, "/test.pdf", "hash123", "/storage/path.pdf")

        updated = update_document_metadata(
            db_conn,
            doc.id,
            citekey="Key2020",
            title="Title Only",
        )

        assert updated.citekey == "Key2020"
        assert updated.title == "Title Only"
        assert updated.authors is None

    def test_update_document_metadata_not_found(self, db_conn: sqlite3.Connection) -> None:
        """update_document_metadata should raise for missing document."""
        from uuid import uuid4

        from local_library.core.errors import LookupError
        from local_library.core.storage import update_document_metadata

        with pytest.raises(LookupError):
            update_document_metadata(db_conn, uuid4(), citekey="Test")


class TestCitekeyCollision:
    """Tests for citekey collision handling."""

    def test_get_document_by_citekey_found(self, db_conn: sqlite3.Connection) -> None:
        """get_document_by_citekey should return document with matching key."""
        from local_library.core.storage import (
            create_document,
            get_document_by_citekey,
            update_document_metadata,
        )

        doc = create_document(db_conn, "/test.pdf", "hash123", "/storage/path.pdf")
        update_document_metadata(db_conn, doc.id, citekey="UniqueKey2020")

        found = get_document_by_citekey(db_conn, "UniqueKey2020")

        assert found is not None
        assert found.id == doc.id

    def test_get_document_by_citekey_not_found(self, db_conn: sqlite3.Connection) -> None:
        """get_document_by_citekey should return None for missing key."""
        from local_library.core.storage import get_document_by_citekey

        result = get_document_by_citekey(db_conn, "NonexistentKey")

        assert result is None

    def test_get_unique_citekey_available(self, db_conn: sqlite3.Connection) -> None:
        """get_unique_citekey should return base key if available."""
        from local_library.core.storage import get_unique_citekey

        result = get_unique_citekey(db_conn, "Smith2020Test")

        assert result == "Smith2020Test"

    def test_get_unique_citekey_collision(self, db_conn: sqlite3.Connection) -> None:
        """get_unique_citekey should add suffix for collision."""
        from local_library.core.storage import (
            create_document,
            get_unique_citekey,
            update_document_metadata,
        )

        # Create document with base key
        doc1 = create_document(db_conn, "/test1.pdf", "hash1", "/storage/1.pdf")
        update_document_metadata(db_conn, doc1.id, citekey="Smith2020Test")

        # Request same key
        result = get_unique_citekey(db_conn, "Smith2020Test")

        assert result == "Smith2020Testa"

    def test_get_unique_citekey_multiple_collisions(
        self, db_conn: sqlite3.Connection
    ) -> None:
        """get_unique_citekey should increment suffix for multiple collisions."""
        from local_library.core.storage import (
            create_document,
            get_unique_citekey,
            update_document_metadata,
        )

        # Create documents with base and first suffix
        doc1 = create_document(db_conn, "/test1.pdf", "hash1", "/storage/1.pdf")
        update_document_metadata(db_conn, doc1.id, citekey="Key2020")

        doc2 = create_document(db_conn, "/test2.pdf", "hash2", "/storage/2.pdf")
        update_document_metadata(db_conn, doc2.id, citekey="Key2020a")

        # Request same base key
        result = get_unique_citekey(db_conn, "Key2020")

        assert result == "Key2020b"
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/unit/test_storage.py -v -k "Metadata or Citekey"
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add tests/unit/test_storage.py
git commit -m "test(storage): add tests for metadata storage and citekey collision

Tests update_document_metadata, get_document_by_citekey,
and get_unique_citekey functions.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Run full test suite and verify Phase 5 complete

**Files:** None (verification only)

**Step 1: Run full test suite**

Run:
```bash
uv run pytest -v
```

Expected: All tests pass.

**Step 2: Verify lint passes**

Run:
```bash
uv run ruff check src/local_library/core/storage.py src/local_library/core/models.py tests/unit/test_storage.py
```

Expected: No errors.

**Step 3: Commit phase completion**

```bash
git add -A
git commit -m "chore: Phase 5 complete - database schema update

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_7 -->

---

## Phase 5 Completion Criteria

- [ ] Schema v2 adds title, authors, issued_date columns
- [ ] Migration from v1 to v2 works for existing databases
- [ ] Indexes created on title and issued_date
- [ ] Document model includes new fields
- [ ] _row_to_document maps new columns
- [ ] update_document_metadata() updates all metadata fields
- [ ] get_document_by_citekey() for citekey lookup
- [ ] get_unique_citekey() handles collision with a/b/c suffixes
- [ ] All tests pass
