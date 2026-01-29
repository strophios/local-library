# Core Domain

Last verified: 2026-01-28

## Purpose

Owns the document lifecycle: what a document IS (models), how it's persisted (storage), and how operations are orchestrated (Library). All other domains depend on core for document identity.

## Contracts

- **Exposes**: Document, DocumentStatus (PENDING, READY, FAILED, NEEDS_REVIEW), AddResult, FieldExtraction, TextExtractionResult, ErrorCode hierarchy (including MetadataError, ZoteroError), Library class (with get_by_citekey, get_all_citekeys, update_metadata), storage functions
- **Guarantees**:
  - Document.id is UUID, globally unique
  - Document.content_hash is SHA-256, content-addressable
  - AddResult returns existing document on duplicate (idempotent adds)
  - All errors inherit LocalLibraryError with ErrorCode for programmatic handling
  - Library dispatches to appropriate handler via `can_handle()` protocol
  - Library.add() accepts optional CSL-JSON metadata; validates and stores with collision-free citekeys
  - Library.add() extracts metadata from text when no explicit metadata provided (if text_extraction_enabled)
  - Documents with low-confidence extraction are set to NEEDS_REVIEW status
  - Library accepts `pdf_llm_enabled` parameter to enable Marker LLM-enhanced extraction for PDFs
- **Expects**: Sources handled by at least one registered acquirer; files handled by at least one extractor

## Dependencies

- **Uses**: `config` (paths), `ingestion` (ContentAcquirer, ContentExtractor protocols, MetadataHandler, TextMetadataExtractor)
- **Used by**: `cli`, future domains (embeddings, search)
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
- **Text extraction integration**: Library._process_text_extraction() handles metadata extraction from document text, sets NEEDS_REVIEW when confidence is low
- **Citekey lookup**: Library.get_by_citekey() returns Document or None; Library.get_all_citekeys() returns all non-null citekeys
- **Metadata updates**: Library.update_metadata() allows updating status, citekey, and csl_json with automatic indexed field extraction

## Invariants

- Every Document has exactly one status (PENDING, READY, FAILED, or NEEDS_REVIEW)
- content_hash uniquely identifies file content (no two documents share a hash)
- storage_path follows Git-style layout: `ab/cd/abcdef...ext`
- All timestamps are UTC
- Handler dispatch order matters: first matching handler wins
- NEEDS_REVIEW status implies extraction succeeded but needs human verification

## Key Files

- `models.py` - Document, AcquisitionResult, ExtractionResult, AddResult, FieldExtraction, TextExtractionResult
- `errors.py` - ErrorCode enum, exception hierarchy (includes ACQUISITION_*, EXTRACTION_*, METADATA_*, ZOTERO_* codes)
- `storage.py` - SQLite CRUD (get_connection, init_schema, create/get/update/delete)
- `library.py` - Library orchestrator (add, get, get_by_citekey, get_all_citekeys, list, delete, update_metadata) with handler dispatch and text extraction integration

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
