"""Exact elapsed exposure for the separately versioned retrospective evaluator.

The policy is defined in ELAPSED-EVALUATION.md. Source comparison intervals,
including abstentions, establish the observation schedule. Row fractions and
case spans are never substituted for missing temporal evidence.
"""
from __future__ import annotations

import math
from decimal import Decimal

from research.event_matching import parse_truth_timestamp_us

EXPOSURE_POLICY_VERSION = "elapsed-intervals-v1"
MICROSECONDS_PER_SECOND = 1_000_000
SECONDS_PER_OBJECT_MONTH = 2_629_800
MICROSECONDS_PER_OBJECT_MONTH = SECONDS_PER_OBJECT_MONTH * MICROSECONDS_PER_SECOND
ZERO_EVENT_CONFIDENCE_LEVEL = 0.95
ZERO_EVENT_TAIL_PROBABILITY = 0.05


def _object(value, allowed: set[str], name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    if set(value) - allowed:
        raise ValueError(f"{name} has unsupported fields")
    return value


def _gap_microseconds(value) -> int:
    if type(value) not in (int, float):
        raise ValueError("max_gap_seconds must be a finite positive number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("max_gap_seconds must be a finite positive number")
    decimal = Decimal(str(value))
    if not decimal.is_finite() or decimal <= 0:
        raise ValueError("max_gap_seconds must be a finite positive number")
    numerator, denominator = decimal.as_integer_ratio()
    microseconds, remainder = divmod(numerator * MICROSECONDS_PER_SECOND, denominator)
    if remainder:
        raise ValueError("max_gap_seconds must resolve to whole microseconds")
    return microseconds


def validate_policy(policy) -> dict | None:
    """Validate supplied policy values; return None if required fields are absent."""
    if policy is None:
        return None
    value = _object(policy, {"version", "max_gap_seconds"}, "exposure_policy")
    if "version" in value and value["version"] != EXPOSURE_POLICY_VERSION:
        raise ValueError("Unsupported exposure policy version")
    if "max_gap_seconds" in value:
        _gap_microseconds(value["max_gap_seconds"])
    if "version" not in value or "max_gap_seconds" not in value:
        return None
    gap = value["max_gap_seconds"]
    if isinstance(gap, float) and gap.is_integer():
        gap = int(gap)
    return {"version": EXPOSURE_POLICY_VERSION, "max_gap_seconds": gap}


def _read_evidence(evidence):
    """Validate every present value, retaining incomplete evidence as unknown."""
    if evidence is None:
        return None, None, [], False
    value = _object(
        evidence, {"window_start_utc", "window_end_utc", "intervals"},
        "exposure_evidence",
    )
    start = parse_truth_timestamp_us(value["window_start_utc"]) if "window_start_utc" in value else None
    end = parse_truth_timestamp_us(value["window_end_utc"]) if "window_end_utc" in value else None
    if start is not None and end is not None and end < start:
        raise ValueError("Exposure window ends before it starts")
    complete = start is not None and end is not None and "intervals" in value
    parsed = []
    if "intervals" in value:
        if not isinstance(value["intervals"], list):
            raise ValueError("Exposure intervals must be an array")
        for raw in value["intervals"]:
            item = _object(raw, {"start_utc", "end_utc", "supported"}, "Exposure interval")
            left = parse_truth_timestamp_us(item["start_utc"]) if "start_utc" in item else None
            right = parse_truth_timestamp_us(item["end_utc"]) if "end_utc" in item else None
            if "supported" in item and type(item["supported"]) is not bool:
                raise ValueError("Interval supported must be Boolean")
            if left is not None and right is not None and right <= left:
                raise ValueError("Source intervals must have strictly positive duration")
            if left is None or right is None or "supported" not in item:
                complete = False
            else:
                parsed.append((left, right, item["supported"]))
    return start, end, parsed, complete


def _union(intervals) -> list[list[int]]:
    """Union half-open intervals, including touching intervals, exactly."""
    result = []
    for start, end in sorted(set(intervals)):
        if result and start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return result


def _reject_conflicting_support(supported, abstained) -> None:
    first = second = 0
    while first < len(supported) and second < len(abstained):
        left, right = supported[first], abstained[second]
        if max(left[0], right[0]) < min(left[1], right[1]):
            raise ValueError("Overlapping eligible intervals have contradictory support decisions")
        if left[1] <= right[1]:
            first += 1
        else:
            second += 1


def measure_exposure(evidence, policy) -> dict:
    """Measure eligible, supported and abstained elapsed time without extrapolation.

    Missing evidence returns an unavailable report. Present malformed values
    always raise ValueError, including when other required evidence is missing.
    Unknown interval arrays are None; a known empty union is an empty list.
    """
    canonical_policy = validate_policy(policy)
    start, end, parsed, complete = _read_evidence(evidence)
    window = end - start if start is not None and end is not None else None
    result = {
        "status": "unavailable",
        "reason": None,
        "policy": canonical_policy,
        "window_start_us": start,
        "window_end_us": end,
        "window_microseconds": window,
        "eligible_microseconds": None,
        "covered_microseconds": None,
        "abstained_microseconds": None,
        "unobserved_microseconds": None,
        "covered_object_months": None,
        "eligible_object_months": None,
        "covered_fraction": None,
        "elapsed_abstention_fraction": None,
        "uncovered_window_fraction": None,
        "eligible_intervals_us": None,
        "covered_intervals_us": None,
    }
    supported, abstained = [], []
    if canonical_policy is not None and window is not None:
        maximum_gap = _gap_microseconds(canonical_policy["max_gap_seconds"])
        for left, right, decision in parsed:
            # A large source gap cannot become admissible merely by clipping it.
            if right - left > maximum_gap:
                continue
            clipped = (max(left, start), min(right, end))
            if clipped[0] < clipped[1]:
                (supported if decision else abstained).append(clipped)
        supported, abstained = _union(supported), _union(abstained)
        _reject_conflicting_support(supported, abstained)
    if canonical_policy is None:
        result["reason"] = "missing_policy"
        return result
    if evidence is None:
        result["reason"] = "missing_exposure_evidence"
        return result
    if not complete:
        result["reason"] = "incomplete_exposure_evidence"
        return result
    eligible = _union([tuple(interval) for interval in supported + abstained])
    eligible_duration = sum(right - left for left, right in eligible)
    covered_duration = sum(right - left for left, right in supported)
    abstained_duration = eligible_duration - covered_duration
    result.update({
        "status": "available",
        "eligible_microseconds": eligible_duration,
        "covered_microseconds": covered_duration,
        "abstained_microseconds": abstained_duration,
        "unobserved_microseconds": window - eligible_duration,
        "covered_object_months": covered_duration / MICROSECONDS_PER_OBJECT_MONTH,
        "eligible_object_months": eligible_duration / MICROSECONDS_PER_OBJECT_MONTH,
        "covered_fraction": covered_duration / window if window else None,
        "elapsed_abstention_fraction": abstained_duration / eligible_duration if eligible_duration else None,
        "uncovered_window_fraction": (window - covered_duration) / window if window else None,
        "eligible_intervals_us": eligible,
        "covered_intervals_us": supported,
    })
    return result


def feature_exposure_evidence(window_start_utc, window_end_utc, rows, scores):
    """Adapt explicit feature-pair bounds and this method's aligned decisions.

    A finite numeric score means supported and None means abstained. Missing
    pair bounds make the whole adapter result unavailable. No interval is
    inferred from index, adjacent retained rows, contextual gaps or row counts.
    """
    start = parse_truth_timestamp_us(window_start_utc) if window_start_utc is not None else None
    end = parse_truth_timestamp_us(window_end_utc) if window_end_utc is not None else None
    if start is not None and end is not None and end < start:
        raise ValueError("Exposure window ends before it starts")
    if rows is not None and not isinstance(rows, list):
        raise ValueError("Feature rows must be an array")
    if scores is not None and not isinstance(scores, list):
        raise ValueError("Method scores must be an array")
    decisions = []
    if scores is not None:
        for score in scores:
            if score is None:
                decisions.append(False)
            elif type(score) not in (int, float):
                raise ValueError("Method scores must be finite numbers or None")
            else:
                try:
                    valid = math.isfinite(score)
                except (OverflowError, TypeError, ValueError):
                    valid = False
                if not valid:
                    raise ValueError("Method scores must be finite numbers or None")
                decisions.append(True)
    if rows is not None and scores is not None and len(rows) != len(scores):
        raise ValueError("Feature row/score length mismatch")
    complete = start is not None and end is not None and rows is not None and scores is not None
    intervals = []
    if rows is not None:
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError("Each feature row must be an object")
            epoch = parse_truth_timestamp_us(row["epoch_utc"]) if "epoch_utc" in row else None
            physics = row.get("physics")
            if physics is None:
                complete = False
                continue
            if not isinstance(physics, dict):
                raise ValueError("Feature physics must be an object when supplied")
            left = parse_truth_timestamp_us(physics["before_epoch_utc"]) if "before_epoch_utc" in physics else None
            right = parse_truth_timestamp_us(physics["after_epoch_utc"]) if "after_epoch_utc" in physics else None
            if left is not None and right is not None and right <= left:
                raise ValueError("Feature source intervals must have strictly positive duration")
            if epoch is not None and right is not None and epoch != right:
                raise ValueError("Feature epoch disagrees with its source interval end")
            if left is None or right is None:
                complete = False
                continue
            if scores is not None:
                intervals.append({
                    "start_utc": physics["before_epoch_utc"],
                    "end_utc": physics["after_epoch_utc"],
                    "supported": decisions[index],
                })
    if not complete:
        return None
    return {
        "window_start_utc": window_start_utc,
        "window_end_utc": window_end_utc,
        "intervals": intervals,
    }


def zero_event_poisson_bound(
    count, exposure_object_months, *, exposure_status="available",
    event_support_consistent=True,
) -> dict:
    """Return a labelled conditional 95% upper value only for zero events."""
    if type(count) is not int or count < 0:
        raise ValueError("Event count must be a nonnegative integer")
    if exposure_status not in ("available", "unavailable"):
        raise ValueError("Exposure status must be available or unavailable")
    if type(event_support_consistent) is not bool:
        raise ValueError("Event support consistency must be Boolean")
    exposure = None
    if exposure_object_months is not None:
        if type(exposure_object_months) not in (int, float):
            raise ValueError("Exposure must be a finite nonnegative number or None")
        try:
            exposure = float(exposure_object_months)
        except (OverflowError, ValueError) as exc:
            raise ValueError("Exposure must be a finite nonnegative number or None") from exc
        if not math.isfinite(exposure) or exposure < 0:
            raise ValueError("Exposure must be a finite nonnegative number or None")
    result = {
        "method": "zero-event-homogeneous-poisson-upper",
        "status": None,
        "count": count,
        "exposure_object_months": exposure,
        "confidence_level": ZERO_EVENT_CONFIDENCE_LEVEL,
        "sidedness": "upper-one-sided",
        "upper_events_per_object_month": None,
        "assumptions_verified": False,
        "assumptions": [
            "A homogeneous event rate over the pooled covered exposure.",
            "Independent increments across disjoint covered intervals and objects.",
            "Correctly measured fixed or non-informative exposure.",
            "Observation and support selection do not selectively hide events.",
        ],
        "limitations": (
            "Grouped candidates, adaptive thresholds, clustering, informative "
            "abstention and satellite heterogeneity can violate these assumptions."
        ),
        "interpretation": "Conditional model calculation; not an operational assurance claim.",
    }
    if not event_support_consistent:
        result["status"] = "inconsistent_event_support"
    elif exposure_status == "unavailable" or exposure is None:
        result["status"] = "unavailable_exposure"
    elif exposure == 0:
        result["status"] = "zero_exposure"
    elif count != 0:
        result["status"] = "nonzero_count"
    else:
        upper = -math.log(ZERO_EVENT_TAIL_PROBABILITY) / exposure
        if not math.isfinite(upper):
            result["status"] = "numerically_unavailable"
        else:
            result["status"] = "conditional_model_bound"
            result["upper_events_per_object_month"] = upper
    return result
