#!/usr/bin/env python3
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from research.selective_v1.core import (
    CONTEXT_NAMES,
    FEATURE_NAMES,
    ScoredRow,
    SupportModel,
    context_regime,
    finite_number,
)


@dataclass(frozen=True)
class IntegrityDecision:
    abstain: bool
    primary_reason: str | None
    reasons: tuple[str, ...]
    alerts: tuple[str, ...]


class SelectiveIntegrityGate:
    """Explicit trustworthy-AI abstention policy for public GP histories.

    The gate never uses stress-test labels. It decides only from catalogue/data-quality audit fields,
    causal row contents, independent calibration support and propagation availability.
    """

    def __init__(
        self,
        *,
        support_threshold: float,
        min_resolved_records: int = 12,
        min_evaluated_pairs: int = 5,
        max_rejected_fraction: float = 0.10,
        max_sgp4_failure_fraction: float = 0.25,
        max_excluded_gap_fraction: float = 0.25,
        max_gap_ratio: float = 4.0,
    ) -> None:
        if not math.isfinite(float(support_threshold)) or support_threshold <= 0:
            raise ValueError('support_threshold must be finite and positive')
        for name, value in (
            ('min_resolved_records', min_resolved_records),
            ('min_evaluated_pairs', min_evaluated_pairs),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f'{name} must be a positive integer')
        for name, value in (
            ('max_rejected_fraction', max_rejected_fraction),
            ('max_sgp4_failure_fraction', max_sgp4_failure_fraction),
            ('max_excluded_gap_fraction', max_excluded_gap_fraction),
        ):
            if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f'{name} must be finite and lie in [0,1]')
        if not math.isfinite(float(max_gap_ratio)) or float(max_gap_ratio) < 1.0:
            raise ValueError('max_gap_ratio must be finite and >= 1')
        self.support_threshold = float(support_threshold)
        self.min_resolved_records = int(min_resolved_records)
        self.min_evaluated_pairs = int(min_evaluated_pairs)
        self.max_rejected_fraction = float(max_rejected_fraction)
        self.max_sgp4_failure_fraction = float(max_sgp4_failure_fraction)
        self.max_excluded_gap_fraction = float(max_excluded_gap_fraction)
        self.max_gap_ratio = float(max_gap_ratio)

    @staticmethod
    def _text_errors(case: dict) -> str:
        return ' | '.join(str(item).lower() for item in (case.get('hard_quality_errors') or []))

    def case_decision(self, case: dict) -> IntegrityDecision:
        # JSON inputs can contain non-finite values, strings or fractional counts.
        # NaN comparisons are false, which otherwise silently bypasses the gates;
        # malformed counts would instead raise before an abstention was recorded.
        case = dict(case)
        invalid = False
        for name in (
            'raw_record_count', 'resolved_record_count', 'exact_duplicate_count',
            'conflicting_duplicate_count', 'unresolved_near_simultaneous_count',
            'superseded_count', 'excluded_gap_count', 'sgp4_pair_count',
            'sgp4_failure_count', 'total_evaluated',
        ):
            value = case.get(name, 0)
            number = finite_number(value)
            if isinstance(value, bool) or number is None or number < 0 or not number.is_integer():
                invalid = True
            else:
                case[name] = int(number)
        for name in ('rejected_fraction', 'sgp4_failure_fraction'):
            value = case.get(name)
            number = finite_number(value)
            if isinstance(value, bool) or number is None or not 0.0 <= number <= 1.0:
                invalid = True
            else:
                case[name] = number
        for name in ('median_gap_days', 'maximum_gap_days'):
            value = case.get(name)
            if value is not None:
                number = finite_number(value)
                if isinstance(value, bool) or number is None or number < 0:
                    invalid = True
                else:
                    case[name] = number
        if invalid:
            reason = 'invalid_quality_metadata'
            return IntegrityDecision(True, reason, (reason,), ())
        reasons: list[str] = []
        alerts: list[str] = []
        hard = self._text_errors(case)
        raw = max(0, int(case.get('raw_record_count') or 0))
        resolved = max(0, int(case.get('resolved_record_count') or 0))
        rejected_fraction = float(case.get('rejected_fraction') or 0.0)
        exact_duplicates = int(case.get('exact_duplicate_count') or 0)
        conflicting_duplicates = int(case.get('conflicting_duplicate_count') or 0)
        unresolved = int(case.get('unresolved_near_simultaneous_count') or 0)
        superseded = int(case.get('superseded_count') or 0)
        excluded = int(case.get('excluded_gap_count') or 0)
        sgp4_pairs = int(case.get('sgp4_pair_count') or 0)
        sgp4_failure_fraction = float(case.get('sgp4_failure_fraction') if case.get('sgp4_failure_fraction') is not None else 1.0)
        median_gap = finite_number(case.get('median_gap_days'))
        maximum_gap = finite_number(case.get('maximum_gap_days'))
        object_ids = {str(item) for item in (case.get('object_ids_seen') or []) if str(item).strip()}
        orbit_regimes = {str(item).upper() for item in (case.get('orbit_regimes_seen') or []) if str(item).strip()}
        regime_change = bool(case.get('regime_change_detected')) or len(orbit_regimes) > 1

        if conflicting_duplicates > 0 or unresolved > 0:
            reasons.append('unresolved_catalogue_revision')
        if 'catalog id consistency' in hard or 'catalog identifier' in hard or len(object_ids) > 1 or regime_change:
            reasons.append('catalogue_identity_or_regime_change')
        if rejected_fraction > self.max_rejected_fraction or 'invalid' in hard or 'rejected' in hard:
            reasons.append('missing_or_corrupted_history')
        if resolved < self.min_resolved_records or int(case.get('total_evaluated') or 0) < self.min_evaluated_pairs:
            reasons.append('insufficient_history')
        if (
            str(case.get('detector_mode_used') or '') != 'SGP4 multivariate'
            or sgp4_pairs < self.min_evaluated_pairs
            or sgp4_failure_fraction > self.max_sgp4_failure_fraction
        ):
            reasons.append('poor_propagation')
        gap_fraction = excluded / max(1, resolved - 1)
        if (
            gap_fraction > self.max_excluded_gap_fraction
            or (median_gap is not None and median_gap > 0 and maximum_gap is not None and maximum_gap / median_gap > self.max_gap_ratio)
        ):
            reasons.append('irregular_or_gapped_sampling')
        if str(case.get('quality_status') or '') == 'unusable':
            reasons.append('poor_data_quality')

        if exact_duplicates > 0:
            alerts.append('replay_or_exact_duplicate_detected')
        if superseded > 0:
            alerts.append('catalogue_correction_resolved')
        if 0.0 < rejected_fraction <= self.max_rejected_fraction:
            alerts.append('partial_record_corruption_rejected')
        if raw > resolved and not (exact_duplicates or superseded or rejected_fraction > 0):
            alerts.append('record_count_changed_during_resolution')

        ordered_reasons = tuple(dict.fromkeys(reasons))
        return IntegrityDecision(
            abstain=bool(ordered_reasons),
            primary_reason=ordered_reasons[0] if ordered_reasons else None,
            reasons=ordered_reasons,
            alerts=tuple(dict.fromkeys(alerts)),
        )

    @staticmethod
    def _row_content_reason(row: dict) -> str | None:
        features = row.get('features') or {}
        context = row.get('context') or {}
        if any(finite_number(features.get(name)) is None for name in FEATURE_NAMES):
            return 'missing_feature_data'
        if any(finite_number(context.get(name)) is None for name in CONTEXT_NAMES):
            return 'missing_context_data'
        physics = row.get('physics')
        if not isinstance(physics, dict):
            return 'missing_physics_data'
        integrity = row.get('integrity') or {}
        if not bool(integrity.get('pair_eligible', False)):
            return 'irregular_or_gapped_sampling'
        if not bool(integrity.get('sgp4_residual_available', False)):
            return 'poor_propagation'
        return None

    def score_sequence(self, model, support: SupportModel, case: dict, rows: list[dict]) -> tuple[list[ScoredRow], dict]:
        case_decision = self.case_decision(case)
        counters: Counter[str] = Counter()
        alerts: Counter[str] = Counter(case_decision.alerts)
        if case_decision.abstain:
            counters[case_decision.primary_reason or 'case_integrity_abstention'] += len(rows)
            return [
                ScoredRow(
                    index=int(row.get('index', index)),
                    epoch_utc=str(row.get('epoch_utc', '')),
                    surprise=None,
                    support_distance=None,
                    status='abstain',
                    reason='integrity gate: ' + (case_decision.primary_reason or 'case integrity failure'),
                )
                for index, row in enumerate(rows)
            ], {
                'case_decision': case_decision,
                'reason_counts': dict(counters),
                'alert_counts': dict(alerts),
            }

        qualified_regimes = support.qualified_regimes()
        precheck: list[tuple[str | None, float | None]] = []
        for row in rows:
            reason = self._row_content_reason(row)
            distance: float | None = None
            if reason is None:
                regime = context_regime(row)
                if regime is None or regime not in qualified_regimes:
                    reason = 'insufficient_calibration_support'
                else:
                    distance = support.distance(row, require_qualified_regime=True)
                    if distance is None:
                        reason = 'insufficient_calibration_support'
                    elif distance > self.support_threshold:
                        reason = 'out_of_distribution_object'
            precheck.append((reason, distance))

        # A pre-score integrity/OOD abstention is a temporal trust boundary. Predict only on
        # contiguous trusted segments, so an untrusted row cannot become hidden-state or
        # previous-observation context for a later trusted score.
        predictions = [None] * len(rows)
        cursor = 0
        while cursor < len(rows):
            while cursor < len(rows) and precheck[cursor][0] is not None:
                cursor += 1
            if cursor >= len(rows):
                break
            segment_end = cursor
            while segment_end < len(rows) and precheck[segment_end][0] is None:
                segment_end += 1
            segment_predictions = model.predict_sequence(rows[cursor:segment_end])
            if len(segment_predictions) != segment_end - cursor:
                raise RuntimeError('model returned wrong prediction length')
            predictions[cursor:segment_end] = segment_predictions
            cursor = segment_end

        scored: list[ScoredRow] = []
        for index, row in enumerate(rows):
            row_index = int(row.get('index', index))
            epoch = str(row.get('epoch_utc', ''))
            reason, distance = precheck[index]
            if reason is not None:
                counters[reason] += 1
                scored.append(ScoredRow(
                    row_index,
                    epoch,
                    None,
                    distance,
                    'abstain',
                    reason='integrity gate: ' + reason,
                ))
                continue
            prediction = predictions[index]
            if prediction is None or not math.isfinite(float(prediction.surprise)):
                counters['conditional_distribution_unavailable'] += 1
                scored.append(ScoredRow(
                    row_index,
                    epoch,
                    None,
                    distance,
                    'abstain',
                    reason='integrity gate: conditional_distribution_unavailable',
                ))
                continue
            scored.append(ScoredRow(
                index=row_index,
                epoch_utc=epoch,
                surprise=float(prediction.surprise),
                support_distance=float(distance),
                status='scored',
                z_scores=prediction.z_scores,
            ))
        return scored, {
            'case_decision': case_decision,
            'reason_counts': dict(sorted(counters.items())),
            'alert_counts': dict(sorted(alerts.items())),
        }


def aggregate_reason_counts(items: Iterable[dict]) -> dict[str, int]:
    total: Counter[str] = Counter()
    for item in items:
        total.update(item.get('reason_counts') or {})
    return dict(sorted(total.items()))
