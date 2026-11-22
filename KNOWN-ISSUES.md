# Known issues and research limitations

The repository is a research screening workbench. Its engineering checks and frozen result records support technical review; operational qualification and several research limitations remain open.

## Confirmatory result and support limits

The completed evaluation compared 16 predeclared methods on 12 satellite-disjoint confirmatory objects, 41 documented event intervals and two verified-quiet controls. Physics-ML v1.0 produced 0 TP and 41 FN, recall 0 and F1 0. Its predeclared gate failed, and it is not integrated into the public workbench. Detector 0.4 remains the public method. See the [final results](research/confirmatory_v1/RESULTS-v1.0.md) and [integration decision](research/confirmatory_v1/INTEGRATION-DISPOSITION.md).

The v1.0 confirmatory partition is consumed. A tuned successor requires a new declared protocol and a genuinely new satellite-level holdout.

The final selective/physics stack requires at least three independent verified-quiet reference satellites per orbit regime. The available benchmark qualifies LEO only. MEO, GEO and HEO remain unsupported and abstain. The development physics stage recorded `0/36` event detections despite a PU ranking statistic of `0.866013`; that ranking improvement did not establish useful detection performance.

## Maintained catalogue and identity limitations

Workbench 3.4.9 validates and canonicalises numeric and Alpha-5 TLE identifiers, while retaining original source lines. Recovering original TLE identity or lost precision requires retained validated source lines. Valid legacy normalised records can still reopen with their available information; missing source details cannot be reconstructed. Alpha-5 is a TLE encoding; native OMM requires a decimal `NORAD_CAT_ID`. TLE Alpha-5 has a finite numbering range, so use OMM for larger catalogue numbers.

## Maintained benchmark limits

The maintained workbench and Python evaluators use `event-matching-v3`, which maximises matched-event count and then minimises total strongest-point-to-truth-midpoint distance. Primary detection delay uses event onset. See the [matching contract](research/EVENT-MATCHING.md) for exact arithmetic, canonical ties and report versions. These engineering corrections do not establish new detection-performance results.

Benchmark truth now requires the strict explicit-zone timestamp format in the matching contract. Legacy files containing dates without a timezone, locale dates, invalid calendars or more than six fractional digits are rejected. Correct them using the source's actual timezone and precision. The repair does not alter the general OMM/TLE parsers, legacy Python prediction-time parsing or the native OMM model-initialisation precision limit.

An explicit browser matching tolerance must be a finite JSON number in [0, 168]; only an omitted value defaults to 24 hours. Legacy files using strings, nulls or other coercible values now fail admission. Exact-epoch catalogue representatives are resolved before near-epoch comparisons, removing the former order-dependent ambiguity flag without accepting genuinely unresolved conflicts.

## Corrected elapsed-time evaluation

The separate `case-statistics-v5` path implements timestamp-based exposure and explicit uncertainty statuses under the [elapsed-time contract](research/ELAPSED-EVALUATION.md). It requires declared observation windows, a maximum gap and the method's support decisions. Old result files often lack that evidence, so corrected elapsed rates cannot be recovered from their row fractions or spans alone. Version v5 also rejects contradictory event/quiet/unknown labels before evaluation; the earlier v4 implementation and reviewed fingerprint remain identifiable. The supplementary zero-event Poisson bound has unverified model assumptions and does not establish operational risk.

Existing v3 research calibration and training paths retain their original calculations and operating points. Their exposure estimates remain subject to the limitations below. A new retrospective report does not restore an untouched holdout or revise the frozen gate.

## Historical statistical limitations

- **Greedy event assignment can lose valid matches.** The archived evaluator retains its original closest-pair selection. Maintained assignment is corrected under a new scoring version; frozen metrics remain the original record.
- **Exposure uses a fraction of records.** The research code estimates covered quiet exposure by multiplying case duration by the fraction of scored rows. It does not integrate eligible timestamp intervals. Irregular sampling can therefore distort the reported object-month denominator and false-event rate. The historical results and v3 calibration code retain this calculation. The separate v4 evaluator requires measured source intervals and an explicit gap policy; sufficient supporting evidence and a new protocol remain necessary for any new study.
- **A zero-event bootstrap can return a zero-width interval.** If every resampled quiet case contains zero false events, the satellite bootstrap returns `[0, 0]` for the observed rate. This does not establish zero population risk. The v4 evaluator identifies this degeneracy and supplies a separately labelled conditional zero-event bound where exposure is known. Future studies still need sufficient independent quiet exposure and justified uncertainty assumptions.
- **Quiet evidence is limited.** The confirmatory set has only two verified-quiet controls. The final selective-model calibration was supported by one LEO quiet satellite, Aqua, over `0.4665623499247091` estimated covered object-month. These samples do not establish a strong operational false-alarm claim.
- **Public event evidence is incomplete.** Unmatched predictions on event-evidence histories remain unscored under positive-unlabelled semantics. Scheduled notices do not independently prove executed burns. Report precision and F1 with these qualifications.

These limitations describe the existing experiments. They do not change the frozen metrics, operating points or failed gate.

## Integrity and availability

The integrity study applied 12 deterministic stress conditions to 18 non-confirmatory cases, producing 234 case variants and 8,439 causal rows. Its findings apply to those tested transformations and do not establish formal adversarial robustness or operational cyber assurance.

A legitimate corrected catalogue record can move the held-out Aqua history outside the frozen support region. The earlier physics anchor had coverage `0.527778`; the final integrity clean run scored 37 of 72 rows, giving coverage `0.513889`, and the corrected-record stress reduced that coverage to zero. The frozen policy was not relaxed after observing this failure. See the [integrity results](research/integrity_v1/RESULTS-v1.0.md).

Legacy history caches without a full-store digest receive structural validation. Version 2 stores also bind acquisition metadata and update time to the full-store digest. A legacy cache hit preserves its bytes and reports unknown acquisition times. These hashes detect local inconsistency; they do not establish cryptographic authenticity of upstream orbital data.

Historical coverage is retained without automatic refetch. Later provider corrections can therefore require the explicit [correction workflow](HISTORY-POLICY.md#applying-a-correction). Current-GP snapshots cannot reconstruct every missed or retrospectively corrected observation. Browser source lineage identifies contributing acquisitions after a merge, without claiming a verified per-record attribution. Local file import time is not upstream retrieval evidence.

## Research execution limits

The separate `neural-execution-v1` interface has bounded CPU execution tests for all five neural architectures. It validates sequence metadata, breaks state at invalid rows and declared gaps, and rejects Transformer segments longer than 1,024 rows. See the [execution contract](research/NEURAL-EXECUTION.md). These synthetic tests cover specific implementation properties, not detection performance or every possible training configuration.

The original v1 training factories remain unchanged to preserve the historical execution boundary. Their direct neural paths retain incomplete gap handling and an unchecked Transformer position limit. Use the versioned interface and a separately declared protocol for subsequent work; passing the smoke suite does not authorise reuse of the consumed holdout.

The [research environment record](research/ENVIRONMENT.md) documents the verified historical dependency pins. The current tree does not contain a complete platform lock or trained neural checkpoints. Exact raw-history and feature hashes are retained, but querying a live upstream service does not by itself guarantee byte-identical historical inputs.

## External qualification

- [Independent technical qualification](review/EXTERNAL-REVIEW-CHECKLIST.md), including astrodynamics review and disposition of findings.
- Human keyboard and assistive-technology testing, plus any formal accessibility documentation required by an adopting organisation.
- Operator-grade or independently curated event truth before operational performance claims.
- Deployment-specific security and operational-readiness review.

The workbench is not validated for flight safety, conjunction assessment, manoeuvre confirmation or autonomous operational decisions.

## Source release and live deployment

The source release is packaged without inherited Git history. Original source uses Apache 2.0, with separate bundled-software and data notices; see [the release procedure](RELEASE.md). Source publication does not close the external qualification and research limitations recorded above. The Apache template now denies encoded physical-namespace aliases and noncanonical public aliases. These guards have been tested on an isolated Apache server, but the live hosting configuration has not been updated by source preparation.
