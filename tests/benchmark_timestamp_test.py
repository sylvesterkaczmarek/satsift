#!/usr/bin/env python3
"""Strict benchmark truth admission and cross-timezone browser/Python parity."""
from __future__ import annotations

import calendar
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.event_matching import (
    parse_truth_timestamp_us, parse_truth_interval_us, validated_truth_events,
)
from research.comparison_v1.run_comparison import (
    match_event_dicts, summarize_results,
)
from research.selective_v1.core import Event, match_events as match_selective
from research.physics_ml.evaluate import (
    evaluate_document, match_events as match_physics, summarise as summarise_physics,
)
from tools.evaluate_benchmark import (
    match_events as match_publication, summarize as summarize_publication,
)

ZONES = ('UTC', 'America/New_York', 'Europe/Berlin', 'Asia/Kolkata')
VALID_START = '2026-01-01T00:00:00Z'


def reference(value):
    """Independent civil-time conversion through the standard datetime library."""
    moment = datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    delta = moment - datetime(1970, 1, 1, tzinfo=timezone.utc)
    microseconds = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    iso = (f'{moment.year:04d}-{moment.month:02d}-{moment.day:02d}T'
           f'{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}.'
           f'{moment.microsecond:06d}Z')
    return {'epoch_us': str(microseconds), 'iso': iso}


def fixtures():
    valid = [
        '0001-01-01T00:00:00Z', '0004-02-29T00:00:00Z',
        '1900-02-28T23:59:59Z', '2000-02-29T12:34:56.123456Z',
        '2024-02-29T00:00:00Z', '9999-12-31T23:59:59.999999Z',
        '0001-01-01T23:59:00+23:59', '9999-12-31T00:00:00-23:59',
        '1969-12-31T23:59:59.999999Z', '1970-01-01T00:00:00.000001Z',
        '2026-01-01T00:00:00Z', '2026-01-01T00:00:00+00:00',
        '2026-01-01T00:00:00-00:00', '2026-01-01T00:00:00+05:45',
        '2026-01-01T00:00:00-03:30', '2026-01-01T00:00:00+23:59',
        '2026-01-01T00:00:00-23:59',
        # Fixed numeric offsets define instants even in local DST gaps or folds.
        '2026-03-08T02:30:00-05:00', '2026-11-01T01:30:00-04:00',
        '2026-11-01T01:30:00-05:00',
    ]
    valid.extend('2026-01-01T00:00:00.' + '123456'[:digits] + 'Z'
                 for digits in range(1, 7))
    invalid = [
        None, False, True, 0, 1.5, 1770000000, [], {}, [VALID_START],
        '', '2026', '2026-01-01', '2026-01-01T00:00:00',
        '2026-01-01T00:00Z', '2026-01-01 00:00:00Z',
        '20260101T000000Z', '2026-W01-4T00:00:00Z', '2026-001T00:00:00Z',
        '2026-01-01t00:00:00Z', '2026-01-01T00:00:00z',
        ' 2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z ',
        '2026-01-01T00:00:00Z\n', '2026-01-01T00:00:00Z\r',
        '2026-01-01T00:00:00Z\r\n', '2026-01-01T00:00:00Z\u2028',
        '2026-01-01T00:00:00Z\u2029', '\t2026-01-01T00:00:00Z',
        '\u00a02026-01-01T00:00:00Z', '２０２６-01-01T00:00:00Z',
        '2026-٠١-01T00:00:00Z', '2026-01-01T00:00:00.١Z',
        '2026-01-01T00:00:00.Z', '2026-01-01T00:00:00.1234567Z',
        '2026-01-01T00:00:00.0000000Z', '2026-01-01T00:00:00,1Z',
        '2026-01-01T00:00:00+01', '2026-01-01T00:00:00+0100',
        '2026-01-01T00:00:00+01:00:30', '2026-01-01T00:00:00+24:00',
        '2026-01-01T00:00:00-24:00', '2026-01-01T00:00:00+00:60',
        '2026-01-01T00:00:00-00:60', '2026-01-01T00:00:00+1:00',
        '2026-01-01T00:00:00UTC', '2026-01-01T00:00:00Zjunk',
        '0000-01-01T00:00:00Z', '10000-01-01T00:00:00Z',
        '0001-01-01T00:00:00+00:01', '9999-12-31T23:59:59-00:01',
        '2026-00-01T00:00:00Z', '2026-13-01T00:00:00Z',
        '2026-01-00T00:00:00Z', '2026-01-32T00:00:00Z',
        '2026-02-29T00:00:00Z', '1900-02-29T00:00:00Z',
        '2026-01-01T24:00:00Z', '2026-01-01T00:60:00Z',
        '2026-01-01T00:00:60Z',
    ]
    for year in (1900, 2000, 2024, 2026):
        for month in range(1, 13):
            final_day = calendar.monthrange(year, month)[1]
            valid.append(f'{year}-{month:02d}-{final_day:02d}T23:59:59.999999Z')
            invalid.append(f'{year}-{month:02d}-{final_day + 1:02d}T00:00:00Z')
    timestamps = [{'name': f'valid-{index}', 'value': value, 'valid': True}
                  for index, value in enumerate(valid)]
    timestamps += [{'name': f'invalid-{index}', 'value': value, 'valid': False}
                   for index, value in enumerate(invalid)]
    intervals = [
        {'name': 'omitted-end', 'truth': {'start': VALID_START}, 'valid': True},
        {'name': 'equal-end', 'truth': {'start': VALID_START, 'end': VALID_START}, 'valid': True},
        {'name': 'equivalent-offsets', 'truth': {
            'start': '2026-01-01T01:00:00.123456+01:00',
            'end': '2026-01-01T00:00:00.123456Z'}, 'valid': True},
        {'name': 'ordered-instants-reversed-wall-clocks', 'truth': {
            'start': '2026-01-01T01:00:00+02:00',
            'end': '2026-01-01T00:00:00Z'}, 'valid': True},
        {'name': 'negative-microseconds', 'truth': {
            'start': '1969-12-31T23:59:59.999998Z',
            'end': '1969-12-31T23:59:59.999999Z'}, 'valid': True},
        {'name': 'microsecond-order', 'truth': {
            'start': '2026-01-01T00:00:00.000001Z',
            'end': '2026-01-01T00:00:00.000002Z'}, 'valid': True},
        {'name': 'missing-start', 'truth': {}, 'valid': False},
        {'name': 'end-only', 'truth': {'end': VALID_START}, 'valid': False},
        {'name': 'reversed-microseconds', 'truth': {
            'start': '2026-01-01T00:00:00.000002Z',
            'end': '2026-01-01T00:00:00.000001Z'}, 'valid': False},
        {'name': 'reversed-utc-offsets', 'truth': {
            'start': '2026-01-01T00:00:00Z',
            'end': '2026-01-01T01:00:00+02:00'}, 'valid': False},
    ]
    intervals += [{'name': f'bad-object-{index}', 'truth': value, 'valid': False}
                  for index, value in enumerate((None, False, 0, '', []))]
    for index, value in enumerate(invalid):
        intervals.append({'name': f'bad-start-{index}', 'truth': {'start': value}, 'valid': False})
        intervals.append({'name': f'bad-end-{index}',
                          'truth': {'start': VALID_START, 'end': value}, 'valid': False})
    matching = [
        {'predictions': [{'start_utc': '2026-01-01T00:00:00.000001Z',
                          'end_utc': '2026-01-01T00:00:00.000002Z',
                          'strongest_utc': '2026-01-01T00:00:00.000002Z'}],
         'truth': [{'start': '2026-01-01T01:00:00.000001+01:00',
                    'end': '2026-01-01T05:45:00.000003+05:45'}], 'tolerance_hours': 0},
        {'predictions': [{'start_utc': '1969-12-31T23:59:59.999999Z',
                          'end_utc': '1969-12-31T23:59:59.999999Z',
                          'strongest_utc': '1969-12-31T23:59:59.999999Z'}],
         'truth': [{'start': '1970-01-01T00:59:59.999999+01:00'}], 'tolerance_hours': 0},
        {'predictions': [{'start_utc': '2026-03-08T07:30:00Z',
                          'end_utc': '2026-03-08T07:30:00Z',
                          'strongest_utc': '2026-03-08T07:30:00Z'}],
         'truth': [{'start': '2026-03-08T02:30:00-05:00'}], 'tolerance_hours': 0},
    ]
    return {'timestamps': timestamps, 'intervals': intervals,
            'collections': [[], None, False, 0, '', {}, {'start': VALID_START}],
            'matching': matching}


def attempt(operation):
    try:
        return {'accepted': True, 'value': operation()}
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        return {'accepted': False, 'error': str(exc)}


def adapter_results(predictions, truth, tolerance=0):
    selected = [Event(index, index, index, item['start_utc'], item['end_utc'],
                      item['strongest_utc'], 1.0, ())
                for index, item in enumerate(predictions)]
    calls = {
        'comparison': lambda: match_event_dicts(predictions, truth, tolerance),
        'selective': lambda: match_selective(selected, truth, tolerance),
        'publication': lambda: match_publication(predictions, truth, tolerance),
        'physics': lambda: match_physics(predictions, truth, tolerance),
    }
    output = {}
    for name, call in calls.items():
        result = attempt(call)
        if result['accepted']:
            pairs = result['value']['matches'] if isinstance(result['value'], dict) else result['value']
            result['value'] = [
                {'prediction_index': pair['prediction_index'], 'truth_index': pair['truth_index'],
                 'delay_hours': pair['delay_hours']} if isinstance(pair, dict)
                else {'prediction_index': pair[0], 'truth_index': pair[1], 'delay_hours': pair[2]}
                for pair in pairs
            ]
        output[name] = result
    return output


def python_probe(payload):
    return {
        'timestamps': [attempt(lambda item=item: str(parse_truth_timestamp_us(item['value'])))
                       for item in payload['timestamps']],
        'intervals': [{
            'parsed': attempt(lambda item=item: list(map(str, parse_truth_interval_us(item['truth'])))),
            'adapters': adapter_results([], [item['truth']]),
        } for item in payload['intervals']],
        'collections': [attempt(lambda value=value: validated_truth_events({'truth_events': value}))
                        for value in payload['collections']],
        'matching': [adapter_results(case['predictions'], case['truth'], case['tolerance_hours'])
                     for case in payload['matching']],
    }


class BenchmarkTimestampTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = fixtures()
        encoded = json.dumps(cls.payload)
        cls.browser = {}
        cls.python = {}
        for zone in ZONES:
            env = dict(os.environ, TZ=zone, PYTHONDONTWRITEBYTECODE='1')
            browser = subprocess.run(['node', 'tests/benchmark_timestamp_bridge.js'], input=encoded,
                                     cwd=ROOT, env=env, check=True, text=True, capture_output=True)
            probe = subprocess.run([sys.executable, '-B', __file__, '--probe'], input=encoded,
                                   cwd=ROOT, env=env, check=True, text=True, capture_output=True)
            cls.browser[zone] = json.loads(browser.stdout)
            cls.python[zone] = json.loads(probe.stdout)

    def test_valid_times_match_independent_datetime_conversion(self):
        for zone in ZONES:
            for index, fixture in enumerate(self.payload['timestamps']):
                if not fixture['valid']:
                    continue
                with self.subTest(zone=zone, name=fixture['name'], value=fixture['value']):
                    expected = reference(fixture['value'])
                    self.assertEqual(self.browser[zone]['timestamps'][index],
                                     {'accepted': True, 'value': expected})
                    self.assertEqual(self.python[zone]['timestamps'][index],
                                     {'accepted': True, 'value': expected['epoch_us']})
        values = {fixture['value']: self.browser['UTC']['timestamps'][index]
                  for index, fixture in enumerate(self.payload['timestamps']) if fixture['valid']}
        self.assertEqual(values['1969-12-31T23:59:59.999999Z']['value']['epoch_us'], '-1')
        self.assertEqual(values['1970-01-01T00:00:00.000001Z']['value']['epoch_us'], '1')

    def test_invalid_types_syntax_calendars_and_utc_overflow_are_rejected(self):
        for zone in ZONES:
            for index, fixture in enumerate(self.payload['timestamps']):
                if fixture['valid']:
                    continue
                with self.subTest(zone=zone, name=fixture['name'], value=fixture['value']):
                    self.assertFalse(self.browser[zone]['timestamps'][index]['accepted'])
                    self.assertFalse(self.python[zone]['timestamps'][index]['accepted'])
        self.assertTrue(all(not item['accepted']
                            for item in self.browser['UTC']['javascript_only_timestamps']))

    def test_interval_validation_does_not_depend_on_predictions(self):
        for zone in ZONES:
            for index, fixture in enumerate(self.payload['intervals']):
                with self.subTest(zone=zone, name=fixture['name']):
                    browser = self.browser[zone]['intervals'][index]
                    python = self.python[zone]['intervals'][index]
                    self.assertEqual(browser['normalisation']['accepted'], fixture['valid'])
                    self.assertEqual(browser['direct_matching']['accepted'], fixture['valid'])
                    self.assertEqual(python['parsed']['accepted'], fixture['valid'])
                    for adapter in python['adapters'].values():
                        self.assertEqual(adapter['accepted'], fixture['valid'])
                    if fixture['valid']:
                        truth = fixture['truth']
                        expected = [reference(truth[key] if key in truth else truth['start'])
                                    for key in ('start', 'end')]
                        self.assertEqual(python['parsed']['value'], [item['epoch_us'] for item in expected])
                        normalised = browser['normalisation']['value']
                        self.assertEqual([normalised['start'], normalised['end']],
                                         [item['iso'] for item in expected])
                    else:
                        self.assertIn('timestamp-case', browser['normalisation']['error'])
        self.assertFalse(self.browser['UTC']['javascript_only_end']['accepted'])

    def test_missing_truth_collection_is_empty_but_invalid_supplied_collections_fail(self):
        self.assertEqual(validated_truth_events({}), [])
        for zone in ZONES:
            self.assertEqual(self.browser[zone]['missing_collection'], {'accepted': True, 'value': []})
            for index, _ in enumerate(self.payload['collections']):
                self.assertEqual(self.browser[zone]['collections'][index]['accepted'], index == 0)
                self.assertEqual(self.python[zone]['collections'][index]['accepted'], index == 0)

    def test_matching_results_and_benchmark_ids_are_timezone_independent(self):
        for zone in ZONES:
            self.assertEqual(self.browser[zone], self.browser['UTC'])
            self.assertEqual(self.python[zone], self.python['UTC'])
            for browser, python in zip(self.browser[zone]['matching'], self.python[zone]['matching']):
                expected = [{key: pair[key] for key in ('prediction_index', 'truth_index', 'delay_hours')}
                            for pair in browser['matches']]
                self.assertEqual(len(expected), 1)
                for adapter in python.values():
                    self.assertEqual(adapter, {'accepted': True, 'value': expected})

    def test_rejected_import_invalidates_old_report_with_contextual_error(self):
        rejected = self.browser['UTC']['rejected_import']
        self.assertFalse(rejected['has_definition'])
        self.assertFalse(rejected['has_report'])
        self.assertTrue(rejected['run_disabled'])
        self.assertTrue(rejected['download_disabled'])
        self.assertEqual(rejected['displays'], ['none'] * 3)
        self.assertEqual(rejected['tables'], ['', ''])
        self.assertEqual(rejected['input'], '')
        self.assertEqual(rejected['orbital_input'], 'retained orbital input')
        self.assertIn('timestamp-case', rejected['hint'])
        self.assertIn('2', rejected['hint'])
        self.assertIn('end', rejected['hint'].lower())

    def test_valid_import_recovers_after_rejection(self):
        recovered = self.browser['UTC']['recovered_import']
        self.assertTrue(recovered['has_definition'])
        self.assertFalse(recovered['has_report'])
        self.assertFalse(recovered['run_disabled'])
        self.assertTrue(recovered['download_disabled'])
        self.assertEqual(recovered['displays'], ['none'] * 3)
        self.assertEqual(recovered['input'], '')
        self.assertEqual(recovered['orbital_input'], 'retained orbital input')
        truth = self.browser['UTC']['recovered_truth'][0]
        self.assertEqual(truth['start'], '2026-01-01T00:00:00.000001Z')
        self.assertEqual(truth['end'], truth['start'])

    def test_physics_aliases_use_presence_without_coercion_or_fallback(self):
        self.assertEqual(match_physics([], [{'start_utc': VALID_START}], 0), [])
        equivalent = {
            'start_utc': VALID_START, 'start': '2026-01-01T01:00:00+01:00',
            'end_utc': '2026-01-01T00:00:00.000001Z',
            'end': '2026-01-01T05:45:00.000001+05:45',
        }
        self.assertEqual(match_physics([], [equivalent], 0), [])
        for truth in [
            {'start_utc': None, 'start': VALID_START},
            {'start_utc': VALID_START, 'start': None},
            {'start_utc': VALID_START, 'start': '2026-01-01T00:00:00.000001Z'},
            {'start_utc': VALID_START, 'end_utc': None, 'end': VALID_START},
            {'start_utc': VALID_START, 'end_utc': VALID_START, 'end': None},
            {'start_utc': VALID_START, 'end_utc': VALID_START,
             'end': '2026-01-01T00:00:00.000001Z'},
            {'start': VALID_START, 'end_utc': False},
            {'start_utc': VALID_START, 'end_utc': ''},
        ]:
            with self.subTest(truth=truth), self.assertRaises((TypeError, ValueError)):
                match_physics([], [truth], 0)

    def test_summaries_validate_truth_in_unknown_quiet_and_unselected_cases(self):
        invalid = {'start': '2026-01-01T00:00:00'}
        for label in ('event-evidence', 'verified-quiet', 'unknown'):
            case = {'case_id': 'unscored-case', 'label_status': label, 'predicted_events': [],
                    'truth_events': [invalid], 'split': 'calibration', 'span_days': 1}
            for summarise in (
                lambda: summarize_results([case]),
                lambda: summarise_physics([case], 0),
                lambda: summarize_publication([case], 0),
                lambda: evaluate_document({'cases': [case]}, split='primary-test', bootstrap_samples=0),
            ):
                with self.subTest(label=label), self.assertRaises((TypeError, ValueError)):
                    summarise()

    def test_dataset_validation_preserves_sealed_partition_precedence(self):
        from research.selective_v1.train_compare import load_document, grouped_rows
        invalid = {'start': '2026-02-30T00:00:00Z'}
        case = {'case_id': 'synthetic', 'split': 'development', 'truth_events': [invalid]}
        document = {'confirmatory_sealed': True, 'cases': [case], 'rows': []}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic-features.json'
            path.write_text(json.dumps(document))
            with self.assertRaises((TypeError, ValueError)):
                load_document(path)
            with self.assertRaises((TypeError, ValueError)):
                grouped_rows(document)
            sealed = {**document, 'cases': [{**case, 'split': 'confirmatory'}]}
            path.write_text(json.dumps(sealed))
            with self.assertRaisesRegex(ValueError, 'CONFIRMATORY PARTITION IS SEALED'):
                load_document(path)
            sealed_row = {**document, 'rows': [{'case_id': 'synthetic', 'split': 'confirmatory'}]}
            with self.assertRaisesRegex(ValueError, 'CONFIRMATORY PARTITION IS SEALED'):
                grouped_rows(sealed_row)

    def test_ranking_paths_validate_truth_before_empty_reference_shortcuts(self):
        from research.selective_v1.train_compare import truth_interval_ranking
        from research.sequential_v1.run_development import sequential_truth_ranking
        from research.physics_v1.run_development import truth_interval_feasibility
        from research.integrity_v1.run_stress import sequential_truth_percentiles
        invalid = [{'start': '2026-02-30T00:00:00Z'}]
        calls = (
            lambda: truth_interval_ranking([], invalid, []),
            lambda: sequential_truth_ranking([], invalid, []),
            lambda: truth_interval_feasibility({'synthetic': {'truth_events': invalid}}, 'synthetic', [], []),
            lambda: sequential_truth_percentiles([], invalid, []),
        )
        for index, call in enumerate(calls):
            with self.subTest(path=index), self.assertRaises((TypeError, ValueError)):
                call()


if __name__ == '__main__':
    if '--probe' in sys.argv:
        print(json.dumps(python_probe(json.load(sys.stdin))))
    else:
        result = unittest.main(verbosity=2, exit=False)
        if result.result.wasSuccessful():
            payload = fixtures()
            print(f"Strict truth timestamp parity verified across {len(ZONES)} timezones, "
                  f"{len(payload['timestamps'])} timestamp fixtures and "
                  f"{len(payload['intervals'])} interval fixtures.")
        sys.exit(not result.result.wasSuccessful())
