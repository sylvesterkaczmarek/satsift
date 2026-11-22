# Comparison suite v1.0

The comparison suite provides the publication comparison layer for the Satellite Maneuver Detector research programme.

The suite is intentionally separate from detector 0.4 and the frozen pre-confirmatory v1.0 methods. It uses only benchmark v1.0 development and calibration objects. Confirmatory objects remained sealed during this comparison. They were subsequently consumed by the [completed confirmatory evaluation](../confirmatory_v1/RESULTS-v1.0.md), which failed its integration gate.

## Included methods

The frozen roster contains detector 0.4, two simple element baselines, an SGP4 RTN consistency baseline, robust multi-element MAD, robust Mahalanobis, robust CUSUM, a Kalman NIS filter, a clearly labelled Shorten-style optimal-proposal particle-filter surrogate, robust conditional linear prediction, LSTM, GRU, TCN, Transformer, a sequential LSTM autoencoder, and the frozen physics-ML v1.0 stack.

`METHOD-v1.0.md` defines the anti-cherry-picking policy, fixed settings, calibration rules, reproducibility boundaries and metrics.

## Primary comparison

Calibration is the primary comparison split. Generic baselines train normal-state parameters only on development verified-quiet histories. Their event threshold uses calibration verified-quiet exposure only. Calibration event labels are never used to select methods or settings.

Detector 0.4 and physics-ML v1.0 retain their already-frozen operating points.

## Outputs

The audited comparison artifacts are:

- `benchmark-results/comparison-v1-development-calibration.json`
- `research/comparison_v1/RESULTS-v1.0.md`
- `tests/comparison_v1_freeze_test.py`
- `review/COMPARISON-AUDIT.md`

The result reports event-level precision, recall, F1, false events per covered object-month, detection delay, abstention, calibration, satellite-cluster confidence intervals, orbit-regime results and computational cost.

## Boundary

The Shorten-style comparator is a structural surrogate because the published method depends on a non-standard mean-element SGP4 implementation and specific Kozai/Brouwer and singularity-aware covariance handling that this repository cannot reproduce exactly from a validated public drop-in implementation. The suite records that limitation explicitly rather than presenting an approximation as an exact reproduction.
