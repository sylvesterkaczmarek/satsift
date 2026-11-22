#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEV=ROOT/'benchmark-results'/'sequential-v1-development.json'
SIM=ROOT/'benchmark-results'/'sequential-v1-null-simulations.json'
EXPECTED_DEV_SHA='9e5bf318de58510ca3b75a01bb5719c1113738a805168052f0b77b1f7020d34d'
EXPECTED_SIM_SHA='178c8cf762796dde185e8e340627b6480be9e6a8dc1b964fdef606af3c238d3f'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert DEV.is_file() and SIM.is_file()
    assert digest(DEV)==EXPECTED_DEV_SHA, (digest(DEV),EXPECTED_DEV_SHA)
    assert digest(SIM)==EXPECTED_SIM_SHA, (digest(SIM),EXPECTED_SIM_SHA)

    dev=json.loads(DEV.read_text())
    assert dev['schema']=='smd-sequential-v1-development-calibration'
    assert dev['confirmatory_partition_accessed'] is False
    assert dev['detector_v0_4_modified'] is False
    assert dev['selected_backbone']=='transformer'
    assert dev['formal_guarantee_status']=='conditional theorem only; real GP conditional exceedance bound is not proved'
    assert dev['operational_target_false_events_per_covered_object_month']==1.0
    assert dev['selected_base_score_threshold']==17.822733355396952
    assert dev['selected_q0_empirical']==0.16603773584905662
    assert dev['final_support_threshold_leo']==1.2019241655473716
    assert dev['unqualified_regimes']==['GEO','HEO','MEO']
    cal=dev['final_event_calibration']
    assert cal['selected_wealth_threshold']==1.01
    assert cal['false_events']==0
    assert cal['covered_verified_quiet_object_months']==0.4665623499247091
    assert cal['false_events_per_object_month']==0.0
    diag=dev['post_calibration_development_diagnostic']
    assert diag['tp']==0 and diag['fn']==36 and diag['recall']==0.0
    selected=dev['base_threshold_candidates'][0]
    assert selected['pu_sequential_wealth_mean_percentile']==0.6427083333333333
    assert selected['pu_scorable_truth_intervals']==32

    sim=json.loads(SIM.read_text())
    assert sim['q0']==0.05 and sim['alpha']==0.05 and sim['wealth_threshold']==20.0
    assert sim['updates_per_path']==500 and sim['replicates']==3000
    by_name={item['name']:item for item in sim['simulations']}
    assert by_name['iid-boundary']['crossing_probability']==0.028
    assert by_name['predictable-valid-nonstationary']['crossing_probability']==0.019666666666666666
    assert by_name['clustered-same-marginal-conditional-bound-violated']['crossing_probability']==0.516
    assert by_name['misspecified-rate-1.5x-q0']['crossing_probability']==0.23266666666666666
    assert by_name['iid-boundary']['crossing_probability'] <= sim['alpha']
    assert by_name['predictable-valid-nonstationary']['crossing_probability'] <= sim['alpha']
    assert by_name['clustered-same-marginal-conditional-bound-violated']['crossing_probability'] > 10*sim['alpha']
    assert by_name['misspecified-rate-1.5x-q0']['crossing_probability'] > 4*sim['alpha']
    print('Sequential v1 frozen decision record and null/failure simulations verified.')


if __name__=='__main__': main()
