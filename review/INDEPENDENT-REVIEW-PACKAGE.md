# Independent astrodynamics review package

## Purpose

This package is for an independent expert review of Satellite Maneuver Screening Workbench 3.4, detector method 0.4. The requested conclusion is limited to research screening and technical evaluation unless the reviewer explicitly supports a narrower or stronger disposition.

## Review freeze

The reviewer must record the exact Git commit SHA reviewed in `EXTERNAL-REVIEW-CHECKLIST.md`. Any source change after that SHA invalidates the sign-off until the reviewer confirms that the change is non-substantive or reviews the affected material again.

## Primary material

Review these files first:

1. `app-3.4.js` for parsing, common-epoch propagation, RTN residuals, feature construction, sequential calibration, candidate gating and event grouping.
2. `history.php` for authenticated history retrieval, cache behavior and catalogue-record provenance.
3. `benchmark/PUBLICATION-PROTOCOL-v1.0.md` for label semantics, satellite-disjoint evaluation, positive-unlabelled scoring and confidence-interval policy.
4. `public-evidence-manifest-v1.0.json`, `benchmark-results/confirmatory-v1-final.json` and `research/confirmatory_v1/RESULTS-v1.0.md` for the frozen v1.0 evidence, including the completed 12-satellite confirmatory evaluation.
5. `review/VALIDATION-STATUS.md`, `review/CONFIRMATORY-AUDIT.md` and `KNOWN-ISSUES.md` for the current claims boundary and the failed physics-ML v1.0 integration gate.
6. `.github/workflows/ci.yml`, `.github/workflows/confirmatory-freeze.yml` and the tests under `tests/` for executable verification evidence.

The learned/physics research stacks under `research/` are separate from public detector method 0.4. Physics-ML v1.0 failed its frozen confirmatory integration/publication gate and was not integrated. Those artifacts are relevant as validation evidence and limitations, but they are not part of detector method 0.4 unless the reviewer explicitly accepts a second research-review scope.

## Reproduction checks

Run the permanent GitHub Actions workflows or equivalent local checks. The expected baseline includes:

- JavaScript and PHP syntax validation;
- catalogue-revision and cross-time-zone epoch regression tests;
- browser-style workbench regression tests;
- history endpoint and concurrent-request integration tests;
- independent Python SGP4 fixture validation;
- JSON, routing, repository-integrity and vendor-fingerprint checks;
- immutable Confirmatory evaluation result-hash, run-lock and Integration decision disposition checks.

Any failure should be recorded as a review finding rather than bypassed.

## Technical questions requiring explicit judgment

### Orbital representation

Confirm that TLE/OMM parsing, UTC treatment, high-resolution ordering and deterministic handling of near-simultaneous catalogue revisions are technically appropriate for the stated use.

### Common-epoch comparison

Verify that consecutive general-perturbations element sets are propagated to a common epoch consistently and that the resulting position difference is projected onto an RTN basis constructed from the reference state with correct orientation and signs.

### Signal interpretation

Assess whether radial, along-track and cross-track residuals, semi-major-axis and mean-motion changes, eccentricity/inclination-vector changes and B* are defensible as screening evidence. Identify any feature that should be removed, transformed or more strongly qualified.

### Statistical calibration

Review the preceding-data-only rolling median/empirical-residual calibration, feature floors, support-count rules, orbit profiles and thresholds. Heuristic thresholds may remain heuristic, but their limitations must be clearly stated and they must not be described as calibrated probabilities.

### Candidate and event logic

Assess the physical plausibility of candidate gating, adjacent-event grouping and orbit-raise/lower interpretation. Confirm that data-quality errors and insufficient evaluated history cause abstention rather than a negative maneuver conclusion.

### Validation design

Review the publication benchmark protocol, especially interval-censored labels, verified-quiet controls, unknown-period treatment, complete-satellite holdout, positive-unlabelled scoring and satellite-cluster confidence intervals. Review the negative Confirmatory evaluation result and whether its limitations are represented conservatively. Note whether additional ground truth is required before any journal or operational performance claim.

## Required output

Complete `EXTERNAL-REVIEW-CHECKLIST.md` and provide each substantive finding with:

- finding ID;
- severity: critical, major, minor or editorial;
- exact file/function or methodological component;
- technical rationale;
- recommended correction;
- final status after correction: open, accepted risk, or resolved.

The repository owner will record the disposition in `REVIEW-DISPOSITION-LOG.md`. A review is complete only when all critical and major findings are either resolved and rechecked or explicitly rejected by the reviewer as non-blocking.

## Independence statement

The reviewer should disclose prior collaboration, financial interest, employment relationship or other conflict that could reasonably affect independence. A reviewer may be unpaid or paid; the relationship and scope should simply be recorded.
