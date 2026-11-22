"""Selective ML v1 research components.

The package is intentionally separate from detector method 0.4 and the public workbench.
"""

from .core import (
    CONTEXT_NAMES,
    FEATURE_NAMES,
    Event,
    ScoredRow,
    SupportModel,
    calibrate_event_threshold,
    group_candidate_events,
    match_events,
    physical_support,
)

__all__ = [
    'CONTEXT_NAMES',
    'FEATURE_NAMES',
    'Event',
    'ScoredRow',
    'SupportModel',
    'calibrate_event_threshold',
    'group_candidate_events',
    'match_events',
    'physical_support',
]
