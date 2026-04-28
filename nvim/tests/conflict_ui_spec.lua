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
