#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import subprocess
from datetime import datetime, timedelta, timezone

from sgp4.api import Satrec, jday


def parse_epoch(line1: str) -> datetime:
    field = line1[18:32]
    year2 = int(field[:2])
    year = 2000 + year2 if year2 < 57 else 1900 + year2
    day = float(field[2:])
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day - 1)


def parse_blocks(raw: str) -> list[tuple[str, str, str]]:
    lines = [line.rstrip() for line in raw.splitlines() if line.strip()]
    if len(lines) % 3:
        raise AssertionError('Fixture TLE text is not arranged as name/line1/line2 triples.')
    return [(lines[index], lines[index + 1], lines[index + 2]) for index in range(0, len(lines), 3)]


def norm(vector: tuple[float, float, float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def dot(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return sum(a * b for a, b in zip(first, second))


def cross(first: tuple[float, float, float], second: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def subtract(first: tuple[float, float, float], second: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(a - b for a, b in zip(first, second))


def unit(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    magnitude = norm(vector)
    if not math.isfinite(magnitude) or magnitude <= 0:
        raise AssertionError('Could not form RTN unit vector.')
    return tuple(value / magnitude for value in vector)


def propagate(satrec: Satrec, epoch: datetime) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    jd, fr = jday(
        epoch.year,
        epoch.month,
        epoch.day,
        epoch.hour,
        epoch.minute,
        epoch.second + epoch.microsecond / 1_000_000,
    )
    error, position, velocity = satrec.sgp4(jd, fr)
    if error != 0:
        raise AssertionError(f'SGP4 returned error code {error}.')
    return tuple(position), tuple(velocity)


def residual(before: tuple[str, str, str], after: tuple[str, str, str]) -> dict[str, float]:
    before_sat = Satrec.twoline2rv(before[1], before[2])
    after_sat = Satrec.twoline2rv(after[1], after[2])
    epoch = parse_epoch(after[1])
    reference_position, reference_velocity = propagate(before_sat, epoch)
    observed_position, _ = propagate(after_sat, epoch)

    radial = unit(reference_position)
    normal = unit(cross(reference_position, reference_velocity))
    along = unit(cross(normal, radial))
    delta = subtract(observed_position, reference_position)
    return {
        'radial_km': dot(delta, radial),
        'along_km': dot(delta, along),
        'cross_km': dot(delta, normal),
        'position_km': norm(delta),
    }


def residual_series(raw: str) -> list[dict[str, float]]:
    blocks = parse_blocks(raw)
    return [residual(blocks[index - 1], blocks[index]) for index in range(1, len(blocks))]


def assert_finite_bounded(values: list[dict[str, float]], bound_km: float, label: str) -> None:
    if not values:
        raise AssertionError(f'{label} produced no residuals.')
    maximum = max(item['position_km'] for item in values)
    if not math.isfinite(maximum) or maximum >= bound_km:
        raise AssertionError(f'{label} residual is implausibly large: {maximum:.3f} km >= {bound_km:.3f} km.')


def main() -> None:
    output = subprocess.check_output(['node', 'tests/export_astrodynamics_fixtures.js'], text=True)
    fixtures = json.loads(output)

    quiet_blocks = parse_blocks(fixtures['quiet'])
    if quiet_blocks[0][1][18:32] != '26201.00000000':
        raise AssertionError('Synthetic fixtures are not anchored at the documented fixed UTC epoch.')

    series = {name: residual_series(raw) for name, raw in fixtures.items() if name != 'sparse'}

    quiet_max = max(item['position_km'] for item in series['quiet'])
    if quiet_max >= 1.0:
        raise AssertionError(f'Quiet fixture common-epoch residual is too large: {quiet_max:.3f} km.')

    event_index = {'leo': 11, 'geo': 12, 'radial': 11, 'cross': 11, 'finite': 10}
    diagnostics: dict[str, dict[str, float]] = {'quiet_max': {'position_km': quiet_max}}

    for name, after_index in event_index.items():
        event_residual = series[name][after_index - 1]
        diagnostics[name] = event_residual
        if event_residual['position_km'] <= 0.25:
            raise AssertionError(f'{name} maneuver fixture did not create a measurable state discontinuity.')
        if event_residual['position_km'] >= 250.0:
            raise AssertionError(f'{name} maneuver fixture created an implausibly large {event_residual["position_km"]:.3f} km residual.')

    if abs(diagnostics['radial']['radial_km']) <= 0.25:
        raise AssertionError('Radial fixture lacks a measurable radial component.')
    if abs(diagnostics['cross']['cross_km']) <= 0.25:
        raise AssertionError('Cross-track fixture lacks a measurable cross-track component.')
    if abs(diagnostics['leo']['along_km']) <= 0.25:
        raise AssertionError('LEO along-track fixture lacks a measurable along-track component.')

    finite_event_positions = [series['finite'][index - 1]['position_km'] for index in (10, 11, 12)]
    if len({round(value, 3) for value in finite_event_positions}) < 2:
        raise AssertionError('Finite-duration fixture does not produce a multi-step disturbance.')

    for name, values in series.items():
        assert_finite_bounded(values, 500.0, name)

    print('Independent Python SGP4 fixture validation passed.')
    print(json.dumps(diagnostics, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
