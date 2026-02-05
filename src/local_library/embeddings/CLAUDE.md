# Embeddings Domain

Last verified: 2026-02-04

## Purpose

Handles document chunking, embedding computation, and vector storage for semantic search. Transforms extracted markdown into searchable vector representations using nomic-embed-text-v1.5 via sentence-transformers, stored in sqlite-vec.

## Contracts

- **Exposes**: `Chunker protocol, Embedder protocol`, `Chunk dataclass, ChunkEmbedding dataclass`, `MarkdownChunker, NomicEmbedder, EmbeddingStorage`, `update_embedding_status, get_documents_needing_embedding, estimate_token_count`
- **Guarantees**:
  - `Chunk` is frozen/immutable with auto-generated UUID and UTC timestamp
  - `ChunkEmbedding` validates 768-dimensional vectors on creation
  - `Chunker.chunk()` returns chunks in document order with sequential chunk_index
  - `Embedder.embed_chunks()` returns ChunkEmbedding for each input chunk
  - `Embedder.embed_query()` uses `search_query:` prefix for nomic-embed-text
  - Chunk embeddings use `search_document:` prefix for nomic-embed-text
- **Expects**: Extracted markdown text (from ingestion pipeline); sqlite-vec extension for vector storage

## Dependencies

- **Uses**: `core.models` (EmbeddingStatus, Document), `core.errors` (EmbeddingError, ErrorCode), `core.vec_extension` (sqlite-vec loading)
- **Used by**: `core.library` (Library orchestrator calls embed methods)
- **Boundary**: Embeddings MUST NOT import from cli

## Key Decisions

- **Protocol-based extensibility**: Chunker and Embedder are protocols (not ABCs) following ingestion module pattern
- **Frozen dataclasses**: Chunk and ChunkEmbedding are immutable (Functional Core pattern)
- **768-dimensional vectors**: Hardcoded for nomic-embed-text-v1.5; ChunkEmbedding validates on creation
- **Section metadata**: Chunk.section captures markdown header context for retrieval augmentation
- **Lazy imports via `__getattr__`**: Prevents circular imports, follows ingestion module pattern
- **Task prefix responsibility**: Embedder implementations handle task prefixes (`search_document:`, `search_query:`)
- **numpy for vectors**: Embeddings stored as numpy float32 arrays; serialized via sqlite_vec.serialize_float32

## Invariants

- Every Chunk has a unique chunk_id (UUID)
- chunk_index is sequential within a document (0, 1, 2, ...)
- ChunkEmbedding.embedding is always shape (768,) and dtype float32
- Chunks maintain document order (sorted by chunk_index)

## Key Files

- `base.py` - Chunk, ChunkEmbedding dataclasses; Chunker, Embedder protocols
- `chunking.py` - MarkdownChunker (section-aware markdown splitting)
- `nomic.py` - NomicEmbedder (nomic-embed-text-v1.5 via sentence-transformers)
- `storage.py` - EmbeddingStorage (sqlite-vec CRUD), status functions

## Gotchas

- nomic-embed-text requires `trust_remote_code=True`
- Task prefixes must be prepended manually
- sqlite-vec requires `serialize_float32()` for insertion
- ChunkEmbedding validates 768 dimensions on creation
- Model download (~262 MB) happens on first embed
- EmbeddingStorage requires sqlite-vec loaded; use `require_vec_extension()` first
- `search_similar()` returns (Chunk, distance) tuples sorted by distance ascending
