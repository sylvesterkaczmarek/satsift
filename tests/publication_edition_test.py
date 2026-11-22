#!/usr/bin/env python3
"""Verify the editorial edition and its cross-artifact provenance links."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_HASHES = {
    'benchmark-results/physics-v1-development.json': '276ed8fa51579936134cbfde1d3f012c85899dc0d34644adec376e26d6f883e4',
    'benchmark-results/integrity-v1-stress.json': 'ebc38c0fd77e03dad76c36b3db7ed6fb5b38e7cad52c41e78aba532e50d2a288',
    'benchmark-results/comparison-v1-development-calibration.json': 'c0b3e28879aecfd9bbeaa8c5f030b87cbd87eb77544ffe762c13a80f5cde4d45',
    'research/confirmatory_v1/DATA-PROVENANCE-v1.0.json': '21948fea6d71a14bb959d684d56c9816f35cb252fe19b0143218f180398c68ef',
    'research/confirmatory_v1/PRECONFIRMATORY-FREEZE.json': '411617d5a4e60be2a8165d48f26f427c891faffdf9092617382156803fac9e46',
    'benchmark-results/confirmatory-v1-final.json': '16cdc46a57bb980cfa7e6ce067055934e9ff6a63db90bbf8776ebb0ecaf628d9',
    'research/confirmatory_v1/RUN-LOCK-v1.0.json': '9120266c8025a61cbda31c8992d0159c3a3d5e5029d554614ee6782ba8d86939',
    'research/confirmatory_v1/AUDIT-VERIFICATION-v1.0.json': 'd32f5384d46b4b3bd598dddab2125c622da0e24d95247e9aeb92587fea39a85c',
}


def read(path: str):
    return json.loads((ROOT / path).read_text())


def main() -> None:
    ledger = read('research/PUBLICATION-EDITION.json')
    assert ledger['schema'] == 'smd-publication-edition-v1'
    assert ledger['source_commit'] == '715e2e60390eb2bc8df36f6fb8d136f20805d2e1'
    assert len(ledger['artifacts']) == len(ORIGINAL_HASHES)
    entries = {item['path']: item for item in ledger['artifacts']}
    assert set(entries) == set(ORIGINAL_HASHES)
    digests = {}
    for path, original in ORIGINAL_HASHES.items():
        entry = entries[path]
        assert entry['original_sha256'] == original, path
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        assert entry['publication_sha256'] == actual, path
        assert actual != original, path
        digests[path] = actual

    freeze = read('research/confirmatory_v1/PRECONFIRMATORY-FREEZE.json')
    result = read('benchmark-results/confirmatory-v1-final.json')
    lock = read('research/confirmatory_v1/RUN-LOCK-v1.0.json')
    audit = read('research/confirmatory_v1/AUDIT-VERIFICATION-v1.0.json')
    for item in (freeze, result):
        assert item['comparison_result_sha256'] == digests['benchmark-results/comparison-v1-development-calibration.json']
        assert item['physics_result_sha256'] == digests['benchmark-results/physics-v1-development.json']
    assert lock['preconfirmatory_freeze_sha256'] == digests['research/confirmatory_v1/PRECONFIRMATORY-FREEZE.json']
    final_hash = digests['benchmark-results/confirmatory-v1-final.json']
    assert lock['final_result_sha256'] == final_hash
    assert audit['final_result_sha256'] == final_hash
    assert (ROOT / 'benchmark-results/confirmatory-v1-final.json.sha256').read_text().split()[0] == final_hash
    assert result['integration_publication_gate']['passed'] is False
    assert lock['rerun_forbidden'] is True
    print('Eight publication-edition artefacts and all linked freeze hashes verified.')


if __name__ == '__main__':
    main()
