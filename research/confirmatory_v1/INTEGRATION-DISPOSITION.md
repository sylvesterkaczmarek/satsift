# Integration decision

## Decision

**NO INTEGRATION. The confirmatory gate failed.**

The frozen confirmatory gate failed. Physics-ML v1.0 therefore has not earned integration into the public Satellite Maneuver Screening Workbench.

At the historical integration decision, Workbench 3.4 and detector method 0.4 were retained, with no changes to `app-3.4.js` or `index.html`. Later engineering maintenance produced Workbench 3.4.2 without integrating physics-ML v1.0. Detector 0.4 remains the public scientific baseline.

## Frozen evidence

- Confirmatory result SHA-256: `f9857bd8f9ae2525b1827ce4fdfd108f7c5468c67142226922542d24b88c923c`
- frozen science commit: `2c394d4d9362c65560a2a08827b4e1a96f23ed87`
- confirmatory objects: `12`
- documented truth intervals: `41`
- verified-quiet controls: `2`
- methods: `16`
- physics-ML v1.0: `0` TP, `41` FN, recall `0`, F1 `0`, mean case abstention about `0.9212`
- overall predeclared integration/publication gate: `FAIL`

The negative result is preserved in `benchmark-results/confirmatory-v1-final.json`, `research/confirmatory_v1/RESULTS-v1.0.md`, and `review/CONFIRMATORY-AUDIT.md`.

## Integration consequence

The integration decision added no physics-ML v1.0 code or new detector version to the public workbench. It made no production UI, documentation, export or deployment changes for learned-method integration. Subsequent engineering maintenance is documented separately.

Any future learned detector must be treated as a new research cycle. It may use the confirmatory set for retrospective diagnosis, but that set can never again be represented as untouched confirmatory evidence for a tuned successor. A successor intended for confirmatory claims requires a genuinely new satellite-level holdout frozen before development.

## Paper consequence

The research plan conditioned integration and preparation of the planned positive-result paper on a successful confirmatory gate. The gate failed. The paper package for `Sequential Risk-Controlled Satellite Maneuver Screening from Public GP Histories` is **not prepared under this roadmap**.

The negative statistical record remains available, and its stored summaries can be independently recomputed. Historical training reproduction has additional [environment and data requirements](../ENVIRONMENT.md). A separate future decision could choose to write a negative-results or lessons-learned paper, or start a new method cycle with a new holdout, but doing either would be a new task and must not reinterpret the failed confirmatory gate.

## Final disposition

The integration decision is complete. The learned method was not integrated, detector 0.4 was retained, the negative result was documented, and the gated paper package was not prepared.
