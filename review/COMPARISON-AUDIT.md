# Comparison evaluation audit

## Disposition

The comparison was implemented as a 16-method comparison suite, run on the frozen development/calibration objects, audited after the first candidate result, corrected, and rerun. The confirmatory partition remained sealed throughout.

## Findings fixed

1. **Detection-delay definition.** Candidate delay used the strongest point of a grouped event. Final delay uses the event onset/first alarm; strongest point remains only the deterministic matching anchor.
2. **Zero-recall F1.** Candidate output left F1 undefined for some methods with zero recall. Final output reports F1 zero when labelled events exist and none are detected.
3. **Temporal/filter integrity.** Sequence comparators now restart at quality-abstention boundaries, and filtering residual estimation excludes quality-failed rows.
4. **Cost comparability.** Candidate inference timing covered different case sets across methods. Final inference timing covers the same 14 calibration cases, with development diagnostics reported separately.
5. **Risk interpretation.** The final result records common-risk-budget compliance explicitly and provides a separate compliant ranking without retuning frozen target methods.

## Anti-cherry-picking verification

All 16 predeclared methods remain in the final artifact. No candidate result caused a baseline to be removed, added, or structurally retuned. Generic baseline fitting uses development verified-quiet histories only; calibration event labels do not select baseline settings or thresholds. The common threshold calibration uses calibration verified-quiet exposure only.

## Final freeze

- methods: `16`;
- primary split: `calibration`;
- confirmatory accessed: `false`;
- bootstrap replicates: `1000`;
- machine-readable SHA-256: `092df5a126d85fb7b58e5a0f682acdee1da39860359be943f102f26a986ddb43`.

## Reproduction boundary

`shorten-op-pf-surrogate` is explicitly a structural surrogate rather than an exact Shorten et al. implementation because the validated non-standard mean-element SGP4/Kozai-Brouwer implementation assumed by that publication is unavailable in this repository.

## Conclusion

The comparison is accepted only within the development/calibration comparison claim boundary. The permanent result retains all methods, all reported weaknesses and the common-risk-budget distinction, while the benchmark v1.0 confirmatory partition remained untouched during this comparison. The later [confirmatory evaluation](../research/confirmatory_v1/RESULTS-v1.0.md) is complete and failed its integration gate.
