local M = {}

local state = {
  active = false,
  bufnr = nil,
  help_win = nil,
  help_buf = nil,
}

local function when_stopped(callback)
  local dap = require("dap")
  local session = dap.session()

  if session and session.stopped_thread_id then
    callback()
    return
  end

  for _, candidate in pairs(dap.sessions()) do
    if candidate.stopped_thread_id then
      callback()
      return
    end
  end
end

local controls = {
  {
    key = "c",
    label = "continue",
    desc = "Continue to breakpoint",
    action = function()
      require("dap").continue()
    end,
  },
  {
    key = "n",
    label = "next",
    desc = "Step over current line",
    action = function()
      when_stopped(function()
        require("dap").step_over()
      end)
    end,
  },
  {
    key = "i",
    label = "into",
    desc = "Step into function",
    action = function()
      when_stopped(function()
        require("dap").step_into()
      end)
    end,
  },
  {
    key = "o",
    label = "out",
    desc = "Step out of function",
    action = function()
      when_stopped(function()
        require("dap").step_out()
      end)
    end,
  },
  {
    key = "b",
    label = "breakpoint",
    desc = "Toggle breakpoint",
    action = function()
      require("dap").toggle_breakpoint()
    end,
  },
  {
    key = "B",
    label = "conditional",
    desc = "Set conditional breakpoint",
    action = function()
      vim.ui.input({ prompt = "Breakpoint condition: " }, function(condition)
        if not condition or vim.trim(condition) == "" then
          return
        end
        require("dap").set_breakpoint(condition)
      end)
    end,
  },
  {
    key = "r",
    label = "cursor",
    desc = "Run to cursor",
    action = function()
      require("dap").run_to_cursor()
    end,
  },
  {
    key = "u",
    label = "ui",
    desc = "Toggle debugger UI",
    action = function()
      require("dapui").toggle({})
    end,
  },
  {
    key = "t",
    label = "terminate",
    desc = "Terminate debugger",
    action = function()
      require("dap").terminate()
    end,
  },
}

local function close_help()
  if state.help_win and vim.api.nvim_win_is_valid(state.help_win) then
    vim.api.nvim_win_close(state.help_win, true)
  end
  state.help_win = nil

  if state.help_buf and vim.api.nvim_buf_is_valid(state.help_buf) then
    vim.api.nvim_buf_delete(state.help_buf, { force = true })
  end
  state.help_buf = nil
end

function M.show_help()
  if state.help_win and vim.api.nvim_win_is_valid(state.help_win) then
    close_help()
    return
  end

  close_help()

  local lines = {
    "Debug mode",
    "",
    "  c  continue to breakpoint",
    "  n  next line / step over",
    "  i  step into function",
    "  o  step out of function",
    "  b  toggle breakpoint",
    "  B  conditional breakpoint, e.g. i == 7",
    "  r  run to cursor",
    "  u  toggle debugger UI",
    "  t  terminate debugger",
    "  ?  show this help",
    "  q  exit debug mode",
  }

  local width = 46
  local height = #lines
  local row = 1
  local col = math.max(0, vim.o.columns - width - 2)

  state.help_buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(state.help_buf, 0, -1, false, lines)
  vim.bo[state.help_buf].bufhidden = "wipe"

  state.help_win = vim.api.nvim_open_win(state.help_buf, false, {
    relative = "editor",
    row = row,
    col = col,
    width = width,
    height = height,
    border = "rounded",
    style = "minimal",
    title = " Debug keys ",
    title_pos = "center",
  })
end

function M.exit()
  if not state.active then
    return
  end

  close_help()

  local bufnr = state.bufnr
  state.active = false
  state.bufnr = nil

  if bufnr and vim.api.nvim_buf_is_valid(bufnr) then
    for _, control in ipairs(controls) do
      pcall(vim.keymap.del, "n", control.key, { buffer = bufnr })
    end
    pcall(vim.keymap.del, "n", "?", { buffer = bufnr })
    pcall(vim.keymap.del, "n", "q", { buffer = bufnr })
  end

  vim.notify("Debug mode off")
end

function M.is_active()
  return state.active
end

function M.enter()
  if state.active then
    M.show_help()
    return
  end

  local bufnr = vim.api.nvim_get_current_buf()
  state.active = true
  state.bufnr = bufnr

  for _, control in ipairs(controls) do
    vim.keymap.set("n", control.key, control.action, {
      buffer = bufnr,
      desc = "Debug mode: " .. control.desc,
      nowait = true,
      silent = true,
    })
  end

  vim.keymap.set("n", "?", M.show_help, {
    buffer = bufnr,
    desc = "Debug mode: show help",
    nowait = true,
    silent = true,
  })

  vim.keymap.set("n", "q", M.exit, {
    buffer = bufnr,
    desc = "Debug mode: exit",
    nowait = true,
    silent = true,
  })

  vim.api.nvim_create_autocmd({ "BufWipeout", "BufDelete" }, {
    buffer = bufnr,
    once = true,
    callback = function()
      if state.bufnr == bufnr then
        state.active = false
        state.bufnr = nil
        close_help()
      end
    end,
  })

  vim.notify("Debug mode on. Press ? for keys, q to exit.")
  M.show_help()
end

function M.toggle()
  if state.active then
    M.exit()
  else
    M.enter()
  end
end

return M
