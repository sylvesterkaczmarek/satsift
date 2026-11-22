#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from research.evaluation_version import EVALUATION_VERSION
from research.event_matching import EVENT_MATCHING_VERSION, parse_truth_events_us, validated_truth_events

from .core import (
    ScoredRow,
    SupportModel,
    calibrate_support_threshold,
    context_regime,
    group_candidate_events,
    match_events,
    parse_time,
    physical_support,
)
from .models import make_candidate

CANDIDATES = ('robust-linear', 'gru', 'tcn', 'transformer')
RISK_BUDGET = 1.0  # empirical false events / covered verified-quiet object-month
SUPPORT_COVERAGE = 0.98
PHYSICS_Z_GATE = 2.0
MAX_EVENT_GAP_POINTS = 2
MATCH_TOLERANCE_HOURS = 24.0


def load_document(path: Path) -> dict:
    document = json.loads(path.read_text())
    if document.get('confirmatory_sealed') is not True:
        raise ValueError('selective-v1 feature artifact must explicitly seal confirmatory data')
    splits = {str(case.get('split')) for case in document.get('cases', [])}
    if 'confirmatory' in splits:
        raise ValueError('CONFIRMATORY PARTITION IS SEALED: training input contains confirmatory metadata')
    if not splits.issubset({'development', 'calibration'}):
        raise ValueError(f'unexpected training split(s): {sorted(splits)}')
    for case in document.get('cases', []):
        validated_truth_events(case)
    return document


def grouped_rows(document: dict) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    cases = {str(case['case_id']): case for case in document.get('cases', [])}
    rows: dict[str, list[dict]] = defaultdict(list)
    for row in document.get('rows', []):
        case_id = str(row['case_id'])
        if case_id not in cases:
            raise ValueError(f'feature row references unknown case {case_id}')
        if str(row.get('split')) == 'confirmatory':
            raise ValueError('CONFIRMATORY PARTITION IS SEALED: feature row is confirmatory')
        rows[case_id].append(row)
    for case in cases.values():
        validated_truth_events(case)
    for values in rows.values():
        values.sort(key=lambda item: (str(item.get('epoch_utc', '')), int(item.get('index', 0))))
    return cases, rows


def case_regime(case: dict) -> str:
    regime = str(case.get('orbit_regime') or case.get('orbit_profile') or '').upper()
    return 'GEO' if regime == 'IGSO' else regime


def quiet_case_ids(cases: dict[str, dict], split: str | None = None) -> list[str]:
    return sorted(
        case_id for case_id, case in cases.items()
        if case.get('label_status') == 'verified-quiet'
        and (split is None or case.get('split') == split)
    )


def event_case_ids(cases: dict[str, dict], split: str | None = None) -> list[str]:
    return sorted(
        case_id for case_id, case in cases.items()
        if case.get('label_status') == 'event-evidence'
        and (split is None or case.get('split') == split)
    )


def sequences(rows_by_case: dict[str, list[dict]], case_ids: list[str]) -> list[list[dict]]:
    output = [rows_by_case[case_id] for case_id in case_ids if rows_by_case.get(case_id)]
    if not output:
        raise ValueError('no feature sequences for requested cases')
    return output


def rows_for_cases(rows_by_case: dict[str, list[dict]], case_ids: list[str]) -> list[dict]:
    return [row for case_id in case_ids for row in rows_by_case.get(case_id, [])]


def raw_score_sequence(model, support: SupportModel, rows: list[dict], *, require_qualified_regime: bool = True) -> list[ScoredRow]:
    predictions = model.predict_sequence(rows)
    if len(predictions) != len(rows):
        raise RuntimeError('model returned wrong prediction length')
    scored: list[ScoredRow] = []
    for row, prediction in zip(rows, predictions):
        index = int(row.get('index', len(scored)))
        epoch = str(row.get('epoch_utc', ''))
        if row.get('quality_ok') is False:
            scored.append(ScoredRow(index, epoch, None, None, 'abstain', reason='catalogue/data-quality gate failed'))
            continue
        distance = support.distance(row, require_qualified_regime=require_qualified_regime)
        if distance is None:
            scored.append(ScoredRow(index, epoch, None, None, 'abstain', reason='insufficient independent calibration support'))
            continue
        if prediction is None or not math.isfinite(float(prediction.surprise)):
            scored.append(ScoredRow(index, epoch, None, distance, 'abstain', reason='conditional distribution unavailable'))
            continue
        scored.append(ScoredRow(
            index=index,
            epoch_utc=epoch,
            surprise=prediction.surprise,
            support_distance=distance,
            status='scored',
            physical_mode=physical_support(prediction.z_scores, z_gate=PHYSICS_Z_GATE),
            z_scores=prediction.z_scores,
        ))
    return scored


def apply_support_threshold(scored: list[ScoredRow], threshold: float) -> list[ScoredRow]:
    output: list[ScoredRow] = []
    for row in scored:
        if row.status == 'scored' and row.support_distance is not None and row.support_distance > threshold:
            output.append(ScoredRow(
                index=row.index,
                epoch_utc=row.epoch_utc,
                surprise=None,
                support_distance=row.support_distance,
                status='abstain',
                reason='outside calibrated support',
            ))
        else:
            output.append(row)
    return output


def coverage_adjusted_quiet(case: dict, scored_rows: list[ScoredRow]) -> dict:
    total = len(scored_rows)
    covered = sum(row.status == 'scored' for row in scored_rows)
    fraction = covered / total if total else 0.0
    return {
        'case_id': case['case_id'],
        'span_days_raw': float(case.get('span_days') or 0.0),
        # Abstained time cannot count in a selective false-event denominator.
        'span_days': float(case.get('span_days') or 0.0) * fraction,
        'coverage_fraction': fraction,
        'scored_rows': scored_rows,
    }


def finite_event_calibration(quiet_cases: list[dict], *, budget: float = RISK_BUDGET) -> dict:
    """Empirical event threshold with a finite sentinel for the zero-event operating point."""
    object_months = sum(float(case.get('span_days') or 0.0) for case in quiet_cases) / 30.4375
    if object_months <= 0.0:
        raise ValueError('covered verified-quiet exposure is required')
    scores = sorted({
        float(row.surprise)
        for case in quiet_cases
        for row in case.get('scored_rows', [])
        if row.status == 'scored' and row.surprise is not None and math.isfinite(float(row.surprise))
    })
    if not scores:
        raise ValueError('no finite covered verified-quiet scores')
    maximum = max(scores)
    no_event_threshold = maximum + max(1e-6, abs(maximum) * 1e-6)
    candidates = [no_event_threshold] + list(reversed(scores))
    feasible = []
    for threshold in candidates:
        false_events = sum(
            len(group_candidate_events(
                case.get('scored_rows', []), threshold=threshold,
                max_gap_points=MAX_EVENT_GAP_POINTS,
                require_physical_support=True,
            ))
            for case in quiet_cases
        )
        rate = false_events / object_months
        if rate <= budget:
            feasible.append((threshold, false_events, rate))
    if not feasible:
        raise RuntimeError('finite no-event threshold unexpectedly failed the empirical risk budget')
    threshold, false_events, rate = min(feasible, key=lambda item: item[0])
    return {
        'selected_threshold': float(threshold),
        'false_events': int(false_events),
        'covered_verified_quiet_object_months': object_months,
        'false_events_per_object_month': rate,
        'budget': budget,
        'candidate_count': len(candidates),
    }


def quiet_score_pool(quiet_cases: list[dict]) -> list[float]:
    return [
        float(row.surprise)
        for case in quiet_cases
        for row in case.get('scored_rows', [])
        if row.status == 'scored' and row.surprise is not None and math.isfinite(float(row.surprise))
    ]


def truth_interval_ranking(scored_rows: list[ScoredRow], truth_events: list[dict], quiet_scores: list[float]) -> list[float]:
    """PU-safe ranking: documented event maxima against verified-quiet scores only.

    Unlabelled rows outside the truth intervals are never used as negatives. The 24-hour margin is
    the frozen benchmark event-matching tolerance, not a newly inferred negative/positive label.
    """
    parse_truth_events_us(truth_events)
    if not quiet_scores:
        return []
    tolerance = MATCH_TOLERANCE_HOURS * 3600.0
    rankings = []
    for event in truth_events:
        start = parse_time(str(event['start'])) - tolerance
        end = parse_time(str(event.get('end') or event['start'])) + tolerance
        values = [
            float(row.surprise)
            for row in scored_rows
            if row.status == 'scored' and row.surprise is not None
            and start <= parse_time(row.epoch_utc) <= end
        ]
        if not values:
            continue
        maximum = max(values)
        below = sum(value < maximum for value in quiet_scores)
        equal = sum(value == maximum for value in quiet_scores)
        rankings.append((below + 0.5 * equal) / len(quiet_scores))
    return rankings


def development_selection_for_candidate(name: str, cases: dict[str, dict], rows_by_case: dict[str, list[dict]]) -> dict:
    dev_quiet = quiet_case_ids(cases, 'development')
    if len(dev_quiet) < 3:
        raise ValueError('development split needs at least three quiet satellites for model selection')
    quiet_regime_counts = Counter(case_regime(cases[case_id]) for case_id in dev_quiet)
    # At least three quiet satellites are required so each leave-one-satellite-out fold retains two
    # same-regime references. Benchmark v1.0 therefore qualifies LEO for architecture selection.
    eligible_regimes = sorted(regime for regime, count in quiet_regime_counts.items() if count >= 3)
    if not eligible_regimes:
        raise ValueError('no development orbit regime has enough independent quiet satellites for selection')

    cv_raw: dict[str, list[ScoredRow]] = {}
    distances: dict[str, list[float]] = defaultdict(list)
    fold_parameters: list[int] = []
    for heldout in dev_quiet:
        regime = case_regime(cases[heldout])
        if regime not in eligible_regimes:
            continue
        training = [case_id for case_id in dev_quiet if case_id != heldout]
        model = make_candidate(name).fit(sequences(rows_by_case, training))
        fold_parameters.append(int(getattr(model, 'parameter_count', 0)))
        support = SupportModel(k=5, min_reference_satellites=2).fit(rows_for_cases(rows_by_case, training))
        scored = raw_score_sequence(model, support, rows_by_case[heldout])
        cv_raw[heldout] = scored
        for row in scored:
            if row.status == 'scored' and row.support_distance is not None:
                distances[regime].append(row.support_distance)

    support_thresholds = {
        regime: calibrate_support_threshold(values, coverage=SUPPORT_COVERAGE)
        for regime, values in distances.items() if values
    }
    quiet_cv_cases = []
    for case_id, raw_scored in cv_raw.items():
        regime = case_regime(cases[case_id])
        threshold = support_thresholds.get(regime)
        if threshold is None:
            continue
        quiet_cv_cases.append(coverage_adjusted_quiet(cases[case_id], apply_support_threshold(raw_scored, threshold)))
    calibration = finite_event_calibration(quiet_cv_cases)
    quiet_scores = quiet_score_pool(quiet_cv_cases)

    final_model = make_candidate(name).fit(sequences(rows_by_case, dev_quiet))
    final_support = SupportModel(k=5, min_reference_satellites=2).fit(rows_for_cases(rows_by_case, dev_quiet))
    event_ids = [
        case_id for case_id in event_case_ids(cases, 'development')
        if case_regime(cases[case_id]) in eligible_regimes
    ]
    tp = fn = 0
    delays: list[float] = []
    rankings: list[float] = []
    scored_count = total_count = 0
    per_case = []
    for case_id in event_ids:
        regime = case_regime(cases[case_id])
        raw = raw_score_sequence(final_model, final_support, rows_by_case[case_id])
        scored_rows = apply_support_threshold(raw, support_thresholds[regime])
        scored_count += sum(row.status == 'scored' for row in scored_rows)
        total_count += len(scored_rows)
        rankings.extend(truth_interval_ranking(scored_rows, validated_truth_events(cases[case_id]), quiet_scores))
        events = group_candidate_events(
            scored_rows,
            threshold=float(calibration['selected_threshold']),
            max_gap_points=MAX_EVENT_GAP_POINTS,
            require_physical_support=True,
        )
        matched = match_events(events, validated_truth_events(cases[case_id]), MATCH_TOLERANCE_HOURS)
        tp += matched['tp']; fn += matched['fn']
        delays.extend(abs(item['delay_hours']) for item in matched['matches'])
        per_case.append({
            'case_id': case_id,
            'regime': regime,
            'truth_intervals': len(validated_truth_events(cases[case_id])),
            'predicted_events': len(events),
            'tp': matched['tp'],
            'fn': matched['fn'],
            'coverage_fraction': (sum(row.status == 'scored' for row in scored_rows) / len(scored_rows)) if scored_rows else 0.0,
        })
    recall = tp / (tp + fn) if tp + fn else None
    abstention = 1.0 - (scored_count / total_count) if total_count else 1.0
    quiet_coverage = (
        sum(case['coverage_fraction'] * max(1, len(case['scored_rows'])) for case in quiet_cv_cases)
        / sum(max(1, len(case['scored_rows'])) for case in quiet_cv_cases)
    ) if quiet_cv_cases else 0.0
    parameter_count = int(getattr(final_model, 'parameter_count', max(fold_parameters or [0])))
    unsupported_events = [
        {'case_id': case_id, 'regime': case_regime(cases[case_id]), 'truth_intervals': len(validated_truth_events(cases[case_id]))}
        for case_id in event_case_ids(cases, 'development')
        if case_regime(cases[case_id]) not in eligible_regimes
    ]
    return {
        'candidate': name,
        'architecture_selection_split': 'development only',
        'eligible_regimes': eligible_regimes,
        'development_quiet_satellites': len(dev_quiet),
        'support_thresholds': support_thresholds,
        'provisional_event_calibration': calibration,
        'pu_event_vs_quiet_mean_percentile': (sum(rankings) / len(rankings)) if rankings else None,
        'pu_scorable_truth_intervals': len(rankings),
        'event_recall_supported_regimes': recall,
        'true_positives': tp,
        'false_negatives': fn,
        'median_absolute_detection_delay_hours': median(delays) if delays else None,
        'event_row_abstention_rate': abstention,
        'quiet_cv_coverage_fraction': quiet_coverage,
        'parameter_count': parameter_count,
        'per_case': per_case,
        'unsupported_development_event_cases': unsupported_events,
    }


def selection_key(result: dict):
    ranking = result.get('pu_event_vs_quiet_mean_percentile')
    recall = result.get('event_recall_supported_regimes')
    delay = result.get('median_absolute_detection_delay_hours')
    return (
        -(float(ranking) if ranking is not None else -1.0),
        -(float(recall) if recall is not None else -1.0),
        float(result.get('event_row_abstention_rate') or 0.0),
        float(delay) if delay is not None else float('inf'),
        int(result.get('parameter_count') or 0),
        str(result['candidate']),
    )


def final_calibration(selected: str, cases: dict[str, dict], rows_by_case: dict[str, list[dict]]) -> dict:
    dev_quiet = quiet_case_ids(cases, 'development')
    cal_quiet = quiet_case_ids(cases, 'calibration')
    if len(cal_quiet) != 4:
        raise ValueError(f'expected all four frozen calibration quiet controls, found {len(cal_quiet)}')
    all_quiet = dev_quiet + cal_quiet

    # Cross-fit each calibration quiet satellite. Model selection is already frozen at this point.
    # A single same-regime reference is enough to measure held-out support distance here; the final
    # detector requires >=3 reference satellites before a regime becomes eligible.
    calibration_raw: dict[str, list[ScoredRow]] = {}
    support_distances: dict[str, list[float]] = defaultdict(list)
    for heldout in cal_quiet:
        training = [case_id for case_id in all_quiet if case_id != heldout]
        model = make_candidate(selected).fit(sequences(rows_by_case, training))
        support = SupportModel(k=5, min_reference_satellites=1).fit(rows_for_cases(rows_by_case, training))
        scored = raw_score_sequence(model, support, rows_by_case[heldout], require_qualified_regime=False)
        calibration_raw[heldout] = scored
        regime = case_regime(cases[heldout])
        for row in scored:
            if row.status == 'scored' and row.support_distance is not None:
                support_distances[regime].append(row.support_distance)

    final_reference_counts = Counter(case_regime(cases[case_id]) for case_id in all_quiet)
    qualified_regimes = sorted(regime for regime, count in final_reference_counts.items() if count >= 3)
    support_thresholds = {
        regime: calibrate_support_threshold(support_distances[regime], coverage=SUPPORT_COVERAGE)
        for regime in qualified_regimes if support_distances.get(regime)
    }
    calibrated_quiet = []
    per_case = []
    for case_id in cal_quiet:
        regime = case_regime(cases[case_id])
        raw = calibration_raw[case_id]
        if regime in support_thresholds:
            scored = apply_support_threshold(raw, support_thresholds[regime])
        else:
            scored = [
                row if row.status == 'abstain' else ScoredRow(
                    row.index, row.epoch_utc, None, row.support_distance, 'abstain',
                    reason='regime lacks three independent quiet reference satellites'
                )
                for row in raw
            ]
        adjusted = coverage_adjusted_quiet(cases[case_id], scored)
        per_case.append({
            'case_id': case_id,
            'regime': regime,
            'coverage_fraction': adjusted['coverage_fraction'],
            'covered_span_days': adjusted['span_days'],
            'raw_span_days': adjusted['span_days_raw'],
        })
        if adjusted['span_days'] > 0.0:
            calibrated_quiet.append(adjusted)
    event_calibration = finite_event_calibration(calibrated_quiet)

    final_model = make_candidate(selected).fit(sequences(rows_by_case, all_quiet))
    final_support = SupportModel(k=5, min_reference_satellites=3).fit(rows_for_cases(rows_by_case, all_quiet))
    missing = sorted(final_support.qualified_regimes() - set(support_thresholds))
    if missing:
        raise ValueError(f'missing cross-satellite support calibration for final regime(s): {missing}')

    return {
        'selected_backbone': selected,
        'minimum_reference_satellites_final': 3,
        'nominal_training_cases_final': all_quiet,
        'calibration_quiet_cases': cal_quiet,
        'reference_satellites_by_regime': dict(sorted(final_reference_counts.items())),
        'qualified_regimes': sorted(final_support.qualified_regimes()),
        'unqualified_regimes': sorted({'LEO', 'MEO', 'GEO', 'HEO'} - final_support.qualified_regimes()),
        'support_thresholds': dict(sorted(support_thresholds.items())),
        'support_coverage_target': SUPPORT_COVERAGE,
        'event_calibration': event_calibration,
        'calibration_quiet_coverage': per_case,
        'final_parameter_count': int(getattr(final_model, 'parameter_count', 0)),
        'physics_z_gate': PHYSICS_Z_GATE,
        'max_event_gap_points': MAX_EVENT_GAP_POINTS,
        'risk_statement': 'empirical false-event calibration on covered verified-quiet object-months; no formal risk-control guarantee',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Select and calibrate the sealed selective ML v1.0 research detector.')
    parser.add_argument('--features', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('benchmark-results/selective-v1-model-selection-case-statistics-v3.json'))
    args = parser.parse_args()
    document = load_document(args.features)
    cases, rows_by_case = grouped_rows(document)

    dev_cases = [case for case in cases.values() if case.get('split') == 'development']
    if len(dev_cases) != 14:
        raise ValueError(f'expected all 14 frozen development satellites, found {len(dev_cases)}')
    if len(quiet_case_ids(cases, 'calibration')) != 4:
        raise ValueError('all four calibration verified-quiet controls are required')

    comparisons = []
    failures = []
    for candidate in CANDIDATES:
        print(f'Comparing {candidate}...')
        try:
            result = development_selection_for_candidate(candidate, cases, rows_by_case)
            comparisons.append(result)
            print(json.dumps({k: result[k] for k in ('candidate','eligible_regimes','pu_event_vs_quiet_mean_percentile','event_recall_supported_regimes','event_row_abstention_rate','parameter_count')}, indent=2))
        except Exception as exc:
            failures.append({'candidate': candidate, 'error': f'{type(exc).__name__}: {exc}'})
            print(f'  candidate failed: {exc}')
    if len(comparisons) != len(CANDIDATES):
        raise SystemExit(f'Not all required model candidates completed successfully: {failures}')
    comparisons.sort(key=selection_key)
    selected = comparisons[0]['candidate']
    print(f'Selected backbone: {selected}')
    calibration = final_calibration(selected, cases, rows_by_case)

    output = {
        'schema': 'smd-selective-ml-v1-model-selection',
        'evaluation_version': EVALUATION_VERSION,
        'scoring_version': EVENT_MATCHING_VERSION,
        'method': 'selective-ml-v1.0',
        'confirmatory_partition_accessed': False,
        'detector_v0_4_modified': False,
        'architecture_is_novelty_claim': False,
        'selection_rule': [
            'development-only PU event-vs-verified-quiet ranking percentile descending',
            'development-only supported-regime event recall descending',
            'event row abstention ascending',
            'median absolute detection delay ascending',
            'parameter count ascending',
        ],
        'candidate_comparisons': comparisons,
        'candidate_failures': failures,
        'selected_backbone': selected,
        'final_calibration': calibration,
        'calibration_event_evaluation': {
            'status': 'not used for model selection or risk calibration',
            'reason': 'seven calibration event histories remained rate-limited at the design run; omitting them avoids availability-biased architecture selection',
        },
        'confirmatory_rule': 'Do not materialise, score, tune on, or inspect confirmatory histories until the final frozen confirmatory task.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(output, indent=2, allow_nan=False) + '\n'
    args.output.write_text(encoded)
    print(encoded)


if __name__ == '__main__':
    main()
