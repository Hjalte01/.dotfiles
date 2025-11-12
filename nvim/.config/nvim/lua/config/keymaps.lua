-- Keymaps are automatically loaded on the VeryLazy event
-- Default keymaps that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/keymaps.lua
-- Add any additional keymaps here

-- Define the mapping using LazyVim's utility

----------------------------------------
---  run c++
----------------------------------------
local Runner = require("utils.runner")
vim.keymap.set("n", "<leader>r", Runner.run_cpp_file, { desc = "Run C++ File" })

----------------------------------------
--- Grep in Neovim config keymap
----------------------------------------
vim.keymap.set("n", "<leader>fC", function()
  require("snacks").picker.grep({
    title = "Grep Config",
    cwd = vim.fn.stdpath("config"),
  })
end, { desc = "Grep in Neovim config" })
