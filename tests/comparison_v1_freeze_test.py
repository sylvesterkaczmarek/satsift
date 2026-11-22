#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'benchmark-results/comparison-v1-development-calibration.json'
EXPECTED_SHA256 = '092df5a126d85fb7b58e5a0f682acdee1da39860359be943f102f26a986ddb43'
EXPECTED_METHODS = ['detector-0.4', 'mean-motion-threshold', 'sma-window-shift', 'sgp4-rtn-consistency', 'multi-element-mad', 'robust-mahalanobis', 'robust-cusum', 'kalman-nis', 'shorten-op-pf-surrogate', 'robust-linear', 'lstm', 'gru', 'tcn', 'transformer', 'sequential-autoencoder', 'physics-ml-v1.0']


def main() -> None:
    raw = RESULT.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    assert actual == EXPECTED_SHA256, (actual, EXPECTED_SHA256)
    data = json.loads(raw)
    assert data['schema'] == 'smd-comparison-suite-v1'
    assert data['confirmatory_partition_accessed'] is False
    assert data['included_splits'] == ['calibration', 'development']
    assert data['primary_evaluation_split'] == 'calibration'
    assert data['method_count'] == 16
    assert data['method_order'] == EXPECTED_METHODS
    assert len(data['methods']) == 16
    assert [item['method'] for item in data['methods']] == EXPECTED_METHODS
    assert data['matching_tolerance_hours'] == 24.0
    assert data['risk_budget_false_events_per_covered_object_month'] == 1.0
    assert data['bootstrap_seed'] == 3404
    assert 'structural surrogate' in data['shorten_reproducibility_note']
    assert 'common_risk_budget_compliant_ranking_table' in data
    detector = next(item for item in data['calibration_ranking_table'] if item['method'] == 'detector-0.4')
    assert detector['common_risk_budget_compliant'] is (
        detector['false_events_per_object_month'] <= data['risk_budget_false_events_per_covered_object_month']
    )
    for item in data['methods']:
        assert 'primary_calibration_evaluation' in item
        assert 'primary_calibration_by_orbit_regime' in item
        assert 'development_event_diagnostic' in item
        assert 'computational_cost' in item
        cost = item['computational_cost']
        assert cost.get('evaluation_cases_inference') == 14
        assert 'timing_scope' in cost
        summary = item['primary_calibration_evaluation']['summary']
        if summary['recall'] == 0.0:
            assert summary['f1'] == 0.0
    source = (ROOT / 'research/comparison_v1/run_comparison.py').read_text()
    method = (ROOT / 'research/comparison_v1/METHOD-v1.0.md').read_text()
    results = (ROOT / 'research/comparison_v1/RESULTS-v1.0.md').read_text()
    audit = (ROOT / 'review/COMPARISON-AUDIT.md').read_text()
    assert 'CONFIRMATORY PARTITION IS SEALED' in source
    assert 'Anti-cherry-picking rule' in method
    assert 'first alarm/event onset' in method
    assert 'Comparison evaluation is complete after post-run code and methodology audit' in results
    assert 'No candidate result caused a baseline to be removed' in audit
    print('Comparison v1 audited frozen result verified.')


if __name__ == '__main__':
    main()
