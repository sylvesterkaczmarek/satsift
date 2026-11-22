"""Load the verified, immutable evaluator for recorded confirmatory-v1 results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import ModuleType

__all__ = ['EVALUATOR_VERSION', 'verify_archive', 'load_evaluator']

EVALUATOR_VERSION = 'confirmatory-v1-historical'
EXPECTED_MANIFEST_SHA256 = 'b9759d2893ce7e2ecbacad1a619bb0a06c6ea5b3dad79b0c644a435d1eda5c9a'
_ARCHIVE_ROOT = Path(__file__).resolve().parent
_MANIFEST_SCHEMA = 'smd-historical-evaluator-manifest-v1'
_SOURCE_SNAPSHOT_COMMIT = 'a810250f1153c6ce43372e56d13b80e4fc589a3e'
_REQUIRED_FILES = frozenset({
    'evaluator.py',
    'source-surfaces/detector-scientific.txt',
    'source-surfaces/resolveCatalogueRevisions.txt',
    'source-surfaces/satrecForRecord.txt',
    'source-surfaces/confirmatory-runner-scientific.txt',
})


def _read_bytes(relative: str) -> bytes:
    try:
        return (_ARCHIVE_ROOT / relative).read_bytes()
    except OSError:
        raise AssertionError(f'Historical archive file is missing or unreadable: {relative}') from None


def _verified_archive() -> tuple[dict, dict[str, bytes]]:
    manifest_bytes = _read_bytes('MANIFEST.json')
    actual = hashlib.sha256(manifest_bytes).hexdigest()
    if actual != EXPECTED_MANIFEST_SHA256:
        raise AssertionError(
            f'Historical archive manifest SHA-256 mismatch: expected {EXPECTED_MANIFEST_SHA256}, got {actual}'
        )
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AssertionError('Historical archive manifest is invalid JSON') from None
    if not isinstance(manifest, dict) or manifest.get('schema') != _MANIFEST_SCHEMA:
        raise AssertionError('Historical archive manifest schema mismatch')
    if manifest.get('evaluator_version') != EVALUATOR_VERSION:
        raise AssertionError('Historical archive evaluator version mismatch')
    if manifest.get('source_snapshot_commit') != _SOURCE_SNAPSHOT_COMMIT:
        raise AssertionError('Historical archive source snapshot mismatch')
    entries = manifest.get('files')
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise AssertionError('Historical archive file inventory is invalid')
    paths = [entry.get('path') for entry in entries]
    if not all(isinstance(relative, str) for relative in paths):
        raise AssertionError('Historical archive file paths are invalid')
    if len(paths) != len(_REQUIRED_FILES) or set(paths) != _REQUIRED_FILES:
        raise AssertionError('Historical archive file inventory differs from the frozen closure')

    payloads = {}
    for entry in entries:
        relative = entry['path']
        payload = _read_bytes(relative)
        actual = hashlib.sha256(payload).hexdigest()
        if actual != entry.get('sha256'):
            raise AssertionError(f'Historical archive SHA-256 mismatch: {relative}')
        payloads[relative] = payload
    return manifest, payloads


def verify_archive() -> dict:
    """Verify the trusted manifest and all payloads, returning the manifest."""
    manifest, _ = _verified_archive()
    return manifest


def load_evaluator() -> ModuleType:
    """Execute verified evaluator bytes in a fresh module with no cached state."""
    _, payloads = _verified_archive()
    module = ModuleType(f'{__name__}._verified_evaluator')
    module.__file__ = str(_ARCHIVE_ROOT / 'evaluator.py')
    module.__package__ = __name__
    # Compile the bytes already hashed above, avoiding a second file read.
    code = compile(payloads['evaluator.py'], module.__file__, 'exec')
    exec(code, module.__dict__)
    return module
