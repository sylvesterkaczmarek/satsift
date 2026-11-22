# Comparison suite v1.0 results

## Status

**Comparison evaluation is complete after post-run code and methodology audit and corrected re-evaluation.**

The benchmark v1.0 confirmatory partition was not accessed. Calibration is the primary comparison split and development event results are diagnostic only.

## Scope

- methods: `16`;
- development plus calibration objects materialized: `28`;
- primary split: `calibration`;
- event matching tolerance: `24.0` hours;
- common quiet risk budget: `1.0` event per covered object-month;
- satellite-cluster bootstrap replicates: `1000`;
- seed: `3404`.

## Audit corrections

The candidate run was retained as evidence but not accepted as the final result. The post-run audit corrected four issues before this freeze:

1. matched-event detection delay is now measured from the first alarm/event onset rather than from the later strongest point used for deterministic matching;
2. zero-recall methods now report `F1 = 0` even when precision is undefined because no scorable prediction was emitted;
3. sequence-model scoring explicitly resets temporal state at quality-abstention boundaries, and the filtering reference covariance no longer admits quality-failed rows;
4. computational inference timing now covers the same 14 primary calibration cases for every method, while development diagnostic timing is separate. The report also distinguishes unconstrained F1 ranking from operating points that actually meet the common verified-quiet risk budget.

No baseline was removed and no event-labelled calibration case was used to retune a baseline after the candidate results were seen.

## Primary calibration metrics

Values in brackets are satellite-cluster 95% bootstrap confidence intervals.

| Method | Precision | Recall | F1 | False events / object-month | Median first-alarm delay h | Abstention | Common budget |
|---|---:|---:|---:|---:|---:|---:|:---:|
| detector-0.4 | 0.8182 [0.5333, 1.0000] | 0.2812 [0.1428, 0.5456] | 0.4186 [0.2373, 0.6582] | 2.1335 [1.0487, 4.6038] | 2.86 [-5.59, 13.48] | 0.0714 [0.0000, 0.2143] | no |
| mean-motion-threshold | 0.8000 [0.3333, 1.0000] | 0.1250 [0.0425, 0.2917] | 0.2162 [0.0779, 0.4308] | 0.9209 [0.0000, 4.1081] | -7.35 [-19.51, 20.96] | 0.0000 [0.0000, 0.0000] | yes |
| sma-window-shift | 0.9167 [0.5714, 1.0000] | 0.1719 [0.0363, 0.4500] | 0.2895 [0.0688, 0.6102] | 0.6709 [0.0000, 3.7406] | 3.06 [-14.62, 30.33] | 0.2076 [0.1053, 0.3555] | yes |
| sgp4-rtn-consistency | 0.8667 [0.5714, 1.0000] | 0.2031 [0.0865, 0.3939] | 0.3291 [0.1551, 0.5455] | 0.9209 [0.0000, 3.3669] | 3.21 [-17.27, 9.10] | 0.0000 [0.0000, 0.0000] | yes |
| multi-element-mad | 0.6667 [0.0000, 1.0000] | 0.0625 [0.0000, 0.1622] | 0.1143 [0.0000, 0.2632] | 0.9209 [0.0000, 4.1081] | -7.14 [-62.20, -7.14] | 0.0000 [0.0000, 0.0000] | yes |
| robust-mahalanobis | 0.8333 [0.4286, 1.0000] | 0.1562 [0.0400, 0.4186] | 0.2632 [0.0741, 0.5614] | 0.9209 [0.0000, 3.3669] | -3.76 [-10.08, 20.05] | 0.0000 [0.0000, 0.0000] | yes |
| robust-cusum | 0.8000 [0.5000, 1.0000] | 0.1250 [0.0682, 0.2857] | 0.2162 [0.1240, 0.4151] | 0.9209 [0.0000, 1.9836] | -402.81 [-556.08, -107.29] | 0.0000 [0.0000, 0.0000] | yes |
| kalman-nis | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | 0.5137 [0.0000, 6.7337] | n/a | 0.0630 [0.0211, 0.1356] | yes |
| shorten-op-pf-surrogate | 0.5000 [0.0000, 1.0000] | 0.0156 [0.0000, 0.0577] | 0.0303 [0.0000, 0.1081] | 0.5137 [0.0000, 6.7337] | 2.51 [2.51, 2.51] | 0.0630 [0.0211, 0.1356] | yes |
| robust-linear | 0.5000 [0.0000, 1.0000] | 0.0312 [0.0000, 0.1515] | 0.0588 [0.0000, 0.2500] | 0.9209 [0.0000, 1.8148] | -33.58 [-38.13, -29.03] | 0.0000 [0.0000, 0.0000] | yes |
| lstm | 0.8000 [0.0000, 1.0000] | 0.0625 [0.0000, 0.2309] | 0.1159 [0.0000, 0.3721] | 0.5137 [0.0000, 6.7337] | 2.86 [2.86, 2.86] | 0.0630 [0.0211, 0.1356] | yes |
| gru | 0.7500 [0.0000, 1.0000] | 0.0469 [0.0000, 0.1732] | 0.0882 [0.0000, 0.2927] | 0.5137 [0.0000, 6.7337] | 3.21 [3.21, 3.21] | 0.0630 [0.0211, 0.1356] | yes |
| tcn | 0.7500 [0.0000, 1.0000] | 0.0469 [0.0000, 0.1732] | 0.0882 [0.0000, 0.2927] | 0.5137 [0.0000, 6.7337] | 3.21 [3.21, 3.21] | 0.0630 [0.0211, 0.1356] | yes |
| transformer | 0.8000 [0.0000, 1.0000] | 0.0625 [0.0000, 0.2309] | 0.1159 [0.0000, 0.3721] | 0.5137 [0.0000, 6.7337] | 2.86 [2.86, 2.86] | 0.0630 [0.0211, 0.1356] | yes |
| sequential-autoencoder | 0.8750 [0.0000, 1.0000] | 0.1094 [0.0000, 0.3333] | 0.1944 [0.0000, 0.4913] | 0.7480 [0.0000, 2.2752] | -8.69 [-62.20, -3.23] | 0.2621 [0.1474, 0.4137] | yes |
| physics-ml-v1.0 | n/a | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | n/a | 0.9623 [0.8869, 1.0000] | yes |

Under positive-unlabelled benchmark semantics, unmatched predictions on event-evidence histories remain unscored. False events are counted only on verified-quiet exposure.

## Descriptive F1 ranking

- 1. `detector-0.4`: F1 0.4186, recall 0.2812, quiet false-event rate 2.1335, common budget not met.
- 2. `sgp4-rtn-consistency`: F1 0.3291, recall 0.2031, quiet false-event rate 0.9209, common budget met.
- 3. `sma-window-shift`: F1 0.2895, recall 0.1719, quiet false-event rate 0.6709, common budget met.
- 4. `robust-mahalanobis`: F1 0.2632, recall 0.1562, quiet false-event rate 0.9209, common budget met.
- 5. `mean-motion-threshold`: F1 0.2162, recall 0.1250, quiet false-event rate 0.9209, common budget met.

This table preserves each method's frozen or calibrated operating point. In particular, a frozen target method is not retroactively retuned to satisfy the common risk budget.

## Common-risk-budget ranking

- 1. `sgp4-rtn-consistency`: F1 0.3291, recall 0.2031, quiet false-event rate 0.9209.
- 2. `sma-window-shift`: F1 0.2895, recall 0.1719, quiet false-event rate 0.6709.
- 3. `robust-mahalanobis`: F1 0.2632, recall 0.1562, quiet false-event rate 0.9209.
- 4. `mean-motion-threshold`: F1 0.2162, recall 0.1250, quiet false-event rate 0.9209.
- 5. `robust-cusum`: F1 0.2162, recall 0.1250, quiet false-event rate 0.9209.

This second table includes only operating points whose observed calibration verified-quiet false-event rate is at most `1.0` per covered object-month. It is descriptive and was not used for tuning.

## Calibration

| Method | Event threshold / wealth point | Covered quiet object-months | Observed quiet false-event rate | Common budget |
|---|---:|---:|---:|:---:|
| detector-0.4 | frozen detector 0.4 internal operating point | 1.8748 | 2.1335 | no |
| mean-motion-threshold | 0.717277 | 2.1718 | 0.9209 | yes |
| sma-window-shift | 0.843254 | 1.4906 | 0.6709 | yes |
| sgp4-rtn-consistency | 4.39701 | 2.1718 | 0.9209 | yes |
| multi-element-mad | 47.7354 | 2.1718 | 0.9209 | yes |
| robust-mahalanobis | 23.2273 | 2.1718 | 0.9209 | yes |
| robust-cusum | 25.8321 | 2.1718 | 0.9209 | yes |
| kalman-nis | 474.188 | 1.9465 | 0.5137 | yes |
| shorten-op-pf-surrogate | 3067.4 | 1.9465 | 0.5137 | yes |
| robust-linear | 43.8695 | 2.1718 | 0.9209 | yes |
| lstm | 15.4773 | 1.9465 | 0.5137 | yes |
| gru | 16.2442 | 1.9465 | 0.5137 | yes |
| tcn | 17.8222 | 1.9465 | 0.5137 | yes |
| transformer | 9.63846 | 1.9465 | 0.5137 | yes |
| sequential-autoencoder | 619.057 | 1.3368 | 0.7480 | yes |
| physics-ml-v1.0 | 1.01 | 0.2569 | 0.0000 | yes |

Generic baselines fit normal-state parameters only on development verified-quiet histories and use calibration verified-quiet histories only to select the final event threshold. Frozen detector 0.4 and physics-ML v1.0 retain their previously defined operating protocols and are not retuned in the comparison study.

## Orbit-regime F1

| Method | LEO | MEO | GEO | HEO | IGSO |
|---|---:|---:|---:|---:|---:|
| detector-0.4 | 0.381 | 0.286 | 0.667 | n/a | 0.000 |
| mean-motion-threshold | 0.237 | 0.333 | 0.000 | n/a | 0.000 |
| sma-window-shift | 0.214 | 0.333 | 0.615 | n/a | 0.000 |
| sgp4-rtn-consistency | 0.305 | 0.286 | 0.545 | n/a | 0.000 |
| multi-element-mad | 0.143 | 0.000 | 0.000 | n/a | 0.000 |
| robust-mahalanobis | 0.145 | 0.333 | 0.769 | n/a | 0.000 |
| robust-cusum | 0.113 | 0.667 | 0.364 | n/a | 0.000 |
| kalman-nis | 0.000 | 0.000 | 0.000 | n/a | 0.000 |
| shorten-op-pf-surrogate | 0.039 | 0.000 | 0.000 | n/a | 0.000 |
| robust-linear | 0.000 | 0.250 | 0.000 | n/a | 1.000 |
| lstm | 0.148 | 0.000 | 0.000 | n/a | 0.000 |
| gru | 0.113 | 0.000 | 0.000 | n/a | 0.000 |
| tcn | 0.113 | 0.000 | 0.000 | n/a | 0.000 |
| transformer | 0.148 | 0.000 | 0.000 | n/a | 0.000 |
| sequential-autoencoder | 0.111 | 0.000 | 0.667 | n/a | 0.000 |
| physics-ml-v1.0 | 0.000 | 0.000 | 0.000 | n/a | 0.000 |

The machine-readable artifact contains the full precision, recall, F1, false-event-rate, delay, abstention and confidence-interval blocks for every available regime. Small regime subsets can produce wide or degenerate bootstrap intervals and must be interpreted accordingly.

## Computational cost

| Method | Fit s | Calibration inference s | Rows/s | Parameters |
|---|---:|---:|---:|---:|
| detector-0.4 | 0.000 | 0.267 | 2526.1 | 0 |
| mean-motion-threshold | 0.000 | 0.001 | 1092113.5 | 2 |
| sma-window-shift | 0.001 | 0.001 | 571932.4 | 2 |
| sgp4-rtn-consistency | 0.001 | 0.001 | 477673.7 | 6 |
| multi-element-mad | 0.001 | 0.002 | 362080.0 | 10 |
| robust-mahalanobis | 0.003 | 0.004 | 152840.5 | 80 |
| robust-cusum | 0.003 | 0.005 | 147395.2 | 82 |
| kalman-nis | 0.032 | 0.010 | 70677.6 | 16 |
| shorten-op-pf-surrogate | 0.003 | 0.163 | 4144.6 | 20 |
| robust-linear | 0.238 | 0.027 | 25085.7 | 272 |
| lstm | 2.033 | 0.057 | 11762.3 | 18224 |
| gru | 2.277 | 0.071 | 9522.6 | 14000 |
| tcn | 0.350 | 0.053 | 12722.7 | 7664 |
| transformer | 0.802 | 0.060 | 11309.5 | 59568 |
| sequential-autoencoder | 0.670 | 0.208 | 3244.6 | 11016 |
| physics-ml-v1.0 | 5.888 | 0.843 | 800.0 | 59568 |

Primary inference timing covers the same 14 calibration cases for every method on the GitHub Actions CPU runner. Fit time is method-specific. Physics-ML fit cost includes its frozen leave-one-calibration-quiet-out reference fits. These timings are engineering measurements from this run, not hardware-independent complexity claims.

## Reproducibility boundary

The Shorten comparator is the explicitly labelled `shorten-op-pf-surrogate`. It preserves the reproducible optimal-proposal particle-filter structure, predictive-density scoring, ESS resampling and regularization strategy, but does not claim the paper-specific non-standard mean-element SGP4/Kozai-Brouwer implementation.

## Frozen artifact

Machine-readable result: `benchmark-results/comparison-v1-development-calibration.json`

Frozen SHA-256: `092df5a126d85fb7b58e5a0f682acdee1da39860359be943f102f26a986ddb43`

## Claim boundary

This is development/calibration comparison evidence only. No benchmark v1.0 confirmatory object was materialized or scored during this comparison. Positive-unlabelled event semantics remain in force. The subsequent [confirmatory evaluation](../confirmatory_v1/RESULTS-v1.0.md) is complete and failed its integration gate.
