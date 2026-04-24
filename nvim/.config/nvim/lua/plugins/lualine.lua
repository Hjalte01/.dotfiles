return {
  {
    "nvim-lualine/lualine.nvim",
    event = "VeryLazy",
    opts = function(_, opts)
      table.insert(opts.sections.lualine_x, {
        function()
          -- Check if codex is loaded before trying to call it
          local ok, codex = pcall(require, "codex")
          if ok then
            return codex.status()
          end
          return ""
        end,
      })
      table.insert(opts.sections.lualine_x, {
        function()
          return "😄"
        end,
      })
    end,
  },
}
