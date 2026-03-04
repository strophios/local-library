# Ingestion Domain

Last verified: 2026-03-03

## Purpose

Handles content acquisition (getting files into the system), extraction (converting to searchable text), and metadata processing (CSL-JSON validation, text-based extraction). Defines protocols for extensibility; implementations handle specific source types.

## Contracts

- **Exposes**: ContentAcquirer protocol, ContentExtractor protocol, FileAcquirer, PdfExtractor, TextMetadataExtractor, cleanup_markdown, ZoteroReader (with ZoteroLibrary, ZoteroCollection, ZoteroItem, ZoteroAttachment dataclasses)
- **Guarantees**:
  - `can_handle()` returns True only for sources/files the handler can process
  - Acquirers copy to temp location (never modify source)
  - AcquisitionResult.content_hash is SHA-256 of acquired content
  - ContentExtractor.extract() produces ExtractionResult with quality metrics
  - ContentExtractor.extract_and_validate() combines extraction + validation in one call
  - FileAcquirer handles any local file path (content-agnostic); detects MIME type dynamically
  - TextMetadataExtractor.extract() returns TextExtractionResult with per-field confidence scores
  - Extraction confidence threshold (default 0.7) determines needs_review status
  - LLM fallback (when enabled) uses heuristic values as context hints
  - PdfExtractor supports LLM-enhanced extraction via `llm_enabled` parameter (better tables, math, images when GEMINI_API_KEY available)
  - `cleanup_markdown()` never raises; each pass catches exceptions and returns input unchanged
  - `cleanup_markdown()` uses a lazy-loaded system word list (`/usr/share/dict/words`) for dehyphenation; degrades gracefully if unavailable
- **Expects**: Source paths exist and are readable; temp directories provided by caller; markdown text for TextMetadataExtractor

## Dependencies

- **Uses**: `core.models` (AcquisitionResult, ExtractionResult, FieldExtraction, TextExtractionResult), `core.errors` (exception types), `llm.base` (LLMClient protocol, TYPE_CHECKING only)
- **Used by**: `core.library` (Library orchestrator dispatches via `can_handle()` and uses TextMetadataExtractor)
- **Boundary**: Ingestion MUST NOT import from cli or storage

## Key Decisions

- **Protocol-based extensibility**: ContentAcquirer and ContentExtractor are protocols (not ABCs) for duck typing
- **Content-agnostic FileAcquirer**: Handles any local file; MIME detection via `mimetypes` module
- **URL rejection**: FileAcquirer rejects URLs (http://, https://, ftp://, file://) to defer to future UrlAcquirer
- **Lazy Marker loading**: PdfExtractor defers model load until first extraction (saves startup time)
- **PdfExtractor LLM mode**: When `llm_enabled=True` and GEMINI_API_KEY is set, configures Marker with `use_llm`, `redo_inline_math`, and `disable_image_extraction` (images become text descriptions). Falls back silently to standard extraction without API key.
- **Quality validation**: ExtractionResult.validate() checks min length and printable ratio
- **compute_storage_path**: Git-style `ab/cd/hash.ext` layout for content-addressable storage
- **MetadataHandler**: Stateless CSL-JSON validation with citekey generation (internal, used by Library)
- **TextMetadataExtractor**: Heuristic extraction of title, authors, date, doc_type from Marker-produced markdown. Optional LLM fallback via injected LLMClient when confidence is low. Returns TextExtractionResult with per-field FieldExtraction objects.
- **LLMClient injection**: TextMetadataExtractor and LLMExtractor accept an optional `LLMClient` instance via constructor. If None, LLM fallback is disabled. Library creates and injects the client; text_extraction.py no longer imports litellm directly.
- **Mixed pattern for text_extraction.py**: File contains pure extraction functions (Functional Core) and LLMExtractor class (requires HTTP calls via LLMClient). Separation adds complexity without testability benefit since LLM tests use mocks.
- **Confidence-based workflow**: Fields below confidence threshold (default 0.7) trigger needs_review. LLM fallback (if enabled) uses heuristic candidates as context hints but preserves heuristic confidence scores.
- **Lazy imports via `__getattr__`**: Ingestion package uses module-level `__getattr__` to defer imports until needed. Breaks circular dependency: ingestion → core.models → core.library → ingestion.base. Zotero module not exposed here to remain isolated.
- **Zotero module isolation**: `zotero.py` uses Mixed pattern for LibraryJsonParser (I/O necessary to parse CSL-JSON; cannot be separated without complexity). Frozen dataclasses remain pure. Tests import directly via `from local_library.ingestion.zotero import ...` to avoid circular import chain.
- **Multi-library support**: ZoteroReader supports filtering by library via `library_id` parameter on relevant methods. `get_personal_library()` returns the user's personal library (type='user'). Collections include `library_id` to support library-scoped queries.
- **Markdown cleanup**: `cleanup_markdown()` applies three composable passes (HTML coercion → dehyphenation → paragraph reflow) between Marker extraction and disk write. Pass ordering is load-bearing. Pure Functional Core — no I/O, no dependencies beyond system dict. Conservative dehyphenation: default keeps hyphen, only removes when positively validated.

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
- `text_extraction.py` - TextMetadataExtractor, LLMExtractor, field extractors (extract_title, extract_authors, extract_date, extract_doc_type), build_csl_json converter
- `markdown_cleanup.py` - cleanup_markdown (three-pass post-processing: HTML coercion, dehyphenation, paragraph reflow)
- `zotero.py` - ZoteroAttachment, ZoteroItem, ZoteroCollection, ZoteroLibrary frozen dataclasses; ZoteroReader facade; CollectionResolver for collection queries; LibraryResolver for multi-library support

## Gotchas

- Use `extract_and_validate()` over `extract()` when quality validation is needed (protocol method)
- FileAcquirer.acquire() returns resolved absolute path in original_path
- Quality thresholds are configurable but default to min_length=100, min_printable_ratio=0.8
- FileAcquirer returns detected MIME type (not hardcoded); callers should not assume PDF
- Importing `from local_library.ingestion.zotero import ...` does NOT trigger eager evaluation of ingestion module imports (uses lazy `__getattr__`)
- Do NOT add zotero imports to ingestion `__init__.py` - keep it isolated to preserve the lazy import pattern
- TextMetadataExtractor preserves heuristic confidence even when LLM provides the value (for consistent needs_review determination)
- LLMExtractor.enabled is now a property derived from whether LLMClient is None (not a stored boolean)
- Field extractors return FieldExtraction with value=None when extraction fails (not exceptions)
- The `nameparser` library is used for robust author name parsing
- PdfExtractor with `llm_enabled=True` passes `gemini_api_key` directly via Marker's config dict (avoids environment variable mutation)
- ZoteroReader methods that accept `library_id=None` operate across all libraries when None; pass specific library_id to filter
- ZoteroCollection.library_id links to Zotero's `libraries` table; personal library is typically libraryID=1 with type='user'
