vim.opt_local.keywordprg = ":Man 3"
vim.opt_local.expandtab = true
vim.opt_local.shiftwidth = 2
vim.opt_local.softtabstop = 2
vim.opt_local.tabstop = 2
vim.opt_local.autoindent = true
vim.opt_local.smartindent = true
vim.opt_local.cindent = true

vim.keymap.set("n", "<leader>a", "<cmd>Assistant<cr>", { buffer = true, desc = "Assistant.nvim" })

local Runner = require("utils.runner")
vim.keymap.set("n", "<leader>r", Runner.run_cpp_file, { buffer = true, desc = "Run C++ File" })

local OnlineJudge = require("utils.online_judge")
vim.keymap.set("n", "<leader>cs", OnlineJudge.submit_current_file, { buffer = true, desc = "Submit to Online Judge" })

local Competitive = require("utils.competitive")
Competitive.ensure_problem_file_location(vim.fn.expand("%:p"))
vim.api.nvim_create_autocmd("BufWritePost", {
  buffer = 0,
  callback = function(args)
    Competitive.ensure_problem_file_location(vim.api.nvim_buf_get_name(args.buf))
  end,
})
vim.keymap.set(
  "n",
  "<leader>cd",
  function()
    require("utils.competitive").archive_current_problem()
  end,
  { buffer = true, desc = "Archive Problem as Done" }
)
vim.keymap.set(
  "n",
  "<leader>cD",
  function()
    require("utils.competitive").archive_all_problems()
  end,
  { buffer = true, desc = "Archive All Problems as Done" }
)
