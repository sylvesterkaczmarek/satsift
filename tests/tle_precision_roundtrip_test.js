'use strict';

const { loadBrowserApp } = require('../tools/load_browser_app');

// Verify integer UTC epochs, propagation, identity and real package handlers offline.
const assert = require('assert/strict');
const fs = require('fs');
const vm = require('vm');

const elements = new Map();
const storage = new Map();
let capturedBlob = null;
let downloadName = '';
function element(id, tagName = 'DIV') {
  if (elements.has(id)) return elements.get(id);
  const classes = new Set();
  const defaults = { win: '6', alpha: '0.10', dath: '0.25', stale: '36500', gapWarn: '4', orbitProfile: 'auto', detectorMode: 'multivariate', sensitivity: 'balanced', demoSelect: 'leo', importMode: 'replace' };
  const item = {
    id, tagName, value: defaults[id] || '', textContent: '', innerHTML: '', className: '',
    hidden: false, disabled: false, open: false, max: '', files: [], style: {}, handlers: {},
    parentNode: null, href: '', download: '', src: '', async: false,
    classList: {
      add(...names) { names.forEach(name => classes.add(name)); },
      remove(...names) { names.forEach(name => classes.delete(name)); },
      contains(name) { return classes.has(name); },
      toggle(name) { if (classes.has(name)) classes.delete(name); else classes.add(name); }
    },
    addEventListener(type, handler) { this.handlers[type] = handler; },
    removeEventListener() {}, focus() {}, select() {}, scrollIntoView() {},
    setAttribute(name, value) { this[name] = value; },
    getAttribute(name) { return this[name] || null; },
    querySelectorAll() { return []; },
    appendChild(child) { child.parentNode = this; },
    removeChild(child) { if (child) child.parentNode = null; },
    getContext() { return null; }, toBlob(callback) { callback(null); },
    click() {
      if (tagName === 'A') downloadName = this.download;
      if (this.handlers.click) this.handlers.click.call(this, { preventDefault() {} });
    }
  };
  elements.set(id, item);
  return item;
}
let created = 0;
const document = {
  getElementById: element,
  createElement(tag) { return element('created-' + (++created), String(tag).toUpperCase()); },
  head: { appendChild(child) { child.parentNode = this; }, removeChild(child) { child.parentNode = null; } },
  body: { appendChild() {}, removeChild() {} },
  execCommand() { return false; }
};
class DownloadURL extends URL {}
DownloadURL.createObjectURL = blob => { capturedBlob = blob; return 'blob:tle-precision-test'; };
DownloadURL.revokeObjectURL = () => {};
const windowObject = {
  document, location: { href: 'https://example.test/satellite-maneuver-detector', search: '' },
  history: { replaceState() {} }, setTimeout() { return 1; }, clearTimeout() {},
  scrollTo() {}, addEventListener() {}, removeEventListener() {}, innerWidth: 1440,
  devicePixelRatio: 1, Plotly: null, satellite: null
};
const context = {
  window: windowObject, document, navigator: { clipboard: null }, console, URL: DownloadURL,
  URLSearchParams, Date, Math, Number, String, Array, Object, Set, Map, BigInt, JSON,
  RegExp, Error, TypeError, Promise, Blob, AbortController,
  fetch: async () => { throw new Error('Network disabled in TLE precision test'); },
  localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) }
};
context.globalThis = context;
context.self = windowObject;
vm.createContext(context);
vm.runInContext(fs.readFileSync('satellite-6.0.2.min.js', 'utf8'), context);
windowObject.satellite = context.satellite || windowObject.satellite;
loadBrowserApp(context, { hooks: `
window.__precisionTest = { parseInput, parseOmmRecord, recordToOmm, serialiseRecordsAsOmm,
  resolveCatalogueRevisions, mergeOrbitalHistories, applyIncomingData, assignInputValue,
  importLocalFile, downloadBundle, addTleChecksum, satrecForRecord, parseTleEpoch,
  formatEpochUs: typeof formatEpochUs === 'function' ? formatEpochUs : null,
  propagateRecordAtEpoch: typeof propagateRecordAtEpoch === 'function' ? propagateRecordAtEpoch : null,
  hasSgp4Support: typeof hasSgp4Support === 'function' ? hasSgp4Support : null,
  computeSgp4Residual, analyzeRaw, makeRunId, getAnalysisOptions, decodeSavedPackage,
  buildMachineReadableResult, analysis: () => lastAnalysis };
` });
const api = windowObject.__precisionTest;
assert.ok(api, 'Application test hooks were not exposed');


const options = {
  requestedWindow: 6, alpha: 0.10, minAbsDeltaA: 0.25,
  maximumStaleDays: 36500, maximumGapFactor: 4,
  orbitProfile: 'auto', detectorMode: 'multivariate'
};
const controls = { win: 'requestedWindow', alpha: 'alpha', dath: 'minAbsDeltaA', stale: 'maximumStaleDays', gapWarn: 'maximumGapFactor', orbitProfile: 'orbitProfile', detectorMode: 'detectorMode' };
const satellite = windowObject.satellite;
const copy = value => JSON.parse(JSON.stringify(value));
function parse(raw) {
  const parsed = api.parseInput(typeof raw === 'string' ? raw : JSON.stringify(raw));
  assert.ok(!parsed.fatalMessage, parsed.fatalMessage);
  assert.equal(parsed.rejectedCount, 0, Array.from(parsed.rejectionReasons).join('; '));
  assert.ok(parsed.records.length, 'Fixture must contain valid orbital records');
  return Array.from(parsed.records);
}
function rows(records) { return JSON.parse(api.serialiseRecordsAsOmm(records)); }
function roundTrip(records) { return parse(api.serialiseRecordsAsOmm(records)); }
function tle({ epoch = '26187.12345678', set = 1, meanMotion = 15.5, anomaly = 50, blankExponents = false } = {}) {
  let one = '1 25544U 98067A   26187.00000000  .00000100  00000-0  10000-4 0  999';
  let two = '2 25544  51.6400  85.0000 0005000  96.0000  50.0000 15.5000000012345';
  one = one.slice(0, 18) + epoch + one.slice(32, 64) + String(set).padStart(4);
  if (blankExponents) for (const start of [44, 53]) one = one.slice(0, start) + '        ' + one.slice(start + 8);
  two = two.slice(0, 43) + anomaly.toFixed(4).padStart(8) + two.slice(51, 52) + meanMotion.toFixed(8).padStart(11) + two.slice(63, 68);
  return 'PRECISION FIXTURE\n' + api.addTleChecksum(one) + '\n' + api.addTleChecksum(two);
}
function historyTle(index) {
  return tle({ epoch: '26' + String(187 + index).padStart(3, '0') + '.' + String(12345678 + index).padStart(8, '0'), set: index + 1, anomaly: (50 + index * 10) % 360 });
}
const historyRaw = Array.from({ length: 16 }, (_, index) => historyTle(index)).join('\n');
function nativeOmm(record, changes = {}) {
  const row = { ...rows([record])[0], ...changes };
  delete row.SMD_SOURCE_FORMAT;
  delete row.SMD_TLE;
  return row;
}
function expectedEpochUs(iso) {
  return Date.parse(iso.slice(0, 23) + 'Z') * 1000 + Number(iso.slice(23, 26));
}
function assertClose(actual, expected, tolerance, label) {
  assert.ok(Number.isFinite(actual) && Number.isFinite(expected), label + ' must be finite');
  assert.ok(Math.abs(actual - expected) <= tolerance, label + ': ' + actual + ' differs from ' + expected + ' by ' + Math.abs(actual - expected));
}
function assertState(actual, expected, label, exact = false) {
  assert.ok(actual && actual.position && actual.velocity, label + ' needs a complete propagated state');
  for (const kind of ['position', 'velocity']) for (const axis of ['x', 'y', 'z']) {
    if (exact) assert.equal(actual[kind][axis], expected[kind][axis], label + ' ' + kind + '.' + axis);
    else assertClose(actual[kind][axis], expected[kind][axis], kind === 'position' ? 1e-9 : 1e-12, label + ' ' + kind + '.' + axis);
  }
}
function referenceSatrec(record) {
  if (record.line1 && record.line2) {
    let one = record.line1;
    for (const start of [44, 53]) if (!one.slice(start, start + 8).trim()) one = one.slice(0, start) + ' 00000-0' + one.slice(start + 8);
    return satellite.twoline2satrec(one, record.line2);
  }
  const row = nativeOmm(record);
  row.EPOCH = record.t.toISOString();
  return satellite.json2satrec(row);
}
function referenceState(record, targetUs) {
  // The pinned native OMM initialiser reads Date precision. TLE uses its exact
  // decimal-day epoch. Evaluate both models at the same integer UTC instant.
  const modelEpochUs = record.line1 && record.line2 ? record.epochUs : record.t.getTime() * 1000;
  return satellite.sgp4(referenceSatrec(record), (targetUs - modelEpochUs) / 60000000);
}
const xyz = value => [value.x, value.y, value.z];
const dot = (a, b) => a.reduce((sum, value, index) => sum + value * b[index], 0);
const norm = a => Math.sqrt(dot(a, a));
const unit = a => a.map(value => value / norm(a));
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const subtract = (a, b) => a.map((value, index) => value - b[index]);
function referenceResidual(before, after) {
  const first = referenceState(before, after.epochUs);
  const second = referenceState(after, after.epochUs);
  const radial = unit(xyz(first.position));
  const normal = unit(cross(xyz(first.position), xyz(first.velocity)));
  const along = unit(cross(normal, radial));
  const deltaPosition = subtract(xyz(second.position), xyz(first.position));
  const deltaVelocity = subtract(xyz(second.velocity), xyz(first.velocity));
  return {
    radialKm: dot(deltaPosition, radial), alongKm: dot(deltaPosition, along),
    crossKm: dot(deltaPosition, normal), positionKm: norm(deltaPosition), velocityMps: norm(deltaVelocity) * 1000
  };
}
function assertResidual(actual, expected, label, exact = false) {
  assert.ok(actual, label + ' must return an RTN residual');
  for (const field of ['radialKm', 'alongKm', 'crossKm', 'positionKm', 'velocityMps']) {
    if (exact) assert.equal(actual[field], expected[field], label + ' ' + field);
    else assertClose(actual[field], expected[field], 1e-9, label + ' ' + field);
  }
}
function analyse(raw, overrides = {}) {
  const result = api.analyzeRaw(typeof raw === 'string' ? raw : JSON.stringify(raw), 'precision regression', { ...options, ...overrides });
  assert.ok(result && !result.error, result && result.message);
  return result;
}
function scientificResult(analysis) {
  const report = api.buildMachineReadableResult(analysis, false);
  const fields = [
    'method_version', 'satellite_js_version', 'run_id', 'valid_snapshots', 'span_days', 'median_gap_days',
    'calibration_window', 'alpha', 'minimum_absolute_delta_a_km', 'maximum_gap_factor', 'orbit_profile',
    'detector_mode', 'sgp4_pair_count', 'excluded_gap_count', 'evaluated_points', 'observed_primary_coverage',
    'interpretable', 'quality_status', 'exact_duplicate_count', 'unresolved_duplicate_count',
    'unresolved_near_simultaneous_count', 'classification', 'events', 'flags', 'rows'
  ];
  return copy({
    ...Object.fromEntries(fields.map(field => [field, report[field]])),
    epochs: Array.from(analysis.records, record => record.epochUs),
    features: Array.from(analysis.rows, row => row.featureValues)
  });
}
async function importText(raw, mode = 'replace', name = 'precision-history.json') {
  const text = typeof raw === 'string' ? raw : JSON.stringify(raw);
  await api.importLocalFile({ name, size: Buffer.byteLength(text), text: async () => text }, mode);
}
async function exportPackage() {
  capturedBlob = null;
  api.downloadBundle();
  assert.ok(capturedBlob, 'Reproducibility export must create a download');
  assert.match(downloadName, /^satellite-maneuver-reproducibility-.+\.json$/);
  return JSON.parse(await capturedBlob.text());
}
function setControls(values) {
  for (const [id, key] of Object.entries(controls)) element(id).value = String(values[key]);
}
function uiState() {
  return {
    input: element('tles').value,
    controls: Object.fromEntries(Object.keys(controls).map(id => [id, element(id).value])),
    analysis: api.analysis()
  };
}
let groups = 0;
let tlePackage;
(async () => {
  // One TLE fractional-day unit is exactly 864 microseconds. The display Date
  // must floor, including dates before 1970, while epochUs preserves all bits.
  for (const [epoch, iso] of [
    ['26187.12345678', '2026-07-06T02:57:46.665792Z'],
    ['26187.00000000', '2026-07-06T00:00:00.000000Z'],
    ['26187.00000001', '2026-07-06T00:00:00.000864Z'],
    ['26187.99999999', '2026-07-06T23:59:59.999136Z'],
    ['26000.00000001', '2025-12-31T00:00:00.000864Z'],
    ['00060.00000001', '2000-02-29T00:00:00.000864Z'],
    ['56366.99999999', '2056-12-31T23:59:59.999136Z'],
    ['57001.00000001', '1957-01-01T00:00:00.000864Z'],
    ['57000.00000001', '1956-12-31T00:00:00.000864Z']
  ]) {
    const record = parse(tle({ epoch }))[0];
    const expected = expectedEpochUs(iso);
    assert.equal(record.epochUs, expected, epoch + ' lost sub-millisecond precision');
    assert.equal(record.t.getTime(), Math.floor(expected / 1000), epoch + ' display Date must floor');
    assert.equal(record.epochRaw, iso);
    assert.equal(api.parseTleEpoch(record.line1).epochUs, expected);
    assert.equal(api.formatEpochUs(expected), iso);
    let current = [record];
    for (let cycle = 0; cycle < 3; cycle++) {
      assert.equal(rows(current)[0].EPOCH, iso);
      current = roundTrip(current);
      assert.equal(current[0].epochUs, expected);
      assert.equal(current[0].t.getTime(), Math.floor(expected / 1000));
    }
  }
  for (const epoch of ['26366.00000000', '56367.00000000', '57001.1234567x']) {
    assert.equal(api.parseTleEpoch(tle({ epoch }).split('\n')[1]), null, 'Invalid TLE epoch was accepted');
  }
  groups++;

  const original = parse(historyRaw);
  for (const record of original.concat(parse(tle({ blankExponents: true })))) {
    let current = [record];
    for (let cycle = 0; cycle < 3; cycle++) {
      const row = rows(current)[0];
      assert.equal(row.SMD_SOURCE_FORMAT, 'TLE');
      assert.deepEqual(row.SMD_TLE, { schema_version: 1, line1: record.line1, line2: record.line2 });
      assert.match(row.EPOCH, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$/);
      current = roundTrip(current);
      assert.equal(current[0].line1, record.line1);
      assert.equal(current[0].line2, record.line2);
    }
  }
  const enriched = rows([original[0]])[0];
  enriched.CREATION_DATE = '2026-07-06T05:06:07.123456Z';
  enriched.GP_ID = '900719925474099312345';
  enriched.NORAD_CAT_ID = '00025544';
  const enrichment = parse([enriched])[0];
  assert.equal(enrichment.line1, original[0].line1, 'Numeric catalogue IDs may contain leading zeroes');
  assert.equal(rows([enrichment])[0].CREATION_DATE, enriched.CREATION_DATE);
  assert.equal(rows([enrichment])[0].GP_ID, enriched.GP_ID);
  groups++;

  // Compare both position and velocity at independent model-relative times.
  const stateFixtures = original.concat(
    parse(tle({ epoch: '57001.00000001' })),
    parse(tle({ epoch: '56366.99999999' })),
    parse(tle({ meanMotion: 1.0027 })),
    parse(tle({ blankExponents: true })),
    parse([nativeOmm(original[0], { EPOCH: '2026-07-06T02:57:46.665793Z' })])
  );
  for (const record of stateFixtures) {
    const reopened = roundTrip([record])[0];
    for (const offsetUs of [0, 864, 60000000, 86400000000]) {
      const targetUs = record.epochUs + offsetUs;
      const before = api.propagateRecordAtEpoch(record, targetUs);
      assertState(before, referenceState(record, targetUs), 'Independent SGP4 state');
      assertState(api.propagateRecordAtEpoch(reopened, targetUs), before, 'Reopened SGP4 state', true);
    }
  }
  groups++;

  const subMsBefore = parse(tle({ epoch: '26187.00000000' }))[0];
  const subMsAfter = parse(tle({ epoch: '26187.00000001', anomaly: 50.01, meanMotion: 15.50000001 }))[0];
  assert.equal(subMsBefore.t.getTime(), subMsAfter.t.getTime(), 'Fixture must share one display millisecond');
  assert.equal(subMsAfter.epochUs - subMsBefore.epochUs, 864);
  const nativeBefore = parse([nativeOmm(original[0])])[0];
  const nativeAfter = parse([nativeOmm(original[1], { EPOCH: '2026-07-07T02:57:46.666657Z' })])[0];
  const pairs = original.slice(1).map((record, index) => [original[index], record]).concat([
    [subMsBefore, subMsAfter], [nativeBefore, nativeAfter], [nativeBefore, original[1]], [original[0], nativeAfter]
  ]);
  for (const [before, after] of pairs) {
    const residual = api.computeSgp4Residual(before, after);
    assertResidual(residual, referenceResidual(before, after), 'Independent RTN residual');
    const reopened = roundTrip([before, after]);
    assertResidual(api.computeSgp4Residual(reopened[0], reopened[1]), residual, 'Reopened RTN residual', true);
  }
  groups++;

  const runId = (records, changes = {}, profile = 'LEO', mode = 'SGP4 multivariate') =>
    api.makeRunId(records, { ...options, ...changes }, profile, mode);
  const baseId = runId([original[0]]);
  assert.match(baseId, /^smd-v2-[0-9a-f]{16}$/);
  assert.equal(runId(roundTrip([original[0]])), baseId);
  assert.notEqual(runId([subMsBefore]), runId([subMsAfter]), 'Distinct sub-millisecond propagation epochs shared an ID');
  const sameOrbitLater = parse(tle({ epoch: '26187.00000001' }))[0];
  assert.notEqual(runId([subMsBefore]), runId([sameOrbitLater]), 'Epoch alone must distinguish model inputs');
  const native = nativeOmm(original[0]);
  const nativeId = runId(parse([native]));
  assert.notEqual(nativeId, baseId, 'TLE and native OMM initialisation paths shared an ID');
  assert.equal(runId(parse([{ ...native, EPOCH: '2026-07-06T03:57:46.665792+01:00' }])), nativeId, 'Equivalent UTC epochs must share canonical numeric time');
  for (const [field, value] of [
    ['EPOCH', '2026-07-06T02:57:46.665793Z'], ['MEAN_MOTION', 15.500000000001],
    ['ECCENTRICITY', 0.000500000001], ['INCLINATION', 51.6400000001],
    ['RA_OF_ASC_NODE', 85.0000000001], ['ARG_OF_PERICENTER', 96.0000000001],
    ['MEAN_ANOMALY', 50.0000000001], ['BSTAR', 0.000010000001],
    ['MEAN_MOTION_DOT', 0.000002], ['MEAN_MOTION_DDOT', 0.00000001]
  ]) assert.notEqual(runId(parse([{ ...native, [field]: value }])), nativeId, field + ' did not change the run ID');
  for (const changes of [
    { requestedWindow: 7 }, { alpha: 0.11 }, { minAbsDeltaA: 0.3 }, { maximumStaleDays: 36000 },
    { maximumGapFactor: 5 }, { orbitProfile: 'LEO' }, { detectorMode: 'elements' }
  ]) assert.notEqual(runId([original[0]], changes), baseId, JSON.stringify(changes) + ' did not change the run ID');
  assert.notEqual(runId([original[0]], {}, 'MEO'), baseId, 'Effective profile did not change the run ID');
  assert.notEqual(runId([original[0]], {}, 'LEO', 'Elements only'), baseId, 'Effective detector mode did not change the run ID');
  assert.notEqual(runId([original[0]], {}, 'LEO', 'Elements only'), runId([original[0]], { detectorMode: 'elements' }, 'LEO', 'Elements only'), 'Requested detector mode was omitted from fallback identity');
  groups++;

  let analysis = analyse(historyRaw);
  assert.equal(analysis.sgp4PairCount, 15);
  assert.ok(analysis.rows.slice(1).every(row => Number.isFinite(row.radialKm) && Number.isFinite(row.alongKm) && Number.isFinite(row.crossKm) && Number.isFinite(row.stateResidualKm)));
  const expectedAnalysis = scientificResult(analysis);
  for (let cycle = 0; cycle < 3; cycle++) {
    analysis = analyse(api.serialiseRecordsAsOmm(analysis.records));
    assert.deepEqual(scientificResult(analysis), expectedAnalysis, 'Normalisation changed numerical results or run identity');
  }
  groups++;

  setControls(options);
  await importText(historyRaw, 'replace', 'precision-original.tle');
  const expectedPackageResult = scientificResult(api.analysis());
  for (let cycle = 0; cycle < 3; cycle++) {
    const saved = await exportPackage();
    assert.equal(saved.package_schema_version, 1);
    assert.equal(saved.run_identity_version, 2);
    assert.equal(saved.run_id, expectedPackageResult.run_id);
    assert.ok(saved.normalized_input_omm.every(row => row.SMD_TLE && row.SMD_TLE.schema_version === 1));
    const decoded = api.decodeSavedPackage(JSON.stringify(saved), 'replace');
    assert.equal(decoded.legacySchema, false);
    assert.equal(decoded.legacy, false);
    api.assignInputValue('', 'before reopening precision package');
    setControls({ ...options, requestedWindow: 10, alpha: 0.2, orbitProfile: 'GEO', detectorMode: 'elements' });
    await importText(saved);
    assert.deepEqual(copy(api.getAnalysisOptions()), options, 'Reopening did not restore saved settings');
    assert.deepEqual(scientificResult(api.analysis()), expectedPackageResult, 'Real export/reopen handlers changed numerical results');
    tlePackage = saved;
  }
  groups++;

  const nativeHistory = original.map(record => nativeOmm(record, { EPOCH: api.formatEpochUs(record.epochUs + 1) }));
  await importText(nativeHistory);
  const expectedNative = scientificResult(api.analysis());
  assert.notEqual(expectedNative.run_id, expectedPackageResult.run_id);
  for (let cycle = 0; cycle < 2; cycle++) {
    const saved = await exportPackage();
    assert.ok(saved.normalized_input_omm.every(row => !Object.hasOwn(row, 'SMD_TLE')), 'Native OMM must not acquire fabricated TLE source');
    await importText(saved);
    assert.deepEqual(scientificResult(api.analysis()), expectedNative, 'Native OMM precision changed after package reopening');
  }
  groups++;

  // Exercise both arrival orders through the real append and download handlers.
  for (const tleFirst of [true, false]) {
    const first = tleFirst ? original.slice(0, 8) : parse(original.slice(0, 8).map(record => nativeOmm(record)));
    const second = tleFirst ? parse(original.slice(8).map(record => nativeOmm(record))) : original.slice(8);
    const expected = scientificResult(analyse(rows(first.concat(second))));
    await importText(tleFirst ? Array.from({ length: 8 }, (_, i) => historyTle(i)).join('\n') : rows(first));
    await importText(tleFirst ? rows(second) : Array.from({ length: 8 }, (_, i) => historyTle(i + 8)).join('\n'), 'append');
    assert.deepEqual(scientificResult(api.analysis()), expected, 'Mixed-source append changed numerical results');
    for (let cycle = 0; cycle < 2; cycle++) {
      const saved = await exportPackage();
      assert.equal(saved.normalized_input_omm.filter(row => row.SMD_TLE).length, 8);
      await importText(saved);
      assert.deepEqual(scientificResult(api.analysis()), expected, 'Mixed-source package changed after reopening');
    }
  }
  groups++;

  // An exact duplicate can restore available source lines without changing
  // the epoch. Truncated historical epochs remain distinct observations.
  const exactLegacyRow = rows([original[0]])[0];
  delete exactLegacyRow.SMD_TLE;
  const exactLegacyRecord = parse([exactLegacyRow])[0];
  for (const order of [[exactLegacyRecord, original[0]], [original[0], exactLegacyRecord]]) {
    const resolved = api.resolveCatalogueRevisions(order);
    assert.equal(resolved.records.length, 1);
    assert.equal(resolved.records[0].line1, original[0].line1, 'Duplicate order discarded available TLE source');
    assert.equal(resolved.records[0].line2, original[0].line2);
    assert.equal(runId(Array.from(resolved.records)), runId([original[0]]));
  }
  api.assignInputValue(JSON.stringify([exactLegacyRow]), 'legacy source enrichment');
  const restored = api.applyIncomingData(historyTle(0), 'append', 'available original TLE');
  assert.equal(restored.unchanged, false, 'Source-only enrichment must be committed');
  assert.equal(parse(element('tles').value)[0].line1, original[0].line1);
  const retainedInput = element('tles').value;
  const repeated = api.applyIncomingData(JSON.stringify([exactLegacyRow]), 'append', 'legacy duplicate');
  assert.equal(repeated.unchanged, true, 'A legacy duplicate must not remove retained source');
  assert.equal(element('tles').value, retainedInput);
  const truncatedLegacyRow = { ...exactLegacyRow, EPOCH: original[0].t.toISOString() };
  const truncatedLegacyRecord = parse([truncatedLegacyRow])[0];
  assert.equal(original[0].epochUs - truncatedLegacyRecord.epochUs, 792);
  for (const order of [[truncatedLegacyRecord, original[0]], [original[0], truncatedLegacyRecord]]) {
    const resolved = api.resolveCatalogueRevisions(order);
    assert.equal(resolved.records.length, 2, 'Lost epoch precision must not be guessed from a nearby TLE');
    const retainedLegacy = Array.from(resolved.records).find(record => record.epochUs === truncatedLegacyRecord.epochUs);
    assert.ok(retainedLegacy);
    assert.ok(!retainedLegacy.line1 && !retainedLegacy.line2, 'Different-epoch source was attached to legacy data');
  }
  api.assignInputValue(JSON.stringify([truncatedLegacyRow]), 'truncated legacy observation');
  api.applyIncomingData(historyTle(0), 'append', 'precise original TLE');
  const bothEpochs = parse(element('tles').value);
  assert.equal(bothEpochs.length, 2);
  assert.ok(!bothEpochs.find(record => record.epochUs === truncatedLegacyRecord.epochUs).line1);
  groups++;

  const validRow = rows([original[0]])[0];
  const corruptions = [
    row => { row.SMD_TLE = null; }, row => { row.SMD_TLE = []; }, row => { row.SMD_TLE = 'text'; },
    row => { row.SMD_TLE.schema_version = 2; }, row => { row.SMD_TLE.schema_version = '1'; },
    row => { delete row.SMD_TLE.schema_version; }, row => { delete row.SMD_TLE.line1; },
    row => { delete row.SMD_TLE.line2; }, row => { row.SMD_TLE.line1 = 1; },
    row => { row.SMD_TLE.line2 = {}; }, row => { delete row.SMD_SOURCE_FORMAT; },
    row => { row.SMD_SOURCE_FORMAT = 'OMM JSON'; },
    row => { row.SMD_TLE.line1 = row.SMD_TLE.line1.slice(0, 68) + ((Number(row.SMD_TLE.line1[68]) + 1) % 10); },
    row => { row.SMD_TLE.line2 = row.SMD_TLE.line2.slice(0, 68) + ((Number(row.SMD_TLE.line2[68]) + 1) % 10); },
    row => { row.EPOCH = '2026-07-06T02:57:46.665793Z'; },
    row => { delete row.ELEMENT_SET_NO; }
  ];
  for (const [field, value] of [
    ['NORAD_CAT_ID', 25545], ['MEAN_MOTION', 15.6], ['ECCENTRICITY', 0.0006],
    ['INCLINATION', 52], ['RA_OF_ASC_NODE', 86], ['ARG_OF_PERICENTER', 97],
    ['MEAN_ANOMALY', 51], ['MEAN_MOTION_DOT', 0.000002], ['MEAN_MOTION_DDOT', 0.00000001],
    ['BSTAR', 0.00002], ['EPHEMERIS_TYPE', 2], ['REV_AT_EPOCH', 12346],
    ['ELEMENT_SET_NO', 2], ['CLASSIFICATION_TYPE', 'C'], ['OBJECT_ID', '1999-001A']
  ]) corruptions.push(row => { row[field] = value; });
  for (const corrupt of corruptions) {
    const row = copy(validRow);
    corrupt(row);
    const rejected = api.parseOmmRecord(row);
    assert.equal(rejected.record, null, 'Inconsistent or invalid retained TLE source was accepted: ' + JSON.stringify(row));
    assert.ok(rejected.errors.length, 'Rejected retained source needs a validation explanation');
  }
  groups++;

  await importText(tlePackage);
  const invalidPackages = [];
  for (const version of [0, 2, '1', null]) invalidPackages.push({ ...copy(tlePackage), package_schema_version: version });
  for (const version of [0, 3, '2', null]) invalidPackages.push({ ...copy(tlePackage), run_identity_version: version });
  for (const corrupt of corruptions) {
    const saved = copy(tlePackage);
    corrupt(saved.normalized_input_omm[7]);
    invalidPackages.push(saved);
  }
  for (const saved of invalidPackages) {
    const protectedState = uiState();
    await importText(saved);
    assert.equal(element('tles').value, protectedState.input, 'Invalid package replaced current input');
    assert.deepEqual(uiState().controls, protectedState.controls, 'Invalid package replaced current settings');
    assert.equal(api.analysis(), protectedState.analysis, 'Invalid package replaced the current analysis');
    assert.ok(element('fileImportHint').textContent.length, 'Invalid package must explain rejection');
  }
  const protectedState = uiState();
  await importText(tlePackage, 'append');
  assert.equal(element('tles').value, protectedState.input, 'Package append must require replace mode');
  assert.deepEqual(uiState().controls, protectedState.controls);
  assert.equal(api.analysis(), protectedState.analysis);
  groups++;

  // Historical exports remain readable without inventing the lost source bits.
  const legacy = copy(tlePackage);
  delete legacy.package_schema_version;
  delete legacy.run_identity_version;
  legacy.run_id = 'smd-0123456789abcdef';
  for (const row of legacy.normalized_input_omm) {
    delete row.SMD_TLE;
    row.EPOCH = new Date(row.EPOCH).toISOString();
  }
  const decodedLegacy = api.decodeSavedPackage(JSON.stringify(legacy), 'replace');
  assert.equal(decodedLegacy.legacySchema, true);
  assert.equal(decodedLegacy.legacy, false, 'Missing schema and missing options are independent legacy cases');
  await importText(legacy);
  assert.ok(api.analysis() && !api.analysis().error, 'Legacy package could not be reopened');
  assert.match(api.analysis().runId, /^smd-v2-[0-9a-f]{16}$/);
  assert.notEqual(api.analysis().runId, legacy.run_id, 'Legacy run ID must not masquerade as the recalculated identity');
  assert.ok(api.analysis().records.every(record => !record.line1 && !record.line2));
  assert.match(element('fileImportHint').textContent, /older|legacy/i, 'Legacy source precision needs a visible qualification');
  const legacyResult = scientificResult(api.analysis());
  const reexportedLegacy = await exportPackage();
  assert.equal(reexportedLegacy.package_schema_version, 1);
  assert.ok(reexportedLegacy.normalized_input_omm.every(row => !Object.hasOwn(row, 'SMD_TLE')), 'Lost historical source lines must not be fabricated');
  await importText(reexportedLegacy);
  assert.deepEqual(scientificResult(api.analysis()), legacyResult);
  const oldOptions = copy(tlePackage);
  delete oldOptions.analysis_options;
  const decodedOptions = api.decodeSavedPackage(JSON.stringify(oldOptions), 'replace');
  assert.equal(decodedOptions.legacySchema, false);
  assert.equal(decodedOptions.legacy, true);
  delete oldOptions.package_schema_version;
  delete oldOptions.run_identity_version;
  const decodedBoth = api.decodeSavedPackage(JSON.stringify(oldOptions), 'replace');
  assert.equal(decodedBoth.legacySchema, true);
  assert.equal(decodedBoth.legacy, true);
  groups++;

  assert.equal(api.hasSgp4Support(), true);
  try {
    for (const missing of ['sgp4', 'twoline2satrec', 'json2satrec']) {
      windowObject.satellite = { ...satellite, [missing]: undefined };
      assert.equal(api.hasSgp4Support(), false, missing + ' is required for the propagation path');
    }
    windowObject.satellite = { ...satellite, propagate: undefined };
    assert.equal(api.hasSgp4Support(), true, 'Date-based propagate is no longer required');
    assert.equal(analyse(historyRaw).sgp4PairCount, 15);
  } finally {
    windowObject.satellite = satellite;
  }
  groups++;

  console.log('TLE precision and saved-package regressions passed (' + groups + ' groups).');
})().catch(error => { console.error(error); process.exitCode = 1; });
