#!/usr/bin/env python3
"""Bounded, synthetic CPU execution checks for the versioned neural adapter."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
import math
import sys
import unittest
from unittest.mock import patch

import torch

from research.comparison_v1.run_comparison import ModelScoreMethod
from research.neural_execution import (
    NEURAL_EXECUTION_VERSION,
    SUPPORTED_ARCHITECTURES,
    NeuralExecutionModel,
)
from research.selective_v1.core import CONTEXT_NAMES, FEATURE_NAMES, SupportModel
from research.selective_v1.detector import SelectiveDetector

FIXTURE_VERSION = 'synthetic-neural-smoke-v1'
SEED = 3404
MAX_GAP_SECONDS = 7200
STUDENT_T_ARCHITECTURES = ('gru', 'tcn', 'transformer', 'lstm')
ARCHITECTURES = STUDENT_T_ARCHITECTURES + ('sequential-autoencoder',)
MODEL_REPORTS: list[dict] = []


def synthetic_rows(count: int, object_id: str = 'synthetic-a', phase: float = 0.0) -> list[dict]:
    """Generate smooth finite channels without loading any research data."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        context = {
            name: 0.1 * (channel + 1) + 0.02 * math.sin(0.13 * index + channel + phase)
            for channel, name in enumerate(CONTEXT_NAMES)
        }
        context.update(
            orbit_leo=1.0, orbit_meo=0.0, orbit_geo=0.0, orbit_heo=0.0,
            log_gap_days=math.log1p(1.0 / 24.0),
        )
        features = {
            name: 0.01 * (channel + 1)
            + 0.003 * math.sin(0.17 * index + 0.23 * channel + phase)
            + 0.001 * math.cos(0.05 * index + 0.12 * channel)
            for channel, name in enumerate(FEATURE_NAMES)
        }
        rows.append({
            'case_id': 'case-' + object_id,
            'object_id': object_id,
            'split': 'development',
            'nominal': True,
            'quality_ok': True,
            'index': index,
            'epoch_utc': (start + timedelta(hours=index)).isoformat().replace('+00:00', 'Z'),
            'context': context,
            'features': features,
        })
    return rows


def training_sequences() -> list[list[dict]]:
    # Ragged batches exercise the real padding mask, with three distinct support objects.
    return [
        synthetic_rows(32, 'synthetic-a', 0.0),
        synthetic_rows(25, 'synthetic-b', 0.3),
        synthetic_rows(18, 'synthetic-c', 0.6),
    ]


def candidate(architecture: str, **changes) -> NeuralExecutionModel:
    options = {
        'max_gap_seconds': MAX_GAP_SECONDS,
        'hidden_size': 8,
        'layers': 1,
        'epochs': 2,
        'learning_rate': 3e-3,
        'seed': SEED,
    }
    options.update(changes)
    return NeuralExecutionModel(architecture, **options)


def shift_times(rows: list[dict], start: int, delta: timedelta) -> None:
    for row in rows[start:]:
        instant = datetime.fromisoformat(row['epoch_utc'].replace('Z', '+00:00'))
        row['epoch_utc'] = (instant + delta).isoformat().replace('+00:00', 'Z')


class NeuralExecutionTests(unittest.TestCase):
    models: dict[str, NeuralExecutionModel]
    updates: dict[str, list[dict]]

    @classmethod
    def setUpClass(cls) -> None:
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        cls.models = {}
        cls.updates = {}
        MODEL_REPORTS.clear()
        original_step = torch.optim.AdamW.step
        for architecture in ARCHITECTURES:
            updates = []

            def observed_step(optimizer, *args, **kwargs):
                parameters = [
                    parameter for group in optimizer.param_groups
                    for parameter in group['params']
                ]
                before = [parameter.detach().clone() for parameter in parameters]
                gradients = [parameter.grad for parameter in parameters if parameter.grad is not None]
                finite_gradients = bool(gradients) and all(
                    bool(torch.isfinite(gradient).all()) for gradient in gradients
                )
                result = original_step(optimizer, *args, **kwargs)
                updates.append({
                    'changed': any(
                        not torch.equal(prior, current.detach())
                        for prior, current in zip(before, parameters)
                    ),
                    'finite_gradients': finite_gradients,
                    'finite_parameters': all(bool(torch.isfinite(p).all()) for p in parameters),
                    'cpu': all(p.device.type == 'cpu' for p in parameters),
                })
                return result

            model = candidate(architecture)
            with patch.object(torch.optim.AdamW, 'step', observed_step):
                fitted = model.fit(training_sequences())
            if fitted is not model:
                raise AssertionError('fit must return its fitted model')
            cls.models[architecture] = model
            cls.updates[architecture] = updates
            MODEL_REPORTS.append(model.provenance())

    def assert_scores_equal(self, actual, expected) -> None:
        self.assertEqual(len(actual), len(expected))
        for left, right in zip(actual, expected):
            if right is None:
                self.assertIsNone(left)
            else:
                self.assertIsNotNone(left)
                self.assertTrue(
                    math.isclose(float(left), float(right), rel_tol=2e-5, abs_tol=2e-6),
                    (left, right),
                )

    def assert_predictions_equal(self, actual, expected) -> None:
        self.assertEqual(len(actual), len(expected))
        for left, right in zip(actual, expected):
            if right is None:
                self.assertIsNone(left)
                continue
            self.assertIsNotNone(left)
            for field in ('location', 'scale', 'z_scores'):
                self.assertEqual(set(getattr(left, field)), set(FEATURE_NAMES))
                self.assert_scores_equal(
                    [getattr(left, field)[name] for name in FEATURE_NAMES],
                    [getattr(right, field)[name] for name in FEATURE_NAMES],
                )
            self.assert_scores_equal([left.surprise], [right.surprise])

    def test_all_supported_architectures_execute_real_cpu_optimiser_steps(self) -> None:
        self.assertEqual(set(SUPPORTED_ARCHITECTURES), set(ARCHITECTURES))
        for architecture, updates in self.updates.items():
            with self.subTest(architecture=architecture):
                self.assertEqual(len(updates), 2)
                for update in updates:
                    self.assertTrue(all(update.values()), update)
                self.assertGreater(self.models[architecture].parameter_count, 0)

    def test_output_dimensions_finiteness_and_alignment(self) -> None:
        rows = synthetic_rows(24, 'synthetic-query', 0.2)
        for architecture, model in self.models.items():
            with self.subTest(architecture=architecture):
                scores = model.score_sequence(rows)
                warmup = 7 if architecture == 'sequential-autoencoder' else 1
                self.assertEqual(len(scores), len(rows))
                self.assertEqual(scores[:warmup], [None] * warmup)
                self.assertTrue(all(
                    value is not None and math.isfinite(value) and value >= 0
                    for value in scores[warmup:]
                ))
                if architecture == 'sequential-autoencoder':
                    with self.assertRaises(TypeError):
                        model.predict_sequence(rows)
                    continue
                predictions = model.predict_sequence(rows)
                self.assertEqual(len(predictions), len(rows))
                self.assertIsNone(predictions[0])
                for prediction, score in zip(predictions[1:], scores[1:]):
                    self.assertIsNotNone(prediction)
                    for field in ('location', 'scale', 'z_scores'):
                        values = getattr(prediction, field)
                        self.assertEqual(set(values), set(FEATURE_NAMES))
                        self.assertTrue(all(math.isfinite(value) for value in values.values()))
                    self.assertTrue(all(value > 0 for value in prediction.scale.values()))
                    self.assertEqual(prediction.surprise, score)

    def test_repeated_training_is_deterministic_within_this_runtime(self) -> None:
        query = synthetic_rows(20, 'synthetic-query', 0.2)
        for architecture, original in self.models.items():
            with self.subTest(architecture=architecture):
                repeated = candidate(architecture).fit(training_sequences())
                self.assertEqual(repeated.provenance(), original.provenance())
                self.assert_scores_equal(
                    repeated.score_sequence(query), original.score_sequence(query),
                )

    def test_future_inputs_cannot_change_fixed_model_prefix_outputs(self) -> None:
        rows = synthetic_rows(24, 'synthetic-query', 0.2)
        cutoff = 14
        changed = copy.deepcopy(rows)
        for row in changed[cutoff:]:
            for field in ('context', 'features'):
                for name in row[field]:
                    row[field][name] += 100.0
        for architecture, model in self.models.items():
            with self.subTest(architecture=architecture):
                full = model.score_sequence(rows)
                self.assert_scores_equal(model.score_sequence(rows[:cutoff]), full[:cutoff])
                self.assert_scores_equal(model.score_sequence(changed)[:cutoff], full[:cutoff])
                if architecture in STUDENT_T_ARCHITECTURES:
                    self.assert_predictions_equal(
                        model.predict_sequence(rows[:cutoff]),
                        model.predict_sequence(rows)[:cutoff],
                    )

    def test_student_t_location_and_scale_do_not_use_current_observed_target(self) -> None:
        rows = synthetic_rows(20, 'synthetic-query', 0.2)
        target = 12
        changed = copy.deepcopy(rows)
        for name in FEATURE_NAMES:
            changed[target]['features'][name] += 0.2
        for architecture in STUDENT_T_ARCHITECTURES:
            with self.subTest(architecture=architecture):
                before = self.models[architecture].predict_sequence(rows)[target]
                after = self.models[architecture].predict_sequence(changed)[target]
                self.assertIsNotNone(before)
                self.assertIsNotNone(after)
                for field in ('location', 'scale'):
                    self.assert_scores_equal(
                        [getattr(before, field)[name] for name in FEATURE_NAMES],
                        [getattr(after, field)[name] for name in FEATURE_NAMES],
                    )
                self.assertNotEqual(before.surprise, after.surprise)

    def test_missing_invalid_or_untrusted_rows_reset_all_temporal_state(self) -> None:
        mutations = {
            'false-quality': lambda row: row.update(quality_ok=False),
            'null-quality': lambda row: row.update(quality_ok=None),
            'missing-quality': lambda row: row.pop('quality_ok'),
            'numeric-quality': lambda row: row.update(quality_ok=1),
            'missing-feature': lambda row: row['features'].pop(FEATURE_NAMES[0]),
            'nan-feature': lambda row: row['features'].update({FEATURE_NAMES[0]: float('nan')}),
            'infinite-feature': lambda row: row['features'].update({FEATURE_NAMES[0]: float('inf')}),
            'boolean-feature': lambda row: row['features'].update({FEATURE_NAMES[0]: True}),
            'string-feature': lambda row: row['features'].update({FEATURE_NAMES[0]: '0.1'}),
            'missing-context': lambda row: row.pop('context'),
            'nan-context': lambda row: row['context'].update({CONTEXT_NAMES[0]: float('nan')}),
            'null-context-channel': lambda row: row['context'].update({CONTEXT_NAMES[0]: None}),
            'string-context': lambda row: row['context'].update({CONTEXT_NAMES[0]: '0.1'}),
        }
        boundary = 8
        for mutation_name, mutate in mutations.items():
            rows = synthetic_rows(24, 'synthetic-query', 0.2)
            mutate(rows[boundary])
            for architecture, model in self.models.items():
                with self.subTest(architecture=architecture, invalid=mutation_name):
                    actual = model.score_sequence(rows)
                    self.assertEqual(len(actual), len(rows))
                    self.assertIsNone(actual[boundary])
                    self.assert_scores_equal(
                        actual[:boundary], model.score_sequence(rows[:boundary]),
                    )
                    self.assert_scores_equal(
                        actual[boundary + 1:], model.score_sequence(rows[boundary + 1:]),
                    )

    def test_elapsed_and_index_gaps_reset_to_independent_suffix(self) -> None:
        boundary = 10
        by_index = synthetic_rows(26, 'synthetic-query', 0.2)
        for row in by_index[boundary:]:
            row['index'] += 1
        by_time = synthetic_rows(26, 'synthetic-query', 0.2)
        shift_times(by_time, boundary, timedelta(hours=1, microseconds=1))
        for reason, rows in (('index-gap', by_index), ('elapsed-gap', by_time)):
            for architecture, model in self.models.items():
                with self.subTest(architecture=architecture, boundary=reason):
                    actual = model.score_sequence(rows)
                    self.assert_scores_equal(
                        actual[:boundary], model.score_sequence(rows[:boundary]),
                    )
                    self.assert_scores_equal(
                        actual[boundary:], model.score_sequence(rows[boundary:]),
                    )

    def test_declared_gap_boundary_is_inclusive(self) -> None:
        normal = synthetic_rows(24, 'synthetic-query', 0.2)
        at_limit = copy.deepcopy(normal)
        shift_times(at_limit, 10, timedelta(hours=1))
        for architecture, model in self.models.items():
            with self.subTest(architecture=architecture):
                self.assert_scores_equal(
                    model.score_sequence(at_limit), model.score_sequence(normal),
                )
                self.assertIsNotNone(model.score_sequence(at_limit)[10])

    def test_training_boundaries_equal_explicit_independent_sequences(self) -> None:
        source = synthetic_rows(52, 'synthetic-segmented', 0.4)
        source[16]['features'].pop(FEATURE_NAMES[0])
        for row in source[34:]:
            row['index'] += 1
        shift_times(source, 34, timedelta(hours=3))
        joined = [source, training_sequences()[1]]
        separate = [source[:16], source[17:34], source[34:], training_sequences()[1]]
        query = synthetic_rows(20, 'synthetic-query', 0.2)
        for architecture in ARCHITECTURES:
            with self.subTest(architecture=architecture):
                first = candidate(architecture).fit(joined)
                second = candidate(architecture).fit(separate)
                self.assert_scores_equal(first.score_sequence(query), second.score_sequence(query))

    def test_order_and_identity_errors_are_rejected_before_execution(self) -> None:
        mutations = {
            'duplicate-time': lambda rows: rows[3].update(epoch_utc=rows[2]['epoch_utc']),
            'decreasing-time': lambda rows: rows[3].update(epoch_utc=rows[1]['epoch_utc']),
            'duplicate-index': lambda rows: rows[3].update(index=rows[2]['index']),
            'decreasing-index': lambda rows: rows[3].update(index=rows[1]['index']),
            'missing-index': lambda rows: rows[3].pop('index'),
            'boolean-index': lambda rows: rows[3].update(index=True),
            'negative-index': lambda rows: rows[3].update(index=-1),
            'fractional-index': lambda rows: rows[3].update(index=3.5),
            'mixed-object': lambda rows: rows[3].update(object_id='another-object'),
            'mixed-case': lambda rows: rows[3].update(case_id='another-case'),
            'missing-object': lambda rows: rows[3].pop('object_id'),
            'blank-case': lambda rows: rows[3].update(case_id=' '),
            'missing-time': lambda rows: rows[3].pop('epoch_utc'),
            'zone-free-time': lambda rows: rows[3].update(epoch_utc='2026-01-01T03:00:00'),
            'invalid-calendar': lambda rows: rows[3].update(epoch_utc='2026-02-30T03:00:00Z'),
            'excess-precision': lambda rows: rows[3].update(epoch_utc='2026-01-01T03:00:00.0000001Z'),
        }
        for name, mutate in mutations.items():
            rows = synthetic_rows(32, 'synthetic-query', 0.2)
            mutate(rows)
            for architecture in ARCHITECTURES:
                with self.subTest(architecture=architecture, invalid=name):
                    with self.assertRaises(ValueError):
                        self.models[architecture].score_sequence(rows)
                    with self.assertRaises(ValueError):
                        candidate(architecture).fit([rows])
        reverse = list(reversed(synthetic_rows(32)))
        for architecture in ARCHITECTURES:
            with self.subTest(architecture=architecture, invalid='reversed-sequence'):
                with self.assertRaises(ValueError):
                    self.models[architecture].score_sequence(reverse)

    def test_empty_all_invalid_and_insufficient_training_are_explicit(self) -> None:
        invalid = synthetic_rows(12)
        for row in invalid:
            row['quality_ok'] = False
        for architecture, model in self.models.items():
            with self.subTest(architecture=architecture):
                self.assertEqual(model.score_sequence([]), [])
                self.assertEqual(model.score_sequence(invalid), [None] * len(invalid))
                for sequences in ([], [invalid], [synthetic_rows(2)]):
                    with self.assertRaises(ValueError):
                        candidate(architecture).fit(sequences)
                with self.assertRaises(RuntimeError):
                    candidate(architecture).score_sequence(synthetic_rows(12))

    def test_transformer_1024_positions_fit_and_infer_without_truncation(self) -> None:
        rows = synthetic_rows(1024, 'synthetic-boundary', 0.2)
        model = candidate('transformer', epochs=1).fit([rows])
        scores = model.score_sequence(rows)
        self.assertEqual(len(scores), 1024)
        self.assertIsNone(scores[0])
        self.assertTrue(all(value is not None and math.isfinite(value) for value in scores[1:]))

    def test_transformer_1025_positions_reject_before_tensor_allocation(self) -> None:
        rows = synthetic_rows(1025, 'synthetic-overlength', 0.2)
        with patch.object(torch, 'tensor', side_effect=AssertionError('allocated before validation')):
            with patch.object(torch, 'zeros', side_effect=AssertionError('allocated before validation')):
                with self.assertRaisesRegex(ValueError, '1024'):
                    candidate('transformer').fit([rows])
                with self.assertRaisesRegex(ValueError, '1024'):
                    self.models['transformer'].score_sequence(rows)

    def test_long_history_with_real_boundaries_keeps_all_output_positions(self) -> None:
        rows = synthetic_rows(1057, 'synthetic-long', 0.2)
        rows[512]['quality_ok'] = False
        model = candidate('transformer', epochs=1).fit([rows])
        actual = model.score_sequence(rows)
        self.assertEqual(len(actual), len(rows))
        self.assertIsNone(actual[512])
        self.assert_scores_equal(actual[:512], model.score_sequence(rows[:512]))
        self.assert_scores_equal(actual[513:], model.score_sequence(rows[513:]))
        self.assertIsNotNone(actual[-1])

    def test_inputs_are_not_reordered_or_modified(self) -> None:
        train = training_sequences()
        before_train = copy.deepcopy(train)
        rows = synthetic_rows(20, 'synthetic-query', 0.2)
        before_rows = copy.deepcopy(rows)
        for architecture, model in self.models.items():
            with self.subTest(architecture=architecture):
                candidate(architecture, epochs=1).fit(train)
                model.score_sequence(rows)
                self.assertEqual(train, before_train)
                self.assertEqual(rows, before_rows)

    def test_selective_and_comparison_interfaces_use_versioned_models(self) -> None:
        references = [row for sequence in training_sequences() for row in sequence]
        support = SupportModel(k=3, min_reference_satellites=3).fit(references)
        rows = synthetic_rows(24, 'synthetic-query', 0.2)
        rows[8]['features'].pop(FEATURE_NAMES[0])
        for architecture in ('gru', 'tcn', 'transformer'):
            with self.subTest(pipeline='selective', architecture=architecture):
                model = self.models[architecture]
                detector = SelectiveDetector(
                    model, support, support_thresholds={'LEO': 1e6},
                    event_threshold=1e6,
                )
                scored = detector.score_rows(rows)
                expected = model.score_sequence(rows)
                self.assertEqual(len(scored), len(rows))
                for row, score in zip(scored, expected):
                    if score is None:
                        self.assertEqual(row.status, 'abstain')
                        self.assertIsNone(row.surprise)
                    else:
                        self.assertEqual(row.status, 'scored')
                        self.assertEqual(row.surprise, score)
                self.assertIn(NEURAL_EXECUTION_VERSION, detector.describe()['backbone'])
        for architecture in STUDENT_T_ARCHITECTURES:
            with self.subTest(pipeline='comparison', architecture=architecture):
                method = ModelScoreMethod(candidate(architecture)).fit(training_sequences())
                self.assert_scores_equal(
                    method.score_sequence(rows), self.models[architecture].score_sequence(rows),
                )
                self.assertGreater(method.parameter_count, 0)
                self.assertIn(NEURAL_EXECUTION_VERSION, method.name)

    def test_constructor_rejects_unimplemented_or_invalid_configuration(self) -> None:
        changes = [
            {'max_gap_seconds': value}
            for value in (0, -1, True, '7200', float('nan'), float('inf'), 0.0000001)
        ] + [
            {'hidden_size': 0}, {'hidden_size': True}, {'hidden_size': 8.5},
            {'layers': 0}, {'layers': True}, {'epochs': 0}, {'epochs': False},
            {'epochs': 1.5}, {'learning_rate': 0}, {'learning_rate': float('nan')},
            {'learning_rate': True}, {'seed': -1}, {'seed': True},
            {'seed': 1.5}, {'seed': 2 ** 63},
        ]
        for architecture in ARCHITECTURES:
            for change in changes:
                with self.subTest(architecture=architecture, configuration=change):
                    with self.assertRaises(ValueError):
                        candidate(architecture, **change)
            model = candidate(architecture)
            self.assertEqual(model.parameter_count, 0)
            with self.assertRaises(RuntimeError):
                model.provenance()
        with self.assertRaises(ValueError):
            candidate('transformer', hidden_size=7)
        with self.assertRaises(ValueError):
            candidate('unimplemented')
        for change in ({'seed': SEED + 1}, {'layers': 2}, {'learning_rate': 1e-3}):
            with self.subTest(architecture='sequential-autoencoder', configuration=change):
                with self.assertRaises(ValueError):
                    candidate('sequential-autoencoder', **change)

    def test_short_training_segments_do_not_contaminate_normalisation(self) -> None:
        query = synthetic_rows(20, 'synthetic-query', 0.2)
        for architecture in ARCHITECTURES:
            short_length = 7 if architecture == 'sequential-autoencoder' else 1
            short = synthetic_rows(short_length, 'synthetic-short', 0.2)
            for row in short:
                for field in ('context', 'features'):
                    for name in row[field]:
                        row[field][name] += 1e6
            with self.subTest(architecture=architecture):
                model = candidate(architecture).fit([short, *training_sequences()])
                original = self.models[architecture]
                self.assert_scores_equal(model.score_sequence(query), original.score_sequence(query))
                for key in ('weights_sha256', 'normalization_sha256', 'state_sha256'):
                    self.assertEqual(model.provenance()[key], original.provenance()[key])
                record = model.provenance()['training']
                self.assertEqual(record['discarded_short_segments'], 1)
                self.assertEqual(record['discarded_short_rows'], short_length)
                self.assertEqual(record['training_rows'], 75)
                self.assertEqual(record['training_segments'], 3)
                self.assertNotEqual(record['input_sha256'], original.provenance()['training']['input_sha256'])
                isolated = [synthetic_rows(short_length, f'synthetic-isolated-{i}') for i in range(24)]
                with self.assertRaises(ValueError):
                    candidate(architecture).fit(isolated)

    def test_fit_restores_caller_random_state_flags_and_default_device(self) -> None:
        enabled = torch.are_deterministic_algorithms_enabled()
        warn_only = torch.is_deterministic_algorithms_warn_only_enabled()
        random_state = torch.get_rng_state().clone()
        try:
            torch.use_deterministic_algorithms(False, warn_only=True)
            for architecture in ARCHITECTURES:
                with self.subTest(architecture=architecture):
                    with torch.device('meta'):
                        model = candidate(architecture, epochs=1).fit(training_sequences())
                        scores = model.score_sequence(synthetic_rows(20, 'synthetic-query', 0.2))
                        self.assertEqual(torch.empty(0).device.type, 'meta')
                    self.assertTrue(torch.equal(torch.get_rng_state(), random_state))
                    self.assertFalse(torch.are_deterministic_algorithms_enabled())
                    self.assertTrue(torch.is_deterministic_algorithms_warn_only_enabled())
                    self.assertTrue(any(score is not None and math.isfinite(score) for score in scores))
                    self.assertEqual(model.provenance()['runtime']['device'], 'cpu')
        finally:
            torch.use_deterministic_algorithms(enabled, warn_only=warn_only)

    def test_provenance_is_json_finite_stable_and_versioned(self) -> None:
        rows = synthetic_rows(20, 'synthetic-query', 0.2)
        for architecture, model in self.models.items():
            with self.subTest(architecture=architecture):
                before = model.provenance()
                serialised = json.dumps(before, allow_nan=False, sort_keys=True)
                self.assertEqual(before['execution_version'], NEURAL_EXECUTION_VERSION)
                self.assertEqual(before['architecture'], architecture)
                self.assertEqual(before['model_name'], model.name)
                self.assertEqual(before['seed'], SEED)
                self.assertEqual(before['parameter_count'], model.parameter_count)
                hyperparameters = before['hyperparameters']
                self.assertEqual(hyperparameters['seed'], SEED)
                self.assertEqual(hyperparameters['epochs'], 2)
                self.assertEqual(hyperparameters['hidden_size'], 8)
                self.assertEqual(hyperparameters['layers'], 1)
                self.assertEqual(hyperparameters['learning_rate'], 3e-3)
                self.assertEqual(
                    hyperparameters['effective_learning_rate'],
                    1e-3 if architecture == 'transformer' else 3e-3,
                )
                runtime = before['runtime']
                self.assertEqual(runtime['device'], 'cpu')
                self.assertEqual(runtime['pytorch'], torch.__version__)
                self.assertEqual(runtime['torch_threads'], 1)
                self.assertEqual(runtime['torch_interop_threads'], 1)
                self.assertTrue(runtime['deterministic_training'])
                policy = before['sequence_policy']
                self.assertEqual(policy['max_gap_microseconds'], 7_200_000_000)
                self.assertEqual(
                    policy['max_segment_rows'], 1024 if architecture == 'transformer' else None,
                )
                self.assertEqual(
                    policy['warmup_rows'], 7 if architecture == 'sequential-autoencoder' else 1,
                )
                training = before['training']
                self.assertEqual(training['input_rows'], 75)
                self.assertEqual(training['input_sequences'], 3)
                self.assertEqual(training['training_segments'], 3)
                self.assertEqual(training['training_rows'], 75)
                self.assertEqual(training['rejected_rows'], 0)
                self.assertEqual(
                    training['training_windows'],
                    54 if architecture == 'sequential-autoencoder' else None,
                )
                for digest in (
                    before['weights_sha256'], before['normalization_sha256'], before['state_sha256'],
                    training['input_sha256'], *before['source_sha256'].values(),
                ):
                    self.assertRegex(digest, r'^[0-9a-f]{64}$')
                self.assertEqual(set(before['source_sha256']), {
                    'research/neural_execution.py', 'research/event_matching.py',
                    'research/selective_v1/core.py', 'research/selective_v1/models.py',
                    'research/comparison_v1/run_comparison.py',
                })
                model.score_sequence(rows)
                self.assertEqual(model.provenance(), before)
                detached = model.provenance()
                detached['hyperparameters']['seed'] = 0
                self.assertEqual(model.provenance(), before)
                # Runtime evidence must not include a workstation location.
                self.assertNotIn('/Users/', serialised)
                self.assertNotIn('/home/', serialised)
                self.assertNotIn('\\Users\\', serialised)


def run_suite(stream=None):
    """Return unittest results and per-architecture evidence for the bounded runner."""
    if stream is None:
        stream = sys.stderr
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NeuralExecutionTests)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return result, copy.deepcopy(MODEL_REPORTS)


def main() -> int:
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        # An embedding runner may already have fixed the inter-op worker count.
        if torch.get_num_interop_threads() != 1:
            raise
    result, models = run_suite()
    print(json.dumps({
        'schema': 'smd-neural-smoke-tests-v1',
        'fixture_version': FIXTURE_VERSION,
        'seed': SEED,
        'tests_run': result.testsRun,
        'skipped': len(result.skipped),
        'successful': result.wasSuccessful(),
        'models': models,
    }, sort_keys=True, allow_nan=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
