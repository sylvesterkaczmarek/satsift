'use strict';

const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadBrowserApp } = require('../tools/load_browser_app');

const context = { console, BigInt, Number, String, Math, Date, window: {} };
vm.createContext(context);
const api = loadBrowserApp(context, { start: false });
const definition = {
  schema: 'smd-event-benchmark-v1',
  cases: [{ case_id: 'synthetic', source: 'https://example.invalid/synthetic',
    input_text: api.exampleTles('leo'), label_status: 'unknown', truth_events: [] }]
};

assert.equal(api.normaliseBenchmarkDefinition(definition).toleranceHours, 24,
  'Only an omitted tolerance may use the documented default.');
for (const value of [0, 0.25, 24, 168]) {
  assert.equal(api.normaliseBenchmarkDefinition({ ...definition, matching_tolerance_hours: value }).toleranceHours, value);
}
const invalid = [null, false, true, [], [24], {}, '', ' ', 'junk', '0', '24',
  '1e2', '0x10', undefined, NaN, Infinity, -Infinity, -1, 168.000001];
for (const value of invalid) {
  assert.throws(() => api.normaliseBenchmarkDefinition({ ...definition, matching_tolerance_hours: value }),
    /matching_tolerance_hours.*finite.*number.*0.*168/,
    'Malformed or out-of-range explicit tolerance was accepted: ' + String(value));
}
assert.equal(api.normaliseBenchmarkDefinition(definition).cases[0].labelStatus, 'unknown');
console.log('Benchmark tolerance admission passed: omitted default, four numeric boundaries and ' + invalid.length + ' rejected explicit values.');
