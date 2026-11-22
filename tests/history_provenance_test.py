#!/usr/bin/env python3
"""Verify retained-history acquisition evidence using an isolated loopback upstream."""
from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import json
import threading
import time
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timezone

from history_admission_test import Endpoint, MockHandler, OPENER, legacy_store, record


def canonical_value(value):
    # These fixtures use ordinary finite decimal values. PHP JSON encodes
    # integral floats as integers without JSON_PRESERVE_ZERO_FRACTION.
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: canonical_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical_value(item) for item in value]
    return value


def digest(value):
    raw = json.dumps(canonical_value(value), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def store_digest(store):
    payload = {key: store[key] for key in ('version', 'source', 'norad', 'intervals', 'records')}
    if store['version'] == 2:
        payload.update({key: store[key] for key in ('updated_at', 'provenance')})
    return digest(payload)


def sign_store(store):
    store['records_sha256'] = digest(store['records'])
    store['store_sha256'] = store_digest(store)
    return store


def request_with_flags(endpoint, **flags):
    query = urllib.parse.urlencode({
        'norad': '41000', 'start': '2026-01-01', 'end': '2026-01-05', **flags,
    })
    try:
        response = OPENER.open(f'http://127.0.0.1:{endpoint.port}/history.php?{query}', timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, dict(response.headers), json.load(response)


class ProvenanceTests(unittest.TestCase):
    def payload(self, response, status=200):
        self.assertEqual(response[0], status, response[2])
        return response[2]

    def store(self, endpoint):
        path = endpoint.cache / 'gp-history-41000.json'
        return path, json.loads(path.read_text())

    def assert_clean(self, endpoint):
        self.assertEqual(
            [name for name in endpoint.files() if name.startswith('st-cookie') or name.endswith('.tmp')],
            [],
        )

    def assert_timestamp(self, value):
        self.assertIsInstance(value, str)
        self.assertRegex(value, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        self.assertEqual(parsed.tzinfo, timezone.utc)
        return parsed

    def assert_envelope(self, payload, store, start='2026-01-01', end='2026-01-05'):
        evidence = payload['data_provenance']
        self.assertEqual(set(evidence), {
            'schema_version', 'provider', 'source_class', 'policy', 'norad',
            'requested_range', 'records_sha256', 'cache_snapshot_sha256',
            'cache_updated_at', 'retrieval_status', 'acquisitions',
        })
        self.assertEqual(evidence['schema_version'], 1)
        self.assertEqual(evidence['provider'], 'Space-Track')
        self.assertEqual(evidence['source_class'], 'GP_HISTORY')
        self.assertEqual(evidence['policy'], 'retained-history-v1')
        self.assertEqual(evidence['norad'], '41000')
        self.assertEqual(evidence['requested_range'], {'start': start, 'end': end})
        self.assertEqual(evidence['records_sha256'], digest(payload['records']))
        self.assertEqual(evidence['cache_snapshot_sha256'], store_digest(store))
        self.assert_timestamp(payload['served_at'])
        for acquisition in evidence['acquisitions']:
            self.assertEqual(set(acquisition), {
                'kind', 'source_class', 'start', 'end', 'retrieved_at', 'records_sha256',
            })
            self.assertEqual(acquisition['source_class'], 'GP_HISTORY')
            self.assertIn(acquisition['kind'], ('upstream-fetch', 'legacy-cache'))
            self.assertRegex(acquisition['records_sha256'], r'^[a-f0-9]{64}$')
            self.assertLessEqual(acquisition['start'], end)
            self.assertGreaterEqual(acquisition['end'], start)
            if acquisition['kind'] == 'upstream-fetch':
                self.assert_timestamp(acquisition['retrieved_at'])
            else:
                self.assertIsNone(acquisition['retrieved_at'])
        return evidence

    def test_new_acquisition_is_persisted_and_cache_hits_do_not_redate_it(self):
        with Endpoint() as endpoint:
            began = datetime.now(timezone.utc).replace(microsecond=0)
            first = self.payload(endpoint.request())
            path, store = self.store(endpoint)
            original = path.read_bytes()
            self.assertEqual(store['version'], 2)
            evidence = self.assert_envelope(first, store)
            self.assertEqual(evidence['retrieval_status'], 'recorded')
            self.assertEqual(len(evidence['acquisitions']), 1)
            acquisition = evidence['acquisitions'][0]
            self.assertEqual(acquisition['records_sha256'], digest(first['records']))
            self.assertEqual(first['retrieved_at'], acquisition['retrieved_at'])
            self.assertGreaterEqual(self.assert_timestamp(first['retrieved_at']), began)
            self.assertEqual(evidence['cache_updated_at'], store['updated_at'])
            self.assertEqual(store['store_sha256'], store_digest(store))

            # Cross a real wall-clock second to distinguish serving from acquisition.
            time.sleep(1.05)
            second = self.payload(endpoint.request())
            self.assertTrue(second['cached'])
            self.assertEqual(second['data_provenance'], evidence)
            self.assertEqual(second['retrieved_at'], first['retrieved_at'])
            self.assertGreater(second['served_at'], first['served_at'])
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(endpoint.state.snapshot()), 2)
            self.assert_clean(endpoint)

    def test_extension_retains_old_acquisitions_and_changes_snapshot_identity(self):
        with Endpoint() as endpoint:
            first = self.payload(endpoint.request(end='2026-01-02'))
            first_evidence = first['data_provenance']
            initial_acquisition = copy.deepcopy(first_evidence['acquisitions'][0])
            extended = self.payload(endpoint.request())
            _, store = self.store(endpoint)
            evidence = self.assert_envelope(extended, store)
            self.assertEqual(len(evidence['acquisitions']), 2)
            self.assertEqual(evidence['acquisitions'][0], initial_acquisition)
            self.assertEqual(evidence['acquisitions'][1]['start'], '2026-01-03')
            self.assertEqual(evidence['acquisitions'][1]['end'], '2026-01-05')
            self.assertNotEqual(evidence['cache_snapshot_sha256'], first_evidence['cache_snapshot_sha256'])
            calls = endpoint.state.snapshot()
            self.assertEqual([call['start'][:10] for call in calls if call['operation'] == 'history'], ['2026-01-01', '2026-01-03'])

            old_range = self.payload(endpoint.request(end='2026-01-02'))
            selected = self.assert_envelope(old_range, store, end='2026-01-02')
            self.assertEqual(selected['acquisitions'], [initial_acquisition])
            self.assertEqual(selected['records_sha256'], first_evidence['records_sha256'])
            self.assertEqual(selected['cache_snapshot_sha256'], evidence['cache_snapshot_sha256'])
            self.assertEqual(old_range['retrieved_at'], initial_acquisition['retrieved_at'])
            self.assertEqual(len(endpoint.state.snapshot()), 4)
            self.assert_clean(endpoint)

    def test_covered_empty_subrange_has_acquisition_evidence(self):
        with Endpoint() as endpoint:
            first = self.payload(endpoint.request())
            empty = self.payload(endpoint.request(start='2026-01-02', end='2026-01-03'))
            _, store = self.store(endpoint)
            evidence = self.assert_envelope(empty, store, start='2026-01-02', end='2026-01-03')
            self.assertEqual(empty['records'], [])
            self.assertEqual(evidence['records_sha256'], digest([]))
            self.assertEqual(evidence['retrieval_status'], 'recorded')
            self.assertEqual(evidence['acquisitions'], first['data_provenance']['acquisitions'])
            self.assertEqual(len(endpoint.state.snapshot()), 2)

    def test_legacy_reads_report_unknown_retrieval_and_preserve_bytes(self):
        for signed in (False, True):
            with self.subTest(signed=signed), Endpoint(credentials=False) as endpoint:
                store = legacy_store('41000')
                if signed:
                    sign_store(store)
                path = endpoint.cache / 'gp-history-41000.json'
                path.write_text(json.dumps(store, separators=(',', ':')))
                original = path.read_bytes()
                payload = self.payload(endpoint.request())
                evidence = self.assert_envelope(payload, store)
                self.assertEqual(evidence['retrieval_status'], 'legacy-unknown')
                self.assertIsNone(evidence['cache_updated_at'])
                self.assertIsNone(payload['retrieved_at'])
                self.assertTrue(evidence['acquisitions'])
                self.assertTrue(all(item['kind'] == 'legacy-cache' for item in evidence['acquisitions']))
                self.assertTrue(all(item['retrieved_at'] is None for item in evidence['acquisitions']))
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(endpoint.state.snapshot(), [])
                self.assert_clean(endpoint)

    def test_legacy_extension_separates_unknown_and_known_coverage(self):
        with Endpoint() as endpoint:
            path = endpoint.put_store('41000', intervals=[{'start': '2026-01-01', 'end': '2026-01-02'}])
            old_records = json.loads(path.read_text())['records']
            mixed = self.payload(endpoint.request())
            _, store = self.store(endpoint)
            evidence = self.assert_envelope(mixed, store)
            self.assertEqual(store['version'], 2)
            self.assertEqual(evidence['retrieval_status'], 'partial')
            self.assertIsNone(mixed['retrieved_at'])
            self.assertEqual([item['kind'] for item in evidence['acquisitions']], ['legacy-cache', 'upstream-fetch'])
            self.assertEqual(evidence['acquisitions'][0]['records_sha256'], digest(old_records))

            old = self.payload(endpoint.request(end='2026-01-02'))
            new = self.payload(endpoint.request(start='2026-01-03'))
            self.assertEqual(old['data_provenance']['retrieval_status'], 'legacy-unknown')
            self.assertIsNone(old['retrieved_at'])
            self.assertEqual(new['data_provenance']['retrieval_status'], 'recorded')
            self.assertEqual(new['retrieved_at'], evidence['acquisitions'][1]['retrieved_at'])
            self.assertEqual(len(endpoint.state.snapshot()), 2)
            self.assert_clean(endpoint)

    def test_age_and_refresh_flags_cannot_trigger_historical_redownload(self):
        with Endpoint() as endpoint:
            self.payload(endpoint.request())
            path, store = self.store(endpoint)
            store['updated_at'] = '2026-02-01T00:00:00Z'
            for acquisition in store['provenance']['acquisitions']:
                acquisition['retrieved_at'] = store['updated_at']
            sign_store(store)
            path.write_text(json.dumps(store, separators=(',', ':')))
            original = path.read_bytes()
            for flags in ({}, {'refresh': '1'}, {'force': '1'}, {'revalidate': '1'}, {'cache': 'bypass'}):
                with self.subTest(flags=flags):
                    payload = self.payload(request_with_flags(endpoint, **flags))
                    self.assertTrue(payload['cached'])
                    self.assertEqual(payload['retrieved_at'], '2026-02-01T00:00:00Z')
                    self.assertEqual(payload['data_provenance']['cache_snapshot_sha256'], store['store_sha256'])
                    self.assertEqual(path.read_bytes(), original)
                    self.assertEqual(len(endpoint.state.snapshot()), 2)
                    self.assert_clean(endpoint)

    def test_provenance_and_update_time_are_covered_by_store_integrity(self):
        with Endpoint() as endpoint:
            self.payload(endpoint.request())
            path, original = self.store(endpoint)
            variants = []
            changed = copy.deepcopy(original)
            changed['updated_at'] = '2026-01-01T00:00:00Z'
            variants.append(changed)
            changed = copy.deepcopy(original)
            changed['provenance']['acquisitions'][0]['retrieved_at'] = '2026-01-01T00:00:00Z'
            variants.append(changed)
            changed = copy.deepcopy(original)
            changed['provenance']['acquisitions'][0]['records_sha256'] = '0' * 64
            variants.append(changed)
            for key in ('provenance', 'updated_at', 'records_sha256', 'store_sha256'):
                changed = copy.deepcopy(original)
                del changed[key]
                variants.append(changed)
            for index, changed in enumerate(variants):
                with self.subTest(change=index):
                    path.write_text(json.dumps(changed, separators=(',', ':')))
                    bad_bytes = path.read_bytes()
                    self.payload(endpoint.request(), 502)
                    self.assertEqual(path.read_bytes(), bad_bytes)
                    self.assertEqual(len(endpoint.state.snapshot()), 2)
                    self.assert_clean(endpoint)

    def test_resigned_malformed_provenance_still_fails_validation(self):
        with Endpoint() as endpoint:
            self.payload(endpoint.request())
            path, original = self.store(endpoint)
            variants = []
            for field, value in (
                ('kind', 'unknown'), ('source_class', 'GP'), ('retrieved_at', None),
                ('retrieved_at', '2026-02-30T12:00:00Z'), ('retrieved_at', '2026-01-01T12:00:00'),
                ('retrieved_at', '2026-01-01T12:00:00+00:00'), ('records_sha256', 'invalid'),
                ('start', '2026-01-02'), ('end', '2026-01-06'),
            ):
                changed = copy.deepcopy(original)
                changed['provenance']['acquisitions'][0][field] = value
                variants.append(changed)
            changed = copy.deepcopy(original)
            changed['provenance']['acquisitions'] = []
            variants.append(changed)
            changed = copy.deepcopy(original)
            changed['provenance']['acquisitions'] *= 2
            variants.append(changed)
            changed = copy.deepcopy(original)
            changed['provenance']['acquisitions'][0]['unexpected'] = True
            variants.append(changed)
            for field, value in (('schema_version', 2), ('policy', 'automatic-refresh')):
                changed = copy.deepcopy(original)
                changed['provenance'][field] = value
                variants.append(changed)
            changed = copy.deepcopy(original)
            changed['updated_at'] = '9999-12-31T23:59:59Z'
            variants.append(changed)
            changed = copy.deepcopy(original)
            changed['provenance']['acquisitions'][0]['retrieved_at'] = '9999-12-31T23:59:59Z'
            variants.append(changed)
            changed = copy.deepcopy(original)
            changed['provenance']['acquisitions'][0]['kind'] = 'legacy-cache'
            variants.append(changed)
            for index, changed in enumerate(variants):
                with self.subTest(change=index):
                    sign_store(changed)
                    path.write_text(json.dumps(changed, separators=(',', ':')))
                    bad_bytes = path.read_bytes()
                    self.payload(endpoint.request(), 502)
                    self.assertEqual(path.read_bytes(), bad_bytes)
                    self.assertEqual(len(endpoint.state.snapshot()), 2)
                    self.assert_clean(endpoint)

    def test_orphan_records_cannot_gain_false_acquisition_evidence(self):
        orphan = record('41000', '2026-01-06T12:00:00Z')
        with Endpoint() as endpoint:
            self.payload(endpoint.request())
            path, store = self.store(endpoint)
            store['records'].append(orphan)
            sign_store(store)
            path.write_text(json.dumps(store, separators=(',', ':')))
            original = path.read_bytes()
            self.payload(endpoint.request(), 502)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(endpoint.state.snapshot()), 2)
            self.assert_clean(endpoint)

        with Endpoint() as endpoint:
            path = endpoint.put_store('41000', records=[record('41000'), orphan])
            original = path.read_bytes()
            cached = self.payload(endpoint.request())
            self.assertEqual(cached['data_provenance']['retrieval_status'], 'legacy-unknown')
            self.payload(endpoint.request(end='2026-01-06'), 502)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(endpoint.state.snapshot(), [])
            self.assert_clean(endpoint)

    def test_acquisition_capacity_rejects_extension_before_upstream_work(self):
        with Endpoint({'MAX_HISTORY_ACQUISITIONS': 1}) as endpoint:
            self.payload(endpoint.request(end='2026-01-02'))
            path, _ = self.store(endpoint)
            original = path.read_bytes()
            self.payload(endpoint.request(), 413)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(endpoint.state.snapshot()), 2)
            self.payload(endpoint.request(end='2026-01-02'))
            self.assertEqual(path.read_bytes(), original)
            self.assert_clean(endpoint)

    def test_late_fragment_failure_does_not_commit_partial_acquisition_evidence(self):
        class LastFragmentFails(MockHandler):
            def send_json(self, status, payload):
                if self.command == 'GET' and '/EPOCH/2026-01-05T' in urllib.parse.unquote(self.path):
                    super().send_json(500, {'error': 'intentional final-fragment failure'})
                else:
                    super().send_json(status, payload)

        with Endpoint() as endpoint:
            intervals = [{'start': f'2026-01-{day:02d}', 'end': f'2026-01-{day:02d}'} for day in (2, 4)]
            records = [record('41000', f'2026-01-{day:02d}T12:00:00Z') for day in (2, 4)]
            path = endpoint.put_store('41000', intervals=intervals, records=records)
            original = path.read_bytes()
            endpoint.upstream.RequestHandlerClass = LastFragmentFails
            self.payload(endpoint.request(), 502)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(endpoint.state.snapshot()), 4)
            self.assert_clean(endpoint)

            endpoint.upstream.RequestHandlerClass = MockHandler
            payload = self.payload(endpoint.request())
            _, store = self.store(endpoint)
            evidence = self.assert_envelope(payload, store)
            self.assertEqual(len(evidence['acquisitions']), 5)
            self.assertEqual(sum(item['kind'] == 'upstream-fetch' for item in evidence['acquisitions']), 3)
            self.assertEqual(len(endpoint.state.snapshot()), 8)
            self.assert_clean(endpoint)

    def test_failed_store_commit_keeps_legacy_data_and_provenance_unmodified(self):
        with Endpoint() as endpoint:
            path = endpoint.put_store('41000', intervals=[{'start': '2026-01-01', 'end': '2026-01-02'}])
            original = path.read_bytes()
            staging = endpoint.cache / 'history-write.tmp'
            staging.mkdir()
            self.payload(endpoint.request(), 503)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(endpoint.state.snapshot()), 2)
            staging.rmdir()
            self.assert_clean(endpoint)
            payload = self.payload(endpoint.request())
            self.assertEqual(payload['data_provenance']['retrieval_status'], 'partial')
            self.assertEqual(len(payload['data_provenance']['acquisitions']), 2)
            self.assert_clean(endpoint)

    def test_concurrent_identical_requests_record_one_acquisition(self):
        with Endpoint() as endpoint:
            endpoint.state.history_delay = 0.1
            barrier = threading.Barrier(2)

            def request():
                barrier.wait(timeout=3)
                return endpoint.request()

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: request(), range(2)))
            payloads = [self.payload(response) for response in responses]
            _, store = self.store(endpoint)
            self.assertEqual(sorted(item['cached'] for item in payloads), [False, True])
            self.assertEqual(payloads[0]['data_provenance'], payloads[1]['data_provenance'])
            self.assertEqual(len(store['provenance']['acquisitions']), 1)
            self.assertEqual(len(endpoint.state.snapshot()), 2)
            self.assert_clean(endpoint)


if __name__ == '__main__':
    unittest.main(verbosity=2)
