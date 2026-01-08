--- nvim/lua/plugins/treesitter.lua ---

return {
  {
    "nvim-treesitter/nvim-treesitter",
    -- branch = "master",
    lazy = false,
    build = ":TSUpdate",
    -- Optional: Add configuration options here if needed,
    -- but setting up parsers is often done via the `ensure_installed` option.
    -- opts = { ensure_installed = { "lua", "c", "cpp" } },
  },
}
