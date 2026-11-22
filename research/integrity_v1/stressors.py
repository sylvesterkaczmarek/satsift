#!/usr/bin/env python3
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Callable


NUMERIC_FIELDS = (
    'MEAN_MOTION',
    'ECCENTRICITY',
    'INCLINATION',
    'RA_OF_ASC_NODE',
    'ARG_OF_PERICENTER',
    'MEAN_ANOMALY',
    'BSTAR',
)
ORBIT_FIELDS = (
    'MEAN_MOTION',
    'ECCENTRICITY',
    'INCLINATION',
    'RA_OF_ASC_NODE',
    'ARG_OF_PERICENTER',
    'MEAN_ANOMALY',
)


def _parse_time(value: str) -> datetime:
    text = str(value).strip().replace('Z', '+00:00')
    result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _finite_float(record: dict, field: str, default: float = 0.0) -> float:
    try:
        return float(record.get(field, default))
    except (TypeError, ValueError):
        return float(default)


def _middle_index(records: list[dict]) -> int:
    if len(records) < 3:
        return max(0, len(records) // 2)
    return min(len(records) - 2, max(1, len(records) // 2))


def _stable_regime_target_index(records: list[dict]) -> int:
    """Choose an interior raw record isolated from near-simultaneous catalogue revisions."""
    timed = []
    for index, record in enumerate(records):
        try:
            timed.append((_parse_time(record['EPOCH']), index))
        except Exception:
            continue
    timed.sort(key=lambda item: item[0])
    if len(timed) < 3:
        return _middle_index(records)
    midpoint = (len(timed) - 1) / 2.0
    candidates = []
    for position in range(1, len(timed) - 1):
        epoch, original_index = timed[position]
        previous = timed[position - 1][0]
        following = timed[position + 1][0]
        isolation = min((epoch - previous).total_seconds(), (following - epoch).total_seconds())
        candidates.append((isolation, -abs(position - midpoint), original_index))
    if not candidates:
        return _middle_index(records)
    return max(candidates)[2]


def _increment_metadata(record: dict, *, seconds: int = 120) -> None:
    try:
        creation = _parse_time(record.get('CREATION_DATE') or record['EPOCH']) + timedelta(seconds=seconds)
        record['CREATION_DATE'] = _format_time(creation)
    except Exception:
        pass
    try:
        record['ELEMENT_SET_NO'] = int(record.get('ELEMENT_SET_NO', 0)) + 1
    except (TypeError, ValueError):
        record['ELEMENT_SET_NO'] = 1
    gp = str(record.get('GP_ID') or '').strip()
    if gp.isdigit():
        record['GP_ID'] = str(int(gp) + 1)
    elif gp:
        record['GP_ID'] = gp + '-R'


def _interpolated_record(first: dict, second: dict, fraction: float = 0.5) -> dict:
    output = copy.deepcopy(first)
    first_epoch = _parse_time(first['EPOCH'])
    second_epoch = _parse_time(second['EPOCH'])
    output['EPOCH'] = _format_time(first_epoch + (second_epoch - first_epoch) * fraction)
    for field in NUMERIC_FIELDS:
        a = _finite_float(first, field)
        b = _finite_float(second, field, a)
        output[field] = a + fraction * (b - a)
    _increment_metadata(output, seconds=300)
    return output


def _timestamp_displacement(case: dict) -> None:
    records = case['records']
    if len(records) < 3:
        return
    index = _middle_index(records)
    records[index]['EPOCH'] = _format_time(_parse_time(records[index]['EPOCH']) + timedelta(hours=6))


def _corrected_duplicate(case: dict) -> None:
    records = case['records']
    if not records:
        return
    index = _middle_index(records)
    correction = copy.deepcopy(records[index])
    correction['MEAN_MOTION'] = _finite_float(correction, 'MEAN_MOTION') + 5e-8
    correction['RA_OF_ASC_NODE'] = (_finite_float(correction, 'RA_OF_ASC_NODE') + 1e-5) % 360.0
    _increment_metadata(correction, seconds=120)
    records.insert(index + 1, correction)


def _unresolved_duplicate(case: dict) -> None:
    records = case['records']
    if not records:
        return
    index = _middle_index(records)
    original = records[index]
    duplicate = copy.deepcopy(original)
    duplicate['MEAN_MOTION'] = _finite_float(duplicate, 'MEAN_MOTION') + 5e-4
    duplicate['MEAN_ANOMALY'] = (_finite_float(duplicate, 'MEAN_ANOMALY') + 0.25) % 360.0
    for item in (original, duplicate):
        item.pop('CREATION_DATE', None)
        item.pop('ELEMENT_SET_NO', None)
        item.pop('GP_ID', None)
    records.insert(index + 1, duplicate)


def _replay(case: dict) -> None:
    records = case['records']
    if len(records) < 3:
        return
    indices = sorted({1, _middle_index(records), max(1, len(records) - 2)})
    records.extend(copy.deepcopy(records[index]) for index in indices)


def _insertion(case: dict) -> None:
    records = case['records']
    if len(records) < 2:
        return
    index = _middle_index(records)
    first = records[index - 1]
    second = records[index]
    injected = _interpolated_record(first, second)
    injected['MEAN_MOTION'] = _finite_float(injected, 'MEAN_MOTION') + 0.003
    injected['ECCENTRICITY'] = min(0.99, max(0.0, _finite_float(injected, 'ECCENTRICITY') + 2e-4))
    injected['MEAN_ANOMALY'] = (_finite_float(injected, 'MEAN_ANOMALY') + 0.5) % 360.0
    records.insert(index, injected)


def _deletion(case: dict) -> None:
    records = case['records']
    if len(records) <= 12:
        case['records'] = records[::2] if len(records) > 2 else records
        return
    case['records'] = [record for index, record in enumerate(records) if index % 4 != 2]


def _truncated_history(case: dict) -> None:
    records = case['records']
    case['records'] = records[-min(9, len(records)):]


def _irregular_sampling(case: dict) -> None:
    records = case['records']
    if len(records) < 10:
        case['records'] = records[::2] if len(records) > 2 else records
        return
    start = len(records) // 3
    width = max(3, len(records) // 5)
    case['records'] = records[:start] + records[min(len(records), start + width):]


def _catalogue_regime_change(case: dict) -> None:
    records = case['records']
    if not records:
        return
    index = _stable_regime_target_index(records)
    record = records[index]
    # Keep catalogue identity and revision metadata unchanged. Target an isolated authoritative
    # epoch so catalogue supersession cannot discard the manipulated row before integrity checks.
    declared = str(case.get('orbit_regime') or case.get('orbit_profile') or '').upper()
    if declared == 'LEO':
        record['MEAN_MOTION'] = 2.0
        record['ECCENTRICITY'] = min(0.2, max(0.05, _finite_float(record, 'ECCENTRICITY') + 0.05))
    else:
        record['MEAN_MOTION'] = 14.5
        record['ECCENTRICITY'] = 0.01
    record['INCLINATION'] = 55.0


def _corrupted_history(case: dict) -> None:
    records = case['records']
    if not records:
        return
    stride = max(3, len(records) // 5)
    for index in range(1, len(records), stride):
        if (index // stride) % 2 == 0:
            records[index]['EPOCH'] = 'not-a-time'
        else:
            records[index]['MEAN_MOTION'] = None


def _adversarial_false_maneuver(case: dict) -> None:
    if case.get('label_status') != 'verified-quiet':
        return
    records = case['records']
    if len(records) < 3:
        return
    index = _middle_index(records)
    record = records[index]
    record['MEAN_MOTION'] = _finite_float(record, 'MEAN_MOTION') + 0.0015
    record['ECCENTRICITY'] = min(0.99, max(0.0, _finite_float(record, 'ECCENTRICITY') + 8e-5))
    record['INCLINATION'] = min(180.0, max(0.0, _finite_float(record, 'INCLINATION') + 0.004))
    record['MEAN_ANOMALY'] = (_finite_float(record, 'MEAN_ANOMALY') + 0.18) % 360.0
    _increment_metadata(record, seconds=45)


def _adversarial_maneuver_suppression(case: dict) -> None:
    if case.get('label_status') != 'event-evidence':
        return
    records = case['records']
    if len(records) < 3:
        return
    truth = case.get('truth_events') or []
    if not truth:
        return
    epochs = []
    for index, record in enumerate(records):
        try:
            epochs.append((index, _parse_time(record['EPOCH'])))
        except Exception:
            continue
    touched: set[int] = set()
    for event in truth:
        try:
            start = _parse_time(event['start'])
            end = _parse_time(event.get('end') or event['start'])
        except Exception:
            continue
        centre = start + (end - start) / 2
        if not epochs:
            continue
        index = min(epochs, key=lambda item: abs((item[1] - centre).total_seconds()))[0]
        if index <= 0 or index >= len(records) - 1 or index in touched:
            continue
        previous = records[index - 1]
        following = records[index + 1]
        for field in ORBIT_FIELDS:
            a = _finite_float(previous, field, _finite_float(records[index], field))
            b = _finite_float(following, field, a)
            records[index][field] = 0.5 * (a + b)
        _increment_metadata(records[index], seconds=30)
        touched.add(index)


STRESSORS: tuple[tuple[str, str, str, Callable[[dict], None]], ...] = (
    ('timestamp_displacement', 'timing-integrity', 'abstain-or-contain', _timestamp_displacement),
    ('corrected_duplicate', 'catalogue-integrity', 'recover-with-audit', _corrected_duplicate),
    ('unresolved_duplicate', 'catalogue-integrity', 'abstain', _unresolved_duplicate),
    ('replay', 'replay-integrity', 'recover-with-audit', _replay),
    ('insertion', 'record-integrity', 'detect-or-abstain', _insertion),
    ('deletion', 'availability-integrity', 'degrade-selectively', _deletion),
    ('truncated_history', 'availability-integrity', 'abstain', _truncated_history),
    ('irregular_sampling', 'sampling-integrity', 'abstain-on-unsupported-segments', _irregular_sampling),
    ('catalogue_regime_change', 'regime-integrity', 'abstain', _catalogue_regime_change),
    ('corrupted_history', 'storage-history-integrity', 'abstain', _corrupted_history),
    ('adversarial_false_maneuver', 'adversarial-integrity', 'no-false-event-or-abstain', _adversarial_false_maneuver),
    ('adversarial_maneuver_suppression', 'adversarial-integrity', 'preserve-ranking-or-abstain', _adversarial_maneuver_suppression),
)


def generate_stress_benchmark(clean_benchmark: dict) -> dict:
    cases = clean_benchmark.get('cases') or []
    if not cases:
        raise ValueError('clean benchmark has no cases')
    if any(str(case.get('split')) == 'confirmatory' for case in cases):
        raise ValueError('CONFIRMATORY PARTITION IS SEALED: integrity stress generator refuses confirmatory cases')

    output_cases: list[dict] = []
    for original in cases:
        baseline = copy.deepcopy(original)
        baseline['base_case_id'] = str(original['case_id'])
        baseline['integrity_stress'] = {
            'condition': 'clean',
            'attack_class': 'baseline',
            'expected_response': 'baseline',
        }
        output_cases.append(baseline)

        for condition, attack_class, expected_response, stressor in STRESSORS:
            variant = copy.deepcopy(original)
            variant['base_case_id'] = str(original['case_id'])
            variant['case_id'] = f"{original['case_id']}__stress__{condition}"
            variant['integrity_stress'] = {
                'condition': condition,
                'attack_class': attack_class,
                'expected_response': expected_response,
            }
            stressor(variant)
            output_cases.append(variant)

    return {
        'schema': 'smd-integrity-stress-benchmark-v1',
        'benchmark_version': str(clean_benchmark.get('benchmark_version') or '1.0') + '-integrity-stress',
        'confirmatory_sealed': True,
        'source_benchmark_version': clean_benchmark.get('benchmark_version'),
        'stress_conditions': ['clean'] + [item[0] for item in STRESSORS],
        'cases': output_cases,
    }
