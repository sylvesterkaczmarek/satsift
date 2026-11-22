#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable, Sequence


def bernoulli_likelihood_ratio(x: int | bool, *, q0: float, q1: float) -> float:
    """One-step e-variable for H0: P(X_t=1 | F_{t-1}) <= q0 against q1 > q0."""
    if not 0.0 < q0 < 1.0:
        raise ValueError('q0 must lie in (0,1)')
    if not q0 < q1 < 1.0:
        raise ValueError('q1 must lie in (q0,1)')
    return q1 / q0 if bool(x) else (1.0 - q1) / (1.0 - q0)


def default_alternatives(q0: float) -> tuple[float, ...]:
    if not 0.0 < q0 < 1.0:
        raise ValueError('q0 must lie in (0,1)')
    fractions = (0.10, 0.25, 0.50, 0.75)
    return tuple(min(1.0 - 1e-9, max(q0 + 1e-9, q0 + f * (1.0 - q0))) for f in fractions)


@dataclass(frozen=True)
class EProcessUpdate:
    time_index: int
    indicator: int
    point_e_value: float
    wealth: float
    dominant_start_index: int | None
    dominant_alternative: float | None


class ChangePointMixtureEProcess:
    """Linear-time mixture e-process over unknown change starts and Bernoulli alternatives.

    Under H0(q0): P(X_t=1 | F_{t-1}) <= q0, each fixed-q1 likelihood-ratio factor has
    conditional expectation at most one. For start weights w_s=1/(s(s+1)) and alternative
    weights v_j, define

        A_t,j = sum_{s<=t} w_s prod_{i=s}^t LR_i(q1_j),
        E_t   = 1/(t+1) + sum_j v_j A_t,j.

    The recursion A_t,j = LR_t,j * (A_{t-1,j} + w_t) makes updates O(number of alternatives)
    while preserving the exact start-mixture wealth. E_t is a nonnegative supermartingale under
    the conditional Bernoulli bound, so Ville gives P(sup_t E_t >= 1/alpha) <= alpha.

    The real GP/TLE application does not prove that conditional bound. Formal theorem status and
    empirical event-rate calibration are therefore reported separately throughout the repository.
    """

    def __init__(self, *, q0: float, alternatives: Sequence[float] | None = None,
                 alternative_weights: Sequence[float] | None = None) -> None:
        if not 0.0 < q0 < 1.0:
            raise ValueError('q0 must lie in (0,1)')
        self.q0 = float(q0)
        self.alternatives = tuple(float(value) for value in (alternatives or default_alternatives(q0)))
        if not self.alternatives or any(not self.q0 < value < 1.0 for value in self.alternatives):
            raise ValueError('alternatives must be nonempty and lie in (q0,1)')
        if alternative_weights is None:
            weights = [1.0 / len(self.alternatives)] * len(self.alternatives)
        else:
            weights = [float(value) for value in alternative_weights]
            if len(weights) != len(self.alternatives):
                raise ValueError('alternative_weights must match alternatives')
            if any(value < 0.0 or not isfinite(value) for value in weights) or sum(weights) <= 0.0:
                raise ValueError('alternative_weights must be finite, nonnegative, and have positive mass')
            total = sum(weights)
            weights = [value / total for value in weights]
        self.alternative_weights = tuple(weights)
        self.reset()

    def reset(self) -> None:
        self.time_index = 0
        self._aggregate = [0.0] * len(self.alternatives)
        # Track the largest single start/alternative term only for an interpretable onset estimate.
        self._dominant_value = [0.0] * len(self.alternatives)
        self._dominant_start = [None] * len(self.alternatives)
        self.wealth = 1.0

    @staticmethod
    def start_weight(start_index: int) -> float:
        if start_index < 1:
            raise ValueError('start_index must be >= 1')
        return 1.0 / (start_index * (start_index + 1.0))

    def update(self, indicator: int | bool) -> EProcessUpdate:
        x = 1 if bool(indicator) else 0
        self.time_index += 1
        w_start = self.start_weight(self.time_index)
        factors = [bernoulli_likelihood_ratio(x, q0=self.q0, q1=q1) for q1 in self.alternatives]

        dominant_contribution = -1.0
        dominant_start = None
        dominant_alt = None
        for j, (factor, q1, alt_weight) in enumerate(zip(factors, self.alternatives, self.alternative_weights)):
            self._aggregate[j] = factor * (self._aggregate[j] + w_start)
            continued = factor * self._dominant_value[j]
            fresh = factor * w_start
            if fresh >= continued:
                self._dominant_value[j] = fresh
                self._dominant_start[j] = self.time_index
            else:
                self._dominant_value[j] = continued
            contribution = alt_weight * self._dominant_value[j]
            if contribution > dominant_contribution:
                dominant_contribution = contribution
                dominant_start = self._dominant_start[j]
                dominant_alt = q1

        future_mass = 1.0 / (self.time_index + 1.0)
        self.wealth = future_mass + sum(weight * value for weight, value in zip(self.alternative_weights, self._aggregate))
        point_e = sum(weight * value for weight, value in zip(self.alternative_weights, factors))
        return EProcessUpdate(
            time_index=self.time_index,
            indicator=x,
            point_e_value=float(point_e),
            wealth=float(self.wealth),
            dominant_start_index=dominant_start,
            dominant_alternative=dominant_alt,
        )

    def run(self, indicators: Iterable[int | bool]) -> list[EProcessUpdate]:
        return [self.update(value) for value in indicators]


def alpha_spending_weight(event_index: int) -> float:
    if event_index < 1:
        raise ValueError('event_index must be >= 1')
    from math import pi
    return 6.0 / (pi * pi * event_index * event_index)


def event_wealth_threshold(*, total_type_i_budget: float, event_index: int) -> float:
    """Repeated-event theorem-mode threshold, not the real-data operational interface."""
    if not 0.0 < total_type_i_budget < 1.0:
        raise ValueError('total_type_i_budget must lie in (0,1)')
    alpha_k = total_type_i_budget * alpha_spending_weight(event_index)
    return 1.0 / alpha_k
