#!/usr/bin/env python3
from __future__ import annotations

import math
import unittest

from detector import CONTEXT, FEATURES, ConditionalNominalModel, SequentialRiskDetector
from evaluate import evaluate_document


def calibration_row(index: int) -> dict:
    context = {
        'log_gap_days': 0.1 + 0.002 * (index % 7),
        'log_semi_major_axis_km': 8.82 + 0.001 * (index % 5),
        'eccentricity': 0.001 + 0.00001 * (index % 3),
        'inclination_sin': 0.78 + 0.001 * (index % 4),
        'log_abs_bstar': 0.0001 + 0.00001 * (index % 6),
    }
    features = {}
    for feature_index, name in enumerate(FEATURES):
        features[name] = 0.02 * math.sin((index + 1) * (feature_index + 2) * 0.37)
    return {
        'index': index,
        'epoch_utc': f'2026-01-01T00:{index:02d}:00Z',
        'nominal': True,
        'quality_ok': True,
        'context': context,
        'features': features,
    }


def test_row(index: int, anomaly: bool = False) -> dict:
    row = calibration_row(index % 20)
    row = {
        **row,
        'index': index,
        'epoch_utc': f'2026-02-01T00:{index:02d}:00Z',
        'context': dict(row['context']),
        'features': dict(row['features']),
    }
    if anomaly:
        row['features']['along_rate'] = 3.0
        row['features']['a_rate'] = 2.0
        row['features']['mean_motion_rate'] = 1.5
    return row


class DetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = ConditionalNominalModel(k=15, min_neighbors=8, max_context_distance=10.0).fit(
            calibration_row(index) for index in range(36)
        )

    def test_quiet_sequence_has_no_candidate(self) -> None:
        detector = SequentialRiskDetector(self.model, alpha_event=0.1, betting_epsilon=0.5)
        decisions, events = detector.run(test_row(index, False) for index in range(12))
        self.assertEqual(events, [])
        self.assertTrue(all(item.status in {'nominal', 'statistical-alert'} for item in decisions))

    def test_persistent_physical_anomaly_creates_event(self) -> None:
        detector = SequentialRiskDetector(self.model, alpha_event=0.1, betting_epsilon=0.5, physics_z_gate=2.0)
        rows = [test_row(index, index >= 4) for index in range(12)]
        decisions, events = detector.run(rows)
        self.assertGreaterEqual(len(events), 1)
        self.assertIn('along-track', {mode for event in events for mode in event.physical_modes})
        self.assertTrue(any(item.status == 'candidate' for item in decisions))

    def test_out_of_support_context_abstains(self) -> None:
        detector = SequentialRiskDetector(self.model, alpha_event=0.1)
        row = test_row(0, False)
        row['context'] = {name: 100.0 for name in CONTEXT}
        decisions, events = detector.run([row])
        self.assertEqual(events, [])
        self.assertEqual(decisions[0].status, 'abstain')

    def test_quality_failure_abstains_before_model(self) -> None:
        detector = SequentialRiskDetector(self.model, alpha_event=0.1)
        row = test_row(0, True)
        row['quality_ok'] = False
        decisions, events = detector.run([row])
        self.assertEqual(events, [])
        self.assertEqual(decisions[0].status, 'abstain')
        self.assertIn('quality', decisions[0].reason)


class EvaluationTests(unittest.TestCase):
    def test_unknown_predictions_are_not_false_positives(self) -> None:
        document = {
            'matching_tolerance_hours': 1,
            'cases': [
                {
                    'case_id': 'event', 'object_id': '1', 'split': 'test', 'label_status': 'event-evidence',
                    'span_days': 10, 'abstained': False,
                    'truth_events': [{'start': '2026-01-02T00:00:00Z', 'end': '2026-01-02T01:00:00Z'}],
                    'predicted_events': [
                        {'start_utc': '2026-01-02T00:10:00Z', 'end_utc': '2026-01-02T00:20:00Z', 'strongest_utc': '2026-01-02T00:15:00Z'},
                        {'start_utc': '2026-01-06T00:00:00Z', 'end_utc': '2026-01-06T00:10:00Z', 'strongest_utc': '2026-01-06T00:05:00Z'},
                    ],
                },
                {
                    'case_id': 'quiet', 'object_id': '2', 'split': 'test', 'label_status': 'verified-quiet',
                    'span_days': 10, 'abstained': False, 'truth_events': [],
                    'predicted_events': [
                        {'start_utc': '2026-01-03T00:00:00Z', 'end_utc': '2026-01-03T00:10:00Z', 'strongest_utc': '2026-01-03T00:05:00Z'}
                    ],
                },
                {
                    'case_id': 'unknown', 'object_id': '3', 'split': 'test', 'label_status': 'unknown',
                    'span_days': 10, 'abstained': False, 'truth_events': [],
                    'predicted_events': [
                        {'start_utc': '2026-01-04T00:00:00Z', 'end_utc': '2026-01-04T00:10:00Z', 'strongest_utc': '2026-01-04T00:05:00Z'}
                    ],
                },
            ],
        }
        report = evaluate_document(document, split='test', bootstrap_samples=100)
        summary = report['summary']
        self.assertEqual(summary['true_positives'], 1)
        self.assertEqual(summary['false_positives_verified_quiet'], 1)
        self.assertEqual(summary['false_negatives'], 0)
        self.assertEqual(summary['unscored_predictions'], 2)
        self.assertAlmostEqual(summary['precision_scorable'], 0.5)
        self.assertAlmostEqual(summary['recall'], 1.0)


if __name__ == '__main__':
    unittest.main()
