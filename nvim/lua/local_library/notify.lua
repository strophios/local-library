-- pattern: Functional Core (mostly) — maps an error table to a (message, level)
-- pair, then calls vim.notify (the only Imperative bit).
--
-- The error table comes from client.request_sync's first return value:
--   { code = <int>, message = <str>, error_code = <str|nil>, details = <table|nil> }

local M = {}

local HANDLERS = {
  DAEMON_UNREACHABLE = function(err)
    return ("local-library: daemon not running. Start it with :LocalLibraryDaemon start.\n(%s)"):format(
      err.message or ""
    ), vim.log.levels.ERROR
  end,
  NOT_IMPLEMENTED = function(err)
    local hook = (err.details or {}).hook or "feature"
    if hook == "doc_id" then
      return "local-library: scoping not yet available. Running unscoped search instead.",
        vim.log.levels.WARN
    end
    return ("local-library: %s not yet implemented"):format(hook), vim.log.levels.WARN
  end,
  EMBEDDING_EXTENSION_UNAVAILABLE = function(_err)
    return "local-library: sqlite-vec extension unavailable. Reinstall the local-library package.",
      vim.log.levels.ERROR
  end,
  NOT_FOUND = function(err)
    local details = err.details or {}
    local suggestions = details.suggestions or {}
    if #suggestions > 0 then
      local quoted = {}
      for _, s in ipairs(suggestions) do
        table.insert(quoted, "@" .. s)
      end
      return ("local-library: %s. Did you mean: %s?"):format(
        err.message or "not found", table.concat(quoted, ", ")
      ), vim.log.levels.WARN
    end
    return ("local-library: %s"):format(err.message or "not found"),
      vim.log.levels.WARN
  end,
}

--- Translate an error table to a vim.notify call.
function M.from_error(err)
  if err.error_code and HANDLERS[err.error_code] then
    local msg, level = HANDLERS[err.error_code](err)
    vim.notify(msg, level)
    return
  end
  vim.notify(
    "local-library: " .. (err.message or "(no error message)"),
    vim.log.levels.ERROR
  )
end

return M
