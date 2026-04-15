# Extraction Resilience and Metadata Pipeline Design

## Summary

This design addresses two failure modes in the current ingestion pipeline. First, Marker — the PDF extraction engine — can time out or crash with no recovery path, leaving documents in a permanent FAILED state even when their text is directly extractable by simpler means. The fix introduces a fast pymupdf pre-check before each Marker invocation: it measures page count, determines whether the PDF contains extractable text, and uses those results to set a document-appropriate timeout (text-based PDFs are fast; scanned image PDFs need much longer). If Marker still fails and the PDF had extractable text, pymupdf's raw `get_text()` output is returned as a degraded fallback rather than a failure. Documents using the fallback are flagged NEEDS_REVIEW so the user can reextract them later under better conditions.

Second, documents that fail extraction currently leave the library in an inconsistent state: no citekey, no metadata, nothing to search or review. The design corrects this by persisting preliminary metadata before extraction begins. Depending on the input path — a Zotero import, an explicit `--metadata` file, or a bare filename — the system generates best-effort CSL-JSON and a citekey upfront. A new `MetadataSource` field tracks provenance, which determines whether subsequent successful extraction should attempt to upgrade that metadata (filename-derived metadata is upgraded; Zotero-provided metadata is authoritative and left alone). Upgrades that would change an existing citekey are blocked and flagged for human review, preserving referential stability across notes and citations.

## Definition of Done

- **PdfExtractor performs a pymupdf pre-check** before launching Marker extraction, determining page count and text extractability
- **Extraction timeout scales dynamically** with document characteristics: text-extractable documents get `max(900, pages * 5)` seconds, image-only documents get `max(1800, pages * 45)` seconds, capped at a configurable maximum (default 4 hours)
- **pdftext fallback** rescues documents with extractable text when Marker fails: pymupdf `get_text()` output is returned as a degraded ExtractionResult with `extraction_method: 'pdftext_fallback'` in metadata. Documents using the fallback are set to NEEDS_REVIEW status with an explanatory message
- **Progress reporting uses a callback protocol** instead of `logger.info()`: PdfExtractor accepts an optional `ProgressCallback`, emitting pre-check analysis results, periodic heartbeats, and completion status. CLI layer provides callback implementation (Rich status panel for interactive, logging for non-interactive). Default behavior falls back to current logging when no callback is provided
- **Library.add() persists preliminary metadata before extraction** for all input types: Zotero CSL-JSON, explicit `--metadata`, or filename-heuristic parse. Every document has a citekey, title, and basic metadata regardless of extraction outcome
- **MetadataSource tracking** (`ZOTERO`, `EXPLICIT`, `FILENAME`, `TEXT_EXTRACTED`) stored as a custom field in CSL-JSON determines whether text extraction should attempt to upgrade metadata after successful extraction
- **Filename heuristic parser** handles common academic PDF naming conventions. Accepts `Path` (not `str`) to prevent accidental URL parsing. Returns best-effort CSL-JSON with source tagged as `FILENAME`
- **Metadata upgrades that would change the citekey** are not auto-applied. The document is flagged NEEDS_REVIEW with candidate metadata shown, preserving citekey stability
- **`reextract` supports FAILED documents** since they now have preliminary metadata persisted before extraction
- **Fallback text that fails quality validation** (min_length, printable_ratio) is treated as no fallback — the document goes to FAILED as before

**Out of scope**: hierarchical document structure (chapters/sections as sub-documents), parallel extraction, olmOCR integration, worker-side per-page progress streaming, URL heuristic parser (stub only until web ingestion lands).

## Glossary

- **Marker**: The primary PDF extraction engine used by this project. Converts PDFs to structured markdown with heading detection, layout analysis, and math notation handling. Runs in a persistent worker subprocess to allow crash recovery.
- **pymupdf**: A Python binding to MuPDF, a fast PDF rendering library. Used here for lightweight pre-checks and as a fallback text extractor when Marker fails. Previously a dev-only dependency; this design promotes it to a runtime dependency.
- **pdftext fallback**: When Marker fails, pymupdf's `get_text()` is used to extract raw text from each page. The output is flat (no headings, no math notation), but usable for RAG and FTS indexing.
- **ExtractionResult**: The structured object returned by `PdfExtractor.extract()`. Carries extracted text, metadata fields (page stats, device used, extraction method), and success/failure information.
- **MPS**: Apple's Metal Performance Shaders GPU backend, used by PyTorch on Apple Silicon. Relevant here because Marker's neural components can segfault on MPS with certain inputs; the existing worker subprocess handles crash recovery.
- **CSL-JSON**: Citation Style Language JSON — the standard schema for bibliographic metadata used throughout this project. Compatible with Zotero and citation processors. Custom fields prefixed with underscore (e.g., `_metadata_source`) are spec-legal.
- **MetadataSource**: A new enum tracking where a document's metadata originated: `ZOTERO`, `EXPLICIT`, `FILENAME`, or `TEXT_EXTRACTED`. Stored as `_metadata_source` in the CSL-JSON blob. Controls whether text extraction should attempt to upgrade metadata after successful extraction.
- **citekey**: A short, stable identifier for a document, typically in BetterBibTeX style (e.g., `Weber1921a`). Used across CLI commands, markdown notes, and citations. Citekey stability is a design invariant — changes break references.
- **NEEDS_REVIEW**: A document status signaling that the document has usable content but requires human attention (low-confidence metadata, degraded extraction, or a metadata upgrade that would change the citekey). The `review` CLI command handles this workflow.
- **FAILED**: A document status indicating extraction failed completely. Previously meant no citekey or metadata existed; after this design, FAILED documents still have preliminary metadata persisted.
- **ProgressCallback**: A callable protocol `(message, elapsed_seconds, context_dict) -> None` accepted by `PdfExtractor`. Replaces hard-coded `logger.info()` heartbeats with a pluggable reporting mechanism. CLI provides Rich-based implementations for interactive contexts.
- **FTS5**: SQLite's full-text search extension. Used alongside sqlite-vec for hybrid retrieval. Fallback documents are embedded and indexed normally, so FTS5 search works on them.
- **RAG (Retrieval-Augmented Generation)**: The query interface that retrieves relevant document chunks and passes them to an LLM to generate answers. Fallback documents participate in RAG normally — the text quality is lower but the pipeline is unchanged.
- **EXTRACTION_FALLBACK**: A new error code (joining `EXTRACTION_TIMEOUT`) that distinguishes "extraction failed but we have usable text via fallback" from "extraction failed with nothing recoverable."
- **Functional Core / Imperative Shell**: The project's architectural pattern separating pure, stateless transformations (Functional Core) from I/O and orchestration (Imperative Shell). The filename heuristic parser is Functional Core; `Library.add()` is Imperative Shell.

## Architecture

### Extraction Resilience (PdfExtractor)

The core change is to `PdfExtractor.extract()`. Before sending a request to the Marker worker subprocess, it performs a fast pymupdf analysis of the PDF and prepares a fallback path.

**Pre-check step** (milliseconds): Opens the PDF with pymupdf, counts pages, samples pages for extractable text (>100 chars of `get_text()` on pages 0, middle, and last). If text is present and total extracted text exceeds a minimum threshold (~100 chars), extracts all pages' text and holds it as a fallback string.

**Dynamic timeout**: Computed from pre-check results:
- Text-extractable: `max(900, pages * 5)` seconds
- Image-only: `max(1800, pages * 45)` seconds
- Capped at configurable maximum (default 4 hours)

The `_extraction_timeout` constructor parameter becomes the base timeout (default 900s). The dynamic calculation overrides it per document when the pre-check produces a higher value.

**Marker attempt**: Sent to the worker subprocess as before, using the dynamically computed timeout.

**Fallback on failure**: If Marker times out or crashes AND fallback text is available:
- Returns an `ExtractionResult` with the pymupdf text
- Sets `metadata['extraction_method'] = 'pdftext_fallback'`
- Includes failure reason in `metadata['marker_failure_reason']`
- Includes pre-check info (page_count, text_extractable flag)

**No fallback available**: If Marker fails AND no extractable text (image-only scan that exceeded even the scaled timeout), raises `ExtractionError` as before.

### Progress Callback Protocol

PdfExtractor accepts an optional progress callback replacing the current `logger.info()` heartbeats:

```python
ProgressCallback = Callable[[str, float, dict[str, Any]], None]
#                           message, elapsed_seconds, context_dict
```

Called at three points:
1. **Pre-check completion**: reports page count, text extractability, estimated timeout
2. **Every 30 seconds during extraction**: reports elapsed time, device, filename
3. **On completion/failure**: reports final status, duration, method used

Library passes a callback when creating PdfExtractor or calling `extract()`. CLI layer provides the implementation — Rich status panel for interactive commands (`zotero import`), logging for non-interactive use. When no callback is provided, falls back to current `logger.info()` behavior.

The intended CLI rendering for batch operations is a two-line display:
```
Importing: 142/1225 documents  [████████░░░░░░░░] 11.6%
  ↳ Extracting Weber1921a... 3m 42s elapsed (MPS, text-extractable, ~15m est.)
```

The top line tracks batch progress; the indented sub-line shows current extraction status and updates in-place every 30 seconds.

### Metadata Pipeline Reordering (Library.add())

The `add()` flow changes from sequential (extract → metadata) to preliminary-metadata-first (preliminary metadata → extract → conditionally upgrade).

**MetadataSource** tracks where a document's metadata came from:
- `ZOTERO` — from Zotero import. Authoritative. Never upgrade.
- `EXPLICIT` — from `--metadata` flag. Authoritative. Never upgrade.
- `FILENAME` — heuristic parse of the input path. Low confidence. Upgrade after successful extraction.
- `TEXT_EXTRACTED` — from text extraction pipeline. Medium confidence. Don't re-upgrade.

Stored as a custom field (`_metadata_source`) in the CSL-JSON blob. Avoids schema migration.

**New add() flow:**
1. **Acquire** file (unchanged)
2. **Persist preliminary metadata:**
   - Zotero metadata provided → persist as CSL-JSON, source=`ZOTERO`, generate citekey
   - `--metadata` file provided → persist as CSL-JSON, source=`EXPLICIT`, generate citekey
   - Bare path → parse filename heuristically, persist as CSL-JSON, source=`FILENAME`, generate citekey (best-effort)
3. **Extract** text (with timeout scaling + pdftext fallback)
4. **Conditionally upgrade metadata:**
   - Source is `FILENAME` and extraction succeeded → run text extraction, replace if higher confidence
   - Source is `ZOTERO` or `EXPLICIT` → skip text extraction entirely
   - Extraction failed → keep preliminary metadata as-is
5. **Citekey stability check** (during metadata upgrade):
   - If upgraded metadata would produce the same citekey → apply silently
   - If upgraded metadata would produce a different citekey → flag NEEDS_REVIEW with candidate metadata in the message; do not auto-apply

**Filename heuristic parser:**
- Signature takes `Path` (not `str`) to prevent accidental URL parsing
- Tries common academic PDF naming conventions: `Author - Year - Title.pdf`, `Author_Title_Year.pdf`, `AuthorYear.pdf`
- Falls back to using the full filename stem as the title
- Returns best-effort CSL-JSON with `_metadata_source: "FILENAME"`
- URL inputs get a separate code path (no-op stub until web ingestion lands)

### Library Integration for Fallback Status

After extraction, `Library.add()` and `Library.reextract()` check `result.metadata.get('extraction_method')`:
- `'pdftext_fallback'` → set document status to `NEEDS_REVIEW` with error_message describing the degraded extraction and the Marker failure reason. A new `EXTRACTION_FALLBACK` error code distinguishes this from `EXTRACTION_TIMEOUT` (the document has usable text, just degraded quality).
- Absent or `'marker'` → normal flow, status `READY`.

Embedding still happens on fallback documents — the text is usable for RAG and search.

`reextract` is extended to target FAILED documents. Since preliminary metadata is now persisted before extraction (Phase 2), FAILED documents have citekeys and CSL-JSON, making reextraction safe.

## Existing Patterns

Investigation found the following relevant patterns:

**Subprocess extraction with crash recovery** (`ingestion/pdf.py`): PdfExtractor already runs Marker in a persistent worker subprocess with MPS → CPU fallback on crash. The pre-check and fallback logic extend this existing resilience pattern rather than introducing a new one.

**ExtractionResult.metadata dict** (`core/models.py`): Already carries Marker's `page_stats` and extraction run info (duration, device, fallback status). The pdftext fallback tracking adds keys to this existing vehicle.

**Lazy loading pattern** (`embeddings/nomic.py`, `ingestion/pdf.py`): Heavy dependencies are deferred. pymupdf is already a dependency (used in tests and the extraction quality framework). No new lazy-loading needed.

**NEEDS_REVIEW status** (`core/models.py`): Already used for low-confidence metadata extraction. Extended here for degraded extraction quality. The `review` CLI command handles the NEEDS_REVIEW workflow.

**Error code tracking** (`core/errors.py`): FAILED documents store error_code and error_message. The new `EXTRACTION_FALLBACK` code follows this pattern.

**CSL-JSON custom fields**: The CSL-JSON spec allows custom fields prefixed with underscore. `_metadata_source` follows this convention for metadata source tracking.

**Functional Core / Imperative Shell**: The filename heuristic parser is pure (Functional Core). The pre-check is I/O (reads PDF) but stateless. PdfExtractor remains Imperative Shell. Library.add() flow change is orchestration (Imperative Shell).

## Implementation Phases

### Phase 1: Pre-Check and Dynamic Timeout

**Goal:** PdfExtractor analyzes documents before extraction and scales timeout accordingly.

**Components:**
- Pre-check function in `src/local_library/ingestion/pdf.py` — pymupdf-based page count and text extractability analysis
- Dynamic timeout computation in PdfExtractor — replaces flat 900s with scaled timeout based on pre-check results
- Updated `_send_request()` to use computed timeout instead of `self._extraction_timeout`

**Dependencies:** None (first phase)

**Done when:** Documents with >200 pages get proportionally longer timeouts. Pre-check correctly distinguishes text-extractable from image-only PDFs. Existing extraction behavior unchanged for normal-length documents.

### Phase 2: pdftext Fallback

**Goal:** Documents with extractable text are rescued when Marker fails, rather than going straight to FAILED.

**Components:**
- Fallback text capture in pre-check step — pymupdf `get_text()` per page, held in memory during extraction attempt
- Fallback return path in `PdfExtractor.extract()` — returns ExtractionResult with fallback text and metadata when Marker fails and fallback is available
- New `EXTRACTION_FALLBACK` error code in `src/local_library/core/errors.py`
- Library integration in `src/local_library/core/library.py` — checks `extraction_method` in result metadata, sets NEEDS_REVIEW for fallback documents

**Dependencies:** Phase 1 (pre-check infrastructure)

**Done when:** A document with extractable text that times out during Marker extraction produces a NEEDS_REVIEW document with usable text, rather than a FAILED document with nothing. Documents without extractable text still fail as before.

### Phase 3: Progress Callback Protocol

**Goal:** Extraction progress is reported via callback instead of logging, enabling proper CLI rendering.

**Components:**
- `ProgressCallback` type alias and protocol in `src/local_library/ingestion/pdf.py`
- Updated `PdfExtractor` constructor and `_send_request()` to use callback when provided, falling back to `logger.info()`
- Pre-check progress emission — reports analysis results before extraction begins
- CLI callback implementations in `src/local_library/cli/` — Rich-based for interactive commands, logging-based for non-interactive
- Fix heartbeat visibility during `zotero import` — investigate and remove Rich progress bar stop/start workaround if subprocess extraction eliminates the original conflict

**Dependencies:** Phase 1 (pre-check emits progress), Phase 2 (fallback status emitted)

**Done when:** Extraction progress is visible during `zotero import` as an in-place updating status line. `reextract` continues to show progress via logging. Pre-check analysis (page count, timeout estimate) is displayed before extraction begins.

### Phase 4: Filename Heuristic Parser

**Goal:** Bare `add <path>` commands produce best-effort metadata from the filename.

**Components:**
- `parse_filename_metadata()` function in `src/local_library/ingestion/metadata.py` — `Path`-typed input, returns CSL-JSON dict with `_metadata_source: "FILENAME"`
- Pattern matching for common academic naming conventions
- Fallback to filename stem as title

**Dependencies:** None (independent of Phases 1-3)

**Done when:** Common academic PDF naming patterns produce reasonable author/year/title metadata. Unconventional filenames produce at least a title. URLs are rejected at the type level (function takes `Path`).

### Phase 5: Metadata Pipeline Reordering

**Goal:** Every document has metadata persisted before extraction begins, regardless of extraction outcome.

**Components:**
- `MetadataSource` enum or string constants in `src/local_library/core/models.py`
- Reordered `Library.add()` flow — preliminary metadata persisted after acquisition, before extraction
- Conditional metadata upgrade logic — only for `FILENAME` source, only after successful extraction
- Citekey stability check — detect when upgrade would change citekey, flag NEEDS_REVIEW instead of auto-applying
- `_metadata_source` field in CSL-JSON blob
- `reextract` extended to accept FAILED documents (now safe since they have metadata)

**Dependencies:** Phase 4 (filename parser provides the preliminary metadata for bare paths)

**Done when:** FAILED documents have citekeys and basic metadata. `reextract` works on FAILED documents. Zotero imports persist metadata before extraction. Metadata upgrades that would change the citekey are flagged for review rather than auto-applied.

## Additional Considerations

**Timeout cap rationale:** The 4-hour default cap is a pragmatic limit for local Marker extraction on consumer hardware. Documents exceeding this (e.g., a 2620-page image-only scan) are outside what the current pipeline can handle and should be addressed through alternative extraction methods (olmOCR on remote GPU, manual splitting) rather than waiting longer.

**pymupdf as a dependency:** pymupdf (via the `pymupdf` package, formerly `fitz`) is already a dev dependency used in the extraction quality framework. Phase 1 promotes it to a runtime dependency for the pre-check. It's lightweight and fast.

**URL input stub:** The filename heuristic parser takes `Path`, making URL inputs a type error. When web ingestion lands, it will need its own metadata source (`URL_HEURISTIC` or similar) with domain/path-based parsing. The `MetadataSource` enum is designed to be extended for this.

**Interaction with extraction metadata persistence (open issue #2):** This design does not add database persistence for extraction run metadata (duration, device, fallback status). That remains a separate concern. The `_metadata_source` field in CSL-JSON is the only new persisted data. Full extraction metadata persistence (schema v4 migration) can be done independently.

**Fallback quality vs. Marker quality:** pdftext fallback produces flat text without Marker's layout analysis, heading detection, or mathematical notation handling. This is adequate for RAG chunking and FTS indexing but produces lower-quality chunks than Marker output. The NEEDS_REVIEW status signals this to the user. Running `reextract` with a longer timeout or on different hardware can upgrade to Marker quality later.
