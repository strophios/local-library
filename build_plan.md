# Build Plan: Local Library

This document describes the implementation plan for the local-library project, a personal knowledge management system with RAG capabilities. It applies the pipeline-first, layer-complete development approach described in `build_philosophy.md`.

## Strategic Context

### Scope Decision: Thick Vertical Slice

Rather than building all functionality for all content types, or building a thin proof-of-concept, we're taking a **thick vertical slice** approach:

- **Full depth:** Build the complete pipeline from ingestion through RAG query
- **Narrow width:** Initially support only PDF ingestion via Zotero import
- **Expand later:** Web content ingestion, auto-tagging, and other features can be added after the core pipeline works

This approach prioritizes:
- Getting to useful RAG functionality with the existing corpus (PDFs in Zotero)
- Building each layer properly, not minimally
- Deferring orthogonal concerns (web content) that don't block core value

### What's Deferred

| Feature | Reason for Deferral |
|---------|---------------------|
| Web content ingestion | Orthogonal to PDF pipeline; can be added as alternate ingestion path |
| Auto-tagging | Enhancement layer; requires working embeddings first |
| Zotero export | Closes the loop but not needed for querying |
| Note management | Nice-to-have; doesn't block RAG functionality |
| Dual embeddings | Optimization for auto-tagging; single embedding set sufficient initially |

---

## Architectural Layers

Four horizontal concerns cut across the entire system:

### Storage Layer

**Responsibility:** All data persistence—schema design, CRUD operations, transactions, queries.

**Components:**
- SQLite database with document records, metadata, tags, embeddings
- sqlite-vec for vector storage and similarity search
- FTS5 for full-text search
- Filesystem layout for original files and extracted content

**Key Design Decisions:**
- Single SQLite file for portability (documents + vectors + FTS in one DB)
- CSL-JSON stored as blob with indexed fields extracted for queries
- Content hashes for duplicate detection
- Embeddings stored per-chunk with foreign key to parent document

**Completeness Checklist:**
- [ ] Create, read, update, delete for documents
- [ ] Create, read, delete for embeddings (update = delete + recreate)
- [ ] Tag management (add, remove, list by document, list by tag)
- [ ] Vector similarity search
- [ ] Full-text search
- [ ] Hybrid search (RRF combination)
- [ ] Transaction support for multi-step operations
- [ ] Error handling for constraint violations, missing records, etc.

### Ingestion Layer

**Responsibility:** Content acquisition and extraction—getting raw files, parsing them to text, extracting metadata.

**Components:**
- PDF extraction via Marker
- (Future: Web extraction via trafilatura)
- (Future: EPUB, other formats)
- Metadata extraction from content and external sources (CrossRef, GROBID)

**Key Design Decisions:**
- Markdown as canonical extracted text format
- Copy files rather than alias (independence from source)
- Metadata extraction conditioned on missing key fields (title, author)
- Polymorphic content handler interface for different file types

**Completeness Checklist:**
- [ ] PDF acquisition (copy from path)
- [ ] PDF text extraction (Marker → markdown)
- [ ] Metadata extraction from PDF content
- [ ] CSL-JSON metadata parsing and validation
- [ ] Content hashing for duplicate detection
- [ ] Error handling for corrupted files, extraction failures

### Embeddings Layer

**Responsibility:** Text chunking, vector computation, similarity operations.

**Components:**
- Chunking logic (size, overlap, boundary detection)
- nomic-embed-text-v1.5 for embedding computation
- Query embedding with appropriate prefix (`search_query:`)
- Document embedding with appropriate prefix (`search_document:`)

**Key Design Decisions:**
- nomic-embed-text-v1.5: 768 dimensions, 8192 token context
- Task-specific prefixes are mandatory (model was trained with them)
- Chunking strategy: ~512 tokens with ~50 token overlap, respect paragraph boundaries
- Brute-force search acceptable up to ~100K vectors

**Completeness Checklist:**
- [ ] Text chunking with configurable parameters
- [ ] Embedding computation for document chunks
- [ ] Embedding computation for queries
- [ ] Batch embedding for efficiency
- [ ] Re-embedding on document update
- [ ] Embedding deletion cascades with document deletion

### Interface Layer

**Responsibility:** User interaction—how users add documents, query the system, manage their library.

**Components:**
- CLI for document operations (add, list, search, delete)
- RAG query interface (natural language → retrieved context → LLM response)
- (Future: API for programmatic access)
- (Future: TUI or GUI for browsing)

**Key Design Decisions:**
- CLI-first for initial implementation
- RAG queries via custom wrapper + LiteLLM for provider flexibility
- Hybrid retrieval (vector + FTS) with RRF fusion

**Completeness Checklist:**
- [ ] Add document (from path, from Zotero)
- [ ] List documents (all, filtered, search)
- [ ] View document details
- [ ] Delete document
- [ ] RAG query (question → answer with sources)
- [ ] Search without LLM (just retrieval)
- [ ] Batch operations (Zotero import)

---

## Pipeline Stages

The record flow—what happens when a document enters the system:

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│   Input     │───▶│  Acquisition │───▶│ Extraction  │───▶│   Metadata   │
│  (path/URL) │    │ (copy file)  │    │ (parse text)│    │  (CSL-JSON)  │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘
                                                                  │
                                                                  ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│   Output    │◀───│   Retrieval  │◀───│   Storage   │◀───│  Embedding   │
│  (response) │    │(query + RAG) │    │  (persist)  │    │  (vectorize) │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘
```

### Stage 1: Input
- Receive content locator (file path or URL) and optional metadata
- Validate input, check for duplicates (by path/URL)
- Create timestamped record with UUID

**Layers touched:** Storage (record creation), Interface (input handling)

### Stage 2: Acquisition
- Copy/download raw content to managed storage location
- Compute content hash
- Check for duplicates (by content hash)
- Store path to acquired content

**Layers touched:** Storage (update record), Ingestion (file operations)

### Stage 3: Extraction
- Parse raw content to markdown text
- Store extracted text (in DB or as file)

**Layers touched:** Storage (update record), Ingestion (content parsing)

### Stage 4: Metadata
- Extract or validate bibliographic metadata
- Convert to CSL-JSON format
- Generate citekey
- Store metadata blob and indexed fields

**Layers touched:** Storage (update record), Ingestion (metadata extraction)

### Stage 5: Embedding
- Chunk extracted text
- Compute embeddings for each chunk (with `search_document:` prefix)
- Store embeddings with chunk text and position

**Layers touched:** Storage (embedding insert), Embeddings (chunking, vectorization)

### Stage 6: Retrieval
- Accept natural language query
- Compute query embedding (with `search_query:` prefix)
- Perform hybrid search (vector similarity + FTS)
- Rank and select top chunks

**Layers touched:** Storage (search), Embeddings (query embedding)

### Stage 7: Output
- Assemble context from retrieved chunks
- Format prompt with query and context
- Call LLM via LiteLLM
- Return response with source citations

**Layers touched:** Interface (response formatting), Embeddings (context assembly)

---

## Milestones

Each milestone extends the pipeline and delivers testable functionality.

### M1: Record Creation and Storage

**Goal:** Create document records, store basic metadata, persist to SQLite.

**Delivers:**
- SQLite schema for documents (without embeddings)
- Record creation with UUID, timestamps
- Basic CRUD operations
- CLI: `add` (creates record from path), `list`, `show`, `delete`

**Done when:**
- Can create a document record from a PDF path
- Record persists across program restarts
- Can list, view, and delete records
- Tests pass for CRUD operations and error cases

**Layers touched:** Storage (primary), Interface (basic CLI)

---

### M2: Content Acquisition and Extraction

**Goal:** Copy PDFs to managed storage, extract text via Marker.

**Delivers:**
- File copy to managed location
- Content hash computation
- Marker integration for PDF → markdown
- Duplicate detection (by path and hash)

**Done when:**
- PDFs are copied to library storage on add
- Markdown extraction produces readable text
- Duplicate files are detected and rejected
- Tests pass for extraction and duplicate detection

**Layers touched:** Ingestion (primary), Storage (path/hash storage)

---

### M3: Metadata Handling

**Goal:** Parse, validate, and store CSL-JSON metadata; generate citekeys.

**Delivers:**
- CSL-JSON schema validation
- Citekey generation (BetterBibTeX-style)
- Indexed field extraction (title, author, date)
- Metadata extraction from PDF if not provided

**Done when:**
- Metadata stored correctly for manually-provided CSL-JSON
- Citekeys generated consistently
- Basic metadata extracted from PDFs lacking explicit metadata
- Tests pass for metadata validation and citekey generation

**Layers touched:** Ingestion (metadata extraction), Storage (metadata storage)

---

### M4: Zotero Import

**Goal:** Batch import documents from Zotero database.

**Delivers:**
- Zotero SQLite reader (read-only, with copy-if-locked handling)
- Item/attachment enumeration
- CSL-JSON construction from Zotero schema
- Batch invocation of record flow

**Done when:**
- Can import all PDF items from a Zotero library
- Metadata correctly mapped to CSL-JSON
- Already-imported items are skipped
- Tests pass for Zotero schema mapping

**Layers touched:** Ingestion (Zotero reader), Interface (import command)

---

### M5: Embedding Pipeline

**Goal:** Chunk documents and compute embeddings.

**Delivers:**
- Text chunking with configurable parameters
- nomic-embed-text integration
- Embedding storage in sqlite-vec
- Re-embedding on document update

**Done when:**
- Documents have searchable embeddings after add/import
- Chunk boundaries respect text structure
- Embeddings are deleted when documents are deleted
- Tests pass for chunking logic and embedding storage

**Layers touched:** Embeddings (primary), Storage (vector tables)

---

### M6: Retrieval

**Goal:** Search documents by vector similarity and full-text.

**Delivers:**
- Query embedding computation
- Vector similarity search via sqlite-vec
- Full-text search via FTS5
- Hybrid ranking via RRF

**Done when:**
- Relevant chunks retrieved for test queries
- Hybrid search outperforms vector-only on keyword queries
- Search results include source document references
- Tests pass for retrieval quality (manual evaluation initially)

**Layers touched:** Embeddings (query), Storage (search), Interface (search command)

---

### M7: RAG Query Interface

**Goal:** Answer natural language questions using retrieved context.

**Delivers:**
- Context assembly from retrieved chunks
- Prompt construction with sources
- LiteLLM integration for LLM calls
- Response formatting with citations

**Done when:**
- Questions about ingested documents receive relevant answers
- Responses cite source documents
- System handles "I don't know" for out-of-scope queries
- Basic latency acceptable (<10s for typical query)

**Layers touched:** Interface (primary), Embeddings (retrieval)

---

## Testing Strategy

Following the layered testing model from `build_philosophy.md`:

### Unit Tests (Substeps)

- Chunking function edge cases (empty text, single paragraph, code blocks)
- CSL-JSON validation for malformed input
- Citekey generation determinism
- SQL query correctness

### Pipeline Stage Tests

- Record creation with various input combinations
- Extraction produces expected markdown for test PDFs
- Embedding computation returns correct dimensions
- Retrieval returns relevant results for known queries

### Transition Tests (Contracts)

- Acquisition output is valid input for extraction
- Extraction output is valid input for chunking
- Zotero reader output matches expected record flow input

### Layer Completeness Tests

- Storage: CRUD for all entities, error handling, transaction rollback
- Ingestion: All supported file types, corrupted file handling
- Embeddings: Batch operations, deletion cascades
- Interface: All commands, invalid input handling

### Integration Tests

- End-to-end: Add PDF → query about its content → receive answer
- Zotero import → verify searchability of imported documents

---

## Open Questions

Decisions to make during implementation:

1. **Extracted text storage:** In database as TEXT column, or as separate .md files? (Tradeoff: query simplicity vs. filesystem browsability)

2. **Chunking boundaries:** How aggressively to respect paragraph/section boundaries vs. fixed token counts?

3. **FTS configuration:** Which tokenizer? Stemming? The right FTS5 options for academic text.

4. **Error recovery:** If extraction fails mid-import, what state should the record be in? Tombstone? Deleted? Marked failed?

5. **CLI framework:** Click? Typer? argparse? (Affects interface layer implementation)

---

## Next Steps

1. Begin M1: Design and implement SQLite schema
2. Scaffold project structure (src layout, test directories, dependencies)
3. Implement basic CLI with record CRUD
4. Write initial test suite for storage layer
