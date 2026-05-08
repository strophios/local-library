# Neovim Citation Workflow Implementation Plan — Phase 4: Plugin Foundation

**Goal:** Stand up the Neovim plugin scaffold so it loads under lazy.nvim, can ping the daemon over a Unix domain socket, surfaces daemon liveness via `:checkhealth local_library`, and shells out to `:LocalLibraryDaemon {start|stop|status|restart}` for process lifecycle management. No retrieval UX yet — that's Phase 5.

**Architecture:** New `nvim/` directory tree. Lua modules under `nvim/lua/local_library/`: `config.lua` (defaults + `setup` merge), `client.lua` (line-delimited JSON-RPC over `vim.fn.sockconnect("pipe", ...)`), `init.lua` (public API + CLI shellout), `health.lua` (`:checkhealth`). Auto-loaded user commands in `nvim/plugin/local_library.lua`. plenary.busted tests in `nvim/tests/`. Telescope extension directory (`nvim/lua/telescope/_extensions/`) created empty — Phase 5 fills it.

**Tech Stack:** Neovim 0.10+, Lua, plenary.nvim (transitive via Telescope; used directly here for `async.wrap` callback→sync conversion + busted-style tests). No new Python-side dependencies.

**Scope:** 4 of 7 phases from `docs/design-plans/2026-04-24-neovim-citation-workflow.md`.

**Codebase verified:** 2026-04-24.

**Executor skills:** `ed3d-house-style:coding-effectively` (FCIS — `client.lua` framing/parse helpers are Functional Core; channel ops are Imperative Shell), `ed3d-plan-and-execute:test-driven-development`, `ed3d-plan-and-execute:verification-before-completion`. The codebase has no Lua linter conventions; if the user has stylua/luacheck configured, the executor uses them — otherwise skip lint for Lua files.

**Important API gotcha:** `vim.fn.sockconnect("pipe", path, ...)` is the correct call for path-based Unix domain sockets in Neovim 0.10+. Despite the misleading mode name, `"unix"` is **not** a valid mode value; `"pipe"` covers both Windows named pipes and Unix domain sockets.

**Test runner environment note (added 2026-04-27 during Phase 4 Task 2):** The plan's `nvim --headless -c "PlenaryBustedFile ..."` invocation only works if plenary.nvim is on the runtimepath. On a system where the default `nvim` config (plain `~/.config/nvim/`) does not have plenary installed, two adaptations are needed:
1. Set `NVIM_APPNAME` to a config that has plenary installed (e.g., `NVIM_APPNAME=nvim-rebuild`), so plenary loads from there.
2. From inside `nvim/`, prepend the plugin's own `lua/` to runtimepath via `--cmd "set rtp+=."` so `require("local_library.config")` resolves.

The full working invocation is therefore: `cd nvim && NVIM_APPNAME=nvim-rebuild nvim --headless --cmd "set rtp+=." -c "PlenaryBustedFile tests/<spec>" -c "qa"`. Task 6's `nvim/scripts/run-tests.sh` should bake in this incantation (or, more portably, add a `tests/minimal_init.lua` that bootstraps plenary from a known location and use `-u tests/minimal_init.lua` so users don't need to set `NVIM_APPNAME`).

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
## Task 1: Plugin directory scaffold + meta files

**Type:** Infrastructure.

**Files:**
- Create: `nvim/CLAUDE.md`
- Create: `nvim/README.md`
- Create: `nvim/.luarc.json`
- Create: `nvim/lua/local_library/.gitkeep`, `nvim/lua/telescope/_extensions/.gitkeep`, `nvim/plugin/.gitkeep`, `nvim/doc/.gitkeep`, `nvim/tests/.gitkeep`

### Step 1: Create directories

```bash
mkdir -p nvim/lua/local_library nvim/lua/telescope/_extensions nvim/plugin nvim/doc nvim/tests nvim/scripts
touch nvim/lua/local_library/.gitkeep nvim/lua/telescope/_extensions/.gitkeep nvim/plugin/.gitkeep nvim/doc/.gitkeep nvim/tests/.gitkeep
```

### Step 2: Write `nvim/CLAUDE.md`

```markdown
# Neovim Plugin Domain

Last verified: 2026-04-24

## Purpose

Lua plugin that connects Neovim to the local-library daemon via a Unix
domain socket and provides claim-driven semantic search over the corpus.
Phase 4 ships the foundation: transport, configuration, health check, and
daemon-management commands. Phase 5 adds the visual-select citation flow
and Telescope picker. Phases 6–7 add reliability and polish.

## Contracts

- **Exposes:** `:LocalLibraryDaemon {start|stop|status|restart}` user
  commands; `require('local_library').setup({...})` for configuration;
  `:checkhealth local_library` diagnostics.
- **Guarantees (Phase 4 only):** The plugin loads under lazy.nvim, can
  ping the daemon over the configured socket path, surfaces daemon
  status via `:checkhealth`, and shells out to the Python CLI for
  `:LocalLibraryDaemon` lifecycle commands.
- **Expects:** Neovim 0.10+; plenary.nvim available on the runtime path
  (transitive dep via Telescope, used directly here for async + tests).
  The daemon (Phase 1+) running, optionally — most commands degrade
  gracefully when the daemon is absent.

## Dependencies

- **Uses:** `vim.fn.sockconnect` (UDS transport), `vim.fn.chansend` /
  `on_data` callback (raw I/O), `vim.fn.json_encode` / `json_decode`
  (JSON), `plenary.async` (callback → sync), `vim.health` (diagnostics).
- **Used by:** End user (via lazy.nvim local-dir spec).
- **Boundary:** UI/data layer split. `client.lua` is transport-only;
  `config.lua`, `health.lua`, `init.lua` know nothing about Telescope.
  The Telescope extension (Phase 5) is the only module that imports
  `telescope.*`.

## Key Decisions

- **`vim.fn.sockconnect("pipe", ...)`** — yes, "pipe" is the correct
  Neovim mode for filesystem-path Unix domain sockets. The name is
  misleading; "unix" is not a valid mode value.
- **`rpc = false`** — we speak line-delimited JSON-RPC, not Neovim's
  msgpack-rpc. Bytes mode + own framing.
- **Default socket path mirrors `platformdirs.user_data_dir`** —
  `$XDG_DATA_HOME/local-library/daemon.sock` if the env var is set,
  otherwise `~/Library/Application Support/local-library/daemon.sock`
  on macOS. User can override via `setup({socket_path = ...})`.

## Invariants

- Every `client.request_sync` either returns a `(err, result)` pair
  inside an `async.run()` context or throws a documented error.
- The transport layer never imports `telescope` — Phase 5's UI must
  stay in `lua/telescope/_extensions/`.
- Public API surface for Phase 4 is `require('local_library').{setup,
  config, client, run_daemon_cli}`. Phase 5 adds `cite()` and friends.

## Key Files

- `lua/local_library/config.lua` — defaults + `setup` merge
- `lua/local_library/client.lua` — JSON-RPC client over UDS
- `lua/local_library/init.lua` — public surface
- `lua/local_library/health.lua` — `:checkhealth`
- `plugin/local_library.lua` — auto-loaded user commands

## Gotchas

- `vim.fn.sockconnect` on Unix takes `mode = "pipe"` despite the name.
- Channels are integer IDs; 0 means "not connected" or "dead." Always
  check `vim.fn.chaninfo(id)` before sending if the channel is reused
  across operations.
- plenary.async functions must be called inside `async.run()` /
  `async.void()` — calling them from a top-level sync context throws
  "must be called from within a coroutine".
- `lazy.nvim` sources `plugin/<name>.lua` automatically when the plugin
  loads. Don't double-call `setup()`; gate it on
  `vim.g.local_library_loaded`.
```

### Step 3: Write `nvim/README.md`

```markdown
# local-library.nvim

Neovim plugin for claim-driven semantic search against the local-library
corpus. Visual-select a claim → daemon-backed retrieval → Telescope
picker → insert citekey + auto-append to your bibliography.

This is **Phase 4** scaffolding. The full citation flow (Telescope picker,
auto-append, conflict resolution) ships in Phase 5.

## Requirements

- Neovim 0.10+
- The local-library daemon (`local-library daemon start`)
- plenary.nvim on the runtime path (transitive dep via Telescope)

## Installation (lazy.nvim, local development)

```lua
{
  dir = "~/development/local-library/nvim",
  name = "local-library.nvim",
  dependencies = { "nvim-lua/plenary.nvim" },
  lazy = false,
  config = function()
    require("local_library").setup({
      -- socket_path = "...",  -- override default; see :checkhealth output
    })
  end,
}
```

## Quickstart

```vim
:LocalLibraryDaemon start    " starts the Python daemon (one-time per session)
:checkhealth local_library   " confirms daemon is reachable
:LocalLibraryDaemon status   " pid, socket, uptime, resident memory
```

## Configuration defaults

```lua
{
  socket_path = nil,  -- nil → resolve from $XDG_DATA_HOME or
                      --        ~/Library/Application Support/local-library/daemon.sock
  request_timeout_ms = 5000,
}
```

## Running tests

```bash
cd nvim
./scripts/run-tests.sh
```

## Troubleshooting

| Symptom | Action |
|---------|--------|
| `:checkhealth` says "daemon not running" | `:LocalLibraryDaemon start` |
| Hangs on connect | check that `socket_path` matches what the daemon binds (`uv run local-library daemon status` from a shell) |
| "module 'plenary.async' not found" | install plenary.nvim, or add it to `dependencies` in lazy spec |
```

### Step 4: Write `nvim/.luarc.json`

```json
{
  "runtime.version": "LuaJIT",
  "diagnostics.globals": ["vim", "describe", "it", "before_each", "after_each", "assert", "pending"],
  "workspace.library": []
}
```

### Step 5: Commit

```bash
git add nvim/
git commit -m "feat(nvim): plugin scaffolding, CLAUDE.md, README, .luarc.json

Empty directory tree for the Neovim plugin: lua/local_library/,
lua/telescope/_extensions/ (Phase 5), plugin/ (auto-load),
doc/ (vimdoc, Phase 7), tests/ (plenary.busted), scripts/.
Domain CLAUDE.md mirrors src/local_library/mcp/CLAUDE.md shape."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
## Task 2: `config.lua` — defaults + setup merge (TDD)

**Type:** Functionality.

**Files:**
- Create: `nvim/tests/config_spec.lua`
- Create: `nvim/lua/local_library/config.lua`

### Step 1: Write failing tests

`nvim/tests/config_spec.lua`:

```lua
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
end)
```

### Step 2: Run failing tests

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/config_spec.lua" -c "qa"
```

Expected: errors because `local_library.config` doesn't exist.

### Step 3: Implement `config.lua`

`nvim/lua/local_library/config.lua`:

```lua
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
```

### Step 4: Run tests, confirm they pass

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/config_spec.lua" -c "qa"
```

Expected: 6 tests pass.

### Step 5: Commit

```bash
git add nvim/lua/local_library/config.lua nvim/tests/config_spec.lua
git commit -m "feat(nvim): config defaults + setup merge with platformdirs-compatible socket path

config.setup() resolves socket_path at call time so XDG_DATA_HOME can be
set after Neovim startup (useful for integration tests). Default mirrors
Python's platformdirs.user_data_dir on macOS:
\$XDG_DATA_HOME/local-library/daemon.sock or
~/Library/Application Support/local-library/daemon.sock."
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
## Task 3: `client.lua` — JSON-RPC over UDS with plenary.async (TDD)

**Type:** Functionality. The most substantial Phase 4 task.

**Files:**
- Create: `nvim/tests/client_spec.lua`
- Create: `nvim/lua/local_library/client.lua`

### Step 1: Write failing tests

`nvim/tests/client_spec.lua`:

```lua
-- Tests for local_library.client transport, with stubbed vim.fn calls.

local stub = require("luassert.stub")

local function reload(modname)
  package.loaded[modname] = nil
  return require(modname)
end

describe("local_library.client", function()
  local client
  local sockconnect_stub
  local chansend_stub
  local chanclose_stub
  local captured_on_data

  before_each(function()
    captured_on_data = nil
    sockconnect_stub = stub(vim.fn, "sockconnect", function(_mode, _addr, opts)
      captured_on_data = opts.on_data
      return 42
    end)
    chansend_stub = stub(vim.fn, "chansend").returns(1)
    chanclose_stub = stub(vim.fn, "chanclose").returns(1)
    stub(vim.fn, "chaninfo").returns({ id = 42 })
    client = reload("local_library.client").new({
      socket_path = "/tmp/test.sock",
      request_timeout_ms = 1000,
    })
  end)

  after_each(function()
    sockconnect_stub:revert()
    chansend_stub:revert()
    chanclose_stub:revert()
    vim.fn.chaninfo:revert()
    package.loaded["local_library.client"] = nil
  end)

  it("connect calls sockconnect with mode='pipe' and rpc=false", function()
    client:connect()
    assert.stub(sockconnect_stub).was_called(1)
    local call_args = sockconnect_stub.calls[1].refs
    assert.equals("pipe", call_args[1])
    assert.equals("/tmp/test.sock", call_args[2])
    assert.is_false(call_args[3].rpc)
    assert.is_function(call_args[3].on_data)
  end)

  it("connect raises when sockconnect returns 0", function()
    sockconnect_stub:revert()
    sockconnect_stub = stub(vim.fn, "sockconnect").returns(0)
    assert.has_error(function() client:connect() end, nil)
  end)

  it("request_sync sends JSON-RPC envelope and resolves on matching response", function()
    client:connect()
    local async = require("plenary.async")
    local result, err
    async.run(function()
      err, result = client:request_sync("ping", {})
    end)
    captured_on_data(42, { '{"jsonrpc":"2.0","id":1,"result":{"ok":true}}', "" })
    vim.wait(100, function() return result ~= nil or err ~= nil end)
    assert.is_nil(err)
    assert.is_table(result)
    assert.is_true(result.ok)
    assert.stub(chansend_stub).was_called(1)
    local sent = chansend_stub.calls[1].refs[2]
    local decoded = vim.fn.json_decode(sent)
    assert.equals("2.0", decoded.jsonrpc)
    assert.equals(1, decoded.id)
    assert.equals("ping", decoded.method)
    assert.is_truthy(sent:sub(-1) == "\n")
  end)

  it("request_sync returns (err, nil) on JSON-RPC error envelope", function()
    client:connect()
    local async = require("plenary.async")
    local result, err
    async.run(function()
      err, result = client:request_sync("ping", {})
    end)
    captured_on_data(42, {
      '{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"Method not found"}}',
      "",
    })
    vim.wait(100, function() return err ~= nil end)
    assert.is_table(err)
    assert.equals(-32601, err.code)
    assert.equals("Method not found", err.message)
    assert.is_nil(result)
  end)

  it("request_sync surfaces data.error_code when present", function()
    client:connect()
    local async = require("plenary.async")
    local result, err
    async.run(function()
      err, result = client:request_sync("get_document", { identifier = "@xyz" })
    end)
    captured_on_data(42, {
      '{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"not found",'
        .. '"data":{"error_code":"NOT_FOUND","details":{"identifier":"@xyz"}}}}',
      "",
    })
    vim.wait(100, function() return err ~= nil end)
    assert.equals("NOT_FOUND", err.error_code)
    assert.equals("@xyz", err.details.identifier)
  end)

  it("ping helper wraps request_sync('ping', {})", function()
    client:connect()
    local async = require("plenary.async")
    local result
    async.run(function()
      _, result = client:ping()
    end)
    captured_on_data(42, { '{"jsonrpc":"2.0","id":1,"result":{"ok":true,"daemon_pid":99}}', "" })
    vim.wait(100, function() return result ~= nil end)
    assert.is_true(result.ok)
    assert.equals(99, result.daemon_pid)
  end)

  it("close calls chanclose and resets state", function()
    client:connect()
    client:close()
    assert.stub(chanclose_stub).was_called_with(42)
  end)

  it("handles fragmented on_data callbacks (single line split across chunks)", function()
    client:connect()
    local async = require("plenary.async")
    local result
    async.run(function()
      _, result = client:ping()
    end)
    captured_on_data(42, { '{"jsonrpc":"2.0","id":1,"resu' })
    captured_on_data(42, { 'lt":{"ok":true}}', "" })
    vim.wait(100, function() return result ~= nil end)
    assert.is_true(result.ok)
  end)
end)
```

### Step 2: Run failing tests

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/client_spec.lua" -c "qa"
```

Expected: errors — module doesn't exist.

### Step 3: Implement `client.lua`

`nvim/lua/local_library/client.lua`:

```lua
-- pattern: Mixed
--   Functional Core: encode_request, _split_complete_lines (pure)
--   Imperative Shell: connect/close/send (vim.fn.sockconnect, chansend)
--
-- JSON-RPC 2.0 client over a Unix domain socket.
--
-- Wire protocol: line-delimited compact JSON (each message terminated by 0x0A).
-- Neovim's sockconnect with rpc=false delivers raw bytes via the on_data
-- callback; we accumulate fragments, split on newlines, parse complete lines,
-- and dispatch each response to the matching pending request.

local async = require("plenary.async")

local M = {}
local Client = {}
Client.__index = Client

--- Construct a new client (does not connect).
---@param opts {socket_path: string, request_timeout_ms: number?}
function M.new(opts)
  local self = setmetatable({}, Client)
  self.socket_path = assert(opts.socket_path, "socket_path is required")
  self.request_timeout_ms = opts.request_timeout_ms or 5000
  self.chan_id = nil
  self._buffer = ""
  self._next_id = 0
  self._pending = {}
  return self
end

local function _split_complete_lines(buffer)
  local lines = {}
  local start = 1
  while true do
    local nl = buffer:find("\n", start, true)
    if not nl then break end
    table.insert(lines, buffer:sub(start, nl - 1))
    start = nl + 1
  end
  return lines, buffer:sub(start)
end

function Client:_on_data(_chan_id, data, _event)
  for _, fragment in ipairs(data) do
    self._buffer = self._buffer .. fragment
  end
  local lines, remainder = _split_complete_lines(self._buffer)
  self._buffer = remainder
  for _, line in ipairs(lines) do
    if line ~= "" then
      self:_dispatch(line)
    end
  end
end

function Client:_dispatch(line)
  local ok, msg = pcall(vim.fn.json_decode, line)
  if not ok or type(msg) ~= "table" then
    vim.notify(
      "local-library: malformed daemon response: " .. tostring(line),
      vim.log.levels.WARN
    )
    return
  end
  local cb = self._pending[msg.id]
  if not cb then return end
  self._pending[msg.id] = nil
  if msg.error then
    local err = {
      code = msg.error.code,
      message = msg.error.message,
      error_code = (msg.error.data or {}).error_code,
      details = (msg.error.data or {}).details,
    }
    cb(err, nil)
  else
    cb(nil, msg.result)
  end
end

--- Open the socket; raises on failure.
function Client:connect()
  local opts = {
    rpc = false,
    on_data = function(chan, data, event)
      self:_on_data(chan, data, event)
    end,
  }
  local id = vim.fn.sockconnect("pipe", self.socket_path, opts)
  if id == 0 then
    error("local-library: failed to connect to " .. self.socket_path)
  end
  self.chan_id = id
end

function Client:_is_alive()
  if not self.chan_id then return false end
  local info = vim.fn.chaninfo(self.chan_id)
  return next(info) ~= nil
end

--- Send a request; invoke `cb(err, result)` when the response arrives.
function Client:request_async(method, params, cb)
  if not self:_is_alive() then
    self:connect()
  end
  self._next_id = self._next_id + 1
  local id = self._next_id
  local envelope = vim.fn.json_encode({
    jsonrpc = "2.0",
    id = id,
    method = method,
    params = params or vim.empty_dict(),
  }) .. "\n"
  self._pending[id] = cb
  local sent = vim.fn.chansend(self.chan_id, envelope)
  if sent == 0 then
    self._pending[id] = nil
    cb({ code = -1, message = "channel send failed (daemon disconnected?)" }, nil)
    return
  end
  vim.defer_fn(function()
    if self._pending[id] then
      self._pending[id] = nil
      cb({ code = -2, message = "request timed out after "
        .. self.request_timeout_ms .. "ms" }, nil)
    end
  end, self.request_timeout_ms)
end

--- plenary.async wrapper: returns (err, result) inside async.run() context.
Client.request_sync = async.wrap(function(self, method, params, cb)
  self:request_async(method, params, function(err, result)
    cb(err, result)
  end)
end, 4)

--- Convenience: ping the daemon. Returns (err, result).
function Client:ping()
  return self:request_sync("ping", {})
end

function Client:close()
  if self.chan_id then
    pcall(vim.fn.chanclose, self.chan_id)
    self.chan_id = nil
  end
  self._pending = {}
  self._buffer = ""
end

return M
```

### Step 4: Run tests, confirm they pass

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/client_spec.lua" -c "qa"
```

Expected: 8 tests pass.

### Step 5: Commit

```bash
git add nvim/lua/local_library/client.lua nvim/tests/client_spec.lua
git commit -m "feat(nvim): JSON-RPC client over Unix-domain socket with plenary.async

Connects via vim.fn.sockconnect('pipe', path, {rpc=false}); buffers raw
bytes from the on_data callback, splits on newline, dispatches each
complete envelope to the matching pending request. data.error_code and
data.details are hoisted onto the err table for ergonomic client branching.
request_async takes a callback; request_sync wraps it via plenary.async
for linear (err, result) returns inside async.run() / async.void()."
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
## Task 4: `init.lua` + `plugin/local_library.lua` + `:LocalLibraryDaemon`

**Type:** Functionality + infrastructure.

**Files:**
- Create: `nvim/lua/local_library/init.lua`
- Create: `nvim/plugin/local_library.lua`
- Create: `nvim/tests/init_spec.lua`

### Step 1: Write failing tests

`nvim/tests/init_spec.lua`:

```lua
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
end)
```

### Step 2: Implement `init.lua`

`nvim/lua/local_library/init.lua`:

```lua
-- pattern: Imperative Shell — orchestrates module lifecycle and exposes
-- the public API surface for the plugin.

local M = {}

local _config_module = require("local_library.config")
local _client = nil
local _setup_done = false

--- Configure the plugin. Idempotent.
---@param opts table|nil
function M.setup(opts)
  _config_module.setup(opts)
  _setup_done = true
end

local function _ensure_setup()
  if not _setup_done then
    M.setup({})
  end
end

--- Return the resolved config table.
function M.config()
  _ensure_setup()
  return _config_module.options
end

--- Return the singleton client (lazily constructed; not yet connected).
function M.client()
  _ensure_setup()
  if _client == nil then
    local Client = require("local_library.client")
    _client = Client.new({
      socket_path = _config_module.options.socket_path,
      request_timeout_ms = _config_module.options.request_timeout_ms,
    })
  end
  return _client
end

--- Reset state (used by tests and `:LocalLibraryDaemon restart`).
function M._reset()
  if _client then
    pcall(_client.close, _client)
  end
  _client = nil
  _setup_done = false
end

--- Run the `local-library daemon <subcommand>` Python CLI.
function M.run_daemon_cli(subcommand)
  local cmd = { "uv", "run", "local-library", "daemon", subcommand }
  local out = vim.fn.system(cmd)
  local code = vim.v.shell_error
  if code == 0 then
    vim.notify("local-library: " .. (out:gsub("%s+$", "")), vim.log.levels.INFO)
  else
    vim.notify(
      "local-library daemon " .. subcommand .. " failed:\n" .. out,
      vim.log.levels.ERROR
    )
  end
  return code
end

return M
```

### Step 3: Implement `plugin/local_library.lua`

`nvim/plugin/local_library.lua`:

```lua
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
```

### Step 4: Run tests

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/init_spec.lua" -c "qa"
```

Expected: 3 tests pass.

### Step 5: Manual verification

After installing the plugin per `nvim/README.md`:

```vim
:LocalLibraryDaemon status
```

Expected: shells out to `uv run local-library daemon status`, prints the daemon table or "daemon not running."

```vim
:lua print(vim.inspect(require('local_library').config()))
```

Expected: prints the resolved config including the default `socket_path`.

### Step 6: Commit

```bash
git add nvim/lua/local_library/init.lua nvim/plugin/local_library.lua nvim/tests/init_spec.lua
git commit -m "feat(nvim): public API surface + auto-loaded :LocalLibraryDaemon command

init.lua exposes setup(), config(), client() (singleton, lazily constructed),
and run_daemon_cli() which shells out to 'uv run local-library daemon <cmd>'.
plugin/local_library.lua registers :LocalLibraryDaemon {start|stop|status|restart}
with completion. Setup is idempotent and lazy — modules don't load until a
command runs."
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
## Task 5: `:checkhealth local_library`

**Type:** Functionality.

**Files:**
- Create: `nvim/lua/local_library/health.lua`
- Create: `nvim/tests/health_spec.lua`

### Step 1: Write failing tests

`nvim/tests/health_spec.lua`:

```lua
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
    stub(vim.fn, "chaninfo").returns({ id = 99 })

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
    vim.fn.chaninfo:revert()
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
```

### Step 2: Implement `health.lua`

`nvim/lua/local_library/health.lua`:

```lua
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
```

### Step 3: Run tests + manual verification

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/health_spec.lua" -c "qa"
```

Expected: 2 tests pass.

Manual smoke test (with the daemon running):

```vim
:checkhealth local_library
```

Expected: report shows OK for plugin loaded, socket present, daemon responding (with pid/uptime/version). Stop the daemon and re-run; expect WARN on socket missing.

### Step 4: Commit

```bash
git add nvim/lua/local_library/health.lua nvim/tests/health_spec.lua
git commit -m "feat(nvim): :checkhealth local_library reports plugin + daemon state

Three checks: plugin module loads, socket file exists at the configured
path, daemon responds to ping. Each check produces a vim.health.{ok,warn,error}
report with actionable advice when failures occur."
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
## Task 6: End-to-end smoke test against a real daemon + Phase 4 close

**Type:** Verification.

**Files:**
- Create: `nvim/tests/integration_spec.lua`
- Create: `nvim/scripts/run-tests.sh`

### Step 1: Write the integration test

`nvim/tests/integration_spec.lua`:

```lua
-- Integration test: spawn a real daemon (subprocess), connect from Neovim,
-- verify ping roundtrip end-to-end through the actual transport stack.
-- Skipped when uv/local-library aren't on PATH.

local function command_available(cmd)
  local handle = io.popen("command -v " .. cmd .. " 2>/dev/null")
  if not handle then return false end
  local result = handle:read("*l")
  handle:close()
  return result ~= nil and result ~= ""
end

describe("end-to-end daemon roundtrip", function()
  local data_dir
  local socket_path
  local daemon_pid

  before_each(function()
    if not command_available("uv") then
      pending("uv not available; skipping integration test")
      return
    end
    data_dir = vim.fn.tempname() .. "-data"
    vim.fn.mkdir(data_dir .. "/local-library", "p")
    vim.env.XDG_DATA_HOME = data_dir
    socket_path = data_dir .. "/local-library/daemon.sock"

    daemon_pid = vim.fn.jobstart({
      "uv", "run", "local-library-daemon",
    }, {
      env = vim.tbl_extend("force", vim.fn.environ(), { XDG_DATA_HOME = data_dir }),
      detach = true,
    })
    local deadline = vim.loop.hrtime() + 30 * 1e9
    while vim.loop.hrtime() < deadline do
      if vim.fn.getftype(socket_path) == "socket" then break end
      vim.wait(100)
    end
    assert(vim.fn.getftype(socket_path) == "socket",
      "daemon did not create socket within 30s")
  end)

  after_each(function()
    if daemon_pid and daemon_pid > 0 then
      pcall(vim.fn.jobstop, daemon_pid)
    end
    vim.env.XDG_DATA_HOME = nil
  end)

  it("ping roundtrip via real socket succeeds", function()
    package.loaded["local_library"] = nil
    package.loaded["local_library.client"] = nil
    package.loaded["local_library.config"] = nil
    require("local_library").setup({ socket_path = socket_path })

    local async = require("plenary.async")
    local err, result
    async.run(function()
      err, result = require("local_library").client():ping()
    end)
    vim.wait(5000, function() return err ~= nil or result ~= nil end)
    assert.is_nil(err, err and err.message or nil)
    assert.is_true(result.ok)
    assert.is_number(result.daemon_pid)
    assert.is_truthy(result.library_version)
  end)
end)
```

### Step 2: Add convenience runner

`nvim/scripts/run-tests.sh`:

```bash
#!/usr/bin/env bash
# Run all plenary-busted specs in nvim/tests/.
set -euo pipefail
cd "$(dirname "$0")/.."
nvim --headless -c "PlenaryBustedDirectory tests/" -c "qa"
```

```bash
chmod +x nvim/scripts/run-tests.sh
```

### Step 3: Run the full plugin test suite

```bash
nvim/scripts/run-tests.sh
```

Expected: all spec files pass (config, client, init, health) + integration spec passes when `uv` is available, otherwise pends.

### Step 4: Verify Phase 4 "Done when" criteria

- ✓ Plugin loads via lazy.nvim local-dir spec — manual verification per `nvim/README.md`
- ✓ `:checkhealth local_library` reports daemon status — Task 5
- ✓ `:LocalLibraryDaemon status` invokes the Python CLI — Task 4
- ✓ Ping helper returns valid response — Task 3 unit + Task 6 integration
- ✓ Plugin unit tests cover connection lifecycle and failure modes — Tasks 2, 3, 4, 5

### Step 5: Commit

```bash
git add nvim/tests/integration_spec.lua nvim/scripts/run-tests.sh
git commit -m "test(nvim): end-to-end daemon roundtrip + run-tests.sh wrapper

Integration spec spawns a real daemon via 'uv run local-library-daemon'
against a tmp XDG_DATA_HOME, connects from Neovim through the full
transport stack, and verifies the ping response shape. Pends when uv
isn't on PATH so CI without uv stays green."
```
<!-- END_TASK_6 -->
