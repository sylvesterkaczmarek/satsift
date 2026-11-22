# Selective ML v1.0 ablation contract

## Purpose

This file records the ablations declared during development. It preserves the original requirements and completed-work boundary. It does not assert that every planned ablation was completed. The subsequent confirmatory evaluation failed, and these plans do not authorise reuse of that partition as untouched evidence.

The confirmatory partition must not be used to choose, tune or interpret any ablation.

## Completed selective-model work

### A1. Backbone family

Compared under one development-only selection contract:

- robust conditional linear;
- GRU;
- causal TCN;
- causal Transformer.

Result: Transformer ranked highest on the PU event-versus-verified-quiet statistic, but all candidates had zero strict-threshold event recall. This architecture ablation is frozen in `benchmark-results/selective-v1-model-selection.json`.

### A2. Conservative support-satellite requirement

An exploratory two-reference-satellite final policy allowed GEO but produced a pathological cross-satellite support-distance threshold. The policy was rejected before finalization.

Final v1.0 requires at least three independent verified-quiet reference satellites per regime. Under benchmark v1.0 this qualifies LEO only.

## Historically declared confirmatory prerequisites

### A3. Catalogue uncertainty/provenance channels

Compare the frozen model with and without:

- creation-lag context;
- element-set/GP-ID availability;
- catalogue supersession fraction;
- epoch-precision context.

All other training/calibration choices must remain fixed.

Purpose: determine whether explicit catalogue provenance contributes beyond ordinary orbital/sampling context.

### A4. Calibration-support abstention

Compare:

1. frozen same-regime support abstention;
2. no support abstention, while retaining the same model and event threshold calibration procedure.

Report both detection metrics and coverage. Abstention must never be counted as a correct negative.

Purpose: quantify the selective-prediction contribution and its cost.

### A5. Independent-reference requirement

Within development/calibration only, report the sensitivity of support coverage to the minimum independent reference-object rule. The final method remains fixed at three unless a preregistered replacement version is created.

Purpose: expose how much apparent support can be created by many rows from too few satellites.

### A6. Heavy-tail objective

Compare the fixed Student-t-shaped conditional objective/nonconformity with a Gaussian location/scale alternative using the same selected backbone and feature/context inputs.

Purpose: test whether heavy-tail handling is materially useful for public GP residuals.

### A7. Physics corroboration

Compare event formation with and without the transparent RTN/orbital-element physical-support gate.

Purpose: quantify whether the gate reduces false events or only suppresses recall. It is not a novelty claim by itself.

### A8. Catalogue-revision resolution

Compare the frozen revision-safe preprocessing with a diagnostic variant that does not use catalogue-revision provenance/resolution before feature extraction.

The diagnostic must not overwrite or replace detector 0.4 preprocessing in the repository.

Purpose: quantify the effect of catalogue revision artifacts on maneuver evidence.

### A9. Context conditioning

Compare the selected conditional model against:

- an unconditional robust nominal distribution;
- orbit-only conditioning;
- orbit + sampling interval;
- full frozen context.

Purpose: isolate the value of object/sampling/catalogue conditioning.

### A10. Sequential evidence

After the sequential layer is implemented, compare:

- frozen pointwise selective-model surprise thresholding;
- the frozen sequential accumulation rule.

Both must use identical nominal scores, support abstention and physical corroboration unless the sequential method definition explicitly requires otherwise.

Purpose: determine whether temporal accumulation recovers event evidence at the same empirical quiet-risk budget.

### A11. Event grouping

Compare the frozen two-evaluated-point grouping rule with pointwise alerts and one preregistered alternative gap.

Purpose: separate better event accounting from better underlying detection.

### A12. Positive-unlabelled semantics

The valid benchmark analysis remains positive-unlabelled. A conventional diagnostic that incorrectly treats unlabelled event-case time as negative may be shown only to demonstrate bias; it must not be used for training, calibration, model selection or headline metrics.

Purpose: demonstrate why the evidence semantics matter without contaminating the method.

### A13. Split leakage diagnostic

A random-window split may be run only as a diagnostic comparison against the frozen satellite-disjoint split. It must be labelled leakage-prone and cannot drive method selection.

Purpose: quantify how much apparent performance can arise from seeing the same satellite in training and evaluation.

### A14. Scheduled evidence

Report results with scheduled-only GPS NANU / Galileo NAGU evidence removed from scoring, while keeping the main frozen evidence-tier analysis.

Purpose: show sensitivity to the distinction between scheduled and executed/operator-confirmed evidence.

## Reporting rule

Every ablation must report:

- satellites and regimes included;
- scorable truth intervals;
- covered verified-quiet object-months;
- recall;
- false events per covered verified-quiet object-month;
- abstention/coverage;
- detection delay when matches exist;
- satellite-cluster uncertainty intervals when sample size permits.

The development protocol prohibited ablations from inspecting confirmatory data before the final method and protocol were frozen. The completed evaluation has now consumed that partition; new confirmatory claims need a new holdout.
