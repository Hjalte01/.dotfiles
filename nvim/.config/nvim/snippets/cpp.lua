local ls = require("luasnip")
local s = ls.snippet
local i = ls.insert_node
local fmt = require("luasnip.extras.fmt").fmt

local function cpp_template_snippet()
  local path = vim.fn.stdpath("config") .. "/templates/main.cpp"
  local template = table.concat(vim.fn.readfile(path), "\n")
  local body, cursor_count = template:gsub("(\n  while %(t%-%-%) {\n)[ \t]*\n", "%1    $1\n", 1)

  assert(cursor_count == 1, "Could not find the cpp snippet cursor position in " .. path)
  return ls.parser.parse_snippet("cpp", body)
end

return {
  cpp_template_snippet(),
  s(
    "strcnt",
    fmt(
      [[
vector<int> cnt(26);
for (char c : {}) {{
  cnt[c - 'a']++;
}}
]],
      {
        i(1, "s"),
      }
    )
  ),
  s(
    "strmap",
    fmt(
      [[
map<string, int> cnt;
for (string s : {}) {{
  cnt[s]++;
}}
]],
      {
        i(1, "words"),
      }
    )
  ),
}
