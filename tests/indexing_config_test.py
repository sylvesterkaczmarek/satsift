#!/usr/bin/env python3
from __future__ import annotations

import re
import json
from urllib.parse import urlsplit
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.sylvesterkaczmarek.com"
EXPECTED = {
    "index.html": f"{BASE}/satsift/",
    "docs.html": f"{BASE}/satsift/docs",
    "benchmark.html": f"{BASE}/satsift/benchmark",
    "accessibility.html": f"{BASE}/satsift/accessibility",
}


class HeadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonicals: list[str] = []
        self.robots: list[str] = []
        self.metadata: dict[str, list[str]] = {}
        self.urls: list[str] = []
        self.structured: list[str] = []
        self.in_structured = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs = dict(attrs)
        for attribute in ('href', 'src'):
            if attrs.get(attribute):
                self.urls.append(attrs[attribute])
        if tag == 'meta':
            key = attrs.get('name', attrs.get('property', '')).lower()
            self.metadata.setdefault(key, []).append(attrs.get('content', ''))
        if tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json':
            self.structured.append('')
            self.in_structured = True
        if tag == "link" and attrs.get("rel", "").lower() == "canonical":
            self.canonicals.append(attrs.get("href", ""))
        if tag == "meta" and attrs.get("name", "").lower() == "robots":
            self.robots.append(attrs.get("content", ""))

    def handle_data(self, value: str) -> None:
        if self.in_structured:
            self.structured[-1] += value

    def handle_endtag(self, tag: str) -> None:
        if tag == 'script':
            self.in_structured = False


def fail(message: str) -> None:
    raise SystemExit("ERROR: " + message)


def check_html_contract() -> None:
    for filename, expected in EXPECTED.items():
        parser = HeadParser()
        parser.feed((ROOT / filename).read_text())
        if parser.canonicals != [expected]:
            fail(f"{filename} canonical mismatch: {parser.canonicals!r} != {[expected]!r}")
        if len(parser.robots) != 1 or parser.robots[0].replace(" ", "").lower() != "index,follow":
            fail(f"{filename} must declare exactly one index, follow robots meta tag")
        if parser.metadata.get('og:url') != [expected] or parser.metadata.get('og:site_name') != ['SatSift']:
            fail(filename + ' must have one matching OpenGraph URL and SatSift site name')
        if parser.metadata.get('twitter:card') != ['summary']:
            fail(filename + ' must declare its supported Twitter summary card')
        for name in ('description', 'og:title', 'og:description', 'twitter:title', 'twitter:description'):
            values = parser.metadata.get(name, [])
            if len(values) != 1 or not values[0].strip():
                fail(filename + ' is missing unique metadata for ' + name)
            if name.endswith(':title') and 'SatSift' not in values[0]:
                fail(filename + ' social title must name SatSift')
        if len(parser.structured) != 1:
            fail(filename + ' must have one structured-data document')
        try:
            structured = json.loads(parser.structured[0])
        except (json.JSONDecodeError, TypeError):
            fail(filename + ' structured data is invalid JSON')
        if not isinstance(structured, dict) or structured.get('@context') != 'https://schema.org' or structured.get('url') != expected or 'SatSift' not in structured.get('name', ''):
            fail(filename + ' structured data must identify the canonical SatSift page')
        for url in parser.urls + [value for values in parser.metadata.values() for value in values]:
            path = urlsplit(url).path
            if path.startswith(('/satellite-maneuver-detector', '/tools/satellite-maneuver-detector')):
                fail(filename + ' active metadata or resource link uses the legacy namespace')
        if expected.endswith(".html"):
            fail(f"{filename} canonical must use a clean URL")


def check_rewrite_contract() -> None:
    text = (ROOT / "deployment/site-root.htaccess").read_text()
    required = [
        r"RewriteRule ^satellite-maneuver-detector(?:\.html|/*)$ https://www.sylvesterkaczmarek.com/satsift/ [R=301,L,NE]",
        r"RewriteRule ^satellite-maneuver-detector/(docs|benchmark|accessibility)(?:\.html|/*)$ https://www.sylvesterkaczmarek.com/satsift/$1 [R=301,L,NE]",
        'Header always set X-Robots-Tag "noindex, nofollow, nosnippet"',
        "(?:satsift|satellite-maneuver-detector)/(?:history",
        "benchmark/(?:manifest|template)",
    ]
    for marker in required:
        if marker not in text:
            fail(f"deployment rewrite/indexing marker missing: {marker}")


def check_robots_snippet() -> None:
    text = (ROOT / "deployment/robots-detector-snippet.txt").read_text()
    required = [
        "Allow: /satsift",
        "Disallow: /satsift/history",
        "Disallow: /satsift/benchmark/manifest",
        "Disallow: /satsift/benchmark/template",
        "Allow: /satellite-maneuver-detector",
        "Disallow: /satellite-maneuver-detector/history",
        "Disallow: /satellite-maneuver-detector/benchmark/manifest",
        "Disallow: /satellite-maneuver-detector/benchmark/template",
        "Disallow: /tools/satellite-maneuver-detector/",
        "Sitemap: https://www.sylvesterkaczmarek.com/sitemap.xml",
    ]
    for marker in required:
        if marker not in text:
            fail(f"robots detector snippet missing: {marker}")
    active_lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if any(value in active_lines for value in ("Disallow: /satsift/", "Disallow: /satellite-maneuver-detector/")):
        fail("robots detector snippet must not broadly disallow all detector child pages")


def check_sitemap_fragment() -> None:
    text = (ROOT / "deployment/sitemap-detector-fragment.xml").read_text()
    locs = re.findall(r"<loc>([^<]+)</loc>", text)
    expected = list(EXPECTED.values())
    if locs != expected:
        fail(f"detector sitemap URLs mismatch: {locs!r} != {expected!r}")
    forbidden = [".html", "/tools/", "/history", "/benchmark/manifest", "/benchmark/template", ".php", ".json", ".js"]
    for url in locs:
        for fragment in forbidden:
            if fragment in url:
                fail(f"forbidden detector sitemap URL fragment {fragment!r}: {url}")


def main() -> None:
    check_html_contract()
    check_rewrite_contract()
    check_robots_snippet()
    check_sitemap_fragment()
    print("Indexing and canonical URL regressions passed: four clean public HTML URLs only.")


if __name__ == "__main__":
    main()
