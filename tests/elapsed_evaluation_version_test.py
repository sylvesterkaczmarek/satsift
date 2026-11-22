#!/usr/bin/env python3
"""Pin the separate elapsed-time evaluator without changing legacy contracts."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'case-statistics-v5'
MODULES = (
    'research/elapsed_exposure.py',
    'research/elapsed_evaluator.py',
    'tools/evaluate_elapsed_benchmark.py',
    'research/event_matching.py',
)
# Register a new version for changed semantics. Previous v1-v3 fingerprints
# remain in evaluation_version_test.py with their unchanged implementations.
REVIEWED_EVALUATION_SHA256 = {
    'case-statistics-v4': '5fc76853026a3d4960950dbfe5355d230277fbcf33b863ac96646362f5cefc90',
    'case-statistics-v5': '63b4416e49779d6dde0bd06b0a99945e09d7c7c4b1bb5ad293ec8cd5e313d934',
}


def canonical_ast(value):
    if isinstance(value, ast.AST):
        return {
            'node': type(value).__name__,
            **{
                name: canonical_ast(item)
                for name, item in ast.iter_fields(value)
                if name != 'type_params' or item
            },
        }
    if isinstance(value, list):
        return [canonical_ast(item) for item in value]
    return value


def fingerprint(sources):
    assert set(sources) == set(MODULES), 'Incomplete elapsed evaluation source surface'
    parts = [(name, canonical_ast(ast.parse(sources[name]))) for name in MODULES]
    encoded = json.dumps(parts, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def verify(version, sources):
    assert version in REVIEWED_EVALUATION_SHA256, 'Unreviewed elapsed evaluation version'
    assert fingerprint(sources) == REVIEWED_EVALUATION_SHA256[version], (
        'Elapsed evaluation changed under an existing version; retain its pin '
        'and declare a separately reviewed version'
    )


def declared_constant(source, name):
    values = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            values.append(ast.literal_eval(node.value))
    assert len(values) == 1, 'Missing or ambiguous version constant ' + name
    return values[0]


def must_reject(version, sources):
    try:
        verify(version, sources)
    except AssertionError:
        return
    raise AssertionError('Elapsed evaluation guard accepted an unreviewed change')


def exercise_guard(sources):
    rejected = 0
    for name in MODULES:
        original_tree = ast.parse(sources[name])
        # Every top-level function is covered, including validation, interval
        # arithmetic, aggregation, bootstrap, matching and output protection.
        function_indices = [
            index for index, node in enumerate(original_tree.body)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert function_indices, 'No functions covered in ' + name
        for index in function_indices:
            changed_tree = copy.deepcopy(original_tree)
            function = changed_tree.body[index]
            function.body.insert(0, ast.parse('raise RuntimeError("unreviewed statistical change")').body[0])
            ast.fix_missing_locations(changed_tree)
            changed = dict(sources)
            changed[name] = ast.unparse(changed_tree)
            must_reject(VERSION, changed)
            rejected += 1
        # A module-level rebinding could bypass an otherwise unchanged helper.
        changed = dict(sources)
        target = original_tree.body[function_indices[0]].name
        changed[name] += '\n' + target + ' = lambda *args, **kwargs: None\n'
        must_reject(VERSION, changed)
        rejected += 1
    # Bind non-function policy values, imports, models and assumption labels too.
    for name in MODULES:
        tree = ast.parse(sources[name])
        candidates = [
            index for index, node in enumerate(tree.body)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
        ]
        for index in candidates:
            changed_tree = copy.deepcopy(tree)
            changed_tree.body[index].value = ast.Constant(value='unreviewed policy')
            ast.fix_missing_locations(changed_tree)
            changed = dict(sources)
            changed[name] = ast.unparse(changed_tree)
            must_reject(VERSION, changed)
            rejected += 1
    must_reject('unreviewed-version', sources)
    rejected += 1
    return rejected


def assert_python_ast_compatibility():
    old = ast.parse('def sample(value):\n    return value + 1\n')
    new = copy.deepcopy(old)
    function = new.body[0]
    if 'type_params' not in function._fields:
        function._fields += ('type_params',)
    function.type_params = []
    assert canonical_ast(old) == canonical_ast(new)
    function.type_params = [ast.Name(id='T', ctx=ast.Load())]
    assert canonical_ast(old) != canonical_ast(new)


def main():
    sources = {name: (ROOT / name).read_text() for name in MODULES}
    if '--fingerprint' in sys.argv:
        print(fingerprint(sources))
        return
    assert declared_constant(sources['research/elapsed_evaluator.py'], 'EVALUATION_VERSION') == VERSION
    assert declared_constant(sources['research/event_matching.py'], 'EVENT_MATCHING_VERSION') == 'event-matching-v3'
    verify(VERSION, sources)
    assert_python_ast_compatibility()
    rejected = exercise_guard(sources)
    print(f'Elapsed evaluator {VERSION} and complete dependency fingerprint verified; {rejected} unreviewed mutations rejected.')


if __name__ == '__main__':
    main()
