# Neovim Citation Workflow

Last updated: 2026-05-08

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
- **Confidence-based result filtering**: Earlier thinking sketched threshold tiers (strict ~0.65, default ~0.45, broad ~0.30) for citation suggestion. The specific numbers are tentative and may not survive once we measure against real use. Worth keeping as a starting point if/when we need to expose "more/fewer results" knobs to the user.

### Daemon Startup Restructure: Parallel Serve + Warmup

The daemon currently runs startup serially: bind socket → run warmup on the
executor (loop parked on `run_until_complete`) → start `_serve`. That serial
shape produces four related warts that we've patched around rather than
fixed:

1. **SIGTERM-during-warmup is parked.** Signal handlers fire on the loop
   thread, but the loop is awaiting the executor task during warmup, so
   `daemon stop` issued in the warmup window hits the CLI's 10s timeout.
   Documented as a gotcha in `src/local_library/daemon/CLAUDE.md`.
2. **Ping is unavailable during init.** The asyncio server isn't accepting
   connections yet, so external monitoring tools and future consumers
   (MCP-style health checks, `daemon status --probe`, etc.) can't
   distinguish "process up but warming" from "process up and serving"
   via the daemon's own protocol.
3. **Connection queueing is opaque.** Connections arriving during warmup
   sit in the kernel accept backlog with no daemon-level visibility. The
   client experiences this as a long latency rather than an explicit
   "warming up" state — fine for the current plugin's 60s timeout, but
   problematic for any client that wants to fail-fast or render state.
4. **Test escape-hatch sprawl.** `LOCAL_LIBRARY_DAEMON_SKIP_WARMUP=1` is
   currently set in four test files (two Lua, two Python) because the
   warmup wait corrupts any timing-based assertion. Easy to forget;
   future tests will hit the same surprising failure.

**Resolution shape:** restructure to run `_serve` and warmup concurrently,
gated by an `asyncio.Event`:

```python
warmup_done = asyncio.Event()
server_task = asyncio.create_task(_serve(listening, stop_event, warmup_done))
warmup_task = asyncio.create_task(_run_warmup(warmup_done))
```

Then:
- `ping` responds immediately (real concurrency from t=0).
- `search` / `get_document` handlers `await warmup_done.wait()` before
  proceeding. Requests during warmup naturally wait without queueing in
  the kernel.
- Signal handlers fire on the now-running loop, so SIGTERM works during
  warmup.
- Test fixtures poll ping until success — actual readiness, no env-var
  escape hatch needed.

**Open design questions** to settle before implementing:
- What should `search` do for requests arriving during warmup — wait on
  the event (current proposal), or fail fast with a `WARMING_UP` error
  code so clients can render explicit state?
- What should `daemon start` (CLI) do — return at bind (current behavior)
  or block until warmup is done? Probably wants a `--wait-ready` flag.
- Should ping report a warmup-state field (`ready: bool`, `warmed: bool`)
  so external probes can distinguish liveness from readiness without
  separate methods?
- How should warmup *failure* surface to in-flight clients? Currently a
  warmup crash kills the daemon at startup. With async serving, we'd
  need to decide: still crash, or surface `WARMUP_FAILED` and continue
  serving non-search methods?

This isn't urgent — current behavior is correct, just suboptimal. Worth
revisiting if/when we add additional daemon clients (MCP v2, HTTP API)
that benefit from real readiness signaling, or if the test escape-hatch
sprawl gets worse.

### Triage-Based Verification Modes
- "What in my library might not support this claim?" — surface potentially contradicting sources
- "Does the cited source(s) plausibly support this claim?" — with citekey(s) selected, check relevance
- These lower the confidence bar from "automated decision" to "narrowing the search space for human review"
- See `docs/RAG_background/citation_tooling_report.md` § triage reframing for the underlying insight

### Additional Plugin Features
- Open associated note (when note management exists)
- Preview citation metadata in floating window
- Insert formatted citation (configurable CSL style)
- Status line integration (daemon status, library stats)
- Floating window for direct `search` or `ask` queries (type a query instead of selecting text)
- Document-level search (scope results to a specific document or set of documents)
- **Placeholder-picker search feedback** — open the Telescope picker immediately
  on `<leader>c` with a "Searching…" placeholder entry, then refresh in place
  via `picker:refresh(new_finder)` once results arrive. Improvement over the
  current single `vim.notify` (commit `e15d841`): keeps feedback colocated
  with the eventual UI rather than flashing in the cmdline. Open design
  questions: how to plumb the picker handle back to the async continuation,
  cancellation sentinel for `<Esc>` during load, and whether to close on
  empty-result vs. show a "no results" placeholder. Not blocking; revisit
  once we have real-use signal on whether the notify is sufficient.

## Previously considered

### nvim-cmp autocomplete source on `[@` trigger

Early sketches included a nvim-cmp source that triggered on `[@` to surface citation candidates inline as the user typed. Latency budget would have been ~70-120ms (feasible with a warm daemon). Dropped because the interaction model doesn't match the actual writing workflow: citations are usually inserted based on a claim or passage, not a half-typed citekey. The visual-mode selection workflow above is a better fit. Leaving this note as a pointer in case something brings it back into scope.

## Dependencies

**Provides to other areas:**
- The daemon is shared infrastructure for any external client (HTTP API, MCP server, TUI)

**Needs from other areas:**
- Full corpus import (Phase 1 quality gate) — citation search is only useful with a populated library
- RAG Pipeline Improvements — search quality directly affects citation relevance
- Note Management — "open associated note" feature depends on notes existing

## References

- `docs/RAG_background/citation_tooling_report.md` — citation suggestion architecture, triage reframing
- `docs/RAG_background/llm_query_interface_report.md` — LLM integration patterns
