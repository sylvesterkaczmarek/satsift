# Maintained event matching

The maintained browser and Python evaluators use scoring version `event-matching-v3`. Version 2 introduced corrected event assignment; version 3 retains that algorithm and requires strict truth timestamps for new evaluations. Earlier reviewed version fingerprints remain recorded. The archived historical evaluator, frozen protocols, result bytes, checksums, operating points and failed confirmatory gate retain their original calculations.

## Assignment objective

Each prediction and truth event may participate in at most one match. Assignment follows these priorities:

1. Maximise the number of matched pairs.
2. Among assignments with that count, minimise total absolute distance from each prediction's strongest point to its matched truth interval midpoint.
3. Resolve remaining equal-cost choices with the canonical ordering and shortest-path rules below.

A pair is eligible when the prediction interval overlaps the tolerance-expanded truth interval, including either boundary. With prediction interval `[ps, pe]`, truth interval `[ts, te]` and tolerance `tau`, this is `pe >= ts - tau` and `ps <= te + tau`. Strongest-point distance is an assignment cost; it does not replace interval-overlap eligibility. A strongest point outside its prediction interval remains accepted by the matching core, consistent with the earlier eligibility rule.

The original cardinality counterexample has truth points at hours 0 and 10, prediction points at hours -5 and 4, and tolerance 6 hours. Greedy closest-pair selection finds one match. The maintained assignment finds two. A separate cost example has truth points at hours 0 and 10, predictions at hours 6 and 20, and tolerance 20 hours. Greedy selection matches both but has total distance 24 hours; the minimum-distance assignment totals 16 hours.

## Exact arithmetic and timestamp validation

The matching core receives integer microsecond epochs. Its exact edge cost is `abs(2 * strongest_us - truth_start_us - truth_end_us)`. This is twice the physical distance in microseconds and preserves half-microsecond truth midpoints without floating-point rounding. Python uses integers and the browser uses `BigInt` for assignment arithmetic, including path costs and potentials. Output delays remain ordinary numeric hours.

Finite nonnegative tolerance hours are interpreted from their decimal spelling and converted with exact `floor(hours * 3_600_000_000)` arithmetic. This preserves the inclusive comparison for integral-microsecond gaps: a gap is eligible exactly when it does not exceed the configured tolerance. Rounding tolerance upwards would admit an extra boundary. Negative or nonfinite tolerances, noninteger core endpoints and reversed intervals fail explicitly.

Browser prediction endpoints and strongest points use the precise record epochs when the analysis records are available. Direct callers with only `Date` values retain their available millisecond precision. The general OMM/TLE input parsers and legacy Python prediction-time parsers retain their separate contracts. Cross-language assignment parity requires both prediction adapters to resolve the same instants. The existing satellite.js OMM model-initialisation precision limit remains. Research ranking and exposure calculations retain their existing formulas, including floating-point time comparisons after strict truth admission. The exact microsecond guarantees here cover parsing, interval validation and event matching.

### Truth timestamp admission

A supplied `truth_events` field must be an array of event objects. Each canonical event has a required `start` and optional `end`. Browser and maintained Python truth timestamps share one supported form: `YYYY-MM-DDTHH:mm:ss[.fraction](Z|+HH:mm|-HH:mm)`. The fraction is optional and contains one to six digits when present. For example, `2026-01-02T03:04:05.123456+01:00` normalises to `2026-01-02T02:04:05.123456Z`.

| Part | Admission rule |
| --- | --- |
| Value and separators | A string only, ASCII digits, uppercase `T` and `Z`, with no surrounding whitespace or trailing characters. |
| Calendar date | Years 0001 to 9999, real Gregorian months and days, including the full leap-year rule. |
| Clock time | Hours 00 to 23, minutes 00 to 59 and seconds 00 to 59. Leap-second notation and `24:00:00` are rejected. |
| Fraction | Absent or one to six decimal digits. Longer fractions are rejected even when their extra digits are zero. No precision is silently truncated. |
| Zone | Explicit `Z` or numeric `+HH:mm`/`-HH:mm`, with offset hours 00 to 23 and minutes 00 to 59. `-00:00` is treated as numeric zero. |
| UTC range | The converted UTC instant must also remain in years 0001 to 9999. |
| Interval end | Omission creates a point event at start. A supplied null, empty, Boolean, numeric or otherwise invalid end is rejected. |
| Interval order | End must be at or after start after exact UTC conversion; microsecond differences are retained. |

Accepted instants are computed as integer microseconds without a floating-point timestamp conversion. Browser truth boundaries are exported as UTC strings with exactly six fractional digits. Validation does not depend on the computer timezone, including daylight-saving transitions. Supplied truth is checked even when no predictions match; label status does not make malformed boundaries valid.

The legacy physics-ML evaluation adapter also accepts `start_utc` and `end_utc` aliases. If both names are supplied for a boundary, both must be valid and represent the same exact UTC instant.

Earlier scoring versions accepted broader date spellings and could interpret timestamps without a zone differently between environments. Legacy benchmark files must be corrected from their source timezone and precision before use with the maintained evaluator. The archived historical parser and frozen evidence remain unchanged.

## Canonical ordering and equal-cost choices

Predictions sort by `(start_us, end_us, strongest_us)` and truth events by `(start_us, end_us)`. Original indices distinguish only temporally identical duplicates. Labels, source descriptions and other metadata do not affect assignment. Duplicate temporal records are interchangeable; permutation invariance concerns the resulting temporal pair multiset, while reported indices always refer to the caller's arrays.

The implementation uses a unit-capacity residual network. Node 0 is the source, followed by canonical prediction nodes, canonical truth nodes and the sink. Source-to-prediction and truth-to-sink edges cost zero. Eligible prediction-to-truth edges use the exact distance cost and are inserted in canonical row order. Each edge has a residual reverse edge with the opposite cost.

Successive shortest augmenting paths use Dijkstra's algorithm with reduced costs and integer node potentials. Equal queue distances select the smaller canonical node number. A predecessor changes only for a strictly shorter path. Each iteration computes all reachable distances before updating their potentials, then augments one unit. Iteration stops only when the sink is unreachable. Reverse edges allow earlier pairs to be reassigned, which is necessary for both maximum cardinality and minimum total cost.

Selected pairs are returned in canonical prediction order and then truth order, with their original indices restored. The tie rule specifies a deterministic algorithm; it does not claim that the final pair-index vector is lexicographically minimal.

For `P` predictions, `T` truths, `E` eligible pairs and `K` matches, graph construction checks `P * T` pairs. Heap-based shortest paths take `O(K * (E + P + T) * log(P + T))` time, in addition to construction and sorting, and `O(E + P + T)` memory. No additional matching dependency is required.

## Delay and report versions

Primary detection delay is `(prediction_start_us - truth_start_us) / 3_600_000_000`. Negative delay means the prediction starts before the documented truth interval. Strongest-point delay uses the strongest epoch in place of prediction onset and remains a separate diagnostic in detailed match dictionaries. The legacy physics-ML three-tuple API keeps its shape and places onset delay in its third item; its detailed strongest-point diagnostic is available through the shared core.

| Surface | Current identity |
| --- | --- |
| Shared Python matcher | `research/event_matching.py`, `EVENT_MATCHING_VERSION = "event-matching-v3"` |
| Browser benchmark report | `smd-event-benchmark-report-v4`, `scoring_version: "event-matching-v3"` |
| Browser benchmark identifier | `smb-v2-` prefix, with scoring version included in the identity contract |
| Maintained Python reports | `evaluation_version: "case-statistics-v3"` and `scoring_version: "event-matching-v3"` |
| Archived verification | `confirmatory-v1-historical`, retaining greedy assignment |

Event-evidence predictions outside documented intervals remain unverified under the existing positive-unlabelled rules. Confirmed-quiet and fully labelled negative coverage keep their existing treatment. Matching changes do not alter detector 0.4 thresholds or generate new performance evidence.

## Verification and future outputs

Run `python3 tests/event_matching_test.py` from the repository root with Python and Node.js available. The independent brute-force oracle checks cardinality and total cost across exhaustive small cases and seeded cases. Targeted checks cover the original defect, overlapping intervals, inclusive tolerance boundaries, exact midpoints, input permutations, delay semantics and browser/Python parity. The browser bridge is `tests/event_matching_bridge.js`. Run `python3 tests/benchmark_timestamp_test.py` for strict admission, exact UTC normalisation, interval validation and browser/Python checks in UTC, America/New_York, Europe/Berlin and Asia/Kolkata. Run `node tests/event_matching_version_test.js` to verify the reviewed browser scoring fingerprint; `tests/evaluation_version_test.py` guards the maintained Python contract. Both repository workflows run the matching regressions and version guards.

Historical verification remains separate. Follow [HISTORICAL-VERIFICATION.md](HISTORICAL-VERIFICATION.md) to reproduce stored calculations without rerunning experiments. Keep future evaluation outputs separately named and versioned. Maintained scored-report CLI defaults use the `case-statistics-v3` suffix where an output filename is provided by default, apart from the separately protected confirmatory runner. Explicit output paths must also keep corrected results separate from frozen evidence. The consumed confirmatory partition remains consumed; a new scoring identifier does not authorise another one-shot experiment.
