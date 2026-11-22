# Sequential evidence v1.0 results

## Disposition

**Research-only. Integration gate not passed.**

The sequential-evidence stage established a rigorous *conditional* e-process theorem and an operational empirical event-rate calibration, but the real development result does not yet support integration into detector method 0.4.

The benchmark v1.0 confirmatory partition was not materialised, inspected or scored during this sequential-evidence stage. The subsequent confirmatory evaluation is recorded in [the final results](../confirmatory_v1/RESULTS-v1.0.md).

## Formal validation

The implemented unknown-change-start Bernoulli mixture is theorem-qualified under the explicit condition

`Pr(X_t = 1 | F_{t-1}) <= q0`

for every monitored update. Exact finite-horizon enumeration in `test_sequential_v1.py` verifies the expected-wealth and Ville-crossing properties of the implementation for a small exhaustive case.

This condition has **not** been proved for the real GP score stream. The real-data `q0` is empirically estimated and is not a conditional confidence bound. Consequently the satellite result is described only as **empirically risk-calibrated sequential screening**.

## Null simulations

Frozen simulation settings:

- `q0 = 0.05`
- theorem-mode `alpha = 0.05`
- wealth threshold `20`
- 500 monitored updates per path
- 3,000 deterministic-seed replicates per scenario

| Scenario | Assumption status | Crossing probability |
|---|---|---:|
| IID Bernoulli at `p=q0` | valid | 0.028000 |
| Predictable nonstationary `p_t <= q0` | valid | 0.019667 |
| Clustered sequence with the same approximate marginal but conditional bound violated | invalid | 0.516000 |
| IID true rate `1.5 q0` | invalid | 0.232667 |

The valid-null simulations remain below the 0.05 Ville bound. The deliberate violation cases exceed it strongly. The clustered case is particularly important: approximately matching the marginal event frequency is not enough when conditional clustering violates the null premise.

Frozen machine-readable output:

`benchmark-results/sequential-v1-null-simulations.json`

SHA-256 of the validated workflow artifact member:

`178c8cf762796dde185e8e340627b6480be9e6a8dc1b964fdef606af3c238d3f`

## Development selection

The Transformer backbone from the selective-model stage remained frozen. Sequential base-threshold candidates were selected on development LEO data only.

Selected parameters:

- base surprise threshold `u = 17.822733355396952`
- empirical exceedance parameter `q0 = 0.16603773584905662`
- development covered quiet exposure `1.3518613220131013` object-month
- provisional development wealth threshold `1.01`
- provisional development false events `0`
- sequential PU event-versus-quiet mean percentile `0.6427083333333333`
- scorable documented truth intervals for the PU statistic `32`

The sequential ranking statistic improved materially relative to the Selective-model pointwise Transformer statistic (`0.480625`). This shows that accumulation changes the ordering in a useful direction.

However, the actual event decision remained ineffective:

- true positives: `0`
- false negatives: `36`
- strict development recall: `0.0`
- predicted events across the four supported LEO event cases: `0`

Therefore improved ranking did not translate into event-level sensitivity.

## Final empirical calibration

After the sequential design was frozen, the final wealth threshold was calibrated on the LEO calibration verified-quiet case `aqua-free-drift-2024-02`.

- final LEO support threshold: `1.2019241655473716`
- calibration covered exposure: `0.4665623499247091` object-month
- operational target: at most `1.0` false event per covered object-month
- selected wealth threshold: `1.01`
- observed calibration false events: `0`
- observed calibration false-event rate: `0.0` per covered object-month

The threshold's diagnostic reciprocal is approximately `0.990099`. That is **not** used as an alpha claim. It demonstrates that the current operational event-rate calibration is not remotely equivalent to a useful theorem-mode 5% crossing threshold. The calibration sample is also very small.

A post-calibration development diagnostic still produced `0/36` detections.

Frozen machine-readable output:

`benchmark-results/sequential-v1-development.json`

SHA-256 of the validated workflow artifact member:

`9e5bf318de58510ca3b75a01bb5719c1113738a805168052f0b77b1f7020d34d`

## Failure diagnosis

The main empirical bottleneck is now clearer than it was in the selective-model stage. Sequential accumulation improves event-versus-quiet ranking, but an event-like update requires both:

1. conditional surprise above the selected base threshold; and
2. the current transparent physical corroboration gate.

At the frozen risk-calibrated operating point, this binary stream does not provide enough sustained event evidence on the documented development maneuvers to trigger events.

This points to the physical/feasibility representation and event evidence definition, rather than a need for another neural architecture. The subsequent maneuver-physics stage tested whether physically feasible directional changes supplied better event evidence; its [frozen results](../physics_v1/RESULTS-v1.0.md) retain zero development event recall.

## Scientific claim boundary

The sequential-evidence results support these statements:

- the implemented Bernoulli mixture is anytime-valid **conditional on** a stated per-update conditional exceedance bound;
- exact tests and null simulations are consistent with that theorem;
- violating the conditional bound through clustering or rate misspecification breaks the nominal crossing behavior;
- the real GP implementation is calibrated in the interpretable unit of false events per covered object-month;
- sequential accumulation improves the development PU ranking statistic over the pointwise selective-model score.

The sequential-evidence results do **not** support these statements:

- formally risk-controlled maneuver detection from public GP histories;
- guaranteed false events per object-month;
- conformal validity for the GP stream;
- improved event recall over detector 0.4;
- readiness to inspect the confirmatory partition.

Detector method 0.4 remains unchanged.