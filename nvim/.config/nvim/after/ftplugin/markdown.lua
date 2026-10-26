local function preview_with_glow(path)
  path = path or vim.api.nvim_buf_get_name(0)
  if path == "" then
    vim.notify("No markdown file to preview", vim.log.levels.WARN)
    return
  end

  local cmd = string.format("glow %s -w 80; echo ''; read -p 'Press Enter to exit...' ", vim.fn.shellescape(path))

  require("snacks.terminal")(cmd, {
    cwd = vim.fs.dirname(path) or vim.fn.getcwd(),
    persist = true,
    win = { position = "float" },
  })
end

local function find_readme()
  local path = vim.fs.find(function(name)
    return name:lower() == "readme.md"
  end, {
    upward = true,
    path = vim.fs.dirname(vim.api.nvim_buf_get_name(0)) or vim.fn.getcwd(),
  })[1]

  return path
end

vim.api.nvim_buf_create_user_command(0, "MarkdownPreview", function()
  require("utils.markdown_preview").open()
end, {
  desc = "Preview Markdown as PDF in Zathura (refreshes on save)",
})

vim.api.nvim_buf_create_user_command(0, "MarkdownPreviewTerminal", function()
  preview_with_glow()
end, {
  desc = "Preview Markdown with Glow inside Neovim",
})

vim.api.nvim_buf_create_user_command(0, "ReadmePreview", function()
  local readme = find_readme()
  if not readme then
    vim.notify("No README.md found", vim.log.levels.WARN)
    return
  end

  require("utils.markdown_preview").open(vim.fn.bufadd(readme))
end, {
  desc = "Preview nearest README.md as PDF in Zathura",
})

vim.keymap.set("n", "<leader>r", function()
  vim.cmd.MarkdownPreview()
end, {
  buffer = true,
  desc = "Preview Markdown as PDF in Zathura",
})

vim.keymap.set("n", "<leader>R", function()
  vim.cmd.ReadmePreview()
end, {
  buffer = true,
  desc = "Preview README.md as PDF in Zathura",
})
