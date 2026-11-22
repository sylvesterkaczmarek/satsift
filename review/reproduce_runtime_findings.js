'use strict';

const { loadBrowserApp } = require('../tools/load_browser_app');

// Read-only diagnostic for the app at 715e2e60390eb2bc8df36f6fb8d136f20805d2e1.
// Usage: node code_review_reproducers.js PATH_TO_REPOSITORY_OR_SNAPSHOT
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { spawnSync } = require('child_process');
const sourceRoot = path.resolve(process.argv[2] || path.join(__dirname, 'code-review-snapshot'));
const defaults = { win: '6', alpha: '0.1', dath: '0.05', stale: '36500', gapWarn: '3', orbitProfile: 'auto', detectorMode: 'multivariate' };
const context = { console, Date, Math, Number, String, Array, Object, Set, Map, BigInt, JSON, window: {}, document: { getElementById: id => ({ value: defaults[id] || '' }) } };
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(sourceRoot, 'satellite-6.0.2.min.js'), 'utf8'), context);
context.window.satellite = context.satellite;
const api = loadBrowserApp(context, { root: sourceRoot, start: false });
const omm = { NORAD_CAT_ID: 25544, EPOCH: '2026-07-06T02:08:05.621280Z', MEAN_MOTION: 15.5, ECCENTRICITY: 0.0005, INCLINATION: 51.64, RA_OF_ASC_NODE: 85, ARG_OF_PERICENTER: 96, MEAN_ANOMALY: 50 };

if (process.argv[3] === 'timezone') {
  const benchmark = { schema: 'smd-event-benchmark-v1', cases: [{ case_id: 'one', source: 'diagnostic fixture', records: [omm], truth_events: [{ start: '2026-07-06T00:00:00', end: '2026-07-06T01:00:00' }] }] };
  try {
    console.log(JSON.stringify({ accepted: true, truth: api.normaliseBenchmarkDefinition(benchmark).cases[0].truthEvents[0] }));
  } catch (error) {
    console.log(JSON.stringify({ accepted: false, reason: error.message }));
  }
  process.exit(0);
}

// 1. Exporting absent metadata invents known ELEMENT_SET_NO=999.
const base = api.parseInput(JSON.stringify([omm])).records[0];
const reopened = api.parseInput(api.serialiseRecordsAsOmm([base])).records[0];
const corrected = api.parseInput(JSON.stringify([{ ...omm, ELEMENT_SET_NO: 10, MEAN_MOTION: 15.6 }])).records[0];
const originalWinner = api.resolveCatalogueRevisions([base, corrected]).records[0];
const reopenedWinner = api.resolveCatalogueRevisions([reopened, corrected]).records[0];
console.log(JSON.stringify({ finding: 'Catalogue metadata changes on normalisation', original_known: base.elementSetNoKnown, reopened_known: reopened.elementSetNoKnown, original_winner_mean_motion: originalWinner.meanMotion, reopened_winner_mean_motion: reopenedWinner.meanMotion, expected_winner_mean_motion: 15.6 }, null, 2));

// 2. TLE precision loss changes SGP4 output while preserving the run identifier.
const raw = api.exampleTles('leo').split('\n').map(line => line.startsWith('1 ') ? api.addTleChecksum(line.slice(0, 31) + '1' + line.slice(32, 68)) : line).join('\n');
const originalAnalysis = api.analyzeRaw(raw, 'original diagnostic fixture');
const reopenedAnalysis = api.analyzeRaw(api.serialiseRecordsAsOmm(originalAnalysis.records), 'reopened diagnostic fixture');
console.log(JSON.stringify({ finding: 'TLE round trip changes residuals under the same run ID', original_run_id: originalAnalysis.runId, reopened_run_id: reopenedAnalysis.runId, original_julian_epoch: api.satrecForRecord(originalAnalysis.records[0]).jdsatepoch, reopened_julian_epoch: api.satrecForRecord(reopenedAnalysis.records[0]).jdsatepoch, maximum_residual_difference_metres: 1000 * Math.max(...originalAnalysis.rows.slice(1).map((row, index) => Math.abs(row.stateResidualKm - reopenedAnalysis.rows[index + 1].stateResidualKm))) }, null, 2));

// 3. Greedy event matching loses one valid match.
const epoch = Date.parse('2026-01-01T00:00:00Z');
const time = hours => new Date(epoch + hours * 3600000);
const predictions = [4, -5].map(hours => ({ start: time(hours), end: time(hours), strongest: { t: time(hours) } }));
const truth = [0, 10].map(hours => ({ start: time(hours).toISOString(), end: time(hours).toISOString() }));
console.log(JSON.stringify({ finding: 'Greedy matching loses a valid detection', observed: api.matchBenchmarkEvents(predictions, truth, 6), expected_true_positives: 2, valid_assignment: ['prediction at -5h to truth at 0h', 'prediction at 4h to truth at 10h'] }, null, 2));

// 4. Accepted truth intervals depend on the operator's local timezone.
for (const timezone of ['UTC', 'America/New_York']) {
  const result = spawnSync(process.execPath, [__filename, sourceRoot, 'timezone'], { env: { ...process.env, TZ: timezone }, encoding: 'utf8' });
  if (result.status !== 0) throw new Error(result.stderr || 'Timezone subprocess failed.');
  console.log(JSON.stringify({ finding: 'Benchmark truth timezone drift', timezone, normalised_truth: JSON.parse(result.stdout) }, null, 2));
}
