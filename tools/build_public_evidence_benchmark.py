#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / 'public-evidence-manifest-v1.0.json'
DEFAULT_OUTPUT = ROOT / 'benchmark-data' / 'public-evidence-benchmark-v1.0.json'
DEFAULT_ENDPOINT = 'https://www.sylvesterkaczmarek.com/satsift/history'
ALLOWED_SPLITS = {'development', 'calibration', 'confirmatory', 'test'}
RUNTIME_LABEL_STATUSES = {'event-evidence', 'confirmed-quiet', 'fully-labelled', 'unknown'}
RUNTIME_LABEL_ALIASES = {'verified-quiet': 'confirmed-quiet'}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_json(url: str, timeout: float, retries: int, backoff_seconds: float) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/json',
            'User-Agent': 'SatelliteManeuverBenchmarkBuilder/1.0',
        },
    )
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code <= 599
            try:
                payload = json.loads(error.read().decode('utf-8'))
                message = payload.get('message') or str(error)
            except Exception:
                message = str(error)
            last_error = RuntimeError(f'History request failed ({error.code}): {message}')
            if not retryable or attempt >= retries:
                raise last_error from error
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            if attempt >= retries:
                raise RuntimeError(f'History request failed after {retries + 1} attempt(s): {error}') from error
        sleep_for = backoff_seconds * (2 ** attempt)
        print(f'  transient history failure; retrying in {sleep_for:.1f}s')
        time.sleep(sleep_for)
    raise RuntimeError(f'History request failed: {last_error}')


def validate_splits(cases: list[dict]) -> None:
    split_by_object: dict[str, str] = {}
    for item in cases:
        case_id = str(item.get('case_id', '<unnamed>'))
        split = str(item.get('split', ''))
        if split not in ALLOWED_SPLITS:
            raise ValueError(f'{case_id}: unsupported split {split!r}')
        object_id = str(item.get('object_id', '')).strip()
        if not object_id:
            raise ValueError(f'{case_id}: object_id is required')
        previous = split_by_object.setdefault(object_id, split)
        if previous != split:
            raise ValueError(f'NORAD {object_id} appears in both {previous} and {split} splits')


def runtime_label_status(value: object) -> str:
    source_status = str(value or '').strip().lower()
    status = RUNTIME_LABEL_ALIASES.get(source_status, source_status)
    if status not in RUNTIME_LABEL_STATUSES:
        raise ValueError(f'unsupported label_status {source_status!r}')
    return status


def build_case(item: dict, endpoint: str, timeout: float, retries: int, backoff_seconds: float) -> dict:
    required = ['case_id', 'object_id', 'start_date', 'end_date', 'source', 'split', 'label_status']
    missing = [field for field in required if not str(item.get(field, '')).strip()]
    if missing:
        raise ValueError(f"{item.get('case_id', '<unnamed>')}: missing {', '.join(missing)}")

    query = urllib.parse.urlencode(
        {
            'norad': str(item['object_id']),
            'start': str(item['start_date']),
            'end': str(item['end_date']),
        }
    )
    payload = fetch_json(endpoint.rstrip('/') + '?' + query, timeout, retries, backoff_seconds)
    records = payload.get('records') if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        raise RuntimeError(f"{item['case_id']}: history endpoint returned no records")

    source_label_status = str(item['label_status']).strip().lower()
    result = {
        'case_id': item['case_id'],
        'object_id': str(item['object_id']),
        'object_name': item.get('object_name'),
        'description': item.get('description', item['case_id']),
        'orbit_profile': item.get('orbit_profile', 'AUTO'),
        'orbit_regime': item.get('orbit_regime', item.get('orbit_profile', 'AUTO')),
        'split': item['split'],
        # The frozen publication manifest uses the evidence term `verified-quiet`.
        # The browser runtime historically calls the same negative-coverage state
        # `confirmed-quiet`, so translate only in this derived browser artifact.
        'label_status': runtime_label_status(source_label_status),
        'label_confidence': item.get('label_confidence', 'unspecified'),
        'evidence_kind': item.get('evidence_kind'),
        'source': item['source'],
        'source_family': item.get('source_family'),
        'source_licence_note': item.get('source_licence_note'),
        'source_provenance': item.get('source_provenance'),
        'records': records,
        'truth_events': item.get('truth_events', []),
        'source_window': {
            'start': item['start_date'],
            'end': item['end_date'],
            'history_endpoint_cached': bool(payload.get('cached')),
            'record_count': len(records),
        },
    }
    if result['label_status'] != source_label_status:
        result['source_label_status'] = source_label_status
    if item.get('corroborating_source'):
        result['corroborating_source'] = item['corroborating_source']
    return {key: value for key, value in result.items() if value is not None}


def build_output(manifest: dict, manifest_bytes: bytes, endpoint: str, built: list[dict]) -> dict:
    return {
        'schema': 'smd-event-benchmark-v1',
        'name': manifest.get('name', 'Public-evidence satellite maneuver benchmark'),
        'benchmark_version': manifest.get('version', '1.0'),
        'matching_tolerance_hours': manifest.get('matching_tolerance_hours', 24),
        'notes': manifest.get('qualification', ''),
        'data_attribution': manifest.get('data_attribution'),
        'split_policy': manifest.get('split_policy'),
        'label_policy': manifest.get('label_policy'),
        'external_label_provenance': manifest.get('external_label_provenance'),
        'frozen_counts': manifest.get('frozen_counts'),
        'materialised_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'source_manifest': DEFAULT_MANIFEST.name,
        'manifest_sha256': sha256_bytes(manifest_bytes),
        'history_endpoint': endpoint,
        'cases': built,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Materialise the public-evidence maneuver benchmark through the same-site Space-Track history endpoint.'
    )
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--skip-unknown', action='store_true', help='Omit label_status=unknown cases from the generated file.')
    parser.add_argument('--delay-seconds', type=float, default=1.0, help='Delay between requests to avoid burst traffic.')
    parser.add_argument('--timeout', type=float, default=45.0)
    parser.add_argument('--retries', type=int, default=5)
    parser.add_argument('--backoff-seconds', type=float, default=2.0)
    args = parser.parse_args()

    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    cases = manifest.get('cases')
    if not isinstance(cases, list) or not cases:
        raise SystemExit('Manifest contains no cases.')
    validate_splits(cases)

    selected = [case for case in cases if not (args.skip_unknown and case.get('label_status') == 'unknown')]
    built = []
    for index, item in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] {item.get('case_id', '<unnamed>')}")
        built.append(build_case(item, args.endpoint, args.timeout, args.retries, args.backoff_seconds))
        if index < len(selected) and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

    output = build_output(manifest, manifest_bytes, args.endpoint, built)
    output['source_manifest'] = args.manifest.name
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(output, indent=2) + '\n').encode('utf-8')
    args.output.write_bytes(encoded)
    digest = sha256_bytes(encoded)
    args.output.with_suffix(args.output.suffix + '.sha256').write_text(f'{digest}  {args.output.name}\n')
    print(f'Wrote {len(built)} case(s) to {args.output}.')
    print(f'SHA-256 {digest}')


if __name__ == '__main__':
    main()
