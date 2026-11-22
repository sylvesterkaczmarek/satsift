'use strict';

const { loadBrowserApp } = require('./load_browser_app');

const fs = require('fs');
const vm = require('vm');

function makeClassList() {
  const values = new Set();
  return { add(...items){items.forEach(x=>values.add(x));}, remove(...items){items.forEach(x=>values.delete(x));}, contains(x){return values.has(x);}, toggle(x){values.has(x)?values.delete(x):values.add(x);} };
}
const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    const defaults = { win:'6', alpha:'0.10', dath:'0.05', stale:'36500', gapWarn:'3', orbitProfile:'auto', detectorMode:'multivariate', sensitivity:'balanced', demoSelect:'leo', importMode:'replace', publicNorad:'', historyStart:'', historyEnd:'', tles:'' };
    elements.set(id, { id, value: defaults[id] || '', textContent:'', innerHTML:'', className:'', hidden:false, disabled:false, open:false, max:'', files:[], style:{}, classList:makeClassList(), addEventListener(){}, removeEventListener(){}, click(){}, focus(){}, select(){}, scrollIntoView(){}, setAttribute(){}, getAttribute(){return null;}, querySelectorAll(){return [];}, appendChild(){}, removeChild(){}, getContext(){return null;}, toBlob(cb){cb(null);} });
  }
  return elements.get(id);
}
const document = { body:{appendChild(){},removeChild(){}}, getElementById:element, createElement(tag){return element('__created_'+tag+'_'+Math.random());}, execCommand(){return false;} };
const windowObject = { document, location:{href:'https://example.test/satellite-maneuver-detector',search:''}, history:{replaceState(){}}, setTimeout(handler){if(typeof handler==='function')handler();return 1;}, clearTimeout(){}, scrollTo(){}, addEventListener(){}, removeEventListener(){}, innerWidth:1440, devicePixelRatio:1, Plotly:null, satellite:null };
const context = { window:windowObject, document, navigator:{clipboard:null}, console, URL, URLSearchParams, Date, Math, Number, String, Array, Object, Set, Map, BigInt, JSON, RegExp, Error, TypeError, Promise, Blob:globalThis.Blob, AbortController:globalThis.AbortController, fetch:async()=>{throw new Error('Network disabled in integrity exporter.');} };
context.globalThis=context; context.self=windowObject; vm.createContext(context);
vm.runInContext(fs.readFileSync('satellite-6.0.2.min.js','utf8'), context, {filename:'satellite-6.0.2.min.js'});
if (!windowObject.satellite && context.satellite) windowObject.satellite=context.satellite;
if (!windowObject.satellite) throw new Error('satellite.js did not initialise.');
const api = loadBrowserApp(context);

const inputPath=process.argv[2];
const outputPath=process.argv[3] || 'benchmark-results/integrity-v1-features.json';
if(!inputPath) throw new Error('Usage: node tools/export_integrity_v1_features.js <stress-benchmark.json> [output.json]');
const benchmark=JSON.parse(fs.readFileSync(inputPath,'utf8'));
const cases=benchmark.cases || [];
if(!cases.length) throw new Error('Input benchmark has no cases.');
if(cases.some(item=>String(item.split)==='confirmatory')) throw new Error('CONFIRMATORY PARTITION IS SEALED: integrity exporter refuses confirmatory cases.');
if(cases.some(item=>!['development','calibration'].includes(String(item.split)))) throw new Error('Integrity v1 exporter accepts development/calibration cases only.');

const settings={requestedWindow:6,alpha:0.10,minAbsDeltaA:0.05,maximumStaleDays:36500,maximumGapFactor:3,orbitProfile:'auto',detectorMode:'multivariate'};
function finite(value){return Number.isFinite(Number(value));}
function safeLog1p(value){return Math.log1p(Math.max(0,Number(value)||0));}
function rcsScale(value){const key=String(value||'').toUpperCase(); return key==='LARGE'?1.0:key==='MEDIUM'?0.6:key==='SMALL'?0.3:0.0;}
function epochPrecision(raw){const match=String(raw||'').match(/\.(\d+)/); return match?Math.min(9,match[1].length)/9:0;}
function orbitContext(regime,profile){const key=String(regime||profile||'').toUpperCase();return {orbit_leo:key==='LEO'?1:0,orbit_meo:key==='MEO'?1:0,orbit_geo:(key==='GEO'||key==='IGSO')?1:0,orbit_heo:key==='HEO'?1:0};}
function objectAgeDays(record){const launch=record&&record.omm&&record.omm.LAUNCH_DATE; if(!launch)return 0; const ms=Date.parse(String(launch)+'T00:00:00Z'); return Number.isFinite(ms)?Math.max(0,(record.t.getTime()-ms)/86400000):0;}
function serialiseElements(record,aKm){
  if(!record||!record.elements)return null;
  const e=record.elements;
  const result={semi_major_axis_km:Number(aKm),eccentricity:Number(e.ecc),inclination_deg:Number(e.incDeg),raan_deg:Number(e.raanDeg),argument_of_periapsis_deg:Number(e.argPerDeg),mean_anomaly_deg:Number(e.meanAnomDeg),mean_motion_rev_per_day:Number(e.meanMotion)};
  return Object.values(result).every(finite)?result:null;
}
function physicsPayload(analysis,row){
  const index=Number(row.index);
  if(!Number.isInteger(index)||index<=0||!Array.isArray(analysis.rows))return null;
  const previous=analysis.rows[index-1];
  if(!previous||!previous.record||!row.record)return null;
  const before=serialiseElements(previous.record,previous.a);
  const after=serialiseElements(row.record,row.a);
  if(!before||!after||!finite(row.dt)||Number(row.dt)<=0)return null;
  const residualAvailable=[row.radialKm,row.alongKm,row.crossKm].every(finite);
  return {formulation_input:'resolved GP mean elements plus common-epoch SGP4 RTN residual',gap_days:Number(row.dt),before_epoch_utc:previous.t.toISOString(),after_epoch_utc:row.t.toISOString(),before_elements:before,after_elements:after,rtn_residual_km:residualAvailable?{radial:Number(row.radialKm),along_track:Number(row.alongKm),cross_track:Number(row.crossKm)}:null};
}
function inferredOrbitRegime(record){
  if(!record||!record.elements)return null;
  const n=Number(record.elements.meanMotion);
  const e=Number(record.elements.ecc);
  if(!Number.isFinite(n)||n<=0)return null;
  const periodMinutes=1440/n;
  if(Number.isFinite(e)&&e>=0.25&&periodMinutes>=225)return 'HEO';
  if(periodMinutes<225)return 'LEO';
  if(periodMinutes>=1200&&periodMinutes<=1800)return 'GEO';
  if(periodMinutes>=225&&periodMinutes<1200)return 'MEO';
  return 'HEO';
}
function analysisAudit(item,analysis,rawRecords){
  const resolved=Array.isArray(analysis.records)?analysis.records.length:0;
  const raw=rawRecords.length;
  const superseded=Array.isArray(analysis.supersededRecords)?analysis.supersededRecords.length:0;
  const sgp4Pairs=Number(analysis.sgp4PairCount||0);
  const sgp4Failures=Number(analysis.sgp4FailureCount||0);
  const rejected=Number(analysis.rejectedCount||0);
  const objectIds=[...new Set((analysis.records||[]).map(record=>String(record.satId||'')).filter(Boolean))];
  const orbitRegimes=[...new Set((analysis.records||[]).map(inferredOrbitRegime).filter(Boolean))].sort();
  return {
    base_case_id:String(item.base_case_id||item.case_id),
    integrity_stress:item.integrity_stress||{condition:'clean',attack_class:'baseline',expected_response:'baseline'},
    raw_record_count:raw,
    resolved_record_count:resolved,
    rejected_record_count:rejected,
    rejected_fraction:raw?rejected/raw:0,
    exact_duplicate_count:Number(analysis.exactDuplicateCount||0),
    conflicting_duplicate_count:Number(analysis.conflictingDuplicateCount||0),
    unresolved_near_simultaneous_count:Number(analysis.unresolvedNearSimultaneousCount||0),
    superseded_count:superseded,
    superseded_fraction:raw?superseded/raw:0,
    excluded_gap_count:Number(analysis.excludedGapCount||0),
    sgp4_pair_count:sgp4Pairs,
    sgp4_failure_count:sgp4Failures,
    sgp4_failure_fraction:(sgp4Pairs+sgp4Failures)>0?sgp4Failures/(sgp4Pairs+sgp4Failures):1,
    detector_mode_used:analysis.detectorModeUsed||null,
    quality_status:analysis.error?'unusable':analysis.qualityStatus,
    quality_warnings:Array.isArray(analysis.qualityWarnings)?analysis.qualityWarnings:[],
    hard_quality_errors:Array.isArray(analysis.hardQualityErrors)?analysis.hardQualityErrors:[],
    median_gap_days:finite(analysis.medianDt)?Number(analysis.medianDt):null,
    maximum_gap_days:finite(analysis.maximumDt)?Number(analysis.maximumDt):null,
    maximum_usable_gap_days:finite(analysis.maximumUsableGap)?Number(analysis.maximumUsableGap):null,
    total_evaluated:Number(analysis.totalEvaluated||0),
    object_ids_seen:objectIds,
    orbit_regimes_seen:orbitRegimes,
    regime_change_detected:orbitRegimes.length>1
  };
}
function researchRow(item,analysis,row,audit){
  const record=row.record;
  if(!record||!record.elements||!row.featureValues||!finite(row.dt)||row.dt<=0)return null;
  const features={a_rate:row.featureValues.aRate,mean_motion_rate:row.featureValues.meanMotionRate,radial_rate:row.featureValues.radialRate,along_rate:row.featureValues.alongRate,cross_rate:row.featureValues.crossRate,eccentricity_vector_rate:row.featureValues.eccentricityVectorRate,inclination_vector_rate:row.featureValues.inclinationVectorRate,bstar_rate:row.featureValues.bstarRate};
  if(!Object.values(features).every(finite))return null;
  const inc=Number(record.elements.incDeg)*Math.PI/180;
  const lagHours=(finite(record.creationUs)&&finite(record.epochUs))?Math.abs(Number(record.creationUs)-Number(record.epochUs))/3.6e9:0;
  const orbit=orbitContext(item.orbit_regime,item.orbit_profile||analysis.profileName);
  return {
    case_id:item.case_id, base_case_id:audit.base_case_id, object_id:String(item.object_id), object_name:item.object_name||analysis.objectName||null,
    orbit_profile:item.orbit_profile||analysis.profileName||'AUTO', orbit_regime:item.orbit_regime||item.orbit_profile||analysis.profileName||'AUTO', split:item.split,
    label_status:item.label_status,label_confidence:item.label_confidence,evidence_kind:item.evidence_kind||null,nominal:item.label_status==='verified-quiet',
    quality_ok:!analysis.error&&audit.hard_quality_errors.length===0&&audit.unresolved_near_simultaneous_count===0&&audit.conflicting_duplicate_count===0,
    index:row.index,epoch_utc:row.t.toISOString(),integrity_stress:audit.integrity_stress,
    integrity:{pair_eligible:Boolean(row.pairEligible),sgp4_residual_available:[row.radialKm,row.alongKm,row.crossKm].every(finite),case_quality_status:audit.quality_status,rejected_fraction:audit.rejected_fraction,exact_duplicate_count:audit.exact_duplicate_count,conflicting_duplicate_count:audit.conflicting_duplicate_count,unresolved_near_simultaneous_count:audit.unresolved_near_simultaneous_count,superseded_fraction:audit.superseded_fraction,excluded_gap_count:audit.excluded_gap_count,sgp4_failure_fraction:audit.sgp4_failure_fraction,raw_record_count:audit.raw_record_count,resolved_record_count:audit.resolved_record_count},
    context:{log_gap_days:safeLog1p(row.dt),log_semi_major_axis_km:safeLog1p(row.a),eccentricity:Number(record.elements.ecc),inclination_sin:Math.sin(inc),log_abs_bstar:Math.log1p(Math.abs(Number(record.bstar||0))),log_creation_lag_hours:Math.log1p(lagHours),object_age_log_days:Math.log1p(objectAgeDays(record)),rcs_scale:rcsScale(record.omm&&record.omm.RCS_SIZE),element_set_known:record.elementSetNoKnown?1:0,gp_id_known:String(record.gpId||'').trim()?1:0,catalogue_superseded_fraction:Number(audit.superseded_fraction),epoch_precision_digits_scaled:epochPrecision(record.epochRaw),...orbit},
    features:Object.fromEntries(Object.entries(features).map(([key,value])=>[key,Number(value)])),
    physics:physicsPayload(analysis,row),
    catalogue:{creation_raw:record.creationRaw||null,epoch_raw:record.epochRaw||null,gp_id:record.gpId||null,element_set_no_known:Boolean(record.elementSetNoKnown),element_set_no:record.elementSetNoKnown?Number(record.elementSetNo):null}
  };
}

const outputCases=[]; const rows=[];
for(const item of cases){
  const rawRecords=Array.isArray(item.records)?item.records:[];
  let analysis;
  try {
    analysis=api.analyzeRaw(JSON.stringify(rawRecords),'integrity stress benchmark development/calibration',{...settings,orbitProfile:item.orbit_profile||'auto'});
  } catch(error) {
    analysis={error:true,records:[],rows:[],qualityStatus:'unusable',qualityWarnings:[],hardQualityErrors:['analysis exception: '+(error&&error.message?error.message:String(error))],rejectedCount:rawRecords.length,exactDuplicateCount:0,conflictingDuplicateCount:0,unresolvedNearSimultaneousCount:0,supersededRecords:[],excludedGapCount:0,sgp4PairCount:0,sgp4FailureCount:0,totalEvaluated:0};
  }
  const audit=analysisAudit(item,analysis,rawRecords);
  outputCases.push({case_id:item.case_id,base_case_id:audit.base_case_id,object_id:String(item.object_id),object_name:item.object_name||analysis.objectName||null,split:item.split,label_status:item.label_status,label_confidence:item.label_confidence,orbit_profile:item.orbit_profile,orbit_regime:item.orbit_regime||item.orbit_profile,source:item.source,truth_events:item.truth_events||[],span_days:analysis.error?0:Number(analysis.spanDays||0),integrity_stress:audit.integrity_stress,...audit});
  if(!analysis.error&&Array.isArray(analysis.rows)){
    for(const row of analysis.rows){const converted=researchRow(item,analysis,row,audit);if(converted)rows.push(converted);}
  }
}
fs.mkdirSync(require('path').dirname(outputPath),{recursive:true});
fs.writeFileSync(outputPath,JSON.stringify({schema:'smd-integrity-v1-features-v1',source_detector_method:'v0.4',benchmark_version:benchmark.benchmark_version,confirmatory_sealed:true,included_splits:[...new Set(cases.map(c=>c.split))].sort(),stress_conditions:benchmark.stress_conditions||[],settings,cases:outputCases,rows},null,2)+'\n');
console.log(`Wrote ${rows.length} integrity feature rows from ${outputCases.length} development/calibration stress cases to ${outputPath}.`);
