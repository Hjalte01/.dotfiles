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
        require("utils.competitive").import_latest_ast_problem()
      end, {})
    end,
    keys = {
      { "<leader>tr", "<cmd>CompetiTest run<cr>", desc = "Run Testcases" },
      { "<leader>ta", "<cmd>CompetiTest add_testcase<cr>", desc = "Add Testcase" },
      { "<leader>te", "<cmd>CompetiTest edit_testcase<cr>", desc = "Edit Testcase" },
      { "<leader>td", "<cmd>CompetiTest delete_testcase<cr>", desc = "Delete Testcase" },
      { "<leader>ts", "<cmd>CompetiTest show_ui<cr>", desc = "Show Test UI" },
      { "<leader>tc", "<cmd>CompetiTest receive testcases<cr>", desc = "Receive Testcases" },
      { "<leader>tp", "<cmd>CompetiTest receive problem<cr>", desc = "Receive Problem" },
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
        "<leader>tA",
        function()
          require("utils.competitive").import_latest_ast_problem()
        end,
        desc = "Import Latest .ast Problem",
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
          exec = "g++",
          args = {
            "-std=c++23",
            "-Wall",
            "-Wextra",
            "-O2",
            "$(FABSPATH)",
            "-o",
            "$(ABSDIR)/$(FNOEXT)",
          },
        },
      },
      run_command = {
        cpp = { exec = "$(ABSDIR)/$(FNOEXT)" },
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
