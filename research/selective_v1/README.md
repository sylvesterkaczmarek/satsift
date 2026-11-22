# Selective ML detector v1.0

## Status

This directory records the selective-model research stage developed after the systematic novelty review and frozen publication benchmark v1.0.

It does **not** replace detector method 0.4 and is not integrated into the public workbench.

The confirmatory partition remained sealed during this development stage. It was subsequently consumed by the completed confirmatory evaluation, which failed its integration gate; see [the final results](../confirmatory_v1/RESULTS-v1.0.md). It may not be reused as untouched evidence for a tuned successor.

## Research contribution

The intended contribution is the selective decision and evaluation framework, not the neural architecture:

- catalogue-aware causal features from the validated detector 0.4 SGP4/RTN pipeline;
- explicit calibration-support abstention rather than extrapolation;
- empirical event-level false-alert calibration on covered verified-quiet exposure;
- positive-unlabelled interval-censored evaluation;
- satellite-disjoint model selection and a sealed confirmatory partition;
- evidence-quality and catalogue-uncertainty channels carried into the decision process.

No formal risk-control guarantee is claimed. The current method is **empirically risk-calibrated**.

## Frozen selective-model result

Four conditional nominal models were compared under the same development-only selection rule:

1. robust conditional linear model;
2. compact GRU;
3. causal TCN;
4. compact causal Transformer.

The Transformer ranked highest on the development-only positive-unlabelled event-versus-verified-quiet ranking statistic and was selected as the backbone for the subsequent sequential and physics stages.

That selection is **relative, not a performance success**. The selected Transformer achieved:

- development PU event-versus-quiet mean percentile: `0.480625`;
- strict empirically calibrated development event recall: `0.0`;
- development event-row abstention rate: `0.17407407407407405`;
- 59,568 trainable parameters.

All four candidate models had zero strict-threshold event recall in the supported development regime. The selective-model stage did not pass an integration/performance gate. The subsequent sequential and physics stages retained this failed development result.

The exact frozen comparison is in `benchmark-results/selective-v1-model-selection.json` and the interpretation is in `MODEL-SELECTION-v1.0.md`.

## Final support scope

A final v1.0 regime requires at least **three independent verified-quiet reference satellites**. The available v1.0 nominal references are:

- LEO: 4;
- GEO: 2;
- MEO: 1;
- HEO: 1.

Consequently, the selective-model stage froze **LEO as the only qualified regime**. GEO, MEO and HEO abstain. This is intentional. A large number of rows from one or two spacecraft is not treated as equivalent to independent cross-satellite support.

The final LEO support-distance threshold is `1.2019241655473716` at the configured 98% calibration-support target.

## Empirical event calibration

After architecture selection, the LEO event threshold was calibrated on covered calibration verified-quiet exposure only:

- threshold: `6.501427015384656`;
- covered verified-quiet exposure: `0.4665623499247091` object-month;
- observed false events: `0`;
- observed false events per covered object-month: `0.0`;
- empirical budget used for calibration: at most `1.0` false event per covered object-month.

This exposure is small and comes from one calibration LEO quiet satellite, Aqua. It is not sufficient for a strong population-level false-alarm claim. It is recorded as calibration evidence only.

The historical false-event denominator multiplies each case duration by its fraction of scored rows. This approximates covered time and can be biased by irregular sampling; see [known limitations](../../KNOWN-ISSUES.md).

## Files

- `core.py`: robust statistics, same-regime support model, heavy-tail surprise, physical support, event grouping and matching.
- `models.py`: robust-linear, GRU, causal TCN and causal Transformer conditional location/scale models.
- `detector.py`: final selective inference wrapper and three-reference-satellite support requirement.
- `train_compare.py`: sealed development-only model selection and calibration-quiet risk calibration.
- `test_selective_v1.py`: deterministic tests that do not require PyTorch.
- `METHOD-v1.0.md`: mathematical/algorithmic contract.
- `MODEL-SELECTION-v1.0.md`: frozen candidate comparison and disposition.
- `ABLATIONS-v1.0.md`: required ablations before any confirmatory claim.

Feature export is performed by `tools/export_selective_v1_features.js`. The exporter hard-fails if a confirmatory case is supplied.

## Integration rule

Selective ML v1.0 is not integrated into `app-3.4.js` and does not replace detector 0.4. Development tools continue to reject confirmatory data.

The completed v1.0 confirmatory evaluation failed. A successor requires a new declared protocol, frozen operating rules and a new satellite-level holdout before making confirmatory claims.
