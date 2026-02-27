## Phase 2: FTS5 Search

**Goal:** Add full-text search capability to `EmbeddingStorage`.

**Components:**
- `search_fts()` method on `EmbeddingStorage` in `src/local_library/embeddings/storage.py`
- Unit tests for FTS5 search in `tests/unit/test_retrieval.py`

**Dependencies:** Phase 1 (FTSQueryError)

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Write unit tests for search_fts()

**Files:**
- Create: `tests/unit/test_retrieval.py`

**Context files for the executor:**
- Read `src/local_library/embeddings/CLAUDE.md` for domain contracts
- Read `src/local_library/core/CLAUDE.md` for core contracts
- Read `tests/unit/test_embedding_storage.py` for existing test patterns (skip pattern, fixture setup, make_chunk_embedding helper)
- Read `src/local_library/embeddings/storage.py` for EmbeddingStorage API

**Step 1: Create the test file**

Create `tests/unit/test_retrieval.py` with the following content:

```python
"""Tests for retrieval: FTS5 search, retrievers, and hybrid fusion."""

# pattern: Imperative Shell

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest

from local_library.core.errors import FTSQueryError
from local_library.core.storage import get_connection, init_schema
from local_library.core.vec_extension import is_vec_available
from local_library.embeddings.base import Chunk, ChunkEmbedding
from local_library.embeddings.storage import EmbeddingStorage

pytestmark = pytest.mark.skipif(
    not is_vec_available(),
    reason="sqlite-vec extension not available",
)


def make_chunk_embedding(
    doc_id: UUID, index: int = 0, text: str = "Test text"
) -> ChunkEmbedding:
    """Create a ChunkEmbedding with random vector for testing."""
    chunk = Chunk.create(doc_id, index, text)
    embedding = np.random.randn(768).astype(np.float32)
    return ChunkEmbedding(chunk=chunk, embedding=embedding)


def _create_test_document(conn: sqlite3.Connection, doc_id: UUID) -> None:
    """Insert a minimal document record for foreign key satisfaction."""
    conn.execute(
        """
        INSERT INTO documents (id, original_path, content_hash, storage_path,
                               extracted_path, status, embedding_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'ready', 'current', ?, ?)
        """,
        (
            str(doc_id),
            "/fake/path.pdf",
            "fakehash" + str(doc_id)[:8],
            "fa/ke/fakehash.pdf",
            "/fake/extracted.md",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory."""
    return tmp_path


@pytest.fixture
def storage(temp_dir: Path) -> EmbeddingStorage:
    """Provide an EmbeddingStorage with initialized schema."""
    db_path = temp_dir / "test.db"
    conn = get_connection(db_path)
    init_schema(conn)
    return EmbeddingStorage(conn)


class TestSearchFts:
    """Tests for EmbeddingStorage.search_fts()."""

    def test_basic_keyword_match(self, storage: EmbeddingStorage) -> None:
        """search_fts returns chunks matching keyword query."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Machine learning algorithms for classification"),
            make_chunk_embedding(doc_id, 1, "Database indexing and query optimization"),
            make_chunk_embedding(doc_id, 2, "Neural network training with backpropagation"),
        ])

        results = storage.search_fts("machine learning")

        assert len(results) >= 1
        texts = [chunk.text for chunk, _ in results]
        assert any("Machine learning" in t for t in texts)

    def test_returns_chunk_and_score_tuples(self, storage: EmbeddingStorage) -> None:
        """search_fts returns list of (Chunk, float) tuples."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Python programming language"),
        ])

        results = storage.search_fts("Python")

        assert len(results) == 1
        chunk, score = results[0]
        assert isinstance(chunk, Chunk)
        assert isinstance(score, float)

    def test_bm25_scores_are_negative(self, storage: EmbeddingStorage) -> None:
        """BM25 scores from FTS5 are negative (lower = better match)."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Python programming language"),
        ])

        results = storage.search_fts("Python")

        assert len(results) == 1
        _, score = results[0]
        assert score < 0

    def test_respects_limit(self, storage: EmbeddingStorage) -> None:
        """search_fts respects the limit parameter."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, i, f"Document about topic {i} with common keyword")
            for i in range(5)
        ])

        results = storage.search_fts("keyword", limit=2)

        assert len(results) <= 2

    def test_filters_by_doc_ids(self, storage: EmbeddingStorage) -> None:
        """search_fts filters results to specified document IDs."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()
        _create_test_document(storage._conn, doc_id_1)
        _create_test_document(storage._conn, doc_id_2)
        storage.store_embeddings([
            make_chunk_embedding(doc_id_1, 0, "Python programming in doc one"),
            make_chunk_embedding(doc_id_2, 0, "Python programming in doc two"),
        ])

        results = storage.search_fts("Python", doc_ids=[doc_id_1])

        assert len(results) == 1
        chunk, _ = results[0]
        assert chunk.doc_id == doc_id_1

    def test_empty_results_for_no_match(self, storage: EmbeddingStorage) -> None:
        """search_fts returns empty list when no chunks match."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Machine learning algorithms"),
        ])

        results = storage.search_fts("xylophone")

        assert results == []

    def test_raises_fts_query_error_on_bad_syntax(
        self, storage: EmbeddingStorage
    ) -> None:
        """search_fts raises FTSQueryError for malformed FTS5 queries."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Some text"),
        ])

        with pytest.raises(FTSQueryError):
            storage.search_fts('"unbalanced quote')

    def test_reconstructs_chunk_correctly(self, storage: EmbeddingStorage) -> None:
        """search_fts returns Chunk objects with all fields populated."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Specific searchable content here"),
        ])

        results = storage.search_fts("searchable")

        assert len(results) == 1
        chunk, _ = results[0]
        assert chunk.doc_id == doc_id
        assert chunk.chunk_index == 0
        assert "searchable" in chunk.text
        assert isinstance(chunk.created_at, datetime)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_retrieval.py::TestSearchFts -v --tb=short`
Expected: FAIL — `AttributeError: 'EmbeddingStorage' object has no attribute 'search_fts'`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement search_fts() on EmbeddingStorage

**Files:**
- Modify: `src/local_library/embeddings/storage.py:12` (add FTSQueryError import)
- Modify: `src/local_library/embeddings/storage.py` (add method after `search_similar()`, after line 276)

**Context files for the executor:**
- Read `src/local_library/embeddings/storage.py` for full class context
- Read `src/local_library/core/errors.py` for FTSQueryError import

**Step 1: Add FTSQueryError import**

At the top of `src/local_library/embeddings/storage.py`, update the import from `core.errors` (line 12) to include `FTSQueryError`:

```python
from local_library.core.errors import EmbeddingError, ErrorCode, FTSQueryError
```

**Step 2: Add search_fts() method**

After `search_similar()` (after line 276), add the following method to `EmbeddingStorage`:

```python
    def search_fts(
        self,
        query: str,
        limit: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Search for chunks using FTS5 full-text search with BM25 ranking.

        Args:
            query: Search query text (passed to FTS5 MATCH)
            limit: Maximum number of results to return
            doc_ids: Optional list of document IDs to filter by

        Returns:
            List of (Chunk, bm25_score) tuples sorted by relevance.
            BM25 scores are negative; more negative = better match.

        Raises:
            FTSQueryError: If query contains invalid FTS5 syntax
        """
        try:
            if doc_ids:
                placeholders = ",".join("?" * len(doc_ids))
                cursor = self._conn.execute(
                    f"""
                    SELECT c.chunk_id, c.doc_id, c.chunk_index, c.text, c.section,
                           c.char_start, c.char_end, c.created_at, bm25(chunks_fts)
                    FROM chunks_fts
                    JOIN chunks c ON chunks_fts.rowid = c.rowid
                    WHERE chunks_fts MATCH ? AND c.doc_id IN ({placeholders})
                    ORDER BY bm25(chunks_fts)
                    LIMIT ?
                    """,
                    [query] + [str(d) for d in doc_ids] + [limit],
                )
            else:
                cursor = self._conn.execute(
                    """
                    SELECT c.chunk_id, c.doc_id, c.chunk_index, c.text, c.section,
                           c.char_start, c.char_end, c.created_at, bm25(chunks_fts)
                    FROM chunks_fts
                    JOIN chunks c ON chunks_fts.rowid = c.rowid
                    WHERE chunks_fts MATCH ?
                    ORDER BY bm25(chunks_fts)
                    LIMIT ?
                    """,
                    [query, limit],
                )
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "fts5" in error_msg or "syntax" in error_msg or "parse" in error_msg:
                raise FTSQueryError(
                    f"invalid FTS5 query syntax: {e}",
                    ErrorCode.EMBEDDING_FTS_QUERY_SYNTAX,
                    details={"query": query},
                ) from e
            raise

        results = []
        for row in cursor.fetchall():
            chunk = Chunk(
                chunk_id=row[0],
                doc_id=UUID(row[1]),
                chunk_index=row[2],
                text=row[3],
                section=row[4] or "",
                char_start=row[5],
                char_end=row[6],
                created_at=datetime.fromisoformat(row[7]),
            )
            score = row[8]
            results.append((chunk, score))

        return results
```

**Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_retrieval.py::TestSearchFts -v --tb=short`
Expected: All tests PASS

**Step 4: Run existing tests for regression**

Run: `uv run pytest tests/unit/test_embedding_storage.py -v --tb=short`
Expected: All existing tests still pass

**Step 5: Commit**

```bash
git add src/local_library/embeddings/storage.py tests/unit/test_retrieval.py
git commit -m "feat(retrieval): add FTS5 search to EmbeddingStorage"
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->
