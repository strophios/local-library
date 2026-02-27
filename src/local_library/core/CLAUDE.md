# Core Domain

Last verified: 2026-02-27

## Purpose

Owns the document lifecycle: what a document IS (models), how it's persisted (storage), and how operations are orchestrated (Library). All other domains depend on core for document identity.

## Contracts

- **Exposes**: Document, DocumentStatus (PENDING, READY, FAILED, NEEDS_REVIEW), EmbeddingStatus (PENDING, CURRENT, STALE), AddResult, FieldExtraction, TextExtractionResult, ErrorCode hierarchy (including MetadataError, ZoteroError, EmbeddingError), Library class (with get_by_citekey, get_all_citekeys, update_metadata, embed, embed_all, get_retriever), storage functions, vec_extension module
- **Guarantees**:
  - Document.id is UUID, globally unique
  - Document.content_hash is SHA-256, content-addressable
  - AddResult returns existing document on duplicate (idempotent adds)
  - All errors inherit LocalLibraryError with ErrorCode for programmatic handling
  - Library dispatches to appropriate handler via `can_handle()` protocol
  - Library.add() accepts optional CSL-JSON metadata; validates and stores with collision-free citekeys
  - Library.add() accepts optional citekey parameter to preserve external citekeys (e.g., from Zotero); bypasses citekey generation when provided
  - Library.add() extracts metadata from text when no explicit metadata provided (if text_extraction_enabled)
  - Documents with low-confidence extraction are set to NEEDS_REVIEW status
  - Library accepts `pdf_llm_enabled` parameter to enable Marker LLM-enhanced extraction for PDFs
  - EmbeddingStatus tracks embedding lifecycle (PENDING → CURRENT, CURRENT → STALE on re-extraction, STALE → CURRENT on re-embed)
  - sqlite-vec extension loaded conditionally; library functions without it for document storage (graceful degradation)
  - Library.embed() computes and stores embeddings, updates status to CURRENT
  - Library.embed_all() processes all PENDING/STALE documents
  - Library.delete() cascades to remove embeddings
  - Library.add() embeds by default when embed_on_add=True and sqlite-vec available
  - Library.get_retriever() factory method returns Retriever protocol-compliant instances (HybridRetriever, VectorRetriever, or FTSRetriever)
- **Expects**: Sources handled by at least one registered acquirer; files handled by at least one extractor

## Dependencies

- **Uses**: `config` (paths), `ingestion` (ContentAcquirer, ContentExtractor protocols, MetadataHandler, TextMetadataExtractor), `embeddings` (MarkdownChunker, NomicEmbedder, EmbeddingStorage)
- **Used by**: `cli`, `embeddings` (retrieval module imports from core.errors)
- **Boundary**: Core MUST NOT import from cli

## Key Decisions

- **Frozen dataclasses**: Document and result types are immutable (Functional Core pattern)
- **ErrorCode enum**: Machine-parseable error codes enable retry logic and user feedback
- **Idempotent adds**: Duplicate detection by path AND hash prevents data duplication
- **Status lifecycle**: PENDING -> READY, FAILED, or NEEDS_REVIEW tracks extraction state. NEEDS_REVIEW indicates extraction succeeded but confidence is low.
- **Handler injection**: Library accepts `acquirers` and `extractors` lists via constructor (defaults: FileAcquirer, PdfExtractor)
- **PDF LLM extraction config**: Library accepts `pdf_llm_enabled` parameter (default False) passed to default PdfExtractor. Custom extractors (passed via constructor) are not affected.
- **Protocol dispatch**: `_find_acquirer()` and `_find_extractor()` iterate handlers, first `can_handle()` wins
- **Lazy Library import**: `core.__init__` uses `__getattr__` to defer Library import until first access. Breaks circular dependency: `core.__init__` -> `core.library` -> `ingestion.pdf` -> `core.errors`. Eager imports for models/errors remain since they don't cause cycles.
- **Citekey collision handling**: `get_unique_citekey()` appends suffixes (a, b, c...) to ensure uniqueness
- **Citekey preservation**: Library.add() accepts optional `citekey` parameter that bypasses generation. Used when importing from external systems (Zotero) to preserve existing citekeys for deduplication
- **Text extraction integration**: Library._process_text_extraction() handles metadata extraction from document text, sets NEEDS_REVIEW when confidence is low
- **Citekey lookup**: Library.get_by_citekey() returns Document or None; Library.get_all_citekeys() returns all non-null citekeys
- **Metadata updates**: Library.update_metadata() allows updating status, citekey, and csl_json with automatic indexed field extraction
- **EmbeddingStatus enum**: Tracks embedding state separately from DocumentStatus (orthogonal concerns)
- **Conditional sqlite-vec**: Extension loaded only when available; graceful degradation allows library to function for document storage even without vector search
- **Cascade deletion**: Chunks and embeddings deleted via ON DELETE CASCADE foreign key when parent document deleted
- **Embedding integration**: Library orchestrates chunking→embedding→storage pipeline; graceful failure on add (document usable, just not vector-searchable)
- **embed_on_add config**: Defaults to True; controlled via Library constructor parameter

## Invariants

- Every Document has exactly one status (PENDING, READY, FAILED, or NEEDS_REVIEW)
- content_hash uniquely identifies file content (no two documents share a hash)
- storage_path follows Git-style layout: `ab/cd/abcdef...ext`
- All timestamps are UTC
- Handler dispatch order matters: first matching handler wins
- NEEDS_REVIEW status implies extraction succeeded but needs human verification

## Key Files

- `models.py` - Document, AcquisitionResult, ExtractionResult, AddResult, FieldExtraction, TextExtractionResult, EmbeddingStatus
- `errors.py` - ErrorCode enum, exception hierarchy (includes ACQUISITION_*, EXTRACTION_*, METADATA_*, ZOTERO_*, EMBEDDING_* codes)
- `storage.py` - SQLite CRUD (get_connection, init_schema, create/get/update/delete), schema v3 with chunks and FTS5
- `library.py` - Library orchestrator (add, get, get_by_citekey, get_all_citekeys, list, delete, embed, embed_all, update_metadata, get_retriever) with handler dispatch and text extraction integration
- `vec_extension.py` - sqlite-vec extension loading, vec0 table creation, availability checking

## Gotchas

- Library.add() re-raises ExtractionError after creating FAILED record (caller sees both)
- Library.add() raises MetadataError if provided metadata fails validation (before updating record)
- get_documents_by_partial_id() is case-sensitive UUID prefix match
- storage.py functions require explicit connection parameter (no global state)
- No matching acquirer raises ACQUISITION_UNSUPPORTED_SOURCE; no matching extractor raises EXTRACTION_UNSUPPORTED_FORMAT
- `from local_library.core import Library` works but is lazy-loaded; `from local_library.core.library import Library` is direct but may trigger circular import issues if called at module level
- Library constructor accepts text_extraction_* parameters to configure automatic metadata extraction behavior
- When no explicit metadata is provided and text extraction is enabled, Library.add() attempts to extract metadata from the document text
- `pdf_llm_enabled` only affects the default PdfExtractor; custom extractors must configure LLM mode themselves
- Library.embed() raises EmbeddingError if sqlite-vec unavailable or document not READY
- Embedding failure in add() is non-fatal; document created but embedding_status stays PENDING
- embed_on_add respects sqlite-vec availability; disabled automatically if extension unavailable
- Library.get_retriever() raises EmbeddingError if sqlite-vec unavailable; factory method handles embedder lazy-init for vector/hybrid modes
