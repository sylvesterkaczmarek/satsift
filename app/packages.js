'use strict';

// Acquisition provenance, reproducibility packages and export payloads.
globalThis.SMDModules = globalThis.SMDModules || Object.create(null);
if (Object.prototype.hasOwnProperty.call(globalThis.SMDModules, "packages")) {
  throw new Error('Workbench module already registered: packages');
}
globalThis.SMDModules["packages"] = function createPackages(common, orbitalInput, benchmark) {
  const {
    METHOD_VERSION, WORKBENCH_VERSION, PACKAGE_SCHEMA_VERSION, TLE_SOURCE_SCHEMA_VERSION,
    RUN_IDENTITY_VERSION, DATA_PROVENANCE_VERSION, INPUT_FINGERPRINT_ALGORITHM,
    MAX_PROVENANCE_SOURCES, MAX_PROVENANCE_ACQUISITIONS, MAX_PROVENANCE_BYTES, PROPAGATION_CONTRACT,
    SATELLITE_JS_VERSION, MAX_HISTORY_RANGE_DAYS, MIN_EVALUATED_POINTS, DAY_MS, FEATURE_LABELS,
    fmtTime, fmtNum, median, stableStringify, fnv1a64
  } = common;
  const {
    formatEpochUs, recordEpochUs, recordToOmm, serialiseRecordsAsOmm
  } = orbitalInput;
  const {
    benchmarkTimestamp
  } = benchmark;

  function provenanceError() {
    return new Error('Acquisition provenance is invalid, unsupported or exceeds its limit. Existing input and settings were retained.');
  }

  function provenanceObject(value, keys) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw provenanceError();
    const supplied = Object.keys(value).sort();
    const expected = keys.slice().sort();
    if (supplied.length !== expected.length || supplied.some((key, index) => key !== expected[index])) throw provenanceError();
  }

  function provenanceTimestamp(value, allowUnknown = false) {
    if (allowUnknown && value === null) return null;
    if (typeof value !== 'string' || value.length > 32 || !/(?:Z|\+00:00)$/.test(value)) throw provenanceError();
    try { benchmarkTimestamp(value); } catch (_) { throw provenanceError(); }
    return value;
  }

  function provenanceDate(value) {
    if (typeof value !== 'string' || value.length !== 10 || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value)) throw provenanceError();
    provenanceTimestamp(value + 'T00:00:00Z');
    return value;
  }

  function provenanceNorad(value) {
    if (typeof value !== 'string' || value.length > 9 || !/^[1-9][0-9]{0,8}$/.test(value)) throw provenanceError();
    return value;
  }

  function provenanceRecordNorad(records) {
    const identifiers = new Set(records.map(record => String(Number(record.satId))));
    if (identifiers.size !== 1) throw provenanceError();
    return provenanceNorad(Array.from(identifiers)[0]);
  }

  function normalizedInputFingerprint(records) {
    // This is a reproducibility binding over the browser's normalized input.
    // It is deliberately separate from the server's reported raw-record SHA-256.
    const normalized = JSON.parse(serialiseRecordsAsOmm(records));
    return { algorithm: INPUT_FINGERPRINT_ALGORITHM, value: fnv1a64(stableStringify(normalized)) };
  }

  function validateInputFingerprint(value) {
    provenanceObject(value, ['algorithm', 'value']);
    if (value.algorithm !== INPUT_FINGERPRINT_ALGORITHM || typeof value.value !== 'string' ||
        value.value.length !== 16 || !/^[0-9a-f]{16}$/.test(value.value)) throw provenanceError();
    return { algorithm: value.algorithm, value: value.value };
  }

  function provenanceSha256(value) {
    if (typeof value !== 'string' || value.length !== 64 || !/^[0-9a-f]{64}$/.test(value)) throw provenanceError();
    return value;
  }

  function validateHistoryProvenance(value, norad, requestedRange = null) {
    provenanceObject(value, ['schema_version', 'provider', 'source_class', 'policy', 'norad', 'requested_range',
      'records_sha256', 'cache_snapshot_sha256', 'cache_updated_at', 'retrieval_status', 'acquisitions']);
    if (value.schema_version !== DATA_PROVENANCE_VERSION || value.provider !== 'Space-Track' ||
        value.source_class !== 'GP_HISTORY' || value.policy !== 'retained-history-v1' ||
        provenanceNorad(value.norad) !== norad) throw provenanceError();
    provenanceObject(value.requested_range, ['start', 'end']);
    const range = { start: provenanceDate(value.requested_range.start), end: provenanceDate(value.requested_range.end) };
    const rangeStart = Date.parse(range.start + 'T00:00:00Z');
    const rangeEnd = Date.parse(range.end + 'T00:00:00Z');
    if (rangeStart > rangeEnd || rangeEnd - rangeStart >= MAX_HISTORY_RANGE_DAYS * DAY_MS ||
        (requestedRange && (range.start !== requestedRange.start || range.end !== requestedRange.end))) throw provenanceError();
    if (!Array.isArray(value.acquisitions) || value.acquisitions.length < 1 ||
        value.acquisitions.length > MAX_PROVENANCE_ACQUISITIONS) throw provenanceError();
    const updatedAt = provenanceTimestamp(value.cache_updated_at, true);
    const acquisitions = value.acquisitions.map(item => {
      provenanceObject(item, ['kind', 'source_class', 'start', 'end', 'retrieved_at', 'records_sha256']);
      if (!['upstream-fetch', 'legacy-cache'].includes(item.kind) || item.source_class !== 'GP_HISTORY') throw provenanceError();
      const acquisition = {
        kind: item.kind, source_class: item.source_class,
        start: provenanceDate(item.start), end: provenanceDate(item.end),
        retrieved_at: provenanceTimestamp(item.retrieved_at, item.kind === 'legacy-cache'),
        records_sha256: provenanceSha256(item.records_sha256)
      };
      if (acquisition.start > acquisition.end || acquisition.end < range.start || acquisition.start > range.end ||
          (item.kind === 'legacy-cache' && acquisition.retrieved_at !== null)) throw provenanceError();
      if (acquisition.retrieved_at !== null && (updatedAt === null ||
          benchmarkTimestamp(acquisition.retrieved_at).epochUs > benchmarkTimestamp(updatedAt).epochUs)) throw provenanceError();
      return acquisition;
    });
    const known = acquisitions.filter(item => item.retrieved_at !== null).length;
    const status = known === acquisitions.length ? 'recorded' : known ? 'partial' : 'legacy-unknown';
    if (value.retrieval_status !== status) throw provenanceError();
    // The acquisition fragments must cover the requested dates exactly once.
    let cursor = rangeStart;
    acquisitions.slice().sort((a, b) => a.start.localeCompare(b.start)).forEach(item => {
      const start = Math.max(rangeStart, Date.parse(item.start + 'T00:00:00Z'));
      const end = Math.min(rangeEnd, Date.parse(item.end + 'T00:00:00Z'));
      if (start !== cursor) throw provenanceError();
      cursor = end + DAY_MS;
    });
    if (cursor !== rangeEnd + DAY_MS) throw provenanceError();
    return {
      schema_version: DATA_PROVENANCE_VERSION, provider: 'Space-Track', source_class: 'GP_HISTORY',
      policy: 'retained-history-v1', norad, requested_range: range,
      records_sha256: provenanceSha256(value.records_sha256),
      cache_snapshot_sha256: provenanceSha256(value.cache_snapshot_sha256),
      cache_updated_at: updatedAt, retrieval_status: status, acquisitions
    };
  }

  function validateProvenanceSource(source, norad) {
    if (!source || typeof source !== 'object' || Array.isArray(source)) throw provenanceError();
    if (source.kind === 'space-track-history') {
      provenanceObject(source, ['kind', 'input_fingerprint', 'metadata']);
      return {
        kind: source.kind, input_fingerprint: validateInputFingerprint(source.input_fingerprint),
        metadata: validateHistoryProvenance(source.metadata, norad)
      };
    }
    if (source.kind === 'celestrak-gp') {
      provenanceObject(source, ['kind', 'input_fingerprint', 'norad', 'retrieved_at']);
      if (provenanceNorad(source.norad) !== norad) throw provenanceError();
      return {
        kind: source.kind, input_fingerprint: validateInputFingerprint(source.input_fingerprint),
        norad, retrieved_at: provenanceTimestamp(source.retrieved_at, true)
      };
    }
    if (source.kind === 'unrecorded-input') {
      provenanceObject(source, ['kind', 'input_fingerprint', 'norad']);
      if (provenanceNorad(source.norad) !== norad) throw provenanceError();
      return { kind: source.kind, input_fingerprint: validateInputFingerprint(source.input_fingerprint), norad };
    }
    throw provenanceError();
  }

  function validateInputProvenance(value, records) {
    if (value === null) return null;
    provenanceObject(value, ['schema_version', 'input_fingerprint', 'sources']);
    if (value.schema_version !== DATA_PROVENANCE_VERSION || !Array.isArray(value.sources) ||
        value.sources.length < 1 || value.sources.length > MAX_PROVENANCE_SOURCES ||
        JSON.stringify(value).length > MAX_PROVENANCE_BYTES) throw provenanceError();
    const fingerprint = validateInputFingerprint(value.input_fingerprint);
    if (fingerprint.value !== normalizedInputFingerprint(records).value) throw provenanceError();
    const norad = provenanceRecordNorad(records);
    const sources = value.sources.map(source => validateProvenanceSource(source, norad));
    if (new Set(sources.map(stableStringify)).size !== sources.length) throw provenanceError();
    return { schema_version: DATA_PROVENANCE_VERSION, input_fingerprint: fingerprint, sources };
  }

  function makeInputProvenance(records, sources) {
    return validateInputProvenance({
      schema_version: DATA_PROVENANCE_VERSION,
      input_fingerprint: normalizedInputFingerprint(records),
      sources
    }, records);
  }

  function unrecordedInputSource(records) {
    return { kind: 'unrecorded-input', input_fingerprint: normalizedInputFingerprint(records), norad: provenanceRecordNorad(records) };
  }

  function historyInputProvenance(response, records, norad, requestedRange) {
    if (!response || !Object.prototype.hasOwnProperty.call(response, 'data_provenance')) return null;
    const metadata = validateHistoryProvenance(response.data_provenance, String(Number(norad)), requestedRange);
    const startUs = BigInt(Date.parse(metadata.requested_range.start + 'T00:00:00Z')) * 1000n;
    const endUs = (BigInt(Date.parse(metadata.requested_range.end + 'T00:00:00Z')) + BigInt(DAY_MS)) * 1000n;
    if (records.some(record => !Number.isSafeInteger(recordEpochUs(record)) ||
        BigInt(recordEpochUs(record)) < startUs || BigInt(recordEpochUs(record)) >= endUs)) throw provenanceError();
    return makeInputProvenance(records, [{
      kind: 'space-track-history', input_fingerprint: normalizedInputFingerprint(records), metadata
    }]);
  }

  function currentGpInputProvenance(records, norad, retrievedAt) {
    let timestamp = null;
    if (retrievedAt !== null) {
      if (!Number.isSafeInteger(retrievedAt) || retrievedAt < 0) throw provenanceError();
      timestamp = provenanceTimestamp(new Date(retrievedAt).toISOString());
    }
    return makeInputProvenance(records, [{
      kind: 'celestrak-gp', input_fingerprint: normalizedInputFingerprint(records),
      norad: provenanceNorad(String(Number(norad))), retrieved_at: timestamp
    }]);
  }

  function provenanceSummary(value) {
    const times = [];
    let unknown = !value;
    if (value) value.sources.forEach(source => {
      if (source.kind === 'space-track-history') source.metadata.acquisitions.forEach(item => {
        if (item.retrieved_at === null) unknown = true;
        else times.push(item.retrieved_at);
      });
      else if (source.kind === 'celestrak-gp' && source.retrieved_at !== null) times.push(source.retrieved_at);
      else unknown = true;
    });
    if (!times.length) return 'Source retrieval time was not recorded.';
    times.sort((a, b) => {
      const first = benchmarkTimestamp(a).epochUs;
      const second = benchmarkTimestamp(b).epochUs;
      return first < second ? -1 : first > second ? 1 : 0;
    });
    const first = times[0];
    const last = times[times.length - 1];
    const summary = benchmarkTimestamp(first).epochUs === benchmarkTimestamp(last).epochUs
      ? 'Source retrieved ' + first + '.'
      : 'Source acquisitions from ' + first + ' to ' + last + '.';
    return summary + (unknown ? ' Some source retrieval times are unknown.' : '');
  }

  function provenanceEvidence(value) {
    const lines = ['Acquisition provenance', provenanceSummary(value)];
    if (!value) return lines.join('\n');
    lines.push('Normalized-input fingerprint (' + value.input_fingerprint.algorithm + '): ' + value.input_fingerprint.value);
    value.sources.forEach((source, index) => {
      if (source.kind === 'space-track-history') {
        lines.push('Source ' + (index + 1) + ' Space-Track requested records SHA-256: ' + source.metadata.records_sha256);
        lines.push('Source ' + (index + 1) + ' retained cache snapshot SHA-256: ' + source.metadata.cache_snapshot_sha256);
      } else if (source.kind === 'celestrak-gp') {
        lines.push('Source ' + (index + 1) + ' CelesTrak GP normalized-input fingerprint: ' + source.input_fingerprint.value);
      } else {
        lines.push('Source ' + (index + 1) + ' has unrecorded acquisition details.');
      }
    });
    lines.push('Source hashes identify reported content snapshots. The separate normalized-input fingerprint is noncryptographic; these identifiers do not authenticate a provider.');
    return lines.join('\n');
  }

  function buildEvidenceNote(analysis) {
    const strongestEvent = analysis.strongestEvent;
    let eventsText;

    if (!analysis.interpretable) {
      eventsText = '- Candidate events are not reported because this run abstained.';
    } else if (analysis.events.length) {
      eventsText = analysis.events.map(event => {
        return `- ${event.id} | ${fmtTime(event.start)} to ${fmtTime(event.end)} | ${event.direction} | net Δa=${fmtNum(event.netDeltaA, 4)} km | tier=${event.tier} | score=${fmtNum(event.score, 2)} | signals=${event.features.map(feature => FEATURE_LABELS[feature] || feature).join(', ')}`;
      }).join('\n');
    } else {
      eventsText = '- No candidate events above the selected criteria.';
    }

    return `Satellite maneuver screening evidence note

Run
Run ID: ${analysis.runId}
Generated: ${analysis.generatedAt}
Workbench version: ${WORKBENCH_VERSION}
Detector method: ${METHOD_VERSION}
Detector mode: ${analysis.detectorModeUsed}
Orbit profile: ${analysis.profileName}
SGP4 dependency: ${analysis.sgp4Available ? 'satellite.js ' + SATELLITE_JS_VERSION : 'unavailable; elements-only fallback used'}

Object
Catalog ID: ${analysis.objectId || 'unknown'}
Object name: ${analysis.objectName || 'not provided'}
Input source: ${analysis.sourceLabel || 'pasted orbital-element history'}
Input format: ${analysis.inputFormat}
Data attribution: ${analysis.sourceLabel.includes('Space-Track') ? 'Basic SSA data from Space-Track.org, operated by USSPACECOM' : 'not applicable'}

Input
Valid snapshots: ${analysis.n}
Rejected records or pairs: ${analysis.rejectedCount}
Input span: ${fmtNum(analysis.spanDays, 2)} days
Median epoch gap: ${fmtNum(analysis.medianDt, 2)} days
Latest epoch age at analysis: ${fmtNum(analysis.ageDays, 2)} days
Excluded oversized gaps: ${analysis.excludedGapCount}
Superseded catalogue revisions: ${analysis.supersededRecords ? analysis.supersededRecords.length : 0}
Successful SGP4 pair comparisons: ${analysis.sgp4PairCount}

Method
Signals: SGP4 radial, along-track and cross-track residuals plus sampling-normalised element changes
Band: rolling median with empirical residual quantiles fitted to preceding eligible pairs
Calibration window: ${analysis.window} eligible pairs
Residual tail fraction alpha: ${fmtNum(analysis.alpha, 2)}
Minimum |Δa| gate: ${analysis.minAbsDeltaA} km
Minimum sequential evaluation points: ${MIN_EVALUATED_POINTS}

Data quality
Overall status: ${analysis.qualityStatus}
Warnings and errors: ${analysis.qualityMessages.length ? analysis.qualityMessages.join('; ') : 'none'}

Result
Classification: ${analysis.classification}
Candidate events: ${analysis.interpretable ? analysis.events.length : 'not reported'}
Strongest event: ${strongestEvent ? strongestEvent.id + ' at ' + fmtTime(strongestEvent.strongest.t) : 'n/a'}
Observed primary-signal coverage: ${Number.isFinite(analysis.observedCoverage) ? fmtNum(analysis.observedCoverage, 2) : 'n/a'}

Candidate events
${eventsText}

Interpretation
This output is a screening cue for follow-up analysis. It does not confirm a maneuver, burn, command, intent or operational purpose. The event tiers are internal anomaly rankings rather than calibrated probabilities. Follow-up should include source review, higher-fidelity orbit determination, additional catalog data and mission-context checks where available.

3D context
The 3D view is approximate visual context only and is not an operational propagator.`;
  }

  function buildCsv(analysis) {
    const eventByIndex = new Map();
    analysis.events.forEach(event => event.flags.forEach(flag => eventByIndex.set(flag.idx, event.id)));
    const header = [
      'epoch_utc',
      'semi_major_axis_km',
      'delta_a_km',
      'gap_days',
      'delta_a_rate_km_per_day',
      'radial_residual_km',
      'along_track_residual_km',
      'cross_track_residual_km',
      'state_residual_km',
      'multivariate_score',
      'breached_features',
      'event_id',
      'pair_eligible',
      'evaluated',
      'flagged'
    ];

    const rows = analysis.rows.map(row => [
      formatEpochUs(recordEpochUs(row.record)),
      fmtNum(row.a, 8),
      Number.isFinite(row.dA) ? fmtNum(row.dA, 8) : '',
      Number.isFinite(row.dt) ? fmtNum(row.dt, 6) : '',
      Number.isFinite(row.dARate) ? fmtNum(row.dARate, 8) : '',
      Number.isFinite(row.radialKm) ? fmtNum(row.radialKm, 8) : '',
      Number.isFinite(row.alongKm) ? fmtNum(row.alongKm, 8) : '',
      Number.isFinite(row.crossKm) ? fmtNum(row.crossKm, 8) : '',
      Number.isFinite(row.stateResidualKm) ? fmtNum(row.stateResidualKm, 8) : '',
      Number.isFinite(row.multivariateScore) ? fmtNum(row.multivariateScore, 6) : '',
      row.breachedFeatures ? row.breachedFeatures.join('|') : '',
      eventByIndex.get(row.index) || '',
      row.pairEligible ? 'true' : 'false',
      row.evaluated ? 'true' : 'false',
      row.flagged ? 'true' : 'false'
    ]);

    return [header, ...rows]
      .map(row => row.map(cell => `"${String(cell).replaceAll('"', '""')}"`).join(','))
      .join('\n');
  }

  function buildMachineReadableResult(analysis, includeInput) {
    const result = {
      method_version: METHOD_VERSION,
      workbench_version: WORKBENCH_VERSION,
      satellite_js_version: analysis.sgp4Available ? SATELLITE_JS_VERSION : null,
      run_id: analysis.runId,
      run_identity_version: RUN_IDENTITY_VERSION,
      propagation_contract: PROPAGATION_CONTRACT,
      source_label: analysis.sourceLabel,
      data_provenance: analysis.dataProvenance ? validateInputProvenance(analysis.dataProvenance, analysis.records) : null,
      data_attribution: (analysis.sourceLabel.includes('Space-Track') ||
        (analysis.dataProvenance && analysis.dataProvenance.sources.some(source => source.kind === 'space-track-history')))
        ? 'Basic SSA data from Space-Track.org, operated by USSPACECOM' : null,
      input_format: analysis.inputFormat,
      object_id: analysis.objectId,
      object_name: analysis.objectName,
      valid_snapshots: analysis.n,
      rejected_records_or_pairs: analysis.rejectedCount,
      span_days: analysis.spanDays,
      median_gap_days: analysis.medianDt,
      latest_age_days: analysis.ageDays,
      calibration_window: analysis.window,
      alpha: analysis.alpha,
      minimum_absolute_delta_a_km: analysis.minAbsDeltaA,
      maximum_gap_factor: analysis.maximumGapFactor,
      orbit_profile: analysis.profileName,
      detector_mode: analysis.detectorModeUsed,
      sgp4_pair_count: analysis.sgp4PairCount,
      excluded_gap_count: analysis.excludedGapCount,
      evaluated_points: analysis.totalEvaluated,
      minimum_required_evaluated_points: MIN_EVALUATED_POINTS,
      observed_primary_coverage: analysis.observedCoverage,
      interpretable: analysis.interpretable,
      quality_status: analysis.qualityStatus,
      quality_messages: analysis.qualityMessages,
      exact_duplicate_count: analysis.exactDuplicateCount || 0,
      unresolved_duplicate_count: analysis.conflictingDuplicateCount || 0,
      unresolved_near_simultaneous_count: analysis.unresolvedNearSimultaneousCount || 0,
      superseded_catalogue_revisions: analysis.supersededRecords || [],
      classification: analysis.classification,
      generated_at: analysis.generatedAt,
      events: analysis.events.map(event => ({
        event_id: event.id,
        start_utc: formatEpochUs(recordEpochUs(analysis.records[event.flags[0].idx])),
        end_utc: formatEpochUs(recordEpochUs(analysis.records[event.flags[event.flags.length - 1].idx])),
        direction: event.direction,
        net_delta_a_km: event.netDeltaA,
        tier: event.tier,
        score: event.score,
        point_count: event.pointCount,
        supporting_features: event.features,
        strongest_epoch_utc: formatEpochUs(recordEpochUs(analysis.records[event.strongest.idx])),
        context_before_epoch_utc: event.contextBeforeIndex >= 0 && analysis.records[event.contextBeforeIndex] ? formatEpochUs(recordEpochUs(analysis.records[event.contextBeforeIndex])) : null,
        context_after_epoch_utc: event.contextAfterIndex >= 0 && analysis.records[event.contextAfterIndex] ? formatEpochUs(recordEpochUs(analysis.records[event.contextAfterIndex])) : null
      })),
      flags: analysis.flags.map(flag => ({
        epoch_utc: formatEpochUs(recordEpochUs(analysis.records[flag.idx])),
        delta_a_km: flag.dA,
        delta_a_rate_km_per_day: flag.dARate,
        multivariate_score: flag.severityScore,
        severity_label: flag.severityLabel,
        breached_features: flag.breachedFeatures,
        feature_scores: flag.featureScores,
        sgp4_residual: flag.sgp4Residual
      })),
      rows: analysis.rows.map(row => ({
        epoch_utc: formatEpochUs(recordEpochUs(row.record)),
        semi_major_axis_km: row.a,
        delta_a_km: Number.isFinite(row.dA) ? row.dA : null,
        gap_days: Number.isFinite(row.dt) ? row.dt : null,
        delta_a_rate_km_per_day: Number.isFinite(row.dARate) ? row.dARate : null,
        radial_residual_km: Number.isFinite(row.radialKm) ? row.radialKm : null,
        along_track_residual_km: Number.isFinite(row.alongKm) ? row.alongKm : null,
        cross_track_residual_km: Number.isFinite(row.crossKm) ? row.crossKm : null,
        state_residual_km: Number.isFinite(row.stateResidualKm) ? row.stateResidualKm : null,
        multivariate_score: Number.isFinite(row.multivariateScore) ? row.multivariateScore : null,
        breached_features: row.breachedFeatures,
        pair_eligible: row.pairEligible,
        evaluated: row.evaluated,
        flagged: row.flagged
      }))
    };

    if (includeInput) {
      result.package_schema_version = PACKAGE_SCHEMA_VERSION;
      result.normalized_input_omm = analysis.records.map(recordToOmm);
      if (analysis.analysisOptions) result.analysis_options = { ...analysis.analysisOptions };
      result.evidence_note = analysis.evidenceText;
      result.csv = analysis.csv;
      result.reproducibility = {
        deterministic_run_id_algorithm: 'Version 2: non-cryptographic FNV-1a 64-bit over exact epochs, retained propagation inputs, requested and effective settings, and implementation versions',
        epoch_unit: 'integer microseconds',
        tle_source_schema_version: TLE_SOURCE_SCHEMA_VERSION,
        propagation_contract: PROPAGATION_CONTRACT,
        omm_initialisation_precision: 'milliseconds (satellite.js 6.0.2 Date-based initialisation)',
        legacy_tle_precision: 'Original precision cannot be recovered from packages without retained TLE lines',
        dependency_assets: {
          plotly: '/satellite-maneuver-detector/plotly-3.3.1.min.js',
          satellite_js: '/satellite-maneuver-detector/satellite-6.0.2.min.js',
          orbit_context: 'Plotly 3D; Cesium dependency removed in Workbench 3.4'
        }
      };
    }
    return result;
  }

  function buildAnalysisDownloadPayloads(analysis) {
    return {
      csv: {
        filename: 'satellite-maneuver-screening.csv',
        mimeType: 'text/csv;charset=utf-8',
        text: analysis.csv
      },
      json: {
        filename: 'satellite-maneuver-screening-' + analysis.runId + '.json',
        mimeType: 'application/json;charset=utf-8',
        text: JSON.stringify(buildMachineReadableResult(analysis, false), null, 2)
      },
      reproducibility: {
        filename: 'satellite-maneuver-reproducibility-' + analysis.runId + '.json',
        mimeType: 'application/json;charset=utf-8',
        text: JSON.stringify(buildMachineReadableResult(analysis, true), null, 2)
      }
    };
  }

  return Object.freeze({
    provenanceError, provenanceObject, provenanceTimestamp, provenanceDate, provenanceNorad,
    provenanceRecordNorad, normalizedInputFingerprint, validateInputFingerprint, provenanceSha256,
    validateHistoryProvenance, validateProvenanceSource, validateInputProvenance,
    makeInputProvenance, unrecordedInputSource, historyInputProvenance, currentGpInputProvenance,
    provenanceSummary, provenanceEvidence, buildEvidenceNote, buildCsv, buildMachineReadableResult,
    buildAnalysisDownloadPayloads
  });
};
