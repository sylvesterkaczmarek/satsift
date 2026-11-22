#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CURATION = ROOT / "benchmark" / "benchmark-v1-curation.json"
DEFAULT_OUTPUT = ROOT / "public-evidence-manifest-v1.0.json"

SOURCE_META = {
    "DORIS-IDS": {
        "confidence": "high-public-evidence",
        "evidence_kind": "executed-tracking-network-maneuver-history",
        "licence_note": "International DORIS Service public maneuver history.",
    },
    "GPS-NANU": {
        "confidence": "medium-public-evidence-scheduled",
        "evidence_kind": "scheduled-forecast-delta-v",
        "licence_note": "GPS NANU notices are U.S. Government public information; FCSTDV is a forecast Delta-V outage, not an execution confirmation.",
        "authority_url": "https://navcen.uscg.gov/nanu-abbreviations-and-descriptions",
    },
    "GALILEO-NAGU": {
        "confidence": "medium-public-evidence-scheduled",
        "evidence_kind": "planned-maneuver-outage",
        "licence_note": "Galileo NAGU notices are reused with European GNSS Service Centre / EU attribution; PLN_MANV is a planned maneuver notice.",
        "authority_url": "https://www.gsc-europa.eu/system-service-status/nagu-information",
    },
    "NOAA-GOES": {
        "confidence": "high-public-evidence-day-censored",
        "evidence_kind": "operator-last-maneuver-date-reconstructed-from-archived-live-state",
        "licence_note": "NOAA navigation summaries are U.S. Government public information. Historical last-maneuver dates were reconstructed from content-distinct Internet Archive snapshots of the NOAA live-state file.",
        "authority_url": "https://www.ospo.noaa.gov/resources/cemscs/navsum.txt",
    },
    "QZSS-OHI": {
        "confidence": "high-public-evidence",
        "evidence_kind": "executed-operator-history",
        "licence_note": "Source: Quasi-Zenith Satellite System website. QZSS OHI is reuse-with-attribution / CC-BY-4.0 as documented by the pinned source dataset.",
    },
}

SPLIT_ORDER = {"development": 0, "calibration": 1, "confirmatory": 2}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def date_bounds(start_date: str, end_date: str) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    end_exclusive = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + timedelta(days=1)
    return start, end_exclusive


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text[:48] or "object"


def source_url(source: str, source_ref: str, label_ref: str | None) -> str:
    if source == "DORIS-IDS":
        if not label_ref:
            raise ValueError("DORIS case is missing label_ref")
        return f"https://ids-doris.org/documents/BC/satellites/{label_ref}man.txt"
    if source == "GPS-NANU":
        match = re.search(r"NANU\s+(\d{7})", source_ref)
        if not match:
            raise ValueError(f"Could not parse NANU number from {source_ref!r}")
        number = match.group(1)
        return f"https://celestrak.org/GPS/NANU/{number[:4]}/nanu.{number}.txt"
    if source == "GALILEO-NAGU":
        match = re.search(r"NAGU\s+(\d{7})", source_ref)
        if not match:
            raise ValueError(f"Could not parse NAGU number from {source_ref!r}")
        number = match.group(1)
        return f"https://www.gsc-europa.eu/sites/default/files/NOTICE_ADVISORY_TO_GALILEO_USERS_NAGU_{number}.txt"
    if source == "NOAA-GOES":
        return "https://www.ospo.noaa.gov/resources/cemscs/navsum.txt"
    if source == "QZSS-OHI":
        if not label_ref:
            raise ValueError("QZSS case is missing label_ref")
        return f"https://qzss.go.jp/en/technical/qzssinfo/khp0mf0000000wuf-att/ohi-{label_ref}.txt"
    raise ValueError(f"Unsupported source: {source}")


def event_from_external(label: dict, label_ref: str | None) -> dict:
    source = str(label["source"])
    meta = SOURCE_META[source]
    event = {
        "start": parse_utc(label["window_start"]).isoformat().replace("+00:00", "Z"),
        "end": parse_utc(label["window_end"]).isoformat().replace("+00:00", "Z"),
        "label": str(label["source_ref"]),
        "source": source_url(source, str(label["source_ref"]), label_ref),
        "source_family": source,
        "source_ref": str(label["source_ref"]),
        "evidence_kind": meta["evidence_kind"],
    }
    if meta.get("authority_url"):
        event["authority_url"] = meta["authority_url"]
    if label.get("maneuver_type") is not None:
        event["maneuver_type"] = label["maneuver_type"]
    if label.get("delta_v") is not None:
        event["delta_v_mps"] = float(label["delta_v"])
    return event


def compile_manifest(curation: dict, external_root: Path) -> dict:
    ext = curation["external_label_source"]
    labels_path = external_root / ext["labels_path"]
    recipe_path = external_root / ext["recipe_path"]
    labels_bytes = labels_path.read_bytes()
    actual_sha = sha256_bytes(labels_bytes)
    if actual_sha != ext["labels_sha256"]:
        raise ValueError(f"External labels SHA-256 mismatch: {actual_sha} != {ext['labels_sha256']}")
    labels = json.loads(labels_bytes)
    recipe = json.loads(recipe_path.read_text())
    entries = recipe.get("entries") if isinstance(recipe, dict) else None
    if not isinstance(entries, list):
        raise ValueError("External recipe does not contain entries")
    entry_by_norad = {int(item["norad_id"]): item for item in entries}

    allowed = set(ext["allowed_sources"])
    forbidden = set(ext.get("forbidden_sources", []))
    external_cases: list[dict] = []
    for selection in curation["external_cases"]:
        norad = int(selection["norad_id"])
        source = str(selection["expected_source"])
        if source not in allowed or source in forbidden:
            raise ValueError(f"NORAD {norad}: source {source} is not permitted")
        entry = entry_by_norad.get(norad)
        if not entry:
            raise ValueError(f"NORAD {norad}: missing from external recipe")
        if str(entry.get("object_name")) != str(selection["expected_object_name"]):
            raise ValueError(f"NORAD {norad}: object-name mismatch")
        if str(entry.get("orbit_class")) != str(selection["orbit_regime"]):
            raise ValueError(f"NORAD {norad}: orbit-regime mismatch")
        start, end_exclusive = date_bounds(selection["start_date"], selection["end_date"])
        chosen = [
            item for item in labels
            if item.get("norad_id") is not None
            and int(item["norad_id"]) == norad
            and str(item.get("source")) == source
            and parse_utc(item["window_end"]) >= start
            and parse_utc(item["window_start"]) < end_exclusive
        ]
        chosen.sort(key=lambda item: (parse_utc(item["window_start"]), parse_utc(item["window_end"]), str(item["source_ref"])))
        expected_count = int(selection["expected_event_count"])
        if len(chosen) != expected_count:
            raise ValueError(f"NORAD {norad}: expected {expected_count} event(s), found {len(chosen)}")
        meta = SOURCE_META[source]
        label_ref = entry.get("label_ref")
        truth = [event_from_external(item, label_ref) for item in chosen]
        case_id = f"{source.lower().replace('_','-')}-{slug(str(entry['object_name']))}-{norad}-{selection['start_date']}"
        primary_source = source_url(source, str(chosen[0]["source_ref"]), label_ref)
        external_cases.append({
            "case_id": case_id,
            "object_id": str(norad),
            "object_name": str(entry["object_name"]),
            "orbit_profile": str(selection["detector_orbit_profile"]),
            "orbit_regime": str(selection["orbit_regime"]),
            "split": str(selection["split"]),
            "label_status": "event-evidence",
            "label_confidence": meta["confidence"],
            "evidence_kind": meta["evidence_kind"],
            "start_date": str(selection["start_date"]),
            "end_date": str(selection["end_date"]),
            "description": f"{entry['object_name']} maneuver-evidence window from {source}; {len(truth)} documented interval(s).",
            "source": primary_source,
            "source_family": source,
            "source_licence_note": meta["licence_note"],
            "source_provenance": {
                "curated_from": f"{ext['repository']}@{ext['commit']}",
                "external_labels_path": ext["labels_path"],
                "external_labels_sha256": ext["labels_sha256"],
                "external_source_ref": label_ref,
                "authority_url": meta.get("authority_url"),
            },
            "truth_events": truth,
        })

    direct_cases = json.loads(json.dumps(curation["direct_cases"]))
    for case in direct_cases:
        case["source_family"] = "DIRECT"
        case["source_provenance"] = {"curated_directly": True}

    cases = external_cases + direct_cases
    cases.sort(key=lambda item: (
        SPLIT_ORDER.get(str(item["split"]), 99),
        str(item.get("orbit_profile", "")),
        int(item["object_id"]),
        str(item["case_id"]),
    ))
    validate_manifest_cases(cases, curation)

    count_by_split: dict[str, dict[str, int]] = {}
    for split in SPLIT_ORDER:
        split_cases = [case for case in cases if case["split"] == split]
        count_by_split[split] = {
            "cases": len(split_cases),
            "objects": len({case["object_id"] for case in split_cases}),
            "truth_event_intervals": sum(len(case.get("truth_events", [])) for case in split_cases),
            "verified_quiet_cases": sum(case["label_status"] == "verified-quiet" for case in split_cases),
        }

    return {
        "schema": "smd-public-evidence-manifest-v1.0",
        "name": "Satellite maneuver publication benchmark v1.0",
        "version": "1.0",
        "matching_tolerance_hours": int(curation["label_policy"]["matching_tolerance_hours"]),
        "data_attribution": "Basic SSA orbital data from Space-Track.org, operated by U.S. Space Command. Public maneuver evidence is cited per case.",
        "qualification": "Positive-unlabelled publication benchmark. Event-evidence intervals are scored only where a public source documents a maneuver; predictions elsewhere in those cases remain unscored. Verified-quiet controls require explicit evidence that maneuvering had ceased, was unavailable, or required no further assistance. Unlabelled periods are never negatives.",
        "split_policy": curation["split_policy"],
        "label_policy": curation["label_policy"],
        "external_label_provenance": {
            **ext,
            "licence": "CC-BY-4.0 for the external dataset's authored recipe/parsed-label artifacts; underlying public sources retain their own terms.",
            "excluded_source_families": sorted(forbidden),
        },
        "frozen_counts": {
            "cases": len(cases),
            "unique_satellites": len({case["object_id"] for case in cases}),
            "event_evidence_cases": sum(case["label_status"] == "event-evidence" for case in cases),
            "verified_quiet_cases": sum(case["label_status"] == "verified-quiet" for case in cases),
            "truth_event_intervals": sum(len(case.get("truth_events", [])) for case in cases),
            "by_split": count_by_split,
        },
        "cases": cases,
    }


def validate_manifest_cases(cases: list[dict], curation: dict) -> None:
    allowed_splits = set(curation["split_policy"]["splits"])
    split_by_object: dict[str, str] = {}
    case_ids: set[str] = set()
    event_regimes: set[str] = set()
    for case in cases:
        cid = str(case["case_id"])
        if cid in case_ids:
            raise ValueError(f"Duplicate case_id: {cid}")
        case_ids.add(cid)
        split = str(case["split"])
        if split not in allowed_splits:
            raise ValueError(f"{cid}: unsupported split {split}")
        obj = str(case["object_id"])
        previous = split_by_object.setdefault(obj, split)
        if previous != split:
            raise ValueError(f"NORAD {obj} appears in both {previous} and {split}")
        status = str(case["label_status"])
        truth = case.get("truth_events") or []
        if status == "event-evidence":
            if not truth:
                raise ValueError(f"{cid}: event-evidence case has no truth intervals")
            event_regimes.add(str(case["orbit_profile"]))
        elif status == "verified-quiet":
            if truth:
                raise ValueError(f"{cid}: verified-quiet case contains truth intervals")
        else:
            raise ValueError(f"{cid}: v1.0 supports only event-evidence and verified-quiet")
    unique = len(split_by_object)
    truths = sum(len(case.get("truth_events") or []) for case in cases)
    targets = curation["minimum_targets"]
    if unique < int(targets["unique_satellites"]):
        raise ValueError(f"Only {unique} unique satellites; target is {targets['unique_satellites']}")
    if truths < int(targets["truth_event_intervals"]):
        raise ValueError(f"Only {truths} truth intervals; target is {targets['truth_event_intervals']}")
    missing_regimes = {"LEO", "MEO", "GEO", "HEO"} - event_regimes
    if missing_regimes:
        raise ValueError("Missing event-evidence orbit regime(s): " + ", ".join(sorted(missing_regimes)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile frozen publication benchmark v1.0 manifest from pinned public evidence.")
    parser.add_argument("--curation", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--external-root", type=Path, required=True, help="Checkout root of the pinned external label repository.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    curation = json.loads(args.curation.read_text())
    manifest = compile_manifest(curation, args.external_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(manifest, indent=2, sort_keys=False) + "\n").encode()
    args.output.write_bytes(encoded)
    digest = sha256_bytes(encoded)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(f"{digest}  {args.output.name}\n")
    print(json.dumps(manifest["frozen_counts"], indent=2))
    print(f"Manifest SHA-256 {digest}")


if __name__ == "__main__":
    main()
