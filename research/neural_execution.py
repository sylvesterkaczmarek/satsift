"""Versioned CPU execution boundary for the retained neural implementations.

This opt-in interface uses the existing networks and objectives with explicit
ordering, admission, gap and length rules. It does not replace the historical
factories, calibrate an operating point or reopen the completed experiment.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from numbers import Real
from pathlib import Path

from research.event_matching import parse_truth_timestamp_us
from research.selective_v1.core import (
    CONTEXT_NAMES, FEATURE_NAMES, DistributionPrediction,
)

NEURAL_EXECUTION_VERSION = 'neural-execution-v1'
SUPPORTED_ARCHITECTURES = ('gru', 'tcn', 'transformer', 'lstm', 'sequential-autoencoder')
TRANSFORMER_MAX_SEGMENT_ROWS = 1024
AUTOENCODER_WINDOW = 8
_SOURCE_PATHS = (
    'research/neural_execution.py',
    'research/event_matching.py',
    'research/selective_v1/core.py',
    'research/selective_v1/models.py',
    'research/comparison_v1/run_comparison.py',
)


@dataclass(frozen=True)
class _Configuration:
    architecture: str
    hidden_size: int
    layers: int
    epochs: int
    learning_rate: float
    seed: int
    max_gap_microseconds: int


def _positive_integer(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f'{name} must be a positive integer')
    return value


def _finite_real(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _canonical_hash(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _source_hashes():
    root = Path(__file__).resolve().parents[1]
    return {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in _SOURCE_PATHS
    }


class NeuralExecutionModel:
    """CPU-only, segmented execution with explicit model and input provenance.

    All architectures admit the same complete feature/context rows. Invalid
    numeric content or a missing/false quality flag creates an abstention and
    resets sequence state. Malformed identities, indices or timestamps reject
    the sequence because its order cannot be established.

    Conditional models warm up for one row; the autoencoder needs eight rows
    and reconstructs the current endpoint. Predictions retain input positions.
    """

    def __init__(
        self, architecture, *, max_gap_seconds, hidden_size=32, layers=None,
        epochs=120, learning_rate=3e-3, seed=3404,
    ):
        if architecture not in SUPPORTED_ARCHITECTURES:
            raise ValueError('unsupported neural architecture')
        hidden_size = _positive_integer(hidden_size, 'hidden_size')
        epochs = _positive_integer(epochs, 'epochs')
        if layers is None:
            layers = 1 if architecture == 'sequential-autoencoder' else 2
        layers = _positive_integer(layers, 'layers')
        if architecture == 'transformer' and hidden_size % 2:
            raise ValueError('Transformer hidden_size must be divisible by two')
        if type(seed) is not int or not 0 <= seed < 2 ** 63:
            raise ValueError('seed must be an integer in [0, 2**63)')
        learning_rate = _finite_real(learning_rate)
        if learning_rate is None or learning_rate <= 0:
            raise ValueError('learning_rate must be finite and positive')
        gap = _finite_real(max_gap_seconds)
        if gap is None or gap <= 0:
            raise ValueError('max_gap_seconds must be finite and positive')
        exact_gap = Decimal(str(max_gap_seconds)) * 1_000_000
        if exact_gap != exact_gap.to_integral_value() or exact_gap < 1:
            raise ValueError('max_gap_seconds must specify whole microseconds')
        if architecture == 'sequential-autoencoder':
            if seed != 3404 or learning_rate != 3e-3 or layers != 1:
                raise ValueError('retained autoencoder requires seed 3404, learning_rate 0.003 and layers 1')
        self._configuration = _Configuration(
            architecture, hidden_size, layers, epochs, learning_rate, seed, int(exact_gap),
        )
        self._model = None
        self._provenance = None

    @property
    def architecture(self):
        return self._configuration.architecture

    @property
    def name(self):
        return f'{self.architecture}@{NEURAL_EXECUTION_VERSION}'

    @property
    def parameter_count(self):
        return int(getattr(self._model, 'parameter_count', 0))

    def _prepare(self, rows):
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise ValueError('a sequence must be a list or tuple of feature rows')
        segments = []
        semantic_rows = []
        current = []
        current_start = None
        previous_epoch = previous_index = None
        identity = None
        admitted = 0
        for position, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise ValueError('each feature row must be an object')
            case_id, object_id = row.get('case_id'), row.get('object_id')
            if any(not isinstance(value, str) or not value.strip() for value in (case_id, object_id)):
                raise ValueError('each row requires nonempty string case_id and object_id')
            if identity is None:
                identity = (case_id, object_id)
            elif identity != (case_id, object_id):
                raise ValueError('a sequence must contain one case and object identity')
            index = row.get('index')
            if type(index) is not int or index < 0:
                raise ValueError('each row requires a nonnegative integer index')
            try:
                epoch = parse_truth_timestamp_us(row.get('epoch_utc'))
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError('each row requires a valid explicit-zone microsecond timestamp') from exc
            if previous_epoch is not None and (epoch <= previous_epoch or index <= previous_index):
                raise ValueError('sequence timestamps and indices must be strictly increasing')
            boundary = previous_epoch is not None and (
                index != previous_index + 1
                or epoch - previous_epoch > self._configuration.max_gap_microseconds
            )
            previous_epoch, previous_index = epoch, index
            converted = {}
            good = row.get('quality_ok') is True
            for field, names in (('features', FEATURE_NAMES), ('context', CONTEXT_NAMES)):
                supplied = row.get(field)
                values = {
                    name: _finite_real(supplied.get(name)) if isinstance(supplied, Mapping) else None
                    for name in names
                }
                converted[field] = values
                good = good and all(value is not None for value in values.values())
            semantic = {
                'case_id': case_id, 'object_id': object_id, 'index': index,
                'epoch_microseconds': epoch, 'admitted': good,
            }
            if good:
                semantic.update(converted)
            semantic_rows.append(semantic)
            if boundary or not good:
                if current:
                    segments.append((current_start, current))
                current = []
                current_start = None
            if good:
                if current_start is None:
                    current_start = position
                current.append({
                    'case_id': case_id, 'object_id': object_id, 'index': index,
                    'epoch_utc': row['epoch_utc'], 'quality_ok': True, **converted,
                })
                admitted += 1
        if current:
            segments.append((current_start, current))
        if self.architecture == 'transformer' and any(
            len(segment) > TRANSFORMER_MAX_SEGMENT_ROWS for _, segment in segments
        ):
            raise ValueError('Transformer trusted segments must contain at most 1024 rows; no truncation is performed')
        return segments, semantic_rows, admitted

    def _new_model(self):
        config = self._configuration
        if self.architecture in {'lstm', 'sequential-autoencoder'}:
            from research.comparison_v1.run_comparison import (
                LSTMStudentTModel, SequentialAutoencoder,
            )
            if self.architecture == 'sequential-autoencoder':
                model = SequentialAutoencoder()
                model.hidden = config.hidden_size
                model.epochs = config.epochs
                return model
            model = LSTMStudentTModel()
            model.hidden_size = config.hidden_size
            model.layers = config.layers
            model.epochs = config.epochs
            model.learning_rate = config.learning_rate
            model.seed = config.seed
            return model
        from research.selective_v1.models import TorchStudentTModel
        return TorchStudentTModel(
            self.architecture, hidden_size=config.hidden_size, layers=config.layers,
            epochs=config.epochs, learning_rate=config.learning_rate, seed=config.seed,
        )

    def fit(self, sequences):
        """Fit fresh state atomically; short segments never enter normalization."""
        if not isinstance(sequences, Sequence) or isinstance(sequences, (str, bytes)):
            raise ValueError('training sequences must be a list or tuple')
        prepared = [self._prepare(rows) for rows in sequences]
        all_segments = [segment for segments, _, _ in prepared for _, segment in segments]
        minimum_length = AUTOENCODER_WINDOW if self.architecture == 'sequential-autoencoder' else 2
        segments = [segment for segment in all_segments if len(segment) >= minimum_length]
        training_rows = sum(map(len, segments))
        if self.architecture == 'sequential-autoencoder':
            training_windows = sum(len(segment) - AUTOENCODER_WINDOW + 1 for segment in segments)
            if training_windows < 8:
                raise ValueError('at least eight complete autoencoder training windows are required')
        else:
            training_windows = None
            if training_rows < 24:
                raise ValueError('at least 24 usable conditional-model training rows are required')
        import numpy
        import torch

        model = self._new_model()
        deterministic_before = torch.are_deterministic_algorithms_enabled()
        warn_only_before = torch.is_deterministic_algorithms_warn_only_enabled()
        try:
            torch.use_deterministic_algorithms(True, warn_only=False)
            with torch.device('cpu'), torch.random.fork_rng(devices=[]):
                model.fit(segments)
                if not torch.are_deterministic_algorithms_enabled() or torch.is_deterministic_algorithms_warn_only_enabled():
                    raise RuntimeError('deterministic neural training was not enabled')
        finally:
            torch.use_deterministic_algorithms(deterministic_before, warn_only=warn_only_before)
        network = model.model if self.architecture == 'sequential-autoencoder' else model._model
        state = network.state_dict()
        weights_hash = hashlib.sha256()
        for key, tensor in sorted(state.items()):
            if tensor.device.type != 'cpu' or not torch.isfinite(tensor).all():
                raise RuntimeError('trained neural state must contain finite CPU tensors')
            weights_hash.update(json.dumps(
                [key, str(tensor.dtype), list(tensor.shape)], separators=(',', ':'),
            ).encode('utf-8'))
            weights_hash.update(tensor.detach().contiguous().numpy().tobytes(order='C'))
        if self.architecture == 'sequential-autoencoder':
            normalization = {'centres': model.centres, 'scales': model.scales}
        else:
            normalization = {
                key: getattr(model, key)
                for key in ('context_centres', 'context_scales', 'feature_centres', 'feature_scales')
            }
        for key, values in normalization.items():
            if any(
                not math.isfinite(value) or ('scales' in key and value <= 0)
                for value in values.values()
            ):
                raise RuntimeError('trained normalization must be finite with positive scales')
        config = asdict(self._configuration)
        config.pop('architecture')
        config.pop('max_gap_microseconds')
        config['effective_learning_rate'] = min(config['learning_rate'], 1e-3) if self.architecture == 'transformer' else config['learning_rate']
        config['window_rows'] = AUTOENCODER_WINDOW if self.architecture == 'sequential-autoencoder' else None
        input_rows = sum(len(rows) for rows in sequences)
        admitted = sum(count for _, _, count in prepared)
        provenance = {
            'execution_version': NEURAL_EXECUTION_VERSION,
            'architecture': self.architecture,
            'model_name': self.name,
            'seed': self._configuration.seed,
            'hyperparameters': config,
            'sequence_policy': {
                'timestamp_format': 'explicit-zone ISO timestamp with at most six fractional digits',
                'strictly_increasing': ['epoch_utc', 'index'],
                'single_identity': ['case_id', 'object_id'],
                'admission': 'quality_ok is true and every feature/context value is a finite real number',
                'gap_reset': 'invalid row, nonconsecutive index or elapsed time strictly above max_gap_microseconds',
                'max_gap_microseconds': self._configuration.max_gap_microseconds,
                'max_segment_rows': TRANSFORMER_MAX_SEGMENT_ROWS if self.architecture == 'transformer' else None,
                'overlength': 'reject before network execution; no truncation',
                'warmup_rows': AUTOENCODER_WINDOW - 1 if self.architecture == 'sequential-autoencoder' else 1,
                'causal_target': 'current endpoint reconstruction from a trailing eight-row window' if self.architecture == 'sequential-autoencoder' else 'current context and previous observed features',
                'context_names': list(CONTEXT_NAMES), 'feature_names': list(FEATURE_NAMES),
            },
            'training': {
                'input_sequences': len(sequences), 'input_rows': input_rows,
                'accepted_rows': admitted, 'rejected_rows': input_rows - admitted,
                'segments': len(all_segments), 'training_segments': len(segments),
                'training_rows': training_rows,
                'discarded_short_segments': len(all_segments) - len(segments),
                'discarded_short_rows': admitted - training_rows,
                'minimum_training_segment_rows': minimum_length,
                'training_windows': training_windows,
                'normalization_scope': 'usable training segments only',
                'input_sha256': _canonical_hash([semantic for _, semantic, _ in prepared]),
                'digest_scope': 'ordered identities, integer UTC epochs, indices, admission and admitted feature/context values',
            },
            'parameter_count': int(model.parameter_count),
            'weights_sha256': weights_hash.hexdigest(),
            'normalization_sha256': _canonical_hash(normalization),
            'state_sha256': _canonical_hash({
                'weights': weights_hash.hexdigest(), 'normalization': normalization,
            }),
            'source_sha256': _source_hashes(),
            'runtime': {
                'python': platform.python_version(),
                'python_implementation': platform.python_implementation(),
                'numpy': numpy.__version__, 'pytorch': torch.__version__,
                'system': sys.platform, 'machine': platform.machine(), 'device': 'cpu',
                'torch_threads': torch.get_num_threads(),
                'torch_interop_threads': torch.get_num_interop_threads(),
                'deterministic_training': True,
            },
            'claim': 'execution provenance only; no detection-performance or calibrated-risk claim',
        }
        _canonical_hash(provenance)
        self._model, self._provenance = model, provenance
        return self

    def _require_fitted(self):
        if self._model is None:
            raise RuntimeError('fit must be called before neural inference or provenance')

    @staticmethod
    def _validate_prediction(prediction):
        if not isinstance(prediction, DistributionPrediction):
            raise RuntimeError('conditional model returned an invalid prediction')
        for field in ('location', 'scale', 'z_scores'):
            values = getattr(prediction, field)
            if set(values) != set(FEATURE_NAMES) or any(
                _finite_real(value) is None or (field == 'scale' and value <= 0)
                or (field == 'z_scores' and value < 0)
                for value in values.values()
            ):
                raise RuntimeError('conditional model returned non-finite or invalid distribution values')
        if _finite_real(prediction.surprise) is None or prediction.surprise < 0:
            raise RuntimeError('conditional model returned a non-finite or invalid surprise')

    def predict_sequence(self, rows):
        if self.architecture == 'sequential-autoencoder':
            raise TypeError('the autoencoder provides scores, not conditional distributions')
        self._require_fitted()
        segments, _, _ = self._prepare(rows)
        import torch
        output = [None] * len(rows)
        for start, segment in segments:
            with torch.device('cpu'):
                predictions = self._model.predict_sequence(segment)
            if len(predictions) != len(segment):
                raise RuntimeError('conditional model returned the wrong prediction length')
            for offset, prediction in enumerate(predictions):
                if offset == 0:
                    if prediction is not None:
                        raise RuntimeError('conditional model did not abstain during warmup')
                else:
                    self._validate_prediction(prediction)
                output[start + offset] = prediction
        return output

    def score_sequence(self, rows):
        self._require_fitted()
        if self.architecture != 'sequential-autoencoder':
            return [
                prediction.surprise if prediction is not None else None
                for prediction in self.predict_sequence(rows)
            ]
        segments, _, _ = self._prepare(rows)
        import torch
        output = [None] * len(rows)
        for start, segment in segments:
            with torch.device('cpu'):
                scores = self._model.score_sequence(segment)
            if len(scores) != len(segment):
                raise RuntimeError('autoencoder returned the wrong score length')
            for offset, score in enumerate(scores):
                if offset < AUTOENCODER_WINDOW - 1:
                    if score is not None:
                        raise RuntimeError('autoencoder did not abstain during warmup')
                elif _finite_real(score) is None or score < 0:
                    raise RuntimeError('autoencoder returned a non-finite or invalid score')
                output[start + offset] = score
        return output

    def provenance(self):
        """Return a detached JSON-safe record without local paths or raw rows."""
        self._require_fitted()
        return json.loads(json.dumps(self._provenance, allow_nan=False))
