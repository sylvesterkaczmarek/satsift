#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "public-evidence-manifest-v1.0.json"
DEFAULT_OUTPUT = ROOT / "benchmark-data" / "public-evidence-benchmark-v1.0.recipe.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def direct_query(norad: str, start: str, end: str) -> str:
    end_exclusive = str(__import__('datetime').date.fromisoformat(end) + __import__('datetime').timedelta(days=1))
    epoch = f"{start}T00:00:00--{end_exclusive}T00:00:00"
    return (
        "https://www.space-track.org/basicspacedata/query/class/gp_history"
        f"/NORAD_CAT_ID/{quote(norad, safe='')}"
        f"/EPOCH/{quote(epoch, safe='')}"
        "/orderby/EPOCH%20asc/limit/5000/format/json/emptyresult/show"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the frozen Space-Track materialization recipe for benchmark v1.0.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    cases = []
    for item in manifest["cases"]:
        norad = str(item["object_id"])
        start = str(item["start_date"])
        end = str(item["end_date"])
        cases.append({
            "case_id": item["case_id"],
            "object_id": norad,
            "object_name": item.get("object_name"),
            "split": item["split"],
            "orbit_profile": item["orbit_profile"],
            "start_date": start,
            "end_date": end,
            "same_site_request": (
                "https://www.sylvesterkaczmarek.com/satellite-maneuver-detector/history"
                f"?norad={norad}&start={start}&end={end}"
            ),
            "space_track_gp_history_query": direct_query(norad, start, end),
        })

    recipe = {
        "schema": "smd-space-track-materialization-recipe-v1",
        "benchmark_version": "1.0",
        "source_manifest": args.manifest.name,
        "source_manifest_sha256": sha256_bytes(manifest_bytes),
        "source": "Space-Track Basic SSA GP_History OMM JSON",
        "data_attribution": manifest.get("data_attribution"),
        "query_semantics": {
            "class": "gp_history",
            "epoch_interval": "UTC start date 00:00:00 inclusive through day after end date 00:00:00 exclusive",
            "ordering": "EPOCH asc",
            "limit": 5000,
            "format": "json",
            "emptyresult": "show",
        },
        "normalization": {
            "catalog_id_must_match": True,
            "records_sorted_by_epoch": True,
            "exact_epoch_duplicates": "retain preferred catalogue record: later CREATION_DATE, then larger ELEMENT_SET_NO",
            "near_simultaneous_catalogue_revisions": "preserved for detector method 0.4 catalogue-revision resolution",
            "raw_fields": "preserve Space-Track OMM JSON record fields returned for each selected record",
        },
        "reconstruction": {
            "direct": "python3 tools/materialize_benchmark_v1_spacetrack.py --recipe benchmark-data/public-evidence-benchmark-v1.0.recipe.json --manifest public-evidence-manifest-v1.0.json --output benchmark-data/public-evidence-benchmark-v1.0.json",
            "same_site": "python3 tools/build_public_evidence_benchmark.py --manifest public-evidence-manifest-v1.0.json --output benchmark-data/public-evidence-benchmark-v1.0.json",
            "credential_environment": ["SPACETRACK_IDENTITY", "SPACETRACK_PASSWORD"],
            "note": "The same-site endpoint is rate limited by design. Direct materialization is preferred for one-shot publication reconstruction when credentials are available.",
        },
        "case_count": len(cases),
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(recipe, indent=2) + "\n").encode()
    args.output.write_bytes(encoded)
    digest = sha256_bytes(encoded)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(f"{digest}  {args.output.name}\n")
    print(f"Wrote {len(cases)} history recipes. SHA-256 {digest}")


if __name__ == "__main__":
    main()
