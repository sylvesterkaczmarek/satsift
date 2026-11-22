'use strict';

const { loadBrowserApp } = require('../tools/load_browser_app');

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
function element(id) {
  if (!elements.has(id)) {
    const handlers = {};
    const valueDefaults = {
      win: '6', alpha: '0.10', dath: '0.25', stale: '36500', gapWarn: '4',
      orbitProfile: 'AUTO', detectorMode: 'multivariate', sensitivity: 'balanced',
      demoSelect: 'leo', importMode: 'replace', publicNorad: '', historyStart: '', historyEnd: '', tles: ''
    };
    elements.set(id, {
      id,
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
      addEventListener(type, handler) { handlers[type] = handler; },
      removeEventListener() {},
      click() { if (handlers.click) handlers.click.call(this, { preventDefault() {} }); },
      focus() {},
      select() {},
      scrollIntoView() {},
      setAttribute() {},
      getAttribute() { return null; },
      querySelectorAll() { return []; },
      appendChild() {},
      removeChild() {},
      getContext() { return null; },
      toBlob(callback) { callback(null); }
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
  URL,
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
  fetch: async () => { throw new Error('Network disabled in workbench self-test harness.'); }
};
context.globalThis = context;
context.self = windowObject;
vm.createContext(context);

const satelliteSource = fs.readFileSync('satellite-6.0.2.min.js', 'utf8');
vm.runInContext(satelliteSource, context, { filename: 'satellite-6.0.2.min.js' });
if (!windowObject.satellite && context.satellite) windowObject.satellite = context.satellite;
if (!windowObject.satellite) throw new Error('satellite.js did not initialise in the test harness.');

loadBrowserApp(context);

const button = element('runSelfTests');
if (!button.handlers.click) throw new Error('Workbench self-test button handler was not registered.');
button.handlers.click.call(button, { preventDefault() {} });

const hint = element('selfTestHint').textContent;
const match = String(hint).match(/(\d+) of (\d+) regression checks passed/);
if (!match) throw new Error('Workbench self-test did not produce a recognizable result: ' + hint);
const passed = Number(match[1]);
const total = Number(match[2]);
if (passed !== total) {
  throw new Error(`Workbench self-test failed: ${passed}/${total}. ${element('selfTestWrap').innerHTML}`);
}

console.log(`Workbench browser-style self-tests passed: ${passed}/${total}.`);
