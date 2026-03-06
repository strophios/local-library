# Embeddings Domain

Last verified: 2026-03-06

## Purpose

Handles document chunking, embedding computation, vector storage, and retrieval for semantic search. Transforms extracted markdown into searchable vector representations using nomic-embed-text-v1.5 via sentence-transformers, stored in sqlite-vec. Provides retriever implementations for vector, full-text, and hybrid (RRF fusion) search.

## Contracts

- **Exposes**: `Chunker protocol, Embedder protocol, Retriever protocol, Reranker protocol`, `Chunk dataclass, ChunkEmbedding dataclass, SearchResult dataclass`, `MarkdownChunker, NomicEmbedder, EmbeddingStorage`, `VectorRetriever, FTSRetriever, HybridRetriever`, `CrossEncoderReranker`, `_rrf_fuse, _group_by_document, _normalize_scores (pure functions)`, `update_embedding_status, get_documents_needing_embedding, estimate_token_count`
- **Guarantees**:
  - `Chunk` is frozen/immutable with auto-generated UUID and UTC timestamp
  - `ChunkEmbedding` validates 768-dimensional vectors on creation
  - `SearchResult` is frozen/immutable with chunk, score, doc metadata, and search_methods provenance
  - `Chunker.chunk()` returns chunks in document order with sequential chunk_index
  - `Embedder.embed_chunks()` returns ChunkEmbedding for each input chunk
  - `Embedder.embed_query()` uses `search_query:` prefix for nomic-embed-text
  - Chunk embeddings use `search_document:` prefix for nomic-embed-text
  - All `Retriever.retrieve()` implementations return `list[SearchResult]` sorted by score descending (higher = more relevant)
  - `VectorRetriever` converts cosine distance to similarity (1.0 - distance)
  - `FTSRetriever` negates BM25 scores (FTS5 returns negative; more negative = better)
  - `HybridRetriever` fuses results via RRF; falls back to vector-only on FTS syntax errors
  - `EmbeddingStorage.search_fts()` raises `FTSQueryError` on invalid FTS5 syntax
  - `Reranker.rerank()` takes query and SearchResult list, returns reranked list sorted by score descending
  - `CrossEncoderReranker` groups candidates by document ID, limits chunks per document, scores via cross-encoder model, and applies sigmoid normalization
  - `_group_by_document()` partitions results by doc_id, keeps top-N chunks per document by score, returns flattened list
  - `_normalize_scores()` applies sigmoid normalization to logits, preserving relative ordering, bounded to [0, 1]
- **Expects**: Extracted markdown text (from ingestion pipeline); sqlite-vec extension for vector storage and retrieval

## Dependencies

- **Uses**: `core.models` (EmbeddingStatus, Document), `core.errors` (EmbeddingError, FTSQueryError, ErrorCode), `core.vec_extension` (sqlite-vec loading)
- **Used by**: `core.library` (Library orchestrator calls embed and retriever methods), `cli.search` (imports SearchResult for type hints)
- **Boundary**: Embeddings MUST NOT import from cli

## Key Decisions

- **Protocol-based extensibility**: Chunker and Embedder are protocols (not ABCs) following ingestion module pattern
- **Frozen dataclasses**: Chunk and ChunkEmbedding are immutable (Functional Core pattern)
- **768-dimensional vectors**: Hardcoded for nomic-embed-text-v1.5; ChunkEmbedding validates on creation
- **Section metadata**: Chunk.section captures markdown header context for retrieval augmentation
- **Lazy imports via `__getattr__`**: Prevents circular imports, follows ingestion module pattern
- **Task prefix responsibility**: Embedder implementations handle task prefixes (`search_document:`, `search_query:`)
- **numpy for vectors**: Embeddings stored as numpy float32 arrays; serialized via sqlite_vec.serialize_float32
- **Retriever protocol**: `Retriever` is a `@runtime_checkable` protocol with `retrieve(query, k, doc_ids)` signature
- **RRF fusion as pure function**: `_rrf_fuse()` is a stateless pure function (Functional Core) composing ranked lists; HybridRetriever delegates fusion to it
- **Score normalization**: Each retriever normalizes scores so higher = more relevant (vector: 1-distance, FTS: -bm25, hybrid: RRF score)
- **Metadata enrichment**: Retrievers batch-lookup doc title/citekey via `_lookup_doc_metadata()` to populate SearchResult display fields
- **FTS fallback in hybrid**: HybridRetriever catches `FTSQueryError` and degrades to vector-only with a warning (queries with special characters can break FTS5 syntax)
- **Candidate multiplier**: HybridRetriever retrieves k * candidate_multiplier (default 3x) from each backend before RRF fusion to improve recall
- **Document-aware reranking**: CrossEncoderReranker groups by document to prevent one document from monopolizing top results; each document contributes at most max_chunks_per_doc candidates to scoring
- **Sigmoid normalization**: Cross-encoder raw logits are converted to [0, 1] range using numerically stable sigmoid, preserving relative ordering
- **Model loading with error handling**: CrossEncoderReranker._load_model() wraps ImportError and generic Exception, raising EmbeddingError with ErrorCode.EMBEDDING_MODEL_LOAD_FAILED

## Invariants

- Every Chunk has a unique chunk_id (UUID)
- chunk_index is sequential within a document (0, 1, 2, ...)
- ChunkEmbedding.embedding is always shape (768,) and dtype float32
- Chunks maintain document order (sorted by chunk_index)
- SearchResult.search_methods is a frozenset (immutable provenance tracking)
- Retriever.retrieve() always returns results sorted by score descending
- Reranker.rerank() preserves chunk and document metadata; updates only score
- _group_by_document() output contains at most max_chunks_per_doc results per unique doc_id
- _normalize_scores() output is always in [0, 1] range with relative ordering preserved
- CrossEncoderReranker bypasses grouping when all input results share a single doc_id (single-document mode)

## Key Files

- `base.py` - Chunk, ChunkEmbedding, SearchResult dataclasses; Chunker, Embedder, Retriever, Reranker protocols
- `chunking.py` - MarkdownChunker (section-aware markdown splitting)
- `nomic.py` - NomicEmbedder (nomic-embed-text-v1.5 via sentence-transformers)
- `storage.py` - EmbeddingStorage (sqlite-vec CRUD, FTS5 search, status functions)
- `retrieval.py` - VectorRetriever, FTSRetriever, HybridRetriever, _rrf_fuse (Imperative Shell + pure function)
- `reranking.py` - CrossEncoderReranker (cross-encoder model reranking), _group_by_document, _normalize_scores (Imperative Shell + pure functions)

## Gotchas

- nomic-embed-text requires `trust_remote_code=True`
- Task prefixes must be prepended manually
- sqlite-vec requires `serialize_float32()` for insertion
- ChunkEmbedding validates 768 dimensions on creation
- Model download (~262 MB) happens on first embed
- EmbeddingStorage requires sqlite-vec loaded; use `require_vec_extension()` first
- `search_similar()` returns (Chunk, distance) tuples sorted by distance ascending
- `search_fts()` returns (Chunk, bm25_score) tuples; BM25 scores are negative (more negative = better match)
- `_rrf_fuse()` is module-private (underscore prefix) but tested directly; stable interface for HybridRetriever
- FTS5 MATCH can fail on queries with special characters (quotes, parentheses, etc.); `search_fts()` wraps these as `FTSQueryError`
- Retrievers access `EmbeddingStorage._conn` directly for metadata lookup (internal coupling, acceptable given shared domain)
- Cross-encoder models require `trust_remote_code=True` for BGE models (parameterized by model name)
- CrossEncoderReranker._load_model() raises EmbeddingError on ImportError or model loading failure (matches NomicEmbedder pattern)
- _group_by_document() returns a new list; input results are not mutated
- _normalize_scores() expects list[float] (typically numpy array converted via .tolist()); output is always Python list[float]
- CrossEncoderReranker model download (~50-100 MB depending on model) happens on first rerank call, not initialization
