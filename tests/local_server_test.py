#!/usr/bin/env python3
"""Exercise the local server's public routes and credential boundary."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
import tempfile
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

spec = importlib.util.spec_from_file_location("preview", Path(__file__).resolve().parents[1] / "tools/serve_workbench.py")
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)
from browser_assets import MODULE_SOURCES, browser_assets, source_for_route, validate_manifest
from update_browser_assets import expected_files


class LocalServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = preview.WorkbenchHTTPServer(("127.0.0.1", 0), preview.WorkbenchHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_all_public_routes(self):
        for route, (filename, content_type) in preview.ROUTES.items():
            with self.subTest(route=route), urlopen(self.base + preview.PREFIX + route + "?v=test") as response:
                self.assertEqual(response.read(), (preview.ROOT / filename).read_bytes())
                self.assertTrue(response.headers["Content-Type"].startswith(content_type))
                self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])

    def test_parallel_browser_graph_requests_complete_without_resets(self):
        assets = browser_assets(preview.ROOT)
        def fetch(asset):
            with urlopen(self.base + asset['url'], timeout=10) as response:
                return response.read() == (preview.ROOT / asset['source']).read_bytes()
        with ThreadPoolExecutor(max_workers=28) as pool:
            self.assertTrue(all(pool.map(fetch, assets * 4)))

    def test_private_files_and_traversal_are_unavailable(self):
        for path in ("/history.php", "/.git/config", "/config/.space-track-config.php.example", "/../README.md", "/%2e%2e/README.md", "/research/physics_v1/core.py", "/browser-assets.json", "/app/common.js", "/app/interface.js", "/app/private-config.json", "/app/common-000000000000.js", "/app/../common.js"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                urlopen(self.base + preview.PREFIX + path)
            self.assertEqual(error.exception.code, 404)

    def test_encoded_paths_cannot_bypass_the_explicit_public_route_map(self):
        for path in (
            '/app%2fcommon.js', '/app/%2e%2e/browser-assets.json',
            '/app/%252e%252e/research/private.py', '/%2e%2e/README.md',
            '/%2fapp%2fcommon.js', '/app/bootstrap-000000000000%2ejs',
            '/%2e/benchmark/manifest', '/app%5ccommon.js',
        ):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                urlopen(self.base + preview.PREFIX + path)
            self.assertEqual(error.exception.code, 404)

    def test_history_explains_local_limitation(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + preview.PREFIX + "/history?norad=25544")
        self.assertEqual(error.exception.code, 503)
        body = json.load(error.exception)
        self.assertEqual(body["code"], "LOCAL_PREVIEW")
        self.assertIn("Import", body["message"])

    @staticmethod
    def snapshot(directory):
        root = Path(directory)
        for name in (*MODULE_SOURCES, 'app-3.4.js', 'browser-assets.json', 'index.html'):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(preview.ROOT / name, target)
        return root

    def test_module_hash_identity_never_serves_changed_source_under_old_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.snapshot(directory)
            old = browser_assets(root)[0]
            path = root / old['source']
            path.write_bytes(path.read_bytes() + b'\n// changed synthetic source fixture\n')
            new = browser_assets(root)[0]
            self.assertNotEqual(old['url'], new['url'])
            self.assertIsNone(source_for_route(root, old['url']))
            self.assertEqual(source_for_route(root, new['url']), old['source'])
            with patch.object(preview, 'ROOT', root):
                with self.assertRaises(HTTPError) as error:
                    urlopen(self.base + old['url'])
                self.assertEqual(error.exception.code, 404)
                with urlopen(self.base + new['url']) as response:
                    self.assertEqual(response.read(), path.read_bytes())

    def test_manifest_rejects_private_sources_duplicates_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.snapshot(directory)
            manifest = root / 'browser-assets.json'
            original = json.loads(manifest.read_text())
            for mutation in (
                lambda value: value['module_sources'].append('config/private.php'),
                lambda value: value.update(entry_source='research/private.py'),
                lambda value: value.update(extra='unexpected'),
            ):
                value = json.loads(json.dumps(original))
                mutation(value)
                manifest.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    validate_manifest(root)
            manifest.write_text('{"schema":"one","schema":"two"}')
            with self.assertRaises(ValueError):
                validate_manifest(root)

    def test_asset_source_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.snapshot(directory)
            source = root / MODULE_SOURCES[0]
            source.unlink()
            source.symlink_to(root / 'app-3.4.js')
            with self.assertRaises(ValueError):
                browser_assets(root)

    def test_asset_updater_rejects_a_symlinked_entry_document(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.snapshot(directory)
            index = root / 'index.html'
            original = index.read_bytes()
            sentinel = root / 'untouched-document.html'
            sentinel.write_bytes(original)
            index.unlink()
            index.symlink_to(sentinel)
            with self.assertRaises(ValueError):
                expected_files(root)
            self.assertEqual(sentinel.read_bytes(), original)

    def test_asset_refresh_is_read_only_until_applied_and_then_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.snapshot(directory)
            before = {name: (root / name).read_bytes() for name in ('index.html', 'app-3.4.js')}
            module = root / MODULE_SOURCES[0]
            module.write_bytes(module.read_bytes() + b'\n// changed synthetic source fixture\n')
            expected = expected_files(root)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in before})
            self.assertTrue(all(expected[name].encode() != before[name] for name in before))
            for name, content in expected.items():
                (root / name).write_text(content)
            self.assertEqual(expected_files(root), expected)
            updated = browser_assets(root)
            self.assertIn(updated[0]['url'], expected['index.html'])
            self.assertIn(updated[0]['url'], expected['app-3.4.js'])
            self.assertIn(updated[-1]['url'], expected['index.html'])

    def test_root_opens_workbench(self):
        with urlopen(self.base) as response:
            self.assertEqual(response.url, self.base + preview.PREFIX + "/")
            self.assertIn(b"Satellite Maneuver", response.read())


if __name__ == "__main__":
    unittest.main()
