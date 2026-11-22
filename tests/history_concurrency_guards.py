#!/usr/bin/env python3
"""Keep the endpoint's admission, cache and upstream lock boundaries explicit."""
from pathlib import Path
import re

SOURCE = Path('history.php').read_text()
ENTRY = SOURCE[SOURCE.index("if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') {"):]

assert 'curl_close(' not in SOURCE, 'Deprecated curl_close() must not contaminate JSON responses on PHP 8.5+.'
assert 'LOCK_EX | LOCK_NB' in SOURCE, 'History locks must use nonblocking acquisition.'
assert not re.search(r'flock\([^,\n]+,\s*LOCK_EX\s*\)', SOURCE), 'Unbounded blocking locks must not return.'
assert "'gp-history-' . $norad . '.lock'" not in SOURCE, 'Catalogue IDs must not allocate unbounded object lock files.'
assert "sprintf('history-object-%02d.lock', $stripe)" in ENTRY, 'Object coordination must use fixed lock stripes.'


def position(fragment: str) -> int:
    value = ENTRY.find(fragment)
    if value < 0:
        raise AssertionError(f'Missing expected history endpoint guard: {fragment}')
    return value


incoming = position('enforceIncomingAdmission($cacheDirectory, $clientAddress);')
store_path = position("$storePath = $cacheDirectory . DIRECTORY_SEPARATOR . 'gp-history-'")
lock = position('$lock = acquireHistoryLock($lockPath);')
store_read = position('if (pathExists($storePath))')
missing = position('$missing = missingIntervals($start, $end, $coveredIntervals);')
cache_gate = position('if ($missing) {')
credentials = position('requireCredentials($identity, $password);')
miss_lock = position('$missLock = acquireHistoryLock(')
storage = position('enforceStorageHeadroom($cacheDirectory, $storePath);')
preflight = position('enforceUpstreamBudget($cacheDirectory, $clientAddress, 1 + count($missing), false,')
session = position('createSessionFile($cookiePath);')
fetch_loop = position('foreach ($missing as $interval)')
atomic_write = position('writeJsonAtomically($storePath, $store);')
miss_unlock = position('releaseHistoryLock($missLock);')
unlock = position('releaseHistoryLock($lock);')

assert incoming < store_path < lock < store_read < missing < cache_gate, (
    'Every valid request must pass incoming admission before object allocation, '
    'then recheck cached coverage under its stripe lock.'
)
assert cache_gate < credentials < miss_lock < storage < preflight < session < fetch_loop < atomic_write < miss_unlock < unlock, (
    'A cache miss must reserve bounded storage and the complete upstream plan under the miss lock, '
    'then retain both locks through validation and the single atomic history commit.'
)
assert 'writeJsonAtomically' not in ENTRY[store_read:cache_gate], 'A cache hit must preserve history bytes.'
assert ENTRY.count('writeJsonAtomically($storePath, $store);') == 1, 'History must be committed once after all fragments succeed.'
assert 'respond(' not in ENTRY[ENTRY.index('try {'):unlock], 'Responses must be rendered after cleanup releases request resources.'

upstream = SOURCE[SOURCE.index('function curlRequest('):SOURCE.index('function normaliseIntervals(')]
assert upstream.index("enforceUpstreamBudget($context['cacheDirectory'], $context['clientAddress'], 1, true,") < upstream.index('curl_exec($handle)'), (
    'Every actual upstream attempt, including login and failures, must be charged before cURL runs.'
)

print('History concurrency guard tests passed.')
