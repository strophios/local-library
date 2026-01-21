# Core Domain

Last verified: 2026-01-21

## Purpose

Owns the document lifecycle: what a document IS (models), how it's persisted (storage), and how operations are orchestrated (Library). All other domains depend on core for document identity.

## Contracts

- **Exposes**: Document, DocumentStatus, AddResult, ErrorCode hierarchy, Library class, storage functions
- **Guarantees**:
  - Document.id is UUID, globally unique
  - Document.content_hash is SHA-256, content-addressable
  - AddResult returns existing document on duplicate (idempotent adds)
  - All errors inherit LocalLibraryError with ErrorCode for programmatic handling
- **Expects**: Valid file paths for add operations; database initialized before queries

## Dependencies

- **Uses**: `config` (paths), `ingestion` (acquirer, extractor)
- **Used by**: `cli`, future domains (embeddings, search)
- **Boundary**: Core MUST NOT import from cli

## Key Decisions

- **Frozen dataclasses**: Document and result types are immutable (Functional Core pattern)
- **ErrorCode enum**: Machine-parseable error codes enable retry logic and user feedback
- **Idempotent adds**: Duplicate detection by path AND hash prevents data duplication
- **Status lifecycle**: PENDING -> READY or FAILED tracks extraction state

## Invariants

- Every Document has exactly one status (PENDING, READY, or FAILED)
- content_hash uniquely identifies file content (no two documents share a hash)
- storage_path follows Git-style layout: `ab/cd/abcdef...ext`
- All timestamps are UTC

## Key Files

- `models.py` - Document, AcquisitionResult, ExtractionResult, AddResult
- `errors.py` - ErrorCode enum, exception hierarchy
- `storage.py` - SQLite CRUD (get_connection, init_schema, create/get/update/delete)
- `library.py` - Library orchestrator (add, get, list, delete)

## Gotchas

- Library.add() re-raises ExtractionError after creating FAILED record (caller sees both)
- get_documents_by_partial_id() is case-sensitive UUID prefix match
- storage.py functions require explicit connection parameter (no global state)
