#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import tempfile

from research.comparison_v1 import run_comparison as comparison
from research.confirmatory_v1 import run_confirmatory

ROOT = Path(__file__).resolve().parents[1]


def test_gate_is_frozen_before_confirmatory_access():
    assert run_confirmatory.MIN_TRUE_POSITIVES == 1
    assert run_confirmatory.MIN_RECALL_EXCLUSIVE == 0.20
    assert run_confirmatory.MAX_FALSE_RATE == 1.0
    assert run_confirmatory.MAX_MEDIAN_ABS_DELAY_HOURS == 24.0


def test_method_roster_is_exactly_comparison():
    assert len(comparison.METHOD_ORDER) == 16
    assert comparison.METHOD_ORDER[0] == 'detector-0.4'
    assert comparison.METHOD_ORDER[-1] == 'physics-ml-v1.0'
    assert 'shorten-op-pf-surrogate' in comparison.METHOD_ORDER


def test_default_exporter_remains_sealed():
    source = (ROOT / 'tools/export_selective_v1_features.js').read_text()
    assert 'CONFIRMATORY PARTITION IS SEALED: exporter refuses confirmatory cases.' in source
    assert "!['development','calibration'].includes" in source


def test_confirmatory_exporter_is_single_use_and_confirmatory_only():
    source = (ROOT / 'tools/export_confirmatory_features.js').read_text()
    assert 'CONFIRMATORY RUN LOCK' in source
    assert 'confirmatory-v1-final.json' in source
    assert "String(item.split)!=='confirmatory'" in source
    assert 'confirmatory_confirmatory_authorized:true' in source
    assert "fs.readFileSync(SOURCE, 'utf8')" in source


def test_runner_has_preflight_and_final_lock():
    source = (ROOT / 'research/confirmatory_v1/run_confirmatory.py').read_text()
    assert 'CONFIRMATORY RUN LOCK' in source
    assert '--preflight-only' in source
    assert 'Irreversible evaluation boundary' in source
    assert 'criteria_frozen_before_confirmatory_access' in source


def test_gate_document_matches_code():
    text = (ROOT / 'research/confirmatory_v1/GATE-v1.0.md').read_text()
    assert 'strictly greater than `0.20`' in text
    assert 'at most `1.0` per covered object-month' in text
    assert 'strictly greater than the highest confirmatory F1' in text
    assert 'at most `24` hours' in text
    assert 'Failure of any one condition' in text



def _authorized_confirmatory_document(*, authorized=True, mixed_row=False):
    cases = []
    truth_counts = [5, 5, 5, 5, 5, 5, 5, 5, 1, 0, 0, 0]
    assert sum(truth_counts) == 41
    for index in range(12):
        quiet = index >= 10
        cases.append({
            'case_id': f'confirm-{index}',
            'object_id': str(900000 + index),
            'split': 'confirmatory',
            'label_status': 'verified-quiet' if quiet else 'event-evidence',
            'truth_events': [
                {'start': f'2026-01-{(j % 28) + 1:02d}T00:00:00Z', 'end': f'2026-01-{(j % 28) + 1:02d}T01:00:00Z'}
                for j in range(truth_counts[index])
            ],
        })
    # Preserve exactly two verified-quiet controls while the other ten are event-evidence.
    cases[9]['label_status'] = 'event-evidence'
    rows = [{
        'case_id': case['case_id'],
        'split': 'development' if mixed_row and i == 0 else 'confirmatory',
        'epoch_utc': f'2026-01-{i + 1:02d}T00:00:00Z',
        'index': i,
    } for i, case in enumerate(cases)]
    return {
        'schema': 'smd-selective-v1-features-v1',
        'confirmatory_sealed': False,
        'confirmatory_confirmatory_authorized': bool(authorized),
        'one_shot': True,
        'included_splits': ['confirmatory'],
        'cases': cases,
        'rows': rows,
    }


def _verify_temp_document(document):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'confirmatory.json'
        path.write_text(json.dumps(document))
        return run_confirmatory.verify_confirmatory(path, {})


def test_confirmatory_authorized_loader_accepts_only_explicit_holdout():
    document, cases, rows = _verify_temp_document(_authorized_confirmatory_document())
    assert document['confirmatory_confirmatory_authorized'] is True
    assert len(cases) == 12 and len(rows) == 12
    assert sum(len(case.get('truth_events') or []) for case in cases.values()) == 41
    assert sum(case.get('label_status') == 'verified-quiet' for case in cases.values()) == 2


def test_confirmatory_authorized_loader_rejects_missing_authorization():
    try:
        _verify_temp_document(_authorized_confirmatory_document(authorized=False))
    except ValueError as error:
        assert 'explicit one-shot authorization' in str(error)
    else:
        raise AssertionError('unauthorized confirmatory artifact was accepted')


def test_confirmatory_authorized_loader_rejects_mixed_rows():
    try:
        _verify_temp_document(_authorized_confirmatory_document(mixed_row=True))
    except ValueError as error:
        assert 'non-confirmatory feature row' in str(error)
    else:
        raise AssertionError('mixed confirmatory/development rows were accepted')

def main():
    tests = [
        test_gate_is_frozen_before_confirmatory_access,
        test_method_roster_is_exactly_comparison,
        test_default_exporter_remains_sealed,
        test_confirmatory_exporter_is_single_use_and_confirmatory_only,
        test_runner_has_preflight_and_final_lock,
        test_gate_document_matches_code,
        test_confirmatory_authorized_loader_accepts_only_explicit_holdout,
        test_confirmatory_authorized_loader_rejects_missing_authorization,
        test_confirmatory_authorized_loader_rejects_mixed_rows,
    ]
    for test in tests:
        test()
        print('PASS', test.__name__)
    print(f'{len(tests)}/{len(tests)} Confirmatory evaluation preflight tests passed.')


if __name__ == '__main__':
    main()
