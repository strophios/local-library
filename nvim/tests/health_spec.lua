local stub = require("luassert.stub")

describe("local_library.health", function()
  local health_calls
  local sockconnect_stub
  local chansend_stub

  before_each(function()
    health_calls = { start = {}, ok = {}, warn = {}, error = {}, info = {} }
    for _, level in ipairs({ "start", "ok", "warn", "error", "info" }) do
      stub(vim.health, level, function(...)
        table.insert(health_calls[level], { ... })
      end)
    end

    sockconnect_stub = stub(vim.fn, "sockconnect").returns(99)
    chansend_stub = stub(vim.fn, "chansend").returns(1)
    stub(vim.fn, "chanclose").returns(1)
    stub(vim.api, "nvim_get_chan_info").returns({ id = 99 })
    stub(vim.fn, "getftype").returns("socket")

    package.loaded["local_library"] = nil
    package.loaded["local_library.health"] = nil
    package.loaded["local_library.client"] = nil
    require("local_library").setup({ socket_path = "/tmp/test.sock" })
  end)

  after_each(function()
    for _, level in ipairs({ "start", "ok", "warn", "error", "info" }) do
      vim.health[level]:revert()
    end
    sockconnect_stub:revert()
    chansend_stub:revert()
    vim.fn.chanclose:revert()
    vim.api.nvim_get_chan_info:revert()
    vim.fn.getftype:revert()
    require("local_library")._reset()
  end)

  it("reports OK when daemon ping succeeds", function()
    local client = require("local_library").client()
    stub(client, "ping", function()
      return nil, { ok = true, daemon_pid = 123, uptime_seconds = 1.5, library_version = "0.1.0" }
    end)
    local async = require("plenary.async")
    async.run(function()
      require("local_library.health").check()
    end)
    vim.wait(200, function() return #health_calls.ok > 0 end)
    assert.is_truthy(#health_calls.ok > 0)
    assert.is_truthy(#health_calls.error == 0)
  end)

  it("reports ERROR when daemon ping returns an error", function()
    local client = require("local_library").client()
    stub(client, "ping", function()
      return { code = -1, message = "channel send failed" }, nil
    end)
    local async = require("plenary.async")
    async.run(function()
      require("local_library.health").check()
    end)
    vim.wait(200, function() return #health_calls.error > 0 end)
    assert.is_truthy(#health_calls.error > 0)
  end)
end)
