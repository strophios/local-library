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
  if not M.options.socket_path then
    M.options.socket_path = default_socket_path()
  end
end

return M
