local M = {}

local function trim(s)
  return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function split_lines(text)
  text = text:gsub("\r\n", "\n"):gsub("\r", "\n")
  return vim.split(text, "\n", { plain = true })
end

local function trim_blank_lines(lines)
  local first = 1
  while first <= #lines and trim(lines[first]) == "" do
    first = first + 1
  end

  local last = #lines
  while last >= first and trim(lines[last]) == "" do
    last = last - 1
  end

  return vim.list_slice(lines, first, last)
end

local function read_block(lines, start_idx, stop_labels)
  local block = {}
  local truncated = false

  for i = start_idx, #lines do
    local line = lines[i]
    local key = trim(line)

    if stop_labels[key] then
      return trim_blank_lines(block), i, truncated
    end

    if key == "..." or key == "…" then
      truncated = true
      return trim_blank_lines(block), i + 1, truncated
    end

    block[#block + 1] = line
  end

  return trim_blank_lines(block), #lines + 1, truncated
end

local function maybe_adjust_visible_test_count(lines, was_truncated)
  if not was_truncated then
    return lines, nil
  end

  local first = 1
  while first <= #lines and trim(lines[first]) == "" do
    first = first + 1
  end

  local declared = tonumber(trim(lines[first] or ""))
  if not declared then
    return lines, nil
  end

  local visible = 0
  for i = first + 1, #lines do
    if trim(lines[i]) ~= "" then
      visible = visible + 1
    end
  end

  if visible > 0 and visible < declared then
    local adjusted = vim.deepcopy(lines)
    adjusted[first] = tostring(visible)
    return adjusted, string.format("adjusted first input line from %d to %d visible non-empty lines", declared, visible)
  end

  return lines, nil
end

local function parse_codeforces_submission(text)
  local lines = split_lines(text)
  local cases = {}

  for i, line in ipairs(lines) do
    if trim(line) == "Input" then
      local input, pos, input_truncated = read_block(lines, i + 1, {
        ["Participant's output"] = true,
        ["Jury's answer"] = true,
        ["Checker comment"] = true,
      })

      while pos <= #lines and trim(lines[pos]) ~= "Jury's answer" do
        pos = pos + 1
      end

      if pos <= #lines then
        local output, _, output_truncated = read_block(lines, pos + 1, {
          ["Checker comment"] = true,
          ["Input"] = true,
          ["Participant's output"] = true,
        })

        cases[#cases + 1] = {
          input = table.concat(input, "\n"),
          output = table.concat(output, "\n"),
          input_truncated = input_truncated,
          output_truncated = output_truncated,
        }
      end
    end
  end

  return cases[#cases]
end

local function parse_wrong_answer_token_index(text)
  return tonumber(text:match("[Ww]rong answer%s+(%d+)%a*%s+words?%s+differ"))
    or tonumber(text:match("(%d+)%a*%s+words?%s+differ"))
end

local function non_empty_lines(text)
  local out = {}
  for _, line in ipairs(split_lines(text)) do
    if trim(line) ~= "" then
      out[#out + 1] = trim(line)
    end
  end
  return out
end

local function tokens(text)
  local out = {}
  for token in text:gmatch("%S+") do
    out[#out + 1] = token
  end
  return out
end

local function append_competitest_case(input, output)
  local bufnr = vim.api.nvim_get_current_buf()
  local config = require("competitest.config")
  local testcases = require("competitest.testcases")

  config.load_buffer_config(bufnr)
  local tctbl = testcases.buf_get_testcases(bufnr)
  local tcnum = 0
  while tctbl[tcnum] do
    tcnum = tcnum + 1
  end

  tctbl[tcnum] = { input = input, output = output }
  testcases.buf_write_testcases(bufnr, tctbl)
  return tcnum
end

function M.import_clipboard_to_competitest()
  local text = vim.fn.getreg("+")
  if text == "" then
    text = vim.fn.getreg("*")
  end

  local parsed = parse_codeforces_submission(text)
  if not parsed or parsed.input == "" then
    vim.notify("No Codeforces Input/Jury's answer block found in clipboard.", vim.log.levels.WARN)
    return
  end

  local input_lines = split_lines(parsed.input)
  local adjusted_lines, adjustment = maybe_adjust_visible_test_count(input_lines, parsed.input_truncated)
  parsed.input = table.concat(adjusted_lines, "\n")

  local bufnr = vim.api.nvim_get_current_buf()
  local config = require("competitest.config")
  local testcases = require("competitest.testcases")
  local widgets = require("competitest.widgets")

  config.load_buffer_config(bufnr)
  local tctbl = testcases.buf_get_testcases(bufnr)
  local tcnum = 0
  while tctbl[tcnum] do
    tcnum = tcnum + 1
  end

  local function save_data(tc)
    if config.get_buffer_config(bufnr).testcases_use_single_file then
      tctbl[tcnum] = tc
      testcases.single_file.buf_write(bufnr, tctbl)
    else
      testcases.io_files.buf_write_pair(bufnr, tcnum, tc.input, tc.output)
    end
  end

  widgets.editor(bufnr, tcnum, parsed.input, parsed.output, save_data, vim.api.nvim_get_current_win())

  local notes = {}
  if parsed.input_truncated then
    notes[#notes + 1] = "input was truncated"
  end
  if parsed.output_truncated then
    notes[#notes + 1] = "answer was truncated"
  end
  if adjustment then
    notes[#notes + 1] = adjustment
  end

  if #notes > 0 then
    vim.notify("Imported visible Codeforces testcase: " .. table.concat(notes, "; ") .. ". Review before saving.")
  else
    vim.notify("Imported Codeforces testcase. Review and save with :wq.")
  end
end

function M.import_failed_clipboard_to_competitest()
  local text = vim.fn.getreg("+")
  if text == "" then
    text = vim.fn.getreg("*")
  end

  local failed_word = parse_wrong_answer_token_index(text)
  if not failed_word then
    vim.notify("No Codeforces 'wrong answer Nth words differ' comment found in clipboard.", vim.log.levels.WARN)
    return
  end

  local parsed = parse_codeforces_submission(text)
  if not parsed or parsed.input == "" or parsed.output == "" then
    vim.notify("No Codeforces Input/Jury's answer block found in clipboard.", vim.log.levels.WARN)
    return
  end

  local input_lines = non_empty_lines(parsed.input)
  local expected_tokens = tokens(parsed.output)
  local declared = tonumber(input_lines[1] or "")

  if not declared then
    vim.notify("Failed testcase import only supports visible multi-test input with a numeric first line.", vim.log.levels.WARN)
    return
  end

  if failed_word > #expected_tokens then
    vim.notify(
      string.format("Failed word %d is not visible in the copied Jury's answer block.", failed_word),
      vim.log.levels.WARN
    )
    return
  end

  local visible_cases = #input_lines - 1
  if failed_word > visible_cases then
    vim.notify(
      string.format(
        "Failed word %d is beyond the %d visible one-line input cases. Copy more of the page or use <leader>tC.",
        failed_word,
        visible_cases
      ),
      vim.log.levels.WARN
    )
    return
  end

  local input = "1\n" .. input_lines[failed_word + 1]
  local output = expected_tokens[failed_word]
  local tcnum = append_competitest_case(input, output)

  local notes = { string.format("appended failed visible case as testcase %d", tcnum) }
  if parsed.input_truncated or parsed.output_truncated then
    notes[#notes + 1] = "source was truncated"
  end
  if declared ~= visible_cases then
    notes[#notes + 1] = string.format("used visible case %d of declared %d", failed_word, declared)
  end

  vim.notify("Codeforces failed testcase import: " .. table.concat(notes, "; ") .. ".")
end

return M
