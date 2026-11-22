# Physics-ML research track

This directory is experimental research. It does not change detector method 0.4 or the public workbench.

## Current status

Physics-ML v0.1-v0.3 is a completed development cycle. Version 0.3 did not pass the integration gate: it reduced verified-quiet false-event burden on the old development benchmark but did not improve recall and materially increased matched-event delay. It remains a research artifact, not the final method.

The post-review selective-model implementation now lives in `research/selective_v1/`. That directory contains the catalogue-aware selective ML v1.0 method, four-backbone comparison, conservative support abstention, frozen model-selection report and ablation contract. The selective-v1 development stage did not access the confirmatory partition and is not integrated into detector 0.4. The subsequent [completed confirmatory evaluation](../confirmatory_v1/RESULTS-v1.0.md) consumed that partition and failed its integration gate.

The systematic novelty review through 14 August 2026 defined the historical v1.0 research claim boundary:

- `SYSTEMATIC-NOVELTY-REVIEW-v1.0.md`
- `REFERENCES-v1.0.bib`
- `PRIOR-ART.md`

## Revised research question

Can a **catalogue-aware selective event-screening framework** materially improve maneuver-screening risk and generalization from public GP histories when evaluation respects catalogue revisions, calibration support, positive-unlabelled interval evidence, verified-quiet exposure and unseen-satellite confirmation?

The question is deliberately architecture-agnostic.

## Novelty boundary after the systematic review

The final paper must not be framed as the first ML, deep-learning, LSTM, Transformer, autoencoder, SNN, physics-informed, hybrid physics-ML, conformal, sequential, or abstaining satellite maneuver detector. Prior art already covers those families.

The contribution to test is instead:

> **A catalogue-aware selective event-screening framework for public GP histories that separates catalogue revisions and unsupported operating regimes from maneuver evidence, calibrates event-level false-alert burden on satellite-disjoint verified-quiet exposure, and evaluates interval-censored public maneuver evidence under positive-unlabelled semantics with a pre-frozen unseen-satellite confirmatory set.**

Central claim candidates:

1. deterministic catalogue revision/supersession provenance, audit and abstention;
2. calibration-support/OOD abstention evaluated explicitly through coverage and risk;
3. satellite-level event operating-point calibration on verified-quiet exposure;
4. positive-unlabelled interval-censored scoring with scheduled/executed evidence tiers;
5. satellite-disjoint development/calibration/confirmatory partitions with the final partition frozen before method tuning;
6. satellite-cluster uncertainty estimates and object-month false-event burden.

Common-epoch SGP4 RTN features, robust conditional nominal models, a temporal ML backbone, sequential evidence accumulation and physical corroboration remain useful **mechanisms**, but are not headline novelty.

## Statistical wording

Use **risk-calibrated** rather than **risk-controlled** unless a future method includes a formal dependence-aware theorem whose assumptions are defensible for irregular, autocorrelated GP histories.

The v0.3 empirical p-value/e-value implementation does not by itself provide an anytime false-event guarantee.

## Design constraints for v1

- Do not inspect benchmark v1.0 confirmatory satellites during architecture, feature, threshold or abstention-rule selection.
- Compare simple statistical and filter baselines as well as open BiLSTM, Transformer and forecast-residual baselines.
- Treat the temporal backbone as a replaceable component and include architecture-swap ablations.
- Preserve benchmark v1.0 positive-unlabelled semantics; never turn unlabeled time into negative ground truth.
- Report abstention and risk/coverage explicitly.
- Calibrate false-alert burden at the **event and satellite** level, not only pointwise.
- Keep physical corroboration as an auditable support constraint and ablate it.

The mandatory baselines and ablations are listed in `SYSTEMATIC-NOVELTY-REVIEW-v1.0.md` and, for the implemented v1 method, `../selective_v1/ABLATIONS-v1.0.md`.

## Existing v0.3 files

- `detector.py` and `detector_v03.py`; experimental reference implementations.
- `METHOD.md`; v0.3 mathematical definition and validity boundary.
- `RESULTS-v0.3.md`; frozen v0.3 evaluation/disposition.
- `evaluate.py`; event matching and satellite-cluster bootstrap evaluation.
- `test_detector.py`; deterministic experimental tests.

## Integration rule

The v1.0 confirmatory evaluation failed, so the learned method does not replace detector 0.4. A successor requires a new declared protocol, frozen development/calibration decisions and a genuinely new satellite-level holdout.

If the selective catalogue/evidence framework does not materially change risk estimates or held-out performance, the paper should be reframed primarily as a benchmark/evaluation-methodology contribution rather than overstating algorithmic novelty.
