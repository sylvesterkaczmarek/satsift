# Neural execution and CPU verification

## Scope and historical boundary

`research.neural_execution.NeuralExecutionModel` provides the explicit `neural-execution-v1` execution contract for GRU, TCN, Transformer, LSTM and sequential-autoencoder research models. It reuses the existing network architectures and fitting objectives while validating temporal input and separating trusted segments. It is an opt-in interface for subsequent research work.

The original selective and comparison factories, confirmatory runner, scientific fingerprints, operating points, stored predictions and results remain unchanged. The original execution paths retain their historical behaviour, including incomplete gap admission and the unchecked Transformer position limit. New work using the interface must retain its execution provenance and use a separately declared research protocol. This engineering change does not establish improved detection performance, repeat the confirmatory experiment or reopen its consumed holdout.

## Sequence admission

Supply `max_gap_seconds` explicitly when constructing a model. The limit must be positive, finite and exactly representable in whole microseconds. It is an execution policy chosen before running a study, not a parameter selected by these smoke tests.

Each row requires nonempty string `case_id` and `object_id` values, a nonnegative integer `index`, and an `epoch_utc` accepted by the strict explicit-zone timestamp parser in the [event-matching contract](EVENT-MATCHING.md). Each sequence belongs to one case and object. Indices and timestamps must strictly increase, including across invalid rows. Missing metadata, duplicate or reversed ordering, and mixed identities raise an error. The interface does not sort or deduplicate input.

A trusted row has `quality_ok` equal to the Boolean `True`, with complete finite numeric context and feature channels. Booleans and numeric strings are not channel values. Missing, non-finite or quality-failed content produces an abstention and ends the current segment. The same channel admission applies to all five architectures.

A nonconsecutive index or elapsed interval greater than `max_gap_seconds` also starts a new segment. An interval exactly equal to the declared limit stays connected. A boundary clears previous-feature input, recurrent state, convolutional history, attention context and autoencoder windows. Separate training sequences remain separate. Invalid rows are never removed in a way that joins their neighbours.

Inference preserves input length and positional alignment. Each Student-t segment has one initial unscored row because it lacks a previous observation. The sequential autoencoder needs eight contiguous valid rows, so its first seven positions abstain. Empty inference returns an empty list after fitting. Insufficient fitting data raises an explicit error. Student-t training excludes segments shorter than two rows from both fitting and normalisation and requires at least 24 remaining rows. Autoencoder training excludes segments shorter than eight rows and requires at least eight complete trailing windows. Provenance records the excluded segment and row counts.

Fitting replaces existing state only after a successful complete fit. The caller's CPU random-number state and deterministic-algorithm settings are restored afterwards.

## Transformer limit

A Transformer segment may contain at most **1,024 rows**, matching its positional embedding. Both fitting and inference validate every segment before neural computation. A segment with 1,025 rows raises `ValueError`. The interface does not truncate a history or introduce artificial windows to bypass the limit.

A history longer than 1,024 rows is accepted when actual quality, index or declared elapsed-time boundaries divide it into admissible segments. Every input position remains represented. The GRU, LSTM and TCN do not have this positional-embedding limit. The autoencoder uses its existing trailing eight-row reconstruction window.

## Causal behaviour

Causality here describes inference with a fixed fitted model and normalisation learned from the fitting data. It does not describe online fitting or guarantee valid statistical assumptions for real orbital histories.

- GRU, LSTM, TCN and Transformer predict the current feature distribution from current context and earlier features in the same trusted segment. Changing the current observed feature vector may change its surprise score, but must not change its predicted location or scale.
- Changing or appending future observations must not change earlier predictions or scores.
- The sequential autoencoder reconstructs a trailing window that includes the current observation. It is a causal reconstruction score, not a next-observation predictive distribution. Future observations remain excluded.
- Predictions after a boundary must agree with running that suffix independently from a cold state.

The smoke suite tests these properties with independent input perturbations and comparisons against separately segmented runs. It includes representative calls through the selective detector and comparison score wrapper.

## Model provenance

Call `provenance()` after successful fitting and retain the returned metadata with any new research artefact. It records the execution version, architecture and qualified model name, seed, actual hyperparameters, segment policy, training-input identity and admission counts, parameter count, model-state identity, source identities and actual runtime. Source keys use repository-relative names; machine paths and credentials are excluded.

The reused autoencoder fixes its seed at `3404`, learning rate at `0.003`, and recurrent depth at one. The interface rejects conflicting requests instead of recording settings the implementation ignores. Its hidden size and fitting epochs remain configurable. Student-t models expose their existing configurable seed and settings. Provenance distinguishes actual model settings from the small synthetic verification configuration.

These identities support traceability. They do not replace a retained checkpoint or establish numerical identity across platforms. The repository does not contain trained historical neural checkpoints.

## Run the bounded smoke suite

The dedicated environment uses CPython `3.12.11`, NumPy `2.3.2` and PyTorch `2.8.0`. Install into a compatible virtual environment. On Linux, use the official CPU wheel index:

```sh
python3 -m pip install --disable-pip-version-check --no-cache-dir numpy==2.3.2
python3 -m pip install --disable-pip-version-check --no-cache-dir torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python3 tools/run_neural_smoke.py
```

On macOS, install `torch==2.8.0` from PyPI instead of the Linux CPU index; the suite explicitly executes on CPU. These commands follow the [official previous-version installation guidance](https://pytorch.org/get-started/previous-versions/). PyTorch documents [reproducibility limits across releases and platforms](https://docs.pytorch.org/docs/2.8/notes/randomness.html).

The runner creates no research dataset or checkpoint. It launches a child process with a **180-second execution limit**, fixed seed `3404`, one compute thread, CPU tensors and deterministic algorithms. The tests use small generated sequences and two fitting epochs. Boundary tests include the complete 1,024-row Transformer segment and explicit rejection above it. Missing dependencies, failed assertions, skipped coverage, invalid reports and timeouts fail the command.

Successful execution prints a JSON verification report to standard output. Test diagnostics use standard error. The report records all five model provenances, fixture identity, source identities, actual interpreter/dependency versions and the bounded execution policy. It contains no detection-performance result. To retain it, redirect standard output to a new file outside the frozen research records.

The permanent `neural-smoke` CI job uses Ubuntu `24.04`, the same interpreter and direct dependency pins, and a ten-minute job limit that includes installation. It runs the same local command and uploads only the successful synthetic verification report. The lightweight repository and frozen-record checks remain independent of the neural runtime.

## What the checks establish

The tests execute fitting and inference, verify that training changes network weights, check complete finite outputs and positive scales, compare deterministic repeats, and exercise ordering, missing data, quality failures, index discontinuities, elapsed gaps and causal invariance. They also verify the documented Transformer boundary without silently discarding data.

Passing demonstrates the tested implementation properties on the recorded environment and fixtures. It does not validate detection accuracy, choose a backbone, calibrate thresholds, establish operational readiness or authorise a new confirmatory run. The historical environment and research disposition remain recorded in [ENVIRONMENT.md](ENVIRONMENT.md).
