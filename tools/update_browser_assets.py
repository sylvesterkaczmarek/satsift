#!/usr/bin/env python3
"""Refresh checked-in browser URLs and integrity values without bundling source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_assets import ROOT, ENTRY_SOURCE, asset_record, module_assets

MODULE_BEGIN = '// BEGIN MODULE ASSETS'
MODULE_END = '// END MODULE ASSETS'
HTML_BEGIN = '<!-- BEGIN BROWSER MODULE SCRIPTS -->'
HTML_END = '<!-- END BROWSER MODULE SCRIPTS -->'


def replace_region(text: str, begin: str, end: str, replacement: str) -> str:
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError('expected exactly one browser asset region')
    first, last = text.index(begin), text.index(end)
    if first >= last:
        raise ValueError('browser asset region markers are reversed')
    return text[:first + len(begin)] + '\n' + replacement + '\n' + text[last:]


def expected_files(repo: Path = ROOT) -> dict[str, str]:
    modules = module_assets(repo)
    records = [{key: asset[key] for key in ('name', 'url', 'integrity')} for asset in modules]
    bootstrap = asset_record(repo, ENTRY_SOURCE)
    entry = (repo / ENTRY_SOURCE).read_text()
    declaration = '  const MODULE_ASSETS = Object.freeze(' + json.dumps(records, indent=2) + ');'
    entry = replace_region(entry, MODULE_BEGIN, MODULE_END, declaration)
    digest = hashlib.sha256(entry.encode()).digest()
    # Compute the entry identity after refreshing its dependency URLs, without writing in check mode.
    import base64
    bootstrap.update(
        target=f'app/bootstrap-{digest.hex()[:12]}.js',
        url=f'/satellite-maneuver-detector/app/bootstrap-{digest.hex()[:12]}.js',
        sha256=digest.hex(), integrity='sha256-' + base64.b64encode(digest).decode('ascii'),
    )
    scripts = '\n'.join(
        f'<script defer src="{asset["url"]}" integrity="{asset["integrity"]}" crossorigin="anonymous"></script>'
        for asset in [*modules, bootstrap]
    )
    index_path = repo / 'index.html'
    if index_path.is_symlink() or not index_path.is_file() or index_path.resolve() != repo.resolve() / 'index.html':
        raise ValueError('index.html must be a regular file beneath the repository')
    index = index_path.read_text()
    if HTML_BEGIN not in index and HTML_END not in index:
        legacy = re.compile(r'<script defer src="/satellite-maneuver-detector/app-3\.4\.js\?v=[0-9a-f]{12}"></script>')
        if len(legacy.findall(index)) != 1:
            raise ValueError('expected one existing application script before creating the managed region')
        index = legacy.sub(HTML_BEGIN + '\n' + HTML_END, index)
    index = replace_region(index, HTML_BEGIN, HTML_END, scripts)
    return {ENTRY_SOURCE: entry, 'index.html': index}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='fail on stale URLs without modifying files')
    args = parser.parse_args(argv)
    try:
        expected = expected_files()
        changed = [name for name, text in expected.items() if (ROOT / name).read_text() != text]
        if args.check:
            if changed:
                print('Stale browser asset identities: ' + ', '.join(changed), file=sys.stderr)
                return 1
        else:
            for name in changed:
                (ROOT / name).write_text(expected[name])
        print('Browser asset identities are current.' if not changed else 'Updated browser asset identities.')
        return 0
    except (ValueError, OSError) as exc:
        print('Browser asset validation failed: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
