#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.browser_source import read_browser_source
EXPECTED_RESULT_SHA256='f9857bd8f9ae2525b1827ce4fdfd108f7c5468c67142226922542d24b88c923c'
# Trusted digest of the publication-baseline scientific surface, excluding
# the separately pinned maintenance functions below. Historical source pins
# remain unchanged in research/historical_v1/. No Git objects are needed here.
EXPECTED_UNCHANGED_SCIENTIFIC_SHA256='fd2164c853586dd7ecb00f8c858995b8788bfb94c2a4df729da4d408c7bad892'
SCIENTIFIC_FUNCTIONS=(
    'median', 'empiricalQuantile', 'inferOrbitProfile', 'eccentricityVector',
    'inclinationVector', 'planarDistance', 'semiMajorAxisKm', 'getAnalysisOptions',
    'recordEpochUs', 'compareRecordEpochs', 'recordsConflict',
    'compareCatalogueIdentifier', 'catalogueMetadataPreference',
    'catalogueRevisionAudit', 'resolveCatalogueRevisions', 'classifySeverity',
    'satrecForRecord', 'computeSgp4Residual', 'featureFloor',
    'groupFlagsIntoEvents', 'analyzeRaw',
    'canonicalCatalogId', 'parseTlePair', 'parseOmmRecord', 'recordToOmm',
    'mergeOrbitalHistories', 'applyIncomingData',
    'parseTleEpoch',
    'formatEpochUs',
    'hasSgp4Support',
    'propagateRecordAtEpoch',
    'canonicalRecord',
    'makeRunId',
    'decodeSavedPackage',
    'normaliseBenchmarkDefinition',
)
# Reviewed input-maintenance bodies through Workbench 3.4.9, retaining prior versions. Input precision,
# propagation initialisation, identity and provenance repairs are individually pinned.
# The one reviewed analyzeRaw capability check is normalised below; every
# other byte of its detector logic remains inside the publication-baseline pin.
# Historical verification and archived source pins remain unchanged.
APPROVED_INPUT_MAINTENANCE={
    'normaliseBenchmarkDefinition': {
        'sha256': '729592eefc92939d072994e11267c09b6661a7ad50fb7e096377798df92494dc',
        'prior_sha256': '1859e4f1d74245f2393267ae4c9458bb58b326cd9a52b436630649c81d65b6be',
        'reason': 'Default an omitted matching tolerance only; require a finite JSON number in the supported range for every explicit value.',
        'regression': 'tests/benchmark_tolerance_test.js',
    },
    'canonicalCatalogId': {
        'sha256': '6a67cf0a10e0d9af3787d3368f72763209dcc23e3b8e75582c794831c3b26bab',
        'reason': 'Canonicalise decimal and standard Alpha-5 TLE catalog identifiers without treating native OMM identifiers as Alpha-5.',
        'regression': 'tests/catalogue_identifier_test.js',
    },
    'resolveCatalogueRevisions': {
        'sha256': '74bce88db3d380cdc0e610490fdb97c486eef32d30f603e499b7afa678e1589d',
        'prior_sha256': '74dd1053ec78c4a0960c0cf50ff76f6bab51c735e53edf13867e8336e9aa436e',
        'reason': 'Resolve exact-epoch metadata and source identity before nearby OMM revisions, preserving real conflicts and canonical permutation-invariant audits.',
        'regression': 'tests/catalogue_revision_test.js',
        'prior_regression': 'tests/tle_precision_roundtrip_test.js',
    },
    'satrecForRecord': {
        'sha256': '308f1d029f112607ddf30100907f865a6e035b8a9a4c4fe52f80dd12ed201835',
        'reason': 'Retain the original TLE initialisation path and explicitly preserve the vendor Date-based native OMM model epoch.',
        'regression': 'tests/tle_precision_roundtrip_test.js',
    },
    'parseTlePair': {
        'sha256': 'ba71e4ca52d50da4526a084fc8c9a26d699caaeee8086b0c4b602ef0f0caffaa',
        'prior_sha256': 'db225803436f89bfd6cfd754a13fffd40ff50134191ca9a524e5b09c10605138',
        'reason': 'Keep precise TLE propagation input while canonicalising decimal and Alpha-5 catalog identifiers.',
        'regression': 'tests/catalogue_identifier_test.js',
    },
    'parseOmmRecord': {
        'sha256': '836667010a91476b4e1ff1442c0cb68f80673c5351e0b2ed68c4c844054ad65b',
        'prior_sha256': '01694daf694c8a7a39eb5bbf52fb428adb6092f2fc42c848799d488036429ae0',
        'reason': 'Normalise decimal OMM identifiers and accept retained Alpha-5 TLE-derived legacy packages only when source TLE matches.',
        'regression': 'tests/catalogue_identifier_test.js',
    },
    'recordToOmm': {
        'sha256': 'f4101d7cea0ab2f7b7972b227fd90e686ce927394f941c67c76be91c9b7ed464',
        'reason': 'Preserve validated TLE source lines in a versioned extension alongside precise epochs and catalogue metadata.',
        'regression': 'tests/tle_precision_roundtrip_test.js',
    },
    'mergeOrbitalHistories': {
        'sha256': '9adeed55f417cb7f37f1db57f5eb622afc1c3cf9d9990000d87b81a324c78698',
        'reason': 'Recognise catalogue metadata enrichment when comparing merged and existing input.',
        'regression': 'tests/catalogue_metadata_roundtrip_test.js',
    },
    'applyIncomingData': {
        'sha256': '9e682bbd67ccdfa3db930a9ca84ce7a63e1da93d90478b4cff4a182b08204adf',
        'prior_sha256': 'fb743e2f0dc800875fae3200196c0bc15494476e63a88fd9063071b7084d4a56',
        'reason': 'Persist metadata-only append changes selected by the catalogue resolver; validate optional provenance before mutation and retain bounded source lineage across merges.',
        'regression': 'tests/history_provenance_test.js',
        'prior_regression': 'tests/catalogue_metadata_roundtrip_test.js',
    },
    'compareCatalogueIdentifier': {
        'sha256': '4eace1fd3bbcef1a9d2ba3f353dace9892f6f9f604b8c29a277cf64fc8666e99',
        'prior_sha256': '5041bacf0bd146fbbc8d386c248624f172f9663df512ffbc1755a52cb640d415',
        'reason': 'Order supplied decimal GP identifiers above opaque identifiers, preserving exact numeric ties and lexical opaque order without nontransitive cycles.',
        'regression': 'tests/catalogue_revision_test.js',
        'prior_regression': 'tests/catalogue_metadata_roundtrip_test.js',
    },
    'parseTleEpoch': {
        'sha256': '77e7face7daf20455b35382953950d3cce0e974e5cfc46082dab7dd9999b6583',
        'reason': 'Convert the eight-digit TLE fractional day directly to integer microseconds, preserving day zero and the standard year pivot.',
        'regression': 'tests/tle_precision_roundtrip_test.js',
    },
    'formatEpochUs': {
        'sha256': 'e4305729636d5f5d0eabfa120b6204dc500b98c29f5782fd383a389aba5a23ab',
        'reason': 'Format exact integer microseconds canonically, including correct Date flooring before 1970.',
        'regression': 'tests/tle_precision_roundtrip_test.js',
    },
    'hasSgp4Support': {
        'sha256': 'dae11a40b7f3ce0809e467ef4c0c7f1a1e9c7b06d6ee06e579726d1af3535dcb',
        'reason': 'Require the direct SGP4 propagator and both supported initialisers before enabling multivariate analysis.',
        'regression': 'tests/tle_precision_roundtrip_test.js',
    },
    'propagateRecordAtEpoch': {
        'sha256': 'c248ef84bc96cbe4788c9b416705a87e6b1a22176877d7ad76f71dd30ff1dca0',
        'reason': 'Use precise elapsed microseconds from the actual TLE or Date-initialised OMM model epoch.',
        'regression': 'tests/tle_precision_roundtrip_test.js',
    },
    'computeSgp4Residual': {
        'sha256': '26d3c16e64f19b7cd80a1c15e503416401abb11b1ff416b3a215a5a97927c2da',
        'reason': 'Sample both models at the exact common epoch while preserving all existing RTN and velocity residual equations.',
        'regression': 'tests/tle_precision_roundtrip_test.js',
    },
    'canonicalRecord': {
        'sha256': 'fa4b64b9ebd6d9cbbb83d790a0b690ec04da64899b64b28c809e0c91962df69c',
        'reason': 'Include exact epochs and retained propagation inputs in deterministic run identity.',
        'regression': 'tests/tle_precision_roundtrip_test.js',
    },
    'makeRunId': {
        'sha256': '794228a5ecf55b3dcad9ff80af2957dae12ec45f99763bcacfe29dcc778b12c8',
        'reason': 'Version run identity and bind it to propagation capability, implementation versions, and requested and effective analysis settings.',
        'regression': 'tests/tle_precision_roundtrip_test.js',
    },
    'decodeSavedPackage': {
        'sha256': 'd87199571836fd0cb6b4fab362da01079527d287187f40bc7252e38ca50650cc',
        'prior_sha256': 'a88f619e27947d405f1829841bc461158477439e6270de4ffba181da10dcf855',
        'reason': 'Validate supported package and identity versions and optional provenance bound to normalised input, retaining explicit compatibility warnings for legacy packages.',
        'regression': 'tests/history_provenance_test.js',
        'prior_regression': 'tests/tle_precision_roundtrip_test.js',
    },
}

def js_function(source: str, name: str) -> str:
    marker=f'  function {name}('
    start=source.index(marker)
    brace=source.index('{', start)
    depth=0
    quote=None
    escaped=False
    for index in range(brace, len(source)):
        character=source[index]
        if quote:
            if escaped:
                escaped=False
            elif character=='\\':
                escaped=True
            elif character==quote:
                quote=None
            continue
        if character in "'\"`":
            quote=character
        elif character=='{':
            depth+=1
        elif character=='}':
            depth-=1
            if depth==0:
                return source[start:index+1]
    raise AssertionError(f'Could not extract JavaScript function {name}')

def restore_reviewed_capability_line(app: str) -> str:
    """Retain the complete detector body in the baseline scientific digest."""
    original=js_function(app, 'analyzeRaw')
    reviewed="    const sgp4Available = hasSgp4Support();"
    baseline="    const sgp4Available = Boolean(window.satellite && typeof window.satellite.propagate === 'function');"
    assert original.count(reviewed)==1, 'Unreviewed SGP4 capability check in analyzeRaw'
    return app.replace(original, original.replace(reviewed, baseline, 1), 1)

def scientific_surface(source: str, *, omit_functions: frozenset[str] = frozenset()) -> bytes:
    constants=[]
    for name in ('MU', 'METHOD_VERSION', 'MIN_EVALUATED_POINTS', 'DAY_MS', 'CATALOGUE_REVISION_TOLERANCE_US'):
        marker=f'  const {name} = '
        start=source.index(marker)
        constants.append(source[start:source.index('\n', start)])
    features_start=source.index('  const FEATURE_LABELS = ')
    features_end=source.index('\n\n  function stableStringify', features_start)
    parts=constants+[source[features_start:features_end]]
    parts.extend(js_function(source, name) for name in SCIENTIFIC_FUNCTIONS if name not in omit_functions)
    return '\n'.join(parts).encode()

def assert_scientific_maintenance(app: str) -> None:
    """Permit only the exact documented repairs; freeze every other covered byte."""
    allowed=frozenset(APPROVED_INPUT_MAINTENANCE)
    assert allowed.issubset(SCIENTIFIC_FUNCTIONS)
    for name, repair in APPROVED_INPUT_MAINTENANCE.items():
        actual=hashlib.sha256(js_function(app, name).encode()).hexdigest()
        assert actual==repair['sha256'], f'Unreviewed maintenance change in {name}'
        assert repair['reason'] and (ROOT/repair['regression']).is_file()
    normalised=restore_reviewed_capability_line(app)
    actual=hashlib.sha256(scientific_surface(normalised, omit_functions=allowed)).hexdigest()
    assert actual==EXPECTED_UNCHANGED_SCIENTIFIC_SHA256, 'Scientific surface changed outside approved input maintenance'

def assert_maintenance_gate_rejects_unapproved_edits(app: str) -> None:
    # Exercise the guard itself so excluding a repaired body cannot accidentally
    # permit arbitrary future changes to that function or detector mathematics.
    mutations=[app.replace('  const MU = 398600.4418;', '  const MU = 398600.0;', 1)]
    for name in ('analyzeRaw', *APPROVED_INPUT_MAINTENANCE):
        original=js_function(app, name)
        mutated=original.replace('{', '{ /* unapproved edit */', 1)
        mutations.append(app.replace(original, mutated, 1))
    for mutated in mutations:
        assert mutated!=app, 'Mutation regression did not alter its target'
        try:
            assert_scientific_maintenance(mutated)
        except AssertionError:
            continue
        raise AssertionError('Scientific maintenance gate accepted an unapproved edit')

def main() -> None:
    result_path=ROOT/'benchmark-results/confirmatory-v1-final.json'
    raw=result_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==EXPECTED_RESULT_SHA256
    data=json.loads(raw)
    assert data['integration_publication_gate']['passed'] is False
    target=next(item for item in data['methods'] if item['method']=='physics-ml-v1.0')
    s=target['confirmatory_evaluation']['summary']
    assert s['true_positives']==0 and s['false_negatives']==41
    assert s['recall']==0.0 and s['f1']==0.0
    assert float(s['mean_case_abstention_fraction'])>0.9
    lock=json.loads((ROOT/'research/confirmatory_v1/RUN-LOCK-v1.0.json').read_text())
    assert lock['one_shot_completed'] is True and lock['rerun_forbidden'] is True
    assert lock['gate_passed'] is False
    assert lock['final_result_sha256']==EXPECTED_RESULT_SHA256
    disp=(ROOT/'research/confirmatory_v1/INTEGRATION-DISPOSITION.md').read_text()
    assert 'NO INTEGRATION' in disp
    assert 'not prepared under this roadmap' in disp
    readme=(ROOT/'README.md').read_text()
    assert '- Detector method: 0.4' in readme
    assert 'INTEGRATION-DISPOSITION.md' in readme
    assert 'failed' in readme.lower(), 'README must disclose the failed confirmatory gate'
    app=read_browser_source(ROOT)
    index=(ROOT/'index.html').read_text()
    assert "const METHOD_VERSION = 'v0.4';" in app
    assert 'Detector method 0.4' in index
    assert_scientific_maintenance(app)
    assert_maintenance_gate_rejects_unapproved_edits(app)
    assert 'physics-ml-v1.0' not in app.lower()
    assert 'physics-ml-v1.0' not in index.lower()
    print(f'Integration decision negative disposition and {len(APPROVED_INPUT_MAINTENANCE)} pinned input-maintenance bodies verified; {len(APPROVED_INPUT_MAINTENANCE) + 2} unapproved mutations rejected.')

if __name__=='__main__':
    main()
