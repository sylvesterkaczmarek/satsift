#!/usr/bin/env python3
from pathlib import Path
import re

text = Path('deployment/site-root.htaccess').read_text(encoding='utf-8')
begin = '# BEGIN satellite-maneuver-detector immutable browser assets'
end = '# END satellite-maneuver-detector immutable browser assets'
main_begin = '# BEGIN satellite-maneuver-detector managed configuration'
if text.count(begin) != 1 or text.count(end) != 1 or not text.index(begin) < text.index(end) < text.index(main_begin):
    raise SystemExit('Immutable browser routing must be a separate complete block before main rules.')
full_text = text
start, finish = text.index(begin), text.index(end) + len(end)
immutable_text = text[start:finish]
text = text[:start] + text[finish:]

scope_token = r'%{THE_REQUEST} =~ m#\s/+satellite-maneuver-detector(?:[/?\s]|$)#'

required_headers = {
    'X-Content-Type-Options': '"nosniff"',
    'Referrer-Policy': '"strict-origin-when-cross-origin"',
    'X-Frame-Options': '"DENY"',
    'Permissions-Policy': '"camera=(), microphone=(), geolocation=(), payment=(), usb=()"',
    'Content-Security-Policy': '"default-src \'self\';',
}

for header, value_prefix in required_headers.items():
    lines = [line.strip() for line in text.splitlines() if line.lstrip().startswith('Header') and f' {header} ' in line]
    if len(lines) != 1:
        raise SystemExit(f'Expected exactly one {header} directive, found {len(lines)}.')
    line = lines[0]
    if value_prefix not in line:
        raise SystemExit(f'{header} value changed unexpectedly.')
    if scope_token not in line:
        raise SystemExit(f'{header} is not expression-scoped to the full detector namespace.')
    if 'env=SMD_ROUTE' in line:
        raise SystemExit(f'{header} must not depend on an environment variable lost across internal rewrites.')

hsts_lines = [line.strip() for line in text.splitlines() if line.lstrip().startswith('Header') and 'Strict-Transport-Security' in line]
if len(hsts_lines) != 1:
    raise SystemExit(f'Expected exactly one HSTS directive, found {len(hsts_lines)}.')
hsts = hsts_lines[0]
for token in ('max-age=31536000', scope_token):
    if token not in hsts:
        raise SystemExit(f'HSTS directive is missing required detector scoping token: {token}')
for unsafe_origin_signal in ("%{HTTPS}", 'X-Forwarded-Proto', 'Forwarded'):
    if unsafe_origin_signal.lower() in hsts.lower():
        raise SystemExit(
            f'HSTS must not depend on unreliable or client-supplied StackCP origin signal: {unsafe_origin_signal}'
        )
if re.search(r'includeSubDomains|preload', hsts, re.IGNORECASE):
    raise SystemExit('HSTS must not opt into includeSubDomains or preload from this detector-specific deployment template.')

required_routes = [
    r'^satellite-maneuver-detector/history/?$',
    r'^satellite-maneuver-detector/docs/?$',
    r'^satellite-maneuver-detector/benchmark/manifest/?$',
    r'^satellite-maneuver-detector/benchmark/template/?$',
    r'^satellite-maneuver-detector/benchmark/?$',
    r'^satellite-maneuver-detector/accessibility/?$',
    r'^satellite-maneuver-detector/app-3\.4\.js$',
    r'^satellite-maneuver-detector/plotly-3\.3\.1\.min\.js$',
    r'^satellite-maneuver-detector/satellite-6\.0\.2\.min\.js$',
    r'^satellite-maneuver-detector/?$',
]
for route in required_routes:
    if route not in text:
        raise SystemExit(f'Missing intended public detector route: {route}')

route_patterns = re.findall(r'^\s*RewriteRule\s+(\^satellite-maneuver-detector[^\s]*)\s+', full_text, re.MULTILINE)
if not route_patterns:
    raise SystemExit('No detector RewriteRule routes found.')
for route in route_patterns:
    if not route.startswith('^satellite-maneuver-detector'):
        raise SystemExit(f'Unexpected detector route outside header namespace: {route}')

physical_condition = r'RewriteCond expr "unescape(%{THE_REQUEST}) =~ m#^\S+\s/+tools/satellite-maneuver-detector(?:/|[?\s])#i"'
physical_rule = 'RewriteRule ^ - [F,L]'
physical_condition_pos = text.find(physical_condition)
physical_block_pos = text.find(physical_rule)
first_public_pos = text.find('RewriteRule ^satellite-maneuver-detector/history/?$')
if (
    text.count(physical_condition) != 1
    or text.count(physical_rule) != 1
    or physical_condition_pos < 0
    or physical_block_pos < physical_condition_pos
    or first_public_pos < physical_block_pos
):
    raise SystemExit('Physical detector namespace block must precede public allowlisted rewrites.')
between = text[physical_condition_pos + len(physical_condition):physical_block_pos]
if any(line.strip() and not line.lstrip().startswith('#') for line in between.splitlines()):
    raise SystemExit('Physical namespace denial must immediately consume its original-request condition.')
if 'RewriteRule ^(?:tools/)?satellite-maneuver-detector(?:/|$|\\.html$) - [F,L,NC]' not in immutable_text:
    raise SystemExit('Rollback routing must preserve the decoded namespace guard.')
if 'RewriteCond %{THE_REQUEST} !' not in immutable_text:
    raise SystemExit('Decoded namespaces must reject noncanonical original request paths.')

module_pattern = r'^satellite-maneuver-detector/app/((?:common|orbital-input|benchmark|packages|detection|interface|bootstrap)-[0-9a-f]{12}\.js)$'
if immutable_text.count('RewriteRule ' + module_pattern + ' ') != 2:
    raise SystemExit('Module routing must use exactly the reviewed filename allowlist.')
for required in (
    'RewriteCond %{DOCUMENT_ROOT}/tools/satellite-maneuver-detector/app -l [OR]',
    'RewriteCond %{DOCUMENT_ROOT}/tools/satellite-maneuver-detector/app/$1 -l',
    'RewriteCond %{THE_REQUEST} \\s/+satellite-maneuver-detector/app/(?:common|orbital-input|benchmark|packages|detection|interface|bootstrap)-[0-9a-f]{12}\\.js(?:[?\\s]|$)',
    'RewriteCond %{DOCUMENT_ROOT}/tools/satellite-maneuver-detector/app/$1 -f',
    'RewriteRule ^satellite-maneuver-detector/app(?:/|$) - [R=404,L]',
):
    if required not in immutable_text:
        raise SystemExit('Missing module path or symlink boundary: ' + required)
for name in ('common', 'orbital-input', 'benchmark', 'packages', 'detection', 'interface', 'bootstrap'):
    if not re.fullmatch(module_pattern, f'satellite-maneuver-detector/app/{name}-0123456789ab.js'):
        raise SystemExit('Known module identity is unreachable.')
for name in ('common.js', 'private-config.json', '../research/private.py', 'private-0123456789ab.js', 'common-000.js'):
    if re.fullmatch(module_pattern, 'satellite-maneuver-detector/app/' + name):
        raise SystemExit('Unrecognised or private module path entered the public allowlist.')


asset_scope = r'%{THE_REQUEST} =~ m#\s/+satellite-maneuver-detector/app/(?:common|orbital-input|benchmark|packages|detection|interface|bootstrap)-[0-9a-f]{12}\.js(?:[?\s]|$)#'
immutable_headers = {
    'X-Content-Type-Options': '"nosniff"',
    'Content-Security-Policy': '"default-src \'self\';',
    'X-Robots-Tag': '"noindex, nofollow, nosnippet"',
}
lines = [line.strip() for line in immutable_text.splitlines() if line.lstrip().startswith('Header')]
if len(lines) != len(immutable_headers):
    raise SystemExit('Unexpected headers in immutable rollback routing block.')
for header, prefix in immutable_headers.items():
    matches = [line for line in lines if f' {header} ' in line]
    if len(matches) != 1 or prefix not in matches[0] or asset_scope not in matches[0]:
        raise SystemExit('Immutable rollback header is missing or incorrectly scoped: ' + header)
    if header == 'Content-Security-Policy':
        main_policy = next(line.strip() for line in text.splitlines() if 'Header always set Content-Security-Policy ' in line)
        if matches[0].split('"')[1] != main_policy.split('"')[1]:
            raise SystemExit('Immutable rollback assets must retain the same CSP as the current detector.')


print(f'Security-header policy passed for {len(route_patterns)} detector rewrite rules; expression scoping survives internal rewrites and StackCP TLS termination.')
