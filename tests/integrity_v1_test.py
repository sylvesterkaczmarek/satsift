#!/usr/bin/env python3
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.integrity_v1.gate import SelectiveIntegrityGate
from research.integrity_v1.stressors import STRESSORS, generate_stress_benchmark
from research.selective_v1.core import CONTEXT_NAMES, FEATURE_NAMES, DistributionPrediction, SupportModel


def row(object_id: str, index: int, *, shift: float = 0.0) -> dict:
    context = {name: 0.01 * index for name in CONTEXT_NAMES}
    context.update({'orbit_leo': 1.0, 'orbit_meo': 0.0, 'orbit_geo': 0.0, 'orbit_heo': 0.0})
    context['log_semi_major_axis_km'] += shift
    features = {name: 0.001 * (index + 1) for name in FEATURE_NAMES}
    return {
        'case_id': 'case', 'object_id': object_id, 'index': index,
        'nominal': True, 'quality_ok': True,
        'epoch_utc': f'2026-01-{index+1:02d}T00:00:00Z',
        'context': context, 'features': features,
        'physics': {'gap_days': 1.0},
        'integrity': {'pair_eligible': True, 'sgp4_residual_available': True},
    }


def case(**overrides) -> dict:
    base = {
        'case_id': 'case', 'object_id': '90001', 'quality_status': 'usable',
        'raw_record_count': 30, 'resolved_record_count': 30, 'rejected_fraction': 0.0,
        'exact_duplicate_count': 0, 'conflicting_duplicate_count': 0,
        'unresolved_near_simultaneous_count': 0, 'superseded_count': 0,
        'excluded_gap_count': 0, 'sgp4_pair_count': 29, 'sgp4_failure_count': 0,
        'sgp4_failure_fraction': 0.0, 'detector_mode_used': 'SGP4 multivariate',
        'median_gap_days': 1.0, 'maximum_gap_days': 1.0, 'total_evaluated': 20,
        'object_ids_seen': ['90001'], 'orbit_regimes_seen': ['LEO'],
        'regime_change_detected': False, 'hard_quality_errors': [],
    }
    base.update(overrides)
    return base


class FakeModel:
    def predict_sequence(self, rows):
        return [DistributionPrediction(
            location={name: 0.0 for name in FEATURE_NAMES},
            scale={name: 1.0 for name in FEATURE_NAMES},
            z_scores={name: 1.0 for name in FEATURE_NAMES},
            surprise=1.0,
        ) for _ in rows]


def support_model() -> SupportModel:
    refs = []
    for object_index, object_id in enumerate(('80001', '80002', '80003')):
        refs.extend(row(object_id, index, shift=0.001 * object_index) for index in range(6))
    return SupportModel(k=5, min_reference_satellites=3).fit(refs)


def test_explicit_case_abstentions() -> None:
    gate = SelectiveIntegrityGate(support_threshold=100.0)
    assert gate.case_decision(case(conflicting_duplicate_count=1)).primary_reason == 'unresolved_catalogue_revision'
    assert gate.case_decision(case(resolved_record_count=8, total_evaluated=2)).primary_reason == 'insufficient_history'
    assert gate.case_decision(case(sgp4_pair_count=0, sgp4_failure_fraction=1.0)).primary_reason == 'poor_propagation'
    assert gate.case_decision(case(rejected_fraction=0.25)).primary_reason == 'missing_or_corrupted_history'
    identity = gate.case_decision(case(object_ids_seen=['90001', '90002']))
    assert identity.abstain and 'catalogue_identity_or_regime_change' in identity.reasons
    regime = gate.case_decision(case(orbit_regimes_seen=['LEO', 'MEO'], regime_change_detected=True))
    assert regime.abstain and 'catalogue_identity_or_regime_change' in regime.reasons


def test_recoverable_catalogue_audits() -> None:
    gate = SelectiveIntegrityGate(support_threshold=100.0)
    decision = gate.case_decision(case(exact_duplicate_count=3, superseded_count=2))
    assert not decision.abstain
    assert set(decision.alerts) == {'replay_or_exact_duplicate_detected', 'catalogue_correction_resolved'}


def test_row_selective_abstention_and_ood() -> None:
    support = support_model(); model = FakeModel()
    clean = row('90001', 2)
    gate = SelectiveIntegrityGate(support_threshold=100.0)
    scored, meta = gate.score_sequence(model, support, case(), [clean])
    assert scored[0].status == 'scored', meta

    bad = deepcopy(clean); bad['integrity']['sgp4_residual_available'] = False
    scored, meta = gate.score_sequence(model, support, case(), [bad])
    assert scored[0].status == 'abstain'
    assert meta['reason_counts'] == {'poor_propagation': 1}

    far = deepcopy(clean); far['context']['log_semi_major_axis_km'] += 1000.0
    tight = SelectiveIntegrityGate(support_threshold=0.01)
    scored, meta = tight.score_sequence(model, support, case(), [far])
    assert scored[0].status == 'abstain'
    assert meta['reason_counts'] == {'out_of_distribution_object': 1}



class SegmentRecordingModel:
    def __init__(self):
        self.calls = []

    def predict_sequence(self, rows):
        self.calls.append([int(item['index']) for item in rows])
        predictions = []
        for position, _item in enumerate(rows):
            if position == 0:
                predictions.append(None)
            else:
                predictions.append(DistributionPrediction(
                    location={name: 0.0 for name in FEATURE_NAMES},
                    scale={name: 1.0 for name in FEATURE_NAMES},
                    z_scores={name: 1.0 for name in FEATURE_NAMES},
                    surprise=1.0,
                ))
        return predictions


def test_integrity_abstention_resets_temporal_context() -> None:
    support = support_model()
    model = SegmentRecordingModel()
    rows = [row('90001', index) for index in range(4)]
    rows[1]['integrity']['pair_eligible'] = False
    gate = SelectiveIntegrityGate(support_threshold=100.0)
    scored, meta = gate.score_sequence(model, support, case(), rows)
    assert model.calls == [[0], [2, 3]], model.calls
    assert [item.status for item in scored] == ['abstain', 'abstain', 'abstain', 'scored']
    assert meta['reason_counts']['irregular_or_gapped_sampling'] == 1
    assert meta['reason_counts']['conditional_distribution_unavailable'] == 2

def test_stress_generator_is_deterministic_and_sealed() -> None:
    records = []
    for index in range(20):
        records.append({
            'NORAD_CAT_ID': '90001', 'EPOCH': f'2026-01-{index+1:02d}T00:00:00.000000Z',
            'CREATION_DATE': f'2026-01-{index+1:02d}T01:00:00.000000Z', 'ELEMENT_SET_NO': index + 1,
            'GP_ID': str(1000 + index), 'MEAN_MOTION': 15.5, 'ECCENTRICITY': 0.001,
            'INCLINATION': 51.6, 'RA_OF_ASC_NODE': 10.0 + index, 'ARG_OF_PERICENTER': 20.0,
            'MEAN_ANOMALY': 30.0 + index, 'BSTAR': 0.0,
        })
    document = {'benchmark_version': '1.0', 'cases': [{
        'case_id': 'x', 'object_id': '90001', 'split': 'development', 'label_status': 'verified-quiet',
        'records': records, 'truth_events': [],
    }]}
    first = generate_stress_benchmark(document)
    second = generate_stress_benchmark(document)
    assert first == second
    assert first['confirmatory_sealed'] is True
    assert len(first['cases']) == len(STRESSORS) + 1
    conditions = {item['integrity_stress']['condition'] for item in first['cases']}
    assert conditions == {'clean'} | {item[0] for item in STRESSORS}


def main() -> None:
    tests = [
        test_explicit_case_abstentions,
        test_recoverable_catalogue_audits,
        test_row_selective_abstention_and_ood,
        test_integrity_abstention_resets_temporal_context,
        test_stress_generator_is_deterministic_and_sealed,
    ]
    for test in tests:
        test()
        print('PASS', test.__name__)
    print(f'{len(tests)}/{len(tests)} integrity-v1 tests passed.')


if __name__ == '__main__':
    main()
