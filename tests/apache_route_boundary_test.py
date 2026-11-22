#!/usr/bin/env python3
"""Exercise the actual root routing template in an isolated loopback Apache."""
from contextlib import contextmanager
import grp
import http.client
import os
from pathlib import Path
import pwd
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = '/satsift'
LEGACY = '/satellite-maneuver-detector'
PHYSICAL = '/tools/satellite-maneuver-detector'
ASSET = '/app/common-012345abcdef.js'
PRIVATE_MARKER = b'private-repository-probe'
PUBLIC_MARKER = b'public-application-probe'


def apache_installation():
    candidates = [shutil.which(name) for name in ('httpd', 'apache2')]
    candidates += ['/usr/sbin/httpd', '/usr/sbin/apache2', '/opt/homebrew/bin/httpd']
    executable = next((Path(p) for p in candidates if p and Path(p).is_file()), None)
    if executable is None:
        raise RuntimeError('Apache 2.4 is required for this test; install apache2 or httpd.')
    compiled = subprocess.run([str(executable), '-l'], capture_output=True, text=True,
                              timeout=5, check=True).stdout
    module_roots = [Path(p) for p in ('/usr/libexec/apache2', '/usr/lib/apache2/modules',
                    '/usr/lib64/httpd/modules', '/usr/lib/httpd/modules',
                    '/opt/homebrew/lib/httpd/modules')]
    module_roots += [executable.resolve().parent.parent / 'lib/httpd/modules']
    directives = []
    for name in ('mpm_prefork', 'unixd', 'authz_core', 'rewrite', 'headers'):
        if 'mod_' + name + '.c' in compiled or (name == 'mpm_prefork' and 'prefork.c' in compiled):
            continue
        module = next((p / ('mod_' + name + '.so') for p in module_roots
                       if (p / ('mod_' + name + '.so')).is_file()), None)
        if module is None:
            raise RuntimeError('Required Apache module is unavailable: ' + name)
        directives.append('LoadModule ' + name + '_module "' + str(module) + '"')
    return executable, directives


@contextmanager
def server(template, *, encoded_slashes='Off'):
    executable, modules = apache_installation()
    with tempfile.TemporaryDirectory(prefix='smd-apache-route-') as folder:
        tmp = Path(folder)
        tmp.chmod(0o755)
        document_root = tmp / 'www'
        physical = document_root / 'tools/satellite-maneuver-detector'
        (physical / 'app').mkdir(parents=True)
        for name in ('index.html', 'docs.html', 'benchmark.html', 'accessibility.html',
                     'history.php', 'dependency-notices.txt', 'benchmark-template.json', 'public-evidence-manifest-v0.1.json',
                     'app-3.4.js', 'plotly-3.3.1.min.js', 'satellite-6.0.2.min.js'):
            (physical / name).write_bytes(PUBLIC_MARKER)
        (physical / ASSET.lstrip('/')).write_bytes(PUBLIC_MARKER)
        (physical / 'repository-only-probe.txt').write_bytes(PRIVATE_MARKER)
        (physical / 'app/common.js').write_bytes(PRIVATE_MARKER)
        (physical / '.space-track-config.php').write_bytes(PRIVATE_MARKER)
        (document_root / 'about.html').write_bytes(b'unrelated-site-probe')
        (document_root / 'satellite-maneuver-detector-other.txt').write_bytes(b'unrelated-site-probe')
        unrelated = '\n<IfModule mod_rewrite.c>\nRewriteEngine On\nRewriteRule ^about$ about.html [L]\n</IfModule>\n'
        (document_root / '.htaccess').write_text(template + unrelated)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        lines = modules + [
            'ServerRoot "' + folder + '"',
            'DefaultRuntimeDir "' + folder + '"',
            'PidFile "' + str(tmp / 'httpd.pid') + '"',
            'Listen 127.0.0.1:' + str(port),
            'ServerName localhost',
            'ErrorLog "' + str(tmp / 'error.log') + '"',
            'LogLevel warn',
            'AllowEncodedSlashes ' + encoded_slashes,
            'DocumentRoot "' + str(document_root) + '"',
            '<Directory "' + str(document_root) + '">',
            'Options FollowSymLinks', 'AllowOverride All', 'Require all granted', '</Directory>',
        ]
        if os.geteuid() == 0:
            account = pwd.getpwnam('nobody')
            lines += ['User ' + account.pw_name, 'Group ' + grp.getgrgid(account.pw_gid).gr_name]
        config = tmp / 'httpd.conf'
        config.write_text('\n'.join(lines) + '\n')
        validation = subprocess.run([str(executable), '-t', '-f', str(config)],
                                    capture_output=True, text=True, timeout=5)
        if validation.returncode:
            raise RuntimeError('Invalid test Apache configuration: ' + validation.stderr)
        with (tmp / 'process.log').open('wb') as output:
            process = subprocess.Popen([str(executable), '-X', '-f', str(config)],
                                       stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            group = process.pid
            try:
                if group == os.getpgrp() or os.getpgid(process.pid) != group:
                    raise RuntimeError('Apache must run in its own process session.')
                ready = False
                for _ in range(60):
                    if process.poll() is not None:
                        break
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                            ready = True
                            break
                    except OSError:
                        time.sleep(0.05)
                if not ready:
                    diagnostics = (tmp / 'process.log').read_text()
                    if (tmp / 'error.log').exists():
                        diagnostics += (tmp / 'error.log').read_text()
                    raise RuntimeError('Apache failed to start: ' + diagnostics)
                yield port, physical
            finally:
                if process.poll() is None:
                    if group == os.getpgrp() or os.getpgid(process.pid) != group:
                        raise RuntimeError('Refusing to signal an unowned process group.')
                    os.killpg(group, signal.SIGTERM)
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(group, signal.SIGKILL)
                        process.wait(timeout=3)


def request(port, path):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    try:
        connection.request('GET', path)
        response = connection.getresponse()
        return response.status, dict((k.lower(), v) for k, v in response.getheaders()), response.read()
    finally:
        connection.close()


class ApacheRouteBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / 'deployment/site-root.htaccess').read_text()
        cls.server = server(cls.template)
        cls.port, cls.physical = cls.server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.server.__exit__(None, None, None)

    def assert_denied(self, path, port=None):
        status, _headers, body = request(port or self.port, path)
        self.assertIn(status, (400, 403, 404), path)
        self.assertNotIn(PRIVATE_MARKER, body, path)
        self.assertNotIn(PUBLIC_MARKER, body, path)

    def test_literal_public_routes_keep_headers_and_encoded_query_values(self):
        for path in ('/', '/docs', '/benchmark', '/accessibility', '/history', '/dependency-notices.txt',
                     '/benchmark/manifest', '/benchmark/template', '/app-3.4.js',
                     '/plotly-3.3.1.min.js', '/satellite-6.0.2.min.js', ASSET):
            for query in ('', '?value=%2ftools%2fsatellite-maneuver-detector%20%3f&x=%73',
                          '?value=%20/tools/satellite-maneuver-detector/private',
                          '?value=%09/tools/%73atellite-maneuver-detector/private',
                          '?value=%20%2Ftools%2Fsatellite-maneuver-detector/private'):
                with self.subTest(path=path, query=query):
                    status, headers, body = request(self.port, PUBLIC + path + query)
                    self.assertEqual(status, 200)
                    self.assertEqual(body, PUBLIC_MARKER)
                    for name in ('content-security-policy', 'x-content-type-options',
                                 'referrer-policy', 'x-frame-options', 'permissions-policy',
                                 'strict-transport-security'):
                        self.assertIn(name, headers)

    def test_physical_and_encoded_physical_paths_are_private(self):
        for prefix in (PHYSICAL, '/tools/%73atellite-maneuver-detector',
                       '/%74ools/satellite-maneuver-detector', '/%74ools/%73atellite-maneuver-detector',
                       '/tools//satellite-maneuver-detector', '//tools/satellite-maneuver-detector',
                       '/unused/../tools/satellite-maneuver-detector',
                       PUBLIC + '/../tools/satellite-maneuver-detector'):
            for suffix in ('/repository-only-probe.txt', '/index.html', ASSET):
                with self.subTest(prefix=prefix, suffix=suffix):
                    self.assert_denied(prefix + suffix)
        self.assert_denied(PHYSICAL + '/.space-track-config.php')

    def test_encoded_or_normalised_public_aliases_are_rejected(self):
        for path in ('/%73atellite-maneuver-detector', PUBLIC + '/%64ocs',
                     '/%2e/satellite-maneuver-detector', PUBLIC + '/docs/..',
                     PUBLIC + '/%2e/docs', PUBLIC + '//docs',
                     PUBLIC + '/app/common-012345abcdef%2ejs',
                     '/%73atellite-maneuver-detector' + ASSET):
            with self.subTest(path=path):
                self.assert_denied(path)

    def test_unknown_and_canonical_source_files_remain_unavailable(self):
        for path in ('/repository-only-probe.txt', '/app/common.js',
                     '/app/common-000000000000.js', '/app/unknown-012345abcdef.js',
                     '/app/../repository-only-probe.txt', '/app/%2e%2e/repository-only-probe.txt'):
            with self.subTest(path=path):
                self.assert_denied(PUBLIC + path)

    def test_symlink_assets_remain_unavailable(self):
        link = self.physical / 'app/common-abcdef012345.js'
        link.symlink_to(self.physical / 'repository-only-probe.txt')
        try:
            self.assert_denied(PUBLIC + '/app/common-abcdef012345.js')
        finally:
            link.unlink()
        directory = self.physical / 'app'
        saved = self.physical / 'saved-assets'
        directory.rename(saved)
        directory.symlink_to(saved, target_is_directory=True)
        try:
            self.assert_denied(PUBLIC + ASSET)
        finally:
            directory.unlink()
            saved.rename(directory)

    def test_unrelated_routes_preserve_site_behaviour(self):
        for path in ('/about', '/a%62out', '/about?value=%2ftools%2f',
                     '/satellite-maneuver-detector-other.txt'):
            with self.subTest(path=path):
                status, headers, body = request(self.port, path)
                self.assertEqual(status, 200)
                self.assertEqual(body, b'unrelated-site-probe')
                self.assertNotIn('content-security-policy', headers)
                self.assertNotIn('strict-transport-security', headers)

    def test_canonical_redirects_remain_usable(self):
        for path in ('', '//', '/docs/', '/benchmark/', '/accessibility/', '.html', '/docs.html'):
            with self.subTest(path=path):
                status, headers, _body = request(self.port, PUBLIC + path)
                self.assertEqual(status, 301)
                self.assertTrue(headers['location'].startswith('https://www.sylvesterkaczmarek.com' + PUBLIC))

    def test_legacy_pages_redirect_once_to_exact_canonical_and_keep_query(self):
        for page in ('', '/docs', '/benchmark', '/accessibility'):
            for ending in ('', '/', '.html'):
                path = LEGACY + page + ending
                for query in ('', '?norad=25544&from=2026-01-01', '?return=%2Fdocs&value=%73'):
                    with self.subTest(path=path, query=query):
                        status, headers, _body = request(self.port, path + query)
                        self.assertEqual(status, 301)
                        self.assertEqual(headers['location'],
                                         'https://www.sylvesterkaczmarek.com' + PUBLIC + (page or '/') + query)

    def test_legacy_machine_routes_remain_direct_and_noindex(self):
        for path in ('/history', '/history/', '/benchmark/manifest', '/benchmark/template',
                     '/app-3.4.js', '/plotly-3.3.1.min.js', '/satellite-6.0.2.min.js', ASSET):
            with self.subTest(path=path):
                status, headers, body = request(self.port, LEGACY + path + '?old=1%2F2')
                self.assertEqual((status, body), (200, PUBLIC_MARKER))
                self.assertNotIn('location', headers)
                self.assertIn('noindex', headers['x-robots-tag'])

    def test_missing_hash_cannot_poison_a_future_asset_cache(self):
        for prefix in (PUBLIC, LEGACY):
            for path in ('/app/common-000000000000.js', '/app/unknown-012345abcdef.js'):
                status, headers, _body = request(self.port, prefix + path)
                self.assertIn(status, (403, 404))
                self.assertEqual(headers.get('cache-control'), 'no-store')
            status, headers, _body = request(self.port, prefix + ASSET)
            self.assertEqual(status, 200)
            self.assertEqual(headers.get('cache-control'), 'public, max-age=31536000, immutable')

    def test_nested_legacy_rules_cannot_rewrite_allowlisted_targets(self):
        nested = self.physical / '.htaccess'
        nested.write_text('RewriteEngine On\nRewriteRule ^ - [F,L]\n')
        try:
            for prefix, path in ((PUBLIC, '/'), (PUBLIC, '/history'), (LEGACY, ASSET)):
                status, _headers, body = request(self.port, prefix + path)
                self.assertEqual((status, body), (200, PUBLIC_MARKER))
        finally:
            nested.unlink()

    def test_encoded_slashes_fail_closed_when_host_accepts_them(self):
        with server(self.template, encoded_slashes='On') as (port, _physical):
            for path in ('/tools%2fsatellite-maneuver-detector/repository-only-probe.txt',
                         '/%74ools%2fsatellite-maneuver-detector/repository-only-probe.txt',
                         PUBLIC + '%2fdocs', PUBLIC + '/app%2fcommon-012345abcdef.js'):
                with self.subTest(path=path):
                    self.assert_denied(path, port)

    def test_retained_immutable_block_preserves_the_boundary_on_rollback(self):
        begin = '# BEGIN satsift compatibility routes'
        end = '# END satsift compatibility routes'
        block = self.template[self.template.index(begin):self.template.index(end) + len(end)]
        with server(block) as (port, _physical):
            status, headers, body = request(port, PUBLIC + ASSET)
            self.assertEqual((status, body), (200, PUBLIC_MARKER))
            for name in ('content-security-policy', 'x-content-type-options', 'x-robots-tag'):
                self.assertIn(name, headers)
            for path in (PHYSICAL + '/repository-only-probe.txt',
                         '/%74ools/satellite-maneuver-detector/repository-only-probe.txt',
                         '/%73atellite-maneuver-detector' + ASSET):
                self.assert_denied(path, port)


if __name__ == '__main__':
    unittest.main()
