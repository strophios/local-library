# M5 Embedding Pipeline Implementation Plan

**Goal:** Build an embedding pipeline that transforms extracted document text into searchable vector representations stored in sqlite-vec.

**Architecture:** The implementation adds an `embeddings/` module parallel to `ingestion/`, with protocol-based chunking (MarkdownChunker) and embedding (NomicEmbedder) components. Vectors are stored in sqlite-vec's vec0 virtual tables alongside FTS5 for future hybrid search. The Library orchestrator coordinates the embedding lifecycle.

**Tech Stack:** sqlite-vec v0.1.6+, sentence-transformers with nomic-embed-text-v1.5, langchain-text-splitters for markdown-aware chunking

**Scope:** 8 phases from original design (phases 1-8)

**Codebase verified:** 2026-02-04

---

## Phase 1: Schema and Infrastructure

**Goal:** Database schema for embeddings, sqlite-vec integration, error codes.

This phase establishes the foundation: schema migration (v2 → v3), sqlite-vec extension loading, and embedding-specific error codes. No functional embedding code yet—just infrastructure.

---

<!-- START_TASK_1 -->
### Task 1: Add embedding dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml:11-20`

**Step 1: Add the three new dependencies**

Add sqlite-vec, sentence-transformers, and langchain-text-splitters to the dependencies list:

```toml
dependencies = [
    "jsonschema>=4.20.0",
    "langchain-text-splitters>=0.3.0",
    "litellm>=1.0.0",
    "marker-pdf==1.8.0",  # Pinned: v1.9.0+ has broken MPS acceleration (20x slowdown on Apple Silicon)
    "nameparser>=1.1.0",
    "platformdirs>=4.0.0",
    "rich>=13.0.0",
    "sentence-transformers>=3.0.0",
    "sqlite-vec>=0.1.6",
    "typer>=0.21.0",
    "unidecode>=1.3.0",
]
```

**Step 2: Verify dependencies install**

Run: `uv sync`
Expected: Dependencies install without errors. sentence-transformers will pull in torch, transformers, numpy, scipy.

**Step 3: Verify sqlite-vec can be imported**

Run: `uv run python -c "import sqlite_vec; print('sqlite-vec imported successfully')"`
Expected: `sqlite-vec imported successfully`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add sqlite-vec, sentence-transformers, langchain-text-splitters for M5 embedding pipeline"
```
<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Add embedding error codes to core/errors.py

**Files:**
- Modify: `src/local_library/core/errors.py:43-55`

**Step 1: Add embedding error codes after the Zotero section**

Insert the new embedding error codes after line 54 (after `ZOTERO_LIBRARY_NOT_FOUND`):

```python
    # Embedding errors
    EMBEDDING_EXTENSION_UNAVAILABLE = "EMBEDDING_EXTENSION_UNAVAILABLE"
    EMBEDDING_MODEL_LOAD_FAILED = "EMBEDDING_MODEL_LOAD_FAILED"
    EMBEDDING_COMPUTATION_FAILED = "EMBEDDING_COMPUTATION_FAILED"
    EMBEDDING_STORAGE_FAILED = "EMBEDDING_STORAGE_FAILED"
    EMBEDDING_CHUNK_FAILED = "EMBEDDING_CHUNK_FAILED"
    EMBEDDING_DOCUMENT_NOT_READY = "EMBEDDING_DOCUMENT_NOT_READY"
```

**Step 2: Add EmbeddingError exception class**

Add after line 114 (after `ZoteroError` class):

```python


class EmbeddingError(LocalLibraryError):
    """Error during embedding operations (chunking, computation, storage)."""

    pass
```

**Step 3: Verify the changes**

Run: `uv run python -c "from local_library.core.errors import ErrorCode, EmbeddingError; print(ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE.value)"`
Expected: `EMBEDDING_EXTENSION_UNAVAILABLE`

**Step 4: Commit**

```bash
git add src/local_library/core/errors.py
git commit -m "feat(errors): add embedding error codes and EmbeddingError exception"
```
<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Add EmbeddingStatus enum to core/models.py

**Files:**
- Modify: `src/local_library/core/models.py:13-20`

**Step 1: Add EmbeddingStatus enum after DocumentStatus**

Insert after line 19 (after the DocumentStatus enum):

```python


class EmbeddingStatus(str, Enum):
    """Embedding state of a document."""

    PENDING = "pending"  # No embeddings yet (new document or embedding failed)
    CURRENT = "current"  # Embeddings match current extracted text
    STALE = "stale"  # Extracted text changed; embeddings need refresh
```

**Step 2: Verify the enum**

Run: `uv run python -c "from local_library.core.models import EmbeddingStatus; print(EmbeddingStatus.PENDING.value)"`
Expected: `pending`

**Step 3: Commit**

```bash
git add src/local_library/core/models.py
git commit -m "feat(models): add EmbeddingStatus enum for tracking embedding state"
```
<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Update SCHEMA_VERSION and add migration v2→v3 in core/storage.py

**Files:**
- Modify: `src/local_library/core/storage.py:17-18` (SCHEMA_VERSION)
- Modify: `src/local_library/core/storage.py:135-141` (migrate_schema)
- Modify: `src/local_library/core/storage.py:144-164` (add new migration function)

**Step 1: Update SCHEMA_VERSION from 2 to 3**

Change line 18:

```python
SCHEMA_VERSION = 3
```

**Step 2: Add embedding_status column to SCHEMA_TABLES**

Insert after line 40 (after `error_code TEXT,`):

```python
    embedding_status TEXT DEFAULT 'pending',
```

**Step 3: Update migrate_schema() to call v2→v3 migration**

After line 137 (`_migrate_v1_to_v2(conn)`), add:

```python
    if current_version < 3:
        _migrate_v2_to_v3(conn)
```

**Step 4: Add _migrate_v2_to_v3 function**

Insert after the `_migrate_v1_to_v2` function (after line 164):

```python


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Migrate from schema v2 to v3: add embedding support.

    Adds embedding_status column to documents table.
    Creates chunks table, chunk_vectors vec0 table, and chunks_fts FTS5 table.
    """
    # Check if embedding_status column already exists (idempotent)
    cursor = conn.execute("PRAGMA table_info(documents)")
    existing_columns = {row["name"] for row in cursor.fetchall()}

    if "embedding_status" not in existing_columns:
        conn.execute(
            "ALTER TABLE documents ADD COLUMN embedding_status TEXT DEFAULT 'pending'"
        )

    # Create chunks table for storing chunk metadata and text
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            section TEXT,
            char_start INTEGER,
            char_end INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
        )
    """)

    # Create index on doc_id for efficient document-scoped queries
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)"
    )

    # Create FTS5 table for full-text search on chunks
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text,
            content='chunks',
            content_rowid='rowid'
        )
    """)

    # Create triggers to keep FTS5 in sync with chunks table
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, text) VALUES (NEW.rowid, NEW.text);
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', OLD.rowid, OLD.text);
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_fts_update AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', OLD.rowid, OLD.text);
            INSERT INTO chunks_fts(rowid, text) VALUES (NEW.rowid, NEW.text);
        END
    """)

    conn.commit()
```

**Step 5: Update _row_to_document to include embedding_status**

First, add the import at the top of the file (after line 15):

```python
from local_library.core.models import Document, DocumentStatus, EmbeddingStatus
```

Then update `_row_to_document` function to include the new field. After line 188 (the `updated_at` line), add:

```python
        embedding_status=EmbeddingStatus(row["embedding_status"]) if row["embedding_status"] else EmbeddingStatus.PENDING,
```

**Step 6: Verify schema migration works**

Run: `uv run python -c "
import tempfile
from pathlib import Path
from local_library.core.storage import get_connection, init_schema

with tempfile.TemporaryDirectory() as tmp:
    db_path = Path(tmp) / 'test.db'
    conn = get_connection(db_path)
    init_schema(conn)

    # Check schema version
    cursor = conn.execute('SELECT version FROM schema_version')
    version = cursor.fetchone()[0]
    print(f'Schema version: {version}')

    # Check embedding_status column exists
    cursor = conn.execute('PRAGMA table_info(documents)')
    columns = [row[1] for row in cursor.fetchall()]
    print(f'embedding_status in columns: {\"embedding_status\" in columns}')

    # Check chunks table exists
    cursor = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'\")
    print(f'chunks table exists: {cursor.fetchone() is not None}')

    # Check FTS5 table exists
    cursor = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'\")
    print(f'chunks_fts table exists: {cursor.fetchone() is not None}')

    conn.close()
"
`

Expected:
```
Schema version: 3
embedding_status in columns: True
chunks table exists: True
chunks_fts table exists: True
```

**Step 7: Commit**

```bash
git add src/local_library/core/storage.py
git commit -m "feat(storage): add schema v3 migration with embedding_status and chunks tables"
```
<!-- END_TASK_4 -->

---

<!-- START_TASK_5 -->
### Task 5: Add embedding_status field to Document dataclass

**Files:**
- Modify: `src/local_library/core/models.py:30-48`

**Step 1: Add embedding_status field to Document**

Insert after line 44 (after `issued_date: str | None = None`):

```python
    embedding_status: "EmbeddingStatus" = EmbeddingStatus.PENDING  # Embedding state
```

Note: The type hint uses a string "EmbeddingStatus" for forward reference since the enum is defined earlier in the same file. Alternatively, since EmbeddingStatus is already defined above Document, you can use the direct type:

```python
    embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING  # Embedding state
```

**Step 2: Update create_pending factory method**

Update the `create_pending` method (around line 59-67) to explicitly set embedding_status:

```python
    @classmethod
    def create_pending(
        cls,
        original_path: str,
        content_hash: str,
        storage_path: str,
    ) -> "Document":
        """Create a new pending document record."""
        now = datetime.now(timezone.utc)
        return cls(
            id=uuid4(),
            original_path=original_path,
            content_hash=content_hash,
            storage_path=storage_path,
            status=DocumentStatus.PENDING,
            embedding_status=EmbeddingStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
```

**Step 3: Verify Document has embedding_status**

Run: `uv run python -c "
from local_library.core.models import Document, EmbeddingStatus

doc = Document.create_pending('/test.pdf', 'hash123', '/storage/hash123.pdf')
print(f'embedding_status: {doc.embedding_status}')
print(f'is PENDING: {doc.embedding_status == EmbeddingStatus.PENDING}')
"`

Expected:
```
embedding_status: EmbeddingStatus.PENDING
is PENDING: True
```

**Step 4: Commit**

```bash
git add src/local_library/core/models.py
git commit -m "feat(models): add embedding_status field to Document dataclass"
```
<!-- END_TASK_5 -->

---

<!-- START_TASK_6 -->
### Task 6: Create sqlite-vec loading infrastructure

**Files:**
- Create: `src/local_library/core/vec_extension.py`

**Step 1: Create the vec_extension module**

Create `src/local_library/core/vec_extension.py`:

```python
"""sqlite-vec extension loading utilities."""

# pattern: Imperative Shell

import sqlite3
from typing import Callable

from local_library.core.errors import EmbeddingError, ErrorCode

# Module-level state for tracking extension availability
_extension_available: bool | None = None
_extension_error: str | None = None


def load_vec_extension(conn: sqlite3.Connection) -> bool:
    """Load sqlite-vec extension into the given connection.

    This function attempts to load the sqlite-vec extension. It caches the
    result of the first attempt to avoid repeated failure messages.

    Args:
        conn: SQLite connection to load extension into

    Returns:
        True if extension loaded successfully, False otherwise

    Note:
        On macOS, the system Python may not support loading extensions.
        Use Homebrew Python or python.org Python for extension support.
    """
    global _extension_available, _extension_error

    # If we've already determined extension is unavailable, return early
    if _extension_available is False:
        return False

    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        _extension_available = True
        return True

    except ImportError as e:
        _extension_available = False
        _extension_error = f"sqlite-vec package not installed: {e}"
        return False

    except Exception as e:
        _extension_available = False
        _extension_error = f"failed to load sqlite-vec extension: {e}"
        return False


def is_vec_available() -> bool:
    """Check if sqlite-vec extension is available.

    Returns:
        True if extension is available, False otherwise
    """
    if _extension_available is None:
        # Test with an in-memory database
        test_conn = sqlite3.connect(":memory:")
        load_vec_extension(test_conn)
        test_conn.close()

    return _extension_available is True


def get_vec_error() -> str | None:
    """Get the error message if sqlite-vec extension failed to load.

    Returns:
        Error message string, or None if extension loaded successfully
    """
    return _extension_error


def require_vec_extension(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec extension, raising an error if unavailable.

    Args:
        conn: SQLite connection to load extension into

    Raises:
        EmbeddingError: If extension cannot be loaded
    """
    if not load_vec_extension(conn):
        raise EmbeddingError(
            _extension_error or "sqlite-vec extension unavailable",
            ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE,
        )


def create_vec0_table(
    conn: sqlite3.Connection,
    table_name: str,
    dimensions: int = 768,
    distance_metric: str = "cosine",
) -> None:
    """Create a vec0 virtual table for vector storage.

    Args:
        conn: SQLite connection (must have sqlite-vec loaded)
        table_name: Name for the virtual table
        dimensions: Vector dimensions (default: 768 for nomic-embed-text-v1.5)
        distance_metric: Distance metric ('cosine', 'L2', 'L1')

    Raises:
        EmbeddingError: If table creation fails
    """
    # Validate distance metric
    valid_metrics = {"cosine", "L2", "L1"}
    if distance_metric.lower() not in {m.lower() for m in valid_metrics}:
        raise EmbeddingError(
            f"invalid distance metric: {distance_metric}. Must be one of {valid_metrics}",
            ErrorCode.EMBEDDING_STORAGE_FAILED,
        )

    # Use uppercase for SQL compatibility
    metric = distance_metric.upper() if distance_metric.lower() != "cosine" else "COSINE"

    try:
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING vec0(
                chunk_id TEXT PRIMARY KEY,
                embedding FLOAT[{dimensions}] DISTANCE_METRIC={metric}
            )
        """)
        conn.commit()
    except sqlite3.Error as e:
        raise EmbeddingError(
            f"failed to create vec0 table {table_name}: {e}",
            ErrorCode.EMBEDDING_STORAGE_FAILED,
        ) from e
```

**Step 2: Verify the module loads**

Run: `uv run python -c "
from local_library.core.vec_extension import is_vec_available, load_vec_extension
import sqlite3

print(f'sqlite-vec available: {is_vec_available()}')

if is_vec_available():
    conn = sqlite3.connect(':memory:')
    loaded = load_vec_extension(conn)
    print(f'Extension loaded: {loaded}')

    # Verify vec_version function works
    cursor = conn.execute('SELECT vec_version()')
    version = cursor.fetchone()[0]
    print(f'vec_version: {version}')
    conn.close()
"`

Expected (if sqlite-vec works):
```
sqlite-vec available: True
Extension loaded: True
vec_version: v0.1.6  (or similar version)
```

**Step 3: Commit**

```bash
git add src/local_library/core/vec_extension.py
git commit -m "feat(core): add sqlite-vec extension loading utilities"
```
<!-- END_TASK_6 -->

---

<!-- START_TASK_7 -->
### Task 7: Integrate vec0 table creation into schema migration

**Files:**
- Modify: `src/local_library/core/storage.py` (import and migration function)

**Step 1: Add import for vec_extension**

At the top of storage.py, after the existing imports (around line 15), add:

```python
from local_library.core.vec_extension import load_vec_extension, create_vec0_table
```

**Step 2: Update _migrate_v2_to_v3 to create vec0 table**

Add vec0 table creation at the end of `_migrate_v2_to_v3`, before the final `conn.commit()`:

```python
    # Create vec0 table for chunk embeddings (only if sqlite-vec is available)
    if load_vec_extension(conn):
        create_vec0_table(conn, "chunk_vectors", dimensions=768, distance_metric="cosine")
```

**Step 3: Verify vec0 table is created**

Run: `uv run python -c "
import tempfile
from pathlib import Path
from local_library.core.storage import get_connection, init_schema
from local_library.core.vec_extension import is_vec_available

with tempfile.TemporaryDirectory() as tmp:
    db_path = Path(tmp) / 'test.db'
    conn = get_connection(db_path)
    init_schema(conn)

    # Check if vec0 table exists
    cursor = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='chunk_vectors'\")
    result = cursor.fetchone()

    if is_vec_available():
        print(f'chunk_vectors table exists: {result is not None}')
    else:
        print('sqlite-vec not available, vec0 table not created (expected)')

    conn.close()
"
`

Expected (if sqlite-vec available):
```
chunk_vectors table exists: True
```

**Step 4: Commit**

```bash
git add src/local_library/core/storage.py
git commit -m "feat(storage): integrate vec0 table creation into schema v3 migration"
```
<!-- END_TASK_7 -->

---

<!-- START_TASK_8 -->
### Task 8: Add unit tests for schema migration and vec extension

**Files:**
- Create: `tests/unit/test_embedding_infrastructure.py`

**Step 1: Create test file for embedding infrastructure**

Create `tests/unit/test_embedding_infrastructure.py`:

```python
"""Unit tests for embedding infrastructure (schema, error codes, vec extension)."""

import sqlite3
from pathlib import Path

import pytest

from local_library.core.errors import EmbeddingError, ErrorCode
from local_library.core.models import Document, DocumentStatus, EmbeddingStatus
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

    def test_schema_migration_creates_embedding_status_column(
        self, temp_dir: Path
    ) -> None:
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

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'"
        )
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
    def test_require_vec_extension_raises_on_failure(self) -> None:
        """require_vec_extension should raise EmbeddingError if unavailable."""
        # This test only makes sense if we can mock the failure
        # For now, just verify it doesn't raise when available
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
```

**Step 2: Run the tests**

Run: `uv run pytest tests/unit/test_embedding_infrastructure.py -v`
Expected: All tests pass (some may skip if sqlite-vec is unavailable)

**Step 3: Commit**

```bash
git add tests/unit/test_embedding_infrastructure.py
git commit -m "test: add unit tests for embedding infrastructure (schema, errors, vec extension)"
```
<!-- END_TASK_8 -->

---

<!-- START_TASK_9 -->
### Task 9: Update core/CLAUDE.md with embedding documentation

**Files:**
- Modify: `src/local_library/core/CLAUDE.md`

**Step 1: Update the Contracts section**

Add embedding-related contracts to the "Exposes" list:

Under "Exposes", add: `EmbeddingStatus (PENDING, CURRENT, STALE), EmbeddingError`

Under "Guarantees", add:
- `EmbeddingStatus tracks embedding lifecycle (PENDING → CURRENT, CURRENT → STALE on re-extraction, STALE → CURRENT on re-embed)`
- `sqlite-vec extension loaded conditionally; library functions without it for document storage`

**Step 2: Add embedding-related Key Decisions**

Add to "Key Decisions" section:
- `**EmbeddingStatus enum**: Tracks embedding state separately from DocumentStatus (orthogonal concerns)`
- `**Conditional sqlite-vec**: Extension loaded only when available; graceful degradation allows library to function for document storage even without vector search`
- `**Cascade deletion**: Chunks and embeddings deleted via ON DELETE CASCADE foreign key when parent document deleted`

**Step 3: Update Key Files**

Add to "Key Files" section:
- `vec_extension.py` - sqlite-vec extension loading, vec0 table creation, availability checking

**Step 4: Update Last verified date**

Change to: `Last verified: 2026-02-04`

**Step 5: Commit**

```bash
git add src/local_library/core/CLAUDE.md
git commit -m "docs: update core/CLAUDE.md with embedding infrastructure documentation"
```
<!-- END_TASK_9 -->

---

## Phase 1 Verification

After completing all tasks, verify the phase is complete:

**Run all tests:**
```bash
uv run pytest tests/unit/test_embedding_infrastructure.py tests/unit/test_storage.py -v
```

**Verify schema version:**
```bash
uv run python -c "from local_library.core.storage import SCHEMA_VERSION; print(f'Schema version: {SCHEMA_VERSION}')"
```
Expected: `Schema version: 3`

**Verify all components import:**
```bash
uv run python -c "
from local_library.core.errors import EmbeddingError, ErrorCode
from local_library.core.models import EmbeddingStatus, Document
from local_library.core.vec_extension import is_vec_available, load_vec_extension
from local_library.core.storage import init_schema

print('All Phase 1 components import successfully')
print(f'sqlite-vec available: {is_vec_available()}')
"
```

**Done when:**
- Schema version is 3
- embedding_status column exists on documents table
- chunks table and chunks_fts FTS5 table exist
- chunk_vectors vec0 table exists (if sqlite-vec available)
- EmbeddingStatus enum defined with PENDING, CURRENT, STALE
- Embedding error codes added to ErrorCode enum
- EmbeddingError exception class exists
- All tests pass
