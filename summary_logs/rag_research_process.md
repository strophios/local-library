# RAG System Research Process Summary

**Date**: 2026-01-08
**Purpose**: Document the multi-agent research process used to produce the RAG implementation reports

---

## Overview

This research effort investigated how to build a RAG (Retrieval-Augmented Generation) system for academic knowledge management. The process used a structured multi-agent approach to gather, analyze, and critically review information across five technical domains.

## Constraints Given

- ~1400 Zotero items (academic PDFs)
- M1 Pro MacBook (2021)
- Python or Rust implementation
- Local-first with Zotero interoperability
- Portability and transparency prioritized

## Research Process

### Phase 1: Research Agent Dispatch

Five research agents were dispatched in parallel, each investigating one component:

| Agent | Topic | Key Questions |
|-------|-------|---------------|
| 1 | PDF to Markdown | Best extraction tools, performance on M1, handling of academic layouts |
| 2 | Embeddings & Chunking | Model selection (local vs. API), chunking strategies for academic text |
| 3 | Vector Storage | Database options at 50k-500k scale, hybrid search, filtering |
| 4 | LLM Querying | RAG pipeline architecture, conversation handling, prompting |
| 5 | Citation Tooling | Suggestion, verification, editor integration, API design |

Each agent produced an initial report with recommendations, code examples, and implementation checklists.

### Phase 2: Critical Review

Five critical reviewer agents were dispatched to evaluate each report:

| Reviewer | Report Reviewed | Key Criticisms |
|----------|-----------------|----------------|
| 1 | PDF to Markdown | Marker output is "human-readable" not "RAG-optimized"; validation process needed |
| 2 | Embeddings | MTEB scores may vary by task; query prefixes critical for BGE |
| 3 | Vector Storage | Memory claims need clarification; sqlite-vss with HNSW can scale further |
| 4 | LLM Querying | Conversation context severely underdeveloped in initial report |
| 5 | Citation Tooling | NLI trained on crowdsourced data may not transfer to academic text; latency targets optimistic |

### Phase 3: Report Revision

Reports were revised to incorporate critical feedback:

- Added caveats where claims were overconfident
- Clarified performance numbers with uncertainty ranges
- Included validation recommendations
- Added edge case handling

### Phase 4: Gap Analysis

Cross-report gaps identified:

1. **End-to-end integration architecture** - How components connect wasn't clearly specified
2. **Bootstrap strategy** - Migrating 1400 existing documents needed attention
3. **Evaluation methodology** - How to measure "good enough" quality
4. **Embedding model lock-in** - Switching models requires complete re-embedding
5. **Backup strategy** - Critical for personal knowledge system

These gaps were addressed in the final summary report.

### Phase 5: Final Summary

A final summary report was written consolidating:

- Two implementation paths (Phased Build vs. Maximum Quality)
- Critical caveats (embedding lock-in, Zotero access, backup strategy)
- Integration architecture diagrams
- Bootstrap strategy with failure rate estimates
- Evaluation framework with quality targets
- Comprehensive risk assessment

### Phase 6: Final Review and Revision

The summary was critically reviewed, identifying issues:

- Original "three paths" structure was confusing (Path 1 and Path 3 were really one phased approach)
- Llama model version was incorrect (3.2:8b doesn't exist)
- Missing critical caveats (embedding lock-in, backup strategy)
- sqlite-vss vs LanceDB decision was deferred when it should be resolved

Summary was revised to address all critical feedback.

---

## Deliverables

### Reports Written

| File | Purpose |
|------|---------|
| `RAG_background/00_final_summary.md` | Executive summary with recommendations |
| `RAG_background/01_pdf_to_markdown.md` | PDF extraction tools analysis |
| `RAG_background/02_embeddings_and_chunking.md` | Embedding models and chunking strategies |
| `RAG_background/03_vector_storage.md` | Vector database comparison |
| `RAG_background/04_llm_querying.md` | RAG pipeline architecture |
| `RAG_background/05_citation_tooling.md` | Citation workflow tools |

### Key Recommendations

**Recommended path**: Phased Build (Path A) in 4-6 weeks

- Phase 1: Marker + all-mpnet + Chroma (prototype)
- Phase 2: BGE-large + sqlite-vss + custom chunker (production quality)
- Phase 3: Citation CLI + Neovim + Claude Haiku (integration)

**Key tools selected**:
- PDF extraction: Marker (with PyMuPDF fallback)
- Embeddings: BGE-large-en-v1.5 (with query prefixes)
- Vector store: sqlite-vss (single-file simplicity)
- LLM: Ollama for development, Claude Haiku for production queries

---

## Process Observations

### What Worked Well

1. **Parallel research agents** - Covered five topics simultaneously, reducing total time
2. **Critical reviewers** - Caught overconfident claims, missing caveats, and unrealistic estimates
3. **Structured iteration** - Research → Review → Revise → Summarize → Review again produced higher quality output
4. **Gap analysis** - Cross-cutting concerns emerged from reviewing all reports together

### What Could Be Improved

1. **Web search limitations** - Subagents couldn't access web search, limiting ability to verify current pricing/versions
2. **Review depth trade-off** - More thorough reviews would catch more issues but take more time
3. **User feedback loop** - Would benefit from user review between phases to validate direction

### Lessons Learned

1. **Initial estimates are optimistic** - Critical review consistently extended timeline estimates (e.g., "6-8 weeks" → "10-14 weeks" for Path B)
2. **Lock-in effects are under-discussed** - Embedding model choice has long-term consequences that weren't initially surfaced
3. **"Three paths" framing was artificial** - Real decision was between phased approach vs. maximum quality from day one

---

## Time Investment

| Phase | Estimated Time |
|-------|----------------|
| Research agent dispatch + completion | ~15-20 min |
| Critical review dispatch + completion | ~10-15 min |
| Report revision | ~20-30 min |
| Gap analysis | ~5 min |
| Final summary writing | ~15 min |
| Final review + revision | ~15-20 min |
| Process documentation | ~10 min |
| **Total** | **~90-120 min** |

---

## Next Steps

The reports provide a foundation for implementation. Recommended next actions:

1. Read `00_final_summary.md` for the recommended approach
2. Set up backup strategy before processing documents
3. Start with Phase 1 prototype (Marker + all-mpnet + Chroma)
4. Process 50-100 sample documents to validate extraction quality
5. Build evaluation test set (50-100 queries)
6. Iterate based on observed quality
