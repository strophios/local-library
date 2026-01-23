# Ingestion Domain

Last verified: 2026-01-22

## Purpose

Handles content acquisition (getting files into the system), extraction (converting to searchable text), and metadata processing (CSL-JSON validation). Defines protocols for extensibility; implementations handle specific source types.

## Contracts

- **Exposes**: ContentAcquirer protocol, ContentExtractor protocol, FileAcquirer, PdfExtractor
- **Guarantees**:
  - `can_handle()` returns True only for sources/files the handler can process
  - Acquirers copy to temp location (never modify source)
  - AcquisitionResult.content_hash is SHA-256 of acquired content
  - ContentExtractor.extract() produces ExtractionResult with quality metrics
  - ContentExtractor.extract_and_validate() combines extraction + validation in one call
  - FileAcquirer handles any local file path (content-agnostic); detects MIME type dynamically
- **Expects**: Source paths exist and are readable; temp directories provided by caller

## Dependencies

- **Uses**: `core.models` (AcquisitionResult, ExtractionResult), `core.errors` (exception types)
- **Used by**: `core.library` (Library orchestrator dispatches via `can_handle()`)
- **Boundary**: Ingestion MUST NOT import from cli or storage

## Key Decisions

- **Protocol-based extensibility**: ContentAcquirer and ContentExtractor are protocols (not ABCs) for duck typing
- **Content-agnostic FileAcquirer**: Handles any local file; MIME detection via `mimetypes` module
- **URL rejection**: FileAcquirer rejects URLs (http://, https://, ftp://, file://) to defer to future UrlAcquirer
- **Lazy Marker loading**: PdfExtractor defers model load until first extraction (saves startup time)
- **Quality validation**: ExtractionResult.validate() checks min length and printable ratio
- **compute_storage_path**: Git-style `ab/cd/hash.ext` layout for content-addressable storage
- **MetadataHandler**: Stateless CSL-JSON validation with citekey generation (internal, used by Library)
- **Lazy imports via `__getattr__`**: Ingestion package uses module-level `__getattr__` to defer imports until needed. Breaks circular dependency: ingestion → core.models → core.library → ingestion.base. Zotero module not exposed here to remain isolated.
- **Zotero module isolation**: `zotero.py` contains only frozen dataclasses with no dependencies. Tests import directly via `from local_library.ingestion.zotero import ...` to avoid circular import chain.

## Invariants

- Acquirers never modify source files
- content_hash computed AFTER copying to temp (verifies what was copied)
- PdfExtractor raises QualityError on invalid output (never silently succeeds)
- FileAcquirer.can_handle() returns False for URL-like strings

## Key Files

- `base.py` - ContentAcquirer, ContentExtractor protocols; compute_storage_path utility
- `file.py` - FileAcquirer (any local file), compute_file_hash, dynamic MIME detection
- `pdf.py` - PdfExtractor (Marker wrapper with quality validation)
- `metadata.py` - MetadataHandler (CSL-JSON validation, citekey generation, field extraction)
- `zotero.py` - ZoteroAttachment, ZoteroItem frozen dataclasses (Functional Core only, no I/O)

## Gotchas

- Use `extract_and_validate()` over `extract()` when quality validation is needed (protocol method)
- FileAcquirer.acquire() returns resolved absolute path in original_path
- Quality thresholds are configurable but default to min_length=100, min_printable_ratio=0.8
- FileAcquirer returns detected MIME type (not hardcoded); callers should not assume PDF
- Importing `from local_library.ingestion.zotero import ...` does NOT trigger eager evaluation of ingestion module imports (uses lazy `__getattr__`)
- Do NOT add zotero imports to ingestion `__init__.py` - keep it isolated to preserve the lazy import pattern
