local M = {}

local function read_problem_url(json_path)
  local lines = vim.fn.readfile(json_path)
  local ok, data = pcall(vim.json.decode, table.concat(lines, "\n"))
  if ok and type(data) == "table" and type(data.url) == "string" and data.url ~= "" then
    return data.url
  end
end

local function find_problem_json(stem)
  local dir = vim.fn.expand("%:p:h")
  while dir and dir ~= "" do
    local json_path = dir .. "/.ast/" .. stem .. ".json"
    if vim.fn.filereadable(json_path) == 1 then
      return json_path
    end

    local parent = vim.fn.fnamemodify(dir, ":h")
    if parent == dir then
      return
    end
    dir = parent
  end
end

local function submit_command(url, source)
  return table.concat({
    "oj",
    "submit",
    vim.fn.shellescape(url),
    vim.fn.shellescape(source),
  }, " ")
end

function M.submit_current_file()
  local source = vim.fn.expand("%:p")
  if source == "" then
    vim.notify("No current file to submit.", vim.log.levels.WARN)
    return
  end

  vim.cmd.write()

  local stem = vim.fn.expand("%:t:r")
  local json_path = find_problem_json(stem)
  if not json_path then
    vim.notify("No problem JSON found for " .. stem, vim.log.levels.WARN)
    return
  end

  local url = read_problem_url(json_path)
  if not url then
    vim.notify("No problem URL found in " .. json_path, vim.log.levels.WARN)
    return
  end

  if url:match("^https?://[^/]*codeforces%.com/") then
    vim.notify("Codeforces CLI submit is disabled; use the website file upload.", vim.log.levels.WARN)
    return
  end

  local cmd = table.concat({
    submit_command(url, source),
    ";",
    "echo",
    "''",
    ";",
    "read",
    "-p",
    vim.fn.shellescape("Press Enter to close terminal..."),
  }, " ")

  require("snacks.terminal")(cmd, {
    cwd = vim.fn.getcwd(),
    persist = true,
  })
end

return M
