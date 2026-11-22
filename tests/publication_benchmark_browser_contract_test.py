#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import build_public_evidence_benchmark as builder


def history_payload(url: str, *_args: object) -> dict:
    norad = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['norad'][0]
    return {
        'cached': True,
        'records': [{
            'NORAD_CAT_ID': norad,
            'EPOCH': '2026-01-01T12:00:00.123456Z',
            'CREATION_DATE': '2026-01-01T13:00:00.000000Z',
            'ELEMENT_SET_NO': 1,
            'GP_ID': '10',
            'MEAN_MOTION': 15.5,
            'ECCENTRICITY': 0.001,
            'INCLINATION': 51.6,
            'RA_OF_ASC_NODE': 10.0,
            'ARG_OF_PERICENTER': 20.0,
            'MEAN_ANOMALY': 30.0,
            'BSTAR': 0.0,
        }],
    }


def main() -> None:
    manifest_bytes = builder.DEFAULT_MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    builder.fetch_json = history_payload
    built = [builder.build_case(item, 'https://example.test/history', 1.0, 0, 0.0) for item in manifest['cases']]
    output = builder.build_output(manifest, manifest_bytes, 'https://example.test/history', built)

    assert len(built) == 40
    quiet = [case for case in built if case['label_status'] == 'confirmed-quiet']
    assert len(quiet) == 10
    assert all(case['source_label_status'] == 'verified-quiet' for case in quiet)
    assert sum(case['label_status'] == 'event-evidence' for case in built) == 30

    with tempfile.TemporaryDirectory() as temp_root:
        materialized = Path(temp_root) / 'public-evidence-benchmark-v1.0.json'
        materialized.write_text(json.dumps(output))
        subprocess.run(
            ['node', 'tests/benchmark_import_contract_test.js', str(materialized)],
            cwd=ROOT,
            check=True,
        )


if __name__ == '__main__':
    main()
