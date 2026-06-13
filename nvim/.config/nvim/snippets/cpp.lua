local ls = require("luasnip")
local s = ls.snippet
local t = ls.text_node
local i = ls.insert_node
local fmt = require("luasnip.extras.fmt").fmt

return {
  s(
    "cpp",
    fmt(
      [[
#include <bits/stdc++.h>
using namespace std;

typedef long long ll;

#define F first
#define S second
#define PB push_back
#define MP make_pair


int main() {{
  ios::sync_with_stdio(0);
  cin.tie(0);

  ll n, k;
  cin >> n >> k;

  {}
  return 0;
}}
]],
      {
        i(1--[[, "// code here"--]]),
      }
    )
  ),
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
