## Phase 3: VectorRetriever & FTSRetriever

**Goal:** Wrap existing search methods in Retriever-protocol-compliant implementations with metadata enrichment.

**Components:**
- `VectorRetriever` and `FTSRetriever` classes in `src/local_library/embeddings/retrieval.py`
- Shared `_lookup_doc_metadata()` helper for document title/citekey lookup
- Unit tests in `tests/unit/test_retrieval.py`
- Updated `embeddings/__init__.py` exports

**Dependencies:** Phase 2 (search_fts on EmbeddingStorage)

**Score conversion notes:**
- Vector: `search_similar()` returns cosine distance (lower = closer). Convert to similarity: `score = 1.0 - distance`
- FTS: `search_fts()` returns negative BM25 (more negative = better). Convert: `score = -bm25_score`
- Both conversions produce "higher = more relevant" scores for SearchResult

<!-- START_TASK_1 -->
### Task 1: Write unit tests for VectorRetriever, FTSRetriever, and metadata helper

**Files:**
- Modify: `tests/unit/test_retrieval.py` (append new test classes after Phase 2's TestSearchFts)

**Context files for the executor:**
- Read `src/local_library/embeddings/base.py` for SearchResult, Retriever protocol, Chunk
- Read `src/local_library/embeddings/storage.py` for EmbeddingStorage.search_similar() and search_fts() signatures
- Read `tests/unit/test_retrieval.py` for existing fixtures and helpers (from Phase 2)
- Read `src/local_library/embeddings/CLAUDE.md` for domain contracts

**Step 1: Add imports to tests/unit/test_retrieval.py**

Add the following imports at the top of the file (after existing imports):

```python
from unittest.mock import MagicMock

from local_library.embeddings.base import Retriever, SearchResult
from local_library.embeddings.retrieval import (
    FTSRetriever,
    VectorRetriever,
    _lookup_doc_metadata,
)
```

**Step 2: Append test classes**

Append the following test classes at the end of the file:

```python
class TestLookupDocMetadata:
    """Tests for the _lookup_doc_metadata helper function."""

    def test_returns_title_and_citekey(self, storage: EmbeddingStorage) -> None:
        """Helper returns dict mapping doc_id to (title, citekey)."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("Test Title", "Smith2023", str(doc_id)),
        )
        storage._conn.commit()

        result = _lookup_doc_metadata(storage._conn, {doc_id})

        assert doc_id in result
        title, citekey = result[doc_id]
        assert title == "Test Title"
        assert citekey == "Smith2023"

    def test_returns_none_for_missing_metadata(self, storage: EmbeddingStorage) -> None:
        """Helper returns (None, None) when title/citekey not set."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)

        result = _lookup_doc_metadata(storage._conn, {doc_id})

        assert doc_id in result
        title, citekey = result[doc_id]
        assert title is None
        assert citekey is None

    def test_empty_input_returns_empty_dict(self, storage: EmbeddingStorage) -> None:
        """Helper returns empty dict for empty input."""
        result = _lookup_doc_metadata(storage._conn, set())
        assert result == {}

    def test_batch_lookup_multiple_docs(self, storage: EmbeddingStorage) -> None:
        """Helper fetches metadata for multiple documents in one query."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()
        _create_test_document(storage._conn, doc_id_1)
        _create_test_document(storage._conn, doc_id_2)
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("Doc One", "Author2023a", str(doc_id_1)),
        )
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("Doc Two", "Author2023b", str(doc_id_2)),
        )
        storage._conn.commit()

        result = _lookup_doc_metadata(storage._conn, {doc_id_1, doc_id_2})

        assert len(result) == 2
        assert result[doc_id_1] == ("Doc One", "Author2023a")
        assert result[doc_id_2] == ("Doc Two", "Author2023b")


class TestVectorRetriever:
    """Tests for VectorRetriever."""

    def test_satisfies_retriever_protocol(self, storage: EmbeddingStorage) -> None:
        """VectorRetriever satisfies the Retriever protocol."""
        embedder = MagicMock()
        retriever = VectorRetriever(storage, embedder)
        assert isinstance(retriever, Retriever)

    def test_returns_search_results(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns list of SearchResult with vector method."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("Test Doc", "Test2023", str(doc_id)),
        )
        storage._conn.commit()
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Some text about machine learning"),
        ])

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        retriever = VectorRetriever(storage, mock_embedder)
        results = retriever.retrieve("machine learning", k=5)

        assert len(results) >= 1
        result = results[0]
        assert isinstance(result, SearchResult)
        assert result.doc_title == "Test Doc"
        assert result.doc_citekey == "Test2023"
        assert "vector" in result.search_methods
        assert result.score >= 0  # Converted from distance

    def test_respects_k_parameter(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns at most k results."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, i, f"Chunk number {i}")
            for i in range(5)
        ])

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        retriever = VectorRetriever(storage, mock_embedder)
        results = retriever.retrieve("query", k=2)

        assert len(results) <= 2

    def test_passes_doc_ids_filter(self, storage: EmbeddingStorage) -> None:
        """retrieve() filters by document IDs when provided."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()
        _create_test_document(storage._conn, doc_id_1)
        _create_test_document(storage._conn, doc_id_2)
        storage.store_embeddings([
            make_chunk_embedding(doc_id_1, 0, "Content in doc one"),
            make_chunk_embedding(doc_id_2, 0, "Content in doc two"),
        ])

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        retriever = VectorRetriever(storage, mock_embedder)
        results = retriever.retrieve("content", k=10, doc_ids=[doc_id_1])

        for result in results:
            assert result.chunk.doc_id == doc_id_1

    def test_empty_results(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns empty list when no embeddings exist."""
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        retriever = VectorRetriever(storage, mock_embedder)
        results = retriever.retrieve("nonexistent query")

        assert results == []


class TestFTSRetriever:
    """Tests for FTSRetriever."""

    def test_satisfies_retriever_protocol(self, storage: EmbeddingStorage) -> None:
        """FTSRetriever satisfies the Retriever protocol."""
        retriever = FTSRetriever(storage)
        assert isinstance(retriever, Retriever)

    def test_returns_search_results(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns list of SearchResult with fts method."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("FTS Doc", "FTS2023", str(doc_id)),
        )
        storage._conn.commit()
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Python programming language features"),
        ])

        retriever = FTSRetriever(storage)
        results = retriever.retrieve("Python programming")

        assert len(results) >= 1
        result = results[0]
        assert isinstance(result, SearchResult)
        assert result.doc_title == "FTS Doc"
        assert result.doc_citekey == "FTS2023"
        assert "fts" in result.search_methods
        assert result.score > 0  # Negated BM25 score

    def test_respects_k_parameter(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns at most k results."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, i, f"Chunk {i} about searchable keyword")
            for i in range(5)
        ])

        retriever = FTSRetriever(storage)
        results = retriever.retrieve("keyword", k=2)

        assert len(results) <= 2

    def test_filters_by_doc_ids(self, storage: EmbeddingStorage) -> None:
        """retrieve() filters by document IDs when provided."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()
        _create_test_document(storage._conn, doc_id_1)
        _create_test_document(storage._conn, doc_id_2)
        storage.store_embeddings([
            make_chunk_embedding(doc_id_1, 0, "Searchable term in doc one"),
            make_chunk_embedding(doc_id_2, 0, "Searchable term in doc two"),
        ])

        retriever = FTSRetriever(storage)
        results = retriever.retrieve("Searchable", doc_ids=[doc_id_1])

        assert len(results) == 1
        assert results[0].chunk.doc_id == doc_id_1

    def test_raises_fts_query_error(self, storage: EmbeddingStorage) -> None:
        """retrieve() propagates FTSQueryError for bad syntax."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Some text"),
        ])

        retriever = FTSRetriever(storage)
        with pytest.raises(FTSQueryError):
            retriever.retrieve('"unbalanced')

    def test_empty_results(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns empty list for no matches."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Some text"),
        ])

        retriever = FTSRetriever(storage)
        results = retriever.retrieve("xylophone")

        assert results == []
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_retrieval.py::TestVectorRetriever -v --tb=short 2>&1 | head -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'local_library.embeddings.retrieval'`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement VectorRetriever, FTSRetriever, and metadata helper

**Files:**
- Create: `src/local_library/embeddings/retrieval.py`

**Context files for the executor:**
- Read `src/local_library/embeddings/base.py` for Chunk, SearchResult, Retriever, Embedder protocols
- Read `src/local_library/embeddings/storage.py` for EmbeddingStorage.search_similar() and search_fts() signatures
- Read `src/local_library/core/errors.py` for FTSQueryError
- Read `src/local_library/embeddings/CLAUDE.md` for domain contracts

**Step 1: Create retrieval.py**

Create `src/local_library/embeddings/retrieval.py`:

```python
"""Retriever implementations wrapping search backends.

VectorRetriever and FTSRetriever wrap EmbeddingStorage's search methods
and return protocol-compliant SearchResult objects enriched with document
metadata. HybridRetriever (Phase 4) composes these two via RRF fusion.
"""

# pattern: Imperative Shell

import sqlite3
from uuid import UUID

from local_library.embeddings.base import Chunk, Embedder, SearchResult
from local_library.embeddings.storage import EmbeddingStorage


def _lookup_doc_metadata(
    conn: sqlite3.Connection,
    doc_ids: set[UUID],
) -> dict[UUID, tuple[str | None, str | None]]:
    """Batch lookup document title and citekey.

    Args:
        conn: Database connection
        doc_ids: Set of document UUIDs to look up

    Returns:
        Dict mapping doc_id to (title, citekey) tuples.
        Missing documents are omitted from the result.
    """
    if not doc_ids:
        return {}
    placeholders = ",".join("?" * len(doc_ids))
    cursor = conn.execute(
        f"SELECT id, title, citekey FROM documents WHERE id IN ({placeholders})",
        [str(d) for d in doc_ids],
    )
    return {UUID(row[0]): (row[1], row[2]) for row in cursor.fetchall()}


class VectorRetriever:
    """Retriever using vector similarity search.

    Wraps EmbeddingStorage.search_similar() with query embedding
    and metadata enrichment. Converts cosine distance to similarity
    score (1.0 - distance) so higher = more relevant.
    """

    def __init__(self, storage: EmbeddingStorage, embedder: Embedder) -> None:
        """Initialize with storage backend and embedder for query encoding.

        Args:
            storage: EmbeddingStorage instance for vector search
            embedder: Embedder instance for converting queries to vectors
        """
        self._storage = storage
        self._embedder = embedder

    def retrieve(
        self,
        query: str,
        k: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Search for chunks by vector similarity.

        Embeds the query using the embedder, searches for similar vectors,
        and enriches results with document metadata.

        Args:
            query: Natural language search query
            k: Maximum number of results
            doc_ids: Optional document ID filter

        Returns:
            List of SearchResult sorted by score descending (higher = more relevant)
        """
        query_embedding = self._embedder.embed_query(query)
        raw_results = self._storage.search_similar(query_embedding, limit=k, doc_ids=doc_ids)

        if not raw_results:
            return []

        # Batch lookup metadata for all unique doc_ids
        unique_doc_ids = {chunk.doc_id for chunk, _ in raw_results}
        metadata = _lookup_doc_metadata(self._storage._conn, unique_doc_ids)

        results = []
        for chunk, distance in raw_results:
            title, citekey = metadata.get(chunk.doc_id, (None, None))
            results.append(
                SearchResult(
                    chunk=chunk,
                    score=1.0 - distance,
                    doc_title=title,
                    doc_citekey=citekey,
                    search_methods=frozenset({"vector"}),
                )
            )

        return results


class FTSRetriever:
    """Retriever using FTS5 full-text search.

    Wraps EmbeddingStorage.search_fts() with metadata enrichment.
    Negates BM25 scores so higher = more relevant.
    """

    def __init__(self, storage: EmbeddingStorage) -> None:
        """Initialize with storage backend.

        Args:
            storage: EmbeddingStorage instance for FTS5 search
        """
        self._storage = storage

    def retrieve(
        self,
        query: str,
        k: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Search for chunks by keyword match.

        Passes the query to FTS5 MATCH and enriches results with
        document metadata.

        Args:
            query: Search query text
            k: Maximum number of results
            doc_ids: Optional document ID filter

        Returns:
            List of SearchResult sorted by score descending (higher = more relevant)

        Raises:
            FTSQueryError: If query contains invalid FTS5 syntax
        """
        raw_results = self._storage.search_fts(query, limit=k, doc_ids=doc_ids)

        if not raw_results:
            return []

        # Batch lookup metadata for all unique doc_ids
        unique_doc_ids = {chunk.doc_id for chunk, _ in raw_results}
        metadata = _lookup_doc_metadata(self._storage._conn, unique_doc_ids)

        results = []
        for chunk, bm25_score in raw_results:
            title, citekey = metadata.get(chunk.doc_id, (None, None))
            results.append(
                SearchResult(
                    chunk=chunk,
                    score=-bm25_score,
                    doc_title=title,
                    doc_citekey=citekey,
                    search_methods=frozenset({"fts"}),
                )
            )

        return results
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_retrieval.py::TestVectorRetriever tests/unit/test_retrieval.py::TestFTSRetriever tests/unit/test_retrieval.py::TestLookupDocMetadata -v --tb=short`
Expected: All tests PASS

**Step 3: Run full test suite for regressions**

Run: `uv run pytest tests/unit/ -v --tb=short -x`
Expected: All tests pass

**Step 4: Commit**

```bash
git add src/local_library/embeddings/retrieval.py tests/unit/test_retrieval.py
git commit -m "feat(retrieval): add VectorRetriever and FTSRetriever implementations"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update embeddings __init__.py exports for retrieval classes

**Files:**
- Modify: `src/local_library/embeddings/__init__.py` (add lazy imports and __all__ entries)

**Step 1: Add lazy imports for VectorRetriever and FTSRetriever**

In `src/local_library/embeddings/__init__.py`, add `elif` branches in `__getattr__`, before the `raise AttributeError`:

```python
    elif name == "VectorRetriever":
        from local_library.embeddings.retrieval import VectorRetriever

        return VectorRetriever
    elif name == "FTSRetriever":
        from local_library.embeddings.retrieval import FTSRetriever

        return FTSRetriever
```

**Step 2: Update __all__**

Add to the `__all__` list in the Implementations section:

```python
    "VectorRetriever",
    "FTSRetriever",
```

**Step 3: Verify imports**

Run: `uv run python -c "from local_library.embeddings import VectorRetriever, FTSRetriever; print(VectorRetriever, FTSRetriever)"`
Expected: Both imports succeed

**Step 4: Commit**

```bash
git add src/local_library/embeddings/__init__.py
git commit -m "feat(retrieval): export VectorRetriever and FTSRetriever from embeddings"
```
<!-- END_TASK_3 -->
