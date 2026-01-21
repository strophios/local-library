"""Unit tests for storage module."""

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from local_library.core.errors import ErrorCode, LookupError
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
                (
                    "test-id",
                    "/test.pdf",
                    "hash",
                    "/storage/hash.pdf",
                    "pending",
                    "2025-01-01",
                    "2025-01-01",
                ),
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
                    (
                        "rollback-id",
                        "/test.pdf",
                        "hash",
                        "/storage/hash.pdf",
                        "pending",
                        "2025-01-01",
                        "2025-01-01",
                    ),
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
        update_document_status(
            db_conn, doc2.id, DocumentStatus.READY, extracted_path="/extracted/b.md"
        )

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
