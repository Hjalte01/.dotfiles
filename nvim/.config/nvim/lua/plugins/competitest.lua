local function focus_competitest_ui()
  for _, win in ipairs(vim.api.nvim_list_wins()) do
    local buf = vim.api.nvim_win_get_buf(win)
    local ok, title = pcall(vim.api.nvim_buf_get_var, buf, "competitest_title")
    if ok and title == "Testcases" then
      vim.api.nvim_set_current_win(win)
      return
    end
  end

  local ok = pcall(vim.cmd, "CompetiTest show_ui")
  if not ok then
    vim.notify("No CompetiTest UI found. Run tests from a solution buffer first.", vim.log.levels.WARN)
  end
end

local competitest_window_order = {
  "Testcases",
  "Output",
  "Expected Output",
  "Input",
  "Errors",
}

local function competitest_title(buf)
  local ok, title = pcall(vim.api.nvim_buf_get_var, buf, "competitest_title")
  if ok then
    return title
  end
end

local function cycle_competitest_window(direction)
  local windows_by_title = {}
  for _, win in ipairs(vim.api.nvim_list_wins()) do
    local title = competitest_title(vim.api.nvim_win_get_buf(win))
    if title then
      windows_by_title[title] = win
    end
  end

  local current_title = competitest_title(vim.api.nvim_get_current_buf())
  if not current_title then
    return
  end

  local current_index = 1
  for index, title in ipairs(competitest_window_order) do
    if title == current_title then
      current_index = index
      break
    end
  end

  for offset = 1, #competitest_window_order do
    local index = ((current_index - 1 + direction * offset) % #competitest_window_order) + 1
    local win = windows_by_title[competitest_window_order[index]]
    if win and vim.api.nvim_win_is_valid(win) then
      vim.api.nvim_set_current_win(win)
      return
    end
  end
end

local function install_competitest_tab_maps()
  for _, win in ipairs(vim.api.nvim_list_wins()) do
    local buf = vim.api.nvim_win_get_buf(win)
    if competitest_title(buf) and not vim.b[buf].competitest_tab_maps then
      vim.b[buf].competitest_tab_maps = true
      vim.keymap.set("n", "<Tab>", function()
        cycle_competitest_window(1)
      end, { buffer = buf, desc = "Next CompetiTest Window" })
      vim.keymap.set("n", "<S-Tab>", function()
        cycle_competitest_window(-1)
      end, { buffer = buf, desc = "Previous CompetiTest Window" })
    end
  end
end

local function run_competitest(command)
  vim.cmd("CompetiTest " .. command)
  vim.defer_fn(install_competitest_tab_maps, 50)
end

return {
  {
    "xeluxee/competitest.nvim",
    dependencies = { "MunifTanjim/nui.nvim" },
    cmd = "CompetiTest",
    init = function()
      vim.api.nvim_create_user_command("CodeforcesImportClipboard", function()
        require("utils.codeforces").import_clipboard_to_competitest()
      end, {})
      vim.api.nvim_create_user_command("CodeforcesImportFailed", function()
        require("utils.codeforces").import_failed_clipboard_to_competitest()
      end, {})
      vim.api.nvim_create_user_command("CodeforcesImportLatestAst", function()
        require("utils.competitive").pull_and_import_latest_ast_problem()
      end, {})
      vim.api.nvim_create_user_command("CodeforcesImportAst", function()
        require("utils.competitive").choose_ast_problem()
      end, {})
      vim.api.nvim_create_autocmd({ "BufEnter", "WinEnter" }, {
        callback = install_competitest_tab_maps,
      })
    end,
    keys = {
      {
        "<leader>tr",
        function()
          run_competitest("run")
        end,
        desc = "Run Testcases",
      },
      {
        "<leader>tD",
        function()
          require("utils.cpp_debug").debug_current_testcase()
        end,
        desc = "Debug Testcase",
      },
      { "<leader>wt", focus_competitest_ui, desc = "Focus Test UI" },
      { "<leader>ta", "<cmd>CompetiTest add_testcase<cr>", desc = "Add Testcase" },
      { "<leader>te", "<cmd>CompetiTest edit_testcase<cr>", desc = "Edit Testcase" },
      { "<leader>td", "<cmd>CompetiTest delete_testcase<cr>", desc = "Delete Testcase" },
      {
        "<leader>ts",
        function()
          run_competitest("show_ui")
        end,
        desc = "Show Test UI",
      },
      { "<leader>tc", "<cmd>CompetiTest receive testcases<cr>", desc = "Receive Testcases" },
      { "<leader>tR", "<cmd>CompetiTest receive problem<cr>", desc = "Receive Problem" },
      {
        "<leader>tC",
        function()
          require("utils.codeforces").import_clipboard_to_competitest()
        end,
        desc = "Import Codeforces Clipboard",
      },
      {
        "<leader>tF",
        function()
          require("utils.codeforces").import_failed_clipboard_to_competitest()
        end,
        desc = "Import Codeforces Failed Case",
      },
      {
        "<leader>tp",
        function()
          require("utils.competitive").pull_and_import_latest_ast_problem()
        end,
        desc = "Pull and Import Latest .ast Problem",
      },
      {
        "<leader>tP",
        function()
          require("utils.competitive").choose_ast_problem()
        end,
        desc = "Choose .ast Problem",
      },
    },
    opts = {
      runner_ui = {
        interface = "popup",
      },
      popup_ui = {
        total_width = 0.85,
        total_height = 0.85,
      },
      compile_command = {
        cpp = {
          exec = "bash",
          args = {
            vim.fn.stdpath("config") .. "/scripts/competitest-cpp",
            "compile",
            "$(FABSPATH)",
            "$(FNOEXT)",
          },
        },
      },
      run_command = {
        cpp = {
          exec = "bash",
          args = {
            vim.fn.stdpath("config") .. "/scripts/competitest-cpp",
            "run",
            "$(FABSPATH)",
            "$(FNOEXT)",
          },
        },
      },
      maximum_time = 5000,
      output_compare_method = "squish",
      view_output_diff = true,
      testcases_directory = "../.tests",
      testcases_auto_detect_storage = true,
      template_file = {
        cpp = vim.fn.stdpath("config") .. "/templates/main.cpp",
      },
      received_files_extension = "cpp",
      received_problems_path = function(task, file_extension)
        return require("utils.competitive").problem_path(task.name, file_extension)
      end,
      received_contests_directory = function()
        return require("utils.competitive").contest_root(vim.fn.getcwd())
      end,
      received_contests_problems_path = function(task, file_extension)
        return "problems/" .. require("utils.competitive").problem_slug(task.name) .. "." .. file_extension
      end,
      received_problems_prompt_path = false,
      received_contests_prompt_directory = false,
      received_contests_prompt_extension = false,
      replace_received_testcases = true,
    },
  },
}
