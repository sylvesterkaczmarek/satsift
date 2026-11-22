'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { sourceFiles, browserAssets, loadBrowserApp } = require('../tools/load_browser_app');

const root = process.cwd();
const files = sourceFiles(root);
const assets = browserAssets(root);
const entry = fs.readFileSync(path.join(root, 'app-3.4.js'), 'utf8');
let groups = 0;

function contextWithElements() {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, { textContent: '', value: id === 'tles' ? 'retained input' : '',
      className: '', disabled: false, attributes: {}, setAttribute(name, value) { this.attributes[name] = value; } });
    return elements.get(id);
  }
  const document = { getElementById: element, createElement() { return {}; }, head: { appendChild() {} } };
  const context = { document, window: { document }, console: { error() {} } };
  vm.createContext(context);
  return { context, element };
}

function inSnapshot(test) {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'smd-browser-module-'));
  try {
    for (const name of ['browser-assets.json', 'index.html', ...files]) {
      const target = path.join(temporary, name);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.copyFileSync(path.join(root, name), target);
    }
    test(temporary);
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}

async function drain() {
  // Each deferred script completion and entry promise chain must settle locally.
  for (let index = 0; index < 12; index++) await new Promise(resolve => setImmediate(resolve));
}

async function main() {
  const normal = contextWithElements();
  const api = loadBrowserApp(normal.context, { start: false });
  assert.equal(normal.context.SMDApplicationBoot.status, 'ready');
  assert.equal(typeof api.analyzeRaw, 'function');
  assert.equal(typeof api.importLocalFile, 'function');
  assert.equal(typeof api.start, 'function');
  assert.throws(() => vm.runInContext(fs.readFileSync(path.join(root, files[0]), 'utf8'), normal.context), /already registered/);
  const firstBoot = normal.context.SMDApplicationBoot;
  vm.runInContext(entry, normal.context);
  assert.strictEqual(normal.context.SMDApplicationBoot, firstBoot, 'Loading the entry twice must not construct a second application.');
  groups++;

  for (const mutate of [
    value => { value.schema = 'unknown'; },
    value => { value.module_sources.push(value.module_sources[0]); },
    value => { value.module_sources.reverse(); },
    value => { value.module_sources[0] = '../private.js'; },
    value => { value.module_sources[0] = 'app/unreviewed.js'; },
    value => { value.entry_source = '../private.js'; },
  ]) {
    inSnapshot(snapshot => {
      const filename = path.join(snapshot, 'browser-assets.json');
      const manifest = JSON.parse(fs.readFileSync(filename, 'utf8'));
      mutate(manifest);
      fs.writeFileSync(filename, JSON.stringify(manifest));
      assert.throws(() => loadBrowserApp(contextWithElements().context, { root: snapshot, start: false }));
    });
  }
  groups++;

  for (const mutate of [
    snapshot => fs.unlinkSync(path.join(snapshot, 'browser-assets.json')),
    snapshot => fs.unlinkSync(path.join(snapshot, files[1])),
    snapshot => fs.appendFileSync(path.join(snapshot, files[1]), '\n// Changed asset bytes.\n'),
    snapshot => {
      const filename = path.join(snapshot, 'index.html');
      fs.writeFileSync(filename, fs.readFileSync(filename, 'utf8').replace(assets[0].url, '/satellite-maneuver-detector/app/missing-000000000000.js'));
    },
    snapshot => {
      const filename = path.join(snapshot, 'index.html');
      const html = fs.readFileSync(filename, 'utf8');
      fs.writeFileSync(filename, html.replace(assets[0].url, 'FIRST_MODULE')
        .replace(assets[1].url, assets[0].url).replace('FIRST_MODULE', assets[1].url));
    },
  ]) inSnapshot(snapshot => {
    mutate(snapshot);
    assert.throws(() => loadBrowserApp(contextWithElements().context, { root: snapshot, start: false }));
  });
  groups++;

  const legacy = contextWithElements();
  const requested = [];
  legacy.context.document.head.appendChild = script => {
    const asset = assets.find(item => item.url === script.src);
    assert(asset && asset.name !== 'bootstrap', 'Legacy loading may request only declared immutable modules.');
    assert.equal(script.integrity, asset.integrity);
    assert.equal(script.crossOrigin, 'anonymous');
    assert.equal(script.async, false);
    requested.push(asset.name);
    queueMicrotask(() => {
      vm.runInContext(fs.readFileSync(path.join(root, asset.source), 'utf8'), legacy.context, { filename: asset.source });
      script.onload();
    });
  };
  vm.runInContext(entry.replace('workbench.start();', 'globalThis.application = workbench;'), legacy.context);
  await drain();
  assert.equal(legacy.context.SMDApplicationBoot.status, 'ready');
  assert.deepEqual(requested, assets.filter(asset => asset.name !== 'bootstrap').map(asset => asset.name));
  assert.equal(typeof legacy.context.application.analyzeRaw, 'function');
  groups++;

  for (const failure of ['network', 'missing-registration']) {
    const rejected = contextWithElements();
    let requests = 0;
    rejected.context.document.head.appendChild = script => {
      requests++;
      queueMicrotask(() => failure === 'network' ? script.onerror() : script.onload());
    };
    vm.runInContext(entry, rejected.context);
    await drain();
    assert.equal(rejected.context.SMDApplicationBoot.status, 'failed');
    assert.equal(requests, 1, 'A failed dependency must stop subsequent loading.');
    assert.equal(rejected.element('status').attributes.role, 'alert');
    assert.equal(rejected.element('run').disabled, true);
    assert.equal(rejected.element('tles').value, 'retained input');
    assert.match(rejected.element('status').textContent, /could not load completely/);
  }
  groups++;
  console.log(`Browser module loading passed: ${groups} groups covering production composition, exact module roster, stale assets, cached-document loading and explicit startup failure.`);
}

main().catch(error => { console.error(error.stack || error); process.exitCode = 1; });
