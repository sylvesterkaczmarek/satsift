#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
    text = str(value).replace('Z', '+00:00')
    return datetime.fromisoformat(text).timestamp()


def match_events(predicted: list[dict], truth: list[dict], tolerance_hours: float) -> dict:
    pairs = match_event_intervals(
        [(
            parse_time_us(prediction['start_utc'], default_timezone=None),
            parse_time_us(prediction['end_utc'], default_timezone=None),
            parse_time_us(prediction['strongest_utc'], default_timezone=None),
        ) for prediction in predicted],
        parse_truth_events_us(truth),
        tolerance_hours_to_us(tolerance_hours),
    )
    matches = [{key: pair[key] for key in ('prediction_index', 'truth_index', 'delay_hours', 'strongest_point_delay_hours')} for pair in pairs]
    return {
        'matches': matches,
        'tp': len(matches),
        'fp': len(predicted) - len(matches),
        'fn': len(truth) - len(matches),
    }


def summarize(cases: list[dict], tolerance_hours: float) -> dict:
    tp = fp = fn = 0
    object_months = 0.0
    delays: list[float] = []
    scored_negative_cases = 0
    scored_positive_cases = 0
    abstained = 0
    for case in cases:
        if case.get('abstained'):
            abstained += 1
        label = case.get('label_status')
        predicted = case.get('predicted_events') or []
        truth = validated_truth_events(case)
        if label == 'event-evidence':
            scored_positive_cases += 1
            match = match_events(predicted, truth, tolerance_hours)
            tp += match['tp']
            fn += match['fn']
            delays.extend(item['delay_hours'] for item in match['matches'])
        elif label == 'verified-quiet':
            scored_negative_cases += 1
            fp += len(predicted)
            span = float(case.get('span_days') or 0)
            if span > 0:
                object_months += span / 30.4375
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {
        'cases': len(cases),
        'positive_cases': scored_positive_cases,
        'verified_quiet_cases': scored_negative_cases,
        'abstained_cases': abstained,
        'true_positives': tp,
        'false_positives': fp,
        'false_negatives': fn,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'object_months_of_verified_quiet': object_months,
        'false_events_per_object_month': fp / object_months if object_months > 0 else None,
        'median_detection_delay_hours': statistics.median(delays) if delays else None,
    }


def bootstrap(cases: list[dict], tolerance: float, iterations: int = 2000, seed: int = 3404) -> dict:
    if not cases:
        return {}
    rng = random.Random(seed)
    fields = ['precision', 'recall', 'f1', 'false_events_per_object_month', 'median_detection_delay_hours']
    samples: dict[str, list[float]] = {field: [] for field in fields}
    for _ in range(iterations):
        drawn = [rng.choice(cases) for _ in cases]
        summary = summarize(drawn, tolerance)
        for field in fields:
            value = summary.get(field)
            if isinstance(value, (int, float)) and math.isfinite(value):
                samples[field].append(float(value))

    def percentile(values: list[float], q: float) -> float | None:
        if not values:
            return None
        values = sorted(values)
        index = (len(values) - 1) * q
        lo, hi = math.floor(index), math.ceil(index)
        if lo == hi:
            return values[lo]
        return values[lo] * (hi - index) + values[hi] * (index - lo)

    return {
        field: {
            'low_95': percentile(values, 0.025),
            'high_95': percentile(values, 0.975),
            'bootstrap_samples': len(values),
        }
        for field, values in samples.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', default='benchmark-results/baseline-v0.4-on-v0.3.json')
    parser.add_argument('--output', default='benchmark-results/baseline-v0.4-on-v0.3-evaluation-case-statistics-v3.json')
    args = parser.parse_args()
    result = json.loads(Path(args.results).read_text())
    tolerance = float(result.get('matching_tolerance_hours', 24))
    cases = result.get('cases') or []
    splits = sorted({str(case.get('split') or 'unspecified') for case in cases})
    report = {
        'schema': 'smd-publication-benchmark-evaluation-v1',
        'evaluation_version': EVALUATION_VERSION,
        'scoring_version': EVENT_MATCHING_VERSION,
        'detector_method': result.get('detector_method'),
        'benchmark_version': result.get('benchmark_version'),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'matching_tolerance_hours': tolerance,
        'by_split': {},
    }
    for split in splits:
        split_cases = [case for case in cases if str(case.get('split') or 'unspecified') == split]
        report['by_split'][split] = {
            'summary': summarize(split_cases, tolerance),
            'bootstrap_95_ci': bootstrap(split_cases, tolerance),
        }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
