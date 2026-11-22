# Validation status

## Completed in the repository baseline

- UTC-safe and sub-millisecond OMM handling with deterministic catalogue supersession and audit output.
- Tested history-request coalescing, including concurrent identical/overlapping requests, persistent-cache integrity and atomic failure behavior.
- SGP4 common-epoch RTN analysis with fixed-epoch quiet and maneuver fixtures and independent Python SGP4 cross-checks.
- Browser-style regression execution, multi-time-zone epoch checks, release-quality checks, security-header checks and allowlisted deployment routing.
- Frozen public-evidence benchmark v1.0 with 40 satellite-disjoint objects, 154 documented event intervals and explicit verified-quiet controls.
- Comparison suite covering detector 0.4, classical statistical/orbital baselines, filtering/particle-filter methods and representative learned baselines under common matching/scoring rules.
- One-shot confirmatory evaluation on 12 satellite-disjoint objects with 41 documented truth intervals and two verified-quiet controls, including 1,000-replicate satellite-cluster confidence intervals.
- Exact confirmatory result/data/feature hashes, run lock, provenance record and independent post-result audit recomputation.
- Reproducibility exports, pinned browser dependencies and permanent GitHub Actions CI/freeze checks.

The engineering and confirmatory-freeze workflows are configured for pushes and pull requests to main. The release verification record distinguishes local execution from any hosted execution and retains the reissued confirmatory result and negative integration decision.

## Physics-ML research disposition

Historical physics-ML v0.3 did not meet its development integration gate and was never integrated.

The later physics-ML v1.0 stack was frozen before confirmatory access and evaluated in the confirmatory study. On the frozen 12-satellite confirmatory partition it produced `0` true positives and `41` false negatives, with recall `0`, F1 `0`, zero verified-quiet false events and mean case abstention about `0.9212`. The predeclared integration/publication gate failed.

The failed gate blocked integration. The maintained repository workbench is version 3.4.9 with detector method 0.4. Its catalogue-metadata repair preserves absent identifiers, supplied TLE identifiers and TLE origin through normalised exports, package reopening and appended corrections. Its TLE precision repair retains original validated TLE pairs, integer-microsecond epochs and precise SGP4 elapsed-time evaluation, with versioned packages and run identities. Later engineering maintenance did not integrate the rejected research method or rerun the frozen evaluation. The negative result is retained under `benchmark-results/confirmatory-v1-final.json`, `research/confirmatory_v1/RESULTS-v1.0.md` and `review/CONFIRMATORY-AUDIT.md`.

## Modular browser implementation

Workbench 3.4.9 loads explicit plain JavaScript module factories through a small composition script. The module extraction retained the original 191 function bodies and scientific constants. The subsequent catalogue identity correction changes two reviewed parser functions and adds one versioned identity helper. Version 3.4.9 separately repairs exact/near-epoch catalogue resolution and strict benchmark-tolerance admission; their prior fingerprints and browser comparison fixtures remain retained. A synthetic fixture captured before extraction binds runtime function identities, complete analyses, normalised exports, packages, matching decisions and run identifiers. Runtime tests execute the actual production factories and composition.

Content-addressed filenames and script integrity values bind the browser's module set. Server and deployment admission remains explicit, including a compatibility loader for cached documents that reference the legacy application script. Updated checks cover asset references, private-path rejection, introduced deployment files and existing browser workflows. The [architecture guide](../BROWSER-ARCHITECTURE.md) describes the entry points and source-inspection boundary.

Detector, scoring, package and identity versions retain their existing semantics. The historical verification code remains independent of maintained browser sources, and its frozen artefacts, expected hashes, failed gate and one-shot lock are unchanged.

## Catalogue identity admission

Workbench 3.4.9 recognises the standard Alpha-5 TLE identifier range, canonicalises decimal and zero-padded object IDs, and keeps the original TLE lines. A legacy TLE-derived OMM package with an Alpha-5 identifier is admitted only when its retained source TLE validates against the normalised fields. A native OMM record must use a decimal `NORAD_CAT_ID`. Reviewed parser and canonicalisation fingerprints have explicit regressions; earlier 3.4.7 fingerprint entries remain documented.

## Maintained precision and replay contract

Workbench 3.4.9 retains reproducibility package schema 1 and run identity version 2. The normalised OMM array retains original TLE pairs in a validated `SMD_TLE` object, so append and saved-package paths preserve their propagation inputs. The `smd-v2-` identifier uses a noncryptographic FNV-1a 64-bit hash over the canonical run contract. Legacy packages remain readable and can be re-exported with their available normalised records. Missing original TLE precision cannot be recovered and is reported when known. Run identity describes numerical input, configuration and propagation; generated time, latest-element age and freshness warnings are recomputed on reopening.

`tests/tle_precision_roundtrip_test.js` covers precise TLE epochs, residual replay, versioned identity and package validation. `tests/tle_precision_reference_check.py` compares the maintained propagation path with the Python `sgp4==2.27` reference. Both permanent workflows run these focused checks alongside the existing historical verification checks. The archived evaluator, frozen numerical results, failed gate and run lock remain unchanged.

Native OMM model initialisation still passes through satellite.js's millisecond-resolution `Date` conversion. Record ordering and propagation target epochs retain microseconds. This remaining vendor limitation bounds the current precision claim.

## Maintained event-scoring contract

Workbench 3.4.9 and the maintained Python matchers use `event-matching-v3`: maximum-cardinality one-to-one assignment followed by minimum total strongest-point-to-truth-midpoint distance. Eligibility remains inclusive interval overlap after expanding the truth interval by the tolerance. Canonical temporal ordering and a specified shortest-path tie rule make equivalent input permutations produce the same temporal assignments. Exact integer-microsecond costs avoid floating-point tie perturbations. Primary detection delay uses prediction onset minus truth onset; detailed matched-pair outputs retain strongest-point delay separately.

New browser reports declare schema `smd-event-benchmark-report-v4`, carry the scoring version and use the `smb-v2-` identifier prefix. Existing research and calibration reports declare `case-statistics-v3` and the scoring version. The current retrospective elapsed-time evaluator declares `case-statistics-v5` while preserving the same event-matching contract. The independent oracle, browser parity and wrapper regressions are in `tests/event_matching_test.py`; the complete [matching contract](../research/EVENT-MATCHING.md) describes their scope. Strict truth admission requires complete strings with explicit timezones, valid calendar and clock fields, at most six fractional digits and chronologically ordered UTC endpoints. Supplied invalid values fail instead of becoming point events. Cross-timezone admission, normalisation and matching checks are in `tests/benchmark_timestamp_test.py`.

The historical evaluator keeps greedy assignment. Its archived bytes, frozen predictions, summaries, hashes, failed gate and consumed holdout remain unchanged. No research evaluation or historical data collection was repeated for this maintenance release.

## Corrected elapsed-time evaluation

The separately versioned `case-statistics-v5` evaluator integrates explicit supported source intervals, with exact microseconds, a declared maximum gap, clipped windows and interval unions. It separates covered duration, elapsed abstention and unobserved time. Missing evidence never falls back to a fraction of rows or a case span. Duplicate or overlapping case windows for one object are rejected when event counts cannot be safely reconciled.

Uncertainty uses whole-object resampling with explicit relevant-object counts, undefined replicate counts and degeneracy statuses. A zero observed candidate count does not produce an inferential zero-width interval. The supplementary one-sided 95% Poisson zero-event upper bound states its assumptions and marks them unverified. These calculations do not establish an operational guarantee.

The initial v4 contract was recorded before implementation. Version v5 rejects unrecognised label values and contradictory label/truth combinations, including on unselected splits. The recognised unknown label remains accepted when its truth list is empty. Synthetic regression suites cover interval arithmetic, metadata admission, missing evidence, sparse quiet data, object-cluster resampling and protected output paths. The complete v4 implementation and matching dependency have a separate source fingerprint. Existing v3 calibration code, operating points, historical verification, frozen results and the one-shot lock remain unchanged. No stored research data was rescored. See [the evaluation contract](../research/ELAPSED-EVALUATION.md).

## Neural CPU execution

The opt-in `neural-execution-v1` interface reuses the existing GRU, TCN, Transformer, LSTM and sequential-autoencoder networks with explicit input admission and trusted-segment boundaries. Invalid channel content, quality failures, missing indices and declared elapsed gaps cannot connect neural state across a boundary. Duplicate or reversed sequence metadata is rejected. Transformer segments are limited to 1,024 rows before fitting or inference, with no silent truncation.

The synthetic CPU suite runs actual fitting and inference for all five architectures, checks finite trained weights and outputs, verifies deterministic repeats and causal perturbations, and exercises selective/comparison integration. It checks the complete length boundary and rejects overlength segments before neural allocation. The bounded local command and dedicated CI configuration record model version, seed, hyperparameters, source identities and actual runtime. See the [execution contract](../research/NEURAL-EXECUTION.md) and [environment record](../research/ENVIRONMENT.md).

The unchanged historical training factories retain their old execution behaviour. No stored dataset was rescored, no threshold was selected, and no confirmatory training was performed for this verification. The source and recorded-result preservation checks remain separate gates. Passing synthetic tests does not establish detection accuracy or platform-independent numerical identity.

## Maintained acquisition provenance

Workbench 3.4.9 carries acquisition evidence through historical loading, CelesTrak GP cache reuse, validated append operations, analysis JSON and reproducibility packages. Package schema 1 gains an optional versioned provenance field with a separate noncryptographic normalised-input fingerprint. Reopening validates and restores this field before input or settings change. Manual edits, demonstrations and unrelated replacements clear stale metadata.

The history endpoint writes schema 2 stores with acquisition metadata and update time included in the full-store SHA-256. Serving time remains separate from actual retrieval time. Legacy stores stay readable and report unknown acquisition times; extensions preserve the distinction. Local content identities do not establish provider authentication or imply a fresh catalogue release.

The [history policy](../HISTORY-POLICY.md) defines retained historical coverage, current-GP append and explicit correction imports. `tests/history_provenance_test.py` and `tests/history_provenance_test.js` exercise these contracts offline. Detector, scoring, prediction, frozen-data and recorded-result contracts are unchanged.

## Maintained materialisation contract

Materialiser 2.0 validates complete Space-Track responses before selecting records. Exact UTC epochs define duplicate groups; supplied UTC creation instants take priority over supplied element-set and GP identifiers. The strongest metadata rank is selected before orbital conflicts are considered. Unresolved conflicts at that rank are rejected, and equivalent copies have a deterministic raw-record tie-break.

The maintained tool explicitly rejects malformed, wrong-object and out-of-window records, checks the raw response limit before exclusions, and validates recipe/manifest binding before authentication. A fully validated observation at the following midnight is excluded from the requested interval and counted. The CLI requires an unused output path and refuses the frozen benchmark output location. New output includes the materialiser version and its selection and response-validation policies.

`tests/materializer_validation_test.py` verifies these rules offline with synthetic data and mocked network access in both permanent workflows. This repair did not collect histories, regenerate the frozen dataset, rerun an evaluation or change the browser release. The frozen recipe, historical evaluator, provenance, numerical results and failed gate remain the evidence of record. See [the materialisation guide](../tools/MATERIALISATION.md) for current usage and historical compatibility limits.

## Qualification boundaries

- Public-evidence labels are not onboard telemetry or definitive command logs.
- Event-evidence histories use positive-unlabelled semantics: unmatched predictions outside documented intervals are not automatically false positives.
- The benchmark v1.0 confirmatory partition has now been consumed and may not be reused as untouched evidence for a tuned successor method.
- Any future learned successor intended for a new confirmatory claim requires a genuinely new satellite-level holdout frozen before development.
- The independent Python SGP4 test validates generated fixtures but is not independent expert certification of the detector methodology.
- Internal astrodynamics and accessibility review material is preparation material, not external certification.
- Repository routing hardening does not prove that the live host has already received the latest repository files.
- The frozen confirmatory result does not support integration of physics-ML v1.0 or a positive-result paper claim for that method.

## Required work before operational reliance

- Independent astrodynamics review and signed disposition of findings.
- Manual assistive-technology testing by a human reviewer and any formal accessibility documentation required by an adopting organisation.
- Operator-grade or independently curated ground truth for any operational performance claim.
- Deployment-specific cybersecurity and operational-readiness assessment.

## Clean source release candidate

The [source release verification](CLEAN-RELEASE-VERIFICATION.md) records the current tree, targeted privacy review, actual Apache routing tests and independent checks of the exported source inventory. The source packager excludes Git history and local state by construction. The [release procedure](../RELEASE.md) identifies the licence, redistribution and publication decisions still required. No live deployment or public visibility change is part of that preparation.
