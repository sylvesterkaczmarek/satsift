# Integrity and selective-abstention v1.0 results

## Disposition

**Integrity evaluation is complete after code audit and corrected re-evaluation.**

The trustworthy-AI / **AI-security research track** remains separate from detector method 0.4 and from the maneuver-detection paper track. The confirmatory partition was not materialized, inspected or scored during this integrity study.

## Audit corrections

The post-implementation audit found and corrected four substantive issues:

1. pre-score integrity, calibration-support and OOD abstentions now reset temporal model context, so an untrusted row cannot influence later trusted predictions through hidden state or previous-observation features;
2. catalogue-regime stress now changes orbital regime while keeping catalogue identity fixed, and the exporter/gate detect same-object regime discontinuities explicitly;
3. persistent history cache integrity now binds coverage intervals and identity metadata together with ordered records through a full-store SHA-256 digest, while retaining read compatibility for earlier records-only and legacy cache stores;
4. machine-readable findings now distinguish containment-gate failures from observed vulnerabilities instead of reporting an empty findings list while documenting weaknesses in prose.

## Re-evaluated scope

- non-confirmatory clean cases: `18`;
- deterministic conditions including clean: `13`;
- case variants: `234`;
- exported causal rows: `8439`;
- development maneuver-evidence cases: `4`;
- documented development intervals: `36`.

## Clean audited anchor

- TP / FN: `0 / 36`;
- recall: `0.000000`;
- PU sequential-wealth mean percentile: `0.866013071895`;
- row abstention fraction: `0.722222222222`;
- held-out Aqua coverage: `0.513888888889`;
- covered verified-quiet exposure: `0.250185607931 object-month`;
- frozen false events: `0`;
- frozen false events per covered object-month: `0.000000000000`.

Physics evaluation's numerical anchor is retained in the machine-readable result for reference. Integrity evaluation's audited clean metrics are allowed to differ because the corrected integrity layer now treats pre-score abstention as a temporal-context reset.

## Stress matrix

| Condition | Hard case abstention | Development row abstention | PU | Aqua coverage | Aqua false-event rate / object-month |
|---|---:|---:|---:|---:|---:|
| clean | 0.2222 | 0.7222 | 0.8660 | 0.5139 | 0.0000 |
| adversarial_false_maneuver | 0.2222 | 0.7222 | 0.8660 | 0.5000 | 0.0000 |
| adversarial_maneuver_suppression | 0.2222 | 0.6407 | 0.8493 | 0.5139 | 0.0000 |
| catalogue_regime_change | 1.0000 | 1.0000 | n/a | 0.0000 | n/a |
| corrected_duplicate | 0.2222 | 0.7222 | 0.8660 | 0.0000 | n/a |
| corrupted_history | 0.7222 | 0.7309 | 0.8564 | 0.5152 | 0.0000 |
| deletion | 0.3333 | 0.7178 | 0.9223 | 0.5000 | 0.0000 |
| insertion | 0.3333 | 0.7080 | 0.8713 | 0.5205 | 0.0000 |
| irregular_sampling | 0.9444 | 1.0000 | n/a | 0.0000 | n/a |
| replay | 0.2222 | 0.7222 | 0.8660 | 0.5139 | 0.0000 |
| timestamp_displacement | 0.3333 | 0.7074 | 0.8650 | 0.5139 | 0.0000 |
| truncated_history | 1.0000 | 1.0000 | n/a | 0.0000 | n/a |
| unresolved_duplicate | 1.0000 | 1.0000 | n/a | 0.0000 | n/a |

## Observed vulnerabilities

- legitimate corrected catalogue records reduce held-out support coverage; coverage 0.513889 -> 0.000000
- adversarial maneuver suppression measurably degrades development event ranking; PU delta -0.016748

Containment-gate failures: `[]`.

## Persistent cache hardening

New cache writes carry both a record-content digest and a full-store digest binding schema version, source, NORAD identity, coverage intervals and ordered records. Valid-but-tampered coverage metadata now fails closed. Earlier records-only stores remain readable as `records-sha256-verified`; unsigned legacy stores remain shape-validated as `legacy-validated` until rewritten.

## Frozen artifact

Machine-readable result: `benchmark-results/integrity-v1-stress.json`

Frozen SHA-256: `fa76061583d2b48b34f44f2167b8f2b702ceadd1553dcef73a2499092c00f73b`

## Claim boundary

The audited integrity result supports deterministic development/calibration evidence about selective abstention, integrity containment and measured degradation under the tested transformations. It does not establish formal adversarial robustness, cryptographic provenance of upstream Space-Track data, attack completeness or operational cyber-security certification. Detector method 0.4 remains unchanged. The confirmatory partition remained sealed during this development stage. It was subsequently consumed by the completed confirmatory evaluation, which failed its integration gate; see [the final results](../confirmatory_v1/RESULTS-v1.0.md). It may not be reused as untouched evidence for a tuned successor.
