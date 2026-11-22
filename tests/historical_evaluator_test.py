#!/usr/bin/env python3
"""Protect the boundary between recorded research and maintained software."""
from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'research/historical_v1'
VERSION = 'confirmatory-v1-historical'
FINAL_RESULT = 'benchmark-results/confirmatory-v1-final.json'
FINAL_SHA256 = 'f9857bd8f9ae2525b1827ce4fdfd108f7c5468c67142226922542d24b88c923c'
EVIDENCE_PATHS = (
    'research/PUBLICATION-EDITION.json',
    'benchmark-results/confirmatory-v1-final.json.sha256',
    'public-evidence-manifest-v1.0.json',
)
SNAPSHOT_PATHS = (
    'tools/confirmatory_post_result_audit.py',
    'research/confirmatory_v1/RESULTS-v1.0.md',
    'research/confirmatory_v1/INTEGRATION-DISPOSITION.md',
    'review/CONFIRMATORY-AUDIT.md',
    'review/CONFIRMATORY-MATERIALISATION-INCIDENT.md',
)
ARCHIVED_SURFACES = (
    'source-surfaces/detector-scientific.txt',
    'source-surfaces/resolveCatalogueRevisions.txt',
    'source-surfaces/satrecForRecord.txt',
    'source-surfaces/confirmatory-runner-scientific.txt',
)

# Child interpreters start without site packages and cannot call Git, the network,
# or a write operation. Only the historical research package may be imported.
CHILD_GUARDS = """
import os
import sys

class HistoricalImportsOnly:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('research.') and not (
            fullname == 'research.historical_v1'
            or fullname.startswith('research.historical_v1.')
        ):
            raise RuntimeError('Maintained research import attempted: ' + fullname)
        if fullname.split('.')[0] in {'numpy', 'torch', 'sgp4'}:
            raise RuntimeError('Third-party research import attempted: ' + fullname)
        return None

def reject_side_effects(event, arguments):
    if event.startswith(('subprocess.', 'socket.')) or event in {
        'os.system', 'os.posix_spawn', 'os.fork', 'os.exec', 'os.spawn',
        'os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.link',
        'os.symlink', 'os.truncate', 'os.chmod', 'os.chown', 'os.utime',
    }:
        raise RuntimeError('Historical verification attempted a side effect: ' + event)
    if event == 'open':
        mode, flags = arguments[1], arguments[2]
        writes = isinstance(mode, str) and any(value in mode for value in 'wax+')
        writes = writes or (
            isinstance(flags, int) and flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            )
        )
        if writes:
            raise RuntimeError('Historical verification attempted a file write')

sys.meta_path.insert(0, HistoricalImportsOnly())
sys.addaudithook(reject_side_effects)
"""

AUDIT_CHILD = CHILD_GUARDS + """
import runpy
from pathlib import Path

if Path('.git').exists():
    raise RuntimeError('Snapshot unexpectedly contains Git metadata')
sys.argv = ['tools/confirmatory_post_result_audit.py']
runpy.run_path(sys.argv[0], run_name='__main__')
"""

TAMPER_CHILD = CHILD_GUARDS + """
from research.historical_v1 import load_evaluator, verify_archive

try:
    verify_archive()
except AssertionError as error:
    rejection = str(error)
    if 'SHA-256 mismatch' not in rejection:
        raise RuntimeError('Tamper was not rejected by the checksum guard') from error
else:
    raise RuntimeError('verify_archive accepted altered historical bytes')

try:
    load_evaluator()
except AssertionError as error:
    if str(error) != rejection:
        raise RuntimeError('Loader did not reject through the same checksum guard') from error
else:
    raise RuntimeError('load_evaluator accepted altered historical bytes')

print('Historical checksum guard rejected tampering before execution.')
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_digests(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): digest(path)
        for path in sorted(root.rglob('*'))
        if path.is_file()
    }


def copy_paths(paths, source: Path, destination: Path) -> None:
    for relative in paths:
        origin = source / relative
        if origin.is_symlink() or not origin.is_file():
            raise AssertionError(f'Snapshot input must be a regular file: {relative}')
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, target)


def replace_once(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise AssertionError(f'Mutation target must occur exactly once: {before}')
    return source.replace(before, after, 1)


def run_child(root: Path, code: str) -> subprocess.CompletedProcess:
    empty_path = root / 'empty-path'
    empty_path.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, '-B', '-S', '-c', code],
        cwd=root,
        env={
            'PATH': str(empty_path),
            'PYTHONPATH': str(root),
            'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONNOUSERSITE': '1',
            'PYTHONUTF8': '1',
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def event_at(hours: int) -> dict[str, str]:
    epoch = datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(hours=hours)
    stamp = epoch.isoformat().replace('+00:00', 'Z')
    return {'start_utc': stamp, 'end_utc': stamp, 'strongest_utc': stamp}


class HistoricalEvaluatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(ROOT))
        from research.historical_v1 import load_evaluator, verify_archive

        cls.manifest = verify_archive()
        cls.evaluator = load_evaluator()
        ledger = json.loads((ROOT / 'research/PUBLICATION-EDITION.json').read_text())
        cls.evidence_paths = tuple(item['path'] for item in ledger['artifacts']) + EVIDENCE_PATHS
        cls.original_evidence = {
            relative: digest(ROOT / relative) for relative in cls.evidence_paths
        }

    @classmethod
    def tearDownClass(cls) -> None:
        actual = {relative: digest(ROOT / relative) for relative in cls.evidence_paths}
        if actual != cls.original_evidence:
            raise AssertionError('Historical tests modified the frozen publication evidence')

    def copy_archive(self, destination: Path) -> None:
        files = ('__init__.py', 'MANIFEST.json') + tuple(
            item['path'] for item in self.manifest['files']
        )
        copy_paths(files, ARCHIVE, destination / 'research/historical_v1')

    def assert_child_passes(self, root: Path, code: str) -> str:
        completed = run_child(root, code)
        self.assertEqual(
            completed.returncode, 0,
            f'Child verification failed:\n{completed.stdout}\n{completed.stderr}',
        )
        return completed.stdout

    def test_all_recorded_statistics_are_reproduced_exactly(self) -> None:
        self.assertEqual(self.evaluator.EVALUATOR_VERSION, VERSION)
        self.assertEqual(digest(ROOT / FINAL_RESULT), FINAL_SHA256)
        result = json.loads((ROOT / FINAL_RESULT).read_text())
        self.assertEqual(len(result['methods']), 16)
        regime_blocks = 0
        for method in result['methods']:
            with self.subTest(method=method['method']):
                cases = method['confirmatory_case_results']
                self.assertEqual(
                    self.evaluator.evaluation_block(cases),
                    method['confirmatory_evaluation'],
                )
                self.assertEqual(
                    self.evaluator.by_regime(cases),
                    method['confirmatory_by_orbit_regime'],
                )
                regime_blocks += len(method['confirmatory_by_orbit_regime'])
        self.assertEqual(regime_blocks, 64)
        self.assertEqual(
            self.evaluator.ranking(result['methods']), result['confirmatory_ranking_table'],
        )
        self.assertEqual(
            self.evaluator.evaluate_gate(result['methods']), result['integration_publication_gate'],
        )
        self.assertIs(result['integration_publication_gate']['passed'], False)
        target = next(item for item in result['methods'] if item['method'] == 'physics-ml-v1.0')
        summary = target['confirmatory_evaluation']['summary']
        self.assertEqual(
            (summary['true_positives'], summary['false_negatives'], summary['recall'], summary['f1']),
            (0, 41, 0.0, 0.0),
        )
        lock = json.loads((ROOT / 'research/confirmatory_v1/RUN-LOCK-v1.0.json').read_text())
        self.assertIs(lock['one_shot_completed'], True)
        self.assertIs(lock['rerun_forbidden'], True)
        self.assertIs(lock['gate_passed'], False)

    def test_historical_semantics_remain_identifiable(self) -> None:
        # These assertions describe the recorded evaluator, including its known
        # limitations. They do not prescribe behavior for a corrected evaluator.
        truth = [{'start': event_at(hour)['start_utc']} for hour in (0, 10)]
        matched = self.evaluator.match_event_dicts(
            [event_at(4), event_at(-5)], truth, tolerance_hours=6,
        )
        self.assertEqual(matched, {
            'matches': [{
                'prediction_index': 0,
                'truth_index': 0,
                'delay_hours': 4.0,
                'strongest_point_delay_hours': 4.0,
            }],
            'tp': 1,
            'fn': 1,
            'unmatched_predictions': 1,
        })

        # Historical exposure uses the stored coverage fraction and case span.
        quiet = [{
            'label_status': 'verified-quiet',
            'coverage_fraction': 0.5,
            'span_days': 30.4375,
            'predicted_events': [event_at(0)],
            'truth_events': [],
        }]
        summary = self.evaluator.summarize_results(quiet)
        self.assertEqual(summary['covered_verified_quiet_object_months'], 0.5)
        self.assertEqual(summary['false_events_per_object_month'], 2.0)
        self.assertEqual(summary['mean_case_abstention_fraction'], 0.5)
        quiet[0]['predicted_events'] = []
        zero_false_rate = self.evaluator.bootstrap(quiet, iterations=32, seed=3404)
        self.assertEqual(
            zero_false_rate['false_events_per_object_month'],
            {'low_95': 0.0, 'high_95': 0.0, 'bootstrap_samples': 32},
        )

        missed = [{
            'label_status': 'event-evidence',
            'coverage_fraction': 1.0,
            'predicted_events': [],
            'truth_events': [
                {'start': event_at(24 * day)['start_utc']} for day in range(41)
            ],
        }]
        intervals = self.evaluator.bootstrap(missed, iterations=32, seed=3404)
        for field in ('recall', 'f1'):
            self.assertEqual(
                intervals[field],
                {'low_95': 0.0, 'high_95': 0.0, 'bootstrap_samples': 32},
            )

    def test_archive_imports_are_closed_over_the_standard_library(self) -> None:
        allowed = {
            '__init__.py': {'__future__', 'hashlib', 'json', 'pathlib', 'types'},
            'evaluator.py': {'__future__', 'datetime', 'math', 'random', 'statistics'},
        }
        for filename, permitted in allowed.items():
            tree = ast.parse((ARCHIVE / filename).read_text())
            for node in ast.walk(tree):
                with self.subTest(file=filename, line=getattr(node, 'lineno', 0)):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertIn(alias.name, permitted)
                    elif isinstance(node, ast.ImportFrom):
                        self.assertEqual(node.level, 0, 'No relative dependency fallback is permitted')
                        self.assertIn(node.module, permitted)
                    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotEqual(node.func.id, '__import__')
                        if filename == 'evaluator.py':
                            self.assertNotIn(node.func.id, {'compile', 'eval', 'exec', 'open'})
        self.assertEqual(
            set(item['path'] for item in self.manifest['files']),
            {'evaluator.py', *ARCHIVED_SURFACES},
        )
        self.assertEqual(
            set(self.manifest['stdlib_dependencies']),
            {'datetime', 'math', 'random', 'statistics'},
        )

    def test_checksum_guards_reject_all_frozen_surfaces_before_execution(self) -> None:
        original = (ARCHIVE / 'evaluator.py').read_text()
        mutations = {
            'constant': replace_once(original, 'SEED = 3404', 'SEED = 3405'),
            'matching default': replace_once(
                original, 'tolerance_hours=MATCH_TOLERANCE_HOURS', 'tolerance_hours=0.0',
            ),
            'matching body': replace_once(original, 'used_p.add(pi)', 'used_p.add(ti)'),
            'exposure': replace_once(original, 'coverage / 30.4375', 'coverage / 30.0'),
            'uncertainty': replace_once(
                original, 'rng = random.Random(seed)', 'rng = random.Random(seed + 1)',
            ),
            # A common timestamp shift preserves relative matches and delays.
            # Recomputed result equality alone would miss this helper mutation.
            'time helper': replace_once(
                original, 'return parsed.timestamp()', 'return parsed.timestamp() + 1.0',
            ),
            'execution order': original + "\nraise RuntimeError('ARCHIVE_CODE_EXECUTED')\n",
        }
        for name, altered in mutations.items():
            with self.subTest(surface=name), tempfile.TemporaryDirectory(prefix='smd-history-') as tmp:
                snapshot = Path(tmp)
                self.copy_archive(snapshot)
                (snapshot / 'research/historical_v1/evaluator.py').write_text(altered)
                self.assert_child_passes(snapshot, TAMPER_CHILD)

        for relative in ARCHIVED_SURFACES:
            with self.subTest(surface=relative), tempfile.TemporaryDirectory(prefix='smd-history-') as tmp:
                snapshot = Path(tmp)
                self.copy_archive(snapshot)
                target = snapshot / 'research/historical_v1' / relative
                target.write_bytes(target.read_bytes() + b'\n// altered historical source\n')
                self.assert_child_passes(snapshot, TAMPER_CHILD)

        for update_payload in (False, True):
            with self.subTest(manifest_rehashed=update_payload), tempfile.TemporaryDirectory(prefix='smd-history-') as tmp:
                snapshot = Path(tmp)
                self.copy_archive(snapshot)
                package = snapshot / 'research/historical_v1'
                path = package / 'MANIFEST.json'
                if update_payload:
                    evaluator = package / 'evaluator.py'
                    evaluator.write_text(mutations['constant'])
                    changed_manifest = json.loads(path.read_text())
                    for entry in changed_manifest['files']:
                        if entry['path'] == 'evaluator.py':
                            entry['sha256'] = digest(evaluator)
                    path.write_text(json.dumps(changed_manifest, indent=2) + '\n')
                else:
                    path.write_bytes(path.read_bytes() + b'\n')
                self.assert_child_passes(snapshot, TAMPER_CHILD)

    def test_source_snapshot_audit_survives_unavailable_and_changed_live_code(self) -> None:
        with tempfile.TemporaryDirectory(prefix='smd-history-') as tmp:
            snapshot = Path(tmp)
            self.copy_archive(snapshot)
            copy_paths(self.evidence_paths + SNAPSHOT_PATHS, ROOT, snapshot)
            self.assertFalse((snapshot / '.git').exists())
            before = file_digests(snapshot)
            original_output = self.assert_child_passes(snapshot, AUDIT_CHILD)
            self.assertIn('all 16 methods', original_output)
            self.assertIn(FINAL_SHA256, original_output)
            self.assertIn('Gate PASS? False', original_output)
            self.assertEqual(file_digests(snapshot), before)

            # Entire modules are poisoned so every maintained matcher, exposure,
            # uncertainty, time helper and runner implementation may change.
            unavailable = "raise RuntimeError('MAINTAINED_SOURCE_USED')\n"
            modules = {
                'research/comparison_v1/__init__.py',
                'research/comparison_v1/run_comparison.py',
                'research/confirmatory_v1/__init__.py',
                'research/confirmatory_v1/run_confirmatory.py',
                'research/selective_v1/__init__.py',
                'research/selective_v1/core.py',
                'research/selective_v1/models.py',
                'research/selective_v1/train_compare.py',
                'research/physics_v1/__init__.py',
                'research/sequential_v1/__init__.py',
                'tests/integration_disposition_test.py',
            }
            for relative in modules:
                path = snapshot / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(unavailable)
            (snapshot / 'app-3.4.js').write_text("throw new Error('MAINTAINED_APP_USED');\n")
            for module in (snapshot / 'app').glob('*.js'):
                module.write_text("throw new Error('MAINTAINED_MODULE_USED');\n")
            changed_sources = file_digests(snapshot)
            changed_output = self.assert_child_passes(snapshot, AUDIT_CHILD)
            self.assertEqual(changed_output, original_output)
            self.assertEqual(file_digests(snapshot), changed_sources)
            self.assertEqual(
                {relative: digest(snapshot / relative) for relative in self.evidence_paths},
                self.original_evidence,
            )


if __name__ == '__main__':
    unittest.main(verbosity=2)
