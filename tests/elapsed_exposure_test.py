#!/usr/bin/env python3
"""Synthetic regressions for exact elapsed exposure and conditional uncertainty."""
from __future__ import annotations

import copy
import itertools
import math
import random
import unittest
from datetime import datetime, timedelta, timezone

from research.elapsed_exposure import (
    feature_exposure_evidence,
    measure_exposure,
    validate_policy,
    zero_event_poisson_bound,
)

HOUR = 3_600_000_000
MONTH = 2_629_800_000_000
ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)
POLICY = {'version': 'elapsed-intervals-v1', 'max_gap_seconds': 7200}


def stamp(microseconds: int) -> str:
    return (ORIGIN + timedelta(microseconds=microseconds)).isoformat(
        timespec='microseconds').replace('+00:00', 'Z')


def interval(start: int, end: int, supported: bool = True) -> dict:
    return {'start_utc': stamp(start), 'end_utc': stamp(end), 'supported': supported}


def evidence(pairs, *, start: int = 0, end: int = 10 * HOUR) -> dict:
    return {
        'window_start_utc': stamp(start),
        'window_end_utc': stamp(end),
        'intervals': [interval(*pair) for pair in pairs],
    }


def cell_oracle(pairs, window_start: int, window_end: int, gap: int) -> tuple[int, int]:
    """Integrate elementary cells independently of an interval-merging algorithm."""
    admitted = [
        (max(start, window_start), min(end, window_end), supported)
        for start, end, supported in pairs
        if end - start <= gap and max(start, window_start) < min(end, window_end)
    ]
    boundaries = sorted({window_start, window_end, *(point for row in admitted for point in row[:2])})
    eligible = covered = 0
    for start, end in zip(boundaries, boundaries[1:]):
        active = [supported for left, right, supported in admitted if left <= start and right >= end]
        if active:
            eligible += end - start
            if any(active):
                covered += end - start
    return eligible, covered


class ElapsedExposureTests(unittest.TestCase):
    def test_irregular_sampling_measures_pairs_instead_of_row_fraction(self) -> None:
        measured = measure_exposure(evidence([
            (0, HOUR, True), (HOUR, 9 * HOUR, True), (9 * HOUR, 10 * HOUR, True),
        ]), POLICY)
        self.assertEqual(measured['status'], 'available')
        self.assertEqual(measured['window_microseconds'], 10 * HOUR)
        self.assertEqual(measured['eligible_microseconds'], 2 * HOUR)
        self.assertEqual(measured['covered_microseconds'], 2 * HOUR)
        self.assertEqual(measured['abstained_microseconds'], 0)
        self.assertEqual(measured['unobserved_microseconds'], 8 * HOUR)
        self.assertAlmostEqual(measured['covered_fraction'], 0.2)
        self.assertAlmostEqual(measured['uncovered_window_fraction'], 0.8)
        self.assertEqual(measured['elapsed_abstention_fraction'], 0.0)
        self.assertAlmostEqual(measured['covered_object_months'], 2 * HOUR / MONTH)

    def test_duplicate_permuted_and_subdivided_intervals_do_not_inflate_time(self) -> None:
        original = [(0, HOUR, True), (HOUR, 2 * HOUR, True), (4 * HOUR, 5 * HOUR, True)]
        expected = measure_exposure(evidence(original), POLICY)
        variants = [
            original * 3,
            list(reversed(original)),
            [(0, HOUR // 2, True), (HOUR // 2, HOUR, True), *original[1:]],
            [(0, 2 * HOUR, True), (HOUR // 2, 3 * HOUR // 2, True), original[-1]],
        ]
        variants.extend(list(order) for order in itertools.permutations(original))
        original_bound = zero_event_poisson_bound(0, expected['covered_object_months'])
        for pairs in variants:
            with self.subTest(pairs=pairs):
                measured = measure_exposure(evidence(pairs), POLICY)
                self.assertEqual(measured['covered_microseconds'], 3 * HOUR)
                self.assertEqual(measured['eligible_microseconds'], 3 * HOUR)
                self.assertEqual(measured['covered_intervals_us'], expected['covered_intervals_us'])
                self.assertEqual(
                    zero_event_poisson_bound(0, measured['covered_object_months'])['upper_events_per_object_month'],
                    original_bound['upper_events_per_object_month'],
                )

    def test_seeded_interval_unions_match_an_independent_cell_oracle(self) -> None:
        rng = random.Random(71203)
        for trial in range(150):
            pairs = []
            for _ in range(rng.randrange(1, 30)):
                start = rng.randrange(-20, 120)
                pairs.append((start, start + rng.randrange(1, 35), True))
            rng.shuffle(pairs)
            maximum_gap = rng.randrange(1, 35)
            policy = {'version': 'elapsed-intervals-v1', 'max_gap_seconds': maximum_gap / 1_000_000}
            expected_eligible, expected_covered = cell_oracle(pairs, 0, 100, maximum_gap)
            measured = measure_exposure(evidence(pairs, end=100), policy)
            with self.subTest(trial=trial):
                self.assertEqual(measured['eligible_microseconds'], expected_eligible)
                self.assertEqual(measured['covered_microseconds'], expected_covered)
                self.assertEqual(measured['unobserved_microseconds'], 100 - expected_eligible)

    def test_gap_limit_is_inclusive_and_checked_before_clipping(self) -> None:
        at_limit = measure_exposure(evidence([(0, 2 * HOUR, True)]), POLICY)
        beyond_limit = measure_exposure(evidence([(0, 2 * HOUR + 1, True)]), POLICY)
        self.assertEqual(at_limit['covered_microseconds'], 2 * HOUR)
        self.assertEqual(beyond_limit['covered_microseconds'], 0)
        clipped_long_gap = measure_exposure(
            evidence([(-HOUR, 2 * HOUR, True)], start=0, end=HOUR), POLICY)
        self.assertEqual(clipped_long_gap['eligible_microseconds'], 0)
        self.assertEqual(clipped_long_gap['unobserved_microseconds'], HOUR)

    def test_clipping_uses_recorded_bounds_without_extrapolation(self) -> None:
        measured = measure_exposure(evidence([
            (-HOUR, HOUR, True), (3 * HOUR, 5 * HOUR, False),
            (9 * HOUR, 11 * HOUR, True),
        ]), POLICY)
        self.assertEqual(measured['eligible_microseconds'], 4 * HOUR)
        self.assertEqual(measured['covered_microseconds'], 2 * HOUR)
        self.assertEqual(measured['abstained_microseconds'], 2 * HOUR)
        self.assertEqual(measured['unobserved_microseconds'], 6 * HOUR)
        self.assertEqual(measured['elapsed_abstention_fraction'], 0.5)

    def test_abstention_is_distinct_from_unobserved_duration(self) -> None:
        measured = measure_exposure(evidence([
            (0, HOUR, True), (HOUR, 2 * HOUR, False),
        ], end=4 * HOUR), POLICY)
        self.assertEqual(measured['covered_microseconds'], HOUR)
        self.assertEqual(measured['abstained_microseconds'], HOUR)
        self.assertEqual(measured['unobserved_microseconds'], 2 * HOUR)
        self.assertEqual(measured['covered_fraction'], 0.25)
        self.assertEqual(measured['elapsed_abstention_fraction'], 0.5)
        self.assertEqual(measured['uncovered_window_fraction'], 0.75)

    def test_contradictory_eligible_support_is_order_independent(self) -> None:
        for pairs in [
            [(0, HOUR, True), (0, HOUR, False)],
            [(0, 2 * HOUR, True), (HOUR, 3 * HOUR, False)],
            [(0, 2 * HOUR, False), (HOUR, 2 * HOUR, True)],
        ]:
            for ordered in (pairs, list(reversed(pairs))):
                with self.subTest(pairs=ordered), self.assertRaises(ValueError):
                    measure_exposure(evidence(ordered), POLICY)
        adjacent = measure_exposure(evidence([
            (0, HOUR, True), (HOUR, 2 * HOUR, False),
        ]), POLICY)
        self.assertEqual(adjacent['covered_microseconds'], HOUR)
        excluded = measure_exposure(evidence([
            (0, 3 * HOUR, False), (0, HOUR, True),
        ]), POLICY)
        self.assertEqual(excluded['covered_microseconds'], HOUR)
        outside = measure_exposure(evidence([
            (-2 * HOUR, -HOUR, False), (-2 * HOUR, -HOUR, True),
        ]), POLICY)
        self.assertEqual(outside['covered_microseconds'], 0)

    def test_missing_evidence_is_not_known_zero(self) -> None:
        for ledger, policy in [
            (None, POLICY),
            ({'window_start_utc': stamp(0), 'window_end_utc': stamp(HOUR)}, POLICY),
            ({'intervals': []}, POLICY),
            (evidence([]), None),
            (evidence([]), {'version': 'elapsed-intervals-v1'}),
        ]:
            with self.subTest(ledger=ledger, policy=policy):
                measured = measure_exposure(ledger, policy)
                self.assertEqual(measured['status'], 'unavailable')
                self.assertIsNotNone(measured['reason'])
                for field in ('covered_microseconds', 'covered_object_months',
                              'eligible_microseconds', 'covered_fraction', 'covered_intervals_us'):
                    self.assertIsNone(measured[field])
        empty = measure_exposure(evidence([]), POLICY)
        self.assertEqual(empty['status'], 'available')
        self.assertEqual(empty['covered_microseconds'], 0)
        self.assertEqual(empty['covered_object_months'], 0)
        self.assertEqual(empty['covered_intervals_us'], [])
        self.assertEqual(empty['unobserved_microseconds'], 10 * HOUR)

    def test_empty_windows_have_undefined_fractions(self) -> None:
        measured = measure_exposure(evidence([(0, HOUR, True)], start=HOUR, end=HOUR), POLICY)
        for field in ('window_microseconds', 'eligible_microseconds', 'covered_microseconds',
                      'abstained_microseconds', 'unobserved_microseconds'):
            self.assertEqual(measured[field], 0)
        for field in ('covered_fraction', 'elapsed_abstention_fraction', 'uncovered_window_fraction'):
            self.assertIsNone(measured[field])

    def test_policy_requires_explicit_exact_positive_gap(self) -> None:
        self.assertIsNone(validate_policy(None))
        self.assertIsNone(validate_policy({}))
        self.assertEqual(validate_policy(POLICY)['version'], 'elapsed-intervals-v1')
        self.assertEqual(validate_policy({'version': 'elapsed-intervals-v1', 'max_gap_seconds': 0.000001})['max_gap_seconds'], 0.000001)
        for gap in (True, False, None, 0, -1, '1', math.nan, math.inf, 0.0000005, 1.0000001):
            with self.subTest(gap=gap), self.assertRaises(ValueError):
                validate_policy({'version': 'elapsed-intervals-v1', 'max_gap_seconds': gap})
        for policy in ([], 'policy', {'version': 'unknown', 'max_gap_seconds': 1},
                       {**POLICY, 'unreviewed': True}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                validate_policy(policy)

    def test_supplied_malformed_evidence_and_timestamps_are_rejected(self) -> None:
        valid = evidence([(0, HOUR, True)])
        bad_times = (
            None, False, 2026, '', '2026-01-01', '2026-01-01T00:00:00',
            '2026-02-30T00:00:00Z', '2026-01-01T24:00:00Z',
            '2026-01-01T00:00:00.0000001Z', ' 2026-01-01T00:00:00Z',
            '2026-01-01T00:00:00Z\n',
        )
        for value in bad_times:
            for location in ('window', 'interval'):
                bad = copy.deepcopy(valid)
                if location == 'window':
                    bad['window_start_utc'] = value
                else:
                    bad['intervals'][0]['start_utc'] = value
                with self.subTest(value=value, location=location), self.assertRaises(ValueError):
                    measure_exposure(bad, POLICY)
        for bad in (
            [], 'evidence', {**valid, 'intervals': None},
            {**valid, 'intervals': [None]}, {**valid, 'extra': True},
            evidence([(HOUR, 0, True)]), evidence([(0, 0, True)]),
            evidence([], start=HOUR, end=0),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                measure_exposure(bad, POLICY)
        for decision in (None, 0, 1, 'true', [], {}):
            with self.subTest(decision=decision), self.assertRaises(ValueError):
                measure_exposure(evidence([(0, HOUR, decision)]), POLICY)

    def test_incomplete_evidence_does_not_mask_malformed_present_values(self) -> None:
        malformed = [
            {'window_start_utc': '2026-02-30T00:00:00Z'},
            {'intervals': [{'start_utc': stamp(0), 'supported': 'yes'}]},
            {'intervals': [None]},
        ]
        for value in malformed:
            for policy in (None, POLICY):
                with self.subTest(value=value, policy=policy), self.assertRaises(ValueError):
                    measure_exposure(value, policy)
        with self.assertRaises(ValueError):
            measure_exposure(None, {'version': 'unreviewed'})
        missing_then_invalid = [
            {'epoch_utc': stamp(HOUR)},
            {'epoch_utc': '2026-02-30T00:00:00Z', 'physics': {}},
        ]
        with self.assertRaises(ValueError):
            feature_exposure_evidence(stamp(0), stamp(HOUR), missing_then_invalid, [1, None])

    def test_microseconds_and_equivalent_timezones_are_exact(self) -> None:
        ledger = evidence([(0, 1, True)], end=1)
        ledger['window_start_utc'] = '2026-01-01T01:00:00+01:00'
        ledger['intervals'][0]['start_utc'] = '2025-12-31T19:00:00-05:00'
        measured = measure_exposure(ledger, {'version': 'elapsed-intervals-v1', 'max_gap_seconds': 0.000001})
        self.assertEqual(measured['covered_microseconds'], 1)
        self.assertEqual(measured['window_microseconds'], 1)
        self.assertEqual(measured['covered_fraction'], 1.0)

    def test_feature_adapter_preserves_source_pairs_and_aligned_support(self) -> None:
        rows = [
            {'epoch_utc': stamp(HOUR), 'physics': {'before_epoch_utc': stamp(0), 'after_epoch_utc': stamp(HOUR)}},
            {'epoch_utc': stamp(10 * HOUR), 'physics': {'before_epoch_utc': stamp(9 * HOUR), 'after_epoch_utc': stamp(10 * HOUR)}},
        ]
        before = copy.deepcopy(rows)
        ledger = feature_exposure_evidence(stamp(0), stamp(10 * HOUR), rows, [0.0, None])
        measured = measure_exposure(ledger, POLICY)
        self.assertEqual(measured['eligible_microseconds'], 2 * HOUR)
        self.assertEqual(measured['covered_microseconds'], HOUR)
        self.assertEqual(measured['abstained_microseconds'], HOUR)
        self.assertEqual(rows, before)
        self.assertEqual(ledger['intervals'][1]['start_utc'], stamp(9 * HOUR))

    def test_feature_adapter_does_not_guess_missing_pairs_or_truncate(self) -> None:
        complete = {'epoch_utc': stamp(HOUR), 'physics': {
            'before_epoch_utc': stamp(0), 'after_epoch_utc': stamp(HOUR)}}
        self.assertIsNone(feature_exposure_evidence(stamp(0), stamp(HOUR), [{'epoch_utc': stamp(HOUR)}], [1.0]))
        self.assertIsNone(feature_exposure_evidence(None, stamp(HOUR), [complete], [1.0]))
        for rows, scores in (([complete], []), ([], [1.0]), ([complete, complete], [1.0])):
            with self.subTest(rows=rows, scores=scores), self.assertRaises(ValueError):
                feature_exposure_evidence(stamp(0), stamp(HOUR), rows, scores)
        for score in (True, False, '1', math.nan, math.inf):
            with self.subTest(score=score), self.assertRaises(ValueError):
                feature_exposure_evidence(stamp(0), stamp(HOUR), [complete], [score])
        inconsistent = copy.deepcopy(complete)
        inconsistent['epoch_utc'] = stamp(HOUR + 1)
        with self.assertRaises(ValueError):
            feature_exposure_evidence(stamp(0), stamp(HOUR), [inconsistent], [1.0])


class ZeroEventBoundTests(unittest.TestCase):
    def test_positive_bound_matches_the_analytic_zero_count_identity(self) -> None:
        for exposure in (1 / 730.5, 0.1, 1.0, 10.0, 1e6):
            with self.subTest(exposure=exposure):
                result = zero_event_poisson_bound(0, exposure)
                self.assertEqual(result['status'], 'conditional_model_bound')
                self.assertAlmostEqual(result['upper_events_per_object_month'] * exposure, -math.log(0.05))
                self.assertGreater(result['upper_events_per_object_month'], 0)
                self.assertEqual(result['confidence_level'], 0.95)
                self.assertEqual(result['sidedness'], 'upper-one-sided')
                self.assertIs(result['assumptions_verified'], False)

    def test_unsupported_bound_conditions_are_explicit(self) -> None:
        for count, exposure, kwargs, status in (
            (0, None, {'exposure_status': 'unavailable'}, 'unavailable_exposure'),
            (0, 0.0, {}, 'zero_exposure'),
            (0, 1.0, {'event_support_consistent': False}, 'inconsistent_event_support'),
            (1, 1.0, {}, 'nonzero_count'),
        ):
            with self.subTest(status=status):
                result = zero_event_poisson_bound(count, exposure, **kwargs)
                self.assertEqual(result['status'], status)
                self.assertIsNone(result['upper_events_per_object_month'])
                self.assertIs(result['assumptions_verified'], False)

    def test_invalid_counts_and_exposure_are_not_coerced(self) -> None:
        for count in (-1, True, False, 0.5, '0', None, math.nan):
            with self.subTest(count=count), self.assertRaises(ValueError):
                zero_event_poisson_bound(count, 1.0)
        for exposure in (-1.0, True, math.nan, math.inf, '1'):
            with self.subTest(exposure=exposure), self.assertRaises(ValueError):
                zero_event_poisson_bound(0, exposure)


if __name__ == '__main__':
    unittest.main(verbosity=2)
