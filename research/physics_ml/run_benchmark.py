#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from detector import SequentialRiskDetector
from detector_v03 import CONTEXT_SCALE_FLOORS, RegimeNominalModel


def event_dict(event):
    return {
        'start_utc': event.start_utc,
        'end_utc': event.end_utc,
        'strongest_utc': event.strongest_utc,
        'max_wealth': event.max_wealth,
        'max_score': event.max_score,
        'physical_modes': list(event.physical_modes),
    }


def fit_profile_model(rows: list[dict]) -> RegimeNominalModel | None:
    n = len(rows)
    if n < 12:
        return None
    min_neighbors = min(12, max(5, n // 3))
    k = min(25, max(min_neighbors + 2, n - 2))
    model = RegimeNominalModel(k=k, min_neighbors=min_neighbors, max_context_distance=12.0, feature_scale_floor=1e-9)
    model.fit(rows)
    return model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--features', default='benchmark-results/features-v0.4-on-v0.3.json')
    parser.add_argument('--baseline', default='benchmark-results/baseline-v0.4-on-v0.3.json')
    parser.add_argument('--output', default='benchmark-results/physics-ml-v0.3-on-v0.3.json')
    args = parser.parse_args()

    features_doc = json.loads(Path(args.features).read_text())
    baseline_doc = json.loads(Path(args.baseline).read_text())
    rows = features_doc.get('rows') or []
    by_case: dict[str, list[dict]] = defaultdict(list)
    nominal_by_profile: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_case[str(row['case_id'])].append(row)
        if row.get('split') == 'calibration' and row.get('nominal') is True:
            nominal_by_profile[str(row.get('orbit_profile') or 'AUTO').upper()].append(row)
    for values in by_case.values():
        values.sort(key=lambda row: (str(row.get('epoch_utc', '')), int(row.get('index', 0))))

    models = {profile: fit_profile_model(values) for profile, values in nominal_by_profile.items()}
    models = {profile: model for profile, model in models.items() if model is not None}
    if not models:
        raise SystemExit('No orbit regime has enough explicit nominal calibration rows.')
    detectors = {profile: SequentialRiskDetector(model, alpha_event=0.02, betting_epsilon=0.5, physics_z_gate=2.0, max_event_gap_points=2) for profile, model in models.items()}

    output_cases = []
    for case in baseline_doc.get('cases') or []:
        profile = str(case.get('orbit_profile') or 'AUTO').upper()
        case_rows = by_case.get(str(case['case_id']), [])
        detector = detectors.get(profile)
        if detector is None:
            events = []; abstained = True
            decision_counts = {'nominal':0,'candidate':0,'statistical-alert':0,'abstain':len(case_rows)}
            abstention_reason = f'no calibrated nominal model for {profile}'
        else:
            decisions, events = detector.run(case_rows)
            abstained = bool(case_rows) and all(decision.status == 'abstain' for decision in decisions)
            decision_counts = {status: sum(decision.status == status for decision in decisions) for status in ('nominal','candidate','statistical-alert','abstain')}
            abstention_reason = None
        output_cases.append({
            'case_id':case['case_id'],'object_id':case['object_id'],'split':case.get('split'),
            'label_status':case.get('label_status'),'label_confidence':case.get('label_confidence'),
            'orbit_profile':profile,'source':case.get('source'),'span_days':case.get('span_days'),
            'abstained':abstained,'abstention_reason':abstention_reason,
            'truth_events':case.get('truth_events') or [],'predicted_events':[event_dict(event) for event in events],
            'decision_counts':decision_counts,
        })

    document = {
        'schema':'smd-physics-ml-benchmark-results-v1','detector_method':'physics-ml-v0.3',
        'benchmark_version':baseline_doc.get('benchmark_version'),'matching_tolerance_hours':baseline_doc.get('matching_tolerance_hours',24),
        'training':{
            'split':'calibration','nominal_rows_by_profile':{p:len(v) for p,v in sorted(nominal_by_profile.items())},
            'calibrated_profiles':sorted(detectors),'alpha_event':0.02,'betting_epsilon':0.5,'physics_z_gate':2.0,
            'context_scale_floors':CONTEXT_SCALE_FLOORS,
            'qualification':'Profile-specific nominal models use verified-quiet calibration rows only. Fixed physical context-scale floors prevent a single quiet spacecraft from defining zero within-regime support width.'
        },
        'cases':output_cases,
    }
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(document,indent=2)+'\n')
    print(f"Wrote {len(output_cases)} case results to {args.output}; calibrated profiles: {', '.join(sorted(detectors))}.")

if __name__=='__main__': main()
