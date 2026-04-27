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
  if sub == "restart" then
    require("local_library")._reset()
  end
  require("local_library").run_daemon_cli(sub)
end, {
  nargs = "?",
  complete = function() return { "start", "stop", "status", "restart" } end,
})
