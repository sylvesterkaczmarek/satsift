# Source Ledger v1.0

This ledger records the evidence families admitted to publication benchmark v1.0 and the qualification applied to each family.

## Pinned parsed-label source

Benchmark v1.0 uses selected parsed public maneuver labels from:

- repository: `astro-tools/maneuver-detect`
- commit: `b7c6dc2ccc8c93cab5145a58085e64a5d37e4137`
- labels artifact: `dataset/v0.3/labels.json`
- labels SHA-256: `19579666bd7d12763c23b75c9194375801a05ea04d48a2440925ae88122757af`
- authored dataset artefacts licence: CC-BY-4.0; underlying public sources retain their own terms.

Only operator/tracking-network-derived source families are admitted. `SELF-GEO` is excluded.

## External source families

| Source family | Public evidence | Benchmark interpretation | Confidence | Important limitation |
|---|---|---|---|---|
| DORIS-IDS | International DORIS Service satellite maneuver histories | executed maneuver interval/history | high | source time precision varies by mission entry |
| GPS-NANU | GPS Notice Advisory to Navstar Users, `FCSTDV` | scheduled forecast Delta-V/outage | medium, scheduled | does not independently prove burn execution |
| GALILEO-NAGU | Galileo Service Centre `PLN_MANV` notices | planned maneuver outage | medium, scheduled | does not independently prove execution |
| NOAA-GOES | NOAA OSPO `navsum.txt`, historical state reconstructed from archived content-distinct snapshots | last-maneuver date, day-censored | high, day-censored | historical event list is reconstructed from changes in an official live-state file |
| QZSS-OHI | QZSS Operational History Information | executed maneuver log, often with Δv | high | IGSO objects retain `orbit_regime=IGSO`; current detector profile mapping is GEO |

### Canonical public endpoints represented by the pinned parser

- DORIS: `https://ids-doris.org/documents/BC/satellites/{ref}man.txt`
- GPS NANU archive: `https://celestrak.org/GPS/NANU/{year}/`
- Galileo NAGU: `https://www.gsc-europa.eu/sites/default/files/NOTICE_ADVISORY_TO_GALILEO_USERS_NAGU_{notice}.txt`
- NOAA GOES live navigation summary: `https://www.ospo.noaa.gov/resources/cemscs/navsum.txt`
- QZSS OHI: `https://qzss.go.jp/en/technical/qzssinfo/khp0mf0000000wuf-att/ohi-{ref}.txt`

The manifest stores the concrete event-level source URL/source reference for each selected interval.

## Direct event evidence

Direct public sources supplement the parsed corpus where they add orbit-regime or operator diversity.

| Object | NORAD | Regime | Split | Evidence | Qualification |
|---|---:|---|---|---|---|
| Galileo 5 | 40128 | MEO | development | ESA recovery campaign | eleven-maneuver campaign represented as one conservative public interval because individual burn times are not published |
| Himawari-9 | 41836 | GEO | development | NOAA/JMA station-keeping notice | scheduled station-keeping interval with stated time window |
| INTEGRAL | 27540 | HEO | development | ESA disposal campaign | one precise ESA burn interval plus one agency-scheduled burn day |
| Cluster Samba | 26410 | HEO | confirmatory | ESA reentry adjustment | conservative two-day interval because ESA reports Samba/Tango burns on 19/20 January 2026 without assigning spacecraft to day |
| Cluster Tango | 26464 | HEO | confirmatory | ESA reentry adjustment | same conservative censoring as Samba |

## Verified-quiet controls

A quiet case is admitted only where the cited authority supports cessation/unavailability of maneuvering or a final trajectory/free-drift state. Silence in a maneuver log is never enough.

| Object | NORAD | Regime | Split | Quiet rationale |
|---|---:|---|---|---|
| ERS-2 | 23560 | LEO | development | fuel depletion and complete passivation after final disposal campaign |
| GOCE | 34602 | LEO | development | xenon exhausted and ion engine shut down; subsequent decay is uncontrolled |
| Meteosat-8 | 27509 | GEO | development | graveyard reorbit completed and spacecraft passivated |
| Aura | 28376 | LEO | development | NASA reports final orbit-maintenance maneuvers completed in 2023 and subsequent drift |
| GIOVE-B | 32781 | MEO | calibration | retired and transferred to graveyard orbit |
| Meteosat-7 | 24932 | GEO | calibration | disposal/graveyard sequence completed and passivated |
| Cluster Salsa | 26411 | HEO | calibration | post-targeting trajectory; ESA states reentry would occur without further assistance |
| Aqua | 27424 | LEO | calibration | final drag-makeup maneuver completed in December 2021; NASA describes free drift thereafter |
| CALIPSO | 29108 | LEO | confirmatory | final passivation completed in December 2023 and spacecraft decommissioned |
| Cluster Rumba | 26463 | HEO | confirmatory | ESA states trajectory was adjusted one last time in August 2024 and set on its final path |

The exact public URLs and selected date windows are frozen in `public-evidence-manifest-v1.0.json`.

## Evidence exclusions

The following are deliberately not used as benchmark truth:

- externally self-derived `SELF-GEO` maneuver labels;
- detector outputs from this project;
- unlabeled periods treated as implicit negatives;
- event timestamps inferred only from orbital discontinuities without independent public evidence;
- generic mission statements that do not support the selected event or quiet interval;
- uncertain object identity mappings.

## Publication-language constraints

The paper must distinguish:

- executed evidence from scheduled evidence;
- precise timestamps from day/campaign-censored intervals;
- verified quiet from merely unlabeled time;
- operator/agency evidence from parsed third-party artefacts derived from those public sources.

No source family in this benchmark justifies a claim that every maneuver occurring in a case window is exhaustively labelled.
