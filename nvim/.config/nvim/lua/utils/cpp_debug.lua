local M = {}

local uv = vim.uv or vim.loop

local function path_join(...)
  return table.concat(
    vim.tbl_filter(function(part)
      return part and part ~= ""
    end, { ... }),
    "/"
  )
end

local function testcase_input_files(src)
  local dir = vim.fn.fnamemodify(src, ":h")
  local stem = vim.fn.fnamemodify(src, ":t:r")
  local tests_dir = vim.fn.fnamemodify(path_join(dir, "../.tests"), ":p"):gsub("/$", "")
  local files = vim.fn.glob(path_join(tests_dir, stem .. "_input*.txt"), false, true)

  table.sort(files, function(left, right)
    local left_num = tonumber(left:match("_input(%d+)%.txt$")) or 0
    local right_num = tonumber(right:match("_input(%d+)%.txt$")) or 0
    return left_num < right_num
  end)

  return files
end

local function debug_binary_path(src)
  local hash = vim.fn.sha256(src)
  local stem = vim.fn.fnamemodify(src, ":t:r")
  local out_dir = "/tmp/competitest.nvim"
  vim.fn.mkdir(out_dir, "p")
  return path_join(out_dir, hash .. "-" .. stem .. "-debug")
end

local function compile_debug(src, binary, callback)
  vim.notify("Compiling debug binary...")
  vim.system({
    "g++",
    "-std=c++23",
    "-Wall",
    "-Wextra",
    "-g",
    "-O0",
    src,
    "-o",
    binary,
  }, { text = true }, function(result)
    vim.schedule(function()
      if result.code ~= 0 then
        local output = vim.trim((result.stderr or "") .. "\n" .. (result.stdout or ""))
        vim.notify(output ~= "" and output or "Debug compile failed", vim.log.levels.ERROR)
        return
      end

      callback()
    end)
  end)
end

local function start_debug(src, binary, input_file)
  local dap = require("dap")
  dap.run({
    type = "codelldb",
    request = "launch",
    name = "Debug current testcase",
    program = binary,
    cwd = vim.fn.fnamemodify(src, ":h"),
    stopOnEntry = false,
    preRunCommands = { "breakpoint set --name main" },
    stdio = { input_file, nil, nil },
  })
end

function M.debug_current_testcase()
  if vim.bo.filetype ~= "cpp" then
    vim.notify("Debug testcase is only configured for C++ files", vim.log.levels.WARN)
    return
  end

  if vim.bo.modified then
    vim.cmd.write()
  end

  local src = vim.fn.expand("%:p")
  local inputs = testcase_input_files(src)
  if #inputs == 0 then
    vim.notify("No CompetiTest input files found for " .. vim.fn.fnamemodify(src, ":t"), vim.log.levels.WARN)
    return
  end

  vim.ui.select(inputs, {
    prompt = "Debug testcase",
    format_item = function(path)
      local tcnum = path:match("_input(%d+)%.txt$") or "?"
      return "testcase " .. tcnum .. "  " .. vim.fn.fnamemodify(path, ":t")
    end,
  }, function(input_file)
    if not input_file then
      return
    end

    local binary = debug_binary_path(src)
    compile_debug(src, binary, function()
      if not uv.fs_stat(binary) then
        vim.notify("Debug binary was not created: " .. binary, vim.log.levels.ERROR)
        return
      end

      start_debug(src, binary, input_file)
    end)
  end)
end

return M
