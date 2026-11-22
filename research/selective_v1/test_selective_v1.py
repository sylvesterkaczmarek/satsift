#!/usr/bin/env python3
from __future__ import annotations

import math

from .core import (
    CONTEXT_NAMES,
    FEATURE_NAMES,
    ScoredRow,
    SupportModel,
    calibrate_event_threshold,
    context_regime,
    group_candidate_events,
    physical_support,
    student_t_surprise,
)
from .detector import SelectiveDetector
from .models import RobustConditionalLinear


def make_row(object_id: str, index: int, regime: str, offset: float = 0.0) -> dict:
    onehot = {
        'orbit_leo': 1.0 if regime == 'LEO' else 0.0,
        'orbit_meo': 1.0 if regime == 'MEO' else 0.0,
        'orbit_geo': 1.0 if regime == 'GEO' else 0.0,
        'orbit_heo': 1.0 if regime == 'HEO' else 0.0,
    }
    context = {
        'log_gap_days': 0.1 + 0.001 * index,
        'log_semi_major_axis_km': {'LEO': 8.82, 'MEO': 10.2, 'GEO': 10.65, 'HEO': 9.7}[regime],
        'eccentricity': {'LEO': 0.001, 'MEO': 0.01, 'GEO': 0.0002, 'HEO': 0.6}[regime],
        'inclination_sin': {'LEO': 0.78, 'MEO': 0.83, 'GEO': 0.01, 'HEO': 0.9}[regime],
        'log_abs_bstar': 0.001,
        'log_creation_lag_hours': 0.5,
        'object_age_log_days': 7.0,
        'rcs_scale': 1.0,
        'element_set_known': 1.0,
        'gp_id_known': 1.0,
        'catalogue_superseded_fraction': 0.01,
        'epoch_precision_digits_scaled': 2.0 / 3.0,
        **onehot,
    }
    features = {
        name: offset + (feature_index + 1) * 0.01 + index * 0.0001
        for feature_index, name in enumerate(FEATURE_NAMES)
    }
    return {
        'case_id': f'case-{object_id}',
        'object_id': object_id,
        'split': 'development',
        'nominal': True,
        'quality_ok': True,
        'index': index,
        'epoch_utc': f'2026-01-{1 + index // 24:02d}T{index % 24:02d}:00:00Z',
        'context': context,
        'features': features,
    }


def test_context_contract() -> None:
    row = make_row('1', 1, 'LEO')
    assert context_regime(row) == 'LEO'
    assert set(row['context']) == set(CONTEXT_NAMES)


def test_support_requires_independent_same_regime_satellites() -> None:
    leo_a = [make_row('100', i, 'LEO') for i in range(8)]
    leo_b = [make_row('101', i, 'LEO', 0.002) for i in range(8)]
    geo = [make_row('200', i, 'GEO') for i in range(8)]
    support = SupportModel(k=3, min_reference_satellites=2).fit(leo_a + leo_b + geo)
    assert support.qualified_regimes() == {'LEO'}
    assert support.distance(make_row('999', 3, 'LEO')) is not None
    assert support.distance(make_row('998', 3, 'GEO')) is None
    assert support.distance(make_row('998', 3, 'GEO'), require_qualified_regime=False) is not None


def test_heavy_tail_surprise_and_physics_gate() -> None:
    location = {name: 0.0 for name in FEATURE_NAMES}
    scale = {name: 1.0 for name in FEATURE_NAMES}
    quiet = student_t_surprise({name: 0.1 for name in FEATURE_NAMES}, location, scale)
    large = student_t_surprise({name: 20.0 for name in FEATURE_NAMES}, location, scale)
    assert math.isfinite(quiet.surprise)
    assert math.isfinite(large.surprise)
    assert large.surprise > quiet.surprise
    z = {name: 0.0 for name in FEATURE_NAMES}
    z['along_rate'] = 3.0; z['a_rate'] = 1.5
    assert physical_support(z, z_gate=2.0) == 'along-track'


def test_event_grouping_and_empirical_calibration() -> None:
    rows = [
        ScoredRow(1, '2026-01-01T00:00:00Z', 1.0, 1.0, 'scored', None),
        ScoredRow(2, '2026-01-01T01:00:00Z', 8.0, 1.0, 'scored', 'along-track'),
        ScoredRow(3, '2026-01-01T02:00:00Z', 7.0, 1.0, 'scored', 'along-track'),
        ScoredRow(8, '2026-01-01T07:00:00Z', 9.0, 1.0, 'scored', 'cross-track'),
    ]
    events = group_candidate_events(rows, threshold=6.0, max_gap_points=2)
    assert len(events) == 2
    # The caller passes covered span, not raw span. Two events over two covered object-months meet
    # a budget of one event/object-month exactly.
    calibration = calibrate_event_threshold(
        [{'span_days': 60.875, 'scored_rows': rows}],
        false_events_per_object_month_budget=1.0,
    )
    assert calibration['false_events_per_object_month'] <= 1.0 + 1e-12
    assert math.isfinite(calibration['selected_threshold'])


def test_robust_linear_and_selective_abstention() -> None:
    sequences = [
        [make_row('100', i, 'LEO', 0.0) for i in range(12)],
        [make_row('101', i, 'LEO', 0.002) for i in range(12)],
        [make_row('102', i, 'LEO', -0.002) for i in range(12)],
    ]
    model = RobustConditionalLinear().fit(sequences)
    prediction = model.predict_sequence([make_row('999', i, 'LEO', 0.001) for i in range(4)])
    assert len(prediction) == 4 and all(item is not None for item in prediction)
    assert model.parameter_count > 0

    support = SupportModel(k=3, min_reference_satellites=3).fit([row for sequence in sequences for row in sequence])
    detector = SelectiveDetector(
        model,
        support,
        support_thresholds={'LEO': 100.0},
        event_threshold=1000.0,
    )
    scored, events = detector.run([make_row('999', i, 'LEO', 0.001) for i in range(4)])
    assert any(row.status == 'scored' for row in scored)
    assert events == []
    meo_scored, _ = detector.run([make_row('888', i, 'MEO', 0.001) for i in range(4)])
    assert all(row.status == 'abstain' for row in meo_scored)
    assert all('unsupported calibration regime' in (row.reason or '') for row in meo_scored)


def main() -> None:
    tests = [
        test_context_contract,
        test_support_requires_independent_same_regime_satellites,
        test_heavy_tail_surprise_and_physics_gate,
        test_event_grouping_and_empirical_calibration,
        test_robust_linear_and_selective_abstention,
    ]
    for test in tests:
        test()
        print('PASS', test.__name__)
    print(f'{len(tests)}/{len(tests)} selective ML v1 tests passed.')


if __name__ == '__main__':
    main()
