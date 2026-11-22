'use strict';

const { loadBrowserApp } = require('../tools/load_browser_app');

const assert = require('assert/strict');
const fs = require('fs');
const vm = require('vm');

const context = { console, Date, Math, Number, String, Array, Object, Set, Map, JSON, window: {} };
vm.createContext(context);
vm.runInContext(fs.readFileSync('satellite-6.0.2.min.js', 'utf8'), context);
context.window.satellite = context.satellite;
const api = loadBrowserApp(context, { start: false });

const validOmm = {
  NORAD_CAT_ID: 25544, EPOCH: '2026-07-06T02:08:05.621280',
  MEAN_MOTION: 15.5, ECCENTRICITY: 0.0005, INCLINATION: 51.64,
  RA_OF_ASC_NODE: 85, ARG_OF_PERICENTER: 96, MEAN_ANOMALY: 50
};
const requiredNumbers = ['MEAN_MOTION', 'ECCENTRICITY', 'INCLINATION', 'RA_OF_ASC_NODE', 'ARG_OF_PERICENTER', 'MEAN_ANOMALY'];
let checks = 0;
function rejectOmm(changes, field) {
  const result = api.parseOmmRecord({ ...validOmm, ...changes });
  assert.equal(result.record, null, `Accepted invalid ${field}: ${JSON.stringify(changes)}`);
  assert.ok(result.errors.some(error => error.includes(field)), `Missing actionable ${field} error`);
  checks++;
}
function acceptOmm(changes = {}) {
  const result = api.parseOmmRecord({ ...validOmm, ...changes });
  assert.ok(result.record, result.errors.join('; '));
  checks++;
  return result.record;
}

const ordinary = acceptOmm();
assert.equal(ordinary.bstar, 0);
assert.equal(ordinary.elementSetNoKnown, false);
for (const field of requiredNumbers) {
  for (const bad of [undefined, null, '', '   ', false, true, [], [0], {}, '0x10', 'Infinity']) {
    rejectOmm({ [field]: bad }, field);
  }
  acceptOmm({ [field]: String(validOmm[field]) });
}
acceptOmm({ ECCENTRICITY: 0, INCLINATION: 0, RA_OF_ASC_NODE: 0, ARG_OF_PERICENTER: 0, MEAN_ANOMALY: 0 });
acceptOmm({ BSTAR: '-1.2e-5', MEAN_MOTION_DOT: '-0.001' });
acceptOmm({ NORAD_CAT_ID: 799500001 });
for (const bad of [0, false, true, [], [25544], 'NORAD', '1000000000']) rejectOmm({ NORAD_CAT_ID: bad }, 'NORAD_CAT_ID');
for (const field of ['BSTAR', 'MEAN_MOTION_DOT', 'MEAN_MOTION_DDOT', 'ELEMENT_SET_NO', 'REV_AT_EPOCH', 'EPHEMERIS_TYPE']) {
  rejectOmm({ [field]: 'invalid' }, field);
  rejectOmm({ [field]: false }, field);
  acceptOmm({ [field]: null });
}
for (const field of ['ELEMENT_SET_NO', 'REV_AT_EPOCH']) {
  rejectOmm({ [field]: -1 }, field);
  rejectOmm({ [field]: 0.5 }, field);
}
for (const [field, expected, unsupported] of [
  ['CENTER_NAME', 'EARTH', 'MARS'], ['REF_FRAME', 'TEME', 'EME2000'],
  ['TIME_SYSTEM', 'UTC', 'TAI'], ['MEAN_ELEMENT_THEORY', 'SGP4', 'DSST']
]) {
  acceptOmm({ [field]: expected });
  acceptOmm({ [field]: expected.toLowerCase() });
  rejectOmm({ [field]: unsupported }, field);
}
for (const type of [0, 2, 3]) acceptOmm({ EPHEMERIS_TYPE: type });
for (const type of [1, 4, 5, 6]) rejectOmm({ EPHEMERIS_TYPE: type }, 'EPHEMERIS_TYPE');

for (const epoch of [
  '2026-02-30T00:00:00Z', '2026-02-29T00:00:00Z', '2024-04-31T00:00:00Z',
  '2024-13-01T00:00:00Z', '2024-00-01T00:00:00Z', '2024-01-00T00:00:00Z',
  '2024-01-01T24:00:00Z', '2024-01-01T00:60:00Z', '2024-01-01T00:00:60Z',
  '2024-01-01T00:00:00+24:00', '2024-01-01T00:00:00+02:60',
  '2024-01-01', 'July 6, 2026', 0, false, []
]) rejectOmm({ EPOCH: epoch }, 'EPOCH');
acceptOmm({ EPOCH: '2024-02-29T23:59:59.999999Z' });
rejectOmm({ CREATION_DATE: '2026-02-30T00:00:00Z' }, 'CREATION_DATE');
const offset = acceptOmm({ EPOCH: '2026-07-06T04:08:05.621280+02:00' });
assert.equal(offset.epochUs, ordinary.epochUs);
assert.equal(offset.epochRaw, '2026-07-06T04:08:05.621280+02:00');
assert.equal(api.parseOmmEpochUtc('2026-07-06T02:08:05.621281Z').epochUs - ordinary.epochUs, 1);
const canonicalSatrec = api.satrecForRecord(ordinary);
for (const record of [offset, acceptOmm({ EPOCH: '2026-07-06t02:08:05.621280z' })]) {
  const satrec = api.satrecForRecord(record);
  assert.equal(satrec.jdsatepoch, canonicalSatrec.jdsatepoch);
  const position = context.satellite.sgp4(satrec, 60).position;
  const expected = context.satellite.sgp4(canonicalSatrec, 60).position;
  for (const axis of ['x', 'y', 'z']) assert.equal(position[axis], expected[axis]);
}

const line1 = api.addTleChecksum('1 25544U 98067A   26187.08900000  .00000100  00000-0  10000-4 0  999');
const line2 = api.addTleChecksum('2 25544  51.6400  85.0000 0005000  96.0000  50.0000 15.5000000012345');
function replaceField(line, start, end, value) {
  assert.equal(value.length, end - start);
  return api.addTleChecksum(line.slice(0, start) + value + line.slice(end, 68));
}
assert.ok(api.parseTlePair('ISS', line1, line2).record);
for (const [start, end, text] of [[33, 43, ' .invalid!'], [44, 52, ' 1234x-5'], [53, 61, ' ABCDE-5'], [64, 68, '    ']]) {
  const result = api.parseTlePair('ISS', replaceField(line1, start, end, text), line2);
  assert.equal(result.record, null, `Accepted malformed TLE line 1 field ${start}`);
  assert.ok(result.errors.length);
  checks++;
}
for (const [start, end] of [[8, 16], [17, 25], [34, 42], [43, 51], [52, 63]]) {
  const result = api.parseTlePair('ISS', line1, replaceField(line2, start, end, ' '.repeat(end - start)));
  assert.equal(result.record, null, `Accepted missing TLE line 2 field ${start}`);
  checks++;
}
const blankLine = replaceField(replaceField(line1, 44, 52, '        '), 53, 61, '        ');
const blank = api.parseTlePair('ISS', blankLine, line2).record;
assert.ok(blank);
assert.equal(blank.bstar, 0);
assert.equal(blank.meanMotionDdot, 0);
const blankSatrec = api.satrecForRecord(blank);
assert.ok(Number.isFinite(context.satellite.sgp4(blankSatrec, 60).position.x));
assert.equal(blank.line1, blankLine, 'Propagation must retain the original source and checksum');
const dayZero = api.parseTleEpoch(replaceField(line1, 18, 32, '26000.00000000'));
assert.equal(dayZero.t.toISOString(), '2025-12-31T00:00:00.000Z');
assert.equal(api.parseTleEpoch(replaceField(line1, 18, 32, '26366.00000000')), null);
assert.equal(api.parseTleEpoch(replaceField(line1, 18, 32, '24366.00000000')).t.toISOString(), '2024-12-31T00:00:00.000Z');
checks += 7;

for (const item of [null, false, 'text', []]) {
  const parsed = api.parseInput(JSON.stringify([item]));
  assert.equal(parsed.records.length, 0);
  assert.equal(parsed.rejectedCount, 1);
  assert.match(parsed.rejectionReasons[0], /JSON object/);
  checks++;
}
const mixed = api.parseInput(JSON.stringify([validOmm, { ...validOmm, INCLINATION: null }]));
assert.equal(mixed.records.length, 1);
assert.equal(mixed.rejectedCount, 1);
assert.ok(api.parseInput(null).fatalMessage);
checks += 2;

console.log(`Input validation and SGP4 boundary regressions passed (${checks} cases).`);
