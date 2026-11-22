# Release notes

## SatSift project identity

SatSift is the name of this research-screening workbench and the public source repository `sylvesterkaczmarek/satsift`. Original source code and documentation are licensed under [Apache License 2.0](LICENSE). The GitHub description, topics and npm package metadata use the same name. The existing hosted URL and its physical deployment route are retained for compatibility. This naming and licensing update does not change detector 0.4, Workbench 3.4.9, stored evaluations or the consumed confirmatory partition.

The first public source release uses a new repository with one initial commit. The original development repository, earlier commits and service records remain private. The publication adds no new detection-performance claim and does not update the live website.

## Workbench 3.4.9

### Input admission and deterministic catalogue resolution

Exact-epoch catalogue groups are resolved before near-epoch comparisons. A later equivalent TLE record can no longer leave an order-dependent ambiguity count after the representative has been enriched. Genuine unresolved orbital conflicts remain grounds for abstention.

Catalogue precedence is creation timestamp, known element-set number, then GP identifier. Supplied decimal GP identifiers outrank opaque identifiers; decimals compare as exact integers and opaque strings use locale-independent lexical order. Equal numeric identifiers remain tied. This defines deterministic selection and does not establish provider chronology for opaque identifiers.

Explicit browser matching tolerances must be finite JSON numbers between 0 and 168 hours inclusive. Omission retains the 24-hour default. Values such as null, booleans, arrays, objects and numeric strings are rejected rather than silently converted. The matching algorithm remains event-matching-v3.

The reviewed maintenance surfaces have new current fingerprints while the previous values are retained. Original browser-equivalence fixtures remain byte-identical; a separate 3.4.9 fixture records the permitted admission and release-identity changes. Detector 0.4, package schema 1, run-identity algorithm 2 and the frozen research evidence remain unchanged.

### Apache routing boundary

The root deployment template now rejects percent-encoded or normalised aliases that could expose the physical source directory or serve a public page without the intended response headers. Literal public routes, encoded query values, immutable browser assets, unrelated site routes and retained rollback compatibility remain supported. The HSTS documentation now describes the proxy-aware header behaviour accurately.

The executable Apache suite uses synthetic files and an isolated loopback process. It demonstrates the former bypass against the original template and passes against the repaired template. This source change has not been deployed to a live server.

### Source packaging and attribution

A deterministic source exporter reads a clean committed Git tree, preserves file bytes and modes, records a per-file inventory and rejects unexpected or sensitive content. It creates an archive without inherited history or local configuration. Independent verification reconstructs the source tree hash without requiring the private development repository.

Bundled component notices and external-label/provider attribution have been added in companion files, preserving all vendored and frozen scientific bytes. The reviewed source is distributed with a file inventory, checksum and verification receipt. See [the release procedure](RELEASE.md) and [verification record](review/CLEAN-RELEASE-VERIFICATION.md).

### Portable browser verification

Browser equivalence now executes the exact original 3.4.7 application beside the maintained modules in each runtime. Complete analyses, exports and reopened results must match exactly for all seven synthetic cases and all three release identities. The original v1/v2/v3 fixtures and source pins remain unchanged, with their recorded numerical hashes additionally required on their documented Node 26 macOS ARM64 profile. This resolves runtime-dependent numerical hash failures in Node 22 verification without introducing tolerances or changing production calculations; altered source and dependency wiring remain rejected. See [the runtime verification boundary](BROWSER-ARCHITECTURE.md#exact-comparisons-across-runtimes).

## Workbench 3.4.8

The combined implementation was independently checked from a fresh source worktree on 22 November 2026. At that review, the maintained engineering candidate was in the **private development repository**, pending a separate clean-history publication release. No live deployment or model retraining was performed.

### Catalogue identity and saved packages

- Standard five-character TLE catalogue numbers and Alpha-5 fields now resolve to canonical decimal NORAD identities, including names with leading zeroes. For example, `A0000` resolves to `100000` and `Z9999` resolves to `339999`.
- Native OMM `NORAD_CAT_ID` remains decimal. TLE-derived OMM exports retain the exact validated source lines, and older TLE-derived exports with an Alpha-5 field can reopen only if the retained source lines agree with the visible orbit and identity metadata.
- The original source lines and integer-microsecond epochs remain the propagation input. The parser rejects unsupported Alpha-5 letters, malformed catalog fields and mismatched retained TLE lines before applying an import.
- Import, append, normalisation, package reopening and corrected catalogue selection use the same numeric object identity. No unsupported package schema or new detector threshold was introduced.
- Workbench 3.4.8 identifies the input-admission change. Detector method 0.4, `event-matching-v3`, reproducibility schema 1 and run-identity algorithm 2 are preserved. Release identity changes are explicit in new run identifiers.

### Maintained retrospective evaluation

- `case-statistics-v5` retains the separately implemented `case-statistics-v4` elapsed-time exposure and qualified uncertainty calculations. It now validates that only `event-evidence`, `verified-quiet` or `unknown` cases are scored and that truth events agree with these labels.
- Contradictory label/truth combinations and unrecognised label values are rejected before scoring, including in unselected splits and non-primary methods.
- Both reviewed v4 and v5 source fingerprints remain in the maintained version guard. Earlier v1-v3 research calculations and the historical evaluator remain independent and unchanged.
- Historical case-level outputs omit the explicit source-interval and method-support evidence required to reconstruct covered elapsed exposure, so **no revised quiet-event rate or new confirmatory claim was calculated**. Missing data remain unavailable.

### Prior engineering work retained

The maintained tree also includes the catalogue-metadata, TLE-precision, materialiser-validation, event-matching, truth-timestamp, history-admission, correction-provenance, duration/uncertainty and neural-execution repairs. Browser code is organised into six modules with explicit content-addressed assets and a backward-compatible bootstrap, without requiring a framework or build step. The historical negative physics-ML integration decision remains **0 detected events out of 41**, with the original frozen gate failed.

### Verification and research limitations

The [combined verification](review/COMBINED-VERIFICATION.md) records the independently reproduced counterexamples, regression coverage, local workflow results and protected-file checks. The original 3.4.7 browser-equivalence fixture remains intact; the updated fixture records the reviewed 3.4.8 input changes and verifies unchanged scientific functions, numerical cases and matching.

No Space-Track or live CelesTrak history was newly collected. Original experimental methods were not retuned or rerun. The TLE Alpha-5 scheme is limited to 339,999, and native OMM numerical initialisation retains the documented millisecond limitation of satellite.js. Legacy packages without retained TLE lines cannot restore missing original precision or other missing metadata.

The workbench remains for **research screening**, with no operational certification. At that review, manual assistive-technology testing, external astrodynamics qualification, source-redistribution review and an approved clean public-history candidate were outstanding publication or operational gates. The later source release closes the source-publication work; external qualification remains outstanding.

### Publication state

At the time of that review, the source repository remained private and the live website and hosting configuration were unchanged. Hosted execution was unavailable for that verification; its recorded results are local. The later source publication retains that historical verification scope. External qualification and any later deployment remain separate.
