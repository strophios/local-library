-- pattern: Imperative Shell — orchestrates module lifecycle and exposes
-- the public API surface for the plugin.

local M = {}

local _config_module = require("local_library.config")
local _client = nil
local _setup_done = false

--- Configure the plugin. Idempotent.
---@param opts table|nil
function M.setup(opts)
  _config_module.setup(opts)
  _setup_done = true
  -- Direct keymap registration. The autocmd in plugin/local_library.lua
  -- is a fallback for users who call setup() inside lazy.nvim's `config`
  -- block (autocmd registered before setup runs). Calling vim.keymap.set
  -- twice with identical args is a no-op.
  local opts_resolved = _config_module.options
  if opts_resolved.keymaps and opts_resolved.keymaps.enabled then
    vim.keymap.set("x", opts_resolved.keymaps.visual_cite, ":LocalLibraryCite<CR>",
      { silent = true, desc = "local-library: cite from selection" })
  end
  vim.api.nvim_exec_autocmds("User", { pattern = "LocalLibraryConfigured" })
end

local function _ensure_setup()
  if not _setup_done then
    M.setup({})
  end
end

--- Return the resolved config table.
function M.config()
  _ensure_setup()
  return _config_module.options
end

--- Return the singleton client (lazily constructed; not yet connected).
function M.client()
  _ensure_setup()
  if _client == nil then
    local Client = require("local_library.client")
    _client = Client.new({
      socket_path = _config_module.options.socket_path,
      request_timeout_ms = _config_module.options.request_timeout_ms,
    })
  end
  return _client
end

--- Reset state (used by tests and `:LocalLibraryDaemon restart`).
function M._reset()
  if _client then
    pcall(_client.close, _client)
  end
  _client = nil
  _setup_done = false
end

--- Run the `local-library daemon <subcommand>` Python CLI.
function M.run_daemon_cli(subcommand)
  local cmd = { "uv", "run", "local-library", "daemon", subcommand }
  local out = vim.fn.system(cmd)
  local code = vim.v.shell_error
  if code == 0 then
    vim.notify("local-library: " .. (out:gsub("%s+$", "")), vim.log.levels.INFO)
  else
    vim.notify(
      "local-library daemon " .. subcommand .. " failed:\n" .. out,
      vim.log.levels.ERROR
    )
  end
  return code
end

--- Visual-mode entry point: capture selection, run search, open Telescope picker.
function M.cite()
  local selection = require("local_library.selection")
  local query = selection.get_visual()
  if not query or query == "" then
    vim.notify("local-library: no visual selection", vim.log.levels.WARN)
    return
  end
  local range = selection.get_visual_range()

  local async = require("plenary.async")
  async.run(function()
    local cli = M.client()
    local err, response = cli:request_sync("search", {
      query = query,
      limit = M.config().search.limit,
      rerank = M.config().search.rerank,
    })
    if err then
      vim.notify("local-library: search failed: " .. (err.message or "?"),
        vim.log.levels.ERROR)
      return
    end
    if not response or #(response.results or {}) == 0 then
      vim.notify("local-library: no results for selection", vim.log.levels.INFO)
      return
    end

    local refs_path = require("local_library.bibliography").resolve_refs_path(0)
    vim.schedule(function()
      require("telescope").extensions.local_library.cite({
        results = response.results,
        ctx = {
          end_line = range.end_line,
          end_col = range.end_col,
          refs_path = refs_path,
          bufnr = vim.api.nvim_get_current_buf(),
        },
      })
    end)
  end)
end

return M
