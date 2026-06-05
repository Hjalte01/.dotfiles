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
    path = vim.api.nvim_buf_get_name(0),
  })[1]

  return path
end

vim.api.nvim_buf_create_user_command(0, "MarkdownPreview", function()
  preview_with_glow()
end, {
  desc = "Preview Markdown with Glow",
})

vim.api.nvim_buf_create_user_command(0, "ReadmePreview", function()
  local readme = find_readme()
  if not readme then
    vim.notify("No README.md found", vim.log.levels.WARN)
    return
  end

  preview_with_glow(readme)
end, {
  desc = "Preview nearest README.md with Glow",
})

vim.keymap.set("n", "<leader>r", preview_with_glow, {
  buffer = true,
  desc = "Preview Markdown with Glow",
})

vim.keymap.set("n", "<leader>R", function()
  vim.cmd.ReadmePreview()
end, {
  buffer = true,
  desc = "Preview README.md with Glow",
})
