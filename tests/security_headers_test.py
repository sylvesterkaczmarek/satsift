#!/usr/bin/env python3
"""Check scoped security policy and the retained compatibility route boundary."""
from pathlib import Path
import re

text = Path('deployment/site-root.htaccess').read_text(encoding='utf-8')
begin = '# BEGIN satsift compatibility routes'
end = '# END satsift compatibility routes'
main_begin = '# BEGIN satsift managed configuration'
if text.count(begin) != 1 or text.count(end) != 1 or not text.index(begin) < text.index(end) < text.index(main_begin):
    raise SystemExit('Compatibility routing must be a complete block before main rules.')
retained = text[text.index(begin):text.index(end) + len(end)]
scope = r'%{THE_REQUEST} =~ m#\s/+(?:satsift|satellite-maneuver-detector)(?:[./?\s]|$)#'
headers = {
    'X-Content-Type-Options': '"nosniff"',
    'Referrer-Policy': '"strict-origin-when-cross-origin"',
    'X-Frame-Options': '"DENY"',
    'Permissions-Policy': '"camera=(), microphone=(), geolocation=(), payment=(), usb=()"',
    'Content-Security-Policy': '"default-src \'self\';',
    'Strict-Transport-Security': '"max-age=31536000"',
}
for header, value in headers.items():
    lines = [line.strip() for line in text.splitlines()
             if line.lstrip().startswith('Header') and f' {header} ' in line]
    if len(lines) != 1 or value not in lines[0] or scope not in lines[0]:
        raise SystemExit('Missing or incorrectly scoped security header: ' + header)
    if lines[0] not in retained or 'env=SMD_ROUTE' in lines[0]:
        raise SystemExit('Rollback must retain original-request-scoped security headers.')
    if header == 'Strict-Transport-Security':
        for forbidden in ('%{HTTPS}', 'X-Forwarded-Proto', 'Forwarded', 'includeSubDomains', 'preload'):
            if forbidden.lower() in lines[0].lower():
                raise SystemExit('HSTS depends on an unsafe transport signal or scope.')
    if header == 'Content-Security-Policy':
        for required in ("script-src 'self'", "object-src 'none'", "base-uri 'self'",
                         "form-action 'self'", "frame-ancestors 'none'",
                         "connect-src 'self' https://celestrak.org"):
            if required not in lines[0]:
                raise SystemExit('CSP lost a required boundary: ' + required)
        if "script-src 'self' 'unsafe" in lines[0]:
            raise SystemExit('Inline or evaluated script was allowed.')

physical_condition = r'RewriteCond expr "unescape(%{THE_REQUEST}) =~ m#^\S+\s/+tools/satellite-maneuver-detector(?:/|[?\s])#i"'
if physical_condition + '\n  RewriteRule ^ - [F,L]' not in retained:
    raise SystemExit('Physical namespace denial must immediately consume its raw-request condition.')
guard = r'RewriteRule ^(?:satsift|(?:tools/)?satellite-maneuver-detector)(?:/|$|\.html$) - [F,L,NC]'
if guard not in retained or 'RewriteCond %{THE_REQUEST} !' not in retained:
    raise SystemExit('Decoded namespaces must reject noncanonical original request paths.')

module = r'^(?:satsift|satellite-maneuver-detector)/app/((?:common|orbital-input|benchmark|packages|detection|interface|bootstrap)-[0-9a-f]{12}\.js)$'
if retained.count('RewriteRule ' + module + ' ') != 2:
    raise SystemExit('Module routing must use exactly the reviewed filename allowlist.')
for required in (
    'RewriteCond %{DOCUMENT_ROOT}/tools/satellite-maneuver-detector/app -l [OR]',
    'RewriteCond %{DOCUMENT_ROOT}/tools/satellite-maneuver-detector/app/$1 -l',
    'RewriteCond %{DOCUMENT_ROOT}/tools/satellite-maneuver-detector/app/$1 -f',
    'RewriteRule ^(?:satsift|satellite-maneuver-detector)/app(?:/|$) - [R=404,L]',
):
    if required not in retained:
        raise SystemExit('Missing module path or symlink boundary: ' + required)
for prefix in ('satsift', 'satellite-maneuver-detector'):
    for name in ('common', 'orbital-input', 'benchmark', 'packages', 'detection', 'interface', 'bootstrap'):
        if not re.fullmatch(module, f'{prefix}/app/{name}-0123456789ab.js'):
            raise SystemExit('Known module identity is unreachable.')
    for name in ('common.js', 'private-config.json', '../research/private.py', 'private-0123456789ab.js', 'common-000.js'):
        if re.fullmatch(module, prefix + '/app/' + name):
            raise SystemExit('Unrecognised or private module path entered the public allowlist.')

for endpoint in ('history', 'benchmark/manifest', 'benchmark/template'):
    route = 'RewriteRule ^(?:satsift|satellite-maneuver-detector)/' + endpoint + '/?$'
    matching = [line for line in retained.splitlines() if route in line]
    if len(matching) != 1 or '[END]' not in matching[0]:
        raise SystemExit('Machine routes must be direct terminal rewrites in both namespaces.')
if 'Header always set X-Robots-Tag "noindex, nofollow, nosnippet"' not in retained:
    raise SystemExit('Machine resources must retain their noindex policy on rollback.')
for marker in ('dependency-notices\\.txt', 'max-age=31536000, immutable', 'Header always set Cache-Control "no-cache"'):
    if marker not in retained:
        raise SystemExit('Missing distribution or cache policy: ' + marker)
print('Scoped security, canonical routing and retained compatibility policy passed.')
