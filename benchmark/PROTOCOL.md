# Publication benchmark protocol

## Scope

This protocol evaluates maneuver-screening methods using only explicitly labelled event intervals and explicitly verified non-maneuvering controls. Unlabelled time is treated as unknown and is excluded from false-positive denominators.

## Evidence classes

- `event-evidence` means an operator, agency or mission source documents one or more maneuver intervals.
- `verified-quiet` means an authoritative source establishes that commanded orbital maneuvering was unavailable, disabled, exhausted or otherwise not possible during the selected interval.
- `unknown` means the absence of a public maneuver notice is insufficient to establish a negative label.

Every case carries a confidence tier. Interval-censored events are allowed when an authoritative source provides a date or campaign interval rather than an exact burn epoch.

## Data source

Orbital records are Space-Track Basic SSA OMM/GP history. Preserve original `EPOCH`, `CREATION_DATE`, `ELEMENT_SET_NO` and `GP_ID` when present. The detector's deterministic catalogue-revision policy must be applied before dynamical intervals are evaluated.

## Splits

The primary evaluation uses complete-satellite holdout. A NORAD object may appear in exactly one of `calibration` or `test`, never both. All tuning, threshold selection and model fitting must use calibration objects only. Test objects remain untouched until the method is frozen.

Within calibration objects, chronological model selection uses earlier windows for fitting and later windows for calibration. Any learned normal model must use only information available before each evaluated epoch.

## Metrics

Report at event level:

- precision on `event-evidence` plus `verified-quiet` cases only;
- recall on documented event intervals;
- F1 when precision and recall are both defined;
- false events per verified-quiet object-month;
- detection delay measured from the start of the labelled interval;
- abstention rate;
- results by orbit regime and label-confidence tier.

For each scalar performance metric, report a 95% satellite-cluster bootstrap confidence interval. Resample complete NORAD objects, not individual observations or events.

## Uncertain labels

For interval-censored labels, a predicted event is a match if its event interval overlaps the truth interval expanded by the declared matching tolerance. Confidence-weighted sensitivity is a secondary analysis only and must not replace the unweighted primary results.

## Missing and irregular data

Run at least three deterministic sensitivity conditions:

1. native sampling;
2. removal of every fourth interior record;
3. removal of a contiguous 20% interior block where sufficient records exist.

Report whether each case remains evaluable and whether event presence changes.

## Publication freeze

A publication result must identify:

- manifest version and SHA-256;
- generated benchmark file SHA-256;
- detector commit SHA;
- settings and model hyperparameters;
- calibration/test object lists;
- dependency versions;
- exact metric code version.

Do not report operational detection claims from provisional or unknown negative windows.
