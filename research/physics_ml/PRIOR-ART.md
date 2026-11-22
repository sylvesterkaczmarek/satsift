# Prior-art boundary

This is the historical design review completed before the v1.0 research stages. Its proposed gates and future-tense requirements describe that earlier plan. The subsequent [confirmatory evaluation](../confirmatory_v1/RESULTS-v1.0.md) is complete, failed its integration gate and consumed the v1.0 holdout. A new method needs new confirmatory evidence.

## Current status

The systematic review through **14 August 2026** is now the controlling novelty assessment:

- `SYSTEMATIC-NOVELTY-REVIEW-v1.0.md`
- `REFERENCES-v1.0.bib`

The older broad framing around a "sequential risk-controlled hybrid physics-ML" maneuver detector is no longer defensible as a novelty claim.

## What prior art already covers

The review identifies established work on historical public-TLE maneuver detection, propagation consistency and moving windows, Kalman/IMM and particle filters, LSTM/BiLSTM, autoencoders and debris-reference anomaly models, Transformers and time-series foundation models, SNNs, hybrid physics-ML gates, common-epoch SGP4 propagation, conformal/sequential change testing, selective prediction/abstention, and public TLE maneuver benchmarks.

None of these components can therefore be the headline novelty in isolation or in a generic pairwise combination.

## Revised defensible contribution

> **A catalogue-aware selective event-screening framework for public GP histories that separates catalogue revisions and unsupported operating regimes from maneuver evidence, calibrates event-level false-alert burden on satellite-disjoint verified-quiet exposure, and evaluates interval-censored public maneuver evidence under positive-unlabelled semantics with a pre-frozen unseen-satellite confirmatory set.**

The strongest elements are:

1. deterministic catalogue revision/supersession provenance, audit and abstention rather than treating near-same-epoch corrections as maneuver evidence;
2. support-aware selective screening for orbit/sampling/calibration contexts outside the calibrated domain, evaluated explicitly through risk/coverage and abstention;
3. event-level operating-point calibration using false candidate events per verified-quiet object-month at the satellite level;
4. positive-unlabelled interval-censored evaluation: documented event intervals score TP/FN, unlabeled surrounding time remains unscored, and only verified-quiet exposure scores false positives;
5. explicit evidence-confidence tiers, including scheduled versus executed maneuver evidence;
6. satellite-disjoint development/calibration/confirmatory partitions with confirmatory satellites frozen before method design and tuning;
7. satellite-cluster uncertainty estimates so repeated records/windows from one object are not treated as independent evidence.

## Components retained but not claimed as novel

These remain useful implementation choices and must be ablated rather than advertised as inventions:

- common-epoch SGP4 RTN residual/change features;
- a causal temporal ML backbone;
- sequential evidence accumulation;
- a physical maneuver-consistency/support gate;
- robust conditional nominal modelling.

The final architecture should be selected empirically from simple causal alternatives. The paper should demonstrate that the claimed contribution is not dependent on one fashionable network family.

## Statistical wording

Use **risk-calibrated** or **empirically risk-calibrated**, not **risk-controlled**, unless the final method includes a formal dependence-aware result whose assumptions are defensible for irregular, autocorrelated GP histories.

Conformal prediction, conformal martingales, e-values and fixed-reference sequential tests are prior art. Merely combining them with orbital features does not create a new theorem or guarantee.

## Claims to avoid

Do not claim:

- first ML/deep-learning satellite maneuver detector;
- first LSTM/BiLSTM/GRU/TCN/Transformer/autoencoder/SNN detector;
- first physics-informed or hybrid physics-ML maneuver detector;
- first runtime physics validation of an ML maneuver alert;
- first common-epoch SGP4 maneuver comparison;
- first nominal/debris-reference anomaly detector;
- first conformal method for space surveillance;
- first sequential conformal/e-process change detector;
- first detector with abstention;
- first public TLE maneuver benchmark;
- formal event-level false-alarm control from the current v0.3 empirical p/e implementation;
- executed-maneuver ground truth when the source only announces a scheduled NANU/NAGU interval.

## Gate before final method design

The next method must keep benchmark v1.0 confirmatory satellites untouched and compare against simple statistical, Kalman/particle-filter and open learned baselines. Mandatory ablations are defined in `SYSTEMATIC-NOVELTY-REVIEW-v1.0.md`.

If catalogue-aware abstention and positive-unlabelled event-level calibration do not materially change risk estimates or held-out performance, the work should be reframed as a benchmark/evaluation-methodology paper rather than overstating algorithmic novelty.
