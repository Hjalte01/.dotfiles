# C++ Competitive Programming Cookbook

Use this as a phrase index for things you remember conceptually but not by C++ name.
Search examples: "string to int", "uppercase", "sort descending", "first greater", "min heap".

## Conversions

- string to int, parse integer: `std::stoi(s)`, `std::stoll(s)` for `long long`, `std::from_chars` for fast no-allocation parsing.
- int to string, number to string: `std::to_string(x)`.
- char digit to int: `c - '0'`.
- int digit to char: `char('0' + d)`.
- string to double: `std::stod(s)`.
- ascii to char code: `int(c)`.

```cpp
int x = stoi(s);
long long y = stoll(s);
string t = to_string(x);
int d = c - '0';
```

## Strings

- substring: `s.substr(pos, len)`.
- find substring, contains: `s.find(needle) != string::npos`.
- append char: `s.push_back(c)`.
- remove last char: `s.pop_back()`.
- reverse string: `reverse(s.begin(), s.end())`.
- sort characters: `sort(s.begin(), s.end())`.
- lowercase string, uppercase string: `transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return tolower(c); })`.
- lowercase char, uppercase char: `tolower((unsigned char)c)`, `toupper((unsigned char)c)`.
- check lowercase uppercase digit letter: `islower`, `isupper`, `isdigit`, `isalpha`, `isalnum`.
- getline with spaces: `getline(cin, s)`.
- skip newline before getline after `cin >> x`: `cin.ignore(numeric_limits<streamsize>::max(), '\n')`.
- split words by spaces: `stringstream ss(s); while (ss >> word)`.
- count chars in string fixed alphabet: `vector<int> cnt(26); for (char c : s) cnt[c - 'a']++;`.
- count chars in string any char: `map<char, int> cnt; for (char c : s) cnt[c]++;`.
- count strings, word frequencies: `map<string, int> cnt; cnt[word]++;`.

```cpp
if (s.find("abc") != string::npos) {}
string mid = s.substr(l, r - l + 1);
transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return tolower(c); });
char upper = toupper((unsigned char)c);

vector<int> cnt(26);
for (char c : s) cnt[c - 'a']++;
```

## Characters

- char to lower case: `tolower((unsigned char)c)`.
- char to upper case: `toupper((unsigned char)c)`.
- is digit: `isdigit((unsigned char)c)`.
- is letter: `isalpha((unsigned char)c)`.
- is lowercase: `islower((unsigned char)c)`.
- is uppercase: `isupper((unsigned char)c)`.
- digit character value: `c - '0'`.
- alphabet index lowercase: `c - 'a'`.
- alphabet index uppercase: `c - 'A'`.
- make lowercase letter from index: `char('a' + i)`.
- make uppercase letter from index: `char('A' + i)`.

```cpp
if (isdigit((unsigned char)c)) {
  int d = c - '0';
}
char lo = tolower((unsigned char)c);
char up = toupper((unsigned char)c);
```

## Vectors And Containers

- vector size: `v.size()`.
- add element: `v.push_back(x)`.
- remove last: `v.pop_back()`.
- clear vector: `v.clear()`.
- check empty: `v.empty()`.
- sort ascending: `sort(v.begin(), v.end())`.
- sort descending: `sort(v.rbegin(), v.rend())`.
- custom sort: `sort(v.begin(), v.end(), [](auto a, auto b) { return a.second < b.second; });`.
- unique sorted vector: `sort`, then `v.erase(unique(v.begin(), v.end()), v.end())`.
- fill vector with value: `fill(v.begin(), v.end(), value)`.
- make vector n copies: `vector<int> v(n, value)`.
- 2d vector grid: `vector<vector<int>> grid(n, vector<int>(m, value))`.
- sum vector: `accumulate(v.begin(), v.end(), 0LL)`.
- max element, min element: `*max_element(v.begin(), v.end())`, `*min_element(v.begin(), v.end())`.
- index of max element: `max_element(v.begin(), v.end()) - v.begin()`.

```cpp
sort(v.begin(), v.end());
v.erase(unique(v.begin(), v.end()), v.end());
```

## Binary Search

- first at least x, lower bound: `lower_bound(v.begin(), v.end(), x)`.
- first greater than x, upper bound: `upper_bound(v.begin(), v.end(), x)`.
- index from iterator: `int i = it - v.begin()`.
- count x in sorted vector: `upper_bound(...) - lower_bound(...)`.
- exists in sorted vector: `binary_search(v.begin(), v.end(), x)`.
- last less than x: `auto it = lower_bound(v.begin(), v.end(), x); if (it != v.begin()) --it;`.
- last at most x: `auto it = upper_bound(v.begin(), v.end(), x); if (it != v.begin()) --it;`.
- binary search answer: `while (lo < hi) { mid = ...; if (ok(mid)) hi = mid; else lo = mid + 1; }`.

```cpp
auto it = lower_bound(v.begin(), v.end(), x);
if (it != v.end()) {
  int idx = it - v.begin();
}
```

## Queues, Stacks, Heaps

- queue fifo: `queue<int> q`.
- stack lifo: `stack<int> st`.
- max heap, largest first: `priority_queue<int> pq`.
- min heap, smallest first: `priority_queue<int, vector<int>, greater<int>> pq`.
- heap of pairs: `priority_queue<pair<int,int>, vector<pair<int,int>>, greater<pair<int,int>>> pq`.

```cpp
priority_queue<int, vector<int>, greater<int>> pq;
pq.push(x);
int x = pq.top();
pq.pop();
```

## Maps And Sets

- ordered set: `set<int> s`.
- unordered hash set: `unordered_set<int> s`.
- ordered map: `map<string, int> mp`.
- hash map: `unordered_map<string, int> mp`.
- contains key: `mp.find(key) != mp.end()`, `s.count(x)`.
- frequency count: `mp[x]++`.
- string frequency map: `map<string, int> cnt; for (string s : words) cnt[s]++;`.
- first key >= x in set: `s.lower_bound(x)`.
- first key > x in set: `s.upper_bound(x)`.
- erase one value from multiset: `auto it = ms.find(x); if (it != ms.end()) ms.erase(it);`.
- iterate map key value: `for (auto [key, value] : mp)`.

```cpp
map<string, int> cnt;
for (string s : words) cnt[s]++;

for (auto [s, amount] : cnt) {
  cout << s << " " << amount << "\n";
}
```

## Pairs And Tuples

- pair first second: `p.first`, `p.second`.
- make pair: `pair<int,int>{a, b}`, `{a, b}`.
- sort vector of pairs: sorts by first, then second by default.
- structured binding pair: `auto [x, y] = p`.
- tuple get element: `get<0>(t)`, `get<1>(t)`.

```cpp
vector<pair<int, int>> vp;
sort(vp.begin(), vp.end());
for (auto [x, y] : vp) {}
```

## Math

- gcd greatest common divisor: `std::gcd(a, b)`.
- lcm least common multiple: `std::lcm(a, b)`.
- absolute value: `abs(x)`, `llabs(x)`.
- min max: `min(a, b)`, `max(a, b)`.
- clamp value: `clamp(x, lo, hi)`.
- power floating point: `pow(a, b)`.
- modulo negative fix: `(x % mod + mod) % mod`.
- ceiling division positive: `(a + b - 1) / b`.
- square root integer: `long long r = sqrt(x); while ((r + 1) * (r + 1) <= x) r++; while (r * r > x) r--;`.
- random number: `mt19937 rng(chrono::steady_clock::now().time_since_epoch().count())`.

```cpp
long long mod_norm(long long x, long long mod) {
  return (x % mod + mod) % mod;
}
```

## Prefix Sums

- prefix sum: `pref[i + 1] = pref[i] + a[i]`.
- range sum inclusive l r: `pref[r + 1] - pref[l]`.

```cpp
vector<long long> pref(n + 1);
for (int i = 0; i < n; i++) pref[i + 1] = pref[i] + a[i];
long long sum = pref[r + 1] - pref[l];
```

## Graphs

- adjacency list unweighted: `vector<vector<int>> g(n)`.
- adjacency list weighted: `vector<vector<pair<int,int>>> g(n)`.
- add undirected edge: `g[u].push_back(v); g[v].push_back(u);`.
- bfs shortest path unweighted: `queue<int>`, `dist[start] = 0`.
- dfs recursion: recursive lambda or function.
- dijkstra shortest path weighted nonnegative: min heap of `{dist, node}`.
- union find dsu: parent array with `find` path compression and `unite`.
- topological sort dag: indegree plus queue.
- grid directions 4-neighbor: `dx = {1,-1,0,0}`, `dy = {0,0,1,-1}`.
- grid directions 8-neighbor: include diagonals.

```cpp
vector<vector<int>> g(n);
g[u].push_back(v);
g[v].push_back(u);
```

## Grids

- 2d grid chars: `vector<string> grid(n)`.
- 2d grid ints: `vector<vector<int>> grid(n, vector<int>(m))`.
- inside bounds: `0 <= r && r < n && 0 <= c && c < m`.
- four directions: `int dr[4] = {1, -1, 0, 0}; int dc[4] = {0, 0, 1, -1};`.
- flatten grid index: `id = r * m + c`.

```cpp
int dr[4] = {1, -1, 0, 0};
int dc[4] = {0, 0, 1, -1};
for (int k = 0; k < 4; k++) {
  int nr = r + dr[k], nc = c + dc[k];
  if (0 <= nr && nr < n && 0 <= nc && nc < m) {}
}
```

## Bits

- check bit set: `(mask >> i) & 1`.
- set bit: `mask | (1 << i)`.
- clear bit: `mask & ~(1 << i)`.
- toggle bit: `mask ^ (1 << i)`.
- count bits: `__builtin_popcount(mask)`, `__builtin_popcountll(mask)`.
- least significant set bit value: `x & -x`.
- iterate submasks: `for (int sub = mask; sub; sub = (sub - 1) & mask)`.
- power of two check: `x > 0 && (x & (x - 1)) == 0`.

```cpp
for (int sub = mask; sub; sub = (sub - 1) & mask) {}
```

## STL Algorithms

- all true: `all_of(v.begin(), v.end(), pred)`.
- any true: `any_of(v.begin(), v.end(), pred)`.
- count value: `count(v.begin(), v.end(), x)`.
- count condition: `count_if(v.begin(), v.end(), pred)`.
- find value: `find(v.begin(), v.end(), x)`.
- next permutation: `next_permutation(v.begin(), v.end())`.
- reverse range: `reverse(v.begin(), v.end())`.
- rotate range: `rotate(v.begin(), v.begin() + k, v.end())`.

```cpp
int cnt = count_if(v.begin(), v.end(), [](int x) { return x % 2 == 0; });
```

## Common Headers

- competitive programming include all standard headers: `#include <bits/stdc++.h>`.
- use std namespace in contests: `using namespace std;`.
- fast input output: `ios::sync_with_stdio(false); cin.tie(nullptr);`.
