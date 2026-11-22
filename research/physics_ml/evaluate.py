#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from research.evaluation_version import EVALUATION_VERSION
from research.event_matching import (
    EVENT_MATCHING_VERSION,
    match_event_intervals,
    parse_time_us,
    parse_truth_events_us,
    validated_truth_events,
    tolerance_hours_to_us,
)


def parse_time(value: str) -> float:
    text = str(value).strip().replace('Z', '+00:00')
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def event_interval(event: dict) -> tuple[float, float, float]:
    start = parse_time(event.get('start_utc') or event.get('start'))
    end = parse_time(event.get('end_utc') or event.get('end') or event.get('start_utc') or event.get('start'))
    strongest = parse_time(event.get('strongest_utc') or event.get('strongest_epoch') or event.get('start_utc') or event.get('start'))
    return start, end, strongest


def _event_interval_us(event: dict) -> tuple[int, int, int]:
    start = event.get('start_utc') or event.get('start')
    end = event.get('end_utc') or event.get('end') or start
    strongest = event.get('strongest_utc') or event.get('strongest_epoch') or start
    return tuple(parse_time_us(str(value).strip()) for value in (start, end, strongest))


def match_events(predicted: list[dict], truth: list[dict], tolerance_hours: float) -> list[tuple[int, int, float]]:
    pairs = match_event_intervals(
        [_event_interval_us(prediction) for prediction in predicted],
        parse_truth_events_us(truth, allow_utc_aliases=True),
        tolerance_hours_to_us(tolerance_hours),
    )
    return [(pair['prediction_index'], pair['truth_index'], pair['delay_hours']) for pair in pairs]


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0 else None


def summarise(cases: list[dict], tolerance_hours: float) -> dict:
    tp = fp = fn = 0; unscored_predictions = 0; quiet_object_months = 0.0; delays = []; abstained = 0
    truth_total = predictions_total = 0
    for case in cases:
        label_status = str(case.get('label_status', 'unknown'))
        predicted = list(case.get('predicted_events') or []); truth = validated_truth_events(case, allow_utc_aliases=True)
        predictions_total += len(predicted); truth_total += len(truth)
        if case.get('abstained'): abstained += 1
        if label_status == 'event-evidence':
            matches = match_events(predicted, truth, tolerance_hours)
            tp += len(matches); fn += len(truth) - len(matches)
            matched_predictions = {item[0] for item in matches}
            unscored_predictions += len(predicted) - len(matched_predictions)
            delays.extend(item[2] for item in matches)
        elif label_status == 'verified-quiet':
            fp += len(predicted)
            quiet_object_months += max(0.0, float(case.get('span_days') or 0.0)) / 30.4375
        else:
            unscored_predictions += len(predicted)
    precision = _safe_ratio(tp, tp + fp); recall = _safe_ratio(tp, tp + fn)
    f1 = 2.0 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall > 0 else None
    return {
        'cases': len(cases), 'abstained_cases': abstained, 'truth_events': truth_total, 'predicted_events': predictions_total,
        'true_positives': tp, 'false_positives_verified_quiet': fp, 'false_negatives': fn,
        'unscored_predictions': unscored_predictions, 'precision_scorable': precision, 'recall': recall, 'f1_scorable': f1,
        'verified_quiet_object_months': quiet_object_months,
        'false_events_per_verified_quiet_object_month': _safe_ratio(fp, quiet_object_months),
        'median_detection_delay_hours': median(delays) if delays else None,
        'abstention_rate': _safe_ratio(abstained, len(cases)),
    }


def percentile(values: list[float], probability: float) -> float | None:
    finite = sorted(value for value in values if value is not None and math.isfinite(value))
    if not finite: return None
    if len(finite) == 1: return finite[0]
    position = (len(finite) - 1) * probability; lower = int(math.floor(position)); upper = int(math.ceil(position))
    if lower == upper: return finite[lower]
    fraction = position - lower
    return finite[lower] * (1.0 - fraction) + finite[upper] * fraction


def satellite_cluster_bootstrap(cases: list[dict], tolerance_hours: float, *, samples: int = 2000, seed: int = 20260814) -> dict:
    by_object: dict[str, list[dict]] = defaultdict(list)
    for case in cases: by_object[str(case.get('object_id', 'unknown'))].append(case)
    objects = sorted(by_object)
    if not objects: return {}
    rng = random.Random(seed)
    metric_names = ['precision_scorable','recall','f1_scorable','false_events_per_verified_quiet_object_month','median_detection_delay_hours','abstention_rate']
    draws = {name: [] for name in metric_names}
    for _ in range(samples):
        sampled_cases = []
        for _slot in objects: sampled_cases.extend(by_object[rng.choice(objects)])
        summary = summarise(sampled_cases, tolerance_hours)
        for name in metric_names:
            value = summary.get(name)
            if value is not None and math.isfinite(value): draws[name].append(float(value))
    return {name: {'low_95': percentile(values,0.025),'high_95': percentile(values,0.975),'valid_bootstrap_draws': len(values)} for name,values in draws.items()}


def evaluate_document(document: dict, *, split: str = 'primary-test', bootstrap_samples: int = 2000) -> dict:
    tolerance = float(document.get('matching_tolerance_hours',24.0)); all_cases = list(document.get('cases') or [])
    for case in all_cases:
        validated_truth_events(case, allow_utc_aliases=True)
    cases = all_cases if split == 'all' else [case for case in all_cases if str(case.get('split','')) == split]
    return {
        'schema':'smd-event-evaluation-v1','split':split,'matching_tolerance_hours':tolerance,
        'evaluation_version':EVALUATION_VERSION,'scoring_version':EVENT_MATCHING_VERSION,
        'summary':summarise(cases,tolerance),
        'confidence_intervals_satellite_cluster_bootstrap':satellite_cluster_bootstrap(cases,tolerance,samples=bootstrap_samples),
        'qualification':'False positives are counted only in verified-quiet intervals. Predictions outside documented event intervals in event-evidence cases are unscored rather than assumed false.'
    }


def main() -> None:
    parser=argparse.ArgumentParser(description='Evaluate event predictions with satellite-cluster confidence intervals.')
    parser.add_argument('results',type=Path); parser.add_argument('--split',default='primary-test'); parser.add_argument('--bootstrap-samples',type=int,default=2000); parser.add_argument('--output',type=Path)
    args=parser.parse_args(); document=json.loads(args.results.read_text()); report=evaluate_document(document,split=args.split,bootstrap_samples=args.bootstrap_samples)
    encoded=json.dumps(report,indent=2)+'\n'
    if args.output: args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(encoded)
    else: print(encoded,end='')

if __name__=='__main__': main()
