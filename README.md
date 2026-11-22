# SatSift

SatSift screens satellite orbital-element histories for candidate manoeuvres and anomalies. It compares TLE and OMM orbit solutions using common-epoch SGP4 evidence, reports data quality and abstention, and exports inputs, settings and results for reproducible review.

**Research screening only.** A candidate is an orbital change that warrants investigation. It does not confirm that a satellite fired its thrusters. The workbench has not been independently qualified for operational space situational awareness decisions.

## Quick start

Python 3.10 or newer is sufficient to run SatSift locally. There is no build step. Clone the repository and start the local server. A verified source archive can also be used without Git:

```sh
git clone https://github.com/sylvesterkaczmarek/satsift.git
cd satsift
python3 tools/serve_workbench.py
```

Open [the local workbench](http://127.0.0.1:8000/satellite-maneuver-detector) and select **Try a synthetic example**, or import a TLE history or OMM JSON file. The examples demonstrate a candidate event, a quiet history and insufficient data.

The server binds to the loopback interface and serves the public application routes. Imported files are processed in your browser. Current CelesTrak snapshots require an internet connection; authenticated historical retrieval requires the PHP configuration described in [DEPLOYMENT.md](DEPLOYMENT.md).

## Current implementation

- Workbench release: 3.4.9
- Project licence: [Apache License 2.0](LICENSE) for original source; third-party and data-specific terms remain separate
- Detector method: 0.4
- Intended use: research screening and technical evaluation
- [Hosted workbench](https://www.sylvesterkaczmarek.com/satellite-maneuver-detector)
- [User documentation](docs.html)
- [Known limitations](KNOWN-ISSUES.md)
- [Publication review and prioritised repairs](review/PUBLICATION-REVIEW.md)
- [Combined verification and release disposition](review/COMBINED-VERIFICATION.md)
- [Release notes](RELEASE-NOTES.md)
- [Source release preparation](RELEASE.md)
- [Third-party notices](THIRD-PARTY-NOTICES.md)

The baseline combines common-epoch SGP4 propagation, radial/along-track/cross-track residuals, orbital-element changes, orbit-specific thresholds, event grouping and explicit abstention. The interface provides UTC charts, orbital context, catalogue-revision diagnostics, JSON and CSV exports, and reproducibility packages.

The maintained release preserves catalogue metadata, original TLE precision, saved-package identity and acquisition provenance. Version 3.4.9 adds deterministic handling of mixed exact/near-epoch TLE and OMM records, strict benchmark-tolerance admission and a repaired Apache routing boundary. Detector 0.4 and its thresholds remain unchanged. The [release notes](RELEASE-NOTES.md) record the version boundaries and earlier repairs.

### Browser source organisation

The browser implementation is organised into plain JavaScript modules for orbital input, benchmark scoring, reproducibility packages, detection and interface state, with shared utilities and a small entry script. The [browser architecture](BROWSER-ARCHITECTURE.md) identifies the responsibilities, dependency composition and verification boundaries. Local startup still requires only Python; there is no build step.

The document and compatibility loader use content-addressed script URLs with integrity metadata. The server and deployment tools expose only declared assets. The original module refactor retained Workbench 3.4.7 and its computation contract. Subsequent input-admission repairs preserve detector 0.4, scoring, package schema and propagation methods, with explicit release identity in new runs. The module refactor is checked against a synthetic fixture captured from the preceding implementation.

## Working with orbital histories

Provide enough history for calibration and at least five subsequent evaluation points. A single current snapshot cannot establish a change. Supported OMM defaults and TLE conventions follow the [CelesTrak GP format documentation](https://celestrak.org/NORAD/documentation/gp-data-formats.php) and [TLE format description](https://celestrak.org/columns/v04n03/).

| Result | Interpretation |
| --- | --- |
| Candidate event | The eligible data exceed the selected screening criteria. Inspect the evidence and catalogue-quality notes. |
| No candidate | The selected method found no candidate in the eligible data. |
| Abstain | Data quality, history length or method support is insufficient for a result. |

Use **Replace current input** to reopen an exported reproducibility package. The workbench restores its normalised input and settings, then recalculates the analysis. Older packages omit the stale-age setting and retain the current limit with a notice.

TLE Alpha-5 identifiers (for example, `A0000` for NORAD 100000) and zero-padded decimal identifiers are canonicalised to the same decimal object identity as OMM. Original validated TLE lines remain preserved for propagation. A legacy Alpha-5 OMM export can reopen when it includes a matching retained TLE pair; native OMM requires a decimal `NORAD_CAT_ID`. Previously exported packages without source lines cannot recover absent metadata.

Exports preserve whether an element-set identifier was supplied. Missing identifiers remain absent; genuine values, including `0` and `999`, are retained. Normalised TLE records retain their origin for catalogue comparison. Appending an identical orbital solution with better catalogue metadata retains that metadata. Equivalent TLE/OMM copies retain TLE origin when revision metadata ties. Exact-epoch groups are resolved before near-epoch comparisons, so input order cannot leave a stale ambiguity count after TLE enrichment. Conflicting solutions with equal numeric catalogue identifiers remain unresolved.

Catalogue precedence is creation timestamp, known element-set number, then GP identifier. Supplied decimal GP identifiers outrank opaque identifiers; decimals compare as exact integers and opaque strings use locale-independent lexical order. Equal numeric identifiers remain tied. This defines deterministic selection and does not establish provider chronology for opaque identifiers.

### History acquisition and corrections

Cached history preserves its original acquisition evidence. A response's serving time is separate from the time its source records were retrieved; legacy acquisition times remain explicitly unknown. Analysis JSON and reproducibility packages retain versioned source provenance, including local content identities and a separate fingerprint of the normalised input. Reopening restores those details.

Use the current GP snapshot control to append a new observation, or import an authorised correction file with **Append and merge**. Preserve the original package and export the reviewed result separately. Historical coverage has no automatic expiry or forced refetch. The [history retention and correction policy](HISTORY-POLICY.md) explains the supported workflow, source-identity limits and server-cache boundary.

### Epoch precision and saved packages

New TLE imports retain full fractional-day epoch precision as integer microseconds. Their normalised records preserve the original validated pair in `SMD_TLE: {schema_version: 1, line1, line2}` alongside `SMD_SOURCE_FORMAT: "TLE"`. Reopening or appending those records retains the TLE propagation input and evaluates common-epoch residuals at exact elapsed times. The importer checks the retained pair against its normalised fields and rejects inconsistent data. Per-epoch results in CSV and analysis JSON use six fractional second digits in UTC; normalised OMM input retains its source epoch spelling. Interface labels retain millisecond resolution.

New packages declare `package_schema_version: 1` and `run_identity_version: 2`, while retaining the `normalized_input_omm` array. Run identifiers use the `smd-v2-` prefix and FNV-1a 64-bit, a noncryptographic hash of the canonical run inputs, settings and propagation contract. Equivalent supported UTC timestamp spellings share an identity. The changed identity version deliberately separates current runs from older identifiers. Run identity covers numerical input, configuration and propagation. Reopening recomputes generated time, latest-element age and freshness warnings, so these report fields can change.

Legacy packages remain importable and receive a recomputed current identifier. Older exports may contain an invented `999`, have lost their TLE origin, or lack the original TLE pair and full epoch precision. The importer reports the original-TLE precision limitation when relevant. Reimport the original source to recover missing information; the package cannot reconstruct it. Legacy records without retained TLE lines can be saved again using their available normalised data, without recovering the missing source precision.

Native OMM timestamps retain microseconds for ordering and target-epoch comparisons. Their orbital models are still initialised through satellite.js's millisecond-resolution JavaScript `Date` path. That vendor limitation remains documented in the [review](review/PUBLICATION-REVIEW.md).

## Validation and research status

Engineering regressions cover parsing, catalogue revisions, timezones, exports, browser workflows, history caching, concurrency, deployment safeguards and independent SGP4 fixtures. Passing these checks does not establish detection accuracy.

The separate physics-ML v1.0 research method **failed its predeclared confirmatory gate**. On the frozen 12-satellite confirmatory partition it detected **0 of 41 documented event intervals**, with recall and F1 both zero. It was not integrated into the public workbench. The public method remains detector 0.4.

The same evaluation reported F1 values of approximately 0.5763 for SGP4 RTN consistency and 0.5263 for detector 0.4. Both methods' verified-quiet false-event point estimates exceeded the common one-event-per-object-month target. These historical results do not establish operational readiness. The review also identifies scoring and exposure-estimation limitations that require a separately versioned evaluation.

See the [confirmatory results](research/confirmatory_v1/RESULTS-v1.0.md), [integration decision](research/confirmatory_v1/INTEGRATION-DISPOSITION.md) and [research environment](research/ENVIRONMENT.md). The confirmatory data have been used and cannot serve as an untouched holdout for a tuned successor.

### Research components

| Component | Purpose and record |
| --- | --- |
| [Historical physics-ML](research/physics_ml/README.md) | Earlier v0.1-v0.3 experiments and their unsuccessful integration decision. |
| [Selective ML](research/selective_v1/README.md) | Conditional nominal models, four-backbone comparison and support abstention. |
| [Sequential evidence](research/sequential_v1/README.md) | Repeated-monitoring evidence and empirical false-event calibration. Formal guarantees require assumptions not established for real GP histories. |
| [Manoeuvre physics](research/physics_v1/README.md) | Equivalent-impulse feasibility, uncertainty and independent physical checks. |
| [Integrity](research/integrity_v1/README.md) | Deterministic corruption, catalogue-revision and abstention stress studies. |
| [Comparison suite](research/comparison_v1/README.md) | Sixteen predeclared methods evaluated on common partitions. |

The [publication-edition record](research/PUBLICATION-EDITION.json) identifies the original and current hashes of eight editorially reissued result and provenance files. Component names, metadata keys and linked hashes were updated; predictions, numerical results, gate criteria and the failed gate were preserved. No experiment was rerun for this edition.

The [historical verification boundary](research/HISTORICAL-VERIFICATION.md) preserves a versioned evaluator for those stored case-level results. Its archived matching, exposure and uncertainty calculations remain unchanged while the maintained software receives separately versioned repairs.

### Corrected elapsed-time evaluation

The separately versioned `case-statistics-v5` evaluator measures supported source intervals using explicit timestamps, a declared gap limit and method support decisions. It reports elapsed abstention separately from missing or excluded time, resamples complete satellite clusters, and identifies insufficient or degenerate uncertainty. A supplementary zero-event Poisson bound is conditional on stated, unverified assumptions.

Use [the elapsed-time evaluation contract](research/ELAPSED-EVALUATION.md) and `tools/evaluate_elapsed_benchmark.py` for this corrected retrospective path. Version v5 also rejects contradictory event labels and unrecognised label values before scoring; the v4 source fingerprint remains recorded. Older exports without the required evidence retain usable event counts but have unavailable elapsed exposure. Existing v3 training and calibration calculations remain unchanged; their row-fraction or whole-span exposure estimates are not corrected by relabelling them. No stored research result was rescored for this implementation.

### Neural execution checks

The opt-in `neural-execution-v1` interface validates temporal input, resets model state at quality or declared gap boundaries, and rejects Transformer segments longer than 1,024 rows before computation. CPU smoke tests fit and exercise all five neural architectures using small synthetic fixtures, including causal invariance and the length boundary. The [execution contract](research/NEURAL-EXECUTION.md) explains admission, warm-up and model provenance.

Run `python3 tools/run_neural_smoke.py` in the documented neural environment. The same command has a 180-second execution limit in the dedicated CI job. Its JSON report records actual runtime and model provenance. Historical training factories, stored results, thresholds and the failed confirmatory gate remain unchanged; these execution tests establish no new detection-performance result.

## Benchmark data

Two artefacts serve different purposes.

**The browser seed** is `public-evidence-manifest-v0.1.json`, served at the workbench's `/benchmark/manifest` route. It demonstrates the runner format. Its unknown candidate controls cannot support precision or false-alert claims.

**Publication benchmark v1.0** contains 40 satellite-disjoint cases, comprising 30 event-evidence cases, ten verified-quiet controls and 154 documented event intervals. It separates development, calibration and confirmatory objects. Its frozen, recipe-based records are:

- [Evidence manifest](public-evidence-manifest-v1.0.json)
- [Historical-data query recipe](benchmark-data/public-evidence-benchmark-v1.0.recipe.json)
- [Scoring protocol](benchmark/PUBLICATION-PROTOCOL-v1.0.md)
- [Source ledger](benchmark/SOURCE-LEDGER-v1.0.md)
- [Data attribution and redistribution notice](benchmark/DATA-NOTICE.md)

Unlabelled periods are not treated as negatives. Scheduled-manoeuvre notices retain their scheduled-evidence status. The browser uses `confirmed-quiet` for eligible negative coverage; the same-site builder translates the research term `verified-quiet` while retaining source provenance.

### Maintained event scoring

New benchmark runs use `scoring_version: "event-matching-v3"`. One-to-one assignment first maximises the number of matched events, then minimises total distance between each prediction's strongest point and its matched truth interval midpoint. Eligibility remains inclusive overlap between the prediction interval and the truth interval expanded by the matching tolerance. The primary detection delay is prediction onset minus truth onset; detailed matches keep strongest-point delay separately.

Browser reports use schema `smd-event-benchmark-report-v4` and the `smb-v2-` identifier prefix. Maintained Python reports also declare `evaluation_version: "case-statistics-v3"`. These identifiers separate corrected scoring from earlier calculations. The [matching contract](research/EVENT-MATCHING.md) specifies precision, deterministic ties and compatibility limits. Frozen protocols, reports and their historical greedy evaluator remain unchanged; no historical experiment was rerun.

An explicit matching_tolerance_hours must be a finite JSON number from 0 through 168 inclusive. Omission defaults to 24 hours. Nulls, booleans, arrays, objects, numeric strings and out-of-range values are rejected; existing files must use numeric values rather than relying on coercion or clamping.

Benchmark truth boundaries must be complete timestamp strings with an explicit `Z` or numeric offset, for example `2026-01-02T03:04:05.123456+01:00`. Fractions may contain up to six digits. Invalid calendars, values without a timezone, non-string values and reversed intervals are rejected. Omitting `end` creates a point event; an explicitly empty or null `end` is invalid. Browser reports normalise accepted boundaries to UTC with six fractional digits.

### Materialising historical inputs

Historical data reconstruction requires authorised source access. Raw credentials, sessions and local caches belong outside version control. The maintained materialiser 2.0 validates complete upstream responses and selects exact-epoch revisions by UTC creation time, then supplied element-set and GP identifiers. Invalid data and unresolved conflicts among the strongest revisions stop materialisation explicitly.

The helper requires a new output path, refuses existing output files or checksum sidecars, and protects the frozen benchmark output location. New output records the materialiser version and selection and validation policies. The frozen recipe, labels and historical results remain unchanged. A fresh response and the repaired selection rules do not reconstruct the original historical source bytes. See the [materialisation guide](tools/MATERIALISATION.md) for the current contract and separate-output workflow.

## Verification

The focused offline checks require Node.js 22 or newer and Python:

```sh
python3 tools/update_browser_assets.py --check
node tests/browser_module_equivalence_test.js
node tests/browser_module_loader_test.js
node tests/input_validation_test.js
node tests/catalogue_metadata_roundtrip_test.js
node tests/catalogue_identifier_test.js
node tests/tle_precision_roundtrip_test.js
node tests/async_input_test.js
node tests/workbench_selftest_harness.js
python3 tests/maneuver_research_regression_test.py
python3 tests/materializer_validation_test.py
python3 tests/event_matching_test.py
python3 tests/benchmark_timestamp_test.py
PYTHONPATH=. python3 tests/elapsed_exposure_test.py
PYTHONPATH=. python3 tests/elapsed_evaluation_test.py
PYTHONPATH=. python3 tests/elapsed_evaluation_version_test.py
python3 tests/neural_smoke_runner_test.py
node tests/event_matching_version_test.js
python3 tests/local_server_test.py
python3 tests/publication_edition_test.py
python3 tests/source_release_test.py
python3 tests/repo_checks.py
```

For desktop and mobile browser tests, downloads and automated accessibility checks:

```sh
npm ci
npx playwright install chromium
npm run test:browser
```

Apache 2.4 with mod_rewrite and mod_headers is required for python3 tests/apache_route_boundary_test.py. This suite starts an isolated loopback server with synthetic files and fails if Apache is unavailable. PHP endpoint tests require PHP CLI with cURL. Run `python3 tests/history_admission_test.py` for offline multi-worker admission, quota and resource-limit checks against a loopback upstream. `python3 tests/history_provenance_test.py` and `node tests/history_provenance_test.js` verify acquisition evidence, correction lineage and saved-package reopening. Independent propagation validation requires `sgp4==2.27`; run `python3 tests/tle_precision_reference_check.py` to compare precise TLE propagation against that reference. The complete commands are maintained in the [repository workflow](.github/workflows/ci.yml) and [confirmatory record workflow](.github/workflows/confirmatory-freeze.yml). Action dependencies are pinned to commit hashes.

The stored-result audit is read-only by default:

```sh
PYTHONPATH=. python3 tools/confirmatory_post_result_audit.py
```

It checks the recorded evaluation and scientific fingerprints without repeating the one-shot experiment or requiring the private development history.

## Deployment and security

See [DEPLOYMENT.md](DEPLOYMENT.md) for the exact public-file allowlist, routing template, local SSH configuration and deployment safeguards. The remote document root is supplied through local configuration and has no committed default. The site routing template is [deployment/site-root.htaccess](deployment/site-root.htaccess).

Keep Space-Track credentials and caches outside the public web root. The repository contains only an [example credential configuration](config/.space-track-config.php.example). The [release procedure](RELEASE.md) creates a verified source-only candidate. The project licence is Apache 2.0. The initial public source release uses a reviewed snapshot with new Git history; the original development history remains private. The history endpoint bounds incoming requests, individual upstream operations, lock waits and retained storage. Read the [endpoint limits and upgrade procedure](DEPLOYMENT.md#history-endpoint-limits) before changing an existing installation. See [SECURITY.md](SECURITY.md) for reporting and scope.

## Repository layout

| Location | Contents |
| --- | --- |
| `index.html`, `app-3.4.js` | Browser document and application composition/startup |
| `app/`, `browser-assets.json` | Declared browser modules and source inventory |
| `BROWSER-ARCHITECTURE.md` | Module responsibilities, asset delivery and equivalence checks |
| `history.php` | Historical-data endpoint and persistent-cache validation |
| `benchmark/`, `benchmark-data/`, `benchmark-results/` | Protocols, data recipes and recorded evaluations |
| `research/` | Experimental methods, provenance and research documentation |
| `tests/` | Engineering, scientific and security regressions |
| `tools/` | Local serving, dataset, verification and deployment utilities |
| `review/` | Review findings and external qualification records |
| `deployment/`, `config/` | Generic routing and configuration templates |
| `LICENSE`, `NOTICE` | Project licence and attribution |
| `licenses/` | Third-party licence notices |

## Licence and remaining qualification

Original SatSift source code and documentation are licensed under the [Apache License 2.0](LICENSE), with project attribution in [NOTICE](NOTICE). [Third-party notices](THIRD-PARTY-NOTICES.md) identify bundled software and its licence sources under [licenses/](licenses/). External data and label attribution remain subject to [separate terms](benchmark/DATA-NOTICE.md).

The source release and its verification are described in [RELEASE.md](RELEASE.md). Release assets include the source inventory and a separate verification receipt. Publication makes the reviewed source available for research and technical evaluation. Independent astrodynamics review and human assistive-technology testing remain outstanding for external qualification.
