-- ~/.dotfiles/nvim/.config/nvim/after/ftplugin/markdown.lua

vim.keymap.set("n", "<leader>r", function()
  local filename = vim.fn.expand("%")
  -- Uses glow to render the markdown, and waits for you to press Enter to close
  local cmd = string.format("glow %s -w 80; echo ''; read -p 'Press Enter to exit...' ", filename)

  require("snacks.terminal")(cmd, {
    cwd = vim.fn.getcwd(),
    persist = true,
    win = { position = "float" },
  })
end, {
  buffer = true,
  desc = "Preview Markdown with Glow",
})
