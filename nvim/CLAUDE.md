# Neovim Plugin Domain

Last verified: 2026-04-24

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
- **Guarantees (Phase 4 only):** The plugin loads under lazy.nvim, can
  ping the daemon over the configured socket path, surfaces daemon
  status via `:checkhealth`, and shells out to the Python CLI for
  `:LocalLibraryDaemon` lifecycle commands.
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

## Key Files

- `lua/local_library/config.lua` — defaults + `setup` merge
- `lua/local_library/client.lua` — JSON-RPC client over UDS
- `lua/local_library/init.lua` — public surface
- `lua/local_library/health.lua` — `:checkhealth`
- `plugin/local_library.lua` — auto-loaded user commands

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
