#!/usr/bin/env python3
"""Loopback-only admission, resource-bound and upstream-accounting regressions."""
from __future__ import annotations

import concurrent.futures
import contextlib
import fcntl
import hashlib
import json
import os
import re
import signal
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

ROOT = Path(__file__).resolve().parents[1]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def record(norad: str, epoch: str = '2026-01-01T12:00:00.123456Z', padding: int = 0) -> dict:
    result = {
        'NORAD_CAT_ID': norad, 'EPOCH': epoch, 'CREATION_DATE': epoch,
        'ELEMENT_SET_NO': 1, 'MEAN_MOTION': 15.5, 'ECCENTRICITY': 0.001,
        'INCLINATION': 51.6, 'RA_OF_ASC_NODE': 10.0,
        'ARG_OF_PERICENTER': 20.0, 'MEAN_ANOMALY': 30.0,
    }
    if padding:
        result['TEST_PADDING'] = 'x' * padding
    return result


def legacy_store(norad: str, intervals=None, records=None) -> dict:
    return {
        'version': 1, 'source': 'Space-Track GP_History', 'norad': norad,
        'intervals': intervals if intervals is not None else [{'start': '2026-01-01', 'end': '2026-01-05'}],
        'records': records if records is not None else [record(norad)],
        'updated_at': '2026-01-06T00:00:00Z',
    }


class MockState:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = []
        self.login_status = 200
        self.history_status = 200
        self.login_delay = 0.0
        self.history_delay = 0.0
        self.padding = 0

    def snapshot(self):
        with self.lock:
            return [item.copy() for item in self.calls]


class MockHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_args):
        pass

    def send_json(self, status, payload):
        body = json.dumps(payload, separators=(',', ':')).encode()
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.close_connection = True
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        if self.path != '/ajaxauth/login':
            self.send_json(404, {'error': 'unexpected mock route'})
            return
        length = int(self.headers.get('Content-Length', '0'))
        self.rfile.read(length)
        state = self.server.state
        with state.lock:
            state.calls.append({'operation': 'login'})
            status, delay = state.login_status, state.login_delay
        if delay:
            time.sleep(delay)
        self.send_json(status, {'ok': status == 200})

    def do_GET(self):
        match = re.search(r'/NORAD_CAT_ID/([0-9]+)/EPOCH/([^/]+)/orderby/', urllib.parse.unquote(self.path))
        if not match or '--' not in match[2]:
            self.send_json(404, {'error': 'unexpected mock route'})
            return
        norad = match[1]
        start, end = match[2].split('--', 1)
        state = self.server.state
        with state.lock:
            state.calls.append({'operation': 'history', 'norad': norad, 'start': start, 'end': end})
            status, delay, padding = state.history_status, state.history_delay, state.padding
        if delay:
            time.sleep(delay)
        if status != 200:
            self.send_json(status, {'error': 'intentional mock failure'})
            return
        epoch = start.replace('T00:00:00', 'T12:00:00.123456Z')
        self.send_json(200, [record(norad, epoch, padding)])


class Endpoint:
    def __init__(self, constants=None, *, credentials=True):
        self.constants = constants or {}
        self.credentials = credentials
        self.state = MockState()

    def __enter__(self):
        try:
            return self.start()
        except BaseException:
            self.__exit__()
            raise

    def start(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.document_root = self.root / 'www'
        self.document_root.mkdir()
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.upstream = ThreadingHTTPServer(('127.0.0.1', 0), MockHandler)
        self.upstream.state = self.state
        self.upstream_thread = threading.Thread(target=lambda: self.upstream.serve_forever(poll_interval=0.02), daemon=True)
        self.upstream_thread.start()
        source = (ROOT / 'history.php').read_text()
        source = source.replace('https://www.space-track.org', f'http://127.0.0.1:{self.upstream.server_port}')
        source = source.replace('CURLOPT_PROTOCOLS => CURLPROTO_HTTPS', 'CURLOPT_PROTOCOLS => CURLPROTO_HTTP')
        source = source.replace('CURLOPT_REDIR_PROTOCOLS => CURLPROTO_HTTPS', 'CURLOPT_REDIR_PROTOCOLS => CURLPROTO_HTTP')
        if 'https://www.space-track.org' in source:
            raise AssertionError('A real upstream URL survived isolation')
        for name, value in self.constants.items():
            source, count = re.subn(r'^const ' + re.escape(name) + r' = [^;\n]+;', f'const {name} = {value};', source, flags=re.MULTILINE)
            if count != 1:
                raise AssertionError(f'Missing or ambiguous test limit {name}')
        (self.document_root / 'history.php').write_text(source)
        env = os.environ.copy()
        for key in ('SPACETRACK_IDENTITY', 'SPACETRACK_PASSWORD', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
            env.pop(key, None)
        env.update({'SATELLITE_HISTORY_CACHE_DIR': str(self.cache), 'PHP_CLI_SERVER_WORKERS': '4', 'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost'})
        if self.credentials:
            env.update({'SPACETRACK_IDENTITY': 'test@example.invalid', 'SPACETRACK_PASSWORD': 'test-only-password'})
        self.port = free_port()
        self.log = (self.root / 'php.log').open('wb')
        self.server = subprocess.Popen(['php', '-S', f'127.0.0.1:{self.port}', '-t', str(self.document_root)], cwd=self.document_root, env=env, stdout=self.log, stderr=self.log, start_new_session=True)
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', self.port), timeout=0.05):
                    return self
            except OSError:
                if self.server.poll() is not None:
                    raise RuntimeError('PHP test server exited before startup')
                time.sleep(0.02)
        raise RuntimeError('PHP test server did not start')

    def __exit__(self, *_exc):
        if hasattr(self, 'server'):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.server.pid, signal.SIGTERM)
            try:
                self.server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.server.pid, signal.SIGKILL)
                self.server.wait(timeout=3)
        if hasattr(self, 'log'):
            self.log.close()
        if hasattr(self, 'upstream_thread'):
            self.upstream.shutdown()
            self.upstream.server_close()
            self.upstream_thread.join(timeout=1)
        if hasattr(self, 'temporary'):
            self.temporary.cleanup()

    def request(self, norad='41000', start='2026-01-01', end='2026-01-05'):
        query = urllib.parse.urlencode({'norad': norad, 'start': start, 'end': end})
        began = time.monotonic()
        try:
            response = OPENER.open(f'http://127.0.0.1:{self.port}/history.php?{query}', timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read().decode()
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as error:
                raise AssertionError(f'Endpoint returned non-JSON HTTP {response.status}: {body[:1000]}') from error
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, headers, payload, time.monotonic() - began

    def put_store(self, norad, *, intervals=None, records=None, extra_whitespace=0):
        path = self.cache / f'gp-history-{norad}.json'
        path.write_text(json.dumps(legacy_store(norad, intervals, records), separators=(',', ':')) + ' ' * extra_whitespace)
        return path

    @contextlib.contextmanager
    def held_lock(self, name):
        with (self.cache / name).open('a+b') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield
            fcntl.flock(handle, fcntl.LOCK_UN)

    def files(self):
        return sorted(path.name for path in self.cache.iterdir())


CLIENT_KEY = hashlib.sha256(b'127.0.0.1').hexdigest()
UPSTREAM_LEDGER = 'upstream-limits.json'


def ledger(version, counts=None, *, timestamp=None):
    timestamp = int(time.time()) if timestamp is None else timestamp
    clients = counts if counts is not None else {CLIENT_KEY: 0}
    return {
        'version': version,
        'clients': {key: [timestamp] * count for key, count in clients.items() if count},
        'global': [timestamp] * sum(clients.values()),
    }


def stripe_name(norad, count=64):
    digest = hashlib.sha256(norad.encode()).hexdigest()
    return f'history-object-{int(digest[:4], 16) % count:02d}.lock'


class AdmissionTests(unittest.TestCase):
    def assert_status(self, response, expected):
        self.assertEqual(response[0], expected, response[2])

    def assert_retry(self, response):
        self.assertIn('retry-after', response[1], response)
        self.assertGreater(int(response[1]['retry-after']), 0)

    def assert_clean(self, endpoint):
        leftovers = [name for name in endpoint.files() if name.startswith('st-cookie') or name.endswith('.tmp')]
        self.assertEqual(leftovers, [], f'Temporary resources survived a completed request: {leftovers}')

    def assert_charged(self, endpoint, expected, *, previous=0):
        state = json.loads((endpoint.cache / UPSTREAM_LEDGER).read_text())
        self.assertEqual(state['version'], 2)
        self.assertEqual(len(state['global']), previous + expected)
        self.assertEqual(sum(len(entries) for entries in state['clients'].values()), previous + expected)
        self.assertEqual(len(endpoint.state.snapshot()), expected)
        self.assertEqual(set(state), {'version', 'clients', 'global'})
        self.assert_clean(endpoint)

    def put_ledger(self, endpoint, name, state):
        path = endpoint.cache / name
        path.write_text(json.dumps(state, separators=(',', ':')))
        return path

    def fragmented_store(self, endpoint, norad='41000'):
        intervals = [{'start': f'2026-01-{day:02d}', 'end': f'2026-01-{day:02d}'} for day in (2, 4)]
        records = [record(norad, f'2026-01-{day:02d}T12:00:00.123456Z') for day in (2, 4)]
        return endpoint.put_store(norad, intervals=intervals, records=records)

    def test_exhausted_incoming_quota_creates_no_object_state(self):
        for limits in ({'INCOMING_CLIENT_LIMIT': 2}, {'INCOMING_GLOBAL_LIMIT': 2, 'INCOMING_CLIENT_LIMIT': 60}):
            with self.subTest(limits=limits), Endpoint(limits) as endpoint:
                endpoint.put_store('41000')
                for _ in range(2):
                    self.assert_status(endpoint.request(), 200)
                initial_files = endpoint.files()
                admission = (endpoint.cache / 'request-limits.json').read_bytes()
                for number in range(42000, 42040):
                    response = endpoint.request(str(number))
                    self.assert_status(response, 429)
                    self.assert_retry(response)
                self.assertEqual(endpoint.files(), initial_files)
                self.assertEqual((endpoint.cache / 'request-limits.json').read_bytes(), admission)
                self.assertEqual(endpoint.state.snapshot(), [])
                self.assertNotIn(UPSTREAM_LEDGER, endpoint.files())
                self.assert_clean(endpoint)

    def test_concurrent_cache_hits_obey_incoming_admission_budget(self):
        with Endpoint({'INCOMING_CLIENT_LIMIT': 2}, credentials=False) as endpoint:
            for number in range(42000, 42008):
                endpoint.put_store(str(number))
            barrier = threading.Barrier(8)

            def request(number):
                barrier.wait(timeout=3)
                return endpoint.request(str(number))

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(request, range(42000, 42008)))
            self.assertEqual(sorted(result[0] for result in results), [200, 200] + [429] * 6, results)
            state = json.loads((endpoint.cache / 'request-limits.json').read_text())
            self.assertEqual(len(state['global']), 2)
            self.assertEqual(len(state['clients'][CLIENT_KEY]), 2)
            self.assertLessEqual(len(list(endpoint.cache.glob('history-object-*.lock'))), 2)
            self.assertEqual(endpoint.state.snapshot(), [])
            self.assertNotIn(UPSTREAM_LEDGER, endpoint.files())
            self.assert_clean(endpoint)

    def test_cache_hit_records_incoming_only_without_credentials(self):
        with Endpoint(credentials=False) as endpoint:
            path = endpoint.put_store('41000')
            original = path.read_bytes()
            self.assert_status(endpoint.request(), 200)
            state = json.loads((endpoint.cache / 'request-limits.json').read_text())
            self.assertEqual(state['version'], 1)
            self.assertEqual(len(state['global']), 1)
            self.assertEqual(path.read_bytes(), original)
            response = endpoint.request('41001')
            self.assert_status(response, 503)
            self.assertEqual(len(json.loads((endpoint.cache / 'request-limits.json').read_text())['global']), 2)
            self.assertNotIn(UPSTREAM_LEDGER, endpoint.files())
            self.assertEqual(endpoint.state.snapshot(), [])
            self.assert_clean(endpoint)

    def test_all_lock_contention_has_bounded_retryable_response(self):
        for name in ('request-limits.lock', stripe_name('41000'), 'history-miss.lock', 'upstream-limits.lock'):
            with self.subTest(lock=name), Endpoint({'LOCK_WAIT_MILLISECONDS': 100}) as endpoint:
                with endpoint.held_lock(name):
                    response = endpoint.request()
                    self.assert_status(response, 503)
                    self.assert_retry(response)
                    self.assertLess(response[3], 1.5)
                    self.assertEqual(endpoint.state.snapshot(), [])
                    self.assert_clean(endpoint)
                self.assert_status(endpoint.request(), 200)
                self.assert_charged(endpoint, 2)

    def test_warm_cache_bypasses_held_miss_lock_and_bad_upstream_state(self):
        with Endpoint({'LOCK_WAIT_MILLISECONDS': 100}, credentials=False) as endpoint:
            endpoint.put_store('41000')
            self.put_ledger(endpoint, UPSTREAM_LEDGER, {'broken': True})
            original = (endpoint.cache / UPSTREAM_LEDGER).read_bytes()
            with endpoint.held_lock('history-miss.lock'):
                self.assert_status(endpoint.request(), 200)
                response = endpoint.request('41001')
                self.assert_status(response, 503)
                self.assertLess(response[3], 1.5)
            self.assertEqual((endpoint.cache / UPSTREAM_LEDGER).read_bytes(), original)
            self.assertEqual(endpoint.state.snapshot(), [])
            self.assert_clean(endpoint)

    def test_object_lock_files_are_fixed_stripes(self):
        with Endpoint({'OBJECT_LOCK_STRIPES': 4}, credentials=False) as endpoint:
            for number in range(42000, 42024):
                self.assert_status(endpoint.request(str(number)), 503)
            stripes = [name for name in endpoint.files() if name.startswith('history-object-')]
            self.assertGreater(len(stripes), 0)
            self.assertLessEqual(len(stripes), 4)
            self.assertTrue(all(re.fullmatch(r'history-object-0[0-3]\.lock', name) for name in stripes))
            self.assertFalse(any(re.fullmatch(r'gp-history-[0-9]+\.lock', name) for name in endpoint.files()))
            self.assertEqual(endpoint.state.snapshot(), [])
            self.assertNotIn(UPSTREAM_LEDGER, endpoint.files())
            self.assert_clean(endpoint)

    def test_login_and_each_fragment_are_separately_charged(self):
        with Endpoint() as endpoint:
            self.fragmented_store(endpoint)
            self.assert_status(endpoint.request(), 200)
            calls = endpoint.state.snapshot()
            self.assertEqual([item['operation'] for item in calls], ['login', 'history', 'history', 'history'])
            self.assertEqual([item['start'][:10] for item in calls[1:]], ['2026-01-01', '2026-01-03', '2026-01-05'])
            self.assert_charged(endpoint, 4)
            self.assert_status(endpoint.request(), 200)
            self.assert_charged(endpoint, 4)
            self.assertEqual(len(json.loads((endpoint.cache / 'request-limits.json').read_text())['global']), 2)

    def test_temporarily_depleted_quota_rejects_whole_plan_before_login(self):
        with Endpoint() as endpoint:
            store = self.fragmented_store(endpoint)
            original = store.read_bytes()
            rate_path = self.put_ledger(endpoint, UPSTREAM_LEDGER, ledger(2, {CLIENT_KEY: 10}))
            original_rate = rate_path.read_bytes()
            response = endpoint.request()
            self.assert_status(response, 429)
            self.assert_retry(response)
            self.assertEqual(endpoint.state.snapshot(), [])
            self.assertEqual(rate_path.read_bytes(), original_rate)
            self.assertEqual(store.read_bytes(), original)
            self.assert_clean(endpoint)
            self.assert_status(endpoint.request(start='2026-01-01', end='2026-01-01'), 200)
            self.assert_charged(endpoint, 2, previous=10)

    def test_retry_after_covers_full_plan_and_rollover_preserves_hourly_events(self):
        with Endpoint() as endpoint:
            self.fragmented_store(endpoint)
            now = int(time.time())
            stamps = [now - 850, now - 800] + [now - 50] * 8
            path = self.put_ledger(endpoint, UPSTREAM_LEDGER, {
                'version': 2, 'clients': {CLIENT_KEY: stamps}, 'global': stamps,
            })
            original = path.read_bytes()
            before = int(time.time())
            response = endpoint.request()
            after = int(time.time())
            self.assert_status(response, 429)
            retry = int(response[1]['retry-after'])
            # Four planned calls need two old charges to expire, not just one.
            second_expiry = stamps[1] + 900
            self.assertGreaterEqual(retry, second_expiry - after)
            self.assertLessEqual(retry, second_expiry - before)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(endpoint.state.snapshot(), [])

            now = int(time.time())
            client_stamps = [now - 902, now - 901] + [now - 50] * 8
            global_stamps = [now - 3701] + client_stamps
            self.put_ledger(endpoint, UPSTREAM_LEDGER, {
                'version': 2, 'clients': {CLIENT_KEY: client_stamps}, 'global': global_stamps,
            })
            self.assert_status(endpoint.request(), 200)
            state = json.loads(path.read_text())
            self.assertEqual(len(state['clients'][CLIENT_KEY]), 12)
            self.assertEqual(len(state['global']), 14)
            self.assertNotIn(now - 3701, state['global'])
            self.assertIn(now - 902, state['global'])
            self.assertNotIn(now - 902, state['clients'][CLIENT_KEY])
            self.assertEqual(len(endpoint.state.snapshot()), 4)
            self.assert_clean(endpoint)

    def test_plan_larger_than_hard_limit_is_413_without_upstream_work(self):
        with Endpoint() as endpoint:
            intervals = [{'start': f'2026-01-{day:02d}', 'end': f'2026-01-{day:02d}'} for day in range(2, 31, 2)]
            store = endpoint.put_store('41000', intervals=intervals, records=[])
            original = store.read_bytes()
            response = endpoint.request(end='2026-01-31')
            self.assert_status(response, 413)
            self.assertEqual(endpoint.state.snapshot(), [])
            self.assertEqual(store.read_bytes(), original)
            self.assert_clean(endpoint)
            self.assert_status(endpoint.request(start='2026-01-01', end='2026-01-01'), 200)
            self.assert_charged(endpoint, 2)

    def test_failed_login_and_history_attempts_remain_charged_and_clean(self):
        for operation, expected_calls in (('login', 1), ('history', 2)):
            with self.subTest(operation=operation), Endpoint() as endpoint:
                store = self.fragmented_store(endpoint)
                original = store.read_bytes()
                setattr(endpoint.state, operation + '_status', 500)
                self.assert_status(endpoint.request(), 502)
                self.assert_charged(endpoint, expected_calls)
                self.assertEqual(store.read_bytes(), original)
                setattr(endpoint.state, operation + '_status', 200)
                self.assert_status(endpoint.request(), 200)
                self.assert_charged(endpoint, expected_calls + 4)

    def test_concurrent_misses_cannot_exceed_shared_upstream_budget(self):
        with Endpoint() as endpoint:
            others = {hashlib.sha256(address).hexdigest(): 9 for address in (b'192.0.2.10', b'192.0.2.11')}
            self.put_ledger(endpoint, UPSTREAM_LEDGER, ledger(2, others))
            endpoint.state.history_delay = 0.05
            barrier = threading.Barrier(4)

            def request(number):
                barrier.wait(timeout=3)
                return endpoint.request(str(number))

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(request, range(42000, 42004)))
            self.assertEqual(sum(result[0] == 200 for result in results), 1, results)
            self.assertTrue(all(result[0] in (200, 429, 503) for result in results), results)
            for result in results:
                if result[0] != 200:
                    self.assert_retry(result)
            self.assert_charged(endpoint, 2, previous=18)
            self.assertEqual(len(list(endpoint.cache.glob('gp-history-*.json'))), 1)

    def test_malformed_or_oversized_incoming_state_fails_closed(self):
        with Endpoint() as endpoint:
            endpoint.put_store('41000')
            self.assert_status(endpoint.request(), 200)
            original_files = endpoint.files()
            now = int(time.time())
            invalid_states = [
                b'{', b'{}',
                json.dumps(ledger(2, {CLIENT_KEY: 1})).encode(),
                json.dumps({'version': 1, 'clients': {CLIENT_KEY: ['recent']}, 'global': ['recent']}).encode(),
                json.dumps(ledger(1, {CLIENT_KEY: 1}, timestamp=now + 86400)).encode(),
                json.dumps({'version': 1, 'clients': {CLIENT_KEY: [now]}, 'global': []}).encode(),
                b' ' * 65537,
            ]
            for index, bad in enumerate(invalid_states):
                with self.subTest(corruption=index):
                    path = endpoint.cache / 'request-limits.json'
                    path.write_bytes(bad)
                    response = endpoint.request('42000')
                    self.assert_status(response, 503)
                    self.assertEqual(path.read_bytes(), bad)
                    self.assertEqual(endpoint.files(), original_files)
                    self.assertEqual(endpoint.state.snapshot(), [])
                    self.assert_clean(endpoint)

    def test_bad_upstream_state_denies_miss_but_preserves_cached_reads(self):
        with Endpoint() as endpoint:
            endpoint.put_store('41000')
            path = endpoint.cache / UPSTREAM_LEDGER
            for index, bad in enumerate((b'{}', b'{', b' ' * 65537)):
                with self.subTest(corruption=index):
                    path.write_bytes(bad)
                    response = endpoint.request('42000')
                    self.assert_status(response, 503)
                    self.assertEqual(path.read_bytes(), bad)
                    self.assert_status(endpoint.request(), 200)
                    self.assertEqual(endpoint.state.snapshot(), [])
                    self.assert_clean(endpoint)

    def test_legacy_quota_is_preserved_during_cooldown_and_after_migration(self):
        for age in (0, 3700):
            with self.subTest(age=age), Endpoint() as endpoint:
                state = ledger(1, {CLIENT_KEY: 1}, timestamp=int(time.time()) - age)
                del state['version']
                path = self.put_ledger(endpoint, 'rate-limits.json', state)
                original = path.read_bytes()
                endpoint.put_store('41000')
                self.assert_status(endpoint.request(), 200)
                self.assertNotIn(UPSTREAM_LEDGER, endpoint.files())
                response = endpoint.request('42000')
                if age == 0:
                    self.assert_status(response, 429)
                    self.assert_retry(response)
                    self.assertLessEqual(int(response[1]['retry-after']), 3600)
                    self.assertEqual(endpoint.state.snapshot(), [])
                    self.assertNotIn(UPSTREAM_LEDGER, endpoint.files())
                else:
                    self.assert_status(response, 200)
                    self.assert_charged(endpoint, 2)
                self.assertEqual(path.read_bytes(), original)
                self.assert_clean(endpoint)

    def test_concurrent_creates_respect_storage_caps_and_keep_cache_readable(self):
        cases = (
            ({'MAX_HISTORY_OBJECTS': 1}, 0),
            ({'MAX_OBJECT_BYTES': 4096, 'MAX_TOTAL_HISTORY_BYTES': 6000}, 2500),
        )
        for constants, padding in cases:
            with self.subTest(caps=constants), Endpoint(constants) as endpoint:
                endpoint.state.history_delay = 0.05
                endpoint.state.padding = padding
                barrier = threading.Barrier(2)

                def request(number):
                    barrier.wait(timeout=3)
                    return endpoint.request(str(number))

                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(request, ('42000', '42001')))
                self.assertEqual(sorted(result[0] for result in results), [200, 503], results)
                stores = list(endpoint.cache.glob('gp-history-*.json'))
                self.assertEqual(len(stores), 1)
                if 'MAX_TOTAL_HISTORY_BYTES' in constants:
                    size = sum(path.stat().st_size for path in stores)
                    self.assertLessEqual(size, constants['MAX_TOTAL_HISTORY_BYTES'])
                    self.assertGreater(size * 2, constants['MAX_TOTAL_HISTORY_BYTES'])
                self.assert_charged(endpoint, 2)
                norad = stores[0].stem.removeprefix('gp-history-')
                self.assert_status(endpoint.request(norad), 200)
                self.assert_status(endpoint.request('43000'), 503)
                self.assert_charged(endpoint, 2)

    def test_total_byte_headroom_denies_new_miss_without_breaking_cache_hit(self):
        with Endpoint({'MAX_OBJECT_BYTES': 4096, 'MAX_TOTAL_HISTORY_BYTES': 6000}) as endpoint:
            path = endpoint.put_store('41000', extra_whitespace=2000)
            self.assertLess(path.stat().st_size, 4096)
            self.assertGreater(path.stat().st_size + 4096, 6000)
            original = path.read_bytes()
            self.assert_status(endpoint.request(), 200)
            self.assert_status(endpoint.request('42000'), 503)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(endpoint.state.snapshot(), [])
            self.assert_clean(endpoint)

    def test_directory_limit_counts_unrecognised_entries(self):
        with Endpoint({'MAX_DIRECTORY_ENTRIES': 24}) as endpoint:
            for number in range(24):
                (endpoint.cache / f'unrelated-{number}').touch()
            self.assert_status(endpoint.request(), 503)
            self.assertEqual(endpoint.state.snapshot(), [])
            self.assertEqual(list(endpoint.cache.glob('gp-history-*.json')), [])
            self.assertEqual(len(list(endpoint.cache.glob('unrelated-*'))), 24)
            self.assert_clean(endpoint)

    def test_control_write_failure_denies_before_object_allocation(self):
        with Endpoint() as endpoint:
            (endpoint.cache / 'request-limits.json.tmp').mkdir()
            response = endpoint.request()
            self.assert_status(response, 503)
            self.assertEqual(endpoint.state.snapshot(), [])
            self.assertEqual(list(endpoint.cache.glob('history-object-*')), [])
            self.assertFalse((endpoint.cache / 'request-limits.json').exists())
            (endpoint.cache / 'request-limits.json.tmp').rmdir()
            self.assert_status(endpoint.request(), 200)
            self.assert_charged(endpoint, 2)

    def test_oversized_body_aborts_before_partial_commit_and_cleans_session(self):
        with Endpoint({'MAX_UPSTREAM_RESPONSE_BYTES': 1024}) as endpoint:
            store = self.fragmented_store(endpoint)
            original = store.read_bytes()
            endpoint.state.padding = 4096
            response = endpoint.request()
            self.assert_status(response, 413)
            self.assertEqual(store.read_bytes(), original)
            self.assert_charged(endpoint, 2)
            endpoint.state.padding = 0
            self.assert_status(endpoint.request(), 200)
            self.assert_charged(endpoint, 6)

    def test_aggregate_upstream_deadline_bounds_login_and_history_together(self):
        with Endpoint({'UPSTREAM_BUDGET_SECONDS': 1}) as endpoint:
            store = self.fragmented_store(endpoint)
            original = store.read_bytes()
            endpoint.state.login_delay = 0.6
            endpoint.state.history_delay = 0.6
            response = endpoint.request()
            self.assert_status(response, 503)
            self.assert_retry(response)
            self.assertLess(response[3], 2.0)
            self.assertEqual(store.read_bytes(), original)
            self.assert_charged(endpoint, 2)
            endpoint.state.login_delay = 0
            endpoint.state.history_delay = 0
            self.assert_status(endpoint.request(), 200)
            self.assert_charged(endpoint, 6)


if __name__ == '__main__':
    unittest.main(verbosity=2)
