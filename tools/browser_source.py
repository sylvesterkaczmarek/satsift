"""Read browser source for inspection without executing a reconstructed program."""
from __future__ import annotations

import json
from pathlib import Path
import re


def browser_source_files(root: Path) -> list[str]:
    root = Path(root)
    manifest = root / 'browser-assets.json'
    if not manifest.is_file():
        source = (root / 'app-3.4.js').read_text()
        if '  function analyzeRaw(' not in source:
            raise ValueError('A modular application requires its browser asset manifest')
        return ['app-3.4.js']
    value = json.loads(manifest.read_text())
    if not isinstance(value, dict) or value.get('schema') != 'smd-browser-assets-v1':
        raise ValueError('Unsupported browser asset manifest')
    modules = value.get('module_sources')
    if not isinstance(modules, list) or not modules or value.get('entry_source') != 'app-3.4.js':
        raise ValueError('Browser sources must declare modules and one entry')
    if any(not isinstance(name, str) or not re.fullmatch(r'app/[a-z][a-z-]*\.js', name) for name in modules):
        raise ValueError('Browser source names must be explicit relative JavaScript paths')
    expected = ['app/common.js', 'app/orbital-input.js', 'app/benchmark.js',
                'app/packages.js', 'app/detection.js', 'app/interface.js']
    if modules != expected:
        raise ValueError('Unknown or reordered browser modules require explicit review')
    files = [*modules, value['entry_source']]
    if len(set(files)) != len(files):
        raise ValueError('Duplicate browser sources')
    return files


def read_browser_source(root: Path) -> str:
    root = Path(root)
    return '\n'.join((root / name).read_text() for name in browser_source_files(root))
