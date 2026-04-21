-- ~/.config/nvim/lua/plugins/codecompanion.lua

return {
  "olimorris/codecompanion.nvim",
  dependencies = {
    "nvim-lua/plenary.nvim",
    "nvim-treesitter/nvim-treesitter",
    "ravitemer/mcphub.nvim", -- Ensure MCP hub loads first
  },
  config = function()
    require("codecompanion").setup({
      adapters = {
        gemini = function()
          return require("codecompanion.adapters").extend("gemini", {
            env = {
              -- Replace this with however you prefer to source your key.
              -- e.g., "cmd:cat ~/.gemini_api_key" or "GEMINI_API_KEY"
              api_key = "cmd:cat ~/.gemini_api_key",
            },
          })
        end,
      },
      strategies = {
        chat = {
          adapter = "gemini",
          tools = {
            ["mcp"] = {
              callback = function()
                return require("mcphub.extensions.codecompanion")
              end,
              description = "Call tools and resources from the MCP Servers",
            },
          },
        },
        inline = {
          adapter = "gemini",
        },
      },
    })
  end,
  keys = {
    -- Mapping <leader>a to open the CodeCompanion Chat
    { "<leader>a", "<cmd>CodeCompanionChat Toggle<cr>", mode = { "n", "v" }, desc = "Toggle AI Chat" },
    -- Mapping <leader>A to prompt CodeCompanion for inline editing
    { "<leader>A", "<cmd>CodeCompanionActions<cr>", mode = { "n", "v" }, desc = "AI Actions" },
  },
}
