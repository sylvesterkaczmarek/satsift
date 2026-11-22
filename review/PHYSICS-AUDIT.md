# Physics evaluation audit

## Disposition

The physics evaluation is complete and remains research-only. Detector method 0.4 is unchanged. Confirmatory data remained sealed at the time of this audit. The later integrity, comparison and confirmatory stages are now complete; the [confirmatory evaluation](../research/confirmatory_v1/RESULTS-v1.0.md) failed its integration gate.

## Verified physics result

- Original physics-stage commit: `7125320001fc379c573b52a551af2d99a82db7a8`.
- Frozen result: `benchmark-results/physics-v1-development.json`.
- Frozen result SHA-256: `b4422b7a2c01a2940513bc6fcef25963e454732792bac6cb17e2183bfd44898e`.
- Development TP/FN: `0 / 36`.
- Development recall: `0.0`.
- PU sequential-wealth mean percentile: `0.8660130718954249`.
- Truth intervals containing a feasible physics solution: `2`.
- Physics evaluation integration gate: failed.

## Audit corrections

Three non-result-changing issues were corrected after the freeze.

1. The method text previously described the production Jacobian as centered numerical differentiation. The implementation uses a forward local perturbation, so the documentation now says `forward/local numerical impulse differentiation`.
2. The integration-gate rule stated that the false-event-rate target must also be satisfied, while the Boolean expression checked only recovered TP and recall. The code now explicitly requires a finite final false-event rate no greater than `TARGET_FALSE_EVENTS_PER_OBJECT_MONTH`.
3. The deterministic injected-maneuver tests generated their synthetic post-burn states with the same Cartesian impulse helper used by the production finite-difference Jacobian. That made the inversion validation partly self-consistent. `independent_check.py` now directly compares the production `[p,f,g,h,k]` RTN Jacobian against an independently derived first-order Jacobian from the classical Gauss variational equations before the injected-maneuver tests are accepted.

The frozen physics result does not change because these corrections affect documentation, gate enforcement and validation strength only. The recorded false-event rate was `0.0`, recall remained `0.0`, the scientific result remains frozen, and the integration gate remains failed.

## Scientific checks

The retained physics validation now covers:

- prograde nonsingular equinoctial inversion;
- unknown burn-phase search;
- radial, along-track and cross-track equivalent impulse estimation;
- uncertainty-bounded delta-v intervals;
- independent common-epoch RTN corroboration where the HCW approximation is valid;
- explicit `nominal`, `feasible`, `inconsistent` and `abstain` outcomes;
- analytic classical Gauss impulsive equations versus Cartesian impulse reconstruction;
- direct production equinoctial Jacobian versus analytic classical Gauss-equation response;
- deterministic injected radial, along-track and cross-track maneuvers;
- abstention when burn geometry or direction is underdetermined;
- explicit refusal to use confirmatory metadata in the physics experiment.

## Subsequent research

The subsequent integrity study used this verified physics baseline and retained separate integrity/security artifacts. It did not access the confirmatory partition. Its final results are recorded in [the integrity audit](INTEGRITY-AUDIT.md).
