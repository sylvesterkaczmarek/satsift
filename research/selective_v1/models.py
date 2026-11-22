#!/usr/bin/env python3
from __future__ import annotations

from math import exp, isfinite, log1p
from statistics import median
from typing import Iterable, Sequence

from .core import (
    CONTEXT_NAMES,
    FEATURE_NAMES,
    DistributionPrediction,
    finite_number,
    robust_scale,
    student_t_surprise,
)


def _solve_ridge(x_rows: Sequence[Sequence[float]], y: Sequence[float], ridge: float, weights=None) -> list[float]:
    if not x_rows:
        raise ValueError('empty regression design')
    p = len(x_rows[0])
    if any(len(row) != p for row in x_rows):
        raise ValueError('inconsistent regression design')
    weights = [1.0] * len(x_rows) if weights is None else list(weights)
    a = [[0.0 for _ in range(p)] for _ in range(p)]
    b = [0.0 for _ in range(p)]
    for row, target, weight in zip(x_rows, y, weights):
        w = max(0.0, float(weight))
        for i in range(p):
            b[i] += w * row[i] * target
            for j in range(p):
                a[i][j] += w * row[i] * row[j]
    for i in range(1, p):
        a[i][i] += float(ridge)

    aug = [a[i][:] + [b[i]] for i in range(p)]
    for column in range(p):
        pivot = max(range(column, p), key=lambda row: abs(aug[row][column]))
        if abs(aug[pivot][column]) < 1e-12:
            aug[pivot][column] += 1e-8
        aug[column], aug[pivot] = aug[pivot], aug[column]
        divisor = aug[column][column]
        if abs(divisor) < 1e-15:
            raise ValueError('singular regression design')
        aug[column] = [value / divisor for value in aug[column]]
        for row in range(p):
            if row == column:
                continue
            factor = aug[row][column]
            if factor == 0.0:
                continue
            aug[row] = [left - factor * right for left, right in zip(aug[row], aug[column])]
    return [aug[i][-1] for i in range(p)]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


class RobustConditionalLinear:
    """Small non-neural conditional Student-t location/scale reference model.

    Location is fitted by Huber-style IRLS on robustly standardised causal context. A second robust
    regression predicts log absolute residual scale. The model is intentionally simple enough to be
    an auditable reference against which sequence models must justify their complexity.
    """

    name = 'robust-linear'

    def __init__(self, *, ridge: float = 1e-2, huber_c: float = 1.5, iterations: int = 6) -> None:
        self.ridge = float(ridge)
        self.huber_c = float(huber_c)
        self.iterations = int(iterations)
        self.context_centres: dict[str, float] = {}
        self.context_scales: dict[str, float] = {}
        self.location_beta: dict[str, list[float]] = {}
        self.scale_beta: dict[str, list[float]] = {}
        self.base_scale: dict[str, float] = {}
        self.fitted = False

    def _basis(self, row: dict) -> list[float] | None:
        context = row.get('context') or {}
        result = [1.0]
        for name in CONTEXT_NAMES:
            value = finite_number(context.get(name))
            if value is None:
                return None
            result.append((value - self.context_centres[name]) / self.context_scales[name])
        return result

    def fit(self, sequences: Sequence[Sequence[dict]]) -> 'RobustConditionalLinear':
        rows = [row for sequence in sequences for row in sequence if row.get('quality_ok') is not False]
        if len(rows) < max(24, len(CONTEXT_NAMES) + 4):
            raise ValueError('insufficient verified-quiet rows for robust linear model')
        for name in CONTEXT_NAMES:
            values = [float(row['context'][name]) for row in rows if finite_number((row.get('context') or {}).get(name)) is not None]
            if len(values) != len(rows):
                raise ValueError(f'missing context channel {name}')
            self.context_centres[name] = median(values)
            self.context_scales[name] = robust_scale(values, 1e-6)
        x_rows = [self._basis(row) for row in rows]
        if any(row is None for row in x_rows):
            raise ValueError('invalid context row')
        design = [list(row) for row in x_rows if row is not None]

        for feature in FEATURE_NAMES:
            y = [float(row['features'][feature]) for row in rows]
            weights = [1.0] * len(y)
            beta = _solve_ridge(design, y, self.ridge, weights)
            for _ in range(self.iterations):
                residuals = [target - _dot(x, beta) for x, target in zip(design, y)]
                scale = robust_scale(residuals, 1e-9)
                weights = [1.0 if abs(residual) <= self.huber_c * scale else (self.huber_c * scale / abs(residual)) for residual in residuals]
                beta = _solve_ridge(design, y, self.ridge, weights)
            residuals = [target - _dot(x, beta) for x, target in zip(design, y)]
            base = robust_scale(residuals, 1e-8)
            scale_target = [log1p(abs(residual) / base) for residual in residuals]
            scale_beta = _solve_ridge(design, scale_target, self.ridge)
            self.location_beta[feature] = beta
            self.scale_beta[feature] = scale_beta
            self.base_scale[feature] = base
        self.fitted = True
        return self

    def predict_sequence(self, rows: Sequence[dict]) -> list[DistributionPrediction | None]:
        if not self.fitted:
            raise RuntimeError('fit must be called before predict_sequence')
        output: list[DistributionPrediction | None] = []
        for row in rows:
            basis = self._basis(row)
            features = row.get('features') or {}
            if basis is None or not all(finite_number(features.get(name)) is not None for name in FEATURE_NAMES):
                output.append(None)
                continue
            location = {name: _dot(basis, self.location_beta[name]) for name in FEATURE_NAMES}
            scale = {}
            for name in FEATURE_NAMES:
                log_ratio = max(-2.0, min(3.0, _dot(basis, self.scale_beta[name])))
                scale[name] = max(1e-9, self.base_scale[name] * exp(log_ratio))
            output.append(student_t_surprise(features, location, scale, degrees_of_freedom=4.0))
        return output

    @property
    def parameter_count(self) -> int:
        p = len(CONTEXT_NAMES) + 1
        return 2 * len(FEATURE_NAMES) * p


def _robust_normalizer(rows: Iterable[dict], names: Sequence[str], field: str) -> tuple[dict[str, float], dict[str, float]]:
    centres: dict[str, float] = {}
    scales: dict[str, float] = {}
    material = list(rows)
    for name in names:
        values = [float((row.get(field) or {})[name]) for row in material]
        centres[name] = median(values)
        scales[name] = robust_scale(values, 1e-6 if field == 'context' else 1e-8)
    return centres, scales


class TorchStudentTModel:
    """Optional compact causal sequence model with a Student-t conditional objective.

    PyTorch is imported only when this class is fitted. Permanent repository CI therefore validates
    the selective framework without acquiring a heavy ML runtime, while the frozen model-selection
    workflow installs CPU PyTorch explicitly.
    """

    def __init__(
        self,
        architecture: str,
        *,
        hidden_size: int = 32,
        layers: int = 2,
        epochs: int = 120,
        learning_rate: float = 3e-3,
        seed: int = 3404,
    ) -> None:
        if architecture not in {'gru', 'tcn', 'transformer'}:
            raise ValueError('architecture must be gru, tcn, or transformer')
        self.architecture = architecture
        self.name = architecture
        self.hidden_size = int(hidden_size)
        self.layers = int(layers)
        self.epochs = int(epochs)
        self.learning_rate = float(learning_rate)
        self.seed = int(seed)
        self.context_centres: dict[str, float] = {}
        self.context_scales: dict[str, float] = {}
        self.feature_centres: dict[str, float] = {}
        self.feature_scales: dict[str, float] = {}
        self._model = None
        self._torch = None
        self._parameter_count = 0

    def _input_row(self, row: dict, previous: dict[str, float] | None) -> list[float]:
        context = row['context']
        values = [(float(context[name]) - self.context_centres[name]) / self.context_scales[name] for name in CONTEXT_NAMES]
        for name in FEATURE_NAMES:
            raw = 0.0 if previous is None else float(previous[name])
            values.append((raw - self.feature_centres[name]) / self.feature_scales[name] if previous is not None else 0.0)
        return values

    def _target_row(self, row: dict) -> list[float]:
        return [(float(row['features'][name]) - self.feature_centres[name]) / self.feature_scales[name] for name in FEATURE_NAMES]

    def _build_network(self, torch):
        nn = torch.nn
        F = torch.nn.functional
        input_size = len(CONTEXT_NAMES) + len(FEATURE_NAMES)
        output_size = 2 * len(FEATURE_NAMES)
        hidden = self.hidden_size
        layers = self.layers
        architecture = self.architecture

        if architecture == 'gru':
            class Net(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.input = nn.Linear(input_size, hidden)
                    self.gru = nn.GRU(hidden, hidden, num_layers=layers, batch_first=True)
                    self.head = nn.Linear(hidden, output_size)
                def forward(self, x, present):
                    z = torch.tanh(self.input(x))
                    z, _ = self.gru(z)
                    return self.head(z)
            return Net()

        if architecture == 'tcn':
            class CausalBlock(nn.Module):
                def __init__(self, dilation):
                    super().__init__()
                    self.dilation = dilation
                    self.conv = nn.Conv1d(hidden, hidden, kernel_size=3, dilation=dilation)
                    self.norm = nn.LayerNorm(hidden)
                def forward(self, x):
                    residual = x
                    pad = 2 * self.dilation
                    y = self.conv(F.pad(x, (pad, 0)))
                    y = torch.nn.functional.gelu(y)
                    y = y.transpose(1, 2)
                    y = self.norm(y)
                    return y.transpose(1, 2) + residual
            class Net(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.input = nn.Linear(input_size, hidden)
                    self.blocks = nn.ModuleList([CausalBlock(2 ** i) for i in range(layers)])
                    self.head = nn.Linear(hidden, output_size)
                def forward(self, x, present):
                    z = torch.tanh(self.input(x)).transpose(1, 2)
                    for block in self.blocks:
                        z = block(z)
                    return self.head(z.transpose(1, 2))
            return Net()

        heads = 4 if hidden % 4 == 0 else 2
        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.input = nn.Linear(input_size, hidden)
                self.position = nn.Embedding(1024, hidden)
                layer = nn.TransformerEncoderLayer(
                    d_model=hidden, nhead=heads, dim_feedforward=4 * hidden,
                    dropout=0.0, activation='gelu', batch_first=True, norm_first=True,
                )
                self.encoder = nn.TransformerEncoder(layer, num_layers=layers, norm=nn.LayerNorm(hidden), enable_nested_tensor=False)
                self.head = nn.Linear(hidden, output_size)
            def forward(self, x, present):
                length = x.shape[1]
                positions = torch.arange(length, device=x.device).unsqueeze(0)
                z = self.input(x) + self.position(positions)
                causal = torch.triu(torch.ones(length, length, device=x.device, dtype=torch.bool), diagonal=1)
                padding = ~present
                z = self.encoder(z, mask=causal, src_key_padding_mask=padding)
                return self.head(z)
        return Net()

    def fit(self, sequences: Sequence[Sequence[dict]]) -> 'TorchStudentTModel':
        rows = [row for sequence in sequences for row in sequence if row.get('quality_ok') is not False]
        if len(rows) < 24:
            raise ValueError('insufficient verified-quiet rows for sequence model')
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError('PyTorch is required to fit neural selective-v1 candidates') from exc
        self._torch = torch
        torch.manual_seed(self.seed)
        try:
            torch.use_deterministic_algorithms(True)
        except Exception:
            pass
        self.context_centres, self.context_scales = _robust_normalizer(rows, CONTEXT_NAMES, 'context')
        self.feature_centres, self.feature_scales = _robust_normalizer(rows, FEATURE_NAMES, 'features')

        prepared = []
        for sequence in sequences:
            x_rows=[]; y_rows=[]; previous=None
            for row in sequence:
                if row.get('quality_ok') is False:
                    continue
                x_rows.append(self._input_row(row, previous))
                y_rows.append(self._target_row(row))
                previous = row['features']
            if len(x_rows) >= 2:
                prepared.append((x_rows, y_rows))
        if not prepared:
            raise ValueError('no usable sequences')
        max_len = max(len(item[0]) for item in prepared)
        batch = len(prepared)
        input_size = len(CONTEXT_NAMES) + len(FEATURE_NAMES)
        feature_count = len(FEATURE_NAMES)
        x = torch.zeros(batch, max_len, input_size, dtype=torch.float32)
        y = torch.zeros(batch, max_len, feature_count, dtype=torch.float32)
        present = torch.zeros(batch, max_len, dtype=torch.bool)
        loss_valid = torch.zeros(batch, max_len, dtype=torch.bool)
        for bi, (x_rows, y_rows) in enumerate(prepared):
            n=len(x_rows)
            x[bi,:n]=torch.tensor(x_rows,dtype=torch.float32)
            y[bi,:n]=torch.tensor(y_rows,dtype=torch.float32)
            present[bi,:n]=True
            loss_valid[bi,1:n]=True  # first token is real context but has no previous observation target

        model = self._build_network(torch)
        lr = min(self.learning_rate, 1e-3) if self.architecture == 'transformer' else self.learning_rate
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
        nu = 4.0
        model.train()
        for _ in range(self.epochs):
            optimizer.zero_grad(set_to_none=True)
            out = model(x, present)
            if not torch.isfinite(out[loss_valid]).all():
                raise RuntimeError(f'non-finite {self.architecture} network output during training')
            mu, raw_scale = out.chunk(2, dim=-1)
            raw_scale = torch.clamp(raw_scale, -8.0, 8.0)
            scale = torch.nn.functional.softplus(raw_scale) + 0.05
            z = torch.clamp((y - mu) / scale, -1e4, 1e4)
            loss_terms = torch.log(scale) + 0.5 * (nu + 1.0) * torch.log1p((z * z) / nu)
            mask = loss_valid.unsqueeze(-1).expand_as(loss_terms)
            loss = loss_terms[mask].mean()
            if not torch.isfinite(loss):
                raise RuntimeError(f'non-finite {self.architecture} training loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
        model.eval()
        self._model = model
        self._parameter_count = sum(parameter.numel() for parameter in model.parameters())
        return self

    def predict_sequence(self, rows: Sequence[dict]) -> list[DistributionPrediction | None]:
        if self._model is None or self._torch is None:
            raise RuntimeError('fit must be called before predict_sequence')
        torch = self._torch
        x_rows=[]; previous=None; scorable=[]; present=[]
        for row in rows:
            context = row.get('context') or {}
            features = row.get('features') or {}
            good = row.get('quality_ok') is not False and all(finite_number(context.get(name)) is not None for name in CONTEXT_NAMES) and all(finite_number(features.get(name)) is not None for name in FEATURE_NAMES)
            if not good:
                x_rows.append([0.0] * (len(CONTEXT_NAMES) + len(FEATURE_NAMES)))
                present.append(False)
                scorable.append(False)
                previous = None
                continue
            x_rows.append(self._input_row(row, previous))
            present.append(True)
            scorable.append(previous is not None)
            previous = features
        if not x_rows:
            return []
        x=torch.tensor([x_rows],dtype=torch.float32)
        present_tensor=torch.tensor([present],dtype=torch.bool)
        with torch.no_grad():
            out=self._model(x,present_tensor)[0]
            mu_norm, raw_scale = out.chunk(2,dim=-1)
            raw_scale=torch.clamp(raw_scale,-8.0,8.0)
            scale_norm=torch.nn.functional.softplus(raw_scale)+0.05
        output=[]
        for index,row in enumerate(rows):
            if not scorable[index]:
                output.append(None); continue
            location={}
            scale={}
            for fi,name in enumerate(FEATURE_NAMES):
                mu_value=float(mu_norm[index,fi])
                scale_value=float(scale_norm[index,fi])
                if not isfinite(mu_value) or not isfinite(scale_value):
                    output.append(None)
                    break
                location[name]=self.feature_centres[name]+self.feature_scales[name]*mu_value
                scale[name]=max(1e-9,self.feature_scales[name]*scale_value)
            else:
                output.append(student_t_surprise(row['features'],location,scale,degrees_of_freedom=4.0))
        return output

    @property
    def parameter_count(self) -> int:
        return int(self._parameter_count)


def make_candidate(name: str):
    if name == 'robust-linear':
        return RobustConditionalLinear()
    if name in {'gru', 'tcn', 'transformer'}:
        return TorchStudentTModel(name)
    raise ValueError(f'unknown model candidate {name!r}')
