'use strict';

const { loadBrowserApp } = require('../tools/load_browser_app');

const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const vm = require('vm');

function makeClassList() {
  const values = new Set();
  return {
    add(...items) { items.forEach(item => values.add(item)); },
    remove(...items) { items.forEach(item => values.delete(item)); },
    contains(item) { return values.has(item); },
    toggle(item) { if (values.has(item)) values.delete(item); else values.add(item); }
  };
}

const elements = new Map();
const storage = new Map();
let fetchHandler = async () => { throw new Error('Network disabled'); };
let createdCounter = 0;
let capturedBlob = null;
let capturedDownload = null;
const appendedScripts = [];

function makeElement(id, tagName = 'DIV') {
  const handlers = {};
  const valueDefaults = {
    win: '6', alpha: '0.10', dath: '0.25', stale: '36500', gapWarn: '4',
    orbitProfile: 'auto', detectorMode: 'multivariate', sensitivity: 'balanced',
    demoSelect: 'leo', importMode: 'replace', publicNorad: '', historyStart: '', historyEnd: '', tles: ''
  };
  return {
    id,
    tagName,
    value: Object.prototype.hasOwnProperty.call(valueDefaults, id) ? valueDefaults[id] : '',
    textContent: '',
    innerHTML: '',
    className: '',
    hidden: false,
    disabled: false,
    open: false,
    max: '',
    files: [],
    style: {},
    classList: makeClassList(),
    handlers,
    parentNode: null,
    href: '',
    download: '',
    src: '',
    async: false,
    addEventListener(type, handler) { handlers[type] = handler; },
    removeEventListener() {},
    click() {
      if (tagName === 'A') capturedDownload = { filename: this.download, href: this.href };
      if (handlers.click) handlers.click.call(this, { preventDefault() {} });
    },
    focus() {},
    select() {},
    scrollIntoView() {},
    setAttribute(name, value) { this[name] = value; },
    getAttribute(name) { return this[name] || null; },
    querySelectorAll() { return []; },
    appendChild(child) { child.parentNode = this; },
    removeChild(child) { if (child) child.parentNode = null; },
    getContext() { return null; },
    toBlob(callback) { callback(null); }
  };
}

function element(id) {
  if (!elements.has(id)) elements.set(id, makeElement(id));
  return elements.get(id);
}

const head = {
  appendChild(child) {
    child.parentNode = this;
    if (child.tagName === 'SCRIPT') appendedScripts.push(child);
  },
  removeChild(child) {
    child.parentNode = null;
    const index = appendedScripts.indexOf(child);
    if (index >= 0) appendedScripts.splice(index, 1);
  }
};

const document = {
  head,
  body: { appendChild() {}, removeChild() {} },
  getElementById: element,
  createElement(tag) { return makeElement('__created_' + tag + '_' + (++createdCounter), String(tag).toUpperCase()); },
  execCommand() { return false; }
};

class CapturingURL extends URL {}
CapturingURL.createObjectURL = blob => {
  capturedBlob = blob;
  return 'blob:smd-release-quality';
};
CapturingURL.revokeObjectURL = () => {};

const windowObject = {
  document,
  location: { href: 'https://example.test/satsift', search: '' },
  history: { replaceState() {} },
  setTimeout() { return 1; },
  clearTimeout() {},
  scrollTo() {},
  addEventListener() {},
  removeEventListener() {},
  innerWidth: 1440,
  devicePixelRatio: 1,
  Plotly: null,
  satellite: null
};

const context = {
  window: windowObject,
  document,
  navigator: { clipboard: null },
  console,
  URL: CapturingURL,
  URLSearchParams,
  Date,
  Math,
  Number,
  String,
  Array,
  Object,
  Set,
  Map,
  BigInt,
  JSON,
  RegExp,
  Error,
  TypeError,
  Promise,
  Blob: globalThis.Blob,
  AbortController: globalThis.AbortController,
  fetch: async (...args) => fetchHandler(...args),
  localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) }
};
context.globalThis = context;
context.self = windowObject;
vm.createContext(context);


vm.runInContext(fs.readFileSync('satellite-6.0.2.min.js', 'utf8'), context);
windowObject.satellite = context.satellite || windowObject.satellite;
loadBrowserApp(context, { hooks: `
window.__test = { loadHistoricalData, fetchPublicOmm, importLocalFile, loadExample, parseInput, recordToOmm,
  readPublicCache, writePublicCache, publicCacheKey, assignInputValue, applyIncomingData,
  loadPublicDataIntoInput, buildMachineReadableResult, decodeSavedPackage, normalizedInputFingerprint,
  currentGpInputProvenance, makeInputProvenance, provenanceSummary, getAnalysisOptions, run,
  provenance: () => currentInputProvenance, analysis: () => lastAnalysis };
` });
const api = windowObject.__test;

const copy = value => JSON.parse(JSON.stringify(value));
const response = data => ({ ok: true, json: async () => copy(data) });
const sha = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const norad = '25544';
const acquisitionTime = '2026-02-01T08:09:10+00:00';
const records = Array.from({ length: 16 }, (_, index) => ({
  OBJECT_NAME: 'PROVENANCE FIXTURE', OBJECT_ID: '1998-067A', NORAD_CAT_ID: norad,
  EPOCH: '2026-01-' + String(index + 1).padStart(2, '0') + 'T12:00:00.123456Z',
  CREATION_DATE: '2026-01-' + String(index + 1).padStart(2, '0') + 'T13:00:00.123456Z',
  GP_ID: String(index + 1), ELEMENT_SET_NO: index + 1,
  MEAN_MOTION: 15.5 - index * 0.00001, ECCENTRICITY: 0.001,
  INCLINATION: 51.6, RA_OF_ASC_NODE: 10, ARG_OF_PERICENTER: 20,
  MEAN_ANOMALY: (30 + index * 15) % 360, BSTAR: 0
}));
const range = { start: '2026-01-01', end: '2026-01-16' };
function historyMetadata(rows = records) {
  return {
    schema_version: 1, provider: 'Space-Track', source_class: 'GP_HISTORY',
    policy: 'retained-history-v1', norad, requested_range: copy(range),
    records_sha256: sha(rows), cache_snapshot_sha256: '2'.repeat(64),
    cache_updated_at: acquisitionTime, retrieval_status: 'recorded',
    acquisitions: [{
      kind: 'upstream-fetch', source_class: 'GP_HISTORY', ...copy(range),
      retrieved_at: acquisitionTime, records_sha256: sha(rows)
    }]
  };
}
const initialMetadata = historyMetadata();
function setHistoryFields() {
  element('publicNorad').value = norad;
  element('historyStart').value = range.start;
  element('historyEnd').value = range.end;
}
function exported() {
  const analysis = api.analysis();
  assert(analysis && !analysis.error, 'Fixture requires a successful analysis');
  return copy(api.buildMachineReadableResult(analysis, true));
}
function snapshot() {
  return {
    raw: element('tles').value,
    options: copy(api.getAnalysisOptions()),
    provenance: copy(api.provenance()),
    analysis: api.analysis(),
    runId: api.analysis() && api.analysis().runId
  };
}
function assertUnchanged(previous) {
  assert.strictEqual(element('tles').value, previous.raw, 'Rejected operation changed input');
  assert.deepStrictEqual(copy(api.getAnalysisOptions()), previous.options, 'Rejected operation changed settings');
  assert.deepStrictEqual(copy(api.provenance()), previous.provenance, 'Rejected operation changed provenance');
  assert.strictEqual(api.analysis(), previous.analysis, 'Rejected operation replaced current analysis');
}
async function importJson(value, mode = 'replace', name = 'source-fixture.json') {
  const raw = JSON.stringify(value);
  await api.importLocalFile({ name, size: Buffer.byteLength(raw), text: async () => raw }, mode);
}
async function restorePackage(value) {
  await importJson(value);
  assert(element('fileImportHint').textContent.includes('Saved input and analysis settings restored.'), element('fileImportHint').textContent);
}
let groups = 0;
(async () => {
  setHistoryFields();
  let calls = 0;
  fetchHandler = async () => {
    calls++;
    return response({
      records, cached: false, retrieved_at: acquisitionTime,
      served_at: '2026-11-22T12:00:00Z', data_provenance: initialMetadata
    });
  };
  await api.loadHistoricalData();
  assert.strictEqual(calls, 1);
  const first = exported();
  const originalRunId = first.run_id;
  assert.strictEqual(first.workbench_version, '3.5.0');
  assert.strictEqual(first.package_schema_version, 1);
  assert.strictEqual(first.run_identity_version, 2);
  assert.strictEqual(first.data_provenance.schema_version, 1);
  assert.strictEqual(first.data_provenance.input_fingerprint.algorithm, 'fnv1a64-utf16-normalized-omm-v1');
  assert.deepStrictEqual(first.data_provenance.sources[0].metadata, initialMetadata);
  assert.deepStrictEqual(first.data_provenance.input_fingerprint, copy(api.normalizedInputFingerprint(api.analysis().records)));
  assert.strictEqual(first.data_provenance.sources[0].kind, 'space-track-history');
  assert.strictEqual(first.data_provenance.sources[0].metadata.records_sha256.length, 64);
  assert.strictEqual(first.data_provenance.input_fingerprint.value.length, 16);
  assert(!JSON.stringify(first.data_provenance).includes('served_at'));
  assert(element('historyFetchHint').textContent.includes(acquisitionTime));
  assert(!element('historyFetchHint').textContent.includes('2026-11-22T12:00:00Z'));
  assert(first.evidence_note.includes('reported content snapshots'));
  assert(first.evidence_note.includes(initialMetadata.cache_snapshot_sha256));
  groups++;

  // Serving the same source again must not rewrite acquisition evidence or run identity.
  setHistoryFields();
  fetchHandler = async () => response({
    records, cached: true, retrieved_at: '2026-11-22T13:00:00Z',
    served_at: '2026-11-22T13:00:00Z', data_provenance: initialMetadata
  });
  await api.loadHistoricalData();
  assert.deepStrictEqual(exported().data_provenance, first.data_provenance);
  assert.strictEqual(exported().run_id, originalRunId);
  assert(element('historyFetchHint').textContent.includes('server cache'));
  groups++;

  // Provenance changes are independent of the numerical run identifier.
  const laterMetadata = copy(initialMetadata);
  laterMetadata.cache_updated_at = '2026-02-02T08:09:10+00:00';
  laterMetadata.acquisitions[0].retrieved_at = laterMetadata.cache_updated_at;
  laterMetadata.cache_snapshot_sha256 = '3'.repeat(64);
  fetchHandler = async () => response({ records, data_provenance: laterMetadata });
  await api.loadHistoricalData();
  assert.strictEqual(exported().run_id, originalRunId);
  assert.notDeepStrictEqual(exported().data_provenance, first.data_provenance);
  await restorePackage(first);
  groups++;

  // A cached current-GP correction retains the original acquisition instant.
  const corrected = { ...records[15], CREATION_DATE: '2026-03-01T00:00:00Z', GP_ID: '1001', MEAN_MOTION: 15.6 };
  const fetchedAt = Date.now() - 60000;
  api.writePublicCache(norad, [corrected], fetchedAt);
  fetchHandler = async () => { throw new Error('Cached GP load must not use a network request'); };
  element('publicNorad').value = norad;
  await api.fetchPublicOmm('append');
  const withCurrent = exported();
  assert.strictEqual(withCurrent.data_provenance.sources.length, 2);
  assert.deepStrictEqual(withCurrent.data_provenance.sources[0], first.data_provenance.sources[0]);
  assert.strictEqual(withCurrent.data_provenance.sources[1].kind, 'celestrak-gp');
  assert.strictEqual(withCurrent.data_provenance.sources[1].retrieved_at, new Date(fetchedAt).toISOString());
  assert.strictEqual(api.readPublicCache(norad).fetchedAt, fetchedAt);
  assert.notStrictEqual(withCurrent.data_provenance.input_fingerprint.value, first.data_provenance.input_fingerprint.value);
  assert.notStrictEqual(withCurrent.run_id, originalRunId);
  assert.strictEqual(withCurrent.normalized_input_omm[15].MEAN_MOTION, 15.6);
  assert.strictEqual(withCurrent.data_attribution, 'Basic SSA data from Space-Track.org, operated by USSPACECOM');
  assert(!withCurrent.evidence_note.includes('Data attribution: not applicable'));
  const unchanged = snapshot();
  api.writePublicCache(norad, [corrected], fetchedAt + 1000);
  await api.fetchPublicOmm('append');
  assertUnchanged(unchanged);
  groups++;

  // Local corrections retain the earlier lineage and mark their own origin unknown.
  const localCorrection = { ...records[14], CREATION_DATE: '2026-04-01T00:00:00Z', GP_ID: '2001', MEAN_MOTION: 15.7 };
  await importJson([localCorrection], 'append', 'private-source-name.json');
  const mixed = exported();
  assert.strictEqual(mixed.data_provenance.sources.length, 3);
  assert.strictEqual(mixed.data_provenance.sources[2].kind, 'unrecorded-input');
  assert(!JSON.stringify(mixed.data_provenance).includes('private-source-name'));
  assert(mixed.evidence_note.includes('Some source retrieval times are unknown.'));
  assert.deepStrictEqual(mixed.data_provenance.sources.slice(0, 2), withCurrent.data_provenance.sources);
  assert.strictEqual(mixed.normalized_input_omm[14].MEAN_MOTION, 15.7);
  groups++;

  for (let cycle = 0; cycle < 3; cycle++) {
    api.assignInputValue('', 'cleared before reopening');
    await restorePackage(mixed);
    assert.deepStrictEqual(exported().data_provenance, mixed.data_provenance, 'Reopening changed source lineage or normalized binding');
    assert.strictEqual(exported().run_id, mixed.run_id);
  }
  groups++;

  // All optional metadata validation precedes changing the editor or controls.
  const invalidPackages = [];
  function invalid(change) { const value = copy(mixed); change(value); invalidPackages.push(value); }
  invalid(value => { value.data_provenance.schema_version = 2; });
  invalid(value => { value.data_provenance.input_fingerprint.algorithm = 'unknown'; });
  invalid(value => { value.data_provenance.input_fingerprint.value = '0'.repeat(16); });
  invalid(value => { value.data_provenance.sources[0].metadata.norad = '99999'; });
  invalid(value => { value.data_provenance.sources[0].metadata.cache_path = '/private/source'; });
  invalid(value => { value.data_provenance.sources[0].metadata.acquisitions[0].retrieved_at = '2026-02-01T08:09:10'; });
  invalid(value => { value.data_provenance.sources[0].metadata.acquisitions[0].retrieved_at = '2026-02-30T08:09:10Z'; });
  invalid(value => { value.data_provenance.sources[0].metadata.acquisitions[0].retrieved_at = '2026-02-01T08:09:10Z\n'; });
  invalid(value => { value.data_provenance.sources[0].metadata.retrieval_status = 'partial'; });
  invalid(value => { value.data_provenance.sources[0].metadata.acquisitions[0].start = '2026-01-02'; });
  invalid(value => { value.data_provenance.sources[0].metadata.acquisitions.push(copy(value.data_provenance.sources[0].metadata.acquisitions[0])); });
  invalid(value => { value.normalized_input_omm[0].MEAN_MOTION += 0.1; });
  invalid(value => { value.data_provenance.sources = Array.from({ length: 65 }, () => copy(value.data_provenance.sources[0])); });
  invalid(value => { value.data_provenance = false; });
  invalid(value => { value.data_provenance = []; });
  invalid(value => {
    value.data_provenance.sources = Array.from({ length: 64 }, (_, sourceIndex) => {
      const source = copy(mixed.data_provenance.sources[0]);
      source.metadata.cache_snapshot_sha256 = sourceIndex.toString(16).padStart(64, '0');
      source.metadata.acquisitions = Array.from({ length: 16 }, (_, index) => ({
        ...copy(source.metadata.acquisitions[0]),
        start: '2026-01-' + String(index + 1).padStart(2, '0'),
        end: '2026-01-' + String(index + 1).padStart(2, '0')
      }));
      return source;
    });
    assert(JSON.stringify(value.data_provenance).length > 65536);
  });
  for (const value of invalidPackages) {
    const previous = snapshot();
    await importJson(value);
    assertUnchanged(previous);
    assert(element('fileImportHint').textContent.includes('provenance'), element('fileImportHint').textContent);
  }
  const wrongObject = { ...records[0], NORAD_CAT_ID: '99999' };
  const beforeWrongAppend = snapshot();
  await importJson([wrongObject], 'append');
  assertUnchanged(beforeWrongAppend);
  groups++;

  // A retained endpoint envelope can be imported with its actual source evidence.
  await importJson({ records, data_provenance: initialMetadata });
  assert.deepStrictEqual(exported().data_provenance, first.data_provenance);
  for (const epoch of ['2025-12-31T23:59:59.999999Z', '2026-01-17T00:00:00.000000Z']) {
    const previous = snapshot();
    const outside = copy(records);
    outside[0].EPOCH = epoch;
    await importJson({ records: outside, data_provenance: initialMetadata });
    assertUnchanged(previous);
    assert(element('fileImportHint').textContent.includes('provenance'));
  }
  const unsortedMetadata = copy(initialMetadata);
  unsortedMetadata.acquisitions = [
    { ...copy(initialMetadata.acquisitions[0]), start: '2026-01-09', end: '2026-01-31' },
    { ...copy(initialMetadata.acquisitions[0]), start: '2025-12-20', end: '2026-01-08' }
  ];
  await importJson({ records, data_provenance: unsortedMetadata });
  assert.deepStrictEqual(exported().data_provenance.sources[0].metadata.acquisitions, unsortedMetadata.acquisitions);
  groups++;

  // Manual edits, demos, ordinary replacement and older sources cannot inherit stale evidence.
  await restorePackage(mixed);
  element('tles').handlers.input.call(element('tles'));
  api.run();
  assert.strictEqual(api.provenance(), null);
  assert.strictEqual(exported().data_provenance, null);
  assert(exported().evidence_note.includes('Source retrieval time was not recorded.'));
  await restorePackage(mixed);
  api.loadExample('leo', true, false);
  assert.strictEqual(api.provenance(), null);
  assert.strictEqual(exported().data_provenance, null);
  await restorePackage(mixed);
  await importJson(records);
  assert.strictEqual(exported().data_provenance, null);
  const oldPackage = copy(first);
  delete oldPackage.data_provenance;
  await restorePackage(oldPackage);
  assert.strictEqual(exported().data_provenance, null);
  setHistoryFields();
  fetchHandler = async () => response({ records, cached: true, retrieved_at: '2026-11-22T12:00:00Z' });
  await api.loadHistoricalData();
  assert.strictEqual(exported().data_provenance, null);
  assert(element('historyFetchHint').textContent.includes('retrieval time was not recorded'));
  groups++;

  // Unknown existing input remains explicit when a recorded current snapshot is appended.
  api.writePublicCache(norad, [corrected], fetchedAt);
  await api.fetchPublicOmm('append');
  assert.strictEqual(exported().data_provenance.sources[0].kind, 'unrecorded-input');
  assert.strictEqual(exported().data_provenance.sources[1].kind, 'celestrak-gp');
  assert(exported().evidence_note.includes('Some source retrieval times are unknown.'));
  groups++;

  // One fresh retrieval instant is shared between the GP cache and source lineage.
  api.assignInputValue('', 'empty input');
  storage.delete(api.publicCacheKey(norad));
  element('publicNorad').value = norad;
  calls = 0;
  fetchHandler = async () => { calls++; return response([corrected]); };
  await api.fetchPublicOmm('replace');
  assert.strictEqual(calls, 1);
  const cached = api.readPublicCache(norad);
  assert(cached);
  assert.strictEqual(api.provenance().sources[0].retrieved_at, new Date(cached.fetchedAt).toISOString());
  groups++;

  // A source-count overflow must preserve the existing complete input and lineage.
  await restorePackage(first);
  const parsed = api.parseInput(element('tles').value).records;
  const manySources = Array.from({ length: 64 }, (_, index) => ({
    kind: 'celestrak-gp', norad,
    input_fingerprint: copy(api.normalizedInputFingerprint(parsed)),
    retrieved_at: new Date(Date.UTC(2026, 1, 1, 0, 0, index)).toISOString()
  }));
  const many = api.makeInputProvenance(parsed, manySources);
  api.assignInputValue(element('tles').value, 'bounded lineage fixture', 'fixture loaded', many);
  api.run();
  const beforeOverflow = snapshot();
  const nextRecords = api.parseInput(JSON.stringify([corrected])).records;
  const incoming = api.currentGpInputProvenance(nextRecords, norad, fetchedAt);
  assert.throws(() => api.applyIncomingData(JSON.stringify([corrected]), 'append', 'current source', incoming), /provenance/);
  assertUnchanged(beforeOverflow);
  groups++;

  console.log('History provenance browser regressions passed (' + groups + ' groups).');
})().catch(error => { console.error(error); process.exitCode = 1; });
