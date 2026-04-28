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
