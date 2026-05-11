# Neovim Citation Workflow

Last updated: 2026-05-11

## Vision

The primary interface for using the library in everyday academic writing. Select text in Neovim, search the library for relevant sources, and insert citations — all without leaving the editor, with sub-second response times.

This is the headline feature for post-Phase-1 development. The library's value scales with how frictionlessly it integrates into the writing workflow, and for this project, writing happens in Neovim.

## Current State

**Shipped and stable.** Both the library daemon and the Neovim plugin are built and in routine use. End-to-end flow: visual-select a claim → `<leader>c` → Telescope picker shows ranked chunks from the daemon → pick one to insert citekey at cursor + auto-append CSL-JSON to project bibliography.

### Library daemon

`src/local_library/daemon/` — a long-running Python process that keeps the embedding model and reranker warm in memory and exposes library operations over a Unix domain socket via JSON-RPC 2.0. Single-worker executor preserves sqlite-vec's single-thread access. Methods: `ping`, `search`, `get_document`. Forward-compatible shim for launchd socket activation. CLI: `local-library daemon {start|stop|status|restart|run}`.

The daemon's API surface continues from what the MCP server validated: same read operations, same identifier resolution patterns (UUID or `@citekey`), same error conventions. This MCP-first ordering paid off — the daemon's protocol crystallized against a confirmed API shape rather than guesses.

Key decisions made during the build:
- **Protocol: line-delimited JSON-RPC 2.0 over UDS.** Not msgpack-rpc (despite Neovim's native support) because line-delimited JSON is human-debuggable and easy to extend with new fields. Not HTTP yet because UDS is local-only — no port management, no TLS to worry about.
- **No `ask` / RAG-query method.** Same rationale as the MCP server's missing `ask_library`: nested LLM calls add latency and isolate context. The daemon returns chunks; the client synthesizes if synthesis is needed.
- **Single-worker executor.** sqlite-vec requires single-thread access; an asyncio loop with a single-worker thread pool gives concurrent method dispatch without violating sqlite-vec's threading model.
- **Warmup at daemon startup, not on first query.** Cold-start latency would have been too disruptive for the sub-second interactive target. Warmup is currently serial with `_serve` startup — see *Near-Term* below.
- **No idle timeout.** The daemon stays up until explicitly stopped. Idle timeout would have added complexity (graceful shutdown, request-mid-shutdown handling) without clear benefit at single-user scale.

Implementation contracts and gotchas (signal handling during warmup, asyncio.Event-based readiness, channel handling) are in `src/local_library/daemon/CLAUDE.md`. Full architectural discussion in `docs/concepts/daemons.md`.

### Neovim plugin

`nvim/` — Lua plugin (`local-library.nvim`), lazy.nvim-installable via top-level symlinks (`lua → nvim/lua`, `plugin → nvim/plugin`, `doc → nvim/doc`) at the repo root.

Three-layer module split:
- **Transport** (`client.lua`) — JSON-RPC, reconnect with bounded backoff, per-method timeouts, structured error envelopes
- **Data** (`bibliography.lua`, `selection.lua`, `actions.lua`) — pure-ish, UI-agnostic; no Telescope imports
- **UI** (`telescope/_extensions/local_library.lua`, `conflict_ui.lua`) — the only modules that import Telescope or manipulate scratch buffers

This split makes alternative UIs (a non-Telescope picker, a free-text input mode) reusable without touching the daemon protocol or the data layer.

Key decisions made during the build:
- **Telescope picker over standalone floating window.** Telescope is the standard Neovim picker — users already have it for fzf-style file navigation. Reusing it lowers cognitive friction and avoids reinventing keymap conventions.
- **Bibliography auto-append from frontmatter.** Buffer frontmatter (`bibliography: refs.json`) is parsed and CSL-JSON is appended automatically on citekey insertion. Scratch-buffer field-level diff handles conflict cases (existing entry present with different metadata).
- **Plugin lives in the local-library monorepo**, not a separate repo. Top-level symlinks expose the standard Neovim runtimepath structure, so any plugin manager that follows the conventions can install it. Avoids version-drift between Python package and Lua plugin.
- **API forward-compat hooks.** The plugin always passes `boost_citekeys` (silent-inert hook: parameter accepted by the daemon but currently ignored — reserved for future bibliography-aware ranking). `doc_id` non-null surfaces a "scoping not yet available" notification (loud-error hook — reserved for future document-scoped search).

Interface contracts and Neovim/plenary gotchas are in `nvim/CLAUDE.md`. End-user docs and configuration reference in `nvim/README.md`.

### What this means downstream

The daemon is now shared infrastructure for latency-sensitive clients. The Neovim plugin is the first consumer; the MCP server is the planned second (v2 swap from in-process `Library()` to daemon socket client, preserving tool contracts). The daemon's API shape and error conventions are already validated — future clients (HTTP API, additional editors) plug in without re-deriving the surface.

## Near-Term

### Daemon startup restructure: parallel serve + warmup

The daemon currently runs startup serially: bind socket → run warmup on the executor (loop parked on `run_until_complete`) → start `_serve`. That serial shape produces four related warts that we've patched around rather than fixed:

1. **SIGTERM-during-warmup is parked.** Signal handlers fire on the loop thread, but the loop is awaiting the executor task during warmup, so `daemon stop` issued in the warmup window hits the CLI's 10s timeout. Documented as a gotcha in `src/local_library/daemon/CLAUDE.md`.
2. **Ping is unavailable during init.** The asyncio server isn't accepting connections yet, so external monitoring tools and future consumers (MCP-style health checks, `daemon status --probe`, etc.) can't distinguish "process up but warming" from "process up and serving" via the daemon's own protocol.
3. **Connection queueing is opaque.** Connections arriving during warmup sit in the kernel accept backlog with no daemon-level visibility. The client experiences this as long latency rather than an explicit "warming up" state — fine for the current plugin's 60s timeout, but problematic for any client that wants to fail-fast or render state.
4. **Test escape-hatch sprawl.** `LOCAL_LIBRARY_DAEMON_SKIP_WARMUP=1` is currently set in four test files (two Lua, two Python) because the warmup wait corrupts any timing-based assertion. Easy to forget; future tests will hit the same surprising failure.

**Resolution shape:** restructure to run `_serve` and warmup concurrently, gated by an `asyncio.Event`:

```python
warmup_done = asyncio.Event()
server_task = asyncio.create_task(_serve(listening, stop_event, warmup_done))
warmup_task = asyncio.create_task(_run_warmup(warmup_done))
```

Then:
- `ping` responds immediately (real concurrency from t=0).
- `search` / `get_document` handlers `await warmup_done.wait()` before proceeding. Requests during warmup naturally wait without queueing in the kernel.
- Signal handlers fire on the now-running loop, so SIGTERM works during warmup.
- Test fixtures poll ping until success — actual readiness, no env-var escape hatch needed.

**Open design questions** to settle before implementing:
- What should `search` do for requests arriving during warmup — wait on the event (current proposal), or fail fast with a `WARMING_UP` error code so clients can render explicit state?
- What should `daemon start` (CLI) do — return at bind (current behavior) or block until warmup is done? Probably wants a `--wait-ready` flag.
- Should ping report a warmup-state field (`ready: bool`, `warmed: bool`) so external probes can distinguish liveness from readiness without separate methods?
- How should warmup *failure* surface to in-flight clients? Currently a warmup crash kills the daemon at startup. With async serving, we'd need to decide: still crash, or surface `WARMUP_FAILED` and continue serving non-search methods?

Not urgent — current behavior is correct, just suboptimal. Becomes more pressing if/when additional daemon clients (MCP v2, HTTP API) want real readiness signaling, or if the test escape-hatch sprawl gets worse.

### Placeholder-picker search feedback

Open the Telescope picker immediately on `<leader>c` with a "Searching…" placeholder entry, then refresh in place via `picker:refresh(new_finder)` once results arrive. Improvement over the current single `vim.notify` (commit `e15d841`): keeps feedback colocated with the eventual UI rather than flashing in the cmdline.

Open design questions: how to plumb the picker handle back to the async continuation, cancellation sentinel for `<Esc>` during load, and whether to close on empty-result vs. show a "no results" placeholder. Not blocking; revisit once we have real-use signal on whether the notify is sufficient.

## Longer-Term Ideas

### Citation search refinements
- **LLM-augmented query rewriting**: Before searching, use an LLM to expand or refine the query (especially useful when the selected text is a claim rather than a keyword query)
- **Bibliography-aware search**: Pass a `.bib` / `refs.json` file and preferentially search those documents, or use titles/abstracts from the bibliography as additional query context — this is what the `boost_citekeys` silent-inert hook is reserved for
- **Tag-aware search**: Use document tags (when auto-tagging exists) to weight or filter results
- **Confidence-based result filtering**: Earlier thinking sketched threshold tiers (strict ~0.65, default ~0.45, broad ~0.30) for citation suggestion. The specific numbers are tentative and may not survive once we measure against real use. Worth keeping as a starting point if/when we need to expose "more/fewer results" knobs to the user.

### Triage-based verification modes
- "What in my library might not support this claim?" — surface potentially contradicting sources
- "Does the cited source(s) plausibly support this claim?" — with citekey(s) selected, check relevance
- These lower the confidence bar from "automated decision" to "narrowing the search space for human review"
- See `docs/RAG_background/citation_tooling_report.md` § triage reframing for the underlying insight

### Additional plugin features
- Open associated note (when note management exists)
- Preview citation metadata in floating window
- Insert formatted citation (configurable CSL style)
- Status line integration (daemon status, library stats)
- Floating window for direct `search` or `ask` queries (type a query instead of selecting text)
- Document-level search (scope results to a specific document or set of documents) — this is what the `doc_id` loud-error hook is reserved for

## Previously considered

### nvim-cmp autocomplete source on `[@` trigger

Early sketches included a nvim-cmp source that triggered on `[@` to surface citation candidates inline as the user typed. Latency budget would have been ~70-120ms (feasible with a warm daemon). Dropped because the interaction model doesn't match the actual writing workflow: citations are usually inserted based on a claim or passage, not a half-typed citekey. The visual-mode selection workflow above is a better fit. Leaving this note as a pointer in case something brings it back into scope.

## Dependencies

**Provides to other areas:**
- The daemon is now shared infrastructure for any latency-sensitive client (HTTP API, MCP server v2, TUI). The MCP-server-v2 daemon-client swap is the next planned consumer.

**Met prerequisites:**
- Full corpus import (Phase 1 quality gate) — done; citation search now operates against the full ~1,216-document corpus
- RAG Pipeline Improvements — partial; cross-encoder reranking is the dominant quality contributor at the chunk level, but eval re-annotation at corpus scale is in progress before further retrieval tuning

**Still needs from other areas:**
- Note Management — the "open associated note" plugin feature depends on notes existing

## References

- `nvim/README.md` — end-user install, configuration, keymap reference
- `nvim/CLAUDE.md` — Neovim plugin domain contracts and gotchas
- `src/local_library/daemon/CLAUDE.md` — daemon protocol details and warmup gotchas
- `docs/concepts/daemons.md` — full architectural discussion (rationale, layer split, shared-infrastructure framing)
- `docs/RAG_background/citation_tooling_report.md` — citation suggestion architecture, triage reframing
- `docs/RAG_background/llm_query_interface_report.md` — LLM integration patterns
