#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.browser_source import read_browser_source
from tools.browser_assets import browser_assets
from tools.update_browser_assets import expected_files
from tools.source_release import verify_directory

REQUIRED = {
    'README.md',
    'LICENSE',
    'NOTICE',
    'RELEASE.md',
    'THIRD-PARTY-NOTICES.md',
    'licenses/THIRD-PARTY-SOURCES.json',
    'review/CLEAN-RELEASE-VERIFICATION.md',
    'tools/source_release.py',
    'tests/source_release_test.py',
    'tests/apache_route_boundary_test.py',
    'RELEASE-NOTES.md',
    'review/COMBINED-VERIFICATION.md',
    'research/ENVIRONMENT.md',
    'research/NEURAL-EXECUTION.md',
    'research/neural_execution.py',
    'tools/run_neural_smoke.py',
    'tests/neural_execution_test.py',
    'tests/neural_smoke_runner_test.py',
    'research/PUBLICATION-EDITION.json',
    'review/PUBLICATION-REVIEW.md',
    'tests/publication_edition_test.py',
    'DEPLOYMENT.md',
    'HISTORY-POLICY.md',
    'SECURITY.md',
    'KNOWN-ISSUES.md',
    'index.html',
    'app-3.4.js',
    'BROWSER-ARCHITECTURE.md',
    '.gitattributes',
    'browser-assets.json',
    'app/common.js',
    'app/orbital-input.js',
    'app/benchmark.js',
    'app/packages.js',
    'app/detection.js',
    'app/interface.js',
    'tools/browser_assets.py',
    'tools/update_browser_assets.py',
    'tools/browser_source.py',
    'tools/load_browser_app.js',
    'tests/browser_module_equivalence_test.js',
    'tests/browser_module_loader_test.js',
    'tests/fixtures/browser-equivalence-v1.json',
    'history.php',
    'docs.html',
    'benchmark.html',
    'accessibility.html',
    'benchmark-template.json',
    'public-evidence-manifest-v0.1.json',
    'public-evidence-manifest-v1.0.json',
    'benchmark/benchmark-v1-curation.json',
    'benchmark/PUBLICATION-PROTOCOL-v1.0.md',
    'benchmark-data/public-evidence-benchmark-v1.0.recipe.json',
    'benchmark-results/selective-v1-model-selection.json',
    'benchmark-results/sequential-v1-development.json',
    'benchmark-results/sequential-v1-null-simulations.json',
    'benchmark-results/physics-v1-development.json',
    'benchmark-results/integrity-v1-stress.json',
    'benchmark-results/comparison-v1-development-calibration.json',
    'benchmark-results/confirmatory-v1-final.json',
    'benchmark-results/confirmatory-v1-final.json.sha256',
    'plotly-3.3.1.min.js',
    'satellite-6.0.2.min.js',
    'vendor-integrity.json',
    'licenses/plotly-LICENSE.txt',
    'licenses/satellite-LICENSE.txt',
    'config/.space-track-config.php.example',
    'deployment/site-root.htaccess',
    'review/EXTERNAL-REVIEW-CHECKLIST.md',
    'review/INDEPENDENT-REVIEW-PACKAGE.md',
    'review/QA-READINESS-REPORT.md',
    'review/VALIDATION-STATUS.md',
    'review/WCAG-REVIEW.md',
    'review/COMPARISON-AUDIT.md',
    'review/CONFIRMATORY-AUDIT.md',
    'review/CONFIRMATORY-MATERIALISATION-INCIDENT.md',
    '.github/workflows/ci.yml',
    '.github/workflows/confirmatory-freeze.yml',
    'tests/catalogue_revision_test.js',
    'tests/catalogue_metadata_roundtrip_test.js',
    'tests/catalogue_identifier_test.js',
    'tests/benchmark_tolerance_test.js',
    'tests/fixtures/browser-equivalence-v2.json',
    'tests/fixtures/browser-equivalence-v3.json',
    'tests/fixtures/browser-presentation-v4.json',
    'tests/console_browser_test.js',
    'dependency-notices.txt',
    'tools/build_browser_notices.py',
    'tests/tle_precision_roundtrip_test.js',
    'tests/tle_precision_reference_check.py',
    'tests/materializer_validation_test.py',
    'tests/timezone_epoch_test.js',
    'tests/benchmark_label_semantics_test.js',
    'tests/event_matching_test.py',
    'tests/benchmark_timestamp_test.py',
    'tests/benchmark_timestamp_bridge.js',
    'tests/event_matching_bridge.js',
    'tests/event_matching_version_test.js',
    'research/event_matching.py',
    'research/ELAPSED-EVALUATION.md',
    'research/elapsed_exposure.py',
    'research/elapsed_evaluator.py',
    'tools/evaluate_elapsed_benchmark.py',
    'tests/elapsed_exposure_test.py',
    'tests/elapsed_evaluation_test.py',
    'tests/elapsed_evaluation_version_test.py',
    'research/EVENT-MATCHING.md',
    'tests/export_astrodynamics_fixtures.js',
    'tests/astrodynamics_fixture_check.py',
    'tests/workbench_selftest_harness.js',
    'tests/release_quality_test.js',
    'tests/security_headers_test.py',
    'tests/history_endpoint_smoke.py',
    'tests/history_concurrency_guards.py',
    'tests/history_concurrency_integration.py',
    'tests/history_admission_test.py',
    'tests/history_provenance_test.py',
    'tests/history_provenance_test.js',
    'tests/selective_v1_freeze_test.py',
    'tests/sequential_v1_freeze_test.py',
    'tests/physics_v1_freeze_test.py',
    'tests/integrity_v1_test.py',
    'tests/integrity_v1_freeze_test.py',
    'tests/history_cache_integrity_test.py',
    'tests/comparison_v1_test.py',
    'tests/comparison_v1_freeze_test.py',
    'tests/confirmatory_v1_preflight_test.py',
    'tests/confirmatory_v1_freeze_test.py',
    'tests/integration_disposition_test.py',
    'tests/deployment_tooling_test.py',
    'tests/production_verifier_test.py',
    'tools/build_public_evidence_benchmark.py',
    'tools/materialize_benchmark_v1_spacetrack.py',
    'tools/MATERIALISATION.md',
    'tools/deploy_production.py',
    'tools/verify_production.py',
    'tools/export_selective_v1_features.js',
    'tools/export_integrity_v1_features.js',
    'tools/export_confirmatory_features.js',
    'tools/finalize_confirmatory.py',
    'tools/confirmatory_post_result_audit.py',
    'research/selective_v1/__init__.py',
    'research/selective_v1/core.py',
    'research/selective_v1/models.py',
    'research/selective_v1/detector.py',
    'research/selective_v1/train_compare.py',
    'research/selective_v1/test_selective_v1.py',
    'research/selective_v1/README.md',
    'research/selective_v1/METHOD-v1.0.md',
    'research/selective_v1/MODEL-SELECTION-v1.0.md',
    'research/selective_v1/ABLATIONS-v1.0.md',
    'research/sequential_v1/__init__.py',
    'research/sequential_v1/formal.py',
    'research/sequential_v1/operational.py',
    'research/sequential_v1/run_development.py',
    'research/sequential_v1/simulate_null.py',
    'research/sequential_v1/test_sequential_v1.py',
    'research/sequential_v1/README.md',
    'research/sequential_v1/METHOD-v1.0.md',
    'research/sequential_v1/RESULTS-v1.0.md',
    'research/physics_v1/__init__.py',
    'research/physics_v1/core.py',
    'research/physics_v1/inverter.py',
    'research/physics_v1/screen.py',
    'research/physics_v1/independent_check.py',
    'research/physics_v1/run_development.py',
    'research/physics_v1/README.md',
    'research/physics_v1/METHOD-v1.0.md',
    'research/physics_v1/RESULTS-v1.0.md',
    'research/integrity_v1/__init__.py',
    'research/integrity_v1/gate.py',
    'research/integrity_v1/stressors.py',
    'research/integrity_v1/run_stress.py',
    'research/integrity_v1/README.md',
    'research/integrity_v1/METHOD-v1.0.md',
    'research/integrity_v1/RESULTS-v1.0.md',
    'research/comparison_v1/__init__.py',
    'research/comparison_v1/run_comparison.py',
    'research/comparison_v1/README.md',
    'research/comparison_v1/METHOD-v1.0.md',
    'research/comparison_v1/RESULTS-v1.0.md',
    'research/confirmatory_v1/__init__.py',
    'research/confirmatory_v1/run_confirmatory.py',
    'research/confirmatory_v1/PRECONFIRMATORY-FREEZE.json',
    'research/confirmatory_v1/GATE-v1.0.md',
    'research/confirmatory_v1/RESULTS-v1.0.md',
    'research/confirmatory_v1/RUN-LOCK-v1.0.json',
    'research/confirmatory_v1/DATA-PROVENANCE-v1.0.json',
    'research/confirmatory_v1/AUDIT-VERIFICATION-v1.0.json',
    'research/confirmatory_v1/INTEGRATION-DISPOSITION.md',
}

FORBIDDEN_TRACKED = {
    '.space-track-config.php',
    '.satellite-vendor-install.lock',
    'vendor.php',
    'install-vendors.php',
    '.github/workflows/patch-utc.yml',
    '.github/workflows/fix-epoch-record-fields.yml',
    '.github/workflows/apply-release-blocker-fixes.yml',
    '.github/workflows/benchmark-v1-devcal-probe.yml',
    '.github/workflows/selective-v1-model-selection.yml',
    '.github/workflows/selective-v1-final-support-patch.yml',
    '.github/workflows/sequential-v1-experiment.yml',
    '.github/workflows/sequential-v1-freeze-artifacts.yml',
    '.github/workflows/physics-v1-probe.yml',
    '.github/workflows/physics-v1-experiment.yml',
    '.github/workflows/physics-v1-import-patch.yml',
    '.github/workflows/physics-v1-freeze.yml',
    '.github/workflows/physics-v1-fix.yml',
    '.github/workflows/integrity-cache-hardening.yml',
    '.github/workflows/integrity-v1-experiment.yml',
    '.github/workflows/integrity-v1-freeze.yml',
    '.github/workflows/integrity-repo-guard.yml',
    '.github/workflows/confirmatory-confirmatory-once.yml',
    '.github/workflows/confirmatory-confirmatory-recovery.yml',
    '.github/workflows/confirmatory-confirmatory-recovery-v2.yml',
    '.github/workflows/confirmatory-authorized-loader-fix.yml',
    '.github/workflows/confirmatory-loader-fix-run.yml',
    '.github/workflows/confirmatory-post-audit-run.yml',
    '.github/workflows/confirmatory-post-audit-run-v2.yml',
    '.github/workflows/integration-negative-disposition.yml',
    '.github/workflows/final-repo-audit-fixes.yml',
    '.github/workflows/final-readme-status.yml',
    '.github/workflows/final-content-audit.yml',
    'tools/patch_integrity_cache.py',
    'tools/patch_integrity_repo_checks.py',
    'tools/apply_release_blocker_patch.py',
    'tools/confirmatory_fix_authorized_loader.py',
}

HTML_FILES = ['index.html', 'docs.html', 'benchmark.html', 'accessibility.html']
JSON_FILES = [
    'tests/fixtures/browser-equivalence-v3.json',
    'tests/fixtures/browser-equivalence-v2.json',
    'browser-assets.json',
    'tests/fixtures/browser-equivalence-v1.json',
    'benchmark-template.json',
    'public-evidence-manifest-v0.1.json',
    'public-evidence-manifest-v1.0.json',
    'benchmark/benchmark-v1-curation.json',
    'benchmark-data/public-evidence-benchmark-v1.0.recipe.json',
    'benchmark-results/selective-v1-model-selection.json',
    'benchmark-results/sequential-v1-development.json',
    'benchmark-results/sequential-v1-null-simulations.json',
    'benchmark-results/physics-v1-development.json',
    'benchmark-results/integrity-v1-stress.json',
    'benchmark-results/comparison-v1-development-calibration.json',
    'benchmark-results/confirmatory-v1-final.json',
    'research/confirmatory_v1/PRECONFIRMATORY-FREEZE.json',
    'research/confirmatory_v1/RUN-LOCK-v1.0.json',
    'research/confirmatory_v1/DATA-PROVENANCE-v1.0.json',
    'research/confirmatory_v1/AUDIT-VERIFICATION-v1.0.json',
    'vendor-integrity.json',
]


class IdAndRefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.refs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        for attr in ('src', 'href'):
            value = attrs.get(attr)
            if value:
                self.refs.append((attr, value))


def tracked_files() -> set[str]:
    if not (ROOT / '.git').exists():
        try:
            manifest = verify_directory(ROOT, exact=False)
        except (ValueError, OSError) as exc:
            fail('source snapshot inventory failed verification: ' + str(exc))
        return {item['path'] for item in manifest['files']}
    top = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=ROOT, text=True).strip()
    if Path(top).resolve() != ROOT.resolve():
        fail('repository checks require the project root')
    raw = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT)
    return {item.decode() for item in raw.split(b'\0') if item}


def fail(message: str) -> None:
    print(f'ERROR: {message}', file=sys.stderr)
    raise SystemExit(1)


def check_required(files: set[str]) -> None:
    missing = sorted(REQUIRED - files)
    if missing:
        fail('missing required files: ' + ', '.join(missing))
    forbidden = sorted(FORBIDDEN_TRACKED & files)
    if forbidden:
        fail('forbidden obsolete/private/temporary files are tracked: ' + ', '.join(forbidden))


def check_secrets(files: set[str]) -> None:
    for path in files:
        name = Path(path).name
        if name == '.space-track-config.php':
            fail(f'private credential file is tracked: {path}')
        if path.startswith('.satellite-maneuver-cache/') or '/.satellite-maneuver-cache/' in path:
            fail(f'cache data is tracked: {path}')
        if path.endswith(('.log', '.cache', '.bak', '.tmp')):
            fail(f'generated runtime file is tracked: {path}')

    example = (ROOT / 'config/.space-track-config.php.example').read_text()
    if 'YOUR_SPACE_TRACK_EMAIL' not in example or 'YOUR_SPACE_TRACK_PASSWORD' not in example:
        fail('Space-Track example must contain placeholders, never real credentials')
    if "__DIR__ . '/.satellite-maneuver-cache'" not in example:
        fail('Space-Track example cache_dir must resolve beside the private config file')


def check_json() -> None:
    for rel in JSON_FILES:
        try:
            json.loads((ROOT / rel).read_text())
        except Exception as exc:
            fail(f'{rel} is invalid JSON: {exc}')


def check_html(files: set[str]) -> None:
    asset_sources = {asset['url']: asset['source'] for asset in browser_assets(ROOT)}
    for rel in HTML_FILES:
        parser = IdAndRefParser()
        parser.feed((ROOT / rel).read_text())
        duplicates = sorted({value for value in parser.ids if parser.ids.count(value) > 1})
        if duplicates:
            fail(f'{rel} contains duplicate IDs: {duplicates}')

        for _attr, ref in parser.refs:
            if ref.startswith(('http://', 'https://', 'mailto:', '#', 'data:', 'javascript:')):
                continue
            clean = ref.split('?', 1)[0].split('#', 1)[0]
            if not clean:
                continue
            if clean in asset_sources:
                if asset_sources[clean] not in files:
                    fail(f'{rel} references an untracked browser module {ref!r}')
                continue
            if clean.startswith('/satsift/'):
                candidate = clean.removeprefix('/satsift/')
                if '/' in candidate and not Path(candidate).suffix:
                    continue
                if candidate and Path(candidate).suffix and candidate not in files:
                    fail(f'{rel} references missing local asset {ref!r}')
            elif clean.startswith('/'):
                continue
            elif Path(clean).suffix and clean not in files:
                fail(f'{rel} references missing relative asset {ref!r}')


def check_versions() -> None:
    index = (ROOT / 'index.html').read_text()
    app = read_browser_source(ROOT)
    satellite_version = hashlib.sha256((ROOT / 'satellite-6.0.2.min.js').read_bytes()).hexdigest()[:12]
    if 'SatSift 3.5.0' not in index or "WORKBENCH_VERSION = '3.5.0'" not in app:
        fail('Workbench version is inconsistent between index.html and browser modules')
    if 'Detector method 0.4' not in index or "METHOD_VERSION = 'v0.4'" not in app:
        fail('Detector method version is inconsistent')
    for relative, expected in expected_files(ROOT).items():
        if (ROOT / relative).read_text() != expected:
            fail(f'{relative} contains stale browser asset references or integrity values')
    positions = []
    for asset in browser_assets(ROOT):
        tag = f'<script defer src="{asset["url"]}" integrity="{asset["integrity"]}" crossorigin="anonymous"></script>'
        if index.count(tag) != 1:
            fail(f'index.html must load exactly one declared script for {asset["source"]}')
        positions.append(index.index(tag))
    if positions != sorted(positions):
        fail('index.html browser script order differs from the declared source inventory')
    if f'/satsift/satellite-6.0.2.min.js?v={satellite_version}' not in index:
        fail('index.html does not load the content-versioned satellite.js script')


def check_routing() -> None:
    htaccess = (ROOT / 'deployment/site-root.htaccess').read_text()
    broad_fragments = [
        'RewriteRule ^satsift/(.+)$', 'RewriteRule ^satsift/(.*)$',
        'RewriteRule ^satellite-maneuver-detector/(.+)$',
        'RewriteRule ^satellite-maneuver-detector/(.*)$',
    ]
    for fragment in broad_fragments:
        if fragment in htaccess:
            fail('deployment routing contains a broad application catch-all rule')
    shared = r'^(?:satsift|satellite-maneuver-detector)/'
    required_routes = [
        shared + r'history/?$', shared + r'benchmark/manifest/?$',
        shared + r'benchmark/template/?$', shared + r'app-3\.4\.js$',
        shared + r'plotly-3\.3\.1\.min\.js$', shared + r'satellite-6\.0\.2\.min\.js$',
        shared + r'dependency-notices\.txt$',
        '^satsift/$', '^satsift/docs$', '^satsift/benchmark$', '^satsift/accessibility$',
        r'^satellite-maneuver-detector(?:\.html|/*)$ https://www.sylvesterkaczmarek.com/satsift/',
    ]
    for route in required_routes:
        if route not in htaccess:
            fail(f'deployment routing is missing {route}')

    required_headers = [
        'Content-Security-Policy',
        'X-Content-Type-Options',
        'Referrer-Policy',
        'X-Frame-Options',
        'Permissions-Policy',
        'Strict-Transport-Security',
    ]
    for header in required_headers:
        if header not in htaccess:
            fail(f'deployment routing is missing detector security header {header}')
    hsts_directives = [line for line in htaccess.splitlines() if line.lstrip().startswith('Header') and 'Strict-Transport-Security' in line]
    if len(hsts_directives) != 1:
        fail('deployment routing must contain exactly one HSTS directive')
    hsts_directive = hsts_directives[0]
    if r'%{THE_REQUEST} =~ m#\s/+(?:satsift|satellite-maneuver-detector)(?:[./?\s]|$)#' not in hsts_directive:
        fail('HSTS must remain scoped to the detector namespace')
    if any(signal.lower() in hsts_directive.lower() for signal in ('%{HTTPS}', 'X-Forwarded-Proto', 'Forwarded')):
        fail('HSTS must not depend on unreliable or client-supplied StackCP origin TLS signals')
    if 'includeSubDomains' in hsts_directive or 'preload' in hsts_directive:
        fail('detector-specific HSTS policy must not opt into includeSubDomains or preload')


def function_slice(text: str, start_marker: str, end_marker: str) -> str:
    try:
        start = text.index(start_marker)
        end = text.index(end_marker, start)
    except ValueError as exc:
        fail(f'could not locate JavaScript function boundary: {exc}')
    return text[start:end]


def check_scientific_guardrails() -> None:
    app = read_browser_source(ROOT)
    if 'new Date(record.EPOCH)' in app:
        fail('OMM epochs are still parsed as local time when timezone information is absent')

    required = [
        'parseOmmEpochUtc',
        'parseTleEpoch',
        'formatEpochUs',
        'propagateRecordAtEpoch',
        'hasSgp4Support',
        'SMD_TLE',
        "const PACKAGE_SCHEMA_VERSION = 1;",
        "const TLE_SOURCE_SCHEMA_VERSION = 1;",
        "const RUN_IDENTITY_VERSION = 2;",
        "const PROPAGATION_CONTRACT = 'sgp4-exact-epoch-v1';",
        'epochUs',
        'recordEpochUs',
        'compareRecordEpochs',
        'resolveCatalogueRevisions',
        'creationRaw',
        'gpId',
        'superseded_catalogue_revisions',
        'normaliseBenchmarkLabelStatus',
        'negativeLabelObjectMonths > 0',
        'DEMO_ANCHOR_MS',
        "exampleTles('radial')",
        "exampleTles('cross')",
        "exampleTles('finite')",
    ]
    for marker in required:
        if marker not in app:
            fail(f'scientific guardrail marker missing: {marker}')

    tle_epoch = function_slice(app, 'function parseTleEpoch', 'function formatEpochUs')
    tle = function_slice(app, 'function parseTlePair', 'function parseTleInput')
    omm = function_slice(app, 'function parseOmmRecord', 'function parseOmmInput')
    examples = function_slice(app, 'function exampleDates', 'function parseTleEpoch')

    if 'fractionUnits * 864' not in tle_epoch or 'Math.floor(epochUs / 1000)' not in tle_epoch:
        fail('TLE epochs must retain exact fractional-day microseconds before constructing display dates')
    if 'epochUs: epochInfo.epochUs' not in tle or 'epochRaw: epochInfo.raw' not in tle:
        fail('TLE parser must preserve its exact fractional-day epoch metadata')
    if 'epochUs: epoch.getTime() * 1000' in tle or 'epochRaw: epoch.toISOString()' in tle:
        fail('TLE parser must not reconstruct precise epoch metadata from a millisecond Date')
    if 'epochUs: epochInfo.epochUs' not in omm or 'epochRaw: epochInfo.raw' not in omm:
        fail('OMM parser must preserve parsed high-precision UTC epoch metadata')
    if 'CREATION_DATE' not in omm or 'GP_ID' not in omm or 'elementSetNoKnown' not in omm:
        fail('OMM parser must preserve catalogue supersession metadata')
    if 'const now = new Date()' in examples:
        fail('deterministic astrodynamics fixtures must not depend on wall-clock time')
    if 'DEMO_ANCHOR_MS' not in examples or 'buildDemoStates' not in examples:
        fail('deterministic propagated astrodynamics fixture generation is missing')


def check_benchmark_label_policy() -> None:
    template = json.loads((ROOT / 'benchmark-template.json').read_text())
    cases = template.get('cases', [])
    if not cases or cases[0].get('label_status') not in {'event-evidence', 'confirmed-quiet', 'fully-labelled', 'unknown'}:
        fail('benchmark template must declare explicit label_status semantics')

    manifest = json.loads((ROOT / 'public-evidence-manifest-v0.1.json').read_text())
    manifest_cases = manifest.get('cases', [])
    if not manifest_cases:
        fail('public evidence manifest contains no cases')
    for case in manifest_cases:
        status = case.get('label_status')
        events = case.get('truth_events', [])
        if status == 'unknown' and events:
            fail(f"unknown benchmark case {case.get('case_id')} contains truth events")
        if not events and status != 'unknown':
            fail(f"zero-event public-evidence case {case.get('case_id')} must remain unknown until independently qualified")


def check_vendor_hashes() -> None:
    expected = json.loads((ROOT / 'vendor-integrity.json').read_text())
    required_assets = {'plotly-3.3.1.min.js', 'satellite-6.0.2.min.js'}
    if set(expected) != required_assets:
        fail('vendor-integrity.json must contain exactly the two deployed vendor assets')
    for filename, sha256 in expected.items():
        asset = ROOT / filename
        if not asset.is_file():
            fail(f'hashed vendor asset missing: {filename}')
        actual = hashlib.sha256(asset.read_bytes()).hexdigest()
        if actual != sha256:
            fail(f'vendor hash mismatch for {filename}: {actual} != {sha256}')



def check_component_notices() -> None:
    inventory = json.loads((ROOT / 'licenses/THIRD-PARTY-SOURCES.json').read_text())
    expected = {'assert', 'buffer', 'ieee754', 'maplibre-gl', 'native-promise-only',
                'object-assign', 'polybooljs', 'safe-buffer'}
    if inventory.get('schema') != 'smd-third-party-notice-sources-v1':
        fail('unsupported component-notice inventory')
    entries = inventory.get('notices', [])
    if len(entries) != len(expected) or {entry['component'] for entry in entries} != expected:
        fail('bundled component-notice inventory is incomplete')
    for entry in entries:
        path = entry['notice_path']
        if not path.startswith('licenses/plotly-bundled/') or '..' in Path(path).parts:
            fail('component notice path leaves its inventory directory')
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != entry['notice_sha256']:
            fail('component notice bytes differ from their reviewed source inventory')

    expanded_path = 'licenses/PLOTLY-COMPONENTS.json'
    expanded_bytes = (ROOT / expanded_path).read_bytes()
    reviewed_digest = 'be257d2ba087dd5fa9041f5bc1d212831192e2a215b5598dd3443d39ec6e0f81'
    if hashlib.sha256(expanded_bytes).hexdigest() != reviewed_digest:
        fail('expanded component inventory differs from the reviewed distribution')
    if inventory.get('expanded_inventory') != {'path': expanded_path, 'sha256': reviewed_digest}:
        fail('original and expanded component inventories are not linked')
    expanded = json.loads(expanded_bytes)
    if expanded.get('schema') != 'satsift-bundled-component-notices-v1':
        fail('unsupported expanded component inventory')
    distribution = expanded['distribution']
    if distribution['path'] != 'plotly-3.3.1.min.js' or distribution['version'] != '3.3.1':
        fail('component notices refer to an unexpected browser distribution')
    distributed_bytes = (ROOT / distribution['path']).read_bytes()
    if hashlib.sha256(distributed_bytes).hexdigest() != distribution['sha256']:
        fail('component notices do not identify the distributed browser bytes')

    evidence_ids = {entry['id'] for entry in expanded['evidence']}
    component_ids = set()
    notices = [expanded['source_attributions']['notice']]
    for component in expanded['components']:
        identifier = component['component'] + '@' + component['version']
        if component['id'] != identifier or identifier in component_ids:
            fail('component identity is duplicated or inconsistent')
        component_ids.add(identifier)
        if not component['inclusion'] or any(item['evidence'] not in evidence_ids for item in component['inclusion']):
            fail('component lacks reviewed inclusion evidence')
        if not component['notices'] or not component['reviewed_license']:
            fail('component lacks its licence or retained notices')
        if not component['source_url'].startswith('https://') or not re.fullmatch(r'[0-9a-f]{64}', component['archive_sha256']):
            fail('component archive provenance is incomplete')
        if component['archive_integrity'] is None and not re.fullmatch(r'[0-9a-f]{40}', component.get('source_commit', '')):
            fail('component archive lacks an integrity value or exact Git source commit')
        notices.extend(component['notices'])

    retained_paths = set()
    for notice in notices:
        path = notice['path']
        parts = Path(path).parts
        if not path.startswith('licenses/') or '..' in parts or '\\' in path or str(Path(path)) != path:
            fail('expanded component notice path is not canonical')
        target = ROOT / path
        if target.is_symlink() or not target.is_file():
            fail('expanded component notice is missing or is a link')
        data = target.read_bytes()
        if len(data) != notice['bytes'] or hashlib.sha256(data).hexdigest() != notice['sha256']:
            fail('expanded component notice differs from its reviewed bytes')
        retained_paths.add(path)
    managed_paths = {path.relative_to(ROOT).as_posix() for path in (ROOT / 'licenses/plotly-components').rglob('*') if path.is_file()}
    if managed_paths != {path for path in retained_paths if path.startswith('licenses/plotly-components/')}:
        fail('expanded notice directory has unreviewed or missing files')
    if expanded['coverage']['notice_component_records'] != len(component_ids):
        fail('component coverage count differs from its inventory')
    component_notice_paths = {notice['path'] for component in expanded['components'] for notice in component['notices']}
    if expanded['coverage']['unique_notice_files'] != len(component_notice_paths):
        fail('component notice count differs from its inventory')
    for source in expanded['source_attributions']['source_records']:
        if source['component_id'] not in component_ids:
            fail('source attribution refers to an unreviewed component')
    excluded = expanded['excluded_components']
    if len(excluded) != 1 or excluded[0]['excluded_component'] != 'numeric' or 'numeric@1.2.6' in component_ids:
        fail('unused Numeric dependency exclusion is inconsistent')
    for marker, count in excluded[0]['absence_checks']['plotly_distributed'].items():
        if count != 0 or marker.encode() in distributed_bytes:
            fail('unused Numeric dependency exclusion no longer matches browser bytes')


def check_project_identity() -> None:
    license_bytes = (ROOT / 'LICENSE').read_bytes()
    if hashlib.sha256(license_bytes).hexdigest() != 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30':
        fail('project LICENSE differs from the reviewed official Apache-2.0 text')

    notice = (ROOT / 'NOTICE').read_text()
    if not all(fragment in notice for fragment in ('SatSift', 'Copyright 2026 Sylvester Kaczmarek',
                                                      'Apache License, Version 2.0', 'THIRD-PARTY-NOTICES.md',
                                                      'benchmark/DATA-NOTICE.md')):
        fail('project copyright and upstream notices are incomplete')

    pkg = json.loads((ROOT / 'package.json').read_text())
    lock = json.loads((ROOT / 'package-lock.json').read_text())
    if pkg.get('name') != 'satsift' or pkg.get('version') != '3.5.0' or pkg.get('private') is not True or pkg.get('license') != 'Apache-2.0':
        fail('private SatSift npm package identity or licence is inconsistent')
    if pkg.get('repository') != {'type': 'git', 'url': 'https://github.com/sylvesterkaczmarek/satsift.git'}:
        fail('npm repository points to an unexpected owner or slug')
    if pkg.get('bugs') != {'url': 'https://github.com/sylvesterkaczmarek/satsift/issues'}:
        fail('npm issue destination is inconsistent')
    if pkg.get('homepage') != 'https://www.sylvesterkaczmarek.com/satsift/':
        fail('npm homepage differs from the canonical SatSift URL')
    expected_keywords = {'satellite', 'satellite-maneuvers', 'orbital-mechanics',
                         'space-situational-awareness', 'sgp4', 'tle', 'anomaly-detection'}
    if not isinstance(pkg.get('keywords'), list) or not expected_keywords.issubset(set(pkg['keywords'])):
        fail('SatSift research discoverability keywords are incomplete')
    if lock.get('name') != pkg['name'] or lock.get('version') != pkg['version']:
        fail('npm lockfile package identity diverges from package.json')
    if lock.get('packages', {}).get('', {}).get('name') != pkg['name'] or lock['packages'][''].get('license') != pkg['license']:
        fail('npm lockfile root licence is inconsistent')

    readme = (ROOT / 'README.md').read_text()
    if not readme.startswith('# SatSift\n') or 'github.com/sylvesterkaczmarek/satsift.git' not in readme:
        fail('README project identity is inconsistent')
    for filename in ('index.html', 'docs.html', 'benchmark.html', 'accessibility.html'):
        html = (ROOT / filename).read_text()
        if '<title>SatSift' not in html and '<title>SatSift ' not in html:
            fail('SatSift search title is missing from ' + filename)
        if 'https://www.sylvesterkaczmarek.com/satsift/' not in html:
            fail('canonical SatSift URL is missing from ' + filename)
    if '<h1>SatSift</h1>' not in (ROOT / 'index.html').read_text():
        fail('workbench name does not appear in the hero')
    deploy = (ROOT / 'tools/deploy_production.py').read_text()
    if 'github.com/sylvesterkaczmarek/satsift.git' not in deploy or 'github.com/sylvesterkaczmarek/satellite-maneuver-detector.git' in deploy:
        fail('deployment source owner/slug guard still admits an obsolete repository')
    source_release = (ROOT / 'tools/source_release.py').read_text()
    if 'satsift-source-candidate.tar.gz' not in source_release or 'tarfile.TarInfo("satsift/" + path)' not in source_release:
        fail('clean-source archive still uses the obsolete project name')


def main() -> None:
    files = tracked_files()
    check_required(files)
    check_secrets(files)
    check_json()
    check_html(files)
    check_versions()
    check_routing()
    check_scientific_guardrails()
    check_benchmark_label_policy()
    check_vendor_hashes()
    check_component_notices()
    check_project_identity()
    print('Repository integrity checks passed.')


if __name__ == '__main__':
    main()
