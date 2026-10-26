return {
  {
    "folke/noice.nvim",
    opts = function(_, opts)
      -- Neovim 0.12 uses separate message kinds for :! commands.
      opts.routes = opts.routes or {}
      table.insert(opts.routes, 1, {
        filter = {
          event = "msg_show",
          kind = { "shell_out", "shell_err", "shell_ret" },
        },
        view = "messages",
      })
    end,
  },
}
