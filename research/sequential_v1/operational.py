#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from research.selective_v1.core import ScoredRow
from .formal import ChangePointMixtureEProcess, default_alternatives

OBJECT_MONTH_DAYS = 30.4375


@dataclass(frozen=True)
class SequentialStep:
    row_index: int
    epoch_utc: str
    status: str
    indicator: int | None
    wealth: float | None
    dominant_start_row_index: int | None
    reason: str | None = None


@dataclass(frozen=True)
class SequentialEvent:
    start_index: int
    end_index: int
    strongest_index: int
    start_utc: str
    end_utc: str
    strongest_utc: str
    trigger_wealth: float
    evidence_updates: int


class SequentialEventLayer:
    """Operational sequential layer around selective-v1 scores.

    The primary interface is an empirically calibrated wealth threshold chosen to meet a requested
    false-events-per-covered-object-month target on verified-quiet exposure. `q0` is likewise an
    empirical nominal exceedance bound unless a caller supplies an externally justified bound.

    Consequently the real-data mode is *risk-calibrated*, not formally risk-controlled. The
    e-process theorem in `formal.py` becomes a formal guarantee only when the stated conditional
    Bernoulli bound is independently valid for the stream being monitored.
    """

    def __init__(self, *, base_score_threshold: float, q0: float, wealth_threshold: float,
                 alternatives: Sequence[float] | None = None, refractory_points: int = 2) -> None:
        if not isfinite(float(base_score_threshold)):
            raise ValueError('base_score_threshold must be finite')
        if not 0.0 < float(q0) < 1.0:
            raise ValueError('q0 must lie in (0,1)')
        if not isfinite(float(wealth_threshold)) or float(wealth_threshold) <= 1.0:
            raise ValueError('wealth_threshold must be finite and > 1')
        if refractory_points < 0:
            raise ValueError('refractory_points must be nonnegative')
        self.base_score_threshold = float(base_score_threshold)
        self.q0 = float(q0)
        self.wealth_threshold = float(wealth_threshold)
        self.alternatives = tuple(alternatives or default_alternatives(self.q0))
        self.refractory_points = int(refractory_points)

    def run(self, rows: Sequence[ScoredRow]) -> tuple[list[SequentialStep], list[SequentialEvent]]:
        process = ChangePointMixtureEProcess(q0=self.q0, alternatives=self.alternatives)
        steps: list[SequentialStep] = []
        events: list[SequentialEvent] = []
        segment_rows: list[ScoredRow] = []
        refractory = 0

        for row in rows:
            if row.status != 'scored' or row.surprise is None or not isfinite(float(row.surprise)):
                process.reset()
                segment_rows = []
                refractory = 0
                steps.append(SequentialStep(
                    row_index=row.index, epoch_utc=row.epoch_utc, status='abstain',
                    indicator=None, wealth=None, dominant_start_row_index=None,
                    reason=row.reason or 'selective layer abstained; sequential evidence reset',
                ))
                continue

            if refractory > 0:
                refractory -= 1
                process.reset()
                segment_rows = []
                steps.append(SequentialStep(
                    row_index=row.index, epoch_utc=row.epoch_utc, status='refractory',
                    indicator=None, wealth=None, dominant_start_row_index=None,
                    reason='post-event refractory point; sequential evidence reset',
                ))
                continue

            indicator = int(
                float(row.surprise) >= self.base_score_threshold
                and row.physical_mode is not None
            )
            segment_rows.append(row)
            update = process.update(indicator)
            dominant_actual = None
            if update.dominant_start_index is not None:
                offset = update.dominant_start_index - 1
                if 0 <= offset < len(segment_rows):
                    dominant_actual = segment_rows[offset].index
            alarm = update.wealth >= self.wealth_threshold
            steps.append(SequentialStep(
                row_index=row.index,
                epoch_utc=row.epoch_utc,
                status='event' if alarm else 'monitor',
                indicator=indicator,
                wealth=update.wealth,
                dominant_start_row_index=dominant_actual,
            ))
            if alarm:
                start_offset = (update.dominant_start_index or update.time_index) - 1
                start_offset = min(max(start_offset, 0), len(segment_rows) - 1)
                start_row = segment_rows[start_offset]
                events.append(SequentialEvent(
                    start_index=start_row.index,
                    end_index=row.index,
                    strongest_index=row.index,
                    start_utc=start_row.epoch_utc,
                    end_utc=row.epoch_utc,
                    strongest_utc=row.epoch_utc,
                    trigger_wealth=update.wealth,
                    evidence_updates=update.time_index - start_offset,
                ))
                process.reset()
                segment_rows = []
                refractory = self.refractory_points
        return steps, events


def empirical_exceedance_bound(quiet_cases: Sequence[dict], *, base_score_threshold: float,
                               smoothing: float = 1.0, inflation: float = 1.10,
                               minimum_q0: float = 0.01) -> dict:
    """Conservative empirical q0 heuristic over independent quiet satellites.

    Each satellite receives a smoothed Bernoulli rate `(hits+s)/(n+2s)`. q0 is the maximum
    satellite rate times an inflation factor. This is intentionally *not* a confidence bound and
    carries no theorem-level validity under temporal dependence.
    """
    if smoothing <= 0.0 or inflation < 1.0:
        raise ValueError('smoothing must be positive and inflation must be >= 1')
    per_case = []
    for case in quiet_cases:
        rows = [row for row in case.get('scored_rows', []) if isinstance(row, ScoredRow) and row.status == 'scored']
        hits = sum(
            row.surprise is not None
            and float(row.surprise) >= float(base_score_threshold)
            and row.physical_mode is not None
            for row in rows
        )
        n = len(rows)
        if n == 0:
            continue
        rate = (hits + smoothing) / (n + 2.0 * smoothing)
        per_case.append({'case_id': case.get('case_id'), 'hits': hits, 'updates': n, 'smoothed_rate': rate})
    if not per_case:
        raise ValueError('verified-quiet scored rows are required to estimate q0')
    q0 = max(item['smoothed_rate'] for item in per_case) * inflation
    q0 = min(0.95, max(float(minimum_q0), q0))
    return {
        'q0': q0,
        'base_score_threshold': float(base_score_threshold),
        'smoothing': smoothing,
        'inflation': inflation,
        'method': 'max satellite-level Laplace-smoothed exceedance rate times inflation; empirical only',
        'per_case': per_case,
    }


def geometric_threshold_grid(*, minimum: float = 1.01, maximum: float = 1e8,
                             ratio: float = 1.08) -> list[float]:
    if not 1.0 < minimum <= maximum or ratio <= 1.0:
        raise ValueError('invalid wealth-threshold grid')
    values=[]
    current=float(minimum)
    while current < maximum:
        values.append(current)
        current *= ratio
    values.append(float(maximum))
    return values


def calibrate_operational_threshold(
    quiet_cases: Sequence[dict],
    *,
    base_score_threshold: float,
    q0: float,
    target_false_events_per_object_month: float,
    alternatives: Sequence[float] | None = None,
    refractory_points: int = 2,
    candidate_thresholds: Sequence[float] | None = None,
) -> dict:
    """Empirically choose the least-conservative wealth threshold meeting an event-rate target."""
    target = float(target_false_events_per_object_month)
    if target < 0.0:
        raise ValueError('target false-event rate must be nonnegative')
    exposure_months = sum(float(case.get('span_days') or 0.0) for case in quiet_cases) / OBJECT_MONTH_DAYS
    if exposure_months <= 0.0:
        raise ValueError('positive covered verified-quiet exposure is required')
    candidates = sorted(set(float(value) for value in (candidate_thresholds or geometric_threshold_grid())))
    candidates = [value for value in candidates if isfinite(value) and value > 1.0]
    if not candidates:
        raise ValueError('no valid candidate wealth thresholds')

    evaluations=[]
    for threshold in candidates:
        false_events = 0
        per_case=[]
        for case in quiet_cases:
            layer = SequentialEventLayer(
                base_score_threshold=base_score_threshold,
                q0=q0,
                wealth_threshold=threshold,
                alternatives=alternatives,
                refractory_points=refractory_points,
            )
            _, events = layer.run(case.get('scored_rows', []))
            false_events += len(events)
            per_case.append({'case_id': case.get('case_id'), 'events': len(events)})
        rate = false_events / exposure_months
        evaluations.append({'threshold': threshold, 'false_events': false_events, 'rate': rate, 'per_case': per_case})
    feasible = [item for item in evaluations if item['rate'] <= target]
    if not feasible:
        raise RuntimeError('wealth grid does not contain an operating point meeting the requested empirical rate')
    selected = min(feasible, key=lambda item: item['threshold'])
    return {
        'selected_wealth_threshold': selected['threshold'],
        'implied_alpha_if_formal_assumption_held': 1.0 / selected['threshold'],
        'false_events': selected['false_events'],
        'covered_verified_quiet_object_months': exposure_months,
        'false_events_per_object_month': selected['rate'],
        'target_false_events_per_object_month': target,
        'candidate_count': len(candidates),
        'grid_ratio': None if candidate_thresholds is not None else 1.08,
        'risk_statement': 'empirical event-rate calibration only; theorem-level guarantee requires the conditional Bernoulli bound in formal.py',
    }
