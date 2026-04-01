# Roadmap

Last updated: 2026-04-01

This document provides a high-level overview of the project's feature areas and current focus. For detailed planning within each area, see the linked feature area documents. For the development approach, see `build_philosophy.md`.

## Current Focus: Evaluation Quality Gate

The Phase 1 PDF pipeline (M1-M7) is functionally complete. The **evaluation and quality gate** is in progress, gating the full Zotero corpus import (~1400 documents).

**Progress:**
1. ✓ Expanded evaluation query set to 76 queries with graded relevance (3-tier)
2. ✓ Ran baseline: hybrid+rerank achieves MRR=0.913, NDCG@10=0.896 on ~20-doc dev corpus
3. ✓ Initial improvement cycle: FTS stop-word/OR-mode fix, RRF weight tuning, cross-encoder reranking
4. **Next**: Establish quality targets, investigate conceptual query gap (NDCG@10=0.784), determine next pipeline improvement
5. Import full Zotero corpus when quality targets are met
6. Re-evaluate with full corpus

See `tests/eval/README.md` for detailed baseline results and findings. See `build_plan.md` § "Post-M7: Pipeline Evaluation and Corpus Scaling" for the full rationale.

---

## Feature Areas

Development beyond Phase 1 is organized into five feature areas. Each area has its own progression from initial exploration through detailed design to implementation. Work is prioritized by current value and what's unblocked, not by a global sequence.

| Area | Status | Priority | Path |
|---|---|---|---|
| [Neovim Citation Workflow](docs/feature-areas/neovim-citation-workflow/README.md) | Exploring | Headline | `docs/feature-areas/neovim-citation-workflow/` |
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
RAG Pipeline Improvements ──────► (quality gate) ──────► Full corpus import
                                                              │
                                                              ▼
Neovim Citation Workflow: daemon ► plugin ──────────► (needs full corpus to be useful)
                            │
Web Content Ingestion ──────┤ (independent, but daemon can serve web content too)
                            │
Note Management ────────────┘ (independent; notes link to documents from any source)

Automated Content Analysis: auto-tagging needs manual tags as seed data
                            triage verification builds on citation workflow
```

Key dependency: The **library daemon** is shared infrastructure. It's the performance prerequisite for Neovim integration and the natural service layer for any external client. It belongs to the Neovim Citation Workflow area because that's the primary motivator, but its design should account for other consumers.

---

## Backlog

Features not currently assigned to a feature area but worth tracking:

- **MCP server** (Claude integration) — depends on daemon; low urgency until needed
- **HTTP API** (FastAPI) — daemon can expose both socket + HTTP; build when external access needed
- **TUI/GUI** — lowest interface priority; CLI + Neovim cover primary workflows
- **Zotero bidirectional note sync** — high complexity; defer until note management is mature
- **Full CSL-JSON spec handling** — accept/preserve all fields; incremental, do when encountered
