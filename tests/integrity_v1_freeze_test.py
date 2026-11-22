#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'benchmark-results/integrity-v1-stress.json'
EXPECTED_SHA256 = 'fa76061583d2b48b34f44f2167b8f2b702ceadd1553dcef73a2499092c00f73b'


def main() -> None:
    raw = RESULT.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    assert actual == EXPECTED_SHA256, (actual, EXPECTED_SHA256)
    data = json.loads(raw)

    assert data['schema'] == 'smd-integrity-security-v1-stress-results'
    assert data['paper_track'] == 'AI-integrity-security'
    assert data['confirmatory_partition_accessed'] is False
    assert data['detector_v0_4_modified'] is False
    assert data['stress_condition_count'] == 12
    assert len(data['stress_conditions']) == 13
    assert data['qualified_regimes'] == ['LEO']

    frozen = data['frozen_parameters']
    assert frozen['base_score_threshold'] == 17.822733355396952
    assert frozen['development_support_threshold'] == 15937.989955517674
    assert frozen['final_support_threshold'] == 1.2019241655473716
    assert frozen['q0'] == 0.24444444444444446
    assert frozen['development_wealth_threshold'] == 1.730962511467316
    assert frozen['final_wealth_threshold'] == 1.01
    assert frozen['risk_budget_false_events_per_covered_object_month'] == 1.0

    clean = data['stress_conditions']['clean']
    development = clean['development_detection']
    assert development['case_count'] == 4
    assert development['truth_intervals'] == 36
    assert development['tp'] + development['fn'] == 36
    assert development['recall'] is None or 0.0 <= development['recall'] <= 1.0
    pu = development['pu_sequential_wealth_mean_percentile']
    assert pu is None or 0.0 <= pu <= 1.0

    calibration = clean['final_calibration']
    assert calibration['coverage_fraction'] > 0.0
    assert calibration['frozen_false_events'] >= 0
    assert calibration['risk_budget_exceeded'] is False
    assert calibration['frozen_false_events_per_object_month'] is not None
    assert calibration['frozen_false_events_per_object_month'] <= 1.0

    for condition in ('unresolved_duplicate', 'catalogue_regime_change', 'truncated_history'):
        stress = data['stress_conditions'][condition]
        assert stress['structural_integrity']['hard_case_abstention_fraction'] == 1.0
        assert stress['development_detection']['row_abstention_fraction'] == 1.0
        assert stress['final_calibration']['coverage_fraction'] == 0.0

    replay = data['stress_conditions']['replay']
    assert replay['structural_integrity']['recoverable_alert_counts']['replay_or_exact_duplicate_detected'] == 18
    assert replay['development_detection']['pu_sequential_wealth_mean_percentile'] == development['pu_sequential_wealth_mean_percentile']
    assert replay['final_calibration']['coverage_fraction'] == calibration['coverage_fraction']
    assert replay['final_calibration']['frozen_false_events'] == calibration['frozen_false_events']

    corrected = data['stress_conditions']['corrected_duplicate']
    assert corrected['structural_integrity']['recoverable_alert_counts']['catalogue_correction_resolved'] == 18

    false_attack = data['stress_conditions']['adversarial_false_maneuver']['final_calibration']
    assert false_attack['risk_budget_exceeded'] is False
    assert false_attack['frozen_false_events'] <= calibration['frozen_false_events']

    assert data['security_gate_failures'] == []
    assert data['security_findings'] == data['observed_vulnerabilities']
    assert 'no confirmatory access' in data['claim_boundary']

    method = (ROOT / 'research/integrity_v1/METHOD-v1.0.md').read_text()
    results = (ROOT / 'research/integrity_v1/RESULTS-v1.0.md').read_text()
    audit = (ROOT / 'review/INTEGRITY-AUDIT.md').read_text()
    stressors = (ROOT / 'research/integrity_v1/stressors.py').read_text()
    runner = (ROOT / 'research/integrity_v1/run_stress.py').read_text()
    exporter = (ROOT / 'tools/export_integrity_v1_features.js').read_text()
    history = (ROOT / 'history.php').read_text()
    assert 'temporal model context' in method
    assert 'same-object orbital-regime discontinuity' in method
    assert 'full-store SHA-256' in method
    assert 'Integrity evaluation audit' in audit
    assert 'Frozen SHA-256' in results
    assert 'CONFIRMATORY PARTITION IS SEALED' in stressors
    assert 'CONFIRMATORY PARTITION IS SEALED' in runner
    assert 'CONFIRMATORY PARTITION IS SEALED' in exporter
    assert 'historyStoreDigest' in history
    assert "store_sha256" in history

    print('Integrity/security v1 audited frozen stress result verified.')


if __name__ == '__main__':
    main()
