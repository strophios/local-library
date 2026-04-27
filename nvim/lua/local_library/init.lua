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

return M
