# M5: Embedding Pipeline Design

## Summary

The embedding pipeline transforms extracted document text into searchable vector representations. When a PDF or web article is ingested, its extracted markdown is split into section-aware chunks (~512 tokens each), converted to 768-dimensional vectors using nomic-embed-text-v1.5, and stored in sqlite-vec for later semantic search. The system tracks embedding status (PENDING/CURRENT/STALE) to handle the document lifecycle: new documents start PENDING, become CURRENT after embedding, and transition to STALE if re-extracted. Embeddings cascade-delete with their parent documents.

The implementation introduces an `embeddings/` module parallel to `ingestion/`, with protocol-based components for chunking (MarkdownChunker) and embedding (NomicEmbedder). A normalized database schema separates chunks from vectors to support future enhancements like clustering embeddings and late chunking. The CLI gains an `embed` command for manual re-embedding, while `add` and `zotero import` embed automatically by default. Two-phase batch operations (extract all → embed all) decouple extraction and embedding for large imports.

## Definition of Done

M5 is complete when:

1. **Documents have searchable embeddings** — Chunks and vectors stored in sqlite-vec after add/import
2. **Chunk boundaries respect markdown structure** — Section-aware chunking using headers and paragraphs
3. **Embeddings cascade on delete** — When a document is deleted, its chunks and embeddings are removed
4. **Embedding status tracking** — Document tracks embedding state (PENDING/CURRENT/STALE) with automatic STALE transition when extracted text changes
5. **CLI `embed` command** — Manual embedding/re-embedding for specific documents or all pending
6. **Two-phase batch operations** — Zotero import supports extract-all → embed-all workflow
7. **Extensible architecture** — Design accommodates future clustering embeddings, late chunking, and hierarchical retrieval
8. **Tests pass** — Coverage for chunking logic, embedding computation, sqlite-vec storage, status transitions, and cascade deletion

### Technical Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Embedding model | nomic-embed-text-v1.5 | 768 dims, 8192 context, local, free, task prefixes |
| Chunking strategy | Section-aware | MarkdownHeaderTextSplitter → RecursiveCharacterTextSplitter |
| Chunk size | ~512 tokens | Balances context and specificity |
| Chunk overlap | ~15% (~75 tokens) | Preserves boundary context |
| Vector storage | sqlite-vec v0.1.6 | Single-file portability, adequate for ~100K vectors |
| Task prefix (RAG) | `search_document:` | Required for nomic-embed-text retrieval quality |

### Scope Boundaries

**In scope:**
- Text chunking with configurable parameters
- nomic-embed-text-v1.5 integration via sentence-transformers
- Embedding storage in sqlite-vec
- Embedding status field and transitions
- CLI `embed` command
- Integration with `add` and `zotero import`
- Cascade deletion of embeddings

**Out of scope (future milestones):**
- Query embedding with `search_query:` prefix (M6)
- Hybrid search combining sqlite-vec + FTS5 (M6)
- RAG query interface (M7)
- Clustering embeddings with `clustering:` prefix (future: auto-tagging)
- Late chunking (future enhancement)
- Hierarchical retrieval via summaries (future enhancement)

## Glossary

- **nomic-embed-text-v1.5**: Open-source embedding model producing 768-dimensional vectors from text; requires task-specific prefixes (`search_document:` for RAG chunks, `search_query:` for user queries) for optimal retrieval quality.
- **sqlite-vec**: SQLite extension for vector similarity search using virtual tables (vec0); provides brute-force k-NN search adequate for ~100K vectors in a single-file database.
- **FTS5**: SQLite's full-text search extension using inverted indexes; enables keyword search to complement vector similarity in hybrid retrieval.
- **Chunking**: Splitting long documents into smaller segments for embedding; section-aware chunking respects markdown structure (headers, paragraphs) before splitting by token count.
- **Task prefix**: String prepended to text before embedding (e.g., `search_document:`); nomic-embed-text uses these to optimize vector representations for specific use cases.
- **Late chunking**: Strategy where embeddings can be recomputed without re-splitting text; enabled by storing chunk boundaries separately from vectors.
- **Hierarchical retrieval**: Multi-stage search strategy using both document-level summaries and chunk-level details to improve result relevance.
- **Cascade deletion**: Database pattern where deleting a parent record automatically removes dependent child records (e.g., deleting a document removes its chunks and embeddings).
- **Protocol (Python)**: Interface definition using `typing.Protocol` for structural typing; allows multiple implementations without inheritance (e.g., `Chunker`, `Embedder`).
- **sentence-transformers**: Python library wrapping Hugging Face models for computing text embeddings; handles model loading, tokenization, and batching.
- **MarkdownHeaderTextSplitter**: LangChain component that splits markdown by headers (## Section) to preserve document structure during chunking.
- **RecursiveCharacterTextSplitter**: LangChain component that recursively splits text by separators (newlines, sentences, words) to meet token limits.
- **vec0**: sqlite-vec's virtual table type for storing and searching vectors; uses special syntax like `vec_distance_L2()` for similarity queries.
- **Frozen dataclass**: Python dataclass with `frozen=True` making instances immutable after creation; ensures data integrity and hashability.
- **Schema migration**: Incremental database schema changes managed by version number (v2 → v3); preserves existing data while adding new tables/columns.

## Architecture

Normalized storage architecture with separate tables for chunks, vectors, and full-text search:

```
┌─────────────────────────────────────────────────────────┐
│                    documents table                       │
│  (existing + embedding_status column)                   │
└─────────────────────────┬───────────────────────────────┘
                          │ 1:N
                          ▼
┌─────────────────────────────────────────────────────────┐
│                     chunks table                         │
│  chunk_id (PK) | doc_id | index | text | section | page │
└─────────────────────────┬───────────────────────────────┘
            │             │             │
            ▼             ▼             ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────────────┐
│ chunks_fts    │ │ chunk_vectors │ │ (future)              │
│ (FTS5)        │ │ (vec0)        │ │ chunk_cluster_vectors │
│ Full-text     │ │ RAG vectors   │ │ Clustering vectors    │
└───────────────┘ └───────────────┘ └───────────────────────┘
```

**Core components:**

- **`embeddings/` module** — New module parallel to `ingestion/`, owns chunking and embedding domain logic
- **`MarkdownChunker`** — Section-aware chunking using markdown headers, then recursive splitting to ~512 tokens
- **`NomicEmbedder`** — Wraps sentence-transformers for nomic-embed-text-v1.5, handles task prefixes
- **`EmbeddingStorage`** — CRUD for chunks, vec0, and FTS5; uses connections from `core/storage.py`

**Data flow:**

1. `Library.embed(doc_id)` loads extracted markdown from `extracted_path`
2. `MarkdownChunker.chunk()` splits into `list[Chunk]` respecting structure
3. `NomicEmbedder.embed_chunks()` computes vectors with `search_document:` prefix
4. `EmbeddingStorage` stores chunks, vectors, and FTS5 entries in a single transaction
5. Document's `embedding_status` updated to CURRENT

**Embedding status model:**

| Status | Meaning |
|--------|---------|
| PENDING | No embeddings yet (new document or embedding failed) |
| CURRENT | Embeddings match current extracted text |
| STALE | Extracted text changed; embeddings need refresh |

Status transitions: PENDING → CURRENT (on successful embed), CURRENT → STALE (on re-extraction), STALE → CURRENT (on re-embed).

**Integration architecture:**

The `embeddings/` module is a deliberate evolution of the architecture, not ad hoc:

- Schema migrations remain centralized in `core/storage.py` (v2 → v3)
- sqlite-vec extension loaded in central `init_schema()`
- `EmbeddingStorage` uses shared connections and transaction patterns
- Library orchestrator coordinates document + embedding lifecycle
- Error codes added to unified `core/errors.py` hierarchy

## Existing Patterns

Investigation found clear patterns to follow:

**Module structure**: `ingestion/` provides the template — `base.py` for protocols, implementation files for concrete classes, `__init__.py` with lazy imports.

**Protocol-based design**: `ContentAcquirer` and `ContentExtractor` protocols in `ingestion/base.py`. The embedding layer follows this with `Chunker` and `Embedder` protocols.

**Frozen dataclasses**: `Document` in `core/models.py` is frozen and immutable. `Chunk` and `ChunkEmbedding` follow the same pattern.

**Schema migrations**: `core/storage.py` has `SCHEMA_VERSION` and `_migrate_v1_to_v2()`. Embedding tables added via `_migrate_v2_to_v3()`.

**Error handling**: `ErrorCode` enum in `core/errors.py` with exception hierarchy (`LocalLibraryError` → `ExtractionError`, etc.). New `EmbeddingError` follows this pattern.

**CLI commands**: Typer with Rich console, `@app.command()` pattern, `--json` output support. The `embed` command follows this.

**Divergence from existing patterns:**

Storage CRUD moves to `embeddings/storage.py` rather than staying in `core/storage.py`. This is justified because:
- sqlite-vec has unique requirements (extension loading, vec0 syntax)
- Embedding domain is sufficiently distinct (three interconnected tables)
- Keeps `core/` focused on core document model
- Schema definitions and migrations remain centralized in `core/`

## Implementation Phases

### Phase 1: Schema and Infrastructure

**Goal:** Database schema for embeddings, sqlite-vec integration, error codes.

**Components:**
- Schema migration (v2 → v3) in `core/storage.py` — adds `embedding_status` to documents, creates `chunks` table, `chunk_vectors` vec0 table, `chunks_fts` FTS5 table
- sqlite-vec extension loading in `init_schema()`
- Error codes (`EMBEDDING_*`) in `core/errors.py`
- `EmbeddingError` exception class

**Dependencies:** None (first phase)

**Done when:** Database initializes with new tables, sqlite-vec loads successfully, graceful degradation if extension unavailable.

### Phase 2: Core Data Models and Protocols

**Goal:** Define the embedding domain's data structures and interfaces.

**Components:**
- `embeddings/__init__.py` — module initialization with lazy imports
- `embeddings/base.py` — `Chunker` protocol, `Embedder` protocol, `Chunk` dataclass, `ChunkEmbedding` dataclass
- `EmbeddingStatus` enum (can live in `core/models.py` or `embeddings/base.py`)

**Dependencies:** Phase 1 (error codes)

**Done when:** Protocols and data models importable, type checking passes.

### Phase 3: Chunking Implementation

**Goal:** Section-aware markdown chunking.

**Components:**
- `embeddings/chunking.py` — `MarkdownChunker` implementation using LangChain's `MarkdownHeaderTextSplitter` and `RecursiveCharacterTextSplitter`
- Token counting via model tokenizer

**Dependencies:** Phase 2 (Chunker protocol, Chunk dataclass)

**Done when:** Chunker splits markdown respecting headers, produces chunks of ~512 tokens with ~15% overlap, handles edge cases (empty text, no headers, very long sections).

### Phase 4: Embedding Computation

**Goal:** nomic-embed-text-v1.5 integration via sentence-transformers.

**Components:**
- `embeddings/nomic.py` — `NomicEmbedder` implementation
- Model loading with lazy initialization
- Batch embedding with `search_document:` prefix
- `embed_query()` method stub (for M6, but interface defined now)

**Dependencies:** Phase 2 (Embedder protocol, ChunkEmbedding dataclass)

**Done when:** Embedder produces 768-dimensional vectors, handles batches efficiently, prepends correct task prefix.

### Phase 5: Embedding Storage

**Goal:** CRUD operations for chunks and vectors.

**Components:**
- `embeddings/storage.py` — `EmbeddingStorage` class
- Insert chunks + vectors transactionally
- FTS5 sync (triggers or manual)
- Delete by document (cascade)
- Query documents needing embedding

**Dependencies:** Phase 1 (schema), Phase 2 (data models)

**Done when:** Chunks and vectors persist correctly, FTS5 stays in sync, cascade delete works, can query PENDING/STALE documents.

### Phase 6: Library Integration

**Goal:** Integrate embedding pipeline into Library orchestrator.

**Components:**
- `Library.embed(doc_id)` method — full pipeline: load text → chunk → embed → store
- `Library.embed_all()` method — batch embedding with progress
- Embedding status transitions
- Integration with `Library.add()` (embed by default, graceful failure)
- Integration with `Library.delete()` (cascade)
- STALE transition on re-extraction

**Dependencies:** Phases 3, 4, 5

**Done when:** `Library.embed()` works end-to-end, status transitions correct, add embeds by default, delete cascades.

### Phase 7: CLI Command

**Goal:** `local-library embed` command.

**Components:**
- `cli/embed.py` — `embed` command with `--pending`, `--all`, `--force`, `--batch-size`, `--dry-run` options
- Modifications to `cli/add.py` — `--skip-embed` flag
- Modifications to `cli/zotero.py` — `--skip-embed` flag, two-phase import

**Dependencies:** Phase 6 (Library methods)

**Done when:** CLI commands work as specified, Rich progress display (with fallback if conflicts arise), proper error output.

### Phase 8: Integration Testing and Polish

**Goal:** End-to-end testing, edge cases, documentation.

**Components:**
- Integration tests for full pipeline
- Edge case handling (empty documents, very large documents, model loading failures)
- Verify Rich + sentence-transformers compatibility (fallback if needed)
- Update CLAUDE.md with new commands and architecture

**Dependencies:** All previous phases

**Done when:** All tests pass, CLI works reliably, documentation updated.

## Additional Considerations

**Rich progress compatibility:** Rich progress bars had conflicts with Marker in Zotero import, requiring Library recreation per batch. Similar issues may occur with sentence-transformers. Implementation should test early and have fallback to simple line-by-line output if needed.

**sqlite-vec graceful degradation:** If sqlite-vec extension is unavailable (e.g., fresh machine without it installed), the library should remain functional for document storage and text extraction. Embedding operations should fail clearly with `EMBEDDING_EXTENSION_UNAVAILABLE` error.

**Future extensibility:**
- **Clustering embeddings:** Architecture supports adding a second vec0 table (`chunk_cluster_vectors`) with `clustering:` prefix embeddings
- **Late chunking:** Chunk metadata separate from vectors allows re-embedding without re-chunking
- **Hierarchical retrieval:** Summary embeddings could be added as a separate vec0 table alongside chunk vectors
