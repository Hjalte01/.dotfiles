return {
  "brenoprata10/nvim-highlight-colors",
  event = "VeryLazy",
  opts = {
    -- "background" highlights the text background.
    -- "virtual" puts a little colored square next to the hex code.
    render = "virtual",

    -- Show a little colored icon next to the text
    virtual_symbol = "■",

    -- Enable highlighting for CSS rgb() and hsl() functions too
    enable_named_colors = true,
  },
}
