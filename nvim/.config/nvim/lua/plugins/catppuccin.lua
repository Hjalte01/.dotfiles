return {
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = function()
        require("config.system-theme").apply()
      end,
    },
  },
  {
    "catppuccin/nvim",
    name = "catppuccin",
    lazy = false,
    priority = 1000,
    opts = {
      flavour = "mocha",
      background = { light = "latte", dark = "mocha" },
      transparent_background = false,
      styles = { comments = { "italic" }, keywords = { "bold" } },
    },
    config = function(_, opts)
      require("catppuccin").setup(opts)
    end,
  },
}
