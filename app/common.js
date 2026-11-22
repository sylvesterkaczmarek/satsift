'use strict';

// Shared versions, numeric helpers and formatting.
globalThis.SMDModules = globalThis.SMDModules || Object.create(null);
if (Object.prototype.hasOwnProperty.call(globalThis.SMDModules, "common")) {
  throw new Error('Workbench module already registered: common');
}
globalThis.SMDModules["common"] = function createCommon() {
  const MU = 398600.4418;
  const METHOD_VERSION = 'v0.4';
  const WORKBENCH_VERSION = '3.4.9';
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

  function formatDateOnly(date) {
    return date instanceof Date && Number.isFinite(date.getTime()) ? date.toISOString().slice(0, 10) : 'n/a';
  }

  function radians(degrees) {
    return degrees * Math.PI / 180;
  }

  return Object.freeze({
    MU, METHOD_VERSION, WORKBENCH_VERSION, EVENT_MATCHING_VERSION, PACKAGE_SCHEMA_VERSION,
    TLE_SOURCE_SCHEMA_VERSION, RUN_IDENTITY_VERSION, DATA_PROVENANCE_VERSION,
    INPUT_FINGERPRINT_ALGORITHM, MAX_PROVENANCE_SOURCES, MAX_PROVENANCE_ACQUISITIONS,
    MAX_PROVENANCE_BYTES, PROPAGATION_CONTRACT, SATELLITE_JS_VERSION, HISTORY_ENDPOINT,
    PLOTLY_ASSET_URL, MAX_HISTORY_RANGE_DAYS, MIN_EVALUATED_POINTS, PUBLIC_CACHE_MS, DAY_MS,
    CATALOGUE_REVISION_TOLERANCE_US, DEMO_ANCHOR_MS, EARTH_RADIUS_KM, J2, FEATURE_LABELS,
    PROFILE_LIBRARY, byId, escapeHtml, fmtTime, fmtNum, median, empiricalQuantile, stableStringify,
    fnv1a64, vectorSubtract, vectorDot, vectorCross, vectorNorm, vectorUnit, formatDateOnly, radians
  });
};
