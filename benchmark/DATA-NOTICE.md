# Benchmark data notice

## Orbital-element data

The materialised benchmark files `public-evidence-benchmark-v0.2.json`, `public-evidence-benchmark-v0.3.json` and `public-evidence-benchmark-v0.4.json` under `benchmark-data/` contain basic SGP4 orbital-element histories obtained through Space-Track.org. Their existing `data_attribution` records credit Space-Track.org and U.S. Space Command. Retain those records and the individual case provenance when redistributing the data or publishing derived analysis.

The [official Space-Track documentation](https://www.space-track.org/documentation), under **Redistribution of Basic SSA Information**, states that USSPACECOM permits redistribution of basic SSA data subject to appropriate citation, and requires citation for analysis based on those data. It explicitly includes TLEs and OMMs. This policy was checked on **22 November 2026**. Its scope should not be extended to other Space-Track products without checking their terms.

The v1.0 repository artefact is a query recipe and evidence manifest. Reconstructed histories remain local derived data. Authentication credentials, sessions and caches must remain private. This distribution boundary is retained for reproducibility and privacy; it does not imply that all basic orbital data lack redistribution permission.

## Parsed public labels

Selected parsed labels in `public-evidence-manifest-v1.0.json` are adapted from [astro-tools' maneuver-detect dataset](https://github.com/astro-tools/maneuver-detect/tree/b7c6dc2ccc8c93cab5145a58085e64a5d37e4137) at commit `b7c6dc2ccc8c93cab5145a58085e64a5d37e4137`, using `dataset/v0.3/labels.json`. Its SHA-256 is `19579666bd7d12763c23b75c9194375801a05ea04d48a2440925ae88122757af`.

The upstream [README](https://github.com/astro-tools/maneuver-detect/blob/b7c6dc2ccc8c93cab5145a58085e64a5d37e4137/README.md) and [dataset documentation](https://github.com/astro-tools/maneuver-detect/blob/b7c6dc2ccc8c93cab5145a58085e64a5d37e4137/docs/dataset.md) identify its authored label artefacts as [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). Credit astro-tools and retain the original source references. This attribution and licence declaration were checked on **22 November 2026**.

This project selects operator and tracking-network source families, restricts observation windows, groups labels into case intervals, assigns its own benchmark splits and adds evidence qualifications. Self-derived `SELF-GEO` labels are excluded. These changes are this project's curation; they do not imply endorsement by astro-tools or the original providers. [SOURCE-LEDGER-v1.0.md](SOURCE-LEDGER-v1.0.md) and the frozen manifest retain the original commit, source families, source references and qualifications.

The CC BY 4.0 designation applies to the identified external authored label artefacts. It does not assign that licence to every orbital record, upstream publication, research result or project-code file.

## Provider acknowledgements

The following credits supplement the event-level source URLs. Terms were checked on **22 November 2026**.

| Source family | Acknowledgement and reuse boundary |
| --- | --- |
| Galileo NAGU | European GNSS Service Centre / European Union, **© EU 2011-2026**. The [GSC terms of use](https://www.gsc-europa.eu/terms-of-use) permit reuse with that source credit unless otherwise stated. Third-party material and logos retain their own terms. Selected `PLN_MANV` intervals remain scheduled notices, not proof of execution. |
| QZSS OHI | **Source: Quasi-Zenith Satellite System website**, Cabinet Office, Government of Japan. Benchmark cases are curated adaptations of the operational-history information at the event-level URLs, rather than original QZSS publications. The [website terms](https://qzss.go.jp/en/policy/rule.html) require source and editing acknowledgement and permit use under CC BY 4.0. The [satellite-information terms](https://qzss.go.jp/en/technical/qzssinfo/index.html) also call for proper credit in publications of analysis using these data. |
| DORIS-IDS | Acknowledge the International DORIS Service and the individual mission histories. The IDS [citation guidance](https://ids-doris.org/resources/articles/citation.html) requests credit for publications using its data and results. This notice does not relabel all IDS material as CC BY 4.0. |
| GPS NANU and NOAA GOES | Retain the U.S. Government provider names, original notice references and source URLs recorded in the manifest. GPS forecast Delta-V windows remain scheduled evidence. NOAA historical dates retain the qualification that they were reconstructed from changes in archived live-state summaries. |
| Direct agency evidence | Retain the individual NASA, ESA, NOAA, EUMETSAT and other provider citations. Links and curated factual labels do not grant rights to redistribute full source articles, images or logos. |

Published analysis should also retain the limitations on scheduled, executed, day-censored and campaign-censored evidence described in the source ledger. No source family establishes an exhaustive record of all manoeuvres.

## Software and project ownership

[Third-party software notices](../THIRD-PARTY-NOTICES.md) cover the bundled browser dependencies and their reviewed component notices. Original SatSift source code is licensed under [Apache License 2.0](../LICENSE). This does not alter the external data and authored-label terms documented above.

These companion acknowledgements leave all frozen benchmark files, result files and checksum values unchanged. They record the reviewed source terms and attribution boundaries without claiming that every upstream item has received comprehensive legal clearance.

## Access and correction policy

Space-Track's [API use guidelines](https://www.space-track.org/documentation) call for retaining downloaded GP_HISTORY data and using the GP class for current elements. Reproduction or cache-refresh work must respect those rules. Retain historical source bytes and retrieve new elements through the permitted mechanism; do not implement periodic wholesale historical downloads.
