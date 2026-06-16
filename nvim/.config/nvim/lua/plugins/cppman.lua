local cookbook_path = vim.fn.stdpath("config") .. "/docs/cpp/cookbook.md"
local review_section = "## Codex Cookbook Review"

local function visual_selection_lines()
  local start_pos = vim.fn.getpos("'<")
  local end_pos = vim.fn.getpos("'>")
  local start_line, start_col = start_pos[2], start_pos[3]
  local end_line, end_col = end_pos[2], end_pos[3]

  if start_line > end_line or (start_line == end_line and start_col > end_col) then
    start_line, end_line = end_line, start_line
    start_col, end_col = end_col, start_col
  end

  local lines = vim.api.nvim_buf_get_lines(0, start_line - 1, end_line, false)
  if #lines == 0 then
    return {}, start_line, end_line
  end

  if #lines == 1 then
    lines[1] = lines[1]:sub(start_col, end_col)
  else
    lines[1] = lines[1]:sub(start_col)
    lines[#lines] = lines[#lines]:sub(1, end_col)
  end

  return lines, start_line, end_line
end

local function ensure_review_section(lines)
  for _, line in ipairs(lines) do
    if line == review_section then
      return
    end
  end

  if #lines > 0 and lines[#lines] ~= "" then
    lines[#lines + 1] = ""
  end
  lines[#lines + 1] = review_section
  lines[#lines + 1] = ""
  lines[#lines + 1] = "Snippets captured from visual selections for later cleanup and review."
end

local function append_selection_to_cookbook()
  local selected, start_line, end_line = visual_selection_lines()
  if #selected == 0 then
    vim.notify("No visual selection to add to cookbook", vim.log.levels.WARN)
    return
  end

  local lines = vim.fn.filereadable(cookbook_path) == 1 and vim.fn.readfile(cookbook_path) or {}
  ensure_review_section(lines)

  local source = vim.fn.expand("%:.")
  local title = vim.fn.input("Cookbook note: ")
  if title == "" then
    title = "Review snippet"
  end

  vim.list_extend(lines, {
    "",
    "### " .. title,
    "",
    ("Source: `%s:%d-%d`"):format(source, start_line, end_line),
    "",
    "```cpp",
  })
  vim.list_extend(lines, selected)
  lines[#lines + 1] = "```"

  vim.fn.writefile(lines, cookbook_path)
  vim.notify("Added selection to C++ cookbook review")
end

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
    {
      "<localleader>cs",
      function()
        require("snacks").picker.grep({
          title = "C++ Cookbook",
          cwd = vim.fn.stdpath("config") .. "/docs/cpp",
          hidden = true,
        })
      end,
      desc = "[C++] cookbook search",
    },
    {
      "<localleader>ca",
      append_selection_to_cookbook,
      mode = "v",
      desc = "[C++] add selection to cookbook review",
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
