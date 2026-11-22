# Elapsed-time evaluation contract

## Scope and version boundary

This contract defines `case-statistics-v4` and exposure policy `elapsed-intervals-v1` before implementation or revised data analysis. It is a separate retrospective evaluation path for retained predictions with explicit observation and support evidence. It preserves `event-matching-v3` assignment and onset-delay semantics. It does not train models, select operating points, rerun the consumed confirmatory experiment or revise its failed gate.

Existing training, calibration and evaluation producers keep their `case-statistics-v3` identity and calculations. In particular, their row-fraction or whole-span exposure estimates are compatibility calculations, not the corrected elapsed-time calculation. The new evaluator must not relabel those calibration results as v4. The historical archive, manifests, result bytes, operating points and run lock remain unchanged.

## Reviewed label admission in case-statistics-v5

The initial elapsed-interval contract is retained under `case-statistics-v4`. The maintained `case-statistics-v5` release adds an explicit label/truth consistency gate before counting events. Only `event-evidence`, `verified-quiet` and `unknown` are admitted. Event-evidence cases must contain at least one documented truth interval; verified-quiet and unknown cases must contain none. Unrecognised labels and contradictions raise an error, including on unselected splits and non-primary methods. Predictions and exposure are validated as before.

The `case-statistics-v4` source fingerprint is retained in the version gate and the v5 source has a separately reviewed fingerprint. The event matcher remains `event-matching-v3`. This repair does not rewrite historical outputs, establish new performance or reopen the consumed confirmatory partition.

## Input evidence

A document supplies one common `exposure_policy` with `version: "elapsed-intervals-v1"` and a positive `max_gap_seconds`. The limit must be declared before analysis. There is no inferred or default gap limit. The number must resolve to an exact whole number of microseconds. Changing the limit changes the evaluation contract and must be disclosed.

Each case can supply `exposure_evidence` with `window_start_utc`, `window_end_utc` and an `intervals` array. Each interval has `start_utc`, `end_utc` and a Boolean `supported`. The ledger represents the common source-observation schedule, including intervals on which the particular method abstained. An empty ledger is an explicit observation of no covered intervals; an absent ledger is missing information.

The supported decision belongs to the comparison ending at that interval's right endpoint. Exported research features already describe such pairs with `physics.before_epoch_utc` and `physics.after_epoch_utc`. An adapter may use those explicit bounds and the method's aligned support decisions. It must check array lengths and, where present, that `epoch_utc` equals the interval end. It must not infer an earlier endpoint from the previous surviving feature row, because invalid rows can have been omitted. A separately produced feature sequence is not proof of another method's support decisions.

Missing policy, boundaries or necessary interval evidence makes exposure unavailable. Supplied malformed values, reversed intervals, non-Boolean decisions, misaligned arrays or inconsistent timestamps are errors. Legacy `span_days`, `coverage_fraction`, row counts and whole-case `abstained: false` cannot establish elapsed exposure. A claimed whole-case abstention is inconsistent with supplied supported duration.

Timestamps use the strict explicit-zone, valid-calendar, at-most-six-fractional-digit parser from the matching contract. Calculations use integer microseconds. Case windows may be empty but cannot be reversed; source intervals must have strictly positive duration.

## Interval calculation

1. Check each complete source interval against the declared maximum gap before clipping. A duration equal to the limit is eligible; one microsecond beyond it is excluded.
2. Intersect eligible source intervals with the declared case window. There is no extrapolation before or after recorded source bounds.
3. Deduplicate intervals and take their union before measuring duration. Order, duplicate records and subdivision of an already covered eligible interval do not increase measured time.
4. Identical or overlapping eligible intervals with contradictory support decisions are rejected. The evaluator does not choose one conflicting decision by input order.
5. Measure the union of all eligible intervals and the union of supported eligible intervals. The difference is elapsed abstention. Time within the window without an eligible source interval is unobserved or excluded, not a supported decision.

Duration intervals are half-open `[start, end)`. A candidate assigned to its observation interval's right endpoint is checked using `(start, end]`; this does not alter duration. The start, end and strongest timestamp of each quiet candidate must each lie in a supported endpoint domain. This does not assert continuous support between grouped event endpoints. Counts outside supported time remain visible, but make the exposure-based rate and bound unavailable rather than producing a misleading ratio.

Report window, eligible, covered, abstained and unobserved durations separately, with exact microseconds as the primary representation. Covered fraction is covered duration divided by window duration. Elapsed abstention fraction is abstained duration divided by eligible duration. The uncovered window fraction is separately identified. Undefined fractions are `null`.

Convert measured duration to object-months using exactly 30.4375 days, or 2,629,800 seconds, per object-month. This is a unit conversion after interval integration.

## Pooling and method comparison

The same policy and source-observation schedule apply to every method in a comparison. Methods may differ in their support decisions. A multi-method input must identify matching cases, object identities, windows, labels and truth, and must not silently compare different supplied schedules. Missing support evidence remains explicit.

Different objects contribute separate object-time. Non-overlapping windows for one object can be pooled. Duplicate cases and overlapping windows for the same object are rejected because their candidate-event numerator cannot be safely deduplicated from interval unions alone. Adjacent windows are permitted. Missing object identity preserves count and per-case exposure diagnostics, but pooled rates, duration fractions, bounds and object-cluster uncertainty remain unavailable because duplicate-object time cannot be checked. Known reported-duration subtotals are diagnostics, not verified distinct object-time.

Each case must explicitly supply `predicted_events` as an array. An absent or null prediction result cannot be interpreted as an observed zero. Case identifiers must be nonempty and unique. The v4 input contract also requires every prediction to have its strongest timestamp within its own inclusive start/end bounds. This admission rule applies to every label and split; existing v3 parsers and matching calculations remain unchanged.

Count-based event metrics retain positive-unlabelled semantics: unmatched predictions on event-evidence cases remain unscored, while false candidates are counted on verified-quiet cases. Validate all supplied truth before split selection, including quiet and unselected cases.

If any selected verified-quiet case lacks exposure evidence, the pooled false-event rate is unavailable. Report the known exposure subtotal and the number of incomplete cases, but never divide all candidate counts by only the known subtotal. Known zero exposure has a distinct status. Event counts remain reportable when their inputs are valid.

## Uncertainty

### Object-cluster resampling

Resample complete object clusters with a deterministic recorded seed. Defaults are 2,000 replicates and seed 3404; both are recorded in each report. Multiple non-overlapping cases for one object belong to the same cluster. Repeated bootstrap draws intentionally have multiplicity; validation of ordinary overlapping cases must not collapse sampled clusters while retaining their event counts.

Each reported metric includes requested and defined replicate counts, relevant independent-object count and a status. A false-event-rate interval needs at least two quiet objects with positive known exposure, regardless of how many event-evidence objects exist. Missing object identities cannot be replaced by one fictitious shared object. Insufficient clusters, unknown or zero exposure, and degenerate values are explicitly identified.

When all observed quiet candidate counts are zero, the observed rate is zero if exposure is positive. Resampling that sample cannot establish a zero upper limit on unseen risk. Report null inferential interval endpoints, identify the zero-event degeneracy and, if useful, retain `[0, 0]` only in explicitly descriptive empirical-percentile fields. Other degenerate replicates also need a clear status. Percentiles based on only defined replicates must disclose their conditional interpretation and the number excluded.

### Conditional zero-event bound

For zero observed events over positive known exposure `T`, report the supplementary one-sided 95% homogeneous-Poisson rate upper value `-log(0.05) / T`. The numerator is approximately 2.995732273553991. This is a conditional model calculation with units of events per covered object-month, not an operational assurance claim.

The report names the model, confidence level, one-sided upper construction, count, exposure and assumptions, and always states `assumptions_verified: false`. Assumptions include a homogeneous rate, independent increments, correctly measured fixed or non-informative exposure, and an observation/support process that does not selectively hide events. Grouped detector candidates, adaptive thresholds, clustering, informative abstention and heterogeneous satellites can violate them. No bound is returned for unknown or zero exposure, inconsistent event support, or nonzero counts; the latter are outside this supplementary zero-event formula.

The formula follows the reciprocal of NIST's zero-event MTBF lower bound under a fixed-exposure homogeneous Poisson process. See [NIST confidence bounds](https://www.itl.nist.gov/div898/handbook/apr/section4/apr451.htm) and [NIST homogeneous Poisson process](https://www.itl.nist.gov/div898/handbook/apr/section1/apr171.htm). These model assumptions do not follow from this repository's engineering tests.

## Reports and output protection

The original v4 contract declared `case-statistics-v4`. Current reports declare `evaluation_version: "case-statistics-v5"`, `scoring_version: "event-matching-v3"`, the exposure policy and `analysis_scope: "retrospective"`. It records the input content digest, bootstrap settings and coverage limitations. It does not include a local input path or infer that a new version restores an untouched holdout.

The command-line interface requires an explicit fresh output destination. It refuses existing files, symlink file destinations, input overwrite and protected archival/data locations. Ordinary parent-directory aliases are resolved before protected-path checks; the resolved directory path is then opened component by component without following a changed symlink. This preserves legitimate platform and storage aliases without permitting a protected-directory alias to bypass validation. It must not overwrite a frozen report or sidecar. Missing support evidence may still produce count metrics with unavailable exposure, not repaired historical rate estimates.

The implementation and verification use the standard library and synthetic offline fixtures. No revised analysis of stored research data is required to implement or verify this contract.

## Using the evaluator

Prepare a JSON input containing retained predictions and the corresponding explicit support ledger. The CLI accepts explicit `cases` or `methods[].cases`; it does not automatically extract nested `case_results` from a frozen report or reconstruct absent support evidence. For example, this entirely synthetic quiet case contains a long excluded gap:

```json
{
  "method": "synthetic-demo",
  "exposure_policy": {
    "version": "elapsed-intervals-v1",
    "max_gap_seconds": 7200
  },
  "cases": [{
    "case_id": "quiet-a",
    "object_id": "synthetic-a",
    "label_status": "verified-quiet",
    "truth_events": [],
    "predicted_events": [],
    "exposure_evidence": {
      "window_start_utc": "2000-01-01T00:00:00Z",
      "window_end_utc": "2000-01-01T10:00:00Z",
      "intervals": [
        {"start_utc": "2000-01-01T00:00:00Z", "end_utc": "2000-01-01T01:00:00Z", "supported": true},
        {"start_utc": "2000-01-01T01:00:00Z", "end_utc": "2000-01-01T09:00:00Z", "supported": true},
        {"start_utc": "2000-01-01T09:00:00Z", "end_utc": "2000-01-01T10:00:00Z", "supported": true}
      ]
    }
  }]
}
```

From the repository root, use an explicit new output path outside protected research and data directories:

```sh
python3 tools/evaluate_elapsed_benchmark.py inputs/results-with-support.json \
  --output retrospective/elapsed-evaluation-v5.json \
  --bootstrap-samples 2000 --seed 3404
```

The optional `--split` selects cases after all supplied truth, predictions and exposure evidence are validated. For a method comparison, replace top-level `cases` with `methods: [{"method": "name", "cases": [...]}]` and retain the one top-level exposure policy. Method-specific policies and incompatible source schedules are rejected.

The Python API is `research.elapsed_evaluator.evaluate_document`. `research.elapsed_exposure.feature_exposure_evidence` can adapt explicit feature-pair endpoints and that same method's aligned finite-score/`None` sequence. It does not run a detector or reconstruct missing support. The input JSON digest and the CLI's original-byte digest are separately labelled; neither includes a local path.

The synthetic example establishes only two hours of covered time and one quiet object. Its observed event count is zero, its object-cluster interval is insufficient, and any supplementary upper value remains conditional on the stated model. It is not a new research-performance result.

## Required regression properties

- Irregular supported pairs `[0h, 1h]`, `[1h, 9h]` and `[9h, 10h]` with a two-hour gap limit yield two hours of eligible exposure.
- Duplicate, permuted and subdivided eligible intervals preserve duration and the zero-event bound.
- Gap boundaries, microseconds, clipping, empty windows, missing intervals, abstention and contradictory support have explicit outcomes.
- Unknown exposure differs from known zero; neither yields a finite rate or positive-exposure bound.
- Same-object overlapping cases are rejected, while bootstrap cluster multiplicity is retained.
- One quiet object cannot acquire a multi-object uncertainty interval through additional event-evidence cases.
- All-zero quiet observations cannot produce an inferential `[0, 0]` interval.
- The new source fingerprint rejects changes to interval arithmetic, denominator construction, uncertainty assumptions or missing-evidence handling. Previous fingerprints and historical verification remain intact.
