# M3a: Metadata Handling Design

## Summary

This milestone adds metadata handling to the document ingestion pipeline. The system will validate bibliographic metadata in CSL-JSON format (the standard used by Zotero and academic citation processors), automatically generate human-readable citation keys for each document, and extract key fields like title and author into indexed database columns for efficient querying. The approach follows the existing handler pattern: a stateless `MetadataHandler` receives CSL-JSON input, validates it against the official schema, generates a citekey if one isn't provided, and extracts specific fields for storage. This handler is source-agnostic — for this milestone metadata comes from a CLI flag, but future sources (PDF extraction, Zotero import, CrossRef API) will convert their outputs to CSL-JSON and pass through the same validation pipeline.

The implementation is designed for extensibility without breaking changes. Validation is lenient (warn on missing optional fields, reject only structural errors), citekey generation includes a fallback chain for incomplete data, and indexed field extraction preserves structured data in the result object to enable future schema evolution (like migrating from author strings to a normalized authors table). The handler integrates between content extraction and storage in the existing `Library.add()` orchestration, requiring no changes to the acquirer/extractor layers.

## Definition of Done

1. **CSL-JSON validation** — When metadata is provided, validate it against CSL-JSON schema; reject invalid input with clear error messages

2. **Citekey generation** — Generate BetterBibTeX-style citekeys (`authorYearTitle`) by default; allow override when citekey is provided in input

3. **Indexed field extraction** — Extract and store title, author, date in indexed columns; design schema for easy addition of more fields later

4. **Integration with existing pipeline** — The `add` command accepts optional metadata; if provided, it's validated and stored; citekey generated if not provided

## Glossary

- **CSL-JSON**: Citation Style Language JSON — a standardized format for bibliographic metadata used by Zotero, citation processors, and academic reference managers. Contains fields like `title`, `author`, `issued`, and `type` (journal article, book, etc.).

- **Citekey**: A short unique identifier for a document (e.g., `Smith2017Attention`) used in plain-text citations and for human-readable reference. Follows the BetterBibTeX convention of `AuthorYearTitle`.

- **BetterBibTeX**: A popular Zotero plugin that generates consistent, human-readable citation keys. This project adopts its key generation pattern for compatibility.

- **Indexed columns**: Database columns with indexes for efficient querying. Title and date fields are extracted from CSL-JSON into dedicated columns to enable fast searching without parsing JSON blobs.

- **Handler pattern**: An architectural pattern where a stateless component processes input and returns a result object without side effects or database access. This project uses handlers for content acquisition, extraction, and now metadata processing.

- **JSON Schema**: A standard for validating JSON structure. The CSL-JSON schema defines required fields, allowed types, and structural rules for bibliographic metadata.

- **Diacritic folding**: Converting accented characters to ASCII equivalents (é → e, ñ → n) using the `unidecode` library. Applied to author names during citekey generation.

- **Frozen dataclass**: An immutable Python dataclass (with `@dataclass(frozen=True)`) that cannot be modified after creation, ensuring result objects remain consistent.

- **Protocol**: Python typing construct defining an interface without inheritance. The existing `ContentExtractor` and `ContentAcquirer` use protocols; MetadataHandler follows the same pattern conceptually.

- **ErrorCode enum**: An enumeration of error types used across the application. New error codes (`METADATA_INVALID_SCHEMA`, etc.) are added to this enum for metadata-specific failures.

## Architecture

MetadataHandler validates CSL-JSON input and produces enriched metadata for storage. It follows the existing handler pattern: pure function transforming input to output without side effects or database access.

**Components:**

- **MetadataHandler** (`src/local_library/ingestion/metadata.py`) — Validates CSL-JSON against schema, generates citekey if not provided, extracts indexed fields. Stateless; schema loaded once at initialization.

- **MetadataResult** (`src/local_library/core/models.py`) — Immutable dataclass holding processed metadata: validated `csl_json`, generated `citekey`, extracted `title`/`authors`/`issued_date`, and `validation_warnings` for non-fatal issues.

- **MetadataError** (`src/local_library/core/errors.py`) — Exception for validation failures with specific error codes (`METADATA_INVALID_SCHEMA`, `METADATA_INVALID_TYPE`, `METADATA_CITEKEY_INVALID`).

**Data flow:**

```
CLI (--metadata flag)
       ↓
Library.add(metadata_path=...)
       ↓
   Acquire → Extract → MetadataHandler.process(csl_json) → Storage
                              ↓
                       MetadataResult
```

The handler is source-agnostic. For M3a, CSL-JSON comes from CLI input. Future sources (content extraction, Zotero import, CrossRef API) will convert to CSL-JSON upstream, then pass through the same handler.

**Validation strategy:**

Lenient validation for import/user input:
- Validate `type` field exists and is valid CSL type (fatal if missing/invalid)
- Validate field types where present (fatal if wrong type)
- Warn but accept missing optional fields
- Reject malformed structure per JSON Schema `additionalProperties: false`

Schema source: Official CSL-JSON schema from `citation-style-language/schema` (v1.0.2), cached locally.

**Citekey generation:**

Pattern: `Auth + Year + TitleWord` (e.g., `Smith2017Attention`)

- **Author:** First author's family name, diacritics folded via `unidecode`, caps preserved
- **Year:** Four-digit year from `issued.date-parts[0][0]`
- **Title:** First significant word after filtering stopwords, caps preserved
- **Fallback:** `unknown-{hash[:8]}` if insufficient data
- **Collision:** Storage layer appends suffix (`a`, `b`, `c`) if citekey exists

If `citation-key` field exists in input, use it directly (still validate format).

## Existing Patterns

Investigation found the following patterns this design follows:

**Handler pattern:** ContentExtractor and ContentAcquirer in `src/local_library/ingestion/` use protocols with `can_handle()` dispatch. MetadataHandler follows similar structure but without protocol dispatch (single handler, multiple sources feed it).

**Result dataclasses:** ExtractionResult and AcquisitionResult in `src/local_library/core/models.py` are frozen dataclasses with factory methods. MetadataResult follows this pattern.

**Error hierarchy:** All exceptions inherit from `LocalLibraryError` with `ErrorCode` enum and optional `details` dict. MetadataError follows this exactly.

**Storage JSON handling:** `storage.py` serializes/deserializes `csl_json` as JSON string. New indexed columns follow the existing nullable field pattern.

**Library orchestration:** `Library.add()` coordinates acquirer → extractor → storage. MetadataHandler slots in after extraction, before storage, following the same coordination pattern.

## Implementation Phases

### Phase 1: Core Types and Error Codes

**Goal:** Add MetadataResult dataclass and metadata-related error codes.

**Components:**
- `MetadataResult` dataclass in `src/local_library/core/models.py`
- New error codes in `src/local_library/core/errors.py`: `METADATA_INVALID_SCHEMA`, `METADATA_INVALID_TYPE`, `METADATA_CITEKEY_INVALID`
- `MetadataError` exception class

**Dependencies:** None

**Done when:** Types importable, error codes defined, basic unit tests pass.

### Phase 2: Schema Validation

**Goal:** CSL-JSON validation using jsonschema library.

**Components:**
- Schema loading and caching in `src/local_library/ingestion/metadata.py`
- `MetadataHandler.validate()` method returning (is_valid, list[issues])
- Classification of errors as fatal vs warning

**Dependencies:** Phase 1 (error codes), `jsonschema` package dependency

**Done when:** Valid CSL-JSON passes, invalid CSL-JSON raises MetadataError with descriptive message, warnings collected for missing optional fields.

### Phase 3: Citekey Generation

**Goal:** Generate citekeys from CSL-JSON metadata.

**Components:**
- `generate_citekey()` function in `src/local_library/ingestion/metadata.py`
- Author extraction with diacritic folding (using `unidecode`)
- Title word extraction with stopword filtering
- Date extraction from CSL date format
- Fallback chain for missing fields

**Dependencies:** Phase 1, `unidecode` package dependency

**Done when:** Citekeys generated correctly for various inputs (single/multiple authors, missing fields, non-ASCII names), override respected when `citation-key` provided.

### Phase 4: Indexed Field Extraction

**Goal:** Extract title, authors, date for indexed storage.

**Components:**
- `extract_indexed_fields()` in MetadataHandler
- Author name formatting (`Family, G.; Family2, G.`)
- Date normalization to ISO format or year-only

**Dependencies:** Phase 1

**Done when:** Indexed fields extracted correctly, missing fields result in None, formatted strings suitable for display and basic search.

### Phase 5: Database Schema Update

**Goal:** Add indexed columns to documents table.

**Components:**
- Schema migration adding `title`, `authors`, `issued_date` columns
- Indexes on `title` and `issued_date`
- Updated `create_document()` accepting new parameters
- New `update_document_metadata()` method
- Citekey collision detection and suffix generation in storage layer

**Dependencies:** Phases 1-4

**Done when:** Schema migrated, CRUD operations work with new columns, citekey collisions handled correctly.

### Phase 6: Pipeline Integration

**Goal:** Wire MetadataHandler into Library.add() and CLI.

**Components:**
- `--metadata PATH` flag in `src/local_library/cli/add.py`
- MetadataHandler instantiation in Library.__init__()
- Handler invocation in Library.add() after extraction
- Error handling and CLI display for validation failures

**Dependencies:** Phases 1-5

**Done when:** `local-library add paper.pdf --metadata meta.json` works end-to-end, validation errors display clearly, documents stored with metadata queryable.

## Additional Considerations

**Future metadata merging:** The handler is designed to be merge-friendly. Future orchestration can combine metadata from multiple sources (user input, extraction, API lookup) with priority rules, then pass merged CSL-JSON through the handler once. The handler doesn't need to know about sources or priorities.

**Author normalization for future indexing:** Authors are stored as formatted string for M3a. The MetadataResult captures structured data (`list[str]`) enabling future migration to a normalized authors table without re-parsing CSL-JSON.
