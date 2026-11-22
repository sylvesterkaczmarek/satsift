#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict
from typing import Sequence

from .core import ScoredRow, SupportModel, context_regime, group_candidate_events, physical_support

FINAL_MIN_REFERENCE_SATELLITES = 3


class SelectiveDetector:
    """Catalogue-aware selective event detector around a fitted conditional distribution model.

    The object is intentionally architecture-agnostic. The research contribution is the selective
    decision/calibration contract; the fitted backbone only needs `predict_sequence(rows)`.

    Final v1.0 inference requires at least three independent verified-quiet reference satellites in
    an orbit regime. Two satellites cannot support a credible leave-one-satellite-out cross-object
    boundary; such regimes abstain instead of extrapolating.
    """

    def __init__(
        self,
        model,
        support_model: SupportModel,
        *,
        support_thresholds: dict[str, float],
        event_threshold: float,
        physics_z_gate: float = 2.0,
        max_event_gap_points: int = 2,
    ) -> None:
        if support_model.min_reference_satellites < FINAL_MIN_REFERENCE_SATELLITES:
            raise ValueError(
                f'final selective-v1 support requires at least {FINAL_MIN_REFERENCE_SATELLITES} '
                'independent verified-quiet reference satellites per regime'
            )
        self.model = model
        self.support_model = support_model
        self.support_thresholds = {str(key).upper(): float(value) for key, value in support_thresholds.items()}
        self.event_threshold = float(event_threshold)
        self.physics_z_gate = float(physics_z_gate)
        self.max_event_gap_points = int(max_event_gap_points)

    def score_rows(self, rows: Sequence[dict]) -> list[ScoredRow]:
        predictions = self.model.predict_sequence(rows)
        if len(predictions) != len(rows):
            raise RuntimeError('conditional model returned the wrong number of predictions')
        output: list[ScoredRow] = []
        qualified = self.support_model.qualified_regimes()
        for row, prediction in zip(rows, predictions):
            index = int(row.get('index', len(output)))
            epoch = str(row.get('epoch_utc', ''))
            if row.get('quality_ok') is False:
                output.append(ScoredRow(index, epoch, None, None, 'abstain', reason='catalogue/data-quality gate failed'))
                continue
            regime = context_regime(row)
            if regime is None or regime not in qualified or regime not in self.support_thresholds:
                output.append(ScoredRow(index, epoch, None, None, 'abstain', reason=f'unsupported calibration regime: {regime or "unknown"}'))
                continue
            distance = self.support_model.distance(row)
            if distance is None or distance > self.support_thresholds[regime]:
                output.append(ScoredRow(index, epoch, None, distance, 'abstain', reason='outside calibration support'))
                continue
            if prediction is None:
                output.append(ScoredRow(index, epoch, None, distance, 'abstain', reason='conditional distribution unavailable'))
                continue
            mode = physical_support(prediction.z_scores, z_gate=self.physics_z_gate)
            output.append(ScoredRow(
                index=index,
                epoch_utc=epoch,
                surprise=prediction.surprise,
                support_distance=distance,
                status='scored',
                physical_mode=mode,
                z_scores=prediction.z_scores,
            ))
        return output

    def run(self, rows: Sequence[dict]):
        scored = self.score_rows(rows)
        events = group_candidate_events(
            scored,
            threshold=self.event_threshold,
            max_gap_points=self.max_event_gap_points,
            require_physical_support=True,
        )
        return scored, events

    def describe(self) -> dict:
        return {
            'method': 'selective-ml-v1.0',
            'backbone': getattr(self.model, 'name', type(self.model).__name__),
            'parameter_count': int(getattr(self.model, 'parameter_count', 0)),
            'minimum_reference_satellites_per_regime': FINAL_MIN_REFERENCE_SATELLITES,
            'qualified_regimes': sorted(self.support_model.qualified_regimes()),
            'support_thresholds': dict(sorted(self.support_thresholds.items())),
            'event_threshold': self.event_threshold,
            'physics_z_gate': self.physics_z_gate,
            'max_event_gap_points': self.max_event_gap_points,
            'claim': 'empirically risk-calibrated selective screening; no formal risk-control guarantee',
        }


def event_to_dict(event) -> dict:
    return asdict(event)
