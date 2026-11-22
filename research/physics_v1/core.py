#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
from math import acos, atan2, cos, isfinite, pi, sin, sqrt, tan
from statistics import median
from typing import Iterable, Sequence

MU_EARTH_KM3_S2 = 398600.4418
SECONDS_PER_DAY = 86400.0

EQUI_NAMES = ('p_km', 'f', 'g', 'h', 'k')
RTN_NAMES = ('radial_km', 'along_km', 'cross_km')


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _norm(vector: Sequence[float]) -> float:
    return sqrt(sum(float(value) ** 2 for value in vector))


def _dot(first: Sequence[float], second: Sequence[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(first, second))


def _cross(first: Sequence[float], second: Sequence[float]) -> list[float]:
    a, b, c = first
    d, e, f = second
    return [b * f - c * e, c * d - a * f, a * e - b * d]


def _add(first: Sequence[float], second: Sequence[float]) -> list[float]:
    return [float(a) + float(b) for a, b in zip(first, second)]


def _sub(first: Sequence[float], second: Sequence[float]) -> list[float]:
    return [float(a) - float(b) for a, b in zip(first, second)]


def _scale(vector: Sequence[float], factor: float) -> list[float]:
    return [float(value) * float(factor) for value in vector]


def _unit(vector: Sequence[float]) -> list[float]:
    length = _norm(vector)
    if length <= 0.0:
        raise ValueError('zero-length vector')
    return _scale(vector, 1.0 / length)


def _wrap_2pi(angle: float) -> float:
    return float(angle) % (2.0 * pi)


def _angle_difference(first: float, second: float) -> float:
    return (float(first) - float(second) + pi) % (2.0 * pi) - pi


def _rotate_z(angle: float, vector: Sequence[float]) -> list[float]:
    c = cos(angle); s = sin(angle)
    x, y, z = vector
    return [c * x - s * y, s * x + c * y, z]


def _rotate_x(angle: float, vector: Sequence[float]) -> list[float]:
    c = cos(angle); s = sin(angle)
    x, y, z = vector
    return [x, c * y - s * z, s * y + c * z]


def solve_kepler(mean_anomaly_rad: float, eccentricity: float) -> float:
    e = float(eccentricity)
    if not 0.0 <= e < 1.0:
        raise ValueError('elliptic eccentricity must lie in [0,1)')
    if not isfinite(float(mean_anomaly_rad)):
        raise ValueError('mean anomaly must be finite')
    mean = (float(mean_anomaly_rad) + pi) % (2.0 * pi) - pi
    eccentric = mean if e < 0.8 else pi
    for _ in range(64):
        residual = eccentric - e * sin(eccentric) - mean
        derivative = 1.0 - e * cos(eccentric)
        step = residual / derivative
        eccentric -= step
        if abs(step) < 1e-14 and abs(eccentric - e * sin(eccentric) - mean) < 1e-13:
            return eccentric
        if not isfinite(eccentric):
            break

    if isfinite(eccentric) and abs(eccentric - e * sin(eccentric) - mean) < 1e-13:
        return eccentric

    # Preserve the historical Newton result when it converges. Its unconstrained
    # iteration can diverge for high eccentricity and negative mean anomaly.
    # On [-pi, pi], E - e*sin(E) is strictly increasing for every elliptic e,
    # so bisection supplies a bounded fallback instead of returning a wrong orbit.
    lower, upper = -pi, pi
    for _ in range(96):
        eccentric = 0.5 * (lower + upper)
        residual = eccentric - e * sin(eccentric) - mean
        if residual == 0.0 or upper - lower <= 2e-15:
            return eccentric
        if residual < 0.0:
            lower = eccentric
        else:
            upper = eccentric
    raise ArithmeticError('elliptic Kepler solver did not converge')


def true_anomaly_from_mean(mean_anomaly_rad: float, eccentricity: float) -> float:
    eccentric = solve_kepler(mean_anomaly_rad, eccentricity)
    e = float(eccentricity)
    return 2.0 * atan2(sqrt(1.0 + e) * sin(eccentric / 2.0), sqrt(1.0 - e) * cos(eccentric / 2.0))


def _element_dict(payload: dict) -> dict[str, float]:
    required = {
        'a': payload.get('semi_major_axis_km'),
        'e': payload.get('eccentricity'),
        'i': None if payload.get('inclination_deg') is None else float(payload['inclination_deg']) * pi / 180.0,
        'raan': None if payload.get('raan_deg') is None else float(payload['raan_deg']) * pi / 180.0,
        'argp': None if payload.get('argument_of_periapsis_deg') is None else float(payload['argument_of_periapsis_deg']) * pi / 180.0,
        'M': None if payload.get('mean_anomaly_deg') is None else float(payload['mean_anomaly_deg']) * pi / 180.0,
    }
    if any(_finite(value) is None for value in required.values()):
        raise ValueError('incomplete orbital-element payload')
    result = {key: float(value) for key, value in required.items()}
    if result['a'] <= 0.0 or not 0.0 <= result['e'] < 1.0:
        raise ValueError('unsupported orbital elements')
    return result


def equinoctial_vector(elements: dict[str, float]) -> list[float]:
    """Nonsingular prograde equinoctial subset [p,f,g,h,k].

    f=e cos(Omega+omega), g=e sin(Omega+omega),
    h=tan(i/2) cos(Omega), k=tan(i/2) sin(Omega).
    The mean/true longitude is deliberately omitted because the burn epoch is unknown inside the GP gap.
    """
    a = float(elements['a']); e = float(elements['e']); inc = float(elements['i'])
    raan = float(elements['raan']); argp = float(elements['argp'])
    p = a * (1.0 - e * e)
    longitude_periapsis = raan + argp
    half_tangent = tan(inc / 2.0)
    return [
        p,
        e * cos(longitude_periapsis),
        e * sin(longitude_periapsis),
        half_tangent * cos(raan),
        half_tangent * sin(raan),
    ]


def state_from_elements(elements: dict[str, float]) -> tuple[list[float], list[float], float]:
    a = float(elements['a']); e = float(elements['e']); inc = float(elements['i'])
    raan = float(elements['raan']); argp = float(elements['argp']); mean = float(elements['M'])
    true_anomaly = true_anomaly_from_mean(mean, e)
    p = a * (1.0 - e * e)
    radius = p / (1.0 + e * cos(true_anomaly))
    position_pf = [radius * cos(true_anomaly), radius * sin(true_anomaly), 0.0]
    velocity_scale = sqrt(MU_EARTH_KM3_S2 / p)
    velocity_pf = [-velocity_scale * sin(true_anomaly), velocity_scale * (e + cos(true_anomaly)), 0.0]
    position = _rotate_z(raan, _rotate_x(inc, _rotate_z(argp, position_pf)))
    velocity = _rotate_z(raan, _rotate_x(inc, _rotate_z(argp, velocity_pf)))
    return position, velocity, true_anomaly


def elements_from_state(position: Sequence[float], velocity: Sequence[float]) -> dict[str, float]:
    r = [float(value) for value in position]; v = [float(value) for value in velocity]
    rmag = _norm(r); vmag = _norm(v)
    angular = _cross(r, v); hmag = _norm(angular)
    if rmag <= 0.0 or hmag <= 0.0:
        raise ValueError('degenerate Cartesian state')
    node = _cross([0.0, 0.0, 1.0], angular); nmag = _norm(node)
    eccentricity_vector = _sub(_scale(_cross(v, angular), 1.0 / MU_EARTH_KM3_S2), _scale(r, 1.0 / rmag))
    eccentricity = _norm(eccentricity_vector)
    energy = 0.5 * vmag * vmag - MU_EARTH_KM3_S2 / rmag
    if energy >= 0.0 or eccentricity >= 1.0:
        raise ValueError('impulse produced non-elliptic orbit')
    semimajor = -MU_EARTH_KM3_S2 / (2.0 * energy)
    inclination = acos(max(-1.0, min(1.0, angular[2] / hmag)))
    raan = _wrap_2pi(atan2(node[1], node[0])) if nmag > 1e-12 else 0.0

    if eccentricity > 1e-12 and nmag > 1e-12:
        cos_argp = max(-1.0, min(1.0, _dot(node, eccentricity_vector) / (nmag * eccentricity)))
        sin_argp = _dot(_cross(node, eccentricity_vector), angular) / (nmag * eccentricity * hmag)
        argp = _wrap_2pi(atan2(sin_argp, cos_argp))
    elif eccentricity > 1e-12:
        argp = _wrap_2pi(atan2(eccentricity_vector[1], eccentricity_vector[0]))
    else:
        argp = 0.0

    if eccentricity > 1e-12:
        cos_true = max(-1.0, min(1.0, _dot(eccentricity_vector, r) / (eccentricity * rmag)))
        sin_true = _dot(_cross(eccentricity_vector, r), angular) / (eccentricity * rmag * hmag)
        true_anomaly = atan2(sin_true, cos_true)
        eccentric_anomaly = 2.0 * atan2(sqrt(1.0 - eccentricity) * sin(true_anomaly / 2.0), sqrt(1.0 + eccentricity) * cos(true_anomaly / 2.0))
        mean_anomaly = _wrap_2pi(eccentric_anomaly - eccentricity * sin(eccentric_anomaly))
    elif nmag > 1e-12:
        cos_u = max(-1.0, min(1.0, _dot(node, r) / (nmag * rmag)))
        sin_u = _dot(_cross(node, r), angular) / (nmag * rmag * hmag)
        mean_anomaly = _wrap_2pi(atan2(sin_u, cos_u))
    else:
        mean_anomaly = _wrap_2pi(atan2(r[1], r[0]))

    return {'a': semimajor, 'e': eccentricity, 'i': inclination, 'raan': raan, 'argp': argp, 'M': mean_anomaly}


def apply_rtn_impulse(elements: dict[str, float], delta_v_km_s: Sequence[float]) -> dict[str, float]:
    position, velocity, _ = state_from_elements(elements)
    radial = _unit(position)
    normal = _unit(_cross(position, velocity))
    along = _cross(normal, radial)
    dv = [
        radial[index] * float(delta_v_km_s[0]) + along[index] * float(delta_v_km_s[1]) + normal[index] * float(delta_v_km_s[2])
        for index in range(3)
    ]
    return elements_from_state(position, _add(velocity, dv))


def propagate_mean_anomaly(elements: dict[str, float], elapsed_seconds: float) -> dict[str, float]:
    output = dict(elements)
    mean_motion_rad_s = sqrt(MU_EARTH_KM3_S2 / float(elements['a']) ** 3)
    output['M'] = _wrap_2pi(float(elements['M']) + mean_motion_rad_s * float(elapsed_seconds))
    return output


def numerical_impulse_jacobian(elements_at_burn: dict[str, float], *, step_km_s: float = 1e-6) -> list[list[float]]:
    if step_km_s <= 0.0:
        raise ValueError('finite-difference step must be positive')
    baseline = equinoctial_vector(elements_at_burn)
    columns: list[list[float]] = []
    for axis in range(3):
        impulse = [0.0, 0.0, 0.0]; impulse[axis] = step_km_s
        perturbed = equinoctial_vector(apply_rtn_impulse(elements_at_burn, impulse))
        columns.append([(perturbed[index] - baseline[index]) / step_km_s for index in range(len(baseline))])
    return [[columns[column][row] for column in range(3)] for row in range(len(baseline))]


def _transpose(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    return [list(row) for row in zip(*matrix)]


def _matmul(first: Sequence[Sequence[float]], second: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[sum(first[i][k] * second[k][j] for k in range(len(second))) for j in range(len(second[0]))] for i in range(len(first))]


def _matvec(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    return [sum(float(a) * float(b) for a, b in zip(row, vector)) for row in matrix]


def _inverse_3x3(matrix: Sequence[Sequence[float]]) -> list[list[float]] | None:
    a, b, c = matrix[0]; d, e, f = matrix[1]; g, h, i = matrix[2]
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    scale = max(1.0, max(abs(value) for row in matrix for value in row))
    if abs(determinant) <= 1e-14 * scale ** 3:
        return None
    cofactors = [
        [e * i - f * h, c * h - b * i, b * f - c * e],
        [f * g - d * i, a * i - c * g, c * d - a * f],
        [d * h - e * g, b * g - a * h, a * e - b * d],
    ]
    return [[value / determinant for value in row] for row in cofactors]


def weighted_least_squares(jacobian: Sequence[Sequence[float]], observed: Sequence[float], sigma: Sequence[float]) -> dict | None:
    if len(jacobian) != len(observed) or len(observed) != len(sigma):
        raise ValueError('least-squares dimensions disagree')
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
    return {'delta_v_km_s': solution, 'weighted_rms': rms, 'condition_estimate': normal_norm * inverse_norm, 'predicted': predicted}


def hcw_position_from_impulse(semimajor_axis_km: float, delta_v_km_s: Sequence[float], elapsed_seconds: float) -> list[float]:
    """Near-circular Hill-Clohessy-Wiltshire position response to an RTN impulse.

    Used only as a secondary common-epoch RTN consistency test for e <= 0.05. The element inversion
    itself does not rely on HCW.
    """
    n = sqrt(MU_EARTH_KM3_S2 / float(semimajor_axis_km) ** 3)
    phase = n * float(elapsed_seconds)
    radial_dv, along_dv, cross_dv = [float(value) for value in delta_v_km_s]
    radial = sin(phase) / n * radial_dv + 2.0 * (1.0 - cos(phase)) / n * along_dv
    along = -2.0 * (1.0 - cos(phase)) / n * radial_dv + (4.0 * sin(phase) - 3.0 * phase) / n * along_dv
    cross = sin(phase) / n * cross_dv
    return [radial, along, cross]


def _mad(values: Sequence[float], centre: float) -> float:
    return median([abs(float(value) - float(centre)) for value in values]) if values else 0.0


def _robust_centre_scale(values: Sequence[float], floor: float) -> tuple[float, float]:
    if not values:
        return 0.0, float(floor)
    centre = median([float(value) for value in values])
    scale = max(float(floor), 1.4826 * _mad(values, centre))
    return centre, scale


def physics_observation(row: dict) -> dict | None:
    payload = row.get('physics') or {}
    try:
        gap_days = float(payload['gap_days'])
        before = _element_dict(payload['before_elements'])
        after = _element_dict(payload['after_elements'])
    except (KeyError, TypeError, ValueError):
        return None
    if not isfinite(gap_days) or gap_days <= 0.0:
        return None
    before_equi = equinoctial_vector(before); after_equi = equinoctial_vector(after)
    equi_delta = [after_equi[index] - before_equi[index] for index in range(5)]
    residual = payload.get('rtn_residual_km')
    rtn = None
    if isinstance(residual, dict):
        values = [residual.get('radial'), residual.get('along_track'), residual.get('cross_track')]
        if all(_finite(value) is not None for value in values):
            rtn = [float(value) for value in values]
    return {'gap_days': gap_days, 'before': before, 'after': after, 'equi_delta': equi_delta, 'rtn_residual_km': rtn}


@dataclass
class RegimeNoise:
    reference_objects: tuple[str, ...]
    equi_rate_centre: tuple[float, ...]
    equi_rate_scale: tuple[float, ...]
    rtn_rate_centre: tuple[float, ...]
    rtn_rate_scale: tuple[float, ...]


@dataclass
class PhysicsNoiseModel:
    min_reference_satellites: int = 3
    regimes: dict[str, RegimeNoise] = field(default_factory=dict)

    EQUI_RATE_FLOORS = (0.05, 1e-7, 1e-7, 1e-7, 1e-7)
    RTN_RATE_FLOORS = (0.08, 0.35, 0.08)

    @staticmethod
    def _regime(row: dict) -> str:
        key = str(row.get('orbit_regime') or row.get('orbit_profile') or '').upper()
        return 'GEO' if key == 'IGSO' else key

    def fit(self, rows: Iterable[dict]) -> 'PhysicsNoiseModel':
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            object_id = row.get('object_id')
            if (
                row.get('nominal') is not True or row.get('quality_ok') is False
                or not isinstance(object_id, (str, int)) or isinstance(object_id, bool)
                or not str(object_id).strip()
            ):
                continue
            observation = physics_observation(row)
            if observation is None:
                continue
            regime = self._regime(row)
            grouped.setdefault(regime, []).append({'row': row, 'obs': observation})
        self.regimes = {}
        for regime, items in grouped.items():
            objects = sorted({str(item['row'].get('object_id')) for item in items if str(item['row'].get('object_id', '')).strip()})
            if len(objects) < self.min_reference_satellites:
                continue
            equi_rates = [[item['obs']['equi_delta'][index] / item['obs']['gap_days'] for item in items] for index in range(5)]
            rtn_items = [item for item in items if item['obs']['rtn_residual_km'] is not None]
            rtn_rates = [[item['obs']['rtn_residual_km'][index] / item['obs']['gap_days'] for item in rtn_items] for index in range(3)]
            equi_stats = [_robust_centre_scale(values, self.EQUI_RATE_FLOORS[index]) for index, values in enumerate(equi_rates)]
            rtn_stats = [_robust_centre_scale(values, self.RTN_RATE_FLOORS[index]) for index, values in enumerate(rtn_rates)]
            self.regimes[regime] = RegimeNoise(
                reference_objects=tuple(objects),
                equi_rate_centre=tuple(item[0] for item in equi_stats),
                equi_rate_scale=tuple(item[1] for item in equi_stats),
                rtn_rate_centre=tuple(item[0] for item in rtn_stats),
                rtn_rate_scale=tuple(item[1] for item in rtn_stats),
            )
        return self

    def qualified_regimes(self) -> set[str]:
        return set(self.regimes)

    def corrected(self, row: dict) -> dict | None:
        observation = physics_observation(row)
        if observation is None:
            return None
        regime = self._regime(row)
        noise = self.regimes.get(regime)
        if noise is None:
            return None
        gap = observation['gap_days']
        equi = [observation['equi_delta'][index] - noise.equi_rate_centre[index] * gap for index in range(5)]
        equi_sigma = [max(self.EQUI_RATE_FLOORS[index] * gap, noise.equi_rate_scale[index] * gap) for index in range(5)]
        rtn = observation['rtn_residual_km']
        corrected_rtn = None; rtn_sigma = None
        if rtn is not None:
            corrected_rtn = [rtn[index] - noise.rtn_rate_centre[index] * gap for index in range(3)]
            rtn_sigma = [max(self.RTN_RATE_FLOORS[index] * gap, noise.rtn_rate_scale[index] * gap) for index in range(3)]
        return {'observation': observation, 'equi_delta': equi, 'equi_sigma': equi_sigma, 'rtn_residual_km': corrected_rtn, 'rtn_sigma': rtn_sigma}


@dataclass(frozen=True)
class PhysicsEstimate:
    status: str
    direction: str | None
    delta_v_interval_mps: tuple[float, float] | None
    delta_v_median_mps: float | None
    component_intervals_mps: dict[str, tuple[float, float]] | None
    burn_phase_interval: tuple[float, float] | None
    best_element_rms: float | None
    best_rtn_rms: float | None
    best_combined_rms: float | None
    condition_estimate: float | None
    candidate_count: int
    reason: str

    @property
    def feasible(self) -> bool:
        return self.status == 'feasible'


class _LegacyManeuverPhysicsInverter:
    """Historical first-pass inverter retained only for implementation provenance.

    The package API uses `physics_v1.screen.ManeuverPhysicsInverter`; this older internal class is not
    used by Physics evaluation experiments.

    Equivalent impulsive maneuver inversion in nonsingular equinoctial coordinates.

    The inversion scans the unknown burn phase inside the GP epoch gap. Each phase uses a numerical
    derivative of a two-body RTN impulse mapping in [p,f,g,h,k]. For near-circular orbits, a separate
    HCW prediction checks the observed common-epoch SGP4 RTN residual. The returned delta-v is an
    *equivalent impulse interval*, not a reconstructed burn profile.
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

    def estimate(self, row: dict) -> PhysicsEstimate:
        corrected = self.noise_model.corrected(row)
        if corrected is None:
            return PhysicsEstimate('abstain', None, None, None, None, None, None, None, None, None, 0, 'missing physics observables or insufficient independent quiet support')
        observation = corrected['observation']; before = observation['before']; gap_seconds = observation['gap_days'] * SECONDS_PER_DAY
        if before['i'] > pi - 0.05:
            return PhysicsEstimate('abstain', None, None, None, None, None, None, None, None, None, 0, 'retrograde singularity is outside the prograde equinoctial formulation')

        candidates = []
        well_conditioned = 0
        for phase_fraction in self.phase_grid:
            at_burn = propagate_mean_anomaly(before, gap_seconds * phase_fraction)
            try:
                jacobian = numerical_impulse_jacobian(at_burn)
                solution = weighted_least_squares(jacobian, corrected['equi_delta'], corrected['equi_sigma'])
            except (ValueError, OverflowError):
                continue
            if solution is None or not isfinite(solution['condition_estimate']) or solution['condition_estimate'] > self.max_condition:
                continue
            well_conditioned += 1
            delta_v = solution['delta_v_km_s']
            magnitude_mps = _norm(delta_v) * 1000.0
            if not isfinite(magnitude_mps) or magnitude_mps > self.max_delta_v_mps:
                continue
            rtn_rms = None
            if corrected['rtn_residual_km'] is not None and corrected['rtn_sigma'] is not None and before['e'] <= 0.05:
                predicted_rtn = hcw_position_from_impulse(before['a'], delta_v, gap_seconds * (1.0 - phase_fraction))
                residuals = [(corrected['rtn_residual_km'][index] - predicted_rtn[index]) / corrected['rtn_sigma'][index] for index in range(3)]
                rtn_rms = sqrt(sum(value * value for value in residuals) / 3.0)
            element_rms = float(solution['weighted_rms'])
            combined = element_rms if rtn_rms is None else sqrt((5.0 * element_rms * element_rms + 3.0 * rtn_rms * rtn_rms) / 8.0)
            candidates.append({
                'phase': phase_fraction,
                'delta_v': delta_v,
                'magnitude_mps': magnitude_mps,
                'element_rms': element_rms,
                'rtn_rms': rtn_rms,
                'combined_rms': combined,
                'condition': solution['condition_estimate'],
            })

        if well_conditioned == 0:
            return PhysicsEstimate('abstain', None, None, None, None, None, None, None, None, None, 0, 'impulse inversion is numerically underdetermined over the burn-phase grid')
        if not candidates:
            return PhysicsEstimate('inconsistent', None, None, None, None, None, None, None, None, None, 0, 'well-conditioned solutions require implausibly large delta-v')

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
                'joint element/RTN changes are not consistent with a single equivalent impulse at calibrated noise scale',
            )

        magnitudes = sorted(item['magnitude_mps'] for item in accepted)
        lower = magnitudes[0]; upper = magnitudes[-1]; med = median(magnitudes)
        components = {
            'radial': tuple(sorted(item['delta_v'][0] * 1000.0 for item in accepted)[index] for index in (0, len(accepted) - 1)),
            'along_track': tuple(sorted(item['delta_v'][1] * 1000.0 for item in accepted)[index] for index in (0, len(accepted) - 1)),
            'cross_track': tuple(sorted(item['delta_v'][2] * 1000.0 for item in accepted)[index] for index in (0, len(accepted) - 1)),
        }
        phases = [item['phase'] for item in accepted]
        dominant = []
        for item in accepted:
            values = item['delta_v']
            axis = max(range(3), key=lambda index: abs(values[index]))
            sign = 1 if values[axis] >= 0.0 else -1
            dominant.append((axis, sign))
        consensus = max(set(dominant), key=dominant.count)
        consensus_fraction = dominant.count(consensus) / len(dominant)
        ratio = upper / max(lower, 1e-9)
        if len(accepted) < 2 or consensus_fraction < 0.8 or ratio > self.max_magnitude_ratio:
            return PhysicsEstimate(
                'abstain', None, (lower, upper), med, None, (min(phases), max(phases)),
                best['element_rms'], best['rtn_rms'], best['combined_rms'], best['condition'], len(accepted),
                'burn phase/direction is underdetermined; returning only a broad equivalent delta-v interval',
            )
        axis_name = ('radial', 'along-track', 'cross-track')[consensus[0]]
        sign_name = 'positive' if consensus[1] > 0 else 'negative'
        return PhysicsEstimate(
            'feasible', f'{sign_name} {axis_name}', (lower, upper), med, components,
            (min(phases), max(phases)), best['element_rms'], best['rtn_rms'], best['combined_rms'], best['condition'], len(accepted),
            'joint nonsingular-element change is consistent with an equivalent RTN impulse; RTN residual corroboration applied where HCW is valid',
        )
