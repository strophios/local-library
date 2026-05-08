# Neovim Citation Workflow Implementation Plan — Phase 5: Core Interaction Flow

**Goal:** End-to-end MVP happy path. Visual-select a claim → `<leader>c` → Telescope picker with chunk preview → one of four actions (insert citekey, insert citekey + chunk text as blockquote, open extracted markdown, cancel). Auto-append CSL-JSON to the project bibliography on insert; conflict resolution via scratch-buffer diff.

**Architecture:** Five new modules under `nvim/lua/local_library/`: `selection.lua` (visual capture), `bibliography.lua` (frontmatter parse + CSL-JSON I/O + diff), `conflict_ui.lua` (scratch-buffer diff with k/o/q keymaps), `actions.lua` (`insert_citekey`, `insert_citekey_with_text`, `open_source`). Plus the Telescope extension at `nvim/lua/telescope/_extensions/local_library.lua` (the only module that imports `telescope.*`). The `:LocalLibraryCite` user command + default `<leader>c` visual-mode keybind are registered in `plugin/local_library.lua`.

**Tech Stack:** Neovim 0.10+, Lua, plenary.async, Telescope 0.1.x. Optional runtime dep: `jq` (for pretty-printed CSL-JSON; compact fallback when absent).

**Scope:** 5 of 7 phases from `docs/design-plans/2026-04-24-neovim-citation-workflow.md`.

**Codebase verified:** 2026-04-24.

**Module responsibility map (the hybrid UI/data split made concrete):**

| Module | Imports `telescope`? | Pattern |
|---|---|---|
| `selection.lua` | no | Mixed (visual capture is small Imperative wrapper) |
| `bibliography.lua` | no | Mixed (parse/diff pure; file I/O imperative) |
| `conflict_ui.lua` | no | Imperative Shell |
| `actions.lua` | no | Mixed |
| `telescope/_extensions/local_library.lua` | **yes — only module that does** | Imperative Shell |

**Executor skills:** `ed3d-house-style:coding-effectively` (FCIS classification per table above), `ed3d-plan-and-execute:test-driven-development`, `ed3d-plan-and-execute:verification-before-completion`.

---

<!-- START_TASK_1 -->
## Task 1: `selection.lua` — visual-mode capture (TDD)

**Type:** Functionality.

**Files:**
- Create: `nvim/tests/selection_spec.lua`
- Create: `nvim/lua/local_library/selection.lua`

### Step 1: Write failing tests

`nvim/tests/selection_spec.lua`:

```lua
local stub = require("luassert.stub")

describe("local_library.selection", function()
  local selection

  before_each(function()
    package.loaded["local_library.selection"] = nil
    selection = require("local_library.selection")
  end)

  it("get_visual returns yanked text and restores prior register", function()
    local register_state = { ['"'] = "prior register contents", _type = "v" }
    stub(vim.fn, "getreg", function(reg) return register_state[reg] end)
    stub(vim.fn, "getregtype", function() return register_state._type end)
    stub(vim.fn, "setreg", function(reg, val, t)
      register_state[reg] = val
      register_state._type = t
    end)
    stub(vim, "cmd", function(cmdstr)
      if cmdstr == "normal! gvy" then
        register_state['"'] = "yanked claim text"
      end
    end)

    local text = selection.get_visual()
    assert.equals("yanked claim text", text)
    assert.equals("prior register contents", register_state['"'])

    vim.fn.getreg:revert()
    vim.fn.getregtype:revert()
    vim.fn.setreg:revert()
    vim.cmd:revert()
  end)

  it("get_visual_range returns the > mark line/column", function()
    stub(vim.fn, "getpos", function(mark)
      if mark == "'>" then return { 0, 7, 42, 0 } end
      if mark == "'<" then return { 0, 5, 1, 0 } end
    end)
    local range = selection.get_visual_range()
    assert.equals(5, range.start_line)
    assert.equals(1, range.start_col)
    assert.equals(7, range.end_line)
    assert.equals(42, range.end_col)
    vim.fn.getpos:revert()
  end)
end)
```

### Step 2: Run tests, confirm they fail

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/selection_spec.lua" -c "qa"
```

### Step 3: Implement `selection.lua`

`nvim/lua/local_library/selection.lua`:

```lua
-- pattern: Mixed
--   Imperative Shell over visual-mode register manipulation.
--
-- Captures the current visual selection's text and range, restoring the
-- caller's register state. Uses the standard `gvy` idiom: re-enter visual
-- mode, yank to the unnamed register, read it, restore the prior register.

local M = {}

--- Capture the visual selection's text. Restores the unnamed register.
--- After this call, the cursor is at the `>` mark (end of selection).
---@return string
function M.get_visual()
  local saved = vim.fn.getreg('"')
  local saved_type = vim.fn.getregtype('"')
  vim.cmd "normal! gvy"
  local text = vim.fn.getreg('"')
  vim.fn.setreg('"', saved, saved_type)
  return text
end

--- Return the visual selection range as a table.
--- All values are 1-indexed (matching :h getpos()).
---@return {start_line: integer, start_col: integer, end_line: integer, end_col: integer}
function M.get_visual_range()
  local s = vim.fn.getpos("'<")
  local e = vim.fn.getpos("'>")
  return {
    start_line = s[2],
    start_col = s[3],
    end_line = e[2],
    end_col = e[3],
  }
end

return M
```

### Step 4: Run + commit

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/selection_spec.lua" -c "qa"
git add nvim/lua/local_library/selection.lua nvim/tests/selection_spec.lua
git commit -m "feat(nvim): visual-mode selection capture with register save/restore"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
## Task 2: `bibliography.lua` — frontmatter parse + CSL-JSON I/O + diff (TDD)

**Type:** Functionality. The largest Phase 5 module.

**Files:**
- Create: `nvim/tests/bibliography_spec.lua`
- Create: `nvim/lua/local_library/bibliography.lua`

### Step 1: Write failing tests

`nvim/tests/bibliography_spec.lua`:

```lua
local stub = require("luassert.stub")

describe("local_library.bibliography", function()
  local bib

  before_each(function()
    package.loaded["local_library.bibliography"] = nil
    bib = require("local_library.bibliography")
  end)

  describe("resolve_refs_path", function()
    it("extracts a scalar bibliography field from frontmatter", function()
      local lines = {
        "---", "title: Paper", "bibliography: refs.json", "---", "", "body",
      }
      assert.equals("refs.json", bib._resolve_refs_path_from_lines(lines))
    end)

    it("extracts the first element of an inline array", function()
      local lines = { "---", "bibliography: [refs.json, other.json]", "---" }
      assert.equals("refs.json", bib._resolve_refs_path_from_lines(lines))
    end)

    it("extracts the first element of a multi-line array", function()
      local lines = {
        "---", "bibliography:", "  - refs.json", "  - other.json", "---",
      }
      assert.equals("refs.json", bib._resolve_refs_path_from_lines(lines))
    end)

    it("returns nil when bibliography field is absent", function()
      local lines = { "---", "title: Paper", "---" }
      assert.is_nil(bib._resolve_refs_path_from_lines(lines))
    end)

    it("returns nil when no frontmatter present", function()
      local lines = { "# A markdown doc with no frontmatter", "body" }
      assert.is_nil(bib._resolve_refs_path_from_lines(lines))
    end)

    it("ignores 'bibliography:' lines outside frontmatter", function()
      local lines = { "# Doc", "bibliography: refs.json" }
      assert.is_nil(bib._resolve_refs_path_from_lines(lines))
    end)

    it("strips quotes from quoted scalar values", function()
      local lines = { "---", 'bibliography: "refs.json"', "---" }
      assert.equals("refs.json", bib._resolve_refs_path_from_lines(lines))
    end)
  end)

  describe("list_citekeys", function()
    it("returns ids from a CSL-JSON array", function()
      local entries = {
        { id = "Smith2023", title = "A" },
        { id = "Doe2024", title = "B" },
      }
      assert.same({ "Smith2023", "Doe2024" }, bib._list_citekeys_from_entries(entries))
    end)

    it("returns empty list for empty array", function()
      assert.same({}, bib._list_citekeys_from_entries({}))
    end)

    it("skips entries without id", function()
      local entries = { { id = "Smith2023" }, { title = "no id" } }
      assert.same({ "Smith2023" }, bib._list_citekeys_from_entries(entries))
    end)
  end)

  describe("diff_entries", function()
    it("returns 'identical' for byte-identical entries", function()
      local a = { id = "Smith2023", title = "A", author = { { family = "Smith" } } }
      local b = { id = "Smith2023", title = "A", author = { { family = "Smith" } } }
      local d = bib.diff_entries(a, b)
      assert.equals("identical", d.status)
    end)

    it("returns 'differs' with field-level changes", function()
      local a = { id = "Smith2023", title = "Old" }
      local b = { id = "Smith2023", title = "New" }
      local d = bib.diff_entries(a, b)
      assert.equals("differs", d.status)
      assert.is_truthy(d.changed_fields.title)
    end)
  end)

  describe("ensure_entry", function()
    local tmp_file

    before_each(function() tmp_file = vim.fn.tempname() .. ".json" end)
    after_each(function() pcall(vim.fn.delete, tmp_file) end)

    it("creates the file when absent and writes a single-entry array", function()
      local entry = { id = "Smith2023", title = "A" }
      local result = bib.ensure_entry(tmp_file, entry)
      assert.equals("appended", result.action)
      assert.equals(1, vim.fn.filereadable(tmp_file))
    end)

    it("appends a new entry to an existing file", function()
      vim.fn.writefile({ '[{"id":"Other2020","title":"X"}]' }, tmp_file)
      local result = bib.ensure_entry(tmp_file, { id = "Smith2023", title = "A" })
      assert.equals("appended", result.action)
      local entries = vim.fn.json_decode(table.concat(vim.fn.readfile(tmp_file), "\n"))
      assert.equals(2, #entries)
    end)

    it("returns 'unchanged' when the entry is already present and identical", function()
      vim.fn.writefile({ '[{"id":"Smith2023","title":"A"}]' }, tmp_file)
      local result = bib.ensure_entry(tmp_file, { id = "Smith2023", title = "A" })
      assert.equals("unchanged", result.action)
    end)

    it("returns 'conflict' with diff when entry exists but differs", function()
      vim.fn.writefile({ '[{"id":"Smith2023","title":"OldTitle"}]' }, tmp_file)
      local result = bib.ensure_entry(tmp_file, { id = "Smith2023", title = "NewTitle" })
      assert.equals("conflict", result.action)
      assert.is_table(result.existing)
      assert.is_table(result.incoming)
      assert.is_truthy(result.diff.changed_fields.title)
    end)
  end)

  describe("read_entries error paths", function()
    it("raises on malformed JSON", function()
      local tmp = vim.fn.tempname() .. ".json"
      vim.fn.writefile({ "not { valid json" }, tmp)
      assert.has_error(function() bib.read_entries(tmp) end)
      vim.fn.delete(tmp)
    end)

    it("returns empty table for missing file", function()
      assert.same({}, bib.read_entries("/nonexistent/path.json"))
    end)
  end)

  describe("write_entries", function()
    it("produces valid CSL-JSON when jq is absent (compact fallback)", function()
      local tmp = vim.fn.tempname() .. ".json"
      stub(vim.fn, "executable", function(name)
        if name == "jq" then return 0 end
        return 1
      end)
      bib.write_entries(tmp, { { id = "Smith2023", title = "A" } })
      local entries = vim.fn.json_decode(table.concat(vim.fn.readfile(tmp), "\n"))
      assert.equals(1, #entries)
      assert.equals("Smith2023", entries[1].id)
      vim.fn.executable:revert()
      vim.fn.delete(tmp)
    end)

    it("falls back to compact when jq exits non-zero", function()
      local tmp = vim.fn.tempname() .. ".json"
      stub(vim.fn, "executable", function(name)
        if name == "jq" then return 1 end
        return 1
      end)
      stub(vim, "system", function(_cmd, _opts)
        return { wait = function() return { code = 5, stdout = "", stderr = "boom" } end }
      end)
      bib.write_entries(tmp, { { id = "X", title = "T" } })
      local entries = vim.fn.json_decode(table.concat(vim.fn.readfile(tmp), "\n"))
      assert.equals("X", entries[1].id)
      vim.fn.executable:revert()
      vim.system:revert()
      vim.fn.delete(tmp)
    end)
  end)

  describe("overwrite_entry", function()
    it("replaces the entry at the given index without reordering", function()
      local tmp = vim.fn.tempname() .. ".json"
      vim.fn.writefile(
        { '[{"id":"A","title":"Aa"},{"id":"B","title":"Bb"},{"id":"C","title":"Cc"}]' },
        tmp
      )
      bib.overwrite_entry(tmp, 2, { id = "B", title = "Bbbb" })
      local entries = vim.fn.json_decode(table.concat(vim.fn.readfile(tmp), "\n"))
      assert.equals("A", entries[1].id)
      assert.equals("B", entries[2].id)
      assert.equals("Bbbb", entries[2].title)
      assert.equals("C", entries[3].id)
      vim.fn.delete(tmp)
    end)
  end)

  describe("diff_entries on nested CSL-JSON shapes", function()
    it("treats author arrays with reordered keys as identical via stable encode", function()
      -- vim.fn.json_encode does not guarantee key order; _stable_encode does.
      local a = {
        id = "Smith2023",
        author = { { family = "Smith", given = "Jane" }, { family = "Doe", given = "Alex" } },
      }
      local b = {
        id = "Smith2023",
        author = { { given = "Jane", family = "Smith" }, { given = "Alex", family = "Doe" } },
      }
      assert.equals("identical", bib.diff_entries(a, b).status)
    end)

    it("detects nested differences inside author arrays", function()
      local a = { id = "X", author = { { family = "Smith", given = "Jane" } } }
      local b = { id = "X", author = { { family = "Smith", given = "Janet" } } }
      local d = bib.diff_entries(a, b)
      assert.equals("differs", d.status)
      assert.is_truthy(d.changed_fields.author)
    end)
  end)
end)
```

### Step 2: Run failing tests

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/bibliography_spec.lua" -c "qa"
```

### Step 3: Implement `bibliography.lua`

`nvim/lua/local_library/bibliography.lua`:

```lua
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
```

### Step 4: Run + commit

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/bibliography_spec.lua" -c "qa"
git add nvim/lua/local_library/bibliography.lua nvim/tests/bibliography_spec.lua
git commit -m "feat(nvim): bibliography file I/O — frontmatter parse, CSL-JSON read/write, diff

resolve_refs_path handles three frontmatter forms (scalar, inline array,
multi-line array). ensure_entry returns {appended|unchanged|conflict} with
field-level diff for conflict cases. write_entries pretty-prints via jq
when available, falls back to compact JSON. diff uses stable sorted-key
encoding so the comparison is deterministic across vim.fn.json_encode runs."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
## Task 3: `conflict_ui.lua` — scratch-buffer diff resolution (TDD)

**Type:** Functionality.

**Files:**
- Create: `nvim/tests/conflict_ui_spec.lua`
- Create: `nvim/lua/local_library/conflict_ui.lua`

### Step 1: Write failing tests

`nvim/tests/conflict_ui_spec.lua`:

```lua
describe("local_library.conflict_ui", function()
  local conflict_ui

  before_each(function()
    package.loaded["local_library.conflict_ui"] = nil
    conflict_ui = require("local_library.conflict_ui")
  end)

  it("resolve creates a scratch buffer with the diff content", function()
    local diff = {
      changed_fields = { title = { existing = "Old", incoming = "New" } },
    }
    local resolution
    conflict_ui.resolve(diff, function(r) resolution = r end)

    local found = false
    for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
      if vim.bo[bufnr].filetype == "diff" then
        found = true
        local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
        local joined = table.concat(lines, "\n")
        assert.is_truthy(joined:match("Old"))
        assert.is_truthy(joined:match("New"))
        assert.is_truthy(joined:match("title"))
        vim.api.nvim_buf_call(bufnr, function()
          vim.api.nvim_feedkeys("q", "x", false)
        end)
        break
      end
    end
    assert.is_true(found)
    vim.wait(100, function() return resolution ~= nil end)
    assert.equals("abort", resolution)
  end)

  it("'k' invokes callback with 'keep'", function()
    local diff = { changed_fields = { title = { existing = "A", incoming = "B" } } }
    local resolution
    conflict_ui.resolve(diff, function(r) resolution = r end)
    for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
      if vim.bo[bufnr].filetype == "diff" then
        vim.api.nvim_buf_call(bufnr, function()
          vim.api.nvim_feedkeys("k", "x", false)
        end)
        break
      end
    end
    vim.wait(100, function() return resolution ~= nil end)
    assert.equals("keep", resolution)
  end)

  it("'o' invokes callback with 'overwrite'", function()
    local diff = { changed_fields = { title = { existing = "A", incoming = "B" } } }
    local resolution
    conflict_ui.resolve(diff, function(r) resolution = r end)
    for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
      if vim.bo[bufnr].filetype == "diff" then
        vim.api.nvim_buf_call(bufnr, function()
          vim.api.nvim_feedkeys("o", "x", false)
        end)
        break
      end
    end
    vim.wait(100, function() return resolution ~= nil end)
    assert.equals("overwrite", resolution)
  end)
end)
```

### Step 2: Implement `conflict_ui.lua`

`nvim/lua/local_library/conflict_ui.lua`:

```lua
-- pattern: Imperative Shell — scratch buffer + buffer-local keymaps.
--
-- Conflict resolution UI for bibliography auto-append. Opens a scratch
-- buffer in a horizontal split with a unified-diff-style display of the
-- changed fields, plus three keymaps:
--   k → callback("keep")        — leave existing entry untouched
--   o → callback("overwrite")   — replace with daemon's entry
--   q | <Esc> → callback("abort") — dismiss, no bib write, no citekey insert

local M = {}

local function _format_diff_lines(diff)
  local lines = {
    "# Bibliography conflict",
    "",
    "The entry already exists in your bibliography but differs from the",
    "library's metadata.",
    "",
    "  k = keep existing entry (insert citekey only, no bib write)",
    "  o = overwrite with library's entry",
    "  q / <Esc> = abort (no citekey, no bib write)",
    "",
    "## Changed fields",
    "",
  }
  for field, change in pairs(diff.changed_fields) do
    table.insert(lines, "@@ field: " .. field .. " @@")
    table.insert(lines, "- " .. vim.inspect(change.existing))
    table.insert(lines, "+ " .. vim.inspect(change.incoming))
    table.insert(lines, "")
  end
  return lines
end

--- Open the conflict UI; invoke `cb` with the resolution string.
---@param diff table
---@param cb fun(resolution: "keep"|"overwrite"|"abort")
function M.resolve(diff, cb)
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, _format_diff_lines(diff))
  vim.bo[buf].filetype = "diff"
  vim.bo[buf].modifiable = false
  vim.bo[buf].buftype = "nofile"

  local function close_and_invoke(resolution)
    if vim.api.nvim_buf_is_valid(buf) then
      vim.api.nvim_buf_delete(buf, { force = true })
    end
    cb(resolution)
  end

  vim.keymap.set("n", "k", function() close_and_invoke("keep") end,
    { buffer = buf, nowait = true, desc = "keep existing bib entry" })
  vim.keymap.set("n", "o", function() close_and_invoke("overwrite") end,
    { buffer = buf, nowait = true, desc = "overwrite with library entry" })
  vim.keymap.set("n", "q", function() close_and_invoke("abort") end,
    { buffer = buf, nowait = true, desc = "abort conflict resolution" })
  vim.keymap.set("n", "<Esc>", function() close_and_invoke("abort") end,
    { buffer = buf, nowait = true, desc = "abort conflict resolution" })

  vim.cmd("split")
  vim.api.nvim_win_set_buf(0, buf)
end

return M
```

### Step 3: Run + commit

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/conflict_ui_spec.lua" -c "qa"
git add nvim/lua/local_library/conflict_ui.lua nvim/tests/conflict_ui_spec.lua
git commit -m "feat(nvim): scratch-buffer conflict-resolution UI with k/o/q keymaps"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
## Task 4: `actions.lua` — insert / open functions (TDD)

**Type:** Functionality.

**Files:**
- Create: `nvim/tests/actions_spec.lua`
- Create: `nvim/lua/local_library/actions.lua`

### Step 1: Write failing tests

`nvim/tests/actions_spec.lua`:

```lua
local stub = require("luassert.stub")

describe("local_library.actions", function()
  local actions

  before_each(function()
    package.loaded["local_library.actions"] = nil
    actions = require("local_library.actions")
  end)

  it("insert_citekey appends '[@citekey]' at the > mark", function()
    local result = { citekey = "Smith2023" }
    local ctx = { end_line = 5, end_col = 10, refs_path = nil }
    local recorded
    stub(vim.api, "nvim_buf_set_text", function(_buf, sl, sc, el, ec, lines)
      recorded = { sl = sl, sc = sc, el = el, ec = ec, lines = lines }
    end)

    actions.insert_citekey(ctx, result, function() end)
    assert.same({ "[@Smith2023]" }, recorded.lines)
    assert.equals(4, recorded.sl)
    assert.equals(10, recorded.sc)

    vim.api.nvim_buf_set_text:revert()
  end)

  it("insert_citekey skips bib write when refs_path is nil", function()
    local notify_calls = {}
    stub(vim, "notify", function(msg, level) table.insert(notify_calls, { msg, level }) end)
    stub(vim.api, "nvim_buf_set_text", function() end)
    local ctx = { end_line = 1, end_col = 0, refs_path = nil }
    actions.insert_citekey(ctx, { citekey = "Smith2023" }, function(ok) end)
    local found = false
    for _, c in ipairs(notify_calls) do
      if c[1]:match("bibliography") and c[2] == vim.log.levels.WARN then
        found = true
      end
    end
    assert.is_true(found)
    vim.notify:revert()
    vim.api.nvim_buf_set_text:revert()
  end)

  it("insert_citekey_with_text inserts citekey + blockquote on new line", function()
    local result = { citekey = "Smith2023", chunk_text = "line1\nline2" }
    local ctx = { end_line = 5, end_col = 10, refs_path = nil }
    local set_text_calls = {}
    local set_lines_calls = {}
    stub(vim.api, "nvim_buf_set_text", function(_, sl, sc, el, ec, lines)
      table.insert(set_text_calls, { lines = lines, sl = sl })
    end)
    stub(vim.api, "nvim_buf_set_lines", function(_, sl, el, _, lines)
      table.insert(set_lines_calls, { lines = lines, sl = sl })
    end)
    actions.insert_citekey_with_text(ctx, result, function() end)
    assert.equals(1, #set_text_calls)
    assert.equals(1, #set_lines_calls)
    assert.same({ "> line1", "> line2" }, set_lines_calls[1].lines)
    vim.api.nvim_buf_set_text:revert()
    vim.api.nvim_buf_set_lines:revert()
  end)

  it("open_source edits the markdown path and searches for chunk text", function()
    local edit_calls = {}
    local search_calls = {}
    stub(vim.cmd, "edit", function(p) table.insert(edit_calls, p) end)
    stub(vim.fn, "search", function(p) table.insert(search_calls, p); return 1 end)
    stub(vim.fn, "filereadable", function() return 1 end)
    actions.open_source({
      extracted_markdown_path = "/tmp/foo.md",
      chunk_text = "the claim",
      chunk_section_heading = "Intro",
    })
    assert.equals("/tmp/foo.md", edit_calls[1])
    assert.is_truthy(search_calls[1])
    vim.cmd.edit:revert()
    vim.fn.search:revert()
    vim.fn.filereadable:revert()
  end)
end)
```

### Step 2: Implement `actions.lua`

`nvim/lua/local_library/actions.lua`:

```lua
-- pattern: Mixed
--   Buffer mutation (Imperative) + bibliography file I/O via bibliography.lua.
--   The chunk_text → blockquote transform is pure.

local bibliography = require("local_library.bibliography")
local conflict_ui = require("local_library.conflict_ui")

local M = {}

--- Insert a citekey of the form `[@citekey]` at the end of the visual selection.
---@param ctx {end_line: integer, end_col: integer, refs_path: string|nil, bufnr: integer?}
---@param result {citekey: string, doc_id: string?}
---@param cb fun(ok: boolean)
function M.insert_citekey(ctx, result, cb)
  local bufnr = ctx.bufnr or 0
  local citekey_text = "[@" .. result.citekey .. "]"

  local function do_insert()
    vim.api.nvim_buf_set_text(
      bufnr,
      ctx.end_line - 1, ctx.end_col,
      ctx.end_line - 1, ctx.end_col,
      { citekey_text }
    )
  end

  M._handle_bibliography_then(ctx, result, function(ok)
    if ok then do_insert() end
    cb(ok)
  end)
end

--- Insert citekey + chunk text as blockquote on a new line below.
function M.insert_citekey_with_text(ctx, result, cb)
  local bufnr = ctx.bufnr or 0
  local citekey_text = "[@" .. result.citekey .. "]"

  local function do_insert()
    vim.api.nvim_buf_set_text(
      bufnr,
      ctx.end_line - 1, ctx.end_col,
      ctx.end_line - 1, ctx.end_col,
      { citekey_text }
    )
    local lines = {}
    for line in (result.chunk_text or ""):gmatch("[^\n]+") do
      table.insert(lines, "> " .. line)
    end
    vim.api.nvim_buf_set_lines(bufnr, ctx.end_line, ctx.end_line, false, lines)
  end

  M._handle_bibliography_then(ctx, result, function(ok)
    if ok then do_insert() end
    cb(ok)
  end)
end

--- Open the extracted markdown for the result; position cursor near the chunk.
function M.open_source(result)
  local path = result.extracted_markdown_path
  if not path or path == "" then
    vim.notify("local-library: no extracted markdown path on result", vim.log.levels.ERROR)
    return
  end
  if vim.fn.filereadable(path) == 0 then
    vim.notify("local-library: extracted markdown not found: " .. path, vim.log.levels.ERROR)
    return
  end
  vim.cmd.edit(path)
  local search_term = vim.fn.escape((result.chunk_text or ""):sub(1, 40), "/\\")
  if search_term == "" or vim.fn.search(search_term) == 0 then
    if result.chunk_section_heading and result.chunk_section_heading ~= "" then
      vim.fn.search(vim.fn.escape(result.chunk_section_heading, "/\\"))
    else
      vim.cmd "normal! gg"
    end
  end
end

--- Internal: orchestrate the bibliography round-trip before any insert.
function M._handle_bibliography_then(ctx, result, cb)
  if not ctx.refs_path then
    vim.notify(
      "local-library: no `bibliography:` field in frontmatter — inserting citekey only",
      vim.log.levels.WARN
    )
    cb(true)
    return
  end
  local async = require("plenary.async")
  async.run(function()
    local client = require("local_library").client()
    local err, doc = client:request_sync("get_document", { identifier = "@" .. result.citekey })
    if err then
      vim.notify("local-library: get_document failed: " .. (err.message or "?"),
        vim.log.levels.ERROR)
      cb(false)
      return
    end
    local entry = doc.csl_json
    if not entry or vim.tbl_isempty(entry) then
      vim.notify("local-library: daemon returned empty csl_json for "
        .. result.citekey, vim.log.levels.WARN)
      cb(true)
      return
    end
    local outcome = bibliography.ensure_entry(ctx.refs_path, entry)
    if outcome.action == "appended" or outcome.action == "unchanged" then
      cb(true)
      return
    end
    conflict_ui.resolve(outcome.diff, function(resolution)
      if resolution == "keep" then
        cb(true)
      elseif resolution == "overwrite" then
        bibliography.overwrite_entry(ctx.refs_path, outcome.index, entry)
        cb(true)
      else
        cb(false)
      end
    end)
  end)
end

return M
```

### Step 3: Run + commit

```bash
cd nvim && nvim --headless -c "PlenaryBustedFile tests/actions_spec.lua" -c "qa"
git add nvim/lua/local_library/actions.lua nvim/tests/actions_spec.lua
git commit -m "feat(nvim): citation actions (insert, insert+blockquote, open)

Each action performs the bibliography round-trip first (get_document RPC,
ensure_entry, conflict UI on diff), then performs the buffer mutation.
Missing frontmatter degrades to citekey-only with a WARN. open_source
edits the extracted markdown and searches for chunk text, falling back to
section heading then top-of-file."
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
## Task 5: Telescope extension + `:LocalLibraryCite` + default keybind

**Type:** Functionality.

**Files:**
- Create: `nvim/lua/telescope/_extensions/local_library.lua`
- Modify: `nvim/lua/local_library/init.lua` (add `cite` orchestrator + autocmd)
- Modify: `nvim/plugin/local_library.lua` (register `:LocalLibraryCite` + `<leader>c`)
- Modify: `nvim/lua/local_library/config.lua` (add `keymaps` and `search` defaults)

### Step 1: Add config defaults

Edit `nvim/lua/local_library/config.lua`. Replace `M.defaults` with:

```lua
M.defaults = {
  socket_path = nil,
  request_timeout_ms = 5000,
  keymaps = {
    enabled = true,
    visual_cite = "<leader>c",
  },
  search = {
    limit = 10,
    rerank = true,
  },
}
```

### Step 2: Add `cite` orchestrator + autocmd to `init.lua`

Append to `nvim/lua/local_library/init.lua`:

```lua
--- Visual-mode entry point: capture selection, run search, open Telescope picker.
function M.cite()
  local selection = require("local_library.selection")
  local query = selection.get_visual()
  if not query or query == "" then
    vim.notify("local-library: no visual selection", vim.log.levels.WARN)
    return
  end
  local range = selection.get_visual_range()

  local async = require("plenary.async")
  async.run(function()
    local cli = M.client()
    local err, response = cli:request_sync("search", {
      query = query,
      limit = M.config().search.limit,
      rerank = M.config().search.rerank,
    })
    if err then
      vim.notify("local-library: search failed: " .. (err.message or "?"),
        vim.log.levels.ERROR)
      return
    end
    if not response or #(response.results or {}) == 0 then
      vim.notify("local-library: no results for selection", vim.log.levels.INFO)
      return
    end

    local refs_path = require("local_library.bibliography").resolve_refs_path(0)
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

Update the existing `M.setup` to register the keymap directly AND fire the autocmd. The direct registration handles the case where `setup()` is called *before* `plugin/local_library.lua` is sourced (e.g., a user calling `setup()` from their own `init.lua` outside lazy.nvim's `config` block); the autocmd handles the more common case where the plugin file's autocmd is registered first. `vim.keymap.set` is idempotent, so the duplication is harmless:

```lua
function M.setup(opts)
  _config_module.setup(opts)
  _setup_done = true
  -- Direct keymap registration. The autocmd in plugin/local_library.lua
  -- is a fallback for users who call setup() inside lazy.nvim's `config`
  -- block (autocmd registered before setup runs). Calling vim.keymap.set
  -- twice with identical args is a no-op.
  local opts_resolved = _config_module.options
  if opts_resolved.keymaps and opts_resolved.keymaps.enabled then
    vim.keymap.set("x", opts_resolved.keymaps.visual_cite, ":LocalLibraryCite<CR>",
      { silent = true, desc = "local-library: cite from selection" })
  end
  vim.api.nvim_exec_autocmds("User", { pattern = "LocalLibraryConfigured" })
end
```

### Step 3: Implement the Telescope extension

`nvim/lua/telescope/_extensions/local_library.lua`:

```lua
-- pattern: Imperative Shell (Telescope picker UI; the only module importing telescope.*)
--
-- Telescope extension: maps daemon search results to picker entries with a
-- previewer and three actions (default insert, <C-t> insert+text, <C-o> open).

local has_telescope, telescope = pcall(require, "telescope")
if not has_telescope then
  return require("local_library").client()
end

local pickers = require("telescope.pickers")
local finders = require("telescope.finders")
local previewers = require("telescope.previewers")
local conf = require("telescope.config").values
local actions = require("telescope.actions")
local action_state = require("telescope.actions.state")

local function entry_maker(result)
  local authors = table.concat(result.document_authors or {}, ", ")
  local year = result.document_year and tostring(result.document_year) or "----"
  local display = string.format(
    "[%s] %s (%s) — %.3f",
    result.citekey or "?",
    result.document_title or "(no title)",
    year,
    result.score or 0.0
  )
  return {
    value = result,
    display = display,
    ordinal = (result.document_title or "") .. " " .. (result.citekey or "")
      .. " " .. authors,
  }
end

local function chunk_previewer()
  return previewers.new_buffer_previewer({
    title = "Chunk preview",
    define_preview = function(self, entry, _status)
      local r = entry.value
      local lines = {
        "Citekey: " .. (r.citekey or "?"),
        "Title:   " .. (r.document_title or ""),
        "Authors: " .. table.concat(r.document_authors or {}, ", "),
        "Year:    " .. tostring(r.document_year or "----"),
        "Score:   " .. string.format("%.3f", r.score or 0.0),
        "Section: " .. (r.chunk_section_heading or "—"),
        "---",
      }
      vim.list_extend(lines, vim.split(r.chunk_text or "", "\n", { plain = true }))
      vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, lines)
      vim.bo[self.state.bufnr].filetype = "markdown"
      vim.bo[self.state.bufnr].wrap = true
    end,
  })
end

local function cite(opts)
  opts = opts or {}
  local results = opts.results or {}
  local ctx = opts.ctx or {}
  local action_handlers = require("local_library.actions")

  pickers.new(opts, {
    prompt_title = "local-library: cite",
    finder = finders.new_table({ results = results, entry_maker = entry_maker }),
    sorter = conf.generic_sorter(opts),
    previewer = chunk_previewer(),
    attach_mappings = function(prompt_bufnr, map)
      actions.select_default:replace(function()
        local sel = action_state.get_selected_entry()
        actions.close(prompt_bufnr)
        action_handlers.insert_citekey(ctx, sel.value, function() end)
      end)
      map({ "i", "n" }, "<C-t>", function()
        local sel = action_state.get_selected_entry()
        actions.close(prompt_bufnr)
        action_handlers.insert_citekey_with_text(ctx, sel.value, function() end)
      end)
      map({ "i", "n" }, "<C-o>", function()
        local sel = action_state.get_selected_entry()
        actions.close(prompt_bufnr)
        action_handlers.open_source(sel.value)
      end)
      return true
    end,
  }):find()
end

return telescope.register_extension({
  setup = function(_ext_config, _config) end,
  exports = {
    cite = cite,
  },
})
```

### Step 4: Register `:LocalLibraryCite` and the keymap

Edit `nvim/plugin/local_library.lua`. Append after the existing `:LocalLibraryDaemon` registration:

```lua
vim.api.nvim_create_user_command("LocalLibraryCite", function()
  require("local_library").cite()
end, { range = true, desc = "Run claim-driven library search on the visual selection" })

-- Default keymap: <leader>c in visual mode. Registered after setup() runs
-- so user-supplied keymaps.enabled = false is honored.
vim.api.nvim_create_autocmd("User", {
  pattern = "LocalLibraryConfigured",
  callback = function()
    local cfg = require("local_library.config").options
    if cfg.keymaps and cfg.keymaps.enabled then
      vim.keymap.set("x", cfg.keymaps.visual_cite, ":LocalLibraryCite<CR>",
        { silent = true, desc = "local-library: cite from selection" })
    end
  end,
})
```

### Step 5: Manual smoke test

With the daemon running and at least one document indexed:

```vim
:LocalLibraryDaemon start
" In a markdown file with `bibliography: refs.json` in the frontmatter:
" Visual-select a sentence, then press <leader>c
```

Expected: Telescope picker opens with ranked results, chunk text in preview, `<CR>` inserts citekey + auto-appends to refs.json, `<C-t>` inserts citekey + blockquote, `<C-o>` opens extracted markdown.

### Step 6: Commit

```bash
git add nvim/lua/telescope/_extensions/local_library.lua nvim/lua/local_library/init.lua nvim/lua/local_library/config.lua nvim/plugin/local_library.lua
git commit -m "feat(nvim): Telescope extension + :LocalLibraryCite + <leader>c visual keybind

Telescope extension is the only module that imports telescope.*; it maps
search results via entry_maker, renders chunk text + metadata in a preview
buffer, and binds <CR>/<C-t>/<C-o> to the action handlers from actions.lua.
Default <leader>c keymap registers in visual mode after setup() completes;
disable via setup({keymaps = {enabled = false}})."
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
## Task 6: End-to-end integration test + Phase 5 verification

**Type:** Verification.

**Files:**
- Create: `nvim/tests/cite_flow_spec.lua`

### Step 1: Write the integration test

`nvim/tests/cite_flow_spec.lua`:

```lua
-- End-to-end cite flow test. Spawns a real daemon against a tmp data dir
-- prepopulated with one document, then drives:
--   1. visual selection → search RPC
--   2. get_document RPC
--   3. ensure_entry on a tmp refs.json
-- Skipped when uv isn't available.

local function command_available(cmd)
  local h = io.popen("command -v " .. cmd .. " 2>/dev/null")
  if not h then return false end
  local r = h:read("*l"); h:close()
  return r ~= nil and r ~= ""
end

describe("end-to-end cite flow", function()
  local tmp_dir, socket_path, daemon_pid, refs_path

  before_each(function()
    if not command_available("uv") then pending("uv not available"); return end
    tmp_dir = vim.fn.tempname() .. "-cite"
    vim.fn.mkdir(tmp_dir .. "/local-library", "p")
    vim.env.XDG_DATA_HOME = tmp_dir
    socket_path = tmp_dir .. "/local-library/daemon.sock"

    local sample = tmp_dir .. "/sample.md"
    vim.fn.writefile({ "# Sample", "", "Discusses retrieval-augmented generation." }, sample)
    vim.fn.system({
      "sh", "-c",
      "XDG_DATA_HOME=" .. tmp_dir .. " uv run python -c '"
        .. "from local_library.core.library import Library; "
        .. "lib = Library(); lib.__enter__(); "
        .. "lib.add(\"" .. sample .. "\", metadata={\"id\": \"Sample2026\", \"title\": \"Sample\"}); "
        .. "lib.embed_all(); lib.close()'"
    })

    daemon_pid = vim.fn.jobstart({ "uv", "run", "local-library-daemon" }, {
      env = vim.tbl_extend("force", vim.fn.environ(), { XDG_DATA_HOME = tmp_dir }),
      detach = true,
    })
    local deadline = vim.loop.hrtime() + 30 * 1e9
    while vim.loop.hrtime() < deadline do
      if vim.fn.getftype(socket_path) == "socket" then break end
      vim.wait(100)
    end

    refs_path = tmp_dir .. "/refs.json"

    package.loaded["local_library"] = nil
    require("local_library").setup({ socket_path = socket_path })
  end)

  after_each(function()
    if daemon_pid and daemon_pid > 0 then pcall(vim.fn.jobstop, daemon_pid) end
    vim.env.XDG_DATA_HOME = nil
  end)

  it("search RPC returns the seeded document and ensure_entry writes refs.json", function()
    local async = require("plenary.async")
    local err, response
    async.run(function()
      err, response = require("local_library").client():request_sync("search",
        { query = "retrieval generation", limit = 5 })
    end)
    vim.wait(10000, function() return err ~= nil or response ~= nil end)
    assert.is_nil(err, err and err.message or "")
    assert.is_truthy(#response.results >= 1)
    assert.equals("Sample2026", response.results[1].citekey)

    local _, doc
    async.run(function()
      _, doc = require("local_library").client():request_sync("get_document",
        { identifier = "@Sample2026" })
    end)
    vim.wait(5000, function() return doc ~= nil end)
    assert.is_truthy(doc.csl_json)

    local outcome = require("local_library.bibliography").ensure_entry(refs_path, doc.csl_json)
    assert.equals("appended", outcome.action)
    assert.equals(1, vim.fn.filereadable(refs_path))
    local entries = vim.fn.json_decode(table.concat(vim.fn.readfile(refs_path), "\n"))
    assert.equals("Sample2026", entries[1].id)

    local outcome2 = require("local_library.bibliography").ensure_entry(refs_path, doc.csl_json)
    assert.equals("unchanged", outcome2.action)
  end)
end)
```

### Step 2: Run + verify Phase 5 "Done when" criteria

```bash
cd nvim && ./scripts/run-tests.sh
```

Manual flow verification (with daemon running, real corpus):

- [ ] Visual-select a claim, hit `<leader>c` → Telescope picker opens with ranked results
- [ ] Previewer renders chunk text + metadata
- [ ] `<CR>` inserts `[@citekey]` at end of selection; CSL-JSON appended to bibliography
- [ ] `<C-t>` inserts citekey + blockquoted chunk text below the selection
- [ ] `<C-o>` opens the extracted markdown, cursor near the chunk
- [ ] Conflict case: scratch buffer opens with diff; `k`/`o`/`q` produce specified behavior
- [ ] Edge cases: missing frontmatter → insert-only with WARN; missing extracted markdown → action 3 errors

### Step 3: Commit

```bash
git add nvim/tests/cite_flow_spec.lua
git commit -m "test(nvim): end-to-end cite flow integration test

Spawns a real daemon, seeds a one-document corpus via the Library Python
API, then drives search → get_document → ensure_entry through the actual
plugin code. Verifies the bibliography file is written correctly and that
re-running yields 'unchanged'."
```
<!-- END_TASK_6 -->
