local Runner = require("utils.runner")

-- Map <leader>r to run the python file
vim.keymap.set("n", "<leader>r", Runner.run_python_file, {
  buffer = true,
  desc = "Run Python File"
})
