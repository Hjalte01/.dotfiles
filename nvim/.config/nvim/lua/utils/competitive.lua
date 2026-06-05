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

local function is_file(path)
  local stat = uv.fs_stat(path)
  return stat and stat.type == "file"
end

local function mkdir_p(path)
  if vim.fn.isdirectory(path) == 0 then
    vim.fn.mkdir(path, "p")
  end
end

local function split_lines(text)
  text = tostring(text or ""):gsub("\r\n", "\n"):gsub("\r", "\n")
  return vim.split(text, "\n", { plain = true })
end

function M.problem_slug(problem_name)
  local slug = problem_name:lower()
  slug = slug:gsub("^%s*(%a)%s*[%.)%-:]%s*", "%1_")
  slug = slug:gsub("[^%w]+", "_")
  slug = slug:gsub("^_+", ""):gsub("_+$", "")
  return slug ~= "" and slug or "problem"
end

function M.contest_root(path)
  path = (path and vim.fn.fnamemodify(path, ":p") or vim.fn.getcwd()):gsub("/$", "")
  local dir = vim.fn.isdirectory(path) == 1 and path or vim.fn.fnamemodify(path, ":h")
  if vim.fn.fnamemodify(dir, ":t") == "problems" then
    return vim.fn.fnamemodify(dir, ":h")
  end

  return vim.fn.fnamemodify(dir, ":p"):gsub("/$", "")
end

function M.problem_path(problem_name, extension)
  local root = M.contest_root(vim.fn.getcwd())
  return path_join(root, "problems", M.problem_slug(problem_name) .. "." .. extension)
end

local function remove_file(path)
  if is_file(path) then
    uv.fs_unlink(path)
  end
end

local function read_json(path)
  local ok, data = pcall(vim.json.decode, table.concat(vim.fn.readfile(path), "\n"))
  if ok and type(data) == "table" then
    return data
  end
end

local function write_template_file(target)
  local template = vim.fn.stdpath("config") .. "/templates/main.cpp"
  mkdir_p(vim.fn.fnamemodify(target, ":h"))

  if vim.fn.filereadable(template) == 1 then
    vim.fn.writefile(vim.fn.readfile(template), target)
  else
    vim.fn.writefile({ "" }, target)
  end
end

local function write_ast_testcases(root, stem, task)
  if type(task.tests) ~= "table" then
    return
  end

  local tests_dir = path_join(root, ".tests")
  mkdir_p(tests_dir)

  for index, testcase in ipairs(task.tests) do
    if type(testcase) == "table" then
      local tcnum = index - 1
      vim.fn.writefile(split_lines(testcase.input or ""), path_join(tests_dir, stem .. "_input" .. tcnum .. ".txt"))
      vim.fn.writefile(split_lines(testcase.output or ""), path_join(tests_dir, stem .. "_output" .. tcnum .. ".txt"))
    end
  end
end

function M.import_latest_ast_problem()
  local root = M.contest_root(vim.fn.getcwd())
  local ast_dir = path_join(root, ".ast")
  if vim.fn.isdirectory(ast_dir) == 0 then
    vim.notify("No .ast directory found under " .. root, vim.log.levels.WARN)
    return
  end

  local candidates = vim.fn.glob(ast_dir .. "/*.json", false, true)
  table.sort(candidates, function(left, right)
    return (uv.fs_stat(left).mtime.sec or 0) > (uv.fs_stat(right).mtime.sec or 0)
  end)

  for _, json_path in ipairs(candidates) do
    local task = read_json(json_path)
    if task and type(task.name) == "string" then
      local stem = M.problem_slug(task.name)
      local target = path_join(root, "problems", stem .. ".cpp")

      if not is_file(target) then
        write_template_file(target)
        write_ast_testcases(root, stem, task)
        vim.cmd.edit(vim.fn.fnameescape(target))
        vim.notify("Imported " .. task.name .. " to " .. target)
        return
      end
    end
  end

  vim.notify("No new .ast problem to import.", vim.log.levels.INFO)
end

function M.ensure_problem_file_location(path)
  path = vim.fn.fnamemodify(path, ":p")
  if vim.fn.filereadable(path) == 0 then
    return
  end

  local dir = vim.fn.fnamemodify(path, ":h")
  local name = vim.fn.fnamemodify(path, ":t")
  if vim.fn.fnamemodify(dir, ":t") == "problems" or vim.fn.fnamemodify(dir, ":t") == ".done" then
    return
  end

  if vim.fn.isdirectory(path_join(dir, ".ast")) == 0 and vim.fn.isdirectory(path_join(dir, ".tests")) == 0 then
    return
  end

  local target_dir = path_join(dir, "problems")
  local target = path_join(target_dir, name)
  if target == path then
    return
  end

  mkdir_p(target_dir)
  if is_file(target) then
    vim.notify(target .. " already exists.", vim.log.levels.WARN)
    return
  end

  local ok, err = uv.fs_rename(path, target)
  if not ok then
    vim.notify("Could not move problem into problems/: " .. tostring(err), vim.log.levels.ERROR)
    return
  end

  vim.schedule(function()
    vim.cmd.edit(vim.fn.fnameescape(target))
    vim.notify("Moved problem to " .. target)
  end)
end

function M.archive_current_problem()
  local source = vim.fn.expand("%:p")
  if source == "" or vim.bo.filetype ~= "cpp" then
    vim.notify("Open a C++ problem file first.", vim.log.levels.WARN)
    return
  end

  if vim.fn.filereadable(source) == 0 then
    vim.notify("Current file has not been written yet.", vim.log.levels.WARN)
    return
  end

  vim.cmd.write()

  local root = M.contest_root(source)
  local done_dir = path_join(root, ".done")
  local target = path_join(done_dir, vim.fn.fnamemodify(source, ":t"))
  local stem = vim.fn.fnamemodify(source, ":t:r")

  mkdir_p(done_dir)

  if is_file(target) then
    vim.notify(target .. " already exists.", vim.log.levels.ERROR)
    return
  end

  local ok, err = uv.fs_rename(source, target)
  if not ok then
    vim.notify("Could not move problem to .done: " .. tostring(err), vim.log.levels.ERROR)
    return
  end

  remove_file(path_join(vim.fn.fnamemodify(source, ":p:h"), stem))
  remove_file(path_join(root, stem))

  vim.cmd.edit(vim.fn.fnameescape(target))
  vim.notify("Moved problem to " .. target)
end

return M
