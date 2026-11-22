# Physics-ML v0.3 results

## Status

Experimental research completed on development benchmark v0.3. The method is **not approved for integration into detector method 0.4**.

Benchmark v0.3 is a development benchmark. Its test split was inspected during the v0.1-v0.3 research cycle and therefore must not be presented as a final confirmatory holdout for a future tuned model.

## Frozen comparison

Held-out v0.3 test split contains six cases, five documented truth events and verified-quiet negative coverage. False positives are counted only inside verified-quiet windows; predictions elsewhere in event-evidence cases are unscored rather than silently labelled false.

| Metric | Detector 0.4 | Physics-ML v0.3 |
|---|---:|---:|
| True positives | 1 | 1 |
| False negatives | 4 | 4 |
| Verified-quiet false positives | 8 | 4 |
| Scorable precision | 0.111 | 0.200 |
| Recall | 0.200 | 0.200 |
| Scorable F1 | 0.143 | 0.200 |
| False events / verified-quiet object-month | 12.750 | 6.375 |
| Median detection delay | 20.262 h | 96.095 h |
| Abstention rate | 0.500 | 0.333 |

The satellite-cluster bootstrap intervals remain wide because this development benchmark is small. The exact machine-readable results and bootstrap intervals are committed under `benchmark-results/`.

## Interpretation

Physics-ML v0.3 demonstrates one useful effect: the physics-conditioned nominal model and sequential evidence reduce false alerts on the verified-quiet windows relative to detector 0.4. However, it does not improve recall and it delays the only matched event substantially. The improvement is therefore insufficient to justify integration.

The v0.1 and v0.2 attempts are retained because they exposed two important failure modes: a global cross-regime context model caused pervasive out-of-support abstention, and profile-specific models trained on a single quiet spacecraft produced degenerate context scales. Version 0.3 added physically bounded context scales, improving coverage but not event sensitivity enough.

## Integration gate

**FAIL.** Do not modify the public workbench or detector method 0.4 to use physics-ML v0.3.

A future model must be evaluated on a new, untouched confirmatory benchmark after its architecture and settings are frozen. It should demonstrate materially better event recall and false-event burden without unacceptable delay or loss of selective reliability.

## Reproducibility

Relevant files:

- `research/physics_ml/detector.py`
- `research/physics_ml/detector_v03.py`
- `research/physics_ml/run_benchmark.py`
- `research/physics_ml/evaluate.py`
- `benchmark-results/baseline-v0.4-test-evaluation.json`
- `benchmark-results/physics-ml-v0.3-test-evaluation.json`
- `benchmark-results/baseline-v0.4-sampling-stress-v0.3.json`

No operational performance claim follows from these development results.
