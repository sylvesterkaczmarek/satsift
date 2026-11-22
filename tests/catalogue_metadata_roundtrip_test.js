'use strict';

const { loadBrowserApp } = require('../tools/load_browser_app');

// Exercise real parsers, merge handlers and saved-package handlers offline.
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
DownloadURL.createObjectURL = blob => { capturedBlob = blob; return 'blob:catalogue-metadata-test'; };
DownloadURL.revokeObjectURL = () => {};
const windowObject = {
  document, location: { href: 'https://example.test/satsift', search: '' },
  history: { replaceState() {} }, setTimeout() { return 1; }, clearTimeout() {},
  scrollTo() {}, addEventListener() {}, removeEventListener() {}, innerWidth: 1440,
  devicePixelRatio: 1, Plotly: null, satellite: null
};
const context = {
  window: windowObject, document, navigator: { clipboard: null }, console, URL: DownloadURL,
  URLSearchParams, Date, Math, Number, String, Array, Object, Set, Map, BigInt, JSON,
  RegExp, Error, TypeError, Promise, Blob, AbortController,
  fetch: async () => { throw new Error('Network disabled in catalogue metadata test'); },
  localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) }
};
context.globalThis = context;
context.self = windowObject;
vm.createContext(context);
vm.runInContext(fs.readFileSync('satellite-6.0.2.min.js', 'utf8'), context);
windowObject.satellite = context.satellite || windowObject.satellite;
loadBrowserApp(context, { hooks: `
window.__catalogueTest = { parseInput, parseOmmRecord, recordToOmm, serialiseRecordsAsOmm,
  resolveCatalogueRevisions, mergeOrbitalHistories, applyIncomingData, assignInputValue,
  importLocalFile, loadPublicDataIntoInput, downloadBundle, addTleChecksum, satrecForRecord,
  analysis: () => lastAnalysis };
` });
const api = windowObject.__catalogueTest;
assert.ok(api, 'Application test hooks were not exposed');

const plainOmm = {
  NORAD_CAT_ID: 25544, EPOCH: '2026-07-06T00:00:00Z', MEAN_MOTION: 15.5,
  ECCENTRICITY: 0.0005, INCLINATION: 51.64, RA_OF_ASC_NODE: 85,
  ARG_OF_PERICENTER: 96, MEAN_ANOMALY: 50
};
function parse(raw) {
  const parsed = api.parseInput(typeof raw === 'string' ? raw : JSON.stringify(raw));
  assert.ok(!parsed.fatalMessage, parsed.fatalMessage);
  assert.equal(parsed.rejectedCount, 0, Array.from(parsed.rejectionReasons).join('; '));
  assert.ok(parsed.records.length, 'Fixture must contain valid orbital records');
  return parsed.records;
}
function rows(records) { return JSON.parse(api.serialiseRecordsAsOmm(records)); }
function roundTrip(records) { return parse(api.serialiseRecordsAsOmm(records)); }
function selected(records) {
  const result = api.resolveCatalogueRevisions(records);
  assert.equal(result.conflictingDuplicateCount, 0, 'Selection fixture became ambiguous');
  assert.equal(result.unresolvedNearSimultaneousCount, 0, 'Selection fixture became ambiguous');
  return Array.from(result.records, record => ({
    epochUs: record.epochUs, meanMotion: record.meanMotion,
    setKnown: record.elementSetNoKnown, set: record.elementSetNoKnown ? record.elementSetNo : null,
    creation: record.creationRaw || null, gp: record.gpId || null, source: record.sourceFormat
  }));
}
function checkSelectionInvariant(records, expectedMotions) {
  for (const input of [records, Array.from(records).reverse()]) {
    let current = input;
    const before = selected(current);
    assert.deepEqual(before.map(record => record.meanMotion), expectedMotions);
    for (let cycle = 0; cycle < 3; cycle++) {
      current = roundTrip(current);
      assert.deepEqual(selected(current), before, 'Record selection changed after serialisation');
    }
  }
}
function tle(setNo, meanMotion = 15.5, epoch = '26187.00000000') {
  let line1 = '1 25544U 98067A   26187.00000000  .00000100  00000-0  10000-4 0  999';
  let line2 = '2 25544  51.6400  85.0000 0005000  96.0000  50.0000 15.5000000012345';
  line1 = line1.slice(0, 18) + epoch + line1.slice(32, 64) + String(setNo).padStart(4);
  line2 = line2.slice(0, 52) + meanMotion.toFixed(8).padStart(11) + line2.slice(63, 68);
  return 'TEST SATELLITE\n' + api.addTleChecksum(line1) + '\n' + api.addTleChecksum(line2);
}
function nativeOmm(record, changes = {}) {
  const value = { ...rows([record])[0], ...changes };
  delete value.SMD_SOURCE_FORMAT;
  delete value.SMD_TLE;
  return value;
}
async function importText(raw, mode = 'replace', name = 'metadata-history.json') {
  const text = typeof raw === 'string' ? raw : JSON.stringify(raw);
  await api.importLocalFile({ name, size: Buffer.byteLength(text), text: async () => text }, mode);
}
async function exportPackage() {
  capturedBlob = null;
  api.downloadBundle();
  assert.ok(capturedBlob, 'Reproducibility handler must create a download');
  assert.match(downloadName, /^satellite-maneuver-reproducibility-.+\.json$/);
  return JSON.parse(await capturedBlob.text());
}
let groups = 0;
(async () => {
  // The original regression: a missing identifier must not turn into known 999.
  const absent = parse([plainOmm]);
  const correction = parse([{ ...plainOmm, ELEMENT_SET_NO: 10, MEAN_MOTION: 15.6 }]);
  assert.equal(absent[0].elementSetNoKnown, false);
  assert.equal(Object.hasOwn(rows(absent)[0], 'ELEMENT_SET_NO'), false, 'Missing metadata was exported as authoritative ELEMENT_SET_NO');
  checkSelectionInvariant(Array.from(absent).concat(Array.from(correction)), [15.6]);
  const exportedOriginal = roundTrip(absent);
  assert.deepEqual(selected(Array.from(exportedOriginal).concat(Array.from(correction))), selected(Array.from(absent).concat(Array.from(correction))));
  groups++;

  for (const omitted of [undefined, null, '', '   ']) {
    let current = parse([{ ...plainOmm, ELEMENT_SET_NO: omitted }]);
    for (let cycle = 0; cycle < 4; cycle++) {
      assert.equal(current[0].elementSetNoKnown, false);
      assert.equal(Object.hasOwn(rows(current)[0], 'ELEMENT_SET_NO'), false);
      assert.equal(Object.hasOwn(rows(current)[0], 'CREATION_DATE'), false);
      assert.equal(Object.hasOwn(rows(current)[0], 'GP_ID'), false);
      current = roundTrip(current);
    }
  }
  for (const supplied of [0, 10, 999, 9999, '00010']) {
    let current = parse([{ ...plainOmm, ELEMENT_SET_NO: supplied }]);
    for (let cycle = 0; cycle < 4; cycle++) {
      assert.equal(current[0].elementSetNoKnown, true);
      assert.equal(rows(current)[0].ELEMENT_SET_NO, Number(supplied));
      current = roundTrip(current);
    }
  }
  groups++;

  const sourceMetadata = { CREATION_DATE: '2026-07-06T01:02:03.456789+00:00', GP_ID: '900719925474099312345', ELEMENT_SET_NO: 0 };
  let current = parse([{ ...plainOmm, ...sourceMetadata }]);
  for (let cycle = 0; cycle < 3; cycle++) {
    for (const key of Object.keys(sourceMetadata)) assert.equal(rows(current)[0][key], sourceMetadata[key]);
    current = roundTrip(current);
  }
  checkSelectionInvariant(parse([
    { ...plainOmm, GP_ID: '9' },
    { ...plainOmm, GP_ID: '10', MEAN_MOTION: 15.6 }
  ]), [15.6]);
  // Element-set metadata is not required by the propagator.
  const missingSatrec = api.satrecForRecord(absent[0]);
  const explicitSatrec = api.satrecForRecord(parse([{ ...plainOmm, ELEMENT_SET_NO: 999 }])[0]);
  for (const axis of ['x', 'y', 'z']) {
    const actual = windowObject.satellite.sgp4(missingSatrec, 60).position[axis];
    assert.ok(Number.isFinite(actual));
    assert.equal(actual, windowObject.satellite.sgp4(explicitSatrec, 60).position[axis]);
  }
  groups++;

  for (const set of [0, 10, 999]) {
    const records = parse(tle(set));
    assert.equal(records[0].elementSetNoKnown, true, 'A validated TLE set number is supplied metadata');
    assert.equal(records[0].elementSetNo, set);
    assert.equal(rows(records)[0].ELEMENT_SET_NO, set);
    checkSelectionInvariant(records, [15.5]);
  }
  const olderTle = parse(tle(9, 15.4))[0];
  const newerTle = parse(tle(10, 15.5))[0];
  checkSelectionInvariant([olderTle, newerTle], [15.5]);
  const unknownNative = nativeOmm(olderTle);
  delete unknownNative.ELEMENT_SET_NO;
  checkSelectionInvariant([parse([unknownNative])[0], newerTle], [15.5]);
  checkSelectionInvariant([parse(tle(999, 15.4))[0], parse([nativeOmm(newerTle)])[0]], [15.4]);
  groups++;

  // These epochs differ by exactly 864 ms, so this checks origin preservation
  // without relying on the separate sub-millisecond TLE precision repair.
  const nearFirst = parse(tle(9, 15.5, '26187.00000000'))[0];
  const nearSecond = parse(tle(10, 15.6, '26187.00001000'))[0];
  assert.equal(nearSecond.epochUs - nearFirst.epochUs, 864000);
  checkSelectionInvariant([nearFirst, nearSecond], [15.5, 15.6]);
  checkSelectionInvariant([nearFirst, parse([nativeOmm(nearSecond)])[0]], [15.5, 15.6]);
  checkSelectionInvariant([parse([nativeOmm(nearFirst)])[0], nearSecond], [15.5, 15.6]);
  checkSelectionInvariant(parse([nativeOmm(nearFirst), nativeOmm(nearSecond)]), [15.6]);
  // Equivalent copies retain their TLE origin irrespective of arrival order.
  // A native duplicate must not cause a separate nearby observation to vanish.
  const exactNativeCopy = parse([nativeOmm(newerTle)])[0];
  const nearNativeCorrection = parse([nativeOmm(nearSecond, { ELEMENT_SET_NO: 11 })])[0];
  for (const permutation of [
    [newerTle, exactNativeCopy, nearNativeCorrection],
    [newerTle, nearNativeCorrection, exactNativeCopy],
    [exactNativeCopy, newerTle, nearNativeCorrection],
    [exactNativeCopy, nearNativeCorrection, newerTle],
    [nearNativeCorrection, newerTle, exactNativeCopy],
    [nearNativeCorrection, exactNativeCopy, newerTle]
  ]) checkSelectionInvariant(permutation, [15.5, 15.6]);
  for (const invalid of ['CSV', true, 7, [], {}]) {
    const rejected = api.parseOmmRecord({ ...plainOmm, SMD_SOURCE_FORMAT: invalid });
    assert.equal(rejected.record, null, 'Invalid source provenance was accepted');
    assert.ok(Array.from(rejected.errors).some(error => error.includes('SMD_SOURCE_FORMAT')));
  }
  groups++;

  for (const records of [
    parse([plainOmm, { ...plainOmm, MEAN_MOTION: 15.6 }]),
    parse([{ ...plainOmm, ELEMENT_SET_NO: 10 }, { ...plainOmm, ELEMENT_SET_NO: 10, MEAN_MOTION: 15.6 }]),
    // Leading zeroes do not make equal numeric catalogue identifiers newer.
    parse([{ ...plainOmm, ELEMENT_SET_NO: 10, GP_ID: '10' }, { ...plainOmm, ELEMENT_SET_NO: 10, GP_ID: '010', MEAN_MOTION: 15.6 }]),
    [newerTle, parse([nativeOmm(newerTle, { MEAN_MOTION: 15.6 })])[0]],
    [parse(tle(10, 15.5))[0], parse(tle(10, 15.6))[0]]
  ]) {
    for (const ordered of [records, Array.from(records).reverse()]) {
      let copy = ordered;
      for (let cycle = 0; cycle < 3; cycle++) {
        const unresolved = api.resolveCatalogueRevisions(copy);
        assert.equal(unresolved.conflictingDuplicateCount, 1);
        assert.equal(unresolved.records.length, 2, 'Genuinely ambiguous solutions must stay visible');
        const inputRows = rows(copy);
        assert.throws(() => api.mergeOrbitalHistories(JSON.stringify([inputRows[0]]), JSON.stringify([inputRows[1]])), /unresolved conflicting/);
        copy = roundTrip(copy);
      }
    }
  }
  api.assignInputValue(JSON.stringify([plainOmm]), 'ambiguous input');
  const protectedInput = element('tles').value;
  await importText([{ ...plainOmm, MEAN_MOTION: 15.6 }], 'append');
  assert.equal(element('tles').value, protectedInput, 'Ambiguous append must preserve current input');
  assert.match(element('fileImportHint').textContent, /unresolved conflicting/);
  groups++;

  // A preferred correction resolves the complete exact-epoch group, including
  // two conflicting records that arrived before it in any input permutation.
  const permutationsOfThree = records => [
    [records[0], records[1], records[2]], [records[0], records[2], records[1]],
    [records[1], records[0], records[2]], [records[1], records[2], records[0]],
    [records[2], records[0], records[1]], [records[2], records[1], records[0]]
  ];
  const preferredCorrection = parse([
    plainOmm,
    { ...plainOmm, MEAN_MOTION: 15.6 },
    { ...plainOmm, ELEMENT_SET_NO: 10, MEAN_MOTION: 15.7 }
  ]);
  for (const order of permutationsOfThree(preferredCorrection)) {
    checkSelectionInvariant(order, [15.7]);
    const inputRows = rows(order);
    const appended = api.mergeOrbitalHistories(JSON.stringify(inputRows.slice(0, 2)), JSON.stringify(inputRows.slice(2)));
    assert.equal(appended.records.length, 1, 'An authoritative correction must resolve the whole epoch group');
    assert.equal(appended.records[0].meanMotion, 15.7);
  }
  const equallyPreferred = parse([
    { ...plainOmm, ELEMENT_SET_NO: 10, MEAN_MOTION: 15.5 },
    { ...plainOmm, ELEMENT_SET_NO: 10, MEAN_MOTION: 15.6 },
    { ...plainOmm, ELEMENT_SET_NO: 9, MEAN_MOTION: 15.4 }
  ]);
  for (const order of permutationsOfThree(equallyPreferred)) {
    let copy = order;
    for (let cycle = 0; cycle < 3; cycle++) {
      const unresolved = api.resolveCatalogueRevisions(copy);
      assert.equal(unresolved.conflictingDuplicateCount, 1);
      assert.equal(unresolved.unresolvedNearSimultaneousCount, 0);
      assert.deepEqual(Array.from(unresolved.records, record => record.meanMotion).sort(), [15.5, 15.6]);
      assert.ok(unresolved.records.every(record => record.elementSetNo === 10));
      const inputRows = rows(copy);
      assert.throws(() => api.mergeOrbitalHistories(JSON.stringify(inputRows.slice(0, 2)), JSON.stringify(inputRows.slice(2))), /unresolved conflicting/);
      copy = roundTrip(copy);
    }
  }
  groups++;

  // A metadata-only enrichment changes later revision decisions and must persist.
  for (const [known, older] of [
    [{ ELEMENT_SET_NO: 10 }, { ELEMENT_SET_NO: 9 }],
    [{ ELEMENT_SET_NO: 0 }, {}],
    [{ ELEMENT_SET_NO: 999 }, { ELEMENT_SET_NO: 10 }],
    [{ CREATION_DATE: '2026-07-06T02:00:00Z' }, { CREATION_DATE: '2026-07-06T01:00:00Z', ELEMENT_SET_NO: 1000 }],
    [{ GP_ID: '900719925474099312345' }, { GP_ID: '900719925474099312344' }]
  ]) {
    api.assignInputValue(JSON.stringify([plainOmm]), 'metadata enrichment');
    const enriched = api.applyIncomingData(JSON.stringify([{ ...plainOmm, ...known }]), 'append', 'metadata enrichment');
    assert.equal(enriched.unchanged, false, 'Metadata-only enrichment must be committed');
    const retainedInput = element('tles').value;
    for (const [key, value] of Object.entries(known)) assert.equal(JSON.parse(retainedInput)[0][key], value);
    const ignored = api.applyIncomingData(JSON.stringify([{ ...plainOmm, ...older, MEAN_MOTION: 15.6 }]), 'append', 'older correction');
    assert.equal(ignored.unchanged, true, 'An older or unknown correction must not replace known metadata');
    assert.equal(element('tles').value, retainedInput);
    assert.equal(parse(element('tles').value)[0].meanMotion, 15.5);
  }
  groups++;

  const history = Array.from({ length: 16 }, (_, index) => ({
    ...plainOmm, EPOCH: new Date(Date.UTC(2026, 6, 6 + index)).toISOString()
  }));
  await importText(history);
  assert.ok(api.analysis() && !api.analysis().error, 'Initial OMM history must analyse successfully');
  for (let cycle = 0; cycle < 3; cycle++) {
    const saved = await exportPackage();
    assert.equal(saved.normalized_input_omm.length, history.length);
    assert.ok(saved.normalized_input_omm.every(row => !Object.hasOwn(row, 'ELEMENT_SET_NO')));
    api.assignInputValue('', 'before reopening');
    await importText(saved);
    assert.ok(api.analysis() && !api.analysis().error, element('fileImportHint').textContent);
    assert.ok(api.analysis().records.every(record => record.elementSetNoKnown === false));
  }
  const latest = history[history.length - 1];
  await importText([{ ...latest, ELEMENT_SET_NO: 10, MEAN_MOTION: 15.6 }], 'append');
  assert.equal(api.analysis().n, history.length);
  assert.equal(api.analysis().records.at(-1).meanMotion, 15.6, 'Correction 10 must survive package reopening');
  const savedCorrection = await exportPackage();
  assert.equal(savedCorrection.normalized_input_omm.at(-1).ELEMENT_SET_NO, 10);
  await importText(savedCorrection);
  api.loadPublicDataIntoInput('25544', [{ ...latest, ELEMENT_SET_NO: 11, MEAN_MOTION: 15.7 }], false, 'append');
  assert.equal(api.analysis().n, history.length);
  assert.equal(api.analysis().records.at(-1).meanMotion, 15.7, 'Public snapshot append must retain correction ordering');
  assert.equal(api.analysis().records.at(-1).elementSetNo, 11);
  const finalPackage = await exportPackage();
  await importText(finalPackage);
  assert.equal(api.analysis().records.at(-1).meanMotion, 15.7);
  assert.equal(api.analysis().records.at(-1).elementSetNo, 11);
  groups++;

  // The same real import and append handlers accept mixed source formats.
  await importText(tle(9, 15.4), 'replace', 'original.tle');
  await importText([nativeOmm(newerTle)], 'append');
  assert.equal(parse(element('tles').value).length, 1);
  assert.equal(parse(element('tles').value)[0].meanMotion, 15.5);
  await importText([nativeOmm(olderTle)], 'replace');
  await importText(tle(10, 15.5), 'append', 'correction.tle');
  assert.equal(parse(element('tles').value).length, 1);
  assert.equal(parse(element('tles').value)[0].meanMotion, 15.5);
  assert.equal(parse(element('tles').value)[0].sourceFormat, 'TLE');
  groups++;

  console.log(`Catalogue metadata round-trip regressions passed (${groups} groups).`);
})().catch(error => { console.error(error); process.exitCode = 1; });
