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
