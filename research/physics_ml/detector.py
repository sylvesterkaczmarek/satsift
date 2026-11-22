#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite, log1p, sqrt
from statistics import median
from typing import Iterable

FEATURES = (
    'a_rate',
    'mean_motion_rate',
    'radial_rate',
    'along_rate',
    'cross_rate',
    'eccentricity_vector_rate',
    'inclination_vector_rate',
    'bstar_rate',
)

CONTEXT = (
    'log_gap_days',
    'log_semi_major_axis_km',
    'eccentricity',
    'inclination_sin',
    'log_abs_bstar',
)

STATE_FEATURES = {'radial_rate', 'along_rate', 'cross_rate'}
ELEMENT_FEATURES = {
    'a_rate',
    'mean_motion_rate',
    'eccentricity_vector_rate',
    'inclination_vector_rate',
    'bstar_rate',
}


def _mad(values: list[float], centre: float | None = None) -> float:
    if not values:
        return float('nan')
    if centre is None:
        centre = median(values)
    return median([abs(value - centre) for value in values])


def _robust_scale(values: list[float], floor: float) -> float:
    if not values:
        return floor
    centre = median(values)
    scale = 1.4826 * _mad(values, centre)
    return max(scale if isfinite(scale) else 0.0, floor)


def _finite_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def make_context(*, gap_days: float, semi_major_axis_km: float, eccentricity: float,
                 inclination_deg: float, bstar: float) -> dict[str, float]:
    from math import pi, sin

    return {
        'log_gap_days': log1p(max(0.0, float(gap_days))),
        'log_semi_major_axis_km': log1p(max(0.0, float(semi_major_axis_km))),
        'eccentricity': float(eccentricity),
        'inclination_sin': sin(float(inclination_deg) * pi / 180.0),
        'log_abs_bstar': log1p(abs(float(bstar))),
    }


@dataclass(frozen=True)
class ScoreResult:
    score: float
    z_scores: dict[str, float]
    support_distance: float
    p_value: float | None = None
    e_value: float | None = None


@dataclass(frozen=True)
class Decision:
    index: int
    epoch_utc: str
    status: str
    wealth: float | None
    score: float | None
    p_value: float | None
    support_distance: float | None
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
    max_wealth: float
    max_score: float
    physical_modes: tuple[str, ...]


class ConditionalNominalModel:
    """Robust k-nearest-neighbour nominal model fitted on calibration satellites.

    Calibration rows must be explicitly nominal. Each row contains `context`,
    `features`, and optionally `epoch_utc`/`object_id`. The model never mutates
    its reference set while scoring a test sequence.
    """

    def __init__(self, *, k: int = 25, min_neighbors: int = 12,
                 max_context_distance: float = 8.0,
                 feature_scale_floor: float = 1e-9) -> None:
        if k < 3:
            raise ValueError('k must be at least 3')
        if min_neighbors < 3 or min_neighbors > k:
            raise ValueError('min_neighbors must be between 3 and k')
        self.k = k
        self.min_neighbors = min_neighbors
        self.max_context_distance = float(max_context_distance)
        self.feature_scale_floor = float(feature_scale_floor)
        self.rows: list[dict] = []
        self.context_centres: dict[str, float] = {}
        self.context_scales: dict[str, float] = {}
        self.calibration_scores: list[float] = []

    def fit(self, rows: Iterable[dict]) -> 'ConditionalNominalModel':
        accepted = []
        for row in rows:
            if row.get('nominal') is not True or row.get('quality_ok') is False:
                continue
            context = row.get('context') or {}
            features = row.get('features') or {}
            if not all(_finite_number(context.get(name)) is not None for name in CONTEXT):
                continue
            if not all(_finite_number(features.get(name)) is not None for name in FEATURES):
                continue
            accepted.append(row)
        if len(accepted) < self.min_neighbors + 2:
            raise ValueError('insufficient explicit nominal calibration rows')
        self.rows = accepted

        for name in CONTEXT:
            values = [float(row['context'][name]) for row in self.rows]
            centre = median(values)
            self.context_centres[name] = centre
            self.context_scales[name] = _robust_scale(values, 1e-6)

        cross_fitted = []
        for index, row in enumerate(self.rows):
            result = self._score(row, exclude_index=index, enforce_support=False)
            if result is not None and isfinite(result.score):
                cross_fitted.append(result.score)
        if len(cross_fitted) < self.min_neighbors:
            raise ValueError('insufficient cross-fitted calibration scores')
        self.calibration_scores = sorted(cross_fitted)
        return self

    def _distance(self, context: dict, row: dict) -> float:
        total = 0.0
        for name in CONTEXT:
            value = float(context[name])
            reference = float(row['context'][name])
            scale = self.context_scales[name]
            total += ((value - reference) / scale) ** 2
        return sqrt(total)

    def _neighbors(self, context: dict, *, exclude_index: int | None = None) -> list[tuple[float, dict]]:
        distances = []
        for index, row in enumerate(self.rows):
            if exclude_index is not None and index == exclude_index:
                continue
            distances.append((self._distance(context, row), row))
        distances.sort(key=lambda item: item[0])
        return distances[: self.k]

    def _score(self, row: dict, *, exclude_index: int | None = None,
               enforce_support: bool = True) -> ScoreResult | None:
        context = row.get('context') or {}
        features = row.get('features') or {}
        if not all(_finite_number(context.get(name)) is not None for name in CONTEXT):
            return None
        if not all(_finite_number(features.get(name)) is not None for name in FEATURES):
            return None
        neighbors = self._neighbors(context, exclude_index=exclude_index)
        if len(neighbors) < self.min_neighbors:
            return None
        support_distance = neighbors[min(self.min_neighbors, len(neighbors)) - 1][0]
        if enforce_support and support_distance > self.max_context_distance:
            return None

        z_scores: dict[str, float] = {}
        for name in FEATURES:
            values = [float(item[1]['features'][name]) for item in neighbors]
            centre = median(values)
            scale = _robust_scale(values, self.feature_scale_floor)
            z_scores[name] = abs(float(features[name]) - centre) / scale
        return ScoreResult(score=max(z_scores.values()), z_scores=z_scores, support_distance=support_distance)

    def score(self, row: dict) -> ScoreResult | None:
        if not self.rows:
            raise RuntimeError('fit must be called before score')
        result = self._score(row)
        if result is None:
            return None
        greater_or_equal = sum(value >= result.score for value in self.calibration_scores)
        p_value = (greater_or_equal + 1.0) / (len(self.calibration_scores) + 1.0)
        return ScoreResult(
            score=result.score,
            z_scores=result.z_scores,
            support_distance=result.support_distance,
            p_value=p_value,
        )


def physical_support(z_scores: dict[str, float], *, z_gate: float = 2.0) -> str | None:
    def z(name: str) -> float:
        value = _finite_number(z_scores.get(name))
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


class SequentialRiskDetector:
    """Fixed-reference experimental detector with mixture e-evidence.

    The power betting transform e(p)=epsilon*p**(epsilon-1) has unit mean for
    an exactly uniform p-value. The mixture is meaningful as an anytime-valid
    e-process only when the input p-values satisfy the conditional validity
    assumptions in METHOD.md. The implementation therefore reports the wealth
    but does not claim a formal guarantee merely because the threshold is crossed.
    """

    def __init__(self, model: ConditionalNominalModel, *, alpha_event: float = 0.01,
                 betting_epsilon: float = 0.5, physics_z_gate: float = 2.0,
                 max_event_gap_points: int = 2) -> None:
        if not 0.0 < alpha_event < 1.0:
            raise ValueError('alpha_event must lie in (0,1)')
        if not 0.0 < betting_epsilon < 1.0:
            raise ValueError('betting_epsilon must lie in (0,1)')
        self.model = model
        self.alpha_event = alpha_event
        self.betting_epsilon = betting_epsilon
        self.physics_z_gate = physics_z_gate
        self.max_event_gap_points = max_event_gap_points

    def _e_value(self, p_value: float) -> float:
        p = min(1.0, max(1e-12, p_value))
        eps = self.betting_epsilon
        return eps * (p ** (eps - 1.0))

    def run(self, rows: Iterable[dict]) -> tuple[list[Decision], list[Event]]:
        threshold = 1.0 / self.alpha_event
        components: list[list[float]] = []  # [weight, product]
        cumulative_weight = 0.0
        decisions: list[Decision] = []

        for sequence_index, row in enumerate(rows, start=1):
            index = int(row.get('index', sequence_index - 1))
            epoch = str(row.get('epoch_utc', ''))
            if row.get('quality_ok') is False:
                decisions.append(Decision(index, epoch, 'abstain', None, None, None, None,
                                          reason='baseline quality gate failed'))
                continue

            scored = self.model.score(row)
            if scored is None or scored.p_value is None:
                decisions.append(Decision(index, epoch, 'abstain', None, None, None, None,
                                          reason='insufficient or out-of-support calibration context'))
                continue

            e_value = self._e_value(scored.p_value)
            for component in components:
                component[1] *= e_value
            weight = 1.0 / (sequence_index * (sequence_index + 1.0))
            cumulative_weight += weight
            components.append([weight, e_value])
            unused_weight = max(0.0, 1.0 - cumulative_weight)
            wealth = unused_weight + sum(weight_i * product for weight_i, product in components)
            mode = physical_support(scored.z_scores, z_gate=self.physics_z_gate)

            if wealth >= threshold and mode:
                status = 'candidate'
                reason = None
            elif wealth >= threshold:
                status = 'statistical-alert'
                reason = 'sequential evidence crossed threshold without physical support'
            else:
                status = 'nominal'
                reason = None

            decisions.append(Decision(
                index=index,
                epoch_utc=epoch,
                status=status,
                wealth=wealth,
                score=scored.score,
                p_value=scored.p_value,
                support_distance=scored.support_distance,
                physical_mode=mode,
                reason=reason,
                z_scores=scored.z_scores,
            ))

        return decisions, self._group_events(decisions)

    def _group_events(self, decisions: list[Decision]) -> list[Event]:
        candidates = [decision for decision in decisions if decision.status == 'candidate']
        if not candidates:
            return []
        groups: list[list[Decision]] = []
        for decision in candidates:
            if not groups or decision.index - groups[-1][-1].index > self.max_event_gap_points:
                groups.append([decision])
            else:
                groups[-1].append(decision)

        events = []
        for group in groups:
            strongest = max(group, key=lambda item: (item.wealth or 0.0, item.score or 0.0))
            modes = tuple(sorted({item.physical_mode for item in group if item.physical_mode}))
            events.append(Event(
                start_index=group[0].index,
                end_index=group[-1].index,
                strongest_index=strongest.index,
                start_utc=group[0].epoch_utc,
                end_utc=group[-1].epoch_utc,
                strongest_utc=strongest.epoch_utc,
                max_wealth=max(item.wealth or 0.0 for item in group),
                max_score=max(item.score or 0.0 for item in group),
                physical_modes=modes,
            ))
        return events
