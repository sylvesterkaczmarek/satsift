#!/usr/bin/env python3
from __future__ import annotations

from math import sqrt

from .core import PhysicsEstimate, PhysicsNoiseModel
from .inverter import ManeuverPhysicsInverter as _ImpulseInverter


class ManeuverPhysicsInverter(_ImpulseInverter):
    """Physics feasibility screen with an explicit calibrated no-maneuver region.

    A row whose corrected joint element/RTN change lies inside the verified-quiet noise envelope is
    a well-posed monitored non-event, not an underdetermined burn. Only rows outside that envelope
    are sent to the unknown-phase equivalent-impulse inversion. This distinction preserves quiet
    exposure while still returning abstention for genuinely anomalous but non-identifiable changes.
    """

    def __init__(self, noise_model: PhysicsNoiseModel, *, quiet_rms_gate: float = 1.5,
                 quiet_max_z_gate: float = 3.0, **kwargs) -> None:
        super().__init__(noise_model, **kwargs)
        if quiet_rms_gate <= 0.0 or quiet_max_z_gate <= 0.0:
            raise ValueError('quiet-envelope gates must be positive')
        self.quiet_rms_gate = float(quiet_rms_gate)
        self.quiet_max_z_gate = float(quiet_max_z_gate)

    def estimate(self, row: dict) -> PhysicsEstimate:
        corrected = self.noise_model.corrected(row)
        if corrected is None:
            return super().estimate(row)
        standardized = [
            corrected['equi_delta'][index] / corrected['equi_sigma'][index]
            for index in range(len(corrected['equi_delta']))
        ]
        if corrected['rtn_residual_km'] is not None and corrected['rtn_sigma'] is not None:
            standardized.extend(
                corrected['rtn_residual_km'][index] / corrected['rtn_sigma'][index]
                for index in range(3)
            )
        rms = sqrt(sum(value * value for value in standardized) / len(standardized)) if standardized else 0.0
        maximum = max((abs(value) for value in standardized), default=0.0)
        if rms <= self.quiet_rms_gate and maximum <= self.quiet_max_z_gate:
            return PhysicsEstimate(
                status='nominal',
                direction=None,
                delta_v_interval_mps=(0.0, 0.0),
                delta_v_median_mps=0.0,
                component_intervals_mps=None,
                burn_phase_interval=None,
                best_element_rms=rms,
                best_rtn_rms=None,
                best_combined_rms=rms,
                condition_estimate=None,
                candidate_count=0,
                reason='joint change lies inside the cross-satellite verified-quiet physics envelope; no maneuver inversion warranted',
            )
        return super().estimate(row)
