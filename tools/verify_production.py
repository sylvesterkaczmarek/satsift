#!/usr/bin/env python3
"""Read-only verification of the public SatSift deployment."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import ssl
import sys
from typing import Callable
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_assets import browser_assets

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://www.sylvesterkaczmarek.com"
PUBLIC_PREFIX = "/satsift"
LEGACY_PREFIX = "/satellite-maneuver-detector"
WORKBENCH_VERSION = json.loads((ROOT / "package.json").read_text())["version"]
EXPECTED_PUBLIC_URLS = (
    DEFAULT_BASE_URL + PUBLIC_PREFIX + "/",
    DEFAULT_BASE_URL + PUBLIC_PREFIX + "/docs",
    DEFAULT_BASE_URL + PUBLIC_PREFIX + "/benchmark",
    DEFAULT_BASE_URL + PUBLIC_PREFIX + "/accessibility",
)
EXPECTED_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "content-security-policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; connect-src 'self' https://celestrak.org; "
        "font-src 'self' data:; worker-src 'self' blob:; object-src 'none'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
}
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes
    final_url: str
    redirects: tuple[tuple[int, str], ...] = ()


class CanonicalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonicals: list[str] = []
        self.scripts: list[dict] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if tag.lower() == "script":
            self.scripts.append(values)
        if tag.lower() == "link" and "canonical" in values.get("rel", "").lower().split():
            self.canonicals.append(values.get("href", ""))


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes: list[str] = []

    def check(self, condition: bool, message: str) -> None:
        (self.passes if condition else self.failures).append(message)


def fetch_url(url: str, timeout: float = 15.0) -> Response:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "SatSift-deployment-verifier/1.1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        method="GET",
    )
    redirects: list[tuple[int, str]] = []
    class RecordRedirects(urllib.request.HTTPRedirectHandler):
        max_redirections = 5
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            redirects.append((code, newurl))
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()), RecordRedirects()
    )
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        return Response(0, {}, b"response exceeded verifier safety limit", response.geturl())
    headers = {key.lower(): value.strip() for key, value in response.headers.items()}
    return Response(int(response.status), headers, body, response.geturl(), tuple(redirects))


def text(response: Response) -> str:
    return response.body.decode("utf-8", "replace")


def content_versioned_path(filename: str, content: bytes) -> str:
    version = hashlib.sha256(content).hexdigest()[:12]
    return f"{PUBLIC_PREFIX}/{filename}?v={version}"


def check_security_headers(report: Report, response: Response, label: str, *, https: bool) -> None:
    for header, expected in EXPECTED_HEADERS.items():
        actual = response.headers.get(header, "")
        report.check(actual == expected, f"{label}: {header} matches repository policy")
    if https:
        report.check(
            response.headers.get("strict-transport-security") == "max-age=31536000",
            f"{label}: HTTPS HSTS policy is present",
        )


def check_canonical(report: Report, response: Response, expected: str, label: str) -> None:
    parser = CanonicalParser()
    parser.feed(text(response))
    report.check(response.status == 200, f"{label}: clean route returns HTTP 200")
    report.check(response.final_url == expected and not response.redirects, f"{label}: response remains on the expected public origin")
    report.check(parser.canonicals == [expected], f"{label}: canonical URL is exact")


def verify(
    base_url: str,
    fetcher: Callable[[str], Response],
    repo: Path = ROOT,
) -> Report:
    base = base_url.rstrip("/")
    https = base.lower().startswith("https://")
    report = Report()

    paths = {
        "workbench": "/",
        "docs": "/docs",
        "benchmark": "/benchmark",
        "accessibility": "/accessibility",
    }
    pages: dict[str, Response] = {}
    for label, suffix in paths.items():
        response = fetcher(base + PUBLIC_PREFIX + suffix)
        pages[label] = response
        canonical = DEFAULT_BASE_URL + PUBLIC_PREFIX + suffix
        check_canonical(report, response, canonical, label)
        check_security_headers(report, response, label, https=https)

    assets = browser_assets(repo)
    workbench_parser = CanonicalParser()
    workbench_parser.feed(text(pages['workbench']))
    scripts = workbench_parser.scripts
    script_sources = [script.get('src') for script in scripts]
    expected_sources = [asset['url'] for asset in assets]
    report.check([source for source in script_sources if source in expected_sources] == expected_sources,
                 'application: all immutable module scripts are ordered before bootstrap')
    fetched_modules = []
    for asset in assets:
        label = 'browser asset ' + asset['name']
        matching_tags = [script for script in scripts if script.get('src') == asset['url']]
        report.check(len(matching_tags) == 1 and 'defer' in matching_tags[0]
                     and matching_tags[0].get('integrity') == asset['integrity'],
                     label + ': exact content-addressed URL, defer and integrity are referenced')
        response = fetcher(base + asset['url'])
        report.check(response.status == 200, label + ': current asset returns HTTP 200')
        report.check(response.final_url == base + asset['url'], label + ': expected public origin is retained')
        report.check(hashlib.sha256(response.body).hexdigest() == asset['sha256'],
                     label + ': deployed SHA-256 matches the repository source')
        report.check(response.headers.get('content-type', '').split(';')[0].lower()
                     in ('text/javascript', 'application/javascript'), label + ': JavaScript MIME type is present')
        check_security_headers(report, response, label, https=https)
        report.check('noindex' in response.headers.get('x-robots-tag', '').lower(),
                     label + ': machine asset carries noindex policy')
        fetched_modules.append(text(response))

    expected_app = (repo / "app-3.4.js").read_bytes()
    expected_satellite = (repo / "satellite-6.0.2.min.js").read_bytes()
    app_asset_path = content_versioned_path("app-3.4.js", expected_app)
    satellite_asset_path = content_versioned_path("satellite-6.0.2.min.js", expected_satellite)

    workbench = text(pages["workbench"])
    report.check("SatSift " + WORKBENCH_VERSION in workbench, "workbench: version " + WORKBENCH_VERSION + " is live")
    report.check("Detector method 0.4" in workbench, "workbench: detector method 0.4 is live")
    report.check(
        assets[-1]["url"] in workbench,
        "workbench: content-versioned application asset is referenced",
    )
    report.check(
        satellite_asset_path in workbench,
        "workbench: content-versioned satellite.js asset is referenced",
    )
    report.check(
        PUBLIC_PREFIX + "/plotly-3.3.1.min.js" not in re.findall(r"<script[^>]+src=[\"']([^\"']+)", workbench, re.I),
        "workbench: Plotly is not eagerly loaded by the initial document",
    )

    app_response = fetcher(base + app_asset_path)
    app = "\n".join([*fetched_modules, text(app_response)])
    report.check(app_response.status == 200, "application: current asset returns HTTP 200")
    report.check(
        app_response.final_url == base + app_asset_path,
        "application: response remains on the expected public origin",
    )
    report.check(
        hashlib.sha256(app_response.body).digest() == hashlib.sha256(expected_app).digest(),
        "application: deployed SHA-256 matches the repository asset",
    )
    required_app_markers = {
        "release and detector versions": (
            "const METHOD_VERSION = 'v0.4';",
            "const WORKBENCH_VERSION = '" + WORKBENCH_VERSION + "';",
        ),
        "UTC-safe OMM parser": (
            "function parseOmmEpochUtc(value)",
            "const normalized = zone ? raw : raw + 'Z';",
        ),
        "precise TLE replay and versioned identity": (
            "function formatEpochUs(epochUs)",
            "function propagateRecordAtEpoch(record, targetUs)",
            "const PACKAGE_SCHEMA_VERSION = 1;",
            "const RUN_IDENTITY_VERSION = 2;",
            "const PROPAGATION_CONTRACT = 'sgp4-exact-epoch-v1';",
            "SMD_TLE",
        ),
        "catalogue supersession": (
            "function catalogueMetadataPreference(first, second)",
            "deterministic catalogue supersession",
        ),
        "lazy Plotly loader": (
            "function ensurePlotlyLoaded()",
            "PLOTLY_ASSET_URL = '/satsift/plotly-3.3.1.min.js",
        ),
    }
    for label, markers in required_app_markers.items():
        report.check(all(marker in app for marker in markers), f"application: {label} implementation is live")
    report.check("new Date(record.EPOCH)" not in app, "application: stale timezone-unsafe parser is absent")
    report.check(
        "const WORKBENCH_VERSION = '3.4';" not in app,
        "application: stale Workbench 3.4 version constant is absent",
    )
    check_security_headers(report, app_response, "application", https=https)
    report.check(
        "noindex" in app_response.headers.get("x-robots-tag", "").lower(),
        "application: machine asset carries noindex policy",
    )

    satellite_response = fetcher(base + satellite_asset_path)
    report.check(satellite_response.status == 200, "satellite.js: current asset returns HTTP 200")
    report.check(
        satellite_response.final_url == base + satellite_asset_path,
        "satellite.js: response remains on the expected public origin",
    )
    report.check(
        hashlib.sha256(satellite_response.body).digest() == hashlib.sha256(expected_satellite).digest(),
        "satellite.js: deployed SHA-256 matches the repository asset",
    )
    check_security_headers(report, satellite_response, "satellite.js", https=https)
    report.check(
        "noindex" in satellite_response.headers.get("x-robots-tag", "").lower(),
        "satellite.js: machine asset carries noindex policy",
    )

    for filename, mime in (("plotly-3.3.1.min.js", "javascript"),
                           ("dependency-notices.txt", "text/plain")):
        url = base + PUBLIC_PREFIX + "/" + filename
        response = fetcher(url)
        report.check(response.status == 200 and response.final_url == url and not response.redirects,
                     filename + ": canonical distribution resource returns HTTP 200 directly")
        report.check(hashlib.sha256(response.body).digest() == hashlib.sha256((repo / filename).read_bytes()).digest(),
                     filename + ": deployed SHA-256 matches the complete repository resource")
        report.check(mime in response.headers.get("content-type", "").lower(),
                     filename + ": correct media type is present")
        report.check("noindex" in response.headers.get("x-robots-tag", "").lower(),
                     filename + ": machine resource carries noindex policy")
        check_security_headers(report, response, filename, https=https)

    # Verify the actual redirect chain, not merely a successful final page.
    for suffix in ("", "/", ".html", "/docs", "/docs.html", "/benchmark", "/accessibility"):
        destination = suffix.removesuffix(".html")
        canonical = base + PUBLIC_PREFIX + (destination if destination and destination != "/" else "/")
        query = "?source=legacy%2Fbookmark"
        response = fetcher(base + LEGACY_PREFIX + suffix + query)
        report.check(response.status == 200 and response.final_url == canonical + query
                     and response.redirects == ((301, canonical + query),),
                     "legacy page " + (suffix or "root") + ": one permanent redirect preserves the query")
    bare = fetcher(base + PUBLIC_PREFIX)
    report.check(bare.status == 200 and bare.final_url == base + PUBLIC_PREFIX + "/"
                 and bare.redirects == ((301, base + PUBLIC_PREFIX + "/"),),
                 "workbench: missing trailing slash redirects once to the canonical root")

    for suffix, expected in (("/benchmark/manifest", (repo / "public-evidence-manifest-v0.1.json").read_bytes()),
                             ("/benchmark/template", (repo / "benchmark-template.json").read_bytes()),
                             ("/satellite-6.0.2.min.js", expected_satellite),
                             ("/" + assets[0]["target"], (repo / assets[0]["source"]).read_bytes())):
        url = base + LEGACY_PREFIX + suffix
        response = fetcher(url)
        report.check(response.status == 200 and response.final_url == url and not response.redirects
                     and hashlib.sha256(response.body).digest() == hashlib.sha256(expected).digest(),
                     "legacy resource " + suffix + ": exact resource remains directly available")

    benchmark = text(pages["benchmark"])
    benchmark_markers = (
        "Public Workbench seed v0.1",
        "Frozen publication benchmark v1.0",
        "confirmatory partition was consumed once",
        "detector method 0.4 remains the public scientific method",
    )
    report.check(
        all(marker in benchmark for marker in benchmark_markers),
        "benchmark: seed v0.1/publication v1.0 and failed-integration wording is current",
    )

    for suffix in ("/benchmark/manifest", "/benchmark/template"):
        machine = fetcher(base + PUBLIC_PREFIX + suffix)
        report.check(machine.status == 200, f"machine route {suffix}: returns HTTP 200")
        report.check(
            machine.final_url == base + PUBLIC_PREFIX + suffix,
            f"machine route {suffix}: remains on the expected public origin",
        )
        try:
            json.loads(machine.body)
            valid_json = True
        except (json.JSONDecodeError, UnicodeDecodeError):
            valid_json = False
        report.check(valid_json, f"machine route {suffix}: returns valid JSON")

    history = fetcher(
        base + PUBLIC_PREFIX + "/history?norad=invalid&start=2026-01-01&end=2026-01-02"
    )
    try:
        history_payload = json.loads(history.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        history_payload = None
    report.check(history.status == 400, "history: safe invalid request returns HTTP 400")
    report.check(
        history.final_url
        == base + PUBLIC_PREFIX + "/history?norad=invalid&start=2026-01-01&end=2026-01-02",
        "history: response remains on the expected public origin",
    )
    report.check(
        isinstance(history_payload, dict) and history_payload.get("ok") is False,
        "history: error response is structured JSON",
    )
    legacy_history_url = base + LEGACY_PREFIX + "/history?norad=invalid&start=2026-01-01&end=2026-01-02"
    legacy_history = fetcher(legacy_history_url)
    try:
        legacy_error = json.loads(legacy_history.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        legacy_error = None
    report.check(legacy_history.status == 400 and legacy_history.final_url == legacy_history_url
                 and not legacy_history.redirects and isinstance(legacy_error, dict) and legacy_error.get("ok") is False,
                 "legacy history: safe invalid request retains direct structured HTTP 400 behaviour")
    history_text = text(history).lower()
    report.check(
        not any(secret in history_text for secret in ("password", "identity=", "private key", "space_track_password")),
        "history: response exposes no credential material",
    )
    for header in ("x-content-type-options", "referrer-policy", "x-frame-options", "permissions-policy"):
        report.check(header in history.headers, f"history: {header} is present")

    denied_paths = (
        "/tools/satellite-maneuver-detector/index.html",
        "/tools/satellite-maneuver-detector/app-3.4.js",
        PUBLIC_PREFIX + "/app/common.js",
        PUBLIC_PREFIX + "/app/private-config.json",
        "/tools/satellite-maneuver-detector/" + assets[0]["target"],
        "/.space-track-config.php",
        "/.satellite-maneuver-cache/",
        "/tools/satellite-maneuver-detector/.space-track-config.php",
        "/tools/satellite-maneuver-detector/.satellite-maneuver-cache/",
    )
    for path in denied_paths:
        denied = fetcher(base + path)
        report.check(denied.status in (403, 404), f"private/physical probe {path}: access is denied")

    robots = fetcher(base + "/robots.txt")
    robots_text = text(robots)
    active_robots = [
        line.strip()
        for line in robots_text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    required_robots = (
        "Allow: /satsift",
        "Disallow: /satsift/history",
        "Disallow: /satsift/benchmark/manifest",
        "Disallow: /satsift/benchmark/template",
        "Allow: /satellite-maneuver-detector",
        "Disallow: /satellite-maneuver-detector/history",
        "Disallow: /satellite-maneuver-detector/benchmark/manifest",
        "Disallow: /satellite-maneuver-detector/benchmark/template",
        "Disallow: /tools/satellite-maneuver-detector/",
        "Sitemap: " + DEFAULT_BASE_URL + "/sitemap.xml",
    )
    report.check(robots.status == 200, "robots.txt: returns HTTP 200")
    report.check(robots.final_url == base + "/robots.txt", "robots.txt: remains on the expected public origin")
    report.check(
        all(active_robots.count(line) == 1 for line in required_robots),
        "robots.txt: detector indexing policy is current",
    )
    report.check(
        all(line not in active_robots for line in ("Disallow: /satsift/", "Disallow: /satellite-maneuver-detector/")),
        "robots.txt: public detector child pages are not broadly blocked",
    )

    sitemap = fetcher(base + "/sitemap.xml")
    locs: list[str] = []
    try:
        sitemap_root = ET.fromstring(sitemap.body)
        locs = [((node.text or "").strip()) for node in sitemap_root.iter() if node.tag.rsplit("}", 1)[-1] == "loc"]
        valid_sitemap = True
    except ET.ParseError:
        valid_sitemap = False
    report.check(sitemap.status == 200 and valid_sitemap, "sitemap.xml: returns valid XML")
    report.check(sitemap.final_url == base + "/sitemap.xml", "sitemap.xml: remains on the expected public origin")
    report.check(
        all(locs.count(url) == 1 for url in EXPECTED_PUBLIC_URLS),
        "sitemap.xml: each clean public detector URL appears exactly once",
    )
    forbidden_locs = [
        loc for loc in locs
        if (re.search(r"/(?:satsift|satellite-maneuver-detector)(?:[./?]|$)", loc) or "/tools/satellite-maneuver-detector" in loc)
        and loc not in EXPECTED_PUBLIC_URLS
    ]
    report.check(not forbidden_locs, "sitemap.xml: no stale, machine, or physical detector URLs are indexed")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="site origin to verify")
    parser.add_argument("--timeout", type=float, default=15.0, help="per-request timeout in seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    def fetcher(url: str) -> Response:
        try:
            return fetch_url(url, timeout=args.timeout)
        except (OSError, urllib.error.URLError) as exc:
            return Response(0, {}, str(exc).encode(), url)

    report = verify(args.base_url, fetcher)
    for message in report.passes:
        print(f"PASS: {message}")
    for message in report.failures:
        print(f"FAIL: {message}")
    if report.failures:
        print(f"Verification failed: {len(report.failures)} check(s) did not match the repository release.")
        return 1
    print(f"Verification passed: {len(report.passes)} read-only checks matched the repository release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
