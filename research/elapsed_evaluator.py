"""Retrospective case statistics with explicit elapsed-time exposure evidence.

This module implements ELAPSED-EVALUATION.md independently of the retained v3
training, calibration and historical evaluation producers. It performs no model
inference or operating-point selection.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics

from research.elapsed_exposure import (
    MICROSECONDS_PER_OBJECT_MONTH,
    measure_exposure,
    validate_policy,
    zero_event_poisson_bound,
)
from research.event_matching import (
    EVENT_MATCHING_VERSION,
    match_event_intervals,
    parse_truth_events_us,
    parse_truth_timestamp_us,
    tolerance_hours_to_us,
)

EVALUATION_VERSION = 'case-statistics-v5'
REPORT_SCHEMA = 'smd-retrospective-elapsed-evaluation-v1'
MAX_BOOTSTRAP_SAMPLES = 10_000
DEFAULT_BOOTSTRAP_SAMPLES = 2_000
DEFAULT_BOOTSTRAP_SEED = 3404

_DURATION_FIELDS = (
    'window_microseconds', 'eligible_microseconds', 'covered_microseconds',
    'abstained_microseconds', 'unobserved_microseconds',
)
_BOOTSTRAP_METRICS = (
    'precision', 'recall', 'f1', 'false_events_per_object_month',
    'median_detection_delay_hours', 'median_absolute_detection_delay_hours',
    'covered_fraction', 'elapsed_abstention_fraction', 'uncovered_window_fraction',
)


def _mapping(value, name):
    if not isinstance(value, dict):
        raise ValueError(name + ' must be an object')
    return value


def _array(value, name):
    if not isinstance(value, list):
        raise ValueError(name + ' must be an array')
    return value


def _identifier(value, name, *, missing_allowed=False):
    if value is None and missing_allowed:
        return None
    if type(value) is int and missing_allowed and value >= 0:
        return str(value)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(name + ' must be a nonempty identifier')
    return value


def _timestamp_alias(event, names, *, default=None, required=False):
    supplied = [parse_truth_timestamp_us(event[name]) for name in names if name in event]
    if supplied:
        if any(value != supplied[0] for value in supplied[1:]):
            raise ValueError('Prediction timestamp aliases disagree')
        return supplied[0]
    if required:
        raise ValueError('Prediction is missing its start timestamp')
    return default


def _prediction_interval(event):
    _mapping(event, 'Each predicted event')
    start = _timestamp_alias(event, ('start_utc', 'start'), required=True)
    end = _timestamp_alias(event, ('end_utc', 'end'), default=start)
    strongest = _timestamp_alias(
        event, ('strongest_utc', 'strongest_epoch', 'strongest_epoch_utc'),
        default=start,
    )
    if end < start:
        raise ValueError('Prediction ends before it starts')
    if not start <= strongest <= end:
        raise ValueError('Strongest prediction timestamp must lie within its event interval')
    return start, end, strongest


def _source_schedule(evidence):
    """Compare original source pairs, including excluded gaps, across methods."""
    if not isinstance(evidence, dict) or 'intervals' not in evidence:
        return None
    intervals = evidence['intervals']
    if not isinstance(intervals, list):
        return None
    pairs = []
    for interval in intervals:
        if not isinstance(interval, dict) or not {'start_utc', 'end_utc'} <= interval.keys():
            return None
        pairs.append((
            parse_truth_timestamp_us(interval['start_utc']),
            parse_truth_timestamp_us(interval['end_utc']),
        ))
    return tuple(sorted(set(pairs)))


def _endpoint_supported(timestamp, intervals):
    # A comparison's decision belongs to its right endpoint. Duration remains
    # half-open; membership here uses the separately declared (start, end] rule.
    return any(start < timestamp <= end for start, end in intervals)


def _prepare_cases(raw_cases, policy, tolerance_us):
    _array(raw_cases, 'cases')
    prepared = []
    identifiers = set()
    for raw in raw_cases:
        _mapping(raw, 'Each case')
        case_id = _identifier(raw.get('case_id'), 'case_id')
        if case_id in identifiers:
            raise ValueError('Duplicate case_id')
        identifiers.add(case_id)
        if 'exposure_policy' in raw:
            raise ValueError('Use the common document exposure_policy')
        object_id = _identifier(raw.get('object_id'), 'object_id', missing_allowed=True)
        split = raw.get('split', 'unspecified')
        if split is None:
            split = 'unspecified'
        if not isinstance(split, str) or not split:
            raise ValueError('Case split must be a nonempty string')
        label = raw.get('label_status', 'unknown')
        if label not in ('event-evidence', 'verified-quiet', 'unknown'):
            raise ValueError('label_status must be event-evidence, verified-quiet or unknown')
        truth = tuple(parse_truth_events_us(raw.get('truth_events', []), allow_utc_aliases=True))
        if label == 'event-evidence' and not truth:
            raise ValueError('event-evidence must include documented truth events')
        if label != 'event-evidence' and truth:
            raise ValueError('verified-quiet and unknown cases must not contain truth events')
        if 'predicted_events' not in raw:
            raise ValueError('Each case must explicitly supply predicted_events')
        predictions = tuple(
            _prediction_interval(event)
            for event in _array(raw['predicted_events'], 'predicted_events')
        )
        if 'abstained' in raw and type(raw['abstained']) is not bool:
            raise ValueError('Whole-case abstained must be Boolean')
        evidence = raw.get('exposure_evidence')
        exposure = measure_exposure(evidence, policy)
        if raw.get('abstained') and (exposure['covered_microseconds'] or 0) > 0:
            raise ValueError('Whole-case abstention contradicts supported duration')

        matches = []
        tp = fp = fn = unscored = 0
        support_status = 'not-applicable'
        unsupported_predictions = None
        if label == 'event-evidence':
            matches = match_event_intervals(predictions, truth, tolerance_us)
            tp = len(matches)
            fn = len(truth) - tp
            unscored = len(predictions) - tp
        elif label == 'verified-quiet':
            fp = len(predictions)
            if exposure['status'] == 'available':
                unsupported_predictions = sum(
                    not all(_endpoint_supported(timestamp, exposure['covered_intervals_us'])
                            for timestamp in prediction)
                    for prediction in predictions
                )
                support_status = 'consistent' if not unsupported_predictions else 'inconsistent'
            else:
                support_status = 'unavailable-exposure'
        else:
            unscored = len(predictions)
        prepared.append({
            'case_id': case_id, 'object_id': object_id, 'split': split,
            'label_status': label, 'truth': truth, 'predictions': predictions,
            'exposure': exposure, 'source_schedule': _source_schedule(evidence),
            'true_positives': tp, 'false_positives': fp, 'false_negatives': fn,
            'unscored_predictions': unscored,
            'delays': [item['delay_hours'] for item in matches],
            'absolute_delays': [abs(item['delay_hours']) for item in matches],
            'matches': matches, 'event_support_status': support_status,
            'unsupported_quiet_predictions': unsupported_predictions,
        })

    # Ordinary input windows cannot duplicate object-time. This validation is
    # intentionally not rerun on bootstrap draws, whose multiplicity is real.
    windows = {}
    for case in prepared:
        start, end = case['exposure']['window_start_us'], case['exposure']['window_end_us']
        if case['object_id'] is not None and start is not None and end is not None and end > start:
            windows.setdefault(case['object_id'], []).append((start, end))
    for values in windows.values():
        previous_end = None
        for start, end in sorted(values):
            if previous_end is not None and start < previous_end:
                raise ValueError('Overlapping case windows for the same object')
            previous_end = end
    return prepared


def _exposure_totals(cases):
    complete = [case for case in cases if case['exposure']['status'] == 'available']
    totals = {
        'known_' + name: sum(
            case['exposure'][name] for case in cases
            if case['exposure'][name] is not None
        )
        for name in _DURATION_FIELDS
    }
    unknown = len(cases) - len(complete)
    missing_identity = sum(case['object_id'] is None for case in cases)
    all_known = bool(cases) and unknown == 0 and missing_identity == 0
    window = totals['known_window_microseconds']
    eligible = totals['known_eligible_microseconds']
    covered = totals['known_covered_microseconds']
    abstained = totals['known_abstained_microseconds']
    return {
        'status': ('empty-selection' if not cases else
                   'missing-object-identity' if missing_identity else
                   'incomplete' if unknown else 'available'),
        'missing_object_id_cases': missing_identity,
        'complete_cases': len(complete),
        'incomplete_cases': unknown,
        **totals,
        'covered_fraction': covered / window if all_known and window else None,
        'elapsed_abstention_fraction': abstained / eligible if all_known and eligible else None,
        'uncovered_window_fraction': (window - covered) / window if all_known and window else None,
    }


def _summarize(cases):
    tp = sum(case['true_positives'] for case in cases)
    fp = sum(case['false_positives'] for case in cases)
    fn = sum(case['false_negatives'] for case in cases)
    delays = [value for case in cases for value in case['delays']]
    absolute_delays = [value for case in cases for value in case['absolute_delays']]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    if tp == 0 and fn > 0:
        f1 = 0.0
    elif precision is not None and recall is not None and precision + recall:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = None
    quiet = [case for case in cases if case['label_status'] == 'verified-quiet']
    known_quiet = [case for case in quiet if case['exposure']['status'] == 'available']
    incomplete_quiet = len(quiet) - len(known_quiet)
    known_quiet_us = sum(case['exposure']['covered_microseconds'] for case in known_quiet)
    known_quiet_months = known_quiet_us / MICROSECONDS_PER_OBJECT_MONTH
    missing_identity = sum(case['object_id'] is None for case in cases)
    inconsistent = sum(case['event_support_status'] == 'inconsistent' for case in quiet)
    if not quiet:
        rate_status = 'no-quiet-cases'
    elif incomplete_quiet:
        rate_status = 'missing-exposure'
    elif missing_identity:
        rate_status = 'missing-object-identity'
    elif inconsistent:
        rate_status = 'inconsistent-event-support'
    elif known_quiet_us == 0:
        rate_status = 'zero-exposure'
    else:
        rate_status = 'available'
    complete_quiet_months = None if incomplete_quiet or missing_identity else known_quiet_months
    exposure = _exposure_totals(cases)
    quiet_exposure = _exposure_totals(quiet)
    bound = zero_event_poisson_bound(
        fp, complete_quiet_months,
        exposure_status='available' if rate_status in (
            'available', 'zero-exposure', 'inconsistent-event-support',
        ) else 'unavailable',
        event_support_consistent=rate_status != 'inconsistent-event-support',
    )
    return {
        'cases': len(cases),
        'objects_with_identity': len({case['object_id'] for case in cases if case['object_id'] is not None}),
        'missing_object_id_cases': missing_identity,
        'positive_cases': sum(case['label_status'] == 'event-evidence' for case in cases),
        'verified_quiet_cases': len(quiet),
        'truth_events': sum(len(case['truth']) for case in cases),
        'predicted_events': sum(len(case['predictions']) for case in cases),
        'true_positives': tp, 'false_positives': fp, 'false_negatives': fn,
        'unscored_predictions': sum(case['unscored_predictions'] for case in cases),
        'precision': precision, 'recall': recall, 'f1': f1,
        'median_detection_delay_hours': statistics.median(delays) if delays else None,
        'median_absolute_detection_delay_hours': statistics.median(absolute_delays) if absolute_delays else None,
        'covered_verified_quiet_microseconds': None if complete_quiet_months is None else known_quiet_us,
        'covered_verified_quiet_object_months': complete_quiet_months,
        'known_covered_verified_quiet_microseconds': known_quiet_us,
        'known_covered_verified_quiet_object_months': known_quiet_months,
        'incomplete_verified_quiet_cases': incomplete_quiet,
        'inconsistent_quiet_event_support_cases': inconsistent,
        'false_events_per_object_month': fp / known_quiet_months if rate_status == 'available' else None,
        'false_event_rate_status': rate_status,
        'exposure': exposure,
        'verified_quiet_exposure': quiet_exposure,
        'covered_fraction': exposure['covered_fraction'],
        'elapsed_abstention_fraction': exposure['elapsed_abstention_fraction'],
        'uncovered_window_fraction': exposure['uncovered_window_fraction'],
        'zero_event_poisson_bound': bound,
    }


def _percentile(values, probability):
    if not values:
        return None
    material = sorted(values)
    position = (len(material) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    return material[lower] * (upper - position) + material[upper] * (position - lower) if lower != upper else material[lower]


def _relevant_cases(cases, metric):
    if metric == 'false_events_per_object_month':
        return [
            case for case in cases
            if case['label_status'] == 'verified-quiet'
            and case['exposure']['status'] == 'available'
            and case['exposure']['covered_microseconds'] > 0
            and case['event_support_status'] == 'consistent'
        ]
    if metric == 'recall':
        return [case for case in cases if case['label_status'] == 'event-evidence' and case['truth']]
    if metric.startswith('median_'):
        return [case for case in cases if case['delays']]
    if metric == 'precision':
        return [case for case in cases if case['true_positives'] + case['false_positives'] > 0]
    if metric == 'f1':
        return [case for case in cases if case['true_positives'] + case['false_positives'] + case['false_negatives'] > 0]
    if metric == 'elapsed_abstention_fraction':
        return [case for case in cases if case['exposure']['status'] == 'available'
                and case['exposure']['eligible_microseconds'] > 0]
    return [
        case for case in cases
        if case['exposure']['status'] == 'available'
        and case['exposure']['window_microseconds'] > 0
    ]


def _bootstrap(cases, summary, samples, seed):
    by_object = {}
    missing_identity = any(case['object_id'] is None for case in cases)
    for case in cases:
        if case['object_id'] is not None:
            by_object.setdefault(case['object_id'], []).append(case)
    objects = sorted(by_object)
    values = {metric: [] for metric in _BOOTSTRAP_METRICS}
    drawn_replicates = 0
    if objects and not missing_identity:
        rng = random.Random(seed)
        for _ in range(samples):
            drawn = []
            for _slot in objects:
                drawn.extend(by_object[rng.choice(objects)])
            sampled = _summarize(drawn)
            drawn_replicates += 1
            for metric in _BOOTSTRAP_METRICS:
                value = sampled[metric]
                if value is not None and math.isfinite(value):
                    values[metric].append(float(value))
    result = {}
    for metric in _BOOTSTRAP_METRICS:
        independent_objects = len({
            case['object_id'] for case in _relevant_cases(cases, metric)
            if case['object_id'] is not None
        })
        material = values[metric]
        empirical = {
            'low_95': _percentile(material, 0.025),
            'high_95': _percentile(material, 0.975),
        }
        zero_events = (metric == 'false_events_per_object_month'
                       and summary['false_event_rate_status'] == 'available'
                       and summary['false_positives'] == 0)
        limitations = []
        if zero_events:
            limitations.append('Zero observed events cannot establish a zero population-risk upper limit.')
        if independent_objects < 2:
            limitations.append('Fewer than two relevant independent objects.')
        if drawn_replicates and len(material) < drawn_replicates:
            limitations.append('Percentiles condition on defined replicates; undefined replicates are excluded.')
        if missing_identity:
            status = 'missing-object-identity'
        elif metric == 'false_events_per_object_month' and summary['false_event_rate_status'] != 'available':
            status = summary['false_event_rate_status']
        elif metric in ('covered_fraction', 'elapsed_abstention_fraction', 'uncovered_window_fraction') and summary['exposure']['incomplete_cases']:
            status = 'missing-exposure'
        elif independent_objects < 2:
            status = 'insufficient-clusters'
        elif samples == 0:
            status = 'not-requested'
        elif summary[metric] is None or not material:
            status = 'undefined'
        elif zero_events:
            status = 'zero-event-degenerate'
        elif min(material) == max(material):
            status = 'degenerate'
            limitations.append('Identical replicate values do not establish zero inferential uncertainty.')
        elif len(material) < samples:
            status = 'conditional-defined-replicates'
        else:
            status = 'available'
        inferential = status in ('available', 'conditional-defined-replicates')
        result[metric] = {
            'method': 'object-cluster-percentile-bootstrap',
            'confidence_level': 0.95,
            'status': status,
            'low_95': empirical['low_95'] if inferential else None,
            'high_95': empirical['high_95'] if inferential else None,
            'empirical_percentiles': empirical,
            'requested_replicates': samples,
            'drawn_replicates': drawn_replicates,
            'defined_replicates': len(material),
            'excluded_replicates': drawn_replicates - len(material),
            'independent_objects': independent_objects,
            'zero_event_degenerate': zero_events,
            'limitations': limitations,
            'interpretation': (
                'Percentile intervals are conditional on the empirical object sample and defined replicates; '
                'they are not an operational risk guarantee.'
            ),
        }
    return result


def _case_report(case):
    return {
        'case_id': case['case_id'], 'object_id': case['object_id'],
        'split': case['split'], 'label_status': case['label_status'],
        'truth_events': len(case['truth']), 'predicted_events': len(case['predictions']),
        'true_positives': case['true_positives'],
        'false_positives': case['false_positives'],
        'false_negatives': case['false_negatives'],
        'unscored_predictions': case['unscored_predictions'],
        'matches': case['matches'],
        'exposure': case['exposure'],
        'quiet_event_support_status': case['event_support_status'],
        'unsupported_quiet_predictions': case['unsupported_quiet_predictions'],
    }


def _compare_methods(methods):
    if len(methods) == 1:
        missing = sum(case['exposure']['status'] != 'available' or case['object_id'] is None for case in methods[0][1])
        return {
            'status': 'single-method', 'methods': 1,
            'incomplete_case_method_pairs': missing,
            'interpretation': 'No cross-method comparison was made.',
        }
    mapped = [{case['case_id']: case for case in cases} for _method, cases in methods]
    reference = mapped[0]
    if any(item.keys() != reference.keys() for item in mapped):
        raise ValueError('Methods must identify the same cases')
    incomplete = 0
    for case_id in reference:
        group = [item[case_id] for item in mapped]
        for key in ('split', 'label_status'):
            if len({case[key] for case in group}) != 1:
                raise ValueError('Method case metadata disagree')
        if len({tuple(sorted(case['truth'])) for case in group}) != 1:
            raise ValueError('Methods must use the same truth intervals')
        if len({case['object_id'] for case in group if case['object_id'] is not None}) > 1:
            raise ValueError('Method case object identities disagree')
        for key in ('window_start_us', 'window_end_us'):
            if len({case['exposure'][key] for case in group if case['exposure'][key] is not None}) > 1:
                raise ValueError('Method case windows disagree')
        if len({case['source_schedule'] for case in group if case['source_schedule'] is not None}) > 1:
            raise ValueError('Methods must use the same source-observation schedule')
        incomplete += sum(case['exposure']['status'] != 'available' or case['object_id'] is None for case in group)
    return {
        'status': 'comparable' if incomplete == 0 else 'incomplete-evidence',
        'methods': len(methods),
        'incomplete_case_method_pairs': incomplete,
        'interpretation': (
            'Methods share case identities, windows, truth, policy and supplied source schedules; '
            'their support decisions may differ.'
            if incomplete == 0 else
            'Missing identities or support evidence prevent a complete elapsed-exposure comparison.'
        ),
    }


def evaluate_document(
    document, *, split='all', bootstrap_samples=DEFAULT_BOOTSTRAP_SAMPLES,
    seed=DEFAULT_BOOTSTRAP_SEED,
):
    """Evaluate supplied retained predictions; never infer missing elapsed support."""
    _mapping(document, 'document')
    if not isinstance(split, str) or not split:
        raise ValueError('split must be a nonempty string')
    if type(bootstrap_samples) is not int or not 0 <= bootstrap_samples <= MAX_BOOTSTRAP_SAMPLES:
        raise ValueError('bootstrap_samples must be an integer between 0 and 10000')
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError('seed must be an integer between 0 and 2**64 - 1')
    try:
        encoded = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError('Input must be a finite JSON document') from exc
    policy = validate_policy(document.get('exposure_policy'))
    tolerance = document.get('matching_tolerance_hours', 24.0)
    if type(tolerance) not in (int, float):
        raise ValueError('matching_tolerance_hours must be a finite nonnegative number')
    tolerance_us = tolerance_hours_to_us(tolerance)
    multi = 'methods' in document
    if multi and 'cases' in document:
        raise ValueError('Supply cases or methods, not both')
    if multi:
        raw_methods = _array(document['methods'], 'methods')
        if not raw_methods:
            raise ValueError('methods must not be empty')
        methods = []
        names = set()
        for item in raw_methods:
            _mapping(item, 'Each method')
            name = _identifier(item.get('method'), 'method')
            if name in names:
                raise ValueError('Duplicate method identifier')
            names.add(name)
            if 'exposure_policy' in item:
                raise ValueError('Use the common document exposure_policy')
            methods.append((name, _prepare_cases(item.get('cases'), policy, tolerance_us)))
    else:
        name = document.get('method')
        if name is not None:
            name = _identifier(name, 'method')
        methods = [(name, _prepare_cases(document.get('cases'), policy, tolerance_us))]
    comparability = _compare_methods(methods)
    report = {
        'schema': REPORT_SCHEMA,
        'evaluation_version': EVALUATION_VERSION,
        'scoring_version': EVENT_MATCHING_VERSION,
        'analysis_scope': 'retrospective',
        'split': split,
        'matching_tolerance_hours': tolerance,
        'exposure_policy': policy,
        'exposure_policy_status': 'available' if policy is not None else 'missing-or-incomplete',
        'input_sha256': hashlib.sha256(encoded).hexdigest(),
        'input_digest_representation': 'canonical-json-utf8',
        'bootstrap': {
            'unit': 'object', 'samples_requested': bootstrap_samples,
            'seed': seed, 'confidence_level': 0.95,
        },
        'comparability': comparability,
        'limitations': [
            'Elapsed exposure requires explicit timestamped source pairs and aligned support decisions.',
            'Missing temporal evidence is not reconstructed from span_days, coverage fractions or row counts.',
            'Unmatched candidates on event-evidence cases are unscored under positive-unlabelled semantics.',
            'Quiet event endpoints must lie in supported endpoint domains; continuous support between grouped endpoints is not inferred.',
            'Bootstrap intervals describe the empirical object sample; zero events do not establish zero underlying risk.',
            'The supplementary Poisson upper value depends on unverified model and observation assumptions.',
            'Retrospective evaluation does not restore an untouched holdout or revise a frozen study.',
        ],
    }
    evaluated = []
    for name, cases in methods:
        selected = [case for case in cases if split == 'all' or case['split'] == split]
        summary = _summarize(selected)
        item = {
            'summary': summary,
            'case_results': [_case_report(case) for case in selected],
            'confidence_intervals': _bootstrap(selected, summary, bootstrap_samples, seed),
        }
        if multi:
            item = {'method': name, **item}
        elif name is not None:
            report['method'] = name
        evaluated.append(item)
    if multi:
        report['methods'] = evaluated
    else:
        report.update(evaluated[0])
    return report
