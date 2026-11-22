'use strict';

const { browserAssets, readBrowserSource, loadBrowserApp } = require('../tools/load_browser_app');

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
let createdCounter = 0;
let capturedBlob = null;
let capturedDownload = null;
const appendedScripts = [];

function makeElement(id, tagName = 'DIV') {
  const handlers = {};
  const valueDefaults = {
    win: '6', alpha: '0.10', dath: '0.25', stale: '36500', gapWarn: '4',
    orbitProfile: 'AUTO', detectorMode: 'multivariate', sensitivity: 'balanced',
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
  location: { href: 'https://example.test/satellite-maneuver-detector', search: '' },
  history: { replaceState() {} },
  setTimeout(handler) { if (typeof handler === 'function') handler(); return 1; },
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
  fetch: async () => { throw new Error('Network disabled in release-quality test.'); }
};
context.globalThis = context;
context.self = windowObject;
vm.createContext(context);

const indexHtml = fs.readFileSync('index.html', 'utf8');
assert(!/<script[^>]+plotly-3\.3\.1\.min\.js/i.test(indexHtml), 'Plotly must not be loaded eagerly by index.html.');
assert(/<script[^>]+satellite-6\.0\.2\.min\.js/i.test(indexHtml), 'satellite.js must remain available at startup for detector method 0.4.');
assert(indexHtml.includes('/satellite-maneuver-detector/satellite-6.0.2.min.js?v=14488fc91092'), 'satellite.js must use its content-versioned CDN key.');
const assets = browserAssets();
const scriptTags = indexHtml.match(/<script\b[^>]*>/g) || [];
let previousPosition = indexHtml.indexOf('/satellite-maneuver-detector/satellite-6.0.2.min.js?v=');
for (const asset of assets) {
  const matching = scriptTags.filter(tag => tag.includes('src="' + asset.url + '"'));
  assert.strictEqual(matching.length, 1, 'Each module must have exactly one content-addressed script tag: ' + asset.name);
  assert(/\bdefer\b/.test(matching[0]), 'Module loading must preserve deferred dependency order.');
  assert(matching[0].includes('integrity="' + asset.integrity + '"'), 'Each module needs its actual byte-integrity value.');
  const position = indexHtml.indexOf(matching[0]);
  assert(position > previousPosition, 'Browser dependencies must precede their entry point.');
  previousPosition = position;
}
assert(!indexHtml.includes('/satellite-maneuver-detector/app-3.4.js?v='), 'New pages must use the immutable bootstrap URL.');

const satelliteSource = fs.readFileSync('satellite-6.0.2.min.js', 'utf8');
vm.runInContext(satelliteSource, context, { filename: 'satellite-6.0.2.min.js' });
if (!windowObject.satellite && context.satellite) windowObject.satellite = context.satellite;
assert(windowObject.satellite, 'satellite.js did not initialise in the test harness.');

const appSource = readBrowserSource();
assert(!appSource.includes('queueOrbitComparisonForFlag'), '3D context must not fall back to a strongest-adjacent-pair helper.');
assert(appSource.includes('queueOrbitComparisonForEvent(event)'), 'Event-table 3D controls must queue the grouped event.');
assert(appSource.includes('event.netDeltaA'), '3D grouped-event context must display the event net delta-a.');
const api = loadBrowserApp(context);
assert(api, 'Release-quality test hooks were not exposed in the VM.');

const groupedRecords = [
  { t: new Date('2026-01-01T00:00:00Z'), a: 7000.0 },
  { t: new Date('2026-01-02T00:00:00Z'), a: 7000.1 },
  { t: new Date('2026-01-03T00:00:00Z'), a: 6999.9 },
  { t: new Date('2026-01-04T00:00:00Z'), a: 6999.5 }
];
const groupedFlags = [
  { idx: 2, t: groupedRecords[2].t, dA: -0.2, severityScore: 1.4, breachedFeatures: ['aRate'] },
  { idx: 3, t: groupedRecords[3].t, dA: -0.4, severityScore: 2.1, breachedFeatures: ['aRate', 'alongRate'] }
];
const grouped = api.groupFlagsIntoEvents(groupedFlags, groupedRecords, 1, 'LEO');
assert.strictEqual(grouped.length, 1, 'Adjacent anomalous points should form one grouped event.');
assert.strictEqual(grouped[0].contextBeforeIndex, 1, 'Grouped context must start at the record before the first flagged point.');
assert.strictEqual(grouped[0].contextAfterIndex, 3, 'Grouped context must end at the final flagged point.');
assert(Math.abs(grouped[0].netDeltaA - (groupedRecords[3].a - groupedRecords[1].a)) < 1e-12, 'Grouped net delta-a must use the same context endpoints shown by 3D.');
assert.notStrictEqual(grouped[0].netDeltaA, grouped[0].strongest.dA, 'Fixture must distinguish grouped net change from strongest adjacent change.');

const options = {
  requestedWindow: 6,
  alpha: 0.10,
  minAbsDeltaA: 0.05,
  maximumStaleDays: 36500,
  maximumGapFactor: 3,
  orbitProfile: 'auto',
  detectorMode: 'multivariate'
};
const analysis = api.analyzeRaw(api.exampleTles('leo'), 'release-quality-test', options);
assert(!analysis.error && analysis.interpretable, 'Fixture analysis must be valid.');
const payloads = api.buildAnalysisDownloadPayloads(analysis);

async function assertExactDownload(payload) {
  capturedBlob = null;
  capturedDownload = null;
  api.downloadText(payload.filename, payload.mimeType, payload.text);
  assert(capturedBlob, `No Blob was created for ${payload.filename}.`);
  assert(capturedDownload, `No browser download was triggered for ${payload.filename}.`);
  assert.strictEqual(capturedDownload.filename, payload.filename, 'Download filename changed unexpectedly.');
  const actual = Buffer.from(await capturedBlob.arrayBuffer());
  const expected = Buffer.from(payload.text, 'utf8');
  assert(actual.equals(expected), `Downloaded bytes differ from generated payload for ${payload.filename}.`);
  assert.strictEqual(
    crypto.createHash('sha256').update(actual).digest('hex'),
    crypto.createHash('sha256').update(expected).digest('hex'),
    `SHA-256 mismatch for ${payload.filename}.`
  );
}

(async () => {
  await assertExactDownload(payloads.csv);
  await assertExactDownload(payloads.json);
  await assertExactDownload(payloads.reproducibility);

  const resultJson = JSON.parse(payloads.json.text);
  const reproducibilityJson = JSON.parse(payloads.reproducibility.text);
  assert.strictEqual(resultJson.run_id, analysis.runId, 'Analysis JSON must preserve the deterministic run ID.');
  assert.strictEqual(reproducibilityJson.run_id, analysis.runId, 'Reproducibility JSON must preserve the deterministic run ID.');
  assert.deepStrictEqual(reproducibilityJson.normalized_input_omm.length, analysis.records.length, 'Reproducibility package must retain every normalized input record.');
  assert.strictEqual(reproducibilityJson.csv, analysis.csv, 'Embedded CSV must be byte-identical to the CSV payload text.');
  assert.strictEqual(reproducibilityJson.evidence_note, analysis.evidenceText, 'Embedded evidence note must be exact.');

  assert.strictEqual(appendedScripts.length, 0, 'Plotly should not be appended before it is requested.');
  const loadPromise = api.ensurePlotlyLoaded();
  assert.strictEqual(appendedScripts.length, 1, 'Plotly loader should append exactly one script.');
  assert.strictEqual(appendedScripts[0].src, '/satellite-maneuver-detector/plotly-3.3.1.min.js', 'Plotly loader must use the pinned same-site asset.');
  windowObject.Plotly = { version: '3.3.1' };
  appendedScripts[0].handlers.load();
  await loadPromise;
  await api.ensurePlotlyLoaded();
  assert.strictEqual(appendedScripts.length, 1, 'Repeated Plotly requests must be coalesced.');

  console.log('Release-quality browser regressions passed: grouped-event context, lazy Plotly, and exact download bytes.');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
