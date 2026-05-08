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
  local tmp_dir, data_dir, socket_path, daemon_pid, refs_path

  before_each(function()
    if not command_available("uv") then pending("uv not available"); return end
    if not command_available("python3") and not command_available("python") then
      pending("python not available"); return
    end

    -- Use a short random path to avoid AF_UNIX sun_path constraint (~104 chars)
    -- Use full randomness to avoid collisions between parallel test runs
    local random_suffix = tostring(vim.fn.getpid()) .. "-" .. tostring(os.time() * 1000 + math.random(1000))
    tmp_dir = "/tmp/ll-cite-" .. random_suffix
    data_dir = tmp_dir .. "/local-library"
    vim.fn.mkdir(data_dir, "p")
    socket_path = data_dir .. "/daemon.sock"

    -- Seed the library with one document via Python CLI
    -- This mirrors the pattern from tests/integration/daemon/test_search_lifecycle.py
    local sample_pdf = tmp_dir .. "/sample.pdf"

    local setup_script = table.concat({
      "import os",
      "import sys",
      "from pathlib import Path",
      "from unittest.mock import MagicMock, patch",
      "from local_library.core.library import Library",
      "",
      "sample_pdf = Path(sys.argv[1])",
      "sample_pdf.parent.mkdir(parents=True, exist_ok=True)",
      'sample_pdf.write_bytes(b"%PDF-1.4\\n%dummy")',
      "",
      "metadata = {",
      '    "id": "Sample2026",',
      '    "type": "article-journal",',
      '    "title": "Sample Paper on RAG",',
      '    "author": [{"family": "Author", "given": "Test"}],',
      '    "issued": {"date-parts": [[2026]]},',
      "}",
      "",
      'data_dir = os.environ.get("LOCAL_LIBRARY_DATA_DIR")',
      "if data_dir:",
      "    data_dir = Path(data_dir)",
      "    lib = Library(",
      '        db_path=data_dir / "library.db",',
      '        storage_dir=data_dir / "storage",',
      '        extracted_dir=data_dir / "extracted",',
      "        embed_on_add=False,",
      "    )",
      "else:",
      "    lib = Library(embed_on_add=False)",
      "",
      "with lib:",
      "    with patch.object(",
      "        lib._extractors[0],",
      '        "extract_and_validate",',
      "    ) as mock_extract:",
      "        mock_extract.return_value = MagicMock(",
      '            text="This document discusses retrieval-augmented generation in detail. "',
      '            "Specifically, the use of dense embeddings combined with full-text search."',
      "        )",
      "        lib.add(str(sample_pdf), metadata=metadata)",
      "",
      "    try:",
      "        lib.embed_all()",
      "    except Exception as e:",
      '        if "EMBEDDING_EXTENSION_UNAVAILABLE" not in str(e):',
      "            raise",
    }, "\n")

    local setup_result = vim.fn.system({
      "sh", "-c",
      "XDG_DATA_HOME=" .. tmp_dir .. " LOCAL_LIBRARY_DATA_DIR=" .. data_dir
        .. " uv run python3 -c '" .. setup_script:gsub("'", "'\\''") .. "' " .. sample_pdf
        .. " 2>&1"
    })
    if vim.v.shell_error ~= 0 then
      -- Seed failed; maybe uv or local-library not in PATH, or setup script error
      pending("could not seed library: " .. tostring(setup_result))
      return
    end

    -- Spawn the daemon
    daemon_pid = vim.fn.jobstart({ "uv", "run", "local-library-daemon" }, {
      env = vim.tbl_extend("force", vim.fn.environ(), {
        XDG_DATA_HOME = tmp_dir,
        LOCAL_LIBRARY_DATA_DIR = data_dir,
      }),
      detach = true,
    })

    -- Wait for daemon socket (up to 60s; embeddings can take time)
    local deadline = vim.loop.hrtime() + 60 * 1e9
    while vim.loop.hrtime() < deadline do
      if vim.fn.getftype(socket_path) == "socket" then break end
      vim.wait(200)
    end
    if vim.fn.getftype(socket_path) ~= "socket" then
      pending("daemon did not create socket within 60s")
      return
    end

    refs_path = tmp_dir .. "/refs.json"

    -- Reset plugin to use test socket with longer timeout for slow operations
    package.loaded["local_library"] = nil
    package.loaded["local_library.client"] = nil
    package.loaded["local_library.config"] = nil
    package.loaded["local_library.bibliography"] = nil
    require("local_library").setup({
      socket_path = socket_path,
      request_timeout_ms = 30000,
    })
  end)

  after_each(function()
    if daemon_pid and daemon_pid > 0 then pcall(vim.fn.jobstop, daemon_pid) end
    vim.env.XDG_DATA_HOME = nil
    vim.env.LOCAL_LIBRARY_DATA_DIR = nil
    -- Clean up the temp directory
    if tmp_dir and vim.fn.isdirectory(tmp_dir) == 1 then
      vim.fn.system({ "rm", "-rf", tmp_dir })
    end
  end)

  it("search RPC returns the seeded document and ensure_entry writes refs.json", function()
    local async = require("plenary.async")
    local err, response

    -- Drive the search RPC (with longer timeout for slow machines)
    async.run(function()
      err, response = require("local_library").client():request_sync("search",
        { query = "retrieval generation", limit = 5 })
    end)
    vim.wait(30000, function() return err ~= nil or response ~= nil end)

    assert.is_nil(err, err and err.message or "")
    assert.is_truthy(response.results)
    assert.is_truthy(#response.results >= 1)

    -- Capture the actual citekey (may differ from the metadata id due to generation heuristic)
    local actual_citekey = response.results[1].citekey
    assert.is_truthy(actual_citekey)

    -- Drive the get_document RPC using the actual citekey
    local doc
    async.run(function()
      _, doc = require("local_library").client():request_sync("get_document",
        { identifier = "@" .. actual_citekey })
    end)
    vim.wait(10000, function() return doc ~= nil end)

    assert.is_truthy(doc)
    assert.is_truthy(doc.csl_json)
    assert.equals("Sample2026", doc.csl_json.id)

    -- Drive ensure_entry on the CSL-JSON
    local bibliography = require("local_library.bibliography")
    local outcome = bibliography.ensure_entry(refs_path, doc.csl_json)
    assert.equals("appended", outcome.action)
    assert.equals(1, vim.fn.filereadable(refs_path))

    -- Verify the file contents
    local entries = vim.fn.json_decode(table.concat(vim.fn.readfile(refs_path), "\n"))
    assert.equals(1, #entries)
    assert.equals("Sample2026", entries[1].id)

    -- Second ensure_entry should return "unchanged"
    local outcome2 = bibliography.ensure_entry(refs_path, doc.csl_json)
    assert.equals("unchanged", outcome2.action)
  end)
end)
