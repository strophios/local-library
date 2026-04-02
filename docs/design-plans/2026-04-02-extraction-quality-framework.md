# Extraction Quality Framework Design

## Summary

This framework builds a regression-tracking quality measurement system for Marker, the PDF-to-markdown extraction tool at the heart of the library's ingestion pipeline. The core problem it solves: currently there is no systematic way to know whether a change to extraction settings, cleanup code, or upstream Marker versions improves or degrades quality, or on what kinds of documents and features. The framework addresses this by introducing annotated synthetic source documents — realistic academic papers written in markdown with embedded region markers — which are compiled into PDFs across four noise tiers (clean digital, clean scan, moderate scan, degraded scan) and then run through the full extraction pipeline. Scores are computed per annotated region for two independent dimensions: semantic fidelity (did the words survive?) and structural fidelity (did headings stay headings, tables stay tables?).

The design prioritizes measurement before intervention. Rather than fixing known extraction weaknesses directly, the framework first establishes a baseline against which future changes can be evaluated. The four noise tiers are specifically chosen to support a recurring question: does a given change help on clean PDFs, noisy PDFs, or both? Results are stored as timestamped JSON and compared against an explicitly promoted baseline, following the same patterns as the existing retrieval evaluation framework in `tests/eval/`. Pytest integration via a custom marker keeps the tests opt-in, since fixture generation depends on external tools (pandoc, pdflatex) and Marker inference is slow.

## Definition of Done

1. 6-8 annotated synthetic source documents exist, covering core academic features (headings, tables, footnotes, bibliography, math), typography edge cases (ligatures, special characters, mixed fonts), and structural edge cases (nested lists, code blocks, figure captions, multi-column spanning elements)
2. PDF generation pipeline produces 4 noise tiers (T0 clean embedded, T1 clean OCR-needed, T2 moderate scan, T3 degraded) from each source document
3. Feature-level validators compute semantic scores (CER, WER) and structural scores per annotated region, tracked independently
4. Region alignment maps source annotations to corresponding regions in Marker-extracted output
5. Test runner orchestrates the full pipeline: generate → extract → score → report
6. Results stored as timestamped JSON with regression comparison against an explicitly promoted baseline
7. Pytest integration via `@pytest.mark.extraction_quality` marker, not run by default

## Glossary

- **Marker**: The primary PDF-to-markdown extraction library used by local-library. It converts PDFs to structured markdown, handling layout analysis, heading detection, table extraction, and math rendering.
- **MarkdownChunker**: The project's section-aware markdown splitter (`embeddings/chunking.py`). It breaks extracted markdown into chunks for embedding, respecting heading boundaries. Structural fidelity in the extracted output directly affects its behavior.
- **RAG (Retrieval-Augmented Generation)**: The query pipeline where retrieved document chunks are assembled into context and passed to an LLM to generate an answer. Extraction quality affects which chunks are retrieved and how coherent the context is.
- **CER (Character Error Rate)**: Edit distance between extracted and source text, normalized by source character count. The primary semantic fidelity metric; catches within-word corruption typical of OCR errors (e.g., "rn" misread as "m").
- **WER (Word Error Rate)**: Word-level edit distance normalized by source word count. Captures word-boundary errors — merges and splits — common in OCR output.
- **Semantic fidelity**: Whether the words in a region survived extraction intact. Measured via CER and WER. Directly relevant to embedding quality and RAG retrieval.
- **Structural fidelity**: Whether the structural intent of a region was preserved — headings rendered as markdown headings, tables as markdown tables, math as LaTeX blocks. Measured by feature-specific validators.
- **Feature type**: A label from a controlled vocabulary (e.g., `heading-h2`, `table-complex`, `display-math`) identifying what kind of document element an annotated region contains. Determines which validator is applied.
- **Noise tier**: One of four degradation levels applied to each source document during PDF generation (T0 clean embedded, T1 clean OCR-needed, T2 moderate scan, T3 degraded). Allows measuring extraction quality as a function of input quality.
- **Region alignment**: The process of finding where an annotated source region landed in Marker's output. Required because annotations exist only in the source markdown, not in the generated PDF.
- **Anchor-based alignment**: The alignment strategy used here: locate a region in extracted output by matching the nearest preceding heading, then fuzzy-matching the region's first and last words.
- **Alignment failure**: When a source region cannot be located in the extracted output. On a clean PDF (T0) this indicates a framework or extraction bug; on a degraded PDF (T3) it may indicate content loss.
- **Baseline**: A designated result file (`baseline.json`) against which all subsequent runs are compared for regression detection. Promotion is explicit and manual — never automatic.
- **pymupdf (fitz)**: Python library for PDF manipulation, used here to render PDF pages to images (needed for T1-T3 tier generation).
- **Pillow**: Python imaging library used to apply noise transforms (blur, rotation, contrast reduction) to rendered page images for T2/T3 tier generation.
- **Content hash check**: A caching mechanism that skips PDF regeneration when the source markdown hasn't changed, keyed on the file's content hash rather than modification time.
- **`@pytest.mark.extraction_quality`**: The pytest marker that gates these tests. Tests with this marker are not collected in ordinary `pytest` runs, since they depend on external tools and are slow.
- **RRF (Reciprocal Rank Fusion)**: The score fusion method used in the existing hybrid retrieval system, mentioned in context of the parallel between retrieval evaluation and extraction evaluation frameworks.

## Architecture

The framework measures extraction quality at **feature-level resolution** against **realistic composite documents**. Rather than isolated feature showcases (e.g., a document that's just headings), source documents are realistic synthetic academic papers that naturally exercise multiple features. Annotations mark feature regions as a measurement overlay.

Two score dimensions are tracked independently per annotated region:

- **Semantic fidelity** (CER, WER): Did the words survive extraction? Directly relevant to embedding quality and RAG retrieval.
- **Structural fidelity** (feature-specific validators): Was structural intent preserved — headings as headings, tables as tables? Relevant to MarkdownChunker's section-aware splitting and readability.

Scores aggregate upward: region → feature type → document → noise tier → overall. Every level is stored for drill-down.

### Source Documents

6-8 markdown files written as realistic academic papers. Each covers a plausible topic and exercises multiple features naturally. Example document concepts:

- Dense prose with footnotes, bibliography, simple tables (urban policy analysis)
- Math-heavy with inline and display equations, Greek symbols (statistical methods)
- Deep heading hierarchy, nested lists, pseudocode blocks (CS survey paper)
- Long-form prose, block quotes from primary sources, substantive footnote asides (historical analysis)
- Complex tables with multi-row headers, figure captions, mixed fonts (empirical study)
- Code blocks, technical notation, superscripts/subscripts beyond math (engineering report)

Feature coverage comes from the union across documents. Each document tests multiple features in realistic context, not one feature in isolation.

### Annotation Format

HTML comments in source markdown mark feature regions:

```markdown
The model is defined by the following relationship:

<!-- feature: display-math id:eq-primary -->
$$E = \sum_{i=1}^{n} w_i \cdot f(x_i) + \epsilon$$
<!-- /feature -->

As shown above, the weights
<!-- feature: inline-math id:inline-weights -->
$w_i \sim \mathcal{N}(0, \sigma^2)$
<!-- /feature -->
are drawn from a normal distribution.
```

Each annotation carries a **feature type** from a controlled vocabulary (`heading-h1`, `heading-h2`, `table-simple`, `table-complex`, `footnote`, `display-math`, `inline-math`, `blockquote`, `bibliography`, `code-block`, `nested-list`, `dense-prose`, etc.) and a unique **id** for tracking. Annotations are stripped before PDF generation.

### PDF Generation Pipeline

Source markdown → strip annotations → pandoc + pdflatex → clean PDF → noise variants.

| Tier | Name | Production method | Purpose |
|------|------|-------------------|---------|
| T0 | Clean embedded | Direct pandoc/pdflatex output | Baseline ceiling — Marker on good input |
| T1 | Clean OCR-needed | Render pages to 300 DPI images, re-composite as image-only PDF | OCR quality on clean source, no text layer |
| T2 | Moderate scan | T1 + slight Gaussian blur, ±1° rotation, faint background noise | Typical library/office scan condition |
| T3 | Degraded | T1 + heavy noise, ±3° skew, contrast reduction, simulated bleed-through | Bad photocopy / historical document |

Noise application uses fixed random seeds per tier for reproducibility. PDFs are cached and regenerated only when source markdown changes (content hash check). Generation is a separate step from testing — run explicitly or as a `make fixtures` target.

External dependencies (pandoc, pdflatex) are required only for fixture generation, not at runtime. Generated PDFs can optionally be committed to avoid CI dependency on LaTeX.

### Metrics

**Semantic fidelity** — computed per annotated region:

- **Character Error Rate (CER)**: Edit distance / source length. Primary metric. Catches within-word corruption (OCR's typical failure mode).
- **Word Error Rate (WER)**: Word-level edit distance / source word count. Captures word-boundary errors (merges/splits) common in OCR.
- Both computed on normalized text (stripped formatting, collapsed whitespace).

**Structural fidelity** — feature-specific validators per region:

- **Headings**: Detected as heading (binary) + level accuracy (exact or off-by-N)
- **Tables**: Detected as markdown table + column count + cell content presence
- **Lists**: Preserved as lists + nesting depth accuracy
- **Math**: Display equations preserved as LaTeX blocks; inline math preserved as `$...$`
- **Footnotes**: Markers extracted + linked to footnote text
- **Block structures**: Block quotes, code blocks preserved as respective markdown

Each validator is a small focused function: takes source region + aligned extracted region, returns score + diagnostics.

### Region Alignment

Since annotations exist only in the source, the framework must find where each annotated region landed in Marker's output. Strategy:

1. **Anchor-based alignment**: Use nearest preceding heading match + fuzzy content matching (first/last N words of the region) to locate corresponding substring in extracted text.
2. **Alignment failure as signal**: If a region can't be aligned, record it as "alignment failure." An alignment failure on T0 is a framework bug; on T3 it may be expected.

### Score Aggregation and Output

```
Per-region scores
  → Per-feature-type (average across regions of that type)
    → Per-document (average across features in document)
      → Per-tier (average across documents at that noise level)
        → Overall dashboard
```

Results written to timestamped JSON:

```json
{
  "run_id": "2026-04-02T14:30:00",
  "pipeline_version": "<git-sha>",
  "results": {
    "urban-transit": {
      "T0": {
        "semantic": { "CER": 0.02, "WER": 0.05 },
        "structural": {
          "heading-h2": { "detected": 1.0, "level_accuracy": 1.0 },
          "table-simple": { "detected": 1.0, "column_accuracy": 0.75 }
        },
        "regions": { "...per-region detail..." }
      }
    }
  }
}
```

### Regression Tracking

Results accumulate in `tests/extraction/synthetic/results/`. A designated `baseline.json` is the comparison target — promotion is explicit, never automatic.

Comparison function diffs latest run against baseline:
- Per-feature-type and per-tier deltas
- Regression flagging when any combination exceeds a configurable threshold (e.g., >5% relative CER increase)
- Human-readable Rich summary (green/yellow/red) and machine-readable JSON diff

## Existing Patterns

The project has an established evaluation framework in `tests/eval/` for retrieval quality: IR metrics (Precision@k, Recall@k, MRR, NDCG@k), a labeled query set, comparative harness, and `baseline_results.json` for regression tracking. This design follows the same patterns:

- **Explicit baseline with manual promotion** (matches `tests/eval/baseline_results.json`)
- **Timestamped result files** (matches eval harness output)
- **pytest marker for selective execution** (matches `@pytest.mark.extraction`)
- **JSON output format** for structured results

The existing `tests/extraction/` directory contains golden set tests (22 real PDFs) with pass/fail quality validation. This design complements rather than replaces them: golden set tests confirm extraction works on real documents; synthetic tests measure how well and track regressions.

Cleanup pipeline patterns followed:
- **Fault tolerance**: All validators catch exceptions and degrade gracefully (matches `markdown_cleanup.py` pattern)
- **Pass ordering**: Generation → extraction → alignment → scoring mirrors the existing artifact cleanup → markdown cleanup pipeline ordering

## Implementation Phases

### Phase 1: Annotation Parser and Metrics

**Goal:** Core infrastructure for parsing annotated markdown and computing quality scores.

**Components:**
- Annotation parser in `tests/extraction/synthetic/annotations.py` — parses `<!-- feature: ... -->` regions from source markdown, strips annotations for PDF generation, returns structured region data
- Metrics module in `tests/extraction/synthetic/metrics.py` — CER and WER computation on normalized text pairs
- Feature-type controlled vocabulary definition

**Dependencies:** None (first phase)

**Done when:** Annotations can be parsed from markdown, CER/WER computed on text pairs, all tests pass

### Phase 2: PDF Generation Pipeline

**Goal:** Produce 4 noise tiers from annotated source markdown.

**Components:**
- Generator in `tests/extraction/synthetic/generate.py` — strips annotations, calls pandoc/pdflatex for T0, renders pages via pymupdf for T1, applies Pillow transforms for T2/T3
- Fixture caching — content hash check to skip regeneration when source unchanged
- At least 2 initial source documents (enough to prove the pipeline end-to-end)

**Dependencies:** Phase 1 (annotation stripping)

**Done when:** 2 source documents produce 4 tiers each (8 PDFs total), generation is deterministic and cached

### Phase 3: Region Alignment

**Goal:** Map annotated source regions to corresponding locations in Marker-extracted output.

**Components:**
- Alignment module in `tests/extraction/synthetic/alignment.py` — anchor-based alignment using heading proximity and fuzzy content matching
- Alignment failure detection and reporting

**Dependencies:** Phase 1 (annotation parser provides region data)

**Done when:** Regions from source documents can be located in extracted text, alignment failures are detected and recorded

### Phase 4: Structural Validators

**Goal:** Feature-specific validation functions for structural fidelity scoring.

**Components:**
- Validators in `tests/extraction/synthetic/validators.py` — one validator per feature type (headings, tables, lists, math, footnotes, block structures)
- Each returns structured score + diagnostics
- Fault-tolerant: exceptions caught and reported, never crash the runner

**Dependencies:** Phase 3 (alignment provides region pairs to validate)

**Done when:** All feature types in the controlled vocabulary have validators, validators produce meaningful scores on test inputs

### Phase 5: Test Runner and Reporting

**Goal:** Orchestrator that runs the full pipeline and produces results.

**Components:**
- Runner in `tests/extraction/synthetic/runner.py` — generates PDFs → extracts via Marker + cleanup pipeline → aligns regions → scores → writes results JSON
- Rich-based human-readable summary output
- Regression comparison against baseline with threshold-based flagging
- pytest integration in `tests/extraction/synthetic/conftest.py` with `@pytest.mark.extraction_quality` marker

**Dependencies:** Phases 1-4 (all prior components)

**Done when:** Full pipeline runs end-to-end on at least 2 documents × 4 tiers, produces results JSON, regression comparison works against a baseline

### Phase 6: Source Document Authoring

**Goal:** Complete the synthetic document set with realistic composite papers.

**Components:**
- 6-8 annotated source documents in `tests/extraction/synthetic/sources/` covering all target feature types
- Feature coverage matrix documenting which documents exercise which features
- Generated fixture PDFs for all documents × 4 tiers

**Dependencies:** Phase 5 (runner must work end-to-end before scaling up documents)

**Done when:** All target feature types covered across the document set, runner produces complete results, initial baseline established

## Additional Considerations

**External dependencies:** pandoc and pdflatex are required for fixture generation only. If CI installation is problematic, pre-generated PDFs can be committed. pymupdf (fitz) is pip-installable and handles PDF-to-image rendering.

**Relationship to future extraction improvements:** This framework is designed to be in place *before* Marker settings tuning, spell-check integration, or reflow improvements. Each subsequent change should show measurable impact in the framework's metrics. The four-tier structure specifically enables answering "does this change help clean PDFs, noisy PDFs, or both?"

**Force-OCR question:** The T0/T1 tier distinction sets up future investigation of whether forcing OCR on documents with embedded text improves quality (cases where embedded text is poor). This is a measurement question the framework can answer once it exists, not a design decision to make now.
