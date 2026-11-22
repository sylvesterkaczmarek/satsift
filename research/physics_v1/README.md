# Maneuver physics feasibility v1.0

This directory contains the maneuver-physics research layer for Satellite Maneuver Detector.

## Status

**Implemented and tested on deterministic fixtures. Not integrated.**

The layer replaces threshold co-occurrence with an astrodynamics inversion that asks whether joint public-GP orbital-element and common-epoch RTN changes are compatible with an equivalent radial, along-track or cross-track impulse.

Detector method 0.4 remains unchanged. The confirmatory partition remained sealed during this development stage. It was subsequently consumed by the completed confirmatory evaluation, which failed its integration gate; see [the final results](../confirmatory_v1/RESULTS-v1.0.md). It may not be reused as untouched evidence for a tuned successor.

## Main files

- `core.py`; orbital conversions, nonsingular equinoctial representation, verified-quiet physics drift model, numerical impulse sensitivity, HCW helper and result types.
- `inverter.py`; uncertainty-aware unknown-burn-phase equivalent impulse inversion.
- `screen.py`; calibrated nominal/no-maneuver envelope plus the final maneuver-physics screen.
- `independent_check.py`; independent analytic Gauss-equation checks and deterministic injected maneuver validation.
- `run_development.py`; sealed development/calibration experiment.
- `METHOD-v1.0.md`; full mathematical/algorithmic definition and limitations.
- `RESULTS-v1.0.md`; frozen physics result and disposition.

Frozen machine-readable output:

`benchmark-results/physics-v1-development.json`

SHA-256:

`b4422b7a2c01a2940513bc6fcef25963e454732792bac6cb17e2183bfd44898e`

## Outcome semantics

- `nominal`: within the verified-quiet joint physics envelope; monitored as a non-event.
- `feasible`: stable signed RTN direction and uncertainty-bounded equivalent delta-v interval are supported.
- `inconsistent`: well-posed inversion does not fit a plausible equivalent impulse at calibrated scale.
- `abstain`: anomalous but underdetermined/ill-conditioned, or outside qualified calibration support.

Only `feasible` acts as physical corroboration for sequential event evidence. Abstentions reset sequential evidence.

## Validation outcome

Independent validation passes:

- analytic classical Gauss impulse changes versus Cartesian impulse reconstruction;
- deterministic radial injection;
- deterministic along-track injection;
- deterministic cross-track injection;
- underdetermined/no-RTN case does not report false directional precision.

## Development result

The physics layer increases the PU sequential wealth ranking from the sequential stage's `0.6427083333333333` to `0.8660130718954249`, and produces a physically feasible positive cross-track equivalent-impulse solution in the Jason-1 development case.

It still produces `0/36` development event detections after calibration. The Physics evaluation integration gate therefore fails.

The failed development result remains frozen. The later confirmatory evaluation also failed; any new method needs its own declared protocol and independent holdout.
