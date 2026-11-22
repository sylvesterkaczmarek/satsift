'use strict';

// Orbital parsing, catalogue revision selection and synthetic examples.
globalThis.SMDModules = globalThis.SMDModules || Object.create(null);
if (Object.prototype.hasOwnProperty.call(globalThis.SMDModules, "orbital-input")) {
  throw new Error('Workbench module already registered: orbital-input');
}
globalThis.SMDModules["orbital-input"] = function createOrbitalInput(common) {
  const {
    MU, TLE_SOURCE_SCHEMA_VERSION, DAY_MS, CATALOGUE_REVISION_TOLERANCE_US, DEMO_ANCHOR_MS,
    EARTH_RADIUS_KM, J2, radians
  } = common;

  function validateFetchedRecords(data, norad, label) {
    const records = Array.isArray(data) ? data : [data];
    const parsed = validatedRecordsFromRaw(JSON.stringify(records), label);
    if (parsed.rejectedCount || parsed.records.some(record => Number(record.satId) !== Number(norad))) {
      throw new Error(label + ' contains invalid records or records for a different NORAD object. Existing input was retained.');
    }
    return parsed;
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

  // Normalise a catalogue identity before comparing TLE and OMM histories.
  // TLE Alpha-5 prefixes exclude I and O; OMM always supplies decimal IDs.
  function canonicalCatalogId(value, allowAlpha5 = false) {
    if (typeof value !== 'string' && typeof value !== 'number') return null;
    const text = String(value).trim();
    if (/^[0-9]{1,9}$/.test(text)) {
      const number = Number(text);
      return Number.isSafeInteger(number) && number > 0 ? String(number) : null;
    }
    if (allowAlpha5 && /^[A-HJ-NP-Z][0-9]{4}$/.test(text)) {
      const prefix = 'ABCDEFGHJKLMNPQRSTUVWXYZ'.indexOf(text[0]) + 10;
      return String(prefix * 10000 + Number(text.slice(1)));
    }
    return null;
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

    const satId1 = line1.length >= 7 ? canonicalCatalogId(line1.slice(2, 7), true) : null;
    const satId2 = line2.length >= 7 ? canonicalCatalogId(line2.slice(2, 7), true) : null;
    if (!satId1 || !satId2 || satId1 !== satId2) {
      errors.push('catalog identifiers must be matching positive numeric or supported Alpha-5 identifiers');
    }

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
    // Read legacy TLE-derived exports that carried an Alpha-5 field as OMM
    // metadata, but keep native OMM identifiers strictly decimal.
    const retainedTle = sourceFormat === 'TLE' && Object.prototype.hasOwnProperty.call(record, 'SMD_TLE');
    const satId = canonicalCatalogId(record.NORAD_CAT_ID, retainedTle) || '';
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
    const firstNumeric = /^\d+$/.test(firstText);
    const secondNumeric = /^\d+$/.test(secondText);
    // Keep one transitive order across accepted metadata: decimal identifiers
    // outrank opaque identifiers; each class retains its existing comparison.
    if (firstNumeric !== secondNumeric) return secondNumeric ? 1 : -1;
    if (firstNumeric && secondNumeric) {
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
    // Finish exact-epoch metadata and source selection before comparing nearby
    // observations. Otherwise a later TLE duplicate can leave a false OMM
    // ambiguity behind. Equal-authority conflicts remain explicitly unresolved.
    const records = inputRecords.slice().sort((first, second) => {
      const preference = compareRecordEpochs(first, second) || catalogueMetadataPreference(first, second) ||
        Number(second.sourceFormat === 'TLE') - Number(first.sourceFormat === 'TLE') ||
        Number(Boolean(second.line1 && second.line2)) - Number(Boolean(first.line1 && first.line2));
      if (preference) return preference;
      const firstKey = JSON.stringify(recordToOmm(first));
      const secondKey = JSON.stringify(recordToOmm(second));
      return firstKey < secondKey ? -1 : firstKey > secondKey ? 1 : 0;
    });
    const supersededRecords = [];
    let exactDuplicateCount = 0;
    let conflictingDuplicateCount = 0;
    let unresolvedNearSimultaneousCount = 0;
    let replacementCount = 0;

    const resolvePass = (input, exactPass) => {
      const retained = [];
      input.forEach(record => {
        if (!retained.length) { retained.push(record); return; }
        const previous = retained[retained.length - 1];
        const deltaUs = recordEpochUs(record) - recordEpochUs(previous);
        const exactEpoch = deltaUs === 0;
        const nearOmmPair = deltaUs > 0 && deltaUs <= CATALOGUE_REVISION_TOLERANCE_US && previous.sourceFormat === 'OMM JSON' && record.sourceFormat === 'OMM JSON';
        if (exactPass ? !exactEpoch : !nearOmmPair) { retained.push(record); return; }

        const conflict = recordsConflict(previous, record);
        const preference = catalogueMetadataPreference(previous, record);
        if (!conflict && exactEpoch) {
          exactDuplicateCount++;
          // Equivalent exact copies retain the preferred source before any
          // native-OMM near-epoch rule is applied in the second pass.
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
      return retained;
    };
    const retained = resolvePass(resolvePass(records, true), false);

    return { records: retained, exactDuplicateCount, conflictingDuplicateCount, unresolvedNearSimultaneousCount, supersededRecords, replacementCount };
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

  return Object.freeze({
    validateFetchedRecords, parseTleExponentField, semiMajorAxisKm, checksumForTleCore,
    addTleChecksum, validateTleChecksum, dateToTleEpoch, putField, fixedField, eccentricityField,
    makeTleBlock, demoSecularRates, exampleDates, buildDemoStates, exampleTles, parseTleEpoch,
    formatEpochUs, parseFiniteField, parseTlePair, parseTleInput, upperCaseKeys, parseOmmEpochUtc,
    recordEpochUs, compareRecordEpochs, parseOmmRecord, parseOmmInput, parseInput, recordToOmm,
    serialiseRecordsAsOmm, validatedRecordsFromRaw, mergeOrbitalHistories, recordsConflict,
    compareCatalogueIdentifier, catalogueMetadataPreference, catalogueRevisionAudit,
    resolveCatalogueRevisions, describeParse
  });
};
