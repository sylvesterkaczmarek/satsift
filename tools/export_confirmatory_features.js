'use strict';

const fs = require('fs');
const path = require('path');

const FINAL_RESULT = 'benchmark-results/confirmatory-v1-final.json';
const SOURCE = 'tools/export_selective_v1_features.js';

if (fs.existsSync(FINAL_RESULT)) {
  throw new Error('CONFIRMATORY RUN LOCK: final confirmatory result already exists; feature export rerun is forbidden.');
}

let source = fs.readFileSync(SOURCE, 'utf8');

function replaceOnce(before, after, label) {
  const first = source.indexOf(before);
  if (first < 0 || source.indexOf(before, first + before.length) >= 0) {
    throw new Error(`Confirmatory evaluation exporter patch ${label} was not uniquely applicable.`);
  }
  source = source.slice(0, first) + after + source.slice(first + before.length);
}

replaceOnce(
  "if(cases.some(item=>String(item.split)==='confirmatory')) throw new Error('CONFIRMATORY PARTITION IS SEALED: exporter refuses confirmatory cases.');",
  "if(cases.some(item=>String(item.split)!=='confirmatory')) throw new Error('CONFIRMATORY ONE-SHOT EXPORT: all cases must be confirmatory.');",
  'confirmatory authorization'
);
replaceOnce(
  "if(cases.some(item=>!['development','calibration'].includes(String(item.split)))) throw new Error('Selective v1 exporter accepts development/calibration cases only.');",
  "if(cases.some(item=>String(item.split)!=='confirmatory')) throw new Error('CONFIRMATORY ONE-SHOT EXPORT: mixed/non-confirmatory input refused.');",
  'split restriction'
);
replaceOnce(
  "'frozen benchmark v1 development/calibration'",
  "'frozen benchmark v1 confirmatory one-shot'",
  'analysis provenance label'
);
replaceOnce(
  "confirmatory_sealed:true,included_splits:",
  "confirmatory_sealed:false,confirmatory_confirmatory_authorized:true,one_shot:true,included_splits:",
  'output authorization metadata'
);
replaceOnce(
  "development/calibration cases to ${outputPath}",
  "one-shot confirmatory cases to ${outputPath}",
  'console provenance'
);

// The default exporter remains untouched and continues to refuse confirmatory data. This wrapper
// executes the same frozen feature-generation implementation with only the explicit Confirmatory evaluation
// authorization/provenance guards above changed in memory for the single confirmatory run.
const execute = new Function('require', 'process', 'console', '__filename', '__dirname', source);
execute(require, process, console, SOURCE, path.dirname(SOURCE));
