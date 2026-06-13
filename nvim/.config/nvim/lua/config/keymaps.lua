-- Keymaps are automatically loaded on the VeryLazy event
-- Default keymaps that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/keymaps.lua
-- Add any additional keymaps here

----------------------------------------
---  run c++
----------------------------------------
local opts = { noremap = true, silent = true }

----------------------------------------
--- Macro recording
----------------------------------------
vim.keymap.set("n", "Q", "q", { desc = "Record macro" })
vim.keymap.set("n", "q", "<Nop>", { desc = "Disable accidental macro recording" })

----------------------------------------
--- Helper functions
----------------------------------------
local function is_mapped(mode, lhs)
  if vim.keymap and vim.keymap.get then
    local maps = vim.keymap.get(mode, lhs)
    return maps and #maps > 0, maps
  end
end

----------------------------------------
--- Grep in Neovim config keymap
----------------------------------------
vim.keymap.set("n", "<leader>fC", function()
  require("snacks").picker.grep({
    title = "Grep Config",
    cwd = vim.fn.stdpath("config"),
  })
end, { desc = "Grep in Neovim config" })

----------------------------------------
--- Grep And Search files in Dotfiles config keymap
---------------------------------------
vim.keymap.set("n", "<leader>f.", function()
  require("snacks").picker.files({
    title = "Find Files in Dotfiles",
    cwd = vim.env.DOTFILES or "~/.dotfiles",
    hidden = true,
  })
end, { desc = "Find files in Dotfiles config" })
vim.keymap.set("n", "<leader>f:", function()
  require("snacks").picker.grep({
    title = "Grep Dotfiles",
    cwd = vim.env.DOTFILES or "~/.dotfies",
    hidden = true,
  })
end, { desc = "Grep in Dotfiles config" })

----------------------------------------
--- LSP helpers
----------------------------------------
vim.keymap.set("n", "<leader>cr", vim.lsp.buf.rename, { desc = "Rename Symbol" })

local function toggle_inlay_hints()
  if not vim.lsp.inlay_hint then
    vim.notify("Inlay hints are not supported by this Neovim version.", vim.log.levels.WARN)
    return
  end

  local enabled = vim.lsp.inlay_hint.is_enabled({ bufnr = 0 })
  vim.lsp.inlay_hint.enable(not enabled, { bufnr = 0 })
  vim.notify((enabled and "Disabled" or "Enabled") .. " inlay hints")
end

vim.api.nvim_create_user_command("LspRename", function()
  vim.lsp.buf.rename()
end, { desc = "Rename symbol under cursor" })

vim.api.nvim_create_user_command("ToggleInlayHints", toggle_inlay_hints, {
  desc = "Toggle LSP inlay hints in the current buffer",
})

vim.keymap.set("n", "<leader>uh", toggle_inlay_hints, { desc = "Toggle Inlay Hints" })

----------------------------------------
--- Copilot and completion integration
----------------------------------------
-- Smart <Tab>: Copilot if visible, else completion, else insert tab
vim.keymap.set("i", "<Tab>", function()
  local copilot_enabled = not require("utils.project").is_codeforces_buffer(0)
  local ok, s = pcall(require, "copilot.suggestion")
  if copilot_enabled and ok and s.is_visible() then
    s.accept()
    return ""
  end
  if vim.fn.pumvisible() == 1 then
    return "<C-n>"
  end
  return "\t"
end, { expr = true, silent = true })

-- Smart <S-Tab>: previous completion item, else backspace a tab stop
vim.keymap.set("i", "<S-Tab>", function()
  if vim.fn.pumvisible() == 1 then
    return "<C-p>"
  end
  return "<BS>"
end, { expr = true, silent = true })

----------------------------------------
--- Move lines keymaps
----------------------------------------
-- Move selected line / block of text in visual mode
vim.keymap.set("v", "J", ":m '>+1<CR>gv=gv", opts)
vim.keymap.set("v", "K", ":m '<-2<CR>gv=gv", opts)

----------------------------------------
--- Window management keymaps
----------------------------------------
-- Save and quit window with <leader>ww if not already mapped
local exists = is_mapped("n", "<leader>ww")
if not exists then
  vim.keymap.set("n", "<leader>ww", "<cmd>wq<cr>", { desc = "Save and Quit Window" })
else
  print("Mapping <leader>ww already exists")
end
----------------------------------------
--- easier to copy errors and such to clickboard
----------------------------------------
vim.keymap.set("n", "<leader>by", "<cmd>%y+<cr>", { desc = "Buffer Yank (Copy all)" })
-- Copy ALL notification history to clipboard instantly
vim.keymap.set("n", "<leader>bY", function()
  local history = require("snacks").notifier.get_history()
  local lines = {}
  for _, notif in ipairs(history) do
    -- Format: [Time] Level: Message
    local time = os.date("%H:%M", notif.added)
    table.insert(lines, string.format("[%s] %s: %s", time, notif.level, notif.msg))
  end

  local text = table.concat(lines, "\n")
  vim.fn.setreg("+", text) -- Put in system clipboard
  -- vim.notify("Copied " .. #lines .. " notifications to clipboard!")
end, { desc = "Copy ALL notifications to clipboard" })
