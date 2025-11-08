-- ~/.config/nvim/lua/plugins/assistant.lua

return {
  -- 1. The plugin repository path
  "A7Lavinraj/assistant.nvim",

  -- 2. Configuration for the plugin
  -- This ensures the plugin's setup function is called after it is installed.
  config = function()
    require("assistant").setup({
      -- IMPORTANT: You must add the specific configuration options
      -- required by A7Lavinraj/assistant.nvim here, such as API keys
      -- or other user-defined settings.
      -- Example (check the plugin's README for actual required config):
      -- api_key = os.getenv("OPENAI_API_KEY"),
      -- model = "gpt-4o",
    })
  end,

  -- 3. Optional: Lazy-loading settings
  -- If the plugin registers a command, you can use `cmd` to load it only
  -- when that command is used, ensuring a fast startup time.
  -- cmd = "Assistant",
}
