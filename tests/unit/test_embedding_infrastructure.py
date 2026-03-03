"""Unit tests for embedding infrastructure (schema, error codes, vec extension)."""

import sqlite3
from pathlib import Path

import pytest

from local_library.core.errors import EmbeddingError, ErrorCode
from local_library.core.models import Document, EmbeddingStatus
from local_library.core.storage import (
    SCHEMA_VERSION,
    create_document,
    get_connection,
    get_document_by_id,
    init_schema,
)
from local_library.core.vec_extension import (
    create_vec0_table,
    is_vec_available,
    load_vec_extension,
    require_vec_extension,
)


class TestEmbeddingStatus:
    """Tests for EmbeddingStatus enum."""

    def test_embedding_status_values(self) -> None:
        """EmbeddingStatus should have PENDING, CURRENT, STALE values."""
        assert EmbeddingStatus.PENDING.value == "pending"
        assert EmbeddingStatus.CURRENT.value == "current"
        assert EmbeddingStatus.STALE.value == "stale"

    def test_embedding_status_is_string_enum(self) -> None:
        """EmbeddingStatus should be usable as string."""
        assert str(EmbeddingStatus.PENDING) == "EmbeddingStatus.PENDING"
        assert EmbeddingStatus.PENDING == "pending"


class TestEmbeddingErrorCodes:
    """Tests for embedding error codes."""

    def test_embedding_error_codes_exist(self) -> None:
        """All embedding error codes should be defined."""
        assert ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE.value == "EMBEDDING_EXTENSION_UNAVAILABLE"
        assert ErrorCode.EMBEDDING_MODEL_LOAD_FAILED.value == "EMBEDDING_MODEL_LOAD_FAILED"
        assert ErrorCode.EMBEDDING_COMPUTATION_FAILED.value == "EMBEDDING_COMPUTATION_FAILED"
        assert ErrorCode.EMBEDDING_STORAGE_FAILED.value == "EMBEDDING_STORAGE_FAILED"
        assert ErrorCode.EMBEDDING_CHUNK_FAILED.value == "EMBEDDING_CHUNK_FAILED"
        assert ErrorCode.EMBEDDING_DOCUMENT_NOT_READY.value == "EMBEDDING_DOCUMENT_NOT_READY"

    def test_embedding_error_exception(self) -> None:
        """EmbeddingError should work like other LocalLibraryError subclasses."""
        error = EmbeddingError(
            "test error",
            ErrorCode.EMBEDDING_COMPUTATION_FAILED,
            details={"doc_id": "abc123"},
        )
        assert error.code == ErrorCode.EMBEDDING_COMPUTATION_FAILED
        assert error.details == {"doc_id": "abc123"}
        assert "test error" in str(error)


class TestSchemaVersion:
    """Tests for schema version and migration."""

    def test_schema_version_is_3(self) -> None:
        """SCHEMA_VERSION should be 3 for embedding support."""
        assert SCHEMA_VERSION == 3

    def test_schema_migration_creates_embedding_status_column(self, temp_dir: Path) -> None:
        """Schema migration should add embedding_status column to documents."""
        db_path = temp_dir / "test.db"
        conn = get_connection(db_path)
        init_schema(conn)

        cursor = conn.execute("PRAGMA table_info(documents)")
        columns = {row["name"] for row in cursor.fetchall()}

        assert "embedding_status" in columns
        conn.close()

    def test_schema_migration_creates_chunks_table(self, temp_dir: Path) -> None:
        """Schema migration should create chunks table."""
        db_path = temp_dir / "test.db"
        conn = get_connection(db_path)
        init_schema(conn)

        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_schema_migration_creates_chunks_fts(self, temp_dir: Path) -> None:
        """Schema migration should create chunks_fts FTS5 table."""
        db_path = temp_dir / "test.db"
        conn = get_connection(db_path)
        init_schema(conn)

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_document_has_embedding_status_field(self) -> None:
        """Document dataclass should have embedding_status field."""
        doc = Document.create_pending("/test.pdf", "hash123", "/storage/hash.pdf")

        assert hasattr(doc, "embedding_status")
        assert doc.embedding_status == EmbeddingStatus.PENDING

    def test_document_embedding_status_persists(self, temp_dir: Path) -> None:
        """embedding_status should persist in database."""
        db_path = temp_dir / "test.db"
        conn = get_connection(db_path)
        init_schema(conn)

        doc = create_document(conn, "/test.pdf", "hash123", "/storage/hash.pdf")
        retrieved = get_document_by_id(conn, doc.id)

        assert retrieved is not None
        assert retrieved.embedding_status == EmbeddingStatus.PENDING
        conn.close()


class TestVecExtension:
    """Tests for sqlite-vec extension loading."""

    def test_is_vec_available_returns_bool(self) -> None:
        """is_vec_available should return a boolean."""
        result = is_vec_available()
        assert isinstance(result, bool)

    @pytest.mark.skipif(not is_vec_available(), reason="sqlite-vec not available")
    def test_load_vec_extension_succeeds(self) -> None:
        """load_vec_extension should return True when successful."""
        conn = sqlite3.connect(":memory:")
        result = load_vec_extension(conn)

        assert result is True
        conn.close()

    @pytest.mark.skipif(not is_vec_available(), reason="sqlite-vec not available")
    def test_vec_version_accessible(self) -> None:
        """vec_version() function should be accessible after loading."""
        conn = sqlite3.connect(":memory:")
        load_vec_extension(conn)

        cursor = conn.execute("SELECT vec_version()")
        version = cursor.fetchone()[0]

        assert version is not None
        assert version.startswith("v")
        conn.close()

    @pytest.mark.skipif(not is_vec_available(), reason="sqlite-vec not available")
    def test_require_vec_extension_succeeds_when_available(self) -> None:
        """require_vec_extension should not raise when extension is available."""
        conn = sqlite3.connect(":memory:")
        require_vec_extension(conn)  # Should not raise
        conn.close()

    @pytest.mark.skipif(not is_vec_available(), reason="sqlite-vec not available")
    def test_create_vec0_table(self) -> None:
        """create_vec0_table should create a vec0 virtual table."""
        conn = sqlite3.connect(":memory:")
        load_vec_extension(conn)

        create_vec0_table(conn, "test_vectors", dimensions=768, distance_metric="cosine")

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_vectors'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    @pytest.mark.skipif(not is_vec_available(), reason="sqlite-vec not available")
    def test_create_vec0_table_invalid_metric(self) -> None:
        """create_vec0_table should raise EmbeddingError for invalid distance metric."""
        conn = sqlite3.connect(":memory:")
        load_vec_extension(conn)

        with pytest.raises(EmbeddingError) as exc_info:
            create_vec0_table(conn, "test_vectors", distance_metric="invalid")

        assert exc_info.value.code == ErrorCode.EMBEDDING_STORAGE_FAILED
        conn.close()

    @pytest.mark.skipif(not is_vec_available(), reason="sqlite-vec not available")
    def test_schema_creates_chunk_vectors_table(self, temp_dir: Path) -> None:
        """Schema migration should create chunk_vectors vec0 table when sqlite-vec is available."""
        db_path = temp_dir / "test.db"
        conn = get_connection(db_path)
        init_schema(conn)

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunk_vectors'"
        )
        assert cursor.fetchone() is not None
        conn.close()
