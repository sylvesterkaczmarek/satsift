'use strict';

// Benchmark truth admission, event matching and aggregate metric helpers.
globalThis.SMDModules = globalThis.SMDModules || Object.create(null);
if (Object.prototype.hasOwnProperty.call(globalThis.SMDModules, "benchmark")) {
  throw new Error('Workbench module already registered: benchmark');
}
globalThis.SMDModules["benchmark"] = function createBenchmark(common, orbitalInput) {
  const {
    METHOD_VERSION, EVENT_MATCHING_VERSION, median, stableStringify, fnv1a64
  } = common;
  const {
    recordEpochUs, compareRecordEpochs, parseInput, serialiseRecordsAsOmm
  } = orbitalInput;

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

    const toleranceHours = Object.prototype.hasOwnProperty.call(decoded, 'matching_tolerance_hours')
      ? decoded.matching_tolerance_hours : 24;
    if (typeof toleranceHours !== 'number' || !Number.isFinite(toleranceHours) || toleranceHours < 0 || toleranceHours > 168) {
      throw new Error('matching_tolerance_hours must be a finite JSON number between 0 and 168.');
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

  return Object.freeze({
    benchmarkTemplateDefinition, normaliseBenchmarkLabelStatus, normaliseBenchmarkDefinition,
    benchmarkTimestamp, benchmarkTruthInterval, benchmarkToleranceUs, benchmarkPredictionInterval,
    matchEventIntervals, matchBenchmarkEvents, makeBenchmarkId, ratioOrNull, metricText,
    deterministicThinBenchmarkRaw, initialiseProfileAccumulator, finaliseProfileMetrics
  });
};
