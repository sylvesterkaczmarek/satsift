# Browser architecture

## Entry points and responsibilities

SatSift uses plain JavaScript module factories and a small composition script. All browser source files are checked in and run directly. Local startup remains `python3 tools/serve_workbench.py`; no framework, compiler or bundler is required.

| Source | Responsibility |
|---|---|
| `app/common.js` | Shared constants, detector profiles, numeric helpers and formatting utilities. |
| `app/orbital-input.js` | TLE and OMM parsing, exact epoch handling, catalogue normalisation and deterministic synthetic orbital histories. |
| `app/benchmark.js` | Benchmark admission, strict truth timestamps, event assignment and summary calculations. |
| `app/packages.js` | Normalised exports, reproducibility-package validation and acquisition provenance. |
| `app/detection.js` | Propagation, feature construction, calibration, screening and candidate-event grouping. |
| `app/interface.js` | Mutable interface state, asynchronous input tickets, loading, charts, downloads and event listeners. |
| `app-3.4.js` | Dependency composition, module-loading compatibility and one-time interface startup. |
| `browser-assets.json` | The explicit ordered source inventory used by loading, serving, deployment and verification. |

Each source registers its factory in the `SMDModules` namespace. Factory construction receives the dependencies it needs. The interface owns application state and supplies the existing analysis-options callback to the detector. Its `start()` method binds events and performs initialisation once. Imports, exports and scientific calculations keep their existing contracts.

These factories are internal application boundaries. A change to their dependency wiring must pass the same behavioural and source checks as a change to the functions they contain.

## Behaviour and version boundary

The modular reorganisation initially retained Workbench `3.4.7` with detector `0.4`, scoring `event-matching-v3`, reproducibility package schema `1` and run identity version `2`. A subsequent reviewed input-admission repair advances Workbench to `3.4.8`, normalising standard Alpha-5 TLE and decimal catalogue identifiers. The earlier v1 equivalence oracle remains unchanged; the v2 oracle pins the reviewed parser and release differences while asserting all other scientific functions and original synthetic numerical decisions. Exact synthetic comparisons cover parsed records, analysis, catalogue decisions, benchmark matching, normalised exports, packages and run identifiers.

Workbench `3.4.9` requires explicit benchmark tolerances to be finite JSON numbers in the inclusive range 0 to 168 hours; only an omitted field defaults to 24 hours. Numeric strings and other coercible values are rejected. Exact-epoch catalogue metadata and TLE source selection now finish before near-epoch OMM comparisons, with a canonical tie order and preserved unresolved conflicts. Detector `0.4`, event matching `v3`, package schema and identity algorithm versions are unchanged.

Catalogue metadata precedence remains creation timestamp, known element-set number, then supplied GP identifier. Decimal GP identifiers outrank opaque identifiers and compare as exact integers; opaque identifiers compare in locale-independent string order. Numerically equal identifiers remain tied, including leading-zero forms. Supplied identifiers retain precedence over absent values. This explicit total order prevents cyclic rankings when numeric and opaque metadata are mixed; it does not assert provider chronology for opaque identifiers.

The v1, v2 and v3 equivalence fixtures retain their original bytes. The v3 fixture identifies the reviewed production source hashes and its baseline commit. The test also retains the exact original 3.4.7 application as an executable oracle. It compares all seven complete synthetic analysis, export and reopening hashes between the maintained modules and that original implementation in the same runtime, with matching release identities. Runtime function checks permit only explicitly reviewed input and presentation functions to differ. The separate v4 presentation fixture pins the 3.5.0 source identities, changed UI functions, release identity and dependency URL metadata; all original fixtures retain their bytes. The strict tolerance admission surface has its own Workbench-specific fingerprint alongside the original scoring fingerprints.

The content-addressed asset names identify the source layout independently of the scientific and saved-package versions. A later change to detector, scoring or input semantics still requires the appropriate version and regression review.

Frozen research artefacts, recorded hashes, the historical evaluator, operating points, the failed confirmatory gate and the one-shot lock remain separate. Refactoring browser code does not authorise another research run.

The project name and GitHub repository slug are SatSift and `satsift`. Workbench 3.5.0 uses `/satsift/` as its canonical public route. Earlier page routes redirect permanently; legacy machine routes, physical deployment storage, asset names and scientific package identifiers remain compatible. Current dependency URLs in new reproducibility packages use the canonical namespace, while recorded acquisition provenance and frozen evidence retain their original references.

## Loading and caching

The document loads the module scripts in their declared order, followed by the composition script. Every new script URL contains a digest of its own bytes, and script integrity metadata binds the response to those bytes. Module files contain no nested script URLs, so changing one file cannot create a cycle in the asset hashes.

The composition script also handles an older cached page that references only `/satellite-maneuver-detector/app-3.4.js`. It loads its exact module set before starting the interface. A failed or inconsistent dependency load produces a reload message and prevents a partially initialised workbench from running.

Canonical sources retain readable filenames such as `app/detection.js`. Public delivery uses names such as `app/detection-<content-digest>.js`. The local server maps only the current declared URLs to those sources. Deployment writes the corresponding immutable files and retains prior public asset versions for already cached documents. The legacy application URL remains an explicit compatibility route.

`tools/browser_assets.py` validates the fixed source inventory and computes asset destinations, hashes and integrity values. `tools/update_browser_assets.py` refreshes the checked-in loading references after source changes and provides a read-only consistency check. These helpers maintain references without compiling the application. Git preserves LF line endings for the browser identity inputs and the equivalence fixture.

After editing a browser source, refresh and verify its references:

```sh
python3 tools/update_browser_assets.py
python3 tools/update_browser_assets.py --check
node tests/browser_module_equivalence_test.js
node tests/browser_module_loader_test.js
```

## Public routing and deployment

Only declared application assets and existing public routes are served. Source-directory URLs, repository metadata, local configuration, research records and verification fixtures are outside the public route map. Module additions must be registered explicitly; a directory wildcard cannot expand the publication boundary.

The Apache routing template keeps the existing same-origin content-security policy. The deployer validates destination paths and introduced files, installs scripts and their routes before publishing the HTML entry, and retains the existing lock, backup, rollback and hash checks. Rollback restores the mutable application entry, document and site content while retaining the approved immutable assets and their narrow compatibility route. This keeps cached documents usable after rollback; automatic asset pruning is excluded. See [DEPLOYMENT.md](DEPLOYMENT.md) for operator commands and configuration. No live deployment is part of the module reorganisation.

## Verification

`tools/load_browser_app.js` executes the real production factories and composition in isolated test contexts. Minimal-DOM tests can construct the workbench without starting its interface. Browser tests exercise the served scripts and cover input changes, superseded asynchronous loads, imports, downloads, charts, keyboard access and mobile layouts.

### Exact comparisons across runtimes

The equivalence fixtures use a fixed clock and synthetic inputs. Their unchanged complete-output hashes have been verified on Node `26.13.1`, V8 `14.6.202.34-node.40`, macOS (`darwin`), ARM64. All four profile fields must match before the test applies those historical numerical hashes; a matching profile must still reproduce every recorded hash exactly. The fixtures remain immutable on every platform.

JavaScript numerical library results can differ at the final binary digit across runtime versions and platforms. For example, `Math.pow(1.0997794692005907, 0.6666666666666666)` returned `1.065459808908431` on Node 22.23.5 and `1.0654598089084313` on Node 26.13.1 on the same macOS ARM64 machine. Those differences propagate into the complete analysis and serialized export hashes. A Linux Node 22 reproduction also reproduced all 28 full-output hash differences seen in CI. The raw inputs, normalised records, settings, run identifiers, counts, flags, classifications and matching decisions remained identical in these checks.

Every runtime executes `tests/fixtures/browser-equivalence-v1/app-3.4.js`, the unchanged 3.4.7 monolith whose SHA-256 is `c8eb05db9c48c1357cdf59e019c82a94c82d4f9150a68291bcfbd0a0e6030098`. The original v1 fixture independently pins this source and the shared satellite.js bytes. Before execution, the test verifies both files and all three fixture hashes, and verifies the current production-source hashes from the v4 presentation fixture. The unmodified historical execution must expose exactly the original 191 function identities and 26 constants.

For each release identity, 3.4.7, 3.4.8, 3.4.9 and 3.5.0, the maintained modules and original application run in separate isolated contexts within the same Node process. The test verifies the original source bytes before rebinding its single release-version literal in memory. The current 3.5.0 application also runs with its native identity and current dependency URLs. Previous-version comparisons inject the matching historical dependency URLs; the 3.5.0 historical comparison rebinds the verified source's two dependency URL literals as well as its single release-version literal. These changes affect release metadata only. Seven synthetic cases compare complete canonical analysis, result-package, download-payload and reopened-result hashes exactly, alongside all case metadata, event matching and invalid-input results. The test applies no rounding, numerical tolerance or alternative accepted hash list.

On that verified reference profile, all three historical full-output fixtures remain mandatory as an additional independent check. On every other profile, all recorded invariant fields, function and constant identities, fixture bytes and source pins remain mandatory alongside the complete same-runtime comparison. Only the four runtime-dependent output hashes in each recorded case use that runtime boundary. A negative check changes the detector's injected CSV serializer while retaining every exposed function body, constant and recorded invariant; the complete-output comparison must reject it. Another negative check rejects altered historical source before execution.

Static fingerprint checks use `tools/browser_source.py` to inspect the canonical sources. The unchanged detector and historical scoring fingerprints retain their expected values. Reviewed input-maintenance and admission changes have additional release-specific pins and mutation checks, with the earlier fingerprints preserved. Historical-verification tests additionally make maintained browser and research sources unavailable, confirming that the archived calculation remains independent.

Before merging changes, run the asset-reference check, focused module checks, existing source and scientific regressions, and the desktop/mobile browser suite. The permanent workflows contain the complete commands. A fresh source snapshot must retain the manifest and canonical module files together with the entry script and verification helpers.
