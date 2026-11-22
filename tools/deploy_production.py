#!/usr/bin/env python3
"""Deploy allowlisted public files using a privately configured SSH target."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_assets import MODULE_SOURCES, ENTRY_SOURCE, browser_assets, validate_manifest
from update_browser_assets import expected_files as expected_browser_files

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ORIGIN_URLS = {
    "https://github.com/sylvesterkaczmarek/satsift.git",
    "git@github.com:sylvesterkaczmarek/satsift.git",
}
# Host identity and deployment destinations belong to the operator's environment.
# These remain unset until configure_target validates the local configuration.
SSH_ALIAS: str | None = None
REMOTE_SHELL_COMMAND = "sh"
REMOTE_SITE_ROOT: PurePosixPath | None = None
REMOTE_APP_ROOT: PurePosixPath | None = None
REMOTE_SANITY_COMMAND: str | None = None
REMOTE_BACKUP_ROOT = PurePosixPath(".satellite-maneuver-deploy-backups")
REMOTE_LOCK_PATH = PurePosixPath(".satellite-maneuver-deploy.lock")
LEGACY_APP_FILES = (
    "index.html",
    "app-3.4.js",
    "history.php",
    "docs.html",
    "benchmark.html",
    "accessibility.html",
    "benchmark-template.json",
    "public-evidence-manifest-v0.1.json",
    "plotly-3.3.1.min.js",
    "satellite-6.0.2.min.js",
)
PUBLIC_APP_FILES = (*LEGACY_APP_FILES, *MODULE_SOURCES)
APP_UPLOAD_ORDER = (
    "plotly-3.3.1.min.js",
    "satellite-6.0.2.min.js",
    "benchmark-template.json",
    "public-evidence-manifest-v0.1.json",
    "history.php",
    "docs.html",
    "benchmark.html",
    "accessibility.html",
    *MODULE_SOURCES,
    "app-3.4.js",
    "index.html",
)
SITE_FILES = {
    ".htaccess": "deployment/site-root.htaccess",
    "robots.txt": "deployment/robots-detector-snippet.txt",
    "sitemap.xml": "deployment/sitemap-detector-fragment.xml",
}
SITE_UPLOAD_ORDER = ("robots.txt", "sitemap.xml", ".htaccess")
IMMUTABLE_BEGIN = "# BEGIN satellite-maneuver-detector immutable browser assets"
IMMUTABLE_END = "# END satellite-maneuver-detector immutable browser assets"
MANAGED_BEGIN = "# BEGIN satellite-maneuver-detector managed configuration"
MANAGED_END = "# END satellite-maneuver-detector managed configuration"
ROBOTS_BEGIN = "# BEGIN satellite-maneuver-detector managed policy"
ROBOTS_END = "# END satellite-maneuver-detector managed policy"
SITEMAP_URL = "https://www.sylvesterkaczmarek.com/sitemap.xml"
PUBLIC_URLS = (
    "https://www.sylvesterkaczmarek.com/satellite-maneuver-detector",
    "https://www.sylvesterkaczmarek.com/satellite-maneuver-detector/docs",
    "https://www.sylvesterkaczmarek.com/satellite-maneuver-detector/benchmark",
    "https://www.sylvesterkaczmarek.com/satellite-maneuver-detector/accessibility",
)
DETECTOR_ROBOTS_LINES = (
    "Allow: /satellite-maneuver-detector",
    "Disallow: /satellite-maneuver-detector/history",
    "Disallow: /satellite-maneuver-detector/benchmark/manifest",
    "Disallow: /satellite-maneuver-detector/benchmark/template",
    "Disallow: /tools/satellite-maneuver-detector/",
)


def public_asset_files(repo: Path = ROOT) -> list[tuple[str, str]]:
    """Return fixed source names and exact public targets, including the legacy alias."""
    identities = {asset['source']: asset for asset in browser_assets(repo)}
    output = []
    for source in APP_UPLOAD_ORDER:
        if source in identities:
            output.append((source, identities[source]['target']))
            if source == ENTRY_SOURCE:
                output.append((source, ENTRY_SOURCE))
        else:
            output.append((source, source))
    return output


def stage_public_assets(repo: Path, directory: Path) -> Path:
    """Make private deployment copies with their immutable destination filenames."""
    directory.mkdir(mode=0o700)
    for source, target in public_asset_files(repo):
        destination = directory / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / source, destination)
    return directory


class DeploymentError(RuntimeError):
    """A preflight or deployment safety condition failed."""



def remote_directory_guards(site: PurePosixPath, app: PurePosixPath) -> list[str]:
    """Validate every writable parent before uploads or rollback file operations."""
    return [
        'set -eu', f'site={shlex.quote(str(site))}', f'app={shlex.quote(str(app))}',
        'test -d "$site"', 'test -d "$app"', 'test ! -L "$site"', 'test ! -L "$app"',
        'smd_home_real=$(pwd -P)', 'smd_site_real=$(cd "$site" && pwd -P)',
        'smd_app_real=$(cd "$app" && pwd -P)',
        'test "$smd_site_real" = "$smd_home_real/$site"',
        'test "$smd_app_real" = "$smd_site_real/tools/satellite-maneuver-detector"',
        f'test ! -L {shlex.quote(str(app / "app"))}',
        f'if test -e {shlex.quote(str(app / "app"))}; then test -d {shlex.quote(str(app / "app"))}; fi',
    ]


def configure_target(site_root: str | None = None, ssh_alias: str | None = None) -> None:
    """Validate private operator settings before any deployment connection is made."""
    global SSH_ALIAS, REMOTE_SITE_ROOT, REMOTE_APP_ROOT, REMOTE_SANITY_COMMAND
    # A rejected reconfiguration must not leave a previously accepted target active.
    SSH_ALIAS = REMOTE_SITE_ROOT = REMOTE_APP_ROOT = REMOTE_SANITY_COMMAND = None
    raw_root = site_root if site_root is not None else os.environ.get("SMD_REMOTE_SITE_ROOT", "")
    alias = ssh_alias if ssh_alias is not None else os.environ.get("SMD_SSH_ALIAS", "smd-production")
    if not raw_root:
        raise DeploymentError("set SMD_REMOTE_SITE_ROOT locally to the site directory relative to the SSH home")
    parts = raw_root.split("/")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", part) for part in parts):
        raise DeploymentError(
            "SMD_REMOTE_SITE_ROOT must be a normalised relative path with simple directory names; "
            "absolute paths, empty segments, dot segments, spaces and shell syntax are not allowed"
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", alias):
        raise DeploymentError("SMD_SSH_ALIAS must be a simple local OpenSSH profile name")
    site = PurePosixPath(raw_root)
    app = site / "tools/satellite-maneuver-detector"
    script = "\n".join([
        *remote_directory_guards(site, app),
        *[
            f"test -f {shlex.quote(str(site / name))}; test ! -L {shlex.quote(str(site / name))}"
            for name in SITE_FILES
        ],
        *[
            f"test -f {shlex.quote(str(app / name))}; test ! -L {shlex.quote(str(app / name))}"
            for name in LEGACY_APP_FILES
        ],
        f"test ! -L {shlex.quote(str(app / 'app'))}",
        f"if test -e {shlex.quote(str(app / 'app'))}; then test -d {shlex.quote(str(app / 'app'))}; fi",
        *[
            f"test ! -L {shlex.quote(str(app / asset['target']))}; "
            f"if test -e {shlex.quote(str(app / asset['target']))}; then "
            f"test -f {shlex.quote(str(app / asset['target']))}; "
            f"{remote_hash_assertion(app / asset['target'], asset['sha256'])}; fi"
            for asset in browser_assets(ROOT)
        ],
        "",
    ])
    SSH_ALIAS, REMOTE_SITE_ROOT, REMOTE_APP_ROOT, REMOTE_SANITY_COMMAND = alias, site, app, script


def require_target() -> None:
    if any(value is None for value in (SSH_ALIAS, REMOTE_SITE_ROOT, REMOTE_APP_ROOT, REMOTE_SANITY_COMMAND)):
        raise DeploymentError("deployment target is not configured; call configure_target before connecting")


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    input_bytes: bytes | None = None,
    capture: bool = True,
    safe_error: str | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            input=input_bytes,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            check=False,
        )
    except OSError as exc:
        raise DeploymentError(safe_error or f"could not execute required program {command[0]}") from exc
    if result.returncode:
        if safe_error is not None:
            raise DeploymentError(f"{safe_error} (exit status {result.returncode})")
        detail = result.stderr.decode("utf-8", "replace").strip() if result.stderr else ""
        raise DeploymentError(f"command failed ({command[0]}): {detail or 'no diagnostic output'}")
    return result


def git_text(repo: Path, *args: str) -> str:
    return run(["git", *args], cwd=repo).stdout.decode("utf-8", "replace").strip()


def validate_repository(repo: Path, *, execute: bool) -> tuple[str, str]:
    top = Path(git_text(repo, "rev-parse", "--show-toplevel")).resolve()
    if top != repo.resolve():
        raise DeploymentError(f"repository root mismatch: expected {repo}")
    dirty = git_text(repo, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise DeploymentError("working tree is dirty; commit or remove every change before deployment")
    branch = git_text(repo, "branch", "--show-current")
    commit = git_text(repo, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise DeploymentError("could not determine a full Git commit SHA")
    if execute and branch != "main":
        raise DeploymentError(f"production deployment requires branch main, not {branch or 'detached HEAD'}")
    if execute:
        origin_url = git_text(repo, "remote", "get-url", "origin")
        if origin_url not in EXPECTED_ORIGIN_URLS:
            raise DeploymentError("origin is not the canonical satellite-maneuver-detector repository")
        try:
            tracking_commit = git_text(repo, "rev-parse", "refs/remotes/origin/main")
        except DeploymentError as exc:
            raise DeploymentError("origin/main is unavailable; fetch the reviewed main branch before deployment") from exc
        if tracking_commit != commit:
            raise DeploymentError("local main does not match the local origin/main tracking ref")
        remote = run(
            ["git", "ls-remote", "--exit-code", "origin", "refs/heads/main"],
            cwd=repo,
            safe_error="could not verify the authoritative origin/main commit",
        ).stdout.decode("utf-8", "replace").strip().splitlines()
        if len(remote) != 1:
            raise DeploymentError("origin returned an ambiguous main branch reference")
        remote_fields = remote[0].split()
        if len(remote_fields) != 2 or remote_fields[1] != "refs/heads/main" or remote_fields[0] != commit:
            raise DeploymentError("local main is not the current authoritative origin/main commit")
    return branch, commit


def validate_allowlist(repo: Path) -> None:
    try:
        validate_manifest(repo)
        expected_browser = expected_browser_files(repo)
    except (ValueError, OSError) as exc:
        raise DeploymentError('browser asset manifest or source validation failed') from exc
    if any((repo / name).read_text() != content for name, content in expected_browser.items()):
        raise DeploymentError('browser asset identities are stale; run tools/update_browser_assets.py')
    expected = set(PUBLIC_APP_FILES)
    if len(expected) != len(PUBLIC_APP_FILES):
        raise DeploymentError("public application allowlist contains a duplicate")
    if set(APP_UPLOAD_ORDER) != expected or len(APP_UPLOAD_ORDER) != len(PUBLIC_APP_FILES):
        raise DeploymentError("application upload order has drifted from the public allowlist")
    forbidden_parts = {
        "research",
        "review",
        "tests",
        "benchmark-results",
        "config",
        ".satellite-maneuver-cache",
    }
    for relative in PUBLIC_APP_FILES:
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or forbidden_parts.intersection(path.parts):
            raise DeploymentError(f"unsafe public allowlist entry: {relative}")
        if path.name == ".space-track-config.php" or not (repo / relative).is_file() or (repo / relative).is_symlink() or (repo / relative).resolve() != repo.resolve() / relative:
            raise DeploymentError(f"missing or forbidden public allowlist entry: {relative}")
    for remote_name, relative in SITE_FILES.items():
        if PurePosixPath(remote_name).name != remote_name or not (repo / relative).is_file():
            raise DeploymentError(f"invalid site-root deployment source: {relative}")
    robots_source = (repo / SITE_FILES["robots.txt"]).read_text(encoding="utf-8")
    if not all(line in robots_source for line in (*DETECTOR_ROBOTS_LINES, f"Sitemap: {SITEMAP_URL}")):
        raise DeploymentError("robots merge policy has drifted from its repository source artifact")
    sitemap_source = (repo / SITE_FILES["sitemap.xml"]).read_text(encoding="utf-8")
    sitemap_urls = tuple(re.findall(r"<loc>([^<]+)</loc>", sitemap_source))
    if sitemap_urls != PUBLIC_URLS:
        raise DeploymentError("sitemap merge policy has drifted from its repository source artifact")


def ssh_base(ssh_config: Path | None = None) -> list[str]:
    command = ["ssh"]
    if ssh_config is not None:
        command.extend(["-F", str(ssh_config)])
    return command


def validate_ssh_alias(ssh_config: Path | None = None) -> None:
    require_target()
    command = [*ssh_base(ssh_config), "-G", SSH_ALIAS]
    result = run(command, safe_error=f"could not resolve required SSH alias {SSH_ALIAS!r}")
    values: dict[str, str] = {}
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        key, _, value = line.partition(" ")
        if key and value and key not in values:
            values[key.lower()] = value.strip()
    hostname = values.get("hostname", "")
    user = values.get("user", "")
    if (
        not hostname
        or hostname.lower() == SSH_ALIAS
        or hostname.startswith("-")
        or any(character.isspace() for character in hostname)
        or not user
    ):
        raise DeploymentError(
            f"SSH alias {SSH_ALIAS!r} is unavailable; configure it in local SSH configuration"
        )
    forbidden_resolution = {
        "proxycommand": "none",
        "proxyjump": "none",
        "localcommand": "none",
        "remotecommand": "none",
    }
    for key, expected in forbidden_resolution.items():
        if values.get(key, expected).lower() != expected:
            raise DeploymentError(f"SSH alias {SSH_ALIAS!r} contains unsupported {key} behavior")
    if values.get("permitlocalcommand", "no").lower() != "no":
        raise DeploymentError(f"SSH alias {SSH_ALIAS!r} must disable PermitLocalCommand")
    if values.get("stdinnull", "no").lower() != "no":
        raise DeploymentError(f"SSH alias {SSH_ALIAS!r} must permit stdin for remote safety scripts")



def ssh_command(ssh_config: Path | None) -> list[str]:
    require_target()
    return [
        *ssh_base(ssh_config),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "PermitLocalCommand=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "RequestTTY=no",
        "-T",
        SSH_ALIAS,
        REMOTE_SHELL_COMMAND,
    ]


def run_remote_script(
    ssh_config: Path | None,
    script: str,
    *,
    safe_error: str,
) -> subprocess.CompletedProcess[bytes]:
    """Run a script over stdin so untrusted transport layers cannot rewrite its structure."""
    if not script or "\x00" in script:
        raise DeploymentError("remote script must be non-empty text without NUL bytes")
    return run(
        ssh_command(ssh_config),
        input_bytes=script.encode("utf-8"),
        safe_error=safe_error,
    )


def check_remote_paths(ssh_config: Path | None) -> None:
    require_target()
    run_remote_script(
        ssh_config,
        REMOTE_SANITY_COMMAND,
        safe_error="remote path safety checks failed",
    )



def remote_module_directory_exists(ssh_config: Path | None) -> bool:
    script = '; '.join(remote_directory_guards(REMOTE_SITE_ROOT, REMOTE_APP_ROOT))
    script += f'; if test -d {shlex.quote(str(REMOTE_APP_ROOT / "app"))}; then printf present; else printf absent; fi'
    state = run_remote_script(ssh_config, script, safe_error='could not inspect the immutable asset directory').stdout
    if state not in (b'present', b'absent'):
        raise DeploymentError('unexpected immutable asset directory status')
    return state == b'present'


def ensure_module_directory(ssh_config: Path | None) -> None:
    script = '; '.join(remote_directory_guards(REMOTE_SITE_ROOT, REMOTE_APP_ROOT))
    directory = shlex.quote(str(REMOTE_APP_ROOT / 'app'))
    script += f'; umask 022; if test ! -d {directory}; then mkdir -- {directory}; fi'
    run_remote_script(ssh_config, script, safe_error='could not prepare the immutable asset directory')


def fetch_remote_file(ssh_config: Path | None, relative: PurePosixPath) -> bytes:
    if relative.is_absolute() or ".." in relative.parts:
        raise DeploymentError(f"unsafe remote read path: {relative}")
    script = f"set -eu\ncat -- {shlex.quote(str(relative))}\n"
    return run_remote_script(
        ssh_config,
        script,
        safe_error=f"could not read required remote site file {relative.name}",
    ).stdout


def _extract_managed_block(source: str) -> str:
    if source.count(MANAGED_BEGIN) != 1 or source.count(MANAGED_END) != 1:
        raise DeploymentError("repository .htaccess must contain one complete managed block")
    start = source.find(MANAGED_BEGIN)
    end = source.find(MANAGED_END)
    if end < start:
        raise DeploymentError("repository .htaccess managed block markers are reversed")
    end += len(MANAGED_END)
    return source[start:end].strip()


def _merge_main_htaccess(remote: str, source: str) -> str:
    block = _extract_managed_block(source)
    begin_count = remote.count(MANAGED_BEGIN)
    end_count = remote.count(MANAGED_END)
    start = remote.find(MANAGED_BEGIN)
    end = remote.find(MANAGED_END)
    if begin_count or end_count:
        if begin_count != 1 or end_count != 1 or end < start:
            raise DeploymentError("remote .htaccess has malformed or duplicate detector managed markers")
        end += len(MANAGED_END)
        outside = remote[:start] + remote[end:]
        if "satellite-maneuver-detector" in outside.lower():
            raise DeploymentError("remote .htaccess contains detector rules outside the managed block")
        return (remote[:start].rstrip() + "\n\n" + block + "\n" + remote[end:].lstrip()).rstrip() + "\n"
    if "satellite-maneuver-detector" in remote.lower():
        unmarked = block.replace(MANAGED_BEGIN, "", 1).replace(MANAGED_END, "", 1).strip()
        if remote.strip() == unmarked:
            return block + "\n"
        raise DeploymentError(
            "remote .htaccess contains unmarked detector rules; refusing an ambiguous automatic merge"
        )
    suffix = remote.lstrip()
    return block + (("\n\n" + suffix) if suffix else "\n")



def _separate_immutable_routes(text: str, *, required: bool = False) -> tuple[str, str | None]:
    first, last = text.find(IMMUTABLE_BEGIN), text.find(IMMUTABLE_END)
    counts = (text.count(IMMUTABLE_BEGIN), text.count(IMMUTABLE_END))
    if counts == (0, 0) and not required:
        return text, None
    if counts != (1, 1) or first >= last:
        raise DeploymentError('malformed immutable browser route markers')
    last += len(IMMUTABLE_END)
    return text[:first] + text[last:], text[first:last]


def merge_htaccess(remote: str, source: str) -> str:
    cleaned, _previous = _separate_immutable_routes(remote)
    _source_main, block = _separate_immutable_routes(source, required=True)
    return block + '\n\n' + _merge_main_htaccess(cleaned, source).lstrip()


def retain_immutable_routes(remote: str, source: str) -> str:
    """Keep cached module graphs reachable while restoring the previous mutable release."""
    cleaned, _previous = _separate_immutable_routes(remote)
    _source_main, block = _separate_immutable_routes(source, required=True)
    _merge_main_htaccess(cleaned, source)  # Validate ownership/markers without replacing the old main block.
    return block + '\n\n' + cleaned


def merge_robots(remote: str) -> str:
    lines = remote.splitlines()
    output: list[str] = []
    in_managed = False
    found_managed = False
    for line in lines:
        stripped = line.strip()
        if stripped == ROBOTS_BEGIN:
            if in_managed or found_managed:
                raise DeploymentError("remote robots.txt has duplicate managed policy markers")
            in_managed = True
            found_managed = True
            continue
        if stripped == ROBOTS_END:
            if not in_managed:
                raise DeploymentError("remote robots.txt has an unmatched managed policy marker")
            in_managed = False
            continue
        if in_managed:
            continue
        lower = stripped.lower()
        if lower == f"sitemap: {SITEMAP_URL}".lower():
            continue
        if lower.startswith(("allow:", "disallow:")):
            _, _, value = stripped.partition(":")
            path = value.strip()
            if path.startswith("/satellite-maneuver-detector") or path.startswith(
                "/tools/satellite-maneuver-detector"
            ):
                continue
        output.append(line)
    if in_managed:
        raise DeploymentError("remote robots.txt has an unterminated managed policy block")

    star_groups = [
        index for index, line in enumerate(output)
        if line.strip().lower() == "user-agent: *"
    ]
    if len(star_groups) != 1:
        raise DeploymentError("remote robots.txt must contain exactly one User-agent: * group")
    group_start = star_groups[0]
    group_end = len(output)
    for later in range(group_start + 1, len(output)):
        if output[later].strip().lower().startswith("user-agent:"):
            group_end = later
            break
    block = [ROBOTS_BEGIN, *DETECTOR_ROBOTS_LINES, ROBOTS_END]
    output[group_end:group_end] = ([""] if group_end and output[group_end - 1].strip() else []) + block
    while output and not output[-1].strip():
        output.pop()
    output.extend(["", f"Sitemap: {SITEMAP_URL}"])
    return "\n".join(output) + "\n"


def merge_sitemap(remote: bytes) -> bytes:
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        root = ET.fromstring(remote, parser=parser)
    except ET.ParseError as exc:
        raise DeploymentError(f"remote sitemap.xml is not valid XML: {exc}") from exc
    if root.tag.rsplit("}", 1)[-1] != "urlset":
        raise DeploymentError("remote sitemap.xml root is not <urlset>")
    namespace = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""
    url_tag = f"{{{namespace}}}url" if namespace else "url"
    loc_tag = f"{{{namespace}}}loc" if namespace else "loc"
    for url in list(root.findall(url_tag)):
        loc = url.find(loc_tag)
        value = (loc.text or "").strip() if loc is not None else ""
        clean_prefix = "https://www.sylvesterkaczmarek.com/satellite-maneuver-detector"
        physical_prefix = "https://www.sylvesterkaczmarek.com/tools/satellite-maneuver-detector"
        owned_clean = value == clean_prefix or value.startswith(clean_prefix + "/") or value.startswith(clean_prefix + ".")
        owned_physical = value == physical_prefix or value.startswith(physical_prefix + "/")
        if owned_clean or owned_physical:
            root.remove(url)
    for value in PUBLIC_URLS:
        url = ET.SubElement(root, url_tag)
        ET.SubElement(url, loc_tag).text = value
    if namespace:
        ET.register_namespace("", namespace)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def prepare_site_files(
    repo: Path,
    ssh_config: Path | None,
    destination: Path,
) -> tuple[dict[str, Path], dict[str, str]]:
    remote_bytes = {
        name: fetch_remote_file(ssh_config, REMOTE_SITE_ROOT / name)
        for name in SITE_FILES
    }
    remote_htaccess = remote_bytes[".htaccess"].decode("utf-8")
    remote_robots = remote_bytes["robots.txt"].decode("utf-8")
    remote_sitemap = remote_bytes["sitemap.xml"]
    generated = {
        ".htaccess": merge_htaccess(
            remote_htaccess,
            (repo / SITE_FILES[".htaccess"]).read_text(encoding="utf-8"),
        ).encode(),
        "robots.txt": merge_robots(remote_robots).encode(),
        "sitemap.xml": merge_sitemap(remote_sitemap),
    }
    paths: dict[str, Path] = {}
    for name, content in generated.items():
        path = destination / name
        path.write_bytes(content)
        paths[name] = path
    rollback_path = destination / 'rollback.htaccess'
    rollback_path.write_text(retain_immutable_routes(
        remote_htaccess, (repo / SITE_FILES['.htaccess']).read_text(encoding='utf-8')
    ))
    paths['_rollback_htaccess'] = rollback_path
    snapshot_hashes = {name: hashlib.sha256(content).hexdigest() for name, content in remote_bytes.items()}
    return paths, snapshot_hashes


def rsync_transport(ssh_config: Path | None) -> str:
    command = ssh_base(ssh_config)
    command.extend(
        [
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "PermitLocalCommand=no",
            "-o",
            "ClearAllForwardings=yes",
            "-o",
            "RequestTTY=no",
        ]
    )
    return shlex.join(command)


def rsync_commands(
    repo: Path,
    site_files: dict[str, Path],
    ssh_config: Path | None,
    *,
    dry_run: bool,
    app_staging: Path,
    module_directory_exists: bool = True,
) -> list[list[str]]:
    require_target()
    common = ["rsync", "-az", "--checksum", "--itemize-changes", "-e", rsync_transport(ssh_config)]
    if dry_run:
        common.append("--dry-run")
    commands: list[list[str]] = []
    activation: list[list[str]] = []
    for _source, target in public_asset_files(repo):
        if dry_run and not module_directory_exists and target.startswith('app/'):
            continue
        local_path = str(app_staging / target)
        command = [*common, '--', local_path, f"{SSH_ALIAS}:{REMOTE_APP_ROOT}/{target}"]
        # Routes and all immutable dependencies must exist before either entry document changes.
        (activation if target in (ENTRY_SOURCE, 'index.html') else commands).append(command)
    for name in SITE_UPLOAD_ORDER:
        commands.append([*common, "--", str(site_files[name]), f"{SSH_ALIAS}:{REMOTE_SITE_ROOT}/{name}"])
    return commands + activation


def remote_targets(repo: Path = ROOT) -> list[tuple[PurePosixPath, PurePosixPath]]:
    # Immutable targets are never overwritten or pruned, including on rollback.
    targets = [(REMOTE_APP_ROOT / name, PurePosixPath('app') / name) for name in LEGACY_APP_FILES]
    targets.extend((REMOTE_SITE_ROOT / name, PurePosixPath('site') / name) for name in SITE_FILES)
    return targets


def remote_hash_assertion(path: PurePosixPath, expected: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise DeploymentError("invalid expected SHA-256 in deployment transaction")
    quoted = shlex.quote(str(path))
    return f"actual=$(sha256sum -- {quoted}); test \"${{actual%% *}}\" = {expected}"


def backup_release(
    ssh_config: Path | None,
    commit: str,
    site_snapshot_hashes: dict[str, str],
    repo: Path = ROOT,
    rollback_htaccess: bytes | None = None,
) -> PurePosixPath:
    if rollback_htaccess is None:
        raise DeploymentError('prepared rollback routing is required before deployment')
    retained = rollback_htaccess.decode('utf-8')
    _unused, retained_block = _separate_immutable_routes(retained, required=True)
    _unused, expected_block = _separate_immutable_routes((repo / SITE_FILES['.htaccess']).read_text(), required=True)
    if retained_block != expected_block:
        raise DeploymentError('rollback routing does not match the reviewed immutable route block')
    backup_dir = REMOTE_BACKUP_ROOT / f"{commit[:12]}-{secrets.token_hex(4)}"
    checks = [REMOTE_SANITY_COMMAND.strip()]
    checks.extend(remote_hash_assertion(REMOTE_SITE_ROOT / name, site_snapshot_hashes[name]) for name in SITE_FILES)
    setup = (
        f"if test -e {shlex.quote(str(REMOTE_BACKUP_ROOT))}; then "
        f"test -d {shlex.quote(str(REMOTE_BACKUP_ROOT))}; test ! -L {shlex.quote(str(REMOTE_BACKUP_ROOT))}; fi; "
        f"mkdir -p -- {shlex.quote(str(REMOTE_BACKUP_ROOT))}; "
        f"test ! -e {shlex.quote(str(backup_dir))}; mkdir -- {shlex.quote(str(backup_dir))}; "
        f"test ! -L {shlex.quote(str(backup_dir))}; "
        f"mkdir -- {shlex.quote(str(backup_dir / 'app'))} {shlex.quote(str(backup_dir / 'site'))}"
    )
    copies = [f"cp -p -- {shlex.quote(str(destination))} {shlex.quote(str(backup_dir / relative))}"
              for destination, relative in remote_targets(repo)]
    copies.append(f"printf '%s' {shlex.quote(retained)} > {shlex.quote(str(backup_dir / 'retained-routes.htaccess'))}")
    protected_work = 'set -eu; ' + '; '.join(checks) + '; ' + setup + '; ' + '; '.join(copies)
    command = (
        f"set -u; umask 077; mkdir -- {shlex.quote(str(REMOTE_LOCK_PATH))} || exit 42; "
        f"if ( {protected_work} ); then exit 0; "
        f"else status=$?; rmdir -- {shlex.quote(str(REMOTE_LOCK_PATH))}; exit $status; fi"
    )
    run_remote_script(ssh_config, command,
                      safe_error='remote release backup or optimistic-concurrency check failed before any upload')
    return backup_dir


def release_deployment_lock(ssh_config: Path | None) -> None:
    run_remote_script(
        ssh_config,
        f"set -eu\nrmdir -- {shlex.quote(str(REMOTE_LOCK_PATH))}\n",
        safe_error="release files are consistent but the remote deployment lock could not be removed",
    )


def restore_release(ssh_config: Path | None, backup_dir: PurePosixPath, commit: str,
                    repo: Path = ROOT) -> None:
    commands = remote_directory_guards(REMOTE_SITE_ROOT, REMOTE_APP_ROOT)
    for destination, backup_relative in remote_targets(repo):
        temporary = destination.parent / f'.{destination.name}.smd-restore-{commit[:12]}'
        saved = backup_dir / ('retained-routes.htaccess' if backup_relative == PurePosixPath('site/.htaccess') else backup_relative)
        commands.append(f'test ! -L {shlex.quote(str(destination))}; test -f {shlex.quote(str(saved))}; test ! -L {shlex.quote(str(saved))}')
        commands.append(f'cp -p -- {shlex.quote(str(saved))} {shlex.quote(str(temporary))}')
        commands.append(f'mv -f -- {shlex.quote(str(temporary))} {shlex.quote(str(destination))}')
    run_remote_script(ssh_config, '; '.join(commands),
                      safe_error='automatic restoration from the private release backup failed')


def expected_release_hashes(repo: Path, site_files: dict[str, Path]) -> dict[PurePosixPath, str]:
    expected = {
        REMOTE_APP_ROOT / target: file_hash(repo / source)
        for source, target in public_asset_files(repo)
    }
    expected.update(
        {REMOTE_SITE_ROOT / name: file_hash(site_files[name]) for name in SITE_FILES}
    )
    return expected


def verify_remote_hashes(
    ssh_config: Path | None,
    expected: dict[PurePosixPath, str],
) -> None:
    command = "set -eu; " + "; ".join(
        remote_hash_assertion(path, digest) for path, digest in expected.items()
    )
    run_remote_script(
        ssh_config,
        command,
        safe_error="remote release hash verification failed",
    )


def execute_release(
    repo: Path,
    ssh_config: Path | None,
    commit: str,
    site_files: dict[str, Path],
    site_snapshot_hashes: dict[str, str],
    commands: list[list[str]],
    *, app_staging: Path | None = None,
) -> None:
    expected_hashes = expected_release_hashes(repo, site_files)
    backup_dir = backup_release(ssh_config, commit, site_snapshot_hashes, repo, site_files['_rollback_htaccess'].read_bytes())
    completed = 0
    try:
        ensure_module_directory(ssh_config)
        verified_graph = False
        for command in commands:
            if not verified_graph and command[-1].endswith('/' + ENTRY_SOURCE):
                verify_remote_hashes(ssh_config, {
                    REMOTE_APP_ROOT / asset['target']: asset['sha256'] for asset in browser_assets(repo)
                })
                verified_graph = True
            result = run(command, cwd=app_staging, safe_error="an allowlisted release upload failed")
            completed += 1
            output = result.stdout.decode("utf-8", "replace").strip()
            if output:
                print(output)
        verify_remote_hashes(ssh_config, expected_hashes)
    except BaseException as upload_error:
        try:
            restore_release(ssh_config, backup_dir, commit, repo)
        except DeploymentError as restore_error:
            raise DeploymentError(
                f"release failed after {completed} of {len(commands)} uploads and rollback could not be confirmed; "
                f"the private backup is {backup_dir}; {restore_error}"
            ) from upload_error
        try:
            release_deployment_lock(ssh_config)
        except DeploymentError as lock_error:
            raise DeploymentError(
                f"release failed after {completed} of {len(commands)} uploads; mutable files were restored from {backup_dir} and immutable assets/routes retained, "
                f"but the deployment lock remains; {lock_error}"
            ) from upload_error
        raise DeploymentError(
            f"release failed after {completed} of {len(commands)} uploads; mutable files were restored from {backup_dir}; immutable assets and compatible routes were retained"
        ) from upload_error
    release_deployment_lock(ssh_config)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def maybe_purge_cache(*, execute: bool) -> None:
    configured = os.environ.get("SMD_CACHE_PURGE_COMMAND", "").strip()
    if not configured:
        print("Cache purge: not configured; a legitimate cache purge is still required after deployment.")
        return
    command_path = Path(configured)
    if not command_path.is_absolute():
        raise DeploymentError("SMD_CACHE_PURGE_COMMAND must be an absolute path to a local executable wrapper")
    if command_path.is_symlink() or not command_path.is_file() or not os.access(command_path, os.X_OK):
        raise DeploymentError("SMD_CACHE_PURGE_COMMAND must name a non-symlink executable file")
    if command_path.stat().st_uid != os.getuid():
        raise DeploymentError("SMD_CACHE_PURGE_COMMAND must be owned by the current local user")
    try:
        command_path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise DeploymentError("SMD_CACHE_PURGE_COMMAND must remain outside the repository")
    if not execute:
        print("Cache purge: an owned local executable wrapper is configured; it would run only after a successful real deployment.")
        return
    try:
        result = subprocess.run(
            [str(command_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError as exc:
        raise DeploymentError("the secret-local cache purge wrapper could not be executed") from exc
    if result.returncode:
        raise DeploymentError("the secret-local cache purge command failed; its output was suppressed")
    print("Cache purge: secret-local command completed successfully (command and output suppressed).")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="preview only (the default)")
    mode.add_argument("--execute", action="store_true", help="perform the production upload")
    parser.add_argument(
        "--ssh-config",
        type=Path,
        help="use an alternate local OpenSSH config file (primarily for isolated testing)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    execute = bool(args.execute)
    try:
        configure_target()
        branch, commit = validate_repository(ROOT, execute=execute)
        validate_allowlist(ROOT)
        validate_ssh_alias(args.ssh_config)
        check_remote_paths(args.ssh_config)
        module_directory_present = remote_module_directory_exists(args.ssh_config)
        print(f"Mode: {'EXECUTE' if execute else 'DRY RUN (no production writes)'}")
        print(f"Git commit: {commit}")
        print(f"Git branch: {branch or 'detached HEAD'}")
        print("SSH target: configured local profile (connection details intentionally not displayed)")
        with tempfile.TemporaryDirectory(prefix="smd-deploy-") as temporary:
            site_files, site_snapshot_hashes = prepare_site_files(
                ROOT,
                args.ssh_config,
                Path(temporary),
            )
            app_staging = stage_public_assets(ROOT, Path(temporary) / 'application')
            commands = rsync_commands(
                ROOT, site_files, args.ssh_config, dry_run=not execute, app_staging=app_staging,
                module_directory_exists=module_directory_present
            )
            if not execute:
                if not module_directory_present:
                    print('New immutable assets are validated and planned; their rsync simulation is omitted because the asset directory is absent. No directory is created by this dry run.')
                for command in commands:
                    result = run(command, cwd=app_staging, safe_error="an rsync dry-run check failed")
                    output = result.stdout.decode("utf-8", "replace").strip()
                    if output:
                        print(output)
            else:
                execute_release(
                    ROOT,
                    args.ssh_config,
                    commit,
                    site_files,
                    site_snapshot_hashes,
                    commands,
                    app_staging=app_staging,
                )
        print("Public application allowlist:")
        for source, target in public_asset_files(ROOT):
            print(f"  {target}  sha256={file_hash(ROOT / source)}")
        print("Site-root merge files (configured destination intentionally not displayed):")
        for name in SITE_FILES:
            print(f"  {name}")
        maybe_purge_cache(execute=execute)
        if execute:
            print("Deployment upload completed; run tools/verify_production.py before declaring success.")
        else:
            print("Dry run completed; no production file or cache state was changed.")
        return 0
    except (DeploymentError, OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
