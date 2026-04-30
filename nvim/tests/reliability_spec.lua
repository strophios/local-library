local function command_available(cmd)
  local h = io.popen("command -v " .. cmd .. " 2>/dev/null")
  if not h then return false end
  local r = h:read("*l"); h:close()
  return r ~= nil and r ~= ""
end

describe("reliability tier 1", function()
  local tmp_dir, socket_path, daemon_pid

  local function spawn_daemon()
    local pid = vim.fn.jobstart({ "uv", "run", "local-library-daemon" }, {
      env = vim.tbl_extend("force", vim.fn.environ(), {
        XDG_DATA_HOME = tmp_dir,
        LOCAL_LIBRARY_DATA_DIR = tmp_dir .. "/local-library",
        -- Skip model warmup: tier-1 reliability tests only exercise transport
        -- (kill/restart/reconnect), not search. Loading the embedder +
        -- reranker would exceed the kill/ping timeout windows.
        LOCAL_LIBRARY_DAEMON_SKIP_WARMUP = "1",
      }),
      detach = true,
    })
    local deadline = vim.loop.hrtime() + 30 * 1e9
    while vim.loop.hrtime() < deadline do
      if vim.fn.getftype(socket_path) == "socket" then return pid end
      vim.wait(100)
    end
    return pid
  end

  before_each(function()
    if not command_available("uv") then pending("uv not available"); return end
    tmp_dir = "/tmp/ll-rel-" .. math.random(100000, 999999)
    vim.fn.mkdir(tmp_dir .. "/local-library", "p")
    vim.env.XDG_DATA_HOME = tmp_dir
    vim.env.LOCAL_LIBRARY_DATA_DIR = tmp_dir .. "/local-library"
    socket_path = tmp_dir .. "/local-library/daemon.sock"
    daemon_pid = spawn_daemon()
    package.loaded["local_library"] = nil
    require("local_library").setup({ socket_path = socket_path })
  end)

  after_each(function()
    if daemon_pid and daemon_pid > 0 then pcall(vim.fn.jobstop, daemon_pid) end
    vim.env.XDG_DATA_HOME = nil
    vim.env.LOCAL_LIBRARY_DATA_DIR = nil
    -- Clean up temp dir
    pcall(function()
      vim.fn.system({ "rm", "-rf", tmp_dir })
    end)
  end)

  it("ping fails with DAEMON_UNREACHABLE after kill", function()
    pcall(vim.fn.jobstop, daemon_pid)
    daemon_pid = nil
    vim.wait(2000, function() return vim.fn.getftype(socket_path) ~= "socket" end)

    local async = require("plenary.async")
    local err
    async.run(function()
      err, _ = require("local_library").client():ping()
    end)
    vim.wait(3000, function() return err ~= nil end)
    assert.is_table(err)
    assert.equals("DAEMON_UNREACHABLE", err.error_code)
  end)

  it("ping succeeds after kill + restart via reconnect", function()
    pcall(vim.fn.jobstop, daemon_pid)
    daemon_pid = nil
    vim.wait(2000, function() return vim.fn.getftype(socket_path) ~= "socket" end)
    daemon_pid = spawn_daemon()

    local async = require("plenary.async")
    local result, err
    async.run(function()
      err, result = require("local_library").client():ping()
    end)
    vim.wait(5000, function() return err ~= nil or result ~= nil end)
    assert.is_nil(err, err and err.message or "")
    assert.is_true(result.ok)
  end)
end)
