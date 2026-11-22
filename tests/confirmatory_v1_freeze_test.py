#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'benchmark-results/confirmatory-v1-final.json'
SIDECAR = ROOT / 'benchmark-results/confirmatory-v1-final.json.sha256'
EXPECTED_SHA256 = 'f9857bd8f9ae2525b1827ce4fdfd108f7c5468c67142226922542d24b88c923c'
EXPECTED_METHODS = ['detector-0.4', 'mean-motion-threshold', 'sma-window-shift', 'sgp4-rtn-consistency', 'multi-element-mad', 'robust-mahalanobis', 'robust-cusum', 'kalman-nis', 'shorten-op-pf-surrogate', 'robust-linear', 'lstm', 'gru', 'tcn', 'transformer', 'sequential-autoencoder', 'physics-ml-v1.0']


def main() -> None:
    raw = RESULT.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_SHA256
    assert SIDECAR.read_text().split()[0] == EXPECTED_SHA256
    data = json.loads(raw)
    assert data['schema'] == 'smd-confirmatory-v1-final'
    assert data['one_shot'] is True
    assert data['confirmatory_partition_accessed'] is True
    assert data['post_confirmatory_method_changes_allowed'] is False
    assert data['confirmatory_objects'] == 12
    assert data['confirmatory_truth_intervals'] == 41
    assert data['confirmatory_verified_quiet_controls'] == 2
    assert data['method_count'] == 16
    assert data['method_order'] == EXPECTED_METHODS
    assert [item['method'] for item in data['methods']] == EXPECTED_METHODS
    assert data['matching_tolerance_hours'] == 24.0
    assert data['bootstrap_iterations'] == 1000
    gate = data['integration_publication_gate']
    assert gate['criteria_frozen_before_confirmatory_access'] is True
    assert set(gate['checks']) == {
        'at_least_one_true_positive',
        'recall_strictly_greater_than_0_20',
        'positive_covered_quiet_exposure',
        'false_event_rate_at_most_1_per_covered_object_month',
        'f1_strictly_greater_than_best_risk_compliant_principal_comparator',
        'median_absolute_detection_delay_at_most_24_hours',
    }
    lock = json.loads((ROOT / 'research/confirmatory_v1/RUN-LOCK-v1.0.json').read_text())
    assert lock['one_shot_completed'] is True and lock['rerun_forbidden'] is True
    assert lock['final_result_sha256'] == EXPECTED_SHA256
    results = (ROOT / 'research/confirmatory_v1/RESULTS-v1.0.md').read_text()
    audit = (ROOT / 'review/CONFIRMATORY-AUDIT.md').read_text()
    assert 'single frozen benchmark v1.0 confirmatory evaluation' in results
    assert 'No confirmatory metric was used to change' in audit
    print('Confirmatory evaluation one-shot confirmatory freeze verified.')


if __name__ == '__main__':
    main()
