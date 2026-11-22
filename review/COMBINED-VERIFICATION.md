# Combined verification and publication disposition

## Review basis

Review date 22 November 2026. Baseline `9962713fcf349f74e613d8d68dc6b0becc42069f` is the private source tree immediately following the browser modularisation. The work was inspected in new, clean, isolated worktrees. The combined engineering workflow was run from that fresh checkout, along with offline regression checks and separate runtime, scientific and security inspection passes. The input-admission and evaluation changes below are the subsequent reviewed maintenance candidate, with their own source fingerprints and tests.

This is an engineering and source-publication assessment. No third-party certification, human assistive-technology audit, live deployment test, authenticated data retrieval, research model retuning or new confirmatory experiment was performed. Bounded neural smoke tests included small synthetic fits.

## Adversarial findings and disposition

| Finding | Result | Regression or boundary |
| --- | --- | --- |
| Missing catalogue metadata becomes authoritative `999` | Resolved in Workbench 3.4.3 and retained | `tests/catalogue_metadata_roundtrip_test.js` |
| TLE fractional epoch and saved-package identity diverge | Resolved in Workbench 3.4.4 and retained | `tests/tle_precision_roundtrip_test.js` and Python SGP4 reference check |
| Older Space-Track creation date can outrank correction | Resolved in materialiser 2.0 and retained | `tests/materializer_validation_test.py` |
| Greedy matching loses valid event pairs | Resolved in `event-matching-v2`, maintained in v3 | `tests/event_matching_test.py`, independent exhaustive oracle |
| Ambiguous truth timestamps depend on local timezone | Resolved in `event-matching-v3` | `tests/benchmark_timestamp_test.py` |
| History requests allocate locks before admission | Resolved with bounded admission, quota and resource checks | `tests/history_admission_test.py`, concurrency suites |
| Cached source acquisition time is replaced by serving time | Resolved with distinct acquisition and service provenance | `tests/history_provenance_test.py` and browser regression |
| Row-fraction coverage and zero-width false-rate bootstrap | Versioned elapsed-time evaluator and qualified uncertainty | `tests/elapsed_exposure_test.py`, `tests/elapsed_evaluation_test.py` |
| Neural execution untested; Transformer exceeds 1,024 positions | Opt-in `neural-execution-v1` runs bounded CPU tests and rejects overlength segments | `tests/neural_execution_test.py` |
| Large browser script and asset upgrade boundary | Six modules, content-addressed loading and guarded deployment/rollback | `tests/browser_module_equivalence_test.js` and module/server/deployment tests |
| Accepted Alpha-5 TLE cannot reopen as normalised OMM | Resolved in Workbench 3.4.8, retaining matching original source lines | `tests/catalogue_identifier_test.js` |
| Zero-padded decimal TLE/OMM identifiers split one object | Resolved by canonical decimal object identities | `tests/catalogue_identifier_test.js` |
| Forged legacy retained Alpha-5 source lines | Mismatched source/visible metadata explicitly rejected | `tests/catalogue_identifier_test.js` |
| Verified-quiet truth events and unrecognised label values silently pass retrospective evaluation | Rejected under the reviewed `case-statistics-v5` contract | `tests/elapsed_evaluation_test.py` |
| Encoded route components or private sources bypass local serving | Tested against explicit local route map; requests remain inaccessible | `tests/local_server_test.py` |

Previously reported defects are retained in [the original review](PUBLICATION-REVIEW.md) with reproductions and engineering limits. No change to the published detector 0.4 method, benchmark event-matching rules or the original materialiser was needed during the final combined review.

## Preserved scientific evidence

The historical evaluator stays isolated from maintained browser and Python implementations, including the separate elapsed evaluation code. It must continue to reproduce the stored 16 method summaries, bootstrap intervals, regime blocks, ranking and the **failed** confirmatory gate. The recorded physics-ML result is **0 true positives and 41 false negatives** on the consumed 12-object confirmatory partition. Its one-shot rerun lock remains in force.

The maintained v3 calibration and v4 retrospective fingerprints stay recorded. The new v5 label validation has its own complete reviewed fingerprint. The 3.4.7 original browser-equivalence fixture stays byte-identical; the reviewed 3.4.8 fixture records the permitted parser and release-identity differences and compares unchanged scientific functions, event matching and synthetic numerical outcomes. Retained original TLE lines continue to determine propagation.

## Retrospective comparison feasibility

The retained confirmatory report contains 16 methods with 12 case-level results each, a total of **192 method-case records**. A read-only inspection finds **zero** records with the explicit per-interval method support ledger required by `elapsed-intervals-v1`. Stored row coverage fractions and `span_days` cannot recover the eligible interval unions or safely distinguish missing observations from method abstention. Thus a valid revised exposure denominator, false-event rate or corresponding uncertainty interval **cannot be calculated from those frozen summaries alone**.

The existing count metrics and failed gate remain the historical record. A revised analysis on the consumed confirmatory data would be retrospective and could not establish a new, independent holdout. No existing output was relabelled as v5, and no false precision or zero-risk upper bound is claimed.

## Verification status

The initial clean-checkout run passed **all 52 local workflow command groups**, including PHP concurrency/security, browser equivalence, deployed-route checks, independent SGP4 fixtures, historical evaluator isolation, frozen hashes, and synthetic CPU neural execution. The corrected 3.4.8 candidate passed all 53 workflow command groups and 19 real browser tests with retries disabled. An independent post-run checksum comparison separately verifies the 59 unchanged protected scientific/data files and the two reviewed npm version fields. Test command and source-asset provenance are retained in the repository workflows.

The historical archive, scientific evidence and original data retain byte-identical checksums for 59 protected files. The two npm package manifests are updated only in their declared Workbench 3.4.7 to 3.4.8 release-version fields, with dependency details unchanged. New versioned software tests must not alter the archived calculation, original model outputs or the one-shot lock.

## Publication-readiness verdict

**Historical engineering verdict.** At that review, the corrections were a conditional candidate for a clean public-source release after final regression verification. The private development repository and its historical Git objects are **not** suitable to publish directly; historical blobs and pull-request descriptions contain internal metadata. At that stage, no root project licence had been selected. The later release procedure closes the project-licence and source-publication decisions while retaining the development repository privately.

At that review, outstanding non-code gates included permission/licence and redistribution review for bundled source and data. Independent astrodynamics review, manual human assistive-technology assessment and a deployment-specific security/operational assessment remain necessary before operational reliance. Existing local automation is insufficient to certify these activities. Hosted execution was unavailable for that verification and cannot be described as passing CI.

The live website and authenticated upstream stores were not modified. No spaceflight or autonomous decision-support qualification is implied.

Subsequently, the owner approved Apache License 2.0 for original project code and documentation and selected SatSift for the private repository. Those decisions closed the naming and project-licence questions recorded in this earlier review. The later source publication follows [the release procedure](../RELEASE.md) and has a separate verification receipt. No live deployment or new operational qualification is implied.
