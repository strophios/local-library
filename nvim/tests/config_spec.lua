-- Tests for local_library.config defaults + setup merging.

local function reload(modname)
  package.loaded[modname] = nil
  return require(modname)
end

describe("local_library.config", function()
  local config

  before_each(function()
    config = reload("local_library.config")
  end)

  it("provides a defaults table", function()
    assert.is_table(config.defaults)
    assert.is_number(config.defaults.request_timeout_ms)
  end)

  it("resolves a default socket path", function()
    config.setup({})
    assert.is_string(config.options.socket_path)
    assert.is_truthy(config.options.socket_path:match("daemon%.sock$"))
  end)

  it("honors XDG_DATA_HOME when present", function()
    local prev = vim.env.XDG_DATA_HOME
    vim.env.XDG_DATA_HOME = "/tmp/xdg-test-home"
    config = reload("local_library.config")
    config.setup({})
    assert.equals(
      "/tmp/xdg-test-home/local-library/daemon.sock",
      config.options.socket_path
    )
    vim.env.XDG_DATA_HOME = prev
  end)

  it("falls back to macOS Application Support when XDG_DATA_HOME is unset", function()
    local prev = vim.env.XDG_DATA_HOME
    vim.env.XDG_DATA_HOME = nil
    config = reload("local_library.config")
    config.setup({})
    assert.is_truthy(
      config.options.socket_path:match("Application Support/local%-library/daemon%.sock$")
    )
    vim.env.XDG_DATA_HOME = prev
  end)

  it("setup overrides take precedence over defaults", function()
    config.setup({ socket_path = "/custom/path", request_timeout_ms = 12345 })
    assert.equals("/custom/path", config.options.socket_path)
    assert.equals(12345, config.options.request_timeout_ms)
  end)

  it("setup merges deeply (does not drop unspecified fields)", function()
    config.setup({ request_timeout_ms = 99 })
    assert.is_truthy(config.options.socket_path)
    assert.equals(99, config.options.request_timeout_ms)
  end)

  it("default search timeout accommodates daemon model warmup", function()
    -- Defense in depth: even though the daemon now warms models during
    -- `daemon start`, a fresh daemon that the plugin reconnects to
    -- mid-session may still pay the cold-load penalty before processing
    -- the first request. The default per-method timeout for `search`
    -- must accommodate that worst case (~30s for nomic + cross-encoder).
    config.setup({})
    local search_timeout = config.options.timeouts.by_method.search
    assert.is_number(search_timeout)
    assert.is_truthy(
      search_timeout >= 30000,
      "default search timeout " .. tostring(search_timeout)
        .. "ms is too low for cold-load fallback (need >= 30000ms)"
    )
  end)
end)
