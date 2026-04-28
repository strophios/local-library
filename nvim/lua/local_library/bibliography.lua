-- pattern: Mixed
--   Functional Core: _resolve_refs_path_from_lines, _list_citekeys_from_entries,
--                    diff_entries, _stable_encode — pure transformations.
--   Imperative Shell: read_entries, write_entries, ensure_entry, resolve_refs_path,
--                     overwrite_entry — touch the filesystem and shell out to jq.

local M = {}

local function _strip_quotes(s)
  return s:match('^"(.*)"$') or s:match("^'(.*)'$") or s
end

--- Pure: extract refs path from a list of lines (first ~50). Returns nil
--- when no frontmatter or no bibliography field.
function M._resolve_refs_path_from_lines(lines)
  if not lines[1] or lines[1] ~= "---" then return nil end
  local end_idx = nil
  for i = 2, math.min(#lines, 50) do
    if lines[i] == "---" then
      end_idx = i
      break
    end
  end
  if not end_idx then return nil end

  for i = 2, end_idx - 1 do
    local line = lines[i]
    local value = line:match("^bibliography:%s*(.*)%s*$")
    if value then
      value = value:gsub("%s+$", "")
      if value == "" then
        -- Multi-line array form.
        for j = i + 1, end_idx - 1 do
          local first = lines[j]:match("^%s*%-%s*(.+)%s*$")
          if first then
            return _strip_quotes(first:gsub("%s+$", ""))
          end
          if not lines[j]:match("^%s") then break end
        end
        return nil
      end
      if value:sub(1, 1) == "[" then
        local first = value:match("^%[%s*([^,%]]+)")
        if first then
          return _strip_quotes(first:gsub("^%s+", ""):gsub("%s+$", ""))
        end
        return nil
      end
      return _strip_quotes(value)
    end
  end
  return nil
end

--- I/O: read the current buffer's first 50 lines and resolve.
function M.resolve_refs_path(bufnr)
  bufnr = bufnr or 0
  local lines = vim.api.nvim_buf_get_lines(bufnr, 0, 50, false)
  local relative = M._resolve_refs_path_from_lines(lines)
  if not relative then return nil end
  if relative:sub(1, 1) == "/" then return relative end
  local buf_path = vim.api.nvim_buf_get_name(bufnr)
  local buf_dir = vim.fn.fnamemodify(buf_path, ":h")
  return buf_dir .. "/" .. relative
end

--- Read a CSL-JSON array file. Returns {} for missing or empty files.
function M.read_entries(path)
  if vim.fn.filereadable(path) == 0 then return {} end
  local text = table.concat(vim.fn.readfile(path), "\n")
  if text == "" then return {} end
  local ok, parsed = pcall(vim.fn.json_decode, text)
  if not ok or type(parsed) ~= "table" then
    error("local-library: malformed CSL-JSON at " .. path)
  end
  return parsed
end

--- Write a CSL-JSON array. Pretty-prints via jq when available.
function M.write_entries(path, entries)
  local compact = vim.fn.json_encode(entries)
  local out = compact
  if vim.fn.executable("jq") == 1 then
    local result = vim.system(
      { "jq", "--indent", "2", "." },
      { stdin = compact, text = true }
    ):wait()
    if result.code == 0 and result.stdout and #result.stdout > 0 then
      out = result.stdout
    end
  end
  local tmp = path .. ".tmp." .. vim.fn.getpid()
  vim.fn.writefile(vim.split(out:gsub("\n$", ""), "\n"), tmp)
  vim.loop.fs_rename(tmp, path)
end

function M._list_citekeys_from_entries(entries)
  local out = {}
  for _, e in ipairs(entries) do
    if e.id then table.insert(out, e.id) end
  end
  return out
end

function M.list_citekeys(path)
  return M._list_citekeys_from_entries(M.read_entries(path))
end

local function _stable_encode(t)
  if type(t) ~= "table" then return vim.fn.json_encode(t) end
  local keys = {}
  for k in pairs(t) do table.insert(keys, k) end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  local parts = {}
  for _, k in ipairs(keys) do
    table.insert(parts, vim.fn.json_encode(k) .. ":" .. _stable_encode(t[k]))
  end
  return "{" .. table.concat(parts, ",") .. "}"
end

function M.diff_entries(a, b)
  if _stable_encode(a) == _stable_encode(b) then
    return { status = "identical", changed_fields = {} }
  end
  local changed = {}
  local seen = {}
  for k in pairs(a) do seen[k] = true end
  for k in pairs(b) do seen[k] = true end
  for k in pairs(seen) do
    if _stable_encode(a[k]) ~= _stable_encode(b[k]) then
      changed[k] = { existing = a[k], incoming = b[k] }
    end
  end
  return { status = "differs", changed_fields = changed }
end

function M.ensure_entry(path, entry)
  local entries = M.read_entries(path)
  for i, existing in ipairs(entries) do
    if existing.id == entry.id then
      local d = M.diff_entries(existing, entry)
      if d.status == "identical" then
        return { action = "unchanged" }
      end
      return {
        action = "conflict",
        existing = existing,
        incoming = entry,
        diff = d,
        index = i,
      }
    end
  end
  table.insert(entries, entry)
  M.write_entries(path, entries)
  return { action = "appended" }
end

function M.overwrite_entry(path, index, entry)
  local entries = M.read_entries(path)
  entries[index] = entry
  M.write_entries(path, entries)
end

return M
