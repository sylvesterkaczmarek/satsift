'use strict';

const { loadBrowserApp } = require('../tools/load_browser_app');

const fs = require('fs');
const vm = require('vm');

if (process.argv.length !== 3) throw new Error('Usage: node tests/benchmark_import_contract_test.js MATERIALIZED.json');

function makeClassList() {
  return { add() {}, remove() {}, contains() { return false; }, toggle() {} };
}

const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    const handlers = {};
    elements.set(id, {
      id, value: '', textContent: '', innerHTML: '', className: '', hidden: false,
      disabled: false, open: false, max: '', files: [], style: {}, classList: makeClassList(), handlers,
      addEventListener(type, handler) { handlers[type] = handler; },
      removeEventListener() {}, click() {}, focus() {}, select() {}, scrollIntoView() {},
      setAttribute() {}, getAttribute() { return null; }, querySelectorAll() { return []; },
      appendChild() {}, removeChild() {}, getContext() { return null; }, toBlob(callback) { callback(null); }
    });
  }
  return elements.get(id);
}

const document = {
  body: { appendChild() {}, removeChild() {} },
  getElementById: element,
  createElement(tag) { return element('__created_' + tag + '_' + Math.random()); },
  execCommand() { return false; }
};
const windowObject = {
  document,
  location: { href: 'https://example.test/satellite-maneuver-detector', search: '' },
  history: { replaceState() {} },
  setTimeout(handler) { if (typeof handler === 'function') handler(); return 1; },
  clearTimeout() {}, scrollTo() {}, addEventListener() {}, removeEventListener() {},
  innerWidth: 1440, devicePixelRatio: 1, Plotly: null, satellite: null
};
const context = {
  window: windowObject, document, navigator: { clipboard: null }, console, URL, URLSearchParams,
  Date, Math, Number, String, Array, Object, Set, Map, BigInt, JSON, RegExp, Error, TypeError, Promise,
  Blob: globalThis.Blob, AbortController: globalThis.AbortController,
  fetch: async () => { throw new Error('Network disabled in benchmark import contract test.'); }
};
context.globalThis = context;
context.self = windowObject;
vm.createContext(context);

vm.runInContext(fs.readFileSync('satellite-6.0.2.min.js', 'utf8'), context, { filename: 'satellite-6.0.2.min.js' });
if (!windowObject.satellite && context.satellite) windowObject.satellite = context.satellite;

const api = loadBrowserApp(context);

const decoded = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const normalized = api.normaliseBenchmarkDefinition(decoded);
if (normalized.cases.length !== 40) throw new Error(`Expected all 40 publication cases, got ${normalized.cases.length}.`);
if (normalized.cases.some(item => !['event-evidence', 'confirmed-quiet'].includes(item.labelStatus))) {
  throw new Error('Publication cases did not normalize to the canonical browser label contract.');
}
if (normalized.cases.filter(item => item.labelStatus === 'confirmed-quiet').length !== 10) {
  throw new Error('Verified-quiet publication exposure was not preserved as 10 confirmed-quiet runtime cases.');
}

console.log('Publication benchmark browser import contract passed: 40 cases, including 10 verified-quiet controls.');
