#!/usr/bin/env python3
"""Create and verify a source-only release candidate from a clean Git commit."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "SOURCE-RELEASE.json"
SCHEMA = "smd-source-release-v1"
CANDIDATE_STATUS = "candidate; publication requires the release decisions in RELEASE.md"
FORBIDDEN_PARTS = {
    ".git", ".hg", ".svn", ".venv", ".venvs", "node_modules", "__pycache__",
    ".satellite-maneuver-cache", "test-results", "playwright-report",
}
SECRET_PATTERNS = {
    "private-key": rb"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----",
    "provider-token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16})\b",
    "service-token": rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b",
    "personal-path": rb"/(?:Users|home|Volumes)/[A-Za-z0-9][^\s'\"<>]*",
    "numbered-authoring-label": rb"\bprompt[\s_-]*#?[\s_-]*[0-9]+\b",
    "generator-credit": rb"\b(?:generated|written|created)\s+by\s+(?:an?\s+)?(?:AI|ChatGPT|Codex|LLM)\b",
}


class ReleaseError(ValueError):
    """A candidate does not meet the source release contract."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_hash(kind: str, data: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, kind.encode() + b" " + str(len(data)).encode() + b"\0" + data).hexdigest()


def validate_path(path: str) -> None:
    if not isinstance(path, str) or not path or "\\" in path or any(ord(c) < 32 for c in path):
        raise ReleaseError("invalid source path")
    pure = PurePosixPath(path)
    if pure.is_absolute() or str(pure) != path or any(part in (".", "..", "") for part in path.split("/")):
        raise ReleaseError("noncanonical source path")
    lower = tuple(part.lower() for part in pure.parts)
    if any(part in FORBIDDEN_PARTS or part.startswith("._") for part in lower):
        raise ReleaseError("private or generated path in source inventory")
    name = lower[-1]
    if (
        (name.startswith(".env") and name != ".env.example")
        or name in (".space-track-config.php", ".ds_store")
        or name.endswith((".log", ".cache", ".tmp", ".bak", ".pyc", ".pyo", ".pem", ".key"))
        or path == "benchmark-data/public-evidence-benchmark-v1.0.json"
    ):
        raise ReleaseError("private or generated file in source inventory")


def scan_content(path: str, data: bytes, deny_literals: tuple[bytes, ...] = ()) -> None:
    combined = path.encode() + b"\0" + data
    identifier = sha256(path.encode())[:12]
    for label, pattern in SECRET_PATTERNS.items():
        if re.search(pattern, combined, flags=re.IGNORECASE if label in ("numbered-authoring-label", "generator-credit") else 0):
            raise ReleaseError(f"{label} match in source item {identifier}; path and content withheld")
    for literal in deny_literals:
        if literal.lower() in data.lower() or literal.lower() in path.encode().lower():
            raise ReleaseError(f"private deny-list match in source item {identifier}; path and content withheld")


def git(root: Path, *args: str, input_data: bytes | None = None) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], input=input_data, capture_output=True, check=False)
    if result.returncode:
        raise ReleaseError("Git source inspection failed; use a complete local checkout")
    return result.stdout


def tree_hash(entries: list[dict], algorithm: str) -> str:
    tree: dict = {}
    for item in entries:
        parts = item["path"].split("/")
        node = tree
        for part in parts[:-1]:
            existing = node.setdefault(part, {})
            if not isinstance(existing, dict):
                raise ReleaseError("file and directory inventory collision")
            node = existing
        if parts[-1] in node:
            raise ReleaseError("duplicate source path")
        node[parts[-1]] = (item["mode"], item["git_blob"])

    def encode(node: dict) -> str:
        payload = bytearray()
        for name, value in sorted(node.items(), key=lambda pair: (pair[0] + ("/" if isinstance(pair[1], dict) else "")).encode()):
            if isinstance(value, dict):
                mode, digest = "40000", encode(value)
            else:
                mode, digest = value
            payload.extend(mode.encode() + b" " + name.encode() + b"\0" + bytes.fromhex(digest))
        return object_hash("tree", bytes(payload), algorithm)

    return encode(tree)


def read_commit(root: Path, deny_literals: tuple[bytes, ...]) -> tuple[dict, dict[str, bytes]]:
    if Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() != root.resolve():
        raise ReleaseError("source must be the checkout root")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"):
        raise ReleaseError("source checkout must be clean, including untracked files")
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    source_tree = git(root, "rev-parse", "HEAD^{tree}").decode().strip()
    algorithm = git(root, "rev-parse", "--show-object-format").decode().strip()
    if algorithm not in ("sha1", "sha256"):
        raise ReleaseError("unsupported Git object format")
    entries = []
    seen = set()
    for row in git(root, "ls-tree", "-rz", "--full-tree", commit).split(b"\0"):
        if not row:
            continue
        descriptor, name = row.split(b"\t", 1)
        mode, kind, oid = descriptor.decode().split()
        path = name.decode("utf-8")
        validate_path(path)
        if path == MANIFEST or mode not in ("100644", "100755") or kind != "blob":
            raise ReleaseError("only regular source files may be exported; manifest name is reserved")
        if path.casefold() in seen:
            raise ReleaseError("case-insensitive source path collision")
        seen.add(path.casefold())
        entries.append({"path": path, "mode": mode, "git_blob": oid})
    if not entries:
        raise ReleaseError("source inventory is empty")
    raw = git(root, "cat-file", "--batch", input_data=b"".join((item["git_blob"] + "\n").encode() for item in entries))
    stream = io.BytesIO(raw)
    files = {}
    for item in entries:
        header = stream.readline().decode().strip().split()
        if len(header) != 3 or header[:2] != [item["git_blob"], "blob"]:
            raise ReleaseError("source object response mismatch")
        data = stream.read(int(header[2]))
        if len(data) != int(header[2]) or stream.read(1) != b"\n":
            raise ReleaseError("truncated source object")
        if object_hash("blob", data, algorithm) != item["git_blob"]:
            raise ReleaseError("source object hash mismatch")
        scan_content(item["path"], data, deny_literals)
        item.update(size=len(data), sha256=sha256(data))
        files[item["path"]] = data
    if stream.read():
        raise ReleaseError("unexpected source object response")
    if tree_hash(entries, algorithm) != source_tree:
        raise ReleaseError("exported inventory differs from the selected Git tree")
    if git(root, "rev-parse", "HEAD").decode().strip() != commit or git(root, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"):
        raise ReleaseError("source changed during export")
    manifest = {
        "schema": SCHEMA,
        "status": CANDIDATE_STATUS,
        "source_commit": commit,
        "source_tree": source_tree,
        "git_object_format": algorithm,
        "files": entries,
    }
    return manifest, files


def read_manifest(root: Path, deny_literals: tuple[bytes, ...] = ()) -> dict:
    manifest_path = root / MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ReleaseError("regular source release manifest is required")
    info = manifest_path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o644:
        raise ReleaseError("release manifest must be an unlinked regular file with mode 0644")
    data = manifest_path.read_bytes()
    scan_content(MANIFEST, data, deny_literals)
    try:
        manifest = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise ReleaseError("invalid source release manifest") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ReleaseError("unsupported source release manifest")
    if set(manifest) != {"schema", "status", "source_commit", "source_tree", "git_object_format", "files"} or manifest.get("status") != CANDIDATE_STATUS:
        raise ReleaseError("unexpected release metadata")
    algorithm = manifest.get("git_object_format")
    if algorithm not in ("sha1", "sha256"):
        raise ReleaseError("invalid Git object format")
    width = 40 if algorithm == "sha1" else 64
    for key in ("source_commit", "source_tree"):
        if not isinstance(manifest.get(key), str) or not re.fullmatch("[0-9a-f]{" + str(width) + "}", manifest[key]):
            raise ReleaseError("invalid source provenance hash")
    if not isinstance(manifest.get("files"), list) or not manifest["files"]:
        raise ReleaseError("missing source inventory")
    return manifest


def verify_directory(root: Path, expected_tree: str | None = None, *, expected_commit: str | None = None, exact: bool = True, deny_literals: tuple[bytes, ...] = ()) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise ReleaseError("candidate must be a regular directory")
    manifest = read_manifest(root, deny_literals)
    algorithm = manifest["git_object_format"]
    width = 40 if algorithm == "sha1" else 64
    paths = set()
    folded = set()
    for item in manifest["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "mode", "git_blob", "size", "sha256"}:
            raise ReleaseError("invalid source inventory entry")
        path = item["path"]
        validate_path(path)
        scan_content(path, b"", deny_literals)
        if path == MANIFEST or path in paths or path.casefold() in folded:
            raise ReleaseError("duplicate or reserved inventory path")
        if item["mode"] not in ("100644", "100755") or type(item["size"]) is not int or item["size"] < 0:
            raise ReleaseError("invalid inventory file metadata")
        if not isinstance(item["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", item["sha256"]):
            raise ReleaseError("invalid source SHA-256")
        if not isinstance(item["git_blob"], str) or not re.fullmatch("[0-9a-f]{" + str(width) + "}", item["git_blob"]):
            raise ReleaseError("invalid source blob hash")
        current = root
        for component in path.split("/"):
            current = current / component
            if current.is_symlink():
                raise ReleaseError("symbolic links are forbidden in the candidate")
        info = current.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ReleaseError("candidate contains a nonregular or hard-linked file")
        data = current.read_bytes()
        if len(data) != item["size"] or sha256(data) != item["sha256"] or object_hash("blob", data, algorithm) != item["git_blob"]:
            raise ReleaseError(f"candidate content mismatch in {path}")
        expected_mode = 0o755 if item["mode"] == "100755" else 0o644
        if stat.S_IMODE(info.st_mode) != expected_mode:
            raise ReleaseError(f"candidate mode mismatch in {path}")
        scan_content(path, data, deny_literals)
        paths.add(path)
        folded.add(path.casefold())
    if tree_hash(manifest["files"], algorithm) != manifest["source_tree"]:
        raise ReleaseError("candidate does not reconstruct the recorded source tree")
    if expected_tree is not None and manifest["source_tree"] != expected_tree:
        raise ReleaseError("candidate differs from the independently supplied source tree")
    if expected_commit is not None and manifest["source_commit"] != expected_commit:
        raise ReleaseError("candidate differs from the independently supplied source commit")
    if exact:
        actual = set()
        for current, directories, filenames in os.walk(root, followlinks=False):
            for name in directories:
                directory = Path(current) / name
                rel = directory.relative_to(root).as_posix()
                if directory.is_symlink() or not any(path.startswith(rel + "/") for path in paths):
                    raise ReleaseError("unexpected directory in candidate")
            for name in filenames:
                candidate = Path(current) / name
                if candidate.is_symlink():
                    raise ReleaseError("symbolic links are forbidden in the candidate")
                actual.add(candidate.relative_to(root).as_posix())
        if actual != paths | {MANIFEST}:
            raise ReleaseError("candidate has missing or unexpected files")
    return manifest


def build(root: Path, output: Path, deny_literals: tuple[bytes, ...] = ()) -> dict:
    root = root.resolve()
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ReleaseError("output must be a new directory")
    if output.resolve().is_relative_to(root):
        raise ReleaseError("release output must be outside the source checkout")
    manifest, files = read_commit(root, deny_literals)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".source-release-", dir=output.parent) as temporary:
        stage = Path(temporary) / "candidate"
        stage.mkdir()
        source = stage / "source"
        source.mkdir()
        for item in manifest["files"]:
            target = source / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(files[item["path"]])
            target.chmod(0o755 if item["mode"] == "100755" else 0o644)
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        (source / MANIFEST).write_bytes(manifest_bytes)
        (source / MANIFEST).chmod(0o644)
        verify_directory(source, manifest["source_tree"], deny_literals=deny_literals)
        archive = stage / "satsift-source-candidate.tar.gz"
        with archive.open("xb") as raw:
            with gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as tar:
                    for path, data in sorted({**files, MANIFEST: manifest_bytes}.items()):
                        entry = tarfile.TarInfo("satsift/" + path)
                        entry.size = len(data)
                        entry.mode = 0o755 if path != MANIFEST and next(item for item in manifest["files"] if item["path"] == path)["mode"] == "100755" else 0o644
                        entry.uid = entry.gid = entry.mtime = 0
                        entry.uname = entry.gname = ""
                        tar.addfile(entry, io.BytesIO(data))
        digest = sha256(archive.read_bytes())
        (stage / (archive.name + ".sha256")).write_text(digest + "  " + archive.name + "\n")
        if output.exists() or output.is_symlink():
            raise ReleaseError("output appeared during export")
        stage.rename(output)
    return {"source_tree": manifest["source_tree"], "source_commit": manifest["source_commit"], "files": len(manifest["files"]), "archive_sha256": digest}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    create = subparsers.add_parser("build", help="export committed regular files without private Git history")
    create.add_argument("--source", type=Path, default=ROOT)
    create.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify", help="verify a clean extracted candidate without Git")
    verify.add_argument("directory", type=Path)
    verify.add_argument("--expected-tree")
    verify.add_argument("--expected-commit")
    for sub in (create, verify):
        sub.add_argument("--deny-file", type=Path, help="private newline-delimited literals to reject; contents are never printed")
    args = parser.parse_args()
    try:
        literals = tuple(line.strip() for line in args.deny_file.read_bytes().splitlines() if line.strip()) if args.deny_file else ()
        if args.operation == "build":
            result = build(args.source, args.output, literals)
        else:
            manifest = verify_directory(args.directory, args.expected_tree, expected_commit=args.expected_commit, deny_literals=literals)
            result = {"source_tree": manifest["source_tree"], "source_commit": manifest["source_commit"], "source_commit_checked": args.expected_commit is not None, "files": len(manifest["files"])}
        print(json.dumps({"verified": True, **result}, indent=2))
    except (ReleaseError, OSError, UnicodeError, KeyError, TypeError) as exc:
        parser.exit(1, "ERROR: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
