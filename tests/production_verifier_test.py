#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_production", ROOT / "tools/verify_production.py")
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


BASE = verifier.DEFAULT_BASE_URL
PREFIX = verifier.PUBLIC_PREFIX


def html_response(path: str, filename: str) -> object:
    return verifier.Response(
        200,
        dict(verifier.EXPECTED_HEADERS, **{"strict-transport-security": "max-age=31536000"}),
        (ROOT / filename).read_bytes(),
        BASE + path,
    )


def current_responses() -> dict[str, object]:
    app_bytes = (ROOT / "app-3.4.js").read_bytes()
    satellite_bytes = (ROOT / "satellite-6.0.2.min.js").read_bytes()
    app_path = verifier.content_versioned_path("app-3.4.js", app_bytes)
    satellite_path = verifier.content_versioned_path("satellite-6.0.2.min.js", satellite_bytes)
    responses = {
        BASE + PREFIX + "/": html_response(PREFIX + "/", "index.html"),
        BASE + PREFIX + "/docs": html_response(PREFIX + "/docs", "docs.html"),
        BASE + PREFIX + "/benchmark": html_response(PREFIX + "/benchmark", "benchmark.html"),
        BASE + PREFIX + "/accessibility": html_response(PREFIX + "/accessibility", "accessibility.html"),
    }
    app_headers = dict(verifier.EXPECTED_HEADERS, **{
        "strict-transport-security": "max-age=31536000",
        "x-robots-tag": "noindex, nofollow, nosnippet",
        "content-type": "text/javascript; charset=utf-8",
    })
    responses[BASE + app_path] = verifier.Response(
        200, app_headers, app_bytes, BASE + app_path
    )
    responses[BASE + satellite_path] = verifier.Response(
        200, app_headers, satellite_bytes, BASE + satellite_path
    )
    for asset in verifier.browser_assets(ROOT):
        responses[BASE + asset['url']] = verifier.Response(
            200, app_headers, (ROOT / asset['source']).read_bytes(), BASE + asset['url']
        )
    for suffix, filename in (
        ("/benchmark/manifest", "public-evidence-manifest-v0.1.json"),
        ("/benchmark/template", "benchmark-template.json"),
    ):
        responses[BASE + PREFIX + suffix] = verifier.Response(
            200, app_headers, (ROOT / filename).read_bytes(), BASE + PREFIX + suffix
        )
    history_url = BASE + PREFIX + "/history?norad=invalid&start=2026-01-01&end=2026-01-02"
    responses[history_url] = verifier.Response(
        400,
        {
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
            "x-frame-options": "DENY",
            "permissions-policy": "camera=()",
        },
        b'{"ok":false,"message":"NORAD must contain digits only."}',
        history_url,
    )
    for path in (
        "/tools/satellite-maneuver-detector/index.html",
        "/tools/satellite-maneuver-detector/app-3.4.js",
        PREFIX + "/app/common.js",
        PREFIX + "/app/private-config.json",
        "/tools/satellite-maneuver-detector/" + verifier.browser_assets(ROOT)[0]["target"],
        "/.space-track-config.php",
        "/.satellite-maneuver-cache/",
        "/tools/satellite-maneuver-detector/.space-track-config.php",
        "/tools/satellite-maneuver-detector/.satellite-maneuver-cache/",
    ):
        responses[BASE + path] = verifier.Response(403, {}, b"Forbidden", BASE + path)
    robots = """User-agent: *
Allow: /satsift
Disallow: /satsift/history
Disallow: /satsift/benchmark/manifest
Disallow: /satsift/benchmark/template
Allow: /satellite-maneuver-detector
Disallow: /satellite-maneuver-detector/history
Disallow: /satellite-maneuver-detector/benchmark/manifest
Disallow: /satellite-maneuver-detector/benchmark/template
Disallow: /tools/satellite-maneuver-detector/
Sitemap: https://www.sylvesterkaczmarek.com/sitemap.xml
"""
    responses[BASE + "/robots.txt"] = verifier.Response(200, {}, robots.encode(), BASE + "/robots.txt")
    sitemap_entries = "".join(f"<url><loc>{url}</loc></url>" for url in verifier.EXPECTED_PUBLIC_URLS)
    sitemap = f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sitemap_entries}</urlset>'
    responses[BASE + "/sitemap.xml"] = verifier.Response(200, {}, sitemap.encode(), BASE + "/sitemap.xml")
    for filename in ("plotly-3.3.1.min.js", "dependency-notices.txt"):
        url = BASE + PREFIX + "/" + filename
        headers = dict(app_headers)
        if filename.endswith('.txt'):
            headers['content-type'] = 'text/plain; charset=utf-8'
        responses[url] = verifier.Response(200, headers, (ROOT / filename).read_bytes(), url)
    for suffix in ("", "/", ".html", "/docs", "/docs.html", "/benchmark", "/accessibility"):
        page = suffix.removesuffix('.html')
        canonical = BASE + PREFIX + (page if page and page != '/' else '/')
        query = '?source=legacy%2Fbookmark'
        current = responses[canonical]
        responses[BASE + verifier.LEGACY_PREFIX + suffix + query] = verifier.Response(
            200, current.headers, current.body, canonical + query, ((301, canonical + query),)
        )
    index = responses[BASE + PREFIX + '/']
    responses[BASE + PREFIX] = verifier.Response(200, index.headers, index.body,
                                               BASE + PREFIX + '/', ((301, BASE + PREFIX + '/'),))
    for suffix, filename in (("/benchmark/manifest", "public-evidence-manifest-v0.1.json"),
                             ("/benchmark/template", "benchmark-template.json"),
                             ("/satellite-6.0.2.min.js", "satellite-6.0.2.min.js"),
                             ("/" + verifier.browser_assets(ROOT)[0]['target'], verifier.browser_assets(ROOT)[0]['source'])):
        url = BASE + verifier.LEGACY_PREFIX + suffix
        responses[url] = verifier.Response(200, app_headers, (ROOT / filename).read_bytes(), url)
    old_history = BASE + verifier.LEGACY_PREFIX + "/history?norad=invalid&start=2026-01-01&end=2026-01-02"
    responses[old_history] = verifier.Response(400, responses[history_url].headers,
                                              responses[history_url].body, old_history)
    return responses


def test_redirect_capture() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith('/old?'):
                self.send_response(301)
                self.send_header('Location', '/new?' + self.path.split('?', 1)[1])
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'canonical fixture')
        def log_message(self, *_args):
            pass
    server = HTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    try:
        response = verifier.fetch_url(base + '/old?value=legacy%2Fbookmark')
        expected = base + '/new?value=legacy%2Fbookmark'
        if response.status != 200 or response.final_url != expected or response.redirects != ((301, expected),):
            raise AssertionError('actual HTTP redirect chain and query were not captured')
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def main() -> None:
    test_redirect_capture()
    responses = current_responses()
    app_path = verifier.content_versioned_path("app-3.4.js", (ROOT / "app-3.4.js").read_bytes())
    report = verifier.verify(BASE, responses.__getitem__)
    if report.failures:
        raise AssertionError("current fixture failed verification:\n" + "\n".join(report.failures))

    redirected = dict(responses)
    docs_response = responses[BASE + PREFIX + "/docs"]
    redirected[BASE + PREFIX + "/docs"] = verifier.Response(
        docs_response.status,
        docs_response.headers,
        docs_response.body,
        "https://unexpected.example.invalid/satellite-maneuver-detector/docs",
    )
    redirect_report = verifier.verify(BASE, redirected.__getitem__)
    if not any("expected public origin" in message for message in redirect_report.failures):
        raise AssertionError("unexpected cross-origin redirect was not detected")

    unversioned = dict(responses)
    current_index = (ROOT / "index.html").read_text()
    unversioned_index = current_index
    for filename in ("app-3.4.js", "satellite-6.0.2.min.js"):
        unversioned_index = unversioned_index.replace(
            verifier.content_versioned_path(filename, (ROOT / filename).read_bytes()),
            f"{PREFIX}/{filename}",
        )
    unversioned[BASE + PREFIX + "/"] = verifier.Response(
        200,
        responses[BASE + PREFIX + "/"].headers,
        unversioned_index.encode(),
        BASE + PREFIX + "/",
    )
    unversioned_report = verifier.verify(BASE, unversioned.__getitem__)
    if not any("content-versioned satellite.js" in message for message in unversioned_report.failures):
        raise AssertionError("unversioned application dependencies were not rejected")

    missing_satellite_hsts = dict(responses)
    satellite_path = verifier.content_versioned_path(
        "satellite-6.0.2.min.js", (ROOT / "satellite-6.0.2.min.js").read_bytes()
    )
    satellite_response = responses[BASE + satellite_path]
    satellite_headers = dict(satellite_response.headers)
    satellite_headers.pop("strict-transport-security")
    missing_satellite_hsts[BASE + satellite_path] = verifier.Response(
        satellite_response.status,
        satellite_headers,
        satellite_response.body,
        satellite_response.final_url,
    )
    satellite_hsts_report = verifier.verify(BASE, missing_satellite_hsts.__getitem__)
    if "satellite.js: HTTPS HSTS policy is present" not in satellite_hsts_report.failures:
        raise AssertionError("missing satellite.js HSTS policy was not rejected")

    stale = dict(responses)
    old_index = (ROOT / "index.html").read_text().replace("SatSift " + verifier.WORKBENCH_VERSION, "SatSift stale")
    stale[BASE + PREFIX + "/"] = verifier.Response(
        200,
        responses[BASE + PREFIX + "/"].headers,
        old_index.encode(),
        BASE + PREFIX + "/",
    )
    old_app = (ROOT / "app-3.4.js").read_text() + "\n// outdated bootstrap fixture\n"
    stale[BASE + app_path] = verifier.Response(
        200,
        responses[BASE + app_path].headers,
        old_app.encode(),
        BASE + app_path,
    )
    stale_report = verifier.verify(BASE, stale.__getitem__)
    if not any("version " + verifier.WORKBENCH_VERSION in message for message in stale_report.failures):
        raise AssertionError("stale Workbench version was not detected")
    if not any("SHA-256" in message for message in stale_report.failures):
        raise AssertionError("stale application hash was not detected")
    for asset in verifier.browser_assets(ROOT):
        corrupt = dict(responses)
        current = responses[BASE + asset['url']]
        corrupt[BASE + asset['url']] = verifier.Response(
            current.status, current.headers, current.body + b'\n// corrupt fixture', current.final_url
        )
        corruption_report = verifier.verify(BASE, corrupt.__getitem__)
        if not any('browser asset ' + asset['name'] + ': deployed SHA-256' in error
                   for error in corruption_report.failures):
            raise AssertionError('corrupt module asset was accepted')
    first = verifier.browser_assets(ROOT)[0]
    bad_integrity = dict(responses)
    bad_integrity[BASE + PREFIX + "/"] = verifier.Response(
        200, responses[BASE + PREFIX + "/"].headers,
        (ROOT / 'index.html').read_text().replace(first['integrity'], 'sha256-invalid').encode(),
        BASE + PREFIX + "/",
    )
    if not any('exact content-addressed URL, defer and integrity' in failure
               for failure in verifier.verify(BASE, bad_integrity.__getitem__).failures):
        raise AssertionError('incorrect script integrity was accepted')
    nonpermanent = dict(responses)
    old_url = BASE + verifier.LEGACY_PREFIX + '?source=legacy%2Fbookmark'
    current = responses[old_url]
    nonpermanent[old_url] = verifier.Response(current.status, current.headers, current.body,
                                            current.final_url, ((302, current.final_url),))
    if not any('one permanent redirect' in error for error in verifier.verify(BASE, nonpermanent.__getitem__).failures):
        raise AssertionError('temporary legacy redirect was accepted')
    missing_notices = dict(responses)
    notice_url = BASE + PREFIX + '/dependency-notices.txt'
    current = responses[notice_url]
    missing_notices[notice_url] = verifier.Response(200, current.headers, b'incomplete notices', notice_url)
    if not any('dependency-notices.txt: deployed SHA-256' in error for error in verifier.verify(BASE, missing_notices.__getitem__).failures):
        raise AssertionError('incomplete distributed notices were accepted')
    print("Production verifier regressions passed: current fixture accepted and stale fixture rejected.")


if __name__ == "__main__":
    main()
