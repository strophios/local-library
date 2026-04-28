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
      require("local_library.notify").from_error(err)
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
