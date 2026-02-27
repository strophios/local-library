# Embeddings Domain

Last verified: 2026-02-27

## Purpose

Handles document chunking, embedding computation, vector storage, and retrieval for semantic search. Transforms extracted markdown into searchable vector representations using nomic-embed-text-v1.5 via sentence-transformers, stored in sqlite-vec. Provides retriever implementations for vector, full-text, and hybrid (RRF fusion) search.

## Contracts

- **Exposes**: `Chunker protocol, Embedder protocol, Retriever protocol`, `Chunk dataclass, ChunkEmbedding dataclass, SearchResult dataclass`, `MarkdownChunker, NomicEmbedder, EmbeddingStorage`, `VectorRetriever, FTSRetriever, HybridRetriever`, `_rrf_fuse (pure function)`, `update_embedding_status, get_documents_needing_embedding, estimate_token_count`
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

## Invariants

- Every Chunk has a unique chunk_id (UUID)
- chunk_index is sequential within a document (0, 1, 2, ...)
- ChunkEmbedding.embedding is always shape (768,) and dtype float32
- Chunks maintain document order (sorted by chunk_index)
- SearchResult.search_methods is a frozenset (immutable provenance tracking)
- Retriever.retrieve() always returns results sorted by score descending

## Key Files

- `base.py` - Chunk, ChunkEmbedding, SearchResult dataclasses; Chunker, Embedder, Retriever protocols
- `chunking.py` - MarkdownChunker (section-aware markdown splitting)
- `nomic.py` - NomicEmbedder (nomic-embed-text-v1.5 via sentence-transformers)
- `storage.py` - EmbeddingStorage (sqlite-vec CRUD, FTS5 search, status functions)
- `retrieval.py` - VectorRetriever, FTSRetriever, HybridRetriever, _rrf_fuse (Imperative Shell + pure function)

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
