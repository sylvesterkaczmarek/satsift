#!/usr/bin/env python3
"""Bounded CPU verification using generated fixtures only; JSON report on stdout."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_SECONDS = 180
SEED = 3404
MINIMUM_TESTS = 20
FIXTURE_VERSION = 'synthetic-neural-smoke-v1'
ARCHITECTURES = {'gru', 'lstm', 'tcn', 'transformer', 'sequential-autoencoder'}
EXECUTION_VERSION = 'neural-execution-v1'
DEPENDENCIES = (
    'numpy', 'torch', 'filelock', 'fsspec', 'Jinja2', 'MarkupSafe', 'mpmath',
    'networkx', 'setuptools', 'sympy', 'typing_extensions', 'pip',
)


def _dependencies() -> dict[str, str | None]:
    versions = {}
    for name in DEPENDENCIES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _reject_constant(value: str):
    raise ValueError('non-finite report value')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate report key')
        result[key] = value
    return result


def _validate_report(report: dict) -> None:
    if not isinstance(report, dict) or report.get('schema') != 'smd-neural-smoke-tests-v1':
        raise ValueError('unrecognised smoke report')
    if report.get('successful') is not True:
        raise ValueError('neural smoke suite did not succeed')
    count = report.get('tests_run')
    if type(count) is not int or count < MINIMUM_TESTS or type(report.get('skipped')) is not int or report['skipped'] != 0:
        raise ValueError('empty or skipped neural smoke coverage')
    if type(report.get('seed')) is not int or report['seed'] != SEED or report.get('fixture_version') != FIXTURE_VERSION:
        raise ValueError('missing synthetic fixture identity')
    models = report.get('models')
    if not isinstance(models, list) or len(models) != len(ARCHITECTURES):
        raise ValueError('incomplete neural architecture coverage')
    if any(not isinstance(model, dict) for model in models):
        raise ValueError('invalid model provenance')
    if {model.get('architecture') for model in models} != ARCHITECTURES:
        raise ValueError('incomplete neural architecture coverage')
    for model in models:
        if model.get('execution_version') != EXECUTION_VERSION or model.get('seed') != SEED:
            raise ValueError('missing model version or seed')
        hashes = model.get('source_sha256')
        if not isinstance(hashes, dict) or not hashes:
            raise ValueError('missing model source identity')
        for name, digest in hashes.items():
            if not isinstance(name, str) or name.startswith('/') or '\\' in name or '..' in name.split('/'):
                raise ValueError('source identities require repository-relative names')
            if not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None:
                raise ValueError('invalid model source identity')
        state = model.get('state_sha256')
        if not isinstance(state, str) or re.fullmatch(r'[0-9a-f]{64}', state) is None:
            raise ValueError('missing model state identity')
        if any(not isinstance(model.get(field), dict) or not model[field]
               for field in ('runtime', 'hyperparameters', 'training')):
            raise ValueError('missing model execution provenance')
        runtime = model['runtime']
        if runtime.get('device') != 'cpu' or runtime.get('deterministic_training') is not True:
            raise ValueError('model did not record deterministic CPU training')
        if any(type(runtime.get(field)) is not int or runtime[field] != 1
               for field in ('torch_threads', 'torch_interop_threads')):
            raise ValueError('model did not record single-threaded execution')
        if any(not isinstance(runtime.get(field), str) or not runtime[field]
               for field in ('python', 'numpy', 'pytorch', 'system', 'machine')):
            raise ValueError('model did not record its actual runtime')
    json.dumps(report, allow_nan=False)


def run() -> dict:
    environment = os.environ.copy()
    environment.update({
        'PYTHONPATH': str(ROOT),
        'PYTHONHASHSEED': str(SEED),
        'PYTHONNOUSERSITE': '1',
        'PYTHONDONTWRITEBYTECODE': '1',
        'OMP_NUM_THREADS': '1',
        'MKL_NUM_THREADS': '1',
        'OPENBLAS_NUM_THREADS': '1',
        'NUMEXPR_NUM_THREADS': '1',
        'VECLIB_MAXIMUM_THREADS': '1',
        'CUDA_VISIBLE_DEVICES': '',
        'PYTORCH_ENABLE_MPS_FALLBACK': '0',
    })
    process = subprocess.run(
        [sys.executable, '-B', str(ROOT / 'tests/neural_execution_test.py')],
        cwd=ROOT, env=environment, check=False, capture_output=True,
        text=True, timeout=TIMEOUT_SECONDS,
    )
    if process.stderr:
        diagnostics = process.stderr.replace(str(ROOT), '<repository>')
        # Keep traceback line numbers and filenames without publishing local environment paths.
        diagnostics = re.sub(r'File "(?:/[^"\n]*/)([^/"\n]+)"', r'File "\1"', diagnostics)
        diagnostics = re.sub(r'(?m)^(?:/[^\n:]+/)([^/\n:]+:\d+(?::\d+)?:)', r'\1', diagnostics)
        print(diagnostics, file=sys.stderr, end='')
    if process.returncode != 0:
        raise ValueError('neural smoke tests failed')
    report = json.loads(process.stdout, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    _validate_report(report)
    report['schema'] = 'smd-neural-cpu-verification-v1'
    report['purpose'] = 'synthetic engineering verification; no detection-performance evaluation'
    report['confirmatory_experiment_run'] = False
    report['runtime'] = {
        'python_implementation': platform.python_implementation(),
        'python_version': platform.python_version(),
        'system': platform.system(),
        'system_release': platform.release(),
        'machine': platform.machine(),
        'dependencies': _dependencies(),
    }
    report['execution_policy'] = {
        'device': 'cpu',
        'seed': SEED,
        'compute_threads': 1,
        'deterministic_algorithms': True,
        'timeout_seconds': TIMEOUT_SECONDS,
        'input': 'generated fixtures only',
    }
    report['verification_source_sha256'] = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in ('tools/run_neural_smoke.py', 'tests/neural_execution_test.py')
    }
    return report


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        print('Usage: python3 tools/run_neural_smoke.py', file=sys.stderr)
        return 2
    try:
        report = run()
        encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    except subprocess.TimeoutExpired:
        print(f'Neural smoke suite exceeded its {TIMEOUT_SECONDS}-second CPU execution limit.', file=sys.stderr)
        return 1
    except (ValueError, OSError, TypeError, KeyError) as exc:
        # Detailed test failures are already shown above; never turn a failed run into an artefact.
        print(f'Neural smoke verification failed ({type(exc).__name__}).', file=sys.stderr)
        return 1
    print(encoded)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
