return {
  {
    "zbirenbaum/copilot.lua",
    opts = function(_, opts)
      local default_should_attach = require("copilot.config.should_attach").default
      local previous_should_attach = opts.should_attach or default_should_attach

      opts.should_attach = function(bufnr, bufname)
        if require("utils.project").is_codeforces_path(bufname) then
          return false
        end

        return previous_should_attach(bufnr, bufname)
      end
    end,
  },
}
