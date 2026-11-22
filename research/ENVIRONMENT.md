# Research environment and reproducibility

The browser workbench, stored-result verification and historical model training have different requirements. A passing snapshot check verifies the retained records and code invariants. It does not repeat the original learned-model experiment.

## Verified historical training environment

The completed confirmatory execution configuration at retained private-source commit `5174f62bcb1da8241594f8fc575a29ca83ef76d7` specified:

| Component | Recorded configuration |
|---|---|
| Runner | GitHub Actions `ubuntu-24.04` |
| NumPy | `2.3.2` |
| PyTorch | `2.8.0`, from the official CPU wheel index |
| Python | Runner-provided `python3`; no exact interpreter patch version was pinned |
| Random seed | `3404`, fixed in the research implementations |

The historical dependency installation commands were:

```sh
python3 -m pip install --disable-pip-version-check --no-cache-dir numpy==2.3.2
python3 -m pip install --disable-pip-version-check --no-cache-dir torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
```

These lines record the historical configuration. They are not a complete environment lock and do not establish compatibility or numerical identity across operating systems, processors or Python versions. The repository does not retain trained neural checkpoints. Original commit references identify the private development record and may not resolve in a separately published source snapshot.

## Verify a source snapshot

The workbench runs with Python 3.10 or newer and requires no ML runtime. Its JavaScript checks use Node.js 22 or newer. Browser checks use the exact development dependency versions in `package-lock.json`.

Stored-result checks include:

```sh
python3 tests/confirmatory_v1_freeze_test.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B -S tools/confirmatory_post_result_audit.py
PYTHONPATH=. python3 -B -S tests/historical_evaluator_test.py
PYTHONPATH=. python3 -B -S tests/evaluation_version_test.py
python3 tests/integration_disposition_test.py
python3 tests/comparison_v1_freeze_test.py
python3 tests/physics_v1_freeze_test.py
python3 tests/integrity_v1_freeze_test.py
```

These checks verify the retained result edition, metrics, gate and scientific implementation fingerprints. They do not materialise confirmatory histories, fit neural models or score a new experiment. The permanent CI configuration records the broader check suite, including the independent SGP4 validator pinned at `sgp4==2.27`.

The lightweight research regressions avoid installing PyTorch. A separate bounded CPU suite now executes all five neural architectures through the opt-in versioned interface. Its Transformer limit is checked explicitly before fitting and inference. The historical factories remain unchanged; their original direct paths retain the unchecked limit.

## Maintained neural smoke environment

The synthetic execution suite uses the following configuration, separate from the historical training record above:

| Component | Verified local execution | Configured CI execution |
|---|---|---|
| Python | CPython `3.12.11` | CPython `3.12.11` |
| NumPy | `2.3.2` | `2.3.2` |
| PyTorch | `2.8.0` from PyPI | `2.8.0` from the official CPU wheel index |
| Platform | macOS `27.2`, Darwin `27.2.0`, ARM64 | GitHub Actions `ubuntu-24.04` |
| Device | CPU | CPU |
| Seed | `3404` | `3404` |
| Compute threads | One intra-op and one inter-op thread | One intra-op and one inter-op thread |
| Algorithms | Deterministic mode enabled | Deterministic mode enabled |
| Training | Synthetic fixtures, two epochs per fit | Same bounded suite |
| Limits | 180 seconds for suite execution | 180 seconds for suite execution; ten minutes including setup |

Local package consistency was checked with `pip check`. The generated verification report records actual interpreter, platform, direct and ancillary package versions, source identities and each model's provenance. The CI column specifies the intended runner; a hosted execution result must be checked separately. The direct pins are not a complete cross-platform dependency lock.

Run `python3 tools/run_neural_smoke.py` after installing the direct dependencies as described in [NEURAL-EXECUTION.md](NEURAL-EXECUTION.md). The runner accepts no input dataset or experiment arguments. It fails on missing dependencies, incomplete or skipped architecture coverage, assertions or timeouts. Successful JSON output is a synthetic engineering record and contains no historical model checkpoint or revised research score.

PyTorch's [reproducibility guidance](https://docs.pytorch.org/docs/2.8/notes/randomness.html) limits numerical identity across releases and platforms. Passing the suite on one CPU platform does not establish identical weights on another.

## Historical reproduction boundary

The manifest, materialisation recipe, raw-record hashes, feature hash and result provenance are retained under `benchmark-data/`, `benchmark-results/` and `research/confirmatory_v1/`. Raw credentials, sessions and cache data are not repository inputs.

A recipe describes the original queries. Exact historical reproduction also requires the matching source bytes and execution environment. A fresh upstream response may differ because records, availability or catalogue corrections have changed. Stored case-level predictions allow independent recomputation of the reported summaries without training or retrieving data. The [historical evaluator](HISTORICAL-VERIFICATION.md) contains the complete standard-library dependency set for that calculation and verifies its archived source hashes before execution. Current implementation fingerprints are checked separately, so later repairs cannot silently reinterpret the frozen results.

The confirmatory study is complete, its integration gate failed, and the run lock remains in force. Installing a dependency environment does not reopen that experiment. A successor method requires a new declared protocol and an independent holdout. Editorial reissue of file names and metadata does not change the scientific outcome.
