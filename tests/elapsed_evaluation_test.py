#!/usr/bin/env python3
"""Independent synthetic integration checks for retrospective elapsed evaluation."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from research.elapsed_evaluator import evaluate_document

ROOT = Path(__file__).resolve().parents[1]
HOUR = 3_600_000_000
MONTH = 2_629_800_000_000
ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)
POLICY = {'version': 'elapsed-intervals-v1', 'max_gap_seconds': 7200}
RATE = 'false_events_per_object_month'


def stamp(microseconds: int) -> str:
    return (ORIGIN + timedelta(microseconds=microseconds)).isoformat(
        timespec='microseconds').replace('+00:00', 'Z')


def event(at: int, *, start: int | None = None, end: int | None = None) -> dict:
    return {
        'start_utc': stamp(at if start is None else start),
        'end_utc': stamp(at if end is None else end),
        'strongest_utc': stamp(at),
    }


def ledger(pairs, *, start: int = 0, end: int = 2 * HOUR) -> dict:
    return {
        'window_start_utc': stamp(start),
        'window_end_utc': stamp(end),
        'intervals': [
            {'start_utc': stamp(left), 'end_utc': stamp(right), 'supported': supported}
            for left, right, supported in pairs
        ],
    }


def quiet(case_id: str = 'quiet', object_id: str = '1', *,
          start: int = 0, end: int = 2 * HOUR, predicted=None,
          pairs=None, split: str = 'test') -> dict:
    return {
        'case_id': case_id,
        'object_id': object_id,
        'split': split,
        'label_status': 'verified-quiet',
        'truth_events': [],
        'predicted_events': [] if predicted is None else predicted,
        'exposure_evidence': ledger(
            [(start, end, True)] if pairs is None else pairs, start=start, end=end),
    }


def document(cases) -> dict:
    return {'exposure_policy': copy.deepcopy(POLICY), 'matching_tolerance_hours': 0, 'cases': cases}


def evaluate(cases, *, samples: int = 40) -> dict:
    return evaluate_document(document(cases), bootstrap_samples=samples, seed=3404)


class ElapsedEvaluationTests(unittest.TestCase):
    def test_version_scope_policy_and_input_identity_are_explicit(self) -> None:
        payload = document([quiet()])
        report = evaluate_document(payload, bootstrap_samples=5, seed=17)
        self.assertEqual(report['evaluation_version'], 'case-statistics-v5')
        self.assertEqual(report['scoring_version'], 'event-matching-v3')
        self.assertEqual(report['analysis_scope'], 'retrospective')
        self.assertEqual(report['exposure_policy'], POLICY)
        self.assertRegex(report['input_sha256'], r'^[a-f0-9]{64}$')
        self.assertIn('canonical', report['input_digest_representation'])
        repeated = evaluate_document(copy.deepcopy(payload), bootstrap_samples=5, seed=17)
        self.assertEqual(report, repeated)
        payload['exposure_policy']['max_gap_seconds'] = 3600
        changed = evaluate_document(payload, bootstrap_samples=5, seed=17)
        self.assertNotEqual(report['input_sha256'], changed['input_sha256'])
        self.assertNotIn('input_path', report)

    def test_irregular_quiet_coverage_uses_elapsed_intervals(self) -> None:
        case = quiet(end=10 * HOUR, predicted=[event(HOUR)], pairs=[
            (0, HOUR, True), (HOUR, 9 * HOUR, True), (9 * HOUR, 10 * HOUR, True),
        ])
        case.update(span_days=3000, coverage_fraction=1.0, abstention_fraction=0.0)
        report = evaluate([case])
        summary = report['summary']
        self.assertEqual(summary['false_positives'], 1)
        self.assertAlmostEqual(summary['covered_verified_quiet_object_months'], 2 * HOUR / MONTH)
        self.assertAlmostEqual(summary[RATE], MONTH / (2 * HOUR))
        self.assertEqual(summary['false_event_rate_status'], 'available')
        self.assertEqual(report['case_results'][0]['exposure']['covered_microseconds'], 2 * HOUR)

    def test_duration_weighted_coverage_keeps_abstention_and_missing_time_separate(self) -> None:
        first = quiet('first', '1', end=10 * HOUR, pairs=[
            (0, 2 * HOUR, True), (2 * HOUR, 4 * HOUR, False),
        ])
        second = quiet('second', '2', end=HOUR)
        summary = evaluate([first, second])['summary']
        self.assertAlmostEqual(summary['covered_fraction'], 3 / 11)
        self.assertAlmostEqual(summary['elapsed_abstention_fraction'], 2 / 5)
        self.assertAlmostEqual(summary['uncovered_window_fraction'], 8 / 11)
        self.assertAlmostEqual(summary['known_covered_verified_quiet_object_months'], 3 * HOUR / MONTH)

    def test_legacy_fields_do_not_create_elapsed_exposure(self) -> None:
        case = quiet(predicted=[event(HOUR)])
        del case['exposure_evidence']
        case.update(span_days=30.4375, coverage_fraction=1.0, abstained=False)
        summary = evaluate([case])['summary']
        self.assertEqual(summary['false_positives'], 1)
        self.assertIsNone(summary['covered_verified_quiet_object_months'])
        self.assertIsNone(summary[RATE])
        self.assertEqual(summary['false_event_rate_status'], 'missing-exposure')
        self.assertEqual(summary['incomplete_verified_quiet_cases'], 1)
        self.assertIsNone(summary['zero_event_poisson_bound']['upper_events_per_object_month'])

    def test_missing_common_policy_cannot_be_inferred(self) -> None:
        payload = document([quiet()])
        del payload['exposure_policy']
        report = evaluate_document(payload, bootstrap_samples=5)
        self.assertIsNone(report['exposure_policy'])
        self.assertIsNone(report['summary'][RATE])
        self.assertEqual(report['summary']['false_event_rate_status'], 'missing-exposure')

    def test_mixed_known_and_unknown_exposure_does_not_publish_a_partial_denominator(self) -> None:
        known = quiet('known', '1', predicted=[event(HOUR)])
        unknown = quiet('unknown', '2', predicted=[event(HOUR)])
        del unknown['exposure_evidence']
        summary = evaluate([known, unknown])['summary']
        self.assertEqual(summary['false_positives'], 2)
        self.assertAlmostEqual(summary['known_covered_verified_quiet_object_months'], 2 * HOUR / MONTH)
        self.assertIsNone(summary['covered_verified_quiet_object_months'])
        self.assertIsNone(summary[RATE])
        self.assertEqual(summary['incomplete_verified_quiet_cases'], 1)
        self.assertEqual(summary['false_event_rate_status'], 'missing-exposure')

    def test_known_zero_exposure_is_distinct_from_missing_exposure(self) -> None:
        summary = evaluate([quiet(pairs=[])])['summary']
        self.assertEqual(summary['covered_verified_quiet_object_months'], 0)
        self.assertEqual(summary['known_covered_verified_quiet_object_months'], 0)
        self.assertEqual(summary['incomplete_verified_quiet_cases'], 0)
        self.assertEqual(summary['false_event_rate_status'], 'zero-exposure')
        self.assertIsNone(summary[RATE])
        self.assertEqual(summary['zero_event_poisson_bound']['status'], 'zero_exposure')
        self.assertIsNone(summary['zero_event_poisson_bound']['upper_events_per_object_month'])

    def test_candidate_support_uses_right_closed_observation_membership(self) -> None:
        accepted = quiet(predicted=[event(2 * HOUR)])
        self.assertEqual(evaluate([accepted])['summary']['false_event_rate_status'], 'available')
        for candidate in (
            event(0), event(2 * HOUR + 1),
            event(HOUR, start=0), event(HOUR, end=2 * HOUR + 1),
        ):
            with self.subTest(candidate=candidate):
                summary = evaluate([quiet(predicted=[candidate])])['summary']
                self.assertEqual(summary['false_positives'], 1)
                self.assertEqual(summary['false_event_rate_status'], 'inconsistent-event-support')
                self.assertIsNone(summary[RATE])
                self.assertIsNone(summary['zero_event_poisson_bound']['upper_events_per_object_month'])

    def test_candidates_in_abstained_or_unobserved_time_remain_visible(self) -> None:
        case = quiet(end=4 * HOUR, predicted=[event(2 * HOUR), event(3 * HOUR)], pairs=[
            (0, HOUR, True), (HOUR, 2 * HOUR, False),
        ])
        summary = evaluate([case])['summary']
        self.assertEqual(summary['false_positives'], 2)
        self.assertEqual(summary['false_event_rate_status'], 'inconsistent-event-support')
        self.assertIsNone(summary[RATE])
        zero = quiet(predicted=[event(HOUR)], pairs=[])
        self.assertIsNone(evaluate([zero])['summary'][RATE])

    def test_claimed_whole_case_abstention_cannot_hide_supported_time(self) -> None:
        case = quiet()
        case['abstained'] = True
        with self.assertRaises(ValueError):
            evaluate([case])
        case['exposure_evidence']['intervals'][0]['supported'] = False
        summary = evaluate([case])['summary']
        self.assertEqual(summary['covered_verified_quiet_object_months'], 0)

    def test_positive_unlabelled_event_counts_and_onset_delays_are_preserved(self) -> None:
        positive = quiet('positive', '1', end=10 * HOUR, pairs=[(0, 2 * HOUR, True)])
        positive['label_status'] = 'event-evidence'
        positive['truth_events'] = [{'start': stamp(HOUR), 'end': stamp(2 * HOUR)}]
        positive['predicted_events'] = [
            event(2 * HOUR, start=HOUR), event(8 * HOUR),
        ]
        negative = quiet('negative', '2', predicted=[event(HOUR)])
        summary = evaluate([positive, negative])['summary']
        self.assertEqual(summary['true_positives'], 1)
        self.assertEqual(summary['false_positives'], 1)
        self.assertEqual(summary['false_negatives'], 0)
        self.assertEqual(summary['precision'], 0.5)
        self.assertEqual(summary['recall'], 1.0)
        self.assertEqual(summary['median_detection_delay_hours'], 0.0)

    def test_unselected_and_quiet_truth_is_validated_before_split_filtering(self) -> None:
        for label in ('verified-quiet', 'event-evidence', 'unknown'):
            invalid = quiet('unselected', '2', split='held-out')
            invalid['label_status'] = label
            invalid['truth_events'] = [{'start': '2026-01-01T00:00:00'}]
            payload = document([quiet(split='test'), invalid])
            with self.subTest(label=label), self.assertRaises((TypeError, ValueError)):
                evaluate_document(payload, split='test', bootstrap_samples=0)

    def test_unselected_predictions_and_evidence_are_also_validated(self) -> None:
        for mutation in ('missing-predictions', 'null-predictions', 'bad-time', 'bad-evidence'):
            invalid = quiet('unselected', '2', split='held-out')
            if mutation == 'missing-predictions':
                del invalid['predicted_events']
            elif mutation == 'null-predictions':
                invalid['predicted_events'] = None
            elif mutation == 'bad-time':
                invalid['predicted_events'] = [event(HOUR)]
                invalid['predicted_events'][0]['strongest_utc'] = '2026-02-30T00:00:00Z'
            else:
                invalid['exposure_evidence']['intervals'][0]['supported'] = 'yes'
            with self.subTest(mutation=mutation), self.assertRaises((TypeError, ValueError)):
                evaluate_document(document([quiet(), invalid]), split='test', bootstrap_samples=0)

    def test_duplicate_cases_and_same_object_overlapping_windows_are_rejected(self) -> None:
        original = quiet()
        for other in (
            copy.deepcopy(original),
            quiet('other', '1', start=HOUR, end=3 * HOUR),
            quiet('other', '1', start=0, end=HOUR),
        ):
            with self.subTest(other=other), self.assertRaises(ValueError):
                evaluate([original, other])
        adjacent = quiet('adjacent', '1', start=2 * HOUR, end=3 * HOUR)
        summary = evaluate([original, adjacent])['summary']
        self.assertAlmostEqual(summary['covered_verified_quiet_object_months'], 3 * HOUR / MONTH)
        distinct = quiet('distinct', '2')
        self.assertAlmostEqual(evaluate([original, distinct])['summary']['covered_verified_quiet_object_months'], 4 * HOUR / MONTH)

    def test_missing_object_identity_retains_counts_without_inventing_clusters(self) -> None:
        missing = quiet('missing', predicted=[event(HOUR)])
        del missing['object_id']
        report = evaluate([missing, quiet('known', '2')])
        self.assertEqual(report['summary']['false_positives'], 1)
        self.assertEqual(report['summary']['false_event_rate_status'], 'missing-object-identity')
        self.assertIsNone(report['summary'][RATE])
        for metric in ('covered_fraction', 'elapsed_abstention_fraction', 'uncovered_window_fraction'):
            self.assertIsNone(report['summary'][metric])
        self.assertEqual(report['summary']['exposure']['status'], 'missing-object-identity')
        self.assertEqual(report['summary']['exposure']['missing_object_id_cases'], 1)
        interval_result = report['confidence_intervals'][RATE]
        self.assertEqual(interval_result['defined_replicates'], 0)
        self.assertIsNone(interval_result['low_95'])
        self.assertIsNone(interval_result['high_95'])

    def test_all_zero_quiet_observations_have_no_zero_width_inferential_limit(self) -> None:
        report = evaluate([quiet('q1', '1'), quiet('q2', '2')], samples=80)
        summary = report['summary']
        self.assertEqual(summary[RATE], 0.0)
        ci = report['confidence_intervals'][RATE]
        self.assertEqual(ci['status'], 'zero-event-degenerate')
        self.assertIsNone(ci['low_95'])
        self.assertIsNone(ci['high_95'])
        self.assertEqual(ci['empirical_percentiles'], {'low_95': 0.0, 'high_95': 0.0})
        self.assertEqual(ci['requested_replicates'], 80)
        self.assertEqual(ci['defined_replicates'], 80)
        self.assertEqual(ci['independent_objects'], 2)
        bound = summary['zero_event_poisson_bound']
        self.assertEqual(bound['status'], 'conditional_model_bound')
        self.assertGreater(bound['upper_events_per_object_month'], 0)
        self.assertAlmostEqual(bound['upper_events_per_object_month'] * (4 * HOUR / MONTH), -math.log(0.05))
        self.assertIs(bound['assumptions_verified'], False)
        self.assertTrue(bound['assumptions'])

    def test_extra_event_objects_do_not_create_quiet_independent_exposure(self) -> None:
        cases = [quiet('q1', '1')]
        for index in range(2, 6):
            positive = quiet('positive-' + str(index), str(index))
            positive['label_status'] = 'event-evidence'
            positive['truth_events'] = [{'start': stamp(HOUR)}]
            cases.append(positive)
        ci = evaluate(cases)['confidence_intervals'][RATE]
        self.assertEqual(ci['independent_objects'], 1)
        self.assertEqual(ci['status'], 'insufficient-clusters')
        self.assertIsNone(ci['low_95'])
        self.assertIsNone(ci['high_95'])

    def test_bootstrap_resamples_complete_object_clusters_with_multiplicity(self) -> None:
        cases = [
            quiet('a-first', 'A', end=HOUR, predicted=[event(HOUR)]),
            quiet('a-second', 'A', start=HOUR, end=2 * HOUR, predicted=[event(2 * HOUR)]),
            quiet('b', 'B'), quiet('c', 'C'),
        ]

        class ScriptedRandom:
            def __init__(self):
                self.calls = 0

            def choice(self, options):
                if len(options) != 3:
                    raise AssertionError('Resampling unit must be three objects, not four cases')
                index = (0, 0, 1)[self.calls % 3]
                self.calls += 1
                return options[index]

        scripted = ScriptedRandom()
        with patch('research.elapsed_evaluator.random.Random', return_value=scripted):
            report = evaluate(cases, samples=7)
        ci = report['confidence_intervals'][RATE]
        expected = 4 / (6 * HOUR / MONTH)
        self.assertAlmostEqual(ci['empirical_percentiles']['low_95'], expected)
        self.assertAlmostEqual(ci['empirical_percentiles']['high_95'], expected)
        self.assertEqual(ci['defined_replicates'], 7)
        self.assertEqual(ci['independent_objects'], 3)
        self.assertEqual(scripted.calls, 21)

    def test_multimethod_inputs_share_source_schedules_but_can_differ_in_support(self) -> None:
        first = quiet()
        second = copy.deepcopy(first)
        second['exposure_evidence']['intervals'][0]['supported'] = False
        payload = {'exposure_policy': POLICY, 'methods': [
            {'method': 'first', 'cases': [first]}, {'method': 'second', 'cases': [second]},
        ]}
        report = evaluate_document(payload, bootstrap_samples=5)
        by_method = {entry['method']: entry for entry in report['methods']}
        self.assertGreater(by_method['first']['summary']['covered_verified_quiet_object_months'], 0)
        self.assertEqual(by_method['second']['summary']['covered_verified_quiet_object_months'], 0)
        for mutate in ('window', 'object', 'label', 'truth', 'schedule', 'case-id'):
            altered = copy.deepcopy(payload)
            case = altered['methods'][1]['cases'][0]
            if mutate == 'window':
                case['exposure_evidence']['window_end_utc'] = stamp(3 * HOUR)
            elif mutate == 'object':
                case['object_id'] = 'different'
            elif mutate == 'label':
                case['label_status'] = 'unknown'
            elif mutate == 'truth':
                case['truth_events'] = [{'start': stamp(HOUR)}]
            elif mutate == 'case-id':
                case['case_id'] = 'different'
            else:
                case['exposure_evidence']['intervals'] = [
                    {'start_utc': stamp(0), 'end_utc': stamp(HOUR), 'supported': False},
                    {'start_utc': stamp(HOUR), 'end_utc': stamp(2 * HOUR), 'supported': False},
                ]
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                evaluate_document(altered, bootstrap_samples=0)

    def test_missing_method_support_is_explicit_and_cannot_imply_comparability(self) -> None:
        first, second = quiet(), quiet()
        del second['exposure_evidence']
        payload = {'exposure_policy': POLICY, 'methods': [
            {'method': 'known', 'cases': [first]}, {'method': 'missing', 'cases': [second]},
        ]}
        report = evaluate_document(payload, bootstrap_samples=5)
        self.assertIsNone(report['methods'][1]['summary'][RATE])
        self.assertRegex(json.dumps(report['comparability']).lower(), r'incomplete|missing|unavailable')

    def test_missing_first_method_does_not_hide_later_known_disagreement(self) -> None:
        missing = quiet()
        del missing['exposure_evidence']
        known = quiet()
        for change in ('window', 'schedule'):
            other = quiet()
            if change == 'window':
                other['exposure_evidence']['window_end_utc'] = stamp(3 * HOUR)
            else:
                other['exposure_evidence']['intervals'] = [
                    {'start_utc': stamp(0), 'end_utc': stamp(HOUR), 'supported': True},
                    {'start_utc': stamp(HOUR), 'end_utc': stamp(2 * HOUR), 'supported': True},
                ]
            payload = {'exposure_policy': POLICY, 'methods': [
                {'method': 'missing', 'cases': [missing]},
                {'method': 'known', 'cases': [known]},
                {'method': 'other', 'cases': [other]},
            ]}
            with self.subTest(change=change), self.assertRaises(ValueError):
                evaluate_document(payload, bootstrap_samples=0)

    def test_zero_exposure_objects_do_not_inflate_quiet_cluster_count(self) -> None:
        report = evaluate([
            quiet('supported', '1', predicted=[event(HOUR)]),
            quiet('empty', '2', pairs=[]),
        ])
        ci = report['confidence_intervals'][RATE]
        self.assertEqual(ci['independent_objects'], 1)
        self.assertEqual(ci['status'], 'insufficient-clusters')
        self.assertIsNone(ci['low_95'])
        self.assertIsNone(ci['high_95'])

    def test_undefined_bootstrap_draws_are_counted_and_conditioning_is_disclosed(self) -> None:
        cases = [quiet('q1', '1', predicted=[event(HOUR)]), quiet('q2', '2')]
        for number in range(3, 8):
            positive = quiet('p' + str(number), str(number))
            positive['label_status'] = 'event-evidence'
            positive['truth_events'] = [{'start': stamp(HOUR)}]
            cases.append(positive)
        ci = evaluate(cases, samples=200)['confidence_intervals'][RATE]
        self.assertEqual(ci['requested_replicates'], 200)
        self.assertGreater(ci['defined_replicates'], 0)
        self.assertLess(ci['defined_replicates'], 200)
        self.assertEqual(ci['excluded_replicates'], 200 - ci['defined_replicates'])
        self.assertRegex(' '.join(ci['limitations']).lower(), r'condition|undefined')
        self.assertEqual(ci['independent_objects'], 2)

    def test_case_and_method_policy_overrides_are_rejected(self) -> None:
        case = quiet()
        case['exposure_policy'] = {'version': 'elapsed-intervals-v1', 'max_gap_seconds': 1}
        with self.assertRaises(ValueError):
            evaluate([case])
        payload = {'exposure_policy': POLICY, 'methods': [{
            'method': 'override', 'cases': [quiet()],
            'exposure_policy': {'version': 'elapsed-intervals-v1', 'max_gap_seconds': 1},
        }]}
        with self.assertRaises(ValueError):
            evaluate_document(payload, bootstrap_samples=0)

    def test_invalid_label_and_truth_combinations_are_rejected(self) -> None:
        for label, events in (
            ('verified-quiet', [{'start': stamp(HOUR)}]),
            ('unknown', [{'start': stamp(HOUR)}]),
            ('event-evidence', []),
            ('fully-labelled', [{'start': stamp(HOUR)}]),
            ('arbitrary-status', []),
        ):
            with self.subTest(label=label, events=events):
                case = quiet()
                case['label_status'] = label
                case['truth_events'] = events
                with self.assertRaises(ValueError):
                    evaluate([case], samples=0)
        legitimate = quiet()
        legitimate['label_status'] = 'event-evidence'
        legitimate['truth_events'] = [{'start': stamp(HOUR)}]
        self.assertEqual(evaluate([legitimate], samples=0)['summary']['false_negatives'], 1)

    def test_invalid_labels_in_unselected_splits_or_methods_are_rejected(self) -> None:
        invalid = quiet('bad', 'bad-object', split='development')
        invalid['label_status'] = 'verified-quiet'
        invalid['truth_events'] = [{'start': stamp(HOUR)}]
        payload = document([quiet('test', 'ok-object'), invalid])
        with self.assertRaises(ValueError):
            evaluate_document(payload, split='test', bootstrap_samples=0)
        second = quiet('bad', 'bad-object')
        second['truth_events'] = [{'start': stamp(HOUR)}]
        payload = {'exposure_policy': POLICY, 'methods': [
            {'method': 'first', 'cases': [quiet('test', 'ok-object')]},
            {'method': 'second', 'cases': [second]},
        ]}
        with self.assertRaises(ValueError):
            evaluate_document(payload, bootstrap_samples=0)

    def test_metric_cluster_counts_require_a_numerator_or_denominator_contribution(self) -> None:
        positive = quiet('matched', 'B', predicted=[event(HOUR)])
        positive['label_status'] = 'event-evidence'
        positive['truth_events'] = [{'start': stamp(HOUR)}]
        missed = quiet('missed', 'C')
        missed['label_status'] = 'event-evidence'
        missed['truth_events'] = [{'start': stamp(HOUR)}]
        empty_positive = quiet('empty-positive', 'D')
        empty_positive['label_status'] = 'unknown'
        report = evaluate([
            quiet('false-event', 'A', predicted=[event(HOUR)]),
            positive, missed, empty_positive, quiet('empty-quiet', 'E'),
        ])
        self.assertEqual(report['confidence_intervals']['precision']['independent_objects'], 2)
        self.assertEqual(report['confidence_intervals']['f1']['independent_objects'], 3)
        self.assertEqual(report['confidence_intervals']['recall']['independent_objects'], 2)

    def test_elapsed_abstention_clusters_require_positive_eligible_time(self) -> None:
        report = evaluate([
            quiet('observed', '1', pairs=[(0, HOUR, True), (HOUR, 2 * HOUR, False)]),
            quiet('unobserved', '2', pairs=[]),
        ])
        ci = report['confidence_intervals']['elapsed_abstention_fraction']
        self.assertEqual(ci['independent_objects'], 1)
        self.assertEqual(ci['status'], 'insufficient-clusters')
        self.assertIsNone(ci['low_95'])
        self.assertIsNone(ci['high_95'])

    def test_inconsistent_candidate_support_cannot_add_a_valid_quiet_cluster(self) -> None:
        report = evaluate([
            quiet('consistent', '1', predicted=[event(HOUR)]),
            quiet('inconsistent', '2', predicted=[event(0)]),
        ])
        ci = report['confidence_intervals'][RATE]
        self.assertEqual(ci['independent_objects'], 1)
        self.assertEqual(ci['status'], 'inconsistent-event-support')

    def test_unavailable_quiet_data_is_not_a_zero_event_observation(self) -> None:
        missing = quiet()
        del missing['exposure_evidence']
        unknown = quiet()
        unknown['label_status'] = 'unknown'
        unidentified = quiet()
        del unidentified['object_id']
        for case in (missing, unknown, unidentified, quiet(pairs=[])):
            with self.subTest(case=case):
                ci = evaluate([case])['confidence_intervals'][RATE]
                self.assertIs(ci['zero_event_degenerate'], False)
                self.assertIsNone(ci['low_95'])
                self.assertIsNone(ci['high_95'])
        available = evaluate([quiet('q1', '1'), quiet('q2', '2')])
        self.assertIs(available['confidence_intervals'][RATE]['zero_event_degenerate'], True)

    def test_strongest_epoch_must_lie_inside_each_prediction_even_when_unselected(self) -> None:
        for label in ('verified-quiet', 'event-evidence', 'unknown'):
            for split in ('test', 'unselected'):
                for strongest in (HOUR - 1, 2 * HOUR + 1):
                    invalid = quiet('invalid', '2', split=split)
                    invalid['label_status'] = label
                    invalid['predicted_events'] = [event(strongest, start=HOUR, end=2 * HOUR)]
                    with self.subTest(label=label, split=split, strongest=strongest), self.assertRaises(ValueError):
                        evaluate_document(document([quiet(), invalid]), split='test', bootstrap_samples=0)
        for strongest in (HOUR, 2 * HOUR):
            report = evaluate([quiet(predicted=[event(strongest, start=HOUR, end=2 * HOUR)])])
            self.assertEqual(report['summary']['false_event_rate_status'], 'available')

    def test_bootstrap_options_are_bounded_and_strictly_typed(self) -> None:
        for samples in (-1, True, 1.5, '5', 10001):
            with self.subTest(samples=samples), self.assertRaises((TypeError, ValueError)):
                evaluate_document(document([quiet()]), bootstrap_samples=samples)
        for seed in (-1, True, 1.5, '5', 2 ** 64):
            with self.subTest(seed=seed), self.assertRaises((TypeError, ValueError)):
                evaluate_document(document([quiet()]), bootstrap_samples=0, seed=seed)


class ElapsedCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix='smd-elapsed-cli-')
        self.addCleanup(self.temporary.cleanup)
        self.snapshot = Path(self.temporary.name) / 'source'
        for relative in (
            'tools/evaluate_elapsed_benchmark.py',
            'research/elapsed_evaluator.py', 'research/elapsed_exposure.py',
            'research/event_matching.py',
        ):
            target = self.snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.input = self.snapshot / 'synthetic-input.json'
        self.input.write_text(json.dumps(document([quiet('q1', '1'), quiet('q2', '2')]), indent=2) + '\n')
        self.environment = dict(os.environ, PYTHONPATH=str(self.snapshot), PYTHONDONTWRITEBYTECODE='1')

    def run_cli(self, destination=None, *, source=None, extra=()):
        command = [sys.executable, '-B', '-S', str(self.snapshot / 'tools/evaluate_elapsed_benchmark.py'),
                   str(self.input if source is None else source)]
        if destination is not None:
            command.extend(['--output', str(destination)])
        command.extend(['--bootstrap-samples', '7', '--seed', '3404', *extra])
        return subprocess.run(command, cwd=self.snapshot, env=self.environment,
                              capture_output=True, text=True, timeout=30)

    def test_cli_creates_a_fresh_retrospective_report_without_local_paths(self) -> None:
        output = self.snapshot / 'reports' / 'elapsed.json'
        result = self.run_cli(output)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(output.read_text())
        self.assertEqual(report['analysis_scope'], 'retrospective')
        self.assertEqual(report['evaluation_version'], 'case-statistics-v5')
        self.assertEqual(report['scoring_version'], 'event-matching-v3')
        self.assertEqual(report['input_file_sha256'], hashlib.sha256(self.input.read_bytes()).hexdigest())
        self.assertEqual(report['input_file_digest_representation'], 'raw-bytes')
        self.assertIn('canonical', report['input_digest_representation'])
        self.assertNotIn(str(self.snapshot), output.read_text())
        self.assertNotIn(self.input.name, output.read_text())

    def test_cli_requires_output_and_refuses_existing_output_or_input_overwrite(self) -> None:
        before = self.input.read_bytes()
        missing = self.run_cli()
        self.assertNotEqual(missing.returncode, 0)
        existing = self.snapshot / 'existing.json'
        existing.write_bytes(b'preserve existing output\n')
        result = self.run_cli(existing)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(existing.read_bytes(), b'preserve existing output\n')
        same = self.run_cli(self.input)
        self.assertNotEqual(same.returncode, 0)
        self.assertEqual(self.input.read_bytes(), before)

    def test_cli_refuses_final_symlinks_and_resolves_allowed_parent_aliases(self) -> None:
        sentinel = self.snapshot / 'sentinel.json'
        sentinel.write_bytes(b'preserve symlink target\n')
        link = self.snapshot / 'linked.json'
        link.symlink_to(sentinel)
        result = self.run_cli(link)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_bytes(), b'preserve symlink target\n')
        directory = self.snapshot / 'real-output'
        directory.mkdir()
        parent_link = self.snapshot / 'linked-output'
        parent_link.symlink_to(directory, target_is_directory=True)
        result = self.run_cli(parent_link / 'new.json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads((directory / 'new.json').read_text())['analysis_scope'], 'retrospective')
        absent = self.snapshot / 'absent-target.json'
        broken = self.snapshot / 'broken.json'
        broken.symlink_to(absent)
        result = self.run_cli(broken)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(broken.is_symlink())
        self.assertFalse(absent.exists())

    def test_cli_rejects_fresh_outputs_in_protected_snapshot_locations(self) -> None:
        for relative in ('benchmark-results', 'benchmark-data', 'research/historical_v1',
                         'research/confirmatory_v1'):
            protected = self.snapshot / relative
            protected.mkdir(parents=True, exist_ok=True)
            sentinel = protected / 'retained-sentinel.txt'
            sentinel.write_bytes(b'historical evidence\n')
            destination = protected / 'new-evaluation.json'
            with self.subTest(directory=relative):
                result = self.run_cli(destination)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(destination.exists())
                self.assertEqual(sentinel.read_bytes(), b'historical evidence\n')
                alias = self.snapshot / ('alias-' + relative.replace('/', '-'))
                alias.symlink_to(protected, target_is_directory=True)
                result = self.run_cli(alias / 'new-evaluation.json')
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(destination.exists())
                self.assertEqual(sentinel.read_bytes(), b'historical evidence\n')

    def load_cli_module(self):
        spec = importlib.util.spec_from_file_location(
            'isolated_elapsed_cli', self.snapshot / 'tools/evaluate_elapsed_benchmark.py')
        module = importlib.util.module_from_spec(spec)
        previous_path = list(sys.path)
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = previous_path
        return module

    def test_late_file_creation_and_parent_redirection_preserve_existing_data(self) -> None:
        module = self.load_cli_module()
        output = self.snapshot / 'late.json'
        destination = module.validate_output_destination(output, self.input)
        output.write_bytes(b'created by another writer\n')
        with self.assertRaises(FileExistsError):
            module.write_fresh_report(destination, b'new report')
        self.assertEqual(output.read_bytes(), b'created by another writer\n')

        parent = self.snapshot / 'race-parent'
        parent.mkdir()
        destination = module.validate_output_destination(parent / 'new.json', self.input)
        original_parent = self.snapshot / 'original-parent'
        parent.rename(original_parent)
        protected = self.snapshot / 'research' / 'historical_v1'
        protected.mkdir(parents=True, exist_ok=True)
        parent.symlink_to(protected, target_is_directory=True)
        with self.assertRaises(OSError):
            module.write_fresh_report(destination, b'new report')
        self.assertFalse((protected / 'new.json').exists())
        self.assertFalse((original_parent / 'new.json').exists())

    def test_cli_validation_failure_does_not_create_an_output(self) -> None:
        bad = document([quiet()])
        bad['cases'][0]['exposure_evidence']['intervals'][0]['supported'] = 1
        self.input.write_text(json.dumps(bad))
        output = self.snapshot / 'invalid-output.json'
        result = self.run_cli(output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
