#!/usr/bin/env python3
"""Research boundary regressions, independent of consumed benchmark holdouts."""
from __future__ import annotations

import copy
import math
import os
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.integrity_v1.gate import SelectiveIntegrityGate
from research.physics_ml.detector import CONTEXT, FEATURES, ConditionalNominalModel
from research.physics_ml.evaluate import match_events, parse_time as evaluation_time
from research.physics_v1.core import PhysicsNoiseModel, solve_kepler
from research.selective_v1.core import CONTEXT_NAMES, SupportModel, parse_time as selective_time


def nominal_row(object_id: str | None, index: int) -> dict:
    context = {name: 0.01 * (index + 1) for name in (*CONTEXT_NAMES, *CONTEXT)}
    context.update(orbit_leo=1.0, orbit_meo=0.0, orbit_geo=0.0, orbit_heo=0.0)
    elements = {
        'semi_major_axis_km': 7000.0, 'eccentricity': 0.01,
        'inclination_deg': 50.0, 'raan_deg': 10.0,
        'argument_of_periapsis_deg': 20.0, 'mean_anomaly_deg': 30.0,
    }
    return {
        'object_id': object_id, 'nominal': True, 'quality_ok': True,
        'context': context, 'features': {name: 0.001 * index for name in FEATURES},
        'orbit_regime': 'LEO',
        'physics': {'gap_days': 1.0, 'before_elements': dict(elements), 'after_elements': dict(elements)},
    }


def valid_case() -> dict:
    return {
        'raw_record_count': 30, 'resolved_record_count': 30,
        'rejected_fraction': 0.0, 'sgp4_pair_count': 29,
        'sgp4_failure_fraction': 0.0, 'total_evaluated': 20,
        'detector_mode_used': 'SGP4 multivariate',
        'median_gap_days': 1.0, 'maximum_gap_days': 1.0,
        'object_ids_seen': ['90001'], 'orbit_regimes_seen': ['LEO'],
        'quality_status': 'usable',
    }


class KeplerRegressionTests(unittest.TestCase):
    def test_previously_divergent_elliptic_cases_satisfy_equation(self) -> None:
        for e, mean in ((0.8, -1.6210618092523332), (0.9, -2.0703095587156737), (0.99, -3.0)):
            with self.subTest(e=e, mean=mean):
                eccentric = solve_kepler(mean, e)
                self.assertLess(abs(eccentric - e * math.sin(eccentric) - mean), 2e-13)

    def test_eccentric_grid_is_bounded_and_satisfies_equation(self) -> None:
        for e in (0.0, 0.5, 0.8, 0.9, 0.99, 0.999999, 1.0 - 2.0**-52):
            for index in range(-100, 101):
                mean = math.pi * index / 101
                eccentric = solve_kepler(mean, e)
                self.assertTrue(math.isfinite(eccentric))
                self.assertLess(abs(eccentric - e * math.sin(eccentric) - mean), 2e-13)

    def test_nonfinite_mean_anomaly_is_rejected(self) -> None:
        for mean in (float('nan'), float('inf'), -float('inf')):
            with self.assertRaises(ValueError):
                solve_kepler(mean, 0.1)


class CalibrationContractTests(unittest.TestCase):
    def test_conditional_model_rejects_implicitly_nominal_rows(self) -> None:
        for label in (None, False, 'true', 1):
            rows = [nominal_row('100', i) for i in range(10)]
            for row in rows:
                row['nominal'] = label
            with self.subTest(label=label), self.assertRaises(ValueError):
                ConditionalNominalModel(k=5, min_neighbors=3).fit(rows)

    def test_conditional_model_excludes_quality_failures(self) -> None:
        rows = [nominal_row('100', i) for i in range(10)]
        bad = nominal_row('101', 1000)
        bad['quality_ok'] = False
        model = ConditionalNominalModel(k=5, min_neighbors=3).fit(rows + [bad])
        self.assertEqual(model.rows, rows)

    def test_support_does_not_count_unknown_identity_as_independent_satellite(self) -> None:
        rows = [nominal_row(object_id, i) for object_id in ('100', None) for i in range(6)]
        support = SupportModel(k=3, min_reference_satellites=2).fit(rows)
        self.assertEqual(support.reference_satellites('LEO'), {'100'})
        self.assertEqual(support.qualified_regimes(), set())
        self.assertIsNone(support.distance(nominal_row('999', 2)))

    def test_support_requires_explicit_quiet_reference_rows(self) -> None:
        for label in (None, False, 'true', 1):
            rows = [nominal_row('100', i) for i in range(6)]
            for row in rows:
                row['nominal'] = label
            with self.subTest(label=label), self.assertRaises(ValueError):
                SupportModel(k=3).fit(rows)

    def test_physics_noise_requires_known_independent_quiet_objects(self) -> None:
        rows = [nominal_row(object_id, i) for object_id in ('100', None) for i in range(6)]
        model = PhysicsNoiseModel(min_reference_satellites=2).fit(rows)
        self.assertEqual(model.qualified_regimes(), set())
        for row in rows:
            row['nominal'] = 'true'
        self.assertEqual(PhysicsNoiseModel(min_reference_satellites=1).fit(rows).qualified_regimes(), set())


@unittest.skipUnless(hasattr(time, 'tzset'), 'host does not expose time.tzset')
class TimestampRegressionTests(unittest.TestCase):
    def test_prediction_parser_and_truth_timezone_contracts(self) -> None:
        original = os.environ.get('TZ')
        try:
            for zone in ('UTC', 'America/Los_Angeles', 'Asia/Tokyo'):
                os.environ['TZ'] = zone
                time.tzset()
                for parser in (evaluation_time, selective_time):
                    with self.subTest(zone=zone, parser=parser.__module__):
                        self.assertEqual(parser('2026-01-01T00:00:00'), parser('2026-01-01T00:00:00Z'))
                        self.assertEqual(parser('2026-01-01T01:00:00+01:00'), parser('2026-01-01T00:00:00Z'))
                predicted = [{'start_utc': '2026-01-01T00:00:00Z'}]
                with self.subTest(zone=zone, truth='zone-free'), self.assertRaises(ValueError):
                    match_events(predicted, [{'start': '2026-01-01T00:00:00'}], tolerance_hours=0.0)
                for truth in ('2026-01-01T00:00:00Z', '2026-01-01T01:00:00+01:00'):
                    with self.subTest(zone=zone, truth=truth):
                        matches = match_events(predicted, [{'start': truth}], tolerance_hours=0.0)
                        self.assertEqual(matches, [(0, 0, 0.0)])
        finally:
            if original is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = original
            time.tzset()


class IntegrityMetadataRegressionTests(unittest.TestCase):
    def test_nonfinite_or_invalid_quality_metadata_abstains(self) -> None:
        gate = SelectiveIntegrityGate(support_threshold=100.0)
        for key, values in (
            ('rejected_fraction', (float('nan'), float('inf'), -0.1, 1.1, 'bad', None)),
            ('sgp4_failure_fraction', (float('nan'), float('inf'), -0.1, 1.1, 'bad', None)),
            ('resolved_record_count', (float('nan'), float('inf'), 10**400, -1, 30.5, 'bad', True)),
            ('maximum_gap_days', (float('nan'), float('inf'), -1, 'bad')),
        ):
            for value in values:
                case = valid_case()
                case[key] = value
                with self.subTest(key=key, value=value):
                    decision = gate.case_decision(case)
                    self.assertTrue(decision.abstain)
                    self.assertEqual(decision.primary_reason, 'invalid_quality_metadata')

    def test_valid_metadata_is_unchanged_and_not_mutated(self) -> None:
        case = valid_case()
        case['resolved_record_count'] = '30'
        original = copy.deepcopy(case)
        decision = SelectiveIntegrityGate(support_threshold=100.0).case_decision(case)
        self.assertFalse(decision.abstain)
        self.assertEqual(case, original)

    def test_invalid_gate_configuration_is_rejected(self) -> None:
        for options in (
            {'support_threshold': float('nan')},
            {'support_threshold': float('inf')},
            {'max_rejected_fraction': float('nan')},
            {'max_sgp4_failure_fraction': 1.1},
            {'max_excluded_gap_fraction': -0.1},
            {'max_gap_ratio': float('inf')},
            {'min_resolved_records': 12.5},
            {'min_evaluated_pairs': 0},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                SelectiveIntegrityGate(**{'support_threshold': 100.0, **options})


if __name__ == '__main__':
    unittest.main()
