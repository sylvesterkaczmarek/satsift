# Materialisation guide

## Scope and version

`materialize_benchmark_v1_spacetrack.py` retrieves authorised Space-Track GP history and builds a dataset from a bound manifest and query recipe. The maintained materialiser is version `2.0`. New datasets include `materializer_version`, `record_selection_policy` and `response_validation_policy` alongside the manifest and recipe hashes.

This tool version identifies input validation and record-selection behaviour independently of the workbench release. It does not change detector method 0.4 or the frozen benchmark's label version, scoring rules or recorded research results.

The accepted input schemas remain `smd-public-evidence-manifest-v1.0` and `smd-space-track-materialization-recipe-v1`. The recipe must identify the exact manifest bytes through `source_manifest_sha256`, share its benchmark version and case identifiers, and bind each direct query to the manifest object and date window.

## Use a separate output

Provide private credentials through `SPACETRACK_IDENTITY` and `SPACETRACK_PASSWORD`. Keep credentials, session cookies and raw source data outside version control. Supply a matching manifest and recipe, and choose an unused output location:

```sh
python3 tools/materialize_benchmark_v1_spacetrack.py \
  --recipe path/to/new-study.recipe.json \
  --manifest path/to/new-study.manifest.json \
  --output path/to/new-study.materialized.json
```

`--output` is required. The helper refuses an existing output file or its `.sha256` sidecar and refuses the frozen benchmark output location. It checks the complete recipe/manifest binding and output destination before authentication. Case identifiers, object identifiers, windows and direct queries must agree. The dataset and checksum are written only after every case has passed validation; a bad later case cannot produce an apparently complete dataset containing only earlier cases. Existing destination files are never overwritten.

The new JSON file has a SHA-256 sidecar. Keep the output, sidecar, manifest, recipe and their version information together.

Each case records its admission counts in `source_window`:

| Field | Meaning |
| --- | --- |
| `raw_record_count` | All rows received before boundary exclusion or revision selection. |
| `record_count` | Selected observations retained in the dataset. |
| `excluded_end_boundary_records` | Fully validated observations at midnight after the requested final day. |
| `superseded_or_duplicate_records` | In-window rows removed by deterministic revision or duplicate selection. |

The three disposition counts sum to `raw_record_count`. These counts account for selection and boundary handling; malformed rows cause failure and never enter a successful dataset.

## Response admission

Every upstream row is validated before duplicate selection. One malformed row rejects the response. Invalid rows are never silently discarded.

The admission rules reject:

- A non-list payload or a non-object row.
- Invalid JSON, duplicate object keys, including names that differ only in letter case, and nonfinite numeric values.
- Reserved `SMD_*` extensions in provider records; these are local workbench metadata.
- Missing, malformed or out-of-range required orbital fields.
- Malformed supplied optional metadata, including catalogue identifiers and creation timestamps.
- A catalogue identifier that differs from the requested object.
- An epoch before the requested start or beyond the following midnight.
- A raw response containing 5,000 or more rows, before any exclusion.
- A response body larger than 10 MiB (10,485,760 bytes).
- A response with no retained observations.

For browser compatibility, supplied `ELEMENT_SET_NO` and `REV_AT_EPOCH` values must not exceed `9007199254740991`. Larger `GP_ID` values must use decimal strings. `NORAD_CAT_ID` must use a positive one-to-nine-digit integer or decimal string without leading zeros.

JSON numbers that would lose supplied decimal precision, underflow or exceed the safe integer range are rejected. Use decimal strings where supported to retain precise source values.

Timestamps use strict calendar validation. Fractional seconds may contain one to six digits; a timestamp without a timezone is interpreted as UTC. Explicit offsets are converted to the same UTC instant for comparison, preserving microseconds.

A requested date window starts at midnight on its first date and ends just before midnight after its final date. An upstream observation exactly at that following midnight is fully validated, excluded from retained evidence and counted. This handles the inclusive query boundary without extending the requested window or hiding an invalid boundary row.

## Revision selection

Records are grouped by their exact UTC epoch. Equivalent timezone spellings belong to one group, and distinct microseconds remain distinct epochs.

Within a group, metadata precedence is:

1. A supplied valid creation timestamp, then the later UTC creation instant.
2. A supplied valid element-set identifier, then the larger integer.
3. A supplied valid GP identifier, then the larger integer.

Creation time has priority over both identifiers. Missing metadata remains missing; genuine zero is a supplied value. Integer identifiers are compared without floating-point conversion, and equivalent leading-zero spellings tie.

The complete epoch group is ranked before conflicts are considered. Conflicting weaker revisions can be superseded by an unambiguous stronger revision. Conflicting orbital solutions tied at the strongest rank cause an explicit failure. Equivalent remaining records use a stable canonical JSON tie-break, so reversing the input order does not change the selected record.

Selected records retain their original raw field values. The output uses canonical key ordering and chronological epoch ordering. Near-simultaneous observations with different exact epochs remain available to the detector's catalogue-revision rules.

## Historical compatibility

The committed benchmark v1.0 manifest, query recipe, protocol, checksum files and research records remain unchanged. The frozen recipe describes the original queries and historical reconstruction procedure. The maintained helper requires a separate output and records its newer selection and admission policies.

A fresh upstream response can contain different catalogue revisions or availability. Applying repaired selection rules to a new response does not recreate the original materialised source bytes. Exact historical verification continues to use the retained hashes, case-level outputs and archived evaluator described in [the historical verification boundary](../research/HISTORICAL-VERIFICATION.md).

The consumed confirmatory partition cannot become an untouched holdout through a new tool or dataset version. New research claims need the separately defined data and evaluation protocol appropriate to that study.

## Offline verification

```sh
python3 tests/materializer_validation_test.py
python3 tests/benchmark_v1_manifest_test.py
PYTHONPATH=. python3 tools/confirmatory_post_result_audit.py
```

The materialiser regression uses synthetic responses and mocked authentication and transport. It does not contact Space-Track or use private credentials. The other checks verify the frozen manifest and recorded historical results without collecting or scoring a new experiment.
