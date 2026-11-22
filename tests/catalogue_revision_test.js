'use strict';

const { loadBrowserApp } = require('../tools/load_browser_app');

const vm = require('vm');

const document = { getElementById: () => ({ value: '' }) };
const context = { console, BigInt, Number, String, Math, Date, document, window: {} };
vm.createContext(context);
context.api = loadBrowserApp(context, { start: false });

function record(epochUs, meanMotion, creationUs, elementSetNo, gpId) {
  return {
    t: new Date(Math.floor(epochUs / 1000)),
    epochUs,
    epochRaw: new Date(Math.floor(epochUs / 1000)).toISOString(),
    meanMotion,
    bstar: 0,
    satId: '25544',
    sourceFormat: 'OMM JSON',
    creationUs: Number.isSafeInteger(creationUs) ? creationUs : null,
    creationRaw: Number.isSafeInteger(creationUs) ? new Date(Math.floor(creationUs / 1000)).toISOString() : '',
    elementSetNoKnown: Number.isFinite(elementSetNo),
    elementSetNo: Number.isFinite(elementSetNo) ? elementSetNo : 999,
    gpId: gpId || '',
    elements: {
      ecc: 0.001,
      incDeg: 51.6,
      raanDeg: 10,
      argPerDeg: 20,
      meanAnomDeg: 30
    }
  };
}

const base = 1700000000000000;

const resolved = context.api.resolveCatalogueRevisions([
  record(base, 15.5, base + 1000000, 100, '1000'),
  record(base + 864, 15.5002, base + 2000000, 101, '1001')
]);
if (resolved.records.length !== 1 || resolved.supersededRecords.length !== 1 || resolved.records[0].meanMotion !== 15.5002) {
  throw new Error('Near-simultaneous corrected OMM solution was not resolved deterministically.');
}

const ambiguous = context.api.resolveCatalogueRevisions([
  record(base, 15.5, null, NaN, ''),
  record(base + 500000, 15.5002, null, NaN, '')
]);
if (ambiguous.unresolvedNearSimultaneousCount !== 1 || ambiguous.records.length !== 2) {
  throw new Error('Ambiguous near-simultaneous solutions must remain visible and force abstention.');
}

const separated = context.api.resolveCatalogueRevisions([
  record(base, 15.5, base + 1000000, 100, '1000'),
  record(base + 2000000, 15.5002, base + 2000000, 101, '1001')
]);
if (separated.records.length !== 2 || separated.supersededRecords.length !== 0) {
  throw new Error('Records outside the one-second revision tolerance must remain independent.');
}

console.log('Catalogue revision regression tests passed.');

// Exact-epoch provenance must be resolved before neighbouring epochs are compared.
const assert = require('node:assert/strict');
function permutations(items) {
  if (items.length < 2) return [items.slice()];
  return items.flatMap((item, index) => permutations(items.filter((_, at) => at !== index))
    .map(rest => [item, ...rest]));
}
let permutationChecks = 0;
function resolutionSummary(records) {
  const result = context.api.resolveCatalogueRevisions(records);
  return JSON.parse(JSON.stringify({ ...result, records: result.records.map(context.api.recordToOmm) }));
}
function invariant(records, check) {
  let expected;
  for (const order of permutations(records)) {
    const result = resolutionSummary(order);
    check(result);
    if (expected) assert.deepEqual(result, expected, 'Catalogue result or audit depends on input permutation.');
    else expected = result;
    permutationChecks++;
  }
}
const earlyNative = record(base, 15.5002, null, NaN, '');
const laterNative = record(base + 500000, 15.5, null, NaN, '');
const laterTle = { ...laterNative, sourceFormat: 'TLE' };
invariant([earlyNative, laterNative, laterTle], result => {
  assert.equal(result.records.length, 2);
  assert.equal(result.records[1].SMD_SOURCE_FORMAT, 'TLE');
  assert.equal(result.exactDuplicateCount, 1);
  assert.equal(result.unresolvedNearSimultaneousCount, 0, 'An equivalent TLE copy must prevent a false native-OMM conflict.');
  assert.equal(result.conflictingDuplicateCount, 0);
});
invariant([earlyNative, { ...earlyNative, sourceFormat: 'TLE' }, laterNative], result => {
  assert.equal(result.records.length, 2);
  assert.equal(result.records[0].SMD_SOURCE_FORMAT, 'TLE');
  assert.equal(result.unresolvedNearSimultaneousCount, 0);
});
invariant([earlyNative, laterNative, laterTle, { ...laterTle, line1: 'retained one', line2: 'retained two' }], result => {
  assert.equal(result.exactDuplicateCount, 2);
  assert.equal(result.unresolvedNearSimultaneousCount, 0);
  assert.equal(result.records[1].SMD_TLE.line1, 'retained one');
});
// A stronger supplied native-OMM correction still wins over weaker TLE metadata.
invariant([earlyNative, laterTle, { ...laterNative, creationUs: base + 2000000,
  creationRaw: context.api.formatEpochUs(base + 2000000) }], result => {
  assert.equal(result.records.length, 1);
  assert.equal(result.records[0].SMD_SOURCE_FORMAT, undefined);
  assert.equal(result.replacementCount, 1);
});
// Canonical ordering must not manufacture authority for equal-metadata conflicts.
invariant([earlyNative, laterNative, { ...laterNative, meanMotion: 15.6 }], result => {
  assert.equal(result.conflictingDuplicateCount, 1);
  assert.equal(result.unresolvedNearSimultaneousCount, 1);
  assert.equal(result.records.length, 3);
});
invariant([earlyNative, laterNative, { ...laterNative, meanMotion: laterNative.meanMotion + 1e-12 }], result => {
  assert.equal(result.exactDuplicateCount, 1);
  assert.equal(result.unresolvedNearSimultaneousCount, 1);
});

// Repeat through real parsers and analysis using validated synthetic source lines.
const history = Array.from(context.api.parseInput(context.api.exampleTles('leo')).records);
const retainedTle = history[8];
const nativeRow = context.api.recordToOmm(retainedTle);
delete nativeRow.SMD_SOURCE_FORMAT;
delete nativeRow.SMD_TLE;
const earlierRow = { ...nativeRow, EPOCH: context.api.formatEpochUs(retainedTle.epochUs - 500000),
  MEAN_MOTION: nativeRow.MEAN_MOTION + 0.0002 };
const ordinaryRows = history.filter((_, index) => index !== 8).map(context.api.recordToOmm);
let analysisId;
for (const orderedRows of permutations([earlierRow, nativeRow, context.api.recordToOmm(retainedTle)])) {
  const raw = JSON.stringify(ordinaryRows.concat(orderedRows));
  const analysis = context.api.analyzeRaw(raw, 'Synthetic mixed provenance', {
    requestedWindow: 6, alpha: 0.1, minAbsDeltaA: 0.05, maximumStaleDays: 36500,
    maximumGapFactor: 3, orbitProfile: 'auto', detectorMode: 'elements'
  });
  assert.equal(analysis.error, false);
  assert.equal(analysis.unresolvedNearSimultaneousCount, 0);
  assert.equal(analysis.conflictingDuplicateCount, 0);
  assert.equal(analysis.hardQualityErrors.length, 0, 'Input order caused false analysis abstention.');
  if (analysisId) assert.equal(analysis.runId, analysisId);
  else analysisId = analysis.runId;
  permutationChecks++;
}
// Accepted opaque identifiers must not create cycles with decimal identifiers.
function metadataRecord(changes) {
  const parsed = context.api.parseOmmRecord({ ...nativeRow, ...changes });
  assert.equal(parsed.errors.length, 0, 'The metadata fixture must pass real OMM admission.');
  assert.ok(parsed.record);
  return parsed.record;
}
invariant(['9', '10', '1a'].map(GP_ID => metadataRecord({ GP_ID })), result => {
  assert.equal(result.records.length, 1);
  assert.equal(result.records[0].GP_ID, '10');
  assert.equal(result.exactDuplicateCount, 2);
});
invariant(['9', '10', '1a'].map((GP_ID, index) => metadataRecord({ GP_ID,
  MEAN_MOTION: nativeRow.MEAN_MOTION + (index + 1) * 0.0002 })), result => {
  assert.equal(result.records.length, 1);
  assert.equal(result.records[0].GP_ID, '10');
  assert.equal(result.replacementCount, 2);
  assert.equal(result.supersededRecords.length, 2);
  assert.equal(result.conflictingDuplicateCount, 0);
});
invariant([undefined, 'opaque', 0].map(GP_ID => metadataRecord({ GP_ID })), result => {
  assert.equal(result.records[0].GP_ID, '0', 'A supplied decimal zero remains distinct from absent metadata.');
});
invariant(['A', 'B', 'a'].map(GP_ID => metadataRecord({ GP_ID })), result => {
  assert.equal(result.records[0].GP_ID, 'a', 'Opaque identifiers use locale-independent string order.');
});
invariant(['900719925474099312344', '900719925474099312345', 'z']
  .map(GP_ID => metadataRecord({ GP_ID })), result => {
  assert.equal(result.records[0].GP_ID, '900719925474099312345', 'Decimal ordering must retain arbitrary precision.');
});
invariant([
  metadataRecord({ GP_ID: '10' }),
  metadataRecord({ GP_ID: '9', CREATION_DATE: context.api.formatEpochUs(retainedTle.epochUs + 1) }),
  metadataRecord({ GP_ID: 'opaque', CREATION_DATE: context.api.formatEpochUs(retainedTle.epochUs + 2) })
], result => {
  assert.equal(result.records[0].GP_ID, 'opaque', 'Creation metadata keeps its stronger precedence.');
});
invariant([
  metadataRecord({ GP_ID: '10', ELEMENT_SET_NO: undefined }),
  metadataRecord({ GP_ID: '9', ELEMENT_SET_NO: 0 }),
  metadataRecord({ GP_ID: 'opaque', ELEMENT_SET_NO: 1 })
], result => {
  assert.equal(result.records[0].GP_ID, 'opaque', 'Known element-set precedence must remain ahead of GP identity.');
});
const identifiers = ['', '0', '9', '10', '010', '1a', 'A', 'a', '900719925474099312345'];
for (const first of identifiers) for (const second of identifiers) {
  const preference = context.api.compareCatalogueIdentifier(first, second);
  assert.ok(preference === -context.api.compareCatalogueIdentifier(second, first), 'Identifier comparison must be antisymmetric.');
  for (const third of identifiers) {
    if (preference >= 0 && context.api.compareCatalogueIdentifier(second, third) >= 0) {
      assert.ok(context.api.compareCatalogueIdentifier(first, third) >= 0, 'Identifier precedence must be transitive.');
    }
  }
}
console.log('Catalogue permutation regressions passed (' + permutationChecks + ' permutations, including six complete analyses).');
