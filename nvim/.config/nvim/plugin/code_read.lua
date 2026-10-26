local function range(opts)
  return opts.range > 0 and { opts.line1, opts.line2 } or nil
end

vim.api.nvim_create_user_command("CodeRead", function(opts)
  require("utils.code_read").open(range(opts))
end, { range = true, desc = "Read this buffer or line range as a highlighted PDF in Zathura" })

vim.api.nvim_create_user_command("CodeExport", function(opts)
  require("utils.code_read").export(opts.args, range(opts), opts.bang)
end, { nargs = 1, complete = "file", range = true, bang = true, desc = "Export this buffer or line range to a PDF" })
