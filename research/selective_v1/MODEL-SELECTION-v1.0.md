# Selective ML v1.0 model selection

## Data firewall

Architecture selection was performed on benchmark v1.0 **development satellites only**. The final empirical support/risk calibration used only the four calibration `verified-quiet` cases after the backbone was selected.

The 12 confirmatory satellites were not materialised, inspected or scored during model selection. Their subsequent evaluation is recorded in [the final results](../confirmatory_v1/RESULTS-v1.0.md).

Seven calibration event histories were unavailable during the design run because the public history proxy reached its request quota. They were deliberately excluded rather than allowing data availability to influence architecture selection. Calibration-event performance is therefore not reported in the selective-model stage.

## Candidates

All candidates use the same causal detector 0.4-derived response/context features, same Student-t-shaped nonconformity interface and same selective support/risk protocol.

| Candidate | Parameters | Development PU event-vs-quiet mean percentile | Strict development event recall | Event-row abstention |
|---|---:|---:|---:|---:|
| Transformer | 59,568 | **0.480625** | 0.000 | 0.174074 |
| Robust linear | 272 | 0.377655 | 0.000 | **0.162963** |
| GRU | 14,000 | 0.340833 | 0.000 | 0.174074 |
| TCN | 7,664 | 0.284375 | 0.000 | 0.174074 |

The primary architecture-selection statistic is positive-unlabelled safe: it compares the maximum score in documented maneuver intervals against cross-fitted verified-quiet scores. Unlabelled rows from event-evidence cases do not become negatives.

## Selection

The frozen selection order is:

1. PU event-versus-verified-quiet mean percentile, descending;
2. strict supported-regime event recall, descending;
3. event-row abstention, ascending;
4. median absolute detection delay, ascending;
5. parameter count, ascending.

The **Transformer** is selected because it has the highest primary statistic, `0.480625`.

This is only a relative selection. A value below `0.5` does not demonstrate useful event-versus-quiet separation, and all four candidates produced zero events at the strict empirical-risk operating point. Selective-model evaluation therefore does **not** establish a detector improvement over method 0.4.

The appropriate disposition is:

- retain the Transformer as the backbone to test in the next sequential-evidence stage;
- retain robust-linear, GRU and TCN as explicit comparison/ablation baselines;
- do not integrate selective ML v1.0 into the public detector;
- do not touch the confirmatory partition;
- require a later development/calibration gate to pass before confirmatory evaluation.

## Final support calibration

The final method requires at least three independent verified-quiet reference satellites in a regime.

Reference counts after adding calibration quiet controls are:

| Regime | Independent quiet satellites | Final status |
|---|---:|---|
| LEO | 4 | qualified |
| GEO | 2 | abstain |
| MEO | 1 | abstain |
| HEO | 1 | abstain |

This rule was tightened after an exploratory two-satellite GEO calibration produced a pathological support-distance threshold. That exploratory threshold was discarded and is not part of final v1.0.

Final LEO support threshold: `1.2019241655473716`.

## Final empirical event calibration

Only covered calibration verified-quiet exposure contributes the denominator.

The final three-satellite support rule leaves Aqua as the only covered calibration quiet case:

- raw span: `14.81842594` days;
- selective coverage: `0.9583333333333334`;
- covered span: `14.200991525833333` days;
- covered exposure: `0.4665623499247091` object-month.

The frozen event threshold is `6.501427015384656`. It produced zero false events on that covered calibration exposure under the empirical budget of at most one false event per covered object-month.

The sample is too small for a strong false-alarm claim. It is an operating-point calibration only.

## Reproducibility record

Exact machine-readable results are in:

`benchmark-results/selective-v1-model-selection.json`

The four-model run used CPU PyTorch `2.8.0`. The feature artifact contained 725 causal rows from 18 non-confirmatory cases: all 14 development cases and the four calibration verified-quiet controls.

Detector method 0.4 was not changed.
