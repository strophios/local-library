# M1+M2: Record Creation, Storage, and PDF Extraction Design

## Summary

This design implements the first two milestones of the PDF RAG pipeline: document record creation and PDF text extraction. The system accepts a local PDF file path, copies the file into content-addressable storage (organized by content hash), extracts the text using Marker (a neural PDF-to-markdown tool), and persists metadata and status in SQLite. The architecture follows a protocol-based design where content acquisition and extraction are abstracted behind interfaces, enabling future expansion to web articles and other content types without modifying orchestration logic.

The implementation uses a module pattern with three layers: storage (SQLite operations), ingestion (file acquisition and PDF extraction), and interface (CLI commands). The add pipeline validates the source file, checks for duplicates by both original path and content hash (returning existing records rather than erroring), performs extraction, validates output quality, and updates record status atomically. Records track their lifecycle state (`pending`, `ready`, `failed`) and store error details for debugging. The CLI provides commands for adding, listing, viewing, and deleting documents, with UUID partial matching and JSON output for programmatic use.

## Definition of Done

**Primary deliverables:**
1. **Storage layer**: SQLite schema for documents with status tracking, content-hash-based file storage layout
2. **Ingestion layer**: PDF copy to managed storage, Marker extraction to markdown
3. **Interface layer**: CLI with `add`, `list`, `show`, `delete` commands

**Success criteria:**
- Can add a PDF: file is copied to managed storage, text is extracted via Marker, record persists across restarts
- Duplicate detection works (by original path and content hash), returns existing record on duplicate
- Failed extractions create records with `status='failed'` for later retry
- Can list, view details, and delete records via UUID (partial match supported)
- Tests pass for CRUD operations, extraction, duplicate handling, and error cases

**Explicit scope boundaries:**
- **IN**: Record CRUD, file acquisition, Marker extraction, duplicate detection, basic CLI
- **OUT**: Metadata extraction/parsing (M3), Zotero import (M4), embeddings (M5), citekey generation (M3)

**Key design decisions:**
- **CLI framework**: Typer (type hints, auto-help generation)
- **Path management**: platformdirs for XDG-compliant paths
- **File storage**: Content-hash layout (`ab/cd/abcd1234...pdf`)
- **Record states**: `pending` (created, not yet processed), `ready` (extraction complete), `failed` (extraction failed)
- **Duplicate handling**: Idempotent adds—return existing record rather than error
- **Metadata**: Nullable fields in schema (citekey, csl_json) to support optional metadata at creation; not populated in M1+M2
- **Identifiers**: UUID with partial matching for CLI; will transition to citekey-primary in M3

## Glossary

- **Marker**: Neural PDF extraction tool that converts PDFs to markdown with formatting preservation; runs locally on CPU or GPU
- **Content-addressable storage**: File organization scheme using cryptographic hashes (e.g., SHA-256) as filenames, ensuring deduplication and immutability (similar to Git's object store)
- **platformdirs**: Python library providing platform-specific standard directories (e.g., `~/.local/share` on Linux, `~/Library/Application Support` on macOS)
- **Typer**: Python CLI framework built on type hints; auto-generates help text and option parsing from function signatures
- **Protocol (Python)**: Structural typing mechanism (PEP 544) defining interfaces via method signatures; enables duck typing with static analysis support
- **CSL-JSON**: Citation Style Language JSON format for bibliographic metadata; standard interchange format used by Zotero, Pandoc, and citation processors
- **Idempotent**: Operation that produces the same result when executed multiple times (here: duplicate adds return existing record rather than creating duplicates or erroring)
- **Content hash**: Cryptographic digest (SHA-256) computed from file contents; used for duplicate detection and content-addressable storage paths
- **CRUD**: Create, Read, Update, Delete—standard database operations
- **Rich**: Python library for styled terminal output (colors, tables, formatting)

## Architecture

Module pattern with Acquirer + Extractor protocols for extensibility to future content types (web, etc.).

```
CLI Commands → Library (orchestration)
                   ↓
         ┌────────┴────────┐
         ↓                 ↓
    storage.py        ingestion/
    (all SQL)         ├── base.py (Protocols: ContentAcquirer, ContentExtractor)
                      ├── file.py (FileAcquirer)
                      └── pdf.py (PdfExtractor using Marker)
```

**Core components:**

- **`core/library.py`**: Orchestrates the add/list/show/delete pipeline. Coordinates acquirers, extractors, and storage. Entry point for all business logic.
- **`core/storage.py`**: All SQLite operations—CRUD, status transitions, duplicate detection. Functions take connection as first argument (no global state).
- **`core/models.py`**: Dataclasses for `Document`, `ExtractionResult`, `AcquisitionResult`.
- **`core/errors.py`**: Custom exceptions with error codes for programmatic handling.
- **`ingestion/base.py`**: Protocol definitions for `ContentAcquirer` and `ContentExtractor`.
- **`ingestion/file.py`**: `FileAcquirer` for local filesystem acquisition.
- **`ingestion/pdf.py`**: `PdfExtractor` wrapping Marker for PDF→Markdown conversion.
- **`cli/`**: Typer commands, thin wrappers around `Library` methods.
- **`config.py`**: Path management via platformdirs.

**Data flow (add pipeline):**

```
1. Select acquirer via can_handle(source)
2. acquirer.validate(source) — or create failed record if --force
3. Check duplicate by original path → return existing if found
4. acquirer.acquire(source, temp_path) → get content hash
5. Check duplicate by hash → return existing if found
6. Move temp_path to content-addressable storage
7. Create record (status='pending')
8. Select extractor via can_handle()
9. extractor.extract() → ExtractionResult
10. result.validate() — quality check
11. Write markdown to extracted/
12. Update record (status='ready' or 'failed')
```

**File storage layout:**

```
~/.local-library/                    # platformdirs user_data_path
├── library.db                       # SQLite database
├── storage/                         # Acquired files
│   └── ab/cd/abcd...5678.pdf       # Content-hash path
└── extracted/                       # Extraction output
    └── ab/cd/abcd...5678.md        # Same hash, .md extension
```

## Existing Patterns

This is a greenfield project—no existing patterns to follow. The design introduces:

- **Module pattern**: Separate modules for storage, ingestion, orchestration (vs. Repository pattern or monolithic services)
- **Protocol-based extensibility**: Acquirer and Extractor protocols enable future content types without modifying orchestration
- **Content-addressable storage**: Git/IPFS-style hash-based file layout

These patterns align with the project's "pipeline-first, layer-complete" philosophy from `build_philosophy.md`.

## Implementation Phases

### Phase 1: Project Scaffolding
**Goal:** Establish project structure, dependencies, and configuration

**Components:**
- `pyproject.toml` with dependencies (typer, rich, platformdirs, marker-pdf)
- `src/local_library/` package structure with `__init__.py` files
- `src/local_library/config.py` — path configuration via platformdirs
- `tests/` directory structure

**Dependencies:** None (first phase)

**Done when:** `uv sync` succeeds, `uv run python -c "import local_library"` works

### Phase 2: Core Models and Errors
**Goal:** Define data structures and exception hierarchy

**Components:**
- `src/local_library/core/models.py` — `Document`, `ExtractionResult`, `AcquisitionResult` dataclasses
- `src/local_library/core/errors.py` — exception classes with error codes

**Dependencies:** Phase 1

**Done when:** Models can be instantiated, exceptions can be raised with codes

### Phase 3: Storage Layer
**Goal:** SQLite schema and CRUD operations

**Components:**
- `src/local_library/core/storage.py` — connection management, schema initialization, all CRUD functions
- Schema: documents table with status, paths, nullable metadata fields, error tracking

**Dependencies:** Phase 2 (models)

**Done when:** Can create/read/update/delete documents, status transitions work, duplicate detection by path and hash works, all storage tests pass

### Phase 4: Ingestion Protocols and FileAcquirer
**Goal:** Acquisition abstraction and local file handling

**Components:**
- `src/local_library/ingestion/base.py` — `ContentAcquirer` and `ContentExtractor` protocols, result dataclasses
- `src/local_library/ingestion/file.py` — `FileAcquirer` implementation (validate, copy, hash)

**Dependencies:** Phase 2 (models)

**Done when:** FileAcquirer can validate paths, copy files to content-addressable locations, compute hashes, all acquirer tests pass

### Phase 5: PdfExtractor with Quality Validation
**Goal:** PDF extraction via Marker with output quality checking

**Components:**
- `src/local_library/ingestion/pdf.py` — `PdfExtractor` wrapping Marker
- Quality validation in `ExtractionResult.validate()` — checks for garbled output, minimum content length, printable character ratio

**Dependencies:** Phase 4 (protocols)

**Done when:** PDFs extract to markdown, quality validation catches garbage output, extraction errors are properly raised, all extractor tests pass

### Phase 6: Library Orchestration
**Goal:** Pipeline coordination with duplicate handling and --force support

**Components:**
- `src/local_library/core/library.py` — `Library` class orchestrating full add/get/list/delete pipeline
- `AddResult` dataclass for idempotent add responses

**Dependencies:** Phases 3, 4, 5

**Done when:** Full add pipeline works (acquire → extract → store), duplicates return existing record, --force creates failed records for inaccessible files, all orchestration tests pass

### Phase 7: CLI Commands
**Goal:** User-facing command-line interface

**Components:**
- `src/local_library/cli/main.py` — Typer app with shared context
- `src/local_library/cli/add.py` — add command with --force and --json options
- `src/local_library/cli/list.py` — list command with --status filter and --json
- `src/local_library/cli/show.py` — show command with UUID partial matching
- `src/local_library/cli/delete.py` — delete command with --force confirmation skip

**Dependencies:** Phase 6

**Done when:** All CLI commands work, Rich output displays correctly, --json produces valid JSON, error messages go to stderr with appropriate exit codes, CLI integration tests pass

### Phase 8: End-to-End Integration
**Goal:** Verify complete workflow and edge cases

**Components:**
- Integration tests covering full add→list→show→delete cycle
- Edge case tests: duplicate detection, extraction failures, --force behavior, quality validation failures

**Dependencies:** Phase 7

**Done when:** E2E tests pass, can add real PDFs, duplicates handled correctly, failed extractions create proper records

## Additional Considerations

**Error handling:** Errors include both human-readable `error_message` and machine-parseable `error_code` (e.g., `ACQUISITION_FILE_NOT_FOUND`, `EXTRACTION_MARKER_CRASH`, `QUALITY_LOW_PRINTABLE`). This enables programmatic filtering and reporting on error types.

**`--force` for acquisition failures:** Users can create placeholder records for inaccessible files via `add --force`. Record is created with `status='failed'` and appropriate error code/message. This allows tracking problematic documents within the database rather than externally.

**Future extensibility:** The Acquirer + Extractor protocol design supports adding web content (trafilatura) and other formats without modifying orchestration logic. Each new format adds an acquirer and/or extractor that implements the protocol.
