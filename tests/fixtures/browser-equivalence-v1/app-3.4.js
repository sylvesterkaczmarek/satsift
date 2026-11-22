(function () {
  'use strict';

  const MU = 398600.4418;
  const METHOD_VERSION = 'v0.4';
  const WORKBENCH_VERSION = '3.4.7';
  const EVENT_MATCHING_VERSION = 'event-matching-v3';
  const PACKAGE_SCHEMA_VERSION = 1;
  const TLE_SOURCE_SCHEMA_VERSION = 1;
  const RUN_IDENTITY_VERSION = 2;
  const DATA_PROVENANCE_VERSION = 1;
  const INPUT_FINGERPRINT_ALGORITHM = 'fnv1a64-utf16-normalized-omm-v1';
  const MAX_PROVENANCE_SOURCES = 64;
  const MAX_PROVENANCE_ACQUISITIONS = 64;
  const MAX_PROVENANCE_BYTES = 65536;
  const PROPAGATION_CONTRACT = 'sgp4-exact-epoch-v1';
  const SATELLITE_JS_VERSION = '6.0.2';
  const HISTORY_ENDPOINT = '/satellite-maneuver-detector/history';
  const PLOTLY_ASSET_URL = '/satellite-maneuver-detector/plotly-3.3.1.min.js';
  const MAX_HISTORY_RANGE_DAYS = 31;
  const MIN_EVALUATED_POINTS = 5;
  const PUBLIC_CACHE_MS = 2 * 60 * 60 * 1000;
  const DAY_MS = 24 * 60 * 60 * 1000;
  const CATALOGUE_REVISION_TOLERANCE_US = 1000000;
  const DEMO_ANCHOR_MS = Date.UTC(2026, 6, 20, 0, 0, 0);
  const EARTH_RADIUS_KM = 6378.137;
  const J2 = 1.08262668e-3;

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

  function validateFetchedRecords(data, norad, label) {
    const records = Array.isArray(data) ? data : [data];
    const parsed = validatedRecordsFromRaw(JSON.stringify(records), label);
    if (parsed.rejectedCount || parsed.records.some(record => Number(record.satId) !== Number(norad))) {
      throw new Error(label + ' contains invalid records or records for a different NORAD object. Existing input was retained.');
    }
    return parsed;
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function fmtTime(value) {
    if (!(value instanceof Date) || !Number.isFinite(value.getTime())) return String(value);
    return value.toISOString().replace('.000', '');
  }

  function fmtNum(value, digits) {
    return Number.isFinite(value) ? value.toFixed(digits) : 'n/a';
  }

  function median(values) {
    if (!values.length) return NaN;
    const sorted = values.slice().sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 1
      ? sorted[mid]
      : 0.5 * (sorted[mid - 1] + sorted[mid]);
  }

  function empiricalQuantile(values, probability) {
    if (!values.length) return NaN;
    const sorted = values.slice().sort((a, b) => a - b);
    const p = Math.min(1, Math.max(0, probability));
    const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(p * sorted.length) - 1));
    return sorted[index];
  }



  const FEATURE_LABELS = Object.freeze({
    aRate: 'Δa/Δt',
    meanMotionRate: 'Mean motion',
    radialRate: 'Radial residual',
    alongRate: 'Along-track residual',
    crossRate: 'Cross-track residual',
    eccentricityVectorRate: 'Eccentricity vector',
    inclinationVectorRate: 'Inclination vector',
    bstarRate: 'B*'
  });

  const PROFILE_LIBRARY = Object.freeze({
    LEO: {
      stateGateKm: 0.75,
      supportRequired: 2,
      scoreThreshold: 1.20,
      eventGapFactor: 2.5,
      floors: { aRate: 0.0001, meanMotionRate: 0.000002, radialRate: 0.08, alongRate: 0.35, crossRate: 0.08, eccentricityVectorRate: 0.000002, inclinationVectorRate: 0.000002, bstarRate: 0.00001 }
    },
    MEO: {
      stateGateKm: 1.5,
      supportRequired: 2,
      scoreThreshold: 1.25,
      eventGapFactor: 2.75,
      floors: { aRate: 0.0002, meanMotionRate: 0.0000005, radialRate: 0.15, alongRate: 0.70, crossRate: 0.15, eccentricityVectorRate: 0.000001, inclinationVectorRate: 0.000001, bstarRate: 0.000005 }
    },
    GEO: {
      stateGateKm: 3.0,
      supportRequired: 2,
      scoreThreshold: 1.20,
      eventGapFactor: 3.0,
      floors: { aRate: 0.0005, meanMotionRate: 0.00000005, radialRate: 0.25, alongRate: 1.2, crossRate: 0.25, eccentricityVectorRate: 0.0000005, inclinationVectorRate: 0.0000005, bstarRate: 0.000001 }
    },
    HEO: {
      stateGateKm: 3.0,
      supportRequired: 2,
      scoreThreshold: 1.30,
      eventGapFactor: 3.5,
      floors: { aRate: 0.0005, meanMotionRate: 0.0000001, radialRate: 0.40, alongRate: 1.5, crossRate: 0.40, eccentricityVectorRate: 0.000001, inclinationVectorRate: 0.000001, bstarRate: 0.000002 }
    }
  });

  function stableStringify(value) {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return '[' + value.map(stableStringify).join(',') + ']';
    return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stableStringify(value[key])).join(',') + '}';
  }

  function fnv1a64(text) {
    let hash = 0xcbf29ce484222325n;
    const prime = 0x100000001b3n;
    for (let index = 0; index < text.length; index++) {
      hash ^= BigInt(text.charCodeAt(index));
      hash = BigInt.asUintN(64, hash * prime);
    }
    return hash.toString(16).padStart(16, '0');
  }

  function vectorSubtract(first, second) {
    return { x: first.x - second.x, y: first.y - second.y, z: first.z - second.z };
  }

  function vectorDot(first, second) {
    return first.x * second.x + first.y * second.y + first.z * second.z;
  }

  function vectorCross(first, second) {
    return {
      x: first.y * second.z - first.z * second.y,
      y: first.z * second.x - first.x * second.z,
      z: first.x * second.y - first.y * second.x
    };
  }

  function vectorNorm(vector) {
    return Math.sqrt(vectorDot(vector, vector));
  }

  function vectorUnit(vector) {
    const norm = vectorNorm(vector);
    if (!Number.isFinite(norm) || norm <= 0) return null;
    return { x: vector.x / norm, y: vector.y / norm, z: vector.z / norm };
  }

  function inferOrbitProfile(records) {
    const periods = records.map(record => 1440 / record.meanMotion).filter(Number.isFinite);
    const eccentricities = records.map(record => record.elements.ecc).filter(Number.isFinite);
    const period = median(periods);
    const eccentricity = median(eccentricities);
    if (Number.isFinite(eccentricity) && eccentricity >= 0.25) return 'HEO';
    if (Number.isFinite(period) && period >= 1200 && period <= 1600) return 'GEO';
    if (Number.isFinite(period) && period >= 225) return 'MEO';
    return 'LEO';
  }

  function eccentricityVector(elements) {
    const longitude = radians((elements.raanDeg || 0) + (elements.argPerDeg || 0));
    return { x: elements.ecc * Math.cos(longitude), y: elements.ecc * Math.sin(longitude) };
  }

  function inclinationVector(elements) {
    const halfInclination = radians(elements.incDeg || 0) / 2;
    const raan = radians(elements.raanDeg || 0);
    const magnitude = Math.sin(halfInclination);
    return { x: magnitude * Math.cos(raan), y: magnitude * Math.sin(raan) };
  }

  function planarDistance(first, second) {
    return Math.hypot(first.x - second.x, first.y - second.y);
  }

  function parseTleExponentField(text) {
    const compact = String(text || '').replace(/\s/g, '');
    const match = compact.match(/^([+-]?)(\d{5})([+-]\d)$/);
    if (!match) return NaN;
    const sign = match[1] === '-' ? -1 : 1;
    return sign * Number('0.' + match[2]) * Math.pow(10, Number(match[3]));
  }


  function semiMajorAxisKm(meanMotionRevPerDay) {
    const n = meanMotionRevPerDay * 2 * Math.PI / 86400;
    return Math.cbrt(MU / (n * n));
  }

  function setStatus(kind, text) {
    const element = byId('status');
    element.textContent = text;
    element.className = 'badge ' + (kind || 'neutral');
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

  function checksumForTleCore(core) {
    let sum = 0;
    for (const character of core) {
      if (character >= '0' && character <= '9') sum += Number(character);
      else if (character === '-') sum += 1;
    }
    return String(sum % 10);
  }

  function addTleChecksum(core) {
    if (core.length !== 68) {
      throw new Error('TLE line core must contain exactly 68 characters.');
    }
    return core + checksumForTleCore(core);
  }

  function validateTleChecksum(line) {
    if (line.length !== 69 || !/\d/.test(line[68])) return false;
    return checksumForTleCore(line.slice(0, 68)) === line[68];
  }

  function dateToTleEpoch(date) {
    const year = date.getUTCFullYear();
    const start = Date.UTC(year, 0, 1);
    const dayOfYear = (date.getTime() - start) / DAY_MS + 1;
    return String(year % 100).padStart(2, '0') + dayOfYear.toFixed(8).padStart(12, '0');
  }

  function putField(buffer, start, width, value, alignRight) {
    const raw = String(value);
    const text = raw.length > width ? raw.slice(0, width) : raw;
    const padded = alignRight === false ? text.padEnd(width, ' ') : text.padStart(width, ' ');
    for (let index = 0; index < width; index++) buffer[start + index] = padded[index];
  }

  function fixedField(value, decimals, width) {
    const number = Number(value);
    const text = Number.isFinite(number) ? number.toFixed(decimals) : String(value);
    return text.padStart(width, ' ');
  }

  function eccentricityField(value) {
    if (typeof value === 'string' && /^\d{7}$/.test(value)) return value;
    const number = Number(value);
    if (!Number.isFinite(number)) return '0000000';
    return String(Math.round(Math.abs(number) * 10000000)).padStart(7, '0').slice(0, 7);
  }

  function makeTleBlock(name, satId, internationalDesignator, epochDate, meanMotion, inclination, raan, eccentricity, argumentOfPerigee, meanAnomaly, revolutionNumber) {
    const sat = String(satId).padStart(5, '0').slice(-5);
    const line1Buffer = new Array(68).fill(' ');
    line1Buffer[0] = '1';
    putField(line1Buffer, 2, 5, sat);
    line1Buffer[7] = 'U';
    putField(line1Buffer, 9, 8, internationalDesignator, false);
    putField(line1Buffer, 18, 14, dateToTleEpoch(epochDate));
    putField(line1Buffer, 33, 10, ' .00000000', false);
    putField(line1Buffer, 44, 8, ' 00000-0', false);
    putField(line1Buffer, 53, 8, ' 00000-0', false);
    line1Buffer[62] = '0';
    putField(line1Buffer, 64, 4, '9991');

    const line2Buffer = new Array(68).fill(' ');
    line2Buffer[0] = '2';
    putField(line2Buffer, 2, 5, sat);
    putField(line2Buffer, 8, 8, fixedField(inclination, 4, 8));
    putField(line2Buffer, 17, 8, fixedField(raan, 4, 8));
    putField(line2Buffer, 26, 7, eccentricityField(eccentricity));
    putField(line2Buffer, 34, 8, fixedField(argumentOfPerigee, 4, 8));
    putField(line2Buffer, 43, 8, fixedField(meanAnomaly, 4, 8));
    putField(line2Buffer, 52, 11, fixedField(meanMotion, 8, 11));
    putField(line2Buffer, 63, 5, String(revolutionNumber || 1).padStart(5, '0').slice(-5));

    return `${name}\n${addTleChecksum(line1Buffer.join(''))}\n${addTleChecksum(line2Buffer.join(''))}`;
  }

  function demoSecularRates(meanMotionRevPerDay, eccentricity, inclinationDeg) {
    const n = meanMotionRevPerDay * 2 * Math.PI / 86400;
    const a = Math.cbrt(MU / (n * n));
    const p = a * (1 - eccentricity * eccentricity);
    const cosI = Math.cos(radians(inclinationDeg));
    const factor = J2 * Math.pow(EARTH_RADIUS_KM / p, 2) * n;
    const radiansPerSecondToDegreesPerDay = 180 / Math.PI * 86400;
    return {
      raanDegPerDay: -1.5 * factor * cosI * radiansPerSecondToDegreesPerDay,
      argPerDegPerDay: 0.75 * factor * (5 * cosI * cosI - 1) * radiansPerSecondToDegreesPerDay,
      meanAnomDegPerDay: (n + 0.75 * factor * Math.sqrt(Math.max(0, 1 - eccentricity * eccentricity)) * (3 * cosI * cosI - 1)) * radiansPerSecondToDegreesPerDay
    };
  }

  function exampleDates(kind, count) {
    if (kind === 'sparse') {
      const ages = [24, 23.5, 23, 22.5, 22, 14, 13.5, 13, 5, 4.5, 4, 0];
      return ages.slice(0, count).map(age => new Date(DEMO_ANCHOR_MS - age * DAY_MS));
    }
    const stepDays = kind === 'geo' ? 0.25 : (5 / 1440);
    return Array.from({ length: count }, (_, index) => new Date(DEMO_ANCHOR_MS + index * stepDays * DAY_MS));
  }

  function buildDemoStates(kind, dates, meanMotions, inclination, baseRaan, eccentricity, argumentOfPerigee, initialMeanAnomaly, eventIndex) {
    const states = [{ inclination, raan: baseRaan, eccentricity, argumentOfPerigee, meanAnomaly: initialMeanAnomaly }];
    for (let index = 1; index < dates.length; index++) {
      const previous = states[index - 1];
      const dtDays = (dates[index] - dates[index - 1]) / DAY_MS;
      const nextInclination = kind === 'cross' && eventIndex !== null && index >= eventIndex ? inclination + 0.05 : previous.inclination;
      const nextEccentricity = kind === 'radial' && eventIndex !== null && index >= eventIndex ? eccentricity + 0.00035 : previous.eccentricity;
      const previousRates = demoSecularRates(meanMotions[index - 1], previous.eccentricity, previous.inclination);
      const nextRates = demoSecularRates(meanMotions[index], nextEccentricity, nextInclination);
      states.push({
        inclination: nextInclination,
        raan: (previous.raan + 0.5 * (previousRates.raanDegPerDay + nextRates.raanDegPerDay) * dtDays + 360) % 360,
        eccentricity: nextEccentricity,
        argumentOfPerigee: (previous.argumentOfPerigee + 0.5 * (previousRates.argPerDegPerDay + nextRates.argPerDegPerDay) * dtDays + 360) % 360,
        meanAnomaly: (previous.meanAnomaly + 0.5 * (previousRates.meanAnomDegPerDay + nextRates.meanAnomDegPerDay) * dtDays + 360000) % 360
      });
    }
    return states;
  }

  function exampleTles(kind) {
    let meanMotions;
    let dates;
    let name;
    let satId;
    let internationalDesignator;
    let inclination;
    let baseRaan;
    let eccentricity;
    let argumentOfPerigee;
    let initialMeanAnomaly;
    let eventIndex = null;

    if (kind === 'geo') {
      meanMotions = new Array(16).fill(1.0027120);
      eventIndex = 12;
      for (let index = eventIndex; index < meanMotions.length; index++) meanMotions[index] += 0.0000780;
      name = 'DEMO GEO STATION-KEEPING OBJECT'; satId = '90002'; internationalDesignator = '26002A';
      inclination = 0.0410; baseRaan = 80; eccentricity = 0.0001800; argumentOfPerigee = 85; initialMeanAnomaly = 275;
    } else if (kind === 'quiet') {
      meanMotions = new Array(16).fill(15.497550);
      name = 'DEMO QUIET LEO OBJECT'; satId = '90004'; internationalDesignator = '26004A';
      inclination = 51.64; baseRaan = 85; eccentricity = 0.0004769; argumentOfPerigee = 96.2942; initialMeanAnomaly = 50.7467;
    } else if (kind === 'sparse') {
      meanMotions = new Array(12).fill(15.497550); eventIndex = 7; meanMotions[eventIndex] += 0.000350;
      name = 'DEMO SPARSE LEO OBJECT'; satId = '90003'; internationalDesignator = '26003A';
      inclination = 51.64; baseRaan = 85; eccentricity = 0.0004769; argumentOfPerigee = 96.2942; initialMeanAnomaly = 50.7467;
    } else if (kind === 'radial') {
      meanMotions = new Array(16).fill(15.497550); eventIndex = 11;
      name = 'FIXTURE RADIAL IMPULSE OBJECT'; satId = '90005'; internationalDesignator = '26005A';
      inclination = 51.64; baseRaan = 85; eccentricity = 0.0004500; argumentOfPerigee = 96.2942; initialMeanAnomaly = 90;
    } else if (kind === 'cross') {
      meanMotions = new Array(16).fill(15.497550); eventIndex = 11;
      name = 'FIXTURE CROSS-TRACK IMPULSE OBJECT'; satId = '90006'; internationalDesignator = '26006A';
      inclination = 51.64; baseRaan = 85; eccentricity = 0.0004769; argumentOfPerigee = 96.2942; initialMeanAnomaly = 140.0;
    } else if (kind === 'finite') {
      meanMotions = new Array(18).fill(15.497550); eventIndex = 10;
      meanMotions[eventIndex] += 0.000500; meanMotions[eventIndex + 1] += 0.001000;
      for (let index = eventIndex + 2; index < meanMotions.length; index++) meanMotions[index] += 0.001500;
      name = 'FIXTURE FINITE-DURATION ALONG-TRACK OBJECT'; satId = '90007'; internationalDesignator = '26007A';
      inclination = 51.64; baseRaan = 85; eccentricity = 0.0004769; argumentOfPerigee = 96.2942; initialMeanAnomaly = 50.7467;
    } else {
      meanMotions = new Array(16).fill(15.497550); eventIndex = 11;
      for (let index = eventIndex; index < meanMotions.length; index++) meanMotions[index] += 0.001500;
      name = 'DEMO LEO ALONG-TRACK MANEUVER OBJECT'; satId = '90001'; internationalDesignator = '26001A';
      inclination = 51.64; baseRaan = 85; eccentricity = 0.0004769; argumentOfPerigee = 96.2942; initialMeanAnomaly = 50.7467;
    }

    dates = exampleDates(kind, meanMotions.length);
    const states = buildDemoStates(kind, dates, meanMotions, inclination, baseRaan, eccentricity, argumentOfPerigee, initialMeanAnomaly, eventIndex);
    return meanMotions.map((meanMotion, index) => makeTleBlock(
      name, satId, internationalDesignator, dates[index], meanMotion,
      states[index].inclination, states[index].raan, states[index].eccentricity,
      states[index].argumentOfPerigee, states[index].meanAnomaly, 100 + index
    )).join('\n');
  }

  function parseTleEpoch(line1) {
    const epochString = line1.slice(18, 32);
    if (!/^\d{5}\.\d{8}$/.test(epochString)) return null;

    const twoDigitYear = Number(epochString.slice(0, 2));
    const year = twoDigitYear < 57 ? 2000 + twoDigitYear : 1900 + twoDigitYear;
    const dayOfYear = Number(epochString.slice(2, 5));
    const fractionUnits = Number(epochString.slice(6));
    const leap = new Date(Date.UTC(year, 1, 29)).getUTCDate() === 29;
    const maximumDay = leap ? 366 : 365;
    // TLE day 000 denotes the preceding 31 December. One fractional-day unit
    // is exactly 864 microseconds; never pass the fraction through Date.
    if (dayOfYear > maximumDay) return null;
    const epochUs = (Date.UTC(year, 0, 1) + (dayOfYear - 1) * DAY_MS) * 1000 + fractionUnits * 864;
    const t = new Date(Math.floor(epochUs / 1000));
    return { t, epochUs, raw: formatEpochUs(epochUs) };
  }

  function formatEpochUs(epochUs) {
    if (!Number.isSafeInteger(epochUs)) throw new Error('Epoch must be an exact integer number of microseconds.');
    const epochMs = Math.floor(epochUs / 1000);
    const remainderUs = epochUs - epochMs * 1000;
    return new Date(epochMs).toISOString().replace(/\.(\d{3})Z$/, (_, milliseconds) =>
      '.' + milliseconds + String(remainderUs).padStart(3, '0') + 'Z');
  }

  function parseFiniteField(text) {
    if (typeof text !== 'string' && typeof text !== 'number') return NaN;
    const trimmed = String(text).trim();
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(trimmed)) return NaN;
    const value = Number(trimmed);
    return Number.isFinite(value) ? value : NaN;
  }

  function parseTlePair(name, line1Raw, line2Raw) {
    const line1 = line1Raw.replace(/\s+$/, '');
    const line2 = line2Raw.replace(/\s+$/, '');
    const errors = [];

    if (line1.length !== 69) errors.push('line 1 must contain 69 characters including checksum');
    if (line2.length !== 69) errors.push('line 2 must contain 69 characters including checksum');
    if (line1[0] !== '1') errors.push('first record is not TLE line 1');
    if (line2[0] !== '2') errors.push('second record is not TLE line 2');

    if (!errors.length) {
      if (!validateTleChecksum(line1)) errors.push('line 1 checksum failed');
      if (!validateTleChecksum(line2)) errors.push('line 2 checksum failed');
    }

    const satId1 = line1.length >= 7 ? line1.slice(2, 7).trim() : '';
    const satId2 = line2.length >= 7 ? line2.slice(2, 7).trim() : '';
    if (!satId1 || !satId2 || satId1 !== satId2) errors.push('catalog identifiers do not match');

    const epochInfo = line1.length >= 32 ? parseTleEpoch(line1) : null;
    if (!epochInfo) errors.push('epoch field is invalid');

    const inclination = line2.length >= 16 ? parseFiniteField(line2.slice(8, 16)) : NaN;
    const raan = line2.length >= 25 ? parseFiniteField(line2.slice(17, 25)) : NaN;
    const eccentricityText = line2.length >= 33 ? line2.slice(26, 33) : '';
    const eccentricity = /^\d{7}$/.test(eccentricityText) ? Number('0.' + eccentricityText) : NaN;
    const argumentOfPerigee = line2.length >= 42 ? parseFiniteField(line2.slice(34, 42)) : NaN;
    const meanAnomaly = line2.length >= 51 ? parseFiniteField(line2.slice(43, 51)) : NaN;
    const meanMotion = line2.length >= 63 ? parseFiniteField(line2.slice(52, 63)) : NaN;
    const meanMotionDot = line1.length >= 43 ? parseFiniteField(line1.slice(33, 43)) : NaN;
    // Entirely blank exponent fields are defined as zero in the TLE format.
    const meanMotionDdot = line1.length >= 52 ? (line1.slice(44, 52).trim() === '' ? 0 : parseTleExponentField(line1.slice(44, 52))) : NaN;
    const bstar = line1.length >= 61 ? (line1.slice(53, 61).trim() === '' ? 0 : parseTleExponentField(line1.slice(53, 61))) : NaN;
    const elementSetNo = line1.length >= 68 ? parseFiniteField(line1.slice(64, 68)) : NaN;
    const revolutionAtEpoch = line2.length >= 68 ? parseFiniteField(line2.slice(63, 68)) : NaN;
    const ephemerisType = line1.length >= 63 ? parseFiniteField(line1[62]) : NaN;

    if (!Number.isFinite(inclination) || inclination < 0 || inclination > 180) errors.push('inclination is outside 0 to 180 degrees');
    if (!Number.isFinite(raan) || raan < 0 || raan >= 360) errors.push('RAAN is outside 0 to 360 degrees');
    if (!Number.isFinite(eccentricity) || eccentricity < 0 || eccentricity >= 1) errors.push('eccentricity is outside 0 to 1');
    if (!Number.isFinite(argumentOfPerigee) || argumentOfPerigee < 0 || argumentOfPerigee >= 360) errors.push('argument of perigee is outside 0 to 360 degrees');
    if (!Number.isFinite(meanAnomaly) || meanAnomaly < 0 || meanAnomaly >= 360) errors.push('mean anomaly is outside 0 to 360 degrees');
    if (!Number.isFinite(meanMotion) || meanMotion <= 0) errors.push('mean motion must be positive');
    if (!Number.isFinite(meanMotionDot)) errors.push('mean motion first derivative is invalid');
    if (!Number.isFinite(meanMotionDdot)) errors.push('mean motion second derivative is invalid');
    if (!Number.isFinite(bstar)) errors.push('BSTAR drag field is invalid');
    if (!Number.isInteger(elementSetNo) || elementSetNo < 0) errors.push('element set number must be a non-negative integer');
    if (!Number.isInteger(revolutionAtEpoch) || revolutionAtEpoch < 0) errors.push('revolution number must be a non-negative integer');
    if (![0, 2, 3].includes(ephemerisType)) errors.push('ephemeris type must use SGP4/SDP4 (0, 2 or 3)');

    if (errors.length) return { record: null, errors };

    return {
      record: {
        t: epochInfo.t,
        epochUs: epochInfo.epochUs,
        epochRaw: epochInfo.raw,
        a: semiMajorAxisKm(meanMotion),
        meanMotion,
        meanMotionDot: Number.isFinite(meanMotionDot) ? meanMotionDot : 0,
        meanMotionDdot: Number.isFinite(meanMotionDdot) ? meanMotionDdot : 0,
        bstar: Number.isFinite(bstar) ? bstar : 0,
        satId: satId1,
        objectId: line1.slice(9, 17).trim(),
        name: name || '',
        classificationType: line1[7] || 'U',
        // A valid TLE must contain its element-set number, including zero.
        elementSetNoKnown: true,
        elementSetNo,
        revolutionAtEpoch: Number.isFinite(revolutionAtEpoch) ? revolutionAtEpoch : 0,
        ephemerisType,
        elements: {
          incDeg: inclination,
          raanDeg: raan,
          ecc: eccentricity,
          argPerDeg: argumentOfPerigee,
          meanAnomDeg: meanAnomaly,
          meanMotion
        },
        line1,
        line2,
        sourceFormat: 'TLE'
      },
      errors: []
    };
  }

  function parseTleInput(raw) {
    const lines = raw
      .split(/\r?\n/)
      .map(line => line.replace(/\s+$/, ''))
      .filter(line => line.trim().length > 0);

    const records = [];
    const rejectionReasons = [];
    let line1Candidates = 0;
    let line2Candidates = 0;
    let pairCandidates = 0;

    for (const line of lines) {
      if (/^1\s/.test(line)) line1Candidates++;
      if (/^2\s/.test(line)) line2Candidates++;
    }

    for (let index = 0; index < lines.length; index++) {
      const line = lines[index];
      if (!/^1\s/.test(line)) continue;

      if (index + 1 >= lines.length || !/^2\s/.test(lines[index + 1])) {
        rejectionReasons.push('line 1 without an immediately following line 2');
        continue;
      }

      pairCandidates++;
      let name = '';
      if (index > 0 && !/^[12]\s/.test(lines[index - 1])) name = lines[index - 1].trim();

      const parsed = parseTlePair(name, line, lines[index + 1]);
      if (parsed.record) records.push(parsed.record);
      else rejectionReasons.push(parsed.errors.join('; '));
      index++;
    }

    return {
      format: 'TLE',
      records,
      totalLines: lines.length,
      line1Candidates,
      line2Candidates,
      pairCandidates,
      rejectedCount: rejectionReasons.length,
      rejectionReasons
    };
  }

  function upperCaseKeys(object) {
    const result = {};
    Object.keys(object || {}).forEach(key => {
      result[String(key).toUpperCase()] = object[key];
    });
    return result;
  }

  function parseOmmEpochUtc(value) {
    if (typeof value !== 'string') return null;
    const raw = value.trim();
    const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?$/i);
    if (!match) return null;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const monthLengths = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    // Date alone silently rolls invalid dates such as February 30 into March.
    if (month < 1 || month > 12 || day < 1 || day > monthLengths[month - 1] ||
        Number(match[4]) > 23 || Number(match[5]) > 59 || Number(match[6]) > 59) return null;
    const zone = match[8] || '';
    if (zone && zone.toUpperCase() !== 'Z' && (Number(zone.slice(1, 3)) > 23 || Number(zone.slice(4)) > 59)) return null;
    const normalized = zone ? raw : raw + 'Z';
    const t = new Date(normalized);
    if (!Number.isFinite(t.getTime())) return null;
    const fraction = match[7] || '';
    const microRemainder = Number(fraction.slice(3, 6).padEnd(3, '0'));
    const epochUs = t.getTime() * 1000 + microRemainder;
    if (!Number.isSafeInteger(epochUs)) return null;
    return { t, epochUs, raw, normalized };
  }

  function recordEpochUs(record) {
    if (record && Number.isSafeInteger(record.epochUs)) return record.epochUs;
    return record && record.t instanceof Date ? record.t.getTime() * 1000 : NaN;
  }

  function compareRecordEpochs(first, second) {
    return recordEpochUs(first) - recordEpochUs(second);
  }

  function parseOmmRecord(rawRecord) {
    if (!rawRecord || typeof rawRecord !== 'object' || Array.isArray(rawRecord)) {
      return { record: null, errors: ['Each OMM record must be a JSON object.'] };
    }
    const record = upperCaseKeys(rawRecord);
    const errors = [];
    const epochInfo = parseOmmEpochUtc(record.EPOCH);
    const creationInfo = parseOmmEpochUtc(record.CREATION_DATE);
    const elementSetRaw = record.ELEMENT_SET_NO;
    const isOmitted = value => value === undefined || value === null || (typeof value === 'string' && value.trim() === '');
    const elementSetNoKnown = !isOmitted(elementSetRaw);
    // Preserve TLE origin through normalisation because near-epoch revision
    // handling distinguishes native OMM records from TLE-derived records.
    const sourceFormat = isOmitted(record.SMD_SOURCE_FORMAT) ? 'OMM JSON'
      : typeof record.SMD_SOURCE_FORMAT === 'string' ? record.SMD_SOURCE_FORMAT.trim().toUpperCase() : '';
    if (!['TLE', 'OMM JSON'].includes(sourceFormat)) errors.push('SMD_SOURCE_FORMAT must be TLE or OMM JSON when provided');
    const optionalNumber = (key, fallback) => {
      if (isOmitted(record[key])) return fallback;
      const value = parseFiniteField(record[key]);
      if (!Number.isFinite(value)) errors.push(key + ' must be a finite number when provided');
      return value;
    };
    const meanMotionDot = optionalNumber('MEAN_MOTION_DOT', 0);
    const meanMotionDdot = optionalNumber('MEAN_MOTION_DDOT', 0);
    const bstar = optionalNumber('BSTAR', 0);
    const elementSetNo = optionalNumber('ELEMENT_SET_NO', 999);
    const revolutionAtEpoch = optionalNumber('REV_AT_EPOCH', 0);
    const ephemerisType = optionalNumber('EPHEMERIS_TYPE', 0);
    if (!Number.isSafeInteger(elementSetNo) || elementSetNo < 0) errors.push('ELEMENT_SET_NO must be a non-negative integer');
    if (!Number.isSafeInteger(revolutionAtEpoch) || revolutionAtEpoch < 0) errors.push('REV_AT_EPOCH must be a non-negative integer');
    if (![0, 2, 3].includes(ephemerisType)) errors.push('EPHEMERIS_TYPE must use SGP4/SDP4 (0, 2 or 3)');
    if (!isOmitted(record.CREATION_DATE) && !creationInfo) errors.push('CREATION_DATE must be a valid ISO date and time');
    // CelesTrak GP JSON intentionally omits these redundant metadata fields.
    for (const [key, expected] of [['CENTER_NAME', 'EARTH'], ['REF_FRAME', 'TEME'], ['TIME_SYSTEM', 'UTC'], ['MEAN_ELEMENT_THEORY', 'SGP4']]) {
      if (!isOmitted(record[key]) && (typeof record[key] !== 'string' || record[key].trim().toUpperCase() !== expected)) {
        errors.push(key + ' must be ' + expected + '; this workbench cannot convert other centres, frames, time systems or element theories');
      }
    }
    const epoch = epochInfo ? epochInfo.t : null;
    const satId = typeof record.NORAD_CAT_ID === 'string' || typeof record.NORAD_CAT_ID === 'number'
      ? String(record.NORAD_CAT_ID).trim()
      : '';
    const meanMotion = parseFiniteField(record.MEAN_MOTION);
    const eccentricity = parseFiniteField(record.ECCENTRICITY);
    const inclination = parseFiniteField(record.INCLINATION);
    const raan = parseFiniteField(record.RA_OF_ASC_NODE);
    const argumentOfPerigee = parseFiniteField(record.ARG_OF_PERICENTER);
    const meanAnomaly = parseFiniteField(record.MEAN_ANOMALY);

    if (!/^[0-9]{1,9}$/.test(satId) || Number(satId) < 1) errors.push('NORAD_CAT_ID is missing or invalid');
    if (!epoch || !Number.isFinite(epoch.getTime())) errors.push('EPOCH must be a valid ISO date and time, such as 2026-07-06T02:08:05.621280Z');
    if (!Number.isFinite(meanMotion) || meanMotion <= 0) errors.push('MEAN_MOTION must be positive');
    if (!Number.isFinite(eccentricity) || eccentricity < 0 || eccentricity >= 1) errors.push('ECCENTRICITY is outside 0 to 1');
    if (!Number.isFinite(inclination) || inclination < 0 || inclination > 180) errors.push('INCLINATION is outside 0 to 180 degrees');
    if (!Number.isFinite(raan) || raan < 0 || raan >= 360) errors.push('RA_OF_ASC_NODE is outside 0 to 360 degrees');
    if (!Number.isFinite(argumentOfPerigee) || argumentOfPerigee < 0 || argumentOfPerigee >= 360) errors.push('ARG_OF_PERICENTER is outside 0 to 360 degrees');
    if (!Number.isFinite(meanAnomaly) || meanAnomaly < 0 || meanAnomaly >= 360) errors.push('MEAN_ANOMALY is outside 0 to 360 degrees');

    if (errors.length) return { record: null, errors };

    const parsedRecord = {
      t: epoch,
      epochUs: epochInfo.epochUs,
      epochRaw: epochInfo.raw,
      a: semiMajorAxisKm(meanMotion),
      meanMotion,
      meanMotionDot,
      meanMotionDdot,
      bstar,
      satId,
      objectId: record.OBJECT_ID ? String(record.OBJECT_ID).trim() : '',
      name: record.OBJECT_NAME ? String(record.OBJECT_NAME).trim() : '',
      classificationType: record.CLASSIFICATION_TYPE ? String(record.CLASSIFICATION_TYPE).trim() : 'U',
      creationUs: creationInfo ? creationInfo.epochUs : null,
      creationRaw: creationInfo ? creationInfo.raw : '',
      gpId: record.GP_ID === undefined || record.GP_ID === null ? '' : String(record.GP_ID).trim(),
      elementSetNoKnown,
      elementSetNo,
      revolutionAtEpoch,
      ephemerisType,
      elements: {
        incDeg: inclination,
        raanDeg: raan,
        ecc: eccentricity,
        argPerDeg: argumentOfPerigee,
        meanAnomDeg: meanAnomaly,
        meanMotion
      },
      omm: rawRecord,
      sourceFormat
    };
    if (Object.prototype.hasOwnProperty.call(record, 'SMD_TLE')) {
      const source = record.SMD_TLE;
      if (!source || typeof source !== 'object' || Array.isArray(source) ||
          source.schema_version !== TLE_SOURCE_SCHEMA_VERSION ||
          typeof source.line1 !== 'string' || typeof source.line2 !== 'string' ||
          sourceFormat !== 'TLE') {
        return { record: null, errors: ['SMD_TLE must contain a supported schema_version and both original TLE lines with SMD_SOURCE_FORMAT set to TLE'] };
      }
      const retained = parseTlePair(parsedRecord.name, source.line1, source.line2);
      if (!retained.record) {
        return { record: null, errors: retained.errors.map(error => 'SMD_TLE: ' + error) };
      }
      const original = retained.record;
      const comparisons = [
        ['EPOCH', parsedRecord.epochUs, original.epochUs],
        ['NORAD_CAT_ID', Number(parsedRecord.satId), Number(original.satId)],
        ['OBJECT_ID', parsedRecord.objectId, original.objectId],
        ['CLASSIFICATION_TYPE', parsedRecord.classificationType, original.classificationType],
        ['ELEMENT_SET_NO', parsedRecord.elementSetNoKnown ? parsedRecord.elementSetNo : null, original.elementSetNo],
        ['REV_AT_EPOCH', parsedRecord.revolutionAtEpoch, original.revolutionAtEpoch],
        ['EPHEMERIS_TYPE', parsedRecord.ephemerisType, original.ephemerisType],
        ['MEAN_MOTION', parsedRecord.meanMotion, original.meanMotion],
        ['MEAN_MOTION_DOT', parsedRecord.meanMotionDot, original.meanMotionDot],
        ['MEAN_MOTION_DDOT', parsedRecord.meanMotionDdot, original.meanMotionDdot],
        ['BSTAR', parsedRecord.bstar, original.bstar],
        ['ECCENTRICITY', parsedRecord.elements.ecc, original.elements.ecc],
        ['INCLINATION', parsedRecord.elements.incDeg, original.elements.incDeg],
        ['RA_OF_ASC_NODE', parsedRecord.elements.raanDeg, original.elements.raanDeg],
        ['ARG_OF_PERICENTER', parsedRecord.elements.argPerDeg, original.elements.argPerDeg],
        ['MEAN_ANOMALY', parsedRecord.elements.meanAnomDeg, original.elements.meanAnomDeg]
      ];
      for (const [field, visible, retainedValue] of comparisons) {
        if (visible !== retainedValue) errors.push('SMD_TLE disagrees with ' + field);
      }
      if (errors.length) return { record: null, errors };
      parsedRecord.line1 = original.line1;
      parsedRecord.line2 = original.line2;
    }
    return { record: parsedRecord, errors: [] };
  }

  function parseOmmInput(raw) {
    let decoded;
    try {
      decoded = JSON.parse(raw);
    } catch (error) {
      return {
        format: 'OMM JSON',
        records: [],
        totalRecords: 0,
        rejectedCount: 1,
        rejectionReasons: ['JSON could not be parsed: ' + error.message],
        fatalMessage: 'The input looks like JSON but could not be parsed.'
      };
    }

    let items;
    if (Array.isArray(decoded)) items = decoded;
    else if (decoded && Array.isArray(decoded.records)) items = decoded.records;
    else if (decoded && typeof decoded === 'object') items = [decoded];
    else items = [];

    const records = [];
    const rejectionReasons = [];
    items.forEach(item => {
      const parsed = parseOmmRecord(item);
      if (parsed.record) records.push(parsed.record);
      else rejectionReasons.push(parsed.errors.join('; '));
    });

    return {
      format: 'OMM JSON',
      records,
      totalRecords: items.length,
      rejectedCount: rejectionReasons.length,
      rejectionReasons
    };
  }

  function parseInput(raw) {
    const text = typeof raw === 'string' ? raw : '';
    const trimmed = text.trim();
    if (!trimmed) {
      return {
        format: 'unknown',
        records: [],
        rejectedCount: 0,
        rejectionReasons: [],
        fatalMessage: 'No orbital-element history was provided.'
      };
    }

    if (trimmed.startsWith('{') || trimmed.startsWith('[')) return parseOmmInput(trimmed);
    return parseTleInput(raw);
  }

  function recordToOmm(record) {
    return {
      OBJECT_NAME: record.name || undefined,
      OBJECT_ID: record.objectId || undefined,
      EPOCH: record.epochRaw || record.t.toISOString(),
      CREATION_DATE: record.creationRaw || undefined,
      GP_ID: record.gpId || undefined,
      ...(record.sourceFormat === 'TLE' ? { SMD_SOURCE_FORMAT: 'TLE' } : {}),
      ...(record.line1 && record.line2
        ? { SMD_TLE: { schema_version: TLE_SOURCE_SCHEMA_VERSION, line1: record.line1, line2: record.line2 } } : {}),
      MEAN_MOTION: record.meanMotion,
      ECCENTRICITY: record.elements.ecc,
      INCLINATION: record.elements.incDeg,
      RA_OF_ASC_NODE: record.elements.raanDeg,
      ARG_OF_PERICENTER: record.elements.argPerDeg,
      MEAN_ANOMALY: record.elements.meanAnomDeg,
      EPHEMERIS_TYPE: Number.isFinite(record.ephemerisType) ? record.ephemerisType : 0,
      CLASSIFICATION_TYPE: record.classificationType || 'U',
      NORAD_CAT_ID: record.satId,
      ...(record.elementSetNoKnown === true && Number.isSafeInteger(record.elementSetNo) && record.elementSetNo >= 0
        ? { ELEMENT_SET_NO: record.elementSetNo } : {}),
      REV_AT_EPOCH: Number.isFinite(record.revolutionAtEpoch) ? record.revolutionAtEpoch : 0,
      BSTAR: Number.isFinite(record.bstar) ? record.bstar : 0,
      MEAN_MOTION_DOT: Number.isFinite(record.meanMotionDot) ? record.meanMotionDot : 0,
      MEAN_MOTION_DDOT: Number.isFinite(record.meanMotionDdot) ? record.meanMotionDdot : 0
    };
  }

  function serialiseRecordsAsOmm(records) {
    return JSON.stringify(records.map(recordToOmm), (key, value) => value === undefined ? undefined : value, 2);
  }

  function validatedRecordsFromRaw(raw, label) {
    const parsed = parseInput(raw);
    if (parsed.fatalMessage || !parsed.records.length) {
      const reason = parsed.fatalMessage || parsed.rejectionReasons[0] || 'No valid records were found.';
      throw new Error((label || 'Input') + ' failed validation: ' + reason);
    }
    return parsed;
  }

  function mergeOrbitalHistories(existingRaw, incomingRaw) {
    const existing = validatedRecordsFromRaw(existingRaw, 'Current input');
    const incoming = validatedRecordsFromRaw(incomingRaw, 'Incoming data');
    const combined = existing.records.concat(incoming.records).sort(compareRecordEpochs);
    const identifiers = new Set(combined.map(record => String(record.satId || '').toUpperCase()).filter(Boolean));
    if (identifiers.size > 1) throw new Error('The incoming data belongs to a different catalog object. Existing input was not changed.');
    const resolved = resolveCatalogueRevisions(combined);
    if (resolved.conflictingDuplicateCount > 0 || resolved.unresolvedNearSimultaneousCount > 0) {
      throw new Error('The incoming data contains an unresolved conflicting or near-simultaneous catalogue solution. Existing input was not changed.');
    }
    const records = resolved.records;
    return {
      records,
      duplicateCount: resolved.exactDuplicateCount + resolved.supersededRecords.length,
      replacementCount: resolved.replacementCount,
      addedCount: Math.max(0, records.length - existing.records.length),
      existingFormat: existing.format,
      incomingFormat: incoming.format,
      // Metadata-only enrichment is an input change even when neither the
      // number of observations nor the selected orbital values has changed.
      unchanged: serialiseRecordsAsOmm(records) === serialiseRecordsAsOmm(existing.records)
    };
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

  function mergeInputProvenance(existingRecords, incomingRecords, mergedRecords, incomingProvenance) {
    if (!currentInputProvenance && !incomingProvenance) return null;
    const previous = validateInputProvenance(currentInputProvenance, existingRecords);
    const sources = (previous ? previous.sources : [unrecordedInputSource(existingRecords)])
      .concat(incomingProvenance ? incomingProvenance.sources : [unrecordedInputSource(incomingRecords)]);
    const unique = new Map(sources.map(source => [stableStringify(source), source]));
    return makeInputProvenance(mergedRecords, Array.from(unique.values()));
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

  function recordsConflict(first, second) {
    return first.satId !== second.satId ||
      Math.abs(first.meanMotion - second.meanMotion) > 1e-10 ||
      Math.abs(first.elements.ecc - second.elements.ecc) > 1e-10 ||
      Math.abs(first.elements.incDeg - second.elements.incDeg) > 1e-7 ||
      Math.abs(first.elements.raanDeg - second.elements.raanDeg) > 1e-7 ||
      Math.abs(first.elements.argPerDeg - second.elements.argPerDeg) > 1e-7 ||
      Math.abs(first.elements.meanAnomDeg - second.elements.meanAnomDeg) > 1e-7 ||
      Math.abs(Number(first.bstar || 0) - Number(second.bstar || 0)) > 1e-12;
  }


  function compareCatalogueIdentifier(first, second) {
    const firstText = String(first || '').trim();
    const secondText = String(second || '').trim();
    if (firstText === secondText) return 0;
    if (/^\d+$/.test(firstText) && /^\d+$/.test(secondText)) {
      const firstNumber = BigInt(firstText);
      const secondNumber = BigInt(secondText);
      if (firstNumber === secondNumber) return 0;
      return secondNumber > firstNumber ? 1 : -1;
    }
    return secondText > firstText ? 1 : -1;
  }

  function catalogueMetadataPreference(first, second) {
    const firstCreationKnown = Number.isSafeInteger(first && first.creationUs);
    const secondCreationKnown = Number.isSafeInteger(second && second.creationUs);
    if (firstCreationKnown && secondCreationKnown && first.creationUs !== second.creationUs) return second.creationUs > first.creationUs ? 1 : -1;
    if (firstCreationKnown !== secondCreationKnown) return secondCreationKnown ? 1 : -1;
    const firstSetKnown = Boolean(first && first.elementSetNoKnown && Number.isFinite(first.elementSetNo));
    const secondSetKnown = Boolean(second && second.elementSetNoKnown && Number.isFinite(second.elementSetNo));
    if (firstSetKnown && secondSetKnown && first.elementSetNo !== second.elementSetNo) return second.elementSetNo > first.elementSetNo ? 1 : -1;
    if (firstSetKnown !== secondSetKnown) return secondSetKnown ? 1 : -1;
    const firstGp = first && first.gpId ? String(first.gpId) : '';
    const secondGp = second && second.gpId ? String(second.gpId) : '';
    if (firstGp || secondGp) {
      if (!firstGp) return 1;
      if (!secondGp) return -1;
      return compareCatalogueIdentifier(firstGp, secondGp);
    }
    return 0;
  }

  function catalogueRevisionAudit(superseded, retained, reason) {
    return {
      reason,
      superseded_epoch: superseded.epochRaw || superseded.t.toISOString(),
      retained_epoch: retained.epochRaw || retained.t.toISOString(),
      superseded_creation_date: superseded.creationRaw || null,
      retained_creation_date: retained.creationRaw || null,
      superseded_element_set_no: superseded.elementSetNoKnown ? superseded.elementSetNo : null,
      retained_element_set_no: retained.elementSetNoKnown ? retained.elementSetNo : null,
      superseded_gp_id: superseded.gpId || null,
      retained_gp_id: retained.gpId || null
    };
  }

  function resolveCatalogueRevisions(inputRecords) {
    // Resolve the strongest supplied metadata first within an exact epoch so
    // a later correction cannot leave an earlier unqualified conflict behind.
    const records = inputRecords.slice().sort((first, second) =>
      compareRecordEpochs(first, second) || catalogueMetadataPreference(first, second));
    const retained = [];
    const supersededRecords = [];
    let exactDuplicateCount = 0;
    let conflictingDuplicateCount = 0;
    let unresolvedNearSimultaneousCount = 0;
    let replacementCount = 0;

    records.forEach(record => {
      if (!retained.length) { retained.push(record); return; }
      const previous = retained[retained.length - 1];
      const deltaUs = recordEpochUs(record) - recordEpochUs(previous);
      const exactEpoch = deltaUs === 0;
      const nearOmmPair = deltaUs >= 0 && deltaUs <= CATALOGUE_REVISION_TOLERANCE_US && previous.sourceFormat === 'OMM JSON' && record.sourceFormat === 'OMM JSON';
      if (!exactEpoch && !nearOmmPair) { retained.push(record); return; }

      const conflict = recordsConflict(previous, record);
      const preference = catalogueMetadataPreference(previous, record);
      if (!conflict && exactEpoch) {
        exactDuplicateCount++;
        // An equivalent OMM copy must not erase TLE origin and thereby merge
        // a nearby observation under the native-OMM revision rule.
        const preserveTleOrigin = preference === 0 && previous.sourceFormat === 'OMM JSON' && record.sourceFormat === 'TLE';
        const preserveTleSource = preference === 0 && !(previous.line1 && previous.line2) && Boolean(record.line1 && record.line2);
        if (preference > 0 || preserveTleOrigin || preserveTleSource) retained[retained.length - 1] = record;
        return;
      }
      if (!conflict && !exactEpoch) {
        if (preference === 0) { retained.push(record); return; }
        const winner = preference > 0 ? record : previous;
        const loser = preference > 0 ? previous : record;
        supersededRecords.push(catalogueRevisionAudit(loser, winner, 'near-simultaneous duplicate catalogue solution'));
        if (preference > 0) retained[retained.length - 1] = record;
        return;
      }
      if (preference === 0) {
        if (exactEpoch) conflictingDuplicateCount++;
        else unresolvedNearSimultaneousCount++;
        retained.push(record);
        return;
      }
      const winner = preference > 0 ? record : previous;
      const loser = preference > 0 ? previous : record;
      supersededRecords.push(catalogueRevisionAudit(loser, winner, 'deterministic catalogue supersession'));
      replacementCount++;
      if (preference > 0) retained[retained.length - 1] = record;
    });

    return { records: retained, exactDuplicateCount, conflictingDuplicateCount, unresolvedNearSimultaneousCount, supersededRecords, replacementCount };
  }

  function classifySeverity(score) {
    if (!Number.isFinite(score)) return 'n/a';
    if (score >= 3) return 'Strong';
    if (score >= 2) return 'Moderate';
    return 'Weak';
  }

  function hasSgp4Support() {
    return Boolean(window.satellite && ['sgp4', 'twoline2satrec', 'json2satrec']
      .every(method => typeof window.satellite[method] === 'function'));
  }

  function satrecForRecord(record) {
    if (!window.satellite || !record) return null;
    if (record._satrec) return record._satrec;
    try {
      if (record.line1 && record.line2) {
        // satellite.js does not interpret the documented all-blank TLE exponent
        // fields as zero. Normalise only its input, retaining the source record.
        let line1 = record.line1;
        for (const start of [44, 53]) {
          if (line1.slice(start, start + 8).trim() === '') {
            line1 = line1.slice(0, start) + ' 00000-0' + line1.slice(start + 8);
          }
        }
        record._satrec = window.satellite.twoline2satrec(line1, record.line2);
      } else {
        // satellite.js 6.0.2 initialises OMM models through Date milliseconds.
        // Supply UTC here; propagateRecordAtEpoch uses this actual model epoch
        // while retaining epochUs for the precise comparison instant.
        const omm = recordToOmm(record);
        omm.EPOCH = record.t.toISOString();
        record._satrec = window.satellite.json2satrec(omm);
      }
      return record._satrec;
    } catch (error) {
      record._satrecError = error && error.message ? error.message : String(error);
      return null;
    }
  }

  function propagateRecordAtEpoch(record, targetUs) {
    if (!Number.isSafeInteger(targetUs)) return null;
    const satrec = satrecForRecord(record);
    if (!satrec || !window.satellite || typeof window.satellite.sgp4 !== 'function') return null;
    const modelEpochUs = record.line1 && record.line2 ? recordEpochUs(record) : record.t.getTime() * 1000;
    const elapsedUs = targetUs - modelEpochUs;
    if (!Number.isSafeInteger(elapsedUs)) return null;
    return window.satellite.sgp4(satrec, elapsedUs / 60000000);
  }

  function computeSgp4Residual(before, after) {
    if (!hasSgp4Support()) return null;
    try {
      const targetUs = recordEpochUs(after);
      const reference = propagateRecordAtEpoch(before, targetUs);
      const observation = propagateRecordAtEpoch(after, targetUs);
      if (!reference || !observation || !reference.position || !reference.velocity || !observation.position || !observation.velocity) return null;

      const radialUnit = vectorUnit(reference.position);
      const crossUnit = vectorUnit(vectorCross(reference.position, reference.velocity));
      if (!radialUnit || !crossUnit) return null;
      const alongUnit = vectorUnit(vectorCross(crossUnit, radialUnit));
      if (!alongUnit) return null;

      const positionDifference = vectorSubtract(observation.position, reference.position);
      const velocityDifference = vectorSubtract(observation.velocity, reference.velocity);
      return {
        radialKm: vectorDot(positionDifference, radialUnit),
        alongKm: vectorDot(positionDifference, alongUnit),
        crossKm: vectorDot(positionDifference, crossUnit),
        positionKm: vectorNorm(positionDifference),
        velocityMps: vectorNorm(velocityDifference) * 1000
      };
    } catch (error) {
      return null;
    }
  }

  function featureFloor(feature, profileName, options, medianGap) {
    const profile = PROFILE_LIBRARY[profileName];
    let floor = profile.floors[feature] || 1e-9;
    if (feature === 'aRate') {
      floor = Math.max(floor, options.minAbsDeltaA / Math.max(medianGap, 0.25) * 0.02);
    }
    return floor;
  }

  function groupFlagsIntoEvents(flags, records, medianGap, profileName) {
    if (!flags.length) return [];
    const profile = PROFILE_LIBRARY[profileName];
    const maximumSeparationDays = Math.max(1, medianGap * profile.eventGapFactor);
    const chronological = flags.slice().sort((first, second) => first.idx - second.idx);
    const groups = [];

    chronological.forEach(flag => {
      const current = groups[groups.length - 1];
      if (!current) {
        groups.push([flag]);
        return;
      }
      const previous = current[current.length - 1];
      const separation = (flag.t - previous.t) / DAY_MS;
      if (flag.idx - previous.idx <= 2 && separation <= maximumSeparationDays) current.push(flag);
      else groups.push([flag]);
    });

    return groups.map((group, index) => {
      const strongest = group.reduce((best, flag) => flag.severityScore > best.severityScore ? flag : best, group[0]);
      const beforeIndex = Math.max(0, group[0].idx - 1);
      const afterIndex = group[group.length - 1].idx;
      const netDeltaA = records[afterIndex].a - records[beforeIndex].a;
      const featureSet = new Set();
      group.forEach(flag => flag.breachedFeatures.forEach(feature => featureSet.add(feature)));
      return {
        id: 'EVT-' + String(index + 1).padStart(3, '0'),
        start: group[0].t,
        end: group[group.length - 1].t,
        contextBeforeIndex: beforeIndex,
        contextAfterIndex: afterIndex,
        pointCount: group.length,
        strongest,
        score: strongest.severityScore,
        tier: classifySeverity(strongest.severityScore),
        netDeltaA,
        direction: netDeltaA > 0.001 ? 'Orbit raise' : netDeltaA < -0.001 ? 'Orbit lower' : 'Primarily plane or fit change',
        features: Array.from(featureSet),
        flags: group
      };
    });
  }

  function canonicalRecord(record) {
    return {
      epochUs: recordEpochUs(record),
      satId: /^\d+$/.test(record.satId) ? String(Number(record.satId)) : record.satId,
      meanMotion: record.meanMotion,
      eccentricity: record.elements.ecc,
      inclination: record.elements.incDeg,
      raan: record.elements.raanDeg,
      argumentOfPerigee: record.elements.argPerDeg,
      meanAnomaly: record.elements.meanAnomDeg,
      bstar: record.bstar || 0,
      meanMotionDot: record.meanMotionDot || 0,
      meanMotionDdot: record.meanMotionDdot || 0,
      ephemerisType: record.ephemerisType || 0,
      propagation: record.line1 && record.line2
        ? { kind: 'tle', line1: record.line1, line2: record.line2 }
        : { kind: 'omm-date-ms', modelEpochUs: record.t.getTime() * 1000 }
    };
  }

  function makeRunId(records, options, profileName, detectorModeUsed) {
    const canonical = {
      identityVersion: RUN_IDENTITY_VERSION,
      method: METHOD_VERSION,
      workbench: WORKBENCH_VERSION,
      propagation: {
        contract: PROPAGATION_CONTRACT,
        satelliteJsVersion: SATELLITE_JS_VERSION,
        available: hasSgp4Support()
      },
      records: records.map(canonicalRecord),
      settings: {
        window: options.requestedWindow,
        alpha: options.alpha,
        minAbsDeltaA: options.minAbsDeltaA,
        maximumStaleDays: options.maximumStaleDays,
        maximumGapFactor: options.maximumGapFactor,
        requestedProfile: options.orbitProfile,
        requestedMode: options.detectorMode,
        profileName,
        detectorModeUsed
      }
    };
    return 'smd-v' + RUN_IDENTITY_VERSION + '-' + fnv1a64(stableStringify(canonical));
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

  function analysisError(parsed, kind, message, qualityItems) {
    return {
      error: true,
      errorKind: kind,
      parsed,
      inputFormat: parsed.format || 'unknown',
      n: parsed.records ? parsed.records.length : 0,
      rejectedCount: parsed.rejectedCount || 0,
      message,
      qualityItems: qualityItems || []
    };
  }

  function analyzeRaw(raw, sourceLabel, overrideOptions) {
    const options = getAnalysisOptions(overrideOptions);
    const parsed = parseInput(raw);

    if (parsed.fatalMessage) {
      return analysisError(parsed, 'invalid-input', parsed.fatalMessage, [
        { kind: 'err', label: 'Input parsing', value: 'failed' }
      ]);
    }

    if (!parsed.records.length) {
      return analysisError(parsed, 'missing-records', 'No valid TLE pairs or OMM JSON records were found. Check the input format and validation details.', [
        { kind: 'err', label: 'Valid snapshots', value: '0' },
        { kind: parsed.rejectedCount ? 'err' : 'neutral', label: 'Rejected records or pairs', value: String(parsed.rejectedCount || 0) }
      ]);
    }

    const hardQualityErrors = [];
    const qualityWarnings = [];

    if (parsed.rejectedCount > 0) {
      const sampleReason = parsed.rejectionReasons[0] ? ': ' + parsed.rejectionReasons[0] : '';
      qualityWarnings.push(parsed.rejectedCount + ' malformed record(s) or pair(s) rejected' + sampleReason);
    }

    const records = parsed.records.slice().sort(compareRecordEpochs);
    const satelliteIds = new Set(records.map(record => record.satId).filter(Boolean));
    const objectNames = new Set(records.map(record => record.name).filter(Boolean));
    if (satelliteIds.size > 1) hardQualityErrors.push('multiple catalog identifiers detected');

    const revisionResolution = resolveCatalogueRevisions(records);
    const uniqueRecords = revisionResolution.records;
    const exactDuplicateCount = revisionResolution.exactDuplicateCount;
    const conflictingDuplicateCount = revisionResolution.conflictingDuplicateCount;
    const unresolvedNearSimultaneousCount = revisionResolution.unresolvedNearSimultaneousCount;
    const supersededRecords = revisionResolution.supersededRecords;

    if (exactDuplicateCount > 0) qualityWarnings.push(exactDuplicateCount + ' exact duplicate epoch(s) removed');
    if (supersededRecords.length > 0) qualityWarnings.push(supersededRecords.length + ' near-simultaneous catalogue revision(s) resolved deterministically');
    if (conflictingDuplicateCount > 0) hardQualityErrors.push(conflictingDuplicateCount + ' conflicting duplicate epoch(s) detected without sufficient supersession metadata');
    if (unresolvedNearSimultaneousCount > 0) hardQualityErrors.push(unresolvedNearSimultaneousCount + ' near-simultaneous catalogue solution(s) could not be resolved safely');

    const n = uniqueRecords.length;
    if (n < 3) {
      return analysisError(parsed, 'too-few', 'At least three unique valid snapshots are required to calculate epoch-to-epoch changes.', [
        { kind: 'err', label: 'Unique valid snapshots', value: String(n) },
        { kind: satelliteIds.size <= 1 ? 'ok' : 'err', label: 'Catalog ID consistency', value: satelliteIds.size <= 1 ? 'passed' : Array.from(satelliteIds).join(', ') }
      ]);
    }

    const profileName = options.orbitProfile === 'auto' ? inferOrbitProfile(uniqueRecords) : options.orbitProfile;
    const profile = PROFILE_LIBRARY[profileName] || PROFILE_LIBRARY.LEO;
    const requestedMultivariate = options.detectorMode === 'multivariate';
    const sgp4Available = hasSgp4Support();
    let detectorModeUsed = requestedMultivariate && sgp4Available ? 'SGP4 multivariate' : 'Elements only';
    if (requestedMultivariate && !sgp4Available) qualityWarnings.push('satellite.js did not load; elements-only fallback used');

    const times = uniqueRecords.map(record => record.t);
    const semiMajorAxes = uniqueRecords.map(record => record.a);
    const spanDays = (recordEpochUs(uniqueRecords[n - 1]) - recordEpochUs(uniqueRecords[0])) / (DAY_MS * 1000);
    const deltaA = new Array(n).fill(NaN);
    const gaps = new Array(n).fill(NaN);
    const deltaARate = new Array(n).fill(NaN);

    for (let index = 1; index < n; index++) {
      const gap = (recordEpochUs(uniqueRecords[index]) - recordEpochUs(uniqueRecords[index - 1])) / (DAY_MS * 1000);
      const change = semiMajorAxes[index] - semiMajorAxes[index - 1];
      gaps[index] = gap > 0 ? gap : NaN;
      deltaA[index] = Number.isFinite(change) ? change : NaN;
      deltaARate[index] = Number.isFinite(change) && Number.isFinite(gaps[index]) ? change / gaps[index] : NaN;
    }

    const validGaps = gaps.filter(Number.isFinite);
    const medianDt = validGaps.length ? median(validGaps) : NaN;
    const maximumDt = validGaps.length ? Math.max(...validGaps) : NaN;
    const maximumUsableGap = Number.isFinite(medianDt) ? medianDt * options.maximumGapFactor : NaN;
    const pairEligible = gaps.map((gap, index) => index > 0 && Number.isFinite(gap) && Number.isFinite(maximumUsableGap) && gap <= maximumUsableGap);
    const excludedGapCount = pairEligible.reduce((count, eligible, index) => count + (index > 0 && !eligible && Number.isFinite(gaps[index]) ? 1 : 0), 0);
    if (excludedGapCount > 0) qualityWarnings.push(excludedGapCount + ' oversized epoch gap(s) excluded from calibration and screening');

    const now = new Date();
    const latestEpoch = times[n - 1];
    const ageDays = (now - latestEpoch) / DAY_MS;
    if (ageDays > options.maximumStaleDays) qualityWarnings.push('latest element set is older than the selected stale-age limit');
    if (ageDays < -7) hardQualityErrors.push('latest epoch is more than seven days in the future');
    else if (ageDays < 0) qualityWarnings.push('latest epoch is in the future; some valid GP element sets use future epochs');

    const featureValues = {};
    Object.keys(FEATURE_LABELS).forEach(key => { featureValues[key] = new Array(n).fill(NaN); });
    const sgp4Residuals = new Array(n).fill(null);
    let sgp4PairCount = 0;
    let sgp4FailureCount = 0;

    for (let index = 1; index < n; index++) {
      if (!Number.isFinite(gaps[index])) continue;
      const before = uniqueRecords[index - 1];
      const after = uniqueRecords[index];
      const gap = gaps[index];
      featureValues.aRate[index] = deltaARate[index];
      featureValues.meanMotionRate[index] = (after.meanMotion - before.meanMotion) / gap;
      featureValues.eccentricityVectorRate[index] = planarDistance(eccentricityVector(after.elements), eccentricityVector(before.elements)) / gap;
      featureValues.inclinationVectorRate[index] = planarDistance(inclinationVector(after.elements), inclinationVector(before.elements)) / gap;
      featureValues.bstarRate[index] = (Number(after.bstar || 0) - Number(before.bstar || 0)) / gap;

      if (requestedMultivariate && sgp4Available) {
        const residual = computeSgp4Residual(before, after);
        if (residual) {
          sgp4Residuals[index] = residual;
          sgp4PairCount++;
          featureValues.radialRate[index] = residual.radialKm / gap;
          featureValues.alongRate[index] = residual.alongKm / gap;
          featureValues.crossRate[index] = residual.crossKm / gap;
        } else {
          sgp4FailureCount++;
        }
      }
    }

    if (requestedMultivariate && sgp4Available && sgp4PairCount === 0) {
      detectorModeUsed = 'Elements only';
      qualityWarnings.push('SGP4 comparison failed for all pairs; elements-only fallback used');
    } else if (requestedMultivariate && sgp4Available && sgp4FailureCount > 0) {
      qualityWarnings.push(sgp4FailureCount + ' pair(s) could not be compared with SGP4');
    }

    const windowSize = options.requestedWindow;
    const histories = {};
    const baselines = {};
    const halfWidths = {};
    Object.keys(FEATURE_LABELS).forEach(key => {
      histories[key] = [];
      baselines[key] = new Array(n).fill(NaN);
      halfWidths[key] = new Array(n).fill(NaN);
    });

    const evaluated = new Array(n).fill(false);
    const multivariateScore = new Array(n).fill(NaN);
    const breachedFeaturesByIndex = new Array(n).fill(null).map(() => []);
    const diagnosticFlags = [];
    let covered = 0;
    let totalEvaluated = 0;

    for (let index = 1; index < n; index++) {
      if (!pairEligible[index] || !Number.isFinite(featureValues.aRate[index])) continue;

      const ratios = {};
      const availableForEvaluation = [];
      Object.keys(FEATURE_LABELS).forEach(feature => {
        const value = featureValues[feature][index];
        const history = histories[feature];
        if (!Number.isFinite(value) || history.length < windowSize) return;
        const calibration = history.slice(-windowSize);
        const centre = median(calibration);
        const residuals = calibration.map(item => Math.abs(item - centre));
        const rawHalfWidth = empiricalQuantile(residuals, 1 - options.alpha);
        const bandHalfWidth = Math.max(rawHalfWidth, featureFloor(feature, profileName, options, medianDt));
        baselines[feature][index] = centre;
        halfWidths[feature][index] = bandHalfWidth;
        ratios[feature] = Math.abs(value - centre) / bandHalfWidth;
        availableForEvaluation.push(feature);
      });

      if (Number.isFinite(ratios.aRate)) {
        evaluated[index] = true;
        totalEvaluated++;
        if (ratios.aRate <= 1) covered++;
        const ratiosArray = Object.values(ratios).filter(Number.isFinite);
        const score = ratiosArray.length ? Math.max(...ratiosArray) : NaN;
        multivariateScore[index] = score;
        const breached = Object.keys(ratios).filter(feature => ratios[feature] > 1);
        breachedFeaturesByIndex[index] = breached;
        const supportCount = breached.length;
        const primaryBreach = ratios.aRate > 1;
        const stateResidualKm = sgp4Residuals[index] ? sgp4Residuals[index].positionKm : NaN;
        const deltaAGate = Math.abs(deltaA[index]) >= options.minAbsDeltaA;
        const stateGate = Number.isFinite(stateResidualKm) && stateResidualKm >= profile.stateGateKm;
        const spatialFeatures = ['radialRate', 'alongRate', 'crossRate'];
        const spatialSupportCount = breached.filter(feature => spatialFeatures.includes(feature)).length;
        const vectorSupport = breached.includes('eccentricityVectorRate') || breached.includes('inclinationVectorRate');
        const smallElementGate = Math.abs(deltaA[index]) >= options.minAbsDeltaA * 0.10;
        const corroboratedStateBreach = detectorModeUsed === 'SGP4 multivariate' &&
          stateGate &&
          supportCount >= profile.supportRequired &&
          (smallElementGate || spatialSupportCount >= 2 || vectorSupport);
        const candidate = Number.isFinite(score) &&
          score >= profile.scoreThreshold &&
          ((primaryBreach && deltaAGate) || corroboratedStateBreach);

        if (candidate) {
          diagnosticFlags.push({
            idx: index,
            t: times[index],
            dA: deltaA[index],
            dARate: deltaARate[index],
            dt: gaps[index],
            baseline: baselines.aRate[index],
            halfWidth: halfWidths.aRate[index],
            severityScore: score,
            severityLabel: classifySeverity(score),
            breachedFeatures: breached,
            featureScores: ratios,
            sgp4Residual: sgp4Residuals[index]
          });
        }
      }

      Object.keys(FEATURE_LABELS).forEach(feature => {
        const value = featureValues[feature][index];
        if (Number.isFinite(value)) histories[feature].push(value);
      });
    }

    const observedCoverage = totalEvaluated > 0 ? covered / totalEvaluated : NaN;
    const interpretable = hardQualityErrors.length === 0 && totalEvaluated >= MIN_EVALUATED_POINTS;
    const flags = interpretable ? diagnosticFlags.slice().sort((first, second) => first.idx - second.idx) : [];
    const events = interpretable ? groupFlagsIntoEvents(flags, uniqueRecords, medianDt, profileName) : [];
    const strongestEvent = events.length ? events.reduce((best, event) => event.score > best.score ? event : best, events[0]) : null;
    const strongestFlag = strongestEvent ? strongestEvent.strongest : null;

    const bandLower = featureValues.aRate.map((value, index) => Number.isFinite(baselines.aRate[index]) && Number.isFinite(halfWidths.aRate[index]) ? baselines.aRate[index] - halfWidths.aRate[index] : null);
    const bandUpper = featureValues.aRate.map((value, index) => Number.isFinite(baselines.aRate[index]) && Number.isFinite(halfWidths.aRate[index]) ? baselines.aRate[index] + halfWidths.aRate[index] : null);

    let classification = 'No clear candidate event';
    let resultKind = 'ok';
    let resultTitle = 'No clear candidate event';
    let resultBody = 'No eligible observation produced a corroborated multivariate breach under the current settings.';

    if (hardQualityErrors.length) {
      classification = 'Abstain due to poor data quality';
      resultKind = 'err';
      resultTitle = 'Abstain due to poor data quality';
      resultBody = 'The input failed one or more hard quality checks. Candidate events and ranking scores are suppressed for this run.';
    } else if (totalEvaluated < MIN_EVALUATED_POINTS) {
      classification = 'Abstain due to insufficient evaluated history';
      resultKind = 'err';
      resultTitle = 'Abstain due to insufficient evaluated history';
      resultBody = `Only ${totalEvaluated} sequential point(s) could be evaluated. At least ${MIN_EVALUATED_POINTS} are required before candidate events are reported.`;
    } else if (events.length > 0) {
      classification = strongestEvent.tier + ' candidate event';
      resultKind = 'warn';
      resultTitle = strongestEvent.tier + ' candidate maneuver event';
      resultBody = 'One or more adjacent anomalous observations were grouped into candidate events. Review the supporting signals and data quality before follow-up.';
    } else if (qualityWarnings.length) {
      classification = 'No clear candidate event, with data warnings';
      resultKind = 'warn';
      resultTitle = 'No clear candidate event, with data warnings';
      resultBody = 'No event passed the current criteria, but the listed data-quality warnings affect interpretation.';
    }

    const qualityMessages = hardQualityErrors.concat(qualityWarnings);
    const qualityStatus = hardQualityErrors.length ? 'poor data quality' : qualityWarnings.length ? 'usable with warnings' : 'usable';

    const rows = uniqueRecords.map((record, index) => {
      const flag = flags.find(candidate => candidate.idx === index);
      const residual = sgp4Residuals[index];
      return {
        index,
        t: record.t,
        a: record.a,
        dA: deltaA[index],
        dt: gaps[index],
        dARate: deltaARate[index],
        radialKm: residual ? residual.radialKm : NaN,
        alongKm: residual ? residual.alongKm : NaN,
        crossKm: residual ? residual.crossKm : NaN,
        stateResidualKm: residual ? residual.positionKm : NaN,
        pairEligible: pairEligible[index],
        evaluated: evaluated[index],
        bandLower: bandLower[index],
        bandUpper: bandUpper[index],
        multivariateScore: multivariateScore[index],
        breachedFeatures: breachedFeaturesByIndex[index],
        flagged: Boolean(flag),
        severityScore: flag ? flag.severityScore : NaN,
        featureValues: Object.fromEntries(Object.keys(FEATURE_LABELS).map(feature => [feature, featureValues[feature][index]])),
        record
      };
    });

    const qualityItems = [
      { kind: n >= windowSize + MIN_EVALUATED_POINTS + 1 ? 'ok' : totalEvaluated >= MIN_EVALUATED_POINTS ? 'warn' : 'err', label: 'Unique valid snapshots', value: String(n) },
      { kind: satelliteIds.size <= 1 ? 'ok' : 'err', label: 'Catalog ID consistency', value: satelliteIds.size <= 1 ? 'passed' : Array.from(satelliteIds).join(', ') },
      { kind: parsed.rejectedCount === 0 ? 'ok' : 'warn', label: 'Rejected records or pairs', value: String(parsed.rejectedCount || 0) },
      { kind: conflictingDuplicateCount === 0 ? exactDuplicateCount === 0 ? 'ok' : 'warn' : 'err', label: 'Duplicate epochs', value: conflictingDuplicateCount ? conflictingDuplicateCount + ' unresolved' : exactDuplicateCount ? exactDuplicateCount + ' removed' : 'none' },
      { kind: unresolvedNearSimultaneousCount > 0 ? 'err' : supersededRecords.length > 0 ? 'warn' : 'ok', label: 'Catalogue revisions', value: unresolvedNearSimultaneousCount ? unresolvedNearSimultaneousCount + ' unresolved' : supersededRecords.length ? supersededRecords.length + ' superseded' : 'none' },
      { kind: excludedGapCount === 0 ? 'ok' : 'warn', label: 'Oversized pair gaps', value: excludedGapCount === 0 ? 'none' : excludedGapCount + ' excluded' },
      { kind: Number.isFinite(ageDays) && ageDays >= -7 && ageDays <= options.maximumStaleDays ? 'ok' : ageDays < -7 ? 'err' : 'warn', label: 'Latest element age', value: Number.isFinite(ageDays) ? fmtNum(ageDays, 2) + ' days' : 'n/a' },
      { kind: detectorModeUsed === 'SGP4 multivariate' ? 'ok' : requestedMultivariate ? 'warn' : 'neutral', label: 'Detector mode used', value: detectorModeUsed },
      { kind: !requestedMultivariate || sgp4PairCount > 0 ? 'ok' : 'warn', label: 'SGP4 pair comparisons', value: String(sgp4PairCount) },
      { kind: totalEvaluated >= MIN_EVALUATED_POINTS ? 'ok' : 'err', label: 'Sequential evaluation points', value: totalEvaluated + ' of ' + MIN_EVALUATED_POINTS + ' required' }
    ];

    const generatedAt = new Date().toISOString();
    const runId = makeRunId(uniqueRecords, options, profileName, detectorModeUsed);
    const analysis = {
      error: false,
      sourceLabel,
      inputFormat: parsed.format,
      parsed,
      rejectedCount: parsed.rejectedCount || 0,
      objectId: satelliteIds.size === 1 ? Array.from(satelliteIds)[0] : '',
      objectName: objectNames.size === 1 ? Array.from(objectNames)[0] : '',
      records: uniqueRecords,
      n,
      spanDays,
      medianDt,
      maximumDt,
      maximumUsableGap,
      ageDays,
      window: windowSize,
      alpha: options.alpha,
      minAbsDeltaA: options.minAbsDeltaA,
      maximumGapFactor: options.maximumGapFactor,
      profileName,
      detectorModeRequested: options.detectorMode,
      detectorModeUsed,
      sgp4Available,
      sgp4PairCount,
      sgp4FailureCount,
      excludedGapCount,
      totalEvaluated,
      observedCoverage,
      interpretable,
      qualityStatus,
      qualityWarnings,
      hardQualityErrors,
      qualityMessages,
      exactDuplicateCount,
      conflictingDuplicateCount,
      unresolvedNearSimultaneousCount,
      supersededRecords,
      classification,
      resultKind,
      resultTitle,
      resultBody,
      diagnosticFlagCount: diagnosticFlags.length,
      flags,
      events,
      strongestFlag,
      strongestEvent,
      rows,
      qualityItems,
      bandLower,
      bandUpper,
      deltaA,
      deltaARate,
      multivariateScore,
      featureValues,
      baselines,
      halfWidths,
      pairEligible,
      evaluated,
      times,
      semiMajorAxes,
      generatedAt,
      runId
    };

    analysis.evidenceText = buildEvidenceNote(analysis);
    analysis.csv = buildCsv(analysis);
    return analysis;
  }

  function describeParse(parsed) {
    if (parsed.format === 'TLE') {
      return `Read ${parsed.totalLines} non-empty lines, found ${parsed.line1Candidates} line-1 and ${parsed.line2Candidates} line-2 candidates, and accepted ${parsed.records.length} validated TLE pairs.`;
    }

    if (parsed.format === 'OMM JSON') {
      return `Read ${parsed.totalRecords || 0} OMM JSON record(s) and accepted ${parsed.records.length}.`;
    }

    return 'Input format could not be determined.';
  }


  function formatDateOnly(date) {
    return date instanceof Date && Number.isFinite(date.getTime()) ? date.toISOString().slice(0, 10) : 'n/a';
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
      window.Plotly.relayout(target, command).finally(() => { syncingCharts = false; });
    }

    orbit.on('plotly_relayout', update => relayRange(rate, update));
    rate.on('plotly_relayout', update => relayRange(orbit, update));

    function relayHover(source, target, event) {
      if (!event || !event.points || !event.points.length || !target.data || !target.data.length) return;
      const point = event.points[0];
      const sourceEpoch = source.data?.[point.curveNumber]?.x?.[point.pointNumber] ?? point.x;
      const pointIndex = nearestTimeIndex(target.data[0].x || [], sourceEpoch);
      window.Plotly.Fx.hover(target, [{ curveNumber: 0, pointNumber: pointIndex }], ['xy']);
    }

    orbit.on('plotly_hover', event => relayHover(orbit, rate, event));
    rate.on('plotly_hover', event => relayHover(rate, orbit, event));
    orbit.on('plotly_unhover', () => window.Plotly.Fx.unhover(rate));
    rate.on('plotly_unhover', () => window.Plotly.Fx.unhover(orbit));
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

    const candidateShapes = analysis.events.map(event => ({
      type: 'line',
      x0: fmtTime(event.strongest.t),
      x1: fmtTime(event.strongest.t),
      y0: 0,
      y1: 1,
      yref: 'paper',
      line: { color: '#dc2626', width: 1, dash: 'dot' }
    }));

    const orbitData = [{
      x: analysis.times.map(fmtTime),
      y: analysis.semiMajorAxes,
      mode: 'lines+markers',
      name: 'Semi-major axis',
      line: { width: 1.8 },
      marker: { size: 5 },
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
      line: { width: 1.4 },
      marker: { size: 5 },
      customdata: analysis.deltaA,
      hovertemplate: '%{x} UTC<br>Δa/Δt = %{y:.4f} km/day<br>Δa = %{customdata:.4f} km<extra></extra>'
    }];

    if (analysis.bandLower.some(value => value !== null)) {
      rateData.push({
        x: analysis.times.map(fmtTime),
        y: analysis.bandLower,
        mode: 'lines',
        name: 'Band lower',
        line: { width: 0.5 },
        hoverinfo: 'skip',
        showlegend: false
      });
      rateData.push({
        x: analysis.times.map(fmtTime),
        y: analysis.bandUpper,
        mode: 'lines',
        name: 'Rolling empirical band',
        line: { width: 0.5 },
        fill: 'tonexty',
        fillcolor: 'rgba(99, 102, 241, 0.15)',
        hoverinfo: 'skip'
      });
    }

    if (excludedRate.some(Number.isFinite)) {
      rateData.push({
        x: analysis.times.map(fmtTime),
        y: excludedRate,
        mode: 'markers',
        name: 'Excluded gap',
        marker: { size: 8, symbol: 'circle-open' },
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
        marker: { size: 11, symbol: 'x', color: '#dc2626' },
        hovertemplate: '%{x} UTC<br>Δa/Δt = %{y:.4f} km/day<extra>Candidate</extra>'
      });
    }

    const common = {
      xaxis: { title: { text: 'Epoch UTC' }, type: 'date', automargin: true },
      hovermode: 'x unified',
      shapes: candidateShapes
    };

    const orbitPromise = safePlot('orbitChart', orbitData, {
      ...common,
      margin: { l: 72, r: 28, t: 58, b: 48 },
      title: { text: 'Semi-major axis over time', x: 0.02, xanchor: 'left', font: { size: 15 } },
      showlegend: false,
      yaxis: { title: { text: 'Semi-major axis [km]' }, zeroline: false, automargin: true }
    });

    const ratePromise = safePlot('rateChart', rateData, {
      ...common,
      margin: { l: 72, r: 28, t: 86, b: 48 },
      title: { text: 'Sampling-normalised change and empirical band', x: 0.02, xanchor: 'left', y: 0.98, font: { size: 15 } },
      legend: { orientation: 'h', x: 0, y: 1.20, xanchor: 'left', yanchor: 'top' },
      yaxis: { title: { text: 'Δa/Δt [km/day]' }, zeroline: true, automargin: true }
    });

    if (orbitPromise && ratePromise) {
      await Promise.all([orbitPromise, ratePromise]);
      if (lastAnalysis !== analysis) return;
      bindChartSynchronization();
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
          <td><button class="table-action" type="button" data-event-index="${index}">${escapeHtml(event.id)}</button></td>
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
        if (event) {
          byId('orbitDetails').open = true;
          queueOrbitComparisonForEvent(event);
        }
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
    if (analysis.strongestEvent) queueOrbitComparisonForEvent(analysis.strongestEvent);
    else queueSingleOrbit(
      analysis.records[Math.floor(analysis.records.length / 2)],
      analysis.interpretable
        ? 'No candidate event selected. Showing one mid-series element set for visual context.'
        : 'This run abstained. Showing one mid-series element set for visual context only.'
    );
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

  function radians(degrees) {
    return degrees * Math.PI / 180;
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
    return {
      title: { text: title, x: 0.02, xanchor: 'left', font: { size: 15 } },
      margin: { l: 0, r: 0, t: 52, b: 0 },
      paper_bgcolor: '#020617',
      plot_bgcolor: '#020617',
      font: { color: '#e2e8f0' },
      legend: { orientation: 'h', x: 0, y: 1.03 },
      scene: {
        aspectmode: 'data',
        bgcolor: '#020617',
        xaxis: { title: { text: 'ECI x [km]' }, gridcolor: '#334155', zerolinecolor: '#475569' },
        yaxis: { title: { text: 'ECI y [km]' }, gridcolor: '#334155', zerolinecolor: '#475569' },
        zaxis: { title: { text: 'ECI z [km]' }, gridcolor: '#334155', zerolinecolor: '#475569' },
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
        line: { width: 5, color: '#22d3ee' }, hovertemplate: 'Pre-event orbit<extra></extra>'
      },
      {
        type: 'scatter3d', mode: 'lines', name: 'Final event record',
        x: afterOrbit.x, y: afterOrbit.y, z: afterOrbit.z,
        line: { width: 5, color: '#fb923c' }, hovertemplate: 'Final event orbit<extra></extra>'
      },
      {
        type: 'scatter3d', mode: 'markers+text', name: 'Element epochs',
        x: [beforeOrbit.point.x, afterOrbit.point.x],
        y: [beforeOrbit.point.y, afterOrbit.point.y],
        z: [beforeOrbit.point.z, afterOrbit.point.z],
        text: ['Pre-event', 'Final event'], textposition: 'top center',
        marker: { size: 5, color: ['#22d3ee', '#fb923c'], line: { color: '#ffffff', width: 1 } },
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
        line: { width: 5, color: '#22d3ee' }, hovertemplate: 'Approximate orbit<extra></extra>'
      },
      {
        type: 'scatter3d', mode: 'markers+text', name: 'Selected epoch',
        x: [orbit.point.x], y: [orbit.point.y], z: [orbit.point.z],
        text: [record.name || record.satId || 'Selected epoch'], textposition: 'top center',
        marker: { size: 6, color: '#ef4444', line: { color: '#ffffff', width: 1 } },
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
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
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


  function benchmarkTemplateDefinition() {
    return {
      schema: 'smd-event-benchmark-v1',
      name: 'Replace with the benchmark name',
      matching_tolerance_hours: 24,
      notes: 'Each case must declare label_status. Truth timestamps require a complete ISO date and time with Z or a numeric offset and at most six fractional digits. Unknown periods are never treated as quiet negatives.',
      cases: [
        {
          case_id: 'replace-with-unique-case-id',
          object_id: '25544',
          description: 'Replace with the object and observation-window description.',
          orbit_profile: 'LEO',
          label_status: 'event-evidence',
          label_confidence: 'high',
          source: 'Public URL, DOI, mission report, operator notice, or other ground-truth citation.',
          records: [],
          truth_events: [
            {
              start: '2026-01-01T00:00:00Z',
              end: '2026-01-01T23:59:59Z',
              label: 'Documented maneuver',
              source: 'Specific source for this event, or omit to use the case source.'
            }
          ]
        }
      ]
    };
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

  function normaliseBenchmarkLabelStatus(value, truthEventCount) {
    const raw = String(value || '').trim().toLowerCase();
    const status = raw === 'verified-quiet'
      ? 'confirmed-quiet'
      : (raw || (truthEventCount > 0 ? 'event-evidence' : 'unknown'));
    if (!['event-evidence', 'confirmed-quiet', 'fully-labelled', 'unknown'].includes(status)) {
      throw new Error('label_status must be event-evidence, verified-quiet/confirmed-quiet, fully-labelled or unknown.');
    }
    if (status === 'event-evidence' && truthEventCount < 1) {
      throw new Error('event-evidence cases require at least one documented truth event.');
    }
    if (status === 'confirmed-quiet' && truthEventCount > 0) {
      throw new Error('confirmed-quiet cases must not contain truth events.');
    }
    return status;
  }

  function normaliseBenchmarkDefinition(decoded) {
    if (!decoded || typeof decoded !== 'object' || Array.isArray(decoded)) {
      throw new Error('The benchmark file must contain one JSON object.');
    }
    if (decoded.schema !== 'smd-event-benchmark-v1') {
      throw new Error('The benchmark schema must be smd-event-benchmark-v1.');
    }
    if (!Array.isArray(decoded.cases) || !decoded.cases.length) {
      throw new Error('The benchmark must contain at least one case.');
    }
    if (decoded.cases.length > 200) {
      throw new Error('The benchmark is limited to 200 cases per browser run.');
    }

    let toleranceHours = Number(decoded.matching_tolerance_hours);
    if (!Number.isFinite(toleranceHours)) toleranceHours = 24;
    if (toleranceHours < 0 || toleranceHours > 168) {
      throw new Error('matching_tolerance_hours must be between 0 and 168.');
    }

    const seenIds = new Set();
    const cases = decoded.cases.map((item, index) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) {
        throw new Error('Benchmark case ' + (index + 1) + ' is not an object.');
      }
      const caseId = String(item.case_id || '').trim();
      if (!caseId) throw new Error('Benchmark case ' + (index + 1) + ' is missing case_id.');
      if (seenIds.has(caseId)) throw new Error('Duplicate benchmark case_id: ' + caseId + '.');
      seenIds.add(caseId);

      const source = String(item.source || '').trim();
      if (!source) throw new Error('Benchmark case ' + caseId + ' requires a public source citation.');

      let raw;
      if (Array.isArray(item.records)) raw = JSON.stringify(item.records);
      else if (typeof item.input_text === 'string') raw = item.input_text;
      else throw new Error('Benchmark case ' + caseId + ' must contain records or input_text.');

      const parsed = parseInput(raw);
      if (parsed.fatalMessage || !parsed.records.length) {
        throw new Error('Benchmark case ' + caseId + ' has no valid orbital records.');
      }

      const truthItems = Object.prototype.hasOwnProperty.call(item, 'truth_events') ? item.truth_events : [];
      if (!Array.isArray(truthItems)) {
        throw new Error('Benchmark case ' + caseId + ' truth_events must be an array.');
      }
      const truthEvents = truthItems.map((truth, truthIndex) => {
        const context = 'Truth event ' + (truthIndex + 1) + ' in ' + caseId;
        const interval = benchmarkTruthInterval(truth, context);
        const eventSource = String(truth.source || source).trim();
        if (!eventSource) throw new Error(context + ' requires a source citation.');
        return {
          start: interval.start.iso,
          end: interval.end.iso,
          label: String(truth.label || 'Documented event'),
          source: eventSource
        };
      });

      const orbitProfile = String(item.orbit_profile || 'AUTO').trim().toUpperCase();
      if (!['AUTO', 'LEO', 'MEO', 'GEO', 'HEO'].includes(orbitProfile)) {
        throw new Error('Benchmark case ' + caseId + ' has an unsupported orbit_profile.');
      }
      const labelConfidence = String(item.label_confidence || 'unspecified').trim().toLowerCase();
      const labelStatus = normaliseBenchmarkLabelStatus(item.label_status, truthEvents.length);

      return {
        caseId,
        objectId: String(item.object_id || '').trim(),
        description: String(item.description || caseId),
        source,
        orbitProfile,
        labelStatus,
        labelConfidence,
        raw,
        truthEvents
      };
    });

    return {
      schema: decoded.schema,
      name: String(decoded.name || 'Unnamed event benchmark'),
      notes: String(decoded.notes || ''),
      toleranceHours,
      cases,
      original: decoded
    };
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

  function benchmarkTimestamp(value) {
    const formatMessage = 'Use YYYY-MM-DDTHH:mm:ss with Z or a numeric +/-HH:mm offset and at most six fractional digits.';
    if (typeof value !== 'string') throw new Error('Timestamp must be a string. ' + formatMessage);
    const match = value.match(/^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?(Z|[+-][0-9]{2}:[0-9]{2})$/);
    // JavaScript's $ anchor may stop before a final newline; require all input.
    if (!match || match[0].length !== value.length) throw new Error(formatMessage);
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const hour = Number(match[4]);
    const minute = Number(match[5]);
    const second = Number(match[6]);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const monthLengths = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (year < 1 || month < 1 || month > 12 || day < 1 || day > monthLengths[month - 1] ||
        hour > 23 || minute > 59 || second > 59) {
      throw new Error('Timestamp has an invalid calendar date or clock time.');
    }
    const zone = match[8];
    if (zone !== 'Z' && (Number(zone.slice(1, 3)) > 23 || Number(zone.slice(4)) > 59)) {
      throw new Error('Timestamp offset must have hours 00-23 and minutes 00-59.');
    }

    // Date handles only the already validated whole second and explicit offset.
    // Fractional microseconds never pass through its millisecond representation.
    const date = new Date(value.slice(0, 19) + zone);
    if (!Number.isFinite(date.getTime()) || date.getUTCFullYear() < 1 || date.getUTCFullYear() > 9999) {
      throw new Error('Timestamp must resolve to a UTC year from 0001 through 9999.');
    }
    const fraction = (match[7] || '').padEnd(6, '0');
    return {
      epochUs: BigInt(date.getTime()) * 1000n + BigInt(fraction),
      iso: date.toISOString().replace(/\.000Z$/, '.' + fraction + 'Z')
    };
  }

  function benchmarkTruthInterval(truth, context = 'Truth event') {
    if (!truth || typeof truth !== 'object' || Array.isArray(truth)) {
      throw new Error(context + ' must be an object with a start timestamp and optional end.');
    }
    const parseBoundary = (value, field) => {
      try {
        return benchmarkTimestamp(value);
      } catch (error) {
        throw new Error(context + ' ' + field + ': ' + error.message);
      }
    };
    if (!Object.prototype.hasOwnProperty.call(truth, 'start')) throw new Error(context + ' start is required.');
    const start = parseBoundary(truth.start, 'start');
    const end = Object.prototype.hasOwnProperty.call(truth, 'end') ? parseBoundary(truth.end, 'end') : start;
    if (end.epochUs < start.epochUs) throw new Error(context + ' end precedes its start.');
    return { start, end };
  }

  function benchmarkToleranceUs(hours) {
    if (!Number.isFinite(hours) || hours < 0) {
      throw new Error('Matching tolerance must be a finite, nonnegative number of hours.');
    }
    // Floor the decimal hours exactly: rounding up could admit an extra pair.
    const [coefficient, exponentText = '0'] = String(hours).toLowerCase().split('e');
    const [whole, fraction = ''] = coefficient.split('.');
    const numerator = BigInt(whole + fraction) * 3600000000n;
    const scale = fraction.length - Number(exponentText);
    return scale >= 0 ? numerator / (10n ** BigInt(scale)) : numerator * (10n ** BigInt(-scale));
  }

  function benchmarkPredictionInterval(event, records = []) {
    const flags = event.flags || [];
    const epoch = (record, date) => record
      ? BigInt(recordEpochUs(record))
      : BigInt(date.getTime()) * 1000n;
    return [
      epoch(flags.length ? records[flags[0].idx] : null, event.start),
      epoch(flags.length ? records[flags[flags.length - 1].idx] : null, event.end),
      epoch(records[event.strongest.idx], event.strongest.t)
    ];
  }

  function matchEventIntervals(predictedIntervals, truthIntervals, toleranceUs) {
    const integer = value => {
      if (typeof value === 'bigint') return value;
      if (Number.isSafeInteger(value)) return BigInt(value);
      throw new Error('Matching timestamps and tolerance must be exact integer microseconds.');
    };
    const tolerance = integer(toleranceUs);
    if (tolerance < 0n) throw new Error('Matching tolerance must be nonnegative.');
    const canonical = (intervals, size) => intervals.map((values, index) => {
      if (!Array.isArray(values) || values.length !== size) throw new Error('Invalid matching interval.');
      const times = values.map(integer);
      if (times[0] > times[1]) throw new Error('Matching interval ends before it starts.');
      return { times, index };
    }).sort((first, second) => {
      for (let index = 0; index < size; index++) {
        if (first.times[index] < second.times[index]) return -1;
        if (first.times[index] > second.times[index]) return 1;
      }
      return first.index - second.index;
    });
    const predictions = canonical(predictedIntervals, 3);
    const truths = canonical(truthIntervals, 2);
    if (!predictions.length || !truths.length) return [];

    const source = 0;
    const truthOffset = 1 + predictions.length;
    const sink = truthOffset + truths.length;
    const graph = Array.from({ length: sink + 1 }, () => []);
    const addEdge = (from, to, cost) => {
      const forward = { to, reverse: graph[to].length, capacity: 1, cost };
      const reverse = { to: from, reverse: graph[from].length, capacity: 0, cost: -cost };
      graph[from].push(forward);
      graph[to].push(reverse);
      return forward;
    };
    predictions.forEach((_, rank) => addEdge(source, rank + 1, 0n));
    const candidates = [];
    predictions.forEach((prediction, predictionRank) => {
      const [start, end, strongest] = prediction.times;
      truths.forEach((truth, truthRank) => {
        const [truthStart, truthEnd] = truth.times;
        if (end < truthStart - tolerance || start > truthEnd + tolerance) return;
        const signedDistance = 2n * strongest - truthStart - truthEnd;
        const distance = signedDistance < 0n ? -signedDistance : signedDistance;
        const edge = addEdge(predictionRank + 1, truthOffset + truthRank, distance);
        candidates.push({ prediction, truth, distance, edge });
      });
    });
    truths.forEach((_, rank) => addEdge(truthOffset + rank, sink, 0n));

    const before = (first, second) => first[0] < second[0] ||
      (first[0] === second[0] && first[1] < second[1]);
    const push = (heap, item) => {
      heap.push(item);
      let index = heap.length - 1;
      while (index > 0) {
        const parent = Math.floor((index - 1) / 2);
        if (!before(item, heap[parent])) break;
        heap[index] = heap[parent];
        index = parent;
      }
      heap[index] = item;
    };
    const pop = heap => {
      const first = heap[0];
      const last = heap.pop();
      if (heap.length) {
        let index = 0;
        while (2 * index + 1 < heap.length) {
          let child = 2 * index + 1;
          if (child + 1 < heap.length && before(heap[child + 1], heap[child])) child++;
          if (!before(heap[child], last)) break;
          heap[index] = heap[child];
          index = child;
        }
        heap[index] = last;
      }
      return first;
    };

    // Each shortest residual path adds one pair. Exhausting paths maximises
    // cardinality; exact costs then minimise total strongest-to-midpoint distance.
    const potentials = Array(graph.length).fill(0n);
    while (true) {
      const distances = Array(graph.length).fill(null);
      const previousNode = Array(graph.length).fill(-1);
      const previousEdge = Array(graph.length).fill(-1);
      distances[source] = 0n;
      const heap = [[0n, source]];
      while (heap.length) {
        const [distance, node] = pop(heap);
        if (distance !== distances[node]) continue;
        graph[node].forEach((edge, edgeIndex) => {
          if (!edge.capacity) return;
          const next = distance + edge.cost + potentials[node] - potentials[edge.to];
          // Keep the first predecessor on a tie in canonical node/edge order.
          if (distances[edge.to] !== null && next >= distances[edge.to]) return;
          distances[edge.to] = next;
          previousNode[edge.to] = node;
          previousEdge[edge.to] = edgeIndex;
          push(heap, [next, edge.to]);
        });
      }
      if (distances[sink] === null) break;
      distances.forEach((distance, node) => {
        if (distance !== null) potentials[node] += distance;
      });
      for (let node = sink; node !== source; node = previousNode[node]) {
        const edge = graph[previousNode[node]][previousEdge[node]];
        edge.capacity = 0;
        graph[node][edge.reverse].capacity = 1;
      }
    }

    return candidates.filter(candidate => candidate.edge.capacity === 0).map(candidate => ({
      predictionIndex: candidate.prediction.index,
      truthIndex: candidate.truth.index,
      distanceTwiceUs: candidate.distance,
      delayHours: Number(candidate.prediction.times[0] - candidate.truth.times[0]) / 3600000000,
      strongestPointDelayHours: Number(candidate.prediction.times[2] - candidate.truth.times[0]) / 3600000000
    }));
  }

  function matchBenchmarkEvents(predictedEvents, truthEvents, toleranceHours, records = []) {
    const predictions = predictedEvents.map(event => benchmarkPredictionInterval(event, records));
    const truths = truthEvents.map((event, index) => {
      const interval = benchmarkTruthInterval(event, 'Truth event ' + (index + 1));
      return [interval.start.epochUs, interval.end.epochUs];
    });
    const matches = matchEventIntervals(predictions, truths, benchmarkToleranceUs(toleranceHours)).map(match => ({
      predictionIndex: match.predictionIndex,
      truthIndex: match.truthIndex,
      distanceMs: Number(match.distanceTwiceUs) / 2000,
      delayHours: match.delayHours,
      strongestPointDelayHours: match.strongestPointDelayHours
    }));
    return {
      matches,
      truePositives: matches.length,
      falsePositives: predictedEvents.length - matches.length,
      falseNegatives: truthEvents.length - matches.length
    };
  }

  function makeBenchmarkId(definition, settings) {
    return 'smb-v2-' + fnv1a64(stableStringify({
      method: METHOD_VERSION,
      scoring_version: EVENT_MATCHING_VERSION,
      definition,
      settings
    }));
  }

  function ratioOrNull(numerator, denominator) {
    return denominator > 0 ? numerator / denominator : null;
  }

  function metricText(value) {
    return Number.isFinite(value) ? value.toFixed(3) : 'n/a';
  }

  function deterministicThinBenchmarkRaw(raw) {
    const parsed = parseInput(raw);
    if (parsed.fatalMessage || parsed.records.length < 8) return null;
    const records = parsed.records
      .slice()
      .sort(compareRecordEpochs)
      .filter((record, index, all) => index === 0 || index === all.length - 1 || index % 4 !== 0);
    if (records.length < 3 || records.length === parsed.records.length) return null;
    return serialiseRecordsAsOmm(records);
  }

  function initialiseProfileAccumulator() {
    return {
      cases: 0,
      scored_cases: 0,
      abstained_cases: 0,
      true_positives: 0,
      false_positives: 0,
      false_negatives: 0,
      positive_evidence_cases: 0,
      negative_label_object_months: 0,
      detection_delays_hours: []
    };
  }

  function finaliseProfileMetrics(accumulator) {
    const precision = accumulator.negative_label_object_months > 0
      ? ratioOrNull(accumulator.true_positives, accumulator.true_positives + accumulator.false_positives)
      : null;
    const recall = ratioOrNull(accumulator.true_positives, accumulator.true_positives + accumulator.false_negatives);
    const f1 = Number.isFinite(precision) && Number.isFinite(recall) && precision + recall > 0
      ? 2 * precision * recall / (precision + recall)
      : null;
    return {
      cases: accumulator.cases,
      scored_cases: accumulator.scored_cases,
      abstained_cases: accumulator.abstained_cases,
      positive_evidence_cases: accumulator.positive_evidence_cases,
      true_positives: accumulator.true_positives,
      false_positives: accumulator.false_positives,
      false_negatives: accumulator.false_negatives,
      precision,
      recall,
      f1,
      negative_label_object_months: accumulator.negative_label_object_months,
      false_events_per_object_month: accumulator.negative_label_object_months > 0
        ? accumulator.false_positives / accumulator.negative_label_object_months
        : null,
      median_detection_delay_hours: accumulator.detection_delays_hours.length ? median(accumulator.detection_delays_hours) : null
    };
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
})();
