return {
  "johnseth97/codex.nvim",
  lazy = true,
  cmd = { "Codex", "CodexToggle" },
  keys = {
    {
      "<leader>ac",
      function()
        require("codex").toggle()
      end,
      desc = "Toggle Codex Agent",
      mode = { "n", "t" },
    },
  },
  opts = {
    keymaps = {
      toggle = nil,
      quit = "<C-q>",
    },
    border = "rounded",
    width = 0.8,
    height = 0.8,
    -- CRITICAL FOR NIXOS: Turn this off since we installed it manually in Step 1
    autoinstall = false,
    panel = false, -- Set to true if you prefer it docked to the side instead of floating!
    use_buffer = false,
  },
}
