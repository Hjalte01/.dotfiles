local M = {}
local previews = {}
local group = vim.api.nvim_create_augroup("MarkdownPdfPreview", { clear = true })

local function notify(message, level)
  vim.notify(message, level or vim.log.levels.ERROR, { title = "Markdown preview" })
end

local function viewer_running(state)
  return state.viewer and vim.fn.jobwait({ state.viewer }, 0)[1] == -1
end

local function show_pdf(state)
  if viewer_running(state) then
    return
  end
  state.viewer = vim.fn.jobstart({ "zathura", state.pdf }, {
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

local function render(buf, state)
  if state.busy then
    state.pending = true
    return
  end
  if not vim.api.nvim_buf_is_loaded(buf) then
    return
  end

  local path = vim.api.nvim_buf_get_name(buf)
  local cwd = path ~= "" and vim.fs.dirname(path) or vim.fn.getcwd()
  local cache = vim.fn.stdpath("cache") .. "/markdown-preview"
  vim.fn.mkdir(cache, "p", 448)
  local identity = path ~= "" and path or ("unnamed:" .. vim.fn.getpid() .. ":" .. buf)
  state.pdf = state.pdf or (cache .. "/" .. vim.fn.sha256(identity) .. ".pdf")
  -- Publish only complete PDFs, so a failed conversion leaves the last preview intact.
  local temporary = state.pdf .. "." .. vim.fn.getpid() .. ".tmp.pdf"
  local source = table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n") .. "\n"
  state.busy = true
  vim.system(
    {
      "pandoc",
      "--from=markdown+autolink_bare_uris+task_lists+pipe_tables+strikeout",
      "--pdf-engine=typst",
      "--standalone",
      "--variable=papersize:a4",
      "--variable=fontsize:11pt",
      "--variable=mainfont:Libertinus Serif",
      "--output=" .. temporary,
    },
    { cwd = cwd, stdin = source, text = true },
    vim.schedule_wrap(function(result)
      state.busy = false
      if state.pending then
        state.pending = false
        vim.fn.delete(temporary)
        render(buf, state)
        return
      end
      if result.code ~= 0 then
        state.open_requested = false
        vim.fn.delete(temporary)
        notify("PDF conversion failed:\n" .. vim.trim(result.stderr or ""))
        return
      end
      local ok, err = vim.uv.fs_rename(temporary, state.pdf)
      if not ok then
        state.open_requested = false
        vim.fn.delete(temporary)
        notify("Could not update PDF: " .. tostring(err))
        return
      end
      if state.open_requested then
        state.open_requested = false
        show_pdf(state)
      end
    end)
  )
end

function M.open(buf)
  buf = buf or vim.api.nvim_get_current_buf()
  for _, program in ipairs({ "pandoc", "typst", "zathura" }) do
    if vim.fn.executable(program) ~= 1 then
      notify(program .. " is required for the PDF preview")
      return
    end
  end
  if not (vim.env.WAYLAND_DISPLAY or vim.env.DISPLAY) then
    notify("Zathura needs a graphical session; use :MarkdownPreviewTerminal over SSH")
    return
  end
  vim.fn.bufload(buf)
  local state = previews[buf]
  if not state then
    state = {}
    previews[buf] = state
    vim.api.nvim_create_autocmd("BufWritePost", {
      group = group,
      buffer = buf,
      callback = function()
        if viewer_running(state) or state.open_requested then
          render(buf, state)
        end
      end,
      desc = "Refresh an open Markdown PDF preview on save",
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
  state.open_requested = true
  render(buf, state)
end

return M
