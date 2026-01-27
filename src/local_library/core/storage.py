"""SQLite storage layer for document records."""

# pattern: Imperative Shell

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from local_library.core.errors import ErrorCode, LookupError, StorageError
from local_library.core.models import Document, DocumentStatus

# Schema version for migrations
SCHEMA_VERSION = 2

SCHEMA_TABLES = """
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
"""

SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_original_path ON documents(original_path);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_citekey ON documents(citekey);
CREATE INDEX IF NOT EXISTS idx_documents_title ON documents(title);
CREATE INDEX IF NOT EXISTS idx_documents_issued_date ON documents(issued_date);
"""

SCHEMA = SCHEMA_TABLES + SCHEMA_INDEXES


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
    Automatically migrates from older schema versions.

    Args:
        conn: Database connection
    """
    # Step 1: Create tables only (without indexes on new columns)
    conn.executescript(SCHEMA_TABLES)

    # Step 2: Check current schema version
    cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        # New database: set to current schema version
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    elif row["version"] < SCHEMA_VERSION:
        # Step 3: Run migration before creating indexes (migration adds columns)
        migrate_schema(conn)

    # Step 4: Create indexes (now all columns exist, whether from tables or migration)
    conn.executescript(SCHEMA_INDEXES)


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
        cursor = conn.execute("SELECT * FROM documents ORDER BY created_at DESC")
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
    now = datetime.now(timezone.utc)

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

    Supports partial updates: only specified fields are updated,
    unspecified fields (None) are preserved.

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
        # Use COALESCE to preserve existing values when parameters are None
        # COALESCE(?, column) returns the first non-NULL value
        cursor = conn.execute(
            """
            UPDATE documents
            SET citekey = COALESCE(?, citekey),
                csl_json = COALESCE(?, csl_json),
                title = COALESCE(?, title),
                authors = COALESCE(?, authors),
                issued_date = COALESCE(?, issued_date),
                updated_at = ?
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
