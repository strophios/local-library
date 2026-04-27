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
  if not cb then
    return
  end
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
