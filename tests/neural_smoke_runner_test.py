#!/usr/bin/env python3
"""Standard-library regressions for the bounded neural verification command."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import run_neural_smoke as runner


def valid_report():
    return {
        'schema': 'smd-neural-smoke-tests-v1', 'successful': True,
        'tests_run': 20, 'skipped': 0, 'seed': 3404,
        'fixture_version': 'synthetic-neural-smoke-v1',
        'models': [
            {
                'architecture': architecture,
                'execution_version': 'neural-execution-v1', 'seed': 3404,
                'source_sha256': {'research/neural_execution.py': 'a' * 64},
                'state_sha256': 'b' * 64,
                'runtime': {
                    'device': 'cpu', 'torch_threads': 1, 'torch_interop_threads': 1,
                    'deterministic_training': True, 'python': '3.12.11',
                    'numpy': '2.3.2', 'pytorch': '2.8.0', 'system': 'test', 'machine': 'test',
                },
                'hyperparameters': {'epochs': 2}, 'training': {'rows': 32},
            }
            for architecture in sorted(runner.ARCHITECTURES)
        ],
    }


class NeuralSmokeRunnerTests(unittest.TestCase):
    def invoke(self, output=None, *, returncode=0, side_effect=None, arguments=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        process = subprocess.CompletedProcess([], returncode, output or '', '')
        with patch.object(runner.subprocess, 'run', return_value=process, side_effect=side_effect) as call:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = runner.main([] if arguments is None else arguments)
        return status, stdout.getvalue(), stderr.getvalue(), call

    def test_success_records_bounded_cpu_policy_and_actual_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('tools/run_neural_smoke.py', 'tests/neural_execution_test.py'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# synthetic verification source\n')
            with patch.object(runner, 'ROOT', root):
                status, output, _, call = self.invoke(json.dumps(valid_report()))
        self.assertEqual(status, 0)
        report = json.loads(output)
        self.assertFalse(report['confirmatory_experiment_run'])
        self.assertEqual(report['execution_policy']['timeout_seconds'], 180)
        self.assertEqual(report['execution_policy']['input'], 'generated fixtures only')
        self.assertTrue(report['runtime']['python_version'])
        self.assertEqual(set(report['verification_source_sha256']), {
            'tools/run_neural_smoke.py', 'tests/neural_execution_test.py',
        })
        self.assertNotIn(temporary, output)
        args, kwargs = call.call_args
        self.assertEqual(args[0][0], sys.executable)
        self.assertEqual(kwargs['timeout'], 180)
        self.assertEqual(kwargs['env']['PYTHONHASHSEED'], '3404')
        self.assertEqual(kwargs['env']['OMP_NUM_THREADS'], '1')
        self.assertEqual(kwargs['env']['MKL_NUM_THREADS'], '1')
        self.assertEqual(kwargs['env']['CUDA_VISIBLE_DEVICES'], '')
        self.assertTrue(kwargs['capture_output'])

    def test_timeout_fails_without_success_artifact(self):
        status, output, error, _ = self.invoke(side_effect=subprocess.TimeoutExpired('child', 180))
        self.assertEqual(status, 1)
        self.assertEqual(output, '')
        self.assertIn('180-second', error)

    def test_failed_process_cannot_supply_a_success_report(self):
        status, output, _, _ = self.invoke(json.dumps(valid_report()), returncode=1)
        self.assertEqual(status, 1)
        self.assertEqual(output, '')

    def test_missing_dependency_or_child_executable_fails(self):
        status, output, _, _ = self.invoke(side_effect=FileNotFoundError('unavailable'))
        self.assertEqual(status, 1)
        self.assertEqual(output, '')

    def test_partial_skipped_or_empty_architecture_coverage_fails(self):
        mutations = (
            lambda r: r.update(tests_run=0),
            lambda r: r.update(tests_run=True),
            lambda r: r.update(tests_run=19),
            lambda r: r.update(skipped=False),
            lambda r: r.update(skipped=1),
            lambda r: r.pop('skipped'),
            lambda r: r.update(successful=False),
            lambda r: r['models'].pop(),
            lambda r: r['models'].__setitem__(0, deepcopy(r['models'][1])),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                report = valid_report()
                mutation(report)
                status, output, _, _ = self.invoke(json.dumps(report))
                self.assertEqual(status, 1)
                self.assertEqual(output, '')

    def test_missing_or_wrong_provenance_fails(self):
        mutations = (
            lambda r: r.update(seed=12),
            lambda r: r.pop('fixture_version'),
            lambda r: r.update(fixture_version='unknown-fixture'),
            lambda r: r['models'][0].update(execution_version='unversioned'),
            lambda r: r['models'][0].pop('source_sha256'),
            lambda r: r['models'][0].pop('state_sha256'),
            lambda r: r['models'][0].pop('runtime'),
            lambda r: r['models'][0].pop('training'),
            lambda r: r['models'][0].pop('hyperparameters'),
            lambda r: r['models'][0].update(state_sha256='invalid'),
            lambda r: r['models'][0].update(source_sha256={'/private/source.py': 'a' * 64}),
            lambda r: r['models'][0].update(source_sha256={'research/source.py': 'invalid'}),
            lambda r: r['models'][0]['runtime'].update(device='cuda'),
            lambda r: r['models'][0]['runtime'].update(deterministic_training=False),
            lambda r: r['models'][0]['runtime'].update(torch_threads=8),
            lambda r: r['models'][0]['runtime'].update(torch_interop_threads=True),
            lambda r: r['models'][0]['runtime'].pop('pytorch'),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                report = valid_report()
                mutation(report)
                status, output, _, _ = self.invoke(json.dumps(report))
                self.assertEqual(status, 1)
                self.assertEqual(output, '')

    def test_malformed_duplicate_and_nonfinite_reports_fail(self):
        for output in ('not json', '[]', '{"schema":1,"schema":2}', '{"value":NaN}'):
            with self.subTest(output=output):
                status, artifact, _, _ = self.invoke(output)
                self.assertEqual(status, 1)
                self.assertEqual(artifact, '')

    def test_traceback_and_warning_diagnostics_hide_local_paths(self):
        diagnostics = (
            '  File "/private-example/work/venv/model.py", line 12, in fit\n'
            '/private-example/work/venv/transformer.py:392: UserWarning: example\n'
        )
        process = subprocess.CompletedProcess([], 1, '', diagnostics)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(runner.subprocess, 'run', return_value=process):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(runner.main([]), 1)
        self.assertEqual(stdout.getvalue(), '')
        self.assertNotIn('/private-example/', stderr.getvalue())
        self.assertIn('model.py', stderr.getvalue())
        self.assertIn('transformer.py:392:', stderr.getvalue())

    def test_command_does_not_accept_datasets_or_experiment_arguments(self):
        status, output, _, call = self.invoke(arguments=['--input', 'benchmark-results/example.json'])
        self.assertEqual(status, 2)
        self.assertEqual(output, '')
        call.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
