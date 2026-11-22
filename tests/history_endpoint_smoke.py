#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def request(url: str, method: str = 'GET') -> tuple[int, dict[str, str], dict]:
    req = urllib.request.Request(url, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read().decode('utf-8')
    payload = json.loads(body)
    headers = {key.lower(): value for key, value in response.headers.items()}
    return int(response.status), headers, payload


def assert_case(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    port = free_port()
    with tempfile.TemporaryDirectory() as temp_root:
        document_root = Path(temp_root) / 'www'
        cache_path = Path(temp_root) / 'cache'
        document_root.mkdir()
        cache_path.mkdir()
        (document_root / 'history.php').write_text((ROOT / 'history.php').read_text())
        env = os.environ.copy()
        env['SATELLITE_HISTORY_CACHE_DIR'] = str(cache_path)
        env.pop('SPACETRACK_IDENTITY', None)
        env.pop('SPACETRACK_PASSWORD', None)
        env.pop('PHP_CLI_SERVER_WORKERS', None)
        server = subprocess.Popen(
            ['php', '-S', f'127.0.0.1:{port}', '-t', str(document_root)],
            cwd=document_root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base = f'http://127.0.0.1:{port}/history.php'
            for _ in range(50):
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError('PHP test server did not start')

            status, headers, payload = request(base, 'POST')
            assert_case(status == 405, f'POST returned {status}, expected 405')
            assert_case(payload.get('ok') is False, 'POST error payload must set ok=false')
            assert_case(headers.get('allow') == 'GET', '405 response must advertise Allow: GET')

            status, headers, payload = request(base + '?norad=abc&start=2026-01-01&end=2026-01-02')
            assert_case(status == 400, f'invalid NORAD returned {status}, expected 400')
            assert_case('digits' in str(payload.get('message', '')).lower(), 'invalid NORAD message is unclear')
            assert_case(headers.get('x-content-type-options') == 'nosniff', 'nosniff header missing')
            assert_case('noindex' in headers.get('x-robots-tag', ''), 'X-Robots-Tag noindex missing')
            assert_case("default-src 'none'" in headers.get('content-security-policy', ''), 'endpoint CSP missing')

            status, _, payload = request(base + '?norad=25544&start=2026-01-03&end=2026-01-02')
            assert_case(status == 400, f'reversed range returned {status}, expected 400')
            assert_case('earlier' in str(payload.get('message', '')).lower(), 'reversed-range message is unclear')

            status, _, payload = request(base + '?norad=25544&start=2026-01-01&end=2026-02-01')
            assert_case(status == 400, f'oversized range returned {status}, expected 400')
            assert_case('31' in str(payload.get('message', '')), 'range-limit message must state the 31-day limit')

            assert_case(not list(cache_path.iterdir()), 'invalid requests must not allocate cache controls or object state')
            cached_store = {
                'version': 1,
                'source': 'Space-Track GP_History',
                'norad': '25544',
                'intervals': [{'start': '2026-01-01', 'end': '2026-01-02'}],
                'records': [
                    {'NORAD_CAT_ID': '25544', 'EPOCH': '2026-01-01T12:00:00.123456'},
                    {'NORAD_CAT_ID': '25544', 'EPOCH': '2026-01-02T12:00:00.654321'},
                ],
                'updated_at': '2026-01-03T00:00:00Z',
            }
            cache_file = cache_path / 'gp-history-25544.json'
            original_store = json.dumps(cached_store)
            cache_file.write_text(original_store)

            status, _, payload = request(base + '?norad=25544&start=2026-01-01&end=2026-01-02')
            assert_case(status == 200, f'fully cached history returned {status}, expected 200')
            assert_case(payload.get('ok') is True, 'cached history must return ok=true')
            assert_case(payload.get('cached') is True, 'cached history must be marked cached')
            assert_case(payload.get('count') == 2, 'cached history returned the wrong record count')
            assert_case(not (cache_path / 'upstream-limits.json').exists(), 'cache hit must not consume the upstream operation budget')
            incoming = json.loads((cache_path / 'request-limits.json').read_text())
            assert_case(len(incoming['global']) == 1, 'cache hit must consume incoming admission')
            assert_case(cache_file.read_text() == original_store, 'cache hit must preserve stored history bytes')

            status, _, payload = request(base + '?norad=25544&start=2026-01-03&end=2026-01-04')
            assert_case(status == 503, f'unconfigured cache miss returned {status}, expected 503')
            assert_case(payload.get('ok') is False, 'unconfigured cache miss must set ok=false')
            safe_message = str(payload.get('message', '')).lower()
            assert_case('password' not in safe_message and 'identity' not in safe_message, 'response exposes credential fields')

            print('History endpoint smoke tests passed.')
        finally:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=3)


if __name__ == '__main__':
    main()
