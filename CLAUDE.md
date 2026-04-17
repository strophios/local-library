# CLAUDE.md

Last verified: 2026-04-17

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a personal knowledge management system that ingests diverse digital documents (web articles, PDFs, etc.), extracts content, manages bibliographic metadata, provides ML-based auto-tagging, and serves as a local RAG database. The system is self-sufficient but designed for interoperability with Zotero.

## Architectural Decisions

### System Philosophy
- **Self-sufficient with Zotero interoperability**: The system functions completely independently but can exchange data with Zotero
- Zotero is treated as a peer/data source, not as a substrate to extend
- The system owns what Zotero doesn't do well: web content ingestion, text extraction, embeddings, auto-tagging, and markdown note management
- Zotero remains valuable for academic PDF management via its browser connector and citation metadata

### Why Not a Zotero Plugin?
ML features (embeddings, RAG, auto-tagging) require Python infrastructure that cannot run in Zotero's JavaScript plugin environment. Once external Python infrastructure is necessary, it makes sense for that system to own all functionality beyond Zotero's strengths.

## Core Data Model

Each document record contains:

- **Identity**: UUID, citekey (BetterBibTeX-style), optional Zotero item key, DOI/URL/ISBN
- **Bibliographic metadata**: CSL-JSON blob (Zotero-compatible, citation-processor-ready) plus indexed fields
- **Content**: Path to original file, extracted plain text, content hash
- **Embeddings**: Vector embeddings for full doc or chunks (sqlite-vec, successor to deprecated sqlite-vss)
- **Tags**: Manual and auto-generated with source flag; confidence scores for auto-tags
- **Notes**: Path to markdown file with YAML frontmatter linking back to record

## Zotero Interoperability

### Reading from Zotero
- Direct SQLite access to `zotero.sqlite` for read operations (Zotero 8+ required)
- Citation keys read from Zotero's native `citationKey` field via itemData EAV schema (fieldID looked up dynamically from `fields` table)
- **Library-scoped citekey resolution**: CitekeyMapper.lookup() and has_citekey() require `library_id` to prevent cross-library collisions (e.g., same citekey in personal and group libraries resolving to wrong item)
- Note: Zotero locks the database while running; copy file first if Zotero is active
- CSL-JSON metadata read from Better BibTeX `library.json` export
- Query items, attachments, tags, and notes from stable schema

### Writing to Zotero
- **NEVER write to SQLite directly** (risk of corruption/sync conflicts)
- Use local API (HTTP server on port 23119) for tags and item modifications
- Alternatively use export/import via Zotero's translation architecture for bulk operations

### Sync Strategy
- Periodic scan for new/modified items in Zotero database
- Import PDFs and metadata for new items
- Push auto-generated tags back via local API
- Notes managed primarily in external system (bidirectional sync adds complexity)

## Build Approach

Development follows a **pipeline-first, layer-complete** approach documented in `build_philosophy.md`. The key insight: pipeline stages (vertical data flow) and architectural layers (horizontal concerns) are orthogonal. Build along the pipeline for rapid feedback; implement layers completely when touched.

### Current Status: Phase 1 Complete + Post-M7 Extensions

Milestones M1 (record storage), M2 (PDF extraction), M3a (metadata validation), M3b (text-based metadata extraction), M4 (Zotero read-only access), M5 (embedding pipeline), M6 (retrieval), and M7 (RAG query interface) are implemented. Post-M7 work has added extraction resilience (pdftext fallback, dynamic timeouts, progress callbacks), a metadata provenance pipeline, and an MCP server for Claude Code integration. **Full Zotero corpus imported**: 1,216 documents ready (99.3%), 9 extraction timeouts. The system can:
- Ingest local PDF files via CLI (`local-library add <path>`)
- Accept explicit CSL-JSON metadata (`--metadata <file>`)
- Extract text to markdown via Marker
- Validate metadata against CSL-JSON schema and generate citekeys
- **Extract metadata from PDF text** when no explicit metadata provided
- Set documents to NEEDS_REVIEW status when extraction confidence is low
- Optionally use LLM fallback (via LiteLLM) for low-confidence extractions
- **Chunk extracted text and compute vector embeddings** via nomic-embed-text-v1.5
- **Track embedding status** (PENDING/CURRENT/STALE) across the document lifecycle
- **Search documents** via hybrid (vector + FTS5 with RRF fusion), vector-only, or FTS-only modes
- **Ask natural language questions** and get RAG-generated answers with source citations (streaming or blocking)
- Store documents in content-addressable storage with SQLite metadata
- Query, list, search, and delete documents via CLI
- Read items, attachments, and metadata from Zotero library (via database or BetterBibTeX JSON export)

**Implemented:**
- PDF ingestion from local filesystem
- Text extraction via Marker with quality validation and markdown cleanup (HTML coercion, dehyphenation, paragraph reflow)
- CSL-JSON metadata validation with BetterBibTeX-style citekey generation
- Indexed field extraction (title, authors, issued_date)
- **Text-based metadata extraction**: heuristic extractors for title, authors, date, and document type with confidence scoring
- **NEEDS_REVIEW workflow**: documents with low-confidence extraction flagged for human review
- **Optional LLM fallback**: LLMClient injection with LiteLLM backend for re-extracting low-confidence fields
- **Embedding pipeline**: section-aware markdown chunking (~512 tokens, ~15% overlap), nomic-embed-text-v1.5 via sentence-transformers (768-dim vectors), sqlite-vec storage with FTS5
- **Embedding status tracking**: PENDING → CURRENT on embed, CURRENT → STALE on re-extraction, cascade deletion on document delete
- **Embed-on-add**: documents automatically embedded during `add` and `zotero import` (use `--skip-embed` to defer)
- **CLI `embed` command**: manual embedding/re-embedding with `--pending`, `--all`, `--force`, `--dry-run` options
- **Graceful degradation**: library functions without sqlite-vec for document storage; embedding operations fail clearly
- **Retrieval system**: VectorRetriever (cosine similarity), FTSRetriever (BM25 via FTS5), HybridRetriever (RRF fusion with configurable weights), **cross-encoder reranking** via RerankedRetriever decorator (enabled by default)
- **Retriever protocol**: Protocol-based extensibility; `Library.get_retriever()` factory method wires up dependencies; `Reranker` protocol for pluggable reranking
- **Cross-encoder reranking**: Document-aware CrossEncoderReranker groups candidates by document, limits chunks per document, scores via cross-encoder/ms-marco-MiniLM-L-12-v2, applies sigmoid normalization. RerankedRetriever wraps any Retriever with broadened candidate pool + reranking
- **CLI `search` command**: hybrid/vector/fts modes, document-scoped search (--doc), JSON output (--json), configurable result limit (--limit), reranking on by default (--no-rerank to disable)
- **Retrieval evaluation framework**: IR metrics (Precision@k, Recall@k, MRR, NDCG@k with graded relevance), 76-query evaluation set across 5 categories with 3-tier relevance grading, automated comparative evaluation harness, reranker benchmark script. Dev-corpus baseline (hybrid+rerank, ~20 docs, post-extraction-fix): English-only MRR=0.944, NDCG@10=0.947 on 70 queries; aggregate NDCG@10=0.880 folds in cross-language misses. Per-query diagnosis in `tests/eval/README.md`
- **LLM abstraction layer**: LLMClient protocol with LiteLLMClient implementation; provider-agnostic LLM access with error mapping to ErrorCode hierarchy
- **RAG query interface**: RAGInterface orchestrates context assembly, prompt construction, and LLM generation; RAGStream supports streaming with token accumulation; pre-LLM gate skips API call when no context retrieved
- **CLI `ask` command**: streaming answers with Rich Live display, --no-stream, --json, --model, --mode, --doc, --limit, --no-rerank options; source citations with citekey attribution
- **MCP server**: FastMCP-based server (stdio transport) exposing 4 read-only tools (search_library, show_document, list_documents, get_document_text) for Claude Code integration. Markdown-only responses, identifier resolution via @citekey/UUID, chunk-based document text access with short-doc/long-doc modes
- **Extraction resilience**: PDF pre-check via pymupdf (page count + text sampling) before Marker runs. Dynamic timeout scaling (text PDFs 5s/page, image PDFs 45s/page, capped at 4h). pdftext fallback when Marker fails and the PDF has extractable text — fallback documents go to NEEDS_REVIEW with EXTRACTION_FALLBACK error code but still embed. Progress callback protocol (precheck_complete, extraction_progress every 30s, extraction_complete, extraction_fallback events) used by zotero import for live Rich output.
- **Metadata provenance pipeline**: `MetadataSource` enum (ZOTERO, EXPLICIT, FILENAME, TEXT_EXTRACTED) tracks where metadata came from. Library.add() persists preliminary metadata before extraction, so FAILED documents retain citekey and basic metadata. Filename heuristic parser (`parse_filename_metadata`) generates best-effort CSL-JSON from academic naming conventions (Author - Year - Title, Author_Year_Title, AuthorYear, etc.). After successful extraction, FILENAME-sourced metadata can be upgraded via text extraction; ZOTERO/EXPLICIT metadata is authoritative and never upgraded. Upgrades that would change the citekey flag NEEDS_REVIEW rather than auto-applying, preserving referential stability.
- SQLite storage with content-addressable file layout (schema v4)
- CLI interface (add, list, show, delete, open, update, review, reextract, embed, search, ask commands)
- @citekey identifier support with fuzzy matching suggestions
- Pagination support (--limit, --all flags on list command)
- Zotero read-only access: ZoteroReader facade with database and JSON export backends, native Zotero 8 citekey mapping (CitekeyMapper via EAV schema with library-scoped lookup), attachment resolution, collection and library filtering
- **Batch import from Zotero**: `zotero import` command with library/collection filtering, dry-run mode, progress tracking, and continue-on-error (defaults to personal library)
- **Reextract command**: `reextract` CLI command re-runs text extraction on existing documents (useful after extraction pipeline improvements)
- **Extraction quality framework**: Synthetic document benchmark in `tests/extraction/synthetic/` measures extraction fidelity across 4 noise tiers (T0 clean embedded, T1 clean OCR, T2 moderate scan, T3 degraded) with CER/WER metrics and structural validators. Config-driven noise pipeline with 7 artifact types and per-page deterministic seeds. 6 annotated source documents. Opt-in via `--run-extraction-quality` pytest flag.

**Immediate next step:** Eval set re-annotation at corpus scale. The initial full-corpus baseline run shows apparent regression that is largely an annotation artifact (the flood of new documents produces many correct-but-unannotated results that score as wrong). Real quality targets and conceptual-query improvements are gated on re-annotating existing queries against the full corpus, adding new queries, and adding chunk-level annotations. See `roadmap.md` and `docs/feature-areas/rag-pipeline-improvements/README.md`.

**Beyond Phase 1:** Development is organized into six feature areas, each with its own progression. **`roadmap.md` is the central overview** — check it for current focus, progress tracking, and cross-cutting dependencies. Feature area READMEs in `docs/feature-areas/` have detailed planning per area:
- **Neovim Citation Workflow** (headline) — library daemon, Neovim plugin for visual-mode citation search
- **Claude Code Integration** — MCP server built (4 read-only tools); research skills layered on top are next
- **Content Ingestion** — `add <url>` with trafilatura; later EPUB and external API metadata enrichment
- **Note Management** — auto-generated markdown stubs with YAML frontmatter
- **Automated Content Analysis** — auto-tagging, clustering, triage-based verification
- **RAG Pipeline Improvements** — evaluation, retrieval quality, query processing (see feature area README for current status)

**Also deferred:** M3b benchmarks (extraction functional but untested at scale), M3c (API metadata enrichment), Zotero tag export, bidirectional note sync. See individual feature area READMEs for context.

### Architectural Layers

Five horizontal concerns cut across the system:

1. **Storage**: SQLite schema, CRUD operations, sqlite-vec, FTS5
2. **Ingestion**: Content acquisition, extraction (Marker), metadata handling
3. **Embeddings + Retrieval**: Chunking, nomic-embed-text, similarity operations, FTS5 search, hybrid retrieval (RRF fusion), cross-encoder reranking
4. **LLM + RAG**: LLMClient protocol, LiteLLM provider abstraction, context assembly, prompt construction, answer generation
5. **Interface**: CLI, MCP server, (later) daemon, Neovim plugin, HTTP API

## Key Libraries and Tools

- **Web extraction**: trafilatura, readability-lxml
- **PDF extraction**: Marker (primary), olmOCR (for scanned historical documents on remote GPU)
- **Embeddings**: nomic-embed-text-v1.5 (local, 768 dims, 8192 context) via sentence-transformers
- **Reranking**: cross-encoder/ms-marco-MiniLM-L-12-v2 via sentence-transformers CrossEncoder
- **Metadata**: CrossRef API, GROBID (for academic PDFs), Open Graph tags (for web)
- **Vector storage**: sqlite-vec (v0.1.6+), SQLite FTS5 for hybrid search
- **LLM interface**: Custom RAGInterface + LiteLLM for provider abstraction
- **MCP server**: FastMCP (mcp>=1.27.0) for Claude Code tool integration over stdio
- **Citations**: citeproc-py against CSL-JSON

## RAG System Design Decisions

Comprehensive research on the RAG pipeline is documented in `RAG_background/`. The final summary (`00_final_summary_report.md`) is the authoritative reference. Key decisions:

### Embedding Model: nomic-embed-text-v1.5
- **MTEB score**: 62.28% (matches OpenAI text-embedding-3-small)
- **Critical**: Requires task-specific prefixes:
  - `search_query:` for user queries
  - `search_document:` for document chunks (RAG)
  - `clustering:` for auto-tagging embeddings (if using dual embeddings)
- For dual-use (RAG + auto-tagging), maintain two embedding sets per document

### Vector Storage: sqlite-vec + FTS5
- Single-file portability prioritized over native hybrid search (LanceDB)
- Brute-force search is adequate for ~100K vectors; scale ceiling ~250K
- Hybrid search implemented via RRF fusion combining sqlite-vec + FTS5 (see `embeddings/retrieval.py`)

### PDF Extraction: Marker + Selective olmOCR
- Marker for primary processing (proven M1 support, ~4s/page)
- olmOCR on remote NVIDIA GPU for scanned historical documents only
- Benchmark claims between tools are contested; Marker is the conservative choice

### Reranking: Document-Aware Cross-Encoder
- **Model**: cross-encoder/ms-marco-MiniLM-L-12-v2 (~50 MB, ~33M params)
- Selected via benchmark against 5 candidates; best balance of NDCG@10 improvement and latency
- **Document-aware grouping**: Prevents single document from monopolizing top results; limits chunks per document before scoring
- **Decorator pattern**: RerankedRetriever wraps any Retriever, broadens candidate pool (default 100 or 3x k), reranks to final k
- **Enabled by default**: `Library.get_retriever(rerank=True)` is the default; CLI `--no-rerank` flag to disable
- **Lazy loading**: Model loaded on first rerank call, not at Library init
- **Sigmoid normalization**: Raw cross-encoder logits mapped to [0, 1] for interpretable scores
- See `docs/benchmarks/2026-03-06-reranker-model-selection.md` for model comparison data

### Citation Tooling: Triage over Automated Verification
- NLI models achieve only ~77-78% accuracy on academic text (vs ~90%+ general)
- Reframe verification as "triage for human review" rather than "automated decision"
- Same infrastructure, lower accuracy bar, immediate utility

### Evaluation Framework
A retrieval evaluation framework is implemented in `tests/eval/`. See `tests/eval/README.md` for full documentation including baseline results and findings.
- **IR metrics**: `retrieval_eval.py` provides Precision@k, Recall@k, MRR, NDCG@k (with graded relevance) and unit tests (`test_retrieval_metrics.py`)
- **Query set**: `test_queries.json` v2.0 contains 76 labeled queries across 6 categories with 3-tier graded relevance (see `annotation_rubric.md`)
- **Comparative harness**: Runs all retriever modes (vector, FTS, hybrid) with/without reranking, per-category breakdowns
- **Baseline results (dev corpus, ~20 docs, post-extraction-fix)**: hybrid+rerank achieves English-only MRR=0.944, Recall@10=0.979, NDCG@10=0.947 on 70 queries; aggregate NDCG@10=0.880 when cross-language queries are folded in. Per-query diagnosis (2026-04-03) showed the aggregate "conceptual query gap" is mostly cross-language contamination, not a structural weakness — English conceptual NDCG@10=0.911. Full results in `baseline_results.json`, analysis in `tests/eval/README.md`
- **Corpus scaled**: Full Zotero corpus (1,216 docs) is now imported. Initial full-corpus eval run shows apparent regression, but this is largely an annotation artifact — the flood of new documents surfaces many correct-but-unannotated results that score as misses. Real corpus-scale performance requires re-annotation before quality targets or conceptual-query work can move forward.
- **Reranker benchmark**: `reranker_benchmark.py` evaluates cross-encoder models; results in `reranker_results.json`
- **Next steps**: Re-annotate existing queries at corpus scale, expand query set, add chunk-level annotations, then reassess quality targets. See `docs/feature-areas/rag-pipeline-improvements/README.md`.

### Extraction Quality Framework
A synthetic extraction quality framework is implemented in `tests/extraction/synthetic/`. It measures how well the Marker + cleanup pipeline preserves content fidelity across document types and degradation levels.
- **Pipeline**: Annotated markdown sources → PDF generation (4 noise tiers) → Marker extraction + cleanup → region alignment → CER/WER scoring + structural validation → aggregated results JSON
- **Noise tiers**: T0 (CLEAN_EMBEDDED, pandoc/pdflatex), T1 (CLEAN_OCR, grayscale image-only), T2 (MODERATE_SCAN, 5 active artifact types), T3 (DEGRADED, 6 active artifact types including occlusion)
- **Noise pipeline**: Config-driven via frozen dataclasses (`TierConfig` composed of per-artifact configs). 7 artifact types implemented: blur, rotation, contrast, Gaussian noise, scanner dust, spatial variation, occlusion. Rotation is disabled in `TIER_CONFIGS` (see known issue below). Fixed application order. Per-page deterministic seeds via `derive_page_seed()` (SHA-256-based, numpy RandomState). `TIER_CONFIGS` dict maps `NoiseTier` to `TierConfig`. Output is grayscale JPEG to match real scanned PDF characteristics.
- **Known issue — surya rotation segfault**: Surya's encoder segfaults on synthetically rotated images. Bilinear resampling crashes at angles ≥~1.5°; nearest-neighbor improves reliability but still crashes for specific angle × document content combinations. Real scanned PDFs with natural physical skew (tested: Tajfel1979, Sewell1996a, Goodwin2011) extract without issue. Rotation artifact is retained in pipeline code but disabled in `TIER_CONFIGS` pending a surya/marker fix.
- **Cache invalidation**: `generation_hash()` combines source content hash + generation parameter hash; parameter changes (range adjustments, new artifacts) automatically invalidate cached PDFs
- **Annotation format**: Source documents use `<!-- @region: name type=<type> -->` / `<!-- @end -->` markers to define expected content regions (paragraph, heading, list, table, math, citation, footnote)
- **Metrics**: Character Error Rate (CER) and Word Error Rate (WER) via rapidfuzz edit distance; structural fidelity validators per region type
- **Alignment**: Fuzzy region matching (`alignment.py`) locates annotated regions in extracted text using variable-length sliding window with rapidfuzz scoring
- **Runner**: `ExtractionQualityRunner` orchestrates the full pipeline with PDF caching, progress tracking, and baseline regression detection
- **Sources**: 6 synthetic academic papers spanning diverse disciplines and document features (see `sources/COVERAGE.md` for feature coverage matrix)
- **Pytest integration**: Tests use `extraction_quality` marker; skipped by default, enabled with `--run-extraction-quality` flag. Requires `pdflatex` installed.
- **Dev dependencies**: rapidfuzz (fuzzy string matching), pymupdf (PDF generation), pypandoc-binary (markdown-to-PDF), numpy, pillow (image-based noise tiers)

### What Would Change These Decisions
- Scale beyond 250K vectors → migrate to LanceDB
- Need native hybrid search → migrate to LanceDB
- Need automated verification workflows → invest in NLI validation (see citation report Section 8.2)

## Design Principles

- Use CSL-JSON for bibliographic metadata (standard, Zotero-compatible)
- Generate citekeys by default for all documents
- Markdown notes with YAML frontmatter for portability and interoperability
- System must function fully without Zotero installed
- Duplicate storage (e.g., PDFs in both systems) is acceptable for independence
- Prioritize easy ingestion: adding a blog post should require only a URL

## Python Tooling

**Always** use uv for package management, ruff for linting, and ty for type checking. Invoke the relevant skill via `astral:uv`, `astral:ruff`, or `astral:ty` when needed.

## Commands

All commands accepting document IDs support both UUID (full or partial) and @citekey identifiers (e.g., `@Smith2023`).

- `uv run local-library add <path>` - Add a PDF to the library (embeds by default; use `--skip-embed` to defer)
- `uv run local-library add <path> --metadata <csl-json-file>` - Add with bibliographic metadata
- `uv run local-library add <path> --llm-extract` - Add with LLM-enhanced PDF extraction (requires GEMINI_API_KEY)
- `uv run local-library list` - List all documents (use `--limit N` for pagination, `--all` for unlimited)
- `uv run local-library list --year 2023` - Filter by publication year
- `uv run local-library list --year-missing` - Show documents with no extractable year
- `uv run local-library list --author-contains Zippel` - Filter authors (case-insensitive substring)
- `uv run local-library list --title-contains methods` - Filter titles (case-insensitive substring)
- `uv run local-library list --citekey-prefix Bourdieu` - Filter citekeys (case-insensitive prefix)
- `uv run local-library show <id>` - Show document details
- `uv run local-library delete <id>` - Delete a document (cascades to embeddings)
- `uv run local-library open <id>` - Open extracted markdown in editor (use `--pdf` for PDF, `--both` for both)
- `uv run local-library update <id>` - Edit document metadata in editor with validation loop
- `uv run local-library review <id>` - Combined open + update workflow for NEEDS_REVIEW documents
- `uv run local-library embed <id>` - Embed a specific document
- `uv run local-library embed --pending` - Embed all PENDING/STALE documents
- `uv run local-library embed --all --force` - Re-embed all READY documents
- `uv run local-library search "<query>"` - Search documents (hybrid mode by default; use `--mode vector` or `--mode fts`)
- `uv run local-library search "<query>" --doc @Author2023` - Search within a specific document
- `uv run local-library search "<query>" --limit 20 --json` - Get more results as JSON
- `uv run local-library search "<query>" --no-rerank` - Search without cross-encoder reranking
- `uv run local-library ask "<question>"` - Ask a question and get a RAG-generated answer (streams by default, reranked by default)
- `uv run local-library ask "<question>" --model anthropic/claude-3-haiku` - Use a specific LLM model
- `uv run local-library ask "<question>" --doc @Author2023` - Scope to a specific document
- `uv run local-library ask "<question>" --json` - Get structured JSON output (implies --no-stream)
- `uv run local-library ask "<question>" --no-stream` - Wait for full answer before displaying
- `uv run local-library ask "<question>" --no-rerank` - Disable cross-encoder reranking
- `uv run local-library zotero import` - Batch import from Zotero (embeds by default; use `--skip-embed` to defer; `--library NAME`, `--collection NAME`, `--dry-run`)
- `uv run local-library zotero collections` - List Zotero collections (personal library by default; use `--library NAME` or `--all-libraries`)
- `uv run local-library zotero libraries` - List available Zotero libraries (personal and group)
- `uv run local-library reextract <id>` - Re-run text extraction on an existing document (useful after extraction pipeline improvements)
- `uv run local-library-mcp` - Start the MCP server (stdio transport, for Claude Code integration)
- `uv run pytest` - Run tests
- `uv run pytest --run-extraction-quality` - Run synthetic extraction quality benchmarks (requires pdflatex)
- `uv run ruff check` - Lint code
- `uv run ruff format` - Format code

## Package Structure

```
src/local_library/
├── __init__.py          # Package root
├── config.py            # XDG-compliant path configuration
├── core/                # Domain: models, storage, orchestration
│   ├── models.py        # Document, EmbeddingStatus, result types (Functional Core)
│   ├── errors.py        # Exception hierarchy with ErrorCode (Functional Core)
│   ├── storage.py       # SQLite CRUD operations, schema v4 (Imperative Shell)
│   ├── library.py       # Library orchestrator (Imperative Shell)
│   └── vec_extension.py # sqlite-vec extension loading and availability checking
├── embeddings/          # Domain: chunking, embedding computation, vector storage, retrieval, reranking
│   ├── base.py          # Chunk, ChunkEmbedding, SearchResult dataclasses; Chunker, Embedder, Retriever, Reranker protocols
│   ├── chunking.py      # MarkdownChunker (section-aware markdown splitting)
│   ├── nomic.py         # NomicEmbedder (nomic-embed-text-v1.5 via sentence-transformers)
│   ├── reranking.py     # CrossEncoderReranker, RerankedRetriever, _group_by_document, _normalize_scores
│   ├── retrieval.py     # VectorRetriever, FTSRetriever, HybridRetriever, _rrf_fuse
│   └── storage.py       # EmbeddingStorage (sqlite-vec CRUD, FTS5 search, status functions)
├── llm/                 # Domain: LLM provider abstraction
│   ├── base.py          # LLMClient protocol (Functional Core)
│   └── litellm_client.py # LiteLLMClient implementation (Imperative Shell)
├── rag/                 # Domain: RAG query pipeline
│   └── interface.py     # RAGInterface, RAGStream, assemble_context, build_messages
├── ingestion/           # Domain: content acquisition and extraction
│   ├── base.py          # Protocols: ContentAcquirer, ContentExtractor
│   ├── file.py          # FileAcquirer implementation
│   ├── pdf.py           # PdfExtractor (Marker wrapper)
│   ├── metadata.py      # MetadataHandler (CSL-JSON validation, citekey generation)
│   ├── text_extraction.py  # TextMetadataExtractor (heuristic + LLM metadata extraction)
│   ├── artifact_cleanup.py # Pre-processing: non-Latin filtering, image reformatting, watermark/boilerplate removal (Functional Core)
│   ├── markdown_cleanup.py # Post-processing: HTML coercion, dehyphenation, paragraph reflow (Functional Core)
│   └── zotero.py        # ZoteroReader facade (database + JSON backends, citekey mapping)
├── mcp/                 # MCP server for Claude Code integration
│   ├── server.py        # FastMCP app, tool definitions, Library lifecycle (Imperative Shell)
│   ├── formatters.py    # Markdown rendering functions (Functional Core)
│   └── CLAUDE.md        # Domain contracts
└── cli/                 # CLI interface (Typer/Rich)
    ├── main.py          # Entry point, command registration
    ├── add.py           # Add command (--skip-embed flag)
    ├── ask.py           # Ask command (RAG queries with streaming, --no-rerank)
    ├── list.py          # List command (pagination with --limit/--all, embed status column)
    ├── show.py          # Show command (@citekey support)
    ├── delete.py        # Delete command (@citekey support)
    ├── embed.py         # Embed command (--pending, --all, --force, --dry-run)
    ├── search.py        # Search command (--limit, --mode, --doc, --json, --no-rerank)
    ├── open.py          # Open command (markdown/PDF viewing)
    ├── update.py        # Update command (editor-based metadata editing)
    ├── review.py        # Review command (combined open + update)
    ├── reextract.py     # Reextract command (re-run extraction on existing documents)
    ├── utils.py         # Shared utilities (identifier resolution, fuzzy matching)
    └── zotero.py        # Zotero commands (import with --skip-embed, collections, libraries)
```

See `src/local_library/core/CLAUDE.md`, `src/local_library/llm/CLAUDE.md`, `src/local_library/rag/CLAUDE.md`, `src/local_library/ingestion/CLAUDE.md`, `src/local_library/embeddings/CLAUDE.md`, `src/local_library/mcp/CLAUDE.md`, and `src/local_library/cli/CLAUDE.md` for domain contracts.

## Background Documentation

### Planning and Roadmap
- `roadmap.md`: **Central overview** — feature areas, current focus, cross-cutting dependencies
- `docs/feature-areas/`: **Feature area planning** — one directory per area with canonical README and supporting material
- `build_plan.md`: Phase 1 milestone overview and layer responsibilities (historical reference once Phase 1 complete)
- `build_philosophy.md`: Pipeline-first, layer-complete development approach
- `docs/design-plans/`: Point-in-time design specifications (date-prefixed)
- `docs/implementation-plans/`: Point-in-time implementation plans (date-prefixed, phased)

### RAG System Research (authoritative for implementation details)
- `RAG_background/00_final_summary_report.md`: Consolidated recommendations — code patterns, schemas, library configuration
- `RAG_background/pdf_extraction_tools_report.md`: Marker, Docling, olmOCR analysis
- `RAG_background/embedding_approaches_report.md`: nomic-embed-text, chunking strategies, dual embeddings
- `RAG_background/vector_storage_report.md`: sqlite-vec vs LanceDB, hybrid search patterns
- `RAG_background/llm_query_interface_report.md`: Custom wrapper architecture, context assembly
- `RAG_background/citation_tooling_report.md`: Suggestion, triage-based verification, Neovim integration

### Project History
- `background/chat_transcript.md`: Full verbatim transcript of initial planning conversation
- `background/chat_summary.md`: Concise summary of architectural decisions and data model
- `RAG_report_guidance.md`: Original requirements and evaluation criteria for RAG research
- `summary_logs/rag_research_process_2.md`: Meta-documentation of research process
- `README.md`: Project goals and development philosophy
