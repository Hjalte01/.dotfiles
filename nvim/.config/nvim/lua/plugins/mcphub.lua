-- ~/.config/nvim/lua/plugins/mcphub.lua

return {
  "ravitemer/mcphub.nvim",
  dependencies = {
    "nvim-lua/plenary.nvim",
  },
  -- Change 1: Use the bundled build script instead of a global npm install
  build = "bundled_build.lua",
  config = function()
    require("mcphub").setup({
      port = 3000,
      -- Change 2: Tell the plugin to use the local binary it just built
      use_bundled_binary = true, 
      
      -- Change 3: Explicitly point to your dotfiles so it always finds the NixOS tool!
      config_path = vim.fn.expand("~/.dotfiles/mcpservers.json") 
    })
  end,
}
