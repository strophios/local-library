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

## Installation (lazy.nvim, from github)

```lua
{
  "strophios/local-library",
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

The plugin code lives in the `nvim/` subdirectory of the repository, but
top-level symlinks (`lua → nvim/lua`, `plugin → nvim/plugin`,
`doc → nvim/doc`) make it installable by any plugin manager that follows
the standard runtimepath conventions. No `subdir` workaround needed.

You'll also need the local-library Python package and its daemon — see
the parent project's README for installation. The Neovim plugin needs
`local-library-daemon` (or `uv run local-library-daemon`) discoverable on
PATH so `:LocalLibraryDaemon start` can spawn it.

### Local development (working on the plugin itself)

If you're hacking on the plugin code directly, point at your checkout:

```lua
{
  dir = "~/development/local-library",  -- repo root, not nvim/
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
