"""Frozen confirmatory-v1 statistics from recorded case-level outputs.

Load through research.historical_v1.load_evaluator so every archive byte is
verified first. Source definitions and scope are recorded in MANIFEST.json.
"""
from __future__ import annotations

import math
import random
import statistics
from datetime import datetime, timezone

EVALUATOR_VERSION = 'confirmatory-v1-historical'


def parse_time(value: str) -> float:
    """Interpret offset-free GP/event timestamps as UTC, never host local time."""
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()

SEED = 3404

MATCH_TOLERANCE_HOURS = 24.0

BOOTSTRAP_ITERATIONS = 1000

METHOD_ORDER = (
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
)

ORBIT_REGIMES = ('LEO', 'MEO', 'GEO', 'HEO', 'IGSO')

def finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None

def match_event_dicts(predicted, truth, tolerance_hours=MATCH_TOLERANCE_HOURS):
    tolerance = float(tolerance_hours) * 3600.0
    candidates = []
    for pi, prediction in enumerate(predicted):
        ps = parse_time(prediction['start_utc'])
        pe = parse_time(prediction['end_utc'])
        strongest = parse_time(prediction['strongest_utc'])
        for ti, target in enumerate(truth):
            ts = parse_time(str(target['start']))
            te = parse_time(str(target.get('end') or target['start']))
            if pe < ts - tolerance or ps > te + tolerance:
                continue
            midpoint = 0.5 * (ts + te)
            candidates.append((
                abs(strongest - midpoint),
                pi,
                ti,
                (ps - ts) / 3600.0,
                (strongest - ts) / 3600.0,
            ))
    candidates.sort()
    used_p, used_t, matches = set(), set(), []
    for _, pi, ti, delay, strongest_delay in candidates:
        if pi in used_p or ti in used_t:
            continue
        used_p.add(pi)
        used_t.add(ti)
        matches.append({
            'prediction_index': pi,
            'truth_index': ti,
            # Detection delay is the first threshold-crossing/event-onset time, not the later
            # strongest point used only for deterministic one-to-one matching.
            'delay_hours': delay,
            'strongest_point_delay_hours': strongest_delay,
        })
    return {
        'matches': matches,
        'tp': len(matches),
        'fn': len(truth) - len(matches),
        'unmatched_predictions': len(predicted) - len(matches),
    }

def summarize_results(case_results):
    tp = fp = fn = 0
    delays = []
    abs_delays = []
    object_months = 0.0
    abstention_sum = 0.0
    case_count = 0
    positive_cases = quiet_cases = 0
    for case in case_results:
        coverage = float(case.get('coverage_fraction') or 0.0)
        abstention_sum += 1.0 - coverage
        case_count += 1
        label = case.get('label_status')
        predicted = case.get('predicted_events') or []
        truth = case.get('truth_events') or []
        if label == 'event-evidence':
            positive_cases += 1
            match = match_event_dicts(predicted, truth)
            tp += match['tp']
            fn += match['fn']
            delays.extend(item['delay_hours'] for item in match['matches'])
            abs_delays.extend(abs(item['delay_hours']) for item in match['matches'])
        elif label == 'verified-quiet':
            quiet_cases += 1
            fp += len(predicted)
            object_months += float(case.get('span_days') or 0.0) * coverage / 30.4375
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    if tp == 0 and fn > 0:
        # A detector that misses all labelled events has F1=0 even if precision is undefined
        # because it emitted no scorable predictions.
        f1 = 0.0
    elif precision is not None and recall is not None and precision + recall:
        f1 = 2.0 * precision * recall / (precision + recall)
    else:
        f1 = None
    return {
        'cases': len(case_results),
        'positive_cases': positive_cases,
        'verified_quiet_cases': quiet_cases,
        'true_positives': tp,
        'false_positives': fp,
        'false_negatives': fn,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'covered_verified_quiet_object_months': object_months,
        'false_events_per_object_month': fp / object_months if object_months > 0 else None,
        'median_detection_delay_hours': statistics.median(delays) if delays else None,
        'median_absolute_detection_delay_hours': statistics.median(abs_delays) if abs_delays else None,
        'mean_case_abstention_fraction': abstention_sum / case_count if case_count else None,
    }

def _percentile(values, q):
    material = sorted(float(v) for v in values if finite(v) is not None)
    if not material:
        return None
    position = (len(material) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return material[lo]
    return material[lo] * (hi - position) + material[hi] * (position - lo)

def bootstrap(case_results, iterations=BOOTSTRAP_ITERATIONS, seed=SEED):
    if not case_results:
        return {}
    rng = random.Random(seed)
    fields = (
        'precision',
        'recall',
        'f1',
        'false_events_per_object_month',
        'median_detection_delay_hours',
        'median_absolute_detection_delay_hours',
        'mean_case_abstention_fraction',
    )
    samples = {field: [] for field in fields}
    for _ in range(int(iterations)):
        drawn = [rng.choice(case_results) for _ in case_results]
        summary = summarize_results(drawn)
        for field in fields:
            value = summary.get(field)
            if finite(value) is not None:
                samples[field].append(float(value))
    return {
        field: {
            'low_95': _percentile(values, 0.025),
            'high_95': _percentile(values, 0.975),
            'bootstrap_samples': len(values),
        }
        for field, values in samples.items()
    }

def evaluation_block(case_results):
    return {
        'summary': summarize_results(case_results),
        'satellite_cluster_bootstrap_95_ci': bootstrap(case_results),
    }

def by_regime(case_results):
    output = {}
    for regime in ORBIT_REGIMES:
        selected = [case for case in case_results if case.get('orbit_regime') == regime]
        if selected:
            output[regime] = evaluation_block(selected)
    return output

MIN_RECALL_EXCLUSIVE = 0.20

MAX_FALSE_RATE = 1.0

MAX_MEDIAN_ABS_DELAY_HOURS = 24.0

MIN_TRUE_POSITIVES = 1

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
