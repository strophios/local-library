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
    -- 20-byte line so end_col=10 clamps to itself (no truncation expected here).
    stub(vim.api, "nvim_buf_get_lines", function(_buf, _s, _e, _strict)
      return { "this is a long line." }
    end)

    actions.insert_citekey(ctx, result, function() end)
    assert.same({ "[@Smith2023]" }, recorded.lines)
    assert.equals(4, recorded.sl)
    assert.equals(10, recorded.sc)

    vim.api.nvim_buf_set_text:revert()
    vim.api.nvim_buf_get_lines:revert()
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

  it("insert_citekey clamps end_col to line byte-length (v$ / V-mode v:maxcol)", function()
    -- Regression: getpos("'>") returns v:maxcol (~2^31-1) for both V-mode
    -- and v$ in characterwise visual mode. Without clamping, nvim_buf_set_text
    -- raises "Invalid 'start_col': out of range" and the throw poisons the
    -- transport buffer for the next request.
    local result = { citekey = "Smith2023" }
    local ctx = { end_line = 1, end_col = 2147483647, refs_path = nil, bufnr = 7 }
    local recorded
    stub(vim.api, "nvim_buf_set_text", function(_buf, sl, sc, el, ec, lines)
      recorded = { sl = sl, sc = sc, el = el, ec = ec, lines = lines }
    end)
    stub(vim.api, "nvim_buf_get_lines", function(_buf, _s, _e, _strict)
      return { "hello world" }  -- 11 bytes
    end)
    actions.insert_citekey(ctx, result, function() end)
    assert.equals(11, recorded.sc)
    assert.equals(11, recorded.ec)
    assert.same({ "[@Smith2023]" }, recorded.lines)
    vim.api.nvim_buf_set_text:revert()
    vim.api.nvim_buf_get_lines:revert()
  end)

  it("insert_citekey_with_text clamps end_col to line byte-length", function()
    local result = { citekey = "Smith2023", chunk_text = "quote" }
    local ctx = { end_line = 3, end_col = 2147483647, refs_path = nil, bufnr = 7 }
    local set_text_recorded
    stub(vim.api, "nvim_buf_set_text", function(_buf, sl, sc, el, ec, lines)
      set_text_recorded = { sl = sl, sc = sc, el = el, ec = ec, lines = lines }
    end)
    stub(vim.api, "nvim_buf_set_lines", function() end)
    stub(vim.api, "nvim_buf_get_lines", function(_buf, _s, _e, _strict)
      return { "hello" }  -- 5 bytes
    end)
    actions.insert_citekey_with_text(ctx, result, function() end)
    assert.equals(5, set_text_recorded.sc)
    assert.equals(5, set_text_recorded.ec)
    vim.api.nvim_buf_set_text:revert()
    vim.api.nvim_buf_set_lines:revert()
    vim.api.nvim_buf_get_lines:revert()
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
