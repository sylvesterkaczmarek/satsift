# Comparison suite v1.0

## Purpose

The comparison suite evaluates the frozen Satellite Maneuver Detector methods against a broad, predeclared set of classical, filtering and learned baselines under one evaluation protocol. The comparison is designed for the maneuver-detection paper and does not change detector 0.4, the frozen benchmark, selective-model artifacts, sequential evidence, maneuver physics or integrity results.

The benchmark v1.0 confirmatory partition remained sealed throughout this comparison. Only development and calibration objects were materialized or scored. The later confirmatory evaluation is documented separately in [the final results](../confirmatory_v1/RESULTS-v1.0.md).

## Frozen evaluation protocol

The benchmark and event semantics are inherited without modification from `benchmark/PUBLICATION-PROTOCOL-v1.0.md`.

- Unit of partitioning and bootstrap resampling is the NORAD object.
- Development and calibration objects remain satellite-disjoint.
- Event evidence is positive-unlabelled. Documented intervals contribute TP and FN. An unmatched prediction on an event-evidence history is unscored rather than declared false.
- Verified-quiet intervals provide the only false-event exposure.
- Event matching uses the frozen 24-hour tolerance and one-to-one greedy assignment by distance between the prediction's strongest epoch and the truth-interval midpoint.
- Predictions are grouped using the same two-index event-gap convention used by the selective detector. An abstained row terminates an event segment.
- Calibration is the primary comparison split. Development event results are diagnostic.
- Confidence intervals use a deterministic 1,000-replicate satellite-cluster bootstrap with seed `3404`.

## Anti-cherry-picking rule

The baseline roster and all fixed structural settings below are declared before calibration event labels are evaluated. Generic baselines fit normal-state parameters only from development verified-quiet histories. Their single event-score threshold is then selected using only calibration verified-quiet exposure. Starting from the no-event threshold, the threshold is lowered until the quiet event-rate budget would first be violated; the last feasible threshold is frozen. This monotone search rule prevents a still-lower threshold from appearing feasible merely because nearby false alarms merge into one grouped event. The budget is at most `1.0` false event per covered object-month. Calibration event labels do not select algorithms, features, windows, network sizes, training epochs or thresholds.

Detector 0.4 and physics-ML v1.0 keep their already-frozen operating points. The comparison does not retune them to improve comparative rank.

## Baseline roster

The fixed order is:

1. `detector-0.4`
2. `mean-motion-threshold`
3. `sma-window-shift`
4. `sgp4-rtn-consistency`
5. `multi-element-mad`
6. `robust-mahalanobis`
7. `robust-cusum`
8. `kalman-nis`
9. `shorten-op-pf-surrogate`
10. `robust-linear`
11. `lstm`
12. `gru`
13. `tcn`
14. `transformer`
15. `sequential-autoencoder`
16. `physics-ml-v1.0`

This roster intentionally retains all four previously considered conditional-model families (`robust-linear`, GRU, TCN and Transformer) rather than reporting only the strongest prior candidate.

## Simple threshold baselines

### Mean-motion threshold

`mean_motion_rate` is robustly standardized using the development verified-quiet median and MAD scale. The absolute robust z-score is the anomaly statistic. This is retained because simple mean-motion changes are a common TLE maneuver signal and provide an important low-complexity reference.

### Semi-major-axis window shift

This is a Kelecy-style causal moving-window reference. Semi-major axis is reconstructed from the exported causal context. At each eligible epoch the median of the latest three states is compared with the preceding three-state median. The absolute shift is robustly standardized from development verified-quiet histories. The total six-point structure matches the workbench's already-frozen six-record analysis scale and is not optimized against event labels.

### SGP4 RTN consistency

The radial, along-track and cross-track common-epoch SGP4 residual rates are independently robustly standardized on development verified-quiet histories. The maximum absolute RTN robust z-score is used. This provides a simple propagation-consistency comparator in the same family of ideas as TLE consistency checks, without claiming to reproduce a particular published implementation.

### Multi-element MAD

Five element-derived channels are standardized independently on development verified-quiet histories: semi-major-axis rate, mean-motion rate, eccentricity-vector rate, inclination-vector rate and B* rate. The row score is the largest absolute robust z-score.

## Robust statistical baselines

### Robust Mahalanobis

All eight causal feature channels are median/MAD standardized. Development-normal z-scores are winsorized to `[-6, 6]`. Their empirical covariance is regularized by `10%` diagonal shrinkage plus a `1e-6` identity floor. The anomaly score is the square root of the resulting Mahalanobis quadratic form. These structural constants are fixed and are not searched on event labels.

### Robust CUSUM

The robust Mahalanobis score is standardized again using its development-normal median and MAD. A one-sided CUSUM accumulates `max(0, C_previous + z - 0.5)`. The allowance `0.5` is fixed in advance. Invalid or abstained rows reset the cumulative statistic.

## Kalman baseline

`kalman-nis` operates on a five-dimensional nonsingular orbital state constructed from public mean elements:

- log mean motion;
- eccentricity multiplied by cosine and sine of longitude of periapsis;
- tangent of half inclination multiplied by cosine and sine of RAAN.

This avoids the circular/equatorial singularities of raw Keplerian angles. State location/scale and robust drift are estimated only from development verified-quiet adjacent pairs. A diagonal local-level Kalman filter then tracks the standardized state. Its process-to-observation variance ratio is selected from the fixed grid `{1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1, 3e-1, 1, 3}` by minimum one-step Gaussian predictive negative log-likelihood on development verified-quiet data only. No maneuver labels participate. The anomaly statistic is the summed normalized innovation squared.

This baseline is motivated by Zollo and Weigel, *Comparison of satellite manoeuvre detection methods based on timeline of orbit elements*, Advances in Space Research 73(1), 2024, DOI `10.1016/j.asr.2023.10.032`, which evaluates discrete linear Kalman filtering for maneuver detection on orbit-element timelines. The comparison does not claim a line-by-line reproduction of their tuned filter.

## Shorten-style particle filter

Shorten et al., *Optimal Proposal Particle Filters for Detecting Anomalies and Manoeuvres from Two Line Element Data*, Acta Astronautica 228, 2025, DOI `10.1016/j.actaastro.2024.11.033`, formulate a Gaussian state/observation model over TLE mean elements, use an optimal-proposal particle filter, monitor effective sample size, apply systematic resampling plus Gaussian regularization, and score anomalies by negative log predictive observation density.

An exact reproduction is not claimed here. Their method depends on a non-standard mean-element SGP4 implementation, including specific Kozai/Brouwer handling and singularity-aware covariance construction, for which this repository has no validated drop-in implementation. Fabricating those internals would be less reproducible than stating the limitation.

`shorten-op-pf-surrogate` therefore preserves the reproducible structural components while replacing only that unavailable transition:

- the same nonsingular five-dimensional mean-element state used by the Kalman comparator;
- a development-quiet empirical state transition and residual covariance;
- `Q` and `R` both initialized from residual variance, matching the paper's conservative residual-covariance convention;
- `256` particles;
- analytic Gaussian optimal proposal with identity observation model;
- negative log predictive density computed with log-sum-exp;
- ESS resampling threshold `0.5 N`;
- systematic resampling;
- Gaussian regularization bandwidth `N^(-1/(d+4))`;
- deterministic per-satellite random seed derived from seed `3404` and case ID.

The result must always be labelled a structural Shorten-style surrogate.

## Learned baselines

All learned baselines train only on development verified-quiet histories and use the same eight causal feature channels. The conditional predictive models also use the frozen 16-channel causal context representation plus previous-observation features.

`robust-linear`, GRU, TCN and Transformer reuse the already-audited selective-v1 implementations rather than creating favorable duplicate implementations. Neural models retain the previously frozen architecture scale of hidden size `32`, two layers, `120` epochs, seed `3404`, AdamW training and Student-t conditional objective.

The LSTM baseline uses the same input/output normalization, hidden size, layer count, epochs, learning rate, seed and Student-t objective as the GRU baseline, changing only the recurrent cell from GRU to LSTM.

The sequential autoencoder follows the anomaly-detection principle of Malhotra et al., *LSTM-based Encoder-Decoder for Multi-sensor Anomaly Detection*, arXiv `1607.00148`. It uses an eight-row causal window ending at the current observation, an LSTM encoder and zero-input LSTM decoder with hidden size `32`, and reconstructs the input sequence in reverse order. The current endpoint reconstruction MSE is the anomaly statistic. The first seven rows of every trusted segment abstain because a complete causal window is unavailable.

## Physics-ML v1.0 comparator

For this comparison, `physics-ml-v1.0` denotes the frozen Transformer from the physics stage plus calibrated-support, sequential-evidence and equivalent-impulse physics stack. Its frozen constants remain:

- base score threshold `17.822733355396952`;
- final support threshold `1.2019241655473716`;
- `q0 = 0.24444444444444446`;
- final wealth threshold `1.01`.

Calibration event cases use all available development and calibration verified-quiet references. Each calibration verified-quiet case is evaluated leave-one-satellite-out so its own history cannot train the model or physical reference used to estimate its false-event exposure. No comparison-stage event label changes the frozen physics operating point.

## Reported metrics

For every method the machine-readable artifact reports:

- event-level precision, recall and F1;
- TP, FP and FN counts;
- false events per covered verified-quiet object-month;
- signed and absolute median matched-event detection delay, measured from the first alarm/event onset to the documented interval start; the strongest point is used only for deterministic one-to-one matching;
- mean case abstention fraction;
- satellite-cluster 95% bootstrap intervals for the main metrics;
- the same metrics by orbit regime where cases exist;
- threshold/calibration information;
- fit time, inference time, throughput and parameter count where meaningful.

Timing is wall-clock benchmark timing on the GitHub Actions CPU runner. Primary inference timing is measured over the same 14 calibration cases for every method; development diagnostic scoring is timed separately. Fit time remains method-specific and is reported separately. It is suitable for relative engineering comparison within this run, not a hardware-independent complexity theorem.

The report also flags whether each frozen/calibrated operating point satisfies the common comparison budget of at most `1.0` false event per covered verified-quiet object-month. Frozen target methods are not retuned to force compliance. A second descriptive ranking is therefore reported only among operating points that already satisfy that budget.

Generic trainable baselines fit normal-state parameters only on development verified-quiet histories, consistent with the benchmark partition intent. `physics-ml-v1.0` is reported at its already-frozen Physics evaluation reference protocol, including its documented calibration-quiet reference use. This historical data-use difference is disclosed rather than silently changing the target method during Comparison evaluation.

## Claim boundary

This comparison used development/calibration data only. It did not access benchmark v1.0 confirmatory objects; its results must be distinguished from the later completed confirmatory evaluation. It does not claim exact reproduction of papers whose complete implementation or proprietary/non-standard propagation details are unavailable. Such methods are labelled according to what is actually reproduced.
