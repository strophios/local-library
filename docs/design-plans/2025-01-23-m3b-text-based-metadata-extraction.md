# M3b: Text-Based Metadata Extraction Design

## Summary

This design implements automatic metadata extraction for PDFs added without explicit bibliographic information. When a user runs `local-library add <path>` without the `--metadata` flag, the system extracts title, authors, publication date, and document type directly from the Marker-produced markdown text. The extraction architecture uses a hybrid approach: fast heuristic extractors run first on each field independently, scoring their confidence based on signal strength and candidate margin. If any field's confidence falls below threshold, an LLM fallback re-extracts all fields in a single call, providing higher-quality values while preserving the original heuristic confidence scores to maintain calibration accuracy.

Documents with low-confidence extractions receive a new `NEEDS_REVIEW` status with diagnostic warnings explaining which fields are uncertain, enabling graceful degradation rather than blocking ingestion. The extracted metadata flows through the existing `MetadataHandler` for CSL-JSON validation and citekey generation, reusing established patterns. This design lays the foundation for M3c (API enrichment) by introducing per-field provenance tracking and confidence scoring that will enable intelligent merging of metadata from multiple sources.

## Definition of Done

**Primary Deliverables:**
1. **TextMetadataExtractor** component that extracts title, authors, and date from Marker-produced markdown, with per-field confidence scores
2. **Integration with MetadataHandler** so extraction flows through existing validation and citekey generation
3. **NEEDS_REVIEW status** added to DocumentStatus, triggered when any field confidence is below threshold, with validation warnings explaining which fields are uncertain
4. **Golden set validation** demonstrating: title ≥80% accuracy, authors ≥70% accuracy, date ≥75% accuracy (against Zotero ground truth)

**Success Criteria:**
- Documents added without `--metadata` get extracted metadata automatically
- Low-confidence extractions are flagged as NEEDS_REVIEW with diagnostic warnings
- Confidence scores correlate with actual accuracy (higher confidence → higher accuracy on test set)
- Graceful degradation: missing/uncertain fields don't block ingestion

**Out of Scope:**
- External API enrichment (M3c, deferred)
- Smoke set testing (deferred until M3b further along)
- Non-PDF content types

## Glossary

- **CSL-JSON**: Citation Style Language JSON format for bibliographic metadata, used by citation processors and Zotero
- **Citekey**: BetterBibTeX-style unique identifier for documents (e.g., "smith2023theory") used in citations
- **Marker**: PDF extraction tool that produces markdown with preserved document structure
- **MetadataHandler**: Existing component that validates CSL-JSON metadata and generates citekeys
- **LiteLLM**: Library for provider-agnostic LLM access, already a project dependency
- **Functional Core**: Design pattern separating pure functions (no I/O, deterministic) from side effects
- **Golden set**: Test dataset of documents with verified ground truth metadata from Zotero
- **Confidence calibration**: Statistical property where confidence scores correlate with actual accuracy (higher confidence → higher accuracy)
- **Candidate margin**: Gap between top extraction candidate and runner-up; larger margin indicates higher certainty
- **Graceful degradation**: System continues functioning with reduced capabilities rather than failing when resources unavailable
- **Heuristic extractors**: Rule-based pattern matching for metadata extraction (fast, no external dependencies)
- **LLM fallback**: Use of language models to improve extraction quality when heuristic confidence is low
- **nameparser**: Python library for parsing person names into family/given components
- **CSL-JSON literal**: Author representation storing full name as single string when family/given split is ambiguous

## Architecture

Hybrid extraction architecture: heuristic extractors run first for speed and cost-efficiency; LLM fallback triggers when any field confidence falls below threshold.

```
┌─────────────────────────────────────────────────────────────────┐
│                    TextMetadataExtractor                         │
├─────────────────────────────────────────────────────────────────┤
│  extract(markdown_text: str) → TextExtractionResult             │
│                                                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────┐│
│  │TitleExtractor│ │AuthorExtractor│ │DateExtractor │ │TypeExtr.││
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────┬────┘│
│         │                │                │               │     │
│         └────────────────┴────────────────┴───────────────┘     │
│                              │                                   │
│                    ConfidenceAggregator                         │
│                              │                                   │
│         ┌────────────────────┴───────────────────┐              │
│         │ any field confidence < threshold?       │              │
│         └────────────────────┬───────────────────┘              │
│              yes │                    │ no                       │
│                  ▼                    ▼                          │
│         ┌─────────────┐      ┌────────────┐                     │
│         │LLMExtractor │      │   Return   │                     │
│         │(all fields) │      │  results   │                     │
│         └──────┬──────┘      └────────────┘                     │
│                │                                                 │
│                ▼                                                 │
│         Return LLM results                                       │
│         (confidence preserved from heuristics)                   │
└─────────────────────────────────────────────────────────────────┘
```

**Key design decisions:**

1. **Per-field extractors** — Each field (title, authors, date, type) has an independent extractor that can be tested and tuned separately. Extractors are pure functions (Functional Core).

2. **Multi-signal confidence scoring** — Confidence derives from candidate margin (gap between top candidate and runner-up) plus signal strength. Higher confidence correlates with higher accuracy.

3. **LLM as enhancement, not authority** — When LLM fallback triggers, it provides values but heuristic confidence is preserved. Documents still flag as NEEDS_REVIEW because the heuristics were uncertain. This allows data collection on LLM reliability before trusting it implicitly.

4. **Whole-document LLM extraction** — When triggered, LLM extracts all fields in one call (cost-efficient, cross-field context benefits).

5. **Graceful degradation** — System works without LLM access. If LLM unavailable, heuristic values are kept and document flagged for review.

**Data flow integration:**

```
Library.add(path, metadata=None)
  → FileAcquirer.acquire()
  → PdfExtractor.extract()           # Returns ExtractionResult with markdown
  │
  ├─ if metadata provided:
  │    → MetadataHandler.process(metadata)    # Existing path unchanged
  │
  └─ if metadata is None:                     # NEW PATH
       → TextMetadataExtractor.extract(markdown_text)
       → build_csl_json(extraction_result)
       → MetadataHandler.process(csl_json)    # Reuses existing validation
       → determine_status(extraction_result)
            → NEEDS_REVIEW if any field below threshold
            → READY otherwise
```

**New data types:**

```python
@dataclass(frozen=True)
class FieldExtraction:
    """Result of extracting a single metadata field."""
    value: str | None              # Extracted value (None if not found)
    confidence: float              # 0.0 to 1.0 (heuristic confidence, preserved even if LLM provided value)
    source: str                    # "heuristic" | "llm"
    alternatives: tuple[str, ...]  # Other candidates considered
    reasoning: str                 # Why this value was chosen

@dataclass(frozen=True)
class TextExtractionResult:
    """Complete metadata extraction result."""
    title: FieldExtraction
    authors: tuple[FieldExtraction, ...]
    date: FieldExtraction
    doc_type: FieldExtraction
    overall_confidence: float      # Min of field confidences
    needs_review: bool
    review_reasons: tuple[str, ...]
```

**DocumentStatus extension:**

```python
class DocumentStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"  # NEW
```

## Existing Patterns

Investigation found existing extraction and metadata handling patterns:

**Follows existing patterns:**
- `PdfExtractor` in `src/local_library/ingestion/pdf.py` — extractor returning typed result with quality metrics. TextMetadataExtractor follows same pattern.
- `MetadataHandler` in `src/local_library/ingestion/metadata.py` — source-agnostic validation. New extractor produces CSL-JSON that flows through existing handler.
- `ExtractionResult` dataclass pattern — frozen dataclass with extracted content and metadata. New types follow same style.
- Error handling via `ErrorCode` enum and typed exceptions.

**New patterns introduced:**
- Per-field confidence scoring — no existing precedent; introduces `FieldExtraction` type.
- `NEEDS_REVIEW` status — extends existing `DocumentStatus` enum for partial-success states.

**Layering foundation for M3c:**
- `TextExtractionResult` structure is designed to be one input to a future `MetadataResolver` that layers multiple sources (explicit metadata > API enrichment > text extraction).
- `source` field tracks provenance for intelligent merging.

## Implementation Phases

### Phase 1: Data Types and Status Extension

**Goal:** Add new types for extraction results and extend DocumentStatus.

**Components:**
- `FieldExtraction` and `TextExtractionResult` dataclasses in `src/local_library/core/models.py`
- `DocumentStatus.NEEDS_REVIEW` added to enum in `src/local_library/core/models.py`
- Storage schema update if needed for new status

**Dependencies:** None (foundation phase)

**Done when:** Types importable, status recognized by storage layer, existing tests still pass.

### Phase 2: Title Extraction

**Goal:** Extract document title from markdown with confidence scoring.

**Components:**
- `TitleExtractor` in `src/local_library/ingestion/text_extraction.py`
- Candidate generation from first 300 words
- Multi-signal scoring (position, isolation, length, capitalization)
- Confidence calculation from candidate margin

**Dependencies:** Phase 1 (FieldExtraction type)

**Done when:** Title extraction achieves ≥80% accuracy on golden set, confidence correlates with accuracy.

### Phase 3: Author Extraction

**Goal:** Extract author names with best-effort family/given parsing.

**Components:**
- `AuthorExtractor` in `src/local_library/ingestion/text_extraction.py`
- Author block detection with fallbacks (Abstract marker, paragraph heuristic, email detection)
- Integration with `nameparser` library for name parsing
- Library author lookup for known names (query existing authors in storage)
- CSL-JSON `literal` fallback for ambiguous names

**Dependencies:** Phase 1 (FieldExtraction type), `nameparser` dependency added

**Done when:** Author extraction achieves ≥70% accuracy on golden set.

### Phase 4: Date and Type Extraction

**Goal:** Extract publication year and document type.

**Components:**
- `DateExtractor` in `src/local_library/ingestion/text_extraction.py`
- Priority search (explicit markers > copyright > ISO dates > standalone years)
- `TypeExtractor` in `src/local_library/ingestion/text_extraction.py`
- Type heuristics (journal markers, chapter numbers, report keywords)
- Default fallback to "article-journal"

**Dependencies:** Phase 1 (FieldExtraction type)

**Done when:** Date extraction achieves ≥75% accuracy on golden set, type defaults sensibly.

### Phase 5: TextMetadataExtractor Orchestration

**Goal:** Combine field extractors with confidence aggregation.

**Components:**
- `TextMetadataExtractor` class in `src/local_library/ingestion/text_extraction.py`
- Orchestrates TitleExtractor, AuthorExtractor, DateExtractor, TypeExtractor
- Aggregates per-field confidence into overall confidence
- Determines `needs_review` flag and `review_reasons`

**Dependencies:** Phases 2, 3, 4

**Done when:** End-to-end extraction works without LLM, NEEDS_REVIEW flag triggers correctly.

### Phase 6: LLM Fallback

**Goal:** Add LLM extraction for low-confidence documents.

**Components:**
- `LLMExtractor` in `src/local_library/ingestion/text_extraction.py`
- Prompt construction with document header and heuristic candidates
- LiteLLM integration (already a project dependency)
- Response parsing to FieldExtraction values
- Configuration: `EXTRACTION_LLM_ENABLED`, `EXTRACTION_LLM_MODEL`, `EXTRACTION_CONFIDENCE_THRESHOLD`

**Dependencies:** Phase 5 (orchestrator provides candidates)

**Done when:** LLM fallback triggers on low-confidence documents, provides values, gracefully degrades if unavailable.

### Phase 7: Library Integration

**Goal:** Wire TextMetadataExtractor into Library.add() flow.

**Components:**
- Update `Library.add()` in `src/local_library/core/library.py` to call TextMetadataExtractor when no metadata provided
- `build_csl_json()` function to convert TextExtractionResult to CSL-JSON
- Status determination based on extraction confidence
- Validation warnings merged with extraction review reasons

**Dependencies:** Phase 5 or 6 (extractor complete)

**Done when:** `local-library add <path>` without `--metadata` extracts metadata automatically, NEEDS_REVIEW documents queryable via CLI.

### Phase 8: Confidence Calibration Validation

**Goal:** Verify confidence scores correlate with actual accuracy.

**Components:**
- Calibration test in `tests/extraction/test_metadata_extraction.py`
- Bin documents by confidence, verify higher confidence → higher accuracy
- Document calibration curve in test output

**Dependencies:** Phase 7 (full integration)

**Done when:** Statistical correlation between confidence and accuracy demonstrated on golden set.

## Additional Considerations

**Author lookup performance:** Library author lookup queries storage on every extraction. For large libraries, consider caching known authors in memory during batch imports.

**LLM cost tracking:** Consider adding extraction cost to document metadata for visibility into LLM usage patterns. Not required for M3b but useful for future optimization.

**Future layering (M3c):** The `source` field in FieldExtraction and per-field confidence scores are designed to enable intelligent merging when external API metadata sources are added. The current design makes no assumptions about source priority beyond "explicit metadata wins."
