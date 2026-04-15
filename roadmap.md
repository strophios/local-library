# Roadmap

Last updated: 2026-04-15

This document provides a high-level overview of the project's feature areas and current focus. For detailed planning within each area, see the linked feature area documents. For the development approach, see `build_philosophy.md`.

## Current Focus: Post-Import Polish and Feature Development

The Phase 1 PDF pipeline (M1-M7) is complete. **Full Zotero corpus imported**: 1,216 documents ready (99.3%), 9 failed (extraction timeout). Retrieval and RAG confirmed functional at scale via evaluation suite and manual testing.

**Immediate next steps (infrastructure/polish):**
1. UI harmonization — consistent extraction status reporting across CLI commands
2. Extraction resilience — pdftext fallback, dynamic timeout scaling, progress callback (designed: `docs/design-plans/2026-04-15-extraction-resilience-and-metadata-pipeline.md`)
3. Metadata pipeline reordering — persist preliminary metadata before extraction (same design plan, Phase 2)
4. Extraction metadata persistence — schema v4 migration for duration/device/fallback tracking

**Feature development (parallel tracks):**
- MCP server for Claude Code integration (validates daemon API surface; see below)
- Web Content Ingestion (`add <url>`)
- Neovim Citation Workflow (daemon → plugin)

**Evaluation framework:**
- Baseline eval queries (76) confirmed as annotation-limited at full corpus scale — retrieval is working, but annotations only cover the original 20-doc set
- Annotation expansion deferred until after feature development stabilizes

See `tests/eval/README.md` for baseline results. See `build_plan.md` § "Post-M7: Pipeline Evaluation and Corpus Scaling" for the original rationale.

---

## Feature Areas

Development beyond Phase 1 is organized into five feature areas. Each area has its own progression from initial exploration through detailed design to implementation. Work is prioritized by current value and what's unblocked, not by a global sequence.

| Area | Status | Priority | Path |
|---|---|---|---|
| [Neovim Citation Workflow](docs/feature-areas/neovim-citation-workflow/README.md) | Exploring | Headline | `docs/feature-areas/neovim-citation-workflow/` |
| [Claude Code Integration](docs/feature-areas/claude-code-integration/README.md) | Exploring | High (validates daemon API surface) | `docs/feature-areas/claude-code-integration/` |
| [Web Content Ingestion](docs/feature-areas/web-content-ingestion/README.md) | Exploring | High (good value/effort) | `docs/feature-areas/web-content-ingestion/` |
| [Note Management](docs/feature-areas/note-management/README.md) | Exploring | Medium | `docs/feature-areas/note-management/` |
| [Automated Content Analysis](docs/feature-areas/automated-content-analysis/README.md) | Exploring | Lower (needs prerequisites) | `docs/feature-areas/automated-content-analysis/` |
| [RAG Pipeline Improvements](docs/feature-areas/rag-pipeline-improvements/README.md) | Partially active | Ongoing | `docs/feature-areas/rag-pipeline-improvements/` |

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

Web Content Ingestion ──────────── (independent; extends add <url>)

Note Management ────────────────── (independent; notes link to documents from any source)

Automated Content Analysis: auto-tagging needs manual tags as seed data
                            triage verification builds on citation workflow
```

Key dependencies:
- The **MCP server** is the first external client of the Library API. It validates the operation surface (search, show, ask, list) that the daemon will later expose over a socket. It loads models in-process (acceptable for Claude Code's long-lived sessions).
- The **library daemon** is shared infrastructure for latency-sensitive clients (Neovim). The MCP server informs its API design but doesn't block on it.
- **Web Content Ingestion** and **Note Management** are independent tracks that can progress in parallel.

---

## Backlog

Features not currently assigned to a feature area but worth tracking:

- **MCP server** (Claude Code integration) — promoted to feature area; see table above
- **HTTP API** (FastAPI) — daemon can expose both socket + HTTP; build when external access needed
- **TUI/GUI** — lowest interface priority; CLI + Neovim cover primary workflows
- **Zotero bidirectional note sync** — high complexity; defer until note management is mature
- **Full CSL-JSON spec handling** — accept/preserve all fields; incremental, do when encountered
