local M = {}
local previous

function M.apply()
  local root = vim.env.XDG_CONFIG_HOME or (vim.env.HOME .. "/.config")
  local path = root .. "/dotfiles-theme/current/colors.json"
  local ok, lines = pcall(vim.fn.readfile, path)
  if not ok then return end
  local valid, palette = pcall(vim.json.decode, table.concat(lines, "\n"))
  if not valid or palette.scheme == previous then return end
  vim.o.background = palette.light and "light" or "dark"
  local applied = pcall(vim.cmd.colorscheme, palette.scheme)
  if applied then
    previous = palette.scheme
    vim.cmd.redraw()
  end
end

function M.watch()
  M.apply()
  local timer = vim.uv.new_timer()
  timer:start(100, 100, vim.schedule_wrap(M.apply))
  vim.api.nvim_create_autocmd("VimLeavePre", { once = true, callback = function()
    timer:stop()
    timer:close()
  end })
end

return M
