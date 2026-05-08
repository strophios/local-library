# Neovim Citation Workflow Implementation Plan — Phase 7: Concepts Doc Case Studies, Polish, Docs

**Goal:** Ship the teaching artifact. Concepts chapter 8 pulls earlier abstract chapters into this project's concrete decisions through four case studies. Design doc gets inline cross-references to the relevant concepts chapters. The Neovim plugin gets vimdoc (`:help local-library` works), README polish, final CLAUDE.md. The daemon's CLAUDE.md gets completed (Phase 1 shipped a seed). Project-level docs (`roadmap.md`, top-level `CLAUDE.md`) reflect shipped reality.

**Architecture:** No code changes. Pure documentation work spread across `docs/concepts/daemons.md`, `docs/design-plans/2026-04-24-neovim-citation-workflow.md`, `nvim/doc/local_library.txt` (new), `nvim/README.md`, `nvim/CLAUDE.md`, `src/local_library/daemon/CLAUDE.md`, `roadmap.md`, `CLAUDE.md`.

**Scope:** 7 of 7 phases. This phase closes the cycle.

**Codebase verified:** 2026-04-24.

**Executor skills:** `ed3d-house-style:writing-for-a-technical-audience`, `ed3d-extending-claude:writing-claude-md-files`, `ed3d-plan-and-execute:verification-before-completion`. No TDD here — documentation tasks verify by reading.

---

<!-- START_TASK_1 -->
## Task 1: Concepts chapter 8 — case studies

**Type:** Documentation.

**Files:**
- Modify: `docs/concepts/daemons.md`

### Step 1: Append chapter 8

Open `docs/concepts/daemons.md`. Replace the closing line `*Chapter 8 is written in Phase 7 (case studies + cross-references).*` (from Phase 6) with:

```markdown

## Chapter 8 — Case studies: how the abstract patterns landed in this project

Earlier chapters introduced abstract patterns: daemons (ch. 1), service
management (ch. 2), framing (ch. 3), RPC envelopes (ch. 4), single-thread
DB constraints (ch. 5), cross-process error handling (ch. 6), reliability
(ch. 7). This final chapter pulls four of the most consequential decisions
into one place — what we chose, what we considered, and why the result is
what it is.

### Case study 1 — sqlite-vec → asyncio: the single-worker executor

**Context (ch. 5):** sqlite-vec requires single-thread access. asyncio
gives us cooperative concurrency on one thread, which seems compatible —
until you observe that model inference (embedder, reranker) is CPU-bound
and would block the event loop, killing `ping` responsiveness.

**Considered:**

1. *Refactor `Retriever.retrieve()` to expose embed/query/rerank phases
   separately,* so the daemon could run model phases in an executor and
   sqlite-vec phases on the loop thread. Would honor the original design
   verbatim. Cost: changes to the Retriever protocol, ripples through
   `VectorRetriever`, `FTSRetriever`, `HybridRetriever`, `RerankedRetriever`,
   plus their tests. High-touch, scope-bending.
2. *Use a multi-worker executor with `check_same_thread=False`.* Would
   permit theoretical parallelism but defeat sqlite-vec's invariant; we'd
   need our own mutex on the connection. The "concurrency" we'd buy is
   illusory — sqlite-vec serializes anyway.
3. *Run the entire `retrieve()` call on the asyncio loop thread.* Simplest
   to write; hangs `ping` for the duration of any search. Unacceptable.

**Chose:** A `ThreadPoolExecutor(max_workers=1)` that owns the Library
end-to-end. The Library is *constructed* on the executor thread, *closed*
on the executor thread, and every `retrieve()` runs on it. The asyncio
loop thread handles only socket I/O and dispatch.

**Why it works:** sqlite-vec sees one thread for its entire lifetime.
The event loop stays free for `ping` (which doesn't enter the executor)
and for accepting new connections. The "loss" of parallel searches is
illusory — sqlite-vec wouldn't have allowed it anyway.

**See:** `daemon/server.py:_make_library_executor`,
`run_on_library_thread`; concepts ch. 5 §"local-library's resolution".

### Case study 2 — JSON-RPC + debuggability: rejecting msgpack-rpc

**Context (ch. 4):** RPC needs a serialization format. The mainstream
choices for a Python daemon talking to a Neovim plugin are JSON-RPC 2.0,
msgpack-rpc (Neovim's native protocol), and a custom binary protocol.

**Considered:**

1. *msgpack-rpc.* Neovim's `vim.fn.sockconnect("...", ..., {rpc=true})`
   speaks it natively. Bytes on the wire are 30-50% smaller than JSON
   for our payloads. `msgpack` is faster to parse than `json`. Looks
   like the obvious choice.
2. *A custom binary protocol.* Maximum compactness; no library
   dependency. Real overhead in implementation and debugging.
3. *JSON-RPC 2.0.* Human-readable, debuggable with `nc -U` + a text
   editor, every language has a JSON library, the spec is three pages
   and two decades stable.

**Chose:** JSON-RPC 2.0.

**Why it works:** Our payloads are small (`<10 KB` typical search
result). The 30-50% size difference is negligible at our scale —
microseconds of wire transit on a Unix socket. What we lose: a small
amount of throughput we never needed. What we gain:

- A human can `nc -U $socket` and type a request. msgpack is opaque
  bytes you can't paste.
- `tcpdump -i lo0 -A` (or its UDS equivalent) shows readable traffic.
  msgpack requires a decoder.
- `python-lsp-jsonrpc` and `jsonrpcserver` exist, but neither earned
  its keep at our 3-method scale (ch. 4 §"Library choice"). We rolled
  our own framing + parser in ~200 LOC and own every line.

**Why msgpack-rpc was actually wrong, not just suboptimal:** Neovim's
msgpack-rpc framing is *its own* — it's not the standard msgpack-rpc
spec. Adopting `rpc=true` would have entangled us with Neovim's RPC
quirks (notification dispatch through Neovim, request-id semantics,
the implicit `nvim_*` method namespace). Our daemon must remain
editor-agnostic for the future MCP server v2 to share it.

**See:** `daemon/protocol.py`; design doc §"Patterns this design
deliberately does not follow"; concepts ch. 4 §"Why JSON-RPC 2.0".

### Case study 3 — CLI-managed with launchd pathway

**Context (ch. 2):** Three styles of process supervision: user-managed
CLI, system supervisor (launchd/systemd), socket activation.

**Considered:**

1. *Full launchd LaunchAgent now.* Plist with `KeepAlive`, `RunAtLoad`,
   `Sockets`. Pays for itself if the daemon is "always on." Requires
   the user to install the plist, deal with launchd diagnostics
   (`launchctl print user/$UID/com.local-library.daemon`), and accept
   that "stop the daemon" means "edit the plist."
2. *Double-fork demonization (PEP 3143).* The classic Unix daemon
   recipe. Modern consensus (per `man systemd.exec` and the
   "type=simple" design): cargo-cult for user-level services in 2025.
3. *CLI-managed (foreground + signal-driven shutdown).* User runs
   `local-library daemon start`/`stop`. No double-fork. Process is a
   plain foreground program for tooling purposes (`ps`, `lsof`).

**Chose:** CLI-managed for MVP, with explicit forward-compat for
launchd via the `LAUNCH_ACTIVATE_SOCKET_FD` env var hook.

**Why it works:**

- The user's workflow is "start the daemon when I begin writing,
  stop it when I'm done." launchd's "always on" model would burn
  ~200 MB of RSS across days when nothing is happening.
- The forward-compat shim (`socket_activation.inherited_socket()`)
  is ~15 LOC and tested. Migrating to launchd is a *packaging* change
  (write a plist, add a `KeepAlive` policy), not a code change.
- Avoiding double-fork avoids a class of bugs: TTY detachment, file
  descriptor inheritance, working directory surprises. We don't pay
  for this complexity because we don't need it.

**The path forward:** A LaunchAgent plist with a `Sockets` key would
pre-bind the socket and pass the FD; the daemon's `inherited_socket()`
would pick it up. No code change in the daemon. The shim turns the
launchd migration from a refactor into a config edit.

**See:** `daemon/socket_activation.py`; design doc §"Process model";
concepts ch. 2 §"local-library's choice".

### Case study 4 — Three hook scaffolding mechanisms

**Context (Phase 5/6):** The MVP defers three features (document-scoped
search, bib-aware ranking, direct text input). Each could be
"deferred" with no scaffolding — but then enabling each later requires
coordinated changes on both sides of the socket boundary. We wanted to
choose hook mechanisms that match each feature's failure semantics.

The three mechanisms (named for their failure mode):

#### Loud-error hook: `search.doc_id`

Document-scoped search ("find chunks within `@Smith2023`") would
silently change the *content* of the response if the daemon ignored
the parameter — the user asks for "within Smith2023" and gets the full
corpus.

**Mechanism:** Daemon accepts `doc_id` parameter. Non-null value raises
`LocalLibraryError(NOT_IMPLEMENTED, details={"hook": "doc_id"})`. The
plugin's `notify` mapper translates this to "document-scoped search is
not yet available." The user gets *signal*, not a wrong answer.

**Coupling profile:** When implementation lands, daemon and plugin
both need to update — daemon to actually filter, plugin to remove the
"not yet available" notification path. Tight two-side coordination.

#### Silent-inert hook: `search.boost_citekeys`

Bib-aware preferential ranking would silently change the *ordering* of
search results if the daemon ignored the parameter — degraded
gracefully, the user just gets unsorted-by-citation-presence results.
That's a quality regression, not a correctness regression.

**Mechanism:** Daemon accepts `boost_citekeys` and currently ignores
it. The plugin always passes the current project's citekeys
(`bibliography.list_citekeys(refs_path)`). When the daemon-side
implementation lands, it has effect immediately — no plugin release
needed.

**Coupling profile:** Plugin-leads-backend. Plugin code is already
correct; daemon catches up in a future release with zero coordination.

#### Architectural hook: direct text input mode

A future feature lets the user type a free-text query (not a visual
selection). The daemon already accepts arbitrary query strings via
`search.query`, so there's no protocol change to make. The hook is
*structural*: the plugin's hybrid UI/data split means a future
`input_ui.lua` module (or an alternative Telescope picker) can feed
the existing pipeline without touching the daemon or any other module.

**Mechanism:** None on the wire. The hook is the architecture itself —
the discipline that `client.lua`, `actions.lua`, `bibliography.lua`
know nothing about Telescope. A new UI consumes them as-is.

**Coupling profile:** Plugin-only. Adding direct input mode is purely
a plugin change.

#### What this vocabulary buys us

We now have three named patterns for "scaffold a future feature today,"
each matched to a different failure mode:

| Mechanism | Failure mode if ignored | Coupling on rollout |
|-----------|-------------------------|---------------------|
| Loud-error | Wrong content | Tight two-side |
| Silent-inert | Degraded ordering | Plugin-leads-backend |
| Architectural | N/A (structural) | Plugin-only |

Each design choice — *not just* "build a hook" but *which kind of
hook* — is a small decision that compounds over the project's life.
Documenting the vocabulary explicitly (here and in design doc
§"Structural hooks") means future contributors can reach for the right
mechanism by name.

**See:** Design doc §"Structural hooks"; `daemon/methods.py`
(loud-error in `search()`); `nvim/lua/local_library/init.lua`
(silent-inert via `boost_citekeys` always passed);
`nvim/lua/local_library/` module organization (architectural).

---

The daemons concepts doc closes here. Each chapter has cross-references
into the design doc and the codebase; each design and code decision has
a return path into a chapter. Future maintainers — including future-you
— have a single document that explains both *what* the daemon does and
*why* it's shaped the way it is.
```

### Step 2: Verify chapter count + commit

```bash
grep -c '^## Chapter' docs/concepts/daemons.md
```

Expected: `8`.

```bash
git add docs/concepts/daemons.md
git commit -m "docs(concepts): add chapter 8 — case studies

Four case studies pulling earlier abstract chapters into this project's
concrete decisions: sqlite-vec → async (single-worker executor),
JSON-RPC + debuggability (rejecting msgpack-rpc), CLI-managed with
launchd pathway, the three hook scaffolding mechanisms. Each names what
was considered, what was chosen, and why; cross-references back to design
doc and code."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
## Task 2: Design-doc cross-references to concepts chapters

**Type:** Documentation.

**Files:**
- Modify: `docs/design-plans/2026-04-24-neovim-citation-workflow.md`

### Step 1: Add inline cross-references

Edit the design doc. Goal: add `→ concepts §N` links from each major architectural section to the relevant concepts chapter.

Specific insertion points (implementer reads each section, adds a one-line italicized cross-reference at the section's end):

1. **§"High-level shape"** → end with: `*Conceptual background: see [docs/concepts/daemons.md](../concepts/daemons.md) chapters 1–2 (what a daemon is; service management).*`

2. **§"Daemon architecture"** → after the ASCII diagram: `*Conceptual background: concepts §5 (asyncio + single-thread DB constraints).*`

3. **§"JSON-RPC contract"** → end with: `*Conceptual background: concepts §3 (framing) and §4 (RPC envelopes); case study in §8.*`

4. **§"Daemon responsibility boundary"** → no cross-ref needed.

5. **§"Plugin architecture"** → end with: `*Conceptual background: concepts §4 (envelope shape); the UI/data split is the architectural hook discussed in §8.*`

6. **§"Structural hooks (three mechanisms)"** → after the numbered list: `*Conceptual background: concepts §8 case study 4 documents the vocabulary in detail.*`

7. **§"Edge cases"** → after the table: `*Conceptual background: concepts §6 (cross-process error handling) and §7 (reliability tier 1).*`

8. **§"Patterns this design deliberately does not follow"** → end with: `*Conceptual background: concepts §8 case studies 2 (msgpack-rpc rejection) and 3 (double-fork rejection).*`

### Step 2: Verify presence

```bash
grep -c "concepts §" docs/design-plans/2026-04-24-neovim-citation-workflow.md
```

Expected: at least 7 matches.

### Step 3: Commit

```bash
git add docs/design-plans/2026-04-24-neovim-citation-workflow.md
git commit -m "docs(design): cross-reference concepts/daemons.md chapters

Each major architectural section now links to the relevant concepts
chapter, so a reader of the design has a direct path to the teaching
material. Pairs with concepts chapter 8's case studies (which already
link back into the design doc)."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
## Task 3: vimdoc — `:help local-library` works

**Type:** Documentation.

**Files:**
- Create: `nvim/doc/local_library.txt`

### Step 1: Author the vimdoc

`nvim/doc/local_library.txt`:

```text
*local_library.txt*	Claim-driven semantic search for Neovim

==============================================================================
CONTENTS                                              *local-library-contents*

  1. Introduction                          |local-library|
  2. Requirements                          |local-library-requirements|
  3. Installation                          |local-library-installation|
  4. Quickstart                            |local-library-quickstart|
  5. Commands                              |local-library-commands|
  6. Keymaps                               |local-library-keymaps|
  7. Configuration                         |local-library-config|
  8. Daemon management                     |local-library-daemon|
  9. Troubleshooting                       |local-library-troubleshooting|

==============================================================================
1. INTRODUCTION                                            *local-library*

local-library.nvim is a Neovim plugin for claim-driven semantic search
against the local-library document corpus. Visual-select a sentence in your
prose; the plugin queries the long-running local-library daemon over a
Unix domain socket; you get a Telescope picker of ranked matching chunks
from your library; selecting one inserts a citation and (optionally)
appends the CSL-JSON entry to your project bibliography.

==============================================================================
2. REQUIREMENTS                                *local-library-requirements*

- Neovim 0.10 or later
- The local-library Python package and daemon (see project README)
- plenary.nvim (transitive dependency via Telescope)
- Telescope.nvim
- jq (optional; used to pretty-print bibliography files)

==============================================================================
3. INSTALLATION                                *local-library-installation*

Install via lazy.nvim using a local directory entry:
>
    {
      dir = "~/development/local-library/nvim",
      name = "local-library.nvim",
      dependencies = { "nvim-lua/plenary.nvim", "nvim-telescope/telescope.nvim" },
      lazy = false,
      config = function()
        require("local_library").setup({})
      end,
    }
<

==============================================================================
4. QUICKSTART                                    *local-library-quickstart*

1. Start the daemon: `:LocalLibraryDaemon start`
2. Confirm health:   `:checkhealth local_library`
3. Open a markdown file with a `bibliography:` frontmatter field
4. Visual-select a sentence; press `<leader>c`
5. Browse results in the Telescope picker; press `<CR>` to insert citekey,
   `<C-t>` to insert citekey + chunk text as a blockquote, `<C-o>` to open
   the source markdown

==============================================================================
5. COMMANDS                                        *local-library-commands*

                                                          *:LocalLibraryCite*
:LocalLibraryCite       Run a claim-driven library search on the visual
                        selection. Opens a Telescope picker. Bound by
                        default to `<leader>c` in visual mode.

                                                       *:LocalLibraryDaemon*
:LocalLibraryDaemon {action}
                        Manage the daemon process. {action} is one of:
                          start    spawn the background daemon
                          stop     SIGTERM the daemon
                          status   show pid, uptime, memory
                          restart  stop + start

                                                              *:checkhealth*
:checkhealth local_library
                        Diagnose plugin + daemon liveness.

==============================================================================
6. KEYMAPS                                          *local-library-keymaps*

Default mapping (visual mode):
>
    <leader>c    :LocalLibraryCite
<

Disable default keymaps:
>
    require("local_library").setup({ keymaps = { enabled = false } })
<

Override the keymap:
>
    require("local_library").setup({
      keymaps = { visual_cite = "<leader>x" },
    })
<

Inside the Telescope picker:
- `<CR>`     insert citekey at end of selection (auto-append to bibliography)
- `<C-t>`    insert citekey + chunk text as a blockquote on a new line
- `<C-o>`    open the extracted markdown source at the chunk
- `<Esc>`    cancel

==============================================================================
7. CONFIGURATION                                     *local-library-config*

                                                  *local-library.setup()*
require('local_library').setup({opts})

Defaults:
>
    {
      socket_path = nil,
        -- nil → resolve from $XDG_DATA_HOME/local-library/daemon.sock
        --       or ~/Library/Application Support/local-library/daemon.sock
      request_timeout_ms = 5000,
        -- legacy fallback (use timeouts.* instead)
      timeouts = {
        default_ms = 5000,
        by_method = {
          ping = 2000,
          get_document = 2000,
          search = 5000,
        },
      },
      keymaps = {
        enabled = true,
        visual_cite = "<leader>c",
      },
      search = {
        limit = 10,
        rerank = true,
      },
    }
<

==============================================================================
8. DAEMON MANAGEMENT                                *local-library-daemon*

The plugin requires a running daemon. Start it once per session via
`:LocalLibraryDaemon start`. Logs are at:
>
    ~/Library/Application Support/local-library/logs/daemon.log
<

The daemon publishes its socket at:
>
    ~/Library/Application Support/local-library/daemon.sock
<

Override either path via `:lua require('local_library').setup{socket_path
= '...'}`.

==============================================================================
9. TROUBLESHOOTING                          *local-library-troubleshooting*

|:checkhealth| says "no socket file":
    The daemon isn't running. Run `:LocalLibraryDaemon start`.

|:checkhealth| says "daemon ping failed":
    The daemon is up but not responding. Check the daemon log:
>
    tail -f ~/Library/Application\ Support/local-library/logs/daemon.log
<

`<leader>c` does nothing:
    Default keymap may be disabled. Check `:lua print(vim.inspect(
    require('local_library').config().keymaps))`. Re-enable with
    `setup({keymaps = {enabled = true}})`.

"DAEMON_UNREACHABLE" notifications:
    The daemon was killed or crashed. Run `:LocalLibraryDaemon start`.

==============================================================================
vim:tw=78:ts=8:ft=help:norl:
```

### Step 2: Build help tags + verify

```bash
nvim --headless -c "helptags nvim/doc/" -c "qa"
nvim -c "help local-library" -c "qa" 2>&1 | head -5
```

Expected: no error; tag resolves cleanly.

### Step 3: Commit

```bash
git add nvim/doc/local_library.txt nvim/doc/tags
git commit -m "docs(nvim): vimdoc for :help local-library

Covers introduction, requirements, installation, quickstart, commands,
keymaps, configuration defaults, daemon management, troubleshooting.
9 named tags. helptags generated."
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
## Task 4: nvim/README.md polish + nvim/CLAUDE.md final + daemon/CLAUDE.md completion

**Type:** Documentation.

**Files:**
- Modify: `nvim/README.md`
- Modify: `nvim/CLAUDE.md`
- Modify: `src/local_library/daemon/CLAUDE.md`

### Step 1: Polish `nvim/README.md`

Replace the existing README:

```markdown
# local-library.nvim

Claim-driven semantic search for Neovim. Visual-select a sentence,
hit `<leader>c`, browse a Telescope picker of relevant chunks from your
library, insert a citation, auto-append the bibliography entry. Backed
by the long-running local-library daemon.

## Why this exists

Two existing tools serve adjacent needs:

- **telescope-zotero.nvim** (`<leader>z`) — author/title lookup. You
  know the work you want to cite.
- **local-library.nvim** (`<leader>c`) — claim-driven search. You have
  a sentence and want to find evidence in your corpus.

This plugin is the second one. It assumes you already wrote the claim;
its job is to surface the supporting passages.

## Quickstart

```vim
:LocalLibraryDaemon start    " starts the Python daemon
:checkhealth local_library   " confirms daemon is reachable
" In a markdown file with `bibliography: refs.json` in frontmatter:
" Visual-select a sentence, press <leader>c
```

## Installation (lazy.nvim, local development)

```lua
{
  dir = "~/development/local-library/nvim",
  name = "local-library.nvim",
  dependencies = {
    "nvim-lua/plenary.nvim",
    "nvim-telescope/telescope.nvim",
  },
  lazy = false,
  config = function()
    require("local_library").setup({})
  end,
}
```

## Actions in the picker

| Key   | Action |
|-------|--------|
| `<CR>` | Insert `[@citekey]` at the end of the visual selection. Auto-append CSL-JSON to your bibliography. |
| `<C-t>` | Same as `<CR>`, plus insert the chunk text as a blockquote on a new line. |
| `<C-o>` | Open the extracted markdown source at the cited chunk. |
| `<Esc>` | Cancel. |

If your buffer has no `bibliography:` frontmatter, the citekey is
inserted but no bibliography write happens (a WARN notification
clarifies this).

## Configuration

See `:help local-library-config` for the full list. Common overrides:

```lua
require("local_library").setup({
  socket_path = "/custom/path/daemon.sock",
  search = { limit = 20, rerank = true },
  keymaps = { visual_cite = "<leader>x" },
})
```

## Bibliography conflict resolution

When you insert a citekey for a doc that already has an entry in your
bibliography but the metadata differs, a scratch buffer opens with a
field-level diff:

- `k` — keep your existing entry, insert citekey only
- `o` — overwrite with the daemon's metadata, insert citekey
- `q` / `<Esc>` — abort entirely (no citekey, no bib write)

## Running tests

```bash
cd nvim
./scripts/run-tests.sh
```

## Troubleshooting

| Symptom | Action |
|---------|--------|
| `:checkhealth` says "no socket file" | `:LocalLibraryDaemon start` |
| `:checkhealth` says "daemon ping failed" | check `~/Library/Application Support/local-library/logs/daemon.log` |
| Hangs on connect | confirm `socket_path` matches daemon (`uv run local-library daemon status`) |
| "DAEMON_UNREACHABLE" notifications | daemon crashed; restart with `:LocalLibraryDaemon start` |
| `<leader>c` does nothing | default keymap may be disabled; see `:help local-library-keymaps` |
| `module 'plenary.async' not found` | install plenary.nvim, or add it to lazy.nvim deps |

## Architecture

The plugin is split into:

- **Transport layer** (`client.lua`) — JSON-RPC over Unix socket, with
  reconnect, per-method timeouts, structured error envelopes.
- **Data layer** (`bibliography.lua`, `selection.lua`, `actions.lua`)
  — pure-ish, UI-agnostic. No Telescope imports.
- **UI layer** (`telescope/_extensions/local_library.lua`,
  `conflict_ui.lua`) — the only modules that import Telescope or
  manipulate scratch buffers.

Future UIs (a non-Telescope picker, a free-text input mode) can reuse
the data layer without touching the daemon. See
`docs/concepts/daemons.md` chapter 8 for the full architectural
discussion.

## License

Same as the parent project.
```

### Step 2: Finalize `nvim/CLAUDE.md`

Edit `nvim/CLAUDE.md`. Bump the freshness date. Update the **Contracts → Guarantees** bullet to:

```markdown
- **Guarantees:** End-to-end claim-driven citation flow. Visual-select
  → `<leader>c` → Telescope picker → insert citekey + auto-append
  bibliography (or open extracted source). Reconnects on dead-channel
  with bounded backoff; per-method timeouts; structured error
  notifications via `notify.from_error`. `:checkhealth local_library`
  surfaces plugin + daemon state. The plugin always passes
  `boost_citekeys` (silent-inert hook); `doc_id` non-null surfaces
  "scoping not yet available" (loud-error hook).
```

Replace the Key Files section with:

```markdown
## Key Files

- `lua/local_library/config.lua` — defaults + `setup` merge
- `lua/local_library/client.lua` — JSON-RPC client, reconnect, timeouts
- `lua/local_library/init.lua` — public API + `cite()` orchestrator
- `lua/local_library/health.lua` — `:checkhealth` hook
- `lua/local_library/selection.lua` — visual-mode capture
- `lua/local_library/bibliography.lua` — frontmatter parse + CSL-JSON I/O + diff
- `lua/local_library/conflict_ui.lua` — scratch-buffer diff resolution
- `lua/local_library/actions.lua` — insert/insert+text/open
- `lua/local_library/notify.lua` — `error_code` → user-facing notification
- `lua/telescope/_extensions/local_library.lua` — Telescope picker (only telescope.* import)
- `plugin/local_library.lua` — auto-loaded user commands + keymap
- `doc/local_library.txt` — vimdoc (`:help local-library`)
```

### Step 3: Complete `src/local_library/daemon/CLAUDE.md`

Bump the freshness date. Replace the **Contracts → Guarantees** bullet:

```markdown
- **Guarantees:** Single-instance daemon with PID file lock + asyncio
  Unix-socket server speaking line-delimited JSON-RPC 2.0. Methods:
  `ping`, `search`, `get_document`. Library wrapped on a single-worker
  ThreadPoolExecutor so sqlite-vec single-thread access is preserved
  while asyncio handles socket I/O concurrently. Structured per-request
  logs at INFO/WARNING/ERROR with method, id, status, duration_ms (and
  error_code on domain errors). Clean shutdown on SIGTERM/SIGINT:
  server closed → socket unlinked → Library closed → PID file removed
  → exit 0. CLI lifecycle via `local-library daemon {start|stop|
  status|restart|run}`. launchd socket-activation forward-compat shim
  in `socket_activation.inherited_socket()`.
```

Replace Key Files with:

```markdown
- `server.py` — main(), asyncio server, signal handling, single-worker
  Library executor, build_dispatcher
- `pid_file.py` — atomic PID write + stale detection + fcntl lock
- `socket_activation.py` — launchd FD-inheritance + manual-bind fallback
- `protocol.py` — JSON-RPC parse + envelope builders (Functional Core)
- `errors.py` — exception → JSON-RPC error envelope translator
- `dispatcher.py` — method registry + async dispatch + structured logging
- `methods.py` — search + get_document handlers + serialization
```

Append a new bullet to Gotchas:

```markdown
- All Library calls must go through `run_on_library_thread(executor, ...)`.
  Never invoke `_library.<anything>()` directly from the asyncio loop —
  it will violate sqlite3's `check_same_thread` and may crash sqlite-vec.
```

### Step 4: Commit

```bash
git add nvim/README.md nvim/CLAUDE.md src/local_library/daemon/CLAUDE.md
git commit -m "docs: polish nvim README, finalize nvim/CLAUDE.md and daemon/CLAUDE.md

nvim/README.md gets full action table, conflict resolution section, and
architecture overview. nvim/CLAUDE.md and daemon/CLAUDE.md updated to
reflect the shipped state across all 7 phases."
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
## Task 5: Project-level docs — `roadmap.md` + top-level `CLAUDE.md`

**Type:** Documentation.

**Files:**
- Modify: `roadmap.md`
- Modify: `CLAUDE.md` (top-level)

### Step 1: Update `roadmap.md`

Read the current `roadmap.md` to find the Neovim Citation Workflow entry. Move it from its current section ("Exploring", "Designed", or similar) to the "Implemented" / "Stable" section. Update the description to:

> Long-running daemon (Python, asyncio, JSON-RPC over UDS) + Lua plugin with Telescope picker. Visual-select claim → daemon-backed semantic search → citation insertion + bibliography auto-append. Three structural hooks for future features (loud-error / silent-inert / architectural).

Cross-reference `docs/concepts/daemons.md` for design background.

### Step 2: Update top-level `CLAUDE.md`

Add to the "Implemented" bullets list:

- `**Long-running daemon**: src/local_library/daemon/ wraps the Library orchestrator behind a Unix-domain-socket JSON-RPC 2.0 server. Single-worker executor preserves sqlite-vec single-thread access. Methods: ping, search, get_document. CLI: local-library daemon {start|stop|status|restart|run}. Forward-compat shim for launchd socket activation.`

- `**Neovim plugin (local-library.nvim)**: nvim/ contains the Lua plugin. Visual-select a claim → <leader>c → Telescope picker → insert citekey + auto-append CSL-JSON to project bibliography. Per-method timeouts, reconnect-with-backoff, error-code-aware notifications. :LocalLibraryDaemon process management; :checkhealth diagnostics.`

Update the freshness date.

### Step 3: Verify all docs reflect reality

```bash
# 8 chapters in concepts doc
grep -c '^## Chapter' docs/concepts/daemons.md

# >=7 cross-references in design doc
grep -c "concepts §" docs/design-plans/2026-04-24-neovim-citation-workflow.md

# Daemon entry point present
grep "local-library-daemon" pyproject.toml

# Plugin tree intact
ls nvim/lua/local_library/ nvim/doc/local_library.txt
```

### Step 3b: Verify cross-reference validity (no dangling links)

Each `concepts §N` reference in the design doc must resolve to a real `## Chapter N` heading; each `See: <file>` reference in the concepts doc must point at a real file. Validate manually:

```bash
# Every "concepts §<N>" referenced should have a matching "## Chapter <N>" heading
for n in $(grep -oE 'concepts §[0-9]+' docs/design-plans/2026-04-24-neovim-citation-workflow.md | grep -oE '[0-9]+' | sort -u); do
  if ! grep -q "^## Chapter $n " docs/concepts/daemons.md; then
    echo "BROKEN REFERENCE: design doc cites concepts §$n but no such chapter exists"
  fi
done

# Every code-file reference in concepts ch. 8 should point at a real file
grep -oE '`[a-z_/]+\.(py|lua)' docs/concepts/daemons.md | tr -d '`' | sort -u | while read -r path; do
  # Some references are "daemon/server.py" (shorthand for src/local_library/...) — accept either form
  if [ ! -f "$path" ] && [ ! -f "src/local_library/$path" ] && [ ! -f "nvim/lua/local_library/$(basename "$path")" ]; then
    echo "POSSIBLY BROKEN PATH: $path (verify manually)"
  fi
done

# Vimdoc tag declarations should each have at least one |tag| reference somewhere
for tag in $(grep -oE '\*[a-z_-]+\*' nvim/doc/local_library.txt | tr -d '*' | sort -u); do
  if ! grep -rq "|$tag|" nvim/doc/ nvim/README.md 2>/dev/null; then
    echo "VIMDOC TAG WITHOUT REFERENCE: $tag (declared but never linked)"
  fi
done
```

Each invocation should produce no output. If any line prints, fix the broken reference before moving on.

### Step 4: Run the full test suite

```bash
uv run pytest tests/unit/daemon/ tests/integration/daemon/ -v
cd nvim && ./scripts/run-tests.sh
```

Expected: all green.

### Step 5: Commit

```bash
git add roadmap.md CLAUDE.md
git commit -m "docs: promote Neovim Citation Workflow to shipped, update top-level CLAUDE.md

Roadmap: feature area moves from Designed to Stable with one-line
summary. Top-level CLAUDE.md gains 'Implemented' bullets for the daemon
and plugin matching the project's existing pattern. Freshness date bumped."
```

### Step 6: Verify Phase 7 "Done when" criteria

- ✓ All 8 concepts chapters exist; each ends with cross-references
- ✓ Design-doc Architecture and Implementation sections link to relevant concepts chapters
- ✓ `:help local-library` works in Neovim
- ✓ Plugin README lets a fresh reader install, configure, and run the first flow without other docs
- ✓ Project `roadmap.md` and top-level `CLAUDE.md` reflect the shipped state
<!-- END_TASK_5 -->
