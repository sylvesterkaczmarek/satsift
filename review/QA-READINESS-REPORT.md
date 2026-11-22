# Satellite Maneuver Screening Workbench quality status

## Release assessment

The repository baseline is suitable for external technical evaluation as a research screening prototype. It is not validated for operational SSA, flight safety, conjunction assessment, maneuver confirmation or autonomous decision-making.

## Engineering and research baseline

- UTC-safe OMM parsing with sub-millisecond preservation and deterministic catalogue supersession.
- Same-site authenticated Space-Track historical retrieval with private caching, request limits, cache-integrity validation and tested request coalescing.
- SGP4 common-epoch RTN residual analysis, multivariate element-change signals, orbit-specific profiles and event grouping.
- Fixed-epoch physical regression fixtures independently cross-checked using Python SGP4.
- Explicit abstention for inadequate or inconsistent data.
- Reproducibility exports and deterministic run identifiers.
- Frozen benchmark v1.0 with 40 satellite-disjoint objects, explicit event/verified-quiet evidence and immutable development/calibration/confirmatory partitions.
- Comparison evaluation completed a 16-method comparison suite under common scoring and matching rules.
- Confirmatory evaluation completed the frozen 12-satellite confirmatory evaluation with 41 truth intervals, two verified-quiet controls and satellite-cluster confidence intervals.
- Physics-ML v1.0 failed the predeclared confirmatory integration/publication gate (`0` TP, `41` FN, recall `0`, F1 `0`, mean abstention about `0.9212`) and is not used by the public workbench.
- Integration decision therefore preserved Workbench 3.4 / detector 0.4 and blocked learned-method integration.
- Allowlisted production routing, pinned third-party browser assets, permanent CI and immutable confirmatory freeze tests are in place.

## Verification performed

Permanent CI checks syntax, repository/security integrity, endpoint behavior, catalogue revision handling, cross-time-zone epochs, concurrent history retrieval, benchmark semantics, browser-style workbench regressions, independent SGP4 fixtures, JSON validity and vendor fingerprints.

The separate permanent frozen-result workflow verifies the confirmatory result hash, run lock, provenance/audit artifacts, confirmatory authorization guards, the negative integration decision, the pinned scientific surface of the public detector and removal of one-shot execution helpers.

## Remaining qualification

Further qualification includes:

1. Independent expert astrodynamics review and disposition.
2. Human keyboard and assistive-technology testing, with formal accessibility documentation if required.
3. Operator-grade ground truth and institutional deployment qualification before any operational claim.
4. Deployment-specific cybersecurity/operational-readiness assessment before operational use.

The repository includes an independent-review package and accessibility manual-test protocol. Those materials do not constitute external certification until completed by independent reviewers.
