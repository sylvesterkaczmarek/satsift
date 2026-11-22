#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import time
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

from research.evaluation_version import EVALUATION_VERSION
from research.event_matching import (
    EVENT_MATCHING_VERSION,
    match_event_intervals,
    parse_time_us,
    parse_truth_events_us,
    validated_truth_events,
    tolerance_hours_to_us,
)

from research.selective_v1.core import (
    CONTEXT_NAMES,
    FEATURE_NAMES,
    SupportModel,
    parse_time,
    robust_scale,
)
from research.selective_v1.models import RobustConditionalLinear, TorchStudentTModel, make_candidate
from research.selective_v1.train_compare import (
    apply_support_threshold,
    grouped_rows,
    load_document,
    raw_score_sequence,
    rows_for_cases,
    sequences,
)
from research.physics_v1.core import PhysicsNoiseModel
from research.physics_v1.screen import ManeuverPhysicsInverter
from research.physics_v1.run_development import (
    SEQUENTIAL_BASE_THRESHOLD,
    SEQUENTIAL_FINAL_SUPPORT_THRESHOLD,
    physics_rows,
)
from research.sequential_v1.operational import SequentialEventLayer

SEED = 3404
MATCH_TOLERANCE_HOURS = 24.0
RISK_BUDGET = 1.0
MAX_GAP_POINTS = 2
BOOTSTRAP_ITERATIONS = 1000
PHYSICS_Q0 = 0.24444444444444446
PHYSICS_FINAL_WEALTH_THRESHOLD = 1.01
NEURAL_EPOCHS = 120
AUTOENCODER_WINDOW = 8
PF_PARTICLES = 256

METHOD_ORDER = (
    'detector-0.4',
    'mean-motion-threshold',
    'sma-window-shift',
    'sgp4-rtn-consistency',
    'multi-element-mad',
    'robust-mahalanobis',
    'robust-cusum',
    'kalman-nis',
    'shorten-op-pf-surrogate',
    'robust-linear',
    'lstm',
    'gru',
    'tcn',
    'transformer',
    'sequential-autoencoder',
    'physics-ml-v1.0',
)

ELEMENT_FEATURES = (
    'a_rate',
    'mean_motion_rate',
    'eccentricity_vector_rate',
    'inclination_vector_rate',
    'bstar_rate',
)
RTN_FEATURES = ('radial_rate', 'along_rate', 'cross_rate')
ORBIT_REGIMES = ('LEO', 'MEO', 'GEO', 'HEO', 'IGSO')


def _require_numpy():
    if np is None:
        raise RuntimeError('NumPy is required for comparison-v1 numerical baselines')
    return np


def finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def median(values, default=0.0):
    values = [float(v) for v in values if finite(v) is not None]
    return statistics.median(values) if values else float(default)


def safe_scale(values, floor=1e-9):
    material = [float(v) for v in values if finite(v) is not None]
    return max(float(floor), robust_scale(material, float(floor))) if material else float(floor)


def quiet_ids(cases, split):
    return sorted(
        case_id for case_id, case in cases.items()
        if case.get('split') == split and case.get('label_status') == 'verified-quiet'
    )


def event_ids(cases, split):
    return sorted(
        case_id for case_id, case in cases.items()
        if case.get('split') == split and case.get('label_status') == 'event-evidence'
    )


def normalize_regime(case):
    return str(case.get('orbit_regime') or case.get('orbit_profile') or 'UNKNOWN').upper()


def score_coverage(scores):
    if not scores:
        return 0.0
    return sum(value is not None and finite(value) is not None for value in scores) / len(scores)


def event_dict(start_row, end_row, strongest_row, score):
    return {
        'start_index': int(start_row['index']),
        'end_index': int(end_row['index']),
        'strongest_index': int(strongest_row['index']),
        'start_utc': str(start_row['epoch_utc']),
        'end_utc': str(end_row['epoch_utc']),
        'strongest_utc': str(strongest_row['epoch_utc']),
        'score': float(score),
    }


def events_from_scores(rows, scores, threshold, max_gap_points=MAX_GAP_POINTS):
    if len(rows) != len(scores):
        raise ValueError('row/score length mismatch')
    if threshold is None or not math.isfinite(float(threshold)):
        return []
    groups = []
    current = []
    last_candidate_index = None
    for row, score in zip(rows, scores):
        if score is None or finite(score) is None:
            if current:
                groups.append(current)
                current = []
            last_candidate_index = None
            continue
        if float(score) < float(threshold):
            continue
        index = int(row['index'])
        if not current or last_candidate_index is None or index - last_candidate_index > max_gap_points:
            if current:
                groups.append(current)
            current = [(row, float(score))]
        else:
            current.append((row, float(score)))
        last_candidate_index = index
    if current:
        groups.append(current)
    output = []
    for group in groups:
        strongest_row, strongest_score = max(group, key=lambda item: item[1])
        output.append(event_dict(group[0][0], group[-1][0], strongest_row, strongest_score))
    return output


def match_event_dicts(predicted, truth, tolerance_hours=MATCH_TOLERANCE_HOURS):
    pairs = match_event_intervals(
        [(
            parse_time_us(prediction['start_utc']),
            parse_time_us(prediction['end_utc']),
            parse_time_us(prediction['strongest_utc']),
        ) for prediction in predicted],
        parse_truth_events_us(truth),
        tolerance_hours_to_us(tolerance_hours),
    )
    matches = [{key: pair[key] for key in ('prediction_index', 'truth_index', 'delay_hours', 'strongest_point_delay_hours')} for pair in pairs]
    return {
        'matches': matches,
        'tp': len(matches),
        'fn': len(truth) - len(matches),
        'unmatched_predictions': len(predicted) - len(matches),
    }

def calibrate_threshold(cases, rows_by_case, scores_by_case, quiet_case_ids, budget=RISK_BUDGET):
    score_values = sorted({
        float(score)
        for case_id in quiet_case_ids
        for score in scores_by_case.get(case_id, [])
        if score is not None and finite(score) is not None
    })
    exposure = 0.0
    for case_id in quiet_case_ids:
        coverage = score_coverage(scores_by_case.get(case_id, []))
        exposure += float(cases[case_id].get('span_days') or 0.0) * coverage / 30.4375
    if exposure <= 0.0 or not score_values:
        return {
            'selected_threshold': None,
            'false_events': None,
            'covered_verified_quiet_object_months': exposure,
            'false_events_per_object_month': None,
            'target_false_events_per_object_month': float(budget),
            'candidate_count': 0,
        }
    sentinel = max(score_values) + max(1e-9, abs(max(score_values)) * 1e-9)
    # Descend from the no-event operating point. Stop at the first risk-budget violation.
    # Event grouping can merge nearby alarms, so event count is not guaranteed to be monotone
    # over every lower threshold. We do not allow a still-lower threshold to become 'feasible'
    # again merely because separate quiet alarms merged into one event.
    candidates = sorted(set([sentinel] + score_values), reverse=True)
    selected = None
    evaluations = []
    for threshold in candidates:
        false_events = 0
        for case_id in quiet_case_ids:
            false_events += len(events_from_scores(
                rows_by_case.get(case_id, []),
                scores_by_case.get(case_id, []),
                threshold,
            ))
        rate = false_events / exposure
        evaluations.append({'threshold': threshold, 'false_events': false_events, 'rate': rate})
        if rate <= budget:
            selected = (threshold, false_events, rate)
            continue
        break
    if selected is None:
        raise RuntimeError('comparison threshold grid failed to meet quiet risk budget')
    return {
        'selected_threshold': selected[0],
        'false_events': selected[1],
        'covered_verified_quiet_object_months': exposure,
        'false_events_per_object_month': selected[2],
        'target_false_events_per_object_month': float(budget),
        'candidate_count': len(candidates),
        'evaluated_until_first_violation': len(evaluations),
        'selection_rule': 'lower threshold from no-event point until the calibration quiet event-rate budget is first violated',
    }


def build_case_results(cases, rows_by_case, scores_by_case, case_ids, threshold):
    output = []
    for case_id in case_ids:
        case = cases[case_id]
        rows = rows_by_case.get(case_id, [])
        scores = scores_by_case.get(case_id, [])
        coverage = score_coverage(scores)
        output.append({
            'case_id': case_id,
            'object_id': str(case.get('object_id')),
            'split': case.get('split'),
            'label_status': case.get('label_status'),
            'orbit_regime': normalize_regime(case),
            'span_days': float(case.get('span_days') or 0.0),
            'coverage_fraction': coverage,
            'abstention_fraction': 1.0 - coverage,
            'truth_events': validated_truth_events(case),
            'predicted_events': events_from_scores(rows, scores, threshold),
        })
    return output


def summarize_results(case_results):
    tp = fp = fn = 0
    delays = []
    abs_delays = []
    object_months = 0.0
    abstention_sum = 0.0
    case_count = 0
    positive_cases = quiet_cases = 0
    for case in case_results:
        coverage = float(case.get('coverage_fraction') or 0.0)
        abstention_sum += 1.0 - coverage
        case_count += 1
        label = case.get('label_status')
        predicted = case.get('predicted_events') or []
        truth = validated_truth_events(case)
        if label == 'event-evidence':
            positive_cases += 1
            match = match_event_dicts(predicted, truth)
            tp += match['tp']
            fn += match['fn']
            delays.extend(item['delay_hours'] for item in match['matches'])
            abs_delays.extend(abs(item['delay_hours']) for item in match['matches'])
        elif label == 'verified-quiet':
            quiet_cases += 1
            fp += len(predicted)
            object_months += float(case.get('span_days') or 0.0) * coverage / 30.4375
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    if tp == 0 and fn > 0:
        # A detector that misses all labelled events has F1=0 even if precision is undefined
        # because it emitted no scorable predictions.
        f1 = 0.0
    elif precision is not None and recall is not None and precision + recall:
        f1 = 2.0 * precision * recall / (precision + recall)
    else:
        f1 = None
    return {
        'cases': len(case_results),
        'positive_cases': positive_cases,
        'verified_quiet_cases': quiet_cases,
        'true_positives': tp,
        'false_positives': fp,
        'false_negatives': fn,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'covered_verified_quiet_object_months': object_months,
        'false_events_per_object_month': fp / object_months if object_months > 0 else None,
        'median_detection_delay_hours': statistics.median(delays) if delays else None,
        'median_absolute_detection_delay_hours': statistics.median(abs_delays) if abs_delays else None,
        'mean_case_abstention_fraction': abstention_sum / case_count if case_count else None,
    }

def _percentile(values, q):
    material = sorted(float(v) for v in values if finite(v) is not None)
    if not material:
        return None
    position = (len(material) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return material[lo]
    return material[lo] * (hi - position) + material[hi] * (position - lo)


def bootstrap(case_results, iterations=BOOTSTRAP_ITERATIONS, seed=SEED):
    if not case_results:
        return {}
    rng = random.Random(seed)
    fields = (
        'precision',
        'recall',
        'f1',
        'false_events_per_object_month',
        'median_detection_delay_hours',
        'median_absolute_detection_delay_hours',
        'mean_case_abstention_fraction',
    )
    samples = {field: [] for field in fields}
    for _ in range(int(iterations)):
        drawn = [rng.choice(case_results) for _ in case_results]
        summary = summarize_results(drawn)
        for field in fields:
            value = summary.get(field)
            if finite(value) is not None:
                samples[field].append(float(value))
    return {
        field: {
            'low_95': _percentile(values, 0.025),
            'high_95': _percentile(values, 0.975),
            'bootstrap_samples': len(values),
        }
        for field, values in samples.items()
    }


def evaluation_block(case_results):
    return {
        'summary': summarize_results(case_results),
        'satellite_cluster_bootstrap_95_ci': bootstrap(case_results),
    }


def by_regime(case_results):
    output = {}
    for regime in ORBIT_REGIMES:
        selected = [case for case in case_results if case.get('orbit_regime') == regime]
        if selected:
            output[regime] = evaluation_block(selected)
    return output


class ScoreMethod:
    name = 'base'
    parameter_count = 0

    def fit(self, sequences_):
        return self

    def score_sequence(self, rows):
        raise NotImplementedError


class RobustFeatureScaler:
    def __init__(self, names):
        self.names = tuple(names)
        self.centres = {}
        self.scales = {}

    def fit(self, sequences_):
        rows = [row for seq in sequences_ for row in seq if row.get('quality_ok') is not False]
        for name in self.names:
            values = [
                float(row['features'][name]) for row in rows
                if finite((row.get('features') or {}).get(name)) is not None
            ]
            self.centres[name] = median(values)
            self.scales[name] = safe_scale(values, 1e-8)
        return self

    def z(self, row, name):
        value = finite((row.get('features') or {}).get(name))
        if value is None:
            return None
        return (value - self.centres[name]) / self.scales[name]


class MeanMotionThreshold(ScoreMethod):
    name = 'mean-motion-threshold'

    def fit(self, sequences_):
        self.scaler = RobustFeatureScaler(('mean_motion_rate',)).fit(sequences_)
        self.parameter_count = 2
        return self

    def score_sequence(self, rows):
        output = []
        for row in rows:
            value = self.scaler.z(row, 'mean_motion_rate')
            output.append(None if row.get('quality_ok') is False or value is None else abs(value))
        return output


class MultiElementMAD(ScoreMethod):
    name = 'multi-element-mad'

    def fit(self, sequences_):
        self.scaler = RobustFeatureScaler(ELEMENT_FEATURES).fit(sequences_)
        self.parameter_count = 2 * len(ELEMENT_FEATURES)
        return self

    def score_sequence(self, rows):
        output = []
        for row in rows:
            if row.get('quality_ok') is False:
                output.append(None)
                continue
            z = [self.scaler.z(row, name) for name in ELEMENT_FEATURES]
            output.append(None if any(value is None for value in z) else max(abs(value) for value in z))
        return output


class SGP4RTNConsistency(ScoreMethod):
    name = 'sgp4-rtn-consistency'

    def fit(self, sequences_):
        self.scaler = RobustFeatureScaler(RTN_FEATURES).fit(sequences_)
        self.parameter_count = 2 * len(RTN_FEATURES)
        return self

    def score_sequence(self, rows):
        output = []
        for row in rows:
            if row.get('quality_ok') is False:
                output.append(None)
                continue
            z = [self.scaler.z(row, name) for name in RTN_FEATURES]
            output.append(None if any(value is None for value in z) else max(abs(value) for value in z))
        return output


def _sma_value(row):
    value = finite((row.get('context') or {}).get('log_semi_major_axis_km'))
    return math.exp(value) - 1.0 if value is not None else None


class SMAWindowShift(ScoreMethod):
    name = 'sma-window-shift'
    window = 3

    def fit(self, sequences_):
        raw_scores = []
        for seq in sequences_:
            raw_scores.extend(value for value in self._raw(seq) if value is not None)
        self.centre = median(raw_scores)
        self.scale = safe_scale(raw_scores, 1e-8)
        self.parameter_count = 2
        return self

    def _raw(self, rows):
        values = [_sma_value(row) if row.get('quality_ok') is not False else None for row in rows]
        output = [None] * len(rows)
        w = self.window
        for index in range(2 * w - 1, len(rows)):
            left = values[index - 2 * w + 1:index - w + 1]
            right = values[index - w + 1:index + 1]
            if any(value is None for value in left + right):
                continue
            output[index] = abs(statistics.median(right) - statistics.median(left))
        return output

    def score_sequence(self, rows):
        return [
            None if value is None else abs((value - self.centre) / self.scale)
            for value in self._raw(rows)
        ]


class RobustMahalanobis(ScoreMethod):
    name = 'robust-mahalanobis'

    def fit(self, sequences_):
        n = _require_numpy()
        rows = [row for seq in sequences_ for row in seq if row.get('quality_ok') is not False]
        self.scaler = RobustFeatureScaler(FEATURE_NAMES).fit(sequences_)
        matrix = []
        for row in rows:
            z = [self.scaler.z(row, name) for name in FEATURE_NAMES]
            if any(value is None for value in z):
                continue
            matrix.append([max(-6.0, min(6.0, value)) for value in z])
        x = n.asarray(matrix, dtype=float)
        if x.shape[0] < len(FEATURE_NAMES) + 2:
            raise ValueError('insufficient rows for robust Mahalanobis baseline')
        cov = n.cov(x, rowvar=False)
        diag = n.diag(n.diag(cov))
        cov = 0.9 * cov + 0.1 * diag + n.eye(len(FEATURE_NAMES)) * 1e-6
        self.inverse = n.linalg.pinv(cov)
        self.parameter_count = 2 * len(FEATURE_NAMES) + len(FEATURE_NAMES) ** 2
        return self

    def raw_score(self, row):
        n = _require_numpy()
        if row.get('quality_ok') is False:
            return None
        z = [self.scaler.z(row, name) for name in FEATURE_NAMES]
        if any(value is None for value in z):
            return None
        vector = n.asarray(z, dtype=float)
        return float(math.sqrt(max(0.0, float(vector @ self.inverse @ vector))))

    def score_sequence(self, rows):
        return [self.raw_score(row) for row in rows]


class RobustCUSUM(RobustMahalanobis):
    name = 'robust-cusum'
    allowance = 0.5

    def fit(self, sequences_):
        super().fit(sequences_)
        raw = [self.raw_score(row) for seq in sequences_ for row in seq]
        material = [value for value in raw if value is not None]
        self.score_centre = median(material)
        self.score_scale = safe_scale(material, 1e-8)
        self.parameter_count += 2
        return self

    def score_sequence(self, rows):
        output = []
        cumulative = 0.0
        for row in rows:
            raw = self.raw_score(row)
            if raw is None:
                cumulative = 0.0
                output.append(None)
                continue
            standardized = (raw - self.score_centre) / self.score_scale
            cumulative = max(0.0, cumulative + standardized - self.allowance)
            output.append(cumulative)
        return output


def nonsingular_state(row):
    payload = row.get('physics')
    if not isinstance(payload, dict):
        return None
    elements = payload.get('after_elements')
    if not isinstance(elements, dict):
        return None
    e = finite(elements.get('eccentricity'))
    inc = finite(elements.get('inclination_deg'))
    raan = finite(elements.get('raan_deg'))
    argp = finite(elements.get('argument_of_periapsis_deg'))
    mean_motion = finite(elements.get('mean_motion_rev_per_day'))
    if None in (e, inc, raan, argp, mean_motion) or mean_motion <= 0.0:
        return None
    raan_r = math.radians(raan)
    lonp = math.radians((raan + argp) % 360.0)
    half_tan = math.tan(0.5 * math.radians(inc))
    return [
        math.log(mean_motion),
        e * math.cos(lonp),
        e * math.sin(lonp),
        half_tan * math.cos(raan_r),
        half_tan * math.sin(raan_r),
    ]


def nonsingular_before_state(row):
    payload = row.get('physics')
    if not isinstance(payload, dict):
        return None
    elements = payload.get('before_elements')
    if not isinstance(elements, dict):
        return None
    return nonsingular_state({'physics': {'after_elements': elements}})


class OrbitDynamicsFit:
    def fit(self, sequences_):
        n = _require_numpy()
        after_states = []
        rates = []
        for seq in sequences_:
            for row in seq:
                if row.get('quality_ok') is False:
                    continue
                before = nonsingular_before_state(row)
                after = nonsingular_state(row)
                gap = finite((row.get('physics') or {}).get('gap_days'))
                if before is None or after is None or gap is None or gap <= 0:
                    continue
                after_states.append(after)
                rates.append([(a - b) / gap for a, b in zip(after, before)])
        if len(after_states) < 24:
            raise ValueError('insufficient nonsingular states for filtering baselines')
        after_array = n.asarray(after_states, dtype=float)
        self.centres = n.median(after_array, axis=0)
        self.scales = n.asarray([
            safe_scale(after_array[:, index].tolist(), 1e-8)
            for index in range(after_array.shape[1])
        ])
        rate_array = n.asarray(rates, dtype=float) / self.scales
        self.drift = n.median(rate_array, axis=0)
        residual_rows = []
        for seq in sequences_:
            for row in seq:
                if row.get('quality_ok') is False:
                    continue
                before = nonsingular_before_state(row)
                after = nonsingular_state(row)
                gap = finite((row.get('physics') or {}).get('gap_days'))
                if before is None or after is None or gap is None or gap <= 0:
                    continue
                b = (n.asarray(before) - self.centres) / self.scales
                a = (n.asarray(after) - self.centres) / self.scales
                residual_rows.append((a - b - self.drift * gap) / math.sqrt(gap))
        residual = n.asarray(residual_rows, dtype=float)
        self.residual_var = n.asarray([
            max(1e-6, safe_scale(residual[:, index].tolist(), 1e-4) ** 2)
            for index in range(residual.shape[1])
        ])
        return self

    def transform(self, row):
        n = _require_numpy()
        state = nonsingular_state(row)
        if state is None:
            return None
        return (n.asarray(state, dtype=float) - self.centres) / self.scales


class KalmanNIS(ScoreMethod):
    name = 'kalman-nis'
    q_ratio_grid = (1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1, 3e-1, 1.0, 3.0)

    def fit(self, sequences_):
        n = _require_numpy()
        self.dynamics = OrbitDynamicsFit().fit(sequences_)
        best = None
        for q_ratio in self.q_ratio_grid:
            nll = 0.0
            count = 0
            for seq in sequences_:
                state = None
                covariance = n.ones(5, dtype=float)
                for row in seq:
                    observation = self.dynamics.transform(row)
                    gap = finite((row.get('physics') or {}).get('gap_days'))
                    if observation is None or gap is None or gap <= 0:
                        state = None
                        covariance = n.ones(5, dtype=float)
                        continue
                    if state is None:
                        state = observation.copy()
                        covariance = n.ones(5, dtype=float)
                        continue
                    predicted = state + self.dynamics.drift * gap
                    predicted_covariance = covariance + q_ratio * gap
                    innovation = observation - predicted
                    innovation_covariance = predicted_covariance + 1.0
                    nll += 0.5 * float(n.sum(
                        n.log(2.0 * math.pi * innovation_covariance)
                        + innovation * innovation / innovation_covariance
                    ))
                    count += 1
                    gain = predicted_covariance / innovation_covariance
                    state = predicted + gain * innovation
                    covariance = (1.0 - gain) * predicted_covariance
            criterion = nll / max(1, count)
            if best is None or criterion < best[0]:
                best = (criterion, q_ratio)
        self.q_ratio = float(best[1])
        self.parameter_count = 16
        return self

    def score_sequence(self, rows):
        n = _require_numpy()
        output = []
        state = None
        covariance = n.ones(5, dtype=float)
        for row in rows:
            observation = self.dynamics.transform(row)
            gap = finite((row.get('physics') or {}).get('gap_days'))
            if row.get('quality_ok') is False or observation is None or gap is None or gap <= 0:
                state = None
                covariance = n.ones(5, dtype=float)
                output.append(None)
                continue
            if state is None:
                state = observation.copy()
                covariance = n.ones(5, dtype=float)
                output.append(None)
                continue
            predicted = state + self.dynamics.drift * gap
            predicted_covariance = covariance + self.q_ratio * gap
            innovation = observation - predicted
            innovation_covariance = predicted_covariance + 1.0
            score = float(n.sum(innovation * innovation / innovation_covariance))
            gain = predicted_covariance / innovation_covariance
            state = predicted + gain * innovation
            covariance = (1.0 - gain) * predicted_covariance
            output.append(score)
        return output


def _logsumexp(values):
    n = _require_numpy()
    maximum = float(n.max(values))
    return maximum + math.log(float(n.sum(n.exp(values - maximum))))


class ShortenStyleOPPF(ScoreMethod):
    name = 'shorten-op-pf-surrogate'
    particles = PF_PARTICLES
    ess_fraction = 0.5

    def fit(self, sequences_):
        self.dynamics = OrbitDynamicsFit().fit(sequences_)
        self.q = self.dynamics.residual_var.copy()
        self.r = self.dynamics.residual_var.copy()
        self.parameter_count = 20
        return self

    @staticmethod
    def _case_seed(rows):
        case_id = str(rows[0].get('case_id') if rows else '')
        digest = hashlib.sha256(f'{SEED}|{case_id}'.encode()).digest()
        return int.from_bytes(digest[:8], 'big') & 0xFFFFFFFF

    @staticmethod
    def _systematic_resample(weights, rng):
        n = _require_numpy()
        count = len(weights)
        positions = (rng.random() + n.arange(count)) / count
        cumulative = n.cumsum(weights)
        return n.searchsorted(cumulative, positions, side='right')

    def score_sequence(self, rows):
        n = _require_numpy()
        rng = n.random.default_rng(self._case_seed(rows))
        output = []
        particles = None
        weights = None
        bandwidth = self.particles ** (-1.0 / 9.0)
        for row in rows:
            observation = self.dynamics.transform(row)
            gap = finite((row.get('physics') or {}).get('gap_days'))
            if row.get('quality_ok') is False or observation is None or gap is None or gap <= 0:
                particles = None
                weights = None
                output.append(None)
                continue
            if particles is None:
                particles = observation + rng.normal(size=(self.particles, 5)) * n.sqrt(self.r)
                weights = n.full(self.particles, 1.0 / self.particles)
                output.append(None)
                continue

            process_covariance = n.maximum(1e-8, self.q * gap)
            observation_covariance = n.maximum(1e-8, self.r)
            predicted_mean = particles + self.dynamics.drift * gap
            predictive_variance = process_covariance + observation_covariance
            log_components = (
                -0.5 * n.sum(n.log(2.0 * math.pi * predictive_variance))
                -0.5 * n.sum((observation - predicted_mean) ** 2 / predictive_variance, axis=1)
                + n.log(n.maximum(weights, 1e-300))
            )
            output.append(float(-_logsumexp(log_components)))

            posterior_variance = 1.0 / (1.0 / process_covariance + 1.0 / observation_covariance)
            posterior_mean = posterior_variance * (
                predicted_mean / process_covariance + observation / observation_covariance
            )
            particles = posterior_mean + rng.normal(size=(self.particles, 5)) * n.sqrt(posterior_variance)
            log_weights = log_components - _logsumexp(log_components)
            weights = n.exp(log_weights)
            ess = 1.0 / float(n.sum(weights * weights))
            if ess / self.particles < self.ess_fraction:
                indices = self._systematic_resample(weights, rng)
                particles = particles[indices]
                weights = n.full(self.particles, 1.0 / self.particles)
                covariance = n.cov(particles, rowvar=False) + n.eye(5) * 1e-8
                try:
                    root = n.linalg.cholesky(covariance)
                except n.linalg.LinAlgError:
                    root = n.diag(n.sqrt(n.maximum(1e-8, n.diag(covariance))))
                particles = particles + bandwidth * (rng.normal(size=(self.particles, 5)) @ root.T)
        return output


class ModelScoreMethod(ScoreMethod):
    def __init__(self, model):
        self.model = model
        self.name = model.name

    def fit(self, sequences_):
        self.model.fit(sequences_)
        self.parameter_count = int(getattr(self.model, 'parameter_count', 0))
        return self

    def score_sequence(self, rows):
        # A quality failure is a temporal trust boundary. Sequence models are invoked only on
        # contiguous trusted segments, so hidden state cannot cross an abstained row.
        output = [None] * len(rows)
        cursor = 0
        while cursor < len(rows):
            while cursor < len(rows) and rows[cursor].get('quality_ok') is False:
                cursor += 1
            if cursor >= len(rows):
                break
            end = cursor
            while end < len(rows) and rows[end].get('quality_ok') is not False:
                end += 1
            predictions = self.model.predict_sequence(rows[cursor:end])
            if len(predictions) != end - cursor:
                raise RuntimeError('comparison model returned wrong prediction length')
            for offset, prediction in enumerate(predictions):
                if prediction is None or finite(prediction.surprise) is None:
                    continue
                output[cursor + offset] = float(prediction.surprise)
            cursor = end
        return output

class LSTMStudentTModel(TorchStudentTModel):
    def __init__(self):
        super().__init__(
            'gru',
            hidden_size=32,
            layers=2,
            epochs=NEURAL_EPOCHS,
            learning_rate=3e-3,
            seed=SEED,
        )
        self.architecture = 'lstm'
        self.name = 'lstm'

    def _build_network(self, torch):
        nn = torch.nn
        input_size = len(CONTEXT_NAMES) + len(FEATURE_NAMES)
        output_size = 2 * len(FEATURE_NAMES)
        hidden = self.hidden_size
        layers = self.layers

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.input = nn.Linear(input_size, hidden)
                self.lstm = nn.LSTM(hidden, hidden, num_layers=layers, batch_first=True)
                self.head = nn.Linear(hidden, output_size)

            def forward(self, x, present):
                z = torch.tanh(self.input(x))
                z, _ = self.lstm(z)
                return self.head(z)

        return Net()


class SequentialAutoencoder(ScoreMethod):
    name = 'sequential-autoencoder'
    window = AUTOENCODER_WINDOW
    hidden = 32
    epochs = NEURAL_EPOCHS

    def fit(self, sequences_):
        _require_numpy()
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError('PyTorch is required for sequential autoencoder') from exc
        self.torch = torch
        torch.manual_seed(SEED)
        try:
            torch.use_deterministic_algorithms(True)
        except Exception:
            pass
        rows = [row for seq in sequences_ for row in seq if row.get('quality_ok') is not False]
        self.centres = {name: median([row['features'][name] for row in rows]) for name in FEATURE_NAMES}
        self.scales = {name: safe_scale([row['features'][name] for row in rows], 1e-8) for name in FEATURE_NAMES}

        def vector(row):
            return [
                (float(row['features'][name]) - self.centres[name]) / self.scales[name]
                for name in FEATURE_NAMES
            ]

        windows = []
        for seq in sequences_:
            segment = []
            for row in seq:
                good = row.get('quality_ok') is not False and all(
                    finite((row.get('features') or {}).get(name)) is not None for name in FEATURE_NAMES
                )
                if not good:
                    segment = []
                    continue
                segment.append(vector(row))
                if len(segment) >= self.window:
                    windows.append(segment[-self.window:])
        if len(windows) < 8:
            raise ValueError('insufficient normal windows for sequential autoencoder')
        x = torch.tensor(windows, dtype=torch.float32)

        hidden = self.hidden
        feature_count = len(FEATURE_NAMES)

        class Net(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder = torch.nn.LSTM(feature_count, hidden, batch_first=True)
                self.decoder = torch.nn.LSTM(feature_count, hidden, batch_first=True)
                self.output = torch.nn.Linear(hidden, feature_count)

            def forward(self, values):
                _, (h, c) = self.encoder(values)
                zeros = torch.zeros_like(values)
                decoded, _ = self.decoder(zeros, (h, c))
                return self.output(decoded)

        model = Net()
        optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
        target = torch.flip(x, dims=[1])
        model.train()
        for _ in range(self.epochs):
            optimizer.zero_grad(set_to_none=True)
            prediction = model(x)
            loss = torch.mean((prediction - target) ** 2)
            if not torch.isfinite(loss):
                raise RuntimeError('non-finite sequential autoencoder training loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
        model.eval()
        self.model = model
        self.parameter_count = sum(parameter.numel() for parameter in model.parameters())
        return self

    def _vector(self, row):
        if row.get('quality_ok') is False:
            return None
        output = []
        for name in FEATURE_NAMES:
            value = finite((row.get('features') or {}).get(name))
            if value is None:
                return None
            output.append((value - self.centres[name]) / self.scales[name])
        return output

    def score_sequence(self, rows):
        torch = self.torch
        output = []
        segment = []
        for row in rows:
            vector = self._vector(row)
            if vector is None:
                segment = []
                output.append(None)
                continue
            segment.append(vector)
            if len(segment) < self.window:
                output.append(None)
                continue
            window = torch.tensor([segment[-self.window:]], dtype=torch.float32)
            with torch.no_grad():
                prediction = self.model(window)[0, 0]
            target = torch.tensor(segment[-1], dtype=torch.float32)
            output.append(float(torch.mean((prediction - target) ** 2)))
        return output


def make_methods():
    return [
        MeanMotionThreshold(),
        SMAWindowShift(),
        SGP4RTNConsistency(),
        MultiElementMAD(),
        RobustMahalanobis(),
        RobustCUSUM(),
        KalmanNIS(),
        ShortenStyleOPPF(),
        ModelScoreMethod(RobustConditionalLinear()),
        ModelScoreMethod(LSTMStudentTModel()),
        ModelScoreMethod(make_candidate('gru')),
        ModelScoreMethod(make_candidate('tcn')),
        ModelScoreMethod(make_candidate('transformer')),
        SequentialAutoencoder(),
    ]


def run_generic_method(method, cases, rows_by_case):
    train_ids = quiet_ids(cases, 'development')
    train_sequences = [rows_by_case[case_id] for case_id in train_ids if rows_by_case.get(case_id)]
    fit_start = time.perf_counter()
    method.fit(train_sequences)
    fit_seconds = time.perf_counter() - fit_start

    calibration_case_ids = sorted(event_ids(cases, 'calibration') + quiet_ids(cases, 'calibration'))
    inference_start = time.perf_counter()
    scores_by_case = {
        case_id: method.score_sequence(rows_by_case.get(case_id, []))
        for case_id in calibration_case_ids
    }
    inference_seconds = time.perf_counter() - inference_start
    calibration_rows = sum(len(rows_by_case.get(case_id, [])) for case_id in calibration_case_ids)

    development_case_ids = event_ids(cases, 'development')
    diagnostic_start = time.perf_counter()
    for case_id in development_case_ids:
        scores_by_case[case_id] = method.score_sequence(rows_by_case.get(case_id, []))
    diagnostic_seconds = time.perf_counter() - diagnostic_start

    calibration = calibrate_threshold(
        cases, rows_by_case, scores_by_case, quiet_ids(cases, 'calibration')
    )
    threshold = calibration['selected_threshold']
    calibration_results = build_case_results(
        cases, rows_by_case, scores_by_case, calibration_case_ids, threshold
    )
    development_results = build_case_results(
        cases, rows_by_case, scores_by_case, development_case_ids, threshold
    )

    return {
        'method': method.name,
        'family': 'comparison-baseline',
        'settings_source': (
            'predeclared fixed method; fitted on development verified-quiet only; '
            'event threshold calibrated on calibration verified-quiet only'
        ),
        'training_reference_partition': 'development verified-quiet only',
        'calibration': calibration,
        'primary_calibration_evaluation': evaluation_block(calibration_results),
        'primary_calibration_by_orbit_regime': by_regime(calibration_results),
        'development_event_diagnostic': evaluation_block(development_results),
        'computational_cost': {
            'fit_seconds': fit_seconds,
            'inference_seconds': inference_seconds,
            'diagnostic_development_inference_seconds': diagnostic_seconds,
            'evaluation_cases_inference': len(calibration_case_ids),
            'feature_rows_inference': calibration_rows,
            'rows_per_second': calibration_rows / inference_seconds if inference_seconds > 0 else None,
            'parameter_count': int(getattr(method, 'parameter_count', 0)),
            'runtime': 'CPU Python; neural methods use CPU PyTorch',
            'timing_scope': 'primary calibration split only for inference; development diagnostics timed separately',
        },
    }

def detector_case_results(detector_document, cases):
    output = []
    for raw in detector_document.get('cases', []):
        case_id = str(raw['case_id'])
        if case_id not in cases or cases[case_id].get('split') != 'calibration':
            continue
        case = cases[case_id]
        abstained = bool(raw.get('abstained'))
        output.append({
            'case_id': case_id,
            'object_id': str(case.get('object_id')),
            'split': 'calibration',
            'label_status': case.get('label_status'),
            'orbit_regime': normalize_regime(case),
            'span_days': float(raw.get('span_days') or case.get('span_days') or 0.0),
            'coverage_fraction': 0.0 if abstained else 1.0,
            'abstention_fraction': 1.0 if abstained else 0.0,
            'truth_events': validated_truth_events(case),
            'predicted_events': raw.get('predicted_events') or [],
        })
    return output


def detector_v04_result(detector_document, detector_cost, cases, rows_by_case):
    primary = detector_case_results(detector_document, cases)
    development = []
    for raw in detector_document.get('cases', []):
        case_id = str(raw['case_id'])
        if (
            case_id not in cases
            or cases[case_id].get('split') != 'development'
            or cases[case_id].get('label_status') != 'event-evidence'
        ):
            continue
        case = cases[case_id]
        abstained = bool(raw.get('abstained'))
        development.append({
            'case_id': case_id,
            'object_id': str(case.get('object_id')),
            'split': 'development',
            'label_status': case.get('label_status'),
            'orbit_regime': normalize_regime(case),
            'span_days': float(raw.get('span_days') or case.get('span_days') or 0.0),
            'coverage_fraction': 0.0 if abstained else 1.0,
            'abstention_fraction': 1.0 if abstained else 0.0,
            'truth_events': validated_truth_events(case),
            'predicted_events': raw.get('predicted_events') or [],
        })
    calibration_ids = sorted(
        case_id for case_id, case in cases.items() if case.get('split') == 'calibration'
    )
    rows = sum(len(rows_by_case.get(case_id, [])) for case_id in calibration_ids)
    seconds = finite(detector_cost.get('wall_seconds')) or 0.0
    quiet_summary = summarize_results([case for case in primary if case.get('label_status') == 'verified-quiet'])
    return {
        'method': 'detector-0.4',
        'family': 'target-method',
        'settings_source': 'frozen detector 0.4 settings; no Comparison evaluation tuning',
        'calibration': {
            'selected_threshold': 'frozen detector 0.4 internal operating point',
            'covered_verified_quiet_object_months': quiet_summary['covered_verified_quiet_object_months'],
            'false_events_per_object_month': quiet_summary['false_events_per_object_month'],
            'target_false_events_per_object_month': None,
        },
        'primary_calibration_evaluation': evaluation_block(primary),
        'primary_calibration_by_orbit_regime': by_regime(primary),
        'development_event_diagnostic': evaluation_block(development),
        'computational_cost': {
            'fit_seconds': 0.0,
            'inference_seconds': seconds,
            'feature_rows_inference': rows,
            'rows_per_second': rows / seconds if seconds > 0 else None,
            'evaluation_cases_inference': len(calibration_ids),
            'diagnostic_development_inference_seconds': None,
            'parameter_count': 0,
            'runtime': 'Node.js workbench detector 0.4 with satellite.js',
            'timing_scope': 'separate primary calibration-only detector 0.4 run',
        },
    }


def physics_score_case(model, support, inverter, rows):
    raw = raw_score_sequence(model, support, rows, require_qualified_regime=False)
    supported = apply_support_threshold(raw, SEQUENTIAL_FINAL_SUPPORT_THRESHOLD)
    transformed, _ = physics_rows(rows, supported, inverter)
    layer = SequentialEventLayer(
        base_score_threshold=SEQUENTIAL_BASE_THRESHOLD,
        q0=PHYSICS_Q0,
        wealth_threshold=PHYSICS_FINAL_WEALTH_THRESHOLD,
    )
    _, events = layer.run(transformed)
    converted = [
        {
            'start_index': event.start_index,
            'end_index': event.end_index,
            'strongest_index': event.strongest_index,
            'start_utc': event.start_utc,
            'end_utc': event.end_utc,
            'strongest_utc': event.strongest_utc,
            'score': event.trigger_wealth,
        }
        for event in events
    ]
    coverage = sum(row.status == 'scored' for row in transformed) / len(transformed) if transformed else 0.0
    return converted, coverage


def physics_ml_v1_result(cases, rows_by_case):
    all_quiet = quiet_ids(cases, 'development') + quiet_ids(cases, 'calibration')
    calibration_event_ids = event_ids(cases, 'calibration')
    calibration_quiet_ids = quiet_ids(cases, 'calibration')
    dev_event_ids = event_ids(cases, 'development')
    fit_seconds = 0.0
    inference_seconds = 0.0
    diagnostic_seconds = 0.0
    primary = []

    start = time.perf_counter()
    model = make_candidate('transformer').fit(sequences(rows_by_case, all_quiet))
    support = SupportModel(k=5, min_reference_satellites=3).fit(rows_for_cases(rows_by_case, all_quiet))
    noise = PhysicsNoiseModel(min_reference_satellites=3).fit(rows_for_cases(rows_by_case, all_quiet))
    inverter = ManeuverPhysicsInverter(noise)
    fit_seconds += time.perf_counter() - start
    parameter_count = int(model.parameter_count)

    for case_id in calibration_event_ids:
        start = time.perf_counter()
        predicted, coverage = physics_score_case(model, support, inverter, rows_by_case.get(case_id, []))
        inference_seconds += time.perf_counter() - start
        case = cases[case_id]
        primary.append({
            'case_id': case_id,
            'object_id': str(case.get('object_id')),
            'split': 'calibration',
            'label_status': case.get('label_status'),
            'orbit_regime': normalize_regime(case),
            'span_days': float(case.get('span_days') or 0.0),
            'coverage_fraction': coverage,
            'abstention_fraction': 1.0 - coverage,
            'truth_events': validated_truth_events(case),
            'predicted_events': predicted,
        })

    for heldout in calibration_quiet_ids:
        training = [case_id for case_id in all_quiet if case_id != heldout]
        start = time.perf_counter()
        held_model = make_candidate('transformer').fit(sequences(rows_by_case, training))
        held_support = SupportModel(k=5, min_reference_satellites=1).fit(rows_for_cases(rows_by_case, training))
        held_noise = PhysicsNoiseModel(min_reference_satellites=3).fit(rows_for_cases(rows_by_case, training))
        held_inverter = ManeuverPhysicsInverter(held_noise)
        fit_seconds += time.perf_counter() - start
        start = time.perf_counter()
        predicted, coverage = physics_score_case(
            held_model, held_support, held_inverter, rows_by_case.get(heldout, [])
        )
        inference_seconds += time.perf_counter() - start
        case = cases[heldout]
        primary.append({
            'case_id': heldout,
            'object_id': str(case.get('object_id')),
            'split': 'calibration',
            'label_status': 'verified-quiet',
            'orbit_regime': normalize_regime(case),
            'span_days': float(case.get('span_days') or 0.0),
            'coverage_fraction': coverage,
            'abstention_fraction': 1.0 - coverage,
            'truth_events': [],
            'predicted_events': predicted,
        })

    development = []
    for case_id in dev_event_ids:
        start = time.perf_counter()
        predicted, coverage = physics_score_case(model, support, inverter, rows_by_case.get(case_id, []))
        diagnostic_seconds += time.perf_counter() - start
        case = cases[case_id]
        development.append({
            'case_id': case_id,
            'object_id': str(case.get('object_id')),
            'split': 'development',
            'label_status': 'event-evidence',
            'orbit_regime': normalize_regime(case),
            'span_days': float(case.get('span_days') or 0.0),
            'coverage_fraction': coverage,
            'abstention_fraction': 1.0 - coverage,
            'truth_events': validated_truth_events(case),
            'predicted_events': predicted,
        })

    rows = sum(
        len(rows_by_case.get(case_id, []))
        for case_id in calibration_event_ids + calibration_quiet_ids
    )
    quiet_summary = summarize_results([case for case in primary if case['label_status'] == 'verified-quiet'])
    return {
        'method': 'physics-ml-v1.0',
        'family': 'target-method',
        'settings_source': (
            'frozen Physics evaluation transformer/support/sequential/equivalent-impulse stack; '
            'no Comparison evaluation retuning'
        ),
        'calibration': {
            'base_score_threshold': SEQUENTIAL_BASE_THRESHOLD,
            'support_threshold': SEQUENTIAL_FINAL_SUPPORT_THRESHOLD,
            'q0': PHYSICS_Q0,
            'wealth_threshold': PHYSICS_FINAL_WEALTH_THRESHOLD,
            'quiet_evaluation': 'leave-one-calibration-quiet-satellite-out',
            'covered_verified_quiet_object_months': quiet_summary['covered_verified_quiet_object_months'],
            'false_events_per_object_month': quiet_summary['false_events_per_object_month'],
        },
        'primary_calibration_evaluation': evaluation_block(primary),
        'primary_calibration_by_orbit_regime': by_regime(primary),
        'development_event_diagnostic': evaluation_block(development),
        'computational_cost': {
            'fit_seconds': fit_seconds,
            'inference_seconds': inference_seconds,
            'diagnostic_development_inference_seconds': diagnostic_seconds,
            'evaluation_cases_inference': len(calibration_event_ids) + len(calibration_quiet_ids),
            'feature_rows_inference': rows,
            'rows_per_second': rows / inference_seconds if inference_seconds > 0 else None,
            'parameter_count': parameter_count,
            'runtime': (
                'CPU Python/PyTorch plus equivalent-impulse inversion; benchmark cost includes '
                'four quiet leave-one-out fits'
            ),
            'timing_scope': 'primary calibration split only for inference; development diagnostics timed separately',
        },
    }


def ranking_key(method):
    summary = method['primary_calibration_evaluation']['summary']
    f1 = summary.get('f1')
    recall = summary.get('recall')
    fp_rate = summary.get('false_events_per_object_month')
    return (
        -1.0 if f1 is None else float(f1),
        -1.0 if recall is None else float(recall),
        -(float(fp_rate) if fp_rate is not None else 1e30),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--features', required=True)
    parser.add_argument('--detector-results', required=True)
    parser.add_argument('--detector-cost', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    feature_document = load_document(Path(args.features))
    cases, rows_by_case = grouped_rows(feature_document)
    splits = {str(case.get('split')) for case in cases.values()}
    if 'confirmatory' in splits:
        raise ValueError('CONFIRMATORY PARTITION IS SEALED: comparison suite refuses confirmatory cases')
    if splits != {'development', 'calibration'}:
        raise ValueError(f'comparison suite requires development+calibration only, found {sorted(splits)}')

    detector_document = json.loads(Path(args.detector_results).read_text())
    if any(str(case.get('split')) == 'confirmatory' for case in detector_document.get('cases', [])):
        raise ValueError('CONFIRMATORY PARTITION IS SEALED: detector results contain confirmatory cases')
    for case in detector_document.get('cases', []):
        validated_truth_events(case)
    detector_cost = json.loads(Path(args.detector_cost).read_text())

    results = [detector_v04_result(detector_document, detector_cost, cases, rows_by_case)]
    for method in make_methods():
        print(f'Running {method.name}...', flush=True)
        results.append(run_generic_method(method, cases, rows_by_case))
    print('Running physics-ml-v1.0...', flush=True)
    results.append(physics_ml_v1_result(cases, rows_by_case))

    names = [item['method'] for item in results]
    if tuple(names) != METHOD_ORDER:
        raise RuntimeError(f'method order drifted: {names}')

    ranked = sorted(results, key=ranking_key, reverse=True)
    table = []
    for rank, item in enumerate(ranked, start=1):
        summary = item['primary_calibration_evaluation']['summary']
        false_rate = summary.get('false_events_per_object_month')
        compliant = false_rate is not None and float(false_rate) <= RISK_BUDGET
        table.append({
            'rank_by_calibration_f1_then_recall': rank,
            'method': item['method'],
            'precision': summary.get('precision'),
            'recall': summary.get('recall'),
            'f1': summary.get('f1'),
            'false_events_per_object_month': false_rate,
            'common_risk_budget_compliant': compliant,
            'median_detection_delay_hours': summary.get('median_detection_delay_hours'),
            'mean_case_abstention_fraction': summary.get('mean_case_abstention_fraction'),
        })

    compliant_ranking = []
    for item in [row for row in table if row['common_risk_budget_compliant']]:
        entry = dict(item)
        entry['rank_within_common_risk_budget'] = len(compliant_ranking) + 1
        compliant_ranking.append(entry)

    output = {
        'schema': 'smd-comparison-suite-v1',
        'evaluation_version': EVALUATION_VERSION,
        'scoring_version': EVENT_MATCHING_VERSION,
        'paper_track': 'maneuver-detection-comparison',
        'benchmark_version': feature_document.get('benchmark_version'),
        'confirmatory_partition_accessed': False,
        'included_splits': ['calibration', 'development'],
        'primary_evaluation_split': 'calibration',
        'matching_tolerance_hours': MATCH_TOLERANCE_HOURS,
        'risk_budget_false_events_per_covered_object_month': RISK_BUDGET,
        'bootstrap_iterations': BOOTSTRAP_ITERATIONS,
        'bootstrap_seed': SEED,
        'method_count': len(results),
        'method_order': list(METHOD_ORDER),
        'settings_policy': (
            'All baseline definitions and fixed hyperparameters were declared before running calibration event labels. '
            'Generic baselines fit only development verified-quiet data and calibrate one event threshold only on '
            'calibration verified-quiet exposure. Detector 0.4 and physics-ML v1.0 retain their frozen operating '
            'points. No calibration event label is used for method or threshold selection.'
        ),
        'shorten_reproducibility_note': (
            'shorten-op-pf-surrogate preserves the optimal-proposal Gaussian update, predictive-density anomaly '
            'statistic, ESS-triggered systematic resampling, regularisation bandwidth and residual-derived Q/R '
            'convention, but replaces the paper-specific non-standard mean-element SGP4/Kozai-Brouwer implementation '
            'with a nonsingular empirical mean-element transition fitted only on development verified-quiet data. '
            'It is therefore a structural surrogate, not an exact reproduction.'
        ),
        'methods': results,
        'calibration_ranking_table': table,
        'common_risk_budget_compliant_ranking_table': compliant_ranking,
        'claim_boundary': (
            'Comparison evaluation development/calibration comparison only. The benchmark v1.0 confirmatory partition remains '
            'sealed. Positive-unlabelled event semantics are preserved: unmatched predictions on event-evidence '
            'histories are unscored, while false events are measured only on verified-quiet exposure.'
        ),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'methods': names, 'ranking': table}, indent=2))


if __name__ == '__main__':
    main()
