# local-library.nvim

Neovim plugin for claim-driven semantic search against the local-library
corpus. Visual-select a claim → daemon-backed retrieval → Telescope
picker → insert citekey + auto-append to your bibliography.

This is **Phase 4** scaffolding. The full citation flow (Telescope picker,
auto-append, conflict resolution) ships in Phase 5.

## Requirements

- Neovim 0.10+
- The local-library daemon (`local-library daemon start`)
- plenary.nvim on the runtime path (transitive dep via Telescope)

## Installation (lazy.nvim, local development)

```lua
{
  dir = "~/development/local-library/nvim",
  name = "local-library.nvim",
  dependencies = { "nvim-lua/plenary.nvim" },
  lazy = false,
  config = function()
    require("local_library").setup({
      -- socket_path = "...",  -- override default; see :checkhealth output
    })
  end,
}
```

## Quickstart

```vim
:LocalLibraryDaemon start    " starts the Python daemon (one-time per session)
:checkhealth local_library   " confirms daemon is reachable
:LocalLibraryDaemon status   " pid, socket, uptime, resident memory
```

## Configuration defaults

```lua
{
  socket_path = nil,  -- nil → resolve from $XDG_DATA_HOME or
                      --        ~/Library/Application Support/local-library/daemon.sock
  request_timeout_ms = 5000,
}
```

## Running tests

```bash
cd nvim
./scripts/run-tests.sh
```

## Troubleshooting

| Symptom | Action |
|---------|--------|
| `:checkhealth` says "daemon not running" | `:LocalLibraryDaemon start` |
| Hangs on connect | check that `socket_path` matches what the daemon binds (`uv run local-library daemon status` from a shell) |
| "module 'plenary.async' not found" | install plenary.nvim, or add it to `dependencies` in lazy spec |
