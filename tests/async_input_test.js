'use strict';

const { loadBrowserApp } = require('../tools/load_browser_app');

const assert = require('assert');
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
  location: { href: 'https://example.test/satellite-maneuver-detector', search: '' },
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
  solveKepler, orbitCoordinatesFromElements, readPublicCache, publicCacheKey, assignInputValue,
  loadPublicDataIntoInput, analysis: () => lastAnalysis };
` });
const api = windowObject.__test;
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }
function response(data) { return { ok: true, json: async () => data }; }
function historyFields() {
  element('publicNorad').value = '99901';
  element('historyStart').value = '2026-07-01';
  element('historyEnd').value = '2026-07-20';
}
let checks = 0;
(async () => {
  api.loadExample('leo', true, false);
  const original = element('tles').value;
  const omm = api.parseInput(original).records.map(api.recordToOmm);
  const norad = String(omm[0].NORAD_CAT_ID);
  historyFields(); element('publicNorad').value = norad;
  let pending = deferred(); fetchHandler = () => pending.promise;
  const loading = api.loadHistoricalData();
  api.loadExample('quiet', true, false);
  const quiet = element('tles').value;
  pending.resolve(response({ records: omm })); await loading;
  assert.strictEqual(element('tles').value, quiet, 'Slow history must not overwrite a newer demo'); checks++;

  pending = deferred();
  const importing = api.importLocalFile({ name: 'delayed.json', size: 100, text: () => pending.promise }, 'replace');
  element('tles').value = 'my new pasted input';
  element('tles').handlers.input();
  pending.resolve(JSON.stringify(omm)); await importing;
  assert.strictEqual(element('tles').value, 'my new pasted input', 'Slow file read must retain newer paste'); checks++;

  api.assignInputValue('', 'test'); element('publicNorad').value = norad;
  pending = deferred(); fetchHandler = () => pending.promise;
  const snapshot = api.fetchPublicOmm('replace');
  element('publicNorad').value = '12345';
  pending.resolve(response([omm[0]])); await snapshot;
  assert.strictEqual(element('tles').value, '', 'A response for an earlier object selection must not apply'); checks++;

  api.assignInputValue('', 'test'); element('publicNorad').value = norad;
  storage.clear(); fetchHandler = async () => response([{ ...omm[0], NORAD_CAT_ID: '12345' }]);
  await api.fetchPublicOmm('replace');
  assert.strictEqual(element('tles').value, '', 'Wrong-object snapshot must not apply');
  assert.strictEqual(storage.size, 0, 'Wrong-object snapshot must not poison cache'); checks++;

  for (const fetchedAt of ['bad', Date.now() + 999999, null]) {
    storage.set(api.publicCacheKey(norad), JSON.stringify({ fetchedAt, data: [omm[0]] }));
    assert.strictEqual(api.readPublicCache(norad), null, 'Invalid cache timestamp must expire');
  } checks++;
  storage.set(api.publicCacheKey(norad), JSON.stringify({ fetchedAt: Date.now(), data: [{ ...omm[0], NORAD_CAT_ID: '12345' }] }));
  assert.strictEqual(api.readPublicCache(norad), null, 'Wrong-object cache must be ignored'); checks++;

  api.loadExample('leo', true, false);
  const updated = api.parseInput(element('tles').value).records.map(api.recordToOmm);
  for (const record of updated) { delete record.SMD_TLE; delete record.SMD_SOURCE_FORMAT; }
  api.assignInputValue(JSON.stringify(updated), 'test OMM history');
  const correction = { ...updated[updated.length - 1], MEAN_MOTION: updated[updated.length - 1].MEAN_MOTION + 0.001, CREATION_DATE: '2026-08-01T00:00:00Z', ELEMENT_SET_NO: 9999, GP_ID: '999999' };
  api.loadPublicDataIntoInput(norad, [correction], false, 'append');
  assert(api.analysis() && !api.analysis().error, 'A correction with no added epoch must re-run the analysis');
  assert.strictEqual(api.analysis().n, updated.length, 'Correction must replace rather than add an epoch'); checks++;

  api.assignInputValue('invalid data', 'test'); element('run').click();
  assert(element('executiveSummary').classList.contains('visible'), 'Invalid input explanation must be visible');
  assert(element('executiveSummary').classList.contains('analysis-error'), 'Old summary must be hidden on invalid input');
  assert(element('stickyResultBar').hidden, 'Stale previous result must not remain in the sticky bar'); checks++;

  for (const e of [0, 0.8, 0.95, 0.999999]) for (const m of [-20, -3, -0.1, 0, 0.001, 2, 20]) {
    const E = api.solveKepler(m, e);
    assert(Math.abs(E - e * Math.sin(E) - m) < 1e-11, `Kepler residual for e=${e}, M=${m}`);
  } checks++;
  const coordinates = api.orbitCoordinatesFromElements({ a: 100000, elements: { ecc: 0.95, incDeg: 0, raanDeg: 0, argPerDeg: 0, meanAnomDeg: 0 } }, 100);
  assert(Math.abs(coordinates.x[0] - 5000) < 1e-8, '3D pericentre must use original eccentricity, not clamp to 0.8');
  assert(Math.abs(coordinates.x[50] + 195000) < 1e-8, '3D apocentre must use original eccentricity'); checks++;
  api.assignInputValue(original + '\n' + original, 'repeated TLE history'); element('run').click();
  assert.strictEqual(api.analysis().n, omm.length, 'Repeated TLEs must not manufacture extra evaluation points'); checks++;
  api.loadPublicDataIntoInput(norad, [omm[0]], false, 'append');
  assert.strictEqual(api.analysis().n, omm.length, 'Appending an equivalent OMM snapshot must not duplicate a TLE epoch'); checks++;
  console.log(`Async loading, visible errors and orbit-context regressions passed: ${checks}/12.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
