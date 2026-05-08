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
