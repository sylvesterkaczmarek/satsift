# Third-party notices

Reviewed on 22 November 2026.

This notice identifies bundled software and the data attribution boundary. Original SatSift code and documentation are licensed under [Apache License 2.0](LICENSE), with attribution in [NOTICE](NOTICE). These terms do not replace the bundled software's separate licences. Preserve component notices when distributing source or browser assets.

## Bundled browser libraries

| Component | Version | Licence | Retained notice |
| --- | --- | --- | --- |
| Plotly.js | 3.3.1 | MIT, with separately licensed bundled components | [Plotly notice](licenses/plotly-LICENSE.txt) |
| satellite.js | 6.0.2 | MIT | [satellite.js notice](licenses/satellite-LICENSE.txt) |

The reviewed files are `plotly-3.3.1.min.js` and `satellite-6.0.2.min.js`. Their original bytes and SHA-256 values in [vendor-integrity.json](vendor-integrity.json) are retained. Their upstream notices were checked against [Plotly tag v3.3.1](https://github.com/plotly/plotly.js/blob/v3.3.1/LICENSE) and [satellite.js tag 6.0.2](https://github.com/shashwatak/satellite-js/blob/6.0.2/LICENSE.md). Existing wrapping in the Plotly companion notice is retained.

## Components identified in the Plotly notice trailer

The preserved Plotly bundle explicitly names the components below. Versions are taken from the [upstream v3.3.1 package lock](https://github.com/plotly/plotly.js/blob/v3.3.1/package-lock.json), Git blob `0fd9dae12c5373c3c34cd55fbca8cdedff1b2b4e`. This version mapping does not establish that every dependency in that lock is included in the browser bundle.

| Component | Pinned version | Licence | Included full notice |
| --- | --- | --- | --- |
| assert | 2.1.0 | MIT | [Joyent and Node contributor notice](licenses/plotly-bundled/assert-LICENSE) |
| buffer | 6.0.3 | MIT | [Feross Aboukhadijeh and contributor notice](licenses/plotly-bundled/buffer-LICENSE) |
| ieee754 | 1.2.1 | BSD-3-Clause | [Fair Oaks Labs notice](licenses/plotly-bundled/ieee754-LICENSE) |
| maplibre-gl | 4.7.1 | BSD-3-Clause and included notices | [MapLibre notice](licenses/plotly-bundled/maplibre-gl-LICENSE.txt) |
| native-promise-only | 0.8.1 | MIT | [Kyle Simpson notice](licenses/plotly-bundled/native-promise-only-NOTICE.txt) |
| object-assign | 4.1.1 | MIT | [Sindre Sorhus notice](licenses/plotly-bundled/object-assign-license) |
| polybooljs | 1.2.2 | MIT | [Sean Connelly notice](licenses/plotly-bundled/polybooljs-LICENSE) |
| safe-buffer | 5.2.1 | MIT | [Feross Aboukhadijeh notice](licenses/plotly-bundled/safe-buffer-LICENSE) |

The MapLibre file also contains the upstream notices for Mapbox-derived code, glfx.js and d3-color. Keep the complete file.

Seven notice files were copied byte for byte from the pinned npm archives after checking each archive against the integrity value in the upstream package lock. [The source inventory](licenses/THIRD-PARTY-SOURCES.json) records archive URLs, integrity values, SHA-256 digests, archive member paths and notice-file digests.

The native-promise-only 0.8.1 archive has no standalone licence file. Its source header supplies Kyle Simpson's copyright credit, and its README declares MIT with a link to [the author's licence page](https://getify.mit-license.org/). The companion notice combines that attribution with the full MIT permission and warranty text, using ASCII punctuation. It is a documented transcription rather than a byte-identical upstream licence file; no publication year has been invented for the version's yearless source credit.

## Resolved Plotly component notices

The [resolved component inventory](licenses/PLOTLY-COMPONENTS.json) supplies **400 package/version or pinned-commit attribution records** for the exact distributed Plotly 3.3.1 file. It combines the visible module paths with the separately bundled dependency graphs, preserving the distinction between compiled-source evidence and conservative dependency coverage.

| Distribution surface | Evidence used for notice selection |
| --- | --- |
| Plotly outer build | 382 source paths mapped to 165 package/version records using the tagged unminified build and its package lock. The tagged minified build is byte-identical to the distributed file. |
| MapLibre GL 4.7.1 | Its distributed source map and the matching release lock identify 19 nested packages. |
| MapLibre style specification 20.3.1 | Its source map and release lock identify four further dependency mappings. |
| Plotly's Mapbox GL 1.13.4 fork | A 28-package runtime dependency superset uses the lock at the package's recorded Git commit. The archive has no source map, so these entries are not presented as an exact compiled-module count. |
| StackGL prebuilt bundle | Its separate tagged lock supplies 224 package/version or commit candidates, including compiler support. The compiled import path excludes Numeric 1.2.6; the inventory retains the source hashes and import-graph evidence for that exclusion. Remaining entries conservatively preserve notices even where a dependency may have been removed during bundling. |

Counts overlap between surfaces. The inventory records each selected package archive URL, integrity value, archive digest, notice path and notice digest. Thirteen Plotly-maintained dependency forks are pinned to their exact Git commits. Their notices come from those committed sources rather than an npm package that happens to have the same version number.

The full notices are under [licenses/plotly-components/](licenses/plotly-components/) and the earlier [licenses/plotly-bundled/](licenses/plotly-bundled/) directory. [Source attributions](licenses/PLOTLY-SOURCE-ATTRIBUTIONS.txt) preserve the additional copyright and licence comments found in the mapped source files and StackGL bundle. These include the pad-left, repeat-string and is-buffer credits outside the original eight-component trailer, Thomas Robinson's assert attribution, the calendar contributors, and the embedded Google WeakMap credit.

Most notices are unchanged upstream archive members. Where the archive supplies a complete licence in a README or source header, that text is retained with its member path and source digest. Some small packages declare MIT or ISC and identify their author without shipping a standalone licence file. Their companion notices retain the supplied attribution, any stated copyright year and the explicit declaration, followed by a documented transcription of the standard permission and warranty terms. No missing copyright year has been invented.

Two provenance details receive explicit treatment:

- The @mapbox/jsonlint-lines-primitives 2.0.2 archive omits its licence file. The [upstream maintainer confirmed MIT](https://github.com/mapbox/mapbox-gl-js/issues/11331#issuecomment-987761989); the notice is copied from [the later upstream licence clarification](https://github.com/mapbox/jsonlint/blob/524533a0ddeeff6f29dab38af1644e30ec74d3c5/LICENSE). The inventory identifies this source accurately.
- The regl distributions include a SHA-256 implementation credited to Angel Marin, Paul Johnston and additional contributors under BSD terms. Its original header and both authors' full BSD notices accompany the regl package notices. The Google WeakMap source attribution is retained with the complete Apache 2.0 licence.

The reviewed licence families are MIT, BSD, ISC, Zlib, Boost Software License 1.0, Apache 2.0 and the Unlicense. The component-specific notices remain authoritative. Preserve the complete notice directories, source-attribution file and inventories when redistributing the browser libraries. A later deployment must provide the notices with the assets it distributes.

## Dependencies installed for verification

The source snapshot includes manifests and installation instructions. It excludes installed dependency directories, browser binaries, virtual environments and model caches.

| Dependency family | Recorded version | Declared licence | Source of record |
| --- | --- | --- | --- |
| @playwright/test and playwright | 1.62.1 | Apache-2.0 | [package-lock.json](package-lock.json) |
| playwright-core | 1.62.1 and 1.63.0 at their respective resolved locations | Apache-2.0 | [package-lock.json](package-lock.json) |
| @axe-core/playwright and axe-core | 4.13.0 | MPL-2.0 | [package-lock.json](package-lock.json) |
| fsevents, optional platform dependency | 2.3.2 | MIT | [package-lock.json](package-lock.json) |

These declarations describe the resolved development packages, which are not bundled with this source snapshot. Python, PHP and Node requirements, including the separately installed SGP4 reference package and research NumPy/PyTorch packages, are documented in [the research environment](research/ENVIRONMENT.md) and [neural execution contract](research/NEURAL-EXECUTION.md). Redistributing installed environments or browser binaries requires retaining their own notices and reviewing that separate distribution.

## Data and external evidence

[The benchmark data notice](benchmark/DATA-NOTICE.md) records Space-Track attribution, the CC BY 4.0 boundary for selected external label artefacts, provider acknowledgements and excluded private material. [The source ledger](benchmark/SOURCE-LEDGER-v1.0.md) identifies the source families and their evidence limitations. A project-code licence does not replace those source-specific terms.

## Review scope

This review covers the exact browser-library bytes identified by [vendor-integrity.json](vendor-integrity.json), the component mappings and dependency supersets described above, their retained notices, and the companion benchmark data attribution. It distinguishes source evidence from dependency candidates and documents exceptional notice sources. It does not claim that every package in an upstream lock contributes code to the distributed bundle.

The project-code licence is Apache-2.0, as approved by the owner. Third-party software and external data retain their own terms. The identified notice obligations for the reviewed source snapshot are supplied by these files and the [benchmark data notice](benchmark/DATA-NOTICE.md). Changing a bundled library or redistributing an installed environment requires reviewing the resulting distribution and updating its notice inventory.
