#!/usr/bin/env python3
"""Build the complete, deterministic browser-distribution notice bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = "dependency-notices.txt"
FIXED_FILES = (
    "LICENSE", "NOTICE", "THIRD-PARTY-NOTICES.md",
    "licenses/plotly-LICENSE.txt", "licenses/satellite-LICENSE.txt",
    "licenses/PLOTLY-SOURCE-ATTRIBUTIONS.txt",
    "licenses/THIRD-PARTY-SOURCES.json", "licenses/PLOTLY-COMPONENTS.json",
)


def checked_file(repo: Path, relative: str, expected: str | None = None) -> bytes:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or not relative or "\\" in relative:
        raise ValueError("Unsafe notice source path")
    if relative not in FIXED_FILES and not re.fullmatch(
        r"licenses/(?:plotly-bundled|plotly-components)/[A-Za-z0-9._/-]+", relative
    ):
        raise ValueError("Notice source is outside the reviewed directories")
    source = repo / relative
    if source.is_symlink() or not source.is_file() or source.resolve() != repo.resolve() / relative:
        raise ValueError("Notice source is missing or traverses a symlink: " + relative)
    data = source.read_bytes()
    data.decode("utf-8")
    if expected is not None and hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Notice source digest mismatch: " + relative)
    return data


def source_files(repo: Path = ROOT) -> dict[str, bytes]:
    files = {name: checked_file(repo, name) for name in FIXED_FILES}
    inventory = json.loads(files["licenses/PLOTLY-COMPONENTS.json"])
    distribution = inventory["distribution"]
    if distribution["path"] != "plotly-3.3.1.min.js" or hashlib.sha256(
        (repo / distribution["path"]).read_bytes()
    ).hexdigest() != distribution["sha256"]:
        raise ValueError("Browser distribution does not match its notice inventory")
    for record in inventory["components"]:
        if not record.get("notices"):
            raise ValueError("Component has no retained notice: " + record["id"])
        for notice in record["notices"]:
            data = checked_file(repo, notice["path"], notice["sha256"])
            if len(data) != notice["bytes"]:
                raise ValueError("Notice byte count mismatch: " + notice["path"])
            files[notice["path"]] = data
    for notice in json.loads(files["licenses/THIRD-PARTY-SOURCES.json"])["notices"]:
        files[notice["notice_path"]] = checked_file(
            repo, notice["notice_path"], notice["notice_sha256"]
        )
    return files


def bundle_bytes(repo: Path = ROOT) -> bytes:
    files = source_files(repo)
    heading = (
        "SatSift browser software notices\n"
        "================================\n\n"
        "Complete retained project and third-party notices for the distributed browser software.\n"
        "Each section identifies its repository source and the SHA-256 of the unchanged source bytes.\n"
        "Relative links in copied documents refer to the public source repository:\n"
        "https://github.com/sylvesterkaczmarek/satsift\n\n"
    ).encode()
    parts = [heading]
    for name in (*FIXED_FILES, *sorted(set(files) - set(FIXED_FILES))):
        data = files[name]
        parts.extend([
            ("\n" + "=" * 80 + "\nSource: " + name + "\nSHA-256: " +
             hashlib.sha256(data).hexdigest() + "\n" + "=" * 80 + "\n\n").encode(),
            data, b"\n",
        ])
    return b"".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = bundle_bytes()
    output = ROOT / OUTPUT
    if args.check:
        if not output.is_file() or output.is_symlink() or output.read_bytes() != expected:
            parser.error("Notice bundle is stale; run python3 tools/build_browser_notices.py")
    else:
        output.write_bytes(expected)
    print("Browser notice bundle verified: " + str(len(source_files())) + " source files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
