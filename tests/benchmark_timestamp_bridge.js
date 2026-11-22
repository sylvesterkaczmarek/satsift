'use strict';

const { loadBrowserApp } = require('../tools/load_browser_app');

// Synthetic truth-timestamp checks, driven by benchmark_timestamp_test.py.
const fs = require('fs');
const vm = require('vm');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: id === 'tles' ? 'retained orbital input' : '',
    textContent: '', innerHTML: '', disabled: false, style: { display: 'none' }
  });
  return elements.get(id);
}
const context = {
  Date, BigInt, Set, Map, console,
  window: { satellite: null },
  document: { getElementById: element }
};
vm.createContext(context);
loadBrowserApp(context, { start: false, hooks: `
  window.timestampApi = {
    benchmarkTimestamp, normaliseBenchmarkDefinition, matchBenchmarkEvents,
    makeBenchmarkId, importBenchmarkFile,
    seedPriorReport() {
      benchmarkDefinition = { name: 'prior benchmark' };
      lastBenchmarkReport = { benchmark_id: 'prior-report' };
    },
    state() { return { benchmarkDefinition, lastBenchmarkReport }; }
  };
` });
const api = context.window.timestampApi;

function attempt(operation) {
  try { return { accepted: true, value: operation() }; }
  catch (error) { return { accepted: false, error: error.message }; }
}
function definition(truthEvents, extra = {}) {
  return {
    schema: 'smd-event-benchmark-v1', matching_tolerance_hours: 0,
    cases: [{ case_id: 'timestamp-case', source: 'https://example.test/evidence',
      records: [{ NORAD_CAT_ID: 25544, EPOCH: '2026-01-01T00:00:00Z',
        MEAN_MOTION: 15.5, ECCENTRICITY: 0.001, INCLINATION: 51.6,
        RA_OF_ASC_NODE: 10, ARG_OF_PERICENTER: 20, MEAN_ANOMALY: 30 }],
      truth_events: truthEvents, ...extra }]
  };
}
function snapshot() {
  const state = api.state();
  return {
    has_definition: state.benchmarkDefinition !== null,
    has_report: state.lastBenchmarkReport !== null,
    run_disabled: element('runBenchmark').disabled,
    download_disabled: element('downloadBenchmarkReport').disabled,
    displays: ['benchmarkMetrics', 'benchmarkTableWrap', 'benchmarkProfileWrap']
      .map(id => element(id).style.display),
    tables: ['benchmarkTableBody', 'benchmarkProfileBody'].map(id => element(id).innerHTML),
    hint: element('benchmarkHint').textContent,
    input: element('benchmarkInput').value,
    orbital_input: element('tles').value
  };
}

async function main() {
  const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
  const results = {
    timestamps: payload.timestamps.map(item => attempt(() => {
      const parsed = api.benchmarkTimestamp(item.value);
      return { epoch_us: parsed.epochUs.toString(), iso: parsed.iso };
    })),
    intervals: payload.intervals.map(item => ({
      normalisation: attempt(() => api.normaliseBenchmarkDefinition(definition([item.truth])).cases[0].truthEvents[0]),
      direct_matching: attempt(() => api.matchBenchmarkEvents([], [item.truth], 0))
    })),
    collections: payload.collections.map(value => attempt(() =>
      api.normaliseBenchmarkDefinition(definition(value)).cases[0].truthEvents)),
    matching: [],
    javascript_only_timestamps: [undefined, new Date('2026-01-01T00:00:00Z'),
      new String('2026-01-01T00:00:00Z'), NaN, Infinity]
      .map(value => attempt(() => api.benchmarkTimestamp(value).iso)),
    javascript_only_end: attempt(() => api.normaliseBenchmarkDefinition(
      definition([{ start: '2026-01-01T00:00:00Z', end: undefined }]))),
    missing_collection: attempt(() => {
      const item = definition([]);
      delete item.cases[0].truth_events;
      return api.normaliseBenchmarkDefinition(item).cases[0].truthEvents;
    })
  };
  for (const fixture of payload.matching) {
    const records = [];
    const predictions = fixture.predictions.map(item => {
      const offset = records.length;
      const values = [item.start_utc, item.end_utc, item.strongest_utc];
      values.forEach(value => records.push({
        t: new Date(value), epochUs: Number(api.benchmarkTimestamp(value).epochUs)
      }));
      return {
        start: records[offset].t, end: records[offset + 1].t,
        flags: [{ idx: offset }, { idx: offset + 1 }],
        strongest: { idx: offset + 2, t: records[offset + 2].t }
      };
    });
    const decoded = definition(fixture.truth);
    const normalised = api.normaliseBenchmarkDefinition(decoded);
    const matched = api.matchBenchmarkEvents(predictions, normalised.cases[0].truthEvents,
      fixture.tolerance_hours, records);
    results.matching.push({
      matches: matched.matches.map(pair => ({
        prediction_index: pair.predictionIndex, truth_index: pair.truthIndex,
        delay_hours: pair.delayHours, strongest_point_delay_hours: pair.strongestPointDelayHours
      })),
      truth: normalised.cases[0].truthEvents,
      benchmark_id: api.makeBenchmarkId(decoded, { matching_tolerance_hours: fixture.tolerance_hours })
    });
  }

  const invalid = definition([
    { start: '2026-01-01T00:00:00Z' },
    { start: '2026-01-02T00:00:00Z', end: '2026-02-30T00:00:00Z' }
  ]);
  api.seedPriorReport();
  ['benchmarkMetrics', 'benchmarkTableWrap', 'benchmarkProfileWrap']
    .forEach(id => { element(id).style.display = 'block'; });
  ['benchmarkTableBody', 'benchmarkProfileBody']
    .forEach(id => { element(id).innerHTML = 'stale report'; });
  element('benchmarkInput').value = 'selected.json';
  await api.importBenchmarkFile({
    name: 'invalid-timestamp.json', size: 300, text: async () => JSON.stringify(invalid)
  });
  results.rejected_import = snapshot();

  await api.importBenchmarkFile({
    name: 'valid-timestamp.json', size: 200,
    text: async () => JSON.stringify(definition([{ start: '2026-01-01T01:00:00.000001+01:00' }]))
  });
  results.recovered_import = snapshot();
  results.recovered_truth = api.state().benchmarkDefinition.cases[0].truthEvents;
  process.stdout.write(JSON.stringify(results));
}
main().catch(error => { console.error(error.stack || error); process.exitCode = 1; });
