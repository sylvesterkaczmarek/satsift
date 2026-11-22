'use strict';

// Regression for decimal/Alpha-5 catalogue identity across TLE and OMM.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ROOT = path.resolve(__dirname, '..');
const { loadBrowserApp } = require('../tools/load_browser_app');

const defaults = { win: '6', alpha: '0.1', dath: '0.05', stale: '36500', gapWarn: '3',
  orbitProfile: 'auto', detectorMode: 'multivariate', sensitivity: 'balanced' };
const document = { getElementById(id) { return { value: defaults[id] || '', textContent: '', style: {} }; } };
const window = { document, satellite: null };
const context = { document, window, Date, console, URL, URLSearchParams, Math, Number,
  String, Array, Object, Set, Map, BigInt, JSON, RegExp, Error, TypeError,
  Promise, Blob, AbortController };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'satellite-6.0.2.min.js'), 'utf8'), context);
window.satellite = context.satellite;
const api = loadBrowserApp(context, { root: ROOT, start: false });

const options = { requestedWindow: 6, alpha: 0.1, minAbsDeltaA: 0.05,
  maximumStaleDays: 36500, maximumGapFactor: 3, orbitProfile: 'auto', detectorMode: 'multivariate' };
const original = api.exampleTles('leo');
const originalTle = api.parseInput(original);
assert.equal(originalTle.rejectedCount, 0);
const count = originalTle.records.length;
assert(count > 10);
const canonical = number => String(Number(number));

function rewriteTleIdentifiers(source, field) {
  assert.equal(field.length, 5);
  return source.split(/\r?\n/).map(line => /^[12] /.test(line)
    ? api.addTleChecksum(line.slice(0, 2) + field + line.slice(7, 68))
    : line).join('\n');
}
function parsed(source) { return api.parseInput(source); }
function assertValid(source, expectedId) {
  const result = parsed(source);
  assert.equal(result.rejectedCount, 0, String(result.rejectionReasons));
  assert.equal(result.records.length, count);
  assert(result.records.every(record => record.satId === expectedId));
  return result;
}
let groups = 0;

for (const [field, expected] of [['00001', '1'], ['A0000', '100000'], ['E8493', '148493'],
                                 ['J2931', '182931'], ['P4018', '234018'],
                                 ['W1928', '301928'], ['Z9999', '339999']]) {
  const raw = rewriteTleIdentifiers(original, field);
  const initial = assertValid(raw, expected);
  const exported = api.serialiseRecordsAsOmm(initial.records);
  const rows = JSON.parse(exported);
  assert(rows.every(row => canonical(row.NORAD_CAT_ID) === expected));
  assert(rows.every(row => row.SMD_TLE && row.SMD_TLE.line1.slice(2, 7) === field));
  const reopened = assertValid(exported, expected);
  assert.deepEqual(Array.from(reopened.records, record => record.epochUs),
    Array.from(initial.records, record => record.epochUs));
  const first = api.analyzeRaw(raw, 'synthetic identifier fixture', options);
  const second = api.analyzeRaw(exported, 'synthetic identifier fixture', options);
  assert.equal(first.error, false, JSON.stringify(first));
  assert.equal(second.error, false, JSON.stringify(second));
  assert.equal(first.runId, second.runId, 'Run identity changed after Alpha-5 TLE export');
  assert.equal(first.events.length, second.events.length);
  const packageResult = api.buildMachineReadableResult(first, true);
  const opened = api.decodeSavedPackage(JSON.stringify(packageResult), 'replace');
  assert(opened, 'A supported TLE was exported into an unreopenable saved package');
  const repeated = assertValid(opened.input, expected);
  assert.equal(repeated.records.length, count);
  groups++;
}

const regular = JSON.parse(api.serialiseRecordsAsOmm(originalTle.records));
for (const row of regular) {
  row.NORAD_CAT_ID = '000' + String(row.NORAD_CAT_ID);
  delete row.SMD_TLE;
  delete row.SMD_SOURCE_FORMAT;
}
const nativeOmm = JSON.stringify(regular);
const native = assertValid(nativeOmm, '90001');
const merged = api.mergeOrbitalHistories(original, nativeOmm);
assert(merged.records.length >= count);
assert(merged.records.every(record => record.satId === '90001'));
assert.equal(native.records[0].satId, '90001');
groups++;

for (const invalid of ['I0000', 'O0000', 'a0000', 'A000A', '00000', '!!!!!']) {
  const source = rewriteTleIdentifiers(original, invalid);
  const result = parsed(source);
  assert.equal(result.records.length, 0, invalid + ' was accepted');
  assert.equal(result.rejectedCount, count);
  groups++;
}

// Older broken exports represented an Alpha-5 TLE catalog field as OMM.
const legacyRows = JSON.parse(api.serialiseRecordsAsOmm(assertValid(rewriteTleIdentifiers(original, 'A0000'), '100000').records));
for (const row of legacyRows) row.NORAD_CAT_ID = 'A0000';
assertValid(JSON.stringify(legacyRows), '100000');
const upgraded = JSON.parse(api.serialiseRecordsAsOmm(assertValid(JSON.stringify(legacyRows), '100000').records));
assert(upgraded.every(row => row.NORAD_CAT_ID === '100000'));
legacyRows[0].NORAD_CAT_ID = 'A0001';
const forged = parsed(JSON.stringify(legacyRows));
assert.equal(forged.rejectedCount, 1, 'Retained TLE must disagree with forged visible catalog ID');
groups++;

const invalidOmm = JSON.stringify(regular.map(row => ({ ...row, NORAD_CAT_ID: 'A0000' })));
assert.equal(parsed(invalidOmm).records.length, 0, 'OMM must supply decimal NORAD_CAT_ID');
groups++;
console.log('Catalogue identity and Alpha-5 TLE round-trip regressions passed (' + groups + ' groups).');
