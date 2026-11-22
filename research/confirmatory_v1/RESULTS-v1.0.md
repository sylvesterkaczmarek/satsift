# Confirmatory evaluation v1.0 results

## Status

**confirmatory gate: FAIL.**

This is the single frozen benchmark v1.0 confirmatory evaluation. The frozen 12-satellite confirmatory evaluation is complete. The result is retained as a negative result. No threshold, architecture, feature, calibration rule, event-matching rule, baseline definition or gate criterion was changed in response to confirmatory performance.

## Freeze and provenance

- frozen code commit: `2c394d4d9362c65560a2a08827b4e1a96f23ed87`
- frozen code tree: `b89b6ead78824e31ebdb41d4cf1fe1569f6ab1a1`
- final evaluation trigger commit: `5174f62bcb1da8241594f8fc575a29ca83ef76d7`
- GitHub Actions run: `31887104065`
- benchmark manifest SHA-256: `a0d72bd15ea579ec2373a5a0cd96c1cf0790bd361b15803f722c740b5e6f7d88`
- benchmark recipe SHA-256: `19512dd380cbd9a56c5cccbf376110d20d5dd8eb0f65f90dae5552d424f9a2c5`
- exact materialized confirmatory dataset SHA-256: `93877ae81f6481c1fe2be29983f9d35f92210b42e2ed41fa36fb23c9a2c632c9`
- exact confirmatory feature artifact SHA-256: `10f37c1464bb3c7c3070cc2f3dda57d21c8519598c3a3c767d8170058ee0ebb4`
- original evaluation output SHA-256 before provenance attachment: `3d8e7293413dbd77fe32a72444d16276e2a28e9e5a1e28e78ebc6abea2d15768`
- final confirmatory result SHA-256: `f9857bd8f9ae2525b1827ce4fdfd108f7c5468c67142226922542d24b88c923c`

Per-case record hashes and frozen windows are in `research/confirmatory_v1/DATA-PROVENANCE-v1.0.json`.

## Confirmatory scope

- satellite-disjoint objects: `12`
- documented truth intervals: `41`
- verified-quiet controls: `2`
- methods: `16`
- matching tolerance: `24` hours
- satellite-cluster bootstrap replicates: `1000`
- bootstrap seed: `3404`

## Complete event-level metrics

Brackets are satellite-cluster 95% bootstrap confidence intervals. False positives are counted only on verified-quiet exposure under the frozen positive-unlabelled protocol.

| Method | TP | FP | FN | Precision | Recall | F1 | False events/object-month | Median abs delay h | Abstention |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| detector-0.4 | 15 | 1 | 26 | 0.9375 [0.7500, 1.0000] | 0.3659 [0.2340, 0.5116] | 0.5263 [0.3703, 0.6574] | 1.0616 [0.0000, 2.1760] | 9.59 [8.2605, 14.5148] | 0.2500 [0.0000, 0.5000] |
| mean-motion-threshold | 12 | 3 | 29 | 0.8000 [0.4000, 1.0000] | 0.2927 [0.1515, 0.4483] | 0.4286 [0.2352, 0.5754] | 3.1847 [0.0000, 6.5281] | 21.40 [16.6453, 62.7906] | 0.0000 [0.0000, 0.0000] |
| sma-window-shift | 8 | 1 | 33 | 0.8889 [0.5000, 1.0000] | 0.1951 [0.0667, 0.3263] | 0.3200 [0.1250, 0.4815] | 1.3125 [0.0000, 2.9014] | 33.02 [18.0121, 131.4118] | 0.2951 [0.1336, 0.5041] |
| sgp4-rtn-consistency | 17 | 1 | 24 | 0.9444 [0.7855, 1.0000] | 0.4146 [0.2500, 0.6667] | 0.5763 [0.3846, 0.7778] | 1.0616 [0.0000, 2.1760] | 33.85 [21.3043, 88.0543] | 0.0000 [0.0000, 0.0000] |
| multi-element-mad | 9 | 1 | 32 | 0.9000 [0.6000, 1.0000] | 0.2195 [0.1034, 0.3336] | 0.3529 [0.1777, 0.4889] | 1.0616 [0.0000, 2.1760] | 7.73 [3.3604, 62.7906] | 0.0000 [0.0000, 0.0000] |
| robust-mahalanobis | 13 | 1 | 28 | 0.9286 [0.7500, 1.0000] | 0.3171 [0.2115, 0.5173] | 0.4727 [0.3437, 0.6512] | 1.0616 [0.0000, 2.1760] | 12.77 [7.0324, 62.8240] | 0.0000 [0.0000, 0.0000] |
| robust-cusum | 10 | 1 | 31 | 0.9091 [0.7000, 1.0000] | 0.2439 [0.1594, 0.4092] | 0.3846 [0.2716, 0.5714] | 1.0616 [0.0000, 2.1760] | 321.97 [62.8240, 515.4989] | 0.0000 [0.0000, 0.0000] |
| kalman-nis | 2 | 1 | 39 | 0.6667 [0.0000, 1.0000] | 0.0488 [0.0000, 0.1739] | 0.0909 [0.0000, 0.2857] | 1.1038 [0.0000, 2.2905] | 66.76 [44.3041, 89.2119] | 0.0632 [0.0267, 0.1129] |
| shorten-op-pf-surrogate | 3 | 2 | 38 | 0.6000 [0.1111, 1.0000] | 0.0732 [0.0000, 0.2000] | 0.1304 [0.0000, 0.3078] | 2.2075 [0.0000, 4.5811] | 18.80 [10.6684, 44.3041] | 0.0632 [0.0267, 0.1129] |
| robust-linear | 0 | 0 | 41 | n/a [n/a, n/a] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | n/a [n/a, n/a] | 0.0000 [0.0000, 0.0000] |
| lstm | 5 | 1 | 36 | 0.8333 [0.3333, 1.0000] | 0.1220 [0.0270, 0.2572] | 0.2128 [0.0513, 0.4000] | 1.1038 [0.0000, 2.2905] | 14.51 [5.4441, 62.7906] | 0.0632 [0.0267, 0.1129] |
| gru | 5 | 1 | 36 | 0.8333 [0.3333, 1.0000] | 0.1220 [0.0270, 0.2572] | 0.2128 [0.0513, 0.4000] | 1.1038 [0.0000, 2.2905] | 14.51 [5.4441, 62.7906] | 0.0632 [0.0267, 0.1129] |
| tcn | 4 | 1 | 37 | 0.8000 [0.3333, 1.0000] | 0.0976 [0.0238, 0.2175] | 0.1739 [0.0444, 0.3448] | 1.1038 [0.0000, 2.2905] | 12.14 [5.0634, 62.7906] | 0.0632 [0.0267, 0.1129] |
| transformer | 7 | 1 | 34 | 0.8750 [0.5542, 1.0000] | 0.1707 [0.0690, 0.2895] | 0.2857 [0.1250, 0.4376] | 1.1038 [0.0000, 2.2905] | 14.51 [9.4745, 118.4179] | 0.0632 [0.0267, 0.1129] |
| sequential-autoencoder | 9 | 1 | 32 | 0.9000 [0.6250, 1.0000] | 0.2195 [0.1316, 0.3103] | 0.3529 [0.2222, 0.4615] | 1.4495 [0.0000, 3.3477] | 11.16 [3.7419, 81.3118] | 0.3465 [0.1870, 0.5504] |
| physics-ml-v1.0 | 0 | 0 | 41 | n/a [n/a, n/a] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | n/a [n/a, n/a] | 0.9212 [0.7635, 1.0000] |

## Frozen calibration and computational cost

| Method | Frozen operating point | Calibration quiet rate | Calibration quiet exposure | Fit s | Confirmatory inference s | Parameters | Rows/s |
|---|---|---:|---:|---:|---:|---:|---:|
| detector-0.4 | frozen detector 0.4 operating point | n/a | n/a | 0.000 | 0.212 | 0 | n/a |
| mean-motion-threshold | event threshold 0.71727662 | 0.9209 | 2.1718 | 0.000 | 0.000 | 2 | 1170799.1 |
| sma-window-shift | event threshold 0.84325387 | 0.6709 | 1.4906 | 0.000 | 0.001 | 2 | 570172.0 |
| sgp4-rtn-consistency | event threshold 4.3970146 | 0.9209 | 2.1718 | 0.000 | 0.001 | 6 | 440792.1 |
| multi-element-mad | event threshold 47.735381 | 0.9209 | 2.1718 | 0.001 | 0.001 | 10 | 336196.5 |
| robust-mahalanobis | event threshold 23.227325 | 0.9209 | 2.1718 | 0.003 | 0.003 | 80 | 151576.8 |
| robust-cusum | event threshold 25.832127 | 0.9209 | 2.1718 | 0.003 | 0.003 | 82 | 144167.7 |
| kalman-nis | event threshold 474.18781 | 0.5137 | 1.9465 | 0.033 | 0.007 | 16 | 67322.1 |
| shorten-op-pf-surrogate | event threshold 3067.4049 | 0.5137 | 1.9465 | 0.003 | 0.108 | 20 | 4323.3 |
| robust-linear | event threshold 43.86949 | 0.9209 | 2.1718 | 0.244 | 0.019 | 272 | 25147.7 |
| lstm | event threshold 15.477285 | 0.5137 | 1.9465 | 2.059 | 0.041 | 18224 | 11341.5 |
| gru | event threshold 16.244202 | 0.5137 | 1.9465 | 2.384 | 0.050 | 14000 | 9346.7 |
| tcn | event threshold 17.822202 | 0.5137 | 1.9465 | 0.351 | 0.039 | 7664 | 12084.1 |
| transformer | event threshold 9.6384551 | 0.5137 | 1.9465 | 0.839 | 0.044 | 59568 | 10568.5 |
| sequential-autoencoder | event threshold 619.05719 | 0.7480 | 1.3368 | 0.541 | 0.139 | 11016 | 3359.7 |
| physics-ml-v1.0 | base_score_threshold=17.822733, support_threshold=1.2019242, q0=0.24444444, wealth_threshold=1.01 | 0.0000 | 0.2569 | 1.296 | 0.546 | 59568 | 857.1 |

Timing is implementation/runtime evidence from the frozen CPU workflow, not a hardware-normalized performance claim.

## Physics-ML v1.0 result

- true positives: `0`
- false positives on verified-quiet controls: `0`
- false negatives: `41`
- recall: `0.0000`
- F1: `0.0000`
- covered verified-quiet exposure: `0.4564` object-month
- false events per covered object-month: `0.0000`
- mean case abstention: `0.9212`
- median absolute first-alarm delay: `n/a` hours

The method missed all `41` documented confirmatory intervals. Its zero false-event count does not compensate for zero recall and very high abstention.

## Frozen integration/publication gate

- FAIL: `at_least_one_true_positive`
- FAIL: `recall_strictly_greater_than_0_20`
- PASS: `positive_covered_quiet_exposure`
- PASS: `false_event_rate_at_most_1_per_covered_object_month`
- FAIL: `f1_strictly_greater_than_best_risk_compliant_principal_comparator`
- FAIL: `median_absolute_detection_delay_at_most_24_hours`

Best point-estimate risk-compliant principal comparator: `robust-linear` with F1 `0.0000` and false-event rate `0.0000`.

**Overall gate: FAIL.**

Confidence intervals are uncertainty reporting only and do not modify the predeclared point-estimate gate.

## Confirmatory ranking by F1 then recall

- 1. `sgp4-rtn-consistency`: F1 0.5763, recall 0.4146, false events/object-month 1.0616.
- 2. `detector-0.4`: F1 0.5263, recall 0.3659, false events/object-month 1.0616.
- 3. `robust-mahalanobis`: F1 0.4727, recall 0.3171, false events/object-month 1.0616.
- 4. `mean-motion-threshold`: F1 0.4286, recall 0.2927, false events/object-month 3.1847.
- 5. `robust-cusum`: F1 0.3846, recall 0.2439, false events/object-month 1.0616.
- 6. `multi-element-mad`: F1 0.3529, recall 0.2195, false events/object-month 1.0616.
- 7. `sequential-autoencoder`: F1 0.3529, recall 0.2195, false events/object-month 1.4495.
- 8. `sma-window-shift`: F1 0.3200, recall 0.1951, false events/object-month 1.3125.
- 9. `transformer`: F1 0.2857, recall 0.1707, false events/object-month 1.1038.
- 10. `lstm`: F1 0.2128, recall 0.1220, false events/object-month 1.1038.
- 11. `gru`: F1 0.2128, recall 0.1220, false events/object-month 1.1038.
- 12. `tcn`: F1 0.1739, recall 0.0976, false events/object-month 1.1038.
- 13. `shorten-op-pf-surrogate`: F1 0.1304, recall 0.0732, false events/object-month 2.2075.
- 14. `kalman-nis`: F1 0.0909, recall 0.0488, false events/object-month 1.1038.
- 15. `robust-linear`: F1 0.0000, recall 0.0000, false events/object-month 0.0000.
- 16. `physics-ml-v1.0`: F1 0.0000, recall 0.0000, false events/object-month 0.0000.

The raw F1 leader is `sgp4-rtn-consistency` (F1 0.5763), followed by detector 0.4 (F1 0.5263). Both have confirmatory quiet false-event point estimates above the frozen 1.0/object-month budget.

## Orbit-regime F1

| Method | LEO | MEO | GEO | HEO | IGSO |
|---|---:|---:|---:|---:|---:|
| detector-0.4 | 0.526 | 0.333 | 0.800 | 0.000 | n/a |
| mean-motion-threshold | 0.486 | 0.333 | 0.000 | 0.571 | n/a |
| sma-window-shift | 0.303 | 0.000 | 0.667 | 0.000 | n/a |
| sgp4-rtn-consistency | 0.444 | 0.333 | 1.000 | 0.800 | n/a |
| multi-element-mad | 0.400 | 0.000 | 0.000 | 0.800 | n/a |
| robust-mahalanobis | 0.353 | 0.333 | 0.800 | 0.800 | n/a |
| robust-cusum | 0.250 | 0.571 | 0.500 | 0.800 | n/a |
| kalman-nis | 0.000 | 0.000 | 0.000 | 0.800 | n/a |
| shorten-op-pf-surrogate | 0.069 | 0.000 | 0.000 | 0.667 | n/a |
| robust-linear | 0.000 | 0.000 | 0.000 | 0.000 | n/a |
| lstm | 0.194 | 0.000 | 0.000 | 0.800 | n/a |
| gru | 0.194 | 0.000 | 0.000 | 0.800 | n/a |
| tcn | 0.133 | 0.000 | 0.000 | 0.800 | n/a |
| transformer | 0.303 | 0.000 | 0.000 | 0.800 | n/a |
| sequential-autoencoder | 0.353 | 0.000 | 0.667 | 0.000 | n/a |
| physics-ml-v1.0 | 0.000 | 0.000 | 0.000 | 0.000 | n/a |

Full per-regime summaries and satellite-cluster confidence intervals remain in the machine-readable frozen result. Small regime subsets have wide or degenerate uncertainty.

## Execution integrity note

Three pre-scoring materialization attempts were interrupted by HTTP 429 before any confirmatory method result was generated. A transport-only recovery subsequently materialized all 12 frozen windows. In that recovery, detector 0.4 executed and the feature artifact was produced, but the integrated runner failed immediately because it incorrectly sent the explicitly authorized confirmatory feature artifact through the development-only sealed loader. No integrated method metric was produced or inspected at that point.

The loader handoff was corrected without changing features, models, thresholds, calibration, matching, bootstrap or gate logic. The successful integrated run then evaluated all 16 frozen methods. Detector 0.4 was necessarily re-executed because its first temporary artifact disappeared with the failed runner workspace. That discarded detector-only execution was not inspected or used for tuning and cannot be byte-compared retrospectively. Physics-ML v1.0 and the 14 generic/statistical comparators were scored only in the successful integrated evaluation. This procedural exception is retained in the audit rather than hidden.

## Claim boundary

The negative result is final for physics-ML v1.0 on benchmark v1.0 confirmatory data. The confirmatory partition may not be used to rescue or retune this method and then be presented as untouched evidence. Detector 0.4 remains the current public baseline unless a separate future research cycle defines a new method and a genuinely new holdout.

