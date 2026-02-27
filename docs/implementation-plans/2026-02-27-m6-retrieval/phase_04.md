## Phase 4: HybridRetriever & RRF Fusion

**Goal:** Combine vector and FTS search via Reciprocal Rank Fusion.

**Components:**
- `_rrf_fuse()` pure function (Functional Core) in `src/local_library/embeddings/retrieval.py`
- `HybridRetriever` class (Imperative Shell) in `src/local_library/embeddings/retrieval.py`
- Unit tests for RRF fusion logic and HybridRetriever in `tests/unit/test_retrieval.py`
- Updated `embeddings/__init__.py` exports

**Dependencies:** Phase 3 (VectorRetriever, FTSRetriever)

**RRF parameters:** `rrf_k=60` (smoothing), `vector_weight=1.0`, `fts_weight=1.0`, `candidate_multiplier=3`

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Write unit tests for RRF fusion and HybridRetriever

**Files:**
- Modify: `tests/unit/test_retrieval.py` (append new test classes)

**Context files for the executor:**
- Read `src/local_library/embeddings/base.py` for SearchResult, Chunk
- Read `tests/unit/test_retrieval.py` for existing fixtures and helpers
- Read `src/local_library/embeddings/CLAUDE.md` for domain contracts

**Step 1: Add imports**

Add the following imports to the top of `tests/unit/test_retrieval.py` (extend existing imports):

```python
import logging

from local_library.embeddings.retrieval import (
    HybridRetriever,
    _rrf_fuse,
)
```

(Also ensure `FTSRetriever`, `VectorRetriever`, `_lookup_doc_metadata` are imported from Phase 3.)

**Step 2: Append test classes**

Append the following test classes at the end of the file:

```python
class TestRrfFuse:
    """Tests for the _rrf_fuse pure function (Functional Core)."""

    def _make_result(
        self,
        chunk_id: str,
        score: float,
        method: str,
        doc_id: UUID | None = None,
    ) -> SearchResult:
        """Helper to create SearchResult for fusion tests."""
        if doc_id is None:
            doc_id = uuid4()
        chunk = Chunk.create(doc_id, 0, f"Text for {chunk_id}")
        # Override chunk_id for deterministic testing
        chunk = Chunk(
            chunk_id=chunk_id,
            doc_id=chunk.doc_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            section=chunk.section,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            created_at=chunk.created_at,
        )
        return SearchResult(
            chunk=chunk,
            score=score,
            doc_title=None,
            doc_citekey=None,
            search_methods=frozenset({method}),
        )

    def test_empty_inputs(self) -> None:
        """RRF with empty lists returns empty list."""
        result = _rrf_fuse([], [], k=10)
        assert result == []

    def test_single_list_vector_only(self) -> None:
        """RRF with only vector results returns them re-scored."""
        vector_results = [
            self._make_result("a", 0.9, "vector"),
            self._make_result("b", 0.8, "vector"),
        ]
        fused = _rrf_fuse(vector_results, [], k=10)

        assert len(fused) == 2
        assert fused[0].chunk.chunk_id == "a"
        assert fused[1].chunk.chunk_id == "b"
        assert fused[0].score > fused[1].score

    def test_single_list_fts_only(self) -> None:
        """RRF with only FTS results returns them re-scored."""
        fts_results = [
            self._make_result("x", 5.0, "fts"),
            self._make_result("y", 3.0, "fts"),
        ]
        fused = _rrf_fuse([], fts_results, k=10)

        assert len(fused) == 2
        assert fused[0].chunk.chunk_id == "x"
        assert fused[1].chunk.chunk_id == "y"

    def test_overlapping_results_merge(self) -> None:
        """Chunks appearing in both lists get combined scores and methods."""
        doc_id = uuid4()
        vector_results = [
            self._make_result("shared", 0.9, "vector", doc_id=doc_id),
            self._make_result("vec_only", 0.7, "vector"),
        ]
        fts_results = [
            self._make_result("shared", 5.0, "fts", doc_id=doc_id),
            self._make_result("fts_only", 3.0, "fts"),
        ]
        fused = _rrf_fuse(vector_results, fts_results, k=10)

        shared_result = next(r for r in fused if r.chunk.chunk_id == "shared")
        assert shared_result.search_methods == frozenset({"vector", "fts"})

        # Shared result should rank highest (gets RRF score from both lists)
        assert fused[0].chunk.chunk_id == "shared"

    def test_respects_k_limit(self) -> None:
        """RRF returns at most k results."""
        vector_results = [
            self._make_result(f"v{i}", 1.0 - i * 0.1, "vector")
            for i in range(5)
        ]
        fts_results = [
            self._make_result(f"f{i}", 5.0 - i, "fts")
            for i in range(5)
        ]
        fused = _rrf_fuse(vector_results, fts_results, k=3)

        assert len(fused) == 3

    def test_sorted_by_score_descending(self) -> None:
        """Fused results are sorted by RRF score descending."""
        vector_results = [
            self._make_result("a", 0.9, "vector"),
            self._make_result("b", 0.5, "vector"),
        ]
        fts_results = [
            self._make_result("c", 5.0, "fts"),
            self._make_result("b", 3.0, "fts"),
        ]
        fused = _rrf_fuse(vector_results, fts_results, k=10)

        scores = [r.score for r in fused]
        assert scores == sorted(scores, reverse=True)

    def test_rrf_k_parameter(self) -> None:
        """Different rrf_k values change scores but not rank order."""
        vector_results = [
            self._make_result("a", 0.9, "vector"),
            self._make_result("b", 0.5, "vector"),
        ]
        fused_60 = _rrf_fuse(vector_results, [], k=10, rrf_k=60)
        fused_10 = _rrf_fuse(vector_results, [], k=10, rrf_k=10)

        # Same order
        assert [r.chunk.chunk_id for r in fused_60] == [r.chunk.chunk_id for r in fused_10]
        # Different scores
        assert fused_60[0].score != fused_10[0].score

    def test_weights_affect_scoring(self) -> None:
        """Non-equal weights change relative contribution of each list."""
        doc_id = uuid4()
        vector_results = [self._make_result("a", 0.9, "vector", doc_id=doc_id)]
        fts_results = [self._make_result("a", 5.0, "fts", doc_id=doc_id)]

        fused_equal = _rrf_fuse(
            vector_results, fts_results, k=10,
            vector_weight=1.0, fts_weight=1.0,
        )
        fused_vector_heavy = _rrf_fuse(
            vector_results, fts_results, k=10,
            vector_weight=2.0, fts_weight=0.5,
        )

        # Scores differ when weights change
        assert fused_equal[0].score != fused_vector_heavy[0].score

    def test_preserves_metadata(self) -> None:
        """Fused results preserve doc_title and doc_citekey from original results."""
        doc_id = uuid4()
        chunk = Chunk.create(doc_id, 0, "Text")
        chunk = Chunk(
            chunk_id="meta_test",
            doc_id=chunk.doc_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            section=chunk.section,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            created_at=chunk.created_at,
        )
        vector_results = [
            SearchResult(
                chunk=chunk,
                score=0.9,
                doc_title="My Title",
                doc_citekey="Key2023",
                search_methods=frozenset({"vector"}),
            )
        ]
        fused = _rrf_fuse(vector_results, [], k=10)

        assert fused[0].doc_title == "My Title"
        assert fused[0].doc_citekey == "Key2023"


class TestHybridRetriever:
    """Tests for HybridRetriever."""

    def test_satisfies_retriever_protocol(self, storage: EmbeddingStorage) -> None:
        """HybridRetriever satisfies the Retriever protocol."""
        mock_embedder = MagicMock()
        vector_ret = VectorRetriever(storage, mock_embedder)
        fts_ret = FTSRetriever(storage)
        hybrid = HybridRetriever(vector_ret, fts_ret)
        assert isinstance(hybrid, Retriever)

    def test_returns_fused_results(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns results from both vector and FTS search."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage._conn.execute(
            "UPDATE documents SET title = ?, citekey = ? WHERE id = ?",
            ("Hybrid Doc", "Hybrid2023", str(doc_id)),
        )
        storage._conn.commit()
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Machine learning classification algorithms"),
        ])

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        vector_ret = VectorRetriever(storage, mock_embedder)
        fts_ret = FTSRetriever(storage)
        hybrid = HybridRetriever(vector_ret, fts_ret)
        results = hybrid.retrieve("machine learning")

        assert len(results) >= 1
        result = results[0]
        assert isinstance(result, SearchResult)
        # The result should come from at least one method
        assert len(result.search_methods) >= 1

    def test_falls_back_to_vector_on_fts_error(
        self, storage: EmbeddingStorage, caplog: pytest.LogCaptureFixture
    ) -> None:
        """HybridRetriever falls back to vector-only when FTS raises FTSQueryError."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, 0, "Some text content"),
        ])

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        vector_ret = VectorRetriever(storage, mock_embedder)
        fts_ret = FTSRetriever(storage)
        hybrid = HybridRetriever(vector_ret, fts_ret)

        # Query with FTS5 syntax error
        with caplog.at_level(logging.WARNING):
            results = hybrid.retrieve('"unbalanced quote')

        # Should still get vector results
        assert len(results) >= 1
        for r in results:
            assert r.search_methods == frozenset({"vector"})

        # Should log a warning
        assert any("FTS" in record.message or "fts" in record.message.lower() for record in caplog.records)

    def test_respects_k_parameter(self, storage: EmbeddingStorage) -> None:
        """retrieve() returns at most k results."""
        doc_id = uuid4()
        _create_test_document(storage._conn, doc_id)
        storage.store_embeddings([
            make_chunk_embedding(doc_id, i, f"Chunk {i} with searchable terms")
            for i in range(10)
        ])

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        vector_ret = VectorRetriever(storage, mock_embedder)
        fts_ret = FTSRetriever(storage)
        hybrid = HybridRetriever(vector_ret, fts_ret)
        results = hybrid.retrieve("searchable", k=3)

        assert len(results) <= 3

    def test_passes_doc_ids_filter(self, storage: EmbeddingStorage) -> None:
        """retrieve() passes doc_ids filter to both sub-retrievers."""
        doc_id_1 = uuid4()
        doc_id_2 = uuid4()
        _create_test_document(storage._conn, doc_id_1)
        _create_test_document(storage._conn, doc_id_2)
        storage.store_embeddings([
            make_chunk_embedding(doc_id_1, 0, "Content about Python programming"),
            make_chunk_embedding(doc_id_2, 0, "Content about Python programming"),
        ])

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        vector_ret = VectorRetriever(storage, mock_embedder)
        fts_ret = FTSRetriever(storage)
        hybrid = HybridRetriever(vector_ret, fts_ret)
        results = hybrid.retrieve("Python", k=10, doc_ids=[doc_id_1])

        for result in results:
            assert result.chunk.doc_id == doc_id_1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_retrieval.py::TestRrfFuse -v --tb=short 2>&1 | head -10`
Expected: FAIL — `ImportError: cannot import name '_rrf_fuse' from 'local_library.embeddings.retrieval'`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement _rrf_fuse and HybridRetriever

**Files:**
- Modify: `src/local_library/embeddings/retrieval.py` (add RRF function and HybridRetriever class)

**Context files for the executor:**
- Read `src/local_library/embeddings/retrieval.py` for existing code (from Phase 3)
- Read `src/local_library/embeddings/base.py` for SearchResult
- Read `src/local_library/core/errors.py` for FTSQueryError

**Step 1: Add imports at top of retrieval.py**

Add `logging` import and `FTSQueryError` import at the top of the file:

```python
import logging

from local_library.core.errors import FTSQueryError
```

Add module logger after imports:

```python
logger = logging.getLogger(__name__)
```

**Step 2: Add _rrf_fuse function**

Add the following function after the `_lookup_doc_metadata` function (before the `VectorRetriever` class). This is Functional Core — pure computation, no I/O:

```python
def _rrf_fuse(
    vector_results: list[SearchResult],
    fts_results: list[SearchResult],
    k: int,
    rrf_k: int = 60,
    vector_weight: float = 1.0,
    fts_weight: float = 1.0,
) -> list[SearchResult]:
    """Fuse ranked lists via Reciprocal Rank Fusion.

    Each result's RRF score is: weight / (rrf_k + rank), summed across lists.
    Results appearing in both lists get combined scores and merged search_methods.

    This is a pure function (Functional Core) — no I/O, fully testable.

    Args:
        vector_results: Ranked results from vector search (score descending)
        fts_results: Ranked results from FTS search (score descending)
        k: Maximum number of results to return
        rrf_k: Smoothing constant (default 60, standard value)
        vector_weight: Weight multiplier for vector scores
        fts_weight: Weight multiplier for FTS scores

    Returns:
        Fused list of SearchResult, sorted by RRF score descending, limited to k
    """
    # Track scores and metadata by chunk_id
    scores: dict[str, float] = {}
    results_by_id: dict[str, SearchResult] = {}
    methods_by_id: dict[str, set[str]] = {}

    # Score vector results
    for rank, result in enumerate(vector_results, start=1):
        cid = result.chunk.chunk_id
        scores[cid] = scores.get(cid, 0.0) + vector_weight / (rrf_k + rank)
        results_by_id[cid] = result
        methods_by_id.setdefault(cid, set()).update(result.search_methods)

    # Score FTS results
    for rank, result in enumerate(fts_results, start=1):
        cid = result.chunk.chunk_id
        scores[cid] = scores.get(cid, 0.0) + fts_weight / (rrf_k + rank)
        if cid not in results_by_id:
            results_by_id[cid] = result
        methods_by_id.setdefault(cid, set()).update(result.search_methods)

    # Build fused results sorted by RRF score descending
    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:k]

    fused = []
    for cid in sorted_ids:
        original = results_by_id[cid]
        fused.append(
            SearchResult(
                chunk=original.chunk,
                score=scores[cid],
                doc_title=original.doc_title,
                doc_citekey=original.doc_citekey,
                search_methods=frozenset(methods_by_id[cid]),
            )
        )

    return fused
```

**Step 3: Add HybridRetriever class**

Add after the `FTSRetriever` class:

```python
class HybridRetriever:
    """Retriever combining vector and FTS search via Reciprocal Rank Fusion.

    Composes VectorRetriever and FTSRetriever, retrieves candidates from both,
    and fuses results using RRF. Falls back to vector-only if FTS fails.
    """

    def __init__(
        self,
        vector_retriever: VectorRetriever,
        fts_retriever: FTSRetriever,
        rrf_k: int = 60,
        vector_weight: float = 1.0,
        fts_weight: float = 1.0,
        candidate_multiplier: int = 3,
    ) -> None:
        """Initialize with sub-retrievers and RRF parameters.

        Args:
            vector_retriever: VectorRetriever instance
            fts_retriever: FTSRetriever instance
            rrf_k: RRF smoothing constant (default 60)
            vector_weight: Weight for vector results in RRF
            fts_weight: Weight for FTS results in RRF
            candidate_multiplier: Retrieve k * multiplier candidates per method
        """
        self._vector = vector_retriever
        self._fts = fts_retriever
        self._rrf_k = rrf_k
        self._vector_weight = vector_weight
        self._fts_weight = fts_weight
        self._candidate_multiplier = candidate_multiplier

    def retrieve(
        self,
        query: str,
        k: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Search using both vector and FTS, fuse results via RRF.

        Retrieves k * candidate_multiplier candidates from each method,
        then fuses to top k via RRF. If FTS fails with a query syntax error,
        falls back to vector-only results with a warning.

        Args:
            query: Natural language search query
            k: Maximum number of results
            doc_ids: Optional document ID filter

        Returns:
            List of SearchResult sorted by RRF score descending
        """
        candidate_k = k * self._candidate_multiplier

        # Always run vector search
        vector_results = self._vector.retrieve(query, k=candidate_k, doc_ids=doc_ids)

        # Try FTS search, fall back to vector-only on syntax error
        fts_results: list[SearchResult] = []
        try:
            fts_results = self._fts.retrieve(query, k=candidate_k, doc_ids=doc_ids)
        except FTSQueryError:
            logger.warning(
                "FTS query failed for '%s', falling back to vector-only results",
                query,
            )

        return _rrf_fuse(
            vector_results,
            fts_results,
            k=k,
            rrf_k=self._rrf_k,
            vector_weight=self._vector_weight,
            fts_weight=self._fts_weight,
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_retrieval.py::TestRrfFuse tests/unit/test_retrieval.py::TestHybridRetriever -v --tb=short`
Expected: All tests PASS

**Step 5: Run full retrieval test suite**

Run: `uv run pytest tests/unit/test_retrieval.py -v --tb=short`
Expected: All tests pass (Phases 2-4)

**Step 6: Commit**

```bash
git add src/local_library/embeddings/retrieval.py tests/unit/test_retrieval.py
git commit -m "feat(retrieval): add HybridRetriever with RRF fusion"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Export HybridRetriever from embeddings package

**Files:**
- Modify: `src/local_library/embeddings/__init__.py`

**Step 1: Add lazy import for HybridRetriever**

In `src/local_library/embeddings/__init__.py`, add an `elif` branch in `__getattr__`:

```python
    elif name == "HybridRetriever":
        from local_library.embeddings.retrieval import HybridRetriever

        return HybridRetriever
```

**Step 2: Update __all__**

Add `"HybridRetriever"` to the Implementations section of `__all__`.

**Step 3: Verify import**

Run: `uv run python -c "from local_library.embeddings import HybridRetriever; print(HybridRetriever)"`
Expected: Import succeeds

**Step 4: Commit**

```bash
git add src/local_library/embeddings/__init__.py
git commit -m "feat(retrieval): export HybridRetriever from embeddings"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->
