local M = {}
local cache = {}

local function message_key(diagnostic, first, last)
  local range = diagnostic.range
  return table.concat({
    diagnostic.rule or diagnostic.code or "",
    diagnostic.message:gsub("%s+", " "),
    first,
    range.start.character,
    last,
    range["end"].character,
  }, "\0")
end

local function baseline_for(path)
  local file = vim.fs.find(".pyright-baseline.json", { path = vim.fs.dirname(path), upward = true })[1]
  if not file then
    return
  end
  local stat = vim.uv.fs_stat(file)
  local stamp = stat.mtime.sec .. ":" .. stat.mtime.nsec
  if not cache[file] or cache[file].stamp ~= stamp then
    local ok, data = pcall(function()
      local value = vim.json.decode(table.concat(vim.fn.readfile(file), "\n"))
      assert(value.version == 1 and type(value.files) == "table", "unsupported baseline")
      for _, entry in pairs(value.files) do
        entry.keys = {}
        for _, diagnostic in ipairs(entry.diagnostics) do
          entry.keys[message_key(diagnostic, diagnostic.range.start.line, diagnostic.range["end"].line)] = true
        end
      end
      return value
    end)
    cache[file] = { stamp = stamp, data = ok and data or nil }
    if not ok then
      vim.notify("Cannot read Pyright baseline: " .. tostring(data), vim.log.levels.WARN)
    end
  end
  local baseline = cache[file].data
  if baseline then
    local relative = path:sub(#vim.fs.dirname(file) + 2)
    return baseline.files[relative]
  end
end

-- Map current lines back to unchanged upstream lines, including unsaved edits.
local function unchanged_lines(original, current)
  local mapping = {}
  local old_line, new_line = 1, 1
  local function copy_until(stop)
    while old_line < stop do
      mapping[new_line - 1] = old_line - 1
      old_line, new_line = old_line + 1, new_line + 1
    end
  end
  for _, hunk in ipairs(vim.diff(original, current, { result_type = "indices", algorithm = "minimal" })) do
    local old_start = hunk[1] + (hunk[2] == 0 and 1 or 0)
    local new_start = hunk[3] + (hunk[4] == 0 and 1 or 0)
    copy_until(old_start)
    old_line, new_line = old_start + hunk[2], new_start + hunk[4]
  end
  local _, lines = original:gsub("\n", "\n")
  copy_until(lines + 1)
  return mapping
end

function M.filter(path, diagnostics, disk)
  local entry = baseline_for(path)
  if not entry then
    return diagnostics
  end
  local buf = vim.fn.bufnr(path)
  local lines
  if not disk and buf ~= -1 and vim.api.nvim_buf_is_loaded(buf) then
    lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
  else
    local ok, result = pcall(vim.fn.readfile, path)
    if not ok then
      return diagnostics
    end
    lines = result
  end
  local mapping = unchanged_lines(entry.source, table.concat(lines, "\n") .. "\n")
  return vim.tbl_filter(function(diagnostic)
    local first, last = diagnostic.range.start.line, diagnostic.range["end"].line
    if mapping[first] == nil then
      return true
    end
    for row = first, last do
      if mapping[row] ~= mapping[first] + row - first then
        return true
      end
    end
    -- The CLI omits unused-code hints. Hide these only on unchanged upstream lines.
    if vim.tbl_contains(diagnostic.tags or {}, 1) then
      return false
    end
    return not entry.keys[message_key(diagnostic, mapping[first], mapping[last])]
  end, diagnostics)
end

function M.publish(err, result, context, config)
  if result and result.diagnostics then
    result.diagnostics = M.filter(vim.uri_to_fname(result.uri), result.diagnostics)
  end
  return vim.lsp.diagnostic.on_publish_diagnostics(err, result, context, config)
end

function M.pull(err, result, context)
  if result and result.kind == "full" then
    result.items = M.filter(vim.uri_to_fname(context.params.textDocument.uri), result.items)
    for uri, related in pairs(result.relatedDocuments or {}) do
      if related.kind == "full" then
        related.items = M.filter(vim.uri_to_fname(uri), related.items)
      end
    end
  end
  return vim.lsp.diagnostic.on_diagnostic(err, result, context)
end

function M.setup()
  vim.api.nvim_create_user_command("PyrightProject", function(opts)
    local path = vim.api.nvim_buf_get_name(0)
    local root = vim.fs.root(path ~= "" and path or vim.fn.getcwd(), { "pyproject.toml", "pyrightconfig.json", ".git" })
      or vim.fn.getcwd()
    local executable = vim.fn.exepath("pyright")
    if executable == "" then
      vim.notify("pyright is not on PATH", vim.log.levels.ERROR)
      return
    end
    vim.notify("Checking Python files in " .. root)
    vim.system(
      { executable, "--outputjson", opts.args ~= "" and opts.args or "." },
      {
        cwd = root,
        text = true,
        timeout = 120000,
      },
      vim.schedule_wrap(function(result)
        local ok, report = pcall(vim.json.decode, result.stdout or "")
        if not ok or not report.generalDiagnostics or result.code > 1 then
          vim.notify(result.stderr ~= "" and result.stderr or "Pyright check failed", vim.log.levels.ERROR)
          return
        end
        local items, grouped, total = {}, {}, #report.generalDiagnostics
        for _, diagnostic in ipairs(report.generalDiagnostics) do
          grouped[diagnostic.file] = grouped[diagnostic.file] or {}
          table.insert(grouped[diagnostic.file], diagnostic)
        end
        local paths = vim.tbl_keys(grouped)
        table.sort(paths)
        for _, filename in ipairs(paths) do
          local diagnostics = opts.bang and grouped[filename] or M.filter(filename, grouped[filename], true)
          for _, diagnostic in ipairs(diagnostics) do
            items[#items + 1] = {
              filename = diagnostic.file,
              lnum = diagnostic.range.start.line + 1,
              col = diagnostic.range.start.character + 1,
              type = diagnostic.severity == "error" and "E" or "W",
              text = diagnostic.message:gsub("%s+", " ") .. " [" .. (diagnostic.rule or "") .. "]",
            }
          end
        end
        vim.fn.setqflist({}, " ", { title = "Pyright: " .. root, items = items })
        vim.cmd("copen")
        vim.notify(("Pyright: %d visible; %d inherited diagnostics hidden"):format(#items, total - #items))
      end)
    )
  end, { bang = true, nargs = "?", complete = "file", desc = "Check Python folder; ! includes upstream typing noise" })
end

return M
