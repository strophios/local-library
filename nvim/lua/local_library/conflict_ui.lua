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
