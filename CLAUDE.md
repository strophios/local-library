# CLAUDE.md

Last verified: 2026-05-10

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a personal knowledge management system that ingests diverse digital documents (PDFs today, web articles and other formats in progress), extracts content, manages bibliographic metadata, embeds and indexes the corpus, and serves it for both ad-hoc retrieval and natural-language RAG queries. The system is self-sufficient but designed for read-only interoperability with Zotero.

The same shared core is exposed through three user-facing interfaces:

- **CLI** (Typer/Rich) — primary surface for ingest, batch operations, search, and ad-hoc queries
- **Claude Code plugin** — bundled MCP server (four read-only tools) plus six skills for grounded retrieval, drafting, and verification
- **Neovim plugin** — Lua plugin backed by a long-running Python daemon for sub-second claim-driven citation search

The boundary between "shared core" and "interface" is real but mobile — the daemon is currently Neovim-specific but is the planned substrate for MCP server v2 (see `## System Architecture`).

For current focus, recently shipped work, and feature-area sequencing, see `roadmap.md` — it is the central overview of what's being worked on and where things are headed, and is generally the right first stop before starting development work.

## Working Conventions

- **`scratchpad.md`** is the user's personal scratch notes. **Ignore it by default** — do not read, reference, or include it in any response unless the user explicitly asks. It is not part of project context.

## System Architecture

### Two-axis model: pipeline and layers

The system is organized along two orthogonal axes.

**Pipeline** (vertical) — the path data takes from ingestion to queryable knowledge:

```
Ingest → Extract text → Validate metadata → Store → Embed → Retrieve → Generate answer
```

**Layers** (horizontal) — five architectural concerns that cut across the pipeline:

1. **Storage** — SQLite (schema v4), content-addressable file layout, sqlite-vec, FTS5
2. **Ingestion** — content acquisition, extraction (Marker + pdftext fallback), metadata handling
3. **Embeddings + Retrieval** — chunking, nomic-embed-text, vector/FTS/hybrid search, cross-encoder reranking
4. **LLM + RAG** — LLMClient protocol, LiteLLM provider abstraction, context assembly, prompt construction, answer generation
5. **Interface** — CLI (Typer + Rich), MCP server (FastMCP, stdio), library daemon (asyncio, UDS, JSON-RPC), Neovim plugin (Lua)

Development follows a **pipeline-first, layer-complete** approach documented in `build_philosophy.md`: build along the pipeline for rapid feedback on the end-to-end experience; implement each architectural layer completely when touched. Pipeline stages and architectural layers are orthogonal — most stages touch multiple layers.

### Shared core, multiple interfaces

The CLI, MCP server, and library daemon are all clients of the same `Library` API in `src/local_library/core/library.py`. The MCP server was built first as a real consumer to validate the API surface; the daemon's protocol was designed against the surface the MCP server validated; the daemon is now the planned substrate for MCP server v2 (in-process `Library()` swaps to a socket client without changing tool contracts).

Each interface targets a distinct workflow with different latency tolerances:

- **CLI** — ingest, batch operations, exploration. Latency-tolerant; spins up cold.
- **Claude Code plugin** — research and writing happen in Claude sessions; the library is a first-class tool there with skills handling grounded retrieval, drafting, and verification.
- **Neovim plugin** — sub-second citation insertion latency requires the daemon's warm-model pool.

The split is partly historical (the CLI was the cheapest harness for the API) and partly workflow-driven (batch ingest belongs on the CLI even if it could live elsewhere). The "shared core" / "interface" boundary is mobile: the daemon currently lives interface-side because only the Neovim plugin uses it, but a daemon-backed MCP server v2 would migrate it inward toward shared infrastructure. New work can extend an existing interface, add a new one, or grow the shared core — and the third sometimes absorbs distinctions the first two were maintaining.

### Self-sufficient with Zotero interoperability

The system functions completely independently of Zotero but reads from a Zotero database when one is present. Zotero is treated as a peer/data source, not as a substrate the system extends.

- **System owns:** web content ingestion, text extraction, embeddings, RAG, auto-tagging, markdown notes
- **Zotero owns:** academic PDF collection via browser connector, citation metadata, reference manager UX

Operational details (database access, citekey resolution, write strategy) are in `## Zotero Interoperability` below.

### Why not a Zotero plugin?

ML features (embeddings, RAG, auto-tagging, reranking) require Python infrastructure that cannot run in Zotero's JavaScript plugin environment. Once external Python infrastructure is necessary, the architecture cleaves naturally: that system owns everything beyond Zotero's strengths, and Zotero stays in its lane.

## Core Data Model

Each document record contains:

- **Identity**: UUID, citekey (BetterBibTeX-style), optional Zotero item key, DOI/URL/ISBN
- **Bibliographic metadata**: CSL-JSON blob (Zotero-compatible, citation-processor-ready) plus indexed fields
- **Metadata provenance**: `MetadataSource` enum (ZOTERO, EXPLICIT, FILENAME, TEXT_EXTRACTED) tracks origin; enables conditional upgrade rules and citekey-stability checks
- **Content**: Path to original file, extracted plain text, content hash
- **Embeddings**: Vector embeddings for full doc or chunks (sqlite-vec, successor to deprecated sqlite-vss); status tracking (PENDING / CURRENT / STALE)
- **Tags**: Manual and auto-generated with source flag; confidence scores for auto-tags (planned)
- **Notes**: Path to markdown file with YAML frontmatter linking back to record (planned)

## Zotero Interoperability

### Reading from Zotero
- Direct SQLite access to `zotero.sqlite` for read operations (Zotero 8+ required)
- Citation keys read from Zotero's native `citationKey` field via itemData EAV schema (fieldID looked up dynamically from `fields` table)
- **Library-scoped citekey resolution**: `CitekeyMapper.lookup()` and `has_citekey()` require `library_id` to prevent cross-library collisions (e.g., same citekey in personal and group libraries resolving to wrong item)
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

## Current State

### Pipeline capabilities

End-to-end pipeline from PDF ingest through RAG query is functional. Full Zotero corpus imported (1,216 documents, 99.3% successful; 9 extraction timeouts).

**Ingest and extract:**
- Add PDFs from local files (`local-library add`) or batch-import from Zotero (`local-library zotero import`); embed-on-add by default (`--skip-embed` to defer)
- Extract text via Marker with quality validation, markdown cleanup (HTML coercion, dehyphenation, paragraph reflow)
- Pre-check PDFs (page count + text sampling via pymupdf) and scale extraction timeouts dynamically (text PDFs 5s/page, image-only 45s/page, capped at 4h)
- Fall back to pdftext when Marker fails — fallback documents go to NEEDS_REVIEW with `EXTRACTION_FALLBACK` error code but still embed
- Surface per-document progress via callback protocol (precheck_complete, extraction_progress every 30s, extraction_complete, extraction_fallback) — used by `zotero import` for live Rich output

**Validate and track metadata:**
- Validate explicit CSL-JSON metadata against schema; generate BetterBibTeX-style citekeys
- Extract metadata from PDF text (title, authors, date, document type) with confidence scoring; flag NEEDS_REVIEW for low-confidence
- Optionally re-extract low-confidence fields via LLM (LiteLLMClient injection; `--llm-extract` requires `GEMINI_API_KEY` for default config)
- Track metadata provenance via `MetadataSource` enum; preliminary metadata persists before extraction so FAILED documents retain citekey and basic metadata
- Heuristic filename parser produces best-effort CSL-JSON for academic naming conventions (Author - Year - Title, Author_Year_Title, AuthorYear, etc.)
- Conditional FILENAME → text upgrades; ZOTERO/EXPLICIT metadata is authoritative and never upgraded; citekey-changing upgrades flag NEEDS_REVIEW rather than auto-applying

**Embed and search:**
- Section-aware markdown chunking (~512 tokens, ~15% overlap)
- nomic-embed-text-v1.5 (768-dim, local) via sentence-transformers, with task-specific prefixes (`search_query:` for queries, `search_document:` for chunks)
- Embedding status tracking: PENDING → CURRENT on embed, CURRENT → STALE on re-extraction, cascade deletion on document delete
- Search via VectorRetriever (cosine), FTSRetriever (BM25 via FTS5), HybridRetriever (RRF fusion); all wrappable by RerankedRetriever (decorator pattern, broadens candidate pool then reranks)
- Cross-encoder reranking via ms-marco-MiniLM-L-12-v2 with document-aware grouping; enabled by default (`Library.get_retriever(rerank=True)`)
- Manual review and re-extraction (`review`, `reextract` commands)
- Retrieval evaluation framework (76-query set, 3-tier graded relevance, IR metrics: P@k, R@k, MRR, NDCG@k)

**RAG:**
- LLMClient protocol with LiteLLMClient implementation (provider-agnostic; works with Claude, GPT, local models via LiteLLM)
- RAGInterface orchestrates context assembly + prompt construction + LLM generation; pre-LLM gate skips API call when no context retrieved
- Streaming (RAGStream) and blocking modes; CLI `ask` command with Rich Live display

**Storage:**
- SQLite schema v4 with content-addressable file layout (`ab/cd/hash.md`)
- sqlite-vec for vectors, FTS5 for text; library degrades gracefully without sqlite-vec for document storage
- Schema v4 includes embedding_status and metadata provenance fields

### Interface surfaces

**CLI** (`src/local_library/cli/`): full surface for the pipeline above, plus Zotero import, daemon lifecycle, daemon-backed search and ask. Identifier resolution accepts UUIDs (full or partial) and `@citekey` with fuzzy matching. Pagination via `--limit/--all`. Filtering on list via `--year`, `--year-missing`, `--author-contains`, `--title-contains`, `--citekey-prefix`. See `## Commands` for the full list.

**MCP server** (`src/local_library/mcp/`): FastMCP-based, stdio transport. Four read-only tools (`search_library`, `show_document`, `list_documents`, `get_document_text`) with markdown-only returns and identifier resolution by UUID or `@citekey`. Stateless; chunk-based long-doc access (full text below 50 chunks; preview + chunk-range fetching above). Two-tier error convention: `⚠ USER-FACING ERROR:` prefix for infrastructure problems, plain `Error:` for tool-level issues. stdout is protocol-only (logging to stderr; `tests/mcp/test_stdout_discipline.py` enforces).

**Claude Code plugin** (`.claude-plugin/`, `skills/`, `.mcp.json`): bundles MCP server config + six skills in three layers.

- *Orientation* (always-apply): `using-local-library-mcp` (citekey/library cue → MCP tools), `handling-extraction-quality` (garbled markdown → PDF fallback via `Read`)
- *Kernel*: `grounding-against-library` (atomic per-assertion retrieve → quote → synthesize → report; returns control on broad inputs)
- *Procedural composition*: `drafting-with-grounded-sources`, `implementation-check-against-papers`, `verifying-claims-against-library`

Installs via `/plugin marketplace add <repo>` then `/plugin install local-library@local-library`. The plugin's `.mcp.json` uses `${CLAUDE_PLUGIN_ROOT}` so the MCP server runs from the installed plugin's working tree. See `skills/README.md` for user-facing install docs and test-drive scenarios; `tests/skills/` for RED/GREEN/Tier-3/smoke verification artifacts.

**Library daemon** (`src/local_library/daemon/`): wraps the Library orchestrator behind a Unix-domain-socket JSON-RPC 2.0 server. Single-worker executor preserves sqlite-vec single-thread access. Methods: `ping`, `search`, `get_document`. Forward-compatible shim for launchd socket activation. CLI: `local-library daemon {start|stop|status|restart|run}`. See `src/local_library/daemon/CLAUDE.md` for protocol details and gotchas (signal handling during warmup, asyncio.Event-based readiness, etc.).

**Neovim plugin** (`nvim/`): Lua plugin (`local-library.nvim`), lazy.nvim-installable via top-level symlinks (`lua → nvim/lua` etc.). Visual-select claim → `<leader>c` → Telescope picker → insert citekey + auto-append CSL-JSON to project bibliography. Per-method timeouts, reconnect-with-backoff, error-code-aware notifications via `notify.from_error`. `:LocalLibraryDaemon` for daemon process management; `:checkhealth local_library` diagnostics. Bibliography conflict resolution via scratch-buffer field-level diff. See `nvim/CLAUDE.md` for the layer split (transport / data / UI), invariants, and Neovim/plenary gotchas.

### Recent changes and current focus

See `roadmap.md` for current focus and feature-area sequencing. Current state in brief:

- **Recently shipped:** Claude Code plugin (six skills + MCP config), Neovim plugin + library daemon, extraction resilience pipeline (pdftext fallback, dynamic timeouts), metadata provenance tracking
- **Active:** eval set re-annotation at corpus scale — apparent regression on full-corpus eval is largely an annotation artifact (many correct-but-unannotated results scoring as wrong). Quality target setting and conceptual-query work are gated on solid eval data at the new scale
- **Polish list:** UI harmonization (consistent extraction status reporting across CLI), schema migration for extraction-metadata persistence (`extraction_duration`, `extraction_device`, fallback flags — pipeline produces this metadata; not yet persisted)

For milestone-by-milestone narrative and project history, see `docs/development-history.md`.

## RAG System Design Deciszions

Comprehensive research on the RAG pipeline is documented in `docs/RAG_background/`. The final summary (`00_final_summary_report.md`) is the authoritative reference. Key decisions:

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
- pdftext as fallback when Marker fails on text-extractable PDFs
- olmOCR on remote NVIDIA GPU for scanned historical documents only (deferred)
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

## Key Libraries and Tools

- **Web extraction:** trafilatura (planned), readability-lxml (planned)
- **PDF extraction:** Marker (primary), pdftext (fallback), pymupdf (pre-check), olmOCR (planned for scanned historical documents on remote GPU)
- **Embeddings:** nomic-embed-text-v1.5 (local, 768 dims, 8192 context) via sentence-transformers
- **Reranking:** cross-encoder/ms-marco-MiniLM-L-12-v2 via sentence-transformers CrossEncoder
- **Metadata:** CrossRef API (planned), GROBID (planned for academic PDFs), Open Graph tags (planned for web)
- **Vector storage:** sqlite-vec (v0.1.6+), SQLite FTS5 for hybrid search
- **LLM interface:** Custom RAGInterface + LiteLLM for provider abstraction
- **MCP server:** FastMCP (mcp>=1.27.0) for Claude Code tool integration over stdio
- **Library daemon:** Python stdlib asyncio + JSON-RPC 2.0 over Unix domain socket
- **Neovim plugin:** Lua, plenary.async (callback → sync), Telescope (UI), `vim.fn.sockconnect` (UDS transport)
- **Citations:** citeproc-py against CSL-JSON (planned)
- **CLI:** Typer + Rich
- **Package management:** uv

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
- `uv run local-library daemon start` - Start the library daemon (UDS, JSON-RPC; used by the Neovim plugin)
- `uv run local-library daemon stop` - Stop the running daemon
- `uv run local-library daemon status` - Check whether the daemon is running and reachable
- `uv run local-library daemon restart` - Restart the daemon
- `uv run local-library daemon run` - Run the daemon in the foreground (for debugging or socket-activation harnesses)
- `uv run local-library-mcp` - Start the MCP server (stdio transport, for Claude Code integration)
- `uv run pytest` - Run tests
- `uv run pytest --run-extraction-quality` - Run synthetic extraction quality benchmarks (requires pdflatex)
- `uv run ruff check` - Lint code
- `uv run ruff format` - Format code

## Package Structure

```
local-library/
├── src/local_library/    # Python package: pipeline + CLI + MCP server + daemon
│   ├── __init__.py
│   ├── config.py         # XDG-compliant path configuration
│   ├── core/             # Library API, storage, models, error hierarchy
│   ├── ingestion/        # PDF extraction, metadata, Zotero import
│   ├── embeddings/       # Chunking, embedding, retrieval, reranking
│   ├── llm/              # LLMClient protocol, LiteLLM backend
│   ├── rag/              # RAGInterface (context assembly, generation, streaming)
│   ├── cli/              # Typer/Rich CLI commands
│   ├── mcp/              # FastMCP server (stdio); see mcp/CLAUDE.md
│   └── daemon/           # Long-running daemon (UDS, JSON-RPC); see daemon/CLAUDE.md
├── nvim/                 # Neovim plugin (Lua); has its own README and CLAUDE.md
│   ├── lua/              # Plugin code (transport / data / UI layer split)
│   ├── plugin/           # Auto-loaded user commands + keymap
│   ├── doc/              # Vimdoc (`:help local-library`)
│   ├── tests/            # plenary-based test suite
│   └── scripts/          # `run-tests.sh` etc.
├── skills/               # Claude Code plugin skills (six SKILL.md files); has its own README
│   ├── using-local-library-mcp/
│   ├── handling-extraction-quality/
│   ├── grounding-against-library/
│   ├── drafting-with-grounded-sources/
│   ├── implementation-check-against-papers/
│   └── verifying-claims-against-library/
├── .claude-plugin/       # Plugin manifest + marketplace entry
│   ├── plugin.json
│   └── marketplace.json
├── .mcp.json             # MCP server config (uses ${CLAUDE_PLUGIN_ROOT})
├── docs/                 # Design plans, implementation plans, RAG research, feature-area planning
└── tests/                # Unit, integration, eval, extraction-quality, skill verification
```

Top-level symlinks at the repo root (`lua → nvim/lua`, `plugin → nvim/plugin`, `doc → nvim/doc`) make the Neovim plugin installable by any plugin manager that follows standard runtimepath conventions, without a `subdir` workaround.

### Domain CLAUDE.md files

Each Python subpackage and the Neovim plugin have their own CLAUDE.md documenting contracts:

- `src/local_library/core/CLAUDE.md` — Library facade, storage, models
- `src/local_library/ingestion/CLAUDE.md` — Acquirer/Extractor protocols, metadata pipeline
- `src/local_library/embeddings/CLAUDE.md` — Chunker/Embedder/Retriever/Reranker protocols
- `src/local_library/llm/CLAUDE.md` — LLMClient protocol contracts
- `src/local_library/rag/CLAUDE.md` — RAGInterface, streaming
- `src/local_library/cli/CLAUDE.md` — CLI conventions
- `src/local_library/mcp/CLAUDE.md` — MCP tool contracts and conventions
- `src/local_library/daemon/CLAUDE.md` — Daemon protocol, warmup gotchas, signal handling
- `nvim/CLAUDE.md` — Neovim plugin layer split (transport / data / UI), invariants, gotchas

## Background Documentation

### Planning and Roadmap
- `roadmap.md`: **Central overview** — feature areas, current focus, cross-cutting dependencies
- `docs/feature-areas/`: **Feature area planning** — one directory per area with canonical README and supporting material
- `build_philosophy.md`: Pipeline-first, layer-complete development approach
- `docs/concepts/daemons.md`: Architectural discussion of the daemon, layer split, and shared-infrastructure rationale
- `docs/design-plans/`: Point-in-time design specifications (date-prefixed)
- `docs/implementation-plans/`: Point-in-time implementation plans (date-prefixed, phased)

### RAG System Research (authoritative for implementation details)
- `docs/RAG_background/00_final_summary_report.md`: Consolidated recommendations — code patterns, schemas, library configuration
- `docs/RAG_background/pdf_extraction_tools_report.md`: Marker, Docling, olmOCR analysis
- `docs/RAG_background/embedding_approaches_report.md`: nomic-embed-text, chunking strategies, dual embeddings
- `docs/RAG_background/vector_storage_report.md`: sqlite-vec vs LanceDB, hybrid search patterns
- `docs/RAG_background/llm_query_interface_report.md`: Custom wrapper architecture, context assembly
- `docs/RAG_background/citation_tooling_report.md`: Suggestion, triage-based verification, Neovim integration

### Project History
- `docs/development-history.md`: Milestone-by-milestone narrative, project history, and development-process record
- `docs/archive/build_plan.md`: Phase 1 milestone overview and layer responsibilities (historical reference; Phase 1 complete)
- `docs/archive/background/chat_transcript.md`: Full verbatim transcript of initial planning conversation
- `docs/archive/background/chat_summary.md`: Concise summary of architectural decisions and data model
- `docs/archive/RAG_report_guidance.md`: Original requirements and evaluation criteria for RAG research
- `docs/archive/summary_logs/rag_research_process_2.md`: Meta-documentation of research process
- `README.md`: Project goals, interfaces, and architectural orientation
