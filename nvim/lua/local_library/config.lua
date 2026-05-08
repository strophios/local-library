-- pattern: Functional Core (pure transformations on tables)
--
-- Configuration defaults and setup merging.
--
-- The default socket_path is resolved at setup() time (not at module load
-- time) so that XDG_DATA_HOME can be set after Neovim starts (useful for
-- integration tests). Resolution mirrors Python's platformdirs.user_data_dir
-- on macOS:
--   1. $XDG_DATA_HOME/local-library/daemon.sock (if set)
--   2. ~/Library/Application Support/local-library/daemon.sock (default)

local M = {}

M.defaults = {
  socket_path = nil,
  request_timeout_ms = 5000,
  keymaps = {
    enabled = true,
    visual_cite = "<leader>c",
  },
  search = {
    limit = 10,
    rerank = true,
  },
}

-- Lazy-loaded per-method timeout defaults (only merged if user doesn't provide timeouts).
--
-- `search`'s timeout is generous (60s) because the daemon may pay the cold-load
-- penalty for nomic-embed + cross-encoder (~5-30s combined) on a freshly-started
-- daemon — even though `daemon start` warms models eagerly now, a plugin client
-- that reconnects to a daemon someone else just started should still complete
-- its first search rather than time out and surface a confusing error.
M.default_timeouts = {
  default_ms = 5000,
  by_method = {
    ping = 2000,
    get_document = 2000,
    search = 60000,
  },
}

local function default_socket_path()
  local xdg = vim.env.XDG_DATA_HOME
  if xdg and xdg ~= "" then
    return xdg .. "/local-library/daemon.sock"
  end
  local home = vim.env.HOME or "~"
  return home .. "/Library/Application Support/local-library/daemon.sock"
end

--- Merge user options into defaults and store the resolved table on M.options.
---@param opts table|nil
function M.setup(opts)
  opts = opts or {}
  M.options = vim.tbl_deep_extend("force", {}, M.defaults, opts)
  -- Apply per-method timeouts. Backward compat: if user provided request_timeout_ms
  -- but not timeouts, use that value only (no per-method overrides).
  if not opts.timeouts then
    if opts.request_timeout_ms then
      -- User explicitly set request_timeout_ms; use it uniformly
      M.options.timeouts = {
        default_ms = opts.request_timeout_ms,
        by_method = {},
      }
    else
      -- User didn't set either; use full defaults (with per-method overrides)
      M.options.timeouts = vim.tbl_deep_extend("force", {}, M.default_timeouts)
    end
  end
  if not M.options.socket_path then
    M.options.socket_path = default_socket_path()
  end
end

return M
