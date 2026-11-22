#!/usr/bin/env python3
"""Write a fresh retrospective report using explicit elapsed exposure evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))

from research.elapsed_evaluator import evaluate_document

PROTECTED_DIRECTORIES = (
    'benchmark-data', 'benchmark-results', 'benchmark', 'research',
    '.git', 'config', 'deployment',
)
PROTECTED_FILES = (
    'benchmark-template.json', 'vendor-integrity.json',
)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON object key')
        result[key] = value
    return result


def _reject_nonfinite(_value):
    raise ValueError('Nonfinite JSON numbers are not accepted')


def _inside(path, directory):
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def validate_output_destination(output, source, *, root=ROOT):
    """Resolve parent aliases, but refuse any existing or symlink file target."""
    destination = Path(os.path.abspath(Path(output).expanduser()))
    if destination.is_symlink() or os.path.lexists(destination):
        raise ValueError('Output destination must be a fresh file and cannot be a symlink')
    parent = destination.parent.resolve()
    destination = parent / destination.name
    source = Path(source).resolve(strict=True)
    root = Path(root).resolve()
    if destination == source:
        raise ValueError('Output cannot overwrite the input')
    if destination.is_symlink() or os.path.lexists(destination):
        raise ValueError('Output destination must be a fresh file and cannot be a symlink')
    if any(_inside(destination, root / name) for name in PROTECTED_DIRECTORIES):
        raise ValueError('Output destination is inside a protected source, archive or data location')
    if destination in {root / name for name in PROTECTED_FILES}:
        raise ValueError('Output destination is a protected repository file')
    if destination.parent == root and destination.name.startswith('public-evidence-manifest-'):
        raise ValueError('Output destination is a protected manifest')
    if destination.suffix == '.sha256':
        raise ValueError('An evaluation report cannot replace or create a checksum sidecar')
    return destination


def _open_directory(path):
    """Open the resolved output parent without following a changed symlink."""
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path.anchor, flags)
    try:
        for component in path.parts[1:]:
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(component, flags, dir_fd=descriptor)
            if not stat.S_ISDIR(os.fstat(child).st_mode):
                os.close(child)
                raise ValueError('Output parent is not a directory')
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def write_fresh_report(destination, encoded):
    """Exclusive creation preserves an existing file even if it appears late."""
    parent = _open_directory(destination.parent)
    descriptor = None
    created_stat = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(destination.name, flags, 0o600, dir_fd=parent)
        created_stat = os.fstat(descriptor)
        with os.fdopen(descriptor, 'wb') as handle:
            descriptor = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(parent)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        if created_stat is not None:
            try:
                current = os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (created_stat.st_dev, created_stat.st_ino):
                    os.unlink(destination.name, dir_fd=parent)
            except FileNotFoundError:
                pass
        raise
    finally:
        os.close(parent)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Evaluate retained predictions with explicit elapsed support; create a fresh retrospective report.'
    )
    parser.add_argument('results', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--split', default='all')
    parser.add_argument('--bootstrap-samples', type=int, default=2000)
    parser.add_argument('--seed', type=int, default=3404)
    args = parser.parse_args(argv)
    try:
        source = args.results.expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError('Input must be a regular file')
        destination = validate_output_destination(args.output, source)
        raw = source.read_bytes()
        document = json.loads(
            raw.decode('utf-8'), object_pairs_hook=_json_object,
            parse_constant=_reject_nonfinite,
        )
        report = evaluate_document(
            document, split=args.split,
            bootstrap_samples=args.bootstrap_samples, seed=args.seed,
        )
        # The API digest identifies canonical JSON. Retain the independently
        # labelled original-byte digest as well; never include a local path.
        report['input_file_sha256'] = hashlib.sha256(raw).hexdigest()
        report['input_file_digest_representation'] = 'raw-bytes'
        encoded = (json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
        destination = validate_output_destination(args.output, source)
        write_fresh_report(destination, encoded)
    except (ValueError, UnicodeError) as exc:
        parser.exit(2, 'Evaluation refused: ' + str(exc) + '\n')
    except OSError as exc:
        parser.exit(2, 'Evaluation I/O failed: ' + (exc.strerror or 'filesystem error') + '\n')
    print('Retrospective evaluation written.')


if __name__ == '__main__':
    main()
