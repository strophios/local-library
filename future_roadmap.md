# Future Roadmap

This document tracks features and capabilities deferred from Phase 1 (see `build_plan.md`). Each entry includes context for why it was deferred and what would be needed to implement it.

The goal is to preserve enough information that future work can pick up these features without re-deriving the reasoning.

---

## Content Ingestion Expansion

### Web Content Ingestion

**What:** Ingest web articles, blog posts, and other URL-based content.

**Why deferred:** Orthogonal to PDF pipeline. The existing corpus is PDFs in Zotero; web content doesn't block core RAG functionality.

**Dependencies:** Phase 1 complete (storage, embedding, search infrastructure in place)

**Implementation notes:**
- Primary library: trafilatura (mentioned in CLAUDE.md)
- Alternative: readability-lxml
- Same record flow as PDFs, different content handler
- Metadata from Open Graph tags, or prompt-based extraction

**Design considerations:**
- May want URL normalization and deduplication
- Consider whether to store HTML or just extracted markdown
- Archive.org integration for link rot protection?

---

### EPUB and Other Formats

**What:** Support EPUB, MOBI, HTML files, plain text, etc.

**Why deferred:** Lower priority than PDF and web. Can be added as additional content handlers without architectural changes.

**Dependencies:** Phase 1 complete; polymorphic content handler interface established

**Implementation notes:**
- EPUB: ebooklib or calibre's ebook-convert
- HTML: same as web extraction
- Plain text: trivial (pass-through)

---

### Selective olmOCR for Scanned Documents

**What:** Use olmOCR on remote GPU for scanned historical documents that Marker handles poorly.

**Why deferred:** Requires GPU infrastructure. Marker handles most documents adequately; olmOCR is for edge cases.

**Dependencies:** Phase 1 complete; identification of which documents need re-processing

**Implementation notes:**
- See RAG report Section 1 for detailed hybrid strategy
- olmOCR achieves 82.3% on historical math scans vs Marker's lower quality
- Requires 20GB+ VRAM, so remote GPU (Lambda Labs, Vast.ai, etc.)
- 20-100x slower than Marker; only for selective use

**Workflow:**
1. Process all PDFs with Marker (Phase 1)
2. Identify problematic documents (manual review or quality heuristics)
3. Re-process subset with olmOCR on remote GPU
4. Replace stored markdown

---

## Metadata Enrichment

### External API Metadata Enrichment (M3c)

**What:** Enrich document metadata via external APIs when text-based extraction (M3b) produces uncertain or incomplete results.

**Why deferred:** Text-based extraction should be evaluated first. API enrichment adds network dependencies and complexity that may not be needed if heuristic extraction achieves acceptable accuracy.

**Dependencies:** M3b (text-based metadata extraction) complete and evaluated

**Implementation notes:**
- **CrossRef API**: Lookup by DOI (reliable) or title/author query (fuzzy matching)
- **GROBID**: Structured header extraction from PDFs (more accurate than heuristics but requires running GROBID server)
- **OpenAlex**: Open scholarly metadata, good coverage of recent publications
- See RAG report Section 1 for metadata extraction discussion

**Architecture:**
```
Text extraction (M3b) → confidence score
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   High confidence     Medium confidence    Low confidence
   (use extracted)     (try API enrich)    (require API or manual)
                            │
                            ▼
                    ┌───────────────┐
                    │  API cascade  │
                    │ DOI → CrossRef│
                    │ else → GROBID │
                    │ else → OpenAlex│
                    └───────────────┘
```

**Design considerations:**
- Caching layer to avoid redundant API calls (by content hash or DOI)
- Rate limiting (CrossRef: 50 req/sec polite pool; GROBID: depends on instance)
- Graceful degradation when APIs unavailable
- Confidence thresholds: at what level to auto-accept vs. flag for review?

**Decision point:** Evaluate M3b accuracy on test corpus before implementing. If text-based extraction achieves >85% accuracy across fields, API enrichment may be unnecessary for Phase 1.

---

## Citation Tooling

### Citation Suggestion (CLI + API)

**What:** Given a claim, suggest relevant citations from the library.

**Why deferred:** Enhancement beyond core RAG queries. Same infrastructure, different interface.

**Dependencies:** Phase 1 complete (embeddings and retrieval working)

**Implementation notes:**
- See RAG report Section 5 for full architecture
- Core logic: embed claim → retrieve similar chunks → return ranked citekeys
- Threshold calibration: strict (0.65), default (0.45), broad (0.30)
- CLI: `cite suggest "attention mechanisms improve sequence modeling"`
- API: FastAPI endpoint for programmatic access

---

### Neovim Autocomplete Integration

**What:** Real-time citation suggestions in Neovim triggered by `[@`.

**Why deferred:** Requires daemon architecture and Lua integration. Nice-to-have after core system works.

**Dependencies:** Citation suggestion working; library daemon running

**Note:** This is a component of the full Neovim plugin (see Interface Expansion). Listed here because it's tightly coupled to the citation suggestion capability.

**Implementation notes:**
- See RAG report Section 5 for architecture diagram
- nvim-cmp source (Lua) connecting to library daemon
- Latency budget: ~70-120ms (well under 200ms target)

---

### MCP Server

**What:** Model Context Protocol server for Claude integration.

**Why deferred:** MCP SDK is young with API churn; lower priority than CLI/API.

**Dependencies:** Citation suggestion working; HTTP API in place

**Implementation notes:**
- Same backend as HTTP API
- Expect some maintenance as MCP spec evolves

---

### Triage-Based Verification

**What:** "What in my library might not support this claim?" — surfacing candidates for human review.

**Why deferred:** Same infrastructure as citation suggestion with different ranking. Enhancement layer.

**Dependencies:** Citation suggestion working

**Implementation notes:**
- See RAG report Section 5.4 for the "triage reframing"
- Key insight: 77-78% NLI accuracy insufficient for automated decisions but excellent for search space reduction
- Same infrastructure, different UX and expectations
- Commands:
  ```bash
  cite-triage related "claim text"
  cite-triage contradictions "claim text"
  ```

**The insight worth preserving:** Many "AI features" blocked by accuracy concerns become viable when reframed as human-assistance rather than automation. A 77% accurate ranker that surfaces 10 candidates is useful; a 77% accurate automated verifier is dangerous.

---

## Auto-Tagging

### Automatic Tag Suggestion

**What:** Suggest tags for documents based on content similarity to existing tagged documents.

**Why deferred:** Requires working embeddings and a base of manually-tagged documents.

**Dependencies:** Phase 1 complete; some documents manually tagged

**Implementation notes:**
- Nearest-neighbor tag suggestion: find similar documents, aggregate their tags
- Or LLM classification with existing tag vocabulary as constraints
- See CLAUDE.md for high-level description

---

### Dual Embeddings (RAG + Clustering)

**What:** Maintain separate embedding sets for RAG retrieval and clustering/tagging.

**Why deferred:** Optimization for auto-tagging. Single embedding set sufficient initially.

**Dependencies:** Auto-tagging implemented; measured need for separate embeddings

**Implementation notes:**
- See RAG report Section 2.4 for dual embedding strategy
- nomic-embed-text supports `clustering:` prefix for this purpose
- Storage overhead: ~6KB per document (~185MB for 1,400 docs)
- Only pursue if tagging quality suffers with RAG embeddings

---

## Zotero Integration

### Zotero Export (Push Tags Back)

**What:** Push auto-generated tags from this system back to Zotero.

**Why deferred:** Closes the loop but not needed for querying. Requires careful handling to avoid conflicts.

**Dependencies:** Auto-tagging working; Zotero local API integration

**Implementation notes:**
- See CLAUDE.md for Zotero write strategy
- NEVER write to SQLite directly (corruption risk)
- Use local API (HTTP on port 23119) for tag modifications
- Consider: namespace auto-tags (e.g., prefix with `auto:`) to distinguish from manual

---

### Bidirectional Note Sync

**What:** Sync notes between this system's markdown files and Zotero.

**Why deferred:** Adds significant complexity. Notes managed primarily in external system initially.

**Dependencies:** Note management working; Zotero export working

**Implementation notes:**
- Conflict resolution is the hard part
- Consider: one-way sync (this system → Zotero) to avoid complexity
- Or: treat as separate note stores with manual reconciliation

---

## Note Management

### Markdown Note Generation

**What:** Generate markdown note stubs with YAML frontmatter linking back to document records.

**Why deferred:** Nice-to-have; doesn't block RAG functionality.

**Dependencies:** Phase 1 complete (document records exist)

**Implementation notes:**
- See CLAUDE.md for note format specification
- Frontmatter should include: citekey, UUID, title, authors, date
- Question: where do notes live? `notes/` directory? Adjacent to PDFs?
- Question: auto-generate on import or on-demand?

---

## Interface Expansion

### Library Daemon

**What:** Long-running background process exposing library functionality via Unix socket.

**Why deferred:** CLI sufficient for Phase 1. Daemon enables low-latency integrations (especially Neovim).

**Dependencies:** Phase 1 complete (core library functionality to expose)

**Implementation notes:**
- Unix socket (`/tmp/local-library.sock` or `$XDG_RUNTIME_DIR/local-library.sock`)
- JSON-RPC or simple line-based protocol
- Keeps embedding model warm in memory for fast query embedding
- Handles: RAG queries, citation suggestion, document search, triage operations

**Startup decision:**
- **On-demand** (preferred): First client connection starts daemon; exits after idle timeout
- **Always-running**: Started on login via launchd/systemd
- Heuristic: if cold-start latency <10s, on-demand is simpler and preferred

**Why not just HTTP?**
- Unix socket avoids port management and has lower overhead
- HTTP API still useful for external integrations, web UI, MCP server
- Daemon can expose both: socket for local clients (Neovim, CLI), HTTP for remote/web

---

### Full Neovim Plugin

**What:** Comprehensive Neovim integration for all library functionality.

**Why deferred:** CLI sufficient for Phase 1. Plugin is the primary writing workflow integration.

**Dependencies:** Library daemon; citation suggestion; RAG queries working

**Components:**
- **Commands:** `:LibraryQuery`, `:CiteSuggest`, `:LibrarySearch`, `:LibraryAdd`, etc.
- **Visual mode integration:** Select text → suggest citations for claim
- **Autocomplete:** nvim-cmp source for `[@` trigger (see Citation Tooling)
- **Telescope picker:** Browse library, search documents, insert citations
- **Floating windows:** Display RAG responses, citation details

**Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│                    Neovim Plugin (Lua)                      │
│  • Commands, mappings, UI components                        │
│  • nvim-cmp source                                         │
│  • Telescope extension                                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ Unix socket
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Library Daemon                            │
│  • All core operations                                      │
│  • Embedding model warm in memory                           │
└─────────────────────────────────────────────────────────────┘
```

**Implementation notes:**
- Plugin in pure Lua (no Vimscript)
- Async communication with daemon (don't block editor)
- Consider: lazy-load daemon connection on first use

**Quality-of-life features to consider:**
- Preview citation metadata in floating window
- Jump to PDF/note from citation
- Insert formatted citation (configurable style)
- Status line integration (daemon status, library stats)

---

### HTTP API

**What:** RESTful API for programmatic access to all functionality.

**Why deferred:** CLI sufficient for initial use. API needed for web integrations.

**Dependencies:** Phase 1 complete; ideally shares backend with daemon

**Implementation notes:**
- FastAPI for modern Python API patterns
- Endpoints: document CRUD, search, RAG query, citation suggestion
- Can be served by the library daemon (secondary interface alongside socket)
- Authentication: probably not needed for local-only use

---

### TUI or GUI

**What:** Terminal UI or graphical interface for browsing and managing the library.

**Why deferred:** CLI sufficient for initial use. Higher effort than other interfaces.

**Dependencies:** Phase 1 complete; HTTP API or daemon

**Implementation notes:**
- TUI: textual (Python) or similar
- GUI: web-based (Streamlit, Gradio) probably easier than native

---

## Quality and Validation

### Evaluation Framework

**What:** Systematic evaluation of retrieval and RAG quality.

**Why deferred:** Needed before production use, but Phase 1 can proceed with manual evaluation.

**Dependencies:** Phase 1 complete (something to evaluate)

**Implementation notes:**
- See RAG report Section 7 "Pending: Evaluation Framework"
- See `RAG_background/v1_backport_content.md` for starter content
- Elements needed:
  - Stratified test query set (50-100 queries)
  - Quality targets: Precision@5 ≥60%, MRR ≥0.5, "I don't know" accuracy ≥80%
  - Latency targets per operation
  - Evaluation code for automated measurement

---

### Full Automated Verification

**What:** Automated NLI-based verification of whether sources support claims.

**Why deferred:** NLI accuracy on academic text (~77-78%) insufficient for automated decisions. Triage approach more practical.

**Dependencies:** Triage-based verification working; validation showing accuracy is acceptable

**Implementation notes:**
- See RAG report Section 5 and citation_tooling_report.md Section 8.2
- Would need: build test set (50-100 labeled pairs), validate accuracy, potentially fine-tune
- 2-4 weeks to validate with significant risk of "not good enough"
- Only pursue if automated workflows required ("reject commits with unsupported citations")

---

## What Would Change Priorities

Certain developments would move items up the priority list:

| Trigger | Feature to Prioritize |
|---------|----------------------|
| Hit 250K vector scale ceiling | Migrate to LanceDB (see RAG report Section 3) |
| Need to query web content | Web content ingestion |
| Neovim workflow integration | Library daemon → Full Neovim plugin (including citation autocomplete) |
| Want to share with others | HTTP API, authentication |
| Quality concerns emerge | Evaluation framework |
| Scanned docs quality poor | Selective olmOCR |
| Need Claude integration | MCP server |
