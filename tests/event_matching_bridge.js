'use strict';

const { readBrowserSource, loadBrowserApp } = require('../tools/load_browser_app');

// Invoked by event_matching_test.py with synthetic cases on standard input.
const fs = require('fs');
const vm = require('vm');
const source = readBrowserSource();

function constantValue(name) {
  const found = source.match(new RegExp(`const ${name} = (['"])(.*?)\\1;`));
  if (!found) throw new Error(`Missing ${name}`);
  return found[2];
}

const methodVersion = constantValue('METHOD_VERSION');
const scoringVersion = constantValue('EVENT_MATCHING_VERSION');
function createContext(scoring = scoringVersion) {
  const elements = new Map();
  const context = {
    Date, Set, BigInt, window: { satellite: null },
    syntheticAnalysis: null,
    byId: id => {
      if (!elements.has(id)) elements.set(id, { disabled: false, textContent: '', value: '', style: {} });
      return elements.get(id);
    },
  };
  context.document = { getElementById: context.byId };
  vm.createContext(context);
  const production = loadBrowserApp(context, {
    start: false,
    configureModules(registry) {
      const common = registry.common;
      registry.common = () => ({ ...common(), EVENT_MATCHING_VERSION: scoring });
      const orbital = registry['orbital-input'];
      registry['orbital-input'] = (...args) => ({ ...orbital(...args),
        parseInput: () => ({ records: context.syntheticAnalysis ? context.syntheticAnalysis.records : [{}] }) });
      const benchmark = registry.benchmark;
      registry.benchmark = (...args) => ({ ...benchmark(...args),
        deterministicThinBenchmarkRaw: () => 'synthetically thinned records' });
      const detection = registry.detection;
      registry.detection = (...args) => ({ ...detection(...args), analyzeRaw: () => context.syntheticAnalysis });
    },
    hooks: `
      getAnalysisOptions = () => ({ requestedWindow: 3, alpha: 0.05, minAbsDeltaA: 0.01,
        maximumStaleDays: 7, maximumGapFactor: 4, orbitProfile: 'AUTO', detectorMode: 'v0.4' });
      renderBenchmarkReport = () => {};
      Object.defineProperties(globalThis, {
        benchmarkDefinition: { get: () => benchmarkDefinition, set: value => { benchmarkDefinition = value; } },
        lastBenchmarkReport: { get: () => lastBenchmarkReport, set: value => { lastBenchmarkReport = value; } }
      });
    `,
  });
  return { ...production, state: context };
}

function normaliseMatch(item) {
  return {
    prediction_index: item.predictionIndex,
    truth_index: item.truthIndex,
    distance_twice_us: item.distanceTwiceUs.toString(),
    delay_hours: item.delayHours,
    strongest_point_delay_hours: item.strongestPointDelayHours
  };
}

const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const api = createContext();
const results = {
  cases: payload.cases.map(item => api.matchEventIntervals(
    item.predictions.map(interval => interval.map(BigInt)),
    item.truth.map(interval => interval.map(BigInt)),
    BigInt(item.tolerance_us)
  ).map(normaliseMatch)),
  wrapper_cases: [],
  validation: [],
  tolerance: []
};

for (const item of payload.wrapper_cases || []) {
  const records = [];
  const predictions = item.predictions.map(prediction => {
    const start = new Date(prediction.start_utc);
    const end = new Date(prediction.end_utc);
    const strongest = new Date(prediction.strongest_utc);
    const offset = records.length;
    records.push(
      { t: start, epochUs: Number(api.benchmarkTimestamp(prediction.start_utc).epochUs) },
      { t: end, epochUs: Number(api.benchmarkTimestamp(prediction.end_utc).epochUs) },
      { t: strongest, epochUs: Number(api.benchmarkTimestamp(prediction.strongest_utc).epochUs) }
    );
    return {
      start, end, flags: [{ idx: offset, t: start }, { idx: offset + 1, t: end }],
      strongest: { t: strongest, idx: offset + 2 }
    };
  });
  const definition = api.normaliseBenchmarkDefinition({
    schema: 'smd-event-benchmark-v1', matching_tolerance_hours: item.tolerance_hours,
    cases: [{
      case_id: 'synthetic', source: 'https://example.test/event-evidence',
      records: [{}], truth_events: item.truth
    }]
  });
  const normalisedTruth = definition.cases[0].truthEvents;
  const matched = api.matchBenchmarkEvents(
    predictions, normalisedTruth, item.tolerance_hours, item.use_records === false ? [] : records);
  if (item.name === 'same-millisecond-distinct') {
    api.state.benchmarkDefinition = definition;
    api.state.syntheticAnalysis = {
      error: false, interpretable: true, events: predictions, records,
      spanDays: 1, profileName: 'LEO', objectId: 'synthetic',
      classification: 'Synthetic event candidates', runId: 'synthetic-run', qualityStatus: 'usable'
    };
    api.runBenchmark();
    if (!api.state.lastBenchmarkReport) {
      throw new Error(api.state.byId('benchmarkHint').textContent);
    }
    results.report = api.state.lastBenchmarkReport;
    results.report_expected_id = api.makeBenchmarkId(definition.original, results.report.settings);
  }
  results.wrapper_cases.push({
    name: item.name, true_positives: matched.truePositives,
    false_positives: matched.falsePositives, false_negatives: matched.falseNegatives,
    matches: matched.matches.map(value => ({
      prediction_index: value.predictionIndex, truth_index: value.truthIndex,
      distance_ms: value.distanceMs, delay_hours: value.delayHours,
      strongest_point_delay_hours: value.strongestPointDelayHours
    })),
    normalised_truth: normalisedTruth
  });
}

const invalidCases = [
  [[[0n, 0n, 0n]], [[0n, 0n]], -1n],
  [[[0n, 0n, 0n]], [[0n, 0n]], 0.5],
  [[[0n, 0n, 0n]], [[0n, 0n]], true],
  [[[0.5, 1n, 1n]], [[0n, 1n]], 0n],
  [[[0n, 1n, false]], [[0n, 1n]], 0n],
  [[[2n, 1n, 1n]], [[0n, 1n]], 0n],
  [[[0n, 1n, 1n]], [[2n, 1n]], 0n],
  [[[Number.MAX_SAFE_INTEGER + 1, 10n ** 18n, 10n ** 18n]], [[0n, 1n]], 0n]
];
for (const args of invalidCases) {
  let rejected = false;
  try { api.matchEventIntervals(...args); } catch (_) { rejected = true; }
  results.validation.push(rejected);
}
for (const value of [0, 0.1, 24, 1e-10, 3.333333333333333e-10, 1.6666666666666667e-9]) {
  results.tolerance.push({ hours: value, microseconds: api.benchmarkToleranceUs(value).toString() });
}
results.invalid_tolerance = [-1, NaN, Infinity, -Infinity].map(value => {
  try { api.benchmarkToleranceUs(value); return false; } catch (_) { return true; }
});

if (payload.identity) {
  const definition = { schema: 'smd-event-benchmark-v1', cases: [], matching_tolerance_hours: 24 };
  const settings = { detector_method: methodVersion, threshold: 1.3 };
  const changed = createContext('event-matching-test-change');
  const schema = source.match(/schema: '(smd-event-benchmark-report-v\d+)'/);
  if (!schema) throw new Error('Missing benchmark report schema.');
  results.identity = {
    scoring_version: scoringVersion, schema: schema[1],
    current: api.makeBenchmarkId(definition, settings),
    repeated: api.makeBenchmarkId(definition, settings),
    changed_scoring: changed.makeBenchmarkId(definition, settings),
    legacy: 'smb-' + api.fnv1a64(api.stableStringify({ method: methodVersion, definition, settings }))
  };
}
process.stdout.write(JSON.stringify(results));
