#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "public-evidence-manifest-v1.0.json"
MANIFEST_SHA = ROOT / "public-evidence-manifest-v1.0.json.sha256"
RECIPE = ROOT / "benchmark-data" / "public-evidence-benchmark-v1.0.recipe.json"
RECIPE_SHA = ROOT / "benchmark-data" / "public-evidence-benchmark-v1.0.recipe.json.sha256"
CURATION = ROOT / "benchmark" / "benchmark-v1-curation.json"

EXPECTED_MANIFEST_SHA256 = "a0d72bd15ea579ec2373a5a0cd96c1cf0790bd361b15803f722c740b5e6f7d88"
EXPECTED_COUNTS = {
    "cases": 40,
    "unique_satellites": 40,
    "event_evidence_cases": 30,
    "verified_quiet_cases": 10,
    "truth_event_intervals": 154,
}
EXPECTED_SPLITS = {
    "development": {"cases": 14, "objects": 14, "truth_event_intervals": 49, "verified_quiet_cases": 4},
    "calibration": {"cases": 14, "objects": 14, "truth_event_intervals": 64, "verified_quiet_cases": 4},
    "confirmatory": {"cases": 12, "objects": 12, "truth_event_intervals": 41, "verified_quiet_cases": 2},
}
EXPECTED_CONFIRMATORY = {
    "41240", "46984", "43437", "37781", "32384", "62339",
    "51850", "62876", "26410", "26464", "29108", "26463",
}
PREVIOUSLY_INSPECTED_V03 = {
    "25544", "23560", "28922", "24932", "26411", "39634",
    "34602", "40128", "41836", "27509", "27540",
}
ALLOWED_SOURCE_FAMILIES = {"DORIS-IDS", "GPS-NANU", "GALILEO-NAGU", "NOAA-GOES", "QZSS-OHI", "DIRECT"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sidecar_digest(path: Path) -> str:
    return path.read_text().strip().split()[0]


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    for path in (MANIFEST, MANIFEST_SHA, RECIPE, RECIPE_SHA, CURATION):
        if not path.is_file():
            fail(f"Missing frozen benchmark v1 artifact: {path.relative_to(ROOT)}")

    manifest_sha = digest(MANIFEST)
    if manifest_sha != EXPECTED_MANIFEST_SHA256:
        fail(f"Benchmark v1 manifest changed: {manifest_sha} != {EXPECTED_MANIFEST_SHA256}")
    if sidecar_digest(MANIFEST_SHA) != manifest_sha:
        fail("Benchmark v1 manifest SHA sidecar mismatch")

    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("schema") != "smd-public-evidence-manifest-v1.0" or manifest.get("version") != "1.0":
        fail("Benchmark v1 manifest schema/version changed")
    counts = manifest.get("frozen_counts") or {}
    for key, expected in EXPECTED_COUNTS.items():
        if counts.get(key) != expected:
            fail(f"Frozen count {key} changed: {counts.get(key)} != {expected}")
    if counts.get("by_split") != EXPECTED_SPLITS:
        fail("Frozen split counts changed")

    cases = manifest.get("cases") or []
    if len(cases) != 40:
        fail("Expected exactly 40 benchmark v1 cases")
    case_ids = [str(case.get("case_id")) for case in cases]
    if len(set(case_ids)) != len(case_ids):
        fail("Duplicate benchmark v1 case_id")

    split_by_object: dict[str, str] = {}
    profiles_with_events: set[str] = set()
    confirmatory: set[str] = set()
    for case in cases:
        obj = str(case.get("object_id") or "")
        split = str(case.get("split") or "")
        if not obj or split not in EXPECTED_SPLITS:
            fail(f"Invalid object/split in {case.get('case_id')}")
        previous = split_by_object.setdefault(obj, split)
        if previous != split:
            fail(f"Object {obj} crosses split boundary")
        if split == "confirmatory":
            confirmatory.add(obj)

        status = case.get("label_status")
        truths = case.get("truth_events") or []
        family = case.get("source_family")
        if family not in ALLOWED_SOURCE_FAMILIES:
            fail(f"Forbidden/unknown source family {family!r} in {case.get('case_id')}")
        if family == "SELF-GEO":
            fail("SELF-GEO must never enter publication benchmark v1")
        if status == "event-evidence":
            if not truths:
                fail(f"Event-evidence case lacks truth intervals: {case.get('case_id')}")
            profiles_with_events.add(str(case.get("orbit_profile")))
        elif status == "verified-quiet":
            if truths:
                fail(f"Verified-quiet case contains truth intervals: {case.get('case_id')}")
            if family != "DIRECT":
                fail(f"Verified-quiet case must have direct authoritative evidence: {case.get('case_id')}")
        else:
            fail(f"Unexpected label_status in v1: {status}")

        if not str(case.get("source") or "").startswith("https://"):
            fail(f"Case source is not an HTTPS public citation: {case.get('case_id')}")
        if not case.get("label_confidence") or not case.get("evidence_kind"):
            fail(f"Missing confidence/evidence-kind metadata: {case.get('case_id')}")
        for event in truths:
            if not str(event.get("source") or "").startswith("https://"):
                fail(f"Truth event lacks direct HTTPS source: {case.get('case_id')}")
            if not event.get("evidence_kind"):
                fail(f"Truth event lacks evidence kind: {case.get('case_id')}")

        if family in {"GPS-NANU", "GALILEO-NAGU"}:
            confidence = str(case.get("label_confidence") or "")
            if "scheduled" not in confidence:
                fail(f"Scheduled notice source lost scheduled confidence tier: {case.get('case_id')}")

    if profiles_with_events != {"LEO", "MEO", "GEO", "HEO"}:
        fail(f"Event evidence does not cover all four principal profiles: {profiles_with_events}")
    if confirmatory != EXPECTED_CONFIRMATORY:
        fail(f"Confirmatory object list changed: {sorted(confirmatory)}")
    overlap = confirmatory & PREVIOUSLY_INSPECTED_V03
    if overlap:
        fail(f"Confirmatory split reuses previously inspected v0.3 objects: {sorted(overlap)}")

    provenance = manifest.get("external_label_provenance") or {}
    if provenance.get("commit") != "b7c6dc2ccc8c93cab5145a58085e64a5d37e4137":
        fail("Pinned external label commit changed")
    if provenance.get("labels_sha256") != "19579666bd7d12763c23b75c9194375801a05ea04d48a2440925ae88122757af":
        fail("Pinned external label SHA-256 changed")
    if "SELF-GEO" not in set(provenance.get("excluded_source_families") or []):
        fail("Manifest must explicitly record SELF-GEO exclusion")

    recipe_sha = digest(RECIPE)
    if sidecar_digest(RECIPE_SHA) != recipe_sha:
        fail("Benchmark v1 materialization recipe SHA sidecar mismatch")
    recipe = json.loads(RECIPE.read_text())
    if recipe.get("schema") != "smd-space-track-materialization-recipe-v1":
        fail("Materialization recipe schema changed")
    if recipe.get("source_manifest_sha256") != manifest_sha:
        fail("Materialization recipe is not bound to the frozen manifest")
    if recipe.get("case_count") != 40 or len(recipe.get("cases") or []) != 40:
        fail("Materialization recipe must contain exactly 40 cases")
    recipe_objects = {str(item.get("object_id")) for item in recipe["cases"]}
    if recipe_objects != set(split_by_object):
        fail("Materialization recipe object set differs from frozen manifest")
    for item in recipe["cases"]:
        direct = str(item.get("space_track_gp_history_query") or "")
        same_site = str(item.get("same_site_request") or "")
        if "/class/gp_history/" not in direct or "/orderby/EPOCH%20asc/limit/5000/format/json/emptyresult/show" not in direct:
            fail(f"Invalid Space-Track recipe query for {item.get('case_id')}")
        if not same_site.startswith("https://www.sylvesterkaczmarek.com/satellite-maneuver-detector/history?"):
            fail(f"Invalid same-site reconstruction request for {item.get('case_id')}")

    print("Benchmark v1 freeze regression passed: 40 satellites, 154 truth intervals, three NORAD-disjoint partitions.")


if __name__ == "__main__":
    main()
