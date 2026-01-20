"""SQLite storage layer for document records."""

# pattern: Imperative Shell

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
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
