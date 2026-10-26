local M = {}
local previews = {}
local group = vim.api.nvim_create_augroup("CodeReadingPdf", { clear = true })

local function notify(message, level)
  vim.notify(message, level or vim.log.levels.ERROR, { title = "Code PDF" })
end

local function cache_dir()
  local path = vim.fn.stdpath("cache") .. "/code-reading"
  vim.fn.mkdir(path, "p", 448)
  return path
end

local function viewer_running(state)
  return state.viewer and vim.fn.jobwait({ state.viewer }, 0)[1] == -1
end

local function show_pdf(state)
  if viewer_running(state) then
    return
  end
  local config = cache_dir() .. "/zathura"
  vim.fn.mkdir(config, "p", 448)
  -- Preserve the PDF's syntax colors regardless of the desktop's recolor theme.
  vim.fn.writefile(
    { "set recolor false", "set adjust-open width", "set selection-clipboard clipboard" },
    config .. "/zathurarc"
  )
  state.viewer = vim.fn.jobstart({ "zathura", "--config-dir=" .. config, state.pdf }, {
    detach = true,
    stderr_buffered = true,
    on_stderr = function(_, lines)
      state.viewer_error = table.concat(lines, "\n")
    end,
    on_exit = function(_, code)
      if code ~= 0 then
        notify("Zathura failed: " .. (state.viewer_error or tostring(code)))
      end
    end,
  })
  if state.viewer <= 0 then
    notify("Could not start Zathura")
  end
end

local languages = {
  sh = "bash",
  zsh = "bash",
  javascriptreact = "jsx",
  typescriptreact = "tsx",
  dosini = "ini",
  tex = "latex",
}

local function snapshot(buf, range)
  local first = range and range[1] or 1
  local last = range and math.min(range[2], vim.api.nvim_buf_line_count(buf)) or -1
  local path = vim.api.nvim_buf_get_name(buf)
  local title = path ~= "" and vim.fn.fnamemodify(path, ":t") or "Untitled"
  if range then
    title = title .. string.format(" · lines %d–%d", first, last)
  end
  local ft = vim.bo[buf].filetype
  return {
    title = title,
    language = languages[ft] or (ft ~= "" and ft or vim.fn.fnamemodify(path, ":e")),
    first_line = first,
    tab_size = vim.bo[buf].tabstop,
    source = table.concat(vim.api.nvim_buf_get_lines(buf, first - 1, last, false), "\n"),
  }
end

local function convert(data, output, done)
  local work = vim.fn.tempname()
  vim.fn.mkdir(work, "p", 448)
  local ok, err = pcall(function()
    vim.fn.writefile({ vim.json.encode(data) }, work .. "/source.json")
    local template = vim.fn.stdpath("config") .. "/templates/code-reading.typ"
    vim.fn.writefile(vim.fn.readfile(template), work .. "/preview.typ")
  end)
  if not ok then
    vim.fn.delete(work, "rf")
    done(false, tostring(err))
    return
  end
  -- Compile off the main thread; publish the complete PDF with an atomic rename.
  local temporary = output .. "." .. vim.fn.getpid() .. "." .. vim.fn.fnamemodify(work, ":t") .. ".tmp.pdf"
  vim.system(
    { "typst", "compile", "--root", work, work .. "/preview.typ", temporary },
    { text = true },
    vim.schedule_wrap(function(result)
      vim.fn.delete(work, "rf")
      if result.code ~= 0 then
        vim.fn.delete(temporary)
        done(false, vim.trim(result.stderr or "PDF conversion failed"))
        return
      end
      local renamed, reason = vim.uv.fs_rename(temporary, output)
      if not renamed then
        vim.fn.delete(temporary)
      end
      done(renamed, reason)
    end)
  )
end

local function render(buf, state)
  if state.busy then
    state.pending = true
    return
  end
  if not vim.api.nvim_buf_is_loaded(buf) then
    return
  end
  state.busy = true
  convert(snapshot(buf, state.range), state.pdf, function(ok, err)
    state.busy = false
    if state.pending then
      state.pending = false
      render(buf, state)
      return
    end
    if not ok then
      state.open_requested = false
      notify("PDF conversion failed:\n" .. tostring(err))
      return
    end
    if state.open_requested then
      state.open_requested = false
      show_pdf(state)
    end
  end)
end

function M.open(range)
  for _, program in ipairs({ "typst", "zathura" }) do
    if vim.fn.executable(program) ~= 1 then
      notify(program .. " is required for code reading")
      return
    end
  end
  if not (vim.env.WAYLAND_DISPLAY or vim.env.DISPLAY) then
    notify("Zathura needs a graphical session; use :CodeExport path.pdf over SSH")
    return
  end
  local buf = vim.api.nvim_get_current_buf()
  local states = previews[buf]
  if not states then
    states = {}
    previews[buf] = states
    vim.api.nvim_create_autocmd("BufWritePost", {
      group = group,
      buffer = buf,
      callback = function()
        local full = states.full
        if full and (viewer_running(full) or full.open_requested) then
          render(buf, full)
        end
      end,
      desc = "Refresh the full code reading PDF on save",
    })
    vim.api.nvim_create_autocmd("BufWipeout", {
      group = group,
      buffer = buf,
      once = true,
      callback = function()
        previews[buf] = nil
      end,
    })
  end
  local key = range and (range[1] .. ":" .. range[2]) or "full"
  local state = states[key]
  if not state then
    local path = vim.api.nvim_buf_get_name(buf)
    local identity = (path ~= "" and path or ("unnamed:" .. vim.fn.getpid() .. ":" .. buf)) .. ":" .. key
    state = { pdf = cache_dir() .. "/" .. vim.fn.sha256(identity) .. ".pdf", range = range }
    states[key] = state
  end
  state.open_requested = true
  render(buf, state)
end

function M.export(path, range, overwrite)
  if vim.fn.executable("typst") ~= 1 then
    notify("Typst is required for PDF export")
    return
  end
  path = vim.fn.fnamemodify(vim.fn.expand(path), ":p")
  if not path:lower():match("%.pdf$") then
    notify("Choose an output filename ending in .pdf")
    return
  end
  if vim.uv.fs_stat(path) and not overwrite then
    notify("File exists; use :CodeExport! to replace it")
    return
  end
  if vim.fn.isdirectory(vim.fs.dirname(path)) ~= 1 then
    notify("The output directory does not exist")
    return
  end
  convert(snapshot(vim.api.nvim_get_current_buf(), range), path, function(ok, err)
    if ok then
      notify("Exported " .. path, vim.log.levels.INFO)
    else
      notify("PDF export failed:\n" .. tostring(err))
    end
  end)
end

return M
