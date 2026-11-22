# Publication review

Reviewed on 22 November 2026 against commit `715e2e60390eb2bc8df36f6fb8d136f20805d2e1`. This review covers the browser workbench, historical-data endpoint, deployment tooling, research pipeline, tests and publication material. It includes executable counterexamples, source inspection and regression checks. It is not an independent operational qualification.

## Decision

The repository remains suitable for research and engineering work. The combined implementation passed fresh-checkout verification, subject to the publication gates in the combined review. The initial publication gate included project licensing and a clean-history candidate. The later licensed source release addresses those decisions through [the release procedure](../RELEASE.md), [bundled-software notices](../THIRD-PARTY-NOTICES.md) and a separate verification receipt. Workbench 3.4.3 and 3.4.4 address the catalogue-metadata and TLE round-trip findings below. Workbench 3.4.5 and maintained evaluation version `case-statistics-v2` repair event assignment under scoring version `event-matching-v2`. Workbench 3.4.6 and maintained evaluation version `case-statistics-v3` enforce strict benchmark truth timestamps under scoring version `event-matching-v3`. Maintained materialiser 2.0 repairs record selection and upstream response validation for separately produced data. The separate `case-statistics-v4` evaluator corrects elapsed exposure and uncertainty reporting where explicit support evidence exists, while retaining v3 calibration calculations. Historical exposure estimates, limited independent evidence and the remaining precision limits still constrain stronger reproducibility or operational claims.

The experimental physics-ML v1.0 method detected **0 of 41** documented confirmatory intervals and failed its predeclared gate. The public application remains detector 0.4. None of the counterexamples below demonstrates that the frozen study's aggregate values or final decision change. Any corrected evaluation must have a new version and retain the original record.

## Completed publication cleanup

- Reorganised the README around installation, use, scientific status, verification and deployment.
- Replaced internal numbered work labels with descriptive component and evaluation names in documentation, scripts, tests, workflows and result metadata.
- Replaced site-specific deployment paths and the personal SSH alias with validated local configuration. Renamed the routing template to `deployment/site-root.htaccess`.
- Retained the deployment allowlist, strict host-key verification, symlink checks, release lock, backup, rollback and hash checks. Missing local configuration stops deployment before a connection is attempted.
- Corrected stale research status and clarified that the confirmatory set has been consumed.
- Added the verified historical research environment and explicit limitations of exposure and uncertainty estimates.
- Made scientific-fingerprint checks independent of private Git history and made the stored-result audit read-only by default.
- Recorded eight editorially reissued artefacts in `research/PUBLICATION-EDITION.json`. Original and publication hashes are both retained. Exact allowed text/key/hash substitutions were checked against the source tree; predictions, array ordering, numerical values, gate criteria and the negative decision were unchanged.

No live service was deployed or probed for the original review. The application algorithm and historical numerical results were not repaired or recomputed in that initial documentation pass.

## Priority repairs

### Preserve catalogue metadata during input round trips

**Fixed in Workbench 3.4.3. Original finding retained below.**

In the reviewed source, `recordToOmm` in `app-3.4.js` exported an `ELEMENT_SET_NO` even when the original field was absent. The parser's internal fallback of 999 consequently became an apparently supplied catalogue identifier after export and reimport. A later corrected record with set number 10 could then be discarded as older.

The counterexample uses an original mean motion of 15.5 and a corrected value of 15.6. Before normalisation, the correction wins. After normalisation, the obsolete 15.5 record wins. Append operations and saved packages both use this normalisation path.

Workbench 3.4.3 preserves absent identifiers and explicitly supplied values, including `0` and `999`, marks supplied TLE identifiers as known, retains TLE origin through normalised OMM, and persists metadata-only append updates. Equivalent mixed-format copies retain TLE origin when metadata ties; numerically equal GP identifiers retain explicit conflicts between different orbital solutions. Regression coverage checks OMM, TLE and mixed-format histories, repeated exports, corrections, reversed input order and unresolved conflicts. The original counterexample is covered by `tests/catalogue_metadata_roundtrip_test.js`. Relevant original locations were `app-3.4.js` lines 770-786 and 1054-1055.

This repair cannot infer missing information from older exports that already invented an identifier or lost TLE origin. Reimporting original input is required to recover that information. The separate TLE epoch-precision repair is recorded below.

### Preserve TLE epoch precision and analysis identity

**Fixed in Workbench 3.4.4. Original finding retained below.**

In the reviewed source, the TLE parser truncated fractional-day epochs to millisecond-resolution JavaScript dates, while the initial propagation still used the original TLE. Reopening the normalised OMM package propagated the truncated epoch. The run identifier also used the truncated representation, so it could not distinguish these two inputs.

A synthetic fixture produced identical run identifiers before and after reopening, while SGP4 residuals differed by up to **7.384 metres**. Its event count stayed the same; the demonstrated failure was numerical round-trip consistency and identity.

Workbench 3.4.4 parses TLE fractional-day fields into exact integer microseconds, preserves the original validated pair in `SMD_TLE: {schema_version: 1, line1, line2}` through normalisation and append operations, and evaluates SGP4 at precise elapsed times. Retained pairs are validated against their normalised fields on import. Reproducibility packages declare `package_schema_version: 1`; identifiers declare `run_identity_version: 2`, use the `smd-v2-` prefix and hash the canonical input and propagation contract with noncryptographic FNV-1a 64-bit. Regression coverage in `tests/tle_precision_roundtrip_test.js` checks propagated residuals as well as epoch precision, identity and malformed packages. `tests/tle_precision_reference_check.py` separately checks the maintained propagation path against Python `sgp4==2.27`.

Legacy packages remain importable and can be re-exported with their available normalised records and recomputed current identifiers. Run identity covers numerical input and propagation; report timestamps, latest-element age and freshness warnings are recomputed on reopening. Their missing original TLE precision is unrecoverable and is reported when relevant; the original source must be reimported to restore it. Native OMM model initialisation remains limited to the millisecond-resolution `Date` path in satellite.js, while record ordering and target-epoch evaluation retain microseconds. The repair does not change detector 0.4 thresholds, the historical evaluator or stored research results. Relevant original locations were `app-3.4.js` lines 695-708, 772-774, 1378-1403 and 1490-1518.

### Correct materialiser record selection and response validation

**Fixed in maintained materialiser 2.0. Original finding retained below.**

In the reviewed source, `tools/materialize_benchmark_v1_spacetrack.py` could select an older creation timestamp when the older record had a larger element-set identifier. Reversing the input order changed the selected solution. It also silently removed malformed upstream rows, which could produce an apparently successful but incomplete dataset.

The maintained tool now validates every response row before selection, compares exact UTC instants, and processes complete groups of equivalent epochs. Selection gives priority to a supplied creation timestamp and its UTC instant, then supplied element-set and GP identifiers as exact integers. It rejects conflicting orbital solutions tied at the strongest metadata rank. Superseded weaker alternatives cannot make acceptance depend on input order; equivalent remaining copies use a stable raw-record tie-break.

Malformed JSON, case-insensitive duplicate keys, nonfinite values, non-object rows, reserved local `SMD_*` extensions, invalid orbital or optional metadata, wrong-object data and out-of-window observations fail explicitly. The raw 5,000-record safety limit applies before any boundary exclusion. An observation exactly at midnight after the final requested date is fully validated, then excluded and counted, consistent with the PHP admission boundary. An empty retained history fails. The complete recipe/manifest binding and output destination are checked before authentication.

New outputs declare `materializer_version: "2.0"`, `record_selection_policy` and `response_validation_policy`. The CLI requires a fresh output path, refuses existing output or checksum files, and protects the frozen benchmark output location. The materialiser repair retained Workbench 3.4.4 with detector method 0.4. The frozen recipe, historical protocol, evaluator, source hashes and research results were preserved; no historical collection or experiment was repeated. Offline regressions are maintained in `tests/materializer_validation_test.py`, with current usage documented in [the materialisation guide](../tools/MATERIALISATION.md). Relevant original locations were lines 35 and 50-75.

### Use a specified maximum-cardinality event assignment

**Fixed in Workbench 3.4.5 and maintained evaluation version `case-statistics-v2`. Original finding retained below.**

The reviewed `matchBenchmarkEvents` greedily consumed the closest eligible truth/prediction pair. This could lose valid matches. With truth events at hours 0 and 10, predictions at hours 4 and -5, and a six-hour tolerance, the original matcher returned one true positive, one false positive and one false negative. A valid one-to-one assignment has two true positives.

The maintained matchers now maximise matched-event count, then minimise total strongest-point-to-truth-midpoint distance using a residual-network assignment. Eligible pairs retain inclusive interval-overlap rules. Canonical temporal ordering and specified shortest-path ties remove dependence on input order, with temporally identical duplicates treated as interchangeable. Integer microseconds and doubled midpoint costs preserve exact assignment comparisons. Primary delay consistently measures prediction onset minus truth onset; detailed matches retain strongest-point delay separately.

The assignment correction introduced `scoring_version: "event-matching-v2"`. That release used browser report schema `smd-event-benchmark-report-v4` and `smb-v2-` identifiers; its maintained Python reports included `evaluation_version: "case-statistics-v2"`. `tests/event_matching_test.py` provides an independent exhaustive oracle, targeted counterexamples, permutation checks and browser/Python parity. The [maintained matching contract](../research/EVENT-MATCHING.md) specifies precision and tie rules. The subsequent strict truth-timestamp repair is recorded below.

The archived historical evaluator retains its greedy assignment and the original counterexample. Frozen result bytes, protocols, hashes, operating points and the failed gate were not changed or recomputed. Relevant original location was `app-3.4.js` lines 3229-3267.

### Validate benchmark truth timestamps consistently

**Fixed in Workbench 3.4.6 and maintained evaluation version `case-statistics-v3`. Original finding retained below.**

The reviewed benchmark truth boundaries used bare JavaScript `new Date`. An accepted timestamp without a timezone moved by four hours between UTC and America/New_York in the reproduced fixture. Calendar rollovers and non-string values were also insufficiently constrained.

The maintained browser and Python truth parsers now require a complete timestamp string with uppercase `T`, an explicit `Z` or numeric offset, valid Gregorian date and clock fields, and at most six fractional digits. Parsing uses exact integer microseconds and rejects locale formats, values without a timezone, surrounding whitespace, non-string values and invalid offsets. The UTC-normalised year must remain within 0001 to 9999. An omitted end denotes a point event; a supplied invalid end is rejected. Ordering is checked after UTC conversion, including differences within one millisecond.

The scoring contract advances to `event-matching-v3` and `case-statistics-v3`, retaining earlier reviewed fingerprints. The maximum-cardinality assignment algorithm is unchanged. Browser report schema v4 and the `smb-v2-` prefix remain, with the new scoring version included in the identifier. General orbital input parsers and historical verification keep their separate contracts.

`tests/benchmark_timestamp_test.py` checks admission, exact normalisation and scoring across UTC, America/New_York, Europe/Berlin and Asia/Kolkata. The original read-only diagnostic reports rejection of the ambiguous fixture in the maintained implementation. No frozen input or result was rewritten or rescored. Relevant original location was `app-3.4.js` lines 3143-3146.

### Admit requests before allocating locks and workers

**Fixed in the maintained history endpoint. Original finding retained below.**

The reviewed `history.php` created a persistent per-object lock and entered blocking `flock()` before the rate-limit check. Rejected requests could therefore create additional lock files, and concurrent requests for a slow object could occupy workers before admission. One admitted request could also trigger several upstream calls when coverage was fragmented, although the quota was charged once.

The endpoint now admits incoming requests before object state, uses 64 fixed lock stripes with bounded waits, and serialises cache misses under a fixed download/storage lock. It preflights the whole missing-range plan and charges each attempted login or history query separately. Response bytes, aggregate upstream time, control files, directory scans, object size and retained storage are bounded. Failed downloads leave previously stored history unchanged; capacity rejection does not evict it.

`tests/history_admission_test.py` exercises admission, concurrency, quota and resource failures against an isolated loopback upstream. Existing history boundary, integrity and overlap tests retain their coverage. The [deployment guide](../DEPLOYMENT.md#history-endpoint-limits) documents the shared-directory requirement, conservative capacity headroom, worker drain and legacy-quota cooldown. The browser, detector and evaluation versions remain unchanged. Relevant original locations were lines 663-676, 703-705 and 732-744.

### Define provider-compliant correction handling

**Correction policy and acquisition provenance implemented in Workbench 3.4.7. Original finding retained below.**

Covered historical dates did not expire or revalidate, and the response's `retrieved_at` was the current serving time even on cache hits. The browser discarded the acquisition metadata. Later catalogue corrections or delayed records could remain absent, while exported analyses lacked a stable source-snapshot identity.

The maintained endpoint preserves historical coverage and distinguishes `served_at` from recorded acquisition times. New schema 2 caches bind acquisitions and update time to their full-store digest. Legacy acquisition times remain unknown, including after an extension. Browser analysis JSON and packages retain versioned source lineage and a separate normalised-input fingerprint; import and append paths validate metadata before changing state.

The [history retention and correction policy](../HISTORY-POLICY.md) follows the published [Space-Track guidance](https://www.space-track.org/documentation) and [CelesTrak usage policy](https://celestrak.org/usage-policy.php). Current GP snapshots use the existing two-hour local cache and validated append path. Historical corrections use an authorised local source and a separately retained analysis package. There is no automatic historical expiry or refetch, and browser corrections do not silently mutate the server cache. Retrospective provider corrections therefore remain an explicit maintenance responsibility.

Offline endpoint and browser provenance regressions cover acquisition times, content identities, legacy migration, integrity, append/reopen behaviour and failure preservation. Frozen research inputs remain separately identified and unchanged. Relevant original locations were `history.php` lines 699-700 and 746-758.

## Research limitations requiring a new evaluation version

### Measure covered elapsed time explicitly

**Corrected in the separate `case-statistics-v4` retrospective evaluator. Original finding retained below.**

`research/comparison_v1/run_comparison.py` estimates covered exposure from the fraction of scored rows multiplied by the full case duration. It does not integrate covered timestamp intervals. For a 30-day history, changing the valid-row fraction from 0.50 to 0.99 changes the reported denominator from approximately 0.492813 to 0.975770 object-months, regardless of where those records occur in time.

This can distort false-event rates with irregular sampling. The frozen reports retain the original calculation, now described as a row-based approximation. The [elapsed-time contract](../research/ELAPSED-EVALUATION.md) was defined before implementation. The v4 evaluator measures the union of supported source intervals, checks an explicit gap limit before clipping, and reports elapsed abstention and unobserved time separately. Duplicate and resampled intervals cannot inflate duration. Missing temporal evidence makes exposure unavailable. Existing v3 calibration and operating-point calculations remain unchanged.

### Qualify zero-width false-event uncertainty intervals

**Qualified in the separate `case-statistics-v4` retrospective evaluator. Original finding retained below.**

The satellite bootstrap returns a zero-width interval when every resampled quiet case has zero observed false events. An executable example with only 14 days of quiet span and 5% coverage returned `[0, 0]`. That interval does not provide a positive upper bound on unseen event risk.

The v4 evaluator reports actual measured exposure, resamples whole object clusters, and identifies insufficient or degenerate uncertainty. It does not present the all-zero resampling result as a zero-width inferential interval. A supplementary one-sided zero-event Poisson upper bound is explicitly conditional on unverified assumptions. Unknown or zero exposure cannot produce a rate or bound. No revised analysis of the stored research data was performed.

### Exercise the neural implementations and length boundary

**Addressed through the opt-in `neural-execution-v1` interface and a bounded CPU suite. Original finding retained below.**

Current permanent tests exercise the robust linear research model, while the neural implementations are not run in CI. The Transformer has a positional embedding for 1,024 rows and indexes it using unrestricted input length. No boundary check or causal windowing is present. The overlength issue is established by source inspection; it was not executed with PyTorch during this review.

The new suite executes GRU, TCN, Transformer, LSTM and sequential-autoencoder fitting and inference on deterministic synthetic data. It checks finite outputs, trained weights, ordering, missing data, gaps, causal properties and the 1,024-row boundary. The versioned interface separates trusted segments and explicitly rejects overlength Transformer segments before computation; no history is silently truncated.

The dedicated CI job and local runner have explicit time limits and record actual environment, seed and model provenance. The [execution contract](../research/NEURAL-EXECUTION.md) distinguishes predictive distributions from current-window reconstruction. Original neural source and historical factories remain unchanged, with their legacy limitations documented. Frozen results, thresholds, the failed gate and run lock are preserved. These checks do not retrain or retune the confirmatory experiment or imply improved detection performance.

## Browser source organisation

The maintained browser implementation now separates orbital input, benchmark evaluation, provenance/packages, propagation/detection and interface state, with shared utilities and a small composition script. All 191 original function bodies and scientific constants are retained. The synthetic equivalence fixture was captured before extraction and checks the runtime functions, analysis, exports, packages and run identities.

Canonical module sources are admitted explicitly. The local server and shared-hosting deployment use content-addressed public filenames and integrity metadata, while the legacy application URL can load the declared modules for an older cached document. Deployment installs assets and routing before publishing the document. Source, configuration, research and verification paths remain outside the public route map.

The existing detector, input-maintenance and scoring fingerprints keep their expected values and mutation checks. The historical archive and failed confirmatory result are unchanged. No live deployment was performed for this refactor. See [the browser architecture](../BROWSER-ARCHITECTURE.md).

## Combined verification repairs

The final fresh-checkout review found an accepted TLE catalogue-identity counterexample. Standard Alpha-5 identifiers could be parsed as TLE text but were exported as nondecimal OMM `NORAD_CAT_ID`, leaving the saved package unable to reopen cleanly. Leading zeros in otherwise decimal identities made mixed TLE/OMM histories appear to contain different objects. Workbench 3.4.8 canonicalises both formats, preserves original TLE lines, and validates older TLE-derived Alpha-5 exports without accepting Alpha-5 values as native OMM. A dedicated regression covers Alpha-5 vectors, zero-padding, repeated export/reopen and mismatched retained lines.

The review also found that the retrospective evaluator accepted a verified-quiet case containing truth, an event-evidence case without truth, or an unrecognised label. `case-statistics-v5` rejects these inputs; its reviewed fingerprint is separate from v4. Detector and event matching algorithms, calibration and the historical evaluator remain unchanged. Encoded private route paths were also checked against the local explicit allowlist; they remain inaccessible. The live Apache deployment was not tested.

For the consolidated evidence, see [the combined verification](COMBINED-VERIFICATION.md). Original counterexamples remain below.

## Publication decisions

### Keep the development history private

Current-file cleanup does not erase earlier commits, branches, pull-request descriptions or deleted historical files. The privacy audit found the former deployment-folder name in 67 distinct historical blobs. Historical pull-request descriptions also retain internal work labels.

The preferred publication route is a fresh repository or source snapshot containing the reviewed tree, with this development repository retained privately. Validate the snapshot independently before publication. Rewriting Git history would also require separate handling of pull requests and other GitHub metadata, and is more disruptive to existing references. No visibility or history rewrite was performed during this review.

### Select a project licence

At the time of this initial review, no root project licence had been selected. The owner subsequently approved Apache License 2.0 and the private repository name SatSift. The root [LICENSE](../LICENSE) and [NOTICE](../NOTICE) record this decision; third-party and data-specific terms remain separate. The later public source release uses the clean-history procedure and separate verification receipt described in [RELEASE.md](../RELEASE.md).

### Retain independent qualification work

External astrodynamics review and human assistive-technology testing remain outstanding. Browser automation and synthetic physics checks cover useful implementation properties, but do not replace those assessments.

## Reproducing the runtime findings

From the repository root:

```sh
node review/reproduce_runtime_findings.js .
```

This diagnostic reads the application in an isolated Node VM and exercises the four original browser findings. It does not make network calls or change source files. Its outputs are review diagnostics rather than a passing release gate. The catalogue, TLE and event-assignment findings now have maintained regressions in `tests/catalogue_metadata_roundtrip_test.js`, `tests/tle_precision_roundtrip_test.js` and `tests/event_matching_test.py`.

## Verification record

All **32 verification stages** from both repository workflows passed locally using fail-fast shell execution, including PHP boundary and concurrency checks, independent SGP4 fixtures, frozen research checks, deployment safeguards and publication-edition hashes. All **16 desktop/mobile browser tests** passed. The read-only audit reproduced the stored evaluation summaries, confidence intervals, regime results, rankings and failed gate for all 16 methods.

A separate source snapshot with no inherited Git commits passed repository integrity, publication-edition, scientific-fingerprint and stored-result audit checks. Targeted scans of the publication tree found no remaining private deployment-folder or numbered authoring-label matches. These verification counts describe the original review. Its four browser counterexamples were reproduced separately. The catalogue-metadata, TLE precision, materialiser, maintained benchmark-assignment, truth-timestamp and history-admission findings are now repaired. The maintained workbench also implements the documented correction policy and acquisition-provenance contract. No historical confirmatory experiment was rerun.

## Clean source release follow-up

The subsequent source-release review reproduced and repaired an Apache percent-encoded namespace bypass, an order-dependent mixed TLE/OMM ambiguity count and malformed browser matching-tolerance coercion. Workbench 3.4.9 records the input changes while preserving the existing detector and matching algorithms. The actual Apache regression and source-only export verification are recorded in [the clean release assessment](CLEAN-RELEASE-VERIFICATION.md).

A new targeted privacy scan at baseline c1a2efb7aceae4cbf5ee7ca96b447f430dffd43c found no selected private-path, authoring-label or recognised-secret matches in its 256 current files. Its reachable-local-history scan found the former hosting name in 60 blobs. That count describes the objects and exact matching rule visible in this later scan; the earlier 67-blob record above has its own review basis. Private historical metadata is excluded from the candidate rather than rewritten.
