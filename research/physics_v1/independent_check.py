#!/usr/bin/env python3
from __future__ import annotations

from math import cos, pi, sin, sqrt, tan, ulp

from .core import (
    MU_EARTH_KM3_S2,
    PhysicsNoiseModel,
    RegimeNoise,
    _angle_difference,
    apply_rtn_impulse,
    equinoctial_vector,
    hcw_position_from_impulse,
    numerical_impulse_jacobian,
    propagate_mean_anomaly,
    true_anomaly_from_mean,
)
from .screen import ManeuverPhysicsInverter


def classical_gauss_impulse(elements: dict[str, float], delta_v_km_s: tuple[float, float, float]) -> dict[str, float]:
    """Independent first-order classical Gauss variational-equation impulse calculation."""
    a = elements['a']; e = elements['e']; inc = elements['i']; argp = elements['argp']
    true = true_anomaly_from_mean(elements['M'], e)
    p = a * (1.0 - e * e)
    radius = p / (1.0 + e * cos(true))
    angular_momentum = sqrt(MU_EARTH_KM3_S2 * p)
    radial, along, cross = delta_v_km_s
    argument_latitude = argp + true
    da = 2.0 * a * a / angular_momentum * (e * sin(true) * radial + (p / radius) * along)
    de = 1.0 / angular_momentum * (
        p * sin(true) * radial + ((p + radius) * cos(true) + radius * e) * along
    )
    di = radius * cos(argument_latitude) / angular_momentum * cross
    if abs(sin(inc)) < 1e-8 or e < 1e-8:
        raise ValueError('independent classical GVE check requires nonsingular classical geometry')
    draan = radius * sin(argument_latitude) / (angular_momentum * sin(inc)) * cross
    dargp = (
        (-p * cos(true) * radial + (p + radius) * sin(true) * along) / (angular_momentum * e)
        - radius * sin(argument_latitude) * cos(inc) / (angular_momentum * sin(inc)) * cross
    )
    return {'a': da, 'e': de, 'i': di, 'raan': draan, 'argp': dargp}


def _assert_close(actual: float, expected: float, *, relative: float = 5e-3, absolute: float = 2e-8) -> None:
    if abs(actual - expected) > max(absolute, relative * max(abs(expected), absolute)):
        raise AssertionError(f'{actual} != {expected}')


def _validation_orbit() -> dict[str, float]:
    return {
        'a': 8000.0,
        'e': 0.15,
        'i': 55.0 * pi / 180.0,
        'raan': 30.0 * pi / 180.0,
        'argp': 70.0 * pi / 180.0,
        'M': 120.0 * pi / 180.0,
    }


def validate_gauss_against_cartesian() -> None:
    base = _validation_orbit()
    impulses = [
        (3e-5, 0.0, 0.0),
        (0.0, 3e-5, 0.0),
        (0.0, 0.0, 3e-5),
        (1e-5, 2e-5, -1e-5),
    ]
    for impulse in impulses:
        predicted = classical_gauss_impulse(base, impulse)
        post = apply_rtn_impulse(base, impulse)
        actual = {
            'a': post['a'] - base['a'],
            'e': post['e'] - base['e'],
            'i': _angle_difference(post['i'], base['i']),
            'raan': _angle_difference(post['raan'], base['raan']),
            'argp': _angle_difference(post['argp'], base['argp']),
        }
        for key in ('a', 'e', 'i', 'raan', 'argp'):
            if abs(predicted[key]) < 1e-10:
                continue
            _assert_close(actual[key], predicted[key])


def validate_production_jacobian_against_gauss() -> None:
    """Compare the production equinoctial RTN Jacobian directly with independent GVE predictions.

    This check avoids validating the inversion only with synthetic states created by the same
    Cartesian impulse helper used inside the production finite-difference Jacobian. The expected
    first-order response is obtained from the classical Gauss equations and then mapped into the
    same nonsingular [p,f,g,h,k] coordinates used by the production inverse problem.
    """
    base = _validation_orbit()
    step_km_s = 1e-7
    production = numerical_impulse_jacobian(base, step_km_s=step_km_s)
    expected = [[0.0, 0.0, 0.0] for _ in range(5)]

    for axis in range(3):
        impulse = [0.0, 0.0, 0.0]
        impulse[axis] = step_km_s
        delta = classical_gauss_impulse(base, tuple(impulse))
        a = base['a']; e = base['e']; inc = base['i']; raan = base['raan']; argp = base['argp']
        da = delta['a'] / step_km_s
        de = delta['e'] / step_km_s
        di = delta['i'] / step_km_s
        draan = delta['raan'] / step_km_s
        dargp = delta['argp'] / step_km_s
        longitude_periapsis = raan + argp
        half_tangent = tan(inc / 2.0)
        d_half_tangent = 0.5 * (1.0 + half_tangent * half_tangent) * di
        expected[0][axis] = (1.0 - e * e) * da - 2.0 * a * e * de
        expected[1][axis] = cos(longitude_periapsis) * de - e * sin(longitude_periapsis) * (draan + dargp)
        expected[2][axis] = sin(longitude_periapsis) * de + e * cos(longitude_periapsis) * (draan + dargp)
        expected[3][axis] = cos(raan) * d_half_tangent - half_tangent * sin(raan) * draan
        expected[4][axis] = sin(raan) * d_half_tangent + half_tangent * cos(raan) * draan

    baseline = equinoctial_vector(base)
    for row in range(5):
        for axis in range(3):
            if abs(expected[row][axis]) <= 1e-12:
                # Differentiating a mathematically zero component amplifies the few-ULP
                # Cartesian-to-elements round-trip noise by 1/step. Bound that local
                # cancellation explicitly instead of weakening nonzero derivatives.
                cancellation_bound = max(2e-6, 8.0 * ulp(baseline[row]) / step_km_s)
                if abs(production[row][axis]) > cancellation_bound:
                    raise AssertionError(
                        f'near-zero derivative {production[row][axis]} exceeds {cancellation_bound}'
                    )
            else:
                _assert_close(production[row][axis], expected[row][axis], relative=7.5e-3, absolute=2e-6)


def _payload(elements: dict[str, float]) -> dict:
    mean_motion = sqrt(MU_EARTH_KM3_S2 / elements['a'] ** 3) * 86400.0 / (2.0 * pi)
    return {
        'semi_major_axis_km': elements['a'],
        'eccentricity': elements['e'],
        'inclination_deg': elements['i'] * 180.0 / pi,
        'raan_deg': elements['raan'] * 180.0 / pi,
        'argument_of_periapsis_deg': elements['argp'] * 180.0 / pi,
        'mean_anomaly_deg': elements['M'] * 180.0 / pi,
        'mean_motion_rev_per_day': mean_motion,
    }


def synthetic_row(delta_v_mps: tuple[float, float, float], *, burn_fraction: float = 0.4, gap_days: float = 0.25, with_rtn: bool = True) -> dict:
    before = {
        'a': 7000.0,
        'e': 0.01,
        'i': 51.6 * pi / 180.0,
        'raan': 35.0 * pi / 180.0,
        'argp': 25.0 * pi / 180.0,
        'M': 40.0 * pi / 180.0,
    }
    at_burn = propagate_mean_anomaly(before, burn_fraction * gap_days * 86400.0)
    delta_v = tuple(value / 1000.0 for value in delta_v_mps)
    after = apply_rtn_impulse(at_burn, delta_v)
    after['M'] = propagate_mean_anomaly(after, (1.0 - burn_fraction) * gap_days * 86400.0)['M']
    residual = hcw_position_from_impulse(before['a'], delta_v, (1.0 - burn_fraction) * gap_days * 86400.0) if with_rtn else None
    return {
        'case_id': 'synthetic', 'object_id': '99999', 'orbit_regime': 'LEO', 'orbit_profile': 'LEO',
        'nominal': False, 'quality_ok': True,
        'physics': {
            'gap_days': gap_days,
            'before_elements': _payload(before),
            'after_elements': _payload(after),
            'rtn_residual_km': None if residual is None else {'radial': residual[0], 'along_track': residual[1], 'cross_track': residual[2]},
        },
    }


def synthetic_noise_model() -> PhysicsNoiseModel:
    model = PhysicsNoiseModel(min_reference_satellites=3)
    model.regimes['LEO'] = RegimeNoise(
        reference_objects=('1', '2', '3'),
        equi_rate_centre=(0.0, 0.0, 0.0, 0.0, 0.0),
        equi_rate_scale=PhysicsNoiseModel.EQUI_RATE_FLOORS,
        rtn_rate_centre=(0.0, 0.0, 0.0),
        rtn_rate_scale=PhysicsNoiseModel.RTN_RATE_FLOORS,
    )
    return model


def validate_injected_maneuvers() -> None:
    inverter = ManeuverPhysicsInverter(synthetic_noise_model(), max_element_rms=5.0, max_rtn_rms=5.0)
    cases = [
        ((0.12, 0.02, 0.0), 'radial'),
        ((0.01, 0.15, 0.0), 'along-track'),
        ((0.0, 0.01, -0.12), 'cross-track'),
    ]
    for delta_v, expected_axis in cases:
        estimate = inverter.estimate(synthetic_row(delta_v))
        if not estimate.feasible:
            raise AssertionError(f'{expected_axis} injection did not invert as feasible: {estimate}')
        if expected_axis not in str(estimate.direction):
            raise AssertionError(f'{expected_axis} injection direction mismatch: {estimate.direction}')
        truth = sqrt(sum(value * value for value in delta_v))
        low, high = estimate.delta_v_interval_mps or (0.0, 0.0)
        if not low <= truth <= high:
            raise AssertionError(f'true delta-v {truth} m/s outside recovered interval {low, high}')


def validate_underdetermined_abstention() -> None:
    inverter = ManeuverPhysicsInverter(synthetic_noise_model(), max_element_rms=5.0, max_rtn_rms=5.0)
    estimate = inverter.estimate(synthetic_row((0.12, 0.02, 0.0), with_rtn=False))
    if estimate.status == 'feasible' and estimate.burn_phase_interval and (estimate.burn_phase_interval[1] - estimate.burn_phase_interval[0]) > 0.6:
        raise AssertionError('wide burn-phase ambiguity was reported with false directional precision')


def main() -> None:
    validate_gauss_against_cartesian()
    print('PASS analytic classical GVE vs independent Cartesian impulse')
    validate_production_jacobian_against_gauss()
    print('PASS production equinoctial Jacobian vs analytic classical GVE')
    validate_injected_maneuvers()
    print('PASS deterministic radial/along/cross injected maneuvers')
    validate_underdetermined_abstention()
    print('PASS underdetermined inversion does not report false precision')


if __name__ == '__main__':
    main()
