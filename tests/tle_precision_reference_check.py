#!/usr/bin/env python3
"""Compare precise app epochs, propagated states and RTN residuals with Python SGP4."""
from __future__ import annotations

import json
import math
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from sgp4.api import Satrec

ROOT = Path(__file__).resolve().parents[1]
DAY_US = 86_400_000_000
POSITION_TOLERANCE_M = 1e-6
VELOCITY_TOLERANCE_MPS = 1e-9
LINE1_CORE = '1 25544U 98067A   26187.00000000  .00000100  00000-0  10000-4 0  999'
LINE2_CORE = '2 25544  51.6400  85.0000 0005000  96.0000  50.0000 15.5000000012345'


def checksum(core: str) -> str:
    assert len(core) == 68
    total = sum(int(char) if char.isdigit() else int(char == '-') for char in core)
    return core + str(total % 10)


def tle(epoch: str, mean_motion: float, anomaly: float) -> tuple[str, str]:
    line1 = LINE1_CORE[:18] + epoch + LINE1_CORE[32:]
    line2 = LINE2_CORE[:43] + f'{anomaly:8.4f}' + LINE2_CORE[51:52] + f'{mean_motion:11.8f}' + LINE2_CORE[63:]
    return checksum(line1), checksum(line2)


def epoch_us(line1: str) -> int:
    """Independent integer conversion; never round fractional days through float."""
    field = line1[18:32]
    year2 = int(field[:2])
    year = 2000 + year2 if year2 < 57 else 1900 + year2
    whole_days = (datetime(year, 1, 1) - datetime(1970, 1, 1)).days + int(field[2:5]) - 1
    return whole_days * DAY_US + int(field[6:]) * 864


def utc_string(value: int) -> str:
    return (datetime(1970, 1, 1) + timedelta(microseconds=value)).isoformat(timespec='microseconds') + 'Z'


def fixtures() -> list[dict]:
    # All data are synthetic and ephemeral. These epochs cover a fractional
    # day, the year pivot, day zero, a leap-year boundary and one 864-us tick.
    cases = (
        ('fractional_day', '26187.12345678', '26188.12345679', 15.5),
        ('day_zero_before_1970', '57000.12345678', '57001.12345679', 15.5),
        ('year_pivot_leap_day', '56365.99999999', '56366.00000000', 15.5),
        ('one_tick_within_millisecond', '26187.00000000', '26187.00000001', 15.5),
        ('rounded_epoch_regression', '26187.00000103', '26188.00000000', 15.5),
        ('deep_space_fractional_day', '26187.12345678', '26188.12345679', 1.0027),
    )
    return [
        {'name': name, 'before': tle(before, motion, 50.0), 'after': tle(after, motion + 0.0002, 60.0)}
        for name, before, after, motion in cases
    ]


def app_results(cases: list[dict]) -> list[dict]:
    code = '\n'.join([
        "const vm = require('node:vm');",
        "const { loadBrowserApp } = require('./tools/load_browser_app');",
        "const context = { window: { satellite: require('./satellite-6.0.2.min.js') },",
        "  document: { getElementById: () => ({ value: '' }) } };",
        "vm.createContext(context);",
        "const { parseTlePair, recordEpochUs, propagateRecordAtEpoch, computeSgp4Residual } =",
        "  loadBrowserApp(context, { start: false });",
        "const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));",
        """
const results = cases.map(test => {
  const records = ['before', 'after'].map(key => {
    const parsed = parseTlePair(test.name, ...test[key]);
    if (!parsed.record || parsed.errors.length) throw new Error(JSON.stringify(parsed.errors));
    return parsed.record;
  });
  const targetUs = recordEpochUs(records[1]);
  return {
    name: test.name,
    records: records.map(record => ({
      epochUs: record.epochUs,
      epochRaw: record.epochRaw,
      dateMs: record.t.getTime(),
      state: propagateRecordAtEpoch(record, targetUs)
    })),
    residual: computeSgp4Residual(...records)
  };
});
process.stdout.write(JSON.stringify(results));
""",
    ])
    return json.loads(subprocess.check_output(
        ['node', '-e', code], cwd=ROOT, input=json.dumps(cases), text=True,
    ))


def vector(value: dict[str, float]) -> tuple[float, float, float]:
    return tuple(value[axis] for axis in ('x', 'y', 'z'))


def dot(first: tuple, second: tuple) -> float:
    return sum(a * b for a, b in zip(first, second))


def cross(first: tuple, second: tuple) -> tuple:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def norm(value: tuple) -> float:
    return math.sqrt(dot(value, value))


def unit(value: tuple) -> tuple:
    magnitude = norm(value)
    assert math.isfinite(magnitude) and magnitude > 0
    return tuple(component / magnitude for component in value)


def residual(before: tuple, after: tuple) -> dict[str, float]:
    position, velocity = before
    observed_position, observed_velocity = after
    radial = unit(position)
    normal = unit(cross(position, velocity))
    along = unit(cross(normal, radial))
    delta = tuple(a - b for a, b in zip(observed_position, position))
    delta_v = tuple(a - b for a, b in zip(observed_velocity, velocity))
    return {
        'radialKm': dot(delta, radial),
        'alongKm': dot(delta, along),
        'crossKm': dot(delta, normal),
        'positionKm': norm(delta),
        'velocityMps': norm(delta_v) * 1000,
    }


def main() -> None:
    cases = fixtures()
    actual = app_results(cases)
    assert len(actual) == len(cases)
    max_position_m = 0.0
    max_velocity_mps = 0.0
    max_residual_m = 0.0
    for case, result in zip(cases, actual):
        assert result['name'] == case['name']
        target_us = epoch_us(case['after'][0])
        expected_states = []
        for key, record in zip(('before', 'after'), result['records']):
            line1, line2 = case[key]
            exact_us = epoch_us(line1)
            assert record['epochUs'] == exact_us, f"{case['name']} {key} epoch lost precision"
            assert record['epochRaw'] == utc_string(exact_us)
            assert record['dateMs'] == exact_us // 1000
            model = Satrec.twoline2rv(line1, line2)
            error, position, velocity = model.sgp4_tsince((target_us - exact_us) / 60_000_000)
            assert error == 0, f"Python SGP4 error {error} in {case['name']} {key}"
            state = record['state']
            assert state and state['position'] and state['velocity']
            position_error_m = math.dist(position, vector(state['position'])) * 1000
            velocity_error_mps = math.dist(velocity, vector(state['velocity'])) * 1000
            assert position_error_m <= POSITION_TOLERANCE_M, f"{case['name']} {key} position error {position_error_m:.9g} m"
            assert velocity_error_mps <= VELOCITY_TOLERANCE_MPS, f"{case['name']} {key} velocity error {velocity_error_mps:.9g} m/s"
            max_position_m = max(max_position_m, position_error_m)
            max_velocity_mps = max(max_velocity_mps, velocity_error_mps)
            expected_states.append((position, velocity))
        expected_residual = residual(*expected_states)
        for component, expected in expected_residual.items():
            scale = 1 if component == 'velocityMps' else 1000
            difference = abs(result['residual'][component] - expected) * scale
            tolerance = VELOCITY_TOLERANCE_MPS if component == 'velocityMps' else POSITION_TOLERANCE_M
            assert difference <= tolerance, f"{case['name']} {component} error {difference:.9g}"
            if component != 'velocityMps':
                max_residual_m = max(max_residual_m, difference)
    print(f'Independent Python SGP4 precision check passed for {len(cases)} synthetic pairs and {len(cases) * 2} states.')
    print(f'Maximum position error {max_position_m:.9g} m; velocity error {max_velocity_mps:.9g} m/s; RTN or position residual error {max_residual_m:.9g} m.')


if __name__ == '__main__':
    main()
