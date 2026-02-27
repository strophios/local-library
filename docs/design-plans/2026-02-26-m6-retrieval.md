# M6: Retrieval Design

## Summary

M6 adds retrieval to the local library — the ability to search ingested documents by content using a combination of semantic similarity and keyword matching. The system already embeds document chunks as vectors (M5); this milestone wraps those embeddings in a query interface and pairs it with SQLite's built-in full-text search (FTS5) to build a hybrid retrieval pipeline.

The hybrid approach matters because the two methods are complementary. Vector search captures semantic similarity — a query about "climate feedback loops" will surface chunks about "global warming amplification" even without exact word overlap. FTS5 captures keyword precision — searches for a specific author name or technical term retrieve documents containing exactly those words. Results from both methods are merged via Reciprocal Rank Fusion (RRF), a well-established algorithm that combines ranked lists without requiring score normalization. The merged results are exposed through a formal `Retriever` protocol, consumed immediately by a new `search` CLI command and designed for direct reuse by the M7 RAG query pipeline. The milestone closes with a programmatic evaluation framework — a labeled test query set and metric computation (Precision@5, Recall@10, MRR) — so retrieval quality is measurable rather than assumed.

## Definition of Done

M6 delivers a hybrid retrieval system that combines vector similarity search (sqlite-vec) and full-text search (FTS5) via Reciprocal Rank Fusion. A formal Retriever protocol defines the search interface, consumed by both the user-facing `search` CLI command and (in M7) the RAG query pipeline. The scope is content-based search only — no metadata filtering. The milestone includes a programmatic evaluation framework with metrics (Precision@5, Recall@10, MRR) computed against a labeled test query set built from the golden test corpus.

**Success criteria:**
- Relevant chunks retrieved for test queries (measured by programmatic metrics)
- Hybrid search outperforms vector-only on keyword-heavy queries (demonstrated by comparative evaluation)
- Search results include source document references (title, citekey, document ID)
- A formal Retriever protocol is defined, used by the CLI and designed for M7 consumption
- Tests pass for all retrieval paths (vector, FTS5, hybrid) and the evaluation framework

**Out of scope:**
- Metadata-based filtering (author, date, type)
- LLM integration / RAG query answering (M7)
- Context assembly and prompt construction (M7)

## Glossary

- **BM25**: The ranking function underlying FTS5's scoring. Weights term frequency against how rare a term is across all documents; standard baseline for keyword search.
- **Chunk**: A contiguous segment of a document's extracted text, sized for embedding (~512 tokens with ~15% overlap). The atomic unit indexed and retrieved by the search system.
- **Citekey**: A short, human-readable identifier for a document in BetterBibTeX format (e.g., `Smith2023`). Surfaces in search results as a citation reference.
- **CSL-JSON**: Citation Style Language JSON — a standard schema for bibliographic metadata, used throughout the system for document records and Zotero interoperability.
- **EmbeddingStorage**: The existing class in `embeddings/storage.py` that owns the sqlite-vec and FTS5 tables and their CRUD operations. M6 adds `search_fts()` to it.
- **FTS5**: SQLite's built-in full-text search extension. Maintains an inverted index over stored text and supports BM25-ranked keyword queries.
- **Functional Core / Imperative Shell**: An architectural pattern that separates pure computation (no I/O, fully testable) from code that coordinates side effects. RRF fusion is Functional Core; the Retriever classes are Imperative Shell.
- **FTSRetriever**: New class in `retrieval.py` that wraps `search_fts()` and returns `SearchResult` objects satisfying the `Retriever` protocol.
- **FTSQueryError**: New exception raised when a user query contains FTS5 syntax that SQLite cannot parse (e.g., unbalanced quotes).
- **Golden test corpus**: A fixed set of PDFs used as ground truth for evaluation. Documents in this set have been embedded and have associated labeled queries.
- **HybridRetriever**: New class that composes `VectorRetriever` and `FTSRetriever`, fuses their ranked outputs via RRF, and returns a single merged result list.
- **Library**: The orchestrator class in `core/library.py` that coordinates storage, ingestion, and embedding operations. M6 adds a `get_retriever()` factory method to it.
- **MRR (Mean Reciprocal Rank)**: Evaluation metric — the average of 1/rank for the first relevant result across queries. Penalizes systems that bury the best result.
- **nomic-embed-text-v1.5**: The local embedding model used throughout the system (768 dimensions, 8192-token context). Requires task-specific prefixes: `search_query:` for user queries, `search_document:` for indexed chunks.
- **Precision@5**: Fraction of the top-5 retrieved results that are relevant. Measures whether the system wastes the user's attention on irrelevant results.
- **Protocol**: Python's structural subtyping mechanism (`typing.Protocol`). A class satisfies a Protocol if it implements the required methods, without explicit inheritance. Used here so all three Retriever implementations are interchangeable.
- **RAG (Retrieval-Augmented Generation)**: A pattern where retrieved document chunks are assembled into context and passed to an LLM to answer a query. M6 builds the retrieval half; M7 adds the LLM query interface.
- **Recall@10**: Fraction of all relevant chunks that appear in the top-10 results. Measures whether the system misses relevant material.
- **Reciprocal Rank Fusion (RRF)**: Algorithm for merging ranked lists from heterogeneous sources. Each result's score is `1 / (k + rank)`, summed across lists. The constant `k` (here 60) smooths the influence of top-ranked results.
- **Retriever protocol**: New formal interface defined in `embeddings/base.py` with a single method `retrieve(query, k, doc_ids) -> list[SearchResult]`. All three retriever implementations satisfy it.
- **SearchResult**: New frozen dataclass returned by all retrievers, carrying the matched chunk, its score, document title, citekey, and which search methods contributed to the result.
- **sqlite-vec**: A SQLite extension that adds vector storage and approximate nearest-neighbor search. Used in M5 for storing chunk embeddings; M6 queries it via `search_similar()`.
- **VectorRetriever**: New class in `retrieval.py` that wraps the existing `search_similar()` method and returns `SearchResult` objects satisfying the `Retriever` protocol.

## Architecture

Three Retriever implementations — `VectorRetriever`, `FTSRetriever`, `HybridRetriever` — all satisfy a `Retriever` protocol defined in `src/local_library/embeddings/base.py`. Each is independently usable: the CLI and evaluation framework accept any `Retriever`, and `HybridRetriever` composes the other two via Reciprocal Rank Fusion.

### Module Structure

All new retrieval code extends the existing `embeddings/` module:

```
src/local_library/embeddings/
  base.py          # + Retriever protocol, SearchResult dataclass
  storage.py       # + search_fts() method on EmbeddingStorage
  retrieval.py     # NEW: VectorRetriever, FTSRetriever, HybridRetriever

src/local_library/core/
  errors.py        # + FTSQueryError

src/local_library/cli/
  search.py        # NEW: search command
  main.py          # + search command registration

tests/unit/
  test_retrieval.py      # NEW: retriever unit tests
tests/integration/
  test_search_integration.py  # NEW: end-to-end search tests
tests/eval/
  retrieval_eval.py    # NEW: evaluation script (standalone)
  test_queries.json    # NEW: labeled test query set
```

### Data Flow

```
User query
  │
  ├──► VectorRetriever
  │      embed_query() ──► search_similar() ──► list[SearchResult]
  │
  ├──► FTSRetriever
  │      search_fts() ──► list[SearchResult]
  │
  └──► HybridRetriever
         ├── VectorRetriever.retrieve() ──► ranked vector results
         ├── FTSRetriever.retrieve() ──► ranked FTS results
         └── _rrf_fuse() ──► merged list[SearchResult] (top k)
```

Each retriever enriches results with document metadata (title, citekey) via a shared helper that queries the `documents` table.

### Contracts

**Retriever protocol** (in `embeddings/base.py`):

```python
@runtime_checkable
class Retriever(Protocol):
    def retrieve(
        self,
        query: str,
        k: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[SearchResult]: ...
```

**SearchResult** (in `embeddings/base.py`):

```python
@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float                    # RRF score (higher = more relevant)
    doc_title: str | None           # Document title for display
    doc_citekey: str | None         # Citekey for citation
    search_methods: frozenset[str]  # {"vector"}, {"fts"}, or {"vector", "fts"}
```

**search_fts() method** (on `EmbeddingStorage`):

```python
def search_fts(
    self,
    query: str,
    limit: int = 10,
    doc_ids: list[UUID] | None = None,
) -> list[tuple[Chunk, float]]:
    """FTS5 full-text search. Returns (Chunk, bm25_rank) tuples.

    Raises:
        FTSQueryError: If query causes FTS5 syntax error
    """
```

**FTSQueryError** (in `core/errors.py`):

```python
class FTSQueryError(EmbeddingError):
    """FTS5 query syntax error. Carries original query in details."""
```

### Composition Pattern

`HybridRetriever` takes `VectorRetriever` and `FTSRetriever` as constructor arguments. It delegates retrieval to each, then fuses results via RRF. If `FTSRetriever` raises `FTSQueryError`, `HybridRetriever` catches it and falls back to vector-only results, propagating a warning.

`Library` provides a factory method `get_retriever(mode="hybrid")` that wires up dependencies (EmbeddingStorage, NomicEmbedder, connection) and returns the requested Retriever implementation.

### RRF Parameters

- `rrf_k = 60` — standard smoothing constant
- `vector_weight = 1.0`, `fts_weight = 1.0` — equal weighting (tunable)
- `candidate_multiplier = 3` — retrieve `k * 3` candidates per method before fusing to top k

## Existing Patterns

**Protocol-based extensibility**: The `Retriever` protocol follows the same pattern as `Chunker` and `Embedder` in `embeddings/base.py` — `@runtime_checkable` protocols with frozen dataclass return types.

**EmbeddingStorage method pattern**: `search_fts()` mirrors `search_similar()` — same return type `list[tuple[Chunk, float]]`, same `doc_ids` filter parameter, same Chunk reconstruction from SQL rows.

**CLI command pattern**: `cli/search.py` follows `cli/embed.py` — Typer-annotated function, `Library` context manager, identifier resolution via `utils.py`, Rich output formatting.

**Error hierarchy**: `FTSQueryError` extends `EmbeddingError`, following the existing pattern where domain errors carry `ErrorCode` and `details` dict.

**Functional Core / Imperative Shell**: RRF fusion is pure computation (Functional Core) — takes ranked lists, returns fused scores. Retrievers are Imperative Shell — they coordinate I/O (database queries, model inference).

## Implementation Phases

### Phase 1: Retriever Protocol & Data Types

**Goal:** Define the contracts that all subsequent phases build against.

**Components:**
- `Retriever` protocol and `SearchResult` dataclass in `src/local_library/embeddings/base.py`
- `FTSQueryError` in `src/local_library/core/errors.py`
- Update `embeddings/__init__.py` exports

**Dependencies:** None (first phase)

**Done when:** Types importable, protocol usable in type annotations, existing tests still pass

### Phase 2: FTS5 Search

**Goal:** Add full-text search capability to `EmbeddingStorage`.

**Components:**
- `search_fts()` method on `EmbeddingStorage` in `src/local_library/embeddings/storage.py`
- Unit tests for FTS5 search in `tests/unit/test_retrieval.py`

**Dependencies:** Phase 1 (FTSQueryError)

**Done when:** FTS5 search returns matching chunks for keyword queries, raises `FTSQueryError` on malformed queries, respects limit and doc_ids filter, tests pass

### Phase 3: VectorRetriever & FTSRetriever

**Goal:** Wrap existing search methods in Retriever-protocol-compliant implementations.

**Components:**
- `VectorRetriever` and `FTSRetriever` classes in `src/local_library/embeddings/retrieval.py`
- Shared metadata enrichment helper (document title/citekey lookup)
- Unit tests for both retrievers in `tests/unit/test_retrieval.py`

**Dependencies:** Phase 2 (search_fts)

**Done when:** Both retrievers satisfy `Retriever` protocol, return `SearchResult` objects with metadata, handle edge cases (empty results, missing metadata), tests pass

### Phase 4: HybridRetriever & RRF Fusion

**Goal:** Combine vector and FTS search via Reciprocal Rank Fusion.

**Components:**
- `HybridRetriever` in `src/local_library/embeddings/retrieval.py` — composes VectorRetriever + FTSRetriever
- RRF fusion as private method (pure function, independently testable)
- Graceful degradation on FTS failure (fall back to vector-only)
- Unit tests for RRF fusion logic and HybridRetriever behavior

**Dependencies:** Phase 3 (VectorRetriever, FTSRetriever)

**Done when:** Hybrid search returns fused results, RRF scores reflect contributions from both methods, FTS failure triggers vector-only fallback with warning, tests pass

### Phase 5: Library Integration

**Goal:** Wire retrievers into the Library orchestrator.

**Components:**
- `get_retriever(mode)` factory method on `Library` in `src/local_library/core/library.py`
- Integration tests in `tests/integration/test_search_integration.py`

**Dependencies:** Phase 4 (HybridRetriever)

**Done when:** `Library.get_retriever()` returns working retriever instances, end-to-end search works (embed chunks → search → results), integration tests pass

### Phase 6: CLI Search Command

**Goal:** User-facing search interface.

**Components:**
- `cli/search.py` — search command with `--limit`, `--mode`, `--json` flags
- Command registration in `cli/main.py`
- Rich table output for human-readable results

**Dependencies:** Phase 5 (Library integration)

**Done when:** `local-library search "query"` returns ranked results with source references, `--mode` selects retriever, `--json` produces machine-readable output, command follows existing CLI patterns

### Phase 7: Evaluation Framework

**Goal:** Programmatic retrieval quality measurement.

**Components:**
- `tests/eval/retrieval_eval.py` — standalone evaluation script
- `tests/eval/test_queries.json` — labeled test query set (50-75 queries with relevant chunk IDs)
- Metric computation: Precision@5, Recall@10, MRR (hand-rolled, ~15 lines each)
- Comparative output: table showing metrics per retriever type, per query category

**Dependencies:** Phase 5 (working retrievers), golden test set with embeddings

**Done when:** Eval script runs against real database, produces metrics for all three retriever types, hybrid meets or exceeds vector-only on keyword queries, results are documented

## Additional Considerations

**FTS5 query preprocessing:** The initial implementation passes the raw user query to FTS5. `HybridRetriever` is the natural place to add query transformation (e.g., extracting keywords for FTS while preserving natural language for vector search) if evaluation shows FTS5 underperforming on conversational queries. The architecture supports this without changes to `search_fts()` or `search_similar()`.

**Evaluation ground truth creation:** Building the labeled test query set (~500 chunk-level relevance judgments) is a manual effort. The workflow: run retrieval on golden test PDFs, label top-10 results per query as relevant/not-relevant (binary). This is approximately 4-8 hours of annotation work and should happen early in the milestone to unblock Phase 7.

**Score interpretation:** RRF scores are ordinal, not cardinal — they determine rank order reliably but the magnitude isn't meaningful in absolute terms. The CLI displays scores for relative comparison within a result set, not for threshold-based filtering.
