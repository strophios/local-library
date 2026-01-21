# Phase 3: Storage Layer

## Goal
Implement SQLite schema and CRUD operations for document records.

---

<!-- START_TASK_1 -->
### Task 1: Create storage module with schema initialization

**Files:**
- Create: `src/local_library/core/storage.py`

**Step 1: Create the storage module with connection management and schema**

```python
"""SQLite storage layer for document records."""

# pattern: Imperative Shell

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator
from uuid import UUID

from local_library.core.errors import ErrorCode, LookupError, StorageError
from local_library.core.models import Document, DocumentStatus


# Schema version for migrations
SCHEMA_VERSION = 1

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
    error_message TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_original_path ON documents(original_path);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_citekey ON documents(citekey);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Create a database connection with recommended settings.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        Configured SQLite connection
    """
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # Enable dict-like row access
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # Better concurrent access
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Context manager for database transactions.

    Commits on success, rolls back on exception.

    Args:
        conn: Database connection

    Yields:
        The same connection for use in the transaction
    """
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_schema(conn: sqlite3.Connection) -> None:
    """Initialize the database schema.

    Creates tables and indexes if they don't exist.
    Safe to call multiple times (idempotent).

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


def _row_to_document(row: sqlite3.Row) -> Document:
    """Convert a database row to a Document object."""
    import json

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
        error_message=row["error_message"],
        error_code=row["error_code"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
```

**Step 2: Verify module is importable**

Run: `uv run python -c "from local_library.core.storage import get_connection, init_schema; print('Storage module loaded')"`

Expected: `Storage module loaded`

**Step 3: Commit**

```bash
git add src/local_library/core/storage.py
git commit -m "feat: add storage module with schema and connection management

- SQLite schema with documents table and indexes
- get_connection() with WAL mode and foreign keys
- transaction() context manager for atomic operations
- init_schema() for idempotent schema initialization

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Add CRUD operations for documents

**Files:**
- Modify: `src/local_library/core/storage.py`

**Step 1: Add the CRUD functions to storage.py**

Append to the existing file:

```python
# --- CRUD Operations ---


def create_document(
    conn: sqlite3.Connection,
    original_path: str,
    content_hash: str,
    storage_path: str,
) -> Document:
    """Create a new document record with pending status.

    Args:
        conn: Database connection
        original_path: Original source path of the document
        content_hash: SHA-256 hash of file contents
        storage_path: Path in content-addressable storage

    Returns:
        The created Document

    Raises:
        StorageError: If database operation fails
    """
    doc = Document.create_pending(original_path, content_hash, storage_path)

    try:
        conn.execute(
            """
            INSERT INTO documents (
                id, original_path, content_hash, storage_path,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(doc.id),
                doc.original_path,
                doc.content_hash,
                doc.storage_path,
                doc.status.value,
                doc.created_at.isoformat(),
                doc.updated_at.isoformat(),
            ),
        )
        conn.commit()
        return doc
    except sqlite3.Error as e:
        raise StorageError(
            f"failed to create document: {e}",
            ErrorCode.STORAGE_DATABASE_ERROR,
            details={"original_path": original_path},
        ) from e


def get_document_by_id(conn: sqlite3.Connection, doc_id: UUID) -> Document | None:
    """Get a document by its UUID.

    Args:
        conn: Database connection
        doc_id: Document UUID

    Returns:
        Document if found, None otherwise
    """
    cursor = conn.execute(
        "SELECT * FROM documents WHERE id = ?",
        (str(doc_id),),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_document(row)


def get_document_by_hash(conn: sqlite3.Connection, content_hash: str) -> Document | None:
    """Get a document by its content hash.

    Args:
        conn: Database connection
        content_hash: SHA-256 hash of file contents

    Returns:
        Document if found, None otherwise
    """
    cursor = conn.execute(
        "SELECT * FROM documents WHERE content_hash = ?",
        (content_hash,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_document(row)


def get_document_by_path(conn: sqlite3.Connection, original_path: str) -> Document | None:
    """Get a document by its original path.

    Args:
        conn: Database connection
        original_path: Original source path

    Returns:
        Document if found, None otherwise
    """
    cursor = conn.execute(
        "SELECT * FROM documents WHERE original_path = ?",
        (original_path,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_document(row)


def get_documents_by_partial_id(conn: sqlite3.Connection, partial_id: str) -> list[Document]:
    """Get documents matching a partial UUID prefix.

    Used for CLI convenience - allows users to specify just the first
    few characters of a UUID.

    Args:
        conn: Database connection
        partial_id: Prefix of a UUID (e.g., "abc123")

    Returns:
        List of matching documents (may be empty, one, or multiple)
    """
    cursor = conn.execute(
        "SELECT * FROM documents WHERE id LIKE ?",
        (f"{partial_id}%",),
    )
    return [_row_to_document(row) for row in cursor.fetchall()]


def list_documents(
    conn: sqlite3.Connection,
    status: DocumentStatus | None = None,
) -> list[Document]:
    """List all documents, optionally filtered by status.

    Args:
        conn: Database connection
        status: Filter by status if provided

    Returns:
        List of documents, ordered by created_at descending
    """
    if status is not None:
        cursor = conn.execute(
            "SELECT * FROM documents WHERE status = ? ORDER BY created_at DESC",
            (status.value,),
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM documents ORDER BY created_at DESC"
        )
    return [_row_to_document(row) for row in cursor.fetchall()]


def update_document_status(
    conn: sqlite3.Connection,
    doc_id: UUID,
    status: DocumentStatus,
    extracted_path: str | None = None,
    error_message: str | None = None,
    error_code: str | None = None,
) -> Document:
    """Update a document's status and related fields.

    Args:
        conn: Database connection
        doc_id: Document UUID
        status: New status
        extracted_path: Path to extracted content (for READY status)
        error_message: Error message (for FAILED status)
        error_code: Error code (for FAILED status)

    Returns:
        Updated Document

    Raises:
        LookupError: If document not found
        StorageError: If database operation fails
    """
    now = datetime.utcnow()

    try:
        cursor = conn.execute(
            """
            UPDATE documents
            SET status = ?, extracted_path = ?, error_message = ?,
                error_code = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status.value,
                extracted_path,
                error_message,
                error_code,
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
            f"failed to update document status: {e}",
            ErrorCode.STORAGE_DATABASE_ERROR,
            details={"doc_id": str(doc_id)},
        ) from e


def delete_document(conn: sqlite3.Connection, doc_id: UUID) -> bool:
    """Delete a document record.

    Note: This only deletes the database record. File cleanup
    should be handled separately by the caller.

    Args:
        conn: Database connection
        doc_id: Document UUID

    Returns:
        True if document was deleted, False if not found
    """
    cursor = conn.execute(
        "DELETE FROM documents WHERE id = ?",
        (str(doc_id),),
    )
    conn.commit()
    return cursor.rowcount > 0
```

**Step 2: Verify CRUD operations work**

Run: `uv run python -c "
from local_library.core.storage import get_connection, init_schema, create_document, get_document_by_id
from pathlib import Path
import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    db = Path(tmpdir) / 'test.db'
    conn = get_connection(db)
    init_schema(conn)
    doc = create_document(conn, '/test.pdf', 'abc123', '/storage/abc123.pdf')
    fetched = get_document_by_id(conn, doc.id)
    print(f'Created: {doc.id}')
    print(f'Fetched: {fetched.id if fetched else None}')
    print('CRUD works!' if doc.id == fetched.id else 'CRUD failed')
"`

Expected:
```
Created: <uuid>
Fetched: <same-uuid>
CRUD works!
```

**Step 3: Commit**

```bash
git add src/local_library/core/storage.py
git commit -m "feat: add CRUD operations for documents

- create_document(): creates pending record
- get_document_by_id/hash/path(): lookup functions
- get_documents_by_partial_id(): CLI convenience for UUID prefix matching
- list_documents(): list all with optional status filter
- update_document_status(): status transitions with extracted_path or error
- delete_document(): remove record

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Create comprehensive storage tests

**Files:**
- Create: `tests/unit/test_storage.py`

**Step 1: Create the test file**

```python
"""Unit tests for storage module."""

import sqlite3
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from local_library.core.errors import ErrorCode, LookupError, StorageError
from local_library.core.models import DocumentStatus
from local_library.core.storage import (
    create_document,
    delete_document,
    get_connection,
    get_document_by_hash,
    get_document_by_id,
    get_document_by_path,
    get_documents_by_partial_id,
    init_schema,
    list_documents,
    transaction,
    update_document_status,
)


@pytest.fixture
def db_conn(temp_dir: Path) -> sqlite3.Connection:
    """Provide an initialized database connection for testing."""
    db_path = temp_dir / "test.db"
    conn = get_connection(db_path)
    init_schema(conn)
    return conn


class TestConnectionAndSchema:
    """Tests for connection management and schema initialization."""

    def test_get_connection_creates_database(self, temp_dir: Path) -> None:
        """get_connection should create database file if it doesn't exist."""
        db_path = temp_dir / "subdir" / "test.db"
        conn = get_connection(db_path)

        assert db_path.exists()
        conn.close()

    def test_get_connection_enables_wal_mode(self, temp_dir: Path) -> None:
        """get_connection should enable WAL journal mode."""
        db_path = temp_dir / "test.db"
        conn = get_connection(db_path)

        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]

        assert mode == "wal"
        conn.close()

    def test_init_schema_creates_tables(self, temp_dir: Path) -> None:
        """init_schema should create the documents table."""
        db_path = temp_dir / "test.db"
        conn = get_connection(db_path)
        init_schema(conn)

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='documents'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_init_schema_is_idempotent(self, db_conn: sqlite3.Connection) -> None:
        """init_schema should be safe to call multiple times."""
        # Schema already initialized by fixture, call again
        init_schema(db_conn)

        # Should not raise, table should still exist
        cursor = db_conn.execute("SELECT COUNT(*) FROM documents")
        assert cursor.fetchone()[0] >= 0


class TestTransaction:
    """Tests for transaction context manager."""

    def test_transaction_commits_on_success(self, db_conn: sqlite3.Connection) -> None:
        """transaction should commit changes on successful completion."""
        with transaction(db_conn):
            db_conn.execute(
                """
                INSERT INTO documents (
                    id, original_path, content_hash, storage_path,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("test-id", "/test.pdf", "hash", "/storage/hash.pdf", "pending", "2025-01-01", "2025-01-01"),
            )

        cursor = db_conn.execute("SELECT * FROM documents WHERE id = 'test-id'")
        assert cursor.fetchone() is not None

    def test_transaction_rollbacks_on_exception(self, db_conn: sqlite3.Connection) -> None:
        """transaction should rollback changes on exception."""
        with pytest.raises(ValueError):
            with transaction(db_conn):
                db_conn.execute(
                    """
                    INSERT INTO documents (
                        id, original_path, content_hash, storage_path,
                        status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("rollback-id", "/test.pdf", "hash", "/storage/hash.pdf", "pending", "2025-01-01", "2025-01-01"),
                )
                raise ValueError("Force rollback")

        cursor = db_conn.execute("SELECT * FROM documents WHERE id = 'rollback-id'")
        assert cursor.fetchone() is None


class TestCreateDocument:
    """Tests for create_document function."""

    def test_creates_document_with_pending_status(self, db_conn: sqlite3.Connection) -> None:
        """create_document should create a document with pending status."""
        doc = create_document(db_conn, "/path/to/file.pdf", "hash123", "/storage/hash123.pdf")

        assert doc.status == DocumentStatus.PENDING

    def test_creates_document_with_uuid(self, db_conn: sqlite3.Connection) -> None:
        """create_document should generate a UUID for the document."""
        doc = create_document(db_conn, "/path/to/file.pdf", "hash123", "/storage/hash123.pdf")

        assert doc.id is not None
        assert str(doc.id)  # UUID should be convertible to string

    def test_creates_document_with_timestamps(self, db_conn: sqlite3.Connection) -> None:
        """create_document should set created_at and updated_at."""
        doc = create_document(db_conn, "/path/to/file.pdf", "hash123", "/storage/hash123.pdf")

        assert doc.created_at is not None
        assert doc.updated_at is not None
        assert doc.created_at == doc.updated_at

    def test_document_persists_in_database(self, db_conn: sqlite3.Connection) -> None:
        """create_document should persist the document in the database."""
        doc = create_document(db_conn, "/path/to/file.pdf", "hash123", "/storage/hash123.pdf")
        fetched = get_document_by_id(db_conn, doc.id)

        assert fetched is not None
        assert fetched.id == doc.id
        assert fetched.original_path == doc.original_path


class TestGetDocument:
    """Tests for document retrieval functions."""

    def test_get_by_id_returns_document(self, db_conn: sqlite3.Connection) -> None:
        """get_document_by_id should return the document."""
        doc = create_document(db_conn, "/test.pdf", "hash", "/storage/hash.pdf")
        fetched = get_document_by_id(db_conn, doc.id)

        assert fetched is not None
        assert fetched.id == doc.id

    def test_get_by_id_returns_none_for_missing(self, db_conn: sqlite3.Connection) -> None:
        """get_document_by_id should return None if not found."""
        fetched = get_document_by_id(db_conn, uuid4())

        assert fetched is None

    def test_get_by_hash_returns_document(self, db_conn: sqlite3.Connection) -> None:
        """get_document_by_hash should return the document."""
        doc = create_document(db_conn, "/test.pdf", "unique_hash", "/storage/unique_hash.pdf")
        fetched = get_document_by_hash(db_conn, "unique_hash")

        assert fetched is not None
        assert fetched.id == doc.id

    def test_get_by_hash_returns_none_for_missing(self, db_conn: sqlite3.Connection) -> None:
        """get_document_by_hash should return None if not found."""
        fetched = get_document_by_hash(db_conn, "nonexistent_hash")

        assert fetched is None

    def test_get_by_path_returns_document(self, db_conn: sqlite3.Connection) -> None:
        """get_document_by_path should return the document."""
        doc = create_document(db_conn, "/unique/path.pdf", "hash", "/storage/hash.pdf")
        fetched = get_document_by_path(db_conn, "/unique/path.pdf")

        assert fetched is not None
        assert fetched.id == doc.id

    def test_get_by_path_returns_none_for_missing(self, db_conn: sqlite3.Connection) -> None:
        """get_document_by_path should return None if not found."""
        fetched = get_document_by_path(db_conn, "/nonexistent/path.pdf")

        assert fetched is None


class TestGetDocumentsByPartialId:
    """Tests for partial UUID matching."""

    def test_returns_matching_documents(self, db_conn: sqlite3.Connection) -> None:
        """get_documents_by_partial_id should return documents matching prefix."""
        doc = create_document(db_conn, "/test.pdf", "hash", "/storage/hash.pdf")
        doc_id_prefix = str(doc.id)[:8]

        matches = get_documents_by_partial_id(db_conn, doc_id_prefix)

        assert len(matches) >= 1
        assert any(m.id == doc.id for m in matches)

    def test_returns_empty_for_no_match(self, db_conn: sqlite3.Connection) -> None:
        """get_documents_by_partial_id should return empty list if no match."""
        matches = get_documents_by_partial_id(db_conn, "zzzzzzz")

        assert matches == []


class TestListDocuments:
    """Tests for list_documents function."""

    def test_returns_all_documents(self, db_conn: sqlite3.Connection) -> None:
        """list_documents should return all documents."""
        create_document(db_conn, "/a.pdf", "hash_a", "/storage/a.pdf")
        create_document(db_conn, "/b.pdf", "hash_b", "/storage/b.pdf")

        docs = list_documents(db_conn)

        assert len(docs) == 2

    def test_filters_by_status(self, db_conn: sqlite3.Connection) -> None:
        """list_documents should filter by status when provided."""
        doc1 = create_document(db_conn, "/a.pdf", "hash_a", "/storage/a.pdf")
        doc2 = create_document(db_conn, "/b.pdf", "hash_b", "/storage/b.pdf")
        update_document_status(db_conn, doc2.id, DocumentStatus.READY, extracted_path="/extracted/b.md")

        pending = list_documents(db_conn, status=DocumentStatus.PENDING)
        ready = list_documents(db_conn, status=DocumentStatus.READY)

        assert len(pending) == 1
        assert pending[0].id == doc1.id
        assert len(ready) == 1
        assert ready[0].id == doc2.id

    def test_orders_by_created_at_descending(self, db_conn: sqlite3.Connection) -> None:
        """list_documents should order by created_at descending."""
        doc1 = create_document(db_conn, "/a.pdf", "hash_a", "/storage/a.pdf")
        doc2 = create_document(db_conn, "/b.pdf", "hash_b", "/storage/b.pdf")

        docs = list_documents(db_conn)

        # Most recent first
        assert docs[0].id == doc2.id
        assert docs[1].id == doc1.id


class TestUpdateDocumentStatus:
    """Tests for update_document_status function."""

    def test_updates_to_ready_with_extracted_path(self, db_conn: sqlite3.Connection) -> None:
        """update_document_status should update status and extracted_path."""
        doc = create_document(db_conn, "/test.pdf", "hash", "/storage/hash.pdf")

        updated = update_document_status(
            db_conn, doc.id, DocumentStatus.READY, extracted_path="/extracted/hash.md"
        )

        assert updated.status == DocumentStatus.READY
        assert updated.extracted_path == "/extracted/hash.md"

    def test_updates_to_failed_with_error(self, db_conn: sqlite3.Connection) -> None:
        """update_document_status should update status and error fields."""
        doc = create_document(db_conn, "/test.pdf", "hash", "/storage/hash.pdf")

        updated = update_document_status(
            db_conn,
            doc.id,
            DocumentStatus.FAILED,
            error_message="extraction failed",
            error_code="EXTRACTION_MARKER_CRASH",
        )

        assert updated.status == DocumentStatus.FAILED
        assert updated.error_message == "extraction failed"
        assert updated.error_code == "EXTRACTION_MARKER_CRASH"

    def test_updates_timestamp(self, db_conn: sqlite3.Connection) -> None:
        """update_document_status should update updated_at timestamp."""
        doc = create_document(db_conn, "/test.pdf", "hash", "/storage/hash.pdf")
        original_updated_at = doc.updated_at

        updated = update_document_status(db_conn, doc.id, DocumentStatus.READY)

        assert updated.updated_at > original_updated_at

    def test_raises_lookup_error_for_missing_document(self, db_conn: sqlite3.Connection) -> None:
        """update_document_status should raise LookupError if document not found."""
        with pytest.raises(LookupError) as exc_info:
            update_document_status(db_conn, uuid4(), DocumentStatus.READY)

        assert exc_info.value.code == ErrorCode.NOT_FOUND


class TestDeleteDocument:
    """Tests for delete_document function."""

    def test_deletes_existing_document(self, db_conn: sqlite3.Connection) -> None:
        """delete_document should remove the document from database."""
        doc = create_document(db_conn, "/test.pdf", "hash", "/storage/hash.pdf")

        result = delete_document(db_conn, doc.id)

        assert result is True
        assert get_document_by_id(db_conn, doc.id) is None

    def test_returns_false_for_missing_document(self, db_conn: sqlite3.Connection) -> None:
        """delete_document should return False if document not found."""
        result = delete_document(db_conn, uuid4())

        assert result is False
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storage.py -v`

Expected: All tests pass (approximately 25 tests)

**Step 3: Commit**

```bash
git add tests/unit/test_storage.py
git commit -m "test: add comprehensive unit tests for storage module

- Tests for connection management and schema initialization
- Tests for transaction commit/rollback behavior
- Tests for all CRUD operations
- Tests for duplicate detection helpers
- Tests for status transitions and error handling

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Update core module exports for storage

**Files:**
- Modify: `src/local_library/core/__init__.py`

**Step 1: Add storage exports to the init file**

Update the existing `__init__.py` to also export storage functions:

```python
"""Core module - models, storage, orchestration."""

from local_library.core.errors import (
    AcquisitionError,
    ErrorCode,
    ExtractionError,
    LocalLibraryError,
    LookupError,
    QualityError,
    StorageError,
)
from local_library.core.models import (
    AcquisitionResult,
    AddResult,
    Document,
    DocumentStatus,
    ExtractionResult,
)
from local_library.core.storage import (
    create_document,
    delete_document,
    get_connection,
    get_document_by_hash,
    get_document_by_id,
    get_document_by_path,
    get_documents_by_partial_id,
    init_schema,
    list_documents,
    transaction,
    update_document_status,
)

__all__ = [
    # Errors
    "ErrorCode",
    "LocalLibraryError",
    "AcquisitionError",
    "ExtractionError",
    "QualityError",
    "StorageError",
    "LookupError",
    # Models
    "DocumentStatus",
    "Document",
    "AcquisitionResult",
    "ExtractionResult",
    "AddResult",
    # Storage
    "get_connection",
    "init_schema",
    "transaction",
    "create_document",
    "get_document_by_id",
    "get_document_by_hash",
    "get_document_by_path",
    "get_documents_by_partial_id",
    "list_documents",
    "update_document_status",
    "delete_document",
]
```

**Step 2: Verify imports work**

Run: `uv run python -c "from local_library.core import get_connection, create_document, Document; print('All storage exports available')"`

Expected: `All storage exports available`

**Step 3: Run all tests**

Run: `uv run pytest tests/ -v`

Expected: All tests pass

**Step 4: Commit**

```bash
git add src/local_library/core/__init__.py
git commit -m "feat: export storage functions from core module

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_4 -->

---

**Phase 3 Definition of Done:**
- Can create/read/update/delete documents
- Status transitions work (pending→ready, pending→failed)
- Duplicate detection by path and hash works
- All storage tests pass
