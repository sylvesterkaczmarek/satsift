'use strict';

const { readBrowserSource, loadBrowserApp } = require('../tools/load_browser_app');

const vm = require('vm');

const source = readBrowserSource();
const context = { window: {} };
vm.createContext(context);
context.fn = loadBrowserApp(context, { start: false }).normaliseBenchmarkLabelStatus;

if (context.fn('', 1) !== 'event-evidence') throw new Error('Positive evidence must default conservatively to event-evidence.');
if (context.fn('', 0) !== 'unknown') throw new Error('Unlabelled zero-event periods must default to unknown.');
if (context.fn('confirmed-quiet', 0) !== 'confirmed-quiet') throw new Error('Confirmed quiet coverage was rejected.');
if (context.fn('verified-quiet', 0) !== 'confirmed-quiet') throw new Error('Publication verified-quiet coverage was not translated to the canonical browser status.');
if (context.fn('fully-labelled', 2) !== 'fully-labelled') throw new Error('Fully labelled coverage was rejected.');

let failed = false;
try { context.fn('event-evidence', 0); } catch (_) { failed = true; }
if (!failed) throw new Error('Event-evidence without a documented event must fail validation.');

failed = false;
try { context.fn('confirmed-quiet', 1); } catch (_) { failed = true; }
if (!failed) throw new Error('Confirmed-quiet coverage containing truth events must fail validation.');

if (!source.includes('const precision = negativeLabelObjectMonths > 0')) {
  throw new Error('Precision must remain unavailable without qualified negative-labelled coverage.');
}
if (!source.includes('unverified_prediction_count')) {
  throw new Error('Unmatched predictions in incomplete coverage must be reported as unverified.');
}
if (!source.includes("label_status: item.labelStatus")) {
  throw new Error('Benchmark report must preserve label status per case.');
}
if (!source.includes("const positiveScored = item.labelStatus === 'event-evidence' || item.labelStatus === 'fully-labelled';")) {
  throw new Error('Documented event evidence must remain the only positive-scored browser coverage.');
}
if (!source.includes("const negativeScored = item.labelStatus === 'confirmed-quiet' || item.labelStatus === 'fully-labelled';")) {
  throw new Error('Only confirmed quiet or fully labelled coverage may score browser false positives.');
}
if (!source.includes("caseUnverifiedPredictions = rawMatch.falsePositives;")) {
  throw new Error('Unmatched predictions in event-evidence histories must remain unverified, not false positives.');
}

const matchingContext = { Date, Set, BigInt, window: {} };
vm.createContext(matchingContext);
matchingContext.fn = loadBrowserApp(matchingContext, { start: false }).matchBenchmarkEvents;
const predicted = [{
  start: new Date('2026-01-10T00:00:00Z'),
  end: new Date('2026-01-10T06:00:00Z'),
  strongest: { t: new Date('2026-01-10T02:00:00Z') }
}];
const truth = [{ start: '2026-01-10T00:00:00Z', end: '2026-01-10T04:00:00Z' }];
const matched = matchingContext.fn(predicted, truth, 24);
if (matched.truePositives !== 1 || matched.falseNegatives !== 0) throw new Error('Strongest-point event matching changed.');
if (matched.matches[0].distanceMs !== 0) throw new Error('Matching must still use the strongest point against the truth midpoint.');
if (matched.matches[0].delayHours !== 0) throw new Error('Detection delay must use event onset/first alarm.');
if (matched.matches[0].strongestPointDelayHours !== 2) throw new Error('Strongest-point diagnostic delay was not preserved.');

const assignment = matchingContext.fn([
  { start: new Date('2026-01-10T10:00:00Z'), end: new Date('2026-01-10T20:00:00Z'), strongest: { t: new Date('2026-01-10T20:00:00Z') } },
  { start: new Date('2026-01-10T00:00:00Z'), end: new Date('2026-01-10T20:00:00Z'), strongest: { t: new Date('2026-01-10T10:00:00Z') } }
], [
  { start: '2026-01-10T10:00:00Z', end: '2026-01-10T10:00:00Z' },
  { start: '2026-01-10T20:00:00Z', end: '2026-01-10T20:00:00Z' }
], 24);
const assignmentPairs = assignment.matches.map(item => `${item.predictionIndex}:${item.truthIndex}`).sort().join(',');
if (assignmentPairs !== '0:1,1:0') throw new Error('One-to-one assignment must be ordered by strongest-point distance, not event onset.');

console.log('Benchmark label semantics tests passed.');
