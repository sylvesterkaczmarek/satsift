'use strict';

// Owns interface state, asynchronous input, visualisation and event wiring.
globalThis.SMDModules = globalThis.SMDModules || Object.create(null);
if (Object.prototype.hasOwnProperty.call(globalThis.SMDModules, "interface")) {
  throw new Error('Workbench module already registered: interface');
}
globalThis.SMDModules["interface"] = function createInterface(common, orbitalInput, benchmark, packages, createDetection) {
  const detection = createDetection(common, orbitalInput, packages, getAnalysisOptions);
  const {
    METHOD_VERSION, WORKBENCH_VERSION, EVENT_MATCHING_VERSION, PACKAGE_SCHEMA_VERSION,
    RUN_IDENTITY_VERSION, SATELLITE_JS_VERSION, HISTORY_ENDPOINT, PLOTLY_ASSET_URL,
    MAX_HISTORY_RANGE_DAYS, PUBLIC_CACHE_MS, DAY_MS, FEATURE_LABELS, byId, escapeHtml, fmtTime,
    fmtNum, median, stableStringify, formatDateOnly, radians
  } = common;
  const {
    validateFetchedRecords, exampleTles, formatEpochUs, parseOmmEpochUtc, parseInput,
    serialiseRecordsAsOmm, validatedRecordsFromRaw, mergeOrbitalHistories, describeParse
  } = orbitalInput;
  const {
    benchmarkTemplateDefinition, normaliseBenchmarkDefinition, benchmarkPredictionInterval,
    matchBenchmarkEvents, makeBenchmarkId, ratioOrNull, metricText, deterministicThinBenchmarkRaw,
    initialiseProfileAccumulator, finaliseProfileMetrics
  } = benchmark;
  const {
    provenanceError, provenanceRecordNorad, normalizedInputFingerprint, validateInputProvenance,
    makeInputProvenance, unrecordedInputSource, historyInputProvenance, currentGpInputProvenance,
    provenanceSummary, provenanceEvidence, buildAnalysisDownloadPayloads
  } = packages;
  const {
    groupFlagsIntoEvents, analyzeRaw
  } = detection;

  let lastAnalysis = null;
  let lastRanking = null;
  let currentExampleKey = '';
  let currentPublicNorad = '';
  let orbitPlotReady = false;
  let suppressManualInputNotice = false;
  let suppressControlInvalidation = false;
  let currentInputSourceLabel = '';
  let currentInputProvenance = null;
  let syncingCharts = false;
  let pendingOrbitContext = null;
  let lastSelfTestReport = null;
  let benchmarkDefinition = null;
  let lastBenchmarkReport = null;
  let plotlyLoadPromise = null;
  let plotlyLoadState = 'idle';
  let inputRevision = 0;
  let inputLoadSequence = 0;
  let started = false;
  let selectedEventIndex = -1;
  let syncingHover = false;
  let consoleTheme = 'dark';

  function plotPalette() {
    return consoleTheme === 'light'
      ? { paper: '#ffffff', text: '#172d40', muted: '#4e6275', grid: '#ccd7e1', measurement: '#076980',
          candidate: '#77500f', band: 'rgba(8,123,148,0.12)', calibration: 'rgba(8,123,148,0.09)',
          gap: 'rgba(82,104,122,0.16)', crosshair: '#52687a' }
      : { paper: '#101e2f', text: '#e6edf5', muted: '#a6b7ca', grid: '#2b4056', measurement: '#73d4e6',
          candidate: '#f5cf83', band: 'rgba(87,204,226,0.13)', calibration: 'rgba(87,204,226,0.08)',
          gap: 'rgba(155,176,195,0.14)', crosshair: '#a8bfd1' };
  }

  function applyTheme(theme, persist) {
    consoleTheme = theme === 'light' ? 'light' : 'dark';
    document.documentElement?.setAttribute('data-theme', consoleTheme);
    const toggle = byId('themeToggle');
    if (toggle) {
      toggle.textContent = consoleTheme === 'dark' ? 'Light theme' : 'Dark theme';
      toggle.setAttribute('aria-label', 'Switch to ' + (consoleTheme === 'dark' ? 'light' : 'dark') + ' theme');
      toggle.setAttribute('aria-pressed', String(consoleTheme === 'light'));
    }
    if (persist) {
      try { window.localStorage?.setItem('satsift-theme', consoleTheme); } catch (_) { /* Storage may be unavailable. */ }
    }
    if (!window.Plotly) return;
    const palette = plotPalette();
    ['orbitChart', 'rateChart'].forEach(id => {
      const chart = byId(id);
      if (!chart?.data) return;
      const update = {
        paper_bgcolor: palette.paper, plot_bgcolor: palette.paper, 'font.color': palette.text,
        'xaxis.gridcolor': palette.grid, 'yaxis.gridcolor': palette.grid,
        'xaxis.zerolinecolor': palette.grid, 'yaxis.zerolinecolor': palette.grid,
        'xaxis.spikecolor': palette.crosshair,
        'hoverlabel.bgcolor': palette.paper, 'hoverlabel.font.color': palette.text,
        'hoverlabel.bordercolor': palette.grid,
        shapes: lastAnalysis && !lastAnalysis.error ? chartEvidenceShapes(lastAnalysis) : []
      };
      window.Plotly.relayout(chart, update).catch(() => {});
      chart.data.forEach((trace, index) => {
        const color = trace.name === 'Candidate epoch' ? palette.candidate
          : trace.name === 'Excluded gap' ? palette.muted : palette.measurement;
        const restyle = { 'line.color': color, 'marker.color': color };
        if (trace.fill) restyle.fillcolor = palette.band;
        window.Plotly.restyle(chart, restyle, [index]).catch(() => {});
      });
    });
    const viewer = byId('orbitViewer');
    if (viewer?.data) {
      const update = { paper_bgcolor: palette.paper, plot_bgcolor: palette.paper,
        'font.color': palette.text, 'scene.bgcolor': palette.paper };
      ['x', 'y', 'z'].forEach(axis => {
        update['scene.' + axis + 'axis.gridcolor'] = palette.grid;
        update['scene.' + axis + 'axis.zerolinecolor'] = palette.grid;
      });
      window.Plotly.relayout(viewer, update).catch(() => {});
      viewer.data.forEach((trace, index) => {
        if (trace.type !== 'scatter3d') return;
        const color = trace.name === 'Final event record' || trace.name === 'Selected epoch'
          ? palette.candidate : palette.measurement;
        const restyle = { 'line.color': color, 'marker.color': color, 'marker.line.color': palette.paper };
        if (trace.name === 'Element epochs') restyle['marker.color'] = [[palette.measurement, palette.candidate]];
        window.Plotly.restyle(viewer, restyle, [index]).catch(() => {});
      });
    }
  }

  function initialiseConsole() {
    let preference = 'dark';
    try { preference = window.localStorage?.getItem('satsift-theme') || 'dark'; } catch (_) { /* Use the default theme. */ }
    applyTheme(preference, false);
    byId('themeToggle')?.addEventListener('click', () => applyTheme(consoleTheme === 'dark' ? 'light' : 'dark', true));
    byId('previousEvent')?.addEventListener('click', () => selectEvent(selectedEventIndex - 1));
    byId('nextEvent')?.addEventListener('click', () => selectEvent(selectedEventIndex + 1));
    byId('focusEventCharts')?.addEventListener('click', focusSelectedEvent);
    renderConsoleSummary(null);
    resetEventInspector();
  }

  function renderConsoleSummary(analysis) {
    const valid = analysis && !analysis.error;
    const latest = valid ? analysis.records[analysis.records.length - 1] : null;
    const inferredRegime = valid ? detection.inferOrbitProfile(analysis.records) : null;
    const values = {
      consoleObject: valid ? analysis.objectName || 'Unnamed object' : 'No analysed object',
      consoleNorad: valid ? analysis.objectId || 'Unresolved' : 'n/a',
      consoleRegime: valid ? inferredRegime : 'n/a',
      consoleEpoch: latest ? formatEpochUs(orbitalInput.recordEpochUs(latest)) : 'n/a',
      consoleQuality: valid ? analysis.qualityStatus : analysis?.error ? 'Input invalid' : 'Awaiting analysis',
      consoleSource: valid ? analysis.sourceLabel + ' · ' + provenanceSummary(analysis.dataProvenance) : 'No analysed source'
    };
    Object.entries(values).forEach(([id, value]) => {
      const element = byId(id);
      if (element) {
        element.textContent = value;
        element.title = id === 'consoleRegime' && valid
          ? inferredRegime + ' inferred from the orbital history; ' + analysis.profileName + ' screening profile selected' : value;
      }
    });
    const quality = byId('consoleQuality');
    if (quality) quality.setAttribute('data-state', valid ? analysis.hardQualityErrors.length ? 'err'
      : analysis.qualityWarnings.length ? 'warn' : 'ok' : analysis?.error ? 'err' : 'neutral');
  }

  function resetEventInspector(message) {
    selectedEventIndex = -1;
    const title = byId('eventInspectorTitle');
    const body = byId('eventInspectorBody');
    if (title) title.textContent = 'Event inspector';
    if (body) body.innerHTML = '<p class="inspector-note">' + escapeHtml(message ||
      'Run a screening analysis, then select a candidate event to review its records and supporting signals.') + '</p>';
    ['previousEvent', 'nextEvent', 'focusEventCharts'].forEach(id => {
      if (byId(id)) byId(id).disabled = true;
    });
  }

  function primaryCalibrationIndices(analysis, epochIndex) {
    const indices = [];
    for (let index = epochIndex - 1; index > 0 && indices.length < analysis.window; index--) {
      if (analysis.pairEligible[index] && Number.isFinite(analysis.featureValues.aRate[index])) indices.push(index);
    }
    return indices.reverse();
  }

  function chartEvidenceShapes(analysis) {
    const palette = plotPalette();
    const selected = analysis.events[selectedEventIndex] || null;
    // Keep the candidate lines first for existing accessible chart consumers.
    const shapes = analysis.events.map(event => ({
      type: 'line', name: 'Candidate ' + event.id, x0: fmtTime(event.strongest.t), x1: fmtTime(event.strongest.t),
      y0: 0, y1: 1, yref: 'paper', layer: 'above',
      line: { color: palette.candidate, width: event === selected ? 2.5 : 1, dash: event === selected ? 'solid' : 'dot' }
    }));
    const rect = (name, first, last, fillcolor) => ({
      type: 'rect', name, x0: fmtTime(analysis.times[first]), x1: fmtTime(analysis.times[last]),
      y0: 0, y1: 1, yref: 'paper', layer: 'below', fillcolor, line: { width: 0 }
    });
    const firstEvaluated = analysis.evaluated.findIndex(Boolean);
    const lastCalibrationIndex = firstEvaluated < 0 ? analysis.times.length - 1 : firstEvaluated - 1;
    if (!selected && lastCalibrationIndex > 0) {
      shapes.push(rect('Initial calibration', 0, lastCalibrationIndex, palette.calibration));
    }
    if (selected) {
      const indices = primaryCalibrationIndices(analysis, selected.strongest.idx);
      let start = 0;
      for (let index = 0; index < indices.length; index++) {
        if (index === indices.length - 1 || indices[index + 1] !== indices[index] + 1) {
          shapes.push(rect('Selected event calibration', indices[start] - 1, indices[index], palette.calibration));
          start = index + 1;
        }
      }
      const first = Math.max(0, selected.contextBeforeIndex);
      shapes.push(rect('Selected event interval', first, selected.contextAfterIndex, palette.band));
    }
    for (let index = 1; index < analysis.times.length; index++) {
      if (analysis.pairEligible[index] || !Number.isFinite(analysis.rows[index].dt)) continue;
      const first = index - 1;
      while (index + 1 < analysis.times.length && !analysis.pairEligible[index + 1] && Number.isFinite(analysis.rows[index + 1].dt)) index++;
      shapes.push(rect('Excluded data gap', first, index, palette.gap));
    }
    return shapes;
  }

  function updateChartEvidence() {
    if (!lastAnalysis || lastAnalysis.error) return;
    const selected = lastAnalysis.events[selectedEventIndex] || null;
    const hint = byId('chartContextHint');
    if (hint) hint.textContent = selected
      ? selected.id + ' selected. Shading marks its grouped interval and the preceding ' + lastAnalysis.window +
        ' eligible primary-rate pairs used for calibration. Other signals may have different available histories. All epochs are UTC.'
      : 'Shading marks initial calibration and excluded data gaps. Candidate lines show the strongest flagged epoch in each group. All epochs are UTC.';
    if (!window.Plotly) return;
    const shapes = chartEvidenceShapes(lastAnalysis);
    ['orbitChart', 'rateChart'].forEach(id => {
      const chart = byId(id);
      if (chart?.data) window.Plotly.relayout(chart, { shapes }).catch(() => {});
    });
  }

  function renderEventInspector(event, index) {
    const title = byId('eventInspectorTitle');
    const body = byId('eventInspectorBody');
    if (!body || !lastAnalysis) return;
    if (title) title.textContent = event.id + ' · ' + (index + 1) + ' of ' + lastAnalysis.events.length;
    const flag = event.strongest;
    const profile = common.PROFILE_LIBRARY[lastAnalysis.profileName];
    const before = lastAnalysis.records[event.contextBeforeIndex];
    const after = lastAnalysis.records[event.contextAfterIndex];
    const pair = (label, value) => '<div><dt>' + escapeHtml(label) + '</dt><dd>' + escapeHtml(value) + '</dd></div>';
    const sourceRecord = (label, record) => {
      if (!record) return '';
      const payload = record.line1 && record.line2
        ? [record.name, record.line1, record.line2].filter(Boolean).join('\n')
        : JSON.stringify(orbitalInput.recordToOmm(record), null, 2);
      return '<details class="inspector-records"><summary>' + escapeHtml(label) +
        '</summary><p class="small mono">' + escapeHtml(formatEpochUs(orbitalInput.recordEpochUs(record))) +
        '</p><pre tabindex="0" aria-label="' + escapeHtml(label) + '">' + escapeHtml(payload) + '</pre></details>';
    };
    const scores = Object.entries(flag.featureScores).filter(([, score]) => Number.isFinite(score));
    const scoreRows = scores.map(([feature, score]) => '<tr><th scope="row">' +
      escapeHtml(FEATURE_LABELS[feature] || feature) + '</th><td class="mono">' + escapeHtml(fmtNum(score, 2)) +
      '×</td><td>' + (score > 1 ? 'Breach' : 'Within band') + '</td></tr>').join('');
    const warnings = lastAnalysis.qualityWarnings.length
      ? '<ul class="inspector-warning">' + lastAnalysis.qualityWarnings.map(item => '<li>' + escapeHtml(item) + '</li>').join('') + '</ul>'
      : '<p class="inspector-note">No data-quality warning was raised for this run.</p>';
    body.innerHTML =
      '<p class="inspector-note">Candidate screening evidence. Scores describe departures from empirical bands; they are not probabilities of a maneuver.</p>' +
      '<dl class="inspector-metrics">' +
      pair('Direction', event.direction) + pair('Grouped interval UTC', fmtTime(event.start) + ' to ' + fmtTime(event.end)) +
      pair('Strongest epoch UTC', fmtTime(flag.t)) + pair('Flagged observations', String(event.pointCount)) +
      pair('Net semi-major-axis change', fmtNum(event.netDeltaA, 4) + ' km') +
      pair('Strongest pair change', fmtNum(flag.dA, 4) + ' km') +
      pair('Strongest pair rate', fmtNum(flag.dARate, 4) + ' km/day') +
      pair('Primary empirical band', fmtNum(flag.baseline - flag.halfWidth, 4) + ' to ' +
        fmtNum(flag.baseline + flag.halfWidth, 4) + ' km/day') +
      pair('SGP4 position residual', flag.sgp4Residual ? fmtNum(flag.sgp4Residual.positionKm, 4) + ' km' : 'Unavailable') +
      pair('Screening score', fmtNum(event.score, 2) + '× · ' + event.tier) + '</dl>' +
      '<details class="inspector-signals" open><summary>Signals at the strongest epoch</summary>' +
      '<div class="table-wrap" tabindex="0" role="region" aria-label="Signal evidence"><table><thead><tr>' +
      '<th scope="col">Signal</th><th scope="col">Band ratio</th><th scope="col">Outcome</th></tr></thead><tbody>' +
      scoreRows + '</tbody></table></div><p class="inspector-note">A ratio above 1 exceeds that signal\'s empirical band. ' +
      'The event also needs to pass the existing corroboration and magnitude gates.</p></details>' +
      '<details class="inspector-thresholds"><summary>Screening settings</summary><dl class="inspector-metrics">' +
      pair('Orbit profile', lastAnalysis.profileName) + pair('Mode', lastAnalysis.detectorModeUsed) +
      pair('Calibration history', lastAnalysis.window + ' eligible pairs per signal') +
      pair('Alpha', fmtNum(lastAnalysis.alpha, 2)) +
      pair('Minimum primary change', fmtNum(lastAnalysis.minAbsDeltaA, 4) + ' km') +
      pair('Minimum screening score', fmtNum(profile.scoreThreshold, 2) + '×') +
      pair('Corroborated state gate', fmtNum(profile.stateGateKm, 2) + ' km') +
      pair('Required state-support signals', String(profile.supportRequired)) +
      pair('Maximum usable pair gap', fmtNum(lastAnalysis.maximumUsableGap, 3) + ' days') + '</dl></details>' +
      '<details class="inspector-provenance"><summary>Source and quality</summary><p class="inspector-note">' +
      escapeHtml(lastAnalysis.sourceLabel) + '</p><p class="inspector-note">' +
      escapeHtml(provenanceSummary(lastAnalysis.dataProvenance)) + '</p>' + warnings + '</details>' +
      sourceRecord('Pre-event source record', before) + sourceRecord('Final grouped-event source record', after) +
      (flag.idx - 1 !== event.contextBeforeIndex
        ? sourceRecord('Strongest-pair prior source record', lastAnalysis.records[flag.idx - 1]) : '') +
      (flag.idx !== event.contextAfterIndex
        ? sourceRecord('Strongest-epoch source record', lastAnalysis.records[flag.idx]) : '');
  }

  function selectEvent(index) {
    if (!lastAnalysis || lastAnalysis.error || !Number.isInteger(index) || index < 0 || index >= lastAnalysis.events.length) return;
    selectedEventIndex = index;
    const event = lastAnalysis.events[index];
    renderEventInspector(event, index);
    byId('flagTableBody').querySelectorAll('[data-event-index]').forEach(button => {
      const selected = Number(button.getAttribute('data-event-index')) === index;
      button.setAttribute('aria-pressed', String(selected));
      button.closest?.('tr')?.classList.toggle('event-selected', selected);
    });
    if (byId('previousEvent')) byId('previousEvent').disabled = index === 0;
    if (byId('nextEvent')) byId('nextEvent').disabled = index === lastAnalysis.events.length - 1;
    if (byId('focusEventCharts')) byId('focusEventCharts').disabled = false;
    updateChartEvidence();
    queueOrbitComparisonForEvent(event);
  }

  function focusSelectedEvent() {
    const event = lastAnalysis?.events?.[selectedEventIndex];
    if (!event || !window.Plotly) return;
    const before = lastAnalysis.records[event.contextBeforeIndex].t.getTime();
    const after = lastAnalysis.records[event.contextAfterIndex].t.getTime();
    const padding = Math.max((after - before) * 0.5, lastAnalysis.medianDt * DAY_MS, 60000);
    const range = [new Date(before - padding).toISOString(), new Date(after + padding).toISOString()];
    syncingCharts = true;
    Promise.all(['orbitChart', 'rateChart'].map(id => {
      const chart = byId(id);
      return chart?.data ? window.Plotly.relayout(chart, { 'xaxis.range': range, 'xaxis.autorange': false }) : Promise.resolve();
    })).catch(() => {}).finally(() => { syncingCharts = false; });
  }

  function beginInputLoad() {
    return { sequence: ++inputLoadSequence, revision: inputRevision, raw: byId('tles').value };
  }

  function inputLoadIsCurrent(ticket) {
    return ticket.sequence === inputLoadSequence && ticket.revision === inputRevision && ticket.raw === byId('tles').value;
  }

  function explainSupersededLoad(ticket, hint) {
    if (ticket.sequence === inputLoadSequence) {
      hint.textContent = 'The loaded data was not applied because your input or selection changed. Load it again when you are ready.';
    }
  }

  function setStatus(kind, text) {
    const element = byId('status');
    element.textContent = text;
    element.className = 'badge ' + (kind || 'neutral');
    const consoleState = byId('consoleState');
    if (consoleState) {
      consoleState.textContent = text;
      consoleState.title = text;
      consoleState.setAttribute('data-state', kind || 'neutral');
    }
  }

  function setRunButtonState(state) {
    const button = byId('run');
    if (!button) return;

    if (state === 'current') {
      button.disabled = true;
      button.textContent = 'Analysis up to date';
    } else if (state === 'error') {
      button.disabled = true;
      button.textContent = 'Fix input to continue';
    } else {
      button.disabled = false;
      button.textContent = 'Run analysis';
    }
  }

  function setChartMessage(message) {
    ['orbitChart', 'rateChart'].forEach(id => {
      const container = byId(id);
      if (!container) return;
      if (window.Plotly) window.Plotly.purge(container);
      container.innerHTML = '<div class="chart-fallback small muted">' + escapeHtml(message) + '</div>';
    });
    byId('resetChartZoom').disabled = true;
    const chartDataBody = byId('chartDataBody');
    if (chartDataBody) {
      chartDataBody.innerHTML = '<tr><td colspan="9" class="muted">Run an analysis to populate the accessible chart data.</td></tr>';
    }
    if (byId('chartDataDetails')) byId('chartDataDetails').open = false;
  }

  function ensurePlotlyLoaded() {
    if (window.Plotly) {
      plotlyLoadState = 'ready';
      return Promise.resolve(window.Plotly);
    }
    if (plotlyLoadPromise) return plotlyLoadPromise;

    plotlyLoadState = 'loading';
    updateDependencyStatus();
    plotlyLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = PLOTLY_ASSET_URL;
      script.async = true;
      script.setAttribute('data-smd-dependency', 'plotly');

      script.addEventListener('load', () => {
        if (window.Plotly) {
          plotlyLoadState = 'ready';
          updateDependencyStatus();
          resolve(window.Plotly);
          return;
        }
        plotlyLoadState = 'failed';
        plotlyLoadPromise = null;
        updateDependencyStatus();
        reject(new Error('The local Plotly asset loaded without exposing the Plotly API.'));
      });
      script.addEventListener('error', () => {
        plotlyLoadState = 'failed';
        plotlyLoadPromise = null;
        updateDependencyStatus();
        if (script.parentNode) script.parentNode.removeChild(script);
        reject(new Error('The local Plotly asset could not be loaded.'));
      });
      document.head.appendChild(script);
    });
    return plotlyLoadPromise;
  }

  function safePlot(containerId, data, layout) {
    const container = byId(containerId);
    if (!window.Plotly) {
      container.innerHTML = '<div class="chart-fallback small muted">Plotly is unavailable. The tabular chart data remains available below.</div>';
      return null;
    }

    container.innerHTML = '';
    return window.Plotly.newPlot(containerId, data, layout, {
      displayModeBar: false,
      responsive: true
    });
  }

  function copyText(text, hintElement, successMessage) {
    function show(message) {
      if (!hintElement) return;
      hintElement.textContent = message;
      window.setTimeout(() => {
        if (hintElement.textContent === message) hintElement.textContent = '';
      }, 1800);
    }

    if (!text || !String(text).trim()) {
      show('Nothing to copy yet.');
      return;
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text)
        .then(() => show(successMessage || 'Copied to clipboard.'))
        .catch(() => show('Copy is unavailable in this browser.'));
      return;
    }

    const temporary = document.createElement('textarea');
    temporary.value = text;
    temporary.style.position = 'fixed';
    temporary.style.opacity = '0';
    document.body.appendChild(temporary);
    temporary.focus();
    temporary.select();

    try {
      const copied = document.execCommand('copy');
      show(copied ? (successMessage || 'Copied to clipboard.') : 'Copy is unavailable in this browser.');
    } catch (error) {
      show('Copy is unavailable in this browser.');
    }

    document.body.removeChild(temporary);
  }

  function downloadText(filename, mimeType, text) {
    const blob = new Blob([text], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function downloadBlob(filename, blob) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function setCopyFlagsEnabled(enabled) {
    byId('copyFlags').disabled = !enabled;
  }

  function setAnalysisExportEnabled(enabled) {
    ['copyEvidence', 'downloadCsv', 'downloadJson', 'downloadBundle', 'saveChart'].forEach(id => {
      byId(id).disabled = !enabled;
    });
  }

  function setRankingExportEnabled(enabled) {
    byId('downloadRankJson').disabled = !enabled;
  }

  function renderQuality(items) {
    const container = byId('qualitySummary');

    if (!items || !items.length) {
      container.innerHTML = `
        <div class="quality-item">
          <div class="quality-left">
            <span class="dot"></span>
            <div>Waiting for analysis</div>
          </div>
          <div class="quality-value">n/a</div>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map(item => {
      const dotClass =
        item.kind === 'ok' ? 'ok-dot' :
        item.kind === 'warn' ? 'warn-dot' :
        item.kind === 'err' ? 'err-dot' : '';

      return `
        <div class="quality-item">
          <div class="quality-left">
            <span class="dot ${dotClass}"></span>
            <div>${escapeHtml(item.label)}</div>
          </div>
          <div class="quality-value">${escapeHtml(item.value)}</div>
        </div>
      `;
    }).join('');
  }

  function renderResult(kind, title, body, details) {
    const box = byId('resultBox');
    const cardClass = kind === 'ok' ? 'ok' : kind === 'warn' ? 'warn' : kind === 'err' ? 'err' : 'neutral';

    let detailHtml = '';
    if (details && details.length) {
      detailHtml = '<div class="result-grid">' + details.map(item => `
        <div class="result-kv">
          <div class="k">${escapeHtml(item.key)}</div>
          <div class="v">${escapeHtml(item.value)}</div>
        </div>
      `).join('') + '</div>';
    }

    box.className = 'soft-card ' + cardClass;
    box.innerHTML = `
      <div class="result-title">${escapeHtml(title)}</div>
      <p class="result-body">${escapeHtml(body)}</p>
      ${detailHtml}
    `;
  }

  function clearRanking(message) {
    const hadRanking = Boolean(lastRanking && lastRanking.length);
    lastRanking = null;
    setRankingExportEnabled(false);
    byId('rankTableBody').innerHTML = '<tr><td colspan="6" class="muted">Run ranked demo screening to populate this table.</td></tr>';
    byId('rankHint').textContent = hadRanking ? (message || '') : '';
  }

  function resetOutputOnly(statusText) {
    lastAnalysis = null;
    resetEventInspector();
    renderConsoleSummary(null);
    if (byId('chartContextHint')) byId('chartContextHint').textContent = 'All epochs are UTC. Load a history to review its orbital-change evidence.';
    setAnalysisExportEnabled(false);
    setCopyFlagsEnabled(false);

    byId('parseSummary').textContent = '';
    byId('pairCount').textContent = '';
    byId('audit').textContent = '';
    byId('flags').textContent = 'Run the analysis to populate the candidate-event list.';
    byId('flagCopyHint').textContent = '';
    byId('flagCount').textContent = '';
    byId('exportHint').textContent = '';
    byId('flagTableWrap').style.display = 'none';
    byId('flagTableBody').innerHTML = '';
    byId('executiveSummary').classList.remove('visible', 'analysis-error');
    byId('candidateEventsCard').hidden = true;
    byId('stickyResultBar').hidden = true;
    byId('chartCard')?.classList.remove('expanded');
    if (byId('toggleChartSize')) byId('toggleChartSize').textContent = 'Expand charts';
    setRunButtonState('ready');

    setStatus('neutral', statusText || 'Waiting for input');
    renderQuality([]);
    renderResult('neutral', 'No analysis yet', 'Load an example, import a file or paste orbital-element history, then run the analysis.', []);
    setChartMessage('Run an analysis to display the orbital-change evidence.');
    clearOrbitContext('Run an analysis, then open this section to load the 3D context.');
  }

  function invalidateResults(message, clearRankedResults) {
    hideDemoNotice();
    resetOutputOnly(message || 'Input or settings changed. Run analysis again.');
    if (clearRankedResults !== false) {
      clearRanking('Settings changed. Run ranked demo screening again.');
    }
  }

  function setSensitivity(value) {
    suppressControlInvalidation = true;
    if (value === 'sensitive') {
      byId('win').value = '5';
      byId('alpha').value = '0.20';
    } else if (value === 'conservative') {
      byId('win').value = '8';
      byId('alpha').value = '0.05';
    } else if (value === 'balanced') {
      byId('win').value = '6';
      byId('alpha').value = '0.10';
    }
    suppressControlInvalidation = false;
  }

  function syncSensitivityFromControls() {
    const windowValue = Number(byId('win').value);
    const alphaValue = Number(byId('alpha').value);
    let preset = 'custom';

    if (windowValue === 6 && Math.abs(alphaValue - 0.10) < 1e-9) preset = 'balanced';
    else if (windowValue === 5 && Math.abs(alphaValue - 0.20) < 1e-9) preset = 'sensitive';
    else if (windowValue === 8 && Math.abs(alphaValue - 0.05) < 1e-9) preset = 'conservative';

    byId('sensitivity').value = preset;
  }

  function currentInputRecordCount() {
    try {
      const raw = byId('tles').value.trim();
      if (!raw) return 0;
      const parsed = parseInput(raw);
      return parsed && Array.isArray(parsed.records) ? parsed.records.length : 0;
    } catch (error) {
      return 0;
    }
  }

  function syncPublicSnapshotControls() {
    const replaceButton = byId('replacePublicOmm');
    const appendButton = byId('appendPublicOmm');
    if (!replaceButton || !appendButton) return;

    const recordCount = currentInputRecordCount();
    const hasHistory = recordCount > 1;
    replaceButton.disabled = hasHistory;
    replaceButton.title = hasHistory
      ? 'Disabled because the current input contains multiple records. Append the current snapshot instead.'
      : '';
    appendButton.disabled = false;
  }

  function mergeInputProvenance(existingRecords, incomingRecords, mergedRecords, incomingProvenance) {
    if (!currentInputProvenance && !incomingProvenance) return null;
    const previous = validateInputProvenance(currentInputProvenance, existingRecords);
    const sources = (previous ? previous.sources : [unrecordedInputSource(existingRecords)])
      .concat(incomingProvenance ? incomingProvenance.sources : [unrecordedInputSource(incomingRecords)]);
    const unique = new Map(sources.map(source => [stableStringify(source), source]));
    return makeInputProvenance(mergedRecords, Array.from(unique.values()));
  }

  function assignInputValue(raw, sourceLabel, statusMessage, provenance = null) {
    let checkedProvenance = null;
    if (provenance !== null) {
      const parsed = validatedRecordsFromRaw(raw, 'Input');
      if (parsed.rejectedCount) throw provenanceError();
      checkedProvenance = validateInputProvenance(provenance, parsed.records);
    }
    inputRevision++;
    suppressManualInputNotice = true;
    byId('tles').value = raw;
    suppressManualInputNotice = false;
    currentInputSourceLabel = sourceLabel || '';
    currentInputProvenance = checkedProvenance;
    currentExampleKey = '';
    currentPublicNorad = '';
    syncPublicSnapshotControls();
    removeObjectParameters();
    invalidateResults(statusMessage || 'Input changed. Run analysis again.');
  }

  function applyIncomingData(raw, mode, sourceLabel, provenance = null) {
    const incoming = validatedRecordsFromRaw(raw, 'Incoming data');
    if (provenance !== null && incoming.rejectedCount) throw provenanceError();
    const incomingProvenance = validateInputProvenance(provenance, incoming.records);

    if (mode === 'append' && byId('tles').value.trim()) {
      const merged = mergeOrbitalHistories(byId('tles').value, raw);
      const unchanged = merged.unchanged;
      if (!unchanged) {
        const existing = validatedRecordsFromRaw(byId('tles').value, 'Current input');
        const mergedProvenance = mergeInputProvenance(existing.records, incoming.records, merged.records, incomingProvenance);
        assignInputValue(
          serialiseRecordsAsOmm(merged.records),
          sourceLabel || 'merged imported orbital-element history',
          'Validated data appended and merged.',
          mergedProvenance
        );
      }
      return {
        parsed: incoming,
        merged: true,
        unchanged,
        total: merged.records.length,
        added: merged.addedCount,
        replacements: merged.replacementCount,
        duplicates: merged.duplicateCount
      };
    }

    assignInputValue(raw.trim(), sourceLabel || 'imported orbital-element history', 'Validated input loaded.', incomingProvenance);
    return {
      parsed: incoming,
      merged: false,
      total: incoming.records.length,
      added: incoming.records.length,
      duplicates: 0
    };
  }

  function decodeSavedPackage(raw, mode) {
    let saved;
    try { saved = JSON.parse(raw); } catch (_) { return null; }
    if (!saved || typeof saved !== 'object' || !Object.prototype.hasOwnProperty.call(saved, 'normalized_input_omm')) return null;
    if (mode === 'append') throw new Error('Choose Replace current input to reopen a saved analysis package with its settings.');
    const legacySchema = !Object.prototype.hasOwnProperty.call(saved, 'package_schema_version');
    if ((!legacySchema && saved.package_schema_version !== PACKAGE_SCHEMA_VERSION) ||
        (!legacySchema && saved.run_identity_version !== RUN_IDENTITY_VERSION) ||
        (Object.prototype.hasOwnProperty.call(saved, 'run_identity_version') && saved.run_identity_version !== RUN_IDENTITY_VERSION)) {
      throw new Error('This saved package uses an unsupported package schema or run identity. Existing input and settings were retained.');
    }
    if (saved.method_version !== METHOD_VERSION) throw new Error('This saved package uses an unsupported detector method. Existing input and settings were retained.');
    if (!Array.isArray(saved.normalized_input_omm) || !saved.normalized_input_omm.length) throw new Error('The saved package has no orbital history.');
    const input = JSON.stringify(saved.normalized_input_omm, null, 2);
    const parsed = validatedRecordsFromRaw(input, 'Saved package');
    if (parsed.rejectedCount) throw new Error('The saved package contains invalid orbital records. Existing input and settings were retained.');
    const options = saved.analysis_options || {
      requestedWindow: saved.calibration_window, alpha: saved.alpha,
      minAbsDeltaA: saved.minimum_absolute_delta_a_km, maximumGapFactor: saved.maximum_gap_factor,
      maximumStaleDays: getAnalysisOptions().maximumStaleDays, orbitProfile: saved.orbit_profile,
      detectorMode: saved.detector_mode === 'SGP4 multivariate' ? 'multivariate' : saved.detector_mode === 'Elements only' ? 'elements' : null
    };
    if (typeof options !== 'object' || Array.isArray(options) ||
        !Number.isInteger(options.requestedWindow) || options.requestedWindow < 5 || options.requestedWindow > 100 ||
        !Number.isFinite(options.alpha) || options.alpha < 0.01 || options.alpha > 0.5 ||
        !Number.isFinite(options.minAbsDeltaA) || options.minAbsDeltaA <= 0 ||
        !Number.isFinite(options.maximumStaleDays) || options.maximumStaleDays <= 0 ||
        !Number.isFinite(options.maximumGapFactor) || options.maximumGapFactor < 1.5 ||
        !['auto', 'LEO', 'MEO', 'GEO', 'HEO'].includes(options.orbitProfile) ||
        !['multivariate', 'elements'].includes(options.detectorMode)) {
      throw new Error('The saved package contains invalid analysis settings. Existing input and settings were retained.');
    }
    const missingTleSource = parsed.records.some(record =>
      (record.sourceFormat === 'TLE' || saved.input_format === 'TLE') && !(record.line1 && record.line2));
    const provenance = Object.prototype.hasOwnProperty.call(saved, 'data_provenance')
      ? validateInputProvenance(saved.data_provenance, parsed.records)
      : null;
    return { input, options, provenance, legacy: !saved.analysis_options, legacySchema, missingTleSource };
  }

  async function importLocalFile(file, mode) {
    const hint = byId('fileImportHint');
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      hint.textContent = 'File rejected because it is larger than 5 MB.';
      return;
    }

    const ticket = beginInputLoad();
    hint.textContent = 'Validating ' + file.name + '…';
    try {
      const raw = await file.text();
      if (!inputLoadIsCurrent(ticket)) { explainSupersededLoad(ticket, hint); return; }
      const saved = decodeSavedPackage(raw, mode);
      let provenance = saved ? saved.provenance : null;
      if (!saved) {
        let decoded = null;
        try { decoded = JSON.parse(raw); } catch (_) { /* A TLE file has no JSON metadata. */ }
        if (decoded && Object.prototype.hasOwnProperty.call(decoded, 'data_provenance')) {
          if (!Array.isArray(decoded.records)) throw provenanceError();
          const parsed = validatedRecordsFromRaw(raw, 'Local source');
          if (parsed.rejectedCount) throw provenanceError();
          const norad = provenanceRecordNorad(parsed.records);
          provenance = historyInputProvenance(decoded, parsed.records, norad, null);
        }
      }
      const result = applyIncomingData(saved ? saved.input : raw, mode, 'local file ' + file.name, provenance);
      if (saved) {
        for (const [id, key] of Object.entries({ win: 'requestedWindow', alpha: 'alpha', dath: 'minAbsDeltaA', stale: 'maximumStaleDays', gapWarn: 'maximumGapFactor', orbitProfile: 'orbitProfile', detectorMode: 'detectorMode' })) {
          byId(id).value = String(saved.options[key]);
        }
        syncSensitivityFromControls();
        invalidateBenchmarkReport('Saved analysis settings restored. Run the labelled benchmark again.');
      }
      hint.textContent = result.merged
        ? `${file.name}: added ${result.added} new snapshot(s), ignored ${result.duplicates} exact duplicate(s), ${result.total} total.`
        : `${file.name}: accepted ${result.parsed.records.length} snapshot(s) as ${result.parsed.format}.`;
      if (saved) hint.textContent += saved.legacy
        ? ' Saved settings restored; this older package omitted the stale-age limit, so the current limit was retained.'
        : ' Saved input and analysis settings restored.';
      if (saved && saved.legacySchema) hint.textContent += ' Legacy package recalculated using the current precision and run-identity rules.';
      if (saved && saved.missingTleSource) hint.textContent += ' Original TLE lines are absent; previously discarded TLE epoch precision cannot be recovered.';
      run();
    } catch (error) {
      if (inputLoadIsCurrent(ticket)) hint.textContent = error && error.message ? error.message : String(error);
    } finally {
      if (ticket.sequence === inputLoadSequence) byId('fileInput').value = '';
    }
  }

  function getAnalysisOptions(overrides) {
    let requestedWindow = Number(byId('win').value);
    if (!Number.isFinite(requestedWindow)) requestedWindow = 6;
    requestedWindow = Math.min(100, Math.max(5, Math.round(requestedWindow)));

    let alpha = Number(byId('alpha').value);
    if (!Number.isFinite(alpha)) alpha = 0.1;
    alpha = Math.min(0.5, Math.max(0.01, alpha));

    let minAbsDeltaA = Number(byId('dath').value);
    if (!Number.isFinite(minAbsDeltaA) || minAbsDeltaA <= 0) minAbsDeltaA = 0.05;

    let maximumStaleDays = Number(byId('stale').value);
    if (!Number.isFinite(maximumStaleDays) || maximumStaleDays <= 0) maximumStaleDays = 30;

    let maximumGapFactor = Number(byId('gapWarn').value);
    if (!Number.isFinite(maximumGapFactor)) maximumGapFactor = 3;
    maximumGapFactor = Math.max(1.5, maximumGapFactor);

    const result = {
      requestedWindow,
      alpha,
      minAbsDeltaA,
      maximumStaleDays,
      maximumGapFactor,
      orbitProfile: byId('orbitProfile') ? byId('orbitProfile').value : 'auto',
      detectorMode: byId('detectorMode') ? byId('detectorMode').value : 'multivariate'
    };

    return Object.assign(result, overrides || {});
  }

  function renderExecutiveSummary(analysis) {
    const container = byId('executiveSummary');
    container.classList.add('visible');
    container.classList.remove('analysis-error');
    const objectLabel = analysis.objectName
      ? analysis.objectName + (analysis.objectId ? ' · ' + analysis.objectId : '')
      : analysis.objectId || 'Unknown object';
    const period = analysis.times && analysis.times.length
      ? formatDateOnly(analysis.times[0]) + ' to ' + formatDateOnly(analysis.times[analysis.times.length - 1])
      : 'n/a';

    byId('summaryObject').textContent = objectLabel;
    byId('summaryPeriod').textContent = period;
    byId('summarySnapshots').textContent = String(analysis.n);
    byId('summaryQuality').textContent = analysis.qualityStatus;
    byId('summaryResult').textContent = analysis.classification;
    byId('summaryEventCount').textContent = analysis.interpretable ? String(analysis.events.length) : 'suppressed';

    const hasEvent = Boolean(analysis.strongestEvent);
    byId('summaryEpochItem').hidden = !hasEvent;
    byId('summaryDeltaAItem').hidden = !hasEvent;
    if (hasEvent) {
      byId('summaryEpoch').textContent = fmtTime(analysis.strongestEvent.strongest.t);
      byId('summaryDeltaA').textContent = fmtNum(analysis.strongestEvent.netDeltaA, 4) + ' km net';
    }

    let interpretation;
    if (!analysis.interpretable) {
      interpretation = 'The workbench abstained. Candidate events are not reported until the data-quality and evaluated-history requirements are satisfied.';
    } else if (analysis.events.length === 1) {
      interpretation = 'One candidate event was identified from corroborating orbital-change signals. It warrants follow-up but does not confirm a maneuver.';
    } else if (analysis.events.length > 1) {
      interpretation = analysis.events.length + ' candidate events were identified. Review their supporting signals as screening evidence rather than confirmed maneuvers.';
    } else {
      interpretation = 'No eligible orbital-change event passed the current multivariate screening criteria.';
    }
    byId('summaryInterpretation').textContent = interpretation;

    byId('stickyObject').textContent = objectLabel;
    byId('stickyResult').textContent = analysis.classification;
    byId('stickyQuality').textContent = analysis.qualityStatus;
    byId('stickyResultBar').hidden = false;
  }

  function nearestTimeIndex(values, target) {
    const plotTimeMs = value => {
      if (typeof value !== 'string') return new Date(value).getTime();
      // Plotly hover events omit the zone and may use a space separator.
      const parsed = parseOmmEpochUtc(value.replace(' ', 'T'));
      return parsed ? parsed.t.getTime() : NaN;
    };
    const targetMs = plotTimeMs(target);
    let bestIndex = 0;
    let bestDistance = Infinity;
    values.forEach((value, index) => {
      const distance = Math.abs(plotTimeMs(value) - targetMs);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    });
    return bestIndex;
  }

  function bindChartSynchronization() {
    const orbit = byId('orbitChart');
    const rate = byId('rateChart');
    if (!orbit || !rate || !window.Plotly) return;

    [orbit, rate].forEach(chart => {
      if (typeof chart.removeAllListeners === 'function') {
        chart.removeAllListeners('plotly_relayout');
        chart.removeAllListeners('plotly_hover');
        chart.removeAllListeners('plotly_unhover');
        chart.removeAllListeners('plotly_click');
      }
    });

    function relayRange(target, update) {
      if (syncingCharts) return;
      const directRange = Array.isArray(update['xaxis.range']) ? update['xaxis.range'] : null;
      const range0 = directRange ? directRange[0] : update['xaxis.range[0]'];
      const range1 = directRange ? directRange[1] : update['xaxis.range[1]'];
      const auto = update['xaxis.autorange'];

      let command = null;
      if (auto === true) command = { 'xaxis.autorange': true };
      else if (range0 !== undefined && range1 !== undefined) {
        command = { 'xaxis.range': [range0, range1], 'xaxis.autorange': false };
      }
      if (!command) return;

      syncingCharts = true;
      window.Plotly.relayout(target, command).catch(() => {}).finally(() => { syncingCharts = false; });
    }

    orbit.on('plotly_relayout', update => relayRange(rate, update));
    rate.on('plotly_relayout', update => relayRange(orbit, update));

    function relayHover(source, target, event) {
      if (syncingHover || !event || !event.points || !event.points.length || !target.data?.[0]?.x?.length) return;
      const point = event.points[0];
      const sourceEpoch = source.data?.[point.curveNumber]?.x?.[point.pointNumber] ?? point.x;
      const pointIndex = nearestTimeIndex(target.data[0].x, sourceEpoch);
      const targetEpochMs = new Date(target.data[0].x[pointIndex]).getTime();
      if (!Number.isFinite(targetEpochMs)) return;
      syncingHover = true;
      // Plotly needs a linear UTC date value to draw both the tooltip and spike.
      try { window.Plotly.Fx.hover(target, { xval: targetEpochMs }, ['xy']); }
      finally { syncingHover = false; }
    }

    orbit.on('plotly_hover', event => relayHover(orbit, rate, event));
    rate.on('plotly_hover', event => relayHover(rate, orbit, event));
    orbit.on('plotly_unhover', () => window.Plotly.Fx.unhover(rate));
    rate.on('plotly_unhover', () => window.Plotly.Fx.unhover(orbit));
    [orbit, rate].forEach(chart => chart.on('plotly_click', event => {
      const point = event?.points?.[0];
      if (!lastAnalysis?.events?.length || !point) return;
      const epoch = chart.data?.[point.curveNumber]?.x?.[point.pointNumber] ?? point.x;
      const index = nearestTimeIndex(lastAnalysis.times, epoch);
      const eventIndex = lastAnalysis.events.findIndex(candidate => candidate.flags.some(flag => flag.idx === index));
      if (eventIndex >= 0) selectEvent(eventIndex);
    }));
  }

  function renderAccessibleChartData(analysis) {
    const body = byId('chartDataBody');
    if (!body) return;

    if (!analysis || !Array.isArray(analysis.rows) || !analysis.rows.length) {
      body.innerHTML = '<tr><td colspan="9" class="muted">No chart data is available.</td></tr>';
      return;
    }

    body.innerHTML = analysis.rows.map(row => {
      const status = row.flagged
        ? 'Candidate observation'
        : row.evaluated
          ? 'Evaluated'
          : row.pairEligible
            ? 'Calibration'
            : Number.isFinite(row.dt)
              ? 'Excluded gap'
              : 'Initial record';
      return `<tr>
        <td class="mono">${escapeHtml(fmtTime(row.t))}</td>
        <td>${escapeHtml(fmtNum(row.a, 4))} km</td>
        <td>${Number.isFinite(row.dA) ? escapeHtml(fmtNum(row.dA, 4)) + ' km' : 'n/a'}</td>
        <td>${Number.isFinite(row.dt) ? escapeHtml(fmtNum(row.dt, 3)) + ' days' : 'n/a'}</td>
        <td>${Number.isFinite(row.dARate) ? escapeHtml(fmtNum(row.dARate, 5)) + ' km/day' : 'n/a'}</td>
        <td>${Number.isFinite(row.radialKm) ? escapeHtml(fmtNum(row.radialKm, 3)) + ' km' : 'n/a'}</td>
        <td>${Number.isFinite(row.alongKm) ? escapeHtml(fmtNum(row.alongKm, 3)) + ' km' : 'n/a'}</td>
        <td>${Number.isFinite(row.crossKm) ? escapeHtml(fmtNum(row.crossKm, 3)) + ' km' : 'n/a'}</td>
        <td>${escapeHtml(status)}</td>
      </tr>`;
    }).join('');
  }

  async function renderCharts(analysis) {
    renderAccessibleChartData(analysis);
    ['orbitChart', 'rateChart'].forEach(id => {
      const container = byId(id);
      if (container) container.innerHTML = '<div class="chart-fallback small muted">Loading the local chart renderer…</div>';
    });

    try {
      await ensurePlotlyLoaded();
    } catch (error) {
      if (lastAnalysis !== analysis) return;
      const message = error && error.message ? error.message : String(error);
      ['orbitChart', 'rateChart'].forEach(id => {
        const container = byId(id);
        if (container) container.innerHTML = '<div class="chart-fallback small muted">Charts are unavailable: ' + escapeHtml(message) + ' The tabular chart data remains available below.</div>';
      });
      byId('resetChartZoom').disabled = true;
      return;
    }
    if (lastAnalysis !== analysis) return;

    const palette = plotPalette();
    const candidateShapes = chartEvidenceShapes(analysis);

    const orbitData = [{
      x: analysis.times.map(fmtTime),
      y: analysis.semiMajorAxes,
      mode: 'lines+markers',
      name: 'Semi-major axis',
      line: { width: 1.8, color: palette.measurement },
      marker: { size: 4, color: palette.measurement },
      customdata: analysis.deltaA,
      hovertemplate: '%{x} UTC<br>a = %{y:.4f} km<br>Δa = %{customdata:.4f} km<extra></extra>'
    }];

    const eligibleRate = analysis.deltaARate.map((value, index) => analysis.pairEligible[index] ? value : null);
    const excludedRate = analysis.deltaARate.map((value, index) => index > 0 && !analysis.pairEligible[index] ? value : null);
    const rateData = [{
      x: analysis.times.map(fmtTime),
      y: eligibleRate,
      mode: 'lines+markers',
      name: 'Eligible Δa/Δt',
      line: { width: 1.4, color: palette.measurement },
      marker: { size: 4, color: palette.measurement },
      customdata: analysis.deltaA,
      hovertemplate: '%{x} UTC<br>Δa/Δt = %{y:.4f} km/day<br>Δa = %{customdata:.4f} km<extra></extra>'
    }];

    if (analysis.bandLower.some(value => value !== null)) {
      rateData.push({
        x: analysis.times.map(fmtTime),
        y: analysis.bandLower,
        mode: 'lines',
        name: 'Band lower',
        line: { width: 0.5, color: palette.measurement },
        hoverinfo: 'skip',
        showlegend: false
      });
      rateData.push({
        x: analysis.times.map(fmtTime),
        y: analysis.bandUpper,
        mode: 'lines',
        name: 'Rolling empirical band',
        line: { width: 0.5, color: palette.measurement },
        fill: 'tonexty',
        fillcolor: palette.band,
        hoverinfo: 'skip'
      });
    }

    if (excludedRate.some(Number.isFinite)) {
      rateData.push({
        x: analysis.times.map(fmtTime),
        y: excludedRate,
        mode: 'markers',
        name: 'Excluded gap',
        marker: { size: 8, symbol: 'circle-open', color: palette.muted },
        customdata: analysis.rows.map(row => row.dt),
        hovertemplate: '%{x} UTC<br>Excluded pair gap = %{customdata:.2f} days<extra></extra>'
      });
    }

    if (analysis.flags.length) {
      rateData.push({
        x: analysis.flags.map(flag => fmtTime(flag.t)),
        y: analysis.flags.map(flag => flag.dARate),
        mode: 'markers',
        name: 'Candidate epoch',
        marker: { size: 10, symbol: 'x', color: palette.candidate },
        hovertemplate: '%{x} UTC<br>Δa/Δt = %{y:.4f} km/day<extra>Candidate</extra>'
      });
    }

    const common = {
      xaxis: { title: { text: 'Epoch UTC' }, type: 'date', automargin: true,
        gridcolor: palette.grid, zerolinecolor: palette.grid, showspikes: true,
        spikemode: 'across', spikesnap: 'data', spikecolor: palette.crosshair, spikethickness: 1 },
      paper_bgcolor: palette.paper, plot_bgcolor: palette.paper,
      font: { color: palette.text, family: 'system-ui, sans-serif', size: 12 },
      hoverlabel: { bgcolor: palette.paper, font: { color: palette.text }, bordercolor: palette.grid },
      hovermode: 'x unified',
      uirevision: analysis.runId,
      shapes: candidateShapes
    };

    const orbitPromise = safePlot('orbitChart', orbitData, {
      ...common,
      margin: { l: 72, r: 28, t: 58, b: 48 },
      title: { text: 'Semi-major axis over time', x: 0.02, xanchor: 'left', font: { size: 15 } },
      showlegend: false,
      yaxis: { title: { text: 'Semi-major axis [km]' }, zeroline: false, automargin: true, gridcolor: palette.grid }
    });

    const ratePromise = safePlot('rateChart', rateData, {
      ...common,
      margin: { l: 72, r: 28, t: 86, b: 48 },
      title: { text: 'Sampling-normalised change and empirical band', x: 0.02, xanchor: 'left', y: 0.98, font: { size: 15 } },
      legend: { orientation: 'h', x: 0, y: 1.20, xanchor: 'left', yanchor: 'top' },
      yaxis: { title: { text: 'Δa/Δt [km/day]' }, zeroline: true, automargin: true, gridcolor: palette.grid, zerolinecolor: palette.grid }
    });

    if (orbitPromise && ratePromise) {
      await Promise.all([orbitPromise, ratePromise]);
      if (lastAnalysis !== analysis) return;
      bindChartSynchronization();
      updateChartEvidence();
      byId('resetChartZoom').disabled = false;
    }
  }

  function resetChartZoom() {
    if (!window.Plotly || !lastAnalysis) return;
    syncingCharts = true;
    Promise.all([
      window.Plotly.relayout('orbitChart', { 'xaxis.autorange': true, 'yaxis.autorange': true }),
      window.Plotly.relayout('rateChart', { 'xaxis.autorange': true, 'yaxis.autorange': true })
    ]).finally(() => { syncingCharts = false; });
  }

  function toggleChartSize() {
    const card = byId('chartCard');
    if (!card) return;
    const expanded = card.classList.toggle('expanded');
    byId('toggleChartSize').textContent = expanded ? 'Compact charts' : 'Expand charts';
    if (window.Plotly) {
      window.setTimeout(() => {
        ['orbitChart', 'rateChart'].forEach(id => {
          const chart = byId(id);
          if (chart && chart.data) window.Plotly.Plots.resize(chart);
        });
      }, 80);
    }
  }

  function renderFlagTable(events) {
    const wrap = byId('flagTableWrap');
    const body = byId('flagTableBody');
    const epochDetails = byId('epochDetails');
    const epochWrap = byId('epochTableWrap');

    if (!events.length) {
      wrap.style.display = 'none';
      body.innerHTML = '';
      epochDetails.style.display = 'none';
      epochWrap.innerHTML = '';
      return;
    }

    body.innerHTML = events.map((event, index) => {
      const features = event.features.map(feature => `<span class="feature-chip">${escapeHtml(FEATURE_LABELS[feature] || feature)}</span>`).join('');
      const interval = fmtTime(event.start) === fmtTime(event.end)
        ? fmtTime(event.start)
        : fmtTime(event.start) + '<br><span class="muted">to ' + fmtTime(event.end) + '</span>';
      return `
        <tr>
          <td><button class="table-action" type="button" data-event-index="${index}" aria-pressed="false" aria-controls="eventInspector">${escapeHtml(event.id)}</button></td>
          <td class="mono">${interval}</td>
          <td>${escapeHtml(event.direction)}</td>
          <td>${escapeHtml(fmtNum(event.netDeltaA, 4))} km</td>
          <td>${escapeHtml(event.tier)} (${escapeHtml(fmtNum(event.score, 2))})</td>
          <td><div class="event-features">${features}</div></td>
        </tr>
      `;
    }).join('');

    body.querySelectorAll('[data-event-index]').forEach(button => {
      button.addEventListener('click', function () {
        const index = Number(this.getAttribute('data-event-index'));
        const event = lastAnalysis && lastAnalysis.events ? lastAnalysis.events[index] : null;
        if (event) selectEvent(index);
      });
    });

    epochWrap.innerHTML = `
      <table>
        <thead><tr><th>Epoch</th><th>Δa</th><th>Score</th><th>Supporting signals</th></tr></thead>
        <tbody>${events.flatMap(event => event.flags.map(flag => `
          <tr>
            <td class="mono">${escapeHtml(fmtTime(flag.t))}</td>
            <td>${escapeHtml(fmtNum(flag.dA, 4))} km</td>
            <td>${escapeHtml(fmtNum(flag.severityScore, 2))}</td>
            <td>${escapeHtml(flag.breachedFeatures.map(feature => FEATURE_LABELS[feature] || feature).join(', '))}</td>
          </tr>
        `)).join('')}</tbody>
      </table>
    `;
    epochDetails.style.display = 'block';
    wrap.style.display = 'block';
  }

  function renderAnalysis(analysis) {
    byId('flagCopyHint').textContent = '';
    byId('exportHint').textContent = '';
    renderFlagTable([]);
    resetEventInspector();
    renderConsoleSummary(analysis);
    setCopyFlagsEnabled(false);

    if (analysis.error) {
      byId('parseSummary').textContent = describeParse(analysis.parsed);
      byId('pairCount').textContent = `Accepted ${analysis.n} valid snapshot(s); rejected ${analysis.rejectedCount}.`;
      byId('audit').textContent = '';
      byId('flags').textContent = analysis.message;
      byId('flagCount').textContent = '';
      byId('executiveSummary').classList.add('visible', 'analysis-error');
      byId('stickyResultBar').hidden = true;
      renderQuality(analysis.qualityItems || []);
      renderResult('err', 'Analysis unavailable', analysis.message, []);
      setStatus('err', analysis.errorKind === 'too-few' ? 'Too few valid snapshots' : 'Input validation failed');
      setChartMessage('No validated screening analysis is available for this input.');
      clearOrbitContext('No orbit context is available for this input.');
      resetEventInspector('No validated analysis is available. Correct the input, then run screening again.');
      setAnalysisExportEnabled(false);
      setRunButtonState('error');
      byId('candidateEventsCard').hidden = true;
      return;
    }

    byId('parseSummary').textContent = describeParse(analysis.parsed);
    byId('pairCount').textContent = `Accepted ${analysis.n} unique snapshots; evaluated ${analysis.totalEvaluated} sequential point(s); compared ${analysis.sgp4PairCount} pair(s) with SGP4; excluded ${analysis.excludedGapCount} oversized gap(s).`;
    renderQuality(analysis.qualityItems);
    renderExecutiveSummary(analysis);
    renderCharts(analysis).catch(error => {
      if (lastAnalysis !== analysis) return;
      const message = error && error.message ? error.message : String(error);
      ['orbitChart', 'rateChart'].forEach(id => {
        const container = byId(id);
        if (container) container.innerHTML = '<div class="chart-fallback small muted">Charts are unavailable: ' + escapeHtml(message) + ' The tabular chart data remains available below.</div>';
      });
      byId('resetChartZoom').disabled = true;
    });

    const resultDetails = [
      { key: 'Orbit profile', value: analysis.profileName },
      { key: 'Detector mode', value: analysis.detectorModeUsed }
    ];
    renderResult(analysis.resultKind, analysis.resultTitle, analysis.resultBody, resultDetails);

    if (analysis.hardQualityErrors.length) setStatus('err', 'Abstain, poor data quality');
    else if (!analysis.interpretable) setStatus('err', 'Abstain, insufficient history');
    else if (analysis.events.length) setStatus('warn', 'Candidate events identified');
    else if (analysis.qualityWarnings.length) setStatus('warn', 'No event, data warnings');
    else setStatus('ok', 'No candidate events for current settings');

    if (!analysis.interpretable) {
      byId('flagCount').textContent = '(suppressed)';
      byId('flags').textContent = 'Candidate events are suppressed because this run abstained. Resolve the data-quality errors or provide enough eligible history.';
    } else if (!analysis.events.length) {
      byId('flagCount').textContent = '(0 events)';
      byId('flags').textContent = 'No corroborated multivariate event passed the current criteria.';
    } else {
      byId('flagCount').textContent = analysis.events.length === 1 ? '(1 event)' : '(' + analysis.events.length + ' events)';
      byId('flags').textContent = analysis.events.map(event => {
        return event.id +
          '  interval=' + fmtTime(event.start) + (fmtTime(event.end) !== fmtTime(event.start) ? ' to ' + fmtTime(event.end) : '') +
          '  direction=' + event.direction +
          '  netΔa=' + event.netDeltaA.toFixed(4) + ' km' +
          '  tier=' + event.tier + ' (' + event.score.toFixed(2) + ')' +
          '  points=' + event.pointCount +
          '  signals=' + event.features.map(feature => FEATURE_LABELS[feature] || feature).join(', ');
      }).join('\n');
    }

    renderFlagTable(analysis.events);
    byId('candidateEventsCard').hidden = !(analysis.interpretable && analysis.events.length > 0);
    setCopyFlagsEnabled(analysis.interpretable && analysis.events.length > 0);

    byId('audit').textContent =
      'run=' + analysis.runId +
      ', method=' + METHOD_VERSION +
      ', workbench=' + WORKBENCH_VERSION +
      ', source=' + analysis.sourceLabel +
      ', acquisition=' + provenanceSummary(analysis.dataProvenance) +
      ', format=' + analysis.inputFormat +
      ', profile=' + analysis.profileName +
      ', mode=' + analysis.detectorModeUsed +
      ', alpha=' + analysis.alpha.toFixed(2) +
      ', primary coverage=' + (Number.isFinite(analysis.observedCoverage) ? analysis.observedCoverage.toFixed(2) : 'n/a') +
      ', window=' + analysis.window +
      ', snapshots=' + analysis.n +
      ', evaluated=' + analysis.totalEvaluated +
      ', SGP4 pairs=' + analysis.sgp4PairCount +
      ', events=' + analysis.events.length +
      ', excluded gaps=' + analysis.excludedGapCount +
      ', span=' + analysis.spanDays.toFixed(2) + ' days';

    setAnalysisExportEnabled(true);
    setRunButtonState('current');
    if (analysis.strongestEvent) selectEvent(analysis.events.indexOf(analysis.strongestEvent));
    else {
      resetEventInspector(analysis.interpretable
        ? 'No candidate event passed the current screening criteria. Review the evidence charts and data quality.'
        : 'This run abstained. Candidate events are suppressed until the history and data-quality requirements are satisfied.');
      updateChartEvidence();
      queueSingleOrbit(
        analysis.records[Math.floor(analysis.records.length / 2)],
        analysis.interpretable
          ? 'No candidate event selected. Showing one mid-series element set for visual context.'
          : 'This run abstained. Showing one mid-series element set for visual context only.'
      );
    }
  }

  function run() {
    const raw = byId('tles').value.trim();
    const sourceLabel = currentInputSourceLabel || (
      currentPublicNorad
        ? 'current public OMM snapshot'
        : currentExampleKey
          ? 'built-in synthetic demo history'
          : 'pasted orbital-element history'
    );

    try {
      lastAnalysis = analyzeRaw(raw, sourceLabel);
      if (!lastAnalysis.error) {
        lastAnalysis.analysisOptions = getAnalysisOptions();
        const parsed = parseInput(raw);
        // A programmatic edit without an input event must also lose stale lineage.
        if (currentInputProvenance && currentInputProvenance.input_fingerprint.value !== normalizedInputFingerprint(parsed.records).value) {
          currentInputProvenance = null;
        }
        const inputProvenance = validateInputProvenance(currentInputProvenance, parsed.records);
        lastAnalysis.dataProvenance = inputProvenance
          ? makeInputProvenance(lastAnalysis.records, inputProvenance.sources)
          : null;
        if (lastAnalysis.dataProvenance && lastAnalysis.dataProvenance.sources.some(source => source.kind === 'space-track-history')) {
          lastAnalysis.evidenceText = lastAnalysis.evidenceText.replace('Data attribution: not applicable',
            'Data attribution: Basic SSA data from Space-Track.org, operated by USSPACECOM');
        }
        lastAnalysis.evidenceText += '\n\n' + provenanceEvidence(lastAnalysis.dataProvenance);
      }
      renderAnalysis(lastAnalysis);
    } catch (error) {
      resetOutputOnly();
      byId('executiveSummary').classList.add('visible', 'analysis-error');
      setAnalysisExportEnabled(false);
      setCopyFlagsEnabled(false);
      setStatus('err', 'Unexpected analysis error');
      byId('flags').textContent = 'Internal error: ' + (error && error.message ? error.message : String(error));
      byId('flagCount').textContent = '';
      renderQuality([{ kind: 'err', label: 'Runtime error', value: error && error.message ? error.message : String(error) }]);
      renderResult('err', 'Analysis failed', 'An unexpected error occurred. Check the input and try again.', []);
      setChartMessage('Analysis failed. Review the error message above.');
      clearOrbitContext('Analysis failed, so no orbit context is available.');
      setRunButtonState('error');
    }
  }

  function solveKepler(meanAnomaly, eccentricity) {
    if (!Number.isFinite(meanAnomaly) || !Number.isFinite(eccentricity) || eccentricity < 0 || eccentricity >= 1) {
      throw new Error('Orbit context requires a finite elliptic orbit with 0 <= eccentricity < 1.');
    }
    // E - e sin(E) is strictly increasing for an elliptic orbit. Safeguard
    // Newton steps with its [-pi, pi] bracket, including near-parabolic cases.
    const turn = 2 * Math.PI;
    const mean = ((meanAnomaly + Math.PI) % turn + turn) % turn - Math.PI;
    let lower = -Math.PI;
    let upper = Math.PI;
    let eccentricAnomaly = mean;
    for (let iteration = 0; iteration < 80; iteration++) {
      const residual = eccentricAnomaly - eccentricity * Math.sin(eccentricAnomaly) - mean;
      if (Math.abs(residual) <= 1e-14) return eccentricAnomaly + (meanAnomaly - mean);
      if (residual > 0) upper = eccentricAnomaly;
      else lower = eccentricAnomaly;
      const next = eccentricAnomaly - residual / (1 - eccentricity * Math.cos(eccentricAnomaly));
      eccentricAnomaly = Number.isFinite(next) && next > lower && next < upper ? next : (lower + upper) / 2;
    }
    throw new Error('Orbit context could not converge for these elements.');
  }

  function orbitCoordinatesFromElements(record, count) {
    if (!record || !record.elements) return null;

    const eccentricity = record.elements.ecc;
    if (!Number.isFinite(eccentricity) || eccentricity < 0 || eccentricity >= 1 || !Number.isFinite(record.a) || record.a <= 0) return null;
    const semiMajorAxis = record.a;
    const inclination = radians(record.elements.incDeg);
    const raan = radians(record.elements.raanDeg);
    const argumentOfPerigee = radians(record.elements.argPerDeg);
    const initialMeanAnomaly = radians(record.elements.meanAnomDeg);

    const cosRaan = Math.cos(raan);
    const sinRaan = Math.sin(raan);
    const cosInclination = Math.cos(inclination);
    const sinInclination = Math.sin(inclination);
    const cosArgument = Math.cos(argumentOfPerigee);
    const sinArgument = Math.sin(argumentOfPerigee);
    const x = [];
    const y = [];
    const z = [];

    for (let index = 0; index <= count; index++) {
      const meanAnomaly = initialMeanAnomaly + 2 * Math.PI * index / count;
      const eccentricAnomaly = solveKepler(meanAnomaly, eccentricity);
      const xOrbital = semiMajorAxis * (Math.cos(eccentricAnomaly) - eccentricity);
      const yOrbital = semiMajorAxis * Math.sqrt(1 - eccentricity * eccentricity) * Math.sin(eccentricAnomaly);
      const x1 = cosArgument * xOrbital - sinArgument * yOrbital;
      const y1 = sinArgument * xOrbital + cosArgument * yOrbital;
      x.push(cosRaan * x1 - sinRaan * cosInclination * y1);
      y.push(sinRaan * x1 + cosRaan * cosInclination * y1);
      z.push(sinInclination * y1);
    }

    return { x, y, z, point: { x: x[0], y: y[0], z: z[0] } };
  }

  function earthSphereTrace() {
    const radius = 6378.137;
    const lonSteps = 30;
    const latSteps = 18;
    const x = [];
    const y = [];
    const z = [];
    for (let latIndex = 0; latIndex <= latSteps; latIndex++) {
      const latitude = -Math.PI / 2 + Math.PI * latIndex / latSteps;
      const xRow = [];
      const yRow = [];
      const zRow = [];
      for (let lonIndex = 0; lonIndex <= lonSteps; lonIndex++) {
        const longitude = 2 * Math.PI * lonIndex / lonSteps;
        xRow.push(radius * Math.cos(latitude) * Math.cos(longitude));
        yRow.push(radius * Math.cos(latitude) * Math.sin(longitude));
        zRow.push(radius * Math.sin(latitude));
      }
      x.push(xRow);
      y.push(yRow);
      z.push(zRow);
    }
    return {
      type: 'surface',
      x,
      y,
      z,
      name: 'Earth reference sphere',
      showscale: false,
      hoverinfo: 'skip',
      opacity: 0.72,
      colorscale: [[0, '#1e3a5f'], [1, '#3b82a0']],
      showlegend: false
    };
  }

  function orbitPlotLayout(title) {
    const palette = plotPalette();
    return {
      title: { text: title, x: 0.02, xanchor: 'left', font: { size: 15 } },
      margin: { l: 0, r: 0, t: 52, b: 0 },
      paper_bgcolor: palette.paper,
      plot_bgcolor: palette.paper,
      font: { color: palette.text },
      legend: { orientation: 'h', x: 0, y: 1.03 },
      scene: {
        aspectmode: 'data',
        bgcolor: palette.paper,
        xaxis: { title: { text: 'ECI x [km]' }, gridcolor: palette.grid, zerolinecolor: palette.grid },
        yaxis: { title: { text: 'ECI y [km]' }, gridcolor: palette.grid, zerolinecolor: palette.grid },
        zaxis: { title: { text: 'ECI z [km]' }, gridcolor: palette.grid, zerolinecolor: palette.grid },
        camera: { eye: { x: 1.45, y: 1.45, z: 1.0 } }
      }
    };
  }

  function clearOrbitContext(message) {
    pendingOrbitContext = null;
    orbitPlotReady = false;
    byId('orbitHint').textContent = message || 'No orbit context available.';
    byId('fitOrbit').disabled = true;
    if (window.Plotly) window.Plotly.purge('orbitViewer');
    byId('orbitViewer').innerHTML = '';
  }

  function orbitalPeriodMinutes(record) {
    return record && Number.isFinite(record.meanMotion) ? 1440 / record.meanMotion : NaN;
  }

  function queueOrbitComparisonForEvent(event) {
    if (!lastAnalysis || !event || !Array.isArray(event.flags) || !event.flags.length) return;
    const beforeIndex = Number.isInteger(event.contextBeforeIndex)
      ? event.contextBeforeIndex
      : Math.max(0, event.flags[0].idx - 1);
    const afterIndex = Number.isInteger(event.contextAfterIndex)
      ? event.contextAfterIndex
      : event.flags[event.flags.length - 1].idx;
    const before = lastAnalysis.records[beforeIndex] || null;
    const after = lastAnalysis.records[afterIndex] || null;
    pendingOrbitContext = { type: 'comparison', before, after, event };
    byId('orbitHint').textContent = 'Open this section to compare the pre-event record with the final record in grouped event ' + event.id + '.';
    if (byId('orbitDetails').open) renderPendingOrbitContext();
  }

  function queueSingleOrbit(record, message) {
    pendingOrbitContext = { type: 'single', record, message };
    byId('orbitHint').textContent = 'Open this section to load approximate orbit context.';
    if (byId('orbitDetails').open) renderPendingOrbitContext();
  }

  async function renderPendingOrbitContext() {
    if (!pendingOrbitContext || !byId('orbitDetails').open) return;
    const context = pendingOrbitContext;
    if (!window.Plotly) {
      byId('orbitHint').textContent = 'Loading the local 3D renderer…';
      try {
        await ensurePlotlyLoaded();
      } catch (error) {
        if (pendingOrbitContext !== context) return;
        byId('orbitHint').textContent = 'The local Plotly dependency could not be loaded, so 3D orbit context is unavailable.';
        return;
      }
    }
    if (pendingOrbitContext !== context || !byId('orbitDetails').open) return;
    if (context.type === 'comparison') {
      await drawOrbitComparison(context.before, context.after, context.event);
    } else {
      await drawSingleOrbit(context.record, context.message);
    }
  }

  async function drawOrbitComparison(before, after, event) {
    if (!before || !after || !before.elements || !after.elements) {
      await drawSingleOrbit(after || before, 'A complete before-and-after pair was unavailable. Showing one element set only.');
      return;
    }

    const beforeOrbit = orbitCoordinatesFromElements(before, 240);
    const afterOrbit = orbitCoordinatesFromElements(after, 240);
    if (!beforeOrbit || !afterOrbit) {
      byId('orbitHint').textContent = 'Could not build the approximate before-and-after orbit paths.';
      return;
    }

    const traces = [
      earthSphereTrace(),
      {
        type: 'scatter3d', mode: 'lines', name: 'Pre-event record',
        x: beforeOrbit.x, y: beforeOrbit.y, z: beforeOrbit.z,
        line: { width: 5, color: plotPalette().measurement }, hovertemplate: 'Pre-event orbit<extra></extra>'
      },
      {
        type: 'scatter3d', mode: 'lines', name: 'Final event record',
        x: afterOrbit.x, y: afterOrbit.y, z: afterOrbit.z,
        line: { width: 5, color: plotPalette().candidate }, hovertemplate: 'Final event orbit<extra></extra>'
      },
      {
        type: 'scatter3d', mode: 'markers+text', name: 'Element epochs',
        x: [beforeOrbit.point.x, afterOrbit.point.x],
        y: [beforeOrbit.point.y, afterOrbit.point.y],
        z: [beforeOrbit.point.z, afterOrbit.point.z],
        text: ['Pre-event', 'Final event'], textposition: 'top center',
        marker: { size: 5, color: [plotPalette().measurement, plotPalette().candidate], line: { color: plotPalette().paper, width: 1 } },
        hovertemplate: '%{text} element epoch<extra></extra>'
      }
    ];

    await window.Plotly.newPlot('orbitViewer', traces, orbitPlotLayout('Approximate grouped-event orbit context'), {
      displayModeBar: false,
      responsive: true
    });
    orbitPlotReady = true;
    byId('fitOrbit').disabled = false;
    const periodChange = orbitalPeriodMinutes(after) - orbitalPeriodMinutes(before);
    const netDeltaA = event && Number.isFinite(event.netDeltaA) ? event.netDeltaA : after.a - before.a;
    const eventLabel = event && event.id ? event.id : 'selected event';
    const intervalText = event
      ? ' Event interval ' + fmtTime(event.start) + (fmtTime(event.end) !== fmtTime(event.start) ? ' to ' + fmtTime(event.end) : '') + '.'
      : '';
    const strongestText = event && event.strongest ? ' Strongest flagged epoch ' + fmtTime(event.strongest.t) + '.' : '';
    byId('orbitHint').textContent =
      eventLabel + ' grouped context. Pre-event ' + fmtTime(before.t) + ': a=' + fmtNum(before.a, 3) + ' km. ' +
      'Final event record ' + fmtTime(after.t) + ': a=' + fmtNum(after.a, 3) + ' km. ' +
      'Net Δa=' + fmtNum(netDeltaA, 4) + ' km; Δperiod=' + fmtNum(periodChange, 4) + ' minutes.' +
      intervalText + strongestText + ' Visual context only.';
  }

  async function drawSingleOrbit(record, message) {
    if (!record || !record.elements) {
      byId('orbitHint').textContent = 'No usable orbital elements are available for the 3D context panel.';
      return;
    }

    const orbit = orbitCoordinatesFromElements(record, 240);
    if (!orbit) {
      byId('orbitHint').textContent = 'Could not build approximate orbit positions from the selected element set.';
      return;
    }

    const traces = [
      earthSphereTrace(),
      {
        type: 'scatter3d', mode: 'lines', name: 'Approximate orbit',
        x: orbit.x, y: orbit.y, z: orbit.z,
        line: { width: 5, color: plotPalette().measurement }, hovertemplate: 'Approximate orbit<extra></extra>'
      },
      {
        type: 'scatter3d', mode: 'markers+text', name: 'Selected epoch',
        x: [orbit.point.x], y: [orbit.point.y], z: [orbit.point.z],
        text: [record.name || record.satId || 'Selected epoch'], textposition: 'top center',
        marker: { size: 6, color: plotPalette().candidate, line: { color: plotPalette().paper, width: 1 } },
        hovertemplate: '%{text}<extra></extra>'
      }
    ];

    await window.Plotly.newPlot('orbitViewer', traces, orbitPlotLayout('Approximate orbit context'), {
      displayModeBar: false,
      responsive: true
    });
    orbitPlotReady = true;
    byId('fitOrbit').disabled = false;
    byId('orbitHint').textContent = message || 'Showing approximate orbit context. Visual context only.';
  }

  function fitOrbitView() {
    if (!orbitPlotReady || !window.Plotly) return;
    window.Plotly.relayout('orbitViewer', {
      'scene.aspectmode': 'data',
      'scene.camera.eye': { x: 1.45, y: 1.45, z: 1.0 }
    });
  }

  function setDefaultHistoryDates() {
    const end = new Date(Date.now() - DAY_MS);
    const start = new Date(end.getTime() - 30 * DAY_MS);
    const maximumDate = end.toISOString().slice(0, 10);
    byId('historyEnd').max = maximumDate;
    byId('historyStart').max = maximumDate;
    byId('historyEnd').value = maximumDate;
    byId('historyStart').value = start.toISOString().slice(0, 10);
  }

  function scrollToResults() {
    const target = byId('executiveSummary').classList.contains('visible')
      ? byId('executiveSummary')
      : byId('resultBox');
    if (window.innerWidth >= 1100 && typeof target.getBoundingClientRect === 'function') {
      const rect = target.getBoundingClientRect();
      if (rect.top >= 0 && rect.top < window.innerHeight * 0.6) return;
    }
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
    target.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
  }

  function demoLabel(kind) {
    return kind === 'geo' ? 'GEO station-keeping demonstration' :
      kind === 'quiet' ? 'Quiet non-event demonstration' :
      kind === 'sparse' ? 'Sparse-history abstention demonstration' :
      'LEO candidate demonstration';
  }

  function updateDemoControls(kind) {
    const selected = ['leo', 'geo', 'quiet', 'sparse'].includes(kind) ? kind : 'leo';
    byId('demoSelect').value = selected;
    byId('demoHeading').textContent = demoLabel(selected);
    byId('tryDemo').textContent = 'Run demonstration';
  }

  function showDemoNotice() {
    const label = demoLabel(currentExampleKey || 'leo');
    byId('demoNoticeTitle').textContent = label + ' analysed.';
    if (lastAnalysis && !lastAnalysis.error) {
      const eventText = lastAnalysis.interpretable
        ? (lastAnalysis.events.length === 1 ? '1 candidate event' : lastAnalysis.events.length + ' candidate events')
        : 'analysis abstained';
      byId('demoNoticeSummary').textContent = lastAnalysis.classification + ' · ' + lastAnalysis.n + ' snapshots · ' + lastAnalysis.qualityStatus + ' · ' + eventText + '.';
    } else {
      byId('demoNoticeSummary').textContent = 'The result is ready below.';
    }
    byId('demoNotice').classList.add('visible');
  }

  function hideDemoNotice() {
    byId('demoNotice').classList.remove('visible');
  }

  function showHistoryFailure(error) {
    const hint = byId('historyFetchHint');
    hint.textContent = '';
    hint.classList.add('history-error');

    const message = document.createElement('div');
    const status = error && Number.isFinite(error.status) ? error.status : null;
    const detail = error && error.message ? error.message : String(error);

    if (status === 503) {
      message.textContent = 'Historical retrieval is unavailable on the server. ' + detail;
    } else if (status === 429) {
      message.textContent = detail + ' The current input has not been changed.';
    } else {
      message.textContent = 'Historical data could not be loaded. ' + detail + ' The current input has not been changed.';
    }
    hint.appendChild(message);

    if (currentExampleKey && byId('tles').value.trim()) {
      const actions = document.createElement('div');
      actions.className = 'history-error-actions actions';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'compact';
      button.textContent = lastAnalysis && !lastAnalysis.error ? 'View demonstration result' : 'Run demonstration analysis';
      button.addEventListener('click', () => {
        if (!lastAnalysis || lastAnalysis.error) run();
        scrollToResults();
      });
      actions.appendChild(button);
      hint.appendChild(actions);
    }
  }

  async function loadHistoricalData() {
    const hint = byId('historyFetchHint');
    const button = byId('loadHistory');
    const norad = byId('publicNorad').value.trim();
    const start = byId('historyStart').value;
    const end = byId('historyEnd').value;
    hint.classList.remove('history-error');

    if (!/^\d{1,9}$/.test(norad)) {
      hint.textContent = 'Enter a NORAD catalog number containing 1 to 9 digits.';
      return;
    }
    if (!start || !end || new Date(start) > new Date(end)) {
      hint.textContent = 'Choose a valid start and end date.';
      return;
    }
    const latestHistoricalDate = new Date(Date.now() - DAY_MS).toISOString().slice(0, 10);
    if (end > latestHistoricalDate) {
      hint.textContent = 'Historical retrieval must end no later than yesterday. Use the current snapshot for today.';
      return;
    }
    const span = (new Date(end + 'T00:00:00Z') - new Date(start + 'T00:00:00Z')) / DAY_MS;
    if (span >= MAX_HISTORY_RANGE_DAYS) {
      hint.textContent = 'Choose a history range of no more than ' + MAX_HISTORY_RANGE_DAYS + ' calendar days, including both dates.';
      return;
    }

    const ticket = beginInputLoad();
    button.disabled = true;
    hint.textContent = 'Requesting historical OMM records…';
    try {
      const url = new URL(HISTORY_ENDPOINT, document.baseURI || window.location.href);
      url.searchParams.set('norad', norad);
      url.searchParams.set('start', start);
      url.searchParams.set('end', end);
      const response = await fetchJsonWithTimeout(url.toString(), 30000);
      if (!inputLoadIsCurrent(ticket) || byId('publicNorad').value.trim() !== norad || byId('historyStart').value !== start || byId('historyEnd').value !== end) {
        explainSupersededLoad(ticket, hint); return;
      }
      const records = Array.isArray(response) ? response : response.records;
      if (!Array.isArray(records) || !records.length) throw new Error(response && response.message ? response.message : 'No historical records were returned.');
      const raw = JSON.stringify(records, null, 2);
      const parsed = validateFetchedRecords(records, norad, 'Historical data');
      const provenance = historyInputProvenance(response, parsed.records, norad, { start, end });
      assignInputValue(raw, 'Space-Track GP_History via same-site endpoint', 'Historical data loaded.', provenance);
      currentPublicNorad = norad;
      byId('publicNorad').value = norad;
      const objectUrl = new URL(window.location.href);
      objectUrl.searchParams.delete('demo');
      objectUrl.searchParams.set('norad', norad);
      objectUrl.searchParams.set('start', start);
      objectUrl.searchParams.set('end', end);
      window.history.replaceState({}, '', objectUrl.toString());
      hint.textContent = `Loaded ${parsed.records.length} historical OMM record(s)${response && response.cached ? ' from the server cache' : ''}.`;
      hint.textContent += ' ' + provenanceSummary(provenance);
      byId('publicFetchHint').textContent = '';
      syncPublicSnapshotControls();
      hideDemoNotice();
      run();
      scrollToResults();
    } catch (error) {
      if (inputLoadIsCurrent(ticket)) showHistoryFailure(error);
    } finally {
      button.disabled = false;
    }
  }

  function fixedTestOptions() {
    return {
      requestedWindow: 6,
      alpha: 0.10,
      minAbsDeltaA: 0.05,
      maximumStaleDays: 36500,
      maximumGapFactor: 3,
      orbitProfile: 'auto',
      detectorMode: 'multivariate'
    };
  }

  function runSelfTests() {
    const hint = byId('selfTestHint');
    const wrap = byId('selfTestWrap');
    hint.textContent = 'Running deterministic regression checks…';
    const options = fixedTestOptions();
    const tests = [];

    function add(name, passed, detail) {
      tests.push({ name, passed: Boolean(passed), detail: detail || '' });
    }

    try {
      const leoRaw = exampleTles('leo');
      const geoRaw = exampleTles('geo');
      const quietRaw = exampleTles('quiet');
      const sparseRaw = exampleTles('sparse');
      const radialRaw = exampleTles('radial');
      const crossRaw = exampleTles('cross');
      const finiteRaw = exampleTles('finite');
      const leo = analyzeRaw(leoRaw, 'self-test', options);
      const geo = analyzeRaw(geoRaw, 'self-test', options);
      const quiet = analyzeRaw(quietRaw, 'self-test', options);
      const sparse = analyzeRaw(sparseRaw, 'self-test', options);
      const radial = analyzeRaw(radialRaw, 'self-test', options);
      const cross = analyzeRaw(crossRaw, 'self-test', options);
      const finite = analyzeRaw(finiteRaw, 'self-test', options);
      add('LEO candidate event', !leo.error && leo.interpretable && leo.events.length >= 1, leo.error ? leo.message : leo.classification);
      add('GEO candidate event', !geo.error && geo.interpretable && geo.events.length >= 1, geo.error ? geo.message : geo.classification);
      add('Quiet control', !quiet.error && quiet.interpretable && quiet.events.length === 0, quiet.error ? quiet.message : quiet.classification);
      add('Sparse-history abstention', !sparse.error && !sparse.interpretable && sparse.events.length === 0, sparse.error ? sparse.message : sparse.classification);
      add('Fixed deterministic fixture epoch', leoRaw.includes('26201.00000000'), 'Fixture anchor is 2026-07-20T00:00:00Z');
      const quietResiduals = !quiet.error ? quiet.rows.slice(1).map(row => row.stateResidualKm).filter(Number.isFinite) : [];
      const maximumQuietResidual = quietResiduals.length ? Math.max(...quietResiduals) : NaN;
      add('Quiet SGP4 residual bound', Number.isFinite(maximumQuietResidual) && maximumQuietResidual < 100, Number.isFinite(maximumQuietResidual) ? maximumQuietResidual.toFixed(3) + ' km maximum' : 'no SGP4 residuals');
      add('Radial maneuver fixture', !radial.error && radial.sgp4PairCount > 0, radial.error ? radial.message : radial.classification);
      add('Cross-track maneuver fixture', !cross.error && cross.sgp4PairCount > 0, cross.error ? cross.message : cross.classification);
      add('Finite-duration maneuver fixture', !finite.error && finite.sgp4PairCount > 0, finite.error ? finite.message : finite.classification);
      const repeated = analyzeRaw(leoRaw, 'self-test', options);
      add('Deterministic run ID', !leo.error && !repeated.error && leo.runId === repeated.runId, leo.runId + ' / ' + repeated.runId);
      add('Event grouping', !leo.error && leo.events.length <= leo.flags.length, `${leo.events.length} event(s) from ${leo.flags.length} anomalous epoch(s)`);
      const groupedRecords = [
        { t: new Date('2026-01-01T00:00:00Z'), a: 7000.0 },
        { t: new Date('2026-01-02T00:00:00Z'), a: 7000.1 },
        { t: new Date('2026-01-03T00:00:00Z'), a: 6999.9 },
        { t: new Date('2026-01-04T00:00:00Z'), a: 6999.5 }
      ];
      const groupedFlags = [
        { idx: 2, t: groupedRecords[2].t, dA: -0.2, severityScore: 1.4, breachedFeatures: ['aRate'] },
        { idx: 3, t: groupedRecords[3].t, dA: -0.4, severityScore: 2.1, breachedFeatures: ['aRate', 'alongRate'] }
      ];
      const groupedEvent = groupFlagsIntoEvents(groupedFlags, groupedRecords, 1, 'LEO')[0];
      add(
        'Grouped-event 3D boundaries',
        groupedEvent && groupedEvent.contextBeforeIndex === 1 && groupedEvent.contextAfterIndex === 3 && Math.abs(groupedEvent.netDeltaA + 0.6) < 1e-9,
        groupedEvent ? `context ${groupedEvent.contextBeforeIndex}→${groupedEvent.contextAfterIndex}, net Δa=${groupedEvent.netDeltaA.toFixed(4)} km` : 'no grouped event'
      );
      const invalidLines = quietRaw.split('\n');
      invalidLines[1] = invalidLines[1].slice(0, -1) + (invalidLines[1].endsWith('0') ? '1' : '0');
      const invalidResult = analyzeRaw(invalidLines.join('\n'), 'self-test', options);
      add('Checksum rejection', invalidResult.error || invalidResult.rejectedCount > 0, invalidResult.error ? invalidResult.message : invalidResult.rejectedCount + ' rejected');
      const mixed = exampleTles('quiet') + '\n' + exampleTles('geo');
      const mixedResult = analyzeRaw(mixed, 'self-test', options);
      add('Mixed-object abstention', !mixedResult.error && mixedResult.hardQualityErrors.length > 0 && !mixedResult.interpretable, mixedResult.error ? mixedResult.message : mixedResult.classification);
    } catch (error) {
      add('Regression harness', false, error && error.message ? error.message : String(error));
    }

    const passedCount = tests.filter(test => test.passed).length;
    lastSelfTestReport = {
      generated_at: new Date().toISOString(),
      method_version: METHOD_VERSION,
      workbench_version: WORKBENCH_VERSION,
      sgp4_available: Boolean(window.satellite),
      passed: passedCount,
      total: tests.length,
      tests
    };
    wrap.innerHTML = `<table><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>${tests.map(test => `<tr><td>${escapeHtml(test.name)}</td><td class="${test.passed ? 'test-pass' : 'test-fail'}">${test.passed ? 'PASS' : 'FAIL'}</td><td>${escapeHtml(test.detail)}</td></tr>`).join('')}</tbody></table>`;
    wrap.style.display = 'block';
    hint.textContent = `${passedCount} of ${tests.length} regression checks passed.${window.satellite ? '' : ' SGP4 was unavailable, so the elements-only fallback was exercised.'}`;
  }

  function invalidateBenchmarkReport(message) {
    lastBenchmarkReport = null;
    byId('downloadBenchmarkReport').disabled = true;
    byId('benchmarkMetrics').style.display = 'none';
    byId('benchmarkTableWrap').style.display = 'none';
    byId('benchmarkProfileWrap').style.display = 'none';
    byId('benchmarkTableBody').innerHTML = '';
    byId('benchmarkProfileBody').innerHTML = '';
    if (benchmarkDefinition) {
      byId('runBenchmark').disabled = false;
      if (message) byId('benchmarkHint').textContent = message;
    }
  }

  async function importBenchmarkFile(file) {
    const hint = byId('benchmarkHint');
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) {
      hint.textContent = 'Benchmark file rejected because it is larger than 20 MB.';
      return;
    }
    const ticket = beginInputLoad();
    hint.textContent = 'Validating ' + file.name + '…';
    try {
      const decoded = JSON.parse(await file.text());
      benchmarkDefinition = normaliseBenchmarkDefinition(decoded);
      lastBenchmarkReport = null;
      byId('runBenchmark').disabled = false;
      byId('downloadBenchmarkReport').disabled = true;
      byId('benchmarkMetrics').style.display = 'none';
      byId('benchmarkTableWrap').style.display = 'none';
      byId('benchmarkProfileWrap').style.display = 'none';
      hint.textContent = `${file.name}: accepted ${benchmarkDefinition.cases.length} case(s), including ${benchmarkDefinition.cases.reduce((count, item) => count + item.truthEvents.length, 0)} documented event(s).`;
    } catch (error) {
      benchmarkDefinition = null;
      invalidateBenchmarkReport();
      byId('runBenchmark').disabled = true;
      hint.textContent = 'Benchmark validation failed: ' + (error && error.message ? error.message : String(error));
    } finally {
      byId('benchmarkInput').value = '';
    }
  }

  function downloadBenchmarkTemplate() {
    downloadText(
      'satellite-maneuver-benchmark-template.json',
      'application/json;charset=utf-8',
      JSON.stringify(benchmarkTemplateDefinition(), null, 2)
    );
    byId('benchmarkHint').textContent = 'Benchmark template downloaded. Replace the placeholder records and source citations before running it.';
  }

  function runBenchmark() {
    const hint = byId('benchmarkHint');
    if (!benchmarkDefinition) {
      hint.textContent = 'Choose and validate a benchmark JSON file first.';
      return;
    }

    const button = byId('runBenchmark');
    button.disabled = true;
    byId('downloadBenchmarkReport').disabled = true;
    hint.textContent = 'Running event-level benchmark and deterministic missing-data sensitivity check…';

    try {
      const options = getAnalysisOptions();
      const caseResults = [];
      const profileAccumulators = {};
      let truePositives = 0;
      let falsePositives = 0;
      let falseNegatives = 0;
      let totalTruth = 0;
      let totalPredicted = 0;
      let abstainedCases = 0;
      let scoredCases = 0;
      let unknownCases = 0;
      let unverifiedPredictions = 0;
      let negativeLabelObjectMonths = 0;
      const detectionDelays = [];
      let thinningCases = 0;
      let thinningTruthEvents = 0;
      let thinningTruePositives = 0;
      let thinningFalseNegatives = 0;
      let eventPresenceStable = 0;

      benchmarkDefinition.cases.forEach(item => {
        const caseOptions = { ...options };
        if (item.orbitProfile && item.orbitProfile !== 'AUTO') caseOptions.orbitProfile = item.orbitProfile;
        const analysis = analyzeRaw(item.raw, 'labelled benchmark ' + item.caseId, caseOptions);
        const predicted = !analysis.error && analysis.interpretable ? analysis.events : [];
        const rawMatch = matchBenchmarkEvents(predicted, item.truthEvents, benchmarkDefinition.toleranceHours, analysis.records);
        const abstained = analysis.error || !analysis.interpretable;
        if (abstained) abstainedCases++;
        totalPredicted += predicted.length;

        const spanObjectMonths = !analysis.error && Number.isFinite(analysis.spanDays) && analysis.spanDays > 0
          ? analysis.spanDays / 30.4375
          : 0;
        const positiveScored = item.labelStatus === 'event-evidence' || item.labelStatus === 'fully-labelled';
        const negativeScored = item.labelStatus === 'confirmed-quiet' || item.labelStatus === 'fully-labelled';
        const caseScored = positiveScored || negativeScored;
        if (caseScored) scoredCases++;
        else unknownCases++;

        let caseTp = 0;
        let caseFp = 0;
        let caseFn = 0;
        let caseUnverifiedPredictions = 0;
        let caseMatches = [];

        if (positiveScored) {
          caseTp = rawMatch.truePositives;
          caseFn = rawMatch.falseNegatives;
          caseMatches = rawMatch.matches;
          totalTruth += item.truthEvents.length;
          if (item.labelStatus === 'event-evidence') {
            caseUnverifiedPredictions = rawMatch.falsePositives;
          }
        }
        if (negativeScored) {
          caseFp = rawMatch.falsePositives;
          negativeLabelObjectMonths += spanObjectMonths;
        } else if (item.labelStatus === 'unknown') {
          caseUnverifiedPredictions = predicted.length;
        }

        truePositives += caseTp;
        falsePositives += caseFp;
        falseNegatives += caseFn;
        unverifiedPredictions += caseUnverifiedPredictions;
        caseMatches.forEach(entry => detectionDelays.push(entry.delayHours));

        const resolvedProfile = item.orbitProfile && item.orbitProfile !== 'AUTO'
          ? item.orbitProfile
          : (!analysis.error && analysis.profileName ? analysis.profileName : 'UNKNOWN');
        if (!profileAccumulators[resolvedProfile]) profileAccumulators[resolvedProfile] = initialiseProfileAccumulator();
        const profile = profileAccumulators[resolvedProfile];
        profile.cases++;
        if (caseScored) profile.scored_cases++;
        if (positiveScored) profile.positive_evidence_cases++;
        if (abstained) profile.abstained_cases++;
        profile.true_positives += caseTp;
        profile.false_positives += caseFp;
        profile.false_negatives += caseFn;
        if (negativeScored) profile.negative_label_object_months += spanObjectMonths;
        caseMatches.forEach(entry => profile.detection_delays_hours.push(entry.delayHours));

        const thinnedRaw = deterministicThinBenchmarkRaw(item.raw);
        let thinning = null;
        if (thinnedRaw) {
          thinningCases++;
          const thinnedAnalysis = analyzeRaw(thinnedRaw, 'deterministically thinned benchmark ' + item.caseId, caseOptions);
          const thinnedPredicted = !thinnedAnalysis.error && thinnedAnalysis.interpretable ? thinnedAnalysis.events : [];
          const thinnedMatch = matchBenchmarkEvents(thinnedPredicted, item.truthEvents, benchmarkDefinition.toleranceHours, thinnedAnalysis.records);
          if (positiveScored) {
            thinningTruthEvents += item.truthEvents.length;
            thinningTruePositives += thinnedMatch.truePositives;
            thinningFalseNegatives += thinnedMatch.falseNegatives;
          }
          if ((predicted.length > 0) === (thinnedPredicted.length > 0)) eventPresenceStable++;
          thinning = {
            original_record_count: parseInput(item.raw).records.length,
            thinned_record_count: parseInput(thinnedRaw).records.length,
            abstained: thinnedAnalysis.error || !thinnedAnalysis.interpretable,
            predicted_event_count: thinnedPredicted.length,
            true_positives: positiveScored ? thinnedMatch.truePositives : null,
            false_negatives: positiveScored ? thinnedMatch.falseNegatives : null,
            classification: thinnedAnalysis.error ? 'Input error' : thinnedAnalysis.classification,
            event_presence_stable: (predicted.length > 0) === (thinnedPredicted.length > 0)
          };
        }

        caseResults.push({
          case_id: item.caseId,
          object_id: analysis.error ? item.objectId : analysis.objectId || item.objectId,
          description: item.description,
          source: item.source,
          orbit_profile: resolvedProfile,
          label_status: item.labelStatus,
          label_confidence: item.labelConfidence,
          truth_event_count: item.truthEvents.length,
          predicted_event_count: predicted.length,
          unverified_prediction_count: caseUnverifiedPredictions,
          true_positives: positiveScored ? caseTp : null,
          false_positives: negativeScored ? caseFp : null,
          false_negatives: positiveScored ? caseFn : null,
          abstained,
          classification: analysis.error ? 'Input error' : analysis.classification,
          run_id: analysis.error ? null : analysis.runId,
          quality_status: analysis.error ? 'unusable' : analysis.qualityStatus,
          truth_events: item.truthEvents,
          predicted_events: predicted.map(event => {
            const interval = benchmarkPredictionInterval(event, analysis.records);
            return {
              event_id: event.id,
              start: formatEpochUs(Number(interval[0])),
              end: formatEpochUs(Number(interval[1])),
              strongest_epoch: formatEpochUs(Number(interval[2])),
              tier: event.tier,
              score: event.score,
              net_delta_a_km: event.netDeltaA,
              supporting_features: event.features
            };
          }),
          matches: caseMatches,
          deterministic_thinning: thinning
        });
      });

      const precision = negativeLabelObjectMonths > 0
        ? ratioOrNull(truePositives, truePositives + falsePositives)
        : null;
      const recall = ratioOrNull(truePositives, truePositives + falseNegatives);
      const f1 = Number.isFinite(precision) && Number.isFinite(recall) && precision + recall > 0
        ? 2 * precision * recall / (precision + recall)
        : null;
      const falseEventsPerObjectMonth = negativeLabelObjectMonths > 0
        ? falsePositives / negativeLabelObjectMonths
        : null;
      const medianDetectionDelayHours = detectionDelays.length ? median(detectionDelays) : null;
      const byProfile = {};
      Object.keys(profileAccumulators).sort().forEach(profileCode => {
        byProfile[profileCode] = finaliseProfileMetrics(profileAccumulators[profileCode]);
      });
      const settings = {
        window: options.requestedWindow,
        alpha: options.alpha,
        minimum_absolute_delta_a_km: options.minAbsDeltaA,
        maximum_stale_days: options.maximumStaleDays,
        maximum_gap_factor: options.maximumGapFactor,
        orbit_profile: options.orbitProfile,
        detector_mode: options.detectorMode
      };
      const benchmarkId = makeBenchmarkId(benchmarkDefinition.original, settings);

      lastBenchmarkReport = {
        schema: 'smd-event-benchmark-report-v4',
        scoring_version: EVENT_MATCHING_VERSION,
        benchmark_id: benchmarkId,
        benchmark_name: benchmarkDefinition.name,
        generated_at: new Date().toISOString(),
        workbench_version: WORKBENCH_VERSION,
        detector_method: METHOD_VERSION,
        satellite_js_version: window.satellite ? SATELLITE_JS_VERSION : null,
        matching_tolerance_hours: benchmarkDefinition.toleranceHours,
        settings,
        summary: {
          cases: caseResults.length,
          scored_cases: scoredCases,
          unknown_cases: unknownCases,
          abstained_cases: abstainedCases,
          truth_events: totalTruth,
          predicted_events: totalPredicted,
          unverified_predictions: unverifiedPredictions,
          true_positives: truePositives,
          false_positives: negativeLabelObjectMonths > 0 ? falsePositives : null,
          false_negatives: falseNegatives,
          precision,
          recall,
          f1,
          negative_label_object_months: negativeLabelObjectMonths,
          false_events_per_object_month: falseEventsPerObjectMonth,
          median_detection_delay_hours: medianDetectionDelayHours
        },
        by_orbit_profile: byProfile,
        missing_data_sensitivity: {
          method: 'Deterministic removal of every fourth interior orbital record; first and last records retained.',
          cases_evaluated: thinningCases,
          positive_truth_events: thinningTruthEvents,
          true_positives: thinningTruePositives,
          false_negatives: thinningFalseNegatives,
          event_recall: ratioOrNull(thinningTruePositives, thinningTruePositives + thinningFalseNegatives),
          event_presence_stability: ratioOrNull(eventPresenceStable, thinningCases)
        },
        cases: caseResults,
        benchmark_definition: benchmarkDefinition.original,
        qualification: negativeLabelObjectMonths > 0
          ? 'Metrics apply only to the supplied labelled coverage and matching tolerance. Unknown periods are excluded from false-positive and false-alert calculations.'
          : 'This dataset has no qualified negative-labelled coverage. Recall against documented event evidence may be reported, but precision, F1 and false-event rate are intentionally unavailable.'
      };

      renderBenchmarkReport(lastBenchmarkReport);
      byId('downloadBenchmarkReport').disabled = false;
      hint.textContent = `${benchmarkId}: ${caseResults.length} case(s), ${truePositives} TP, ${falseNegatives} FN, ${unverifiedPredictions} unverified prediction(s), ${abstainedCases} abstention(s).`;
    } catch (error) {
      lastBenchmarkReport = null;
      byId('downloadBenchmarkReport').disabled = true;
      hint.textContent = 'Benchmark run failed: ' + (error && error.message ? error.message : String(error));
    } finally {
      button.disabled = !benchmarkDefinition;
    }
  }

  function renderBenchmarkReport(report) {
    const summary = report.summary;
    byId('benchmarkCases').textContent = String(summary.cases);
    byId('benchmarkTp').textContent = String(summary.true_positives);
    byId('benchmarkFp').textContent = String(summary.false_positives);
    byId('benchmarkFn').textContent = String(summary.false_negatives);
    byId('benchmarkPrecision').textContent = metricText(summary.precision);
    byId('benchmarkRecall').textContent = metricText(summary.recall);
    byId('benchmarkF1').textContent = metricText(summary.f1);
    byId('benchmarkFalseRate').textContent = metricText(summary.false_events_per_object_month);
    byId('benchmarkDelay').textContent = Number.isFinite(summary.median_detection_delay_hours) ? summary.median_detection_delay_hours.toFixed(2) + ' h' : 'n/a';
    byId('benchmarkAbstentions').textContent = String(summary.abstained_cases);
    byId('benchmarkProfiles').textContent = String(Object.keys(report.by_orbit_profile || {}).length);
    byId('benchmarkThinRecall').textContent = metricText(report.missing_data_sensitivity && report.missing_data_sensitivity.event_recall);
    byId('benchmarkMetrics').style.display = 'grid';

    byId('benchmarkTableBody').innerHTML = report.cases.map(item => `
      <tr>
        <td>${escapeHtml(item.case_id)}</td>
        <td>${escapeHtml(item.object_id || 'n/a')}</td>
        <td>${item.truth_event_count}</td>
        <td>${item.predicted_event_count}</td>
        <td>${item.true_positives === null ? 'n/a' : item.true_positives}</td>
        <td>${escapeHtml(item.classification)}</td>
        <td class="${item.abstained ? 'test-fail' : 'test-pass'}">${item.abstained ? 'ABSTAIN' : 'EVALUATED'}</td>
      </tr>
    `).join('');
    byId('benchmarkTableWrap').style.display = 'block';

    const profileEntries = Object.entries(report.by_orbit_profile || {});
    byId('benchmarkProfileBody').innerHTML = profileEntries.map(([profileCode, metrics]) => `
      <tr>
        <td>${escapeHtml(profileCode)}</td>
        <td>${metrics.cases}</td>
        <td>${metrics.true_positives}</td>
        <td>${metrics.false_positives}</td>
        <td>${metrics.false_negatives}</td>
        <td>${escapeHtml(metricText(metrics.precision))}</td>
        <td>${escapeHtml(metricText(metrics.recall))}</td>
        <td>${escapeHtml(metricText(metrics.f1))}</td>
      </tr>
    `).join('');
    byId('benchmarkProfileWrap').style.display = profileEntries.length ? 'block' : 'none';
  }

  function downloadBenchmarkReport() {
    if (!lastBenchmarkReport) {
      byId('benchmarkHint').textContent = 'Run a benchmark before downloading its report.';
      return;
    }
    downloadText(
      'satellite-maneuver-benchmark-' + lastBenchmarkReport.benchmark_id + '.json',
      'application/json;charset=utf-8',
      JSON.stringify(lastBenchmarkReport, null, 2)
    );
    byId('benchmarkHint').textContent = 'Benchmark report downloaded.';
  }

  function updateDependencyStatus() {
    const element = byId('dependencyStatus');
    if (!element) return;
    const sgp4Ready = Boolean(window.satellite && typeof window.satellite.propagate === 'function');
    const plotlyText = window.Plotly
      ? ' Plotly charts and 3D context are loaded from the pinned same-site asset.'
      : plotlyLoadState === 'loading'
        ? ' The pinned same-site Plotly asset is loading on demand.'
        : plotlyLoadState === 'failed'
          ? ' Plotly could not be loaded; tabular result data remains available.'
          : ' Plotly charts and 3D context load on demand after analysis.';
    if (sgp4Ready) {
      element.textContent = 'SGP4 ready through the same-site pinned satellite.js ' + SATELLITE_JS_VERSION + '. The detector will compare consecutive records at a common epoch.' + plotlyText;
      element.className = plotlyLoadState === 'failed' ? 'dependency-note small warn' : 'dependency-note small ok';
    } else {
      element.textContent = 'satellite.js did not load. The workbench remains usable in elements-only fallback mode, but SGP4 residual signals are unavailable.' + plotlyText;
      element.className = 'dependency-note small warn';
    }
  }

  function publicCacheKey(norad) {
    return 'satellite-maneuver-workbench:celestrak:gp:' + norad;
  }

  function readPublicCache(norad) {
    try {
      const raw = localStorage.getItem(publicCacheKey(norad));
      if (!raw) return null;
      const cached = JSON.parse(raw);
      if (!cached || !cached.fetchedAt || !cached.data) return null;
      const age = Date.now() - cached.fetchedAt;
      if (typeof cached.fetchedAt !== 'number' || !Number.isFinite(age) || age < 0 || age >= PUBLIC_CACHE_MS) return null;
      validateFetchedRecords(cached.data, norad, 'Cached public data');
      return cached;
    } catch (error) {
      return null;
    }
  }

  function writePublicCache(norad, data, fetchedAt = Date.now()) {
    try {
      localStorage.setItem(publicCacheKey(norad), JSON.stringify({ fetchedAt, data }));
    } catch (error) {
      // Storage can be disabled. The loader still works without caching.
    }
  }

  async function fetchJsonWithTimeout(url, timeoutMs) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        cache: 'no-store',
        signal: controller.signal,
        headers: { Accept: 'application/json' }
      });

      let payload = null;
      try {
        payload = await response.json();
      } catch (error) {
        payload = null;
      }

      if (!response.ok) {
        const message = payload && payload.message
          ? String(payload.message)
          : 'The request failed with HTTP ' + response.status + '.';
        const requestError = new Error(message);
        requestError.status = response.status;
        requestError.code = payload && payload.code ? String(payload.code) : '';
        throw requestError;
      }

      if (payload === null) throw new Error('The server returned an invalid JSON response.');
      return payload;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function loadPublicDataIntoInput(norad, data, fromCache, mode, retrievedAt = null) {
    const records = Array.isArray(data) ? data : [data];
    if (!records.length) throw new Error('No OMM record returned for this catalog number.');

    const raw = JSON.stringify(records, null, 2);
    const parsed = validateFetchedRecords(records, norad, 'Public data');
    const provenance = currentGpInputProvenance(parsed.records, norad, retrievedAt);
    const result = applyIncomingData(raw, mode, mode === 'append' ? 'orbital history with current public OMM snapshot' : 'current public OMM snapshot', provenance);
    currentPublicNorad = norad;
    currentExampleKey = '';
    byId('publicNorad').value = norad;

    const deepLink = new URL(window.location.href);
    deepLink.searchParams.delete('demo');
    deepLink.searchParams.set('norad', norad);
    deepLink.searchParams.delete('start');
    deepLink.searchParams.delete('end');
    window.history.replaceState({}, '', deepLink.toString());

    const cacheText = fromCache ? 'from the local two-hour cache' : 'from CelesTrak and cached locally for two hours';
    if (mode === 'append' && result.unchanged) {
      byId('publicFetchHint').textContent = `The current OMM snapshot already exists in the loaded history ${cacheText}. The analysis and exports remain current.`;
      return;
    }

    byId('publicFetchHint').textContent = mode === 'append'
      ? `Current OMM snapshot appended ${cacheText}. ${result.added} new snapshot(s), ${result.replacements || 0} corrected snapshot(s), ${result.total} total. Analysis updated.`
      : `Current OMM snapshot loaded ${cacheText}. Screening still needs multiple historical records.`;

    if (mode === 'append' && !result.unchanged) {
      run();
      scrollToResults();
    }
  }

  async function fetchPublicOmm(mode) {
    const input = byId('publicNorad');
    const hint = byId('publicFetchHint');
    const buttons = [byId('replacePublicOmm'), byId('appendPublicOmm')];
    const norad = input.value.trim();

    if (!/^\d{1,9}$/.test(norad)) {
      hint.textContent = 'Enter a NORAD catalog number containing 1 to 9 digits.';
      return;
    }

    const currentRecordCount = currentInputRecordCount();
    if (mode === 'replace' && currentRecordCount > 1) {
      hint.textContent = `The current input contains ${currentRecordCount} records. Append the snapshot instead, or clear the input before replacing it.`;
      syncPublicSnapshotControls();
      return;
    }

    const ticket = beginInputLoad();
    buttons.forEach(button => { button.disabled = true; });
    hint.textContent = 'Loading current public OMM JSON from CelesTrak…';

    try {
      const cached = readPublicCache(norad);
      if (cached) {
        loadPublicDataIntoInput(norad, cached.data, true, mode, cached.fetchedAt);
        return;
      }

      const url = 'https://celestrak.org/NORAD/elements/gp.php?CATNR=' + encodeURIComponent(norad) + '&FORMAT=JSON';
      const data = await fetchJsonWithTimeout(url, 15000);
      validateFetchedRecords(data, norad, 'Public data');
      const fetchedAt = Date.now();
      writePublicCache(norad, data, fetchedAt);
      if (!inputLoadIsCurrent(ticket) || input.value.trim() !== norad) { explainSupersededLoad(ticket, hint); return; }
      loadPublicDataIntoInput(norad, data, false, mode, fetchedAt);
    } catch (error) {
      const message = error && error.name === 'AbortError'
        ? 'The CelesTrak request timed out.'
        : error && error.message
          ? error.message
          : String(error);
      if (inputLoadIsCurrent(ticket)) hint.textContent = 'Public OMM load failed: ' + message;
    } finally {
      syncPublicSnapshotControls();
    }
  }

  function copyDeepLink() {
    const hint = byId('publicFetchHint');
    const url = new URL(window.location.href);
    let norad = '';

    if (currentPublicNorad) norad = currentPublicNorad;
    else if (!currentExampleKey && lastAnalysis && /^\d{1,9}$/.test(lastAnalysis.objectId || '')) norad = lastAnalysis.objectId;
    else if (!currentExampleKey && /^\d{1,9}$/.test(byId('publicNorad').value.trim())) norad = byId('publicNorad').value.trim();

    if (norad) {
      url.searchParams.delete('demo');
      url.searchParams.set('norad', norad);
      if (byId('historyStart').value) url.searchParams.set('start', byId('historyStart').value);
      if (byId('historyEnd').value) url.searchParams.set('end', byId('historyEnd').value);
    } else if (currentExampleKey) {
      url.searchParams.delete('norad');
      url.searchParams.set('demo', currentExampleKey);
    } else {
      hint.textContent = 'Load or analyse an object before copying an object link.';
      return;
    }

    copyText(url.toString(), hint, 'Link copied. Opening it will not fetch data automatically.');
  }

  function loadExample(kind, runImmediately, revealResults) {
    inputRevision++;
    updateDemoControls(kind);
    byId('historyDetails').open = false;
    byId('manualInputDetails').open = false;
    currentExampleKey = kind;
    currentPublicNorad = '';
    currentInputSourceLabel = 'built-in synthetic demo history';
    currentInputProvenance = null;
    suppressManualInputNotice = true;
    byId('tles').value = exampleTles(kind);
    suppressManualInputNotice = false;

    resetOutputOnly();
    clearRanking('Example changed. Run ranked demo screening again if needed.');
    byId('publicFetchHint').textContent = 'Built-in synthetic example loaded. This is not live public orbital data.';
    byId('fileImportHint').textContent = '';

    const label =
      kind === 'geo' ? 'GEO station-keeping example loaded.' :
      kind === 'quiet' ? 'Noisy non-event example loaded.' :
      kind === 'sparse' ? 'Sparse-data example loaded.' :
      'LEO candidate example loaded.';

    const url = new URL(window.location.href);
    url.searchParams.delete('norad');
    url.searchParams.delete('start');
    url.searchParams.delete('end');
    url.searchParams.set('demo', kind);
    window.history.replaceState({}, '', url.toString());
    setStatus('neutral', runImmediately ? label + ' Running analysis…' : label + ' Press Run analysis.');
    if (runImmediately) {
      run();
      showDemoNotice();
      if (revealResults) scrollToResults();
    } else {
      hideDemoNotice();
    }
  }

  function rankExamples() {
    const examples = [
      { key: 'leo', label: 'DEMO LEO CANDIDATE OBJECT' },
      { key: 'geo', label: 'DEMO GEO STATION-KEEPING OBJECT' },
      { key: 'quiet', label: 'DEMO QUIET LEO OBJECT' },
      { key: 'sparse', label: 'DEMO SPARSE LEO OBJECT' }
    ];

    const results = examples.map(item => {
      const analysis = analyzeRaw(exampleTles(item.key), 'built-in ranked demo');
      const score = !analysis.error && analysis.interpretable && analysis.strongestEvent
        ? analysis.strongestEvent.score
        : 0;

      return {
        key: item.key,
        label: item.label,
        objectId: analysis.error ? '' : analysis.objectId,
        classification: analysis.error ? 'Input error' : analysis.classification,
        score,
        quality: analysis.error ? 'unusable' : analysis.qualityStatus,
        candidateCount: analysis.error || !analysis.interpretable ? 0 : analysis.events.length,
        profileName: analysis.error ? 'n/a' : analysis.profileName,
        generatedAt: new Date().toISOString()
      };
    }).sort((first, second) => second.score - first.score);

    lastRanking = results;
    renderRanking(results);
    setRankingExportEnabled(true);
  }

  function renderRanking(results) {
    const body = byId('rankTableBody');
    const hint = byId('rankHint');

    if (!results.length) {
      body.innerHTML = '<tr><td colspan="6" class="muted">No ranking results available.</td></tr>';
      hint.textContent = '';
      return;
    }

    body.innerHTML = results.map((result, index) => `
      <tr>
        <td>${index + 1}</td>
        <td><button class="table-action" type="button" data-rank-key="${escapeHtml(result.key)}">${escapeHtml(result.label)}</button></td>
        <td>${escapeHtml(result.profileName || 'n/a')}</td>
        <td>${escapeHtml(result.classification)}</td>
        <td class="rank-score">${escapeHtml(fmtNum(result.score, 2))}</td>
        <td>${escapeHtml(result.quality)}</td>
      </tr>
    `).join('');

    body.querySelectorAll('[data-rank-key]').forEach(button => {
      button.addEventListener('click', function () {
        loadExample(this.getAttribute('data-rank-key'), true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });

    hint.textContent = 'Ranking complete. Abstained examples receive a score of zero. Choose an object to load and analyse it.';
  }

  function downloadRankJson() {
    const hint = byId('rankHint');
    if (!lastRanking || !lastRanking.length) {
      hint.textContent = 'Run ranked demo screening before exporting the ranking.';
      return;
    }

    downloadText(
      'satellite-maneuver-ranking-demo.json',
      'application/json;charset=utf-8',
      JSON.stringify({
        method_version: METHOD_VERSION,
        workbench_version: WORKBENCH_VERSION,
        generated_at: new Date().toISOString(),
        note: 'Built-in synthetic demo ranking. Abstained runs receive a score of zero.',
        results: lastRanking
      }, null, 2)
    );
    hint.textContent = 'Ranking JSON downloaded.';
  }

  function copyFlags() {
    const text = byId('flags').textContent.trim();
    const hint = byId('flagCopyHint');
    if (!lastAnalysis || lastAnalysis.error || !lastAnalysis.interpretable || !lastAnalysis.events.length) {
      copyText('', hint);
      return;
    }
    copyText(text, hint, 'Flagged list copied.');
  }

  function copyEvidence() {
    const hint = byId('exportHint');
    if (!lastAnalysis || lastAnalysis.error || !lastAnalysis.evidenceText) {
      copyText('', hint);
      return;
    }
    copyText(lastAnalysis.evidenceText, hint, 'Evidence note copied.');
  }

  function downloadCsv() {
    const hint = byId('exportHint');
    if (!lastAnalysis || lastAnalysis.error || !lastAnalysis.csv) {
      hint.textContent = 'Run a validated analysis before exporting CSV.';
      return;
    }
    const payload = buildAnalysisDownloadPayloads(lastAnalysis).csv;
    downloadText(payload.filename, payload.mimeType, payload.text);
    hint.textContent = 'CSV downloaded.';
  }

  function downloadJson() {
    const hint = byId('exportHint');
    if (!lastAnalysis || lastAnalysis.error) {
      hint.textContent = 'Run a validated analysis before exporting JSON.';
      return;
    }
    const payload = buildAnalysisDownloadPayloads(lastAnalysis).json;
    downloadText(payload.filename, payload.mimeType, payload.text);
    hint.textContent = 'Analysis JSON downloaded.';
  }

  function downloadBundle() {
    const hint = byId('exportHint');
    if (!lastAnalysis || lastAnalysis.error) {
      hint.textContent = 'Run a validated analysis before exporting a reproducibility package.';
      return;
    }
    const payload = buildAnalysisDownloadPayloads(lastAnalysis).reproducibility;
    downloadText(payload.filename, payload.mimeType, payload.text);
    hint.textContent = 'Reproducibility package downloaded.';
  }

  async function saveChart() {
    const hint = byId('exportHint');
    if (!lastAnalysis || lastAnalysis.error) {
      hint.textContent = 'Run a validated analysis before saving the charts.';
      return;
    }

    const button = byId('saveChart');
    button.disabled = true;
    hint.textContent = 'Preparing combined chart image…';

    try {
      await ensurePlotlyLoaded();
      const [orbitUrl, rateUrl] = await Promise.all([
        window.Plotly.toImage('orbitChart', { format: 'png', width: 1400, height: 620, scale: 1 }),
        window.Plotly.toImage('rateChart', { format: 'png', width: 1400, height: 620, scale: 1 })
      ]);

      const loadImage = source => new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = reject;
        image.src = source;
      });

      const [orbitImage, rateImage] = await Promise.all([loadImage(orbitUrl), loadImage(rateUrl)]);
      const canvas = document.createElement('canvas');
      canvas.width = 1400;
      canvas.height = 1320;
      const context = canvas.getContext('2d');
      context.fillStyle = '#ffffff';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = '#0f172a';
      context.font = 'bold 26px system-ui, sans-serif';
      context.fillText('Satellite Maneuver Screening Workbench', 34, 40);
      context.font = '16px system-ui, sans-serif';
      context.fillStyle = '#475569';
      const objectText = (lastAnalysis.objectName || lastAnalysis.objectId || 'Unknown object') + ' · ' + lastAnalysis.classification + ' · ' + lastAnalysis.runId;
      context.fillText(objectText, 34, 68);
      context.drawImage(orbitImage, 0, 82, 1400, 620);
      context.drawImage(rateImage, 0, 700, 1400, 620);

      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
      if (!blob) throw new Error('The combined image could not be created.');
      const suffix = lastAnalysis.objectId ? '-' + lastAnalysis.objectId : '';
      downloadBlob('satellite-maneuver-screening-' + lastAnalysis.runId + suffix + '.png', blob);
      hint.textContent = 'Combined chart PNG downloaded.';
    } catch (error) {
      hint.textContent = 'Chart export failed: ' + (error && error.message ? error.message : String(error));
    } finally {
      button.disabled = false;
    }
  }

  function removeObjectParameters() {
    const url = new URL(window.location.href);
    url.searchParams.delete('demo');
    url.searchParams.delete('norad');
    url.searchParams.delete('start');
    url.searchParams.delete('end');
    window.history.replaceState({}, '', url.toString());
  }

  function handleInitialUrl() {
    const parameters = new URLSearchParams(window.location.search);
    const norad = parameters.get('norad');
    const demo = parameters.get('demo');
    const start = parameters.get('start');
    const end = parameters.get('end');
    setDefaultHistoryDates();

    if (start && /^\d{4}-\d{2}-\d{2}$/.test(start)) byId('historyStart').value = start;
    if (end && /^\d{4}-\d{2}-\d{2}$/.test(end) && end <= byId('historyEnd').max) byId('historyEnd').value = end;

    if (norad && /^\d{1,9}$/.test(norad)) {
      byId('historyDetails').open = true;
      byId('publicNorad').value = norad;
      byId('tles').value = '';
      resetOutputOnly('Object link loaded');
      byId('historyFetchHint').textContent = 'Object link loaded for NORAD ' + norad + '. Press Load history and analyse to request the selected date range.';
      return;
    }

    if (demo && ['leo', 'geo', 'quiet', 'sparse'].includes(demo)) {
      loadExample(demo, true, false);
      return;
    }

    currentInputSourceLabel = '';
    currentInputProvenance = null;
    byId('tles').value = '';
    resetOutputOnly('Waiting for input');
  }

  function start() {
    if (started) return;
    started = true;
    initialiseConsole();
    byId('run').addEventListener('click', () => { run(); scrollToResults(); });
    byId('reset').addEventListener('click', () => resetOutputOnly('Output reset. Input retained.'));
    byId('heroHistoryButton').addEventListener('click', () => {
      byId('historyDetails').open = true;
      byId('historyDetails').scrollIntoView({ behavior: 'smooth', block: 'start' });
      window.setTimeout(() => byId('publicNorad').focus(), 350);
    });
    byId('heroDemoButton')?.addEventListener('click', () => loadExample(byId('demoSelect').value, true, true));
    byId('tryDemo').addEventListener('click', () => loadExample(byId('demoSelect').value, true, true));
    byId('viewDemoResults').addEventListener('click', scrollToResults);
    byId('stickyViewResult').addEventListener('click', scrollToResults);
    byId('toggleChartSize').addEventListener('click', toggleChartSize);
    byId('demoSelect').addEventListener('change', function () { updateDemoControls(this.value); });
    byId('copyFlags').addEventListener('click', copyFlags);
    byId('copyEvidence').addEventListener('click', copyEvidence);
    byId('downloadCsv').addEventListener('click', downloadCsv);
    byId('downloadJson').addEventListener('click', downloadJson);
    byId('saveChart').addEventListener('click', saveChart);
    byId('downloadBundle').addEventListener('click', downloadBundle);
    byId('loadHistory').addEventListener('click', loadHistoricalData);
    byId('runSelfTests').addEventListener('click', runSelfTests);
    byId('chooseBenchmark').addEventListener('click', () => byId('benchmarkInput').click());
    byId('benchmarkInput').addEventListener('change', () => {
      const file = byId('benchmarkInput').files && byId('benchmarkInput').files[0];
      importBenchmarkFile(file);
    });
    byId('downloadBenchmarkTemplate').addEventListener('click', downloadBenchmarkTemplate);
    byId('runBenchmark').addEventListener('click', runBenchmark);
    byId('downloadBenchmarkReport').addEventListener('click', downloadBenchmarkReport);
    byId('replacePublicOmm').addEventListener('click', () => fetchPublicOmm('replace'));
    byId('appendPublicOmm').addEventListener('click', () => fetchPublicOmm('append'));
    byId('copyDeepLink').addEventListener('click', copyDeepLink);
    byId('rankExamples').addEventListener('click', rankExamples);
    byId('downloadRankJson').addEventListener('click', downloadRankJson);
    byId('fitOrbit').addEventListener('click', fitOrbitView);
    byId('resetChartZoom').addEventListener('click', resetChartZoom);
    byId('orbitDetails').addEventListener('toggle', () => {
      if (byId('orbitDetails').open) renderPendingOrbitContext();
    });

    byId('sensitivity').addEventListener('change', function () {
      setSensitivity(this.value);
      invalidateResults('Sensitivity changed. Run analysis again.');
      invalidateBenchmarkReport('Settings changed. Run the labelled benchmark again.');
    });

    ['dath', 'stale', 'gapWarn', 'orbitProfile', 'detectorMode'].forEach(id => {
      const element = byId(id);
      element.addEventListener('input', () => {
        if (!suppressControlInvalidation) {
          invalidateResults('Analysis settings changed. Run analysis again.');
          invalidateBenchmarkReport('Settings changed. Run the labelled benchmark again.');
        }
      });
      element.addEventListener('change', () => {
        if (!suppressControlInvalidation) {
          invalidateResults('Analysis settings changed. Run analysis again.');
          invalidateBenchmarkReport('Settings changed. Run the labelled benchmark again.');
        }
      });
    });

    ['win', 'alpha'].forEach(id => {
      const element = byId(id);
      element.addEventListener('input', () => {
        if (suppressControlInvalidation) return;
        syncSensitivityFromControls();
        invalidateResults('Analysis settings changed. Run analysis again.');
        invalidateBenchmarkReport('Settings changed. Run the labelled benchmark again.');
      });
      element.addEventListener('change', () => {
        if (suppressControlInvalidation) return;
        syncSensitivityFromControls();
        invalidateResults('Analysis settings changed. Run analysis again.');
        invalidateBenchmarkReport('Settings changed. Run the labelled benchmark again.');
      });
    });

    byId('tles').addEventListener('input', function () {
      if (suppressManualInputNotice) return;
      inputRevision++;
      currentExampleKey = '';
      currentPublicNorad = '';
      currentInputSourceLabel = 'pasted orbital-element history';
      currentInputProvenance = null;
      hideDemoNotice();
      removeObjectParameters();
      syncPublicSnapshotControls();
      invalidateResults('Input changed. Run analysis again.');
      byId('publicFetchHint').textContent = 'Input edited manually. It will be treated as pasted TLE or OMM JSON history.';
      byId('historyFetchHint').textContent = '';
    });

    byId('chooseFile').addEventListener('click', () => byId('fileInput').click());
    byId('fileInput').addEventListener('change', () => {
      const file = byId('fileInput').files && byId('fileInput').files[0];
      importLocalFile(file, byId('importMode').value);
    });

    const dropZone = byId('dropZone');
    ['dragenter', 'dragover'].forEach(type => dropZone.addEventListener(type, event => {
      event.preventDefault();
      dropZone.classList.add('dragover');
    }));
    ['dragleave', 'drop'].forEach(type => dropZone.addEventListener(type, event => {
      event.preventDefault();
      dropZone.classList.remove('dragover');
    }));
    dropZone.addEventListener('drop', event => {
      const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
      importLocalFile(file, byId('importMode').value);
    });
    dropZone.addEventListener('click', () => byId('fileInput').click());
    dropZone.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        byId('fileInput').click();
      }
    });


    setAnalysisExportEnabled(false);
    setCopyFlagsEnabled(false);
    setRankingExportEnabled(false);
    handleInitialUrl();
    syncPublicSnapshotControls();
    window.setTimeout(updateDependencyStatus, 0);
  }

  // Interface API.
  return Object.freeze({
    ...common, ...orbitalInput, ...benchmark, ...packages, ...detection,
    beginInputLoad, inputLoadIsCurrent, explainSupersededLoad, setStatus, setRunButtonState,
    setChartMessage, ensurePlotlyLoaded, safePlot, copyText, downloadText, downloadBlob,
    setCopyFlagsEnabled, setAnalysisExportEnabled, setRankingExportEnabled, renderQuality,
    renderResult, clearRanking, resetOutputOnly, invalidateResults, setSensitivity,
    syncSensitivityFromControls, currentInputRecordCount, syncPublicSnapshotControls,
    mergeInputProvenance, assignInputValue, applyIncomingData, decodeSavedPackage, importLocalFile,
    getAnalysisOptions, renderExecutiveSummary, nearestTimeIndex, bindChartSynchronization,
    renderAccessibleChartData, renderCharts, resetChartZoom, toggleChartSize, renderFlagTable,
    renderAnalysis, run, solveKepler, orbitCoordinatesFromElements, earthSphereTrace,
    orbitPlotLayout, clearOrbitContext, orbitalPeriodMinutes, queueOrbitComparisonForEvent,
    queueSingleOrbit, renderPendingOrbitContext, drawOrbitComparison, drawSingleOrbit, fitOrbitView,
    setDefaultHistoryDates, scrollToResults, demoLabel, updateDemoControls, showDemoNotice,
    hideDemoNotice, showHistoryFailure, loadHistoricalData, fixedTestOptions, runSelfTests,
    invalidateBenchmarkReport, importBenchmarkFile, downloadBenchmarkTemplate, runBenchmark,
    renderBenchmarkReport, downloadBenchmarkReport, updateDependencyStatus, publicCacheKey,
    readPublicCache, writePublicCache, fetchJsonWithTimeout, loadPublicDataIntoInput,
    fetchPublicOmm, copyDeepLink, loadExample, rankExamples, renderRanking, downloadRankJson,
    copyFlags, copyEvidence, downloadCsv, downloadJson, downloadBundle, saveChart,
    removeObjectParameters, handleInitialUrl, start
  });
};
