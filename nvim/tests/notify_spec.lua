local stub = require("luassert.stub")

describe("local_library.notify", function()
  local notify
  local notify_calls

  before_each(function()
    package.loaded["local_library.notify"] = nil
    notify = require("local_library.notify")
    notify_calls = {}
    stub(vim, "notify", function(msg, level)
      table.insert(notify_calls, { msg = msg, level = level })
    end)
  end)

  after_each(function() vim.notify:revert() end)

  it("DAEMON_UNREACHABLE produces an actionable ERROR with restart hint", function()
    notify.from_error({ error_code = "DAEMON_UNREACHABLE", message = "boom" })
    assert.equals(1, #notify_calls)
    assert.equals(vim.log.levels.ERROR, notify_calls[1].level)
    assert.is_truthy(notify_calls[1].msg:match(":LocalLibraryDaemon start"))
  end)

  it("NOT_IMPLEMENTED for doc_id surfaces 'scoping not yet available'", function()
    notify.from_error({
      error_code = "NOT_IMPLEMENTED",
      message = "document-scoped search is not yet implemented",
      details = { hook = "doc_id" },
    })
    assert.equals(1, #notify_calls)
    assert.equals(vim.log.levels.WARN, notify_calls[1].level)
    assert.is_truthy(notify_calls[1].msg:match("scoping not yet available"))
  end)

  it("EMBEDDING_EXTENSION_UNAVAILABLE produces an installer hint", function()
    notify.from_error({
      error_code = "EMBEDDING_EXTENSION_UNAVAILABLE",
      message = "sqlite-vec missing",
    })
    assert.equals(vim.log.levels.ERROR, notify_calls[1].level)
    assert.is_truthy(notify_calls[1].msg:match("sqlite%-vec"))
  end)

  it("NOT_FOUND with suggestions formats 'did you mean...'", function()
    notify.from_error({
      error_code = "NOT_FOUND",
      message = "no such doc",
      details = { identifier = "@Smyth", suggestions = { "Smith2023", "Schmidt2021" } },
    })
    assert.is_truthy(notify_calls[1].msg:match("Smith2023"))
    assert.is_truthy(notify_calls[1].msg:match("Schmidt2021"))
  end)

  it("unknown error code falls back to message + ERROR level", function()
    notify.from_error({ error_code = "BIZARRE_NEW_CODE", message = "weird" })
    assert.equals(vim.log.levels.ERROR, notify_calls[1].level)
    assert.is_truthy(notify_calls[1].msg:match("weird"))
  end)

  it("nil error_code (transport-layer error like timeout) uses code-based fallback", function()
    notify.from_error({ code = -2, message = "request 'search' timed out after 5000ms" })
    assert.equals(vim.log.levels.ERROR, notify_calls[1].level)
    assert.is_truthy(notify_calls[1].msg:match("timed out"))
  end)
end)
