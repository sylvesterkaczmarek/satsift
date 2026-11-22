#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path

from research.comparison_v1 import run_comparison as cmp

FINAL_RESULT = Path('benchmark-results/confirmatory-v1-final.json')
MIN_RECALL_EXCLUSIVE = 0.20
MAX_FALSE_RATE = 1.0
MAX_MEDIAN_ABS_DELAY_HOURS = 24.0
MIN_TRUE_POSITIVES = 1


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def close(left, right, *, rel=1e-6, abs_=1e-9) -> bool:
    if finite(left) is None or finite(right) is None:
        return left == right
    return math.isclose(float(left), float(right), rel_tol=rel, abs_tol=abs_)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def verify_freeze(freeze_path: Path, frozen_comparison_path: Path) -> dict:
    if FINAL_RESULT.exists():
        raise RuntimeError('CONFIRMATORY RUN LOCK: final confirmatory result already exists; rerun is forbidden')
    freeze = load_json(freeze_path)
    if freeze.get('schema') != 'smd-confirmatory-preconfirmatory-freeze-v1':
        raise ValueError('invalid Confirmatory evaluation preconfirmatory freeze')
    if freeze.get('confirmatory_accessed') is not False:
        raise ValueError('preconfirmatory freeze must record confirmatory_accessed=false')
    if sha256_file(frozen_comparison_path) != freeze['comparison_result_sha256']:
        raise ValueError('Comparison evaluation frozen comparison hash mismatch')
    gate = freeze.get('gate') or {}
    expected = {
        'minimum_true_positives': MIN_TRUE_POSITIVES,
        'minimum_recall_exclusive': MIN_RECALL_EXCLUSIVE,
        'maximum_false_events_per_covered_object_month': MAX_FALSE_RATE,
        'require_positive_covered_quiet_exposure': True,
        'require_f1_strictly_greater_than_best_risk_compliant_principal_comparator': True,
        'maximum_median_absolute_detection_delay_hours': MAX_MEDIAN_ABS_DELAY_HOURS,
    }
    if gate != expected:
        raise ValueError(f'Confirmatory evaluation gate drifted: {gate!r}')
    return freeze


def verify_devcal(features_path: Path):
    document = cmp.load_document(features_path)
    cases, rows_by_case = cmp.grouped_rows(document)
    splits = {str(case.get('split')) for case in cases.values()}
    if splits != {'development', 'calibration'}:
        raise ValueError(f'Confirmatory evaluation preflight expects development/calibration only, got {sorted(splits)}')
    if len(cases) != 28 or len({str(case.get('object_id')) for case in cases.values()}) != 28:
        raise ValueError('Confirmatory evaluation preflight requires exactly 28 satellite-disjoint development/calibration cases')
    return document, cases, rows_by_case


def verify_confirmatory(features_path: Path, devcal_cases: dict):
    # Confirmatory evaluation is the sole explicit authorization path for the frozen holdout.
    # Normal selective-v1 loading/grouping remains sealed against confirmatory data.
    document = load_json(features_path)
    if document.get('schema') != 'smd-selective-v1-features-v1':
        raise ValueError('Confirmatory evaluation confirmatory feature artifact schema is invalid')
    if document.get('confirmatory_sealed') is not False:
        raise ValueError('Confirmatory evaluation confirmatory artifact must record confirmatory_sealed=false')
    if document.get('confirmatory_confirmatory_authorized') is not True or document.get('one_shot') is not True:
        raise ValueError('Confirmatory evaluation confirmatory artifact lacks explicit one-shot authorization')
    if document.get('included_splits') != ['confirmatory']:
        raise ValueError('Confirmatory evaluation confirmatory artifact must contain only the confirmatory split')

    cases = {str(case['case_id']): case for case in document.get('cases', [])}
    rows_by_case = {case_id: [] for case_id in cases}
    for row in document.get('rows', []):
        case_id = str(row.get('case_id', ''))
        if case_id not in cases:
            raise ValueError(f'Confirmatory evaluation feature row references unknown case {case_id}')
        if str(row.get('split')) != 'confirmatory':
            raise ValueError('Confirmatory evaluation one-shot artifact contains a non-confirmatory feature row')
        rows_by_case[case_id].append(row)
    for values in rows_by_case.values():
        values.sort(key=lambda item: (str(item.get('epoch_utc', '')), int(item.get('index', 0))))

    splits = {str(case.get('split')) for case in cases.values()}
    if splits != {'confirmatory'}:
        raise ValueError(f'Confirmatory evaluation one-shot input must contain confirmatory cases only, got {sorted(splits)}')
    if len(cases) != 12 or len({str(case.get('object_id')) for case in cases.values()}) != 12:
        raise ValueError('Confirmatory evaluation requires exactly 12 satellite-disjoint confirmatory cases')
    truth_count = sum(len(case.get('truth_events') or []) for case in cases.values())
    quiet_count = sum(case.get('label_status') == 'verified-quiet' for case in cases.values())
    if truth_count != 41 or quiet_count != 2:
        raise ValueError(f'frozen confirmatory composition mismatch: truth={truth_count}, quiet={quiet_count}')
    dev_ids = {str(case.get('object_id')) for case in devcal_cases.values()}
    confirm_ids = {str(case.get('object_id')) for case in cases.values()}
    if dev_ids & confirm_ids:
        raise ValueError('confirmatory object IDs overlap development/calibration objects')
    return document, cases, rows_by_case


def frozen_methods(document: dict) -> dict[str, dict]:
    methods = {str(item['method']): item for item in document.get('methods') or []}
    if tuple(document.get('method_order') or []) != cmp.METHOD_ORDER or len(methods) != 16:
        raise ValueError('Comparison evaluation method roster drifted')
    return methods


def calibration_threshold(item: dict):
    value = (item.get('calibration') or {}).get('selected_threshold')
    return value if isinstance(value, (int, float)) else None


def fit_and_verify_generic(method, devcal_cases, devcal_rows, frozen_item):
    train_ids = cmp.quiet_ids(devcal_cases, 'development')
    train_sequences = [devcal_rows[case_id] for case_id in train_ids if devcal_rows.get(case_id)]
    fit_start = time.perf_counter()
    method.fit(train_sequences)
    fit_seconds = time.perf_counter() - fit_start

    calibration_quiet_ids = cmp.quiet_ids(devcal_cases, 'calibration')
    scores = {
        case_id: method.score_sequence(devcal_rows.get(case_id, []))
        for case_id in calibration_quiet_ids
    }
    recalibrated = cmp.calibrate_threshold(
        devcal_cases, devcal_rows, scores, calibration_quiet_ids, budget=cmp.RISK_BUDGET
    )
    expected_threshold = calibration_threshold(frozen_item)
    if expected_threshold is None or not close(recalibrated.get('selected_threshold'), expected_threshold):
        raise RuntimeError(
            f'preconfirmatory calibration mismatch for {method.name}: '
            f"{recalibrated.get('selected_threshold')} != {expected_threshold}"
        )
    expected_exposure = (frozen_item.get('calibration') or {}).get('covered_verified_quiet_object_months')
    if finite(expected_exposure) is not None and not close(
        recalibrated.get('covered_verified_quiet_object_months'), expected_exposure, rel=1e-6, abs_=1e-8
    ):
        raise RuntimeError(f'preconfirmatory quiet-exposure mismatch for {method.name}')
    return fit_seconds, expected_threshold, recalibrated


def physics_reference(devcal_cases, devcal_rows):
    all_quiet = cmp.quiet_ids(devcal_cases, 'development') + cmp.quiet_ids(devcal_cases, 'calibration')
    start = time.perf_counter()
    model = cmp.make_candidate('transformer').fit(cmp.sequences(devcal_rows, all_quiet))
    support = cmp.SupportModel(k=5, min_reference_satellites=3).fit(cmp.rows_for_cases(devcal_rows, all_quiet))
    noise = cmp.PhysicsNoiseModel(min_reference_satellites=3).fit(cmp.rows_for_cases(devcal_rows, all_quiet))
    inverter = cmp.ManeuverPhysicsInverter(noise)
    elapsed = time.perf_counter() - start
    return model, support, inverter, elapsed


def preflight(devcal_cases, devcal_rows, frozen_by_name):
    verified = []
    for method in cmp.make_methods():
        _, threshold, _ = fit_and_verify_generic(method, devcal_cases, devcal_rows, frozen_by_name[method.name])
        verified.append({'method': method.name, 'selected_threshold': threshold})
    model, support, inverter, _ = physics_reference(devcal_cases, devcal_rows)
    if int(model.parameter_count) <= 0:
        raise RuntimeError('Confirmatory evaluation physics-ML Transformer failed preflight fit')
    if 'LEO' not in support.qualified_regimes():
        raise RuntimeError('Confirmatory evaluation physics-ML support model lost frozen LEO qualification')
    if 'LEO' not in inverter.noise_model.qualified_regimes():
        raise RuntimeError('Confirmatory evaluation maneuver-physics reference lost frozen LEO qualification')
    return verified


def detector_confirmatory_result(detector_document, detector_cost, cases):
    raw_by_id = {str(item['case_id']): item for item in detector_document.get('cases') or []}
    primary = []
    for case_id in sorted(cases):
        case = cases[case_id]
        raw = raw_by_id.get(case_id)
        if raw is None:
            raise ValueError(f'detector 0.4 result missing confirmatory case {case_id}')
        abstained = bool(raw.get('abstained'))
        primary.append({
            'case_id': case_id,
            'object_id': str(case.get('object_id')),
            'split': 'confirmatory',
            'label_status': case.get('label_status'),
            'orbit_regime': cmp.normalize_regime(case),
            'span_days': float(raw.get('span_days') or case.get('span_days') or 0.0),
            'coverage_fraction': 0.0 if abstained else 1.0,
            'abstention_fraction': 1.0 if abstained else 0.0,
            'truth_events': case.get('truth_events') or [],
            'predicted_events': raw.get('predicted_events') or [],
        })
    summary = cmp.evaluation_block(primary)
    seconds = float((detector_cost or {}).get('wall_seconds') or 0.0)
    return {
        'method': 'detector-0.4',
        'family': 'target-baseline',
        'settings_source': 'frozen detector 0.4 operating point; no Confirmatory evaluation tuning',
        'confirmatory_case_results': primary,
        'confirmatory_evaluation': summary,
        'confirmatory_by_orbit_regime': cmp.by_regime(primary),
        'computational_cost': {
            'fit_seconds': 0.0,
            'inference_seconds': seconds,
            'evaluation_cases_inference': 12,
            'parameter_count': 0,
            'timing_scope': 'one-shot confirmatory detector 0.4 run',
        },
    }


def generic_confirmatory_result(method, devcal_cases, devcal_rows, confirm_cases, confirm_rows, frozen_item):
    fit_seconds, threshold, recalibrated = fit_and_verify_generic(
        method, devcal_cases, devcal_rows, frozen_item
    )
    start = time.perf_counter()
    scores = {
        case_id: method.score_sequence(confirm_rows.get(case_id, []))
        for case_id in sorted(confirm_cases)
    }
    inference_seconds = time.perf_counter() - start
    primary = cmp.build_case_results(
        confirm_cases, confirm_rows, scores, sorted(confirm_cases), threshold
    )
    rows = sum(len(confirm_rows.get(case_id, [])) for case_id in confirm_cases)
    return {
        'method': method.name,
        'family': frozen_item.get('family') or 'principal-baseline',
        'settings_source': frozen_item.get('settings_source') or 'frozen Comparison evaluation method',
        'frozen_calibration': frozen_item.get('calibration') or recalibrated,
        'confirmatory_case_results': primary,
        'confirmatory_evaluation': cmp.evaluation_block(primary),
        'confirmatory_by_orbit_regime': cmp.by_regime(primary),
        'computational_cost': {
            'fit_seconds': fit_seconds,
            'inference_seconds': inference_seconds,
            'evaluation_cases_inference': 12,
            'parameter_count': int(getattr(method, 'parameter_count', 0) or 0),
            'rows_per_second': rows / inference_seconds if inference_seconds > 0 else None,
            'timing_scope': 'one-shot confirmatory split only for inference',
        },
    }


def physics_confirmatory_result(devcal_cases, devcal_rows, confirm_cases, confirm_rows, frozen_item):
    model, support, inverter, fit_seconds = physics_reference(devcal_cases, devcal_rows)
    primary = []
    start = time.perf_counter()
    for case_id in sorted(confirm_cases):
        predicted, coverage = cmp.physics_score_case(
            model, support, inverter, confirm_rows.get(case_id, [])
        )
        case = confirm_cases[case_id]
        primary.append({
            'case_id': case_id,
            'object_id': str(case.get('object_id')),
            'split': 'confirmatory',
            'label_status': case.get('label_status'),
            'orbit_regime': cmp.normalize_regime(case),
            'span_days': float(case.get('span_days') or 0.0),
            'coverage_fraction': coverage,
            'abstention_fraction': 1.0 - coverage,
            'truth_events': case.get('truth_events') or [],
            'predicted_events': predicted,
        })
    inference_seconds = time.perf_counter() - start
    rows = sum(len(confirm_rows.get(case_id, [])) for case_id in confirm_cases)
    return {
        'method': 'physics-ml-v1.0',
        'family': 'target-method',
        'settings_source': (
            'frozen Physics evaluation Transformer/support/sequential/equivalent-impulse stack; '
            'trained only on pre-confirmatory verified-quiet references; no Confirmatory evaluation tuning'
        ),
        'frozen_calibration': frozen_item.get('calibration') or {},
        'confirmatory_case_results': primary,
        'confirmatory_evaluation': cmp.evaluation_block(primary),
        'confirmatory_by_orbit_regime': cmp.by_regime(primary),
        'computational_cost': {
            'fit_seconds': fit_seconds,
            'inference_seconds': inference_seconds,
            'evaluation_cases_inference': 12,
            'parameter_count': int(model.parameter_count),
            'rows_per_second': rows / inference_seconds if inference_seconds > 0 else None,
            'timing_scope': 'one-shot confirmatory split only for inference',
        },
    }


def metric(item, field, default=-1.0):
    value = ((item.get('confirmatory_evaluation') or {}).get('summary') or {}).get(field)
    return float(value) if finite(value) is not None else float(default)


def ranking(results):
    ordered = sorted(
        results,
        key=lambda item: (
            metric(item, 'f1'),
            metric(item, 'recall'),
            metric(item, 'precision'),
        ),
        reverse=True,
    )
    return [
        {
            'rank_by_confirmatory_f1_then_recall': index,
            'method': item['method'],
            **{
                key: ((item['confirmatory_evaluation']['summary']).get(key))
                for key in (
                    'precision', 'recall', 'f1', 'false_events_per_object_month',
                    'median_detection_delay_hours', 'median_absolute_detection_delay_hours',
                    'mean_case_abstention_fraction', 'covered_verified_quiet_object_months',
                )
            },
        }
        for index, item in enumerate(ordered, start=1)
    ]


def evaluate_gate(results):
    by_name = {item['method']: item for item in results}
    target = by_name['physics-ml-v1.0']['confirmatory_evaluation']['summary']
    comparator_candidates = []
    for item in results:
        if item['method'] == 'physics-ml-v1.0':
            continue
        summary = item['confirmatory_evaluation']['summary']
        exposure = finite(summary.get('covered_verified_quiet_object_months'))
        rate = finite(summary.get('false_events_per_object_month'))
        if exposure is not None and exposure > 0.0 and rate is not None and rate <= MAX_FALSE_RATE:
            comparator_candidates.append(item)
    best = max(comparator_candidates, key=lambda item: metric(item, 'f1')) if comparator_candidates else None
    best_f1 = metric(best, 'f1') if best is not None else None

    target_tp = int(target.get('true_positives') or 0)
    target_recall = finite(target.get('recall'))
    target_exposure = finite(target.get('covered_verified_quiet_object_months'))
    target_rate = finite(target.get('false_events_per_object_month'))
    target_f1 = finite(target.get('f1'))
    target_delay = finite(target.get('median_absolute_detection_delay_hours'))

    checks = {
        'at_least_one_true_positive': target_tp >= MIN_TRUE_POSITIVES,
        'recall_strictly_greater_than_0_20': target_recall is not None and target_recall > MIN_RECALL_EXCLUSIVE,
        'positive_covered_quiet_exposure': target_exposure is not None and target_exposure > 0.0,
        'false_event_rate_at_most_1_per_covered_object_month': (
            target_rate is not None and target_rate <= MAX_FALSE_RATE
        ),
        'f1_strictly_greater_than_best_risk_compliant_principal_comparator': (
            best is not None and target_f1 is not None and best_f1 is not None and target_f1 > best_f1
        ),
        'median_absolute_detection_delay_at_most_24_hours': (
            target_delay is not None and target_delay <= MAX_MEDIAN_ABS_DELAY_HOURS
        ),
    }
    return {
        'gate_version': 'v1.0-preconfirmatory',
        'criteria_frozen_before_confirmatory_access': True,
        'checks': checks,
        'passed': all(checks.values()),
        'best_risk_compliant_principal_comparator': None if best is None else {
            'method': best['method'],
            'f1': best['confirmatory_evaluation']['summary'].get('f1'),
            'recall': best['confirmatory_evaluation']['summary'].get('recall'),
            'false_events_per_object_month': best['confirmatory_evaluation']['summary'].get('false_events_per_object_month'),
            'covered_verified_quiet_object_months': best['confirmatory_evaluation']['summary'].get('covered_verified_quiet_object_months'),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--devcal-features', required=True)
    parser.add_argument('--confirmatory-features')
    parser.add_argument('--detector-results')
    parser.add_argument('--detector-cost')
    parser.add_argument('--frozen-comparison', default='benchmark-results/comparison-v1-development-calibration.json')
    parser.add_argument('--freeze', default='research/confirmatory_v1/PRECONFIRMATORY-FREEZE.json')
    parser.add_argument('--output')
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()

    frozen_path = Path(args.frozen_comparison)
    freeze = verify_freeze(Path(args.freeze), frozen_path)
    frozen_document = load_json(frozen_path)
    frozen_by_name = frozen_methods(frozen_document)
    _, devcal_cases, devcal_rows = verify_devcal(Path(args.devcal_features))

    if args.preflight_only:
        verified = preflight(devcal_cases, devcal_rows, frozen_by_name)
        print(json.dumps({
            'status': 'preflight-passed',
            'confirmatory_accessed': False,
            'generic_methods_reproduced': len(verified),
            'method_count_frozen': len(cmp.METHOD_ORDER),
        }, indent=2))
        return

    if not args.confirmatory_features or not args.detector_results or not args.output:
        raise ValueError('actual Confirmatory evaluation run requires confirmatory features, detector results and output')

    # Irreversible evaluation boundary. Everything above is pre-confirmatory validation.
    _, confirm_cases, confirm_rows = verify_confirmatory(Path(args.confirmatory_features), devcal_cases)
    detector_document = load_json(Path(args.detector_results))
    detector_cost = load_json(Path(args.detector_cost)) if args.detector_cost else {}

    results = [detector_confirmatory_result(detector_document, detector_cost, confirm_cases)]
    for method in cmp.make_methods():
        results.append(generic_confirmatory_result(
            method, devcal_cases, devcal_rows, confirm_cases, confirm_rows, frozen_by_name[method.name]
        ))
    results.append(physics_confirmatory_result(
        devcal_cases, devcal_rows, confirm_cases, confirm_rows, frozen_by_name['physics-ml-v1.0']
    ))

    names = tuple(item['method'] for item in results)
    if names != cmp.METHOD_ORDER:
        raise RuntimeError(f'confirmatory method order drifted: {names}')

    gate = evaluate_gate(results)
    report = {
        'schema': 'smd-confirmatory-v1-final',
        'evaluation_version': cmp.EVALUATION_VERSION,
        'scoring_version': cmp.EVENT_MATCHING_VERSION,
        'paper_track': 'sequential-risk-controlled-satellite-maneuver-screening',
        'one_shot': True,
        'confirmatory_partition_accessed': True,
        'post_confirmatory_method_changes_allowed': False,
        'frozen_code_commit': freeze['frozen_code_commit'],
        'frozen_code_tree': freeze.get('frozen_code_tree'),
        'trigger_commit': os.environ.get('GITHUB_SHA'),
        'github_workflow_run_id': os.environ.get('GITHUB_RUN_ID'),
        'benchmark_manifest_sha256': freeze['benchmark_manifest_sha256'],
        'benchmark_recipe_sha256': freeze['benchmark_recipe_sha256'],
        'comparison_result_sha256': freeze['comparison_result_sha256'],
        'physics_result_sha256': freeze['physics_result_sha256'],
        'benchmark_version': '1.0-confirmatory',
        'confirmatory_objects': 12,
        'confirmatory_truth_intervals': 41,
        'confirmatory_verified_quiet_controls': 2,
        'matching_tolerance_hours': cmp.MATCH_TOLERANCE_HOURS,
        'bootstrap_iterations': cmp.BOOTSTRAP_ITERATIONS,
        'bootstrap_seed': cmp.SEED,
        'method_count': len(cmp.METHOD_ORDER),
        'method_order': list(cmp.METHOD_ORDER),
        'methods': results,
        'confirmatory_ranking_table': ranking(results),
        'integration_publication_gate': gate,
    }
    Path(args.output).write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    target = next(item for item in results if item['method'] == 'physics-ml-v1.0')
    print(json.dumps({
        'confirmatory_evaluation_complete': True,
        'physics_ml_v1': target['confirmatory_evaluation']['summary'],
        'gate': gate,
    }, indent=2))


if __name__ == '__main__':
    main()
