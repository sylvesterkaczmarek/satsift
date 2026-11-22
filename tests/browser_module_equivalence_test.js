'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadBrowserApp, sourceFiles, readBrowserSource } = require('../tools/load_browser_app');

const CLOCK = '2026-11-22T12:00:00.000Z';
const ORIGINAL_FIXTURE = path.join(__dirname, 'fixtures/browser-equivalence-v1.json');
const PRIOR_FIXTURE = path.join(__dirname, 'fixtures/browser-equivalence-v2.json');
const FIXTURE = path.join(__dirname, 'fixtures/browser-equivalence-v3.json');
const ORIGINAL_FIXTURE_SHA256 = '980d62fc9fe22a061c7fda35520049a8144f2feab6fc803eaf8f562bb3c53a41';
const PRIOR_FIXTURE_SHA256 = '1a596ee8b07949eed9d07d499e20d985e05d58fbd02998fcd10d5c440027f454';
const FIXTURE_SHA256 = 'fd9910e1065c9f057c3e5ee0657cfdc3f03653c636e2ba97b6e49416932fbac4';
const OPTIONS = Object.freeze({ requestedWindow: 6, alpha: 0.1, minAbsDeltaA: 0.05,
  maximumStaleDays: 36500, maximumGapFactor: 3, orbitProfile: 'auto', detectorMode: 'multivariate' });

function hash(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}
function canonical(value) {
  const decoded = JSON.parse(JSON.stringify(value));
  function sorted(item) {
    if (Array.isArray(item)) return item.map(sorted);
    if (item && typeof item === 'object') return Object.fromEntries(Object.keys(item).sort().map(key => [key, sorted(item[key])]));
    return item;
  }
  return JSON.stringify(sorted(decoded));
}
function createContext(root) {
  const defaults = { win: '6', alpha: '0.1', dath: '0.05', stale: '36500', gapWarn: '3',
    orbitProfile: 'auto', detectorMode: 'multivariate', sensitivity: 'balanced', importMode: 'replace' };
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { value: defaults[id] || '', textContent: '', innerHTML: '',
      disabled: false, style: {}, classList: { add() {}, remove() {}, contains() { return false; } } });
    return elements.get(id);
  };
  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : [CLOCK])); }
    static now() { return Date.parse(CLOCK); }
  }
  const document = { getElementById: element };
  const window = { document, satellite: null };
  const context = { window, document, Date: FixedDate, console, URL, URLSearchParams,
    Math, Number, String, Array, Object, Set, Map, BigInt, JSON, RegExp, Error, TypeError, Promise,
    Blob, AbortController, fetch: async () => { throw new Error('Network disabled in equivalence fixtures.'); } };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root, 'satellite-6.0.2.min.js'), 'utf8'), context,
    { filename: 'satellite-6.0.2.min.js' });
  context.window.satellite = context.satellite;
  return context;
}

function captureSnapshot(root = process.cwd(), comparisonVersion = null) {
  const context = createContext(root);
  // Bind only the release identity to an older version in this isolated test
  // context. This lets complete numerical/export hashes be compared with both
  // preserved prior oracles, without modifying production source or fixtures.
  const configureModules = comparisonVersion === null ? null : modules => {
    const original = modules.common;
    modules.common = () => Object.freeze({ ...original(), WORKBENCH_VERSION: comparisonVersion });
  };
  const api = loadBrowserApp(context, { root, start: false, configureModules });
  const functions = Object.fromEntries(Object.entries(api)
    .filter(([name, value]) => typeof value === 'function' && name !== 'start')
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, value]) => [name, hash(Function.prototype.toString.call(value))]));
  const constants = Object.fromEntries(Object.entries(api).filter(([name]) => /^[A-Z][A-Z_0-9]*$/.test(name))
    .sort(([a], [b]) => a.localeCompare(b)).map(([name, value]) => [name, hash(canonical(value))]));
  const cases = {};
  for (const name of ['leo', 'geo', 'quiet', 'sparse', 'radial', 'cross', 'finite']) {
    const raw = api.exampleTles(name);
    const parsed = api.parseInput(raw);
    assert.equal(parsed.rejectedCount, 0);
    const analysis = api.analyzeRaw(raw, `synthetic equivalence ${name}`, OPTIONS);
    assert.equal(analysis.error, false);
    analysis.analysisOptions = api.getAnalysisOptions(OPTIONS);
    const result = api.buildMachineReadableResult(analysis, true);
    const decoded = api.decodeSavedPackage(JSON.stringify(result), 'replace');
    assert(decoded && !decoded.missingTleSource && !decoded.legacySchema);
    const reopened = api.analyzeRaw(decoded.input, analysis.sourceLabel, decoded.options);
    assert.equal(reopened.runId, analysis.runId);
    cases[name] = {
      raw_sha256: hash(raw), normalized_input_sha256: hash(api.serialiseRecordsAsOmm(parsed.records)),
      analysis_sha256: hash(canonical(analysis)), result_sha256: hash(canonical(result)),
      downloads_sha256: hash(canonical(api.buildAnalysisDownloadPayloads(analysis))),
      reopened_result_sha256: hash(canonical(api.buildMachineReadableResult(reopened, true))),
      reopened_settings_sha256: hash(canonical(decoded.options)),
      run_id: analysis.runId, records: analysis.n, evaluated_points: analysis.totalEvaluated,
      events: analysis.events.length, flags: analysis.flags.length, classification: analysis.classification,
    };
  }
  const epoch = context.Date.parse('2026-01-01T00:00:00Z');
  const time = hours => new context.Date(epoch + hours * 3600000);
  const predictions = [4, -5].map(hours => ({ start: time(hours), end: time(hours), strongest: { t: time(hours) } }));
  const truth = [0, 10].map(hours => ({ start: time(hours).toISOString(), end: time(hours).toISOString() }));
  const matching = JSON.parse(canonical(api.matchBenchmarkEvents(predictions, truth, 6)));
  const invalid = ['', 'invalid orbital input', '{broken json'].map(raw => JSON.parse(canonical(api.analyzeRaw(raw, 'synthetic invalid', OPTIONS))));
  return { functions, constants, cases, matching, invalid };
}

function main() {
  const originalBytes = fs.readFileSync(ORIGINAL_FIXTURE);
  assert.equal(hash(originalBytes), ORIGINAL_FIXTURE_SHA256, 'The original refactor oracle must remain unchanged.');
  const original = JSON.parse(originalBytes);
  assert.equal(original.schema, 'smd-browser-equivalence-v1');
  assert.equal(original.source_commit, '0e3304b0f42c0097da2e8c4156fceb1cf33bdb9c');
  const priorBytes = fs.readFileSync(PRIOR_FIXTURE);
  assert.equal(hash(priorBytes), PRIOR_FIXTURE_SHA256, 'The reviewed catalogue-identity oracle must remain unchanged.');
  const prior = JSON.parse(priorBytes);
  assert.equal(prior.schema, 'smd-browser-equivalence-v2');
  assert.equal(prior.source_commit, '9962713fcf349f74e613d8d68dc6b0becc42069f');
  assert.equal(prior.prior_oracle_sha256, ORIGINAL_FIXTURE_SHA256);
  const bytes = fs.readFileSync(FIXTURE);
  assert.equal(hash(bytes), FIXTURE_SHA256, 'The reviewed deterministic-admission oracle must remain unchanged.');
  const fixture = JSON.parse(bytes);
  assert.equal(fixture.schema, 'smd-browser-equivalence-v3');
  assert.equal(fixture.clock, CLOCK);
  assert.equal(fixture.baseline_commit, 'c1a2efb7aceae4cbf5ee7ca96b447f430dffd43c');
  assert.equal(fixture.workbench_version, '3.4.9');
  assert.equal(fixture.prior_oracle_sha256, PRIOR_FIXTURE_SHA256);
  assert.deepEqual(fixture.source_files_sha256, Object.fromEntries(sourceFiles()
    .map(name => [name, hash(fs.readFileSync(name))])), 'The maintenance oracle must identify its actual production source.');
  const actual = captureSnapshot();
  assert.deepEqual(actual, fixture.expected, 'Current browser module behaviour diverged from reviewed release.');
  assert.deepEqual(Object.keys(actual.functions), Object.keys(prior.expected.functions));
  const maintained = new Set(['resolveCatalogueRevisions', 'normaliseBenchmarkDefinition', 'compareCatalogueIdentifier']);
  for (const [name, digest] of Object.entries(prior.expected.functions)) {
    if (!maintained.has(name)) assert.equal(actual.functions[name], digest, 'Unexpected function change since 3.4.8: ' + name);
  }
  for (const [name, digest] of Object.entries(original.expected.functions)) {
    if (!maintained.has(name) && !['parseTlePair', 'parseOmmRecord'].includes(name)) {
      assert.equal(actual.functions[name], digest, 'Unexpected scientific function change: ' + name);
    }
  }
  for (const baseline of [original, prior]) {
    for (const [name, digest] of Object.entries(baseline.expected.constants)) {
      if (name !== 'WORKBENCH_VERSION') {
        assert.equal(actual.constants[name], digest, 'Unexpected scientific constant change: ' + name);
      }
    }
    assert.deepEqual(actual.matching, baseline.expected.matching, 'Event matching changed during input repair.');
    assert.deepEqual(actual.invalid, baseline.expected.invalid, 'Invalid-input decisions changed unexpectedly.');
  }
  for (const [version, baseline] of [['3.4.7', original], ['3.4.8', prior]]) {
    const comparable = captureSnapshot(process.cwd(), version);
    assert.deepEqual(comparable.cases, baseline.expected.cases,
      'Complete numerical analyses, exports or reopened results changed beyond release identity: ' + version);
  }
  const source = readBrowserSource();
  const declared = [...source.matchAll(/^  (?:async )?function ([A-Za-z_$][\w$]*)\(/gm)].map(match => match[1]);
  for (const name of Object.keys(fixture.expected.functions)) {
    assert.equal(declared.filter(item => item === name).length, 1, `Original definition must be unique: ${name}`);
  }
  assert.deepEqual(declared.filter(name => !Object.hasOwn(fixture.expected.functions, name)).sort(),
    sourceFiles().length === 1 ? [] : ['canonicalCatalogId', 'loadModule', 'moduleReady', 'reportLoadFailure', 'start', 'startApplication'], 'Unknown application functions need explicit review.');
  console.log(`Browser module equivalence passed: ${Object.keys(actual.functions).length} runtime functions, ${Object.keys(actual.constants).length} constants, seven complete analyses/export/reopen paths against both preserved prior oracles.`);
}

module.exports = { captureSnapshot, CLOCK };
if (require.main === module) main();
