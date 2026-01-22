# Core Domain

Last verified: 2026-01-22

## Purpose

Owns the document lifecycle: what a document IS (models), how it's persisted (storage), and how operations are orchestrated (Library). All other domains depend on core for document identity.

## Contracts

- **Exposes**: Document, DocumentStatus, AddResult, ErrorCode hierarchy (including MetadataError), Library class, storage functions
- **Guarantees**:
  - Document.id is UUID, globally unique
  - Document.content_hash is SHA-256, content-addressable
  - AddResult returns existing document on duplicate (idempotent adds)
  - All errors inherit LocalLibraryError with ErrorCode for programmatic handling
  - Library dispatches to appropriate handler via `can_handle()` protocol
  - Library.add() accepts optional CSL-JSON metadata; validates and stores with collision-free citekeys
- **Expects**: Sources handled by at least one registered acquirer; files handled by at least one extractor

## Dependencies

- **Uses**: `config` (paths), `ingestion` (ContentAcquirer, ContentExtractor protocols, MetadataHandler)
- **Used by**: `cli`, future domains (embeddings, search)
- **Boundary**: Core MUST NOT import from cli

## Key Decisions

- **Frozen dataclasses**: Document and result types are immutable (Functional Core pattern)
- **ErrorCode enum**: Machine-parseable error codes enable retry logic and user feedback
- **Idempotent adds**: Duplicate detection by path AND hash prevents data duplication
- **Status lifecycle**: PENDING -> READY or FAILED tracks extraction state
- **Handler injection**: Library accepts `acquirers` and `extractors` lists via constructor (defaults: FileAcquirer, PdfExtractor)
- **Protocol dispatch**: `_find_acquirer()` and `_find_extractor()` iterate handlers, first `can_handle()` wins
- **Citekey collision handling**: `get_unique_citekey()` appends suffixes (a, b, c...) to ensure uniqueness

## Invariants

- Every Document has exactly one status (PENDING, READY, or FAILED)
- content_hash uniquely identifies file content (no two documents share a hash)
- storage_path follows Git-style layout: `ab/cd/abcdef...ext`
- All timestamps are UTC
- Handler dispatch order matters: first matching handler wins

## Key Files

- `models.py` - Document, AcquisitionResult, ExtractionResult, AddResult
- `errors.py` - ErrorCode enum, exception hierarchy (includes ACQUISITION_UNSUPPORTED_SOURCE, EXTRACTION_UNSUPPORTED_FORMAT)
- `storage.py` - SQLite CRUD (get_connection, init_schema, create/get/update/delete)
- `library.py` - Library orchestrator (add, get, list, delete) with handler dispatch

## Gotchas

- Library.add() re-raises ExtractionError after creating FAILED record (caller sees both)
- Library.add() raises MetadataError if provided metadata fails validation (before updating record)
- get_documents_by_partial_id() is case-sensitive UUID prefix match
- storage.py functions require explicit connection parameter (no global state)
- No matching acquirer raises ACQUISITION_UNSUPPORTED_SOURCE; no matching extractor raises EXTRACTION_UNSUPPORTED_FORMAT
