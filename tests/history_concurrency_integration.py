#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import json
import os
import signal
import re
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


class UpstreamState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.history_calls: list[dict[str, str]] = []
        self.login_calls = 0

    def add_history(self, item: dict[str, str]) -> None:
        with self.lock:
            self.history_calls.append(item)

    def add_login(self) -> None:
        with self.lock:
            self.login_calls += 1

    def calls_for(self, norad: str) -> list[dict[str, str]]:
        with self.lock:
            return [item.copy() for item in self.history_calls if item['norad'] == norad]


STATE = UpstreamState()


class MockSpaceTrackHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_args) -> None:
        return

    def write_json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != '/ajaxauth/login':
            self.write_json(404, {'error': 'not found'})
            return
        length = int(self.headers.get('Content-Length', '0'))
        if length:
            self.rfile.read(length)
        STATE.add_login()
        self.write_json(200, {'ok': True})

    def do_GET(self) -> None:
        decoded = urllib.parse.unquote(self.path)
        match = re.search(r'/NORAD_CAT_ID/(\d+)/EPOCH/([^/]+)/orderby/', decoded)
        if not match:
            self.write_json(404, {'error': 'unexpected path', 'path': decoded})
            return

        norad = match.group(1)
        interval = match.group(2)
        if '--' not in interval:
            self.write_json(400, {'error': 'bad interval'})
            return
        start, end_exclusive = interval.split('--', 1)
        STATE.add_history({'norad': norad, 'start': start, 'end_exclusive': end_exclusive})

        time.sleep(0.20)

        if norad == '40002':
            self.write_json(500, {'error': 'intentional upstream failure'})
            return

        epoch = start.replace('T00:00:00', 'T12:00:00.123456')
        self.write_json(200, [{
            'NORAD_CAT_ID': norad,
            'EPOCH': epoch,
            'CREATION_DATE': epoch,
            'ELEMENT_SET_NO': 1,
            'MEAN_MOTION': 15.5,
            'ECCENTRICITY': 0.001,
            'INCLINATION': 51.6,
            'RA_OF_ASC_NODE': 10.0,
            'ARG_OF_PERICENTER': 20.0,
            'MEAN_ANOMALY': 30.0,
            'BSTAR': 0.0,
        }])


def fetch(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return int(response.status), json.load(response)
    except urllib.error.HTTPError as error:
        return int(error.code), json.loads(error.read().decode('utf-8'))


def request_url(base: str, norad: str, start: str, end: str) -> str:
    return base + '?' + urllib.parse.urlencode({'norad': norad, 'start': start, 'end': end})


def parse_date_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def assert_non_overlapping(calls: list[dict[str, str]]) -> None:
    intervals = sorted(
        (parse_date_time(item['start']), parse_date_time(item['end_exclusive']))
        for item in calls
    )
    for first, second in zip(intervals, intervals[1:]):
        if first[1] > second[0]:
            raise AssertionError(f'Overlapping upstream intervals were fetched: {first} and {second}')


def assert_server_digest(cache_dir: Path, norad: str) -> None:
    store_path = cache_dir / f'gp-history-{norad}.json'
    store = json.loads(store_path.read_text())
    record_digest = str(store.get('records_sha256') or '')
    store_digest = str(store.get('store_sha256') or '')
    if not re.fullmatch(r'[a-f0-9]{64}', record_digest):
        raise AssertionError(f'New persistent history cache lacks a SHA-256 record digest: {record_digest!r}')
    if not re.fullmatch(r'[a-f0-9]{64}', store_digest):
        raise AssertionError(f'New persistent history cache lacks a full-store SHA-256 digest: {store_digest!r}')


def main() -> None:
    upstream_port = free_port()
    upstream = ThreadingHTTPServer(('127.0.0.1', upstream_port), MockSpaceTrackHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()

    try:
        with tempfile.TemporaryDirectory() as temp_root:
            temp = Path(temp_root)
            document_root = temp / 'www'
            document_root.mkdir()
            cache_dir = temp / 'cache'
            cache_dir.mkdir()

            source = (ROOT / 'history.php').read_text()
            source = source.replace('https://www.space-track.org', f'http://127.0.0.1:{upstream_port}')
            source = source.replace('CURLOPT_PROTOCOLS => CURLPROTO_HTTPS', 'CURLOPT_PROTOCOLS => CURLPROTO_HTTP')
            source = source.replace('CURLOPT_REDIR_PROTOCOLS => CURLPROTO_HTTPS', 'CURLOPT_REDIR_PROTOCOLS => CURLPROTO_HTTP')
            (document_root / 'history.php').write_text(source)

            php_port = free_port()
            env = os.environ.copy()
            env.update({
                'SPACETRACK_IDENTITY': 'test@example.invalid',
                'SPACETRACK_PASSWORD': 'test-password',
                'SATELLITE_HISTORY_CACHE_DIR': str(cache_dir),
                'PHP_CLI_SERVER_WORKERS': '4',
            })
            server = subprocess.Popen(
                ['php', '-S', f'127.0.0.1:{php_port}', '-t', str(document_root)],
                cwd=document_root,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                for _ in range(100):
                    try:
                        with socket.create_connection(('127.0.0.1', php_port), timeout=0.1):
                            break
                    except OSError:
                        time.sleep(0.05)
                else:
                    raise RuntimeError('Multi-worker PHP test server did not start.')

                base = f'http://127.0.0.1:{php_port}/history.php'

                same = request_url(base, '40000', '2026-01-01', '2026-01-05')
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(lambda _index: fetch(same), range(2)))
                if [status for status, _ in results] != [200, 200]:
                    raise AssertionError(f'Concurrent identical requests failed: {results}')
                calls = STATE.calls_for('40000')
                if len(calls) != 1:
                    raise AssertionError(f'Expected one upstream fetch for identical concurrent requests, got {len(calls)}: {calls}')
                if sorted(bool(payload.get('cached')) for _, payload in results) != [False, True]:
                    raise AssertionError('Exactly one identical concurrent request should perform upstream work and one should become a cache hit.')
                if any(payload.get('cache_integrity') != 'sha256-verified' for _, payload in results):
                    raise AssertionError(f'New history-cache responses must report SHA-256 verification: {results}')
                assert_server_digest(cache_dir, '40000')

                urls = [
                    request_url(base, '40001', '2026-02-01', '2026-02-05'),
                    request_url(base, '40001', '2026-02-03', '2026-02-07'),
                ]
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    overlap_results = list(executor.map(fetch, urls))
                if any(status != 200 for status, _ in overlap_results):
                    raise AssertionError(f'Concurrent overlapping requests failed: {overlap_results}')
                overlap_calls = STATE.calls_for('40001')
                if len(overlap_calls) != 2:
                    raise AssertionError(f'Expected two non-duplicative upstream ranges, got {len(overlap_calls)}: {overlap_calls}')
                assert_non_overlapping(overlap_calls)
                if any(payload.get('cache_integrity') != 'sha256-verified' for _, payload in overlap_results):
                    raise AssertionError(f'Overlapping history-cache responses must remain SHA-256 verified: {overlap_results}')
                assert_server_digest(cache_dir, '40001')

                failed = request_url(base, '40002', '2026-03-01', '2026-03-03')
                status, payload = fetch(failed)
                if status != 502 or payload.get('ok') is not False:
                    raise AssertionError(f'Intentional upstream failure was not contained safely: {status}, {payload}')
                if (cache_dir / 'gp-history-40002.json').exists():
                    raise AssertionError('Failed upstream work left a partial committed history cache.')

                print('History concurrency integration tests passed.')
            finally:
                # The multi-worker server and its children belong to this group.
                try:
                    os.killpg(server.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    server.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGKILL)
                    server.wait(timeout=3)
    finally:
        upstream.shutdown()
        upstream.server_close()


if __name__ == '__main__':
    main()
