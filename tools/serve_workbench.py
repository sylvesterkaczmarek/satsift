#!/usr/bin/env python3
"""Run the public workbench locally, without credentials or a PHP server."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_assets import browser_assets

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/satsift"
LEGACY_PREFIX = "/satellite-maneuver-detector"
ROUTES = {
    "/": ("index.html", "text/html"),
    "/dependency-notices.txt": ("dependency-notices.txt", "text/plain"),
    "/docs": ("docs.html", "text/html"),
    "/benchmark": ("benchmark.html", "text/html"),
    "/accessibility": ("accessibility.html", "text/html"),
    "/benchmark/manifest": ("public-evidence-manifest-v0.1.json", "application/json"),
    "/benchmark/template": ("benchmark-template.json", "application/json"),
    "/app-3.4.js": ("app-3.4.js", "text/javascript"),
    "/satellite-6.0.2.min.js": ("satellite-6.0.2.min.js", "text/javascript"),
    "/plotly-3.3.1.min.js": ("plotly-3.3.1.min.js", "text/javascript"),
}




class WorkbenchHTTPServer(ThreadingHTTPServer):
    # Two browser contexts can request the complete deferred graph at once.
    request_queue_size = 64
    daemon_threads = True


class WorkbenchHandler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        query = ("?" + parsed.query) if parsed.query else ""
        if path == "/":
            self.redirect(302, PREFIX + "/" + query)
            return
        prefix = next((candidate for candidate in (PREFIX, LEGACY_PREFIX)
                       if path == candidate or path.startswith(candidate + "/")
                       or path == candidate + ".html"), None)
        route = path[len(prefix):] if prefix else None
        pages = ("", "/docs", "/benchmark", "/accessibility")
        if route is not None:
            for page in pages:
                aliases = (page, page + ".html", page + "/")
                if route in aliases:
                    canonical = PREFIX + (page or "/")
                    if path != canonical:
                        self.redirect(301, canonical + query)
                        return
                    break
        if route in ("/history", "/history/"):
            self.respond(503, "application/json", (
                b'{"code":"LOCAL_PREVIEW","message":"Historical retrieval is unavailable '
                b'in local preview. Import your own TLE or OMM history, or try a built-in example. '
                b'See DEPLOYMENT.md to configure a PHP server with Space-Track access."}'
            ))
        elif route is not None and route.startswith('/app/'):
            try:
                assets = {"/" + asset["target"]: asset["source"] for asset in browser_assets(ROOT)}
                source = assets.get(route)
            except (ValueError, OSError):
                self.respond(503, 'text/plain', b'Browser assets are unavailable.\n')
                return
            if source is None:
                self.respond(404, 'text/plain', b'Not found.\n')
            else:
                self.respond(200, 'text/javascript', (ROOT / source).read_bytes())
        else:
            if route in ("/benchmark/manifest/", "/benchmark/template/"):
                route = route[:-1]
            if route in ROUTES:
                name, content_type = ROUTES[route]
                self.respond(200, content_type, (ROOT / name).read_bytes())
            else:
                self.respond(404, "text/plain", b"Not found.\n")

    def redirect(self, status: int, location: str) -> None:
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def respond(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; "
                         "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                         "connect-src 'self' https://celestrak.org; font-src 'self' data:; "
                         "worker-src 'self' blob:; object-src 'none'; base-uri 'self'; "
                         "form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    with WorkbenchHTTPServer(("127.0.0.1", args.port), WorkbenchHandler) as server:
        print(f"Open http://127.0.0.1:{server.server_port}{PREFIX}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
