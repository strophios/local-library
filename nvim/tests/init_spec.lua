local function reload(modname)
  package.loaded[modname] = nil
  return require(modname)
end

describe("local_library.init", function()
  before_each(function()
    package.loaded["local_library"] = nil
    package.loaded["local_library.config"] = nil
    package.loaded["local_library.client"] = nil
  end)

  it("setup is idempotent", function()
    local lib = reload("local_library")
    lib.setup({})
    lib.setup({})
    assert.is_table(lib.config())
  end)

  it("setup honors socket_path override", function()
    local lib = reload("local_library")
    lib.setup({ socket_path = "/custom/sock" })
    assert.equals("/custom/sock", lib.config().socket_path)
  end)

  it("client() returns a singleton client", function()
    local lib = reload("local_library")
    lib.setup({})
    local c1 = lib.client()
    local c2 = lib.client()
    assert.equals(c1, c2)
  end)
end)
