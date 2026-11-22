#!/usr/bin/env python3
"""Exercise materialiser admission, deterministic selection and offline CLI output."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import itertools
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'materializer_under_test', ROOT / 'tools/materialize_benchmark_v1_spacetrack.py')
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)
START = '2026-01-01'
END = '2026-01-02'


def record(norad: str = '40010', **changes) -> dict:
    return {
        'NORAD_CAT_ID': norad,
        'EPOCH': '2026-01-01T12:00:00.123456Z',
        'CREATION_DATE': '2026-01-01T13:00:00.000000Z',
        'ELEMENT_SET_NO': '1',
        'GP_ID': '10',
        'MEAN_MOTION': '15.5',
        'ECCENTRICITY': '0.001',
        'INCLINATION': '51.6',
        'RA_OF_ASC_NODE': '10.0',
        'ARG_OF_PERICENTER': '20.0',
        'MEAN_ANOMALY': '30.0',
        'BSTAR': '0.0',
        **changes,
    }


def query(norad: str = '40010', start: str = START, end: str = END) -> str:
    after = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    interval = quote(f'{start}T00:00:00--{after}T00:00:00', safe='')
    return ('https://www.space-track.org/basicspacedata/query/class/gp_history'
            f'/NORAD_CAT_ID/{norad}/EPOCH/{interval}'
            '/orderby/EPOCH%20asc/limit/5000/format/json/emptyresult/show')


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200) -> None:
        super().__init__(body)
        self.status = status
        self.headers = {}
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        data = super().read(size)
        self.bytes_read += len(data)
        return data

    def geturl(self) -> str:
        return query()


class FakeOpener:
    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append((request.full_url, timeout))
        if not self.outcomes:
            raise AssertionError('Unexpected additional upstream request')
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, FakeResponse):
            return outcome
        body = outcome if isinstance(outcome, bytes) else json.dumps(outcome).encode()
        return FakeResponse(body)


class MaterializerAdmissionTests(unittest.TestCase):
    def normalize(self, records, start: str = START, end: str = END):
        return M.normalize(records, '40010', start, end)

    def reject(self, bad) -> None:
        with self.assertRaises(M.MaterializationError):
            self.normalize([record(), bad])

    def request(self, opener: FakeOpener, retries: int = 0, backoff: float = 0.5):
        return M.request_json(opener, query(), retries, backoff)

    def test_creation_precedence_is_independent_of_input_order(self) -> None:
        newest = record(CREATION_DATE='2026-01-02T02:00:00Z',
                        ELEMENT_SET_NO='1', GP_ID='20', MEAN_MOTION='15.6')
        older = record(CREATION_DATE='2026-01-02T01:00:00Z',
                       ELEMENT_SET_NO='99', GP_ID='999', MEAN_MOTION='15.5')
        other_old = {**older, 'MEAN_MOTION': '15.4'}
        for order in itertools.permutations([older, other_old, newest]):
            with self.subTest(order=[row['MEAN_MOTION'] for row in order]):
                self.assertEqual(self.normalize(list(order)), [newest])

    def test_creation_instants_include_offsets_and_microseconds(self) -> None:
        newest = record(CREATION_DATE='2026-01-02T02:00:00.000001Z',
                        ELEMENT_SET_NO='0', GP_ID='1', MEAN_MOTION='15.6')
        older = record(CREATION_DATE='2026-01-02T04:00:00.000000+02:00',
                       ELEMENT_SET_NO='999', GP_ID='999', MEAN_MOTION='15.4')
        missing = record(ELEMENT_SET_NO='9999', GP_ID='9999', MEAN_MOTION='15.3')
        del missing['CREATION_DATE']
        for order in itertools.permutations([older, missing, newest]):
            self.assertEqual(self.normalize(list(order)), [newest])
        equivalent = {**newest, 'CREATION_DATE': '2026-01-02T03:00:00.000001+01:00',
                      'GP_ID': '2', 'MEAN_MOTION': '15.7'}
        self.assertEqual(self.normalize([equivalent, newest]), [equivalent])
        self.assertEqual(self.normalize([newest, equivalent]), [equivalent])

    def test_catalogue_identifier_ties_use_exact_integers(self) -> None:
        absent = record(MEAN_MOTION='15.4')
        for field in ('CREATION_DATE', 'ELEMENT_SET_NO', 'GP_ID'):
            del absent[field]
        zero = {**absent, 'ELEMENT_SET_NO': '0', 'MEAN_MOTION': '15.5'}
        present_gp = {**zero, 'GP_ID': 0, 'MEAN_MOTION': '15.6'}
        for order in itertools.permutations([absent, zero, present_gp]):
            self.assertEqual(self.normalize(list(order)), [present_gp])
        first = record(GP_ID='9007199254740992', MEAN_MOTION='15.4')
        second = record(GP_ID='9007199254740993', MEAN_MOTION='15.6')
        for order in ([first, second], [second, first]):
            self.assertEqual(self.normalize(order), [second])
        larger_set = {**first, 'ELEMENT_SET_NO': '2'}
        self.assertEqual(self.normalize([second, larger_set]), [larger_set])

    def test_unresolved_top_rank_conflicts_are_explicit_errors(self) -> None:
        first = record(GP_ID='00010')
        conflicting = record(GP_ID=10, MEAN_MOTION='15.6')
        for order in itertools.permutations([first, conflicting, first]):
            with self.subTest(order=order), self.assertRaises(M.MaterializationError):
                self.normalize(list(order))

    def test_equivalent_ties_choose_one_stable_raw_representative(self) -> None:
        first = record(OBJECT_NAME='SYNTHETIC ONE')
        equivalent = record(EPOCH='2026-01-01T13:00:00.123456+01:00',
                            CREATION_DATE='2026-01-01T14:00:00+01:00',
                            ELEMENT_SET_NO='0001', GP_ID=10, OBJECT_NAME='SYNTHETIC TWO')
        expected = self.normalize([first, equivalent])
        self.assertEqual(len(expected), 1)
        self.assertIn(expected[0], [first, equivalent])
        for order in itertools.permutations([first, equivalent, copy.deepcopy(first)]):
            self.assertEqual(self.normalize(list(order)), expected)
        source = [copy.deepcopy(equivalent), copy.deepcopy(first)]
        before = copy.deepcopy(source)
        self.normalize(source)
        self.assertEqual(source, before, 'Raw upstream records must not be mutated')

    def test_epoch_sorting_uses_utc_instants_and_preserves_microseconds(self) -> None:
        first = record(EPOCH='2026-01-01T12:00:00.123456Z')
        second = record(EPOCH='2026-01-01T11:00:00.123457-01:00')
        third = record(EPOCH='2026-01-01t12:00:00.123458z')
        fourth = record(EPOCH='2026-01-01T12:00:00.123459')
        self.assertEqual(self.normalize([fourth, second, third, first]), [first, second, third, fourth])
        historic = record(EPOCH='1957-01-01T00:00:00.000001Z', CREATION_DATE=None)
        self.assertEqual(self.normalize([historic], '1956-12-31', '1957-01-01'), [historic])

    def test_invalid_rows_and_wrong_objects_are_never_silently_removed(self) -> None:
        for bad in [None, True, 7, 'row', [], {}, record(NORAD_CAT_ID='49999'),
                    record(NORAD_CAT_ID=True), record(NORAD_CAT_ID=40010.0),
                    record(NORAD_CAT_ID='40010x')]:
            with self.subTest(bad=bad):
                self.reject(bad)
        integer_id = record(NORAD_CAT_ID=40010)
        self.assertEqual(self.normalize([integer_id]), [integer_id])

    def test_field_aliases_and_local_extensions_cannot_bypass_admission(self) -> None:
        for alias, value in [('norad_cat_id', '49999'), ('epoch', '2025-01-01T00:00:00Z'),
                             ('mean_motion', '0'), ('bstar', 'not a number')]:
            with self.subTest(alias=alias):
                self.reject({**record(), alias: value})
        for field, value in [('BSTAR', 'not a number'), ('REF_FRAME', 'GCRF'),
                             ('CREATION_DATE', 'tomorrow'), ('MEAN_MOTION', False)]:
            invalid = record()
            invalid.pop(field, None)
            invalid[field.lower()] = value
            with self.subTest(field=field):
                self.reject(invalid)
        for field, value in [('SMD_TLE', {}), ('smd_tle', 'invalid'),
                             ('SMD_SOURCE_FORMAT', 'TLE'), ('SmD_Source_Format', 'OMM JSON'),
                             ('SMD_FUTURE_EXTENSION', None)]:
            with self.subTest(extension=field):
                self.reject({**record(), field: value})
        mixed = {key.lower() if index % 2 else key: value
                 for index, (key, value) in enumerate(record().items())}
        self.assertEqual(self.normalize([mixed]), [mixed], 'Accepted raw source spelling must be retained')
        lower = {key.lower(): value for key, value in record().items()}
        self.assertEqual(self.normalize([lower]), [lower])

    def test_invalid_orbital_fields_fail_even_in_a_weaker_revision(self) -> None:
        required = ['MEAN_MOTION', 'ECCENTRICITY', 'INCLINATION',
                    'RA_OF_ASC_NODE', 'ARG_OF_PERICENTER', 'MEAN_ANOMALY']
        invalid = [None, '', [], {}, True, False, 'NaN', 'Infinity', '1e999', float('nan')]
        for field in required:
            for value in invalid:
                with self.subTest(field=field, value=value):
                    self.reject(record(**{field: value, 'CREATION_DATE': '2025-01-01T00:00:00Z'}))
            missing = record()
            del missing[field]
            with self.subTest(missing=field):
                self.reject(missing)
        for field, value in [('MEAN_MOTION', 0), ('MEAN_MOTION', -1),
                             ('ECCENTRICITY', -0.1), ('ECCENTRICITY', 1),
                             ('INCLINATION', -1), ('INCLINATION', 180.1),
                             ('RA_OF_ASC_NODE', -1), ('RA_OF_ASC_NODE', 360),
                             ('ARG_OF_PERICENTER', 360), ('MEAN_ANOMALY', 360)]:
            with self.subTest(field=field, value=value):
                self.reject(record(**{field: value}))
        boundaries = record(ECCENTRICITY=0, INCLINATION=180,
                            RA_OF_ASC_NODE=0, ARG_OF_PERICENTER=0, MEAN_ANOMALY=0)
        self.assertEqual(self.normalize([boundaries]), [boundaries])

    def test_optional_metadata_has_strict_types_and_finite_values(self) -> None:
        for field in ['ELEMENT_SET_NO', 'GP_ID', 'REV_AT_EPOCH']:
            for value in [-1, 1.5, 1.0, True, [], {}, '1.0', '1e3', '-1', 'bad']:
                with self.subTest(field=field, value=value):
                    self.reject(record(**{field: value}))
        for field in ['BSTAR', 'MEAN_MOTION_DOT', 'MEAN_MOTION_DDOT']:
            for value in [True, [], {}, 'Infinity', 'NaN', '1e999', float('-inf')]:
                with self.subTest(field=field, value=value):
                    self.reject(record(**{field: value}))
            accepted = record(**{field: '-0.00001'})
            self.assertEqual(self.normalize([accepted]), [accepted])
        for value in [1, 4, True, 'bad', -1, 0.0]:
            with self.subTest(ephemeris=value):
                self.reject(record(EPHEMERIS_TYPE=value))
        for value in [0, '2', 3]:
            accepted = record(EPHEMERIS_TYPE=value)
            self.assertEqual(self.normalize([accepted]), [accepted])
        for omitted in [None, '', '   ']:
            accepted = record(CREATION_DATE=omitted, ELEMENT_SET_NO=omitted, GP_ID=omitted,
                              BSTAR=omitted, MEAN_MOTION_DOT=omitted, MEAN_MOTION_DDOT=omitted,
                              REV_AT_EPOCH=omitted, EPHEMERIS_TYPE=omitted)
            self.assertEqual(self.normalize([accepted]), [accepted])

    def test_optional_reference_frame_metadata_is_validated(self) -> None:
        fields = {'CENTER_NAME': 'EARTH', 'REF_FRAME': 'TEME', 'TIME_SYSTEM': 'UTC',
                  'MEAN_ELEMENT_THEORY': 'SGP4'}
        for field, expected in fields.items():
            for value in ['unsupported', True, [], {}]:
                with self.subTest(field=field, value=value):
                    self.reject(record(**{field: value}))
            accepted = record(**{field: ' ' + expected.lower() + ' '})
            self.assertEqual(self.normalize([accepted]), [accepted])

    def test_invalid_row_errors_identify_the_row_and_field(self) -> None:
        with self.assertRaises(M.MaterializationError) as caught:
            self.normalize([record(), record(MEAN_MOTION=None)])
        self.assertIn('2', str(caught.exception))
        self.assertIn('MEAN_MOTION', str(caught.exception))

    def test_browser_numeric_bounds_and_canonical_catalogue_ids(self) -> None:
        maximum = 9007199254740991
        for field in ['ELEMENT_SET_NO', 'REV_AT_EPOCH']:
            for value in [maximum, str(maximum)]:
                accepted = record(**{field: value})
                self.assertEqual(self.normalize([accepted]), [accepted])
            for value in [maximum + 1, str(maximum + 1)]:
                with self.subTest(field=field, value=value):
                    self.reject(record(**{field: value}))
        accepted_gp = record(GP_ID=str(maximum + 1))
        self.assertEqual(self.normalize(self.request(FakeOpener([accepted_gp]))), [accepted_gp])
        self.reject(record(GP_ID=maximum + 1))
        safe_gp = record(GP_ID=maximum)
        self.assertEqual(self.normalize(self.request(FakeOpener([safe_gp]))), [safe_gp])
        for value in [maximum + 1, -maximum - 1]:
            body = json.dumps([{**record(), 'UPSTREAM_COUNTER': value}]).encode()
            with self.subTest(json_integer=value), self.assertRaises(M.MaterializationError):
                self.request(FakeOpener(body))
        for value in [maximum, -maximum]:
            accepted = {**record(), 'UPSTREAM_COUNTER': value}
            self.assertEqual(self.request(FakeOpener([accepted])), [accepted])
        for value in ['040010', '0' * 100 + '40010']:
            with self.subTest(object_id=value):
                self.reject(record(NORAD_CAT_ID=value))
            with self.assertRaises(M.MaterializationError):
                M.normalize([record()], value, START, END)
        for value in ['40010', 40010, ' 40010 ']:
            accepted = record(NORAD_CAT_ID=value)
            self.assertEqual(self.normalize([accepted]), [accepted])

    def test_timestamp_calendar_and_precision_are_strict(self) -> None:
        invalid = [None, False, 0, [], {}, 'yesterday', '2026-01-01',
                   '2026-01-00T12:00:00Z', '2026-02-30T12:00:00Z',
                   '2026-01-01T24:00:00Z', '2026-01-01T12:60:00Z',
                   '2026-01-01T12:00:60Z', '2026-01-01T12:00:00.1234567Z',
                   '2026-01-01T12:00:00+24:00', '2026-01-01T12:00:00+01:60',
                   '2026-01-01 12:00:00Z']
        for value in invalid:
            with self.subTest(epoch=value):
                self.reject(record(EPOCH=value))
            if value is not None and value != '':
                with self.subTest(creation=value):
                    self.reject(record(CREATION_DATE=value))
        leap = record(EPOCH='2024-02-29T12:00:00.000001Z')
        self.assertEqual(self.normalize([leap], '2024-02-29', '2024-02-29'), [leap])
        with self.assertRaises(M.MaterializationError):
            self.normalize([record(EPOCH='2023-02-29T12:00:00Z')], '2023-02-28', '2023-03-01')

    def test_requested_window_and_provider_end_boundary(self) -> None:
        beginning = record(EPOCH='2026-01-01T00:00:00Z')
        last = record(EPOCH='2026-01-02T23:59:59.999999Z')
        boundary = record(EPOCH='2026-01-03T01:00:00+01:00')
        self.assertEqual(self.normalize([boundary, last, beginning]), [beginning, last])
        for epoch in ['2025-12-31T23:59:59.999999Z', '2026-01-03T00:00:00.000001Z']:
            with self.subTest(epoch=epoch):
                self.reject(record(EPOCH=epoch))
        self.reject({**boundary, 'MEAN_MOTION': False})
        self.reject({**boundary, 'NORAD_CAT_ID': '49999'})
        for records in [[], [boundary]]:
            with self.subTest(records=records), self.assertRaises(M.MaterializationError):
                self.normalize(records)

    def test_invalid_window_arguments_fail(self) -> None:
        for start, end in [('2026-02-30', END), (START, '2026-02-30'),
                           ('20260101', END), (START, '2026-1-2'),
                           (END, START)]:
            with self.subTest(start=start, end=end), self.assertRaises(M.MaterializationError):
                self.normalize([record()], start, end)

    def test_limit_is_checked_before_selection(self) -> None:
        self.assertEqual(self.normalize([record()] * 4999), [record()])
        with self.assertRaises(M.MaterializationError):
            self.normalize([record()] * 5000)
        with self.assertRaises(M.MaterializationError):
            self.request(FakeOpener([record()] * 5000))

    def test_json_shape_and_all_rows_are_validated(self) -> None:
        for payload in [{}, {'error': 'Session expired'}, None, True, 1, 'data',
                        [record(), None], [record(), 'bad row'], [record(), []]]:
            opener = FakeOpener(payload)
            with self.subTest(payload=payload), patch.object(M.time, 'sleep') as sleep:
                with self.assertRaises(M.MaterializationError):
                    self.request(opener, retries=3)
                self.assertEqual(len(opener.calls), 1, 'Invalid content must not be retried')
                sleep.assert_not_called()
        self.assertEqual(self.request(FakeOpener([record()])), [record()])

    def test_invalid_json_extensions_and_duplicate_keys_are_rejected(self) -> None:
        for body in [b'{broken', b'[] {}', b'\xff', b'[{"value":NaN}]',
                     b'[{"value":Infinity}]', b'[{"value":-Infinity}]',
                     b'[{"NORAD_CAT_ID":"40010","NORAD_CAT_ID":"40011"}]',
                     b'[{"metadata":{"value":1,"value":2}}]']:
            opener = FakeOpener(body)
            with self.subTest(body=body), self.assertRaises(M.MaterializationError):
                self.request(opener, retries=2)
            self.assertEqual(len(opener.calls), 1)

    def test_json_numbers_cannot_silently_lose_source_precision(self) -> None:
        for token in ['15.50000000000000001', '15.50000000000000002', '1e-999', '9007199254740992.5']:
            body = ('[{"value":' + token + '}]').encode()
            with self.subTest(token=token), self.assertRaises(M.MaterializationError):
                self.request(FakeOpener(body))
        ordinary = record(MEAN_MOTION=15.5, ECCENTRICITY=0.001, BSTAR=0.0)
        self.assertEqual(self.normalize(self.request(FakeOpener([ordinary]))), [ordinary])
        first = record(MEAN_MOTION='15.50000000000000001')
        second = record(MEAN_MOTION='15.50000000000000002')
        self.assertEqual(self.normalize(self.request(FakeOpener([first]))), [first])
        for order in [[first, second], [second, first]]:
            with self.assertRaises(M.MaterializationError):
                self.normalize(self.request(FakeOpener(order)))

    def test_http_success_and_response_size_are_bounded(self) -> None:
        for status in [201, 204, 302]:
            with self.subTest(status=status), self.assertRaises(M.MaterializationError):
                self.request(FakeOpener(FakeResponse(b'[]', status)))
        body = b'[]' + b' ' * M.MAX_RESPONSE_BYTES
        response = FakeResponse(body)
        with self.assertRaises(M.MaterializationError):
            self.request(FakeOpener(response))
        self.assertLessEqual(response.bytes_read, M.MAX_RESPONSE_BYTES + 1)
        self.assertTrue(response.closed)

    def test_retry_parameters_fail_before_network(self) -> None:
        for retries, backoff in [(-1, 0.5), (True, 0.5), (1.0, 0.5),
                                 (0, -1), (0, True), (0, float('nan')), (0, float('inf'))]:
            opener = FakeOpener()
            with self.subTest(retries=retries, backoff=backoff), self.assertRaises(M.MaterializationError):
                self.request(opener, retries=retries, backoff=backoff)
            self.assertEqual(opener.calls, [])

    def test_transient_retries_are_bounded_and_exponential(self) -> None:
        errors = [
            urllib.error.HTTPError(query(), 429, 'rate limited', {}, io.BytesIO()),
            urllib.error.HTTPError(query(), 503, 'unavailable', {}, io.BytesIO()),
            urllib.error.URLError('temporary failure'),
            TimeoutError('fixture timeout'),
        ]
        for error in errors[:2]:
            self.addCleanup(error.close)
        opener = FakeOpener(*errors, [record()])
        with patch.object(M.time, 'sleep') as sleep, redirect_stdout(io.StringIO()):
            self.assertEqual(self.request(opener, retries=4, backoff=0.5), [record()])
        self.assertEqual(len(opener.calls), 5)
        self.assertTrue(all(error.closed for error in errors[:2]), 'HTTP error response bodies must be closed before retry')
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.5, 1.0, 2.0, 4.0])
        exhausted = FakeOpener(*[urllib.error.URLError('unavailable') for _ in range(3)])
        with patch.object(M.time, 'sleep') as sleep, redirect_stdout(io.StringIO()):
            with self.assertRaises(M.MaterializationError):
                self.request(exhausted, retries=2)
        self.assertEqual(len(exhausted.calls), 3)
        self.assertEqual(sleep.call_count, 2)

    def test_permanent_http_failures_do_not_retry(self) -> None:
        for status in [400, 401, 403, 404]:
            error = urllib.error.HTTPError(query(), status, 'fixture error', {}, io.BytesIO())
            self.addCleanup(error.close)
            opener = FakeOpener(error)
            with self.subTest(status=status), patch.object(M.time, 'sleep') as sleep:
                with self.assertRaises((M.MaterializationError, urllib.error.HTTPError)):
                    self.request(opener, retries=3)
                self.assertEqual(len(opener.calls), 1)
                sleep.assert_not_called()
                self.assertTrue(error.closed, 'Permanent HTTP error response bodies must be closed')


class MaterializerCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.manifest_path = self.directory / 'synthetic-manifest.json'
        self.recipe_path = self.directory / 'synthetic-recipe.json'
        self.output = self.directory / 'new-benchmark.json'
        self.sidecar = self.output.with_suffix('.json.sha256')
        cases = []
        for number in range(2):
            norad = str(40010 + number)
            cases.append({
                'case_id': f'synthetic-{number + 1}', 'object_id': norad,
                'object_name': f'SYNTHETIC {number + 1}', 'start_date': START, 'end_date': END,
                'orbit_profile': 'LEO', 'orbit_regime': 'LEO', 'split': 'development',
                'label_status': 'verified-quiet', 'label_confidence': 'synthetic fixture',
                'evidence_kind': 'synthetic', 'source': 'https://example.invalid/synthetic',
                'truth_events': [],
            })
        self.manifest = {
            'schema': 'smd-public-evidence-manifest-v1.0', 'version': '1.0',
            'name': 'Synthetic admission fixture', 'matching_tolerance_hours': 6,
            'qualification': 'Synthetic offline verification only',
            'data_attribution': 'Synthetic test data',
            'split_policy': {}, 'label_policy': {}, 'external_label_provenance': {},
            'frozen_counts': {'cases': 2, 'unique_satellites': 2}, 'cases': cases,
        }
        self.recipe = {
            'schema': 'smd-space-track-materialization-recipe-v1',
            'benchmark_version': '1.0', 'case_count': 2,
            'cases': [{
                'case_id': row['case_id'], 'object_id': row['object_id'],
                'start_date': START, 'end_date': END,
                'space_track_gp_history_query': query(row['object_id']),
            } for row in cases],
        }
        self.write_inputs()
        self.credentials = patch.dict(os.environ, {
            'SPACETRACK_IDENTITY': 'fixture@example.invalid',
            'SPACETRACK_PASSWORD': 'fixture-password',
        }, clear=True)
        self.credentials.start()
        self.addCleanup(self.credentials.stop)

    def write_inputs(self, bind_hash: bool = True) -> None:
        encoded = (json.dumps(self.manifest, indent=2) + '\n').encode()
        self.manifest_path.write_bytes(encoded)
        if bind_hash:
            self.recipe['source_manifest_sha256'] = hashlib.sha256(encoded).hexdigest()
        self.recipe_path.write_text(json.dumps(self.recipe))

    def argv(self, output: Path | None = None) -> list[str]:
        return ['--recipe', str(self.recipe_path), '--manifest', str(self.manifest_path),
                '--output', str(output or self.output), '--delay-seconds', '0', '--retries', '0']

    def assert_preflight_rejected(self, output: Path | None = None) -> None:
        before = {path: path.read_bytes() for path in [self.output, self.sidecar] if path.exists()}
        with patch.object(M, 'login') as login, patch.object(M, 'request_json') as request:
            with redirect_stdout(io.StringIO()), self.assertRaises((M.MaterializationError, SystemExit)):
                M.main(self.argv(output))
            login.assert_not_called()
            request.assert_not_called()
        for path, original in before.items():
            self.assertEqual(path.read_bytes(), original)
        if not before:
            self.assertFalse(self.output.exists())
            self.assertFalse(self.sidecar.exists())

    def test_cli_requires_explicit_output_and_protects_frozen_destination(self) -> None:
        with patch.object(M, 'login') as login, patch('sys.stderr', io.StringIO()):
            with self.assertRaises(SystemExit):
                M.main(['--recipe', str(self.recipe_path), '--manifest', str(self.manifest_path)])
            login.assert_not_called()
        self.assert_preflight_rejected(M.DEFAULT_OUTPUT)

    def test_existing_output_or_sidecar_is_never_overwritten(self) -> None:
        for target in [self.output, self.sidecar]:
            with self.subTest(target=target.name):
                self.output.unlink(missing_ok=True)
                self.sidecar.unlink(missing_ok=True)
                target.write_bytes(b'preserved earlier materialisation\n')
                self.assert_preflight_rejected()
                self.assertEqual(target.read_bytes(), b'preserved earlier materialisation\n')

    def test_all_recipe_cases_are_checked_before_login(self) -> None:
        original = copy.deepcopy(self.recipe)
        mutations = [
            lambda value: value.update(source_manifest_sha256='0' * 64),
            lambda value: value.update(case_count=1),
            lambda value: value['cases'].pop(),
            lambda value: value['cases'].append(copy.deepcopy(value['cases'][0])),
            lambda value: value['cases'][1].update(case_id='unknown-case'),
            lambda value: value['cases'][1].update(object_id='49999'),
            lambda value: value['cases'][1].update(start_date='2026-01-02'),
            lambda value: value['cases'][1].update(end_date='2026-01-03'),
            lambda value: value['cases'][1].update(space_track_gp_history_query=query('49999')),
            lambda value: value['cases'][1].update(space_track_gp_history_query=query('40011').replace('https:', 'http:')),
            lambda value: value['cases'][1].update(space_track_gp_history_query=query('40011').replace('www.space-track.org', 'example.invalid')),
        ]
        for number, mutate in enumerate(mutations):
            self.recipe = copy.deepcopy(original)
            mutate(self.recipe)
            self.write_inputs(bind_hash=False)
            with self.subTest(mutation=number):
                self.assert_preflight_rejected()

    def test_duplicate_manifest_case_and_invalid_window_fail_before_login(self) -> None:
        original = copy.deepcopy(self.manifest)
        for mutate in [
            lambda value: value['cases'][1].update(case_id=value['cases'][0]['case_id']),
            lambda value: value['cases'][1].update(start_date='2026-02-30'),
            lambda value: value['cases'][1].update(end_date='2025-12-31'),
        ]:
            self.manifest = copy.deepcopy(original)
            mutate(self.manifest)
            self.write_inputs()
            self.assert_preflight_rejected()

    def test_invalid_cli_throttling_is_rejected_before_login(self) -> None:
        for option, value in [('--retries', '-1'), ('--delay-seconds', '-1'),
                              ('--delay-seconds', 'nan'), ('--backoff-seconds', 'inf')]:
            with self.subTest(option=option, value=value), patch.object(M, 'login') as login:
                with self.assertRaises(M.MaterializationError):
                    M.main(self.argv() + [option, value])
                login.assert_not_called()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.sidecar.exists())

    def test_destination_races_preserve_other_writers_and_remove_own_partial_output(self) -> None:
        original_destinations = M.output_destinations
        fixture_names = {self.manifest_path.name, self.recipe_path.name}
        for raced in [self.output, self.sidecar]:
            self.output.unlink(missing_ok=True)
            self.sidecar.unlink(missing_ok=True)

            def race(*args, **kwargs):
                destinations = original_destinations(*args, **kwargs)
                raced.write_bytes(b'concurrent writer data')
                return destinations

            with self.subTest(destination=raced.name), patch.object(M, 'output_destinations', side_effect=race):
                with self.assertRaises(M.MaterializationError):
                    M.write_output(self.output, b'{"synthetic":true}\n')
            self.assertEqual(raced.read_bytes(), b'concurrent writer data')
            other = self.sidecar if raced == self.output else self.output
            self.assertFalse(other.exists(), 'Failed publication must remove only its own file')
            self.assertEqual({path.name for path in self.directory.iterdir()}, fixture_names | {raced.name})

    def test_later_invalid_case_cannot_publish_a_partial_benchmark(self) -> None:
        for later in [[record('40011', MEAN_MOTION=None)], [], [record('49999')]]:
            with self.subTest(later=later), patch.object(M, 'login', return_value=object()) as login:
                with patch.object(M, 'request_json', side_effect=[[record()], later]) as request:
                    with redirect_stdout(io.StringIO()), self.assertRaises(M.MaterializationError):
                        M.main(self.argv())
                    self.assertEqual(login.call_count, 1)
                    self.assertEqual(request.call_count, 2)
                    self.assertFalse(self.output.exists())
                    self.assertFalse(self.sidecar.exists())

    def test_successful_offline_materialisation_has_version_and_matching_digest(self) -> None:
        old = record(CREATION_DATE='2026-01-02T01:00:00Z', ELEMENT_SET_NO='99')
        newest = record(CREATION_DATE='2026-01-02T02:00:00Z', ELEMENT_SET_NO='1', MEAN_MOTION='15.6')
        boundary = record(EPOCH='2026-01-03T00:00:00Z')
        second = {key.lower(): value for key, value in record('40011').items()}
        with patch.object(M, 'login', return_value=object()) as login:
            with patch.object(M, 'request_json', side_effect=[[old, boundary, newest], [second]]) as request:
                with redirect_stdout(io.StringIO()):
                    M.main(self.argv())
                login.assert_called_once_with('fixture@example.invalid', 'fixture-password')
                self.assertEqual(request.call_count, 2)
        encoded = self.output.read_bytes()
        saved = json.loads(encoded)
        self.assertEqual(saved['materializer_version'], '2.0')
        self.assertTrue(saved['record_selection_policy'])
        self.assertEqual([case['records'] for case in saved['cases']], [[newest], [second]])
        self.assertEqual([case['source_window']['record_count'] for case in saved['cases']], [1, 1])
        self.assertEqual([case['source_window']['raw_record_count'] for case in saved['cases']], [3, 1])
        self.assertEqual([case['source_window']['excluded_end_boundary_records'] for case in saved['cases']], [1, 0])
        self.assertEqual([case['source_window']['superseded_or_duplicate_records'] for case in saved['cases']], [1, 0])
        self.assertEqual(saved['manifest_sha256'], hashlib.sha256(self.manifest_path.read_bytes()).hexdigest())
        self.assertEqual(saved['materialization_recipe_sha256'], hashlib.sha256(self.recipe_path.read_bytes()).hexdigest())
        self.assertEqual(self.sidecar.read_text(), f'{hashlib.sha256(encoded).hexdigest()}  {self.output.name}\n')
        self.assertNotIn('fixture-password', encoded.decode())
        self.assertNotIn('fixture@example.invalid', encoded.decode())


if __name__ == '__main__':
    unittest.main()
