# Confirmatory evaluation execution and materialization incident record

## Scope

This file preserves infrastructure and software-execution incidents encountered after the Confirmatory evaluation preconfirmatory freeze. None authorized scientific retuning.

## Frozen boundary

- frozen scientific commit: `2c394d4d9362c65560a2a08827b4e1a96f23ed87`
- frozen scientific tree: `b89b6ead78824e31ebdb41d4cf1fe1569f6ab1a1`
- confirmatory partition: 12 unique satellites, 41 truth intervals, two verified-quiet controls
- method roster: 16
- gate: committed before confirmatory history materialization

## Materialization attempts 1 and 2

GitHub Actions run `31885152208` attempts 1 and 2 each passed the full preconfirmatory checks and reproduced the frozen calibration. Both stopped during GP_History materialization with HTTP 429 after the first three frozen histories. No detector/model scoring followed those failures.

## Materialization attempt 3

The same frozen job was retried once more without method changes. It again stopped at the fourth history with HTTP 429 before any scoring.

## Transport-only recovery

Run `31886194238` changed only HTTP retry behavior so the benchmark builder honored the endpoint's `Retry-After` instruction. It used the same Space-Track GP_History source, object IDs, dates, labels and frozen `build_case` semantics. All 12 histories were successfully materialized.

The detector 0.4 subprocess then executed and the dedicated confirmatory feature exporter produced 468 causal rows. The integrated 16-method runner failed immediately in `verify_confirmatory` before constructing any stored method summary because it called the development-only loader, which correctly rejected an artifact marked `confirmatory_sealed=false` even though the dedicated confirmatory wrapper had also marked it `confirmatory_confirmatory_authorized=true` and `one_shot=true`.

No integrated confirmatory metric was generated or used to change the method or gate. The detector-only temporary result was not inspected for tuning and was lost with the failed workflow workspace.

## Execution-only loader repair

Commit `c9a41abdf36313b09bbada1ef861aefb7a741d3f` changed only the confirmatory authorization handoff plus its regression tests. It did not change features, detector 0.4, any baseline, model architecture, hyperparameter, calibration, threshold, matching, bootstrap or gate logic. The normal selective-v1 loader remains sealed against confirmatory data.

## Successful integrated evaluation

Run `31887104065` reverified the frozen science, reproduced calibration, materialized the same 12 frozen histories, hashed the raw test-set and feature artifacts, and executed the complete 16-method integrated evaluation. Detector 0.4 had to be regenerated because the first detector-only temporary file was unavailable after the failed orchestration. Physics-ML v1.0 and the 14 generic/statistical comparison methods were scored only in this successful integrated run.

The final result was frozen with SHA-256 `f9857bd8f9ae2525b1827ce4fdfd108f7c5468c67142226922542d24b88c923c` and the predeclared gate failed.

## Interpretation

The HTTP failures were data-transport incidents. The later loader failure was an execution-plumbing defect discovered only after the holdout artifact existed. Its repair was restricted to explicit authorization parsing. The detector 0.4 regeneration is a documented procedural exception to the strongest literal reading of "exactly once", but there was no inspection-driven adaptation, no target-method rerun and no post-hoc gate change.
