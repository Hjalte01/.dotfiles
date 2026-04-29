return {
  {
    "folke/which-key.nvim",
    opts = function(_, opts)
      local function key_sort_value(item)
        local key = item.raw_key or item.key
        local parts = {}

        for i = 1, #key do
          local byte = key:byte(i)
          local char = key:sub(i, i)
          local lower = char:lower()

          if lower:match("%a") then
            local letter_index = lower:byte() - string.byte("a")
            local case_index = char == lower and 0 or 1
            parts[#parts + 1] = ("0%02d%d"):format(letter_index, case_index)
          else
            parts[#parts + 1] = ("1%03d"):format(byte)
          end
        end

        return table.concat(parts)
      end

      -- Keep the leader popup in key order, with a/A, b/B... first,
      -- then non-letter keys in their normal byte order.
      opts.sort = {
        key_sort_value,
      }
    end,
  },

  -- change some telescope options and a keymap to browse plugin files
  {
    "nvim-telescope/telescope.nvim",
    keys = {
      -- add a keymap to browse plugin files
      -- stylua: ignore
      {
        "<leader>fp",
        function() require("telescope.builtin").find_files({ cwd = require("lazy.core.config").options.root }) end,
        desc = "Find Plugin File",
      },
    },
    -- change some options
    opts = {
      defaults = {
        layout_strategy = "horizontal",
        layout_config = { prompt_position = "top" },
        sorting_strategy = "ascending",
        winblend = 0,
      },
    },
  },
}
