"""Explicit source and immutable public identities for the browser modules."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PREFIX = '/satellite-maneuver-detector'
MODULE_SOURCES = (
    'app/common.js', 'app/orbital-input.js', 'app/benchmark.js',
    'app/packages.js', 'app/detection.js', 'app/interface.js',
)
ENTRY_SOURCE = 'app-3.4.js'


def _unique_object(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError('duplicate browser asset manifest key')
        output[key] = value
    return output


def validate_manifest(repo: Path = ROOT) -> dict:
    path = repo / 'browser-assets.json'
    if path.is_symlink() or not path.is_file():
        raise ValueError('browser asset manifest must be a regular repository file')
    manifest = json.loads(path.read_text(), object_pairs_hook=_unique_object)
    expected = {
        'schema': 'smd-browser-assets-v1',
        'module_sources': list(MODULE_SOURCES),
        'entry_source': ENTRY_SOURCE,
    }
    if manifest != expected:
        raise ValueError('browser asset manifest differs from the explicit public source allowlist')
    return manifest


def asset_record(repo: Path, source: str) -> dict[str, str]:
    if source not in (*MODULE_SOURCES, ENTRY_SOURCE):
        raise ValueError('unknown browser asset source')
    root = repo.resolve()
    path = repo / source
    if path.is_symlink() or not path.is_file() or path.resolve() != root / source:
        raise ValueError('browser asset source must be a regular file beneath the repository')
    digest = hashlib.sha256(path.read_bytes()).digest()
    hexdigest = digest.hex()
    name = 'bootstrap' if source == ENTRY_SOURCE else Path(source).stem
    target = f'app/{name}-{hexdigest[:12]}.js'
    return {
        'name': name, 'source': source, 'target': target,
        'url': f'{PUBLIC_PREFIX}/{target}', 'sha256': hexdigest,
        'integrity': 'sha256-' + base64.b64encode(digest).decode('ascii'),
    }


def module_assets(repo: Path = ROOT) -> list[dict[str, str]]:
    validate_manifest(repo)
    return [asset_record(repo, source) for source in MODULE_SOURCES]


def browser_assets(repo: Path = ROOT) -> list[dict[str, str]]:
    return module_assets(repo) + [asset_record(repo, ENTRY_SOURCE)]


def source_for_route(repo: Path, path: str) -> str | None:
    """Resolve only current, content-addressed assets; canonical sources stay private."""
    return next((asset['source'] for asset in browser_assets(repo) if asset['url'] == path), None)
