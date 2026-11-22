#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

from research.evaluation_version import EVALUATION_VERSION
from research.event_matching import EVENT_MATCHING_VERSION, parse_truth_events_us, validated_truth_events

from research.selective_v1.core import SupportModel, calibrate_support_threshold, parse_time, quantile, match_events
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
from .operational import SequentialEventLayer, calibrate_operational_threshold, empirical_exceedance_bound

TARGET_FALSE_EVENTS_PER_OBJECT_MONTH = 1.0
BASE_QUANTILES = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95)


def development_quiet_crossfit(cases, rows_by_case):
    dev_quiet=quiet_case_ids(cases,'development')
    leo=[case_id for case_id in dev_quiet if case_regime(cases[case_id])=='LEO']
    if len(leo)<3:
        raise ValueError('sequential v1 requires at least three development LEO quiet satellites')
    raw={}; distances=[]
    for heldout in leo:
        training=[case_id for case_id in dev_quiet if case_id!=heldout]
        model=make_candidate('transformer').fit(sequences(rows_by_case,training))
        support=SupportModel(k=5,min_reference_satellites=2).fit(rows_for_cases(rows_by_case,training))
        scored=raw_score_sequence(model,support,rows_by_case[heldout])
        raw[heldout]=scored
        distances.extend(row.support_distance for row in scored if row.status=='scored' and row.support_distance is not None)
    threshold=calibrate_support_threshold(distances,coverage=.98)
    quiet=[]
    for case_id,scored in raw.items():
        quiet.append(coverage_adjusted_quiet(cases[case_id],apply_support_threshold(scored,threshold)))
    return dev_quiet, leo, threshold, quiet


def sequential_truth_ranking(steps, truth_events, quiet_wealth):
    parse_truth_events_us(truth_events)
    if not quiet_wealth:
        return []
    tolerance=MATCH_TOLERANCE_HOURS*3600.0
    result=[]
    for truth in truth_events:
        start=parse_time(str(truth['start']))-tolerance
        end=parse_time(str(truth.get('end') or truth['start']))+tolerance
        values=[step.wealth for step in steps if step.wealth is not None and start<=parse_time(step.epoch_utc)<=end]
        if not values:
            continue
        maximum=max(values)
        below=sum(value<maximum for value in quiet_wealth)
        equal=sum(value==maximum for value in quiet_wealth)
        result.append((below+.5*equal)/len(quiet_wealth))
    return result


def evaluate_base(base_threshold, cases, rows_by_case, dev_quiet, support_threshold, quiet_cv):
    q0_record=empirical_exceedance_bound(quiet_cv,base_score_threshold=base_threshold)
    q0=q0_record['q0']
    provisional=calibrate_operational_threshold(
        quiet_cv,base_score_threshold=base_threshold,q0=q0,
        target_false_events_per_object_month=TARGET_FALSE_EVENTS_PER_OBJECT_MONTH,
    )
    wealth_threshold=provisional['selected_wealth_threshold']

    model=make_candidate('transformer').fit(sequences(rows_by_case,dev_quiet))
    support=SupportModel(k=5,min_reference_satellites=2).fit(rows_for_cases(rows_by_case,dev_quiet))
    event_ids=[case_id for case_id in event_case_ids(cases,'development') if case_regime(cases[case_id])=='LEO']

    quiet_wealth=[]
    for case in quiet_cv:
        layer=SequentialEventLayer(base_score_threshold=base_threshold,q0=q0,wealth_threshold=1e100)
        steps,_=layer.run(case['scored_rows'])
        quiet_wealth.extend(step.wealth for step in steps if step.wealth is not None)

    tp=fn=0; delays=[]; rankings=[]; per_case=[]
    for case_id in event_ids:
        raw=raw_score_sequence(model,support,rows_by_case[case_id])
        scored=apply_support_threshold(raw,support_threshold)
        ranking_layer=SequentialEventLayer(base_score_threshold=base_threshold,q0=q0,wealth_threshold=1e100)
        ranking_steps,_=ranking_layer.run(scored)
        rankings.extend(sequential_truth_ranking(ranking_steps,validated_truth_events(cases[case_id]),quiet_wealth))

        layer=SequentialEventLayer(base_score_threshold=base_threshold,q0=q0,wealth_threshold=wealth_threshold)
        _,events=layer.run(scored)
        matched=match_events(events,validated_truth_events(cases[case_id]),MATCH_TOLERANCE_HOURS)
        tp+=matched['tp']; fn+=matched['fn']
        delays.extend(abs(item['delay_hours']) for item in matched['matches'])
        per_case.append({'case_id':case_id,'truth_intervals':len(validated_truth_events(cases[case_id])),'predicted_events':len(events),'tp':matched['tp'],'fn':matched['fn']})
    return {
        'base_score_threshold':base_threshold,
        'q0_empirical':q0,
        'q0_record':q0_record,
        'provisional_event_calibration':provisional,
        'development_recall':tp/(tp+fn) if tp+fn else None,
        'tp':tp,'fn':fn,
        'median_absolute_delay_hours':median(delays) if delays else None,
        'pu_sequential_wealth_mean_percentile':sum(rankings)/len(rankings) if rankings else None,
        'pu_scorable_truth_intervals':len(rankings),
        'per_case':per_case,
    }


def selection_key(item):
    recall=item.get('development_recall')
    ranking=item.get('pu_sequential_wealth_mean_percentile')
    delay=item.get('median_absolute_delay_hours')
    return (
        -(float(recall) if recall is not None else -1.0),
        -(float(ranking) if ranking is not None else -1.0),
        float(delay) if delay is not None else float('inf'),
        float(item['base_score_threshold']),
    )


def calibration_quiet_crossfit(cases, rows_by_case, all_quiet):
    cal_quiet=quiet_case_ids(cases,'calibration')
    aqua=[case_id for case_id in cal_quiet if case_regime(cases[case_id])=='LEO']
    if len(aqua)!=1:
        raise ValueError(f'expected exactly one LEO calibration quiet case, found {aqua}')
    heldout=aqua[0]
    training=[case_id for case_id in all_quiet if case_id!=heldout]
    model=make_candidate('transformer').fit(sequences(rows_by_case,training))
    support=SupportModel(k=5,min_reference_satellites=1).fit(rows_for_cases(rows_by_case,training))
    raw=raw_score_sequence(model,support,rows_by_case[heldout],require_qualified_regime=False)
    distances=[row.support_distance for row in raw if row.status=='scored' and row.support_distance is not None]
    threshold=calibrate_support_threshold(distances,coverage=.98)
    adjusted=coverage_adjusted_quiet(cases[heldout],apply_support_threshold(raw,threshold))
    return heldout,threshold,adjusted


def final_development_diagnostic(cases,rows_by_case,all_quiet,support_threshold,base_threshold,q0,wealth_threshold):
    model=make_candidate('transformer').fit(sequences(rows_by_case,all_quiet))
    support=SupportModel(k=5,min_reference_satellites=3).fit(rows_for_cases(rows_by_case,all_quiet))
    event_ids=[case_id for case_id in event_case_ids(cases,'development') if case_regime(cases[case_id])=='LEO']
    tp=fn=0; delays=[]; per_case=[]
    for case_id in event_ids:
        raw=raw_score_sequence(model,support,rows_by_case[case_id])
        scored=apply_support_threshold(raw,support_threshold)
        layer=SequentialEventLayer(base_score_threshold=base_threshold,q0=q0,wealth_threshold=wealth_threshold)
        _,events=layer.run(scored)
        matched=match_events(events,validated_truth_events(cases[case_id]),MATCH_TOLERANCE_HOURS)
        tp+=matched['tp']; fn+=matched['fn']
        delays.extend(abs(item['delay_hours']) for item in matched['matches'])
        per_case.append({'case_id':case_id,'predicted_events':len(events),'tp':matched['tp'],'fn':matched['fn']})
    return {'tp':tp,'fn':fn,'recall':tp/(tp+fn) if tp+fn else None,'median_absolute_delay_hours':median(delays) if delays else None,'per_case':per_case}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--features',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('benchmark-results/sequential-v1-development-case-statistics-v3.json'))
    args=parser.parse_args()
    document=load_document(args.features)
    if document.get('confirmatory_sealed') is not True:
        raise ValueError('CONFIRMATORY PARTITION IS SEALED')
    cases,rows_by_case=grouped_rows(document)
    if any(case.get('split')=='confirmatory' for case in cases.values()):
        raise ValueError('CONFIRMATORY PARTITION IS SEALED: sequential experiment refuses confirmatory metadata')

    dev_quiet,dev_leo,support_dev,quiet_cv=development_quiet_crossfit(cases,rows_by_case)
    quiet_scores=[float(row.surprise) for case in quiet_cv for row in case['scored_rows'] if row.status=='scored' and row.surprise is not None]
    if not quiet_scores:
        raise ValueError('no development quiet scores')
    bases=sorted(set(quantile(quiet_scores,q) for q in BASE_QUANTILES))
    candidates=[evaluate_base(base,cases,rows_by_case,dev_quiet,support_dev,quiet_cv) for base in bases]
    candidates.sort(key=selection_key)
    selected=candidates[0]

    cal_quiet=quiet_case_ids(cases,'calibration')
    all_quiet=dev_quiet+cal_quiet
    heldout,support_final,cal_case=calibration_quiet_crossfit(cases,rows_by_case,all_quiet)
    final_calibration=calibrate_operational_threshold(
        [cal_case],base_score_threshold=selected['base_score_threshold'],q0=selected['q0_empirical'],
        target_false_events_per_object_month=TARGET_FALSE_EVENTS_PER_OBJECT_MONTH,
    )
    diagnostic=final_development_diagnostic(
        cases,rows_by_case,all_quiet,support_final,selected['base_score_threshold'],selected['q0_empirical'],
        final_calibration['selected_wealth_threshold'],
    )
    output={
        'schema':'smd-sequential-v1-development-calibration',
        'evaluation_version':EVALUATION_VERSION,'scoring_version':EVENT_MATCHING_VERSION,
        'method':'selective-ml-v1.0 + sequential-evidence-v1.0',
        'confirmatory_partition_accessed':False,
        'detector_v0_4_modified':False,
        'selected_backbone':'transformer',
        'formal_guarantee_status':'conditional theorem only; real GP conditional exceedance bound is not proved',
        'operational_target_false_events_per_covered_object_month':TARGET_FALSE_EVENTS_PER_OBJECT_MONTH,
        'development_support_threshold_leo':support_dev,
        'base_threshold_candidates':candidates,
        'selected_base_score_threshold':selected['base_score_threshold'],
        'selected_q0_empirical':selected['q0_empirical'],
        'selection_rule':['development recall descending','PU sequential wealth percentile descending','median absolute delay ascending','base score threshold ascending'],
        'calibration_quiet_case':heldout,
        'final_support_threshold_leo':support_final,
        'final_event_calibration':final_calibration,
        'post_calibration_development_diagnostic':diagnostic,
        'unqualified_regimes':['GEO','HEO','MEO'],
        'failure_boundary':'q0 is empirical, temporal dependence is not certified, and calibration quiet exposure is small; no formal real-data risk-control claim is made',
        'confirmatory_rule':'Do not materialise, inspect, score, or tune against the confirmatory partition.',
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print(json.dumps(output,indent=2,allow_nan=False))


if __name__=='__main__': main()
