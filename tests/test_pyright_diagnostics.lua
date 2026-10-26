-- Run with: nvim --headless -u NONE -l tests/test_pyright_diagnostics.lua
vim.opt.runtimepath:append(vim.fn.getcwd() .. "/nvim/.config/nvim")
local filter = require("utils.pyright_diagnostics")
local directory = vim.fn.tempname()
vim.fn.mkdir(directory, "p")
local path = directory .. "/sample.py"
local source = "# header\ncall(x)\n# footer\n"
local diagnostic = {
	code = "reportArgumentType",
	message = "Argument has incompatible type",
	range = { start = { line = 1, character = 0 }, ["end"] = { line = 1, character = 7 } },
}
local baseline_diagnostic = vim.deepcopy(diagnostic)
baseline_diagnostic.rule, baseline_diagnostic.code = diagnostic.code, nil
vim.fn.writefile(
	{
		vim.json.encode({
			version = 1,
			files = { ["sample.py"] = { source = source, diagnostics = { baseline_diagnostic } } },
		}),
	},
	directory .. "/.pyright-baseline.json"
)
local function write(text)
	vim.fn.writefile(vim.split(text:gsub("\n$", ""), "\n", { plain = true }), path)
end
write(source)
assert(#filter.filter(path, { diagnostic }) == 0, "unchanged upstream diagnostic")
write("# added\n" .. source)
local shifted = vim.deepcopy(diagnostic)
shifted.range.start.line, shifted.range["end"].line = 2, 2
assert(#filter.filter(path, { shifted }) == 0, "inserted lines must remap")
write(source:gsub("call%(x%)", "call(y)"))
assert(#filter.filter(path, { diagnostic }) == 1, "changed source must remain visible")
write(source)
local new_error = vim.deepcopy(diagnostic)
new_error.message = "New incompatible type"
assert(#filter.filter(path, { new_error }) == 1, "new error on original line")
local undefined = vim.deepcopy(diagnostic)
undefined.code = "reportUndefinedVariable"
assert(#filter.filter(path, { undefined }) == 1, "undefined name must remain visible")
local hint = vim.deepcopy(diagnostic)
hint.code, hint.tags = nil, { 1 }
assert(#filter.filter(path, { hint }) == 0, "inherited unused-code hint")
write(source:gsub("call%(x%)", "call(y)"))
assert(#filter.filter(path, { hint }) == 1, "hint in edited code must remain visible")
write(source)
vim.cmd.edit(path)
vim.api.nvim_buf_set_lines(0, 1, 2, false, { "call(y)" })
assert(#filter.filter(path, { diagnostic }) == 1, "must inspect unsaved changes")
assert(#filter.filter(path, { diagnostic }, true) == 0, "folder scan must inspect disk")
assert(#filter.filter(directory .. "/other.py", { diagnostic }) == 1, "file not in baseline")
filter.setup()
assert(vim.fn.exists(":PyrightProject") == 2, "folder command registered")
vim.fn.delete(directory, "rf")
print("PASS: baseline filtering, shifted lines, changed code, new errors, hints, unsaved edits, opt-in scope")
vim.cmd("qa!")
