return {
  -- add pyright to lspconfig
  {
    "neovim/nvim-lspconfig",
    config = function()
      local nix_clangd = "/etc/profiles/per-user/" .. vim.env.USER .. "/bin/clangd"
      if vim.fn.executable(nix_clangd) == 1 then
        vim.g.lazyvim_cpp_tools = vim.g.lazyvim_cpp_tools or {}
        vim.g.lazyvim_cpp_tools.clangd_cmd = { nix_clangd }
      end
    end,
    ---@class PluginLspOpts
    opts = {
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
