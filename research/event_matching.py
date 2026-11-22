"""Deterministic maximum-cardinality, minimum-distance event assignment.

Times are integral UTC microseconds. Eligible prediction intervals overlap a
truth interval expanded by an inclusive tolerance. Pairing maximises the number
of matches, then minimises total strongest-point distance to truth midpoints.
Canonical temporal ordering and stable shortest-path ties resolve equal costs.
Historical evaluators retain their archived implementation.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from heapq import heappop, heappush
from typing import Sequence

EVENT_MATCHING_VERSION = 'event-matching-v3'
MICROSECONDS_PER_HOUR = 3_600_000_000


def parse_time_us(value: str, *, default_timezone=timezone.utc) -> int:
    """Preserve ISO microseconds without passing through a float timestamp.

    A caller may retain its existing local-time treatment of naive timestamps
    with default_timezone=None. Timestamp admission is handled by input parsers.
    """
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None and default_timezone is not None:
        parsed = parsed.replace(tzinfo=default_timezone)
    delta = parsed.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


TRUTH_TIMESTAMP_PATTERN = re.compile(
    r'([0-9]{4})-([0-9]{2})-([0-9]{2})T'
    r'([0-9]{2}):([0-9]{2}):([0-9]{2})'
    r'(?:\.([0-9]{1,6}))?(Z|[+-][0-9]{2}:[0-9]{2})'
)


def parse_truth_timestamp_us(value: str) -> int:
    """Parse the shared explicit-zone truth format as exact UTC microseconds."""
    if not isinstance(value, str):
        raise ValueError('Truth timestamp must be a string')
    match = TRUTH_TIMESTAMP_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError('Truth timestamp must use YYYY-MM-DDTHH:mm:ss[.ffffff] with Z or an explicit +/-HH:mm offset')
    year, month, day, hour, minute, second = (int(match[index]) for index in range(1, 7))
    fraction = match[7] or ''
    microsecond = int(fraction.ljust(6, '0')) if fraction else 0
    zone = match[8]
    offset_minutes = 0
    if zone != 'Z':
        offset_hours, minutes = int(zone[1:3]), int(zone[4:6])
        if offset_hours > 23 or minutes > 59:
            raise ValueError('Truth timestamp has an invalid UTC offset')
        offset_minutes = (offset_hours * 60 + minutes) * (-1 if zone[0] == '-' else 1)
    try:
        local = datetime(
            year, month, day, hour, minute, second, microsecond,
            tzinfo=timezone(timedelta(minutes=offset_minutes)),
        )
        utc = local.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError('Truth timestamp has an invalid calendar, time or UTC year') from exc
    elapsed = utc - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (elapsed.days * 86_400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds


def parse_truth_interval_us(
    event: dict, *, start_key: str = 'start', end_key: str = 'end',
) -> tuple[int, int]:
    """A genuinely omitted end denotes a point; supplied invalid ends fail."""
    if not isinstance(event, dict):
        raise ValueError('Each truth event must be an object')
    if start_key not in event:
        raise ValueError('Truth event is missing its start timestamp')
    start = parse_truth_timestamp_us(event[start_key])
    end = parse_truth_timestamp_us(event[end_key]) if end_key in event else start
    if end < start:
        raise ValueError('Truth event ends before it starts')
    return start, end


def parse_truth_events_us(events: list[dict], *, allow_utc_aliases: bool = False) -> list[tuple[int, int]]:
    """Validate every supplied truth event, even when no predictions exist."""
    if not isinstance(events, list):
        raise ValueError('truth_events must be an array when supplied')
    intervals = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('Each truth event must be an object')
        if allow_utc_aliases:
            for canonical, alias in (('start', 'start_utc'), ('end', 'end_utc')):
                if canonical in event and alias in event:
                    if parse_truth_timestamp_us(event[canonical]) != parse_truth_timestamp_us(event[alias]):
                        raise ValueError('Canonical and legacy truth timestamps disagree')
        start_key = 'start_utc' if allow_utc_aliases and 'start_utc' in event else 'start'
        end_key = 'end_utc' if allow_utc_aliases and 'end_utc' in event else 'end'
        intervals.append(parse_truth_interval_us(event, start_key=start_key, end_key=end_key))
    return intervals


def validated_truth_events(case: dict, *, allow_utc_aliases: bool = False) -> list[dict]:
    """Return case truth after strict array, calendar and interval validation."""
    if not isinstance(case, dict):
        raise ValueError('Each benchmark case must be an object')
    events = case['truth_events'] if 'truth_events' in case else []
    parse_truth_events_us(events, allow_utc_aliases=allow_utc_aliases)
    return events


def tolerance_hours_to_us(hours) -> int:
    """Floor a finite nonnegative decimal tolerance onto the microsecond grid."""
    try:
        value = Decimal(str(hours))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Matching tolerance must be finite and nonnegative') from exc
    if not value.is_finite() or value < 0:
        raise ValueError('Matching tolerance must be finite and nonnegative')
    numerator, denominator = value.as_integer_ratio()
    return numerator * MICROSECONDS_PER_HOUR // denominator


def match_event_intervals(
    predicted: Sequence[tuple[int, int, int]],
    truth: Sequence[tuple[int, int]],
    tolerance_us: int,
) -> list[dict]:
    """Return canonical pairs with original input indices and onset delays.

    Prediction keys are (start, end, strongest); truth keys are (start, end).
    Original indices break ties only for temporally indistinguishable events.
    Residual nodes are source, sorted predictions, sorted truths, then sink.
    Dijkstra visits the lowest node ID on equal distances, retains the first
    equal-cost predecessor, and updates potentials after all reachable nodes.
    Costs are twice the distance in microseconds, so half-microsecond truth
    midpoints and large UTC epochs require neither rounding nor float epsilon.
    """
    if type(tolerance_us) is not int or tolerance_us < 0:
        raise ValueError('Matching tolerance must be a nonnegative integer')
    for events, width in ((predicted, 3), (truth, 2)):
        for event in events:
            if len(event) != width or any(type(value) is not int for value in event):
                raise ValueError('Event times must be integer microseconds')
            if event[0] > event[1]:
                raise ValueError('Event end precedes its start')
    predictions = sorted(enumerate(predicted), key=lambda item: (*item[1], item[0]))
    targets = sorted(enumerate(truth), key=lambda item: (*item[1], item[0]))
    prediction_count, truth_count = len(predictions), len(targets)
    if not prediction_count or not truth_count:
        return []
    source = 0
    truth_offset = 1 + prediction_count
    sink = truth_offset + truth_count
    graph = [[] for _ in range(sink + 1)]

    def add_edge(start, end, cost):
        forward = [end, len(graph[end]), 1, cost]
        reverse = [start, len(graph[start]), 0, -cost]
        graph[start].append(forward)
        graph[end].append(reverse)
        return forward

    for prediction_rank in range(prediction_count):
        add_edge(source, 1 + prediction_rank, 0)
    pair_edges = []
    for prediction_rank, (_, prediction) in enumerate(predictions):
        start, end, strongest = prediction
        for truth_rank, (_, target) in enumerate(targets):
            truth_start, truth_end = target
            if end < truth_start - tolerance_us or start > truth_end + tolerance_us:
                continue
            cost = abs(2 * strongest - truth_start - truth_end)
            edge = add_edge(1 + prediction_rank, truth_offset + truth_rank, cost)
            pair_edges.append((prediction_rank, truth_rank, edge))
    for truth_rank in range(truth_count):
        add_edge(truth_offset + truth_rank, sink, 0)

    potentials = [0] * len(graph)
    while True:
        distances = [None] * len(graph)
        previous = [None] * len(graph)
        distances[source] = 0
        queue = [(0, source)]
        while queue:
            distance, node = heappop(queue)
            if distance != distances[node]:
                continue
            for edge_index, edge in enumerate(graph[node]):
                destination, _, capacity, cost = edge
                if not capacity:
                    continue
                candidate = distance + cost + potentials[node] - potentials[destination]
                if distances[destination] is None or candidate < distances[destination]:
                    distances[destination] = candidate
                    previous[destination] = (node, edge_index)
                    heappush(queue, (candidate, destination))
        if distances[sink] is None:
            break
        for node, distance in enumerate(distances):
            if distance is not None:
                potentials[node] += distance
        node = sink
        while node != source:
            previous_node, edge_index = previous[node]
            edge = graph[previous_node][edge_index]
            edge[2] = 0
            graph[node][edge[1]][2] = 1
            node = previous_node

    matches = []
    for prediction_rank, truth_rank, edge in pair_edges:
        if edge[2]:
            continue
        prediction_index, prediction = predictions[prediction_rank]
        truth_index, target = targets[truth_rank]
        matches.append({
            'prediction_index': prediction_index,
            'truth_index': truth_index,
            'distance_twice_us': edge[3],
            'delay_hours': (prediction[0] - target[0]) / MICROSECONDS_PER_HOUR,
            'strongest_point_delay_hours': (prediction[2] - target[0]) / MICROSECONDS_PER_HOUR,
        })
    return matches
