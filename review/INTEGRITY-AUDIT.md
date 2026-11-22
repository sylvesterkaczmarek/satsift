# Integrity evaluation audit

## Disposition

The integrity study used the audited physics baseline, reviewed at code level, corrected, and re-evaluated from the sealed development/calibration input. Detector method 0.4 remains unchanged and confirmatory satellites were not accessed.

## Findings fixed

1. **Temporal contamination across abstention boundaries.** The old gate scored the full sequence before applying row-level integrity/OOD abstention, allowing an untrusted row to affect later model context. Prediction is now segmented at every pre-score trust boundary and regression-tested.
2. **Regime stress conflated with identity mismatch.** The old catalogue/regime stress also changed NORAD identity. The corrected stress preserves identity and forces a same-object orbital-regime discontinuity, which is independently exported and gated.
3. **Coverage metadata outside cache digest.** The old persistent digest protected records but did not bind syntactically valid coverage intervals. New writes include a full-store SHA-256 digest over version, source, NORAD identity, intervals and records; interval tampering is regression-tested fail-closed.
4. **Machine findings disagreed with prose.** The old machine result could report an empty `security_findings` list while prose documented vulnerabilities. The audited schema separates `security_gate_failures`, `observed_vulnerabilities` and their combined `security_findings`.

## Final experiment

- case variants: `234`;
- exported causal rows: `8439`;
- stress conditions excluding clean: `12`;
- clean development TP/FN: `0/36`;
- clean PU: `0.866013071895`;
- clean Aqua coverage: `0.513888888889`;
- clean false-event rate/object-month: `0.000000000000`;
- containment-gate failures: `[]`;
- observed vulnerabilities: `['legitimate corrected catalogue records reduce held-out support coverage; coverage 0.513889 -> 0.000000', 'adversarial maneuver suppression measurably degrades development event ranking; PU delta -0.016748']`.

Frozen result SHA-256: `fa76061583d2b48b34f44f2167b8f2b702ceadd1553dcef73a2499092c00f73b`.

## Audit conclusion

The integrity study is accepted as a completed research stage only under the stated deterministic development/calibration claim boundary. Its code now enforces the intended abstention semantics, the same-object regime stress is independent of identity mismatch, cache coverage metadata is integrity-bound, machine-readable findings reflect observed weaknesses, and the confirmatory partition remained sealed during this study. The later [confirmatory evaluation](../research/confirmatory_v1/RESULTS-v1.0.md) is complete and failed its integration gate.
