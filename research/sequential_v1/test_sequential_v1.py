#!/usr/bin/env python3
from __future__ import annotations

import itertools
from math import isclose

from research.selective_v1.core import ScoredRow
from .formal import ChangePointMixtureEProcess, bernoulli_likelihood_ratio, event_wealth_threshold
from .operational import SequentialEventLayer, calibrate_operational_threshold, empirical_exceedance_bound


def exact_path_probability(bits, p):
    ones=sum(bits)
    return (p ** ones) * ((1.0-p) ** (len(bits)-ones))


def test_one_step_e_variable():
    q0=.1
    for q1 in (.2,.4,.7):
        expectation=q0*bernoulli_likelihood_ratio(1,q0=q0,q1=q1)+(1-q0)*bernoulli_likelihood_ratio(0,q0=q0,q1=q1)
        assert isclose(expectation,1.0,rel_tol=1e-12,abs_tol=1e-12)
        p=.04
        expectation=p*bernoulli_likelihood_ratio(1,q0=q0,q1=q1)+(1-p)*bernoulli_likelihood_ratio(0,q0=q0,q1=q1)
        assert expectation <= 1.0+1e-12


def test_exact_mixture_expectation_and_ville():
    q0=.1
    horizon=7
    alpha=.1
    threshold=1.0/alpha
    expected_wealth=0.0
    crossing_probability=0.0
    for bits in itertools.product((0,1),repeat=horizon):
        process=ChangePointMixtureEProcess(q0=q0,alternatives=(.2,.4,.7))
        maximum=1.0
        for bit in bits:
            maximum=max(maximum,process.update(bit).wealth)
        probability=exact_path_probability(bits,q0)
        expected_wealth += probability*process.wealth
        if maximum >= threshold:
            crossing_probability += probability
    assert expected_wealth <= 1.0+1e-10
    assert crossing_probability <= alpha+1e-12


def row(index, surprise, mode='along-track', status='scored'):
    return ScoredRow(index=index,epoch_utc=f'2026-01-01T00:{index:02d}:00Z',surprise=surprise if status=='scored' else None,
                     support_distance=.2 if status=='scored' else None,status=status,physical_mode=mode if status=='scored' else None,
                     reason=None if status=='scored' else 'synthetic abstention')


def test_abstention_reset_and_event():
    layer=SequentialEventLayer(base_score_threshold=2.0,q0=.1,wealth_threshold=2.0,alternatives=(.8,),refractory_points=1)
    rows=[row(0,3.0),row(1,3.0),row(2,0.0,status='abstain'),row(3,3.0),row(4,3.0)]
    steps,events=layer.run(rows)
    assert steps[2].status=='abstain'
    assert len(events)>=1
    # Evidence before the abstention may not set the start of a later event.
    for event in events:
        if event.end_index >= 3:
            assert event.start_index >= 3


def test_empirical_q0_and_rate_calibration():
    quiet=[
        {'case_id':'q1','span_days':30.4375,'scored_rows':[row(i,3.0 if i in {3,9} else 0.2) for i in range(12)]},
        {'case_id':'q2','span_days':30.4375,'scored_rows':[row(i,3.0 if i==6 else 0.2) for i in range(12)]},
    ]
    q=empirical_exceedance_bound(quiet,base_score_threshold=2.0)
    assert 0.0 < q['q0'] < 1.0
    result=calibrate_operational_threshold(
        quiet,base_score_threshold=2.0,q0=q['q0'],target_false_events_per_object_month=1.0,
        alternatives=(min(.95,q['q0']+.5*(1-q['q0'])),),candidate_thresholds=(1.1,2,4,8,16,32,64,128,256),
    )
    assert result['false_events_per_object_month'] <= 1.0
    assert result['selected_wealth_threshold'] > 1.0


def test_repeated_event_spending_thresholds_increase():
    first=event_wealth_threshold(total_type_i_budget=.05,event_index=1)
    second=event_wealth_threshold(total_type_i_budget=.05,event_index=2)
    third=event_wealth_threshold(total_type_i_budget=.05,event_index=3)
    assert 1.0 < first < second < third


def main():
    tests=[
        test_one_step_e_variable,
        test_exact_mixture_expectation_and_ville,
        test_abstention_reset_and_event,
        test_empirical_q0_and_rate_calibration,
        test_repeated_event_spending_thresholds_increase,
    ]
    for test in tests:
        test(); print('PASS',test.__name__)
    print(f'{len(tests)}/{len(tests)} sequential-v1 tests passed.')


if __name__=='__main__': main()
