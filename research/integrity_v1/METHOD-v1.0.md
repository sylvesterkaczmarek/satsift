# Integrity and selective-abstention layer v1.0

## Scope

The integrity study evaluates a separate abstention and data-integrity layer around the frozen maneuver-physics method. It did not modify detector method 0.4 or access benchmark v1.0 confirmatory satellites. The confirmatory partition remained sealed during this development stage. It was subsequently consumed by the completed confirmatory evaluation, which failed its integration gate; see [the final results](../confirmatory_v1/RESULTS-v1.0.md). It may not be reused as untouched evidence for a tuned successor.

The layer has two functions:

1. make abstention causes explicit instead of collapsing data, support and integrity failures into one generic state;
2. stress the complete development/calibration research path under deterministic integrity attacks and data failures.

Results are stored under the `integrity_v1` namespace so they can be analysed independently from the maneuver-detection paper and can support a separate AI-integrity/security study.

## Frozen scientific stack and two evaluation anchors

The physics stage used different support/calibration states for its development ranking diagnostic and its final held-out verified-quiet calibration. The integrity study preserves that distinction rather than combining them into one incomparable metric.

### Development detection/ranking anchor

The development stress view uses exactly the physics-stage development diagnostic stack:

- Transformer nominal model fitted on clean development verified-quiet cases;
- base surprise threshold `17.822733355396952`;
- development LEO support threshold `15937.989955517674`;
- Physics-stage empirical `q0 = 0.24444444444444446`;
- development wealth threshold `1.730962511467316`;
- maneuver-physics v1.0 equivalent-impulse screen;
- four LEO development event-evidence cases containing 36 documented intervals;
- fixed clean verified-quiet wealth reference reconstructed with the development cross-fit used by the physics stage.

The clean condition must reproduce the physics stage's PU sequential-wealth percentile `0.8660130718954249` and TP/FN `0/36` before stress deltas are interpreted.

### Final held-out calibration anchor

The final calibration stress view uses exactly the held-out Aqua setup from the physics stage:

- Aqua is held out from model/support/physics background fitting;
- the other seven clean verified-quiet development/calibration objects form the training/reference pool;
- final LEO support threshold `1.2019241655473716`;
- the same frozen `q0 = 0.24444444444444446`;
- final wealth threshold `1.01`;
- target at most `1.0` false event per covered verified-quiet object-month.

The earlier physics-stage Aqua anchor recorded coverage `0.5277777777777778` and zero false events. After the integrity gate introduced temporal-context resets, the final clean integrity condition scored 37 of 72 rows, with coverage `0.5138888888888888` and zero false events. Stress deltas in the frozen integrity result use that final clean condition; the earlier anchor remains recorded separately.

Stressed variants are never used for fitting the Transformer, support model or physics background model. The confirmatory partition remained sealed throughout this integrity study.

## Explicit selective abstention

`SelectiveIntegrityGate` evaluates case-level integrity before ML scoring and row-level integrity before a score is allowed into the sequential process.

### Case-level hard abstention

A case is suppressed when any of the following is present:

- unresolved conflicting catalogue duplicates or near-simultaneous revisions;
- catalogue identity/regime inconsistency;
- excessive rejected/malformed records;
- insufficient resolved history or too few evaluable pairs;
- inadequate SGP4 propagation support or excessive propagation failure;
- excessive excluded gaps or strongly irregular sampling;
- detector-level hard data-quality failure.

These produce named reasons such as `unresolved_catalogue_revision`, `catalogue_identity_or_regime_change`, `missing_or_corrupted_history`, `insufficient_history`, `poor_propagation`, and `irregular_or_gapped_sampling`.

### Recoverable integrity alerts

Some anomalies are explicitly auditable without forcing abstention:

- exact duplicate/replay records that are deterministically removed;
- catalogue corrections that are deterministically superseded;
- a small fraction of malformed records that are rejected while the remaining history stays usable.

These are surfaced separately as recoverable integrity alerts rather than being silently ignored.

### Row-level abstention

For a case that survives the hard gate, individual rows abstain for:

- missing feature/context/physics data;
- ineligible oversized sampling gaps;
- unavailable common-epoch SGP4 RTN residuals;
- an orbit regime with insufficient independent calibration satellites;
- unavailable same-regime support distance;
- support distance above the applicable frozen calibrated threshold, reported as `out_of_distribution_object`;
- unavailable/non-finite conditional distribution output;
- underdetermined maneuver-physics inversion.

Any abstention resets sequential evidence. A pre-score integrity, calibration-support or OOD abstention also resets the temporal model context: prediction is performed only within contiguous trusted row segments, so an untrusted row cannot influence a later score through hidden state or previous-observation features. Abstained exposure never contributes to the verified-quiet false-event denominator.

## Integrity stress matrix

The deterministic stress generator produces a clean reference plus twelve attack/failure conditions for every eligible development/calibration case:

| Condition | Integrity class | Intended property |
|---|---|---|
| timestamp displacement | timing integrity | displaced epochs should be contained or abstained when support/sampling becomes unreliable |
| corrected duplicate | catalogue integrity | later authoritative correction should be deterministically resolved and audited |
| unresolved duplicate | catalogue integrity | conflicting revision without preference metadata should abstain |
| replay | replay integrity | exact replay should be deduplicated and audited |
| insertion | record integrity | inserted synthetic state should be detected, rejected or selectively abstained |
| deletion | availability integrity | degraded history should reduce coverage instead of creating false confidence |
| truncated history | availability integrity | insufficient history should abstain |
| irregular sampling | sampling integrity | unsupported/gapped segments should abstain |
| catalogue-regime change | regime integrity | a same-object orbital-regime discontinuity should abstain without relying on an identity mismatch |
| corrupted history | storage/history integrity | malformed records should be rejected and excessive corruption should abstain |
| adversarial false maneuver | adversarial integrity | coherent manipulation of a verified-quiet history should not silently create trusted false events |
| adversarial maneuver suppression | adversarial integrity | smoothing a documented event should be visible as ranking/coverage degradation or abstention |

The attack label is used only to group results. It is never passed to the abstention gate or model.

## Persistent history-cache integrity

The integrity work also hardens `history.php` independently of the ML experiment. New cache writes bind the ordered record list to a SHA-256 digest. Cache reads validate:

- schema version;
- requested NORAD identity;
- coverage-interval syntax;
- record identity and epoch presence;
- record SHA-256 digest when present;
- full-store SHA-256 binding of version, source, NORAD identity, coverage intervals and ordered records when present.

Malformed JSON, wrong-object records and digest mismatch fail closed with a 502 response instead of being silently trusted or silently treated as an ordinary cache miss. Legacy stores without a digest remain shape-validated and are labelled `legacy-validated` until rewritten.

## Stress metrics

Every stress condition reports three separate groups of metrics.

### Development detection/ranking

- true positives and false negatives on the four LEO development event-evidence cases;
- event recall and predicted event count;
- positive-unlabelled sequential-wealth percentile against the fixed clean verified-quiet wealth reference from the physics stage;
- change in that ranking relative to clean;
- row and hard-case abstention fractions with named reasons.

### Final calibration degradation

- held-out Aqua coverage and covered verified-quiet object-months;
- false events and false events/object-month under the frozen final operating point from the physics stage;
- empirical `q0` re-estimated only as a diagnostic under stress;
- `q0` and coverage changes relative to clean;
- wealth threshold that would be required if calibration were repeated under the stressed Aqua data;
- whether the frozen `1.0` false-event/object-month target is exceeded.

### Structural integrity response

Across all 18 case variants for each condition, the integrity study also reports:

- hard case abstention fraction;
- named reason counts;
- recoverable integrity-alert counts and case fraction.

This structural view is intentionally separate from maneuver-detection performance because non-LEO and sparse cases can legitimately be unsupported while still being useful integrity tests.

## Claim boundary

This experiment measures robustness to a deterministic attack suite. It does not prove adversarial robustness, cryptographic provenance of upstream Space-Track data, formal OOD guarantees, or operational cyber assurance. A successful stress condition means only that the tested transformation was contained under the frozen development/calibration setup.
