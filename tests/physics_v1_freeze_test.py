#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'benchmark-results/physics-v1-development.json'
EXPECTED_SHA256 = 'b4422b7a2c01a2940513bc6fcef25963e454732792bac6cb17e2183bfd44898e'


def main() -> None:
    raw = RESULT.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    assert actual == EXPECTED_SHA256, (actual, EXPECTED_SHA256)
    data = json.loads(raw)

    assert data['schema'] == 'smd-maneuver-physics-v1-development-calibration'
    assert data['confirmatory_partition_accessed'] is False
    assert data['detector_v0_4_modified'] is False
    assert data['selected_backbone'] == 'transformer'
    assert data['qualified_regimes'] == ['LEO']
    assert data['unqualified_regimes'] == ['GEO', 'HEO', 'MEO']
    assert data['sequential_frozen_base_score_threshold'] == 17.822733355396952
    assert data['sequential_reference']['development_tp'] == 0
    assert data['sequential_reference']['development_fn'] == 36

    development = data['development_evaluation']
    assert development['tp'] == 0
    assert development['fn'] == 36
    assert development['recall'] == 0.0
    assert development['pu_sequential_wealth_mean_percentile'] == 0.8660130718954249
    assert development['pu_scorable_truth_intervals'] == 21
    assert development['truth_intervals_with_feasible_physics'] == 2

    feasible_intervals = []
    for case in development['per_case']:
        for interval in case['truth_feasibility']['intervals']:
            if interval['has_feasible_physics_row']:
                feasible_intervals.append(interval)
    assert len(feasible_intervals) == 2
    assert {item['direction'] for item in feasible_intervals} == {'positive cross-track'}
    for item in feasible_intervals:
        low, high = item['delta_v_interval_mps']
        assert low < item['delta_v_median_mps'] < high
        assert low == 51.806746934408174
        assert high == 139.80480469885603

    aura = data['development_quiet_physics_crossfit'][0]
    assert aura['status_counts'] == {'nominal': 38}
    aqua = data['calibration_quiet_physics']
    assert aqua['status_counts'] == {'abstain': 31, 'nominal': 38}
    assert aqua['coverage_fraction'] == 0.5277777777777778

    q0 = data['empirical_q0_after_physics_gate']
    assert q0['q0'] == 0.24444444444444446
    calibration = data['final_event_calibration']
    assert calibration['selected_wealth_threshold'] == 1.01
    assert calibration['false_events'] == 0
    assert calibration['covered_verified_quiet_object_months'] == 0.25694738111795573
    assert calibration['false_events_per_object_month'] == 0.0
    assert calibration['target_false_events_per_object_month'] == 1.0

    diagnostic = data['post_calibration_development_diagnostic']
    assert diagnostic['tp'] == 0
    assert diagnostic['fn'] == 36
    assert diagnostic['recall'] == 0.0
    assert data['integration_gate']['passed'] is False

    method = (ROOT / 'research/physics_v1/METHOD-v1.0.md').read_text()
    results = (ROOT / 'research/physics_v1/RESULTS-v1.0.md').read_text()
    exporter = (ROOT / 'tools/export_selective_v1_features.js').read_text()
    experiment = (ROOT / 'research/physics_v1/run_development.py').read_text()
    independent = (ROOT / 'research/physics_v1/independent_check.py').read_text()
    assert 'equivalent-impulse' in method.lower()
    assert 'forward/local numerical impulse differentiation' in method
    assert 'centered/local numerical impulse differentiation' not in method
    assert 'Production Jacobian versus analytic Gauss equations' in method
    assert 'validate_production_jacobian_against_gauss' in independent
    assert 'production equinoctial Jacobian vs analytic classical GVE' in independent
    assert "final_calibration['false_events_per_object_month'] <= TARGET_FALSE_EVENTS_PER_OBJECT_MONTH" in experiment
    assert "not an assertion of the spacecraft's true executed finite-burn history" in method
    assert 'Physics evaluation integration gate failed' in results
    assert 'CONFIRMATORY PARTITION IS SEALED' in exporter
    assert 'CONFIRMATORY PARTITION IS SEALED' in experiment

    print('Maneuver physics v1 freeze checks passed.')


if __name__ == '__main__':
    main()
