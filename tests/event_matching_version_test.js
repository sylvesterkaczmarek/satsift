'use strict';

const { readBrowserSource } = require('../tools/load_browser_app');

const assert = require('assert');
const crypto = require('crypto');

const source = readBrowserSource();
const DEFINITIONS = [
  'parseOmmEpochUtc', 'recordEpochUs', 'formatEpochUs',
  'normaliseBenchmarkDefinition', 'benchmarkTimestamp', 'benchmarkTruthInterval', 'benchmarkToleranceUs',
  'benchmarkPredictionInterval', 'matchEventIntervals', 'matchBenchmarkEvents', 'makeBenchmarkId'
];
// Keep reviewed pins when adding a new scoring version. Historical source and
// results are verified independently by historical_evaluator_test.py.
const REVIEWED_SCORING_SHA256 = Object.freeze({
  'event-matching-v2': 'eadf5da278ad08a80ca68b4d18ded4618e72759e9e39fe3504ab252b0b666744',
  'event-matching-v3': 'b4e453d29668ddbfdc6f28d4c1a3d70b0a0e5e3b3b381c1cc802d9d4438b4b27'
});
// Input admission has a separate Workbench release boundary. The matcher and
// timestamp arithmetic remain v3; retain its original full-surface fingerprint.
// The equivalence test independently compares all unchanged scoring bodies.
const REVIEWED_ADMISSION_SHA256 = Object.freeze({
  '3.4.9/event-matching-v3': '1708e27be17c3be442f0c0a2ab6d458a33caba48be9db4b0e33d435fc76d1b7a',
  '3.5.0/event-matching-v3': '1708e27be17c3be442f0c0a2ab6d458a33caba48be9db4b0e33d435fc76d1b7a'
});

function definition(text, name) {
  const start = text.indexOf('  function ' + name + '(');
  assert(start >= 0, 'Missing matching definition ' + name);
  const end = text.indexOf('\n  }\n', start);
  assert(end >= 0, 'Missing matching definition end ' + name);
  return text.slice(start, end + 4);
}

function fingerprint(text) {
  const definitions = DEFINITIONS.map(name => [name, definition(text, name)]);
  return crypto.createHash('sha256').update(JSON.stringify(definitions)).digest('hex');
}

function verify(text) {
  const match = text.match(/const EVENT_MATCHING_VERSION = '([^']+)';/);
  assert(match, 'The browser matcher must declare its scoring version.');
  const reviewedScoring = REVIEWED_SCORING_SHA256[match[1]];
  assert(reviewedScoring, 'Review and register a new scoring version before changing matching semantics.');
  const workbench = text.match(/const WORKBENCH_VERSION = '([^']+)';/);
  assert(workbench, 'The input-admission surface must declare its Workbench release.');
  const expected = REVIEWED_ADMISSION_SHA256[workbench[1] + '/' + match[1]] || reviewedScoring;
  assert.strictEqual(fingerprint(text), expected,
    'Matching changed under an existing scoring version. Review the change and retain earlier version pins.');
}

if (process.argv.includes('--fingerprint')) {
  console.log(fingerprint(source));
} else {
  verify(source);
  const mutations = [
    ['matchEventIntervals', 'signedDistance = 2n * strongest - truthStart - truthEnd', 'signedDistance = strongest - truthStart'],
    ['matchEventIntervals', 'end < truthStart - tolerance || start > truthEnd + tolerance', 'strongest < truthStart - tolerance || strongest > truthEnd + tolerance'],
    ['matchEventIntervals', 'first.times[index] < second.times[index]', 'first.times[index] > second.times[index]'],
    ['matchEventIntervals', 'next >= distances[edge.to]', 'next > distances[edge.to]'],
    ['matchEventIntervals', 'Number(candidate.prediction.times[0] - candidate.truth.times[0])', 'Number(candidate.prediction.times[2] - candidate.truth.times[0])'],
    ['benchmarkToleranceUs', 'numerator / (10n ** BigInt(scale))', 'numerator / (10n ** BigInt(scale)) + 1n'],
    ['benchmarkPredictionInterval', 'BigInt(recordEpochUs(record))', 'BigInt(record.t.getTime()) * 1000n'],
    ['parseOmmEpochUtc', "fraction.slice(3, 6).padEnd(3, '0')", "fraction.slice(3, 5).padEnd(3, '0')"],
    ['normaliseBenchmarkDefinition', 'start: interval.start.iso', 'start: truth.start'],
    ['normaliseBenchmarkDefinition', "Object.prototype.hasOwnProperty.call(decoded, 'matching_tolerance_hours')", 'true'],
    ['normaliseBenchmarkDefinition', "typeof toleranceHours !== 'number'", 'false'],
    ['normaliseBenchmarkDefinition', 'toleranceHours < 0 || toleranceHours > 168', 'toleranceHours < -1 || toleranceHours > 200'],
    ['benchmarkTimestamp', 'match[0].length !== value.length', 'false'],
    ['benchmarkTimestamp', 'year < 1 || month < 1', 'year < 0 || month < 1'],
    ['benchmarkTruthInterval', "Object.prototype.hasOwnProperty.call(truth, 'end') ? parseBoundary(truth.end, 'end') : start", "truth.end ? parseBoundary(truth.end, 'end') : start"],
    ['makeBenchmarkId', 'scoring_version: EVENT_MATCHING_VERSION,\n      definition', 'scoring_version: null,\n      definition']
  ];
  // Other features may reuse an expression. Mutate its reviewed definition.
  for (const [name, before, after] of mutations) {
    assert(DEFINITIONS.includes(name), 'Mutation must target a reviewed definition: ' + name);
    const original = definition(source, name);
    assert(original.includes(before), 'Mutation must target live code in ' + name + ': ' + before);
    assert.strictEqual(original.indexOf(before), original.lastIndexOf(before),
      'Mutation target must be unique within ' + name);
    const mutated = source.replace(original, original.replace(before, after));
    assert.throws(() => verify(mutated), assert.AssertionError);
  }
  assert.throws(() => verify(source.replace("EVENT_MATCHING_VERSION = 'event-matching-v3'", "EVENT_MATCHING_VERSION = 'unreviewed-version'")), assert.AssertionError);
  assert.throws(() => verify(source.replace("WORKBENCH_VERSION = '3.5.0'", "WORKBENCH_VERSION = '3.4.8'")), assert.AssertionError);
  console.log('Browser event-matching and versioned admission verified; ' + (mutations.length + 2) + ' mutation checks passed.');
}
