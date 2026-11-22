# Selective ML detector v1.0 method specification

## 1. Scope and validity boundary

Selective ML v1.0 is a research screening method for public GP/TLE/OMM histories. It is separate from detector method 0.4 and is not operational SSA validation.

The method is designed around the novelty boundary established in `research/physics_ml/SYSTEMATIC-NOVELTY-REVIEW-v1.0.md`: architecture choice, conformal machinery, a physics gate and generic abstention are not claimed as novel. The contribution under test is catalogue-aware selective screening with support-limited decisions and positive-unlabelled, satellite-disjoint calibration/evaluation.

No formal type-I, anytime-valid or finite-sample event-risk guarantee is claimed. All risk language in this method is empirical calibration on explicitly verified-quiet exposure.

The confirmatory partition remained sealed during this development stage. It was subsequently consumed by the completed confirmatory evaluation, which failed its integration gate; see [the final results](../confirmatory_v1/RESULTS-v1.0.md). It may not be reused as untouched evidence for a tuned successor.

## 2. Input and catalogue qualification

The research feature exporter consumes the existing detector 0.4 analysis pipeline rather than implementing a second astrodynamics stack.

Before a row is eligible for ML scoring, the input history therefore inherits detector 0.4 handling for:

- UTC-safe OMM epochs and sub-millisecond ordering;
- deterministic near-simultaneous catalogue-revision supersession;
- duplicate/conflict handling;
- common-epoch SGP4 comparison;
- RTN residual construction;
- data-gap and quality diagnostics.

A history with unresolved near-simultaneous catalogue ambiguity or a hard detector 0.4 quality error is non-scorable. It becomes an abstention rather than a negative example.

## 3. Causal response features

For evaluated row `t`, the signed response vector is

`y_t = [a_rate, mean_motion_rate, radial_rate, along_rate, cross_rate, eccentricity_vector_rate, inclination_vector_rate, bstar_rate]`.

The feature set combines common-epoch SGP4/RTN change evidence with nonsingular orbital-change representations. Rates retain sign for conditional distribution learning; absolute standardized residual magnitudes are introduced only after the model predicts nominal location and scale.

The feature exporter never uses a truth label, future record or confirmatory membership to compute `y_t`.

## 4. Causal conditioning context

The context vector contains only information available by the current evaluated record:

`x_t = [`

- `log_gap_days`,
- `log_semi_major_axis_km`,
- `eccentricity`,
- `inclination_sin`,
- `log_abs_bstar`,
- `log_creation_lag_hours`,
- `object_age_log_days`,
- `rcs_scale`,
- `element_set_known`,
- `gp_id_known`,
- `catalogue_superseded_fraction`,
- `epoch_precision_digits_scaled`,
- `orbit_leo`, `orbit_meo`, `orbit_geo`, `orbit_heo`

`]`.

These channels explicitly expose sampling interval, orbit regime, coarse object characteristics and catalogue provenance/uncertainty to the nominal model.

IGSO retains its source regime in metadata but uses the detector's GEO-profile support channel because detector 0.4 has no independent IGSO operational profile.

## 5. Nominal training contract

Only cases whose benchmark label status is `verified-quiet` are used as nominal-training sequences.

Unlabelled time inside an event-evidence case is **not** treated as nominal or negative training data. Absence of a public maneuver report is not negative ground truth.

The final selective-model training pool contains the four development quiet cases and four calibration quiet cases. Architecture selection itself is development-only; calibration quiet data enter only after the backbone has been selected.

## 6. Conditional distribution candidates

Four compact model families are implemented behind the same interface.

### 6.1 Robust conditional linear reference

Each context channel is robustly standardized. For every response feature, conditional location is fitted with ridge-regularized Huber-style iteratively reweighted least squares. A second robust regression models log absolute residual scale.

This model is the auditable non-neural baseline.

### 6.2 GRU

The GRU receives current context plus the previous observed feature vector. It is causal. It predicts per-feature conditional location and scale for the current response vector.

### 6.3 Causal TCN

The TCN uses left-padded dilated convolutions only. No future token is available to the current prediction.

### 6.4 Causal Transformer

The Transformer uses a triangular causal attention mask. Real first tokens are available as context but are excluded from the prediction loss because no previous response exists. Padding tokens are masked separately.

The frozen compact configuration has 59,568 trainable parameters.

## 7. Heavy-tail objective and surprise score

The public GP residual distribution is treated as heavy-tailed. Neural candidates therefore optimize a fixed Student-t-shaped conditional location/scale objective with degrees of freedom `nu = 4` rather than a Gaussian squared-error objective.

The robust-linear candidate is converted to the same Student-t-shaped nonconformity score after predicting location and scale.

For each feature, define

`z_j = (y_j - mu_j) / sigma_j`.

The row surprise is the mean of

`0.5 * (nu + 1) * log(1 + z_j^2 / nu)`

across the eight response features.

This score is an empirical nonconformity score. It is not a p-value and is not itself a probability of maneuver.

## 8. Calibration-support abstention

A separate model-independent support layer robustly standardizes the causal context channels and computes the `k`th nearest same-regime reference distance.

Rows are compared only with verified-quiet reference rows from the same orbit regime. A large number of observations from one satellite cannot substitute for independent reference objects.

### Final v1.0 qualification rule

A regime must have at least **three independent verified-quiet reference satellites** before final v1.0 inference may score that regime.

The frozen reference counts are:

- LEO: 4;
- GEO: 2;
- MEO: 1;
- HEO: 1.

Therefore final selective-model support is LEO-only. GEO, MEO and HEO abstain.

The final LEO support threshold is the 98% calibration-support boundary `1.2019241655473716`.

A row also abstains when required context/features are missing, catalogue/data quality fails, the conditional model cannot produce a finite distribution, or the same-regime support distance exceeds the frozen threshold.

## 9. Physical corroboration

The standardized conditional residuals retain a transparent physics-consistency gate. A candidate can receive physical support from:

- along-track residual plus semi-major-axis/mean-motion change;
- radial residual plus eccentricity-vector change;
- cross-track residual plus inclination-vector change;
- a mixed state-residual plus orbital-element pattern.

The frozen `z` gate is `2.0`.

This layer is an interpretability and consistency constraint. It is not claimed as novel, it is not inverse maneuver reconstruction, and it does not confirm a burn.

## 10. Event construction

Rows above the event surprise threshold and with physical support are grouped when successive candidate indices are separated by no more than two evaluated points.

Each event reports its start/end row and strongest surprise row.

## 11. Positive-unlabelled architecture selection

Architecture selection uses development data only.

The primary continuous ranking statistic is the percentile of each documented event interval's maximum surprise relative to scores from cross-fitted verified-quiet development exposure. Rows outside documented truth intervals in event-evidence cases are not used as negatives.

Selection order is frozen as:

1. higher development PU event-versus-verified-quiet mean percentile;
2. higher strict supported-regime event recall;
3. lower event-row abstention;
4. lower median absolute matched-event delay;
5. fewer parameters.

The only development orbit regime with sufficient independent quiet objects for this comparison is LEO.

## 12. Final empirical event-risk calibration

After architecture selection, final support and event threshold calibration uses the frozen calibration verified-quiet cases.

The frozen implementation estimates covered verified-quiet exposure as case duration multiplied by the fraction of scored rows. It excludes abstained rows through that factor, rather than integrating timestamp intervals. The reported **covered verified-quiet object-month** is therefore a row-based approximation that can be biased by irregular sampling. Historical values remain unchanged; a future protocol should define duration weighting and gap handling.

The selective-model empirical budget is at most `1.0` false event per covered verified-quiet object-month.

Under the conservative three-reference-satellite rule only the Aqua LEO calibration control contributes covered exposure:

- coverage: `0.9583333333333334`;
- covered span: `14.200991525833333` days;
- covered exposure: `0.4665623499247091` object-month;
- final event threshold: `6.501427015384656`;
- observed calibration false events: `0`.

This is a small calibration sample. The observed zero is not a population false-alarm guarantee.

## 13. Frozen architecture result

The Transformer is selected for subsequent research because it has the highest development-only PU ranking statistic among the four candidates:

- Transformer: `0.480625`;
- robust linear: `0.37765522875817`;
- GRU: `0.3408333333333333`;
- TCN: `0.284375`.

Every candidate has zero strict-threshold development event recall under the selective-model event calibration. The selected Transformer's ranking statistic is also below `0.5`.

Accordingly, the architecture is frozen as the **relative winner for continuation**, while the standalone selective detector fails the development utility/integration gate. No claim of improved maneuver detection is made from the selective-model stage.

## 14. Confirmatory firewall

`tools/export_selective_v1_features.js` hard-fails if any confirmatory case is supplied. `train_compare.py` independently rejects confirmatory metadata or rows.

The historical protocol required the confirmatory partition to remain untouched until the final method, comparison baselines, calibration rules and integration gate were frozen. The completed evaluation has consumed this partition. A tuned successor needs a new holdout.

## 15. Reproducibility

The frozen model-selection metrics are committed in `benchmark-results/selective-v1-model-selection.json`.

Permanent CI validates the non-PyTorch method code, confirmatory firewall markers, exporter syntax and deterministic selective-v1 tests. The expensive four-model comparison was run once in a read-only GitHub Actions workflow with CPU PyTorch 2.8.0 and no confirmatory data.
