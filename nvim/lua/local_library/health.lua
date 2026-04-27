-- pattern: Imperative Shell — uses vim.health.* I/O and probes the daemon.
--
-- :checkhealth local_library
--
-- Reports: plugin loaded, socket file present, daemon responds to ping.

local M = {}

function M.check()
  vim.health.start("local-library")

  local ok, lib = pcall(require, "local_library")
  if not ok then
    vim.health.error("plugin module not found", { "reinstall the plugin" })
    return
  end
  vim.health.ok("plugin module loaded")

  local cfg = lib.config()
  vim.health.info("socket path: " .. cfg.socket_path)

  if vim.fn.getftype(cfg.socket_path) ~= "socket" then
    vim.health.warn(
      "no socket file at " .. cfg.socket_path,
      { "start the daemon: :LocalLibraryDaemon start" }
    )
    return
  end
  vim.health.ok("socket file present")

  local async = require("plenary.async")
  local err, result
  async.run(function()
    err, result = lib.client():ping()
  end)
  vim.wait(2000, function() return err ~= nil or result ~= nil end)

  if err then
    vim.health.error(
      "daemon ping failed: " .. (err.message or "(no message)"),
      { "check daemon log: ~/Library/Application Support/local-library/logs/daemon.log" }
    )
    return
  end
  if not result or not result.ok then
    vim.health.error("daemon responded but ok=false", {})
    return
  end
  vim.health.ok(string.format(
    "daemon responding (pid=%d, uptime=%.1fs, version=%s)",
    result.daemon_pid or -1,
    result.uptime_seconds or 0.0,
    result.library_version or "?"
  ))
end

return M
