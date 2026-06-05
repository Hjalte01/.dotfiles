return {
  "L3MON4D3/LuaSnip",
  opts = function(_, opts)
    -- Load Lua snippets from ~/.config/nvim/snippets/
    require("luasnip.loaders.from_lua").lazy_load({
      paths = { vim.fn.stdpath("config") .. "/snippets" },
    })

    return opts
  end,
  keys = {
    {
      "<C-k>",
      function()
        local ls = require("luasnip")
        if ls.expand_or_jumpable() then
          ls.expand_or_jump()
        end
      end,
      mode = { "i", "s" },
      desc = "Expand or jump snippet",
      silent = true,
    },
    {
      "<C-j>",
      function()
        local ls = require("luasnip")
        if ls.jumpable(-1) then
          ls.jump(-1)
        end
      end,
      mode = { "i", "s" },
      desc = "Jump backward in snippet",
      silent = true,
    },
  },
  specs = {
    {
      "saghen/blink.cmp",
      optional = true,
      opts = {
        snippets = {
          preset = "luasnip",
        },
      },
    },
  },
}
