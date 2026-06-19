return {
  {
    "rcarriga/nvim-dap-ui",
    opts = {
      layouts = {
        {
          elements = {
            { id = "scopes", size = 0.76 },
            { id = "watches", size = 0.08 },
            { id = "stacks", size = 0.08 },
            { id = "breakpoints", size = 0.08 },
          },
          size = 45,
          position = "left",
        },
        {
          elements = {
            { id = "repl", size = 0.5 },
            { id = "console", size = 0.5 },
          },
          size = 8,
          position = "bottom",
        },
      },
    },
  },
}
