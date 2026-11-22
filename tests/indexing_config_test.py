#!/usr/bin/env python3
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.sylvesterkaczmarek.com"
EXPECTED = {
    "index.html": f"{BASE}/satellite-maneuver-detector",
    "docs.html": f"{BASE}/satellite-maneuver-detector/docs",
    "benchmark.html": f"{BASE}/satellite-maneuver-detector/benchmark",
    "accessibility.html": f"{BASE}/satellite-maneuver-detector/accessibility",
}


class HeadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonicals: list[str] = []
        self.robots: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs = dict(attrs)
        if tag == "link" and attrs.get("rel", "").lower() == "canonical":
            self.canonicals.append(attrs.get("href", ""))
        if tag == "meta" and attrs.get("name", "").lower() == "robots":
            self.robots.append(attrs.get("content", ""))


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
        if expected.endswith(".html"):
            fail(f"{filename} canonical must use a clean URL")


def check_rewrite_contract() -> None:
    text = (ROOT / "deployment/site-root.htaccess").read_text()
    required = [
        "RewriteRule ^satellite-maneuver-detector\\.html$ https://www.sylvesterkaczmarek.com/satellite-maneuver-detector [R=301,L,NE]",
        "RewriteRule ^satellite-maneuver-detector/(docs|benchmark|accessibility)\\.html$ https://www.sylvesterkaczmarek.com/satellite-maneuver-detector/$1 [R=301,L,NE]",
        'Header always set X-Robots-Tag "noindex, nofollow, nosnippet"',
        "satellite-maneuver-detector/(?:history",
        "benchmark/(?:manifest|template)",
    ]
    for marker in required:
        if marker not in text:
            fail(f"deployment rewrite/indexing marker missing: {marker}")


def check_robots_snippet() -> None:
    text = (ROOT / "deployment/robots-detector-snippet.txt").read_text()
    required = [
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
    if "Disallow: /satellite-maneuver-detector/" in active_lines:
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
