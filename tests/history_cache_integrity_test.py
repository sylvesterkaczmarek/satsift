#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def fetch(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return int(response.status), json.load(response)
    except urllib.error.HTTPError as error:
        return int(error.code), json.loads(error.read().decode('utf-8'))


def request_url(port: int, norad: str = '40010') -> str:
    base = f'http://127.0.0.1:{port}/history.php'
    return base + '?' + urllib.parse.urlencode({'norad': norad, 'start': '2026-01-01', 'end': '2026-01-02'})


def valid_legacy_store(norad: str = '40010') -> dict:
    record = {
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
    }
    return {
        'version': 1,
        'source': 'Space-Track GP_History',
        'norad': norad,
        'intervals': [{'start': '2026-01-01', 'end': '2026-01-02'}],
        'records': [record],
        'updated_at': '2026-01-03T00:00:00Z',
    }


def canonical_digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def signed_store(norad: str = '40010') -> dict:
    store = valid_legacy_store(norad)
    store['records_sha256'] = canonical_digest(store['records'])
    payload = {
        'version': int(store['version']),
        'source': str(store['source']),
        'norad': str(store['norad']),
        'intervals': store['intervals'],
        'records': store['records'],
    }
    store['store_sha256'] = canonical_digest(payload)
    return store


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_root:
        temp = Path(temp_root)
        document_root = temp / 'www'
        cache_dir = temp / 'cache'
        document_root.mkdir(); cache_dir.mkdir()
        (document_root / 'history.php').write_text((ROOT / 'history.php').read_text())

        port = free_port()
        env = os.environ.copy()
        env['SATELLITE_HISTORY_CACHE_DIR'] = str(cache_dir)
        env.pop('SPACETRACK_IDENTITY', None)
        env.pop('SPACETRACK_PASSWORD', None)
        server = subprocess.Popen(
            ['php', '-S', f'127.0.0.1:{port}', '-t', str(document_root)],
            cwd=document_root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.03)
            else:
                raise RuntimeError('PHP test server did not start')

            cache_file = cache_dir / 'gp-history-40010.json'
            store = valid_legacy_store()
            cache_file.write_text(json.dumps(store, separators=(',', ':')))
            status, payload = fetch(request_url(port))
            assert status == 200, (status, payload)
            assert payload['cached'] is True
            assert payload['cache_integrity'] == 'legacy-validated'
            assert payload['count'] == 1

            signed = signed_store()
            cache_file.write_text(json.dumps(signed, separators=(',', ':')))
            status, payload = fetch(request_url(port))
            assert status == 200, (status, payload)
            assert payload['cache_integrity'] == 'sha256-verified'

            records_only = signed_store()
            records_only.pop('store_sha256')
            cache_file.write_text(json.dumps(records_only, separators=(',', ':')))
            status, payload = fetch(request_url(port))
            assert status == 200, (status, payload)
            assert payload['cache_integrity'] == 'records-sha256-verified'

            tampered_interval = signed_store()
            tampered_interval['intervals'][0]['end'] = '2026-01-03'
            cache_file.write_text(json.dumps(tampered_interval, separators=(',', ':')))
            status, payload = fetch(request_url(port))
            assert status == 502 and payload['ok'] is False, (status, payload)

            bad_hash = signed_store(); bad_hash['records_sha256'] = '0' * 64
            cache_file.write_text(json.dumps(bad_hash, separators=(',', ':')))
            status, payload = fetch(request_url(port))
            assert status == 502 and payload['ok'] is False, (status, payload)

            wrong_object = valid_legacy_store(); wrong_object['records'][0]['NORAD_CAT_ID'] = '49999'
            cache_file.write_text(json.dumps(wrong_object, separators=(',', ':')))
            status, payload = fetch(request_url(port))
            assert status == 502 and payload['ok'] is False, (status, payload)

            cache_file.write_text('{broken json')
            status, payload = fetch(request_url(port))
            assert status == 502 and payload['ok'] is False, (status, payload)

            invalid_interval = valid_legacy_store(); invalid_interval['intervals'] = [{'start': '2026-99-01', 'end': '2026-01-02'}]
            cache_file.write_text(json.dumps(invalid_interval, separators=(',', ':')))
            status, payload = fetch(request_url(port))
            assert status == 502 and payload['ok'] is False, (status, payload)

            print('History cache integrity stress tests passed.')
        finally:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill(); server.wait(timeout=3)


if __name__ == '__main__':
    main()
