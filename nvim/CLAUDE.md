# Neovim Plugin Domain

Last verified: 2026-05-08

## Purpose

Lua plugin that connects Neovim to the local-library daemon via a Unix
domain socket and provides claim-driven semantic search over the corpus.
Phase 4 ships the foundation: transport, configuration, health check, and
daemon-management commands. Phase 5 adds the visual-select citation flow
and Telescope picker. Phases 6–7 add reliability and polish.

## Contracts

- **Exposes:** `:LocalLibraryDaemon {start|stop|status|restart}` user
  commands; `require('local_library').setup({...})` for configuration;
  `:checkhealth local_library` diagnostics.
- **Guarantees:** End-to-end claim-driven citation flow. Visual-select
  → `<leader>c` → Telescope picker → insert citekey + auto-append
  bibliography (or open extracted source). Reconnects on dead-channel
  with bounded backoff; per-method timeouts; structured error
  notifications via `notify.from_error`. `:checkhealth local_library`
  surfaces plugin + daemon state. The plugin always passes
  `boost_citekeys` (silent-inert hook); `doc_id` non-null surfaces
  "scoping not yet available" (loud-error hook).
- **Expects:** Neovim 0.10+; plenary.nvim available on the runtime path
  (transitive dep via Telescope, used directly here for async + tests).
  The daemon (Phase 1+) running, optionally — most commands degrade
  gracefully when the daemon is absent.

## Dependencies

- **Uses:** `vim.fn.sockconnect` (UDS transport), `vim.fn.chansend` /
  `on_data` callback (raw I/O), `vim.fn.json_encode` / `json_decode`
  (JSON), `plenary.async` (callback → sync), `vim.health` (diagnostics).
- **Used by:** End user (via lazy.nvim local-dir spec).
- **Boundary:** UI/data layer split. `client.lua` is transport-only;
  `config.lua`, `health.lua`, `init.lua` know nothing about Telescope.
  The Telescope extension (Phase 5) is the only module that imports
  `telescope.*`.

## Key Decisions

- **`vim.fn.sockconnect("pipe", ...)`** — yes, "pipe" is the correct
  Neovim mode for filesystem-path Unix domain sockets. The name is
  misleading; "unix" is not a valid mode value.
- **`rpc = false`** — we speak line-delimited JSON-RPC, not Neovim's
  msgpack-rpc. Bytes mode + own framing.
- **Default socket path mirrors `platformdirs.user_data_dir`** —
  `$XDG_DATA_HOME/local-library/daemon.sock` if the env var is set,
  otherwise `~/Library/Application Support/local-library/daemon.sock`
  on macOS. User can override via `setup({socket_path = ...})`.

## Invariants

- Every `client.request_sync` either returns a `(err, result)` pair
  inside an `async.run()` context or throws a documented error.
- The transport layer never imports `telescope` — Phase 5's UI must
  stay in `lua/telescope/_extensions/`.
- Public API surface for Phase 4 is `require('local_library').{setup,
  config, client, run_daemon_cli}`. Phase 5 adds `cite()` and friends.
- `client._on_data` is exception-safe: the buffer state advances
  before any dispatch, and each dispatch is `pcall`-trapped. A throw
  from a registered callback is surfaced via `vim.notify` (WARN) and
  does not corrupt the line buffer or skip subsequent dispatches in
  the same callback batch.
- `actions.insert_citekey` / `insert_citekey_with_text` clamp the
  visual `end_col` to the byte length of the target line. This
  handles both V-mode and `v$` in characterwise mode, where
  `getpos("'>")` returns `v:maxcol` (~2³¹−1).
- `run_daemon_cli` drops the cached client (`_reset_client`) on
  success of any lifecycle subcommand (stop / start / restart) but
  not on `status`. Without this, the singleton client survives daemon
  restarts holding a chan_id that points at the previous daemon's
  closed socket, and subsequent requests can wedge waiting for a
  response that will never arrive. `_reset_client` is narrower than
  `_reset` — it preserves `setup({...})` options across the reset.

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

## Gotchas

- `vim.fn.sockconnect` on Unix takes `mode = "pipe"` despite the name.
- Channels are integer IDs; 0 means "not connected" or "dead." Always
  check `vim.api.nvim_get_chan_info(id)` before sending if the channel is
  reused across operations. Note: `vim.fn.chaninfo` and `vim.fn.getchaninfo`
  both error with E117 on Neovim 0.12.x; only the API form is reliable.
- plenary.async functions must be called inside `async.run()` /
  `async.void()` — calling them from a top-level sync context throws
  "must be called from within a coroutine".
- `lazy.nvim` sources `plugin/<name>.lua` automatically when the plugin
  loads. Don't double-call `setup()`; gate it on
  `vim.g.local_library_loaded`.
