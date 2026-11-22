#!/usr/bin/env python3
from __future__ import annotations

from math import isfinite

from detector import ConditionalNominalModel

# Minimum context scales encode within-regime variation that a single quiet
# calibration spacecraft cannot estimate from its own short time series. They
# are deliberately broad and are defined before the next held-out evaluation.
CONTEXT_SCALE_FLOORS = {
    'log_gap_days': 0.50,
    'log_semi_major_axis_km': 0.10,
    'eccentricity': 0.01,
    'inclination_sin': 0.25,
    'log_abs_bstar': 0.001,
}


class RegimeNominalModel(ConditionalNominalModel):
    """Conditional nominal model with non-degenerate physical context scales.

    The base estimator learns robust context scales from the explicit quiet
    calibration rows. A short history from one spacecraft can have essentially
    zero inclination/eccentricity variation, which must not imply that every
    other spacecraft in the same orbit regime is out of support. This class
    clamps each context dimension to a documented physical minimum and then
    recomputes leave-one-out calibration scores under those same scales.
    """

    def fit(self, rows):
        super().fit(rows)
        for name, floor in CONTEXT_SCALE_FLOORS.items():
            current = self.context_scales.get(name, 0.0)
            self.context_scales[name] = max(current if isfinite(current) else 0.0, floor)

        cross_fitted = []
        for index, row in enumerate(self.rows):
            result = self._score(row, exclude_index=index, enforce_support=False)
            if result is not None and isfinite(result.score):
                cross_fitted.append(result.score)
        if len(cross_fitted) < self.min_neighbors:
            raise ValueError('insufficient cross-fitted calibration scores after context-scale clamping')
        self.calibration_scores = sorted(cross_fitted)
        return self
