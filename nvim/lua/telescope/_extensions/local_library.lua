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
		ordinal = (result.document_title or "") .. " " .. (result.citekey or "") .. " " .. authors,
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
			-- vim.bo[self.state.bufnr].wrap = true
		end,
	})
end

local function cite(opts)
	opts = opts or {}
	local results = opts.results or {}
	local ctx = opts.ctx or {}
	local action_handlers = require("local_library.actions")

	pickers
		.new(opts, {
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
		})
		:find()
end

return telescope.register_extension({
	setup = function(_ext_config, _config) end,
	exports = {
		cite = cite,
	},
})
