#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'benchmark-results' / 'selective-v1-model-selection.json'


def close(actual: float, expected: float, tol: float = 1e-12) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=tol, abs_tol=tol):
        raise AssertionError(f'{actual} != {expected}')


def main() -> None:
    report = json.loads(REPORT.read_text())
    assert report['schema'] == 'smd-selective-ml-v1-model-selection'
    assert report['method'] == 'selective-ml-v1.0'
    assert report['confirmatory_partition_accessed'] is False
    assert report['detector_v0_4_modified'] is False
    assert report['architecture_is_novelty_claim'] is False
    assert report['selected_backbone'] == 'transformer'
    assert report['candidate_failures'] == []

    comparisons = {item['candidate']: item for item in report['candidate_comparisons']}
    assert set(comparisons) == {'robust-linear', 'gru', 'tcn', 'transformer'}
    expected_rankings = {
        'transformer': 0.480625,
        'robust-linear': 0.37765522875817,
        'gru': 0.3408333333333333,
        'tcn': 0.284375,
    }
    for candidate, expected in expected_rankings.items():
        close(comparisons[candidate]['pu_event_vs_quiet_mean_percentile'], expected)
        close(comparisons[candidate]['event_recall_supported_regimes'], 0.0)
        assert comparisons[candidate]['eligible_regimes'] == ['LEO']
        assert comparisons[candidate]['architecture_selection_split'] == 'development only'

    final = report['final_calibration']
    assert final['selected_backbone'] == 'transformer'
    assert final['minimum_reference_satellites_final'] == 3
    assert final['reference_satellites_by_regime'] == {'GEO': 2, 'HEO': 1, 'LEO': 4, 'MEO': 1}
    assert final['qualified_regimes'] == ['LEO']
    assert set(final['unqualified_regimes']) == {'GEO', 'HEO', 'MEO'}
    close(final['support_thresholds']['LEO'], 1.2019241655473716)
    assert final['final_parameter_count'] == 59568
    assert final['risk_statement'] == 'empirical false-event calibration on covered verified-quiet object-months; no formal risk-control guarantee'

    event = final['event_calibration']
    close(event['selected_threshold'], 6.501427015384656)
    assert event['false_events'] == 0
    close(event['covered_verified_quiet_object_months'], 0.4665623499247091)
    close(event['false_events_per_object_month'], 0.0)
    close(event['budget'], 1.0)

    coverage = {item['case_id']: item for item in final['calibration_quiet_coverage']}
    close(coverage['aqua-free-drift-2024-02']['coverage_fraction'], 0.9583333333333334)
    for case_id in (
        'cluster-salsa-post-final-manoeuvres-2024-02',
        'gioveb-retired-2012-09',
        'meteosat7-passivated-2017-05',
    ):
        close(coverage[case_id]['coverage_fraction'], 0.0)

    assert report['calibration_event_evaluation']['status'] == 'not used for model selection or risk calibration'
    assert 'Do not materialise' in report['confirmatory_rule']
    print('Selective ML v1 frozen decision record passed.')


if __name__ == '__main__':
    main()
