# Integrity and selective-abstention v1.0

Integrity and selective-abstention research for the Satellite Maneuver Screening Workbench.

This directory is deliberately separate from the maneuver-detection method so integrity/security results can be studied as an independent paper track.

## What it contains

- `gate.py`; explicit case- and row-level selective-abstention policy with temporal-context reset at pre-score trust boundaries;
- `stressors.py`; deterministic clean + 12-condition integrity/security stress generator; confirmatory cases are refused;
- `run_stress.py`; development/calibration stress evaluation with separate ranking and held-out calibration views;
- `METHOD-v1.0.md`; threat/stress model, abstention semantics, metrics and claim boundary;
- `RESULTS-v1.0.md`; audited frozen integrity results and limitations.

Related permanent artifacts include `tools/export_integrity_v1_features.js`, `benchmark-results/integrity-v1-stress.json`, `tests/integrity_v1_test.py`, `tests/history_cache_integrity_test.py` and `tests/integrity_v1_freeze_test.py`.

## Audited result

The final audited run covers `234` case variants and `8439` exported causal rows. Clean development recall is `0.000000`, PU ranking is `0.866013`, and held-out Aqua coverage is `0.513889`. The deterministic false-maneuver attack does not exceed the frozen false-event budget. Same-object catalogue-regime discontinuities, unresolved duplicates and truncated histories are required by the frozen regression to fail closed in all tested cases.

Frozen result SHA-256: `fa76061583d2b48b34f44f2167b8f2b702ceadd1553dcef73a2499092c00f73b`.

## Boundary

This remains a deterministic development/calibration stress study. It is not a formal adversarial-robustness proof or operational cyber-security certification. Detector method 0.4 is unchanged. The confirmatory partition remained sealed during this development stage. It was subsequently consumed by the completed confirmatory evaluation, which failed its integration gate; see [the final results](../confirmatory_v1/RESULTS-v1.0.md). It may not be reused as untouched evidence for a tuned successor.
