# Confirmatory evaluation audit

## Disposition

**Confirmatory evaluation scientific gate: FAIL.** The final integrated confirmatory report is frozen and independently recomputed from its stored case-level outputs.

No confirmatory metric was used to change an architecture, feature, threshold, calibration rule, event-matching rule, baseline definition or gate criterion.

## What was verified

- frozen code commit/tree, manifest hash, recipe hash, physics-result hash and comparison-result hash match the preconfirmatory record;
- the confirmatory partition contains exactly 12 unique objects, 41 truth intervals and two verified-quiet controls;
- confirmatory object IDs remain disjoint from all development/calibration object IDs;
- all 16 methods contain the same frozen confirmatory cases, labels and truth intervals;
- event-level summaries were independently recomputed from stored case-level predictions for every method;
- all 1000-replicate satellite-cluster confidence intervals were independently recomputed for every method;
- all orbit-regime statistical blocks were independently recomputed;
- the F1/recall ranking and frozen gate were independently recomputed;
- generic/ML/particle/filter frozen calibration metadata match the comparison study;
- the exact materialized raw-history payload and feature artifact are linked by SHA-256 provenance;
- the only post-access implementation correction was the confirmatory authorized-loader handoff; frozen scientific constants and scoring/gate functions did not change.

## Leakage and fairness review

No confirmatory object was used for architecture selection, training, threshold selection or calibration. Generic comparators train only on development verified-quiet references and reproduce their preconfirmatory calibration. Physics-ML v1.0 uses only preconfirmatory verified-quiet references. Detector 0.4 remains at its frozen operating point. Matching, positive-unlabelled scoring, abstention boundaries and bootstrap seed/replicate count are shared with the comparison study.

## Post-boundary software incident

The first full-data recovery exposed an execution-plumbing defect: the dedicated confirmatory exporter correctly marked the artifact as an authorized confirmatory one-shot, while `verify_confirmatory` called the ordinary selective-v1 loader that deliberately rejects all unsealed/confirmatory artifacts. The exception occurred before the integrated runner computed any of its 16 method summaries.

The repair replaced only that loader handoff with an explicit confirmatory parser that requires the expected schema, `confirmatory_sealed=false`, `confirmatory_confirmatory_authorized=true`, `one_shot=true`, confirmatory-only case metadata and confirmatory-only rows. The normal training loader remains unchanged and sealed. Regression tests cover authorized acceptance, missing authorization rejection and mixed-row rejection.

## One-shot procedural qualification

Detector 0.4 did execute in the failed orchestration immediately before the loader exception. Its temporary result was not inspected or used for adaptation and was lost with the failed workspace, so the successful integrated run had to regenerate it. Physics-ML v1.0 and the 14 generic/statistical comparators were not scored in that failed orchestration. The final integrated 16-method result was generated once after the execution-only repair. This is a procedural exception to a literal "every executable component only once" interpretation, but it does not create post-hoc tuning or information leakage.

## Statistical audit

The stored point estimates and 95% satellite-cluster bootstrap intervals exactly reproduce from the stored case-level predictions under the frozen seed `3404` and `1000` replicates. The gate recomputes exactly from the final result and remains FAIL. Confidence intervals were not used to weaken or reinterpret the point-estimate gate.

## Gate result

- FAIL: `at_least_one_true_positive`
- FAIL: `recall_strictly_greater_than_0_20`
- PASS: `positive_covered_quiet_exposure`
- PASS: `false_event_rate_at_most_1_per_covered_object_month`
- FAIL: `f1_strictly_greater_than_best_risk_compliant_principal_comparator`
- FAIL: `median_absolute_detection_delay_at_most_24_hours`

Physics-ML v1.0 has `0` true positives, `41` false negatives, recall `0`, F1 `0`, no verified-quiet false events, and mean case abstention about `0.9212`. It therefore does not earn integration.

## Reproducibility

- final result SHA-256: `f9857bd8f9ae2525b1827ce4fdfd108f7c5468c67142226922542d24b88c923c`
- exact materialized test-set SHA-256: `93877ae81f6481c1fe2be29983f9d35f92210b42e2ed41fa36fb23c9a2c632c9`
- confirmatory feature artifact SHA-256: `10f37c1464bb3c7c3070cc2f3dda57d21c8519598c3a3c767d8170058ee0ebb4`
- original evaluation-output SHA-256 before provenance attachment: `3d8e7293413dbd77fe32a72444d16276e2a28e9e5a1e28e78ebc6abea2d15768`
- per-case raw-record hashes: `research/confirmatory_v1/DATA-PROVENANCE-v1.0.json`
- independent audit verification: `research/confirmatory_v1/AUDIT-VERIFICATION-v1.0.json`

## Repository completion status

All temporary confirmatory orchestration and patch workflows have been removed. The permanent `confirmatory-freeze.yml` workflow and normal `ci.yml` are the only workflows retained. The frozen result, run lock, provenance and audit artifacts are permanent; no further confirmatory scientific execution is permitted.
