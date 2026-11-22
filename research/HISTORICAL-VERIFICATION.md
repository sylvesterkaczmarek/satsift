# Historical verification and evaluation versions

The completed physics-ML v1.0 study detected **0 of 41** documented confirmatory intervals and failed its predeclared gate. Its numerical results, publication-edition hashes and one-shot run lock remain unchanged. The public application remains detector 0.4.

This boundary preserves the calculations needed to verify that record while allowing separately versioned repairs to the maintained software.

## Separate verification contracts

| Contract | Implementation | Purpose |
| --- | --- | --- |
| `confirmatory-v1-historical` | [`historical_v1/`](historical_v1/) | Recompute the frozen summaries, bootstrap intervals, regime blocks, ranking and gate from retained case-level outputs. |
| `case-statistics-v1` | Prior source-fingerprint entry in [`evaluation_version_test.py`](../tests/evaluation_version_test.py) | Retain the identity of the initial maintained contract, including greedy event assignment. |
| `case-statistics-v2` | Prior source-fingerprint entry in [`evaluation_version_test.py`](../tests/evaluation_version_test.py) | Retain the first corrected assignment contract, with its original truth timestamp admission rules. |
| `case-statistics-v3` | [`evaluation_version.py`](evaluation_version.py), existing research and calibration modules | Preserve the compatibility contract with strict truth admission and `event-matching-v3`, including its original exposure and uncertainty calculations. |
| `case-statistics-v4` | Reviewed prior fingerprint in [`elapsed_evaluation_version_test.py`](../tests/elapsed_evaluation_version_test.py) | Retain the initial elapsed exposure and uncertainty evaluation contract. |
| `case-statistics-v5` | [`elapsed_evaluator.py`](elapsed_evaluator.py), [`elapsed_exposure.py`](elapsed_exposure.py) | Retain v4 exposure and uncertainty rules while rejecting contradictory event-evidence, verified-quiet and unknown truth labels. |
| `event-matching-v2` | Retained reviewed browser and Python scoring fingerprints | Preserve the identity of maximum-cardinality, minimum-distance assignment before strict truth timestamp admission. |
| `event-matching-v3` | [`event_matching.py`](event_matching.py), browser benchmark matcher | Retain corrected assignment, canonical ties and onset delay while requiring explicit-zone, calendar-valid truth timestamps. |
| Detector 0.4 release checks | [`integration_disposition_test.py`](../tests/integration_disposition_test.py) | Check the current public detector and its exact approved input-maintenance fingerprints independently of historical verification. |

The initial boundary retained the existing calculations. The maintained `case-statistics-v2` contract introduced corrected [event assignment](EVENT-MATCHING.md), and `case-statistics-v3` adds strict truth timestamp admission. The historical archive keeps its original parser and greedy matcher. The separate [elapsed-time contract](ELAPSED-EVALUATION.md) introduced corrected exposure and uncertainty reporting under v4 and maintains the stricter v5 label-admission rule where explicit evidence exists. Existing v3 training and calibration producers remain unchanged and retain their statistical limitations. A new scoring version does not revise stored results or establish improved detector performance.

## Archived calculation

[`MANIFEST.json`](historical_v1/MANIFEST.json) identifies the source definitions and pins the complete historical evaluator. It contains its own timestamp parser, event matcher, aggregation, percentile and bootstrap functions, orbit-regime grouping, ranking and gate logic. It imports only the Python standard library. It does not import maintained research or application modules.

The loader checks the trusted manifest digest and every listed file before executing the verified evaluator bytes. It does not use an existing Python bytecode cache. It never falls back to the current implementation if verification fails.

Four inert source extracts preserve the existing scientific fingerprints for the detector, its two approved input-maintenance functions and the confirmatory runner. These extracts are verification evidence and are not executable application or training snapshots.

The extracts and evaluator were taken from the publication-edition source at commit `a810250f1153c6ce43372e56d13b80e4fc589a3e`. That source includes the two documented input repairs and editorial changes. The extracts are not presented as byte-identical files from the original preconfirmatory commit.

The historical calculation deliberately retains its greedy event assignment, row-fraction exposure estimate and satellite bootstrap, including zero-width intervals where the stored observations produce them. Their limitations remain documented in [KNOWN-ISSUES.md](../KNOWN-ISSUES.md). A successful historical audit confirms reproduction of the recorded calculation; it does not establish that these estimators are adequate for future use.

## What can be reproduced

The audit uses the retained predictions, truth intervals, coverage fractions and other case-level fields. It recomputes all 16 method summaries and confidence intervals, every recorded orbit-regime block, the ranking and the failed gate. It also checks the retained provenance links and calibration metadata.

It does not reconstruct the original raw orbital histories, regenerate features, run propagation or model inference, retrain models, or establish how every stored prediction was produced. Those operations require inputs and dependencies outside this statistical verification boundary. Original commit identifiers are provenance, and private Git objects are not required by the audit.

The final result, its sidecar, the publication-edition ledger and the run lock remain the evidence of record. The evaluator archive adds verification code without editing those files.

## Verify from a source snapshot

Run these commands from the repository root using Python 3.10 or newer. No Git history, network access, NumPy, PyTorch or upstream credentials are required.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B -S tools/confirmatory_post_result_audit.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B -S tests/historical_evaluator_test.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B -S tests/evaluation_version_test.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B -S tests/elapsed_evaluation_version_test.py
python3 tests/publication_edition_test.py
python3 tests/integration_disposition_test.py
```

The historical boundary tests check exact reproduction, reject modified archive dependencies and repeat the audit in a source snapshot with maintained implementations deliberately unavailable, including the browser modules. Maintained browser fingerprint checks inspect the explicit module inventory through `tools/browser_source.py`; runtime equivalence tests instantiate the actual factories and entry wiring. Their existing expected scientific and input-maintenance hashes remain unchanged. The maintained-version test separately rejects unversioned changes to the selected evaluation definitions and exercises the current runner fingerprint guard. CI runs both sets of checks.

The audit is read-only by default. Its existing `--write` option is an explicit report-regeneration operation and is not part of these verification commands. Do not regenerate frozen reports to make corrected software agree with historical output.

## Rules for subsequent repairs

1. Leave `historical_v1/`, the historical result bytes, publication-edition ledger, recorded operating points and run lock unchanged.
2. Change maintained code and add a regression demonstrating the defect and its correction. Check that the historical audit still reproduces the old results independently.
3. Give changes to matching, time interpretation, coverage or exposure, aggregation, bootstrap or interval calculation, ranking or gate semantics a new evaluation version. Retain prior version entries and register the reviewed source fingerprint in the applicable version guard. `tests/evaluation_version_test.py` preserves v1-v3; `tests/elapsed_evaluation_version_test.py` preserves the v4 fingerprint and guards the current v5 evaluator and its complete dependencies. A version name cannot be reused for changed semantics.
4. Keep future outputs separate and include their evaluation version. Frozen reports predate this field and are identified by their retained hashes and the historical manifest; do not retrofit metadata into them.
5. Review public detector or input changes under their separate release and regression contract. A historical audit pass does not approve a current detector change.

The v1.0 confirmatory partition remains consumed. A new version identifier does not authorise another one-shot evaluation or turn this partition into an untouched holdout.
