vim.keymap.set("n", "<leader>a", "<cmd>Assistant<cr>", { buffer = true, desc = "Assistant.nvim" })

local Runner = require("utils.runner")
vim.keymap.set("n", "<leader>r", Runner.run_cpp_file, { buffer = true, desc = "Run C++ File" })
