#!/usr/bin/env python3
"""Guard versioned case statistics without importing model/training modules."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from research.evaluation_version import EVALUATION_VERSION

ROOT = Path(__file__).resolve().parents[1]

# Cover statistical calculations and their case/report producers, including
# direct coverage, calibration and ranking construction. Whole producer bodies
# are pinned so an alternate calculation cannot bypass a reviewed helper. Model
# implementations and raw-record ingestion retain their separate contracts.
EVALUATION_DEFINITIONS = {
    'research/selective_v1/core.py': (
        'parse_time', 'match_events',
    ),
    'research/comparison_v1/run_comparison.py': (
        'SEED', 'MATCH_TOLERANCE_HOURS', 'RISK_BUDGET', 'MAX_GAP_POINTS',
        'BOOTSTRAP_ITERATIONS', 'METHOD_ORDER', 'ORBIT_REGIMES', 'PHYSICS_Q0',
        'PHYSICS_FINAL_WEALTH_THRESHOLD', 'finite', 'quiet_ids', 'event_ids',
        'normalize_regime', 'score_coverage', 'event_dict', 'events_from_scores',
        'match_event_dicts', 'calibrate_threshold', 'build_case_results',
        'summarize_results', '_percentile', 'bootstrap', 'evaluation_block',
        'by_regime', 'make_methods', 'run_generic_method', 'detector_case_results',
        'detector_v04_result', 'physics_score_case', 'physics_ml_v1_result',
        'ranking_key', 'main',
    ),
    'research/selective_v1/train_compare.py': (
        'load_document', 'grouped_rows', 'truth_interval_ranking',
        'development_selection_for_candidate', 'main',
    ),
    'research/physics_v1/run_development.py': (
        'truth_interval_feasibility', 'development_event_evaluation',
        'post_calibration_development', 'main',
    ),
    'research/sequential_v1/run_development.py': (
        'sequential_truth_ranking', 'evaluate_base', 'final_development_diagnostic', 'main',
    ),
    'research/confirmatory_v1/run_confirmatory.py': (
        'MIN_RECALL_EXCLUSIVE', 'MAX_FALSE_RATE', 'MAX_MEDIAN_ABS_DELAY_HOURS',
        'MIN_TRUE_POSITIVES', 'finite', 'close', 'calibration_threshold',
        'fit_and_verify_generic', 'physics_reference', 'detector_confirmatory_result',
        'generic_confirmatory_result', 'physics_confirmatory_result', 'metric',
        'ranking', 'evaluate_gate', 'main',
    ),
}
EVALUATION_IMPORTS = {
    'research/selective_v1/core.py': {
        'datetime', 'timezone', 'match_event_intervals', 'parse_time_us',
        'parse_truth_events_us', 'tolerance_hours_to_us',
    },
    'research/comparison_v1/run_comparison.py': {
        'math', 'random', 'statistics', 'parse_time', 'EVALUATION_VERSION',
        'EVENT_MATCHING_VERSION', 'match_event_intervals', 'parse_time_us',
        'parse_truth_events_us', 'validated_truth_events', 'tolerance_hours_to_us',
        'argparse', 'json', 'time', 'Path', 'SupportModel', 'make_candidate',
        'RobustConditionalLinear', 'raw_score_sequence', 'apply_support_threshold',
        'physics_rows', 'SequentialEventLayer', 'SEQUENTIAL_BASE_THRESHOLD',
        'SEQUENTIAL_FINAL_SUPPORT_THRESHOLD', 'sequences', 'rows_for_cases',
        'PhysicsNoiseModel', 'ManeuverPhysicsInverter', 'grouped_rows', 'load_document',
    },
    'research/selective_v1/train_compare.py': {
        'EVALUATION_VERSION', 'EVENT_MATCHING_VERSION', 'match_events',
        'parse_truth_events_us', 'validated_truth_events', 'json', 'Path', 'defaultdict',
    },
    'research/physics_v1/run_development.py': {
        'EVALUATION_VERSION', 'EVENT_MATCHING_VERSION', 'match_events',
        'validated_truth_events',
    },
    'research/sequential_v1/run_development.py': {
        'EVALUATION_VERSION', 'EVENT_MATCHING_VERSION', 'match_events',
        'parse_truth_events_us', 'validated_truth_events',
    },
    'research/confirmatory_v1/run_confirmatory.py': {
        'math', 'cmp', 'argparse', 'json', 'os', 'time', 'Path',
    },
}

# Include complete modules for shared matching and standalone evaluators. This
# also covers helper additions, global rebinding, import targets and constants.
FULL_EVALUATION_MODULES = (
    'research/event_matching.py',
    'research/physics_ml/evaluate.py',
    'tools/evaluate_benchmark.py',
    'research/integrity_v1/run_stress.py',
)

OUTPUT_VERSIONS = {
    'research/comparison_v1/run_comparison.py': (
        'smd-comparison-suite-v1', 'EVALUATION_VERSION', 'EVENT_MATCHING_VERSION',
    ),
    'research/confirmatory_v1/run_confirmatory.py': (
        'smd-confirmatory-v1-final', 'cmp.EVALUATION_VERSION', 'cmp.EVENT_MATCHING_VERSION',
    ),
    'research/physics_ml/evaluate.py': (
        'smd-event-evaluation-v1', 'EVALUATION_VERSION', 'EVENT_MATCHING_VERSION',
    ),
    'tools/evaluate_benchmark.py': (
        'smd-publication-benchmark-evaluation-v1', 'EVALUATION_VERSION', 'EVENT_MATCHING_VERSION',
    ),
    'research/selective_v1/train_compare.py': (
        'smd-selective-ml-v1-model-selection', 'EVALUATION_VERSION', 'EVENT_MATCHING_VERSION',
    ),
    'research/physics_v1/run_development.py': (
        'smd-maneuver-physics-v1-development-calibration', 'EVALUATION_VERSION', 'EVENT_MATCHING_VERSION',
    ),
    'research/sequential_v1/run_development.py': (
        'smd-sequential-v1-development-calibration', 'EVALUATION_VERSION', 'EVENT_MATCHING_VERSION',
    ),
    'research/integrity_v1/run_stress.py': (
        'smd-integrity-security-v1-stress-results', 'EVALUATION_VERSION', 'EVENT_MATCHING_VERSION',
    ),
}

# Append a new version for semantic changes; retain existing entries. Do not
# relabel corrected statistics as an old result or replace its fingerprint.
REVIEWED_EVALUATION_SHA256 = {
    'case-statistics-v1': '585ddd36efa110ab9a33db824e1e39a3a34306c2985abc360f33e42b55a5da44',
    'case-statistics-v2': 'ba9cc2216ae17dae0ac64ba678e30acc49004ebdf779cb8c8827bf7a59732415',
    'case-statistics-v3': '5b96151906b39e75d0809cea2eed224a6556f016863ea9baa966ce45b523bd05',
}


def canonical_ast(value):
    """Omit only an empty field added to FunctionDef in Python 3.12."""
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


def evaluation_fingerprint(sources: dict[str, str]) -> str:
    parts = []
    for path, selected in EVALUATION_DEFINITIONS.items():
        definitions = {}
        imports = {}
        for node in ast.parse(sources[path]).body:
            names = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = [node.name]
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = [target.id for target in targets if isinstance(target, ast.Name)]
            for name in names:
                if name in selected:
                    assert name not in definitions, f'Duplicate evaluation definition {path}:{name}'
                    definitions[name] = canonical_ast(node)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound = alias.asname or alias.name.split('.')[0]
                    if bound in EVALUATION_IMPORTS[path]:
                        assert bound not in imports, f'Duplicate evaluation import {path}:{bound}'
                        imports[bound] = {
                            'module': node.module if isinstance(node, ast.ImportFrom) else None,
                            'level': node.level if isinstance(node, ast.ImportFrom) else 0,
                            'name': alias.name,
                            'asname': alias.asname,
                        }
        assert set(definitions) == set(selected), f'Missing evaluation definition in {path}'
        assert set(imports) == EVALUATION_IMPORTS[path], f'Missing evaluation import in {path}'
        parts.append((path, definitions, imports))
    for path in FULL_EVALUATION_MODULES:
        parts.append((path, canonical_ast(ast.parse(sources[path]))))
    encoded = json.dumps(parts, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def assert_evaluation_contract(version: str, sources: dict[str, str]) -> None:
    assert version in REVIEWED_EVALUATION_SHA256, 'Unreviewed evaluation version'
    actual = evaluation_fingerprint(sources)
    assert actual == REVIEWED_EVALUATION_SHA256[version], (
        'Evaluation semantics changed under an existing version; declare a new '
        'version and retain the previous fingerprint and frozen results'
    )


def assert_output_version(source: str, schema: str, expression: str, field: str = 'evaluation_version') -> None:
    """Check the report producer without executing inference or training."""
    matches = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        keys = {
            key.value: value
            for key, value in zip(node.keys, node.values)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        declared_schema = keys.get('schema')
        if isinstance(declared_schema, ast.Constant) and declared_schema.value == schema:
            matches.append(keys)
    assert len(matches) == 1, f'Missing or ambiguous report schema {schema}'
    value = matches[0].get(field)
    assert value is not None, f'Report {schema} omits {field}'
    assert canonical_ast(value) == canonical_ast(ast.parse(expression, mode='eval').body), (
        f'Report {schema} uses an incorrect {field}'
    )


def assert_version_gate_rejects_unversioned_edits(sources: dict[str, str]) -> None:
    comparison = 'research/comparison_v1/run_comparison.py'
    mutations = (
        ('MATCH_TOLERANCE_HOURS = 24.0', 'MATCH_TOLERANCE_HOURS = 25.0'),
        ("object_months += float(case.get('span_days') or 0.0) * coverage / 30.4375",
         "object_months += float(case.get('span_days') or 0.0) * coverage / 30.0"),
        ("'high_95': _percentile(values, 0.975)", "'high_95': _percentile(values, 0.95)"),
        ('ranked = sorted(results, key=ranking_key, reverse=True)',
         'ranked = sorted(results, key=ranking_key, reverse=False)'),
        ("coverage = sum(row.status == 'scored' for row in transformed) / len(transformed) if transformed else 0.0",
         'coverage = 0.0'),
    )
    for original, replacement in mutations:
        changed = dict(sources)
        assert changed[comparison].count(original) == 1, 'Version mutation target is ambiguous'
        changed[comparison] = changed[comparison].replace(original, replacement, 1)
        try:
            assert_evaluation_contract(EVALUATION_VERSION, changed)
        except AssertionError:
            continue
        raise AssertionError('Evaluation version gate accepted unversioned statistical changes')
    matching = 'research/event_matching.py'
    dependency_mutations = (
        (matching, 'cost = abs(2 * strongest - truth_start - truth_end)',
         'cost = abs(strongest - truth_start)'),
        (matching, 'return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds',
         'return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds // 1000 * 1000'),
        (matching, 'candidate < distances[destination]',
         'candidate <= distances[destination]'),
        (matching, '(prediction[0] - target[0]) / MICROSECONDS_PER_HOUR',
         '(prediction[2] - target[0]) / MICROSECONDS_PER_HOUR'),
        (matching, 'return numerator * MICROSECONDS_PER_HOUR // denominator',
         'return (numerator * MICROSECONDS_PER_HOUR + denominator - 1) // denominator'),
        (matching, 'TRUTH_TIMESTAMP_PATTERN.fullmatch(value)',
         'TRUTH_TIMESTAMP_PATTERN.match(value)'),
        (matching, 'if not isinstance(value, str):',
         'if False:'),
        (matching, 'if offset_hours > 23 or minutes > 59:',
         'if offset_hours > 24 or minutes > 60:'),
        (matching, 'end = parse_truth_timestamp_us(event[end_key]) if end_key in event else start',
         'end = parse_truth_timestamp_us(event.get(end_key) or event[start_key])'),
        (matching, "events = case['truth_events'] if 'truth_events' in case else []",
         "events = case.get('truth_events') or []"),
        (matching, 'if parse_truth_timestamp_us(event[canonical]) != parse_truth_timestamp_us(event[alias]):',
         'if False:'),
        ('research/selective_v1/train_compare.py',
         "    for case in document.get('cases', []):\n        validated_truth_events(case)\n    return document",
         '    return document'),
        ('tools/evaluate_benchmark.py', 'truth = validated_truth_events(case)',
         "truth = case.get('truth_events') or []"),
        (comparison, 'from research.event_matching import (',
         'from research.historical_v1.evaluator import ('),
    )
    for path, original, replacement in dependency_mutations:
        changed = dict(sources)
        assert changed[path].count(original) == 1, 'Matching mutation target is ambiguous'
        changed[path] = changed[path].replace(original, replacement, 1)
        try:
            assert_evaluation_contract(EVALUATION_VERSION, changed)
        except AssertionError:
            continue
        raise AssertionError('Evaluation version gate accepted an unversioned matching change')
    changed = dict(sources)
    changed[matching] += '\nmatch_event_intervals = lambda *args: []\n'
    try:
        assert_evaluation_contract(EVALUATION_VERSION, changed)
    except AssertionError:
        pass
    else:
        raise AssertionError('Evaluation version gate accepted a matching dependency bypass')
    try:
        assert_evaluation_contract('unreviewed-version', sources)
    except AssertionError:
        pass
    else:
        raise AssertionError('Evaluation version gate accepted an unreviewed version')


# Derived from the preconfirmatory runner and checked against the maintained
# source. Only descriptive settings-source values are normalised; numerical
# functions, gate constants and their other source bytes remain frozen.
EXPECTED_RUNNER_SCIENTIFIC_SHA256 = '80fe660398204142c1d5f9ee3ae8abd788851a688e3717d06de12c3555331780'
RUNNER_SCIENTIFIC_CONSTANTS = frozenset({
    'MIN_RECALL_EXCLUSIVE', 'MAX_FALSE_RATE', 'MAX_MEDIAN_ABS_DELAY_HOURS',
    'MIN_TRUE_POSITIVES',
})
RUNNER_SCIENTIFIC_FUNCTIONS = frozenset({
    'finite', 'close', 'calibration_threshold', 'fit_and_verify_generic',
    'physics_reference', 'detector_confirmatory_result',
    'generic_confirmatory_result', 'physics_confirmatory_result',
    'metric', 'ranking', 'evaluate_gate',
})


def runner_scientific_surface(source: str) -> bytes:
    parts = []
    found_constants = set()
    found_functions = set()
    for node in ast.parse(source).body:
        selected = False
        if isinstance(node, ast.FunctionDef) and node.name in RUNNER_SCIENTIFIC_FUNCTIONS:
            found_functions.add(node.name)
            selected = True
        elif isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            found_constants.update(names & RUNNER_SCIENTIFIC_CONSTANTS)
            selected = bool(names & RUNNER_SCIENTIFIC_CONSTANTS)
        if not selected:
            continue
        text = ast.get_source_segment(source, node)
        for child in ast.walk(node):
            if isinstance(child, ast.Dict):
                for key, value in zip(child.keys, child.values):
                    if isinstance(key, ast.Constant) and key.value == 'settings_source':
                        # Normalise descriptive string literals only. Calls and
                        # all other expressions remain covered by the digest.
                        for part in ast.walk(value):
                            if isinstance(part, ast.Constant) and isinstance(part.value, str) and part.value != 'settings_source':
                                text = text.replace(ast.get_source_segment(source, part), "'frozen settings provenance'", 1)
        parts.append(text)
    assert found_constants == RUNNER_SCIENTIFIC_CONSTANTS, 'Missing frozen runner constant'
    assert found_functions == RUNNER_SCIENTIFIC_FUNCTIONS, 'Missing frozen runner function'
    return '\n'.join(parts).encode()


def assert_runner_scientific_freeze(source: str) -> None:
    actual = hashlib.sha256(runner_scientific_surface(source)).hexdigest()
    assert actual == EXPECTED_RUNNER_SCIENTIFIC_SHA256, 'Confirmatory runner scientific surface changed'


def assert_runner_gate_rejects_unapproved_edits(source: str) -> None:
    mutations = [
        source.replace('MIN_RECALL_EXCLUSIVE = 0.20', 'MIN_RECALL_EXCLUSIVE = 0.19', 1),
        source.replace('target_tp >= MIN_TRUE_POSITIVES', 'target_tp > MIN_TRUE_POSITIVES', 1),
        source.replace('reverse=True,', 'reverse=False,', 1),
        source.replace("frozen_item.get('settings_source') or", "frozen_item.pop('settings_source') or", 1),
    ]
    for mutated in mutations:
        assert mutated != source, 'Runner mutation did not alter its target'
        try:
            assert_runner_scientific_freeze(mutated)
        except AssertionError:
            continue
        raise AssertionError('Runner freeze gate accepted an unapproved edit')


def assert_ast_field_compatibility() -> None:
    # FunctionDef gained an empty type_params field in Python 3.12. Model both
    # schemas explicitly so the same source has one pin on Python 3.10+.
    older = ast.parse('def fixture(value):\n    return value\n').body[0]
    newer = ast.parse('def fixture(value):\n    return value\n').body[0]
    older._fields = tuple(name for name in older._fields if name != 'type_params')
    newer._fields = (*older._fields, 'type_params')
    newer.type_params = []
    assert canonical_ast(older) == canonical_ast(newer), 'AST schema changed the version pin'
    newer.type_params = [ast.Name(id='T', ctx=ast.Load())]
    assert canonical_ast(older) != canonical_ast(newer), 'Nonempty type parameters were ignored'


def main() -> None:
    assert_ast_field_compatibility()
    sources = {path: (ROOT / path).read_text() for path in (*EVALUATION_DEFINITIONS, *FULL_EVALUATION_MODULES)}
    assert_evaluation_contract(EVALUATION_VERSION, sources)
    assert_version_gate_rejects_unversioned_edits(sources)
    runner = sources['research/confirmatory_v1/run_confirmatory.py']
    for path, (schema, evaluation_expression, matching_expression) in OUTPUT_VERSIONS.items():
        assert_output_version(sources[path], schema, evaluation_expression)
        assert_output_version(sources[path], schema, matching_expression, 'scoring_version')
    # The original current-runner guard remains separate from historical
    # verification. Moving an audit to archived code must not weaken this check.
    assert_runner_scientific_freeze(runner)
    assert_runner_gate_rejects_unapproved_edits(runner)
    print(
        'Maintained evaluation version verified; matching, timestamp precision, '
        'tolerance, onset delay, dependency, exposure, CI, ranking and coverage '
        'mutations rejected; eight report producers labelled; '
        'four current-runner mutations rejected.'
    )


if __name__ == '__main__':
    main()
