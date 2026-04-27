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
    captured_on_data(42, { '{"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n', "" })
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
      '{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"Method not found"}}\n',
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
        .. '"data":{"error_code":"NOT_FOUND","details":{"identifier":"@xyz"}}}}\n',
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
    captured_on_data(42, { '{"jsonrpc":"2.0","id":1,"result":{"ok":true,"daemon_pid":99}}\n', "" })
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
    captured_on_data(42, { 'lt":{"ok":true}}\n', "" })
    vim.wait(100, function() return result ~= nil end)
    assert.is_true(result.ok)
  end)
end)
