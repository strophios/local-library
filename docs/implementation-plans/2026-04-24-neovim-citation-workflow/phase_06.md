# Neovim Citation Workflow Implementation Plan — Phase 6: Reliability Tier 1 + Hooks Completion

**Goal:** Meet the Phase 6 reliability bar from the design doc. Daemon emits structured per-request logs. Plugin maps `data.error_code` values to user-friendly `vim.notify` messages, reconnects on dead-channel detection with bounded backoff, applies per-method client-side timeouts, routinely sends `boost_citekeys` (silent-inert hook exercised), and surfaces `doc_id` `NOT_IMPLEMENTED` as a clear "scoping not yet available" notification.

**Architecture:** Daemon side — extend `dispatcher.py` to emit per-request log lines (method, status, duration_ms) at INFO level. Plugin side — add per-method timeouts (config-driven), reconnect logic with exponential backoff in `client.lua`, a new `nvim/lua/local_library/notify.lua` module that translates `(err)` tables to user-facing notifications based on `error_code`, and modify `init.lua`'s `cite()` to always include `boost_citekeys = bibliography.list_citekeys(refs_path)`.

**Tech Stack:** No new dependencies. Python `logging`, `time.perf_counter`, Lua `vim.defer_fn` + `vim.loop.hrtime`.

**Scope:** 6 of 7 phases from `docs/design-plans/2026-04-24-neovim-citation-workflow.md`.

**Codebase verified:** 2026-04-24.

**Executor skills:** `ed3d-house-style:coding-effectively`, `ed3d-plan-and-execute:test-driven-development`, `ed3d-plan-and-execute:verification-before-completion`. The daemon work uses `astral:ruff` for lint/format.

**Plan dependencies on prior phases:** Phase 2's `dispatcher.py` extended (not rewritten). Phase 4's `client.lua` adds methods; existing API surface stays compatible. Phase 5's `init.lua:cite()` gets one additional param.

---

<!-- START_TASK_1 -->
## Task 1: Daemon structured per-request logging

**Type:** Functionality.

**Files:**
- Modify: `src/local_library/daemon/dispatcher.py`
- Modify: `tests/unit/daemon/test_dispatcher.py`

### Step 1: Add a failing test

Append to `tests/unit/daemon/test_dispatcher.py`:

```python
def test_dispatch_emits_structured_log_line(caplog) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="local_library.daemon.dispatcher")
    d = dispatcher.Dispatcher()

    async def handler(**_) -> dict:
        return {"ok": True}

    d.register("ping", handler)
    req = protocol.ParsedRequest(method="ping", params={}, id=1)
    _run(d.dispatch(req))

    matching = [r for r in caplog.records
                if r.levelno == logging.INFO and "method=ping" in r.message]
    assert matching, f"expected INFO log for method=ping, got: {[r.message for r in caplog.records]}"
    msg = matching[0].message
    assert "status=ok" in msg
    assert "duration_ms=" in msg


def test_dispatch_logs_error_status_on_local_library_error(caplog) -> None:
    import logging

    caplog.set_level(logging.WARNING, logger="local_library.daemon.dispatcher")
    d = dispatcher.Dispatcher()

    async def handler(**_) -> dict:
        raise LibLookupError(
            "no", ErrorCode.NOT_FOUND, details={"identifier": "@xyz"}
        )

    d.register("get_document", handler)
    req = protocol.ParsedRequest(method="get_document", params={}, id=2)
    _run(d.dispatch(req))

    msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(
        "method=get_document" in m and "error_code=NOT_FOUND" in m
        for m in msgs
    ), msgs
```

### Step 2: Implement structured logging

Add the new module-level imports near the top of `src/local_library/daemon/dispatcher.py` (alongside the existing imports — do NOT import inside the function):

```python
import time

from local_library.core.errors import LocalLibraryError
```

Then modify `Dispatcher.dispatch` in `src/local_library/daemon/dispatcher.py`. Replace the body of the non-notification path with:

```python
        start = time.perf_counter()

        handler = self._methods.get(request.method)
        if handler is None:
            duration_ms = (time.perf_counter() - start) * 1000
            _LOGGER.info(
                "method=%s id=%s status=method_not_found duration_ms=%.1f",
                request.method, request.id, duration_ms,
            )
            return protocol.build_error_response(
                request_id=request.id,
                code=protocol.METHOD_NOT_FOUND,
                message=f"Method not found: {request.method}",
            )

        try:
            result = await handler(**request.params)
        except protocol.JsonRpcError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            _LOGGER.info(
                "method=%s id=%s status=protocol_error code=%d duration_ms=%.1f",
                request.method, request.id, exc.code, duration_ms,
            )
            return errors.translate(request.id, exc)
        except TypeError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            _LOGGER.info(
                "method=%s id=%s status=invalid_params duration_ms=%.1f",
                request.method, request.id, duration_ms,
            )
            return errors.translate(
                request.id,
                protocol.InvalidParams(f"Invalid params: {exc}"),
            )
        except LocalLibraryError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            _LOGGER.warning(
                "method=%s id=%s status=domain_error error_code=%s duration_ms=%.1f",
                request.method, request.id, exc.code.value, duration_ms,
            )
            return errors.translate(request.id, exc)
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.perf_counter() - start) * 1000
            _LOGGER.exception(
                "method=%s id=%s status=internal_error duration_ms=%.1f",
                request.method, request.id, duration_ms,
            )
            return errors.translate(request.id, exc)

        duration_ms = (time.perf_counter() - start) * 1000
        _LOGGER.info(
            "method=%s id=%s status=ok duration_ms=%.1f",
            request.method, request.id, duration_ms,
        )
        return protocol.build_success_response(request.id, result)
```

The notification branch above this stays unchanged.

### Step 3: Run + commit

```bash
uv run pytest tests/unit/daemon/test_dispatcher.py -v
uv run ruff check src/local_library/daemon/dispatcher.py tests/unit/daemon/test_dispatcher.py
git add src/local_library/daemon/dispatcher.py tests/unit/daemon/test_dispatcher.py
git commit -m "feat(daemon): structured per-request logging

Each dispatched request emits one log line with method, id, status,
duration_ms (and error_code when applicable). INFO for normal flow +
protocol/method-not-found errors; WARNING for domain errors; ERROR
(with traceback) for unknown exceptions. Format is key=value for
grep/awk tooling."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
## Task 2: Per-method client timeouts

**Type:** Functionality.

**Files:**
- Modify: `nvim/lua/local_library/config.lua`
- Modify: `nvim/lua/local_library/client.lua`
- Modify: `nvim/lua/local_library/init.lua`
- Modify: `nvim/tests/client_spec.lua`

### Step 1: Update config defaults

In `nvim/lua/local_library/config.lua`, add to `M.defaults`:

```lua
  timeouts = {
    default_ms = 5000,
    by_method = {
      ping = 2000,
      get_document = 2000,
      search = 5000,
    },
  },
```

### Step 2: Add per-method timeout to `client.lua`

Modify `M.new`:

```lua
function M.new(opts)
  local self = setmetatable({}, Client)
  self.socket_path = assert(opts.socket_path, "socket_path is required")
  self.request_timeout_ms = opts.request_timeout_ms or 5000
  self.timeouts = opts.timeouts or {
    default_ms = self.request_timeout_ms,
    by_method = {},
  }
  self.chan_id = nil
  self._buffer = ""
  self._next_id = 0
  self._pending = {}
  return self
end
```

Add the helper:

```lua
function Client:_timeout_for(method)
  local by = self.timeouts.by_method or {}
  return by[method] or self.timeouts.default_ms or self.request_timeout_ms
end
```

In `request_async`, use it in the deferred timeout callback:

```lua
  local timeout_ms = self:_timeout_for(method)
  vim.defer_fn(function()
    if self._pending[id] then
      self._pending[id] = nil
      cb({ code = -2, message = "request '" .. method .. "' timed out after "
        .. timeout_ms .. "ms" }, nil)
    end
  end, timeout_ms)
```

### Step 3: Pass timeouts through `init.lua`

Modify `M.client()`:

```lua
function M.client()
  _ensure_setup()
  if _client == nil then
    local Client = require("local_library.client")
    _client = Client.new({
      socket_path = _config_module.options.socket_path,
      request_timeout_ms = _config_module.options.request_timeout_ms,
      timeouts = _config_module.options.timeouts,
    })
  end
  return _client
end
```

### Step 4: Add a timeout test

Append to `nvim/tests/client_spec.lua`:

```lua
  it("uses per-method timeout from config", function()
    package.loaded["local_library.client"] = nil
    local Client = require("local_library.client")
    local c = Client.new({
      socket_path = "/tmp/test.sock",
      timeouts = {
        default_ms = 5000,
        by_method = { ping = 50 },
      },
    })
    local sc = stub(vim.fn, "sockconnect").returns(7)
    local cs = stub(vim.fn, "chansend").returns(1)
    stub(vim.fn, "chaninfo").returns({ id = 7 })
    local async = require("plenary.async")
    local err
    async.run(function()
      err, _ = c:ping()
    end)
    vim.wait(500, function() return err ~= nil end)
    assert.is_table(err)
    assert.is_truthy(err.message:match("ping"))
    assert.is_truthy(err.message:match("50ms"))
    sc:revert(); cs:revert(); vim.fn.chaninfo:revert()
  end)
```

### Step 5: Run + commit

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/client_spec.lua" -c "qa"
git add nvim/lua/local_library/config.lua nvim/lua/local_library/client.lua nvim/lua/local_library/init.lua nvim/tests/client_spec.lua
git commit -m "feat(nvim): per-method timeouts for client requests

config.timeouts.by_method overrides config.timeouts.default_ms per RPC name.
Defaults: ping=2s, get_document=2s, search=5s. Backwards compatible with
the legacy request_timeout_ms option."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
## Task 3: Reconnect-on-dead-channel with bounded backoff

**Type:** Functionality.

**Files:**
- Modify: `nvim/lua/local_library/client.lua`
- Modify: `nvim/tests/client_spec.lua`

### Step 1: Add reconnect logic

In `nvim/lua/local_library/client.lua`, add the constant + helper:

```lua
local MAX_RECONNECT_ATTEMPTS = 3

function Client:_try_reconnect()
  for attempt = 1, MAX_RECONNECT_ATTEMPTS do
    local ok = pcall(function() self:connect() end)
    if ok and self:_is_alive() then
      return true
    end
    -- Exponential backoff: 50ms, 150ms, 450ms.
    local backoff = 50 * (3 ^ (attempt - 1))
    vim.wait(backoff)
  end
  return false
end
```

Replace `request_async` with the reconnect-aware version:

```lua
function Client:request_async(method, params, cb)
  if not self:_is_alive() then
    if not self:_try_reconnect() then
      cb({
        code = -3,
        message = "daemon not running. Run :LocalLibraryDaemon start",
        error_code = "DAEMON_UNREACHABLE",
      }, nil)
      return
    end
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
    if self:_try_reconnect() then
      self._pending[id] = cb
      sent = vim.fn.chansend(self.chan_id, envelope)
    end
    if sent == 0 then
      self._pending[id] = nil
      cb({
        code = -1,
        message = "channel send failed (daemon disconnected and reconnect exhausted)",
        error_code = "DAEMON_UNREACHABLE",
      }, nil)
      return
    end
  end
  local timeout_ms = self:_timeout_for(method)
  vim.defer_fn(function()
    if self._pending[id] then
      self._pending[id] = nil
      cb({ code = -2, message = "request '" .. method .. "' timed out after "
        .. timeout_ms .. "ms" }, nil)
    end
  end, timeout_ms)
end
```

### Step 2: Add reconnect tests in their own describe block

The reconnect tests need fully isolated stubs (different from the Phase 4 `before_each` setup that reuses an outer `captured_on_data` and a single `chaninfo` stub). Append a SEPARATE `describe(...)` block at the bottom of `nvim/tests/client_spec.lua`:

```lua
describe("local_library.client reconnect", function()
  local Client
  local client
  local captured_on_data

  before_each(function()
    captured_on_data = nil
    package.loaded["local_library.client"] = nil
    Client = require("local_library.client")
  end)

  it("reconnects when the initial channel is dead", function()
    local connect_calls = 0
    local sc = stub(vim.fn, "sockconnect", function(_m, _a, opts)
      connect_calls = connect_calls + 1
      captured_on_data = opts.on_data
      return 42
    end)
    local cs = stub(vim.fn, "chansend").returns(1)
    local chaninfo_calls = 0
    local ci = stub(vim.fn, "chaninfo", function()
      chaninfo_calls = chaninfo_calls + 1
      if chaninfo_calls == 1 then return {} end
      return { id = 42 }
    end)

    client = Client.new({ socket_path = "/tmp/test.sock", request_timeout_ms = 1000 })
    local async = require("plenary.async")
    local result
    async.run(function()
      _, result = client:ping()
    end)
    captured_on_data(42, { '{"jsonrpc":"2.0","id":1,"result":{"ok":true}}', "" })
    vim.wait(500, function() return result ~= nil end)
    assert.is_table(result)
    assert.is_truthy(connect_calls >= 1)

    sc:revert(); cs:revert(); ci:revert()
  end)

  it("returns DAEMON_UNREACHABLE when reconnect fails 3x", function()
    local sc = stub(vim.fn, "sockconnect").returns(0)
    local ci = stub(vim.fn, "chaninfo").returns({})

    client = Client.new({ socket_path = "/tmp/test.sock", request_timeout_ms = 1000 })
    local async = require("plenary.async")
    local err
    async.run(function()
      err, _ = client:ping()
    end)
    vim.wait(2000, function() return err ~= nil end)
    assert.is_table(err)
    assert.equals("DAEMON_UNREACHABLE", err.error_code)

    sc:revert(); ci:revert()
  end)
end)
```

The fresh `before_each` reloads `local_library.client` so neither test inherits state from the outer `describe("local_library.client", ...)` block (which uses its own `before_each`/`after_each` for stub setup and revert). All stubs in these tests are local — created inside the `it` and reverted at the end of the `it` — so there's no `after_each` interaction with already-reverted stubs.

### Step 3: Run + commit

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/client_spec.lua" -c "qa"
git add nvim/lua/local_library/client.lua nvim/tests/client_spec.lua
git commit -m "feat(nvim): reconnect-on-dead-channel with bounded exponential backoff

3 attempts with 50/150/450ms backoff. Two reconnect points: at request
entry if the channel is already dead, and after a failed chansend. On
exhaustion: returns {error_code = 'DAEMON_UNREACHABLE'} so the
notification mapper (Task 4) can surface a useful message."
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
## Task 4: Error-code → notify mapper + boost_citekeys + doc_id handling

**Type:** Functionality.

**Files:**
- Create: `nvim/lua/local_library/notify.lua`
- Create: `nvim/tests/notify_spec.lua`
- Modify: `nvim/lua/local_library/init.lua`
- Modify: `nvim/lua/local_library/actions.lua`

### Step 1: Write failing tests

`nvim/tests/notify_spec.lua`:

```lua
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
```

### Step 2: Implement `notify.lua`

`nvim/lua/local_library/notify.lua`:

```lua
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
      return "local-library: document-scoped search is not yet available — running unscoped search instead.",
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
```

### Step 3: Wire mapper into `cite()` + add `boost_citekeys`

In `nvim/lua/local_library/init.lua`, replace `M.cite()`:

```lua
function M.cite()
  local selection = require("local_library.selection")
  local query = selection.get_visual()
  if not query or query == "" then
    vim.notify("local-library: no visual selection", vim.log.levels.WARN)
    return
  end
  local range = selection.get_visual_range()

  local refs_path = require("local_library.bibliography").resolve_refs_path(0)
  local boost_citekeys = {}
  if refs_path and vim.fn.filereadable(refs_path) == 1 then
    local ok, keys = pcall(require("local_library.bibliography").list_citekeys, refs_path)
    if ok then boost_citekeys = keys end
  end

  local async = require("plenary.async")
  async.run(function()
    local cli = M.client()
    local err, response = cli:request_sync("search", {
      query = query,
      limit = M.config().search.limit,
      rerank = M.config().search.rerank,
      boost_citekeys = boost_citekeys,
    })
    if err then
      require("local_library.notify").from_error(err)
      return
    end
    if not response or #(response.results or {}) == 0 then
      vim.notify("local-library: no results for selection", vim.log.levels.INFO)
      return
    end

    vim.schedule(function()
      require("telescope").extensions.local_library.cite({
        results = response.results,
        ctx = {
          end_line = range.end_line,
          end_col = range.end_col,
          refs_path = refs_path,
          bufnr = vim.api.nvim_get_current_buf(),
        },
      })
    end)
  end)
end
```

### Step 4: Wire mapper into `actions.lua`

In `actions._handle_bibliography_then`, replace the `get_document` error block:

```lua
    if err then
      require("local_library.notify").from_error(err)
      cb(false)
      return
    end
```

### Step 5: Run + commit

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/notify_spec.lua" -c "qa"
cd nvim && ./scripts/run-tests.sh
git add nvim/lua/local_library/notify.lua nvim/lua/local_library/init.lua nvim/lua/local_library/actions.lua nvim/tests/notify_spec.lua
git commit -m "feat(nvim): error-code → notify mapper + boost_citekeys + doc_id handling

notify.from_error(err) translates daemon error envelopes to user-friendly
vim.notify calls, branching on data.error_code. DAEMON_UNREACHABLE prompts
restart; NOT_IMPLEMENTED for doc_id surfaces 'scoping not yet available';
NOT_FOUND with suggestions formats a 'did you mean…?' hint;
EMBEDDING_EXTENSION_UNAVAILABLE points at reinstall.

cite() now passes boost_citekeys = bibliography.list_citekeys(refs_path)
on every search — exercising the silent-inert hook so a future daemon-side
implementation requires zero plugin coordination."
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
## Task 5: Reliability integration tests

**Type:** Verification.

**Files:**
- Create: `nvim/tests/reliability_spec.lua`

### Step 1: Write the test

`nvim/tests/reliability_spec.lua`:

```lua
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
      env = vim.tbl_extend("force", vim.fn.environ(), { XDG_DATA_HOME = tmp_dir }),
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
    tmp_dir = vim.fn.tempname() .. "-rel"
    vim.fn.mkdir(tmp_dir .. "/local-library", "p")
    vim.env.XDG_DATA_HOME = tmp_dir
    socket_path = tmp_dir .. "/local-library/daemon.sock"
    daemon_pid = spawn_daemon()
    package.loaded["local_library"] = nil
    require("local_library").setup({ socket_path = socket_path })
  end)

  after_each(function()
    if daemon_pid and daemon_pid > 0 then pcall(vim.fn.jobstop, daemon_pid) end
    vim.env.XDG_DATA_HOME = nil
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
```

### Step 2: Run + verify Phase 6 "Done when" criteria

```bash
cd nvim && ./scripts/run-tests.sh
```

- ✓ Kill daemon → next request surfaces clear notify with restart hint — `reliability_spec` + `notify_spec` `DAEMON_UNREACHABLE` test
- ✓ Restart daemon and run again without reloading Neovim — `reliability_spec` second test
- ✓ Slow-query timeout fires with clear message — `client_spec` per-method timeout test (Task 2)
- ✓ Test-only `doc_id` usage surfaces "scoping not yet available" — `notify_spec` `NOT_IMPLEMENTED` test
- ✓ `boost_citekeys` verified in payload — manual: `tail -f ~/Library/Application\ Support/local-library/logs/daemon.log` shows `method=search` lines after firing `<leader>c`. The structured log doesn't include params (intentional — noise), so payload-presence is verified by reading the plugin code and the `init_spec` flow.

### Step 3: Commit

```bash
git add nvim/tests/reliability_spec.lua
git commit -m "test(nvim): reliability integration tests (kill + restart roundtrip)

Spawns daemon, kills it, verifies the next request surfaces
DAEMON_UNREACHABLE with the restart hint. Restarts the daemon,
verifies the next request succeeds via reconnect logic without
reloading Neovim."
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
## Task 6: Concepts doc chapter 7 (reliability)

**Type:** Documentation.

**Files:**
- Modify: `docs/concepts/daemons.md`

### Step 1: Append chapter 7

Open `docs/concepts/daemons.md`. Replace `*Chapter 8 is written in Phase 7 (case studies + cross-references).*` (the closing line from Phase 3) with the content below. Wait — re-check ordering: Phase 3 wrote chapters 5-6, ending the doc with `*Chapter 7 is written in Phase 6 (reliability case study); chapter 8 in Phase 7.*`. Replace that line with the chapter content.

```markdown

## Chapter 7 — Reliability: crash recovery, timeouts, liveness

A daemon plus a client is a distributed system, even when both processes
live on the same machine. The daemon can crash, hang, become slow, or
just stop responding. The client must:

1. Detect that the daemon is unreachable and tell the user something
   actionable (not "request failed: -1").
2. Recover when the daemon comes back, ideally without restarting itself.
3. Bound the time it will wait for any single request, so a hung daemon
   doesn't lock up the editor.

These three behaviors compose into what we call **tier-1 reliability** —
enough to keep the workflow usable under common failure modes (the user
killed the daemon manually, the machine slept, a query is genuinely slow).
Higher tiers (transparent failover, persistent request queues, retries
with idempotency tokens) are out of scope for this MVP.

### Detection: dead-channel + structured envelopes

Two signals tell the client the daemon is gone:

- **OS-level dead channel.** `vim.fn.chansend` returns 0 on a closed
  socket. `vim.fn.chaninfo(chan_id)` returns an empty table. We check
  the latter before every request and the former after every send.
- **No response within the per-method timeout.** If the daemon is alive
  but hung, our deferred timeout fires and we surface a request-level
  error with the method name and elapsed time.

Both paths produce a typed error table with a stable shape:
`{ code, message, error_code, details }`. The plugin's `notify.lua`
mapper translates the `error_code` to a user-facing string and a
`vim.log.levels` value. `DAEMON_UNREACHABLE` always pairs with an
ERROR-level toast that names `:LocalLibraryDaemon start` so the user
knows the next step.

### Recovery: bounded retry, not infinite reconnection

When `request_async` finds the channel dead, it tries to reconnect up
to three times with exponential backoff (50 ms, 150 ms, 450 ms). If all
three fail, the request errors out with `DAEMON_UNREACHABLE`. We do
*not* loop forever:

- **Three attempts is enough** to ride through a launchd respawn or a
  manual `daemon restart`, both of which complete in well under 1 s on
  a warm system.
- **Failing fast is correct** when the daemon is genuinely down. The
  user has actionable information; further retries just delay the
  notification.

The client also reconnects between sessions transparently. If the user
kills the daemon, runs `:LocalLibraryDaemon start`, and immediately
fires `<leader>c` without reloading Neovim, the first request succeeds
via the reconnect path.

### Bounded waits: per-method timeouts

Different RPCs have different reasonable durations:

- `ping`: ~1 ms warm, 50 ms cold. **2 s timeout** flags real wedging.
- `get_document`: a few SQL lookups, no model inference. **2 s timeout**.
- `search`: includes embedder + reranker + sqlite-vec. **5 s timeout**
  by default; the warm p95 should be well under this.

Configurable per-method timeouts are essential because a search timeout
must be larger than a ping timeout, and tying them together means
either pings hang too long or searches abort spuriously.

The timeout is implemented via `vim.defer_fn` + a pending-id check in
`request_async`. If the response arrives before the timeout fires, the
deferred callback finds the pending entry already cleared and does
nothing. If the timeout wins, the response (when it eventually
arrives) is dropped — its id is no longer in `_pending`.

### What we did NOT build (and why)

- **Idempotency tokens for retries.** All our methods are read-only;
  retrying a `search` that may have partially completed is harmless.
  When write methods land (Phase 7+ MCP v2 ingestion), this becomes
  necessary.
- **Connection pooling.** A single client instance per Neovim session
  is fine; the daemon happily multiplexes via `asyncio.start_unix_server`'s
  per-connection coroutines.
- **Circuit breakers.** With a 3-attempt cap and per-method timeouts,
  the existing logic is effectively a tiny circuit breaker (open after
  3 failures within ~700 ms; closes on the next successful connect).
  A formal breaker would add state we don't currently need.

### Operator visibility: structured logs

The daemon-side logging change emits one log line per request:

```
2026-04-25 09:15:01,234 INFO local_library.daemon.dispatcher
  method=search id=42 status=ok duration_ms=183.4
```

`grep status=domain_error` shows all errors over a session. `grep
duration_ms=` plus `awk` gives ad-hoc latency distributions without
spinning up a metrics stack. This is the simplest possible observability
that's still useful — operator tooling builds on top of grep, not under it.

### Cross-references

- Design doc §"Edge cases" — the table of failure modes and their UX
- `nvim/lua/local_library/client.lua` — reconnect + timeout logic
- `nvim/lua/local_library/notify.lua` — `error_code` → user message mapper
- `src/local_library/daemon/dispatcher.py` — structured per-request log
- `nvim/tests/reliability_spec.lua` — kill + restart roundtrip verification

*Chapter 8 is written in Phase 7 (case studies + cross-references).*
```

### Step 2: Verify chapter count

```bash
grep -c '^## Chapter' docs/concepts/daemons.md
```

Expected: `7`.

### Step 3: Commit

```bash
git add docs/concepts/daemons.md
git commit -m "docs(concepts): add chapter 7 of the daemons concepts doc

Chapter 7: reliability tier 1 — dead-channel detection, bounded reconnect
with exponential backoff, per-method timeouts, structured per-request
logs as the simplest observability surface. Documents what we did NOT
build (idempotency tokens, connection pooling, formal circuit breakers)
and why those are the right deferrals at this scale."
```
<!-- END_TASK_6 -->
