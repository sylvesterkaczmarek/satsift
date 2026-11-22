#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from statistics import median

from research.evaluation_version import EVALUATION_VERSION
from research.event_matching import EVENT_MATCHING_VERSION, validated_truth_events

from research.selective_v1.core import ScoredRow, SupportModel, match_events, parse_time
from research.selective_v1.models import make_candidate
from research.selective_v1.train_compare import (
    MATCH_TOLERANCE_HOURS,
    apply_support_threshold,
    case_regime,
    coverage_adjusted_quiet,
    event_case_ids,
    grouped_rows,
    load_document,
    quiet_case_ids,
    raw_score_sequence,
    rows_for_cases,
    sequences,
)
from research.sequential_v1.operational import (
    SequentialEventLayer,
    calibrate_operational_threshold,
    empirical_exceedance_bound,
)
from .core import PhysicsEstimate, PhysicsNoiseModel
from .screen import ManeuverPhysicsInverter

SEQUENTIAL_BASE_THRESHOLD = 17.822733355396952
SEQUENTIAL_PU_RANKING = 0.6427083333333333
SEQUENTIAL_DEVELOPMENT_TP = 0
SEQUENTIAL_DEVELOPMENT_FN = 36
SEQUENTIAL_DEV_SUPPORT_THRESHOLD = 15937.989955517674
SEQUENTIAL_FINAL_SUPPORT_THRESHOLD = 1.2019241655473716
TARGET_FALSE_EVENTS_PER_OBJECT_MONTH = 1.0


def physics_rows(feature_rows: list[dict], scored_rows: list[ScoredRow], inverter: ManeuverPhysicsInverter):
    if len(feature_rows) != len(scored_rows):
        raise ValueError('physics feature/scored-row lengths disagree')
    output: list[ScoredRow] = []
    estimates: list[PhysicsEstimate | None] = []
    for feature_row, scored in zip(feature_rows, scored_rows):
        if scored.status != 'scored':
            output.append(scored); estimates.append(None); continue
        estimate = inverter.estimate(feature_row)
        estimates.append(estimate)
        if estimate.status == 'abstain':
            output.append(ScoredRow(
                index=scored.index,
                epoch_utc=scored.epoch_utc,
                surprise=None,
                support_distance=scored.support_distance,
                status='abstain',
                physical_mode=None,
                reason='maneuver-physics abstention: ' + estimate.reason,
                z_scores=scored.z_scores,
            ))
        elif estimate.status == 'feasible':
            output.append(ScoredRow(
                index=scored.index,
                epoch_utc=scored.epoch_utc,
                surprise=scored.surprise,
                support_distance=scored.support_distance,
                status='scored',
                physical_mode=estimate.direction,
                z_scores=scored.z_scores,
            ))
        else:
            # A well-posed but physically inconsistent inversion is a monitored non-event update.
            output.append(ScoredRow(
                index=scored.index,
                epoch_utc=scored.epoch_utc,
                surprise=scored.surprise,
                support_distance=scored.support_distance,
                status='scored',
                physical_mode=None,
                reason=f'maneuver-physics {estimate.status}',
                z_scores=scored.z_scores,
            ))
    return output, estimates


def physics_status_summary(estimates: list[PhysicsEstimate | None]) -> dict:
    statuses = Counter(estimate.status for estimate in estimates if estimate is not None)
    feasible = [estimate for estimate in estimates if estimate is not None and estimate.feasible]
    directions = Counter(estimate.direction for estimate in feasible if estimate.direction)
    magnitudes = [estimate.delta_v_median_mps for estimate in feasible if estimate.delta_v_median_mps is not None]
    return {
        'evaluated': sum(statuses.values()),
        'status_counts': dict(sorted(statuses.items())),
        'direction_counts': dict(sorted(directions.items())),
        'median_equivalent_delta_v_mps': median(magnitudes) if magnitudes else None,
    }


def truth_interval_feasibility(cases: dict, case_id: str, scored_rows: list[ScoredRow], estimates: list[PhysicsEstimate | None]) -> dict:
    tolerance = MATCH_TOLERANCE_HOURS * 3600.0
    intervals = []
    truth_events = validated_truth_events(cases[case_id])
    for truth_index, truth in enumerate(truth_events):
        start = parse_time(str(truth['start'])) - tolerance
        end = parse_time(str(truth.get('end') or truth['start'])) + tolerance
        candidates = []
        for scored, estimate in zip(scored_rows, estimates):
            if estimate is None or not estimate.feasible:
                continue
            epoch = parse_time(scored.epoch_utc)
            if start <= epoch <= end:
                candidates.append((float(scored.surprise or 0.0), scored, estimate))
        strongest = max(candidates, key=lambda item: item[0]) if candidates else None
        intervals.append({
            'truth_index': truth_index,
            'has_feasible_physics_row': strongest is not None,
            'direction': strongest[2].direction if strongest else None,
            'delta_v_interval_mps': list(strongest[2].delta_v_interval_mps) if strongest and strongest[2].delta_v_interval_mps else None,
            'delta_v_median_mps': strongest[2].delta_v_median_mps if strongest else None,
            'row_epoch_utc': strongest[1].epoch_utc if strongest else None,
        })
    return {
        'truth_intervals': len(truth_events),
        'intervals_with_feasible_physics': sum(item['has_feasible_physics_row'] for item in intervals),
        'intervals': intervals,
    }


def development_quiet_physics_crossfit(cases, rows_by_case, sequential_quiet_cv):
    dev_quiet = quiet_case_ids(cases, 'development')
    output = []
    summaries = []
    for quiet in sequential_quiet_cv:
        heldout = quiet['case_id']
        if case_regime(cases[heldout]) != 'LEO':
            continue
        training_ids = [case_id for case_id in dev_quiet if case_id != heldout]
        training_rows = rows_for_cases(rows_by_case, training_ids)
        noise = PhysicsNoiseModel(min_reference_satellites=2).fit(training_rows)
        if 'LEO' not in noise.qualified_regimes():
            raise ValueError(f'physics cross-fit lacks two independent LEO quiet references for {heldout}')
        inverter = ManeuverPhysicsInverter(noise)
        transformed, estimates = physics_rows(rows_by_case[heldout], quiet['scored_rows'], inverter)
        adjusted = coverage_adjusted_quiet(cases[heldout], transformed)
        output.append(adjusted)
        summaries.append({'case_id': heldout, **physics_status_summary(estimates), 'coverage_fraction': adjusted['coverage_fraction']})
    if len(output) != 3:
        raise ValueError(f'expected three cross-fitted development LEO quiet cases, found {len(output)}')
    return output, summaries


def development_event_evaluation(cases, rows_by_case, dev_quiet, quiet_cv, q0, wealth_threshold):
    model = make_candidate('transformer').fit(sequences(rows_by_case, dev_quiet))
    support = SupportModel(k=5, min_reference_satellites=2).fit(rows_for_cases(rows_by_case, dev_quiet))
    noise = PhysicsNoiseModel(min_reference_satellites=3).fit(rows_for_cases(rows_by_case, dev_quiet))
    if noise.qualified_regimes() != {'LEO'}:
        raise ValueError(f'expected only LEO physics support from development quiet set, got {sorted(noise.qualified_regimes())}')
    inverter = ManeuverPhysicsInverter(noise)
    event_ids = [case_id for case_id in event_case_ids(cases, 'development') if case_regime(cases[case_id]) == 'LEO']

    quiet_wealth = []
    for quiet in quiet_cv:
        layer = SequentialEventLayer(base_score_threshold=SEQUENTIAL_BASE_THRESHOLD, q0=q0, wealth_threshold=1e100)
        steps, _ = layer.run(quiet['scored_rows'])
        quiet_wealth.extend(step.wealth for step in steps if step.wealth is not None)

    tp = fn = 0; delays = []; rankings = []; per_case = []
    truth_with_physics = 0
    for case_id in event_ids:
        raw = raw_score_sequence(model, support, rows_by_case[case_id])
        supported = apply_support_threshold(raw, SEQUENTIAL_DEV_SUPPORT_THRESHOLD)
        transformed, estimates = physics_rows(rows_by_case[case_id], supported, inverter)
        truth_physics = truth_interval_feasibility(cases, case_id, transformed, estimates)
        truth_with_physics += truth_physics['intervals_with_feasible_physics']

        ranking_layer = SequentialEventLayer(base_score_threshold=SEQUENTIAL_BASE_THRESHOLD, q0=q0, wealth_threshold=1e100)
        ranking_steps, _ = ranking_layer.run(transformed)
        tolerance = MATCH_TOLERANCE_HOURS * 3600.0
        for truth in validated_truth_events(cases[case_id]):
            start = parse_time(str(truth['start'])) - tolerance
            end = parse_time(str(truth.get('end') or truth['start'])) + tolerance
            values = [step.wealth for step in ranking_steps if step.wealth is not None and start <= parse_time(step.epoch_utc) <= end]
            if values and quiet_wealth:
                maximum = max(values)
                below = sum(value < maximum for value in quiet_wealth)
                equal = sum(value == maximum for value in quiet_wealth)
                rankings.append((below + 0.5 * equal) / len(quiet_wealth))

        layer = SequentialEventLayer(
            base_score_threshold=SEQUENTIAL_BASE_THRESHOLD,
            q0=q0,
            wealth_threshold=wealth_threshold,
        )
        _, events = layer.run(transformed)
        matched = match_events(events, validated_truth_events(cases[case_id]), MATCH_TOLERANCE_HOURS)
        tp += matched['tp']; fn += matched['fn']
        delays.extend(abs(item['delay_hours']) for item in matched['matches'])
        per_case.append({
            'case_id': case_id,
            'predicted_events': len(events),
            'tp': matched['tp'],
            'fn': matched['fn'],
            'physics': physics_status_summary(estimates),
            'truth_feasibility': truth_physics,
        })
    return {
        'tp': tp,
        'fn': fn,
        'recall': tp / (tp + fn) if tp + fn else None,
        'median_absolute_delay_hours': median(delays) if delays else None,
        'pu_sequential_wealth_mean_percentile': sum(rankings) / len(rankings) if rankings else None,
        'pu_scorable_truth_intervals': len(rankings),
        'truth_intervals_with_feasible_physics': truth_with_physics,
        'per_case': per_case,
    }


def final_aqua_calibration(cases, rows_by_case, all_quiet, q0):
    aqua = [case_id for case_id in quiet_case_ids(cases, 'calibration') if case_regime(cases[case_id]) == 'LEO']
    if len(aqua) != 1:
        raise ValueError(f'expected exactly one LEO calibration quiet case, found {aqua}')
    heldout = aqua[0]
    training = [case_id for case_id in all_quiet if case_id != heldout]
    model = make_candidate('transformer').fit(sequences(rows_by_case, training))
    support = SupportModel(k=5, min_reference_satellites=1).fit(rows_for_cases(rows_by_case, training))
    raw = raw_score_sequence(model, support, rows_by_case[heldout], require_qualified_regime=False)
    supported = apply_support_threshold(raw, SEQUENTIAL_FINAL_SUPPORT_THRESHOLD)
    noise = PhysicsNoiseModel(min_reference_satellites=3).fit(rows_for_cases(rows_by_case, training))
    if 'LEO' not in noise.qualified_regimes():
        raise ValueError('final physics calibration lacks three independent LEO quiet references')
    transformed, estimates = physics_rows(rows_by_case[heldout], supported, ManeuverPhysicsInverter(noise))
    adjusted = coverage_adjusted_quiet(cases[heldout], transformed)
    calibration = calibrate_operational_threshold(
        [adjusted],
        base_score_threshold=SEQUENTIAL_BASE_THRESHOLD,
        q0=q0,
        target_false_events_per_object_month=TARGET_FALSE_EVENTS_PER_OBJECT_MONTH,
    )
    return heldout, adjusted, estimates, calibration


def post_calibration_development(cases, rows_by_case, all_quiet, q0, wealth_threshold):
    model = make_candidate('transformer').fit(sequences(rows_by_case, all_quiet))
    support = SupportModel(k=5, min_reference_satellites=3).fit(rows_for_cases(rows_by_case, all_quiet))
    noise = PhysicsNoiseModel(min_reference_satellites=3).fit(rows_for_cases(rows_by_case, all_quiet))
    inverter = ManeuverPhysicsInverter(noise)
    event_ids = [case_id for case_id in event_case_ids(cases, 'development') if case_regime(cases[case_id]) == 'LEO']
    tp = fn = 0; delays = []; per_case = []
    for case_id in event_ids:
        raw = raw_score_sequence(model, support, rows_by_case[case_id])
        supported = apply_support_threshold(raw, SEQUENTIAL_FINAL_SUPPORT_THRESHOLD)
        transformed, estimates = physics_rows(rows_by_case[case_id], supported, inverter)
        layer = SequentialEventLayer(
            base_score_threshold=SEQUENTIAL_BASE_THRESHOLD,
            q0=q0,
            wealth_threshold=wealth_threshold,
        )
        _, events = layer.run(transformed)
        matched = match_events(events, validated_truth_events(cases[case_id]), MATCH_TOLERANCE_HOURS)
        tp += matched['tp']; fn += matched['fn']
        delays.extend(abs(item['delay_hours']) for item in matched['matches'])
        per_case.append({'case_id': case_id, 'predicted_events': len(events), 'tp': matched['tp'], 'fn': matched['fn'], 'physics': physics_status_summary(estimates)})
    return {'tp': tp, 'fn': fn, 'recall': tp / (tp + fn) if tp + fn else None, 'median_absolute_delay_hours': median(delays) if delays else None, 'per_case': per_case}


def main() -> None:
    parser = argparse.ArgumentParser(description='Evaluate maneuver-physics feasibility layer without touching confirmatory data.')
    parser.add_argument('--features', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('benchmark-results/physics-v1-development-case-statistics-v3.json'))
    args = parser.parse_args()
    document = load_document(args.features)
    if document.get('confirmatory_sealed') is not True:
        raise ValueError('CONFIRMATORY PARTITION IS SEALED')
    cases, rows_by_case = grouped_rows(document)
    if any(case.get('split') == 'confirmatory' for case in cases.values()):
        raise ValueError('CONFIRMATORY PARTITION IS SEALED: physics experiment refuses confirmatory metadata')

    dev_quiet = quiet_case_ids(cases, 'development')
    cal_quiet = quiet_case_ids(cases, 'calibration')
    if len(dev_quiet) != 4 or len(cal_quiet) != 4:
        raise ValueError('Physics evaluation requires all four development and four calibration quiet cases')

    # Recreate Sequential evaluation's development quiet cross-fit scores, but replace its simple physics gate.
    from research.sequential_v1.run_development import development_quiet_crossfit
    _, _, support_dev, sequential_quiet_cv = development_quiet_crossfit(cases, rows_by_case)
    if abs(support_dev - SEQUENTIAL_DEV_SUPPORT_THRESHOLD) > 1e-6 * max(1.0, abs(SEQUENTIAL_DEV_SUPPORT_THRESHOLD)):
        raise ValueError('Sequential evaluation development support threshold changed unexpectedly')
    quiet_cv, quiet_physics_summaries = development_quiet_physics_crossfit(cases, rows_by_case, sequential_quiet_cv)

    q0_record = empirical_exceedance_bound(quiet_cv, base_score_threshold=SEQUENTIAL_BASE_THRESHOLD)
    q0 = q0_record['q0']
    provisional = calibrate_operational_threshold(
        quiet_cv,
        base_score_threshold=SEQUENTIAL_BASE_THRESHOLD,
        q0=q0,
        target_false_events_per_object_month=TARGET_FALSE_EVENTS_PER_OBJECT_MONTH,
    )
    development = development_event_evaluation(
        cases, rows_by_case, dev_quiet, quiet_cv, q0, provisional['selected_wealth_threshold']
    )

    all_quiet = dev_quiet + cal_quiet
    heldout, aqua_case, aqua_estimates, final_calibration = final_aqua_calibration(cases, rows_by_case, all_quiet, q0)
    diagnostic = post_calibration_development(
        cases, rows_by_case, all_quiet, q0, final_calibration['selected_wealth_threshold']
    )

    output = {
        'schema': 'smd-maneuver-physics-v1-development-calibration',
        'evaluation_version': EVALUATION_VERSION,
        'scoring_version': EVENT_MATCHING_VERSION,
        'method': 'selective-ml-v1.0 + sequential-evidence-v1.0 + maneuver-physics-v1.0',
        'confirmatory_partition_accessed': False,
        'detector_v0_4_modified': False,
        'selected_backbone': 'transformer',
        'physics_formulation': 'unknown-burn-phase equivalent RTN impulse inversion in prograde nonsingular equinoctial elements with independent HCW common-epoch RTN corroboration for near-circular orbits',
        'delta_v_interpretation': 'uncertainty-bounded equivalent impulse interval; not an executed finite-burn reconstruction',
        'sequential_frozen_base_score_threshold': SEQUENTIAL_BASE_THRESHOLD,
        'sequential_reference': {
            'pu_sequential_wealth_mean_percentile': SEQUENTIAL_PU_RANKING,
            'development_tp': SEQUENTIAL_DEVELOPMENT_TP,
            'development_fn': SEQUENTIAL_DEVELOPMENT_FN,
        },
        'development_quiet_physics_crossfit': quiet_physics_summaries,
        'empirical_q0_after_physics_gate': q0_record,
        'provisional_development_event_calibration': provisional,
        'development_evaluation': development,
        'calibration_quiet_case': heldout,
        'calibration_quiet_physics': {**physics_status_summary(aqua_estimates), 'coverage_fraction': aqua_case['coverage_fraction']},
        'final_event_calibration': final_calibration,
        'post_calibration_development_diagnostic': diagnostic,
        'qualified_regimes': ['LEO'],
        'unqualified_regimes': ['GEO', 'HEO', 'MEO'],
        'integration_gate': {
            'passed': bool(
                diagnostic['tp'] > SEQUENTIAL_DEVELOPMENT_TP
                and diagnostic['recall'] is not None
                and diagnostic['recall'] >= 0.10
                and final_calibration.get('false_events_per_object_month') is not None
                and final_calibration['false_events_per_object_month'] <= TARGET_FALSE_EVENTS_PER_OBJECT_MONTH
            ),
            'rule': 'requires at least one recovered Sequential evaluation-missed event and >=0.10 post-calibration development recall without exceeding the frozen <=1 false-event/covered-object-month calibration target',
        },
        'confirmatory_rule': 'Do not materialise, inspect, score, or tune against the confirmatory partition.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
