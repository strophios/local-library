# Document-Aware Cross-Encoder Reranking Design

## Summary

The retrieval pipeline currently uses a hybrid of vector similarity and BM25 full-text search, fused via Reciprocal Rank Fusion. Both stages are bi-encoder approaches — the query and each document chunk are embedded independently, so relevance is assessed without considering the query and chunk together as a pair. Cross-encoder reranking addresses this by taking a smaller set of already-retrieved candidates and scoring each (query, chunk) pair jointly, which is slower but substantially more accurate. This design adds a cross-encoder reranking stage as a transparent wrapper around the existing retrieval pipeline: the inner retriever broadens its candidate pool (to ~100 results), and the reranker then scores and selects the final top-k from that pool.

A second concern the design addresses is source diversity: without grouping, a single highly-relevant document can monopolize the candidate pool by contributing many chunks, crowding out results from other documents. The reranker applies document-aware grouping before scoring — selecting at most three chunks per document from the candidate pool — so the cross-encoder evaluates a range of sources rather than re-scoring the same document repeatedly. The result is a pipeline that is both more precise (cross-encoder scoring) and better-diversified (grouping) without any changes to the embedding model, the FTS index, or the RAG prompt layer. Reranking is on by default and can be disabled with `--no-rerank` on both `search` and `ask`.

## Definition of Done

- **A cross-encoder reranking stage** is added to the retrieval pipeline, applying document-aware grouping (group candidates by parent document, select top-N per document, rerank via cross-encoder) to improve both precision and source diversity
- **Reranking is on by default** for all retrieval modes (hybrid, vector, fts), with a `--no-rerank` flag on both `search` and `ask` commands to opt out
- **The initial retrieval pool is broadened** (from the current effective ~30 candidates to ~100) so the reranker has enough candidates to work with
- **The reranker model is lazy-loaded** following existing patterns (NomicEmbedder), with the architecture supporting future persistent loading (daemon mode)
- **Implementation follows existing patterns**: `Reranker` protocol, wrapper `Retriever` implementation, frozen `SearchResult` instances, Functional Core / Imperative Shell classification
- **Three cross-encoder models are evaluated** (MiniLM-L-6, MiniLM-L-12, BGE-reranker-v2-m3) with a leaning toward MiniLM-L-12, final selection based on quality/latency tradeoffs

**Out of scope**: query expansion, HyDE, multi-stage retrieval (separate priorities), changes to the embedding model, changes to the RAG prompt or LLM layer.

## Glossary

- **Bi-encoder**: A retrieval architecture where the query and each document are encoded independently into vectors, and relevance is measured by vector similarity (e.g., cosine distance). Fast and scalable, but misses fine-grained query-document interactions.
- **Cross-encoder**: A model that takes a (query, document) pair as a single input and produces a relevance score. More accurate than bi-encoders because it attends over both simultaneously, but requires one forward pass per candidate, making it unsuitable for full-corpus retrieval — used here as a reranking stage over a pre-filtered candidate set.
- **Reranking**: A two-stage retrieval strategy: a fast first-stage retriever (bi-encoder or BM25) produces a candidate pool, then a slower but more accurate model (cross-encoder) rescores and reorders that pool to produce the final results.
- **Document-aware grouping**: The step within `CrossEncoderReranker` that groups candidate chunks by their parent document before reranking, capping the number of chunks contributed per document. Prevents a single document from dominating the reranked results.
- **RRF (Reciprocal Rank Fusion)**: A rank fusion method that combines results from multiple retrieval sources (here, vector and FTS) by summing reciprocals of each candidate's rank. The existing hybrid retrieval mechanism; not changed by this design.
- **FTS5**: SQLite's built-in full-text search extension, implementing BM25 scoring. Used by `FTSRetriever` as the lexical retrieval leg of the hybrid pipeline.
- **BM25**: A probabilistic ranking function for full-text search; the scoring model underlying FTS5. Rewards term frequency in a document relative to corpus-wide frequency.
- **Logit**: The raw, unbounded output of a classification model before any normalization. Cross-encoder models output logits; this design normalizes them via sigmoid to the [0, 1] range before storing in `SearchResult`.
- **Sigmoid normalization**: Applying the sigmoid function (`1 / (1 + exp(-x))`) to map unbounded logit scores to the [0, 1] range. Used here so reranked scores are comparable to the existing "higher = better" convention and are interpretable in JSON output.
- **Pool size**: The number of candidates the inner retriever is asked to return so the reranker has enough material to work with. Distinct from `k`, the number of results ultimately returned to the caller.
- **`candidate_multiplier`**: The over-fetching factor used inside `HybridRetriever` when running RRF — each sub-retriever fetches more than the requested `k` to ensure RRF fusion has adequate coverage. Unchanged by this design.
- **Decorator pattern**: A software design pattern where an object wraps another object of the same interface, adding behavior without modifying the wrapped object. `RerankedRetriever` wraps any `Retriever` and itself implements `Retriever`, making reranking transparent to callers.
- **Retriever protocol**: The Python `Protocol` class in `embeddings/base.py` defining the `retrieve(query, k, doc_ids)` interface. All retriever implementations — `VectorRetriever`, `FTSRetriever`, `HybridRetriever`, and the new `RerankedRetriever` — satisfy this protocol.
- **Lazy loading**: Deferring the import and initialization of a heavy resource (here, the cross-encoder model) to the first time it is actually used, rather than at construction. Keeps CLI startup fast.
- **MPS (Metal Performance Shaders)**: Apple Silicon's GPU compute framework, accessible via PyTorch. Mentioned as a future optimization for daemon mode where the reranker stays loaded across queries.
- **ONNX (Open Neural Network Exchange)**: A model interchange format that enables exporting PyTorch models for faster inference runtimes, including quantized int8 variants. Referenced as a future latency optimization.
- **NDCG@k (Normalized Discounted Cumulative Gain)**: An IR evaluation metric measuring ranking quality, giving more credit to relevant results appearing earlier in the list. Used in Phase 4 benchmarking.
- **MRR (Mean Reciprocal Rank)**: An IR evaluation metric measuring the average reciprocal rank of the first relevant result across queries. Used in Phase 4 benchmarking alongside NDCG@k.
- **MiniLM**: A family of small, distilled transformer models from Microsoft. The MiniLM-L-6 and MiniLM-L-12 variants (6 and 12 transformer layers respectively) are two of the three cross-encoder candidates evaluated in Phase 4.
- **BGE (BAAI General Embedding)**: A family of embedding and reranking models from the Beijing Academy of Artificial Intelligence. `bge-reranker-v2-m3` is the third cross-encoder candidate. Requires `trust_remote_code=True` when loaded via `sentence_transformers`.
- **`sentence_transformers`**: The Python library used to load and run both the existing `NomicEmbedder` and the new `CrossEncoderReranker`. Provides a `CrossEncoder` class for pair-scoring models.
- **Functional Core / Imperative Shell**: The codebase's architectural classification for modules. Pure transformation functions (no I/O, no side effects) are Functional Core; modules that perform I/O, load models, or orchestrate dependencies are Imperative Shell. Marked via `# pattern:` comments.

## Architecture

### Approach: Wrapper Retriever (Decorator Pattern)

Reranking is implemented as a `RerankedRetriever` that wraps any `Retriever` and itself implements the `Retriever` protocol. This makes reranking transparent to all callers — both the `search` CLI (which calls `retriever.retrieve()` directly) and the `ask` CLI (which goes through `Library.query()`).

Two new components, separated by responsibility:

- **`Reranker` protocol** — defines the scoring contract. A `rerank(query, results, k)` method that takes raw retrieval results and returns reranked results. The implementation handles document-aware grouping internally.
- **`RerankedRetriever`** — the composition wrapper. Implements `Retriever` by delegating to an inner retriever with a broadened candidate pool, then passing results through a `Reranker`.

This mirrors the existing separation between `Embedder` (the scoring engine) and `VectorRetriever` (the pipeline plumbing).

### Data Flow

```
User query (k=10)
  └─ RerankedRetriever.retrieve(k=10)
       │  effective_pool = max(pool_size, k * 3)  →  100
       └─ inner.retrieve(k=100)
            └─ HybridRetriever (or Vector/FTS)
                 ├─ VectorRetriever (k=300, via candidate_multiplier=3)
                 ├─ FTSRetriever (k=300)
                 └─ _rrf_fuse → 100 candidates
       └─ reranker.rerank(query, 100 candidates, k=10)
            ├─ Group by doc_id
            ├─ Select top-3 chunks per document (by original score)
            ├─ Score (query, chunk.text) pairs via cross-encoder
            ├─ Sigmoid-normalize logits to 0-1
            ├─ Create new frozen SearchResult instances
            └─ Return top-10 by reranked score
```

### Pool Size and k Relationship

The `RerankedRetriever` has a `pool_size` parameter (default 100) controlling how many candidates the inner retriever produces. The effective pool is `max(pool_size, k * 3)`, ensuring at least 3x headroom for the reranker regardless of the requested `k`. This prevents degenerate cases where a large `--limit` leaves too few candidates for meaningful reranking.

The inner retriever's `candidate_multiplier` (HybridRetriever's RRF over-fetching) is unchanged. At current scale (<50K chunks), the compound over-fetching (pool_size × candidate_multiplier) is handled by SQLite in <10ms. The cross-encoder inference dominates latency.

### Document-Aware Grouping

The grouping step within `CrossEncoderReranker.rerank()`:

1. Group `SearchResult` candidates by `chunk.doc_id`
2. Within each document group, sort by original retrieval score (descending)
3. Select up to `max_chunks_per_doc` (default 3) from each group
4. Score all selected chunks via cross-encoder

**Single-document edge case**: When all candidates share the same `doc_id` (triggered by `--doc` flag), grouping is skipped — all candidates are scored directly. This avoids the `max_chunks_per_doc` cap artificially limiting results within a single document.

### Score Semantics

Cross-encoder models output raw logits (unbounded, can be negative). Scores are normalized via sigmoid to the 0-1 range before constructing new `SearchResult` instances. This maintains the existing convention of "higher = better" scores and provides interpretable values for JSON output consumers.

The `search_methods` frozenset carries forward from the original `SearchResult`, preserving provenance of how each chunk was initially retrieved.

### Contracts

**Reranker protocol** (in `embeddings/base.py`):

```python
@runtime_checkable
class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        k: int = 10,
    ) -> list[SearchResult]: ...
```

**RerankedRetriever** (in `embeddings/reranking.py`):

```python
class RerankedRetriever:
    """Retriever wrapper that applies cross-encoder reranking."""
    # Implements Retriever protocol

    def __init__(
        self,
        inner: Retriever,
        reranker: Reranker,
        pool_size: int = 100,
        min_pool_ratio: int = 3,
    ) -> None: ...

    def retrieve(
        self,
        query: str,
        k: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[SearchResult]: ...
```

**CrossEncoderReranker** (in `embeddings/reranking.py`):

```python
class CrossEncoderReranker:
    """Document-aware cross-encoder reranker with lazy model loading."""
    # Implements Reranker protocol
    # pattern: Imperative Shell

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
        max_chunks_per_doc: int = 3,
        batch_size: int = 16,
        lazy_load: bool = True,
    ) -> None: ...

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        k: int = 10,
    ) -> list[SearchResult]: ...
```

**Library.get_retriever()** (modified signature):

```python
def get_retriever(self, mode: str = "hybrid", rerank: bool = True) -> Retriever:
    ...
```

### Model Lifecycle

The `CrossEncoderReranker` follows the `NomicEmbedder` lazy-loading pattern:

- `self._model = None` at construction
- Model loaded on first `rerank()` call
- Cached for subsequent calls
- `sentence_transformers.CrossEncoder` import deferred to load time

At the `Library` level:
- `self._reranker: CrossEncoderReranker | None = None`
- `_get_reranker()` creates on first use, caches on `self`
- Same pattern as `self._embedder` and `self._rag_interface`

**Future daemon mode**: The architecture supports persistent loading — the `Library` instance (and its cached `_reranker`) can be held in a long-running process. Switching from CPU to MPS backend (`device="mps"`) would amortize MPS initialization across queries, making GPU acceleration worthwhile even for the smaller MiniLM models.

### CLI Integration

Both `search` and `ask` commands gain a `--no-rerank` flag (default False):

- `search` already calls `lib.get_retriever()` — pass `rerank=not no_rerank`
- `ask` goes through `Library.query()` — add `rerank` parameter, forwarded to `get_retriever()`

No changes to output format, JSON structure, or streaming behavior. Reranking is transparent to the presentation layer.

## Existing Patterns

This design follows established codebase patterns identified during investigation:

- **Retriever protocol** (`embeddings/base.py:192-215`): `RerankedRetriever` implements the same `Retriever` protocol as `VectorRetriever`, `FTSRetriever`, and `HybridRetriever`. Callers are unaware of whether reranking is active.
- **Protocol + Implementation separation** (`embeddings/base.py` protocols vs `embeddings/retrieval.py` implementations): `Reranker` protocol in `base.py`, `CrossEncoderReranker` implementation in new `reranking.py`. Follows the `Embedder`/`NomicEmbedder` split.
- **Frozen SearchResult** (`embeddings/base.py:169-188`): Reranking creates new `SearchResult` instances rather than mutating existing ones. Consistent with the immutable dataclass pattern.
- **Lazy model loading** (`embeddings/nomic.py:32-60`): `CrossEncoderReranker` uses the same `_model = None` / `_load_model()` pattern as `NomicEmbedder`, deferring the `sentence_transformers` import to first use.
- **Library cached instances** (`core/library.py`): `self._reranker` follows the `self._embedder` and `self._rag_interface` lifecycle pattern.
- **Functional Core / Imperative Shell** (`# pattern:` comments): Document grouping and score normalization are pure functions (Functional Core). `CrossEncoderReranker` is Imperative Shell (ML model I/O). `RerankedRetriever` is Imperative Shell (composition/delegation).

No new patterns are introduced. The wrapper/decorator approach is a natural extension of the existing protocol-based composition.

## Implementation Phases

### Phase 1: Protocols and Core Reranking Logic

**Goal:** Implement the `Reranker` protocol, pure helper functions, and `CrossEncoderReranker` with document-aware grouping.

**Components:**
- `Reranker` protocol added to `src/local_library/embeddings/base.py`
- Pure functions in `src/local_library/embeddings/reranking.py`: document grouping (`_group_by_document`), score normalization (`_normalize_scores`)
- `CrossEncoderReranker` in `src/local_library/embeddings/reranking.py` — lazy-loaded cross-encoder model, document-aware grouping, batch scoring
- Unit tests for pure functions (grouping edge cases, normalization, single-document bypass) and `CrossEncoderReranker` (mocked `CrossEncoder.predict`)

**Dependencies:** None (first phase)

**Done when:** `CrossEncoderReranker.rerank()` correctly groups candidates by document, scores via cross-encoder, normalizes scores, and returns top-k results. All unit tests pass.

### Phase 2: RerankedRetriever Wrapper

**Goal:** Implement the `RerankedRetriever` wrapper that composes any `Retriever` with a `Reranker`.

**Components:**
- `RerankedRetriever` in `src/local_library/embeddings/reranking.py` — pool size logic, delegation to inner retriever and reranker, `doc_ids` pass-through
- Unit tests with mocked inner retriever and reranker: pool size calculation, k pass-through, empty result handling, doc_ids forwarding

**Dependencies:** Phase 1 (Reranker protocol and CrossEncoderReranker)

**Done when:** `RerankedRetriever.retrieve()` correctly broadens the candidate pool, delegates to inner retriever and reranker, and returns the final top-k. All tests pass.

### Phase 3: Library and CLI Integration

**Goal:** Wire reranking into the Library orchestrator and expose the opt-out flag on CLI commands.

**Components:**
- `Library._get_reranker()` and `self._reranker` lifecycle in `src/local_library/core/library.py`
- Modified `Library.get_retriever(mode, rerank)` to optionally wrap with `RerankedRetriever`
- Modified `Library.query()` and `Library.query_stream()` to accept and forward `rerank` parameter
- `--no-rerank` flag on `src/local_library/cli/search.py` and `src/local_library/cli/ask.py`
- Integration tests verifying `get_retriever(rerank=True)` returns `RerankedRetriever`, `get_retriever(rerank=False)` returns unwrapped retriever
- CLI tests verifying flag pass-through

**Dependencies:** Phase 2 (RerankedRetriever)

**Done when:** `search` and `ask` commands use reranking by default. `--no-rerank` disables it. All tests pass.

### Phase 4: Model Benchmarking and Default Selection

**Goal:** Evaluate the three cross-encoder model candidates on the actual corpus and select the default.

**Components:**
- Benchmark script or extension to existing evaluation harness in `tests/eval/`
- Compare `cross-encoder/ms-marco-MiniLM-L-6-v2`, `cross-encoder/ms-marco-MiniLM-L-12-v2`, and `BAAI/bge-reranker-v2-m3`
- Metrics: latency per query (50-100 pairs), memory footprint, retrieval quality (NDCG@k, MRR) against existing test queries
- Update default `model_name` in `CrossEncoderReranker` based on results

**Dependencies:** Phase 3 (full pipeline working end-to-end)

**Done when:** All three models benchmarked. Default model selected and configured. Results documented.

## Additional Considerations

**Edge case — BGE model loading**: `BAAI/bge-reranker-v2-m3` requires `trust_remote_code=True` when loading via `sentence_transformers.CrossEncoder`. The other two models do not. `CrossEncoderReranker` should pass this flag conditionally based on model name, or unconditionally (low risk, simplifies code).

**Future optimization — MPS backend**: For a future daemon mode where the reranker model stays loaded across queries, switching to `device="mps"` on Apple Silicon would amortize GPU initialization overhead and improve per-query latency. This requires no architectural changes — only a device parameter change at construction time. Not implemented in this design; documented for future reference.

**Future optimization — ONNX quantization**: sentence-transformers supports ONNX export with int8 dynamic quantization for 2-3x CPU speedup. Worth evaluating after initial deployment if latency needs tightening.
