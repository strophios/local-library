# Extraction Testing Infrastructure Design

## Summary

This design establishes a pytest-based testing infrastructure to validate PDF extraction quality and metadata extraction accuracy using a curated golden set of ~20 PDFs with Zotero as the ground-truth source. The infrastructure supports the current milestone (M2 extraction validation) and prepares for M3b (metadata extraction from PDF content), where the system will learn to extract bibliographic metadata directly from PDFs rather than requiring explicit CSL-JSON input.

The approach uses pytest parametrization over real PDFs from `tests/extraction/golden_set/`, loading corresponding metadata from the user's existing Zotero library via BetterBibTeX JSON export. Tests compare Marker extraction output against ground truth using normalized string similarity for titles, set-based matching for authors, and exact matching for publication years. An optional manifest provides enrichment (categories, expected failures, notes) without being load-bearing. Diagnostic output shows per-document pass/fail status with field-level diffs, enabling rapid iteration on extraction heuristics during M3b development.

## Definition of Done

**Primary deliverables:**
1. **Test fixtures** that load golden set PDFs and their Zotero ground-truth metadata (via ZoteroReader/BetterBibTeX JSON)
2. **Extraction quality tests** validating Marker output quality (character count, printable ratio, structure preservation)
3. **Metadata extraction accuracy tests** comparing extracted title/authors/date against ground truth with defined accuracy metrics
4. **Basic diagnostic output** showing per-document pass/fail and field-level extracted-vs-expected diffs when tests run

**Success criteria:**
- Tests can run via `uv run pytest tests/extraction/` and report aggregate accuracy scores
- When a test fails, output shows which documents failed and what the discrepancy was (not just "accuracy below threshold")
- Infrastructure is ready to support M3b development: add extraction heuristics → run tests → see what improved/regressed

**Out of scope (deferred):**
- Smoke set (~50-100 PDFs with symlinks)
- HTML reports or trend tracking across runs
- Automated corpus selection tooling

## Glossary

- **BetterBibTeX**: Zotero plugin that generates stable citation keys (e.g., `author2023title`) and exports libraries to JSON format; serves as the bridge between Zotero items and test ground truth
- **Citekey**: Stable human-readable identifier for a bibliographic item (e.g., `knuth1984literate`), generated from author/year/title and used to match PDFs to their metadata
- **CSL-JSON**: Citation Style Language JSON format for bibliographic metadata, used by citation processors and Zotero; contains fields like `title`, `author`, `issued` with specific structural conventions
- **Golden set**: Curated collection of representative test documents with known-good metadata, used for validation and regression testing
- **Ground truth**: Verified correct metadata for test documents, sourced from Zotero's existing bibliographic records
- **Marker**: ML-based PDF extraction tool that converts PDFs to markdown while preserving structure; primary extraction engine for the system
- **M2/M3a/M3b**: Milestone identifiers from the project build plan (M2=PDF extraction, M3a=metadata validation, M3b=metadata extraction from content)
- **Pytest parametrization**: Pattern where a single test function runs multiple times with different input values (here: one run per PDF in the golden set)
- **Session-scoped fixture**: pytest fixture created once per test session and shared across all tests; used for expensive resources like the PDF extractor
- **Smoke set**: Larger test corpus (~50-100 PDFs) for quick sanity checks; intentionally deferred in this design
- **XDG**: Cross-Desktop Group standards for file system paths (config, data, cache directories); followed by the application for portable storage
- **ZoteroReader**: Application facade providing read-only access to Zotero library data via either direct SQLite access or BetterBibTeX JSON export

## Architecture

Hybrid test infrastructure combining pytest parametrization with an optional manifest for enrichment.

**Core flow:**

```
tests/extraction/golden_set/*.pdf
         ↓ (discover files, parse citekey from filename)
    (pdf_path, citekey) tuples
         ↓ (ZoteroReader.get_item via fixture)
    GroundTruth(title, authors, issued_date)
         ↓ (PdfExtractor.extract via fixture)
    ExtractionResult + comparison against ground truth
         ↓
    Per-document pass/fail with diagnostic output
```

**Key components:**

| Component | Location | Responsibility |
|-----------|----------|----------------|
| Test fixtures | `tests/extraction/conftest.py` | Load PDFs, ZoteroReader, extractor; provide ground truth |
| Quality tests | `tests/extraction/test_extraction_quality.py` | Validate Marker output (M2 validation) |
| Accuracy tests | `tests/extraction/test_metadata_extraction.py` | Validate metadata extraction (M3b validation) |
| Ground truth model | `tests/extraction/conftest.py` | `GroundTruth` dataclass with CSL-JSON normalization |
| Diagnostic output | `tests/extraction/conftest.py` | `DocumentResult` dataclass, session summary hook |
| Optional manifest | `tests/extraction/golden_set_manifest.json` | Categories, expected failures, notes |

**Data flow:**

1. **Discovery**: Glob `golden_set/*.pdf`, extract citekey from filename stem
2. **Ground truth loading**: `ZoteroReader` (session-scoped) loads CSL-JSON from `~/Zotero/library.json`
3. **Extraction**: `PdfExtractor` (session-scoped, lazy_load=True) extracts each PDF once
4. **Comparison**: Normalize and compare extracted metadata against ground truth
5. **Reporting**: Per-document results aggregated into session summary

## Existing Patterns

**Fixture patterns from codebase:**

This design follows established patterns from `tests/integration/conftest.py`:
- Session-scoped fixtures for expensive resources (matches `integration_library` pattern)
- Generator-based fixtures with cleanup (matches `temp_dir` pattern)
- Real resources over mocks where possible (existing tests use actual SQLite, valid PDF bytes)

**ZoteroReader usage from `tests/unit/test_zotero.py`:**
- Context manager pattern (`with ZoteroReader(...) as reader`)
- Fixture composition: temp_dir → directory structure → reader instance

**New patterns introduced:**

- **Parametrized tests over external files**: Unlike existing tests that generate minimal PDFs, these tests use real PDFs from a golden set directory. This is appropriate for quality/accuracy testing vs. unit testing.
- **Optional manifest enrichment**: The manifest pattern is new but non-intrusive (tests work without it).

## Implementation Phases

### Phase 1: Directory Structure and Core Fixtures

**Goal:** Establish test directory, move golden set PDFs, create foundational fixtures.

**Components:**
- `tests/extraction/` directory structure
- `tests/extraction/golden_set/` with PDFs moved from `pdf_test_set/`
- `tests/extraction/conftest.py` with:
  - `zotero_reader` fixture (session-scoped, pointing to `~/Zotero`)
  - `golden_set_pdfs` fixture (discovers PDFs, returns `list[tuple[Path, str]]`)
  - `pdf_extractor` fixture (session-scoped, lazy_load=True)

**Dependencies:** None (first phase)

**Done when:** `pytest tests/extraction/ --collect-only` discovers test files and fixtures load without error

### Phase 2: Ground Truth Loading

**Goal:** Load and normalize Zotero metadata as ground truth for comparison.

**Components:**
- `GroundTruth` dataclass in `tests/extraction/conftest.py`:
  - `citekey: str`
  - `title: str`
  - `authors: tuple[str, ...]` (normalized to "Family, Given" format)
  - `issued_date: str | None` (normalized from CSL date-parts)
  - `from_csl_json()` classmethod for construction
- `ground_truth` fixture returning `dict[str, GroundTruth]` keyed by citekey

**Dependencies:** Phase 1 (ZoteroReader fixture)

**Done when:** Ground truth loads for all golden set citekeys, author/date normalization handles edge cases

### Phase 3: Extraction Quality Tests

**Goal:** Validate Marker extraction produces usable output for each golden set PDF.

**Components:**
- `tests/extraction/test_extraction_quality.py`:
  - `TestExtractionQuality` class
  - Parametrized test over golden set PDFs
  - Assertions for character count (≥100) and printable ratio (≥0.8)
- pytest marker registration: `extraction` marker in `pyproject.toml`

**Dependencies:** Phase 1 (fixtures), Phase 2 (ground truth for citekey validation)

**Done when:** Quality tests run, pass for well-formed PDFs, fail with clear messages for problematic ones

### Phase 4: Accuracy Metrics and Comparison Functions

**Goal:** Implement comparison logic for metadata accuracy measurement.

**Components:**
- Comparison functions in `tests/extraction/conftest.py`:
  - `title_similarity(extracted: str, expected: str) -> float` (normalized string comparison)
  - `author_match_score(extracted: tuple[str, ...], expected: tuple[str, ...]) -> float` (set-based)
  - `year_matches(extracted: str | None, expected: str | None) -> bool`
- `DocumentResult` dataclass capturing per-document outcomes

**Dependencies:** Phase 2 (ground truth model)

**Done when:** Comparison functions handle normalization edge cases (whitespace, case, partial dates)

### Phase 5: Metadata Extraction Accuracy Tests

**Goal:** Test infrastructure for M3b metadata extraction validation.

**Components:**
- `tests/extraction/test_metadata_extraction.py`:
  - `TestMetadataExtraction` class
  - Parametrized tests for title, author, and date accuracy
  - Placeholder/skip markers until M3b extraction logic exists
- Threshold constants: TITLE_THRESHOLD=0.9, AUTHOR_THRESHOLD=0.7

**Dependencies:** Phase 4 (comparison functions)

**Done when:** Test structure exists, runs with skips, ready to enable when M3b implements extraction

### Phase 6: Diagnostic Output and Summary

**Goal:** Provide actionable diagnostic output when tests run.

**Components:**
- `DocumentResult` enhancement with failure reasons
- `AccuracyReport` dataclass for aggregate statistics
- `pytest_sessionfinish` hook or fixture finalizer printing summary:
  - Per-category accuracy percentages
  - List of failed documents with reasons
  - Extracted vs. expected values for failures

**Dependencies:** Phases 3-5 (tests generating results)

**Done when:** Running `pytest tests/extraction/ -v` shows per-document status; summary shows aggregate accuracy

### Phase 7: Optional Manifest Integration

**Goal:** Add manifest support for categories, expected failures, and filtering.

**Components:**
- `tests/extraction/golden_set_manifest.json` (initially empty or minimal)
- `golden_set_manifest` fixture loading manifest or returning empty default
- `pytest_generate_tests` hook adding category markers from manifest
- `pytest.mark.xfail` application for documents with `expected_failures`

**Dependencies:** Phase 1 (fixture infrastructure)

**Done when:** Tests work without manifest; with manifest, can filter by category and known failures show as xfail

## Additional Considerations

**Zotero availability:** Tests assume `~/Zotero` exists with `library.json`. If running in CI or on a machine without Zotero, tests should skip gracefully with clear message.

**Extraction performance:** Golden set is ~20 PDFs. With Marker's lazy loading, first test loads models (~10-20 seconds), subsequent extractions are faster. Session-scoped extractor avoids reloading.

**Type extraction (deferred):** Document type classification is not included in M3b scope. Future enhancement: heuristic inference with user confirmation at ingestion time.

**Smoke set (deferred):** Infrastructure supports future addition of smoke set via symlinks to Zotero storage. Would require manifest or separate discovery mechanism for larger corpus.
