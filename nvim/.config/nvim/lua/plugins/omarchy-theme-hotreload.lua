return {
  {
    name = "theme-hotreload",
    dir = vim.fn.stdpath("config"),
    lazy = false,
    config = function()
      vim.api.nvim_create_autocmd("VimEnter", { once = true, callback = function()
        require("config.system-theme").watch()
      end })
    end,
  },
}
