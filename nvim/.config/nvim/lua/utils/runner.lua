-- ~/.config/nvim/lua/utils/runner.lua

local M = {} -- M is the table (module) we will export

function M.run_cpp_file()
  local filetype = vim.bo.filetype
  if filetype == "cpp" then
    -- Get the current file name (e.g., main.cpp)
    local filename = vim.fn.expand("%")
    -- Define the output path for the compiled binary
    local binary_path = "/tmp/a.out"

    -- Simplified command: Compile to /tmp/, Execute, then wait for Enter.
    -- The `cwd` option below handles the directory.
    local compile_and_run = string.format(
      "g++ %s -o %s && %s; read -p 'Press Enter to close terminal...' ",
      filename,
      binary_path,
      binary_path
    )

    -- Use the new required snacks.terminal function
    require("snacks.terminal")(compile_and_run, {
      cwd = vim.fn.getcwd(), -- Correctly set the Working Directory
      persist = true,        -- Keep the terminal open
    })
  else
    vim.notify("This command is only for C++ files!", vim.log.levels.WARN)
  end
end

function M.run_python_file()
  local filetype = vim.bo.filetype
  if filetype == "python" then
    local filename = vim.fn.expand("%")
    -- We use 'python3 -u' (unbuffered) so print statements show up immediately
    local cmd = string.format("python3 -u %s; echo ''; read -p 'Press Enter to exit...' ", filename)

    require("snacks.terminal")(cmd, {
      cwd = vim.fn.getcwd(),
      persist = true,
      win = { position = "float" }, -- Optional: makes it float like your Java setup
    })
  else
    vim.notify("This command is only for Python files!", vim.log.levels.WARN)
  end
end

return M -- Export the module
