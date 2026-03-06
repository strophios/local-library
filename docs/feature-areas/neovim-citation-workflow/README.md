# Neovim Citation Workflow

Last updated: 2026-03-06

## Vision

The primary interface for using the library in everyday academic writing. Select text in Neovim, search the library for relevant sources, and insert citations — all without leaving the editor, with sub-second response times.

This is the headline feature for post-Phase-1 development. The library's value scales with how frictionlessly it integrates into the writing workflow, and for this project, writing happens in Neovim.

## Current State

The backend infrastructure exists: hybrid search (vector + FTS + RRF fusion), RAG query interface, and the retriever protocol. These are accessible via the CLI (`search`, `ask`), but CLI cold-start latency (~5-10s for model loading) makes it unsuitable for interactive editor use.

No daemon, no Neovim plugin, no socket/API interface exists yet.

## Near-Term (next to build)

### Library Daemon

The performance prerequisite. A long-running process that keeps the embedding model warm in memory, exposing library operations over a Unix socket.

**Key design decisions to make:**
- Protocol: JSON-RPC vs. line-based vs. msgpack-rpc (Neovim itself uses msgpack-rpc)
- Operations to expose: at minimum search, RAG query, document lookup
- Model lifecycle: lazy-load on first query? Pre-load at startup?
- Startup model: on-demand (first client connection starts it) vs. always-running (launchd)
- Idle timeout: shut down after N minutes of inactivity?
- Error handling: what happens when the daemon crashes mid-query?

**Notes:**
- If cold-start latency is <2s, on-demand startup might be acceptable
- Daemon should account for future consumers (HTTP API, MCP server) even if only Unix socket is built initially
- The embedding model (~500MB) is the main memory cost; the cross-encoder (if implemented) adds another ~100-300MB

### Neovim Plugin

A Lua plugin communicating with the daemon. The core interaction:

1. User selects text in visual mode
2. Keyboard shortcut sends selected text to the daemon as a search query
3. Daemon returns ranked results (score, citekey, title, chunk text, document ID)
4. Plugin displays results in a floating window:
   - Left pane: one line per result (score, citekey, truncated title), navigable
   - Right pane: full text of the currently selected chunk
5. User actions on a selected result:
   - **Confirm**: insert citekey at cursor position (and add to `.bib` file if present?)
   - **Confirm with text**: insert citekey + chunk text (after newline)
   - **Open source**: open the extracted markdown document (ideally scrolled to the chunk's location)
   - **Cancel**: close the window, nothing happens

**Open questions:**
- Separate repo or part of the local-library monorepo?
- Does this integrate with Telescope, or is it a standalone floating window?
- How to handle the `.bib` file interaction (detect presence, add entry, avoid duplicates)?
- What additional context should the plugin send with the query? (buffer filename, project context, etc.)
- Should there be a mode that passes the full open document as LLM context for query improvement?

## Longer-Term Ideas

### Citation Search Refinements
- **LLM-augmented query rewriting**: Before searching, use an LLM to expand or refine the query (especially useful when the selected text is a claim rather than a keyword query)
- **Bibliography-aware search**: Pass a `.bib` file and preferentially search those documents, or use titles/abstracts from the bibliography as additional query context
- **Tag-aware search**: Use document tags (when auto-tagging exists) to weight or filter results

### Triage-Based Verification Modes
- "What in my library might not support this claim?" — surface potentially contradicting sources
- "Does the cited source(s) plausibly support this claim?" — with citekey(s) selected, check relevance
- These lower the confidence bar from "automated decision" to "narrowing the search space for human review"
- See `RAG_background/citation_tooling_report.md` § triage reframing for the underlying insight

### Additional Plugin Features
- Open associated note (when note management exists)
- Preview citation metadata in floating window
- Insert formatted citation (configurable CSL style)
- Status line integration (daemon status, library stats)
- Floating window for direct `search` or `ask` queries (type a query instead of selecting text)
- Document-level search (scope results to a specific document or set of documents)

## Dependencies

**Provides to other areas:**
- The daemon is shared infrastructure for any external client (HTTP API, MCP server, TUI)

**Needs from other areas:**
- Full corpus import (Phase 1 quality gate) — citation search is only useful with a populated library
- RAG Pipeline Improvements — search quality directly affects citation relevance
- Note Management — "open associated note" feature depends on notes existing

## References

- `project_breakdown.md` — detailed interaction design notes (especially the Neovim plugin UX)
- `future_roadmap.md` § "Citation Tooling", "Interface Expansion" — original feature descriptions
- `RAG_background/citation_tooling_report.md` — citation suggestion architecture, triage reframing
- `RAG_background/llm_query_interface_report.md` — LLM integration patterns
