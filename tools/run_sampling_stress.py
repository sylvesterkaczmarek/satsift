#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / 'benchmark-data/public-evidence-benchmark-v0.3.json'
ORIGINAL_RESULTS = ROOT / 'benchmark-results/baseline-v0.4-on-v0.3.json'
OUTPUT = ROOT / 'benchmark-results/baseline-v0.4-sampling-stress-v0.3.json'


def thin_records(records: list[dict], mode: str) -> list[dict]:
    n = len(records)
    if n <= 4:
        return records[:]
    if mode == 'quarter-drop':
        return [r for i, r in enumerate(records) if i in (0, n - 1) or i % 4 != 0]
    if mode == 'half-drop':
        return [r for i, r in enumerate(records) if i in (0, n - 1) or i % 2 == 1]
    if mode == 'middle-burst-loss':
        lo, hi = n // 3, 2 * n // 3
        return [r for i, r in enumerate(records) if i < lo or i >= hi]
    raise ValueError(mode)


def event_presence_by_case(document: dict) -> dict[str, bool]:
    return {str(case['case_id']): bool(case.get('predicted_events')) for case in document.get('cases') or []}


def run_variant(benchmark: dict, mode: str, tmp: Path) -> tuple[dict, dict]:
    variant = json.loads(json.dumps(benchmark))
    retained = original = 0
    for case in variant.get('cases') or []:
        records = list(case.get('records') or [])
        original += len(records)
        case['records'] = thin_records(records, mode)
        retained += len(case['records'])
    benchmark_path = tmp / f'{mode}.json'
    result_path = tmp / f'{mode}-results.json'
    features_path = tmp / f'{mode}-features.json'
    eval_path = tmp / f'{mode}-evaluation.json'
    benchmark_path.write_text(json.dumps(variant))
    subprocess.run([
        'node', 'tools/run_baseline_benchmark.js', str(benchmark_path), str(result_path), str(features_path)
    ], cwd=ROOT, check=True)
    subprocess.run([
        'python3', 'research/physics_ml/evaluate.py', str(result_path), '--split', 'test', '--output', str(eval_path)
    ], cwd=ROOT, check=True)
    return json.loads(result_path.read_text()), {
        'evaluation': json.loads(eval_path.read_text()),
        'original_records': original,
        'retained_records': retained,
        'retained_fraction': retained / original if original else None,
    }


def main() -> None:
    benchmark = json.loads(BENCHMARK.read_text())
    original = json.loads(ORIGINAL_RESULTS.read_text())
    original_presence = event_presence_by_case(original)
    report = {
        'schema': 'smd-sampling-stress-report-v1',
        'benchmark_version': benchmark.get('benchmark_version'),
        'detector_method': 'v0.4',
        'qualification': 'Stress variants remove observations without altering retained timestamps or states. They test missing and increasingly irregular sampling, not synthetic orbital dynamics.',
        'variants': {}
    }
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        for mode in ('quarter-drop', 'half-drop', 'middle-burst-loss'):
            results, metadata = run_variant(benchmark, mode, tmp)
            presence = event_presence_by_case(results)
            comparable = sorted(set(original_presence) & set(presence))
            stable = sum(original_presence[key] == presence[key] for key in comparable)
            metadata['event_presence_stability'] = stable / len(comparable) if comparable else None
            metadata['stable_cases'] = stable
            metadata['comparable_cases'] = len(comparable)
            report['variants'][mode] = metadata
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
