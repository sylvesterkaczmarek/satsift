#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

FINAL = Path('benchmark-results/confirmatory-v1-final.json')
SIDECAR = Path('benchmark-results/confirmatory-v1-final.json.sha256')
FREEZE = Path('research/confirmatory_v1/PRECONFIRMATORY-FREEZE.json')
EXPECTED_METHODS = [
    'detector-0.4',
    'mean-motion-threshold',
    'sma-window-shift',
    'sgp4-rtn-consistency',
    'multi-element-mad',
    'robust-mahalanobis',
    'robust-cusum',
    'kalman-nis',
    'shorten-op-pf-surrogate',
    'robust-linear',
    'lstm',
    'gru',
    'tcn',
    'transformer',
    'sequential-autoencoder',
    'physics-ml-v1.0',
]


def fmt(value, digits=4):
    if value is None:
        return 'n/a'
    return f'{float(value):.{digits}f}'


def ci(block: dict, field: str, digits=4):
    summary = block.get('summary') or {}
    point = summary.get(field)
    if point is None:
        return 'n/a'
    interval = (block.get('satellite_cluster_bootstrap_95_ci') or {}).get(field) or {}
    low, high = interval.get('low_95'), interval.get('high_95')
    if low is None or high is None:
        return fmt(point, digits)
    return f'{fmt(point, digits)} [{fmt(low, digits)}, {fmt(high, digits)}]'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--result', required=True)
    args = parser.parse_args()

    if FINAL.exists():
        raise RuntimeError('CONFIRMATORY RUN LOCK: final confirmatory result already exists; overwrite forbidden')

    data = json.loads(Path(args.result).read_text())
    assert data['schema'] == 'smd-confirmatory-v1-final'
    assert data['one_shot'] is True
    assert data['confirmatory_partition_accessed'] is True
    assert data['post_confirmatory_method_changes_allowed'] is False
    assert data['confirmatory_objects'] == 12
    assert data['confirmatory_truth_intervals'] == 41
    assert data['confirmatory_verified_quiet_controls'] == 2
    assert data['method_count'] == 16
    assert data['method_order'] == EXPECTED_METHODS
    assert len(data['methods']) == 16
    assert 'integration_publication_gate' in data

    raw = json.dumps(data, indent=2, allow_nan=False) + '\n'
    FINAL.parent.mkdir(parents=True, exist_ok=True)
    FINAL.write_text(raw)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    SIDECAR.write_text(f'{digest}  {FINAL.name}\n')

    by_name = {item['method']: item for item in data['methods']}
    metric_rows = []
    regime_rows = []
    regimes = ['LEO', 'MEO', 'GEO', 'HEO', 'IGSO']
    for method in EXPECTED_METHODS:
        item = by_name[method]
        block = item['confirmatory_evaluation']
        metric_rows.append(
            f"| {method} | {ci(block, 'precision')} | {ci(block, 'recall')} | {ci(block, 'f1')} | "
            f"{ci(block, 'false_events_per_object_month')} | {ci(block, 'median_absolute_detection_delay_hours', 2)} | "
            f"{ci(block, 'mean_case_abstention_fraction')} |"
        )
        regime = item.get('confirmatory_by_orbit_regime') or {}
        values = []
        for name in regimes:
            part = regime.get(name)
            values.append('n/a' if not part else fmt((part.get('summary') or {}).get('f1'), 3))
        regime_rows.append(f"| {method} | " + ' | '.join(values) + ' |')

    ranking = data['confirmatory_ranking_table']
    ranking_text = '\n'.join(
        f"- {row['rank_by_confirmatory_f1_then_recall']}. `{row['method']}`: F1 {fmt(row.get('f1'))}, "
        f"recall {fmt(row.get('recall'))}, false events/object-month {fmt(row.get('false_events_per_object_month'))}."
        for row in ranking
    )
    gate = data['integration_publication_gate']
    gate_text = '\n'.join(
        f"- {'PASS' if passed else 'FAIL'}: `{name}`"
        for name, passed in gate['checks'].items()
    )
    target = by_name['physics-ml-v1.0']['confirmatory_evaluation']
    target_summary = target['summary']
    comparator = gate.get('best_risk_compliant_principal_comparator')
    disposition = 'PASS' if gate['passed'] else 'FAIL'
    next_step = (
        'Integration decision is permitted by the frozen roadmap, but no integration has been performed in Confirmatory evaluation.'
        if gate['passed'] else
        'Integration decision integration is not permitted for physics-ML v1.0. Detector 0.4 must remain the public method and this negative result must be retained.'
    )

    results = f'''# Confirmatory evaluation v1.0 results

## Status

**Confirmatory evaluation confirmatory gate: {disposition}.**

This is the single frozen benchmark v1.0 confirmatory evaluation. The method, calibration rules, thresholds, benchmark protocol and gate were frozen before confirmatory access. No post-confirmatory retuning is permitted.

## Freeze record

- frozen code commit: `{data['frozen_code_commit']}`
- frozen code tree: `{data.get('frozen_code_tree')}`
- one-shot trigger commit: `{data.get('trigger_commit')}`
- GitHub Actions run: `{data.get('github_workflow_run_id')}`
- benchmark manifest SHA-256: `{data['benchmark_manifest_sha256']}`
- benchmark recipe SHA-256: `{data['benchmark_recipe_sha256']}`
- Comparison evaluation result SHA-256: `{data['comparison_result_sha256']}`
- Physics evaluation result SHA-256: `{data['physics_result_sha256']}`
- final confirmatory result SHA-256: `{digest}`

## Confirmatory scope

- satellite-disjoint objects: `12`
- documented truth intervals: `41`
- verified-quiet controls: `2`
- methods: `16`
- matching tolerance: `{data['matching_tolerance_hours']}` hours
- satellite-cluster bootstrap replicates: `{data['bootstrap_iterations']}`
- bootstrap seed: `{data['bootstrap_seed']}`

## Complete confirmatory metrics

Values in brackets are satellite-cluster 95% bootstrap confidence intervals.

| Method | Precision | Recall | F1 | False events / covered object-month | Median absolute first-alarm delay h | Abstention |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(metric_rows)}

## Physics-ML v1.0

- true positives: `{target_summary.get('true_positives')}`
- false negatives: `{target_summary.get('false_negatives')}`
- verified-quiet false positives: `{target_summary.get('false_positives')}`
- precision: `{fmt(target_summary.get('precision'))}`
- recall: `{fmt(target_summary.get('recall'))}`
- F1: `{fmt(target_summary.get('f1'))}`
- covered verified-quiet exposure: `{fmt(target_summary.get('covered_verified_quiet_object_months'))}` object-month
- false events per covered object-month: `{fmt(target_summary.get('false_events_per_object_month'))}`
- median absolute first-alarm delay: `{fmt(target_summary.get('median_absolute_detection_delay_hours'), 2)}` hours
- mean case abstention: `{fmt(target_summary.get('mean_case_abstention_fraction'))}`

## Frozen integration and publication gate

{gate_text}

Best risk-compliant principal comparator: `{None if comparator is None else comparator.get('method')}` with confirmatory F1 `{None if comparator is None else fmt(comparator.get('f1'))}`.

**Overall gate: {disposition}.**

{next_step}

## Confirmatory ranking

{ranking_text}

## Orbit-regime F1

| Method | LEO | MEO | GEO | HEO | IGSO |
|---|---:|---:|---:|---:|---:|
{chr(10).join(regime_rows)}

Small regime subsets can have wide or degenerate intervals. The machine-readable result contains the full per-regime statistical blocks.

## Statistical and claim boundary

Event-evidence histories retain positive-unlabelled semantics: unmatched predictions outside documented intervals are not converted into false positives. False events are counted only on verified-quiet exposure. Confidence intervals quantify satellite-cluster uncertainty but do not alter the gate after the fact.

This result is final for the frozen physics-ML v1.0 method and benchmark v1.0 confirmatory partition. A failed result cannot be rescued by changing thresholds and rerunning this confirmatory set.
'''
    Path('research/confirmatory_v1/RESULTS-v1.0.md').write_text(results)

    freeze_sha = hashlib.sha256(FREEZE.read_bytes()).hexdigest()
    lock = {
        'schema': 'smd-confirmatory-run-lock-v1',
        'one_shot_completed': True,
        'rerun_forbidden': True,
        'frozen_code_commit': data['frozen_code_commit'],
        'trigger_commit': data.get('trigger_commit'),
        'github_workflow_run_id': data.get('github_workflow_run_id'),
        'preconfirmatory_freeze_sha256': freeze_sha,
        'final_result_sha256': digest,
        'gate_passed': bool(gate['passed']),
    }
    Path('research/confirmatory_v1/RUN-LOCK-v1.0.json').write_text(json.dumps(lock, indent=2) + '\n')

    audit = f'''# Confirmatory evaluation audit

## Disposition

Confirmatory evaluation was executed as a single confirmatory evaluation after the complete method, thresholds, comparison rules, benchmark hashes and integration/publication gate were committed and frozen.

Confirmatory objects: `12`. Confirmatory truth intervals: `41`. Verified-quiet controls: `2`. Methods evaluated: `16`.

## Data firewall

Before the irreversible boundary, the workflow reconstructed only development/calibration data, reproduced the frozen generic-baseline calibration thresholds, fitted the frozen physics-ML reference stack and ran syntax/regression checks. Confirmatory histories were materialized only after those checks passed.

The development exporters retained their normal confirmatory refusal. Confirmatory evaluation used an explicit single-use wrapper around the same frozen feature exporter. The wrapper refuses execution once the final result exists.

## No post-hoc modification

No confirmatory metric was used to change an architecture, feature, threshold, calibration rule, event-matching rule, baseline definition or gate criterion. The one-shot workflow removes itself in the result commit. Historical workflow reruns are also guarded by the final result on `origin/main` before confirmatory access.

## Freeze

- preconfirmatory freeze SHA-256: `{freeze_sha}`
- final result SHA-256: `{digest}`
- gate: `{disposition}`

## Consequence

{next_step}
'''
    Path('review/CONFIRMATORY-AUDIT.md').write_text(audit)

    test = f'''#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'benchmark-results/confirmatory-v1-final.json'
SIDECAR = ROOT / 'benchmark-results/confirmatory-v1-final.json.sha256'
EXPECTED_SHA256 = '{digest}'
EXPECTED_METHODS = {EXPECTED_METHODS!r}


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
    assert set(gate['checks']) == {{
        'at_least_one_true_positive',
        'recall_strictly_greater_than_0_20',
        'positive_covered_quiet_exposure',
        'false_event_rate_at_most_1_per_covered_object_month',
        'f1_strictly_greater_than_best_risk_compliant_principal_comparator',
        'median_absolute_detection_delay_at_most_24_hours',
    }}
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
'''
    Path('tests/confirmatory_v1_freeze_test.py').write_text(test)

    print(json.dumps({
        'final_result_sha256': digest,
        'gate_passed': bool(gate['passed']),
        'physics_ml_v1_recall': target_summary.get('recall'),
        'physics_ml_v1_f1': target_summary.get('f1'),
    }, indent=2))


if __name__ == '__main__':
    main()
