# Sequential evidence v1.0

This directory implements the sequential-evidence layer on top of selective ML v1.0.

It does **not** change detector method 0.4 or the public workbench. The confirmatory partition remained sealed during this development stage. It was subsequently consumed by the completed confirmatory evaluation, which failed its integration gate; see [the final results](../confirmatory_v1/RESULTS-v1.0.md). It may not be reused as untouched evidence for a tuned successor.

## Components

- `formal.py`; theorem-qualified Bernoulli likelihood-ratio e-process and unknown-change-start mixture.
- `operational.py`; empirical false-events-per-covered-object-month calibration and repeated-event interface.
- `run_development.py`; development/calibration experiment using only non-confirmatory benchmark data.
- `simulate_null.py`; valid-null and deliberate assumption-violation simulations.
- `test_sequential_v1.py`; deterministic mathematical and operational regressions.
- `METHOD-v1.0.md`; mathematical definition, assumptions, calibration and claim boundary.

## Statistical status

Two statements are intentionally kept separate:

1. **Conditional theorem:** if the monitored binary exceedance process satisfies `Pr(X_t=1 | F_{t-1}) <= q0` for every monitored update, the implemented mixture wealth is a nonnegative supermartingale and Ville's inequality supplies an anytime-valid crossing bound.
2. **Real GP histories:** `q0` is estimated empirically from verified-quiet satellites and the required conditional bound has not been proved. Real-data operation is therefore described only as **empirically risk-calibrated sequential screening**.

The normal control is a target false-event burden per **covered object-month**, not a generic alpha slider.

## Conformal/e-process disposition

Conformal test martingales and the 2026 fixed-reference conditional conformal test-martingale construction were reviewed. They are not used to claim real-data validity because public GP residual scores are irregular and temporally dependent, and this repository has not established the required exchangeability/conditional-superuniform assumptions.

The Bernoulli e-process was chosen because its formal premise is explicit and testable as a mathematical assumption rather than hidden inside a transformed score.

## Integration gate

The sequential layer remains research-only. Its historical integration requirements were:

- development/calibration event performance materially improves over the pointwise selective-model result and detector 0.4 at an acceptable covered false-event rate;
- failure simulations and calibration sensitivity are reported;
- the operating point is frozen before confirmatory access;
- a single confirmatory evaluation after the complete method and comparison protocol were frozen.

The later confirmatory evaluation failed. Any successor needs a new holdout; this list is retained as the historical decision rule.
