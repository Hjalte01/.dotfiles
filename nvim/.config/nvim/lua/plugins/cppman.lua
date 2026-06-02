return {
  "simonwinther/cppman.nvim",
  version = "*",
  cmd = "CPPMan",
  keys = {
    {
      "<localleader>cu",
      function()
        require("cppman").open_for(vim.fn.expand("<cword>"))
      end,
      desc = "[C++] open under cursor",
    },
    {
      "<localleader>ck",
      function()
        require("cppman").search()
      end,
      desc = "[C++] keyword search",
    },
  },
  dependencies = {
    "folke/snacks.nvim",
  },
  opts = {
    index = {
      db_path = (function()
        local matches = vim.fn.glob(
          "/nix/store/*-cppman-*/lib/python*/site-packages/cppman/lib/index.db",
          false,
          true
        )
        return matches[1]
      end)(),
    },
  },
}
