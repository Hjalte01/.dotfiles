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

local function codeforces_problem_url(text)
  text = tostring(text or "")
  local url = text:match("https?://[%w%._%-]*codeforces%.com/[%w%._%-%?%%&=/#]+")
  if not url then
    return nil
  end

  url = url:gsub("[%)%],%.;]+$", "")
  if url:match("/problemset/problem/%d+/[A-Za-z0-9]+/?$") or url:match("/contest/%d+/problem/[A-Za-z0-9]+/?$") or url:match("/gym/%d+/problem/[A-Za-z0-9]+/?$") then
    return url
  end
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

local function import_ast_problem(json_path, opts)
  opts = opts or {}

  local task = read_json(json_path)
  if not task or type(task.name) ~= "string" then
    vim.notify("Could not read problem from " .. json_path, vim.log.levels.WARN)
    return false
  end

  local root = M.contest_root(vim.fn.getcwd())
  local stem = M.problem_slug(task.name)
  local target = path_join(root, "problems", stem .. ".cpp")

  if is_file(target) then
    if opts.open_existing then
      vim.cmd.edit(vim.fn.fnameescape(target))
      vim.notify(task.name .. " is already imported.")
    end
    return false
  end

  write_template_file(target)
  write_ast_testcases(root, stem, task)
  vim.cmd.edit(vim.fn.fnameescape(target))
  vim.notify("Imported " .. task.name .. " to " .. target)
  return true
end

local function ast_candidates(root)
  local ast_dir = path_join(root, ".ast")
  if vim.fn.isdirectory(ast_dir) == 0 then
    vim.notify("No .ast directory found under " .. root, vim.log.levels.WARN)
    return {}
  end

  local candidates = vim.fn.glob(ast_dir .. "/*.json", false, true)
  table.sort(candidates, function(left, right)
    return (uv.fs_stat(left).mtime.sec or 0) > (uv.fs_stat(right).mtime.sec or 0)
  end)
  return candidates
end

function M.import_latest_ast_problem()
  local root = M.contest_root(vim.fn.getcwd())

  for _, json_path in ipairs(ast_candidates(root)) do
    if import_ast_problem(json_path) then
      return
    end
  end

  vim.notify("No new .ast problem to import.", vim.log.levels.INFO)
end

function M.pull_and_import_latest_ast_problem()
  local puller = vim.fn.expand("~/.local/bin/codeforces-auto-pull")
  if vim.fn.executable(puller) ~= 1 then
    M.import_latest_ast_problem()
    return
  end

  local clipboard = vim.fn.getreg("+")
  if clipboard == "" then
    clipboard = vim.fn.getreg("*")
  end

  local url = codeforces_problem_url(clipboard)
  local args = url and { puller, "--url", url } or { puller, "--once", "--limit", "40" }
  vim.notify(url and ("Pulling Codeforces samples from " .. url) or "Pulling latest Codeforces samples from Firefox history...")
  vim.system(args, { text = true }, function(result)
    vim.schedule(function()
      if result.code ~= 0 then
        local stderr = vim.trim(result.stderr or "")
        vim.notify(
          stderr ~= "" and stderr or "Could not pull latest Codeforces samples.",
          vim.log.levels.WARN
        )
        return
      end
      M.import_latest_ast_problem()
    end)
  end)
end

function M.choose_ast_problem()
  local root = M.contest_root(vim.fn.getcwd())
  local choices = {}

  for _, json_path in ipairs(ast_candidates(root)) do
    local task = read_json(json_path)
    if task and type(task.name) == "string" then
      local stat = uv.fs_stat(json_path)
      choices[#choices + 1] = {
        name = task.name,
        path = json_path,
        mtime = stat and stat.mtime.sec or 0,
        imported = is_file(path_join(root, "problems", M.problem_slug(task.name) .. ".cpp")),
      }
    end
  end

  if #choices == 0 then
    vim.notify("No .ast problems found under " .. root, vim.log.levels.INFO)
    return
  end

  vim.ui.select(choices, {
    prompt = "Import Codeforces problem",
    format_item = function(item)
      local suffix = item.imported and " (imported)" or ""
      return string.format("%s  %s%s", os.date("%H:%M:%S", item.mtime), item.name, suffix)
    end,
  }, function(choice)
    if choice then
      import_ast_problem(choice.path, { open_existing = true })
    end
  end)
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

local function archive_problem_file(source)
  local root = M.contest_root(source)
  local done_dir = path_join(root, ".done")
  local target = path_join(done_dir, vim.fn.fnamemodify(source, ":t"))
  local stem = vim.fn.fnamemodify(source, ":t:r")

  mkdir_p(done_dir)

  if is_file(target) then
    return false, target .. " already exists."
  end

  local ok, err = uv.fs_rename(source, target)
  if not ok then
    return false, "Could not move problem to .done: " .. tostring(err)
  end

  remove_file(path_join(vim.fn.fnamemodify(source, ":p:h"), stem))
  remove_file(path_join(root, stem))

  return true, target
end

local function write_loaded_buffer_for_path(path)
  path = vim.fn.fnamemodify(path, ":p")
  for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
    if vim.api.nvim_buf_is_loaded(bufnr) and vim.fn.fnamemodify(vim.api.nvim_buf_get_name(bufnr), ":p") == path then
      if vim.bo[bufnr].modified then
        vim.api.nvim_buf_call(bufnr, function()
          vim.cmd.write()
        end)
      end
      return bufnr
    end
  end
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

  local ok, result = archive_problem_file(source)
  if not ok then
    vim.notify(result, vim.log.levels.ERROR)
    return
  end

  local target = result
  vim.cmd.edit(vim.fn.fnameescape(target))
  vim.notify("Moved problem to " .. target)
end

function M.archive_all_problems()
  local root = M.contest_root(vim.fn.expand("%:p") ~= "" and vim.fn.expand("%:p") or vim.fn.getcwd())
  local problems_dir = path_join(root, "problems")
  local sources = vim.fn.glob(problems_dir .. "/*.cpp", false, true)

  table.sort(sources)

  if #sources == 0 then
    vim.notify("No C++ problems found in " .. problems_dir, vim.log.levels.INFO)
    return
  end

  local moved = {}
  local skipped = {}
  local current = vim.fn.expand("%:p")

  for _, source in ipairs(sources) do
    write_loaded_buffer_for_path(source)
    local ok, result = archive_problem_file(source)
    if ok then
      moved[source] = result
    else
      skipped[#skipped + 1] = vim.fn.fnamemodify(source, ":t") .. ": " .. result
    end
  end

  if moved[current] then
    vim.cmd.edit(vim.fn.fnameescape(moved[current]))
  end

  local moved_count = vim.tbl_count(moved)
  local message = string.format("Moved %d C++ problem%s to %s", moved_count, moved_count == 1 and "" or "s", path_join(root, ".done"))
  if #skipped > 0 then
    message = message .. string.format(" (%d skipped)", #skipped)
    vim.notify(table.concat(vim.list_extend({ message }, skipped), "\n"), vim.log.levels.WARN)
  else
    vim.notify(message)
  end
end

return M
