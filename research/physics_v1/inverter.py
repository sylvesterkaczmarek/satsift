#!/usr/bin/env python3
from __future__ import annotations

from math import isfinite, pi, sqrt
from statistics import median
from typing import Sequence

from .core import (
    SECONDS_PER_DAY,
    PhysicsEstimate,
    PhysicsNoiseModel,
    _inverse_3x3,
    _matmul,
    _matvec,
    _norm,
    _transpose,
    hcw_position_from_impulse,
    numerical_impulse_jacobian,
    propagate_mean_anomaly,
)


def weighted_least_squares_with_uncertainty(
    jacobian: Sequence[Sequence[float]], observed: Sequence[float], sigma: Sequence[float]
) -> dict | None:
    """Weighted linear inversion with covariance from the local normal matrix.

    The covariance is a local first-order uncertainty approximation. It represents sensitivity to
    the empirically calibrated element-change scale, not a posterior distribution for an executed burn.
    """
    if len(jacobian) != len(observed) or len(observed) != len(sigma):
        raise ValueError('least-squares dimensions disagree')
    if any(float(value) <= 0.0 or not isfinite(float(value)) for value in sigma):
        raise ValueError('all inversion scales must be finite and positive')
    weighted = [[float(value) / float(sigma[row]) for value in jacobian[row]] for row in range(len(observed))]
    response = [float(observed[row]) / float(sigma[row]) for row in range(len(observed))]
    transposed = _transpose(weighted)
    normal = _matmul(transposed, weighted)
    inverse = _inverse_3x3(normal)
    if inverse is None:
        return None
    solution = _matvec(inverse, _matvec(transposed, response))
    predicted = _matvec(jacobian, solution)
    residuals = [(float(observed[index]) - predicted[index]) / float(sigma[index]) for index in range(len(observed))]
    rms = sqrt(sum(value * value for value in residuals) / len(residuals))
    normal_norm = max(sum(abs(value) for value in row) for row in normal)
    inverse_norm = max(sum(abs(value) for value in row) for row in inverse)
    component_sigma = [sqrt(max(0.0, inverse[index][index])) for index in range(3)]
    return {
        'delta_v_km_s': solution,
        'component_sigma_km_s': component_sigma,
        'weighted_rms': rms,
        'condition_estimate': normal_norm * inverse_norm,
        'predicted': predicted,
    }


class ManeuverPhysicsInverter:
    """Uncertainty-aware equivalent impulsive maneuver inversion.

    The unknown burn epoch is scanned across the GP epoch interval. At each phase, the local
    RTN-to-equinoctial sensitivity is obtained by an independent numerical impulse derivative, and
    weighted least squares estimates the equivalent radial/along/cross impulse. For near-circular
    orbits, an HCW common-epoch RTN prediction provides a second observable family.

    The algorithm returns `feasible` only when direction and magnitude are sufficiently stable.
    Ambiguous burn phase, ill-conditioned geometry, missing calibration support, or broad direction
    uncertainty returns `abstain`; poor joint fit returns `inconsistent`.
    """

    def __init__(
        self,
        noise_model: PhysicsNoiseModel,
        *,
        phase_grid: Sequence[float] | None = None,
        max_condition: float = 1e8,
        max_element_rms: float = 4.0,
        max_rtn_rms: float = 4.0,
        max_delta_v_mps: float = 2000.0,
        max_magnitude_ratio: float = 3.0,
    ) -> None:
        self.noise_model = noise_model
        self.phase_grid = tuple(phase_grid or [0.05 + 0.025 * index for index in range(37)])
        if not self.phase_grid or any(not 0.0 < value < 1.0 for value in self.phase_grid):
            raise ValueError('burn phase grid must lie strictly inside (0,1)')
        self.max_condition = float(max_condition)
        self.max_element_rms = float(max_element_rms)
        self.max_rtn_rms = float(max_rtn_rms)
        self.max_delta_v_mps = float(max_delta_v_mps)
        self.max_magnitude_ratio = float(max_magnitude_ratio)

    def _intervals(self, accepted: list[dict]) -> tuple[tuple[float, float], dict[str, tuple[float, float]]]:
        magnitude_intervals = []
        component_intervals_by_axis: list[list[tuple[float, float]]] = [[], [], []]
        for item in accepted:
            values = item['delta_v']; sigmas = item['component_sigma']
            magnitude_km_s = _norm(values)
            if magnitude_km_s > 1e-15:
                magnitude_sigma_km_s = sqrt(sum(
                    (values[index] / magnitude_km_s) ** 2 * sigmas[index] ** 2 for index in range(3)
                ))
            else:
                magnitude_sigma_km_s = _norm(sigmas)
            uncertainty_mps = max(0.05 * item['magnitude_mps'], 2.0 * magnitude_sigma_km_s * 1000.0)
            magnitude_intervals.append((
                max(0.0, item['magnitude_mps'] - uncertainty_mps),
                item['magnitude_mps'] + uncertainty_mps,
            ))
            for axis in range(3):
                centre = values[axis] * 1000.0
                half = max(0.02 * max(item['magnitude_mps'], 1e-9), 2.0 * sigmas[axis] * 1000.0)
                component_intervals_by_axis[axis].append((centre - half, centre + half))
        magnitude = (
            min(interval[0] for interval in magnitude_intervals),
            max(interval[1] for interval in magnitude_intervals),
        )
        components = {
            name: (
                min(interval[0] for interval in component_intervals_by_axis[index]),
                max(interval[1] for interval in component_intervals_by_axis[index]),
            )
            for index, name in enumerate(('radial', 'along_track', 'cross_track'))
        }
        return magnitude, components

    def _phase_interval(self, accepted: list[dict]) -> tuple[float, float]:
        phases = [item['phase'] for item in accepted]
        spacings = [b - a for a, b in zip(self.phase_grid[:-1], self.phase_grid[1:]) if b > a]
        half_step = 0.5 * min(spacings) if spacings else 0.025
        return (max(0.0, min(phases) - half_step), min(1.0, max(phases) + half_step))

    def estimate(self, row: dict) -> PhysicsEstimate:
        corrected = self.noise_model.corrected(row)
        if corrected is None:
            return PhysicsEstimate(
                'abstain', None, None, None, None, None, None, None, None, None, 0,
                'missing physics observables or insufficient independent verified-quiet support',
            )
        observation = corrected['observation']
        before = observation['before']
        gap_seconds = observation['gap_days'] * SECONDS_PER_DAY
        if before['i'] > pi - 0.05:
            return PhysicsEstimate(
                'abstain', None, None, None, None, None, None, None, None, None, 0,
                'retrograde singularity is outside the prograde equinoctial formulation',
            )

        candidates: list[dict] = []
        well_conditioned = 0
        for phase_fraction in self.phase_grid:
            at_burn = propagate_mean_anomaly(before, gap_seconds * phase_fraction)
            try:
                jacobian = numerical_impulse_jacobian(at_burn)
                solution = weighted_least_squares_with_uncertainty(
                    jacobian, corrected['equi_delta'], corrected['equi_sigma']
                )
            except (ValueError, OverflowError):
                continue
            if solution is None:
                continue
            condition = float(solution['condition_estimate'])
            if not isfinite(condition) or condition > self.max_condition:
                continue
            well_conditioned += 1
            delta_v = solution['delta_v_km_s']
            magnitude_mps = _norm(delta_v) * 1000.0
            if not isfinite(magnitude_mps) or magnitude_mps > self.max_delta_v_mps:
                continue

            rtn_rms = None
            if corrected['rtn_residual_km'] is not None and corrected['rtn_sigma'] is not None and before['e'] <= 0.05:
                predicted_rtn = hcw_position_from_impulse(
                    before['a'], delta_v, gap_seconds * (1.0 - phase_fraction)
                )
                residuals = [
                    (corrected['rtn_residual_km'][index] - predicted_rtn[index]) / corrected['rtn_sigma'][index]
                    for index in range(3)
                ]
                rtn_rms = sqrt(sum(value * value for value in residuals) / 3.0)
            element_rms = float(solution['weighted_rms'])
            combined = element_rms if rtn_rms is None else sqrt(
                (5.0 * element_rms * element_rms + 3.0 * rtn_rms * rtn_rms) / 8.0
            )
            candidates.append({
                'phase': phase_fraction,
                'delta_v': delta_v,
                'component_sigma': solution['component_sigma_km_s'],
                'magnitude_mps': magnitude_mps,
                'element_rms': element_rms,
                'rtn_rms': rtn_rms,
                'combined_rms': combined,
                'condition': condition,
            })

        if well_conditioned == 0:
            return PhysicsEstimate(
                'abstain', None, None, None, None, None, None, None, None, None, 0,
                'impulse inversion is numerically underdetermined over the burn-phase grid',
            )
        if not candidates:
            return PhysicsEstimate(
                'inconsistent', None, None, None, None, None, None, None, None, None, 0,
                'well-conditioned solutions require implausibly large equivalent delta-v',
            )

        best = min(candidates, key=lambda item: item['combined_rms'])
        accepted = [
            item for item in candidates
            if item['element_rms'] <= self.max_element_rms
            and (item['rtn_rms'] is None or item['rtn_rms'] <= self.max_rtn_rms)
            and item['combined_rms'] <= max(best['combined_rms'] + 1.0, 1.25 * best['combined_rms'])
        ]
        if not accepted:
            return PhysicsEstimate(
                'inconsistent', None, None, None, None, None,
                best['element_rms'], best['rtn_rms'], best['combined_rms'], best['condition'], 0,
                'joint element/RTN changes are not consistent with one equivalent impulse at the calibrated noise scale',
            )

        magnitude_interval, component_intervals = self._intervals(accepted)
        point_magnitudes = sorted(item['magnitude_mps'] for item in accepted)
        median_magnitude = median(point_magnitudes)
        phase_interval = self._phase_interval(accepted)
        dominant = []
        for item in accepted:
            values = item['delta_v']
            axis = max(range(3), key=lambda index: abs(values[index]))
            sign = 1 if values[axis] >= 0.0 else -1
            dominant.append((axis, sign))
        consensus = max(set(dominant), key=dominant.count)
        consensus_fraction = dominant.count(consensus) / len(dominant)
        magnitude_ratio = point_magnitudes[-1] / max(point_magnitudes[0], 1e-9)

        unique_phase_corroborated = False
        if len(accepted) == 1:
            item = accepted[0]
            absolute = sorted(abs(value) for value in item['delta_v'])
            strongest = absolute[-1]; runner_up = absolute[-2]
            component_name = ('radial', 'along_track', 'cross_track')[consensus[0]]
            dominant_interval = component_intervals[component_name]
            sign_resolved = dominant_interval[0] > 0.0 or dominant_interval[1] < 0.0
            unique_phase_corroborated = (
                item['rtn_rms'] is not None
                and item['rtn_rms'] <= min(1.0, self.max_rtn_rms / 2.0)
                and item['element_rms'] <= min(1.0, self.max_element_rms / 2.0)
                and strongest >= 1.5 * max(runner_up, 1e-12)
                and sign_resolved
            )

        if (
            (len(accepted) < 2 and not unique_phase_corroborated)
            or consensus_fraction < 0.8
            or magnitude_ratio > self.max_magnitude_ratio
        ):
            return PhysicsEstimate(
                'abstain', None, magnitude_interval, median_magnitude, component_intervals, phase_interval,
                best['element_rms'], best['rtn_rms'], best['combined_rms'], best['condition'], len(accepted),
                'burn phase/direction is underdetermined; returning only an uncertainty-bounded equivalent delta-v interval',
            )

        axis_name = ('radial', 'along-track', 'cross-track')[consensus[0]]
        sign_name = 'positive' if consensus[1] > 0 else 'negative'
        return PhysicsEstimate(
            'feasible', f'{sign_name} {axis_name}', magnitude_interval, median_magnitude,
            component_intervals, phase_interval, best['element_rms'], best['rtn_rms'],
            best['combined_rms'], best['condition'], len(accepted),
            'joint nonsingular-element change is consistent with an equivalent RTN impulse; common-epoch RTN corroboration applied where HCW is valid',
        )
