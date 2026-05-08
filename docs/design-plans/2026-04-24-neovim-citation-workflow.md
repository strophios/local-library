# Neovim Citation Workflow Design

<!-- Status: Design completed 2026-04-24. Seven implementation phases. Ready for `writing-plans` skill to produce a detailed implementation plan. -->

## Summary

This design builds a long-running Python daemon and a companion Neovim plugin that together enable claim-driven semantic search against the local-library corpus, integrated directly into a writing workflow. The daemon wraps the existing `Library` orchestrator — unchanged — behind a Unix-socket JSON-RPC 2.0 server, keeping the embedding model and SQLite connection warm in memory for sub-500 ms search latency once loaded. The Neovim plugin is structured with an explicitly separable data layer (transport, bibliography file I/O, buffer actions) and a UI layer (initial implementation: a Telescope picker extension), so that future alternate UIs can reuse the data layer without touching the daemon.

The architectural commitments are shaped by three interlocking constraints: the sqlite-vec library requires single-threaded access, the embedding and reranking models are CPU/GPU-bound, and the plugin must remain responsive across multiple actions. The design resolves this by running model inference in `asyncio`'s executor thread pool while keeping all database operations on the event-loop thread — a discipline that is new to this codebase and explicitly documented as a pattern. Three hook mechanisms with different failure semantics scaffold future features (document-scoped search, bibliography-biased ranking, direct text input) without requiring coordinated changes on both sides of the socket boundary when they eventually ship. The entire cycle carries a deliberate didactic posture: a companion concepts document on daemons, IPC, and RPC is written in lockstep with the seven implementation phases, so the teaching is grounded in the actual design decisions rather than reconstructed afterward.

## Definition of Done

By the end of this design cycle we will have produced:

1. **Design document** at `docs/design-plans/2026-04-24-neovim-citation-workflow.md` specifying the daemon (process model, protocol, operations, lifecycle, error handling) and the Neovim plugin (UX, data layer, UI layer), with discrete implementation phases.
2. **Concepts document** at `docs/concepts/daemons.md` (or similar) — a standalone teaching reference on daemons, IPC, and the reasoning behind this project's choices. Cross-referenced from the design doc. Reflects the user's explicit choice for a *deep* didactic bent to this cycle.
3. The design is specific enough that an implementation plan can be written from it without re-litigating MVP scope.

### Scope boundaries for the MVP (as targeted by the design)

**In scope (MVP — shipped at the end of the eventual implementation cycle):**

- **Long-running library daemon**: Unix-socket IPC, embedding model warm in memory, exposes at minimum semantic search + document metadata read (+ whatever else the plugin actions need).
- **Neovim Lua plugin** with separable data layer / UI layer; initial UI is a Telescope extension. Hybrid form-factor chosen as a *soft commitment*: conditional on UI/data separation not bloating the MVP. If during brainstorming that cost is found to be high, fall back to a plain Telescope extension and defer the abstraction to later.
- **Core interaction flow**: visual-select claim → keybind → Telescope picker with chunk preview pane → one of four actions:
  - Insert citekey at cursor
  - Insert citekey + chunk text (under the line)
  - Open source document (extracted markdown)
  - Cancel
- **Auto-append CSL-JSON entry** to the project bibliography. File location resolved via YAML `bibliography:` frontmatter (pandoc/quarto convention). On citekey conflict: present a field-level diff and let the user decide (warn-on-conflict).
- **Complementary positioning** relative to existing `<leader>z` (telescope-zotero.nvim): distinct keybind, distinct intent — this plugin is for *claim-driven semantic search*; `<leader>z` remains for *author/title lookup*.

**Hooks only (scaffolded in the design, implemented in later cycles):**

- Document-scope search (scope results to a single citekey).
- Bib-aware preferential search (bias ranking toward entries already present in the refs file).
- Direct input mode (type a free-text query instead of visual-selecting).

**Out of scope for this design cycle (not designed, not hooked):**

- Triage verification modes ("what in my library might contradict this claim?" / "does the cited source plausibly support this claim?").
- Context-aware snippet-style insertion (automatic full-citation-syntax insertion based on surrounding context, continuation-of-citation-list mode, etc.).
- Tag-aware search (depends on the Automated Content Analysis feature area, which does not yet exist).
- Daemon as host for the MCP server v2 (acknowledged future direction in `roadmap.md`; not actively designed this cycle).
- **Daemon Marker integration** — *planned non-inclusion*. The Neovim plugin is read-only and will never need Marker. The MCP server *might* eventually need Marker if import/add tools are added there, at which point the daemon would grow Marker-aware capability. For this cycle, the daemon is not designed to host Marker, but the architecture should not structurally foreclose adding it later.

## Architecture

### High-level shape

The design produces three artifacts:

1. A Python daemon (`local-library-daemon`) — a long-running asyncio Unix-socket server speaking JSON-RPC 2.0, wrapping the existing `Library` orchestrator class as a read-only access service.
2. A Neovim Lua plugin at `nvim/` in the local-library repo — separable data layer (RPC client, bibliography file I/O, pure actions) and UI layer (initial implementation is a Telescope extension). Hybrid UI/data split is committed; brainstorming verified separation cost is near-zero (the split just means "don't mix RPC calls into Telescope entry-makers").
3. A standalone concepts document at `docs/concepts/daemons.md` — eight chapters written in lockstep with implementation phases, exemplifying daemon / IPC / RPC / concurrency concepts through this project's specific decisions.

*Conceptual background: see [docs/concepts/daemons.md](../concepts/daemons.md) chapters 1–2 (what a daemon is; service management).*

### Daemon architecture

```
┌─────────────────────────────────────────────────────────────┐
│ local-library-daemon (Python, asyncio, single event loop)   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ JSON-RPC 2.0 server                                     │ │
│ │  - line-delimited compact JSON framing                  │ │
│ │  - request dispatcher                                   │ │
│ │  - LocalLibraryError → JSON-RPC error envelope          │ │
│ └──────────────────────────┬──────────────────────────────┘ │
│ ┌──────────────────────────▼──────────────────────────────┐ │
│ │ Library singleton (existing class, reused as-is)        │ │
│ │  - lazy-loaded embedder, reranker, retriever            │ │
│ │  - sqlite-vec connection (single-threaded)              │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ loop.run_in_executor for blocking model inference       │ │
│ │  (embedder and reranker run in executor; sqlite-vec     │ │
│ │  stays on the event-loop thread — single-thread         │ │
│ │  discipline preserved, not bypassed)                    │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         ▲
         │ Unix domain socket, line-delimited JSON-RPC 2.0
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Neovim plugin (Lua)                                         │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ client.lua         — JSON-RPC over vim.fn.sockconnect   │ │
│ │ bibliography.lua   — YAML frontmatter + CSL-JSON I/O    │ │
│ │ conflict_ui.lua    — scratch-buffer diff resolution     │ │
│ │ actions.lua        — insert_citekey, _with_text, open   │ │
│ │ selection.lua      — visual-mode capture                │ │
│ │                    (all UI-agnostic)                    │ │
│ └──────────────────────────┬──────────────────────────────┘ │
│ ┌──────────────────────────▼──────────────────────────────┐ │
│ │ telescope/_extensions/local_library.lua                 │ │
│ │  (UI adapter: picker + previewer + action binding)      │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

*Conceptual background: concepts §5 (asyncio + single-thread DB constraints).*

**Process model**: CLI-managed for MVP. Entry points: `uv run local-library daemon start | stop | status | restart | run`. PID file at `config.get_daemon_pid_path()`, socket at `config.get_socket_path()`, logs at `config.get_daemon_log_dir()`. Startup accepts a pre-bound socket FD via the `LaunchDaemonSockets` environment variable (forward-compat shim for future launchd socket-activation upgrade, ~15 lines of code).

**Concurrency model**: Single asyncio event loop, single `Library` instance, single sqlite-vec connection. Blocking model calls (embedder, reranker) wrapped in `loop.run_in_executor` — the executor's worker thread runs only torch/transformers inference; sqlite-vec and `Library` remain on the event-loop thread. The sqlite-vec single-thread assumption (verified during codebase investigation) is preserved by this discipline, not bypassed.

**What asyncio buys us** (despite the single-thread DB constraint): multi-client coexistence for the future MCP v2 + Neovim simultaneously, I/O interleaving during CPU-bound executor work, clean timeouts and cancellation via `asyncio.wait_for`, and cheap liveness probes — `ping` remains responsive while a search is running because it doesn't touch the executor.

### Daemon responsibility boundary

The daemon is a **read-only library access service**. It does not touch project bibliography files, does not parse YAML frontmatter, does not know about the current buffer. Plugin owns all file-system interaction. This keeps the daemon reusable for the future MCP server v2 and any other non-Neovim clients that lack editor-specific context.

### JSON-RPC contract (MVP method surface)

**Framing**: line-delimited compact JSON. One JSON object per line, terminated by a real newline byte (0x0A). Standard JSON serializers escape string-internal newlines as the two-character sequence `\` + `n` (bytes 0x5C 0x6E), so no raw 0x0A bytes appear inside serialized message bodies. Splitting the incoming stream on 0x0A always yields complete messages.

**Methods**:

```typescript
// Health check + observability probe
ping() → {
  ok: boolean,
  daemon_pid: number,
  resident_bytes: number,
  uptime_seconds: number,
  library_version: string
}

// Primary search operation
search({
  query: string,                         // required
  mode?: "hybrid" | "vector" | "fts",    // default "hybrid"
  limit?: number,                        // default 10
  rerank?: boolean,                      // default true
  doc_id?: string | null,                // HOOK: scope search to doc
                                         //   MVP: errors NOT_IMPLEMENTED if non-null
  boost_citekeys?: string[]              // HOOK: bib-aware ranking
                                         //   MVP: silently ignored
}) → {
  results: Array<{
    chunk_id: string,
    doc_id: string,
    citekey: string,
    document_title: string,
    document_authors: string[],
    document_year: number | null,
    score: number,
    rerank_score?: number,
    chunk_text: string,                  // eager: inline with result
    chunk_section_heading?: string,
    extracted_markdown_path: string      // for "open source" action
  }>,
  total_candidates: number,
  reranked: boolean
}

// Fetch full document metadata, including CSL-JSON entry
get_document({ identifier: string }) → {    // UUID or "@citekey"
  doc_id: string,
  citekey: string,
  csl_json: object,                      // what plugin writes on auto-append
  title: string,
  authors: string[],
  year: number | null,
  extracted_markdown_path: string,
  chunk_count: number,
  status: string
}
```

**Error envelope**:

```typescript
{
  jsonrpc: "2.0",
  id: N,
  error: {
    code: number,                        // -32000 for LocalLibraryError;
                                         // -32700/-32600/-32601/-32602/-32603
                                         // for transport-layer errors
    message: string,                     // exception.message
    data: {
      error_code: string,                // ErrorCode.value
                                         //   — client branches on this
      details: object                    // exception.details dict
    }
  }
}
```

*Conceptual background: concepts §3 (framing) and §4 (RPC envelopes); case study in §8.*

### Plugin architecture

**Module layout**:

```
nvim/
├── lua/
│   ├── local_library/
│   │   ├── init.lua            -- setup(), user commands, public API
│   │   ├── config.lua          -- defaults merged with user overrides
│   │   ├── client.lua          -- JSON-RPC client (UI-agnostic transport)
│   │   ├── selection.lua       -- visual-mode selection capture
│   │   ├── bibliography.lua    -- YAML frontmatter + CSL-JSON I/O + diff
│   │   ├── conflict_ui.lua     -- scratch-buffer diff resolution
│   │   ├── actions.lua         -- insert / open functions (pure-ish)
│   │   └── health.lua          -- :checkhealth local_library
│   └── telescope/_extensions/
│       └── local_library.lua   -- Telescope extension (initial UI adapter)
├── plugin/
│   └── local_library.lua       -- auto-registered commands/keybinds
├── doc/
│   └── local_library.txt       -- :help local-library
├── CLAUDE.md                   -- domain contracts
└── README.md
```

**Responsibility boundaries** (what makes the hybrid split real, not aspirational):

- `client.lua`: transport layer. Persistent Unix-socket channel via `vim.fn.sockconnect('unix', path, {rpc=false})`. JSON-RPC envelope handling; async surface via plenary.async. Knows nothing about Telescope, bibliography, or UX.
- `bibliography.lua`: file layer. Narrow-regex parser for the `bibliography:` YAML frontmatter field (no full YAML library). CSL-JSON read/write with `jq --indent 2` pretty-print (compact fallback). Conflict detection via normalized byte-compare plus field-level diff computation.
- `conflict_ui.lua`: diff UI. Opens a scratch buffer with `filetype=diff`, resolution instructions, and three local keymaps (`k` = keep existing, `o` = overwrite from library, `q` / `<Esc>` = abort entirely). Invokes a callback with the resolution.
- `actions.lua`: pure-ish orchestration. `insert_citekey`, `insert_citekey_with_text`, `open_source` — each takes `(ctx, result)` and performs the buffer modification, calling into `bibliography.lua` and `conflict_ui.lua` as needed.
- `telescope/_extensions/local_library.lua`: UI adapter. Maps `search` results → Telescope entries; previewer renders `chunk_text` + section heading + score; binds `<CR>` / `<C-t>` / `<C-o>` to the action functions. Only this module imports `telescope`.
- `init.lua`: public surface. `setup(opts)`, `:LocalLibraryCite`, `:LocalLibraryDaemon {start|stop|status|restart}`.

*Conceptual background: concepts §4 (envelope shape); the UI/data split is the architectural hook discussed in §8.*

### Core interaction flow (happy path)

```
[<leader>c fires in visual mode]
  ↓
selection.get_visual()           -- "gvy" + getreg('"'), register save/restored
  ↓
bibliography.resolve_refs_path(buf)   -- frontmatter → path (nil if absent)
  ↓
client.search({                  -- JSON-RPC over Unix socket, async
  query = selection_text,
  limit = config.search.limit,
  rerank = true,
  boost_citekeys = current_bib_keys    -- silent-inert hook passed routinely
})
  ↓
Telescope picker opens
  left pane:  ranked results (score, citekey, title)
  right pane: chunk_text preview (+ section heading, authors)
  ↓
user picks action:
  <CR>    → actions.insert_citekey(ctx, result)
  <C-t>   → actions.insert_citekey_with_text(ctx, result)
  <C-o>   → actions.open_source(ctx, result)
  <Esc>   → cancel
  ↓
for insert actions:
  client.get_document({ identifier: result.citekey })   -- fetch CSL-JSON
    ↓
  bibliography.ensure_entry(refs_path, csl_json)
    -- absent:    append to file
    -- identical: no-op
    -- differs:   return diff → conflict_ui.resolve(diff, callback)
                  -- k: insert citekey without bib write
                  -- o: write overwrite, insert citekey
                  -- q: abort entirely (no citekey, no write)
    ↓
  insert citekey at `>` mark (end of visual selection)
  (insert_with_text also appends chunk_text as blockquote on new line)
```

### Structural hooks (three mechanisms)

The design scaffolds three future-facing features using three distinct hook mechanisms. Each is chosen to match the failure semantics of the hook.

1. **Document-scope search** (loud-error hook). `search.doc_id` is accepted but returns a `NOT_IMPLEMENTED` error if non-null. Silently ignoring scope gives wrong *content* — the user asks for "within Smith2023" and gets the full corpus. Must self-report. The plugin surfaces this as a "scoping not yet available" notification.
2. **Bib-aware preferential ranking** (silent-inert hook). `search.boost_citekeys` is accepted and currently ignored. The plugin routinely passes the current project's bibliography citekeys in every search. Silently ignoring gives wrong *ordering* — degrades gracefully. Implementation can roll out on the daemon side with zero plugin-release coordination.
3. **Direct input mode** (architectural hook — no RPC change). The existing `search` method already accepts any query string. The plugin's hybrid split means a future `input_ui.lua` module can feed the same pipeline without touching Telescope or the daemon. This is the payoff of the hybrid split itself.

*Conceptual background: concepts §8 case study 4 documents the vocabulary in detail.*

The three mechanisms correspond to different post-MVP coupling profiles (tight two-side / plugin-leads-backend / plugin-only) and constitute a deliberate vocabulary of future-proofing patterns — captured as a case study in concepts chapter 8.

### Edge cases

| Situation | Behavior |
|---|---|
| No YAML `bibliography:` field in current buffer | Actions 1 & 2 insert citekey but skip auto-append; `vim.notify(..., WARN)` |
| Search returns zero results | Empty Telescope picker with a status-line message; `<Esc>` dismisses |
| Daemon not responding | `vim.notify(..., ERROR)` with restart hint; picker doesn't open |
| `extracted_markdown_path` missing on disk | Action 3 errors with a clear message; actions 1 & 2 unaffected |
| Bibliography file named in frontmatter but doesn't exist | `bibliography.ensure_entry` creates it as a single-entry array |
| Conflict on auto-append | Scratch buffer with diff; `k` / `o` / `q` resolve (abort leaves source buffer unmodified) |

*Conceptual background: concepts §6 (cross-process error handling) and §7 (reliability tier 1).*

## Existing Patterns

The daemon architecture follows established patterns in the local-library codebase. The plugin is new code but follows patterns established by the user's existing Neovim plugin stack.

### Codebase patterns followed

- **Entry-point convention** (`pyproject.toml [project.scripts]`): existing entries `local-library = "local_library.cli.main:app"` and `local-library-mcp = "local_library.mcp.server:main"`. The daemon adds `local-library-daemon = "local_library.daemon.server:main"` in the same style.
- **`Library` as service class**: the existing `Library` orchestrator (`src/local_library/core/library.py`) is already service-shaped — idempotent read methods returning domain objects, no CLI coupling, context-manager lifecycle. The daemon wraps it as-is without a service-layer refactor. Codebase investigation (2026-04-24) verified no architectural blockers.
- **External-client pattern (MCP server as template)**: `src/local_library/mcp/server.py` establishes the pattern of module-level `_library` singleton + `Library(embed_on_add=False)` + protocol-specific output formatting. The daemon replicates this pattern with JSON-RPC-specific formatting where MCP does markdown.
- **Lazy-loaded heavy models**: embedder and reranker loaded on first use (`Library._embedder = None` + `NomicEmbedder(lazy_load=True)` on the first `get_retriever` / `embed` call). The daemon preserves this — startup stays fast (~1–3 s) and first-query warmup is ~3–8 s; subsequent warm requests stay in the sub-500 ms target.
- **ErrorCode hierarchy**: `src/local_library/core/errors.py` defines `LocalLibraryError` with an `ErrorCode` enum. The daemon catches and maps `{code, message, details}` to the JSON-RPC error envelope (`data.error_code` carries the string enum value for client branching).
- **XDG paths via platformdirs** (`src/local_library/config.py`): existing functions `get_data_dir()`, `get_database_path()`, `get_storage_dir()`, etc. New `get_socket_path()`, `get_daemon_pid_path()`, `get_daemon_log_dir()` extend the same convention.
- **Domain-specific CLAUDE.md**: existing per-domain files (`src/local_library/core/CLAUDE.md`, `src/local_library/mcp/CLAUDE.md`, etc.) with `Last verified: YYYY-MM-DD` freshness headers. New `src/local_library/daemon/CLAUDE.md` and `nvim/CLAUDE.md` follow the same pattern.
- **Functional Core / Imperative Shell classification**: `# pattern:` comment at module headers. The daemon's protocol layer is Functional Core (pure serialization); socket handling is Imperative Shell. The plugin's `bibliography.lua` and `actions.lua` are Functional-Core-ish; `conflict_ui.lua` and the Telescope extension are Imperative Shell.

### Neovim plugin patterns followed

From the user's existing stack (`~/.config/nvim-rebuild/`):

- **lazy.nvim local-dir install**: `{ dir = "~/development/local-library/nvim", name = "local-library.nvim" }`. Consistent with the user's conventions for in-development plugins.
- **plenary.nvim for async** (transitive dependency via Telescope): `client.request` wrapped with `plenary.async` so consumer code reads linearly (`local err, result = client.search(...)`) rather than callback pyramids.
- **Telescope extension layout**: `lua/telescope/_extensions/local_library.lua` follows the `telescope.extensions.local_library.cite` convention used by `telescope-zotero.nvim` and comparable extensions.
- **`:checkhealth` support** via `health.lua`: standard Neovim idiom for plugin-level diagnostics.
- **Vimdoc at `doc/local_library.txt`**: standard help-tag convention; enables `:help local-library-*`.

### Patterns this design deliberately does not follow

- **No python-daemon / PEP 3143 double-fork pattern**: modern consensus treats manual daemonization as cargo-cult for user-level services when a supervisor is available. CLI-managed MVP uses a foreground process the user starts; future launchd upgrade uses launchd's own supervision. No double-fork code is written.
- **No pynvim as server**: pynvim is designed as a Neovim *client* library. Using it as an RPC server introduces event-loop composition issues. The daemon uses `python-lsp-jsonrpc` (production-tested via pylsp) or `jsonrpcserver` directly over asyncio.
- **No msgpack-rpc**: considered and rejected during brainstorming. Python server-side support is rough (less mature libraries, event-loop friction) and the binary wire format is opaque to standard debugging tools. JSON-RPC's debuggability and Python library maturity outweighed msgpack's marginal serialization efficiency at our payload sizes. Full rationale captured in the concepts document (chapter 4).

*Conceptual background: concepts §8 case studies 2 (msgpack-rpc rejection) and 3 (double-fork rejection).*

### Patterns introduced

- **Structured hook scaffolding vocabulary**: three distinct hook mechanisms (loud-error, silent-inert, architectural) with explicit failure-semantics reasoning. New to the codebase; captured as a reusable vocabulary in concepts chapter 8.
- **`run_in_executor` + sqlite-vec single-thread preservation**: new pattern in this codebase. The daemon is the first component where blocking model work needs to interleave with socket I/O while respecting a single-threaded DB layer.

## Implementation Phases

Seven phases. Each ends with a concrete, testable checkpoint. The concepts document's chapters are written in lockstep with the implementation phases that exemplify them, rather than deferred to the end — teaching emerges from the work rather than being reconstructed after.

### Phase 1: Daemon scaffolding

**Goal:** Runnable daemon process with `start` / `stop` / `status` / `restart` / `run` lifecycle and an asyncio Unix-socket server (echo-only — protocol comes in Phase 2).

**Components:**

- `local-library-daemon` entry in `pyproject.toml [project.scripts]` pointing at `local_library.daemon.server:main`.
- `src/local_library/daemon/` package with `__init__.py`, `server.py`, `cli.py`.
- `src/local_library/cli/daemon.py` — new CLI module wired into the main Typer app, exposing `start`, `stop`, `status`, `restart`, `run` subcommands.
- Extensions to `src/local_library/config.py`: `get_socket_path()`, `get_daemon_pid_path()`, `get_daemon_log_dir()` following the existing platformdirs pattern.
- PID-file lifecycle and SIGTERM / SIGINT signal handlers.
- `LaunchDaemonSockets` environment-variable inheritance shim for future launchd socket-activation upgrade.
- `src/local_library/daemon/CLAUDE.md` with `Last verified` date and the module's domain contract.

**Dependencies:** None (first phase).

**Done when:**

- `uv run local-library daemon start` spawns the daemon, writes a PID file, and binds the socket; `nc -U <socket>` connects and echoes input.
- `uv run local-library daemon status` reports `pid`, `uptime_seconds`, `resident_bytes`.
- `uv run local-library daemon stop` terminates cleanly (SIGTERM handled, socket unlinked, PID file removed).
- `uv run local-library daemon run` stays in the foreground (for launchd-compat and development use).
- Unit tests in `tests/unit/daemon/` cover PID-file lifecycle, signal handling, and double-start detection.

**Concepts doc deliverables:** Chapter 1 (what a daemon is, and why) and chapter 2 (process supervision and service management) written.

### Phase 2: JSON-RPC protocol layer

**Goal:** Replace the echo server with a compliant JSON-RPC 2.0 server. Only `ping` is registered in this phase; the foundation supports later method registration.

**Components:**

- `src/local_library/daemon/protocol.py` — line-delimited compact-JSON framing; message parser; response envelope builder.
- `src/local_library/daemon/dispatcher.py` — method registry and async dispatch loop.
- `src/local_library/daemon/errors.py` — translation from `LocalLibraryError` / `ErrorCode` to JSON-RPC error envelopes. Handles the standard transport codes (`-32700` parse error, `-32600` invalid request, `-32601` method not found, `-32602` invalid params, `-32603` internal error) and the generic server code (`-32000`) carrying structured `data.error_code`.
- `ping` method returning `{ ok, daemon_pid, resident_bytes, uptime_seconds, library_version }`.

**Dependencies:** Phase 1 (scaffolding).

**Done when:**

- A Python test client sends `{"jsonrpc":"2.0","id":1,"method":"ping"}` and receives a valid response with all expected fields.
- Malformed input returns `-32700`; unknown method returns `-32601`; missing required param returns `-32602`.
- A raised `LocalLibraryError` inside a handler is translated to `-32000` with `data.error_code` matching the raised `ErrorCode`.
- Unit tests in `tests/unit/daemon/` cover each of the above cases.

**Concepts doc deliverables:** Chapter 3 (IPC: byte streams and framing, including the `\n` wire-vs-escape distinction) and chapter 4 (RPC: encoding, framing, envelopes) written.

### Phase 3: Library integration — `search` and `get_document`

**Goal:** Daemon serves real search and metadata requests, with correct `run_in_executor` discipline and hook-parameter semantics.

**Components:**

- Module-level `Library` singleton construction (`Library(embed_on_add=False)`) in `server.py`, with clean shutdown on daemon exit.
- `search` method implementation — calls `Library.get_retriever(mode, rerank)`, wraps `embedder.embed_query` and reranker scoring in `loop.run_in_executor`, serializes `SearchResult` objects to the RPC response shape. Implements `doc_id` hook (loud-error: returns `NOT_IMPLEMENTED` if non-null) and `boost_citekeys` hook (silent-inert: accepted, currently ignored).
- `get_document` method — identifier resolution (UUID or `@citekey`), returns `csl_json`, metadata, `extracted_markdown_path`, `chunk_count`.
- Integration tests in `tests/integration/daemon/` using a real small test-corpus fixture.

**Dependencies:** Phase 2 (protocol layer).

**Done when:**

- A Python test client calling `search` with a real query receives ranked results with chunk text, citekeys, and `extracted_markdown_path` populated.
- `get_document({ identifier: "@citekey" })` returns the expected CSL-JSON entry.
- `search` with non-null `doc_id` returns an error response whose `data.error_code` is `NOT_IMPLEMENTED`.
- `search` with `boost_citekeys` set returns the same results as without (silent-inert verified by test).
- Measured warm reranked hybrid search latency on the dev corpus confirms p95 ≤ 500 ms.

**Concepts doc deliverables:** Chapter 5 (asyncio and single-threaded concurrency, including the `run_in_executor` + sqlite-vec interplay) and chapter 6 (error handling across process boundaries) written.

### Phase 4: Plugin foundation

**Goal:** Plugin loads in Neovim, can talk to the daemon via `client.ping()`, surfaces daemon status via `:checkhealth` and `:LocalLibraryDaemon status`. No search interaction yet.

**Components:**

- `nvim/` directory structure: `lua/local_library/`, `lua/telescope/_extensions/`, `plugin/`, `doc/`, `README.md`, `CLAUDE.md`.
- `lua/local_library/client.lua` — async JSON-RPC client over `vim.fn.sockconnect('unix', socket_path, {rpc=false})`. Methods: `connect`, `request(method, params, cb)`, `request_sync(method, params)` (plenary.async wrapper), `ping()`. Reconnect-on-dead-socket logic scaffolded (full reliability work is Phase 6).
- `lua/local_library/config.lua` — defaults plus `setup(opts)` merge. Default socket path matches `config.get_socket_path()`; configurable.
- `lua/local_library/init.lua` — `setup(opts)`, user commands (`:LocalLibraryDaemon {status|start|stop|restart}`). Daemon-control commands shell out to the Python CLI.
- `lua/local_library/health.lua` — `:checkhealth` hook reporting daemon liveness, socket path, plugin version.
- `nvim/CLAUDE.md` with `Last verified` date; `nvim/README.md` with lazy.nvim `dir =` install snippet.

**Dependencies:** Phase 3 (the daemon must actually respond to `ping`).

**Done when:**

- Plugin loads via `{ dir = "~/development/local-library/nvim", name = "local-library.nvim" }` in the user's lazy.nvim spec.
- `:checkhealth local_library` reports daemon status (running or not, with pid / uptime / resident bytes when running).
- `:LocalLibraryDaemon status` invokes the Python CLI and reports back.
- `:lua =require('local_library.client').ping()` returns a valid ping response.
- Plugin unit tests in `nvim/tests/` (using plenary.nvim test harness) cover connection lifecycle and common failure modes (socket absent, daemon not responding, malformed reply).

### Phase 5: Core interaction flow

**Goal:** End-to-end MVP happy path — visual-select claim, Telescope picker, all four actions, bibliography auto-append with conflict resolution.

**Components:**

- `lua/local_library/selection.lua` — visual-mode capture using `gvy` + `getreg('"')` with register save/restore.
- `lua/local_library/bibliography.lua` — narrow-regex YAML frontmatter parser (extracts `bibliography:` from the first 50 lines of the current buffer); walk-up fallback looking for `_quarto.yml`; CSL-JSON read/write with `jq --indent 2` pretty-print (compact fallback); `ensure_entry(refs_path, csl_json)` returning `{action, ...}` (`appended` / `unchanged` / `conflict`); field-level diff computation with author and key normalization.
- `lua/local_library/conflict_ui.lua` — scratch buffer with `filetype=diff`, header text with resolution instructions, three local keymaps (`k` keep, `o` overwrite, `q` / `<Esc>` abort). Invokes a callback with the resolution.
- `lua/local_library/actions.lua` — `insert_citekey(ctx, result)`, `insert_citekey_with_text(ctx, result)`, `open_source(ctx, result)`. Each handles the bibliography round-trip (when `refs_path` is resolved), calls `conflict_ui.resolve` on conflict, and performs the buffer modification.
- `lua/telescope/_extensions/local_library.lua` — Telescope extension. Picker with `entry_maker` mapping `search` results to entries; previewer showing `chunk_text` + section heading + score; default action map (`<CR>` → insert_citekey, `<C-t>` → insert_citekey_with_text, `<C-o>` → open_source, `<Esc>` → cancel).
- `:LocalLibraryCite` user command and default `<leader>c` visual-mode keybind (user can disable via `setup({ keymaps = false })`).
- Integration tests covering each action end-to-end (mock daemon, real buffer manipulation).

**Dependencies:** Phase 4 (plugin foundation with working `client`).

**Done when:**

- Visual-select a claim, hit `<leader>c`: Telescope picker opens with ranked results and the previewer renders chunk text.
- `<CR>` on a result: citekey inserted at the end of the visual selection; CSL-JSON entry appended to the bibliography file when `refs_path` resolves; no conflict on a fresh file.
- `<C-t>`: citekey plus blockquoted chunk text inserted.
- `<C-o>`: extracted markdown opens, cursor positioned near the chunk (text-search fallback to section heading if needed).
- Conflict case: scratch buffer opens with formatted diff; `k` / `o` / `q` all produce the specified behavior.
- Edge cases handled per the Architecture table (missing frontmatter → insert-only with WARN; missing file → created on append; absent extracted markdown → action 3 errors).

### Phase 6: Reliability tier 1 and hooks completion

**Goal:** Meet the tier-1 reliability bar. Plugin exercises both hooks routinely. Dead-socket reconnection works.

**Components:**

- Daemon logging: structured output to `config.get_daemon_log_dir()/daemon.log`. Request / response logging records method, status, and duration (not chunk content). Append mode; rotation is a future concern.
- Plugin error surfacing: `client.request`'s error handler maps JSON-RPC `data.error_code` values to user-friendly `vim.notify` messages. Cases: daemon unreachable, `NOT_IMPLEMENTED` from scoped search, `EMBEDDING_EXTENSION_UNAVAILABLE`, generic fallback.
- Reconnect logic: detect dead channel (chan_id = 0 after send); reconnect with exponential backoff (max 3 attempts); surface a clear error when unrecoverable.
- Per-method client-side timeouts: 5 s default for `search`, 2 s for `ping` and `get_document`, configurable via `setup({ timeouts = { ... } })`.
- Plugin always passes `boost_citekeys = bibliography.list_citekeys(refs_path)` in every `search` call (silent-inert hook routinely exercised).
- `doc_id` formally returns `NOT_IMPLEMENTED` from the daemon; the plugin's error handler maps it to a "document-scope search not yet available" notification.

**Dependencies:** Phase 5 (core flow must exist to have something to fail).

**Done when:**

- Kill the daemon mid-use (`kill -9`): the next search surfaces a clear `vim.notify` with "daemon not running — run `:LocalLibraryDaemon start`".
- Restart the daemon and run a search again without reloading Neovim: succeeds via reconnect logic.
- Slow-query test fixture: client-side timeout triggers with a clear message.
- Test-only `doc_id` usage: plugin surfaces the "scoping not yet available" notification.
- `boost_citekeys` verified to be in the RPC request payload via daemon-side log inspection.

**Concepts doc deliverables:** Chapter 7 (reliability: crash recovery, timeouts, liveness) written.

### Phase 7: Concepts doc case studies, polish, docs

**Goal:** Teaching artifact complete and cross-linked. Plugin usable by a fresh reader with just the README. Project docs reflect shipped reality.

**Components:**

- Concepts chapter 8 (`docs/concepts/daemons.md` §8): case studies pulling earlier abstract chapters into this project's concrete decisions — sqlite-vec → async, JSON-RPC + debuggability, CLI-managed with launchd pathway, three hook scaffolding mechanisms. Each earlier chapter gets an "in local-library, see §X" cross-reference to the design doc.
- Design-doc updates: in-place cross-references pointing at concepts chapters from the Architecture and Implementation Phases sections (where teaching content exists).
- `nvim/doc/local_library.txt` — vimdoc covering setup, commands, keymaps, config, troubleshooting (`:help local-library-*`).
- `nvim/README.md` — install instructions (lazy.nvim spec), setup snippet, quickstart (daemon start + visual-select demo), troubleshooting table.
- `nvim/CLAUDE.md` — domain contracts for the plugin (pattern classification, freshness date, mirrors `src/local_library/*/CLAUDE.md` shape).
- `src/local_library/daemon/CLAUDE.md` — domain contracts for the daemon module (completed from its Phase 1 seed).
- Project-level `roadmap.md` update: daemon + plugin promoted from "Exploring" to "Stable" under Neovim Citation Workflow.
- Top-level `CLAUDE.md` update: new "Implemented" bullets for daemon and plugin; freshness date bumped.

**Dependencies:** Phase 6 (reliability work provides material for chapter 8's reliability case study).

**Done when:**

- All eight concepts chapters exist; each ends with a design-doc cross-reference.
- Design-doc Architecture and Implementation sections link to the relevant concepts chapters.
- `:help local-library` works in Neovim.
- Plugin README lets a fresh reader install, configure, and run the first visual-select → insert flow without reading anything else.
- Project `roadmap.md` and top-level `CLAUDE.md` reflect the shipped state.

## Additional Considerations

### Didactic implementation posture

The user selected the "deep" didactic bent for this design cycle. This shapes not only the concepts-doc deliverable but the implementation posture overall:

- Commits should be walkable as teaching artifacts. Granular commits with "why" captured in the message, not only "what."
- Code comments on daemon infrastructure (startup, socket handling, protocol framing, error translation) tilt toward explanation rather than minimalism.
- The concepts document is written in lockstep with the phases it exemplifies, not retrofitted at the end, so the teaching emerges from the work rather than being reconstructed after.

### Forward-compat constraints preserved

Three future trajectories are explicitly kept open:

- **launchd socket-activation upgrade**: the FD-inheritance shim introduced in Phase 1 makes moving to a LaunchAgent plist a packaging-only change, not a daemon-code change.
- **MCP server v2 hosted by the daemon**: the daemon stays editor-agnostic (read-only library access service, no Neovim-specific state). The MCP server can later swap from its in-process `Library` singleton to a daemon client without forcing daemon changes.
- **Marker integration (planned non-inclusion)**: the Neovim plugin will never need Marker, but MCP v2 might if import/add tools are added there. The daemon module layout keeps import/write operations out of Phase 1–6 scope but does not structurally foreclose adding a `daemon/ingestion.py` module later.

### Dependencies on other feature areas

- **RAG Pipeline Improvements** provides retrieval-quality gains transparently: the plugin always surfaces whatever the retriever produces. Better retrieval → better suggestions, no plugin change required.
- **Corpus re-annotation at scale** (per `roadmap.md`) is the upstream dependency that gates meaningful latency and quality measurement on the full corpus. The p95 ≤ 500 ms target is a developer yardstick, not a formal SLO; if full-corpus baseline shows different numbers once re-annotation lands, the target is revisited.
- **Automated Content Analysis (tags)**: the "tag-aware search" longer-term idea depends on an auto-tagging feature area that does not yet exist. Explicitly out of scope; no hook scaffolded.

### Explicit non-inclusions (reinforcing the DoD)

No triage verification modes. No context-aware snippet insertion. No tag-aware search. No MCP v2 hosting by the daemon this cycle. No Marker integration in the daemon. Each has its own reasoning in the DoD and feature-area README.

### Scope for implementation planning

Seven phases fits within the `writing-plans` skill's 8-phase hard limit, so a single implementation plan will suffice. Phase 5 is the largest chunk and will produce the most tasks; Phase 7 is smaller but has many small deliverables across several files.

## Glossary

- **asyncio**: Python's built-in library for writing concurrent code using a single-threaded cooperative event loop, used here to handle multiple simultaneous client connections without spawning threads.
- **BetterBibTeX (BBT)**: A Zotero extension that generates stable, human-readable citation keys (citekeys) for bibliography entries; this project uses the same key format independently.
- **citekey**: A short identifier for a bibliographic reference (e.g., `Smith2023`), used in citation syntax and as a stable handle for documents throughout this system.
- **CSL-JSON**: Citation Style Language JSON — a standard format for bibliographic metadata that is also the native exchange format used by Zotero; this project stores and outputs bibliography entries in this format.
- **Functional Core / Imperative Shell**: An architectural pattern that separates pure, side-effect-free logic (Functional Core) from code that interacts with the outside world — I/O, sockets, file writes (Imperative Shell). Used pervasively in this codebase and applied to the new daemon and plugin modules.
- **JSON-RPC 2.0**: A lightweight remote procedure call protocol using JSON encoding; specifies request/response envelopes, error codes, and method dispatch. Used as the wire protocol between the daemon and the Neovim plugin.
- **launchd**: macOS's system and user-level service supervisor, analogous to systemd on Linux. The daemon is designed with a forward-compatibility shim so it can eventually be managed by launchd without code changes.
- **lazy.nvim**: The dominant Neovim plugin manager; the plugin is installed via a `dir =` local-path entry in the user's lazy.nvim configuration.
- **line-delimited JSON (framing)**: A transport convention where each JSON object occupies exactly one line, terminated by a newline byte (0x0A). Enables simple stream parsing without a length-prefix protocol.
- **MCP (Model Context Protocol)**: A protocol for exposing tools to Claude Code; this project already has an MCP server (Phase 1 complete). The daemon is designed to be reusable as a backend for a future MCP server v2.
- **plenary.nvim**: A Lua utility library for Neovim providing, among other things, an async abstraction layer used here to write `client.request` calls that read linearly rather than as callback chains.
- **RRF (Reciprocal Rank Fusion)**: The algorithm used to combine vector similarity scores and BM25 full-text search scores into a single ranked list for hybrid retrieval.
- **run_in_executor**: An asyncio API that submits a blocking function to a thread-pool executor, allowing CPU-bound work (here: model inference) to proceed without blocking the event loop.
- **sqlite-vec**: A SQLite extension for vector similarity search; it requires single-threaded access, which constrains the daemon's concurrency model.
- **Telescope**: A fuzzy-finder and picker UI framework for Neovim; the plugin's initial UI is implemented as a Telescope extension providing a results picker with a chunk-preview pane.
- **Unix domain socket**: An IPC mechanism that uses a filesystem path instead of a network address; faster than TCP for local communication and avoids network port conflicts. Used as the transport between daemon and plugin.
- **vimdoc**: Neovim's built-in help format (plain text with specific tag syntax); the plugin ships a `doc/local_library.txt` file so `:help local-library` works natively.
