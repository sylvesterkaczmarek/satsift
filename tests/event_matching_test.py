#!/usr/bin/env python3
"""Independent assignment oracle and browser/Python scoring parity regressions."""
from __future__ import annotations

import itertools
import json
import random
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.event_matching import (
    EVENT_MATCHING_VERSION, match_event_intervals, parse_time_us, tolerance_hours_to_us,
)
from research.evaluation_version import EVALUATION_VERSION
from research.comparison_v1.run_comparison import match_event_dicts
from research.selective_v1.core import Event, match_events as match_selective
from research.physics_ml.evaluate import evaluate_document, match_events as match_physics
from tools.evaluate_benchmark import match_events as match_publication

HOUR_US = 3_600_000_000


def oracle(predictions, truth, tolerance_us):
    """Enumerate assignments, including every unmatched option, without a flow solver."""
    best = (1, 0)
    assignments = set()

    def visit(index, used_truth, pairs, total_distance):
        nonlocal best, assignments
        if index == len(predictions):
            objective = (-len(pairs), total_distance)
            result = tuple(pairs)
            if objective < best:
                best, assignments = objective, {result}
            elif objective == best:
                assignments.add(result)
            return
        visit(index + 1, used_truth, pairs, total_distance)
        start, end, strongest = predictions[index]
        for truth_index, (truth_start, truth_end) in enumerate(truth):
            eligible = end >= truth_start - tolerance_us and start <= truth_end + tolerance_us
            if eligible and truth_index not in used_truth:
                distance = abs(2 * strongest - truth_start - truth_end)
                visit(index + 1, used_truth | {truth_index},
                      pairs + [(index, truth_index)], total_distance + distance)

    visit(0, set(), [], 0)
    return best, assignments


def temporal_pairs(predictions, truth, matches):
    return sorted((tuple(predictions[item['prediction_index']]),
                   tuple(truth[item['truth_index']])) for item in matches)


def wire_case(case):
    return {
        'name': case['name'],
        'predictions': [[str(value) for value in item] for item in case['predictions']],
        'truth': [[str(value) for value in item] for item in case['truth']],
        'tolerance_us': str(case['tolerance_us']),
    }


def synthetic_cases():
    cases = []
    prediction_types = [(0, 0, 0), (2, 2, 2), (4, 4, 4), (0, 4, 2), (0, 4, 4)]
    truth_types = [(0, 0), (2, 2), (4, 4), (1, 3)]
    prediction_sets = [values for size in range(3)
                       for values in itertools.combinations_with_replacement(prediction_types, size)]
    truth_sets = [values for size in range(3)
                  for values in itertools.combinations_with_replacement(truth_types, size)]
    for predictions, truth, tolerance in itertools.product(prediction_sets, truth_sets, (0, 1, 2)):
        cases.append({'name': f'exhaustive-{len(cases)}', 'predictions': predictions,
                      'truth': truth, 'tolerance_us': tolerance})
    assert len(cases) == 945
    rng = random.Random(20261122)
    for index in range(200):
        predictions = []
        truth = []
        for _ in range(rng.randrange(6)):
            start, end = sorted((rng.randrange(-8, 9), rng.randrange(-8, 9)))
            predictions.append((start, end, rng.randint(start, end)))
        for _ in range(rng.randrange(6)):
            truth.append(tuple(sorted((rng.randrange(-8, 9), rng.randrange(-8, 9)))))
        cases.append({'name': f'seeded-{index}', 'predictions': predictions,
                      'truth': truth, 'tolerance_us': rng.randrange(4)})
    cases.extend([
        {'name': 'lost-cardinality', 'predictions': [(4, 4, 4), (-5, -5, -5)],
         'truth': [(0, 0), (10, 10)], 'tolerance_us': 6},
        {'name': 'global-distance', 'predictions': [(0, 0, 0), (10, 10, 10)],
         'truth': [(9, 9), (12, 12)], 'tolerance_us': 12},
        {'name': 'overlap-with-strongest-outside-truth', 'predictions': [(5, 15, 6)],
         'truth': [(10, 20)], 'tolerance_us': 0},
        {'name': 'inclusive-before', 'predictions': [(4, 4, 4)],
         'truth': [(10, 20)], 'tolerance_us': 6},
        {'name': 'inclusive-after', 'predictions': [(21, 23, 21)],
         'truth': [(10, 20)], 'tolerance_us': 1},
        {'name': 'outside-before', 'predictions': [(3, 3, 3)],
         'truth': [(10, 20)], 'tolerance_us': 6},
        {'name': 'outside-after', 'predictions': [(22, 23, 22)],
         'truth': [(10, 20)], 'tolerance_us': 1},
        {'name': 'nested-overlaps', 'predictions': [(0, 20, 5), (8, 12, 10), (10, 10, 10)],
         'truth': [(2, 18), (10, 10), (9, 11)], 'tolerance_us': 0},
        {'name': 'half-microsecond-midpoint', 'predictions': [(0, 0, 0), (1, 1, 1)],
         'truth': [(0, 1)], 'tolerance_us': 0},
        {'name': 'strongest-distance', 'predictions': [(0, 20, 20), (0, 20, 10)],
         'truth': [(10, 10), (20, 20)], 'tolerance_us': 0},
        {'name': 'identical-duplicates', 'predictions': [(0, 4, 2)] * 4,
         'truth': [(1, 3)] * 3, 'tolerance_us': 0},
        {'name': 'distinct-equal-costs', 'predictions': [(0, 4, 2), (1, 3, 2), (2, 2, 2)],
         'truth': [(0, 4), (1, 3), (2, 2)], 'tolerance_us': 0},
        {'name': 'beyond-number-safe-integer',
         'predictions': [(10**18 + 1, 10**18 + 1, 10**18 + 1),
                         (10**18 + 2, 10**18 + 2, 10**18 + 2)],
         'truth': [(10**18 + 2, 10**18 + 2), (10**18 + 1, 10**18 + 1)],
         'tolerance_us': 1},
        {'name': 'negative-precise-epochs',
         'predictions': [(-10**18 - 2, -10**18 - 1, -10**18 - 1)],
         'truth': [(-10**18 - 2, -10**18 - 1)], 'tolerance_us': 0},
    ])
    return cases


def iso(microseconds):
    instant = datetime(2026, 1, 10, tzinfo=timezone.utc) + timedelta(microseconds=microseconds)
    return instant.isoformat(timespec='microseconds').replace('+00:00', 'Z')


def event_dict(interval):
    start, end, strongest = interval
    return {'start_utc': iso(start), 'end_utc': iso(end), 'strongest_utc': iso(strongest)}


def truth_dict(interval):
    start, end = interval
    return {'start': iso(start), 'end': iso(end)}


def selective_events(predictions):
    return [Event(index, index, index, item['start_utc'], item['end_utc'],
                  item['strongest_utc'], 1.0, ()) for index, item in enumerate(predictions)]


class EventMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = synthetic_cases()
        cls.python = [match_event_intervals(case['predictions'], case['truth'], case['tolerance_us'])
                      for case in cls.cases]
        cls.by_name = {case['name']: index for index, case in enumerate(cls.cases)}
        rng = random.Random(517)
        cls.permutations = []
        candidates = [case for case in cls.cases
                      if case['name'].startswith('seeded-') and len(case['predictions']) >= 2
                      and len(case['truth']) >= 2][:40]
        candidates.extend(case for case in cls.cases
                          if case['name'] in {'identical-duplicates', 'distinct-equal-costs', 'nested-overlaps'})
        for case in candidates:
            for repeat in range(8):
                predictions = list(case['predictions'])
                truth = list(case['truth'])
                rng.shuffle(predictions)
                rng.shuffle(truth)
                cls.permutations.append({
                    'name': f"{case['name']}-permutation-{repeat}",
                    'source': case['name'], 'predictions': predictions,
                    'truth': truth, 'tolerance_us': case['tolerance_us'],
                })
        cls.permuted_python = [
            match_event_intervals(case['predictions'], case['truth'], case['tolerance_us'])
            for case in cls.permutations
        ]
        cls.wrapper_cases = [
            {'name': 'cardinality',
             'predictions': [event_dict((4 * HOUR_US,) * 3), event_dict((-5 * HOUR_US,) * 3)],
             'truth': [truth_dict((0, 0)), truth_dict((10 * HOUR_US,) * 2)], 'tolerance_hours': 6},
            {'name': 'onset-delay',
             'predictions': [event_dict((2 * HOUR_US, 6 * HOUR_US, 5 * HOUR_US))],
             'truth': [truth_dict((HOUR_US, 3 * HOUR_US))], 'tolerance_hours': 0},
            {'name': 'same-millisecond-distinct',
             'predictions': [event_dict((1, 1, 1)), event_dict((2, 2, 2))],
             'truth': [truth_dict((2, 2)), truth_dict((1, 1))], 'tolerance_hours': 0},
            {'name': 'microsecond-delay', 'predictions': [event_dict((1, 5, 4))],
             'truth': [truth_dict((0, 6))], 'tolerance_hours': 0},
            {'name': 'date-fallback', 'predictions': [event_dict((1000, 3000, 2000))],
             'truth': [truth_dict((1000, 3000))], 'tolerance_hours': 0, 'use_records': False},
            {'name': 'fractional-tolerance-boundary',
             'predictions': [event_dict((0, 0, 0))],
             'truth': [truth_dict((1, 1)), truth_dict((2, 2))],
             'tolerance_hours': 3.333333333333333e-10},
            {'name': 'negative-epoch-wrapper',
             'predictions': [{'start_utc': '1969-12-31T23:59:59.999998Z',
                              'end_utc': '1969-12-31T23:59:59.999999Z',
                              'strongest_utc': '1969-12-31T23:59:59.999999Z'}],
             'truth': [{'start': '1969-12-31T23:59:59.999998Z',
                        'end': '1969-12-31T23:59:59.999999Z'}], 'tolerance_hours': 0},
            {'name': 'offset-truth', 'predictions': [event_dict((2, 2, 2))],
             'truth': [{'start': '2026-01-10T01:00:00.000002+01:00',
                        'end': '2026-01-10T01:00:00.000002+01:00'}], 'tolerance_hours': 0},
        ]
        payload = {'cases': [wire_case(case) for case in cls.cases + cls.permutations],
                   'wrapper_cases': cls.wrapper_cases, 'identity': True}
        cls.browser = json.loads(subprocess.check_output(
            ['node', 'tests/event_matching_bridge.js'], input=json.dumps(payload),
            text=True, cwd=ROOT))

    def test_exhaustive_assignment_oracle(self):
        for case, actual in zip(self.cases, self.python):
            with self.subTest(case=case['name']):
                objective, optimal = oracle(case['predictions'], case['truth'], case['tolerance_us'])
                pairs = tuple(sorted((item['prediction_index'], item['truth_index']) for item in actual))
                self.assertIn(pairs, optimal)
                self.assertEqual(-len(actual), objective[0])
                self.assertEqual(sum(item['distance_twice_us'] for item in actual), objective[1])
                self.assertEqual(len({item['prediction_index'] for item in actual}), len(actual))
                self.assertEqual(len({item['truth_index'] for item in actual}), len(actual))
                canonical = [(tuple(case['predictions'][item['prediction_index']]),
                              item['prediction_index']) for item in actual]
                self.assertEqual(canonical, sorted(canonical))

    def test_browser_python_exact_parity(self):
        all_python = self.python + self.permuted_python
        self.assertEqual(len(self.browser['cases']), len(all_python))
        for case, actual, browser in zip(self.cases + self.permutations, all_python, self.browser['cases']):
            with self.subTest(case=case['name']):
                converted = [dict(item, distance_twice_us=int(item['distance_twice_us'])) for item in browser]
                self.assertEqual(converted, actual)

    def test_global_objective_counterexamples(self):
        cardinality = self.python[self.by_name['lost-cardinality']]
        self.assertEqual({(item['prediction_index'], item['truth_index']) for item in cardinality},
                         {(0, 1), (1, 0)})
        minimum_cost = self.python[self.by_name['global-distance']]
        self.assertEqual(sum(item['distance_twice_us'] for item in minimum_cost), 22)
        self.assertEqual({(item['prediction_index'], item['truth_index']) for item in minimum_cost},
                         {(0, 0), (1, 1)})

    def test_permutation_invariance_including_ties_and_duplicates(self):
        for case, actual in zip(self.permutations, self.permuted_python):
            source_index = self.by_name[case['source']]
            original = self.cases[source_index]
            with self.subTest(case=case['name']):
                self.assertEqual(temporal_pairs(case['predictions'], case['truth'], actual),
                                 temporal_pairs(original['predictions'], original['truth'],
                                                self.python[source_index]))

    def test_inclusive_interval_eligibility_and_exact_distances(self):
        for name in ('inclusive-before', 'inclusive-after', 'overlap-with-strongest-outside-truth'):
            self.assertEqual(len(self.python[self.by_name[name]]), 1, name)
        for name in ('outside-before', 'outside-after'):
            self.assertEqual(self.python[self.by_name[name]], [], name)
        self.assertEqual(self.python[self.by_name['half-microsecond-midpoint']][0]['distance_twice_us'], 1)
        precise = self.python[self.by_name['beyond-number-safe-integer']]
        self.assertEqual([item['distance_twice_us'] for item in precise], [0, 0])
        self.assertEqual([(item['prediction_index'], item['truth_index']) for item in precise],
                         [(0, 1), (1, 0)])

    def test_core_rejects_ambiguous_numeric_inputs(self):
        for predictions, truth, tolerance in [
            ([(0, 0, 0)], [(0, 0)], -1),
            ([(0, 0, 0)], [(0, 0)], 0.5),
            ([(0, 0, 0)], [(0, 0)], True),
            ([(0.5, 1, 1)], [(0, 1)], 0),
            ([(0, 1, False)], [(0, 1)], 0),
            ([(2, 1, 1)], [(0, 1)], 0),
            ([(0, 1, 1)], [(2, 1)], 0),
        ]:
            with self.subTest(predictions=predictions, truth=truth, tolerance=tolerance):
                with self.assertRaises((TypeError, ValueError)):
                    match_event_intervals(predictions, truth, tolerance)

        self.assertEqual(self.browser['validation'], [True] * 8)

    def test_tolerance_rounding_matches_exact_decimal_contract(self):
        expected = [0, 360_000_000, 86_400_000_000, 0, 1, 6]
        self.assertEqual([int(item['microseconds']) for item in self.browser['tolerance']], expected)
        for item, value in zip(self.browser['tolerance'], expected):
            self.assertEqual(tolerance_hours_to_us(item['hours']), value)
        for value in (-1, float('nan'), float('inf'), -float('inf')):
            with self.assertRaises((TypeError, ValueError)):
                tolerance_hours_to_us(value)
        self.assertEqual(self.browser['invalid_tolerance'], [True] * 4)

    def test_browser_adapters_preserve_microseconds_through_normalisation(self):
        self.assertEqual(len(self.browser['wrapper_cases']), len(self.wrapper_cases))
        for case, browser in zip(self.wrapper_cases, self.browser['wrapper_cases']):
            with self.subTest(case=case['name']):
                predictions = [tuple(parse_time_us(item[key]) for key in
                                     ('start_utc', 'end_utc', 'strongest_utc'))
                               for item in case['predictions']]
                truth = [tuple(parse_time_us(item[key]) for key in ('start', 'end'))
                         for item in case['truth']]
                expected = match_event_intervals(predictions, truth,
                                                 tolerance_hours_to_us(case['tolerance_hours']))
                self.assertEqual(browser['true_positives'], len(expected))
                self.assertEqual(browser['false_positives'], len(predictions) - len(expected))
                self.assertEqual(browser['false_negatives'], len(truth) - len(expected))
                expected_report = [{
                    'prediction_index': item['prediction_index'],
                    'truth_index': item['truth_index'],
                    'distance_ms': item['distance_twice_us'] / 2000,
                    'delay_hours': item['delay_hours'],
                    'strongest_point_delay_hours': item['strongest_point_delay_hours'],
                } for item in expected]
                self.assertEqual(browser['matches'], expected_report)
                for original, normalised in zip(case['truth'], browser['normalised_truth']):
                    for key in ('start', 'end'):
                        self.assertEqual(parse_time_us(normalised[key]), parse_time_us(original[key]))

    def test_browser_report_runs_corrected_matching_and_exports_exact_epochs(self):
        report = self.browser['report']
        self.assertEqual(report['schema'], 'smd-event-benchmark-report-v4')
        self.assertEqual(report['scoring_version'], EVENT_MATCHING_VERSION)
        self.assertEqual(report['benchmark_id'], self.browser['report_expected_id'])
        self.assertEqual(report['summary']['true_positives'], 2)
        self.assertEqual(report['summary']['false_negatives'], 0)
        self.assertEqual(report['missing_data_sensitivity']['true_positives'], 2)
        self.assertEqual(report['missing_data_sensitivity']['false_negatives'], 0)
        case = report['cases'][0]
        self.assertEqual(case['deterministic_thinning']['true_positives'], 2)
        self.assertEqual({(item['predictionIndex'], item['truthIndex']) for item in case['matches']},
                         {(0, 1), (1, 0)})
        for event, microseconds in zip(case['predicted_events'], (1, 2)):
            for key in ('start', 'end', 'strongest_epoch'):
                self.assertEqual(event[key], iso(microseconds))
        self.assertEqual([item['start'] for item in case['truth_events']], [iso(2), iso(1)])

    def test_all_maintained_python_adapters_use_onset_delay(self):
        predictions = [event_dict((2 * HOUR_US, 6 * HOUR_US, 5 * HOUR_US))]
        truth = [truth_dict((HOUR_US, 3 * HOUR_US))]
        for name, actual in [
            ('comparison', match_event_dicts(predictions, truth, 0)),
            ('selective', match_selective(selective_events(predictions), truth, 0)),
            ('publication', match_publication(predictions, truth, 0)),
        ]:
            with self.subTest(adapter=name):
                self.assertEqual(actual['tp'], 1)
                self.assertEqual(actual['fn'], 0)
                self.assertEqual(actual['matches'][0]['delay_hours'], 1.0)
                self.assertEqual(actual['matches'][0]['strongest_point_delay_hours'], 4.0)
        self.assertEqual(match_physics(predictions, truth, 0), [(0, 0, 1.0)])

    def test_all_maintained_python_adapters_preserve_cardinality_and_microseconds(self):
        for name in ('lost-cardinality', 'beyond-number-safe-integer'):
            case = self.cases[self.by_name[name]]
            # Browser Date adapters have a finite calendar range; microsecond regressions use 2026.
            offset = 10**18 if name == 'beyond-number-safe-integer' else 0
            predictions = [event_dict(tuple(value - offset for value in item))
                           for item in case['predictions']]
            truth = [truth_dict(tuple(value - offset for value in item)) for item in case['truth']]
            tolerance = case['tolerance_us'] / HOUR_US
            expected = {(item['prediction_index'], item['truth_index'])
                        for item in self.python[self.by_name[name]]}
            for adapter_name, actual in [
                ('comparison', match_event_dicts(predictions, truth, tolerance)),
                ('selective', match_selective(selective_events(predictions), truth, tolerance)),
                ('publication', match_publication(predictions, truth, tolerance)),
            ]:
                with self.subTest(case=name, adapter=adapter_name):
                    self.assertEqual({(item['prediction_index'], item['truth_index'])
                                      for item in actual['matches']}, expected)
            self.assertEqual({item[:2] for item in match_physics(predictions, truth, tolerance)}, expected)

    def test_new_reports_identify_corrected_scoring_and_onset_delay(self):
        self.assertEqual(EVENT_MATCHING_VERSION, 'event-matching-v3')
        self.assertEqual(EVALUATION_VERSION, 'case-statistics-v3')
        case = {
            'case_id': 'synthetic', 'object_id': 'test', 'split': 'primary-test',
            'label_status': 'event-evidence', 'span_days': 1,
            'predicted_events': [event_dict((2 * HOUR_US, 6 * HOUR_US, 5 * HOUR_US))],
            'truth_events': [truth_dict((HOUR_US, 3 * HOUR_US))],
        }
        report = evaluate_document({'matching_tolerance_hours': 0, 'cases': [case]},
                                   bootstrap_samples=3)
        self.assertEqual(report['evaluation_version'], EVALUATION_VERSION)
        self.assertEqual(report['scoring_version'], EVENT_MATCHING_VERSION)
        self.assertEqual(report['summary']['median_detection_delay_hours'], 1.0)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'synthetic-predictions.json'
            output = Path(temporary) / 'synthetic-evaluation.json'
            source.write_text(json.dumps({'matching_tolerance_hours': 0, 'cases': [case]}))
            subprocess.run([sys.executable, 'tools/evaluate_benchmark.py', '--results',
                            str(source), '--output', str(output)], cwd=ROOT, check=True,
                           stdout=subprocess.DEVNULL)
            publication = json.loads(output.read_text())
        self.assertEqual(publication['evaluation_version'], EVALUATION_VERSION)
        self.assertEqual(publication['scoring_version'], EVENT_MATCHING_VERSION)
        self.assertEqual(publication['by_split']['primary-test']['summary']['median_detection_delay_hours'], 1.0)
        identity = self.browser['identity']
        self.assertEqual(identity['scoring_version'], EVENT_MATCHING_VERSION)
        self.assertEqual(identity['schema'], 'smd-event-benchmark-report-v4')
        self.assertTrue(identity['current'].startswith('smb-v2-'))
        self.assertEqual(identity['current'], identity['repeated'])
        self.assertNotEqual(identity['current'], identity['changed_scoring'])
        self.assertNotEqual(identity['current'], identity['legacy'])


if __name__ == '__main__':
    result = unittest.main(verbosity=2, exit=False)
    if result.result.wasSuccessful():
        print('Assignment oracle verified 945 exhaustive inputs, 200 seeded inputs, '
              '14 targeted cases and 344 permutations with exact browser/Python parity.')
    sys.exit(not result.result.wasSuccessful())
