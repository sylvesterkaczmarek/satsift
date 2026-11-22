# Maneuver physics feasibility v1.0 results

## Disposition

**Research-only. Physics evaluation integration gate failed.**

The new layer is a substantial physics improvement over threshold co-occurrence: it performs an uncertainty-aware equivalent RTN impulse inversion, returns signed direction and delta-v intervals only when identifiable, explicitly abstains on underdetermined anomalous geometry, and passes independent deterministic astrodynamics validation.

However, the development/calibration result still does not support integration into detector method 0.4. The benchmark v1.0 confirmatory partition was not materialized, inspected or scored during this physics stage. It was later consumed by the [completed confirmatory evaluation](../confirmatory_v1/RESULTS-v1.0.md), which also failed.

## Independent astrodynamics validation

The validation suite passed all required tests:

1. independent classical Gauss impulsive equations versus Cartesian velocity impulses and Cartesian-to-element reconstruction;
2. deterministic radial maneuver injection;
3. deterministic along-track maneuver injection;
4. deterministic cross-track maneuver injection;
5. removal of RTN corroboration does not produce false directional precision when burn phase is broad/ambiguous.

For the injected maneuver cases, the inversion recovers the correct dominant RTN direction and the known injected delta-v lies inside the returned uncertainty interval.

## Frozen detector settings

Physics evaluation did not retune the sequential-evidence detector after inspecting event outcomes.

Frozen values include:

- Transformer backbone;
- base conditional-surprise threshold `17.822733355396952`;
- Sequential development support threshold `15937.989955517674`;
- final LEO support threshold `1.2019241655473716`;
- target at most `1.0` false event per covered verified-quiet object-month;
- GEO/MEO/HEO unsupported and abstaining;
- confirmatory partition sealed.

The event-like Bernoulli parameter was necessarily re-estimated after replacing the physics gate because the definition of an event-like update changed.

## Development quiet cross-fit

The physics background model was cross-fitted using explicit development verified-quiet satellites only.

| Case | Physics outcomes | Selective coverage |
|---|---|---:|
| Aura post-final-orbit-maintenance | 38 nominal | 0.974359 |
| ERS-2 passivated | 2 nominal, 53 inconsistent, 2 feasible, 4 abstain | 0.919355 |
| GOCE propulsion exhausted | 5 inconsistent, 2 feasible, 44 abstain | 0.134615 |

The relatively low GOCE coverage is reported rather than hidden. It reflects poor cross-satellite support/identifiability under the frozen physics model.

The new event-like stream has empirical

`q0 = 0.24444444444444446`.

This is an empirical satellite-level estimate, not a formal conditional bound.

## Development event evaluation

On the four LEO development maneuver-evidence cases:

- documented truth intervals: `36`;
- true-positive events: `0`;
- false negatives: `36`;
- strict event recall: `0.0`;
- median matched-event delay: unavailable because there were no matches;
- PU sequential-wealth mean percentile: **`0.8660130718954249`**;
- PU-scorable truth intervals: `21`;
- truth intervals containing at least one physically feasible inversion: `2`.

The ranking change is substantial:

- Selective-model pointwise Transformer: `0.480625`;
- sequential evidence with simple physical gate: `0.6427083333333333`;
- Physics evaluation sequential evidence with explicit maneuver physics: **`0.8660130718954249`**.

This is useful evidence that the successive modeling layers improve event-versus-quiet ordering. It still does not establish a usable event detector because the calibrated decision procedure produced no event detections.

## Example feasible inversion

The development Jason-1 case contains the only feasible maneuver-physics row used by two overlapping/matching-tolerance truth intervals:

- row epoch: `2011-10-05T05:38:24.464Z`;
- dominant direction: **positive cross-track**;
- equivalent delta-v median: `95.8057758166321 m/s`;
- equivalent delta-v interval: **`51.806746934408174` to `139.80480469885603 m/s`**.

This must be interpreted as an equivalent impulse compatible with catalogue-derived changes at the model's uncertainty scale. It is not an estimate of an operator-reported executed burn, and the same row intersects two interval-censored truth windows under the frozen matching tolerance.

## Final verified-quiet calibration

The final LEO verified-quiet calibration case remains Aqua free drift.

Physics outcomes on supported Aqua rows:

- evaluated by physics layer: `69`;
- nominal: `38`;
- abstain: `31`;
- feasible maneuver inversions: `0`;
- resulting selective coverage: `0.5277777777777778`.

Final covered verified-quiet exposure is only

`0.25694738111795573 object-month`.

The final sequential wealth threshold remains `1.01`, with:

- observed false events: `0`;
- observed false events per covered object-month: `0.0`;
- target: at most `1.0`.

This exposure is too small for a strong false-alarm claim. The reciprocal of the wealth threshold is not an operational alpha claim.

## Post-calibration development diagnostic

After the final calibration was frozen, the development diagnostic still produced:

- true positives: `0`;
- false negatives: `36`;
- recall: `0.0`.

Therefore the predeclared Physics evaluation integration gate failed.

Gate rule:

> recover at least one event missed by the sequential layer and achieve at least 0.10 post-calibration development recall while remaining within the frozen empirical false-event-rate target.

The first two conditions were not met.

## Failure diagnosis

The stronger physics layer shows that the problem is no longer simply the old threshold-co-occurrence corroboration rule. The remaining bottlenecks are broader:

1. many documented maneuver intervals have no feature row inside sufficiently strong calibration support;
2. among supported anomalous rows, the public GP pair often does not identify a stable single equivalent impulse because the burn epoch is unknown and catalogue mean-element changes include propagation/catalogue effects;
3. only a small fraction of truth intervals yield an identifiable maneuver-physics solution;
4. the final support threshold inherited from the selective-model stage remains very restrictive on the maneuver-evidence cases;
5. verified-quiet calibration exposure is small.

These are scientifically meaningful limitations of maneuver inference from public GP histories and should be reported, not removed through post-hoc threshold relaxation.

## Frozen artifact

Machine-readable result:

`benchmark-results/physics-v1-development.json`

Final validated artifact-member SHA-256:

`b4422b7a2c01a2940513bc6fcef25963e454732792bac6cb17e2183bfd44898e`

## Scientific claim boundary

The physics evaluation supports:

- an explicit nonsingular equivalent-impulse inversion from joint GP element changes;
- calibrated nominal/no-maneuver screening;
- independent common-epoch RTN corroboration for near-circular cases;
- uncertainty-bounded delta-v/direction output when identifiable;
- explicit abstention for underdetermined anomalous cases;
- independent analytic Gauss-versus-Cartesian validation;
- deterministic injected radial/along/cross maneuver recovery;
- a substantial development PU-ranking improvement relative to the selective-model and sequential-evidence stages.

The physics evaluation does **not** support:

- exact executed burn reconstruction;
- operational-quality delta-v estimation;
- useful development event recall;
- integration into detector 0.4;
- inspection of the confirmatory partition.

Detector method 0.4 remains unchanged.
