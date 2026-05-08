local function reload(modname)
  package.loaded[modname] = nil
  return require(modname)
end

describe("local_library.init", function()
  before_each(function()
    package.loaded["local_library"] = nil
    package.loaded["local_library.config"] = nil
    package.loaded["local_library.client"] = nil
  end)

  it("setup is idempotent", function()
    local lib = reload("local_library")
    lib.setup({})
    lib.setup({})
    assert.is_table(lib.config())
  end)

  it("setup honors socket_path override", function()
    local lib = reload("local_library")
    lib.setup({ socket_path = "/custom/sock" })
    assert.equals("/custom/sock", lib.config().socket_path)
  end)

  it("client() returns a singleton client", function()
    local lib = reload("local_library")
    lib.setup({})
    local c1 = lib.client()
    local c2 = lib.client()
    assert.equals(c1, c2)
  end)

  it("run_daemon_cli('stop') drops the cached client so the next call reconnects", function()
    -- Regression: stop+start (or any lifecycle subcommand) must invalidate
    -- the singleton client. Otherwise the next request reuses the chan_id
    -- that points at the previous daemon's now-closed socket; depending on
    -- how quickly Neovim updates channel state after the remote closes,
    -- request_async may either send into the void (response never arrives →
    -- timeout) or correctly reconnect. Don't depend on the race.
    local stub = require("luassert.stub")
    local lib = reload("local_library")
    lib.setup({})

    -- Stub the transport so client() instantiation doesn't actually
    -- touch the socket; we only care about object identity here.
    stub(vim.fn, "sockconnect").returns(42)
    stub(vim.api, "nvim_get_chan_info").returns({ id = 42 })
    stub(vim.fn, "chanclose").returns(1)

    local c1 = lib.client()
    assert.is_truthy(c1)

    -- Force vim.v.shell_error = 0 by running a real fast successful command,
    -- then stub vim.fn.system to return empty output. The stub does not
    -- update vim.v.shell_error, so the prior 0 persists.
    vim.fn.system("true")
    assert.equals(0, vim.v.shell_error)
    stub(vim.fn, "system", function() return "" end)
    stub(vim, "notify")

    lib.run_daemon_cli("stop")

    local c2 = lib.client()
    assert.is_not.equals(c1, c2)

    vim.fn.sockconnect:revert()
    vim.api.nvim_get_chan_info:revert()
    vim.fn.chanclose:revert()
    vim.fn.system:revert()
    vim.notify:revert()
  end)

  it("run_daemon_cli('status') preserves the cached client", function()
    -- Status is a query, not a state change. Resetting the client on
    -- status would churn connections for no reason.
    local stub = require("luassert.stub")
    local lib = reload("local_library")
    lib.setup({})

    stub(vim.fn, "sockconnect").returns(42)
    stub(vim.api, "nvim_get_chan_info").returns({ id = 42 })

    local c1 = lib.client()
    vim.fn.system("true")
    stub(vim.fn, "system", function() return "" end)
    stub(vim, "notify")

    lib.run_daemon_cli("status")

    local c2 = lib.client()
    assert.equals(c1, c2)

    vim.fn.sockconnect:revert()
    vim.api.nvim_get_chan_info:revert()
    vim.fn.system:revert()
    vim.notify:revert()
  end)

  it("cite() notifies that the search is in progress", function()
    -- UX: between <leader>c and the picker appearing, the user should see
    -- some evidence that the request is happening. Without this, a cold or
    -- slow daemon makes the editor look frozen.
    local stub = require("luassert.stub")
    package.loaded["local_library.selection"] = nil
    package.loaded["local_library.bibliography"] = nil

    local lib = reload("local_library")
    lib.setup({})

    -- Stub the visual capture path so cite() proceeds past the early returns.
    stub(require("local_library.selection"), "get_visual", function() return "test query" end)
    stub(require("local_library.selection"), "get_visual_range", function()
      return { start_line = 1, start_col = 1, end_line = 1, end_col = 10 }
    end)
    stub(require("local_library.bibliography"), "resolve_refs_path", function() return nil end)

    -- Stub the client so request_sync returns an error immediately. We don't
    -- need to drive the full picker flow — only verify the pre-search notify.
    local fake_client = { request_sync = function(_self, _method, _params)
      return { code = -2, message = "stub", error_code = "DAEMON_UNREACHABLE" }, nil
    end }
    stub(lib, "client", function() return fake_client end)

    local notify_calls = {}
    stub(vim, "notify", function(msg, level)
      table.insert(notify_calls, { msg = msg, level = level })
    end)

    lib.cite()
    -- async.run schedules; let it drain.
    vim.wait(200, function() return #notify_calls >= 1 end)

    local saw_searching = false
    for _, c in ipairs(notify_calls) do
      if c.msg:lower():match("search") then
        saw_searching = true
      end
    end
    assert.is_true(saw_searching,
      "expected a 'searching' notify before/during the request")

    vim.notify:revert()
    require("local_library.selection").get_visual:revert()
    require("local_library.selection").get_visual_range:revert()
    require("local_library.bibliography").resolve_refs_path:revert()
    lib.client:revert()
  end)
end)
