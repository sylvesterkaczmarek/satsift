#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from research.evaluation_version import EVALUATION_VERSION
from research.event_matching import EVENT_MATCHING_VERSION, parse_truth_events_us, validated_truth_events

from research.physics_v1.core import PhysicsNoiseModel
from research.physics_v1.run_development import (
    SEQUENTIAL_BASE_THRESHOLD,
    SEQUENTIAL_DEV_SUPPORT_THRESHOLD,
    SEQUENTIAL_FINAL_SUPPORT_THRESHOLD,
    development_quiet_physics_crossfit,
    physics_rows,
)
from research.physics_v1.screen import ManeuverPhysicsInverter
from research.selective_v1.core import SupportModel, match_events, parse_time
from research.selective_v1.models import make_candidate
from research.selective_v1.train_compare import (
    MATCH_TOLERANCE_HOURS,
    case_regime,
    coverage_adjusted_quiet,
    grouped_rows,
    load_document,
    rows_for_cases,
    sequences,
)
from research.sequential_v1.operational import (
    OBJECT_MONTH_DAYS,
    SequentialEventLayer,
    calibrate_operational_threshold,
    empirical_exceedance_bound,
)
from research.sequential_v1.run_development import development_quiet_crossfit
from .gate import SelectiveIntegrityGate

PHYSICS_Q0 = 0.24444444444444446
PHYSICS_DEVELOPMENT_WEALTH_THRESHOLD = 1.730962511467316
PHYSICS_FINAL_WEALTH_THRESHOLD = 1.01
PHYSICS_DEVELOPMENT_PU = 0.8660130718954249
RISK_BUDGET = 1.0


def condition_of(case: dict) -> str:
    return str((case.get('integrity_stress') or {}).get('condition') or 'clean')


def expected_response(case: dict) -> str:
    return str((case.get('integrity_stress') or {}).get('expected_response') or 'unspecified')


def attack_class(case: dict) -> str:
    return str((case.get('integrity_stress') or {}).get('attack_class') or 'unspecified')


def base_case_id(case: dict) -> str:
    return str(case.get('base_case_id') or case.get('case_id'))


def clean_ids(cases: dict[str, dict], *, label_status: str | None = None, split: str | None = None) -> list[str]:
    result = []
    for case_id, case in cases.items():
        if condition_of(case) != 'clean':
            continue
        if label_status is not None and case.get('label_status') != label_status:
            continue
        if split is not None and case.get('split') != split:
            continue
        result.append(case_id)
    return sorted(result)


def sequential_truth_percentiles(scored_rows, truth_events, quiet_wealth) -> list[float]:
    parse_truth_events_us(truth_events)
    if not quiet_wealth:
        return []
    layer = SequentialEventLayer(
        base_score_threshold=SEQUENTIAL_BASE_THRESHOLD,
        q0=PHYSICS_Q0,
        wealth_threshold=1e100,
    )
    steps, _ = layer.run(scored_rows)
    tolerance = MATCH_TOLERANCE_HOURS * 3600.0
    result = []
    for truth in truth_events:
        start = parse_time(str(truth['start'])) - tolerance
        end = parse_time(str(truth.get('end') or truth['start'])) + tolerance
        values = [step.wealth for step in steps if step.wealth is not None and start <= parse_time(step.epoch_utc) <= end]
        if not values:
            continue
        maximum = max(values)
        below = sum(value < maximum for value in quiet_wealth)
        equal = sum(value == maximum for value in quiet_wealth)
        result.append((below + 0.5 * equal) / len(quiet_wealth))
    return result


def score_with_stack(case: dict, feature_rows: list[dict], model, support, inverter, gate, *, wealth_threshold: float):
    secure, gate_meta = gate.score_sequence(model, support, case, feature_rows)
    transformed, estimates = physics_rows(feature_rows, secure, inverter)
    layer = SequentialEventLayer(
        base_score_threshold=SEQUENTIAL_BASE_THRESHOLD,
        q0=PHYSICS_Q0,
        wealth_threshold=wealth_threshold,
    )
    steps, events = layer.run(transformed)
    total = len(transformed)
    abstained = sum(row.status != 'scored' for row in transformed)
    return {
        'rows': transformed,
        'estimates': estimates,
        'steps': steps,
        'events': events,
        'gate_meta': gate_meta,
        'summary': {
            'rows_input': total,
            'rows_scored': sum(row.status == 'scored' for row in transformed),
            'rows_abstained': abstained,
            'row_abstention_fraction': abstained / total if total else 1.0,
            'physics_abstentions': sum(estimate is not None and estimate.status == 'abstain' for estimate in estimates),
            'physically_feasible_rows': sum(estimate is not None and estimate.status == 'feasible' for estimate in estimates),
            'hard_case_abstention': bool(gate_meta['case_decision'].abstain),
            'case_reasons': list(gate_meta['case_decision'].reasons),
            'case_alerts': list(gate_meta['case_decision'].alerts),
            'row_reason_counts': gate_meta['reason_counts'],
            'predicted_events': len(events),
        },
    }


def structural_integrity(condition_ids: list[str], cases: dict[str, dict], gate: SelectiveIntegrityGate) -> dict:
    hard = 0
    reasons: Counter[str] = Counter()
    alerts: Counter[str] = Counter()
    cases_with_alerts = 0
    for case_id in condition_ids:
        decision = gate.case_decision(cases[case_id])
        hard += int(decision.abstain)
        reasons.update(decision.reasons)
        alerts.update(decision.alerts)
        cases_with_alerts += int(bool(decision.alerts))
    count = len(condition_ids)
    return {
        'case_count': count,
        'hard_case_abstentions': hard,
        'hard_case_abstention_fraction': hard / count if count else None,
        'cases_with_recoverable_alerts': cases_with_alerts,
        'recoverable_alert_case_fraction': cases_with_alerts / count if count else None,
        'reason_counts': dict(sorted(reasons.items())),
        'recoverable_alert_counts': dict(sorted(alerts.items())),
    }


def clean_physics_quiet_wealth(clean_cases: dict[str, dict], clean_rows: dict[str, list[dict]]) -> tuple[list[float], list[str]]:
    dev_quiet, _leo, support_threshold, sequential_quiet_cv = development_quiet_crossfit(clean_cases, clean_rows)
    if abs(float(support_threshold) - SEQUENTIAL_DEV_SUPPORT_THRESHOLD) > 1e-9:
        raise ValueError(f'Physics evaluation development support threshold drifted: {support_threshold}')
    quiet_cv, _summaries = development_quiet_physics_crossfit(clean_cases, clean_rows, sequential_quiet_cv)
    q0 = empirical_exceedance_bound(quiet_cv, base_score_threshold=SEQUENTIAL_BASE_THRESHOLD)['q0']
    if abs(float(q0) - PHYSICS_Q0) > 1e-12:
        raise ValueError(f'Physics evaluation q0 drifted: {q0}')
    wealth = []
    for quiet in quiet_cv:
        layer = SequentialEventLayer(base_score_threshold=SEQUENTIAL_BASE_THRESHOLD, q0=PHYSICS_Q0, wealth_threshold=1e100)
        steps, _ = layer.run(quiet['scored_rows'])
        wealth.extend(step.wealth for step in steps if step.wealth is not None)
    if not wealth:
        raise ValueError('Physics evaluation clean quiet reference produced no sequential wealth')
    return wealth, dev_quiet


def evaluate_development_detection(
    condition_ids: list[str], cases: dict[str, dict], rows_by_case: dict[str, list[dict]],
    model, support, inverter, gate, clean_quiet_wealth,
) -> dict:
    event_ids = [
        case_id for case_id in condition_ids
        if cases[case_id].get('split') == 'development'
        and cases[case_id].get('label_status') == 'event-evidence'
        and case_regime(cases[case_id]) == 'LEO'
    ]
    tp = fn = predicted = rows_total = rows_abstained = hard = 0
    rankings: list[float] = []
    reasons: Counter[str] = Counter()
    alerts: Counter[str] = Counter()
    per_case = []
    for case_id in sorted(event_ids):
        case = cases[case_id]
        result = score_with_stack(
            case, rows_by_case.get(case_id, []), model, support, inverter, gate,
            wealth_threshold=PHYSICS_DEVELOPMENT_WEALTH_THRESHOLD,
        )
        matched = match_events(result['events'], validated_truth_events(case), MATCH_TOLERANCE_HOURS)
        tp += matched['tp']; fn += matched['fn']; predicted += len(result['events'])
        rankings.extend(sequential_truth_percentiles(result['rows'], validated_truth_events(case), clean_quiet_wealth))
        summary = result['summary']
        rows_total += summary['rows_input']; rows_abstained += summary['rows_abstained']; hard += int(summary['hard_case_abstention'])
        reasons.update(summary['case_reasons']); reasons.update(summary['row_reason_counts']); alerts.update(summary['case_alerts'])
        per_case.append({
            'case_id': case_id,
            'base_case_id': base_case_id(case),
            'truth_intervals': len(validated_truth_events(case)),
            'tp': matched['tp'], 'fn': matched['fn'],
            **summary,
        })
    return {
        'scope': 'LEO development event-evidence cases at the Physics evaluation development diagnostic support/calibration point',
        'case_count': len(event_ids),
        'truth_intervals': tp + fn,
        'tp': tp, 'fn': fn,
        'recall': tp / (tp + fn) if tp + fn else None,
        'predicted_events': predicted,
        'pu_sequential_wealth_mean_percentile': mean(rankings) if rankings else None,
        'pu_scorable_truth_intervals': len(rankings),
        'row_abstention_fraction': rows_abstained / rows_total if rows_total else 1.0,
        'hard_case_abstention_fraction': hard / len(event_ids) if event_ids else None,
        'reason_counts': dict(sorted(reasons.items())),
        'recoverable_alert_counts': dict(sorted(alerts.items())),
        'per_case': per_case,
    }


def evaluate_final_aqua(
    condition_ids: list[str], cases: dict[str, dict], rows_by_case: dict[str, list[dict]],
    clean_aqua_base: str, model, support, inverter, gate,
) -> dict:
    candidates = [case_id for case_id in condition_ids if base_case_id(cases[case_id]) == clean_aqua_base]
    if len(candidates) != 1:
        raise ValueError(f'expected one Aqua variant for condition, found {candidates}')
    case_id = candidates[0]; case = cases[case_id]
    result = score_with_stack(
        case, rows_by_case.get(case_id, []), model, support, inverter, gate,
        wealth_threshold=PHYSICS_FINAL_WEALTH_THRESHOLD,
    )
    summary = result['summary']
    adjusted = coverage_adjusted_quiet(case, result['rows'])
    exposure = float(adjusted.get('span_days') or 0.0) / OBJECT_MONTH_DAYS
    false_events = len(result['events'])
    q0_stress = None
    try:
        q0_stress = empirical_exceedance_bound([adjusted], base_score_threshold=SEQUENTIAL_BASE_THRESHOLD)['q0']
    except ValueError:
        pass
    recalibrated = None
    if exposure > 0:
        try:
            recalibrated = calibrate_operational_threshold(
                [adjusted],
                base_score_threshold=SEQUENTIAL_BASE_THRESHOLD,
                q0=PHYSICS_Q0,
                target_false_events_per_object_month=RISK_BUDGET,
            )
        except (ValueError, RuntimeError):
            pass
    return {
        'scope': 'held-out LEO calibration verified-quiet Aqua case at the frozen Physics evaluation final support point',
        'case_id': case_id,
        'base_case_id': clean_aqua_base,
        **summary,
        'coverage_fraction': adjusted['coverage_fraction'],
        'covered_verified_quiet_object_months': exposure,
        'frozen_false_events': false_events,
        'frozen_false_events_per_object_month': false_events / exposure if exposure > 0 else None,
        'empirical_q0_under_stress': q0_stress,
        'recalibrated_wealth_threshold': recalibrated['selected_wealth_threshold'] if recalibrated else None,
        'risk_budget_exceeded': bool(exposure > 0 and false_events / exposure > RISK_BUDGET),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Run Integrity evaluation selective-abstention and integrity/security stress evaluation.')
    parser.add_argument('--features', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('benchmark-results/integrity-v1-stress-case-statistics-v3.json'))
    args = parser.parse_args()

    document = load_document(args.features)
    if document.get('confirmatory_sealed') is not True:
        raise ValueError('CONFIRMATORY PARTITION IS SEALED')
    cases, rows_by_case = grouped_rows(document)
    if any(case.get('split') == 'confirmatory' for case in cases.values()):
        raise ValueError('CONFIRMATORY PARTITION IS SEALED: integrity stress input contains confirmatory metadata')

    by_condition: dict[str, list[str]] = defaultdict(list)
    for case_id, case in cases.items():
        by_condition[condition_of(case)].append(case_id)
    for values in by_condition.values():
        values.sort()
    if len(by_condition) != 13 or 'clean' not in by_condition:
        raise ValueError(f'expected clean plus twelve stress conditions, found {sorted(by_condition)}')

    clean_case_map = {case_id: cases[case_id] for case_id in by_condition['clean']}
    clean_rows = {case_id: rows_by_case.get(case_id, []) for case_id in by_condition['clean']}
    clean_quiet = clean_ids(cases, label_status='verified-quiet')
    dev_quiet = clean_ids(cases, label_status='verified-quiet', split='development')
    cal_quiet = clean_ids(cases, label_status='verified-quiet', split='calibration')
    if len(clean_quiet) != 8 or len(dev_quiet) != 4 or len(cal_quiet) != 4:
        raise ValueError('Integrity evaluation requires four clean development and four clean calibration verified-quiet cases')

    clean_quiet_wealth, physics_dev_quiet = clean_physics_quiet_wealth(clean_case_map, clean_rows)
    if sorted(physics_dev_quiet) != sorted(dev_quiet):
        raise ValueError('Physics evaluation development quiet set drifted')

    dev_model = make_candidate('transformer').fit(sequences(clean_rows, dev_quiet))
    dev_support = SupportModel(k=5, min_reference_satellites=2).fit(rows_for_cases(clean_rows, dev_quiet))
    dev_noise = PhysicsNoiseModel(min_reference_satellites=3).fit(rows_for_cases(clean_rows, dev_quiet))
    dev_inverter = ManeuverPhysicsInverter(dev_noise)
    dev_gate = SelectiveIntegrityGate(support_threshold=SEQUENTIAL_DEV_SUPPORT_THRESHOLD)

    aqua_candidates = [case_id for case_id in cal_quiet if case_regime(cases[case_id]) == 'LEO']
    if len(aqua_candidates) != 1:
        raise ValueError(f'expected one clean LEO calibration quiet case, found {aqua_candidates}')
    clean_aqua = aqua_candidates[0]
    clean_aqua_base = base_case_id(cases[clean_aqua])
    final_training = [case_id for case_id in clean_quiet if case_id != clean_aqua]
    final_model = make_candidate('transformer').fit(sequences(clean_rows, final_training))
    final_support = SupportModel(k=5, min_reference_satellites=1).fit(rows_for_cases(clean_rows, final_training))
    final_noise = PhysicsNoiseModel(min_reference_satellites=3).fit(rows_for_cases(clean_rows, final_training))
    final_inverter = ManeuverPhysicsInverter(final_noise)
    final_gate = SelectiveIntegrityGate(support_threshold=SEQUENTIAL_FINAL_SUPPORT_THRESHOLD)

    results = {}
    order = ['clean'] + sorted(condition for condition in by_condition if condition != 'clean')
    for condition in order:
        ids = by_condition[condition]
        sample = cases[ids[0]]
        results[condition] = {
            'condition': condition,
            'attack_class': attack_class(sample),
            'expected_response': expected_response(sample),
            'structural_integrity': structural_integrity(ids, cases, dev_gate),
            'development_detection': evaluate_development_detection(
                ids, cases, rows_by_case, dev_model, dev_support, dev_inverter, dev_gate, clean_quiet_wealth
            ),
            'final_calibration': evaluate_final_aqua(
                ids, cases, rows_by_case, clean_aqua_base, final_model, final_support, final_inverter, final_gate
            ),
        }

    clean = results['clean']
    for item in results.values():
        detection = item['development_detection']
        clean_detection = clean['development_detection']
        detection['pu_delta_vs_clean'] = (
            None if detection['pu_sequential_wealth_mean_percentile'] is None or clean_detection['pu_sequential_wealth_mean_percentile'] is None
            else detection['pu_sequential_wealth_mean_percentile'] - clean_detection['pu_sequential_wealth_mean_percentile']
        )
        calibration = item['final_calibration']; clean_cal = clean['final_calibration']
        calibration['coverage_delta_vs_clean'] = calibration['coverage_fraction'] - clean_cal['coverage_fraction']
        calibration['q0_delta_vs_clean'] = (
            None if calibration['empirical_q0_under_stress'] is None or clean_cal['empirical_q0_under_stress'] is None
            else calibration['empirical_q0_under_stress'] - clean_cal['empirical_q0_under_stress']
        )
        calibration['false_event_rate_delta_vs_clean'] = (
            None if calibration['frozen_false_events_per_object_month'] is None or clean_cal['frozen_false_events_per_object_month'] is None
            else calibration['frozen_false_events_per_object_month'] - clean_cal['frozen_false_events_per_object_month']
        )

    findings = []
    for condition in ('unresolved_duplicate', 'catalogue_regime_change', 'truncated_history'):
        if results[condition]['structural_integrity']['hard_case_abstention_fraction'] < 1.0:
            findings.append(f'{condition} was not fully contained by case-level abstention')
    corrected_alerts = results['corrected_duplicate']['structural_integrity']['recoverable_alert_counts'].get('catalogue_correction_resolved', 0)
    if corrected_alerts < len(by_condition['corrected_duplicate']):
        findings.append('not every corrected-duplicate stress case surfaced a catalogue-correction audit alert')
    replay_alerts = results['replay']['structural_integrity']['recoverable_alert_counts'].get('replay_or_exact_duplicate_detected', 0)
    if replay_alerts < len(by_condition['replay']):
        findings.append('not every replay stress case surfaced an exact-duplicate audit alert')
    false_attack = results['adversarial_false_maneuver']['final_calibration']
    clean_false = clean['final_calibration']
    if false_attack['frozen_false_events'] > clean_false['frozen_false_events']:
        findings.append('adversarial false-maneuver manipulation increased held-out verified-quiet false events')
    if false_attack['risk_budget_exceeded']:
        findings.append('adversarial false-maneuver manipulation exceeded the frozen false-event budget')

    vulnerabilities = []
    corrected_final = results['corrected_duplicate']['final_calibration']
    clean_final = clean['final_calibration']
    if corrected_final['coverage_fraction'] < clean_final['coverage_fraction']:
        vulnerabilities.append(
            'legitimate corrected catalogue records reduce held-out support coverage; '
            f"coverage {clean_final['coverage_fraction']:.6f} -> {corrected_final['coverage_fraction']:.6f}"
        )
    suppression = results['adversarial_maneuver_suppression']['development_detection']
    suppression_delta = suppression.get('pu_delta_vs_clean')
    if suppression_delta is not None and suppression_delta < -0.01:
        vulnerabilities.append(
            'adversarial maneuver suppression measurably degrades development event ranking; '
            f"PU delta {suppression_delta:.6f}"
        )

    output = {
        'schema': 'smd-integrity-security-v1-stress-results',
        'evaluation_version': EVALUATION_VERSION,
        'scoring_version': EVENT_MATCHING_VERSION,
        'paper_track': 'AI-integrity-security',
        'method': 'selective-ml-v1.0 + sequential-evidence-v1.0 + maneuver-physics-v1.0 + integrity-abstention-v1.0',
        'confirmatory_partition_accessed': False,
        'detector_v0_4_modified': False,
        'frozen_parameters': {
            'base_score_threshold': SEQUENTIAL_BASE_THRESHOLD,
            'development_support_threshold': SEQUENTIAL_DEV_SUPPORT_THRESHOLD,
            'final_support_threshold': SEQUENTIAL_FINAL_SUPPORT_THRESHOLD,
            'q0': PHYSICS_Q0,
            'development_wealth_threshold': PHYSICS_DEVELOPMENT_WEALTH_THRESHOLD,
            'final_wealth_threshold': PHYSICS_FINAL_WEALTH_THRESHOLD,
            'risk_budget_false_events_per_covered_object_month': RISK_BUDGET,
        },
        'physics_reference': {
            'development_pu_sequential_wealth_mean_percentile': PHYSICS_DEVELOPMENT_PU,
            'development_tp': 0,
            'development_fn': 36,
            'final_aqua_coverage_fraction': 0.5277777777777778,
            'final_aqua_false_events': 0,
        },
        'qualified_regimes': sorted(dev_noise.qualified_regimes()),
        'stress_condition_count': len(results) - 1,
        'stress_conditions': results,
        'security_gate_failures': findings,
        'observed_vulnerabilities': vulnerabilities,
        'security_findings': findings + vulnerabilities,
        'claim_boundary': 'development/calibration deterministic integrity stress only; no confirmatory access, formal adversarial-robustness claim, or operational cyber-security guarantee',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    print(json.dumps({
        'conditions': len(results),
        'clean_development_detection': results['clean']['development_detection'],
        'clean_final_calibration': results['clean']['final_calibration'],
        'findings': findings,
        'output': str(args.output),
    }, indent=2))


if __name__ == '__main__':
    main()
