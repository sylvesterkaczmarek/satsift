# Publication Benchmark Protocol v1.0

## Status

This document records the frozen publication benchmark v1.0 protocol for satellite maneuver screening from public GP histories. The confirmatory evaluation is now complete and its integration gate failed; see [the final results](../research/confirmatory_v1/RESULTS-v1.0.md). The original split, scoring and evidence rules below remain unchanged. The consumed confirmatory partition cannot serve as untouched evidence for a tuned successor.

The immutable benchmark core consists of:

- `public-evidence-manifest-v1.0.json` and its SHA-256 file;
- `benchmark-data/public-evidence-benchmark-v1.0.recipe.json` and its SHA-256 file;
- the pinned external label provenance recorded in the manifest;
- the split assignments, evidence intervals, confidence tiers and verified-quiet controls recorded in the manifest.

A fully materialized `benchmark-data/public-evidence-benchmark-v1.0.json` is a derived Space-Track GP_History artifact. It can be reconstructed with the frozen recipe and private Space-Track credentials. It must not change labels, splits or evaluation semantics.

## Frozen scope

Benchmark v1.0 contains:

- 40 cases from 40 unique NORAD objects;
- 30 event-evidence cases;
- 10 verified-quiet controls;
- 154 documented maneuver/event intervals;
- event-evidence coverage in LEO, MEO, GEO and HEO;
- one QZSS IGSO case retained as `orbit_regime=IGSO` and evaluated with the current detector's GEO profile.

The numerical target was not used to admit weak labels. Cases were selected only when a public operator, agency, tracking-network source or a pinned high-quality parsed-label artifact supported the stated interval.

## Satellite-disjoint partitions

The unit of splitting is the NORAD object. An object may appear in exactly one partition.

| Partition | Objects | Truth intervals | Verified-quiet controls | Intended use |
|---|---:|---:|---:|---|
| development | 14 | 49 | 4 | model and feature development |
| calibration | 14 | 64 | 4 | calibration, abstention and operating-point selection |
| confirmatory | 12 | 41 | 2 | final untouched evaluation only |

The confirmatory object list was frozen before physics-ML v1.0 development. Confirmatory labels, histories and detector outcomes must not be inspected for tuning. If that boundary is broken, a new confirmatory partition/version is required.

## Label semantics

### Event evidence

A documented public event is represented by an interval `[start, end]`, not by an assumed point timestamp unless the source supplies one.

For an `event-evidence` case:

- documented truth intervals contribute true-positive and false-negative scoring;
- a detector event may match a truth interval within the declared 24-hour tolerance;
- unmatched detector events outside documented truth intervals are **unscored**, because the surrounding period is not asserted to be maneuver-free;
- unlabelled time is never converted into a negative label.

This is positive-unlabelled evaluation.

### Verified quiet

A `verified-quiet` interval contributes false-positive exposure only when the cited source explicitly supports a state such as:

- propulsion/fuel exhausted and maneuvering unavailable;
- spacecraft passivated/decommissioned;
- final maneuver completed and subsequent free drift/final trajectory stated;
- no further assistance/manoeuvring required for the selected interval.

Absence of a maneuver notice is not enough to create a quiet label.

## Evidence confidence and censoring

The benchmark preserves source-specific uncertainty rather than flattening all evidence into an identical label type.

- `high-public-evidence`: executed maneuver history or direct operator/agency confirmation.
- `high-public-evidence-day-censored`: operator state establishes a maneuver date but not a precise burn time.
- `medium-public-evidence-scheduled`: a public operational notice schedules a maneuver/outage but does not independently prove execution.

GPS NANU `FCSTDV` and Galileo NAGU `PLN_MANV` cases therefore remain scheduled-evidence tiers. They are useful publication evidence but must not be described as executed-burn ground truth.

Where an agency reports a multi-burn campaign without individual timestamps, the campaign is represented as one conservative interval rather than inventing burn times.

## Source families

The pinned external label source is `astro-tools/maneuver-detect` at commit `b7c6dc2ccc8c93cab5145a58085e64a5d37e4137`, with `dataset/v0.3/labels.json` SHA-256 `19579666bd7d12763c23b75c9194375801a05ea04d48a2440925ae88122757af`.

Allowed parsed source families are:

- DORIS/IDS maneuver histories;
- GPS NANU FCSTDV notices;
- Galileo NAGU PLN_MANV notices;
- NOAA GOES navigation-summary history reconstructed from archived official live-state files;
- QZSS Operational History Information maneuver logs.

The external dataset's `SELF-GEO` labels are explicitly excluded because benchmark v1.0 does not use self-derived labels as publication truth.

Direct ESA, NASA, EUMETSAT and NOAA/JMA evidence supplies additional event cases, HEO coverage and verified-quiet controls.

See `benchmark/SOURCE-LEDGER-v1.0.md` for source qualifications and limitations.

## Space-Track history reconstruction

The orbital-history source is Space-Track Basic SSA `gp_history` OMM JSON.

For each case the frozen materialization recipe records:

- NORAD catalog ID;
- UTC inclusive start date;
- UTC inclusive end date;
- exact direct `gp_history` query;
- equivalent same-site history request;
- ascending epoch ordering and 5000-record safety limit.

The query interval is encoded as start date 00:00:00 UTC through the day after the end date 00:00:00 UTC, exclusive at the upper bound.

Exact duplicate epochs are resolved deterministically by preferring the later `CREATION_DATE`, then the larger `ELEMENT_SET_NO`. Near-simultaneous catalogue revisions remain available to detector method 0.4's catalogue-revision logic.

Two reconstruction routes are supported:

1. `tools/materialize_benchmark_v1_spacetrack.py` with private `SPACETRACK_IDENTITY` and `SPACETRACK_PASSWORD` environment variables. This is the preferred one-shot publication reconstruction route.
2. `tools/build_public_evidence_benchmark.py` through the same-site history endpoint. This route deliberately inherits the public server's quota/rate protections and may therefore require cached data or staged execution.

Credentials, session cookies and cache files must never be committed.

## Evaluation

The core event-level metrics are:

- precision over scorable predictions only;
- recall;
- F1;
- false events per verified-quiet object-month;
- median matched-event detection delay;
- abstention rate;
- satellite-cluster bootstrap confidence intervals.

Results must be reported overall and by orbit regime/profile where sample size permits. Any future tuning must use only development and calibration partitions. The confirmatory partition is run once after the method, hyperparameters and integration gate are frozen.

## Integrity and provenance checks

Permanent CI must verify:

- manifest and recipe SHA-256 sidecars;
- exact frozen case/event/split counts;
- NORAD-disjoint partitions;
- no `SELF-GEO` source family;
- event-evidence cases contain truth intervals;
- verified-quiet cases contain none;
- all four principal orbit regimes have event evidence;
- the confirmatory object list remains unchanged;
- scheduled evidence retains its lower confidence tier;
- the pinned external label commit and SHA-256 remain unchanged;
- materializer/compiler/builder syntax remains valid.

Any change to a label, source, split, case window or materialization recipe requires a new benchmark version and new hashes.
