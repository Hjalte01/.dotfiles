return {
  "L3MON4D3/LuaSnip",
  opts = function(_, opts)
    -- Load Lua snippets from ~/.config/nvim/snippets/
    require("luasnip.loaders.from_lua").lazy_load({
      paths = { vim.fn.stdpath("config") .. "/snippets" },
    })

    return opts
  end,
}
