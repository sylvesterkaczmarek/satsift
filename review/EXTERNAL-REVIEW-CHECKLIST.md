# External astrodynamics review checklist

## Reviewer information

- Name:
- Organisation:
- Relevant orbit-determination, flight-dynamics or SSA experience:
- Conflicts of interest:
- Review date:
- Git commit SHA reviewed:

## Review questions

### Data and propagation

- [ ] TLE and OMM field parsing is correct for the supported formats.
- [ ] SGP4 is applied within an appropriate use case for public general-perturbations elements.
- [ ] Consecutive states are compared at a common epoch without a frame mismatch.
- [ ] RTN basis construction and signs are correct.
- [ ] Failed or invalid propagation is handled conservatively.

### Features and calibration

- [ ] Semi-major-axis and mean-motion transformations are dimensionally correct.
- [ ] Eccentricity- and inclination-vector features are appropriate for screening.
- [ ] B* is appropriately qualified as supporting evidence.
- [ ] Rolling calibration uses preceding records only.
- [ ] Minimum feature floors and profile thresholds are justified or clearly marked heuristic.

### Classification and event formation

- [ ] Candidate gating is sufficiently conservative for the stated research purpose.
- [ ] Event grouping is reasonable across LEO, MEO, GEO and HEO cadences.
- [ ] Abstention and data-quality rules prevent misleading outputs.
- [ ] Internal tiers are not presented as calibrated probabilities.

### Validation evidence

- [ ] Public-evidence labels are traceable to the cited sources.
- [ ] Quiet controls have been independently checked.
- [ ] Precision, recall, false-event rate and detection delay are reported with exact settings.
- [ ] Missing-data and irregular-sampling sensitivity is reported.
- [ ] Results are separated by orbit profile.
- [ ] The frozen confirmatory result, confidence intervals and failed integration/publication gate are represented accurately.

## Reviewer findings

| ID | Severity | Finding | Recommended action | Disposition |
|---|---|---|---|---|
| | | | | |

## Final disposition

Choose one:

- [ ] Accept for research screening and technical evaluation
- [ ] Accept conditionally after listed corrections
- [ ] Reject pending major methodological revision
- [ ] Suitable for a limited operator pilot under supervision
- [ ] Suitable for operational use within a separately defined assurance case

Signature and date:
