#!/usr/bin/env python3
"""Exercise history admission against a local upstream, never a real account."""
from __future__ import annotations

import copy
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from history_cache_integrity_test import free_port, valid_legacy_store

ROOT = Path(__file__).resolve().parents[1]


class HistoryBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.document_root = cls.directory / 'www'
        cls.cache = cls.directory / 'cache'
        cls.document_root.mkdir()
        cls.cache.mkdir()
        cls.upstream_body = []
        cls.upstream_calls = 0

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                pass

            def respond(self, payload) -> None:
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                self.respond({'ok': True})

            def do_GET(self) -> None:
                cls.upstream_calls += 1
                self.respond(cls.upstream_body)

        cls.upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        cls.upstream_thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.upstream_thread.start()
        source = (ROOT / 'history.php').read_text()
        source = source.replace('https://www.space-track.org', f'http://127.0.0.1:{cls.upstream.server_port}')
        source = source.replace('CURLOPT_PROTOCOLS => CURLPROTO_HTTPS', 'CURLOPT_PROTOCOLS => CURLPROTO_HTTP')
        source = source.replace('CURLOPT_REDIR_PROTOCOLS => CURLPROTO_HTTPS', 'CURLOPT_REDIR_PROTOCOLS => CURLPROTO_HTTP')
        (cls.document_root / 'history.php').write_text(source)
        cls.port = free_port()
        env = os.environ.copy()
        env.update({
            'SPACETRACK_IDENTITY': 'fixture@example.invalid',
            'SPACETRACK_PASSWORD': 'fixture-password',
            'SATELLITE_HISTORY_CACHE_DIR': str(cls.cache),
        })
        # A single owned process avoids leaving PHP worker children behind.
        env.pop('PHP_CLI_SERVER_WORKERS', None)
        cls.server = subprocess.Popen(
            ['php', '-d', 'display_errors=1', '-S', f'127.0.0.1:{cls.port}', '-t', str(cls.document_root)],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', cls.port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.03)
        else:
            cls.tearDownClass()
            raise RuntimeError('PHP test server did not start')

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.terminate()
        try:
            cls.server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait(timeout=3)
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.upstream_thread.join(timeout=3)
        cls.temp.cleanup()

    def setUp(self) -> None:
        for item in self.cache.iterdir():
            item.unlink()
        type(self).upstream_body = [valid_legacy_store()['records'][0]]
        type(self).upstream_calls = 0

    def request(self, query: dict | None = None, raw_query: str | None = None) -> tuple[int, dict]:
        query = query or {'norad': '40010', 'start': '2026-01-01', 'end': '2026-01-02'}
        url = f'http://127.0.0.1:{self.port}/history.php?' + (raw_query if raw_query is not None else urllib.parse.urlencode(query))
        try:
            response = urllib.request.urlopen(url, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read().decode()
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self.fail(f'Endpoint returned non-JSON output: {body[:500]!r}')
            return int(response.status), payload

    def assert_upstream_rejected(self, body) -> None:
        # Each validation subcase has an independent cache and admission budget.
        # The admission suite separately checks cumulative accounting.
        for item in self.cache.iterdir():
            item.unlink()
        type(self).upstream_body = body
        status, payload = self.request()
        self.assertEqual(status, 502, payload)
        self.assertFalse(payload['ok'])
        self.assertFalse((self.cache / 'gp-history-40010.json').exists(), 'Invalid data must not mark the interval covered')
        self.assertEqual(list(self.cache.glob('st-cookie-*')), [], 'Temporary login cookies must be removed')

    def test_error_object_is_not_cached_as_empty_history(self) -> None:
        self.assert_upstream_rejected({'error': 'Session expired'})

    def test_empty_object_is_not_an_empty_record_list(self) -> None:
        self.assert_upstream_rejected({})

    def test_malformed_row_does_not_make_a_partial_interval_complete(self) -> None:
        self.assert_upstream_rejected([self.upstream_body[0], 'invalid row'])

    def test_wrong_object_is_not_silently_dropped(self) -> None:
        record = copy.deepcopy(self.upstream_body[0])
        record['NORAD_CAT_ID'] = '49999'
        self.assert_upstream_rejected([record])

    def test_epoch_must_be_an_absolute_valid_calendar_time(self) -> None:
        for epoch in ['yesterday', '2026-01-00T12:00:00Z', '2026-02-30T12:00:00Z', '2026-01-01T24:00:00Z', []]:
            with self.subTest(epoch=epoch):
                record = copy.deepcopy(self.upstream_body[0])
                record['EPOCH'] = epoch
                self.assert_upstream_rejected([record])

    def test_invalid_orbital_fields_are_not_cached(self) -> None:
        base = valid_legacy_store()['records'][0]
        cases = [('MEAN_MOTION', 0), ('MEAN_MOTION', None), ('ECCENTRICITY', 1), ('ECCENTRICITY', ''), ('INCLINATION', -1), ('RA_OF_ASC_NODE', 360), ('ARG_OF_PERICENTER', []), ('MEAN_ANOMALY', False)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                record = {**base, field: value}
                self.assert_upstream_rejected([record])
        missing = dict(base)
        del missing['MEAN_MOTION']
        self.assert_upstream_rejected([missing])

    def test_record_outside_requested_query_is_rejected(self) -> None:
        record = copy.deepcopy(self.upstream_body[0])
        record['EPOCH'] = '2025-12-31T23:59:59Z'
        self.assert_upstream_rejected([record])

    def test_invalid_creation_time_is_rejected(self) -> None:
        record = copy.deepcopy(self.upstream_body[0])
        record['CREATION_DATE'] = 'tomorrow'
        self.assert_upstream_rejected([record])

    def test_legitimate_empty_history_is_cached(self) -> None:
        type(self).upstream_body = []
        status, payload = self.request()
        self.assertEqual((status, payload['count'], payload['cached']), (200, 0, False))
        status, payload = self.request()
        self.assertEqual((status, payload['count'], payload['cached']), (200, 0, True))
        self.assertEqual(self.upstream_calls, 1)

    def test_inclusive_upstream_end_boundary_is_not_stored_for_next_day(self) -> None:
        boundary = {**self.upstream_body[0], 'EPOCH': '2026-01-03T00:00:00Z'}
        type(self).upstream_body = [self.upstream_body[0], boundary]
        status, payload = self.request()
        self.assertEqual((status, payload['count']), (200, 1))
        stored = json.loads((self.cache / 'gp-history-40010.json').read_text())
        self.assertEqual(len(stored['records']), 1)

    def test_newer_creation_time_wins_over_larger_old_element_set(self) -> None:
        newer = {**self.upstream_body[0], 'CREATION_DATE': '2026-01-02T02:00:00Z', 'ELEMENT_SET_NO': 1, 'GP_ID': 20}
        older = {**newer, 'CREATION_DATE': '2026-01-02T01:00:00Z', 'ELEMENT_SET_NO': 99, 'GP_ID': 10}
        type(self).upstream_body = [newer, older]
        status, payload = self.request()
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload['records'][0]['GP_ID'], 20)

    def test_equivalent_epoch_timezones_are_one_record(self) -> None:
        first = {**self.upstream_body[0], 'EPOCH': '2026-01-01T12:00:00.123456Z', 'GP_ID': 10}
        corrected = {**first, 'EPOCH': '2026-01-01T13:00:00.123456+01:00', 'CREATION_DATE': '2026-01-01T15:00:00Z', 'GP_ID': 20}
        type(self).upstream_body = [first, corrected]
        status, payload = self.request()
        self.assertEqual((status, payload['count']), (200, 1))
        self.assertEqual(payload['records'][0]['GP_ID'], 20)

    def test_distinct_microseconds_remain_distinct_and_sorted(self) -> None:
        first = {**self.upstream_body[0], 'EPOCH': '2026-01-01T12:00:00.123456Z'}
        second = {**first, 'EPOCH': '2026-01-01T12:00:00.123457Z'}
        type(self).upstream_body = [second, first]
        status, payload = self.request()
        self.assertEqual((status, payload['count']), (200, 2))
        self.assertEqual([row['EPOCH'] for row in payload['records']], [first['EPOCH'], second['EPOCH']])

    def test_creation_times_compare_utc_instants(self) -> None:
        newer = {**self.upstream_body[0], 'CREATION_DATE': '2026-01-02T02:00:00Z', 'GP_ID': 20}
        older = {**newer, 'CREATION_DATE': '2026-01-02T03:00:00+02:00', 'GP_ID': 10}
        type(self).upstream_body = [newer, older]
        status, payload = self.request()
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload['records'][0]['GP_ID'], 20)

    def test_unresolved_conflicting_solutions_reach_browser_integrity_checks(self) -> None:
        first = dict(self.upstream_body[0])
        conflicting = {**first, 'MEAN_MOTION': '15.6'}
        type(self).upstream_body = [first, conflicting, first]
        status, payload = self.request()
        self.assertEqual((status, payload['count']), (200, 2))
        self.assertEqual({row['MEAN_MOTION'] for row in payload['records']}, {'15.5', '15.6'})
        status, payload = self.request()
        self.assertEqual((status, payload['count'], payload['cached']), (200, 2, True))

    def test_newer_revision_resolves_all_older_alternatives(self) -> None:
        first = dict(self.upstream_body[0])
        conflicting = {**first, 'MEAN_MOTION': '15.6'}
        newest = {**first, 'CREATION_DATE': '2026-01-02T00:00:00Z', 'GP_ID': 20}
        type(self).upstream_body = [first, conflicting, newest]
        status, payload = self.request()
        self.assertEqual((status, payload['count']), (200, 1))
        self.assertEqual(payload['records'][0]['GP_ID'], 20)

    def test_catalogue_identifier_tiebreak_does_not_lose_integer_precision(self) -> None:
        older = {**self.upstream_body[0], 'GP_ID': '9007199254740992'}
        newer = {**older, 'GP_ID': '9007199254740993'}
        type(self).upstream_body = [newer, older]
        status, payload = self.request()
        self.assertEqual((status, payload['count']), (200, 1))
        self.assertEqual(payload['records'][0]['GP_ID'], newer['GP_ID'])

    def test_failed_missing_interval_leaves_existing_cache_untouched(self) -> None:
        store = valid_legacy_store()
        store['intervals'][0]['end'] = '2026-01-01'
        cache_file = self.cache / 'gp-history-40010.json'
        original = json.dumps(store)
        cache_file.write_text(original)
        type(self).upstream_body = {'error': 'Session expired'}
        status, payload = self.request()
        self.assertEqual(status, 502, payload)
        self.assertEqual(cache_file.read_text(), original)

    def test_bad_upstream_response_can_be_retried_with_valid_history(self) -> None:
        self.assert_upstream_rejected({'error': 'Temporary upstream failure'})
        type(self).upstream_body = [valid_legacy_store()['records'][0]]
        status, payload = self.request()
        self.assertEqual((status, payload['count'], payload['cached']), (200, 1, False))

    def test_full_upstream_limit_is_not_treated_as_complete(self) -> None:
        type(self).upstream_body = self.upstream_body * 5000
        status, payload = self.request()
        self.assertEqual(status, 413, payload)
        self.assertFalse((self.cache / 'gp-history-40010.json').exists())

    def test_invalid_cached_epoch_fails_closed(self) -> None:
        store = valid_legacy_store()
        store['records'][0]['EPOCH'] = '2026-02-30T12:00:00Z'
        (self.cache / 'gp-history-40010.json').write_text(json.dumps(store))
        status, payload = self.request()
        self.assertEqual(status, 502, payload)
        self.assertFalse(payload['ok'])
        self.assertEqual(self.upstream_calls, 0)

    def test_leading_zero_catalogue_id_reuses_canonical_cache(self) -> None:
        store = valid_legacy_store()
        (self.cache / 'gp-history-40010.json').write_text(json.dumps(store))
        status, payload = self.request({'norad': '0040010', 'start': '2026-01-01', 'end': '2026-01-02'})
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload['cached'])
        self.assertEqual(payload['norad'], '40010')
        self.assertEqual(self.upstream_calls, 0)

    def test_array_query_values_return_clean_json_errors(self) -> None:
        for field in ['norad', 'start', 'end']:
            with self.subTest(field=field):
                values = {'norad': '40010', 'start': '2026-01-01', 'end': '2026-01-02'}
                raw = '&'.join(urllib.parse.urlencode({key + ('[]' if key == field else ''): value}) for key, value in values.items())
                status, payload = self.request(raw_query=raw)
                self.assertEqual(status, 400, payload)
                self.assertFalse(payload['ok'])

    def test_zero_catalogue_id_is_rejected(self) -> None:
        status, payload = self.request({'norad': '000', 'start': '2026-01-01', 'end': '2026-01-02'})
        self.assertEqual(status, 400, payload)
        self.assertFalse(payload['ok'])


if __name__ == '__main__':
    unittest.main()
