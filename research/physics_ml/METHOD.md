# Method definition

> **Status:** historical physics-ML v0.3 method definition. This is not the final v1 method. The systematic novelty review in `SYSTEMATIC-NOVELTY-REVIEW-v1.0.md` supersedes the earlier broad research framing. In particular, the final work must use **risk-calibrated** wording unless a new dependence-aware validity result is proved, and the temporal/sequential/physics components below are mechanisms rather than novelty claims.

## Input contract

The experimental detector consumes row-level features derived from a history that has already passed the baseline catalogue and data-quality checks. It does not parse raw OMM independently.

For each evaluated epoch `t`, the feature vector is

`y_t = [a_rate, mean_motion_rate, radial_rate, along_rate, cross_rate, eccentricity_vector_rate, inclination_vector_rate, bstar_rate]`.

The conditioning context is

`x_t = [log(1+gap_days), log(1+a_km), eccentricity, sin(inclination), log(1+|B*|)]`.

Only past/calibration objects are used to fit the nominal model. Test-satellite observations never enter the reference set.

## Conditional nominal model

For each test context `x_t`, select the `k` nearest calibration samples after robust standardisation of the context coordinates. For every feature, estimate a local centre by the median and a local scale by `1.4826 * MAD`, with a numerical floor.

The point nonconformity score is the maximum absolute local robust z-score across available detector features.

Calibration nonconformity scores are produced by leave-one-out fitting on the calibration reference. The empirical p-value for a test score `s_t` is

`p_t = (1 + #{s_i_cal >= s_t}) / (n_cal + 1)`.

This is deliberately a simple, auditable reference implementation. A paper-quality implementation may replace the neighbour model with a learned conditional density or quantile model, but the calibration/test split must remain satellite-disjoint.

## Sequential evidence

For betting parameter `epsilon` in `(0,1)`, transform each p-value using

`e_t = epsilon * p_t^(epsilon - 1)`.

For every possible start time `s`, maintain the product `P_{s,t} = product_{i=s..t} e_i`. Mix these products with weights

`w_s = 1 / (s(s+1))`.

The reported wealth is

`M_t = (1 - sum_{s<=t} w_s) + sum_{s<=t} w_s P_{s,t}`.

The nominal event threshold is `M_t >= 1 / alpha_event`.

### Validity boundary

The e-process interpretation requires the p-values to satisfy the corresponding conditional super-uniformity assumptions. Local empirical p-values from a finite, potentially non-exchangeable orbital catalogue are not automatically guaranteed to satisfy those assumptions. Therefore:

- the code reports e-wealth and a nominal `alpha_event` threshold;
- the repository does not label that threshold a proved false-event guarantee;
- calibration on verified quiet objects and held-out satellite evaluation are mandatory;
- a formal paper must either establish the required conditions for the chosen calibration scheme or weaken the claim to empirical risk calibration.

This boundary is intentional. It prevents a statistical guarantee from being inferred merely from the use of conformal-style p-values.

## Physical support

Crossing the sequential statistical threshold is insufficient. A candidate requires one of the following patterns in local robust z-scores:

- along-track residual support plus semi-major-axis or mean-motion support;
- radial residual support plus eccentricity-vector support;
- cross-track residual support plus inclination-vector support;
- at least one state-residual feature and one orbital-element feature above the physical support gate.

This gate is a screening consistency check, not an inverse maneuver solver and not a burn confirmation.

## Abstention

The detector abstains when any of the following applies:

- baseline catalogue/data-quality checks fail;
- required context or feature values are missing;
- fewer than the minimum calibration neighbours exist;
- the nearest calibration support is beyond the configured context-distance limit.

Abstention is measured as an outcome in the benchmark and must not be silently scored as a correct negative.

## Event grouping

Adjacent candidate epochs are grouped when separated by no more than the configured number of evaluated points. Event time is reported as the grouped interval, with the strongest e-wealth point retained for ranking.

## Evaluation contract

Primary evaluation is performed only on frozen test satellites that were not used for fitting, tuning or calibration. Event matching follows `benchmark/PROTOCOL.md`. Confidence intervals use a satellite-cluster bootstrap so multiple windows or events from one object are never treated as independent samples.
