#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECIPE = ROOT / "benchmark-data" / "public-evidence-benchmark-v1.0.recipe.json"
DEFAULT_MANIFEST = ROOT / "public-evidence-manifest-v1.0.json"
# Reserved historical destination, retained here only to prevent overwriting it.
DEFAULT_OUTPUT = ROOT / "benchmark-data" / "public-evidence-benchmark-v1.0.json"
LOGIN_URL = "https://www.space-track.org/ajaxauth/login"
MATERIALIZER_VERSION = "2.0"
MAX_RECORDS = 5000
MAX_SAFE_INTEGER = 9007199254740991
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
UTC = timezone.utc
USER_AGENT = f"SatelliteManeuverBenchmarkMaterializer/{MATERIALIZER_VERSION}"
TIMESTAMP = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]{1,6}))?([Zz]|[+-][0-9]{2}:[0-9]{2})?"
)
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
RECORD_SELECTION_POLICY = {
    "version": 2,
    "epoch_grouping": "exact UTC instant at microsecond precision",
    "precedence": ["CREATION_DATE UTC instant", "ELEMENT_SET_NO integer", "GP_ID integer"],
    "missing_metadata": "supplied valid metadata outranks omission",
    "unresolved_top_rank_conflicts": "reject differing orbital solutions",
    "equivalent_top_rank_records": "retain the lexically first canonical JSON representation",
    "raw_fields": "preserve fields of the selected source record",
}
RESPONSE_VALIDATION_POLICY = {
    "version": 2,
    "timestamps": "strict calendar ISO timestamps with at most six fractional digits; missing zone means UTC",
    "interval": "UTC start midnight inclusive through midnight after the final day exclusive",
    "provider_end_boundary": "validate the exact following midnight, exclude it and report its count",
    "invalid_records": "reject the complete response before record selection",
    "field_names": "case-insensitive, without duplicate aliases or local SMD extensions",
    "numeric_json_values": "reject decimal rounding and unsafe integers; retain precise values as strings",
    "raw_record_limit_exclusive": MAX_RECORDS,
    "maximum_response_bytes": MAX_RESPONSE_BYTES,
}


class MaterializationError(RuntimeError):
    """Invalid source data or a materialisation that cannot be completed safely."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def omitted(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def parse_utc(value: object, field: str = "timestamp") -> datetime:
    match = TIMESTAMP.fullmatch(value.strip()) if isinstance(value, str) else None
    if match is None:
        raise MaterializationError(f"{field} must be an ISO calendar timestamp with at most six fractional digits")
    year, month, day, hour, minute, second = (int(part) for part in match.groups()[:6])
    microsecond = int((match[7] or "").ljust(6, "0"))
    zone = match[8] or "Z"
    offset = timedelta()
    if zone.upper() != "Z":
        zone_hours, zone_minutes = int(zone[1:3]), int(zone[4:6])
        if zone_hours > 23 or zone_minutes > 59:
            raise MaterializationError(f"{field} has an invalid UTC offset")
        offset = timedelta(minutes=(zone_hours * 60 + zone_minutes) * (1 if zone[0] == "+" else -1))
    try:
        return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=timezone(offset)).astimezone(UTC)
    except (ValueError, OverflowError) as error:
        raise MaterializationError(f"{field} has an invalid calendar date or time") from error


def requested_window(start: str, end: str) -> tuple[datetime, datetime]:
    try:
        if not all(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) for value in (start, end)):
            raise ValueError
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first > last:
            raise ValueError
        following = last + timedelta(days=1)
        return datetime.combine(first, datetime.min.time(), UTC), datetime.combine(following, datetime.min.time(), UTC)
    except (ValueError, OverflowError) as error:
        raise MaterializationError("Requested start and end must be valid, ordered YYYY-MM-DD dates") from error


def integer_identifier(value: object, field: str, *, optional: bool = True, maximum: int | None = None) -> int | None:
    if optional and omitted(value):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise MaterializationError(f"{field} must be a non-negative integer when supplied")
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]+", text):
        raise MaterializationError(f"{field} must be a non-negative integer when supplied")
    try:
        number = int(text)
    except ValueError as error:
        raise MaterializationError(f"{field} is too large to parse as an integer") from error
    if maximum is not None and number > maximum:
        raise MaterializationError(f"{field} exceeds the supported integer range")
    return number


def norad_identifier(value: object) -> str:
    number = integer_identifier(value, "NORAD_CAT_ID", optional=False, maximum=999999999)
    if number is None or number < 1 or not re.fullmatch(r"[1-9][0-9]{0,8}", str(value).strip()):
        raise MaterializationError("NORAD_CAT_ID must use canonical digits for an integer from 1 to 999999999")
    return str(number)


def orbital_number(record: dict, field: str, default: int | None = None) -> Decimal:
    value = record.get(field)
    if default is not None and omitted(value):
        return Decimal(default)
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise MaterializationError(f"{field} must be a finite number")
    text = str(value).strip()
    if not NUMBER.fullmatch(text):
        raise MaterializationError(f"{field} must be a finite number")
    try:
        number = Decimal(text)
        if not number.is_finite() or not math.isfinite(float(number)):
            raise ValueError
        return number
    except (InvalidOperation, OverflowError, ValueError) as error:
        raise MaterializationError(f"{field} must be a finite number") from error


def orbital_signature(record: dict) -> tuple:
    fields = ("MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY")
    values = tuple(orbital_number(record, field) for field in fields)
    for field, value in zip(fields, values):
        valid = (float(value) > 0 if field == "MEAN_MOTION" else
                 0 <= value < 1 if field == "ECCENTRICITY" else
                 0 <= value <= 180 if field == "INCLINATION" else 0 <= value < 360)
        if not valid:
            raise MaterializationError(f"{field} is outside its valid orbital range")
    drag = tuple(orbital_number(record, field, 0) for field in ("BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"))
    ephemeris = integer_identifier(record.get("EPHEMERIS_TYPE"), "EPHEMERIS_TYPE")
    if ephemeris is not None and ephemeris not in (0, 2, 3):
        raise MaterializationError("EPHEMERIS_TYPE must use SGP4/SDP4 (0, 2 or 3)")
    integer_identifier(record.get("REV_AT_EPOCH"), "REV_AT_EPOCH", maximum=MAX_SAFE_INTEGER)
    for field, expected in (("CENTER_NAME", "EARTH"), ("REF_FRAME", "TEME"), ("TIME_SYSTEM", "UTC"), ("MEAN_ELEMENT_THEORY", "SGP4")):
        value = record.get(field)
        if not omitted(value) and (not isinstance(value, str) or value.strip().upper() != expected):
            raise MaterializationError(f"{field} must be {expected}")
    return values + drag + (ephemeris or 0,)


def preference_key(record: dict) -> tuple:
    raw_creation = record.get("CREATION_DATE")
    creation = None if omitted(raw_creation) else parse_utc(raw_creation, "CREATION_DATE")
    element_set = integer_identifier(record.get("ELEMENT_SET_NO"), "ELEMENT_SET_NO", maximum=MAX_SAFE_INTEGER)
    gp_raw = record.get("GP_ID")
    if isinstance(gp_raw, int) and not isinstance(gp_raw, bool) and gp_raw > MAX_SAFE_INTEGER:
        raise MaterializationError("GP_ID above the exact JSON integer range must use a decimal string")
    gp_id = integer_identifier(gp_raw, "GP_ID")
    return (
        creation is not None, creation or datetime.min.replace(tzinfo=UTC),
        element_set is not None, element_set if element_set is not None else 0,
        gp_id is not None, gp_id if gp_id is not None else 0,
    )


def canonical_record(record: dict) -> str:
    try:
        return json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise MaterializationError("Record fields must be valid finite JSON values") from error


def record_fields(record: dict) -> dict:
    fields = {}
    for key, value in record.items():
        if not isinstance(key, str):
            raise MaterializationError("Record field names must be strings")
        canonical = key.upper()
        if canonical in fields:
            raise MaterializationError(f"Record contains a case-ambiguous duplicate field {canonical}")
        if canonical.startswith("SMD_"):
            raise MaterializationError("Local SMD extensions are not valid direct Space-Track source fields")
        fields[canonical] = value
    return fields


def response_records(data: object) -> list[dict]:
    if not isinstance(data, list):
        raise MaterializationError("Space-Track GP_History returned a non-list JSON payload")
    if len(data) >= MAX_RECORDS:
        raise MaterializationError(f"Space-Track response reached the {MAX_RECORDS}-record safety limit")
    if not data:
        raise MaterializationError("Space-Track GP_History returned an empty history")
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise MaterializationError(f"Space-Track response record {index} must be a JSON object")
        try:
            record_fields(item)
        except MaterializationError as error:
            raise MaterializationError(f"Record {index}: {error}") from error
    return data


def strict_json(data: bytes, label: str) -> object:
    def reject_constant(_: str) -> None:
        raise MaterializationError(f"{label} contains a non-finite JSON number")

    def exact_integer(value: str) -> int:
        parsed = int(value)
        if abs(parsed) > MAX_SAFE_INTEGER:
            raise MaterializationError(f"{label} contains an unsafe JSON integer; use a decimal string")
        return parsed

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            reject_constant(value)
        if Decimal(value) != Decimal(str(parsed)):
            raise MaterializationError(f"{label} contains a numeric value that loses decimal precision; use a decimal string")
        return parsed

    def unique_object(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise MaterializationError(f"{label} contains a duplicate JSON field")
            result[key] = value
        return result

    try:
        return json.loads(data, parse_constant=reject_constant, parse_float=finite_float, parse_int=exact_integer, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, RecursionError) as error:
        raise MaterializationError(f"{label} is not valid JSON") from error


def request_json(opener: urllib.request.OpenerDirector, url: str, retries: int, backoff: float) -> list[dict]:
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
        raise MaterializationError("Retries must be a non-negative integer")
    if isinstance(backoff, bool) or not isinstance(backoff, (int, float)) or not math.isfinite(backoff) or backoff < 0:
        raise MaterializationError("Backoff must be a finite non-negative number")
    last: Exception | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        try:
            with opener.open(request, timeout=90) as response:
                if response.status != 200:
                    raise MaterializationError(f"Space-Track GP_History returned HTTP {response.status}")
                body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise MaterializationError("Space-Track GP_History response exceeded the byte limit")
            return response_records(strict_json(body, "Space-Track GP_History response"))
        except urllib.error.HTTPError as error:
            last = error
            error.close()
            if error.code != 429 and not (500 <= error.code <= 599):
                raise
        except (urllib.error.URLError, TimeoutError) as error:
            last = error
        if attempt >= retries:
            break
        delay = backoff * (2 ** attempt)
        if not math.isfinite(delay):
            raise MaterializationError("Retry backoff exceeded the finite time range")
        print(f"  transient Space-Track failure; retrying in {delay:.1f}s")
        time.sleep(delay)
    raise MaterializationError(f"Space-Track request failed after {retries + 1} attempt(s): {last}")


@dataclass(frozen=True)
class AdmittedRecord:
    raw: dict
    epoch: datetime
    preference: tuple
    orbit: tuple
    canonical: str


def normalize(records: list[dict], norad: str, start: str, end: str) -> list[dict]:
    response_records(records)
    object_id = norad_identifier(norad)
    first, following = requested_window(start, end)
    by_epoch: dict[datetime, list[AdmittedRecord]] = {}
    # Validate the complete response, including superseded revisions and the
    # provider's inclusive upper-boundary row, before selecting any evidence.
    for index, record in enumerate(records, start=1):
        try:
            fields = record_fields(record)
            if norad_identifier(fields.get("NORAD_CAT_ID")) != object_id:
                raise MaterializationError("NORAD_CAT_ID belongs to the wrong object")
            epoch = parse_utc(fields.get("EPOCH"), "EPOCH")
            if epoch < first or epoch > following:
                raise MaterializationError("EPOCH is outside the requested time interval")
            admitted = AdmittedRecord(record, epoch, preference_key(fields), orbital_signature(fields), canonical_record(record))
        except MaterializationError as error:
            raise MaterializationError(f"Record {index}: {error}") from error
        if epoch < following:
            by_epoch.setdefault(epoch, []).append(admitted)

    selected = []
    for epoch in sorted(by_epoch):
        group = by_epoch[epoch]
        strongest = max(record.preference for record in group)
        winners = [record for record in group if record.preference == strongest]
        if len({record.orbit for record in winners}) > 1:
            raise MaterializationError(f"Unresolved orbital conflict at {epoch.isoformat()}: top-ranked records have equal revision metadata")
        selected.append(min(winners, key=lambda record: record.canonical).raw)
    if not selected:
        raise MaterializationError("No GP_History records fall inside the requested half-open interval")
    return selected


def login(identity: str, password: str) -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    payload = urllib.parse.urlencode({"identity": identity, "password": password}).encode()
    request = urllib.request.Request(
        LOGIN_URL,
        data=payload,
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
        method="POST",
    )
    with opener.open(request, timeout=60) as response:
        if response.status != 200:
            raise MaterializationError(f"Space-Track authentication returned HTTP {response.status}")
        response.read()
    if not list(jar):
        raise MaterializationError("Space-Track authentication did not establish a session cookie")
    return opener


def expected_query(norad: str, start: str, end: str) -> str:
    first, following = requested_window(start, end)
    epoch = first.replace(tzinfo=None).isoformat(timespec="seconds") + "--" + following.replace(tzinfo=None).isoformat(timespec="seconds")
    return (
        "https://www.space-track.org/basicspacedata/query/class/gp_history"
        f"/NORAD_CAT_ID/{urllib.parse.quote(norad, safe='')}"
        f"/EPOCH/{urllib.parse.quote(epoch, safe='')}"
        f"/orderby/EPOCH%20asc/limit/{MAX_RECORDS}/format/json/emptyresult/show"
    )


def validated_cases(recipe: object, manifest: object, manifest_bytes: bytes) -> list[tuple[dict, dict]]:
    if not isinstance(recipe, dict) or recipe.get("schema") != "smd-space-track-materialization-recipe-v1":
        raise MaterializationError("Unsupported materialisation recipe schema")
    if not isinstance(manifest, dict) or manifest.get("schema") != "smd-public-evidence-manifest-v1.0":
        raise MaterializationError("Unsupported public-evidence manifest schema")
    if recipe.get("source_manifest_sha256") != sha256_bytes(manifest_bytes):
        raise MaterializationError("Recipe source_manifest_sha256 does not match the supplied manifest")
    if recipe.get("benchmark_version") != manifest.get("version"):
        raise MaterializationError("Recipe benchmark version does not match the manifest")
    for field in ("name", "version", "matching_tolerance_hours", "qualification", "data_attribution",
                  "split_policy", "label_policy", "external_label_provenance", "frozen_counts"):
        if field not in manifest:
            raise MaterializationError(f"Manifest is missing {field}")
    manifest_rows, recipe_rows = manifest.get("cases"), recipe.get("cases")
    if not isinstance(manifest_rows, list) or not manifest_rows or not isinstance(recipe_rows, list) or not recipe_rows:
        raise MaterializationError("Manifest and recipe must contain non-empty case lists")
    if type(recipe.get("case_count")) is not int or recipe["case_count"] != len(recipe_rows):
        raise MaterializationError("Recipe case_count does not match its cases")

    def indexed_cases(rows: list, label: str) -> dict[str, dict]:
        indexed = {}
        for row in rows:
            case_id = row.get("case_id") if isinstance(row, dict) else None
            if not isinstance(case_id, str) or not case_id.strip() or case_id in indexed:
                raise MaterializationError(f"{label} has a missing or duplicate case_id")
            indexed[case_id] = row
        return indexed

    manifest_cases = indexed_cases(manifest_rows, "Manifest")
    recipe_cases = indexed_cases(recipe_rows, "Recipe")
    if manifest_cases.keys() != recipe_cases.keys():
        raise MaterializationError("Recipe cases do not exactly match the manifest cases")
    result = []
    for case_id, item in manifest_cases.items():
        spec = recipe_cases[case_id]
        for field in ("object_id", "start_date", "end_date", "orbit_profile", "split",
                      "label_status", "label_confidence", "source"):
            if field not in item:
                raise MaterializationError(f"{case_id}: manifest case is missing {field}")
        norad = norad_identifier(item["object_id"])
        if norad_identifier(spec.get("object_id")) != norad:
            raise MaterializationError(f"{case_id}: recipe object does not match the manifest")
        start, end = item["start_date"], item["end_date"]
        requested_window(start, end)
        if spec.get("start_date") != start or spec.get("end_date") != end:
            raise MaterializationError(f"{case_id}: recipe dates do not match the manifest")
        if spec.get("space_track_gp_history_query") != expected_query(norad, start, end):
            raise MaterializationError(f"{case_id}: recipe query does not match the manifest object and interval")
        result.append((spec, item))
    return result


def output_destinations(output: Path, inputs: tuple[Path, ...] = ()) -> tuple[Path, Path]:
    sidecar = output.with_suffix(output.suffix + ".sha256")
    if output.resolve() == DEFAULT_OUTPUT.resolve():
        raise MaterializationError("The historical benchmark output is reserved; choose a new output path")
    input_paths = {path.resolve() for path in inputs}
    for destination in (output, sidecar):
        if destination.resolve() in input_paths:
            raise MaterializationError("Output must not replace a recipe or manifest input")
        if destination.exists() or destination.is_symlink():
            raise MaterializationError("Output or SHA-256 sidecar already exists; choose a new output path")
    return output, sidecar


def write_output(output: Path, encoded: bytes) -> str:
    destinations = output_destinations(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(encoded)
    payloads = (encoded, f"{digest}  {output.name}\n".encode())
    created = []
    try:
        # Exclusive creation works on both native filesystems and exFAT. Keep
        # handles open until both files are complete so rollback can identify
        # this invocation's files without removing another writer's replacement.
        for destination, payload in zip(destinations, payloads):
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            handle = os.fdopen(descriptor, "wb")
            created.append((destination, handle))
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        for destination, handle in reversed(created):
            try:
                if os.path.samestat(os.fstat(handle.fileno()), destination.stat()):
                    destination.unlink()
            except FileNotFoundError:
                pass
        raise MaterializationError("Could not write output and checksum without overwriting existing files") from error
    finally:
        for _, handle in created:
            handle.close()
    return digest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Materialise a new benchmark copy from Space-Track GP_History with validated UTC record selection.")
    parser.add_argument("--recipe", type=Path, default=DEFAULT_RECIPE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True, help="New output path; existing files and the historical benchmark destination are protected")
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--backoff-seconds", type=float, default=3.0)
    args = parser.parse_args(argv)
    if args.retries < 0 or not all(math.isfinite(value) and value >= 0 for value in (args.delay_seconds, args.backoff_seconds)):
        raise MaterializationError("Retries must be non-negative; delay and backoff must be finite and non-negative")
    output_destinations(args.output, (args.recipe, args.manifest))
    recipe_bytes, manifest_bytes = args.recipe.read_bytes(), args.manifest.read_bytes()
    recipe = strict_json(recipe_bytes, "Recipe")
    manifest = strict_json(manifest_bytes, "Manifest")
    cases = validated_cases(recipe, manifest, manifest_bytes)

    identity = os.environ.get("SPACETRACK_IDENTITY", "").strip()
    password = os.environ.get("SPACETRACK_PASSWORD", "")
    if not identity or not password:
        raise MaterializationError("Set SPACETRACK_IDENTITY and SPACETRACK_PASSWORD in the environment. Credentials are never written to output.")
    opener = login(identity, password)

    built = []
    for index, (spec, item) in enumerate(cases, start=1):
        case_id = item["case_id"]
        print(f"[{index}/{len(cases)}] {case_id}")
        raw = request_json(opener, spec["space_track_gp_history_query"], args.retries, args.backoff_seconds)
        try:
            records = normalize(raw, norad_identifier(item["object_id"]), item["start_date"], item["end_date"])
        except MaterializationError as error:
            raise MaterializationError(f"{case_id}: {error}") from error
        _, following = requested_window(item["start_date"], item["end_date"])
        boundary_count = sum(parse_utc(record_fields(record)["EPOCH"], "EPOCH") == following for record in raw)
        case = {
            "case_id": case_id,
            "object_id": norad_identifier(item["object_id"]),
            "object_name": item.get("object_name"),
            "description": item.get("description"),
            "orbit_profile": item["orbit_profile"],
            "orbit_regime": item.get("orbit_regime", item["orbit_profile"]),
            "split": item["split"],
            "label_status": item["label_status"],
            "label_confidence": item["label_confidence"],
            "evidence_kind": item.get("evidence_kind"),
            "source": item["source"],
            "source_family": item.get("source_family"),
            "source_licence_note": item.get("source_licence_note"),
            "source_provenance": item.get("source_provenance"),
            "records": records,
            "truth_events": item.get("truth_events", []),
            "source_window": {
                "start": item["start_date"],
                "end": item["end_date"],
                "record_count": len(records),
                "raw_record_count": len(raw),
                "excluded_end_boundary_records": boundary_count,
                "superseded_or_duplicate_records": len(raw) - boundary_count - len(records),
                "space_track_query": spec["space_track_gp_history_query"],
            },
        }
        built.append({key: value for key, value in case.items() if value is not None})
        if index < len(cases) and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

    output = {
        "schema": "smd-event-benchmark-v1",
        "name": manifest["name"],
        "benchmark_version": manifest["version"],
        "materializer_version": MATERIALIZER_VERSION,
        "record_selection_policy": RECORD_SELECTION_POLICY,
        "response_validation_policy": RESPONSE_VALIDATION_POLICY,
        "matching_tolerance_hours": manifest["matching_tolerance_hours"],
        "notes": manifest["qualification"],
        "data_attribution": manifest["data_attribution"],
        "split_policy": manifest["split_policy"],
        "label_policy": manifest["label_policy"],
        "external_label_provenance": manifest["external_label_provenance"],
        "frozen_counts": manifest["frozen_counts"],
        "source_manifest": args.manifest.name,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "materialization_recipe": args.recipe.name,
        "materialization_recipe_sha256": sha256_bytes(recipe_bytes),
        "history_source": "Space-Track Basic SSA GP_History OMM JSON",
        "cases": built,
    }
    encoded = (json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()
    digest = write_output(args.output, encoded)
    print(f"Wrote {len(built)} materialized cases. SHA-256 {digest}")


if __name__ == "__main__":
    try:
        main()
    except (MaterializationError, OSError) as error:
        raise SystemExit(str(error))
