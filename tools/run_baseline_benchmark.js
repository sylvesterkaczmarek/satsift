'use strict';

const { loadBrowserApp } = require('./load_browser_app');

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
    const defaults = {
      win: '6', alpha: '0.10', dath: '0.05', stale: '36500', gapWarn: '3',
      orbitProfile: 'auto', detectorMode: 'multivariate', sensitivity: 'balanced',
      demoSelect: 'leo', importMode: 'replace', publicNorad: '', historyStart: '', historyEnd: '', tles: ''
    };
    elements.set(id, {
      id,
      value: Object.prototype.hasOwnProperty.call(defaults, id) ? defaults[id] : '',
      textContent: '', innerHTML: '', className: '', hidden: false, disabled: false,
      open: false, max: '', files: [], style: {}, classList: makeClassList(), handlers,
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
  window: windowObject, document, navigator: { clipboard: null }, console,
  URL, URLSearchParams, Date, Math, Number, String, Array, Object, Set, Map, BigInt,
  JSON, RegExp, Error, TypeError, Promise, Blob: globalThis.Blob,
  AbortController: globalThis.AbortController,
  fetch: async () => { throw new Error('Network disabled in baseline benchmark harness.'); }
};
context.globalThis = context;
context.self = windowObject;
vm.createContext(context);

vm.runInContext(fs.readFileSync('satellite-6.0.2.min.js', 'utf8'), context, { filename: 'satellite-6.0.2.min.js' });
if (!windowObject.satellite && context.satellite) windowObject.satellite = context.satellite;
if (!windowObject.satellite) throw new Error('satellite.js did not initialise.');

const api = loadBrowserApp(context);
if (!api || typeof api.analyzeRaw !== 'function') throw new Error('Failed to expose analyzeRaw.');

const benchmarkPath = process.argv[2] || 'benchmark-data/public-evidence-benchmark-v0.3.json';
const outputPath = process.argv[3] || 'benchmark-results/baseline-v0.4-on-v0.3.json';
const featuresPath = process.argv[4] || 'benchmark-results/features-v0.4-on-v0.3.json';
const benchmark = JSON.parse(fs.readFileSync(benchmarkPath, 'utf8'));

const settings = {
  requestedWindow: 6,
  alpha: 0.10,
  minAbsDeltaA: 0.05,
  maximumStaleDays: 36500,
  maximumGapFactor: 3,
  orbitProfile: 'auto',
  detectorMode: 'multivariate'
};

function finite(value) { return Number.isFinite(Number(value)); }
function safeLog1p(value) { return Math.log1p(Math.max(0, Number(value))); }
function researchRow(caseItem, analysis, row) {
  const record = row.record;
  if (!record || !record.elements || !row.featureValues || !finite(row.dt) || row.dt <= 0) return null;
  const map = {
    a_rate: row.featureValues.aRate,
    mean_motion_rate: row.featureValues.meanMotionRate,
    radial_rate: row.featureValues.radialRate,
    along_rate: row.featureValues.alongRate,
    cross_rate: row.featureValues.crossRate,
    eccentricity_vector_rate: row.featureValues.eccentricityVectorRate,
    inclination_vector_rate: row.featureValues.inclinationVectorRate,
    bstar_rate: row.featureValues.bstarRate
  };
  if (!Object.values(map).every(finite)) return null;
  const incRadians = Number(record.elements.incDeg) * Math.PI / 180;
  return {
    case_id: caseItem.case_id,
    object_id: String(caseItem.object_id),
    orbit_profile: caseItem.orbit_profile || analysis.profileName || 'AUTO',
    split: caseItem.split,
    label_status: caseItem.label_status,
    label_confidence: caseItem.label_confidence,
    nominal: caseItem.label_status === 'verified-quiet',
    quality_ok: !analysis.error && analysis.hardQualityErrors.length === 0,
    index: row.index,
    epoch_utc: row.t.toISOString(),
    context: {
      log_gap_days: safeLog1p(row.dt),
      log_semi_major_axis_km: safeLog1p(row.a),
      eccentricity: Number(record.elements.ecc),
      inclination_sin: Math.sin(incRadians),
      log_abs_bstar: Math.log1p(Math.abs(Number(record.bstar || 0)))
    },
    features: Object.fromEntries(Object.entries(map).map(([key, value]) => [key, Number(value)]))
  };
}

const caseResults = [];
const featureRows = [];
for (const item of benchmark.cases || []) {
  const raw = JSON.stringify(item.records || []);
  const overrides = { ...settings, orbitProfile: item.orbit_profile || 'auto' };
  const analysis = api.analyzeRaw(raw, 'frozen public-evidence benchmark', overrides);
  const predicted = !analysis.error && analysis.interpretable ? analysis.events : [];
  caseResults.push({
    case_id: item.case_id,
    object_id: String(item.object_id),
    split: item.split,
    label_status: item.label_status,
    label_confidence: item.label_confidence,
    orbit_profile: item.orbit_profile,
    source: item.source,
    span_days: analysis.error ? 0 : analysis.spanDays,
    abstained: Boolean(analysis.error || !analysis.interpretable),
    classification: analysis.error ? 'Input error' : analysis.classification,
    quality_status: analysis.error ? 'unusable' : analysis.qualityStatus,
    run_id: analysis.error ? null : analysis.runId,
    truth_events: item.truth_events || [],
    predicted_events: predicted.map(event => ({
      event_id: event.id,
      start_utc: event.start.toISOString(),
      end_utc: event.end.toISOString(),
      strongest_utc: event.strongest.t.toISOString(),
      tier: event.tier,
      score: event.score,
      net_delta_a_km: event.netDeltaA,
      supporting_features: event.features
    }))
  });
  if (!analysis.error) {
    for (const row of analysis.rows) {
      const converted = researchRow(item, analysis, row);
      if (converted) featureRows.push(converted);
    }
  }
}

fs.mkdirSync(require('path').dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, JSON.stringify({
  schema: 'smd-baseline-benchmark-results-v1',
  detector_method: 'v0.4',
  benchmark_version: benchmark.benchmark_version,
  matching_tolerance_hours: benchmark.matching_tolerance_hours,
  settings,
  cases: caseResults
}, null, 2) + '\n');

fs.mkdirSync(require('path').dirname(featuresPath), { recursive: true });
fs.writeFileSync(featuresPath, JSON.stringify({
  schema: 'smd-research-features-v1',
  source_detector_method: 'v0.4',
  benchmark_version: benchmark.benchmark_version,
  settings,
  rows: featureRows
}, null, 2) + '\n');

console.log(`Wrote ${caseResults.length} baseline case result(s) to ${outputPath}.`);
console.log(`Wrote ${featureRows.length} research feature row(s) to ${featuresPath}.`);
