# Development History

Last verified: 2026-05-11

This document records the milestone-by-milestone story of how the project was built — what got built when, what shaped the sequencing, and what we learned along the way. It is the project's process record.

For where things are headed, see [`roadmap.md`](../roadmap.md). For the current architectural shape and contracts, see [`CLAUDE.md`](../CLAUDE.md). For the development methodology applied here, see [`build_philosophy.md`](../build_philosophy.md).

## Pre-development groundwork: RAG research

Before any code was written, and before the design-plan / implementation-plan cadence began, the project ran a substantial research phase into the RAG-system design space. `docs/RAG_background/` collects that research: extraction tools (Marker, Docling, olmOCR), embedding models (nomic-embed-text and alternatives), vector storage (sqlite-vec vs LanceDB), LLM interface architecture, and citation tooling. The consolidated summary (`docs/RAG_background/00_final_summary_report.md`) is the authoritative reference for implementation-level decisions.

This wasn't a methodology applied during development — it was the conceptual groundwork that made the subsequent development legible. Most of the durable design decisions (nomic-embed-text-v1.5 with mandatory prefixes, sqlite-vec for single-file portability, Marker for PDF extraction, RRF for hybrid fusion, triage-over-automated-verification framing for citations) trace back to this phase rather than being made on the fly during Phase 1.

## Methodology in practice

Two patterns shape how development work happens on this project.

**Pipeline-first, layer-complete development** (per `build_philosophy.md`). Milestones extend how far data flows through the pipeline. Each milestone delivers testable end-to-end functionality. When a milestone touches a layer, the layer is built completely (full CRUD, error handling, consistent patterns) — not just the minimum the current milestone needs. The two axes are orthogonal, so most milestones touch multiple layers.

**Design plan → implementation plan → execution.** Non-trivial milestones and features get a design plan at `docs/design-plans/<date>-<topic>.md` (point-in-time spec, with rationale and trade-offs explicit) followed by an implementation plan at `docs/implementation-plans/<date>-<topic>/` (phased execution detail). Plans capture *reasoning*, not just outcomes — they are how decisions persist across sessions and how this project's history stays legible.

## Phase 1: PDF pipeline (M1–M7)

Phase 1 delivered an end-to-end pipeline from PDF ingestion through RAG-grounded answers. Milestone definitions are in `docs/archive/build_plan.md`; this section is the development narrative.

### M1: Record creation and storage

Established the SQLite schema, content-addressable file layout (`ab/cd/hash.md`), and CRUD operations on document records. CLI got `add`, `list`, `show`, `delete`. Decisions from M1 that persist: Typer + Rich for the CLI, transactions for multi-step operations, no partial records on failure (transaction rollback on extraction failure was made explicit later, but the substrate was already there).

### M2: Content acquisition and extraction

PDF files copied to managed storage on add (rather than aliased — independence from source location). Marker integration produced markdown output. Content hashes for duplicate detection. Markdown chosen as the canonical extracted-text format. Marker selected over Docling/olmOCR per the PDF extraction tools report — best balance of Apple Silicon (M-series) support and quality.

### M3a: Metadata validation and citekeys

CSL-JSON validation against the official schema. BetterBibTeX-style citekey generation (deterministic from author/year/title). Indexed field extraction (title, authors, issued_date) for fast queries against the indexed columns rather than the JSON blob.

### M4 (reordered before M3b): Zotero read-only access

M4 was deliberately implemented before M3b. Zotero's existing metadata serves as ground truth for testing text-based metadata extraction in M3b — without it, M3b's quality bar would have been synthetic.

The Zotero reader uses direct SQLite access (Zotero 8+ required) with copy-if-locked handling. Citekeys come from Zotero's native `citationKey` field via the itemData EAV schema (fieldID looked up dynamically). CSL-JSON metadata comes from a Better BibTeX `library.json` export.

Library-scoped citekey resolution (`CitekeyMapper.lookup()` and `has_citekey()` requiring `library_id`) was added later when cross-library collisions surfaced — the same citekey appearing in personal and group libraries had been resolving to the wrong item.

### M3b: Text-based metadata extraction

Heuristic extractors for title (first heading, font-size signals), authors (header/footer parsing), and date from document content. Confidence scoring per field. NEEDS_REVIEW status when extraction confidence is low. Optional LLM fallback via LLMClient injection (LiteLLM-backed) for re-extracting low-confidence fields.

The original M3b done-when criteria included accuracy benchmarks (>80% title, >70% authors, >75% date against Zotero ground truth). **These benchmarks were deferred.** Extraction functionality and the LLM fallback path were fully implemented and covered the cases heuristics struggled with; hitting the benchmark targets wasn't blocking end-to-end pipeline progress. The benchmark requirement remains as a future quality gate if it becomes blocking.

### M5: Embedding pipeline

Section-aware markdown chunking (MarkdownHeaderTextSplitter + RecursiveCharacterTextSplitter, ~512 tokens with ~15% overlap, respect section boundaries). nomic-embed-text-v1.5 via sentence-transformers (768-dim, local inference, no API calls). Task-specific prefixes (`search_query:` and `search_document:`) — these are mandatory for nomic, not optional.

**Schema migration v2 → v3** added the `chunks` table, sqlite-vec vector storage, FTS5 chunk search, and the `embedding_status` column (PENDING / CURRENT / STALE) with automatic transitions on add / re-extract / delete. Cascade deletion on document delete. Graceful degradation when sqlite-vec is unavailable: document storage still works, embedding operations fail clearly.

Two-phase add was introduced here too: `add --skip-embed` defers embedding so batch operations complete first; `embed --pending` catches up later. This becomes important for the Zotero corpus import.

Design at `docs/design-plans/2026-02-03-m5-embedding-pipeline.md`; implementation at `docs/implementation-plans/2026-02-04-m5-embedding-pipeline/`.

### M6: Retrieval

Protocol-based retriever architecture: `Retriever` protocol in `embeddings/base.py` with `VectorRetriever` (cosine over sqlite-vec), `FTSRetriever` (BM25 via FTS5), and `HybridRetriever` (RRF fusion with configurable weights — `rrf_k=60`, equal vector/FTS weighting, 3x candidate multiplier). `Library.get_retriever(mode)` factory wires the dependencies.

CLI `search` command with `--mode` (hybrid/vector/fts), `--doc` scoping, `--limit`, `--json`. Initial evaluation framework: 12 labeled test queries, Precision@k / Recall@k / MRR metrics, comparative harness across all three modes.

**Cross-encoder reranking** was added shortly after M6 as a decorator over the retriever protocol — `RerankedRetriever` wraps any `Retriever`, broadens the candidate pool (default 100 or 3x k), and reranks via `cross-encoder/ms-marco-MiniLM-L-12-v2` with document-aware grouping (limits chunks per document before scoring, prevents single-document monopoly). Sigmoid normalization maps raw logits to [0, 1] for interpretable scores. Selected via benchmark against five candidate models; results in `docs/benchmarks/2026-03-06-reranker-model-selection.md`. Reranking enabled by default (`Library.get_retriever(rerank=True)`); CLI `--no-rerank` opts out.

Design at `docs/design-plans/2026-02-26-m6-retrieval.md`; implementation at `docs/implementation-plans/2026-02-27-m6-retrieval/`.

### M7: RAG query interface

Context assembly from retrieved chunks, prompt construction with source attributions, LiteLLM integration for LLM provider abstraction, response formatting with citations. `RAGInterface` orchestrates the pipeline; `RAGStream` supports streaming with token accumulation. A pre-LLM gate skips the API call when no context is retrieved (rather than asking the model to answer from nothing).

CLI `ask` command with Rich Live display, streaming by default, `--no-stream` / `--json` / `--model` / `--doc` / `--limit` / `--no-rerank` flags.

### Post-M7 quality gate (decision, not a milestone)

A 2026-02-27 decision deferred full Zotero corpus import (~1,200 docs) and evaluation query expansion until after M7 was complete and a systematic evaluation pass could be run. Three reasons:

1. **End-to-end RAG quality is the most informative signal.** M7 reveals which retrieval failures actually matter — a query returning the right document but wrong chunks is invisible to document-level P@k but fatal for answer quality. Evaluation queries written after M7 experience target real failure modes rather than hypothetical ones.
2. **Full import is expensive and effectively one-way.** Re-extracting and re-embedding ~1,200 documents after discovering pipeline issues wastes significant compute. Better to validate on a small set first.
3. **Query expansion against a real corpus is more valuable.** Writing 50–100 queries against documents you've actually read and queried produces better relevance annotations than synthetic coverage.

This decision shaped the Phase 1 → post-Phase-1 transition: M7 finished with a 12-query regression baseline, then post-Phase-1 work expanded the evaluation set and added pipeline improvements before the corpus import.

## Post-Phase-1 work

### Extraction resilience and metadata pipeline (merged `db2cb6b`)

The systematic evaluation pass after M7 surfaced extraction reliability as the practical bottleneck. Some PDFs were timing out under Marker, some were producing garbled output, and FAILED documents were leaving no metadata trace — making them invisible in the library rather than identifiable failures.

Shipped in this wave:
- **pdftext fallback** when Marker fails on text-extractable PDFs. Fallback documents go to NEEDS_REVIEW with `EXTRACTION_FALLBACK` error code but still embed.
- **Dynamic timeout scaling** based on a pre-check (page count + text sampling via pymupdf): text PDFs at 5s/page, image-only at 45s/page, capped at 4h.
- **Progress callback protocol** (precheck_complete, extraction_progress every 30s, extraction_complete, extraction_fallback) — used by `zotero import` for live Rich output.
- **`MetadataSource` provenance enum** (ZOTERO, EXPLICIT, FILENAME, TEXT_EXTRACTED) tracking metadata origin. Preliminary metadata persists *before* extraction, so FAILED documents retain citekey and basic identifying info rather than vanishing.
- **Filename heuristic parser** for academic naming conventions (Author - Year - Title, Author_Year_Title, AuthorYear, etc.) as best-effort metadata pre-extraction.
- **Conditional metadata upgrade rules.** FILENAME-sourced metadata can be upgraded by text extraction; ZOTERO/EXPLICIT metadata is authoritative and never auto-upgraded. Citekey-changing upgrades flag NEEDS_REVIEW rather than auto-applying — referential stability prioritized over speculative improvement.

Schema migration v3 → v4 added the metadata provenance fields.

Design at `docs/design-plans/2026-04-15-extraction-resilience-and-metadata-pipeline.md`.

### MCP server (merged `1e0fefb`)

Four read-only tools (`search_library`, `show_document`, `list_documents`, `get_document_text`) exposed to Claude Code over MCP stdio transport. **The MCP server was deliberately built before the library daemon**, even though the daemon was the longer-running infrastructure investment. The MCP server became the first external client of the Library API, validating the read operation surface (search, show, list, chunk-range access) that the daemon would later expose over a socket. By the time the daemon's protocol was being designed, the API shape had already been confirmed by a real consumer.

Key design decisions:
- **No `ask_library` tool.** The original plan included a RAG-based answer tool, but building it would mean Claude calling a tool that calls another LLM. Instead, `search_library` returns chunks and Claude synthesizes directly. Eliminates latency, avoids context isolation between the inner LLM call and the outer session, keeps the codebase simpler.
- **Markdown-only returns.** No JSON format option. Reduces per-call decision overhead and keeps tool output readable in conversation.
- **No session state.** Each tool call is stateless; "show me more about that third result" is handled by Claude re-issuing a tool call with the right identifier, not by the server tracking conversational context.
- **Two-tier error convention.** `⚠ USER-FACING ERROR:` prefix for infrastructure problems Claude should surface; plain `Error:` for tool-level issues Claude can work around or retry.
- **stdout protocol-only.** All logging goes to stderr. A dedicated audit test (`tests/mcp/test_stdout_discipline.py`) verifies that importing and invoking tools produces zero stdout output. This prevents any accidental `print()` from corrupting the JSON-RPC stream.
- **Chunk-based long-doc access.** Documents above 50 chunks return a preview plus chunk-range fetch instructions, rather than dumping full text. Chunk indices from `search_library` feed directly into `get_document_text`.

Design at `docs/design-plans/2026-04-15-mcp-server.md`; implementation at `docs/implementation-plans/2026-04-15-mcp-server/`.

### Evaluation infrastructure expansion

The 12-query M6 evaluation baseline expanded to a **76-query set with 3-tier graded relevance** across six categories, documented in `tests/eval/test_queries.json` v2.0 with `annotation_rubric.md`. Metrics expanded to NDCG@k with graded relevance (alongside the existing P@k, R@k, MRR). The comparative harness runs all retriever modes (vector, FTS, hybrid) with and without reranking, producing per-category breakdowns.

Dev-corpus baseline (~20 docs, post-extraction-fix): hybrid+rerank achieved English-only MRR=0.944, Recall@10=0.979, NDCG@10=0.947 on 70 queries; aggregate NDCG@10=0.880 with cross-language queries folded in. A 2026-04-03 per-query diagnosis pass showed the aggregate "conceptual query gap" was mostly cross-language contamination, not a structural weakness — English conceptual NDCG@10=0.911.

`reranker_benchmark.py` evaluates cross-encoder candidates; results in `reranker_results.json` informed the model selection documented in `docs/benchmarks/2026-03-06-reranker-model-selection.md`.

### Extraction quality framework

A synthetic extraction quality framework built to measure how well the Marker + cleanup pipeline preserves content fidelity. Lives in `tests/extraction/synthetic/`. Six annotated source documents → PDF generation across four noise tiers (T0 CLEAN_EMBEDDED, T1 CLEAN_OCR, T2 MODERATE_SCAN, T3 DEGRADED) → Marker extraction + cleanup → region alignment → CER/WER scoring + structural validation.

Seven artifact types implemented (blur, rotation, contrast, Gaussian noise, scanner dust, spatial variation, occlusion). Per-page deterministic seeds via SHA-256-based seed derivation. `generation_hash()` combines source content hash + parameter hash for automatic cache invalidation when parameters change.

**Known issue documented here:** Surya (Marker's OCR backend) segfaults on synthetically rotated images. Bilinear resampling crashes at angles ≥~1.5°; nearest-neighbor improves reliability but still crashes for specific angle × content combinations. Real scanned PDFs with natural physical skew extract without issue. Rotation artifact is retained in pipeline code but disabled in `TIER_CONFIGS` pending an upstream fix.

Opt-in via `--run-extraction-quality` pytest flag. Requires `pdflatex` installed.

### Full Zotero corpus import

With extraction resilience, metadata provenance, and evaluation infrastructure in place, the full Zotero corpus (~1,216 documents) was imported. 99.3% successful; 9 extraction timeouts. Retrieval and RAG confirmed functional at scale.

Initial full-corpus eval showed an apparent quality regression that proved to be largely an **annotation artifact** — the flood of new documents surfaced many correct-but-unannotated results that scored as wrong under the existing rubric. Real corpus-scale performance assessment is gated on eval re-annotation work (re-grade existing queries against the full corpus, add new queries, add chunk-level annotations). This is the current active workstream within RAG Pipeline Improvements; see `roadmap.md` for status.

## Recent waves (2026-04 to 2026-05)

### Claude Code plugin (merged `66ac046`)

A repository-bundled Claude Code plugin: six skills + the MCP server config bundled in-repo, installable via `/plugin marketplace add <repo>` then `/plugin install local-library@local-library`. Three-layer skill architecture:

- **Orientation (always-apply):** `using-local-library-mcp` (citekey/library cue → MCP tools), `handling-extraction-quality` (garbled markdown → PDF fallback via `Read`)
- **Kernel:** `grounding-against-library` (atomic per-assertion retrieve → quote → synthesize → report)
- **Procedural composition:** `drafting-with-grounded-sources`, `implementation-check-against-papers`, `verifying-claims-against-library`

Development methodology was distinctive. Rather than the usual design-plan + implementation-plan + execute pattern, the plugin used a **six-phase RED/GREEN/Tier-3 verification cycle**:

1. **Phase 1 (RED baselines):** capture skill-off failure modes for each intended skill — what does Claude do without the skill that the skill is meant to fix?
2. **Phases 2–4 (GREEN / Tier-3):** write each skill, verify it produces the intended behavior against the baselines, harden against rationalization loopholes.
3. **Phase 5:** install-and-permissions audit (does the plugin install correctly, do tools have appropriate authorization?).
4. **Phase 6:** smoke transcripts + Definition-of-Done audit (does the assembled plugin pass realistic test-drive scenarios?).

Artifacts in `tests/skills/`. Design at `docs/design-plans/2026-04-24-local-library-claude-code-plugin.md`; implementation plan at `docs/implementation-plans/2026-04-24-local-library-claude-code-plugin/`.

The plugin's `.mcp.json` migrated to use `${CLAUDE_PLUGIN_ROOT}` so the MCP server runs from the installed plugin's working tree (previously a hardcoded user-specific path). The MCP server itself didn't change — what changed was its packaging and the surrounding skill scaffolding.

### Neovim Citation Workflow: library daemon + Neovim plugin

The headline feature for post-Phase-1 development. Two coupled parts.

**Library daemon** (`src/local_library/daemon/`) — a single-worker asyncio server speaking JSON-RPC 2.0 over a Unix domain socket. Single-worker design preserves sqlite-vec's single-thread access pattern. Methods: `ping`, `search`, `get_document`. Forward-compatible shim for launchd socket activation. CLI: `local-library daemon {start|stop|status|restart|run}`.

The daemon's API surface is direct continuation of what the MCP server validated — same read operations, same identifier resolution patterns, same error conventions. The MCP-first ordering paid off: the daemon's protocol was designed against a confirmed API shape rather than a hypothetical one.

**Neovim plugin** (`nvim/`) — Lua plugin (`local-library.nvim`), installable via lazy.nvim through top-level symlinks (`lua → nvim/lua`, `plugin → nvim/plugin`, `doc → nvim/doc`) at the repo root. Visual-select a claim → `<leader>c` → Telescope picker → insert citekey + auto-append CSL-JSON to project bibliography.

Three-layer module split:
- **Transport** (`client.lua`) — JSON-RPC, reconnect with bounded backoff, per-method timeouts, structured error envelopes
- **Data** (`bibliography.lua`, `selection.lua`, `actions.lua`) — pure-ish, UI-agnostic; no Telescope imports
- **UI** (`telescope/_extensions/local_library.lua`, `conflict_ui.lua`) — the only modules that import Telescope or manipulate scratch buffers

This split makes alternative UIs (a non-Telescope picker, a free-text input mode) reusable without touching the daemon. Per-method timeouts; reconnect-with-backoff; error-code-aware notifications via `notify.from_error`. `:checkhealth local_library` for diagnostics. Bibliography conflict resolution via a scratch-buffer field-level diff.

See `docs/feature-areas/neovim-citation-workflow/README.md` and `docs/concepts/daemons.md` for the full architectural discussion.

## Process learnings

A handful of patterns that worked well, and a few things that pushed back during development.

**M4 reordering** (Zotero access before M3b) was a good call. It gave M3b ground-truth metadata for testing extraction accuracy. The cost was a small phase-shuffle; the payoff was that M3b's quality bar was real rather than synthetic. Ground-truth-first testing is worth the reordering when the data is there.

**Deferring M3b benchmarks** was pragmatic, but in a specific structural way. Original done-when criteria included accuracy targets (>80% title, >70% authors, >75% date). Hitting those would have blocked end-to-end pipeline progress. The deferral was easy to make because alternative paths already covered the practical use case: the LLM fallback handles low-confidence heuristic output, and most documents come from Zotero, which already provides clean ground-truth metadata via the citekey field and Better BibTeX export. The benchmark requirement remains as a future quality gate. The generalizable lesson here isn't a blanket "ship the substrate and defer the bar" — it's that when the cost of deferring a quality bar is low because alternative paths cover the practical use case, deferral is the right move. Without the LLM fallback and the Zotero ground-truth path, the same deferral would have left a real gap.

**Post-M7 quality gate before corpus scaling** was correct. Re-extracting and re-embedding 1,200+ documents after discovering pipeline issues would have wasted significant compute, and the extraction resilience wave found enough real gaps that the deferral was clearly justified. End-to-end RAG quality was the most informative signal because failures at the answer level don't always trace cleanly to retrieval metrics: a chunk can score high on relevance but contain garbled math that's unusable in synthesis, or be split mid-sentence so the retrieved span lacks the context that makes it informative, or be in a language the query isn't (which retrieval may rank reasonably but the LLM can't use). Document-level Precision@k can be perfect while answers are wrong. The systematic post-M7 eval pass surfaced exactly these kinds of problems — extraction timeouts, garbled output, FAILED documents with no metadata trace — and motivated the extraction resilience wave that followed.

**MCP server before daemon** shaped the daemon's protocol well. Rather than designing the daemon's API in the abstract, the MCP server validated which read operations were actually needed and what their error conventions should look like. The daemon's protocol then crystallized against confirmed shape rather than guesses.

**RED/GREEN/Tier-3 for skills** was a new methodology adapted from TDD principles — write the failing case first (skill-off baseline), then write the skill to address it, then iterate against rationalization loopholes (Tier-3 hardening). The methodology is documented in detail in `docs/implementation-plans/2026-04-24-local-library-claude-code-plugin/` for future skill work; the same approach likely applies to other prompt-engineering domains where verifying behavior matters more than verifying code.

**Some surprises along the way:**
- Surya (Marker's OCR backend) segfaults on synthetically rotated images but handles natural physical skew fine. The rotation artifact stays in the extraction-quality framework code but is disabled in `TIER_CONFIGS` pending an upstream fix.
- Surya also segfaults on MPS with specific tensor shapes. The daemon spawns a CPU-fallback worker subprocess to handle these cases.
- The reranker's `no_rerank: bool = False` parameter inverts intuitively — `False` means reranking is ON; `True` disables it. This footgun is documented in `skills/grounding-against-library/references/tool-selection.md`.
- Marker pinned at v1.8.0 because v1.9.0+ introduced a ~20x slowdown on Apple Silicon MPS ([marker issue #960](https://github.com/datalab-to/marker/issues/960)). Upgrade path is documented in `roadmap.md` under *Backlog > Extraction infrastructure*.

For the active project trajectory and what comes next, see [`roadmap.md`](../roadmap.md).
