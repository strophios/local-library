# Roadmap

Last updated: 2026-05-09

This document provides a high-level overview of the project's feature areas and current focus. For detailed planning within each area, see the linked feature area documents. For the development approach, see `build_philosophy.md`.

## Current Focus: Feature Development

The Phase 1 PDF pipeline (M1-M7) is complete. **Full Zotero corpus imported**: 1,216 documents ready (99.3%), 9 failed (extraction timeout). Retrieval and RAG confirmed functional at scale.

Two infrastructure tracks recently wrapped:

- ✓ **Extraction resilience and metadata pipeline** (merged `db2cb6b`) — pdftext fallback when Marker fails, dynamic timeout scaling based on pre-check, progress callback protocol, `MetadataSource` provenance tracking, preliminary metadata persistence before extraction, conditional filename-to-text metadata upgrade with citekey stability checks. See `docs/design-plans/2026-04-15-extraction-resilience-and-metadata-pipeline.md`.
- ✓ **MCP server for Claude Code** (merged `1e0fefb`) — four read-only tools (search_library, show_document, list_documents, get_document_text) over stdio transport. Markdown-only returns, no `ask_library` (Claude synthesizes answers from retrieved chunks directly). See `docs/feature-areas/claude-code-integration/README.md`.

**Still on the polish list:**
1. UI harmonization — consistent extraction status reporting across CLI commands
2. Extraction metadata persistence — schema v4 migration for duration/device/fallback tracking in the DB (the pipeline now produces this metadata, but it isn't persisted yet)

**Recently shipped:**
- ✓ **Local-library Claude Code plugin** (merged `66ac046`) — six skills + MCP config bundled in-repo as a Claude Code plugin. Three-layer architecture: two orientation skills (citekey/library-cue → MCP tools; garbled-extraction → PDF fallback), one atomic grounding kernel (per-assertion retrieve → quote → synthesize → report), three procedural composition skills (drafting-with-grounded-sources, implementation-check-against-papers, verifying-claims-against-library). Installs via `/plugin marketplace add <repo>` then `/plugin install local-library@local-library`. See `docs/feature-areas/claude-code-integration/README.md` and `tests/skills/` for RED/GREEN/Tier-3/smoke verification artifacts.
- ✓ **Neovim Citation Workflow** — daemon (Python/asyncio JSON-RPC over UDS) + Lua plugin with Telescope picker. Visual-select claim → daemon-backed semantic search → citation insertion + bibliography auto-append. Three structural hooks for future features (loud-error / silent-inert / architectural). See `docs/feature-areas/neovim-citation-workflow/README.md` and `docs/concepts/daemons.md` for full rationale.

**Feature development (parallel tracks):**
- Content Ingestion (`add <url>`; later EPUB and external metadata API enrichment)

**Evaluation framework:**
- Corpus-scale baseline was run, but the results show an apparent quality regression that is largely an **annotation artifact**: the flood of new documents surfaces many correct-but-unannotated results that score as wrong under the existing rubric.
- Real next step is re-annotation at scale: re-grade existing queries against the full corpus, add new queries, add chunk-level annotations. Quality target setting and conceptual-query work are gated on having solid eval data at this new scale.
- See `docs/feature-areas/rag-pipeline-improvements/README.md` for details.

---

## Feature Areas

Development beyond Phase 1 is organized into five feature areas. Each area has its own progression from initial exploration through detailed design to implementation. Work is prioritized by current value and what's unblocked, not by a global sequence.

| Area | Status | Priority | Path |
|---|---|---|---|
| [Neovim Citation Workflow](docs/feature-areas/neovim-citation-workflow/README.md) | Stable | Headline | `docs/feature-areas/neovim-citation-workflow/` |
| [Claude Code Integration](docs/feature-areas/claude-code-integration/README.md) | Stable | High | `docs/feature-areas/claude-code-integration/` |
| [Content Ingestion](docs/feature-areas/content-ingestion/README.md) | Exploring | High (good value/effort) | `docs/feature-areas/content-ingestion/` |
| [Note Management](docs/feature-areas/note-management/README.md) | Exploring | Medium | `docs/feature-areas/note-management/` |
| [Automated Content Analysis](docs/feature-areas/automated-content-analysis/README.md) | Exploring | Lower (needs prerequisites) | `docs/feature-areas/automated-content-analysis/` |
| [RAG Pipeline Improvements](docs/feature-areas/rag-pipeline-improvements/README.md) | Partially active | Ongoing (eval re-annotation is next) | `docs/feature-areas/rag-pipeline-improvements/` |

### Status Definitions

- **Exploring**: Brainstorming, gathering requirements, open questions outnumber decisions
- **Designing**: Requirements clear enough to produce design specs
- **Building**: Active implementation underway
- **Stable**: Core functionality delivered; maintenance and incremental improvement

---

## Cross-Cutting Dependencies

```
                    MCP server (validates API surface, in-process Library)
                        │
                        ▼
Neovim Citation Workflow: daemon (extracts shared operations into service)
                            │           │
                            ▼           ▼
                     Neovim plugin   MCP server v2 (swaps to daemon client)

Content Ingestion ──────────────── (independent; web, EPUB, API metadata enrichment)

Note Management ────────────────── (independent; notes link to documents from any source)

Automated Content Analysis: auto-tagging needs manual tags as seed data
                            triage verification builds on citation workflow
```

Key dependencies:
- The **MCP server** is now the first external client of the Library API. It validated the read operation surface (search, show, list, text access) that the daemon will later expose over a socket. Notable design outcome: no `ask_library` tool — Claude synthesizes answers directly from retrieved chunks, avoiding nested LLM calls. Worth preserving in daemon design.
- The **library daemon** is shared infrastructure for latency-sensitive clients (Neovim). The MCP server's API shape and error conventions are direct inputs.
- **Content Ingestion** and **Note Management** are independent tracks that can progress in parallel.

---

## Backlog

Features not currently assigned to a feature area but worth tracking:

- **HTTP API** (FastAPI) — daemon can expose both socket + HTTP; build when external access needed
- **TUI/GUI** — lowest interface priority; CLI + Neovim cover primary workflows
- **Zotero bidirectional note sync** — high complexity; defer until note management is mature
- **Full CSL-JSON spec handling** — accept/preserve all fields; incremental, do when encountered

### Extraction infrastructure

- **Upgrade Marker to v1.9.0+** — pinned at 1.8.0 because v1.9.0+ has a bug causing ~20x slowdown on Apple Silicon MPS ([marker issue #960](https://github.com/datalab-to/marker/issues/960)). Upstream features we're missing: block-mode OCR (v1.9.0), LLM-based table extraction improvements (v1.9.2), new layout detection model and HTML table rendering (v1.10.0). Upgrade steps when the upstream fix lands: change `marker-pdf==1.8.0` → `marker-pdf>=1.10.0` in `pyproject.toml`, `uv sync`, run `uv run pytest --run-extraction-quality`, verify MPS extraction is back to ~4s/page.
- **Selective olmOCR for scanned historical documents** — olmOCR (82.3% on historical math scans vs Marker's lower quality) could handle documents Marker struggles with. Requires 20GB+ VRAM so remote GPU (Lambda Labs, Vast.ai); 20-100x slower than Marker. Workflow: identify problem docs (manual review or quality heuristics), process subset on remote GPU, replace stored markdown. Not urgent; the extraction quality framework in `tests/extraction/synthetic/` can help identify candidates systematically. See `docs/RAG_background/pdf_extraction_tools_report.md` for the full hybrid strategy.

---

## What Would Change Priorities

Certain developments would move items up the priority list:

| Trigger | Feature to prioritize |
|---------|----------------------|
| Hit 250K vector scale ceiling | Migrate to LanceDB (see `docs/RAG_background/vector_storage_report.md`) |
| Metadata quality issues emerge at scale | External API enrichment (CrossRef, GROBID, OpenAlex) in Content Ingestion |
| Need to query web content routinely | Web content ingestion |
| Neovim workflow integration becomes blocking | Library daemon → Full Neovim plugin |
| Want to share library with others | HTTP API, authentication |
| RAG answer quality issues | Expand evaluation framework beyond retrieval to end-to-end answer quality |
| Scanned doc extraction quality poor | Selective olmOCR |
| Automated verification (not just triage) needed | Invest in NLI validation + fine-tuning |
