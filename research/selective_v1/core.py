#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite, log1p, sqrt
from statistics import median
from typing import Iterable, Sequence

from research.event_matching import match_event_intervals, parse_time_us, parse_truth_events_us, tolerance_hours_to_us

FEATURE_NAMES = (
    'a_rate',
    'mean_motion_rate',
    'radial_rate',
    'along_rate',
    'cross_rate',
    'eccentricity_vector_rate',
    'inclination_vector_rate',
    'bstar_rate',
)

# All context channels are causal and available at the evaluated record. Orbit is one-hot rather than
# inferred from labels. Catalogue fields describe provenance/quality, not maneuver truth.
CONTEXT_NAMES = (
    'log_gap_days',
    'log_semi_major_axis_km',
    'eccentricity',
    'inclination_sin',
    'log_abs_bstar',
    'log_creation_lag_hours',
    'object_age_log_days',
    'rcs_scale',
    'element_set_known',
    'gp_id_known',
    'catalogue_superseded_fraction',
    'epoch_precision_digits_scaled',
    'orbit_leo',
    'orbit_meo',
    'orbit_geo',
    'orbit_heo',
)

STATE_FEATURES = {'radial_rate', 'along_rate', 'cross_rate'}
ELEMENT_FEATURES = {
    'a_rate',
    'mean_motion_rate',
    'eccentricity_vector_rate',
    'inclination_vector_rate',
    'bstar_rate',
}


def finite_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def mad(values: Sequence[float], centre: float | None = None) -> float:
    if not values:
        return float('nan')
    c = median(values) if centre is None else float(centre)
    return median([abs(float(value) - c) for value in values])


def robust_scale(values: Sequence[float], floor: float = 1e-8) -> float:
    if not values:
        return float(floor)
    centre = median(values)
    scale = 1.4826 * mad(values, centre)
    return max(float(floor), scale if isfinite(scale) else 0.0)


def quantile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError('quantile requires at least one value')
    if not 0.0 <= q <= 1.0:
        raise ValueError('q must lie in [0,1]')
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * q
    lo = int(position)
    hi = min(len(ordered) - 1, lo + 1)
    weight = position - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def parse_time(value: str) -> float:
    """Interpret offset-free GP/event timestamps as UTC, never host local time."""
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def context_regime(row: dict) -> str | None:
    context = row.get('context') or {}
    channels = {
        'LEO': finite_number(context.get('orbit_leo')) or 0.0,
        'MEO': finite_number(context.get('orbit_meo')) or 0.0,
        'GEO': finite_number(context.get('orbit_geo')) or 0.0,
        'HEO': finite_number(context.get('orbit_heo')) or 0.0,
    }
    regime, value = max(channels.items(), key=lambda item: item[1])
    return regime if value >= 0.5 else None


@dataclass(frozen=True)
class DistributionPrediction:
    location: dict[str, float]
    scale: dict[str, float]
    z_scores: dict[str, float]
    surprise: float


@dataclass(frozen=True)
class ScoredRow:
    index: int
    epoch_utc: str
    surprise: float | None
    support_distance: float | None
    status: str
    physical_mode: str | None = None
    reason: str | None = None
    z_scores: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Event:
    start_index: int
    end_index: int
    strongest_index: int
    start_utc: str
    end_utc: str
    strongest_utc: str
    max_surprise: float
    physical_modes: tuple[str, ...]


class SupportModel:
    """Robust same-regime k-neighbour calibration-support model over causal context channels.

    The support model is deliberately independent of the ML backbone. Context channels are robustly
    standardized on explicit verified-quiet reference rows. A scored row is compared only with
    reference rows from the same orbit regime. `qualified_regimes()` additionally requires a minimum
    number of independent reference satellites, preventing hundreds of rows from one spacecraft from
    masquerading as cross-satellite support.
    """

    def __init__(self, *, k: int = 5, min_reference_satellites: int = 2) -> None:
        if k < 1:
            raise ValueError('k must be positive')
        if min_reference_satellites < 1:
            raise ValueError('min_reference_satellites must be positive')
        self.k = int(k)
        self.min_reference_satellites = int(min_reference_satellites)
        self.rows: list[dict] = []
        self.centres: dict[str, float] = {}
        self.scales: dict[str, float] = {}

    def fit(self, rows: Iterable[dict]) -> 'SupportModel':
        accepted = []
        for row in rows:
            object_id = row.get('object_id')
            if (
                row.get('nominal') is not True or row.get('quality_ok') is False
                or not isinstance(object_id, (str, int)) or isinstance(object_id, bool)
                or not str(object_id).strip()
            ):
                continue
            context = row.get('context') or {}
            if context_regime(row) is None:
                continue
            if all(finite_number(context.get(name)) is not None for name in CONTEXT_NAMES):
                accepted.append(row)
        if len(accepted) < self.k + 1:
            raise ValueError('insufficient rows for support model')
        self.rows = accepted
        for name in CONTEXT_NAMES:
            values = [float(row['context'][name]) for row in accepted]
            self.centres[name] = median(values)
            self.scales[name] = robust_scale(values, 1e-6)
        return self

    def reference_satellites(self, regime: str) -> set[str]:
        key = str(regime).upper()
        return {
            str(row.get('object_id'))
            for row in self.rows
            if context_regime(row) == key and str(row.get('object_id', '')).strip()
        }

    def qualified_regimes(self) -> set[str]:
        return {
            regime for regime in ('LEO', 'MEO', 'GEO', 'HEO')
            if len(self.reference_satellites(regime)) >= self.min_reference_satellites
        }

    def vector(self, row: dict) -> list[float] | None:
        context = row.get('context') or {}
        values: list[float] = []
        for name in CONTEXT_NAMES:
            number = finite_number(context.get(name))
            if number is None:
                return None
            values.append((number - self.centres[name]) / self.scales[name])
        return values

    def distance(self, row: dict, *, exclude_object_id: str | None = None,
                 require_qualified_regime: bool = True) -> float | None:
        vector = self.vector(row)
        regime = context_regime(row)
        if vector is None or regime is None:
            return None
        eligible = [
            reference for reference in self.rows
            if context_regime(reference) == regime
            and (exclude_object_id is None or str(reference.get('object_id')) != str(exclude_object_id))
        ]
        unique_objects = {str(reference.get('object_id')) for reference in eligible if str(reference.get('object_id', '')).strip()}
        if require_qualified_regime and len(unique_objects) < self.min_reference_satellites:
            return None
        distances: list[float] = []
        for reference in eligible:
            ref_vector = self.vector(reference)
            if ref_vector is None:
                continue
            distances.append(sqrt(sum((a - b) ** 2 for a, b in zip(vector, ref_vector))))
        if len(distances) < self.k:
            return None
        distances.sort()
        return distances[self.k - 1]


def calibrate_support_threshold(distances: Sequence[float], *, coverage: float = 0.98) -> float:
    usable = [float(value) for value in distances if isfinite(float(value))]
    if not usable:
        raise ValueError('no finite support distances to calibrate')
    # Small calibration sets should not extrapolate beyond observed support. A 2% numerical margin
    # prevents equal-distance floating-point noise from becoming an abstention.
    return quantile(usable, coverage) * 1.02 + 1e-9


def student_t_surprise(
    features: dict[str, float],
    location: dict[str, float],
    scale: dict[str, float],
    *,
    degrees_of_freedom: float = 4.0,
) -> DistributionPrediction:
    """Heavy-tail robust nonconformity from a conditional location/scale prediction.

    This is a Student-t-shaped empirical score, not a calibrated probability. The final event
    threshold is calibrated on verified-quiet satellites. Fixed low degrees of freedom prevents a
    few large public-GP residuals from dominating model fitting/selection as a Gaussian objective
    would.
    """
    if degrees_of_freedom <= 2.0:
        raise ValueError('degrees_of_freedom must exceed 2')
    z_scores: dict[str, float] = {}
    terms: list[float] = []
    for name in FEATURE_NAMES:
        value = finite_number(features.get(name))
        mu = finite_number(location.get(name))
        sigma = finite_number(scale.get(name))
        if value is None or mu is None or sigma is None or sigma <= 0.0:
            raise ValueError(f'invalid distribution prediction for {name}')
        z = (value - mu) / sigma
        z_scores[name] = abs(z)
        terms.append(0.5 * (degrees_of_freedom + 1.0) * log1p((z * z) / degrees_of_freedom))
    return DistributionPrediction(
        location={name: float(location[name]) for name in FEATURE_NAMES},
        scale={name: float(scale[name]) for name in FEATURE_NAMES},
        z_scores=z_scores,
        surprise=sum(terms) / len(terms),
    )


def physical_support(z_scores: dict[str, float], *, z_gate: float = 2.0) -> str | None:
    """Transparent maneuver-consistency check retained as an interpretability constraint.

    This is not inverse maneuver reconstruction and is not claimed as the research novelty.
    """
    def z(name: str) -> float:
        value = finite_number(z_scores.get(name))
        return value if value is not None else 0.0

    half = 0.5 * z_gate
    if z('along_rate') >= z_gate and max(z('a_rate'), z('mean_motion_rate')) >= half:
        return 'along-track'
    if z('radial_rate') >= z_gate and z('eccentricity_vector_rate') >= half:
        return 'radial'
    if z('cross_rate') >= z_gate and z('inclination_vector_rate') >= half:
        return 'cross-track'
    state_hits = sum(z(name) >= z_gate for name in STATE_FEATURES)
    element_hits = sum(z(name) >= z_gate for name in ELEMENT_FEATURES)
    if state_hits >= 1 and element_hits >= 1:
        return 'mixed-physical-support'
    return None


def group_candidate_events(
    rows: Sequence[ScoredRow],
    *,
    threshold: float,
    max_gap_points: int = 2,
    require_physical_support: bool = True,
) -> list[Event]:
    candidates = [
        row for row in rows
        if row.status == 'scored'
        and row.surprise is not None
        and row.surprise >= threshold
        and (row.physical_mode is not None or not require_physical_support)
    ]
    if not candidates:
        return []
    groups: list[list[ScoredRow]] = []
    for row in candidates:
        if not groups or row.index - groups[-1][-1].index > max_gap_points:
            groups.append([row])
        else:
            groups[-1].append(row)
    result: list[Event] = []
    for group in groups:
        strongest = max(group, key=lambda item: float(item.surprise or 0.0))
        result.append(Event(
            start_index=group[0].index,
            end_index=group[-1].index,
            strongest_index=strongest.index,
            start_utc=group[0].epoch_utc,
            end_utc=group[-1].epoch_utc,
            strongest_utc=strongest.epoch_utc,
            max_surprise=max(float(row.surprise or 0.0) for row in group),
            physical_modes=tuple(sorted({row.physical_mode for row in group if row.physical_mode})),
        ))
    return result


def match_events(predicted: Sequence[Event], truth: Sequence[dict], tolerance_hours: float = 24.0) -> dict:
    pairs = match_event_intervals(
        [(
            parse_time_us(prediction.start_utc),
            parse_time_us(prediction.end_utc),
            parse_time_us(prediction.strongest_utc),
        ) for prediction in predicted],
        parse_truth_events_us(truth),
        tolerance_hours_to_us(tolerance_hours),
    )
    matches = [{key: pair[key] for key in ('prediction_index', 'truth_index', 'delay_hours', 'strongest_point_delay_hours')} for pair in pairs]
    return {'matches': matches, 'tp': len(matches), 'fn': len(truth) - len(matches)}


def _quiet_object_months(cases: Sequence[dict]) -> float:
    total_days = sum(float(case.get('span_days') or 0.0) for case in cases)
    return total_days / 30.4375


def calibrate_event_threshold(
    quiet_cases: Sequence[dict],
    *,
    false_events_per_object_month_budget: float = 1.0,
    max_gap_points: int = 2,
    require_physical_support: bool = True,
) -> dict:
    """Choose the least-conservative event threshold meeting an empirical quiet-exposure budget.

    Each item must contain `scored_rows` and `span_days`. This is empirical risk calibration only;
    no formal finite-sample or anytime guarantee is claimed.
    """
    if false_events_per_object_month_budget < 0.0:
        raise ValueError('risk budget must be non-negative')
    object_months = _quiet_object_months(quiet_cases)
    if object_months <= 0.0:
        raise ValueError('verified-quiet exposure is required for event calibration')
    scores = sorted({
        float(row.surprise)
        for case in quiet_cases
        for row in case.get('scored_rows', [])
        if isinstance(row, ScoredRow) and row.status == 'scored' and row.surprise is not None
    })
    if not scores:
        raise ValueError('no scorable verified-quiet rows')

    candidates = [float('inf')] + list(reversed(scores))
    feasible: list[dict] = []
    all_results: list[dict] = []
    for threshold in candidates:
        false_events = 0
        for case in quiet_cases:
            false_events += len(group_candidate_events(
                case.get('scored_rows', []), threshold=threshold,
                max_gap_points=max_gap_points,
                require_physical_support=require_physical_support,
            ))
        rate = false_events / object_months
        item = {'threshold': threshold, 'false_events': false_events, 'false_events_per_object_month': rate}
        all_results.append(item)
        if rate <= false_events_per_object_month_budget:
            feasible.append(item)
    # The least-conservative threshold is the smallest numeric threshold among feasible choices.
    selected = min(feasible, key=lambda item: item['threshold']) if feasible else all_results[0]
    return {
        'selected_threshold': selected['threshold'],
        'false_events': selected['false_events'],
        'verified_quiet_object_months': object_months,
        'false_events_per_object_month': selected['false_events_per_object_month'],
        'budget': false_events_per_object_month_budget,
        'candidate_count': len(candidates),
    }
