const { readFileSync } = require('node:fs');
const { runInNewContext } = require('node:vm');
const { test } = require('node:test');
const assert = require('node:assert/strict');

// Exercise the actual pure comparison helpers without a browser or DOM fixture.
const source = readFileSync(`${__dirname}/app.js`, 'utf8');
const start = source.indexOf('const chartIdentity =');
const end = source.indexOf('function options(', start);
assert.ok(start >= 0 && end > start);
const { sameChartScope } = runInNewContext(
  `${source.slice(start, end)}; ({sameChartScope})`
);

test('stable chart IDs compare renamed charts only within the same filter scope', () => {
  const base = { chartId: 'top-trending', chart: 'Top Trending', appliedFilters: 'device=computer,age=all,country=all' };
  assert.equal(sameChartScope(base, { ...base, chart: 'Renamed trending chart' }), true);
  assert.equal(sameChartScope(base, { ...base, chartId: 'top-playing-now' }), false);
  assert.equal(sameChartScope(base, { ...base, appliedFilters: 'device=all,age=all,country=all' }), false);
  assert.equal(sameChartScope(base, { chart: 'Top Trending' }), false);
});

test('legacy chart names and seed records remain comparable within unknown scope', () => {
  assert.equal(sameChartScope({ chart: 'trending' }, { chart: 'Top Trending' }), true);
  assert.equal(sameChartScope({ chart: 'playing' }, { chart: 'Top Playing Now', appliedFilters: null }), true);
  assert.equal(sameChartScope({ chart: 'RBX Radar candidate sample' }, { chart: 'RBX Radar candidate sample' }), true);
  assert.equal(sameChartScope({ chart: 'Top Trending' }, { chart: 'RBX Radar candidate sample' }), false);
});
