# History retention and corrections

This policy applies to the maintained workbench and history endpoint from Workbench 3.4.7. Its purpose is to retain acquired data, identify the source snapshots used in an analysis and handle corrections explicitly. It does not change the frozen research inputs or authorise another evaluation.

## Provider guidance

The [Space-Track API guidelines](https://www.space-track.org/documentation), checked on 22 November 2026, require downloaded GP_HISTORY data to be retained and direct current-element retrieval to the GP class. Large historical collections should use the provider's archive or an agreed collection plan. This endpoint therefore retains covered dates and has no automatic historical expiry or force-refresh operation.

The current-snapshot control uses CelesTrak's GP service. Its [usage policy](https://celestrak.org/usage-policy.php) and [GP documentation](https://celestrak.org/NORAD/documentation/gp-data-formats.php), checked on the same date, limit downloads to data needed for use and one download per update; GP updates occur every two hours. The existing local two-hour cache remains in place. Shared networks and multiple applications must coordinate their own use of the provider. An upstream error is reported for investigation without an automatic retry loop.

## Supported acquisition paths

| Situation | Behaviour |
| --- | --- |
| Requested historical dates are already covered | Read and validate retained history. Preserve acquisition timestamps and source identities. |
| Some historical dates have never been stored | Request only the missing ranges, subject to the admission and storage limits. Commit new data and acquisition metadata together after every fragment succeeds. |
| A current element is needed | Explicitly load the CelesTrak GP snapshot and append it to the existing analysis. Reuse the local cache within its two-hour window. |
| A catalogue correction is supplied | Import or append an authorised correction file using the procedure below. Preserve the original analysis and source artefact. |
| A broad historical collection or unusual correction is needed | Use the provider's published archive or obtain guidance for the intended collection. Do not repeatedly query held history to check whether it changed. |

The endpoint accepts date ranges up to 31 days ending no later than yesterday. Its coverage marker means the range was acquired, including a legitimate empty response. It cannot establish that the provider will never publish a later correction. Cache age, a new page load, and an extra query parameter do not trigger historical refetching. Removing a cache file to force a repeat download is outside this policy.

A current GP snapshot can add a new observation or a recognised revision. It cannot reconstruct missed observations between snapshots or guarantee discovery of every historical correction. The workbench does not operate a background collector.

## Acquisition times and source identities

New persistent history stores use version 2. Each successful upstream fragment adds an acquisition entry with its requested date range, the actual UTC retrieval time and the SHA-256 of its accepted raw records. The complete store digest also includes the acquisition metadata and store update time. Cache hits preserve those bytes.

Version 1 stores remain readable. A cache hit does not rewrite them. If a later request adds previously unheld dates, the new store records the inherited ranges as `legacy-cache` acquisitions with unknown retrieval times. The old `updated_at` field is not sufficient evidence of when each range was fetched, so the upgrade does not promote it to an acquisition timestamp.

The response distinguishes these fields:

| Field | Meaning |
| --- | --- |
| `served_at` | UTC time this HTTP response was served. It is not source freshness evidence. |
| `retrieved_at` | Latest acquisition time for the requested coverage when all of that coverage has recorded acquisition times; otherwise `null`. Individual acquisitions retain their own times. |
| `data_provenance.records_sha256` | Content identity of the raw record array selected for this response. |
| `data_provenance.cache_snapshot_sha256` | Identity of the complete validated cache snapshot. It can change when unrelated dates are added even if the selected records are unchanged. |
| `data_provenance.cache_updated_at` | Last committed version 2 store update. Legacy responses use `null`. This is not a promise of provider freshness. |
| `data_provenance.acquisitions` | Acquisition evidence for the requested coverage, including explicit legacy entries with unknown retrieval time. |
| `data_provenance.retrieval_status` | `recorded`, `partial` or `legacy-unknown`, according to the acquisition evidence available for the requested range. |

These SHA-256 values identify local content snapshots. They are not provider release numbers or signatures. A digest detects inconsistency relative to retained metadata; it cannot authenticate a provider or recover a lost acquisition record. Source `GP_ID`, `ELEMENT_SET_NO` and `CREATION_DATE` remain record metadata and keep their existing catalogue-selection semantics.

The store holds at most 4,096 acquisition entries within its existing size limit. A request that cannot retain the additional evidence stops before upstream work. Prior records and acquisition entries remain intact. The [deployment guide](DEPLOYMENT.md#history-endpoint-limits) describes the other limits and coordinated upgrade procedure.

## Analysis exports and reopening

Machine-readable analyses and reproducibility packages carry optional, independently versioned `data_provenance`. Source entries identify reported Space-Track snapshots, current CelesTrak GP acquisitions or an input component whose acquisition was not recorded. The CelesTrak entry uses the original fetch time, including when the snapshot comes from local storage. Importing a local file does not prove when its provider data was retrieved.

The browser separately binds provenance to its normalised OMM input using `fnv1a64-utf16-normalized-omm-v1`. This is a noncryptographic consistency fingerprint. The server's raw-record SHA-256 and the browser's normalised-input fingerprint cover different representations and must not be substituted for one another. Source lineage retains acquisitions, including batches whose rows were later superseded. It does not claim a verified source assignment for every surviving record after a merge.

Package schema 1 and run identity version 2 remain supported. A package with supplied provenance is validated before input or settings are changed. Reopening preserves its acquisition evidence. Older packages remain usable with unknown acquisition provenance. Serving time and acquisition metadata are separate from the numerical run identifier.

Successful append operations retain the source lineage of the existing and incoming data. Failed or unchanged appends preserve existing provenance. Manual text editing, demonstrations and unrelated replacement clear prior provenance. Browser provenance is bounded to 64 source entries, 64 acquisitions per history source and 64 KiB. Unsupported or excessive supplied metadata is rejected rather than silently dropping earlier evidence.

## Applying a correction

1. Export the current reproducibility package and retain its original source file privately. Preserve the original acquisition evidence and any provider notice or permission associated with the correction.
2. Obtain the correction from an authorised provider source or an already retained local artefact. For a current GP observation, use the existing current-snapshot control. A new local import time must not be recorded as the provider retrieval time.
3. Choose **Append and merge** for a correction intended to participate in catalogue revision selection. The existing validation and ordering rules apply. Unresolved equal-rank alternatives remain a data-quality issue; changing identifiers or timestamps to force a preferred result would invalidate the evidence.
4. If the reviewed correction replaces a whole history or removes a wrongly associated observation, use **Replace current input** with the reviewed complete history. Keep the original package and document the reason privately. Appending a new epoch alone does not remove an obsolete record at another epoch.
5. Review the accepted records, supersession diagnostics, abstentions and changed results. Export a new reproducibility package. Keep the original and corrected packages separately so that their inputs, source identities and decisions remain reviewable.

This procedure changes the selected browser analysis. It does not silently revise the persistent server cache. Server-side correction requires a separately reviewed maintenance procedure that preserves the original cache and follows provider guidance; there is no public cache-mutation route in this release. Frozen benchmark data, result files, checksums and the one-shot run lock remain the historical evidence of record.

## Offline verification

Run these checks from the repository root:

```sh
python3 tests/history_provenance_test.py
node tests/history_provenance_test.js
```

The PHP checks use isolated temporary caches, dummy credentials and a loopback upstream. They verify stable cache-hit provenance, legacy migration, metadata integrity, bounded growth, failure preservation and concurrent requests. Browser checks cover acquisition capture, export and reopening, append lineage, invalid metadata and stale-provenance removal. The existing admission, cache-integrity and scientific freeze checks continue to apply.
