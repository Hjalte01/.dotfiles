local cookbook_path = vim.fn.stdpath("config") .. "/docs/cpp/cookbook.md"
local review_section = "## Codex Cookbook Review"

local function resolve_cookbook_item_path(item)
  if not item or not item.file then
    return nil
  end

  if vim.fn.fnamemodify(item.file, ":p") == item.file then
    return item.file
  end

  return vim.fs.joinpath(vim.fn.stdpath("config"), "docs/cpp", item.file)
end

local function section_end(lines, start_line)
  for i = start_line + 1, #lines do
    if lines[i]:match("^##%s+") then
      return i - 1
    end
  end

  return #lines
end

local function code_block_around_or_after(lines, line_nr)
  local open_line

  for i = 1, line_nr do
    if lines[i]:match("^```") then
      open_line = open_line and nil or i
    end
  end

  if open_line then
    for i = line_nr + 1, #lines do
      if lines[i]:match("^```") then
        return vim.list_slice(lines, open_line + 1, i - 1)
      end
    end
  end

  local last_heading = 1
  for i = line_nr, 1, -1 do
    if lines[i]:match("^##%s+") then
      last_heading = i
      break
    end
  end

  local stop_line = section_end(lines, last_heading)
  for i = line_nr + 1, stop_line do
    if lines[i]:match("^```") then
      for j = i + 1, stop_line do
        if lines[j]:match("^```") then
          return vim.list_slice(lines, i + 1, j - 1)
        end
      end
      break
    end
  end

  return nil
end

local function yank_cookbook_code_block(picker, item, action)
  local path = resolve_cookbook_item_path(item)
  local line_nr = item and item.pos and item.pos[1] or nil
  if not path or not line_nr or vim.fn.filereadable(path) ~= 1 then
    vim.notify("Could not find cookbook entry to yank", vim.log.levels.WARN)
    return
  end

  local lines = vim.fn.readfile(path)
  local block = code_block_around_or_after(lines, line_nr)
  if not block or #block == 0 then
    vim.notify("No code block found for this cookbook entry", vim.log.levels.WARN)
    return
  end

  local reg = action and action.reg or vim.v.register
  local value = table.concat(block, "\n")
  vim.fn.setreg(reg, value)
  vim.notify(("Yanked cookbook code block to register `%s`"):format(reg), vim.log.levels.INFO)
end

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
          actions = {
            cookbook_yank_code_block = yank_cookbook_code_block,
          },
          win = {
            input = {
              keys = {
                ["yy"] = { "cookbook_yank_code_block", mode = "n" },
              },
            },
            list = {
              keys = {
                ["yy"] = "cookbook_yank_code_block",
              },
            },
          },
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
