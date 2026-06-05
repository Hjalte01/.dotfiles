-- ~/.config/nvim/lua/plugins/assistant.lua

return {
  -- 1. The plugin repository path
  "A7Lavinraj/assistant.nvim",

  -- 2. Configuration for the plugin
  -- This ensures the plugin's setup function is called after it is installed.
  config = function()
    local cpp_template = vim.fn.stdpath("config") .. "/templates/main.cpp"

    require("assistant").setup({
      commands = {
        cpp = {
          extension = "cpp",
          template = cpp_template,
          compile = {
            main = "g++",
            args = {
              "$FILENAME_WITH_EXTENSION",
              "-std=c++23",
              "-Wall",
              "-Wextra",
              "-O2",
              "-o",
              "$FILENAME_WITHOUT_EXTENSION",
            },
          },
          execute = {
            main = "./$FILENAME_WITHOUT_EXTENSION",
            args = nil,
          },
        },
      },
      -- IMPORTANT: You must add the specific configuration options
      -- required by A7Lavinraj/assistant.nvim here, such as API keys
      -- or other user-defined settings.
      -- Example (check the plugin's README for actual required config):
      -- api_key = os.getenv("OPENAI_API_KEY"),
      -- model = "gpt-4o",
    })

    require("assistant.config").values.commands.python = nil

    local picker = require("assistant.builtins.__picker").standard
    local original_pick = picker.pick
    picker.pick = function(self, items, options, on_choice)
      if options and options.prompt == "source" and vim.tbl_contains(items, "cpp") then
        on_choice(nil)
        return
      end

      return original_pick(self, items, options, on_choice)
    end
  end,

  -- 3. Optional: Lazy-loading settings
  -- If the plugin registers a command, you can use `cmd` to load it only
  -- when that command is used, ensuring a fast startup time.
  -- cmd = "Assistant",
}
