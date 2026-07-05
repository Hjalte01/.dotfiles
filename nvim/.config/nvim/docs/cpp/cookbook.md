# C++ Competitive Programming Cookbook

Use this as a phrase index for things you remember conceptually but not by C++ name.
Search examples: "string to int", "uppercase", "sort descending", "first greater", "min heap".

## Codeforces Tags Quick Index

Search these exact words when a problem tag gives you the idea but not the C++ pattern.

- bitmasks, bits, xor: masks, subsets, parity, toggles, `a ^ b ^ a = b`.
- two pointers, 2pointers: sorted pair search, remove duplicates, shrinking windows.
- sliding window: maintain a valid contiguous range with add/remove operations.
- prefix sums, suffix sums: fast range sums, counts, xor prefixes.
- binary search: lower bound, upper bound, binary search answer.
- greedy: sort by useful order, take earliest/latest/smallest/largest locally safe choice.
- dynamic programming, dp: states, transitions, base cases, knapsack, subsequences.
- graphs, dfs, bfs, dsu: components, shortest paths, connectivity, trees.
- math, number theory: gcd, lcm, modular arithmetic, primes, divisors.
- implementation, debugging, timing: runtime clock, print containers, edge cases.

## Timing And Runtime Tests

- clock runtime, measure time, test algorithm speed: use `clock()` around the code.
- `clock()` measures CPU time used by the process, not wall time.
- Good for local testing only. Remove timing prints before submitting.

```cpp
clock_t startTime = clock();

// some code here

cout << double(clock() - startTime) / (double)CLOCKS_PER_SEC
     << " seconds." << endl;
```

Alternative with chrono:

```cpp
auto start = chrono::high_resolution_clock::now();

// some code here

auto stop = chrono::high_resolution_clock::now();
auto ms = chrono::duration_cast<chrono::milliseconds>(stop - start).count();
cerr << ms << " ms\n";
```

## Common Contest Tips

- Try tiny edge cases: `n = 0`, `n = 1`, all equal, already sorted, reverse sorted, negative numbers, maximum values.
- Watch overflow: use `long long` for sums, products, counts of pairs, and `mid = lo + (hi - lo) / 2`.
- For modulo subtraction: `(a - b + mod) % mod`.
- For sorted problems, ask whether sorting makes greedy, two pointers, binary search, or prefix sums possible.
- For "minimum possible maximum" or "maximum possible minimum", think binary search answer.
- For "subarray", think prefix sums, sliding window, two pointers, or Kadane.
- For "subsequence", think DP or greedy with positions.
- For "permutation", think sorting, cycles, inversions, or next permutation.
- For "tree", remember `n - 1` edges, DFS from any node, parent array, subtree sizes.
- Estimate complexity before coding: `n <= 2e5` usually wants `O(n log n)` or `O(n)`, not `O(n^2)`.

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
- prefix xor: `px[i + 1] = px[i] ^ a[i]`.
- range xor inclusive l r: `px[r + 1] ^ px[l]`.
- prefix counts: `cnt[i + 1][c] = cnt[i][c] + (s[i] == c)`.

```cpp
vector<long long> pref(n + 1);
for (int i = 0; i < n; i++) pref[i + 1] = pref[i] + a[i];
long long sum = pref[r + 1] - pref[l];
```

## Two Pointers

- two pointers, 2pointers sorted pair sum: move `l` or `r` based on current sum.
- two pointers remove duplicates sorted vector: keep write pointer.
- two pointers longest valid window: move `r` forward, then move `l` while invalid.
- Works best when moving a pointer only makes the condition change monotonically.

```cpp
int l = 0, r = n - 1;
while (l < r) {
  long long sum = a[l] + a[r];
  if (sum == target) {
    // found l, r
    break;
  } else if (sum < target) {
    l++;
  } else {
    r--;
  }
}
```

## Sliding Window

- sliding window contiguous range: add right element, remove left element.
- longest subarray with condition: expand `r`, shrink `l` while invalid.
- number of valid subarrays ending at r: after fixing window, add `r - l + 1`.
- Usually for nonnegative arrays, frequencies, distinct count, or constraints that can be repaired by moving `l`.

```cpp
int l = 0;
long long sum = 0, ans = 0;
for (int r = 0; r < n; r++) {
  sum += a[r];
  while (sum > limit) {
    sum -= a[l];
    l++;
  }
  ans = max(ans, (long long)r - l + 1);
}
```

## Greedy

- greedy sort intervals by ending time: take earliest finishing interval that fits.
- greedy minimize cost: often sort by cost, ratio, deadline, or value.
- exchange argument: prove any optimal answer can swap to your choice without becoming worse.
- If greedy fails, look for a small counterexample before coding more.

```cpp
sort(intervals.begin(), intervals.end(), [](auto a, auto b) {
  return a.second < b.second;
});

int taken = 0, lastEnd = INT_MIN;
for (auto [l, r] : intervals) {
  if (l >= lastEnd) {
    taken++;
    lastEnd = r;
  }
}
```

## Dynamic Programming

- dp state: what information must be remembered so the future is independent of the past.
- dp transition: try all choices from previous smaller states.
- dp base case: known answer for empty, first, or impossible state.
- initialize impossible max/min dp: use large `INF` or `-INF`.
- knapsack 0/1: loop capacity backwards so each item is used once.
- unbounded knapsack: loop capacity forwards so item can be reused.

```cpp
const long long INF = 4e18;
vector<long long> dp(target + 1, INF);
dp[0] = 0;
for (int x : coins) {
  for (int s = x; s <= target; s++) {
    dp[s] = min(dp[s], dp[s - x] + 1);
  }
}
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

```cpp
if ((mask >> i) & 1) {}
mask |= (1 << i);      // set bit
mask &= ~(1 << i);     // clear bit
mask ^= (1 << i);      // toggle bit
int cnt = __builtin_popcount(mask);
```

- iterate submasks: `for (int sub = mask; sub; sub = (sub - 1) & mask)`.
- power of two check: `x > 0 && (x & (x - 1)) == 0`.

```cpp
for (int sub = mask; sub; sub = (sub - 1) & mask) {}
bool isPowerOfTwo = x > 0 && (x & (x - 1)) == 0;
```

- xor same value cancels: `a ^ a = 0`.
- xor identity: `a ^ 0 = a`.
- xor principle: `a ^ b ^ a = b`.
- xor swap/cancel order does not matter: xor is associative and commutative.
- find unique when every other number appears twice: xor all numbers.

```cpp
int result = a ^ b ^ a; // result == b

int x = 0;
for (int value : a) x ^= value; // leaves the value that appears once
```

- bitmasks subsets: loop `mask` from `0` to `(1 << n) - 1`.

```cpp
for (int mask = 0; mask < (1 << n); mask++) {
  for (int i = 0; i < n; i++) {
    if ((mask >> i) & 1) {
      // use item i
    }
  }
}
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
