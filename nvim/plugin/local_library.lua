-- Auto-loaded on Neovim startup (per :h plugin). Registers user commands
-- without forcing a require of the heavier modules until a command runs.

if vim.g.local_library_loaded then return end
vim.g.local_library_loaded = true

vim.api.nvim_create_user_command("LocalLibraryDaemon", function(opts)
  local sub = opts.args
  if sub == "" or sub == nil then sub = "status" end
  if not vim.tbl_contains({ "start", "stop", "status", "restart" }, sub) then
    vim.notify(
      "usage: :LocalLibraryDaemon {start|stop|status|restart}",
      vim.log.levels.ERROR
    )
    return
  end
  -- run_daemon_cli drops the cached client on lifecycle subcommands
  -- (stop/start/restart) after the subprocess succeeds, so the next
  -- request opens a fresh socket. No pre-call reset needed here.
  require("local_library").run_daemon_cli(sub)
end, {
  nargs = "?",
  complete = function() return { "start", "stop", "status", "restart" } end,
})

vim.api.nvim_create_user_command("LocalLibraryCite", function()
  require("local_library").cite()
end, { range = true, desc = "Run claim-driven library search on the visual selection" })

-- Default keymap: <leader>c in visual mode. Registered after setup() runs
-- so user-supplied keymaps.enabled = false is honored.
vim.api.nvim_create_autocmd("User", {
  pattern = "LocalLibraryConfigured",
  callback = function()
    local cfg = require("local_library.config").options
    if cfg.keymaps and cfg.keymaps.enabled then
      vim.keymap.set("x", cfg.keymaps.visual_cite, ":LocalLibraryCite<CR>",
        { silent = true, desc = "local-library: cite from selection" })
    end
  end,
})
