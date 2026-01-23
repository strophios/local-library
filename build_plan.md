# Build Plan: Phase 1 — PDF Pipeline

This document describes the Phase 1 implementation plan for the local-library project. Phase 1 delivers a complete RAG pipeline for PDF documents imported from Zotero.

This plan applies the pipeline-first, layer-complete development approach described in `build_philosophy.md`.

## Scope

### What Phase 1 Includes

- **PDF ingestion** via Zotero import (the existing corpus)
- **Text extraction** via Marker
- **Embeddings** via nomic-embed-text-v1.5
- **Vector + full-text search** via sqlite-vec + FTS5
- **RAG queries** via custom wrapper + LiteLLM
- **CLI interface** for document management and queries

### What Phase 1 Does Not Include

Features deferred to later phases are documented in `future_roadmap.md`:
- Web content ingestion (trafilatura)
- Citation tooling (Neovim integration, CLI suggestion, MCP server)
- Auto-tagging and dual embeddings
- Note management
- Zotero export (pushing tags back)
- API/GUI interfaces

### Implementation References

This plan focuses on milestones, layer responsibilities, and testing strategy. For detailed implementation guidance (code patterns, schema designs, library configuration), see:

- **RAG_background/00_final_summary_report.md** — consolidated implementation recommendations
  - Section 1: PDF extraction with Marker
  - Section 2: Embeddings with nomic-embed-text, chunking strategy
  - Section 3: Vector storage schema, hybrid search implementation
  - Section 4: LLM query interface patterns

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
- nomic-embed-text-v1.5: 1024 dimensions, 8192 token context (see RAG report Section 2)
- Task-specific prefixes are mandatory: `search_query:` for queries, `search_document:` for chunks
- Chunking strategy: ~512 tokens with ~15% overlap, respect section boundaries
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

### M1: Record Creation and Storage ✓

**Goal:** Create document records, store basic metadata, persist to SQLite.

**Delivers:**
- SQLite schema for documents (without embeddings)
- Record creation with UUID, timestamps
- Basic CRUD operations
- CLI: `add` (creates record from path), `list`, `show`, `delete`

**Done when:**
- Can create a document record from a PDF path ✓
- Record persists across program restarts ✓
- Can list, view, and delete records ✓
- Tests pass for CRUD operations and error cases ✓

**Layers touched:** Storage (primary), Interface (basic CLI)

**Status:** Complete

---

### M2: Content Acquisition and Extraction ✓

**Goal:** Copy PDFs to managed storage, extract text via Marker.

**Delivers:**
- File copy to managed location
- Content hash computation
- Marker integration for PDF → markdown
- Duplicate detection (by path and hash)

**Done when:**
- PDFs are copied to library storage on add ✓
- Markdown extraction produces readable text ✓
- Duplicate files are detected and rejected ✓
- Tests pass for extraction and duplicate detection ✓

**Layers touched:** Ingestion (primary), Storage (path/hash storage)

**Status:** Complete

---

### M3a: Metadata Validation and Citekeys ✓

**Goal:** Parse, validate, and store CSL-JSON metadata; generate citekeys.

**Delivers:**
- CSL-JSON schema validation against official schema
- Citekey generation (BetterBibTeX-style: AuthorYearTitleword)
- Indexed field extraction (title, authors, issued_date)
- CLI `--metadata` flag for providing CSL-JSON at add time

**Done when:**
- Metadata stored correctly for manually-provided CSL-JSON ✓
- Citekeys generated consistently and deterministically ✓
- Field extraction produces searchable indexed values ✓
- Tests pass for metadata validation and citekey generation ✓

**Layers touched:** Ingestion (MetadataHandler), Storage (metadata columns)

**Status:** Complete

---

### M4: Zotero Import (Reordered) ✓

> **Note:** M4 is implemented before M3b because Zotero read-only access provides
> ground-truth metadata for testing the extraction quality and metadata extraction
> accuracy in M3b. See [Extraction Testing Infrastructure](#extraction-testing-infrastructure).

**Goal:** Read-only access to Zotero database for import and ground-truth testing.

**Delivers:**
- Zotero SQLite reader (read-only, with copy-if-locked handling)
- Item/attachment enumeration
- CSL-JSON construction from Zotero schema
- Ground-truth metadata access for extraction testing

**Done when:**
- Can read items and attachments from Zotero database ✓
- Metadata correctly mapped to CSL-JSON ✓
- Can access PDF paths and associated metadata for any item ✓
- Tests pass for Zotero schema mapping ✓

**Layers touched:** Ingestion (Zotero reader)

**Status:** Complete

**Deferred to later:** Full batch import CLI command (depends on M3b for complete pipeline)

---

### M3b: Text-Based Metadata Extraction

> **Dependency:** Requires M4 (Zotero Import) for ground-truth testing data.

**Goal:** Extract bibliographic metadata from document text when not explicitly provided.

**Delivers:**
- Heuristic extraction of title from extracted markdown (first heading, font size signals)
- Author name extraction from document headers/footers
- Date extraction from document content
- Confidence scoring for extracted metadata
- Integration with MetadataHandler (extracted metadata → validation → storage)

**Done when:**
- Title extracted correctly for >80% of test corpus (against Zotero ground truth)
- Author names extracted correctly for >70% of test corpus
- Date/year extracted correctly for >75% of test corpus
- Confidence scores correlate with actual accuracy
- Graceful fallback when extraction confidence is low

**Layers touched:** Ingestion (new TextMetadataExtractor), Core (confidence model)

**Testing:** See [Extraction Testing Infrastructure](#extraction-testing-infrastructure)

---

### M3c: External API Metadata Enrichment (Deferred)

**Goal:** Enrich metadata via external APIs when text-based extraction is uncertain.

**Status:** Deferred to post-Phase 1. Evaluate need based on M3b accuracy results.

**See:** `future_roadmap.md` § "External API Metadata Enrichment (M3c)" for full implementation details, API cascade architecture, and decision criteria.

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

## Extraction Testing Infrastructure

Testing metadata extraction quality requires ground-truth data. Rather than manually annotating PDFs, we leverage Zotero's existing metadata as the authoritative source. This creates a dependency: M4 (Zotero read-only access) must be implemented before M3b (text-based metadata extraction) can be properly tested.

### Dependency Chain

```
Extraction Quality → Metadata Extraction Accuracy
       ↓                        ↓
   Marker output         Title/Author/Date parsing
   (M2, complete)           (M3b, pending)
                               ↓
                    Zotero ground truth (M4)
```

Poor extraction quality will cause metadata extraction to fail regardless of how sophisticated the parsing heuristics are. Testing must validate both layers.

### Test Corpus Design (Two-Tier)

**Tier 1: Golden Set (~10-20 PDFs)**
- Hand-selected to cover diverse document types
- Categories:
  - Single-column academic (journal articles)
  - Two-column academic (IEEE, ACM formats)
  - Book chapters
  - Technical reports
  - Scanned/OCR-heavy documents
  - Math-heavy papers
  - Tables-heavy papers
- Each PDF has manually verified Zotero metadata
- Used for detailed quality analysis and debugging

**Tier 2: Smoke Set (~50-100 PDFs)**
- Stratified random sample from Zotero library
- Used for regression testing and aggregate accuracy metrics
- Zotero metadata assumed correct (fix edge cases in Zotero itself)

### Ground Truth Source

Zotero metadata serves as ground truth for testing:
- **Title**: `items.title` field
- **Authors**: `creators` table with `creatorTypeID=1` (author)
- **Date**: `items.date` or parsed from `itemData` fields
- **Type**: `itemTypes.typeName`

If Zotero metadata is incorrect for a test document, fix it in Zotero rather than creating separate annotations.

### Quality Metrics

**Extraction Quality (M2 validation)**
- Character count (minimum threshold)
- Printable character ratio (detect garbled output)
- Structure preservation (heading count, paragraph count)
- Section detection accuracy (for documents with known structure)

**Metadata Extraction Accuracy (M3b validation)**
- Title: Exact match or normalized similarity (Levenshtein, token overlap)
- Authors: Set comparison (order-independent), partial credit for subset
- Date: Year match (strict), full date match (bonus)
- Aggregate: Precision, recall, F1 per field

### Test Implementation

Tests live in `tests/extraction/` with:
- `conftest.py` - Fixtures for loading test corpus and Zotero ground truth
- `test_extraction_quality.py` - Marker output quality validation
- `test_metadata_extraction.py` - Title/author/date extraction accuracy
- `golden_set/` - Golden set PDFs (git-lfs or symlinks to Zotero storage)
- `golden_set_manifest.json` - Optional manifest for categorization and expected failures
- `smoke_set_manifest.json` - List of Zotero item keys for smoke testing (deferred)

**Status:** Golden set infrastructure complete. Smoke set deferred until M3b is further along.

**Note:** Extraction tests are slow (~4s/page via Marker). By default, tests marked `@pytest.mark.extraction` are skipped. Run with `--run-extraction` flag to execute them.

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

### Extraction Quality Tests

See [Extraction Testing Infrastructure](#extraction-testing-infrastructure) for detailed design.

- **Golden set tests**: Detailed quality validation against hand-selected PDFs
- **Smoke tests**: Aggregate accuracy metrics across stratified sample
- **Metadata extraction accuracy**: Title/author/date extraction validated against Zotero ground truth

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

1. ~~**Extracted text storage:** In database as TEXT column, or as separate .md files?~~ **Resolved:** TEXT column in database (implemented in M2)

2. **Chunking boundaries:** How aggressively to respect paragraph/section boundaries vs. fixed token counts?

3. **FTS configuration:** Which tokenizer? Stemming? The right FTS5 options for academic text.

4. ~~**Error recovery:** If extraction fails mid-import, what state should the record be in?~~ **Resolved:** Transaction rollback, no partial records (implemented in M1-M2)

5. ~~**CLI framework:** Click? Typer? argparse?~~ **Resolved:** Typer with Rich (implemented in M1)

6. **Metadata extraction heuristics:** What signals best identify title vs. heading? How to handle multi-line titles? Author name formats vary widely.

7. **Confidence thresholds:** At what confidence level should extracted metadata be auto-accepted vs. flagged for review?

---

## Next Steps

Current status: M1 ✓, M2 ✓, M3a ✓, M4 ✓

1. **M3b: Text-based metadata extraction** — Implement heuristics with confidence scoring, validated against Zotero ground truth via extraction testing infrastructure
2. Continue to M5 (embeddings) once metadata pipeline is complete
