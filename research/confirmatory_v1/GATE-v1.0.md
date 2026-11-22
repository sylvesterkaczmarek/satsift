# Confirmatory evaluation gate v1.0

## Status

This gate was frozen before benchmark v1.0 confirmatory histories were materialized, inspected or scored. The evaluation is complete and the gate failed; see [the final results](RESULTS-v1.0.md). The criteria below remain the historical decision rule.

The evaluation was specified as a one-shot confirmatory study. Its method, thresholds, benchmark protocol, comparison roster and gate criteria remain closed to post-result changes.

## Evidence inherited before confirmatory access

The prior physics-ML v0.3 experiment was explicitly rejected with held-out recall `0.20`, despite a lower false-event burden than detector 0.4. A future method was required to demonstrate materially better event recall and false-event burden without unacceptable delay or loss of selective reliability.

The physics-ML v1.0 research programme already freezes an empirical target of at most `1.0` false event per covered verified-quiet object-month. The comparison uses a frozen 24-hour event-matching tolerance and preserves all principal comparison methods.

## Integration and publication gate

The predeclared rule required **all** of the following to hold on the then-untouched confirmatory partition:

1. **At least one documented event is detected.** Confirmatory true positives must be at least `1`.
2. **Recall materially exceeds the rejected v0.3 result.** Overall confirmatory event recall must be strictly greater than `0.20`.
3. **The empirical quiet-risk target is met with measurable exposure.** Covered confirmatory verified-quiet exposure must be greater than zero and the observed false-event rate must be at most `1.0` per covered object-month.
4. **Comparative event performance is superior at the common risk budget.** Physics-ML v1.0 confirmatory F1 must be strictly greater than the highest confirmatory F1 among detector 0.4 and the principal comparison baselines that themselves have positive covered confirmatory verified-quiet exposure and an observed false-event rate at or below `1.0` per covered object-month. If no such comparator has measurable compliant exposure, this condition fails rather than being waived.
5. **Detection delay remains within the frozen event-time tolerance.** Median absolute matched-event first-alarm delay must be at most `24` hours.

These are conjunctive conditions. Failure of any one condition means the confirmatory integration/publication gate fails.

## Statistical reporting

The gate uses point estimates because the confirmatory set is deliberately small and satellite-disjoint. Satellite-cluster 95% bootstrap confidence intervals must nevertheless be reported for precision, recall, F1, false events per covered object-month, detection delay and abstention. Confidence intervals are evidence and uncertainty reporting, not post-hoc gate modifiers.

Abstention is reported directly. There is no separate numerical abstention threshold, but a method that completely abstains on verified-quiet confirmatory exposure cannot satisfy the measurable quiet-risk condition, and a method that misses event evidence cannot satisfy the true-positive, recall or comparative-F1 conditions.

## Frozen method constants

Physics-ML v1.0 retains the previously frozen maneuver-physics stack:

- Transformer nominal model;
- base conditional-surprise threshold `17.822733355396952`;
- final support threshold `1.2019241655473716`;
- empirical event-like parameter `q0 = 0.24444444444444446`;
- sequential wealth threshold `1.01`;
- equivalent-impulse maneuver-physics feasibility layer;
- selective abstention and integrity rules already defined before the confirmatory study.

Detector 0.4 remains unchanged. Principal baseline structures and their calibration rules remain those frozen in the comparison study.

## One-shot rule

The historical protocol required a single confirmatory evaluation. Its completed execution and procedural exception are recorded in [the audit](../../review/CONFIRMATORY-AUDIT.md). No threshold, architecture, feature, training rule, baseline definition, event matching rule, gate criterion or benchmark label may be changed after confirmatory results are observed. A failed gate is retained as a negative result and does not authorize integration under the integration decision.
