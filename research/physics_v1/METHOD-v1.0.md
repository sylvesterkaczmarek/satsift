# Maneuver physics feasibility v1.0

## Scope

This research layer replaces the earlier threshold-co-occurrence physics corroboration with an explicit astrodynamics feasibility calculation. It is applied only after catalogue/data-quality and calibration-support checks. It does not change detector method 0.4 or the public workbench. The confirmatory partition remained sealed during this development stage. It was subsequently consumed by the completed confirmatory evaluation, which failed its integration gate; see [the final results](../confirmatory_v1/RESULTS-v1.0.md). It may not be reused as untouched evidence for a tuned successor.

The goal is narrower than orbit reconstruction: determine whether the joint changes between two resolved public GP/OMM states are compatible with a plausible **equivalent RTN impulse**, estimate a defensible delta-v range/direction when identifiable, and abstain when burn geometry is underdetermined.

Public GP/OMM elements are catalogue mean-element products. The result is therefore an equivalent-impulse feasibility estimate, not an assertion of the spacecraft's true executed finite-burn history.

## Inputs

For each adjacent resolved GP pair the research feature exporter preserves:

- epoch gap `Delta t`;
- before/after semi-major axis, eccentricity, inclination, RAAN, argument of periapsis and mean anomaly;
- the detector 0.4 common-epoch SGP4 RTN residual `[Delta R, Delta T, Delta N]`;
- catalogue provenance and the existing causal ML context/features.

The inversion uses the element changes themselves rather than treating the existing per-day research feature rates as delta-v proxies.

## Nonsingular state representation

For the inversion we use the prograde modified equinoctial subset

`y = [p, f, g, h, k]`,

with

`p = a(1-e^2)`,

`f = e cos(Omega + omega)`,

`g = e sin(Omega + omega)`,

`h = tan(i/2) cos(Omega)`,

`k = tan(i/2) sin(Omega)`.

This removes the classical circular/equatorial singularities that would otherwise make a local delta-v inversion unstable. Mean/true longitude is deliberately excluded from the response vector because the burn epoch is unknown inside the GP epoch interval and along-track phase is strongly confounded with that unknown time.

The formulation is consistent with the established use of equinoctial elements and Gauss variational equations for local radial/along-track/cross-track perturbations. See, for example, Broucke and Cefola's equinoctial-element formulation, ESA/GODOT's Gauss-equation implementation in equinoctial elements and local RAC accelerations, and the ESA ICATT formation-control treatment of velocity increments through Gauss variational equations.

## Verified-quiet drift model

Raw GP element differences contain catalogue/force-model drift in addition to maneuver effects. For each qualified orbit regime, the physics layer therefore fits a robust background model only on explicit verified-quiet satellites:

1. compute `Delta y / Delta t` and common-epoch RTN residual per day;
2. estimate each channel's median drift rate;
3. estimate scale with `1.4826 * MAD`, subject to conservative floors;
4. for a candidate pair subtract the expected median drift over its actual gap;
5. scale inversion residuals by the corresponding gap-adjusted robust scale.

A regime must have at least three independent verified-quiet reference satellites in the final research method. Benchmark v1.0 currently qualifies LEO only. GEO, MEO and HEO return abstention.

## Explicit nominal/no-maneuver region

A quiet observation should not be forced through an ill-posed burn inversion. After verified-quiet drift correction, standardized joint element and RTN changes are tested against a conservative nominal envelope.

If joint RMS is at most `1.5` and every absolute standardized component is at most `3.0`, the row is classified `nominal`: no maneuver inversion is warranted and the sequential monitor receives a normal non-event update.

This is distinct from `abstain`. Abstention is reserved for anomalous observations for which the maneuver geometry cannot be identified reliably.

## Unknown-burn-phase impulse inversion

For anomalous rows, the executed burn time is unknown within the interval between GP epochs. Let

`tau in (0,1)`

be the fraction of the epoch interval at which an equivalent instantaneous impulse occurs. The frozen grid is

`tau = 0.05, 0.075, ..., 0.95`.

At each candidate `tau`:

1. two-body propagate the before-state mean anomaly to the candidate burn phase;
2. convert the mean elements to Cartesian position/velocity;
3. construct the local RTN frame;
4. apply infinitesimal radial, along-track and cross-track velocity perturbations;
5. map the perturbed Cartesian state back to elements and then `[p,f,g,h,k]`;
6. obtain the local sensitivity matrix

`J_tau = partial y / partial [Delta v_R, Delta v_T, Delta v_N]`

by forward/local numerical impulse differentiation;
7. solve the weighted linear inverse problem

`Delta y ~= J_tau Delta v`

using the verified-quiet channel scales.

This numerical sensitivity is an implementation of the same first-order impulse relationship represented analytically by Gauss variational equations, while avoiding singular classical-element derivatives in the production inversion.

## Conditioning and uncertainty

For each phase, the normal matrix `J^T W J` is inspected. Singular or excessively ill-conditioned phases are discarded. The final local covariance approximation is the inverse weighted normal matrix, and its diagonal is used to construct component uncertainty intervals.

Solutions requiring an equivalent impulse above `2000 m/s` are rejected as implausible for this screening formulation.

The result across accepted burn phases is reported as:

- equivalent delta-v magnitude interval;
- median equivalent delta-v;
- radial, along-track and cross-track component intervals;
- burn-phase interval;
- dominant signed RTN direction if stable;
- weighted element-fit RMS;
- RTN corroboration RMS where applicable;
- condition estimate.

The intervals represent local inversion/noise and burn-phase ambiguity. They are not Bayesian credible intervals and do not imply knowledge of the actual thrust profile.

## Independent RTN corroboration

For near-circular cases (`e <= 0.05`) the common-epoch SGP4 RTN residual is used as a second observable family. For a candidate equivalent impulse, the Hill-Clohessy-Wiltshire zero-initial-position response predicts the relative RTN displacement over the time from the candidate burn to the later epoch.

The standardized difference between predicted and observed common-epoch RTN displacement contributes to the joint feasibility score.

HCW is deliberately not used as the primary inversion for eccentric cases. In those cases the equinoctial element inversion remains available, but the absence of a valid HCW check increases ambiguity and can lead to abstention.

## Outcomes

The physics screen has four explicit outcomes:

- `nominal`: corrected change lies inside the verified-quiet physics envelope; monitored as a non-event;
- `feasible`: a stable equivalent RTN impulse direction and uncertainty-bounded delta-v interval are supported;
- `inconsistent`: the inversion is well posed but no candidate equivalent impulse jointly fits the observations at the calibrated scale;
- `abstain`: the observation is anomalous but burn phase/direction/magnitude is underdetermined, geometry is singular/ill-conditioned, or the regime lacks independent calibration support.

Only `feasible` satisfies the sequential event-like physical corroboration requirement. `nominal` and `inconsistent` are monitored non-event updates. `abstain` resets sequential evidence rather than being encoded as zero.

## Direction identifiability

A signed dominant direction is returned only if accepted phase solutions agree on the dominant RTN component and magnitude is sufficiently stable. A single surviving burn phase may be called feasible only when:

- common-epoch RTN corroboration is strong;
- element fit is strong;
- one RTN component clearly dominates;
- its uncertainty interval resolves its sign.

Otherwise the layer returns abstention and, when possible, only a broad equivalent delta-v interval.

## Deterministic validation

`independent_check.py` performs three separate validation families.

### Analytic Gauss equations versus Cartesian impulse

For a nonsingular eccentric/inclined orbit, independent classical Gauss impulsive equations calculate first-order changes in

`a, e, i, Omega, omega`

for radial, along-track, cross-track and mixed impulses. These are compared with the main code's Cartesian velocity impulse followed by Cartesian-to-element reconstruction.

### Production Jacobian versus analytic Gauss equations

The production `numerical_impulse_jacobian()` is also evaluated directly. For radial, along-track and cross-track basis impulses, an independent first-order response is generated from the classical Gauss equations and mapped analytically, by the chain rule, into the same nonsingular `[p,f,g,h,k]` coordinates. Meaningful nonzero derivatives retain strict element-by-element relative and absolute checks. Components that the analytic mapping proves are zero use only a local floating-point cancellation bound derived from the component ULP and finite-difference step; that platform-portability treatment does not relax any nonzero derivative check.

This direct check breaks the circularity that would arise if the inversion were validated only with synthetic maneuver states generated by the same Cartesian impulse helper used inside the numerical Jacobian.

### Known injected maneuvers

Synthetic LEO cases inject known radial, along-track and cross-track impulses. The inversion must:

- return `feasible`;
- recover the correct dominant direction;
- contain the injected delta-v magnitude inside its returned interval.

A corresponding injection with RTN corroboration removed is used to verify that broad burn-phase ambiguity does not produce false directional precision.

## Research evaluation firewall

Physics evaluation keeps these sequential-evidence choices frozen:

- Transformer backbone;
- base surprise threshold `17.822733355396952`;
- satellite-disjoint benchmark partitions;
- positive-unlabelled truth semantics;
- event-rate target of at most one false event per covered verified-quiet object-month;
- confirmatory embargo.

The physics layer is calibrated/evaluated using development and calibration verified-quiet data only. Confirmatory histories are neither materialized nor scored.

## Claim boundary

Allowed language:

**astrodynamics-based equivalent-impulse feasibility screening with uncertainty-aware abstention**.

Do not claim:

- exact burn reconstruction from TLE/OMM;
- precise executed delta-v;
- finite-burn thrust-profile estimation;
- operational orbit determination;
- formal false-event guarantees from the physics layer.

## References

- Broucke, R. A. and Cefola, P. J., *On the Equinoctial Orbit Elements*, NASA NTRS 19730046311.
- Cefola, P. J., *Equinoctial Orbit Elements - Application to Artificial Satellite Orbits*, NASA NTRS 19720019148.
- ESA ICATT 2016, formation-control work using Gauss variational equations to relate local velocity increments to element changes.
- ESA GODOT documentation, `gaussEquation`, equinoctial elements with local RAC accelerations.
- Clohessy, W. H. and Wiltshire, R. S., *Terminal Guidance System for Satellite Rendezvous*, Journal of the Aerospace Sciences, 1960.
