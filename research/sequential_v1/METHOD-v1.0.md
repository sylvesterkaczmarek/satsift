# Sequential evidence v1.0

## Scope

This layer sits on top of the frozen selective-ML v1.0 conditional nominal model. It does not change detector method 0.4 and it does not alter the benchmark labels. The confirmatory partition remained sealed during this development stage. It was subsequently consumed by the completed confirmatory evaluation, which failed its integration gate; see [the final results](../confirmatory_v1/RESULTS-v1.0.md). It may not be reused as untouched evidence for a tuned successor.

The design goal is repeated monitoring with an interpretable operational control, **false events per covered object-month**, while keeping theorem-level anytime validity separate from empirical calibration on real public GP histories.

## Why we did not claim conformal validity on the GP stream

Conformal test martingales and e-processes provide strong anytime-valid results when their assumptions hold. Vovk et al. describe conformal test martingales under exchangeability; Shaer et al. (2026) give a fixed-reference conditional conformal test-martingale construction that accounts for finite-reference estimation error. These are important prior-art/reference constructions, but neither result by itself proves that irregular, autocorrelated, catalogue-mediated GP residual scores are conditionally super-uniform or exchangeable.

Therefore this repository does **not** take a conformal rank from the nominal-model score and label it a valid sequential p-value. Doing that would overstate the mathematics.

References used for the design boundary:

- Vovk et al., *Retrain or not retrain: Conformal test martingales for change-point detection*, arXiv:2102.10439.
- Shaer, Bar, Prinster and Romano, *Testing For Distribution Shifts with Conditional Conformal Test Martingales*, arXiv:2602.13848 v2.
- Ramdas, Ruf, Larsson and Koolen, *Testing exchangeability: fork-convexity, supermartingales, and e-processes*, arXiv:2102.00630 / International Journal of Approximate Reasoning.
- Howard et al., *Time-uniform, nonparametric, nonasymptotic confidence sequences*, Annals of Statistics 49(2), 2021.

## Monitored indicator

For a selective-v1 row that is inside calibrated support, define the binary event-like exceedance

`X_t = 1{ S_t >= u and P_t = 1 }`,

where:

- `S_t` is the Student-t-shaped conditional surprise from selective ML v1.0;
- `u` is a development-selected base score threshold;
- `P_t` indicates transparent physical corroboration from the existing RTN/element consistency gate.

An abstained row is not encoded as zero. It resets sequential evidence. Post-event refractory rows also reset the process.

## The theorem-qualified null

For a fixed `q0 in (0,1)`, define

`H0(q0): Pr(X_t = 1 | F_{t-1}) <= q0` for every monitored update `t`.

This is a **conditional** bound, not a statement about the marginal frequency alone.

For an alternative `q1 > q0`, define the one-step likelihood-ratio e-variable

`e_t(q1) = (q1/q0)^X_t * ((1-q1)/(1-q0))^(1-X_t)`.

If the conditional null holds with `p_t = Pr(X_t=1 | F_{t-1}) <= q0`, then

`E[e_t(q1) | F_{t-1}]`

`= p_t q1/q0 + (1-p_t)(1-q1)/(1-q0)`

`= 1 + (p_t-q0)(q1-q0)/(q0(1-q0)) <= 1`.

So each factor is a conditional e-variable under `H0(q0)`.

## Unknown-change-start mixture

A monitoring layer should not assume the maneuver/change starts at the first observation. Let

`w_s = 1 / (s(s+1))`, for `s = 1,2,...`.

These weights sum to one. For each fixed alternative `q1_j`, define

`A_t,j = sum_{s<=t} w_s * product_{i=s..t} e_i(q1_j)`.

The future, not-yet-started mass after update `t` is `1/(t+1)`. With fixed alternative weights `v_j` summing to one,

`E_t = 1/(t+1) + sum_j v_j A_t,j`.

The recursion used in code is

`A_t,j = e_t(q1_j) * (A_{t-1,j} + w_t)`.

Therefore the exact mixture is updated in time linear in the number of alternative rates rather than quadratic in sequence length.

Under `H0(q0)`, `E_t` is a nonnegative supermartingale with `E_0 = 1`. Ville's inequality then gives

`Pr_H0( sup_t E_t >= 1/alpha ) <= alpha`.

### What this theorem does and does not prove

It proves an anytime-valid crossing bound **if `q0` is a valid conditional exceedance bound for the monitored stream**. We have not proved that premise for real GP residuals. An empirical estimate of `q0` does not convert this conditional theorem into a formal real-data guarantee.

## Repeated events

If theorem mode were available, repeated post-reset episodes can spend a total type-I budget using

`alpha_k = alpha_total * 6/(pi^2 k^2)`.

The series sums to `alpha_total`. If every episode starts at a stopping time and continues to satisfy the same conditional null, a union bound over Ville-valid episodes controls the probability of one or more false events by `alpha_total`.

This is retained as a theorem/reference interface, **not** exposed as the normal operating control for the GP workbench.

## Operational real-data calibration

The operational quantity is

**target false events per covered verified-quiet object-month**.

The procedure is:

1. Freeze the Transformer backbone and selective support policy from the selective-model stage.
2. Use development LEO quiet satellites in leave-one-satellite-out form to choose candidate base score thresholds `u`.
3. For each `u`, estimate an empirical `q0` as the maximum satellite-level Laplace-smoothed event-like exceedance rate, inflated by 10%. This is a heuristic bound, not a confidence bound.
4. On development verified-quiet exposure, choose the least-conservative sequential wealth threshold on a fixed geometric grid that meets the requested false-event rate.
5. Select `u` on development data only using event recall at that operating point, then PU-safe sequential-wealth ranking, then delay.
6. Freeze `u` and the empirical `q0`.
7. Recalibrate only the final wealth threshold on the calibration verified-quiet LEO case, counting **covered** exposure only.
8. Report the implied `1/wealth_threshold` solely as a diagnostic showing what the Ville threshold would mean *if* the conditional null premise were independently justified.

Unlabelled rows in event-evidence cases are never used as negatives or as false-event exposure.

## Selective support

The selective-model policy requires at least three independent verified-quiet reference satellites in a regime. Benchmark v1.0 currently qualifies only LEO. GEO, MEO and HEO remain explicit abstention regimes.

Abstentions reset sequential wealth. This avoids carrying evidence across unsupported catalogue/sampling contexts and avoids treating missing/unsupported intervals as nominal observations.

## Simulations

`simulate_null.py` covers four cases:

1. IID Bernoulli at the boundary `p=q0`, where the theorem applies.
2. Predictable nonstationary Bernoulli probabilities that vary but never exceed `q0`, where the theorem still applies.
3. A positively clustered Markov sequence with approximately the same marginal event frequency as `q0` but `Pr(X_t=1|X_{t-1}=1) > q0`; the conditional assumption is violated.
4. IID data with the true exceedance probability `1.5*q0`; the assumed null is misspecified.

Cases 3 and 4 are deliberate failure tests demonstrating why a marginal observed frequency cannot justify an anytime-valid claim.

## Failure conditions

Formal validity is unavailable or can fail when any of the following holds:

- the empirical `q0` is below the true conditional exceedance probability;
- event-like exceedances cluster so that a marginal frequency hides a larger conditional probability after a hit;
- monitoring/abstention decisions depend on the unseen current `X_t` rather than predictable context;
- the nominal model, base threshold, physical gate or support rule is adaptively changed using the live stream without a new validity argument;
- catalogue revisions or unsupported regimes leak into the scored stream instead of causing abstention/reset;
- the calibration exposure is too small to support a stable empirical false-event estimate.

## Claim language

For real GP histories use:

**empirically risk-calibrated sequential event screening**.

Do not use:

- formally risk-controlled satellite maneuver detector;
- guaranteed false-event rate;
- anytime-valid GP maneuver alarm;
- conformal guarantee.

Those stronger phrases require an independently justified conditional null or a new dependence-aware proof.