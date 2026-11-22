'use strict';

const childProcess = require('child_process');

const childCode = `
const vm = require('node:vm');
const { loadBrowserApp } = require('./tools/load_browser_app');
const context = { Date, window: {} };
vm.createContext(context);
const { parseOmmEpochUtc } = loadBrowserApp(context, { start: false });
const primary = parseOmmEpochUtc('2026-07-06T02:08:05.621280');
const first = parseOmmEpochUtc('2026-07-31T21:27:03.182112');
const second = parseOmmEpochUtc('2026-07-31T21:27:03.182976');
const explicit = parseOmmEpochUtc('2026-07-06T02:08:05.621280Z');
process.stdout.write(JSON.stringify({
  iso: primary.t.toISOString(),
  epochUs: primary.epochUs,
  raw: primary.raw,
  normalized: primary.normalized,
  microsecondDifference: second.epochUs - first.epochUs,
  explicitEpochUs: explicit.epochUs
}));
`;

const zones = ['UTC', 'Europe/London', 'America/New_York', 'Asia/Kathmandu'];
const results = zones.map(zone => {
  const output = childProcess.execFileSync(process.execPath, ['-e', childCode], {
    encoding: 'utf8',
    env: { ...process.env, TZ: zone }
  });
  return { zone, value: JSON.parse(output) };
});

const reference = JSON.stringify(results[0].value);
for (const result of results) {
  if (JSON.stringify(result.value) !== reference) {
    throw new Error(`OMM epoch parsing changed with timezone ${result.zone}: ${JSON.stringify(result.value)} != ${reference}`);
  }
}

const value = results[0].value;
if (value.iso !== '2026-07-06T02:08:05.621Z') {
  throw new Error(`Offset-less UTC epoch was shifted: ${value.iso}`);
}
if (value.normalized !== '2026-07-06T02:08:05.621280Z') {
  throw new Error(`Offset-less OMM epoch was not normalized explicitly to UTC: ${value.normalized}`);
}
if (value.raw !== '2026-07-06T02:08:05.621280') {
  throw new Error('Original OMM epoch text was not preserved.');
}
if (value.microsecondDifference !== 864) {
  throw new Error(`Sub-millisecond ordering was lost: expected 864 microseconds, got ${value.microsecondDifference}.`);
}
if (value.epochUs !== value.explicitEpochUs) {
  throw new Error('Offset-less UTC and explicit-Z OMM epochs do not map to the same instant.');
}

console.log(`Cross-timezone OMM epoch tests passed in ${zones.join(', ')}.`);
