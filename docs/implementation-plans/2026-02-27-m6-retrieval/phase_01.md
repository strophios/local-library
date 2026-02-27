# M6 Retrieval Implementation Plan

**Goal:** Build a hybrid retrieval system combining vector similarity search and full-text search via Reciprocal Rank Fusion, exposed through a formal Retriever protocol.

**Architecture:** Three Retriever implementations (Vector, FTS, Hybrid) satisfy a common protocol defined in `embeddings/base.py`. HybridRetriever composes the other two via RRF. A new `search` CLI command consumes the protocol. An evaluation framework measures retrieval quality.

**Tech Stack:** Python 3.12+, SQLite (sqlite-vec for vectors, FTS5 for full-text), nomic-embed-text-v1.5, Typer/Rich for CLI

**Scope:** 7 phases from original design (phases 1-7, complete implementation)

**Codebase verified:** 2026-02-27

---

## Phase 1: Retriever Protocol & Data Types

**Goal:** Define the contracts that all subsequent phases build against.

**Components:**
- `Retriever` protocol and `SearchResult` dataclass in `src/local_library/embeddings/base.py`
- `FTSQueryError` in `src/local_library/core/errors.py`
- Updated `embeddings/__init__.py` exports

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add FTSQueryError to error hierarchy

**Files:**
- Modify: `src/local_library/core/errors.py:9-62` (add error code)
- Modify: `src/local_library/core/errors.py:125-128` (add class after EmbeddingError)

**Step 1: Add FTS_QUERY_SYNTAX_ERROR to ErrorCode enum**

In `src/local_library/core/errors.py`, add a new error code to the `ErrorCode` enum after line 62 (inside the `# Embedding errors` section):

```python
    EMBEDDING_FTS_QUERY_SYNTAX = "EMBEDDING_FTS_QUERY_SYNTAX"
```

This goes after `EMBEDDING_DOCUMENT_NOT_READY` (line 62), keeping embedding codes grouped.

**Step 2: Add FTSQueryError class**

After `EmbeddingError` (line 128), add:

```python
class FTSQueryError(EmbeddingError):
    """FTS5 query syntax error.

    Raised when a user query contains syntax that SQLite FTS5 cannot parse
    (e.g., unbalanced quotes, invalid operators).
    """

    pass
```

**Step 3: Verify existing tests still pass**

Run: `uv run pytest tests/unit/test_storage.py tests/unit/test_embedding_storage.py -v --tb=short`
Expected: All existing tests pass (no behavior changed)

**Step 4: Commit**

```bash
git add src/local_library/core/errors.py
git commit -m "feat(retrieval): add FTSQueryError to error hierarchy"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add Retriever protocol and SearchResult dataclass to base.py

**Files:**
- Modify: `src/local_library/embeddings/base.py` (add new types after existing protocols, after line 167)

**Step 1: Add SearchResult dataclass and Retriever protocol**

At the end of `src/local_library/embeddings/base.py` (after line 167), add:

```python


@dataclass(frozen=True)
class SearchResult:
    """A single search result with score and provenance metadata.

    Returned by all Retriever implementations. Frozen for immutability.

    Attributes:
        chunk: The matched chunk of text
        score: Relevance score (higher = more relevant). RRF score for hybrid,
               converted distance for vector, BM25 rank for FTS.
        doc_title: Document title for display (None if metadata unavailable)
        doc_citekey: Citekey for citation reference (None if not set)
        search_methods: Which search methods contributed to this result
    """

    chunk: Chunk
    score: float
    doc_title: str | None
    doc_citekey: str | None
    search_methods: frozenset[str]


@runtime_checkable
class Retriever(Protocol):
    """Protocol for searching document chunks by content.

    Implementations wrap one or more search backends (vector similarity,
    full-text search, or a hybrid combination) and return ranked results.
    """

    def retrieve(
        self,
        query: str,
        k: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Search for chunks matching a query.

        Args:
            query: Natural language search query
            k: Maximum number of results to return
            doc_ids: Optional document ID filter (search only these documents)

        Returns:
            List of SearchResult objects, sorted by score descending
        """
        ...
```

**Step 2: Verify existing tests still pass**

Run: `uv run pytest tests/unit/test_embedding_models.py -v --tb=short`
Expected: All existing tests pass (only additions, no changes)

**Step 3: Commit**

```bash
git add src/local_library/embeddings/base.py
git commit -m "feat(retrieval): add Retriever protocol and SearchResult dataclass"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update embeddings __init__.py exports

**Files:**
- Modify: `src/local_library/embeddings/__init__.py` (add lazy imports and __all__ entries)

**Step 1: Add lazy imports for SearchResult and Retriever**

In `src/local_library/embeddings/__init__.py`, add two new `elif` branches in the `__getattr__` function, before the `raise AttributeError` at line 49:

```python
    elif name == "SearchResult":
        from local_library.embeddings.base import SearchResult

        return SearchResult
    elif name == "Retriever":
        from local_library.embeddings.base import Retriever

        return Retriever
```

**Step 2: Update __all__ to include new exports**

Update the `__all__` list to include the new types:

```python
__all__ = [
    # Protocols
    "Chunker",
    "Embedder",
    "Retriever",
    # Data models
    "Chunk",
    "ChunkEmbedding",
    "SearchResult",
    # Implementations
    "MarkdownChunker",
    "NomicEmbedder",
    "EmbeddingStorage",
    # Utilities
    "estimate_token_count",
    "update_embedding_status",
    "get_documents_needing_embedding",
]
```

**Step 3: Verify imports work**

Run: `uv run python -c "from local_library.embeddings import Retriever, SearchResult; print('Retriever:', Retriever); print('SearchResult:', SearchResult)"`
Expected: Both imports succeed and print the class references

**Step 4: Run full test suite to confirm no regressions**

Run: `uv run pytest tests/ -v --tb=short -x`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/local_library/embeddings/__init__.py
git commit -m "feat(retrieval): export Retriever and SearchResult from embeddings package"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->
