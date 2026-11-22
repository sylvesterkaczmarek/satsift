#!/usr/bin/env python3
from __future__ import annotations

from research.comparison_v1.run_comparison import (
    METHOD_ORDER,
    calibrate_threshold,
    events_from_scores,
    match_event_dicts,
    ModelScoreMethod,
    summarize_results,
)


def row(index: int, day: int) -> dict:
    return {
        'index': index,
        'epoch_utc': f'2026-01-{day:02d}T00:00:00Z',
    }


def test_method_roster_is_predeclared_and_complete() -> None:
    assert len(METHOD_ORDER) == 16
    assert len(set(METHOD_ORDER)) == len(METHOD_ORDER)
    required = {
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
    }
    assert set(METHOD_ORDER) == required


def test_abstention_is_hard_event_boundary() -> None:
    rows = [row(0, 1), row(1, 2), row(2, 3), row(3, 4)]
    events = events_from_scores(rows, [6.0, None, 7.0, 8.0], threshold=5.0)
    assert len(events) == 2
    assert events[0]['start_index'] == events[0]['end_index'] == 0
    assert events[1]['start_index'] == 2
    assert events[1]['end_index'] == 3
    assert events[1]['strongest_index'] == 3


def test_frozen_event_matching_semantics() -> None:
    predicted = [{
        'start_utc': '2026-01-10T00:00:00Z',
        'end_utc': '2026-01-10T06:00:00Z',
        'strongest_utc': '2026-01-10T02:00:00Z',
    }]
    truth = [{'start': '2026-01-10T00:00:00Z', 'end': '2026-01-10T04:00:00Z'}]
    matched = match_event_dicts(predicted, truth, tolerance_hours=24.0)
    assert matched['tp'] == 1
    assert matched['fn'] == 0
    assert matched['matches'][0]['delay_hours'] == 0.0
    assert matched['matches'][0]['strongest_point_delay_hours'] == 2.0


def test_positive_unlabelled_precision_ignores_unmatched_event_history_predictions() -> None:
    cases = [
        {
            'case_id': 'event',
            'label_status': 'event-evidence',
            'coverage_fraction': 1.0,
            'span_days': 30.4375,
            'truth_events': [{'start': '2026-01-10T00:00:00Z', 'end': '2026-01-10T04:00:00Z'}],
            'predicted_events': [
                {
                    'start_utc': '2026-01-10T00:00:00Z',
                    'end_utc': '2026-01-10T01:00:00Z',
                    'strongest_utc': '2026-01-10T00:30:00Z',
                },
                {
                    'start_utc': '2026-01-20T00:00:00Z',
                    'end_utc': '2026-01-20T01:00:00Z',
                    'strongest_utc': '2026-01-20T00:30:00Z',
                },
            ],
        },
        {
            'case_id': 'quiet',
            'label_status': 'verified-quiet',
            'coverage_fraction': 1.0,
            'span_days': 30.4375,
            'truth_events': [],
            'predicted_events': [{
                'start_utc': '2026-01-05T00:00:00Z',
                'end_utc': '2026-01-05T01:00:00Z',
                'strongest_utc': '2026-01-05T00:30:00Z',
            }],
        },
    ]
    summary = summarize_results(cases)
    assert summary['true_positives'] == 1
    assert summary['false_positives'] == 1
    assert summary['false_negatives'] == 0
    assert summary['precision'] == 0.5
    assert summary['recall'] == 1.0
    assert summary['false_events_per_object_month'] == 1.0


def test_calibration_stops_at_first_budget_violation() -> None:
    cases = {'quiet': {'span_days': 30.4375}}
    rows_by_case = {'quiet': [row(index, index + 1) for index in range(6)]}
    # At threshold 10 there are two separated false events, violating a one-event/month budget.
    # At threshold 0 they would merge into one event. Calibration must not exploit that merger.
    scores = {'quiet': [10.0, 0.0, 0.0, 10.0, 0.0, 0.0]}
    result = calibrate_threshold(cases, rows_by_case, scores, ['quiet'], budget=1.0)
    assert result['selected_threshold'] > 10.0
    assert result['false_events'] == 0
    assert result['evaluated_until_first_violation'] == 2


def test_zero_recall_has_zero_f1_even_without_predictions() -> None:
    summary = summarize_results([{
        'case_id': 'event',
        'label_status': 'event-evidence',
        'coverage_fraction': 1.0,
        'span_days': 30.4375,
        'truth_events': [{'start': '2026-01-10T00:00:00Z', 'end': '2026-01-10T04:00:00Z'}],
        'predicted_events': [],
    }])
    assert summary['precision'] is None
    assert summary['recall'] == 0.0
    assert summary['f1'] == 0.0


class _Prediction:
    def __init__(self, surprise: float):
        self.surprise = surprise


class _RecordingModel:
    name = 'recording'
    parameter_count = 0

    def __init__(self):
        self.calls = []

    def predict_sequence(self, rows):
        self.calls.append([int(row['index']) for row in rows])
        return [_Prediction(float(index + 1)) for index, _row in enumerate(rows)]


def test_sequence_models_reset_at_quality_abstention() -> None:
    model = _RecordingModel()
    method = ModelScoreMethod(model)
    rows = [
        {'index': 0, 'quality_ok': True},
        {'index': 1, 'quality_ok': False},
        {'index': 2, 'quality_ok': True},
        {'index': 3, 'quality_ok': True},
    ]
    scores = method.score_sequence(rows)
    assert model.calls == [[0], [2, 3]]
    assert scores == [1.0, None, 1.0, 2.0]


def main() -> None:
    tests = [
        test_method_roster_is_predeclared_and_complete,
        test_abstention_is_hard_event_boundary,
        test_frozen_event_matching_semantics,
        test_positive_unlabelled_precision_ignores_unmatched_event_history_predictions,
        test_calibration_stops_at_first_budget_violation,
        test_zero_recall_has_zero_f1_even_without_predictions,
        test_sequence_models_reset_at_quality_abstention,
    ]
    for test in tests:
        test()
        print(f'PASS {test.__name__}')
    print(f'{len(tests)}/{len(tests)} comparison-v1 tests passed.')


if __name__ == '__main__':
    main()
