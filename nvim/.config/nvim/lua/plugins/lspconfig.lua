return {
  -- add pyright to lspconfig
  {
    "neovim/nvim-lspconfig",
    ---@class PluginLspOpts
    opts = {
      inlay_hints = {
        enabled = false,
      },
      ---@type lspconfig.options
      servers = {
        -- pyright will be automatically installed with mason and loaded with lspconfig
        pyright = {},
        clangd = {
          mason = false,
          cmd = (function()
            local nix_clangd = "/etc/profiles/per-user/" .. vim.env.USER .. "/bin/clangd"
            if vim.fn.executable(nix_clangd) == 1 then
              return { nix_clangd }
            end
            return { "clangd" }
          end)(),
        },
      },
    },
  },

  -- for typescript, LazyVim also includes extra specs to properly setup lspconfig,
  -- treesitter, mason and typescript.nvim. So instead of the above, you can use:
}
