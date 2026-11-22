# Clean source release verification

## Scope and disposition

Review date 22 November 2026. The starting private source commit is c1a2efb7aceae4cbf5ee7ca96b447f430dffd43c, following the combined engineering review. This follow-up prepares Workbench 3.4.9 for a source-only release candidate. The candidate's generated SOURCE-RELEASE.json identifies its exact source commit, source tree and complete file inventory.

The development repository remains private. The live website and hosting configuration are unchanged. At the time of this review, project licensing, redistribution and public destination were outstanding. The owner subsequently approved Apache 2.0 and the SatSift repository identity; the development repository remains private. The later source publication is documented in [the release procedure](../RELEASE.md) and its accompanying release receipt. Independent astrodynamics qualification and human assistive-technology testing remain open for external or operational claims.

## Reproduced defects and repairs

| Finding | Reproduction and disposition | Permanent check |
| --- | --- | --- |
| Encoded physical Apache paths expose a synthetic private file | Original template returned HTTP 200; decoded namespace and original request-target guards now deny aliases | tests/apache_route_boundary_test.py |
| Encoded public Apache paths lose intended headers | Original template served an encoded workbench path without CSP, HSTS or nosniff; noncanonical aliases now fail before content routing | tests/apache_route_boundary_test.py |
| Decoding query data accidentally denies a valid route | Independent review of the repair found encoded whitespace in query values triggering the physical-path guard; anchoring to the request target preserves those queries | tests/apache_route_boundary_test.py |
| Malformed benchmark tolerance silently changes scoring inputs | Explicit null, boolean, array, object and string values previously became zero, one or 24 hours; explicit values now require finite JSON numbers in [0, 168] | tests/benchmark_tolerance_test.js |
| Mixed exact/near-epoch records leave an order-dependent ambiguity flag | Exact-epoch representatives are now resolved before near-epoch comparisons, retaining genuine unresolved conflicts | tests/catalogue_revision_test.js |
| Mixed numeric and opaque GP identifiers form a comparison cycle | Decimal and opaque identifiers now have a consistent total order, with exact integer comparison and preserved equal-ID ties | tests/catalogue_revision_test.js |
| Release manifest can carry unreviewed private metadata | Exact schema, content scanning, link/mode validation and trusted commit/tree comparisons now cover the manifest as well as source files | tests/source_release_test.py |
| Release diagnostic can echo a denied value in a filename | Sensitive findings use a stable path digest and withhold the path and matched content | tests/source_release_test.py |

Apache regressions execute the actual root template against synthetic files on an isolated loopback server. They include ordinary and encoded queries, public response headers, canonical redirects, private files, known and unknown assets, symlinks, unrelated site rewrites, encoded-slash handling and rollback compatibility. The original template fails the adversarial cases, establishing that the new tests detect the defect. No live server or production configuration was probed.

The TCN layer-count concern was checked against the implementation: the execution interface forwards the layer count and the network builds that number of causal blocks. No repair was required.

## Scientific and software preservation

Detector method 0.4, event-matching-v3, package schema 1 and run-identity algorithm 2 remain the maintained contracts. Workbench 3.4.9 versions the input-admission changes. Prior maintenance and scoring fingerprints remain recorded alongside the reviewed current values.

The original browser-equivalence fixtures remain intact. The new fixture records the current production-source hashes. The comparison also rebinds only release identity inside an isolated test VM and requires complete synthetic analysis, export and reopening hashes to agree with both earlier fixtures.

Historical evaluators, raw-data recipes, recorded results, publication-edition hashes, archived scientific source surfaces, the failed 0 TP / 41 FN gate and one-shot lock remain evidence of record. No source histories were fetched, research thresholds selected, stored cases rescored or confirmatory experiment rerun. Bounded synthetic neural fits are engineering tests.

## Privacy boundary

The independent baseline audit examined all 256 tracked regular files and found no selected private hosting-name, personal-path, numbered authoring-label, private-key or recognised-token matches. Generic deployment fixtures and legitimate bundled upstream notices were retained.

The same audit inspected 515 reachable local commits, 917 blobs and 1,269 trees. It found the former hosting name in 60 blobs and ten trees, personal paths in five blobs, numbered authoring labels in 174 blobs and 122 commits, and generator references in three blobs. These are scoped local counts, distinct from the earlier review's historical count.

All 20 visible pull requests, numbers 7 through 26, were inspected. Six earlier pull requests contain numbered authoring labels. No issue comments, inline review comments or review submissions were returned. Unavailable remote refs, unreachable objects, workflow logs, attachments, releases and other service surfaces were not comprehensively scanned.

The assembled 273-file source tree also passes the targeted scan, including the owner-specific private deny-list. The candidate excludes Git history and service metadata entirely. Current-source scans cover selected patterns and an owner-specific private deny-list; they do not certify the absence of every encoded or unknown secret.

## Redistribution evidence

The two vendored browser files and their existing top-level licences remain unchanged. Eight additional full component notices and a source/hash inventory cover the components named in Plotly's preserved licence trailer. Seven are exact archive-member copies; the Native Promise Only notice records its source-header attribution and the separately documented MIT-text transcription.

The companion data notice now supplies an explicit external-label licence link, adaptation attribution and verified provider acknowledgements. Frozen manifests and numerical artefacts were not edited for these additions. That initial [third-party notice inventory](../THIRD-PARTY-NOTICES.md) covered the eight trailer entries. The subsequent publication review expanded the component and source-attribution coverage described below.

## Candidate verification record

All **56 local workflow command groups passed** on the assembled source checkout, covering the two repository workflows and bounded neural job. All **19 Playwright tests passed with retries disabled**. The added executable Apache suite has **nine tests**, the source-release suite has **13 tests**, and the catalogue suite checks **102 permutations** in addition to transitivity and antisymmetry. Strict tolerance regression covers the omitted default, valid numerical boundaries and 19 malformed explicit values.

The workflow-equivalent run reused the existing isolated dependency environments after checking the declared pins and pip consistency. The local Apache installation and required modules were checked in place of Ubuntu package installation. The actual test commands ran; package setup and operating system equivalence are qualified. Local Apache execution used macOS Apache 2.4.67. Hosted jobs and Linux execution must not be inferred from these results.

All **59 files in the original frozen evidence manifest** retain their recorded SHA-256 values. A further comparison of **88 selected research implementation, data, result, original-oracle and vendor files** confirms byte identity with the review baseline; these sets overlap. Earlier scientific source pins remain in the version guards. The two npm manifests change only their release-version fields from 3.4.8 to 3.4.9.

The source-release manifest records the exact candidate commit and tree. The accompanying release receipt records the archive checksum and independent inventory, privacy and extracted-source verification. The distributed source is kept untouched; test outputs are confined to a separate extracted copy. A passing local result is not a claim that hosted CI executed successfully.

## Release decision

The original source archive was a conditional candidate before licence selection. The later Apache 2.0 approval and SatSift naming required a new reviewed source commit and regenerated candidate. The subsequent source publication uses fresh history from that verified snapshot at the approved SatSift destination. Any live deployment requires the updated routing template and deployment-specific verification.

## Publication notice review

The final source-publication review traced the exact Plotly 3.3.1 distribution through the outer build, MapLibre, Mapbox and StackGL components. The [resolved inventory](../licenses/PLOTLY-COMPONENTS.json) records 400 package/version or pinned-commit attribution entries and 406 distinct notice files. It explicitly distinguishes source mappings from conservative dependency coverage where prebuilt bundles omit source paths. Additional source credits and exceptional notice sources are retained and documented. The [third-party notice](../THIRD-PARTY-NOTICES.md) records the reviewed scope and redistribution requirements.

The publication adds notice files, integrity checks and public-facing documentation. Bundled executable assets, detector code, frozen evidence, original source fingerprints and stored scientific results retain their prior bytes. The release receipt records the final public commit, source tree, archive checksum and the actual verification performed on the source and extracted package. The original development history remains private.
