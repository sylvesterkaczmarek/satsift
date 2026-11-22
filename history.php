<?php
declare(strict_types=1);

/*
 * Satellite Maneuver Screening Workbench history endpoint
 *
 * Retrieves GP_History OMM records from Space-Track without exposing account
 * credentials to the browser. Retrieved date intervals are stored persistently
 * by object, and later overlapping requests fetch only dates not already held.
 *
 * PHP 7.4+ with the cURL extension is recommended.
 */

const MAX_RANGE_DAYS = 31;
const MAX_RECORDS = 5000;
const CLIENT_WINDOW_SECONDS = 900;
const CLIENT_REQUEST_LIMIT = 12;
const GLOBAL_WINDOW_SECONDS = 3600;
const GLOBAL_REQUEST_LIMIT = 20;
const INCOMING_WINDOW_SECONDS = 900;
const INCOMING_CLIENT_LIMIT = 60;
const INCOMING_GLOBAL_LIMIT = 240;
const OBJECT_LOCK_STRIPES = 64;
const LOCK_WAIT_MILLISECONDS = 500;
const UPSTREAM_BUDGET_SECONDS = 30;
const UPSTREAM_CONNECT_TIMEOUT_SECONDS = 10;
const MAX_UPSTREAM_RESPONSE_BYTES = 4194304;
const MAX_UPSTREAM_HEADER_BYTES = 65536;
const MAX_COOKIE_BYTES = 65536;
const MAX_OBJECT_BYTES = 8388608;
const MAX_RESPONSE_BYTES = 8388608;
const MAX_TOTAL_HISTORY_BYTES = 134217728;
const MAX_HISTORY_OBJECTS = 128;
const MAX_LEDGER_BYTES = 65536;
const MAX_DIRECTORY_ENTRIES = 1024;
const HISTORY_STORE_VERSION = 2;
const HISTORY_PROVENANCE_SCHEMA_VERSION = 1;
const HISTORY_RETENTION_POLICY = 'retained-history-v1';
const MAX_HISTORY_ACQUISITIONS = 4096;

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store, max-age=0');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');
header('X-Robots-Tag: noindex, nofollow');
header('Cross-Origin-Resource-Policy: same-origin');
header("Content-Security-Policy: default-src 'none'; frame-ancestors 'none'");

function respond(int $status, array $payload): void
{
    $encoded = json_encode(
        $payload,
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE
    );
    if ($encoded === false || strlen($encoded) > MAX_RESPONSE_BYTES) {
        $status = 413;
        $encoded = '{"ok":false,"message":"The history response exceeded the server size limit. Choose a shorter date range."}';
    }
    http_response_code($status);
    echo $encoded;
    exit;
}

function utcDate(string $value, string $field): DateTimeImmutable
{
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $value)) {
        respond(400, ['ok' => false, 'message' => "$field must use YYYY-MM-DD format."]);
    }

    $date = DateTimeImmutable::createFromFormat('!Y-m-d', $value, new DateTimeZone('UTC'));
    $errors = DateTimeImmutable::getLastErrors();
    if (!$date || ($errors !== false && ($errors['warning_count'] > 0 || $errors['error_count'] > 0))) {
        respond(400, ['ok' => false, 'message' => "$field is not a valid calendar date."]);
    }
    return $date;
}

function ensureDirectory(string $path): void
{
    if (!is_dir($path) && !@mkdir($path, 0700, true) && !is_dir($path)) {
        throw new HistoryRequestException(503, 'The persistent history-cache directory could not be created.');
    }
    @chmod($path, 0700);
}

function readConfiguration(): array
{
    $config = [];

    // Keep credentials and persistent history outside the public web root.
    // DOCUMENT_ROOT is preferred because the project can be moved within it.
    $documentRoot = realpath((string) ($_SERVER['DOCUMENT_ROOT'] ?? ''));
    $privateRoot = $documentRoot !== false && $documentRoot !== ''
        ? dirname($documentRoot)
        : dirname(__DIR__, 3);
    $configPath = $privateRoot . DIRECTORY_SEPARATOR . '.space-track-config.php';
    if (is_file($configPath)) {
        $loaded = require $configPath;
        if (is_array($loaded)) {
            $config = $loaded;
        }
    }

    $identity = trim((string) getenv('SPACETRACK_IDENTITY'));
    $password = (string) getenv('SPACETRACK_PASSWORD');
    $cacheDirectory = trim((string) getenv('SATELLITE_HISTORY_CACHE_DIR'));

    if ($identity === '') {
        $identity = trim((string) ($config['identity'] ?? ''));
    }
    if ($password === '') {
        $password = (string) ($config['password'] ?? '');
    }
    if ($cacheDirectory === '') {
        $cacheDirectory = trim((string) ($config['cache_dir'] ?? ''));
    }
    if ($cacheDirectory === '') {
        $cacheDirectory = $privateRoot . DIRECTORY_SEPARATOR . '.satellite-maneuver-cache';
    }

    return [$identity, $password, $cacheDirectory];
}

final class HistoryRequestException extends RuntimeException
{
    public $status;
    public $retryAfter;

    public function __construct(int $status, string $message, ?int $retryAfter = null)
    {
        parent::__construct($message);
        $this->status = $status;
        $this->retryAfter = $retryAfter;
    }
}

function monotonicSeconds(): float
{
    return hrtime(true) / 1000000000;
}

/** @return resource */
function acquireHistoryLock(string $path, ?float $requestDeadline = null)
{
    if (is_link($path) || (file_exists($path) && !is_file($path))) {
        throw new HistoryRequestException(503, 'The server request coordinator is unavailable.');
    }
    $handle = @fopen($path, 'c+b');
    if ($handle === false) {
        throw new HistoryRequestException(503, 'The server request coordinator is unavailable.');
    }
    if (!@chmod($path, 0600)) {
        fclose($handle);
        throw new HistoryRequestException(503, 'The server request coordinator is unavailable.');
    }

    $deadline = monotonicSeconds() + LOCK_WAIT_MILLISECONDS / 1000;
    if ($requestDeadline !== null) {
        $deadline = min($deadline, $requestDeadline);
    }
    do {
        if (monotonicSeconds() >= $deadline) {
            break;
        }
        if (@flock($handle, LOCK_EX | LOCK_NB)) {
            return $handle;
        }
        $remaining = $deadline - monotonicSeconds();
        if ($remaining <= 0) {
            break;
        }
        usleep((int) min(10000, max(1, $remaining * 1000000)));
    } while (true);

    fclose($handle);
    throw new HistoryRequestException(503, 'The history service is busy. Try again shortly.', 1);
}

function releaseHistoryLock($handle): void
{
    if (is_resource($handle)) {
        @flock($handle, LOCK_UN);
        fclose($handle);
    }
}

function pathExists(string $path): bool
{
    return file_exists($path) || is_link($path);
}

function readBoundedFile(string $path, int $maximumBytes): string
{
    if (is_link($path) || !is_file($path)) {
        throw new HistoryRequestException(503, 'The server history storage is unavailable.');
    }
    $handle = @fopen($path, 'rb');
    if ($handle === false) {
        throw new HistoryRequestException(503, 'The server history storage is unavailable.');
    }
    try {
        $stat = fstat($handle);
        if ($stat === false || $stat['size'] > $maximumBytes) {
            throw new HistoryRequestException(503, 'The server history storage exceeds its configured limit.');
        }
        $contents = stream_get_contents($handle, $maximumBytes + 1);
        if ($contents === false || !feof($handle) || strlen($contents) > $maximumBytes) {
            throw new HistoryRequestException(503, 'The server history storage could not be read within its limit.');
        }
        return $contents;
    } finally {
        fclose($handle);
    }
}

function requireCredentials(string $identity, string $password): void
{
    if ($identity === '' || $password === '') {
        throw new HistoryRequestException(
            503,
            'Historical retrieval is not configured on this server. Add Space-Track credentials to the server configuration.'
        );
    }
}

function quotaStateError(): HistoryRequestException
{
    return new HistoryRequestException(503, 'The server request-limit store is unavailable.');
}

/**
 * Decode bounded, internally consistent counters. Old miss counters are read
 * solely for a conservative migration cooldown, never reinterpreted as calls.
 */
function readQuotaState(
    string $path,
    int $version,
    int $clientLimit,
    int $globalLimit,
    int $clientWindow,
    int $now,
    bool $legacy = false
): array {
    try {
        $decoded = json_decode(readBoundedFile($path, MAX_LEDGER_BYTES), false, 32, JSON_THROW_ON_ERROR);
    } catch (Throwable $error) {
        throw quotaStateError();
    }
    if (!$decoded instanceof stdClass) {
        throw quotaStateError();
    }
    $keys = array_keys(get_object_vars($decoded));
    sort($keys, SORT_STRING);
    $expectedKeys = $legacy ? ['clients', 'global'] : ['clients', 'global', 'version'];
    if ($keys !== $expectedKeys || (!$legacy && $decoded->version !== $version)) {
        throw quotaStateError();
    }
    if ((!$decoded->clients instanceof stdClass && $decoded->clients !== []) || !is_array($decoded->global)) {
        throw quotaStateError();
    }
    $clients = (array) $decoded->clients;
    $global = $decoded->global;
    if (count($clients) > $globalLimit || count($global) > $globalLimit) {
        throw quotaStateError();
    }
    $freshGlobalCounts = [];
    foreach ($global as $timestamp) {
        if (!is_int($timestamp) || $timestamp < 0 || $timestamp > $now) {
            throw quotaStateError();
        }
        if ($timestamp > $now - $clientWindow) {
            $freshGlobalCounts[$timestamp] = ($freshGlobalCounts[$timestamp] ?? 0) + 1;
        }
    }
    foreach ($clients as $key => $timestamps) {
        if (!is_string($key) || !preg_match('/^[a-f0-9]{64}$/', $key)
            || !is_array($timestamps) || count($timestamps) > $clientLimit) {
            throw quotaStateError();
        }
        foreach ($timestamps as $timestamp) {
            if (!is_int($timestamp) || $timestamp < 0 || $timestamp > $now) {
                throw quotaStateError();
            }
            if ($timestamp > $now - $clientWindow) {
                if (($freshGlobalCounts[$timestamp] ?? 0) < 1) {
                    throw quotaStateError();
                }
                $freshGlobalCounts[$timestamp]--;
            }
        }
    }
    if (array_sum($freshGlobalCounts) !== 0) {
        throw quotaStateError();
    }
    return ['version' => $version, 'clients' => $clients, 'global' => $global];
}

function quotaRetryAfter(array $timestamps, int $window, int $limit, int $cost, int $now): int
{
    $mustExpire = count($timestamps) + $cost - $limit;
    if ($mustExpire <= 0) {
        return 0;
    }
    sort($timestamps, SORT_NUMERIC);
    return max(1, $timestamps[$mustExpire - 1] + $window - $now);
}

function updateQuota(
    string $cacheDirectory,
    string $clientAddress,
    bool $upstream,
    int $cost,
    bool $charge,
    ?float $deadline = null
): void {
    $clientLimit = $upstream ? CLIENT_REQUEST_LIMIT : INCOMING_CLIENT_LIMIT;
    $globalLimit = $upstream ? GLOBAL_REQUEST_LIMIT : INCOMING_GLOBAL_LIMIT;
    $clientWindow = $upstream ? CLIENT_WINDOW_SECONDS : INCOMING_WINDOW_SECONDS;
    $globalWindow = $upstream ? GLOBAL_WINDOW_SECONDS : INCOMING_WINDOW_SECONDS;
    $version = $upstream ? 2 : 1;
    $basename = $upstream ? 'upstream-limits' : 'request-limits';
    if ($cost < 1 || $cost > min($clientLimit, $globalLimit)) {
        throw new LengthException('The requested history needs too many upstream operations. Choose a shorter date range.');
    }

    $lock = acquireHistoryLock($cacheDirectory . DIRECTORY_SEPARATOR . $basename . '.lock', $deadline);
    try {
        if ($deadline !== null) {
            requireUpstreamTime($deadline);
        }
        $now = time();
        $path = $cacheDirectory . DIRECTORY_SEPARATOR . $basename . '.json';
        $state = ['version' => $version, 'clients' => [], 'global' => []];
        if (pathExists($path)) {
            $state = readQuotaState($path, $version, $clientLimit, $globalLimit, $clientWindow, $now);
        } elseif ($upstream) {
            $legacyPath = $cacheDirectory . DIRECTORY_SEPARATOR . 'rate-limits.json';
            if (pathExists($legacyPath)) {
                $legacy = readQuotaState(
                    $legacyPath,
                    2,
                    CLIENT_REQUEST_LIMIT,
                    GLOBAL_REQUEST_LIMIT,
                    CLIENT_WINDOW_SECONDS,
                    $now,
                    true
                );
                $latest = 0;
                foreach ($legacy['global'] as $timestamp) {
                    $latest = max($latest, $timestamp);
                }
                foreach ($legacy['clients'] as $timestamps) {
                    foreach ($timestamps as $timestamp) {
                        $latest = max($latest, $timestamp);
                    }
                }
                if ($latest > 0 && $latest + GLOBAL_WINDOW_SECONDS > $now) {
                    throw new HistoryRequestException(
                        429,
                        'Historical retrieval is waiting for the previous request-limit window to expire.',
                        $latest + GLOBAL_WINDOW_SECONDS - $now
                    );
                }
            }
        }

        foreach ($state['clients'] as $key => $timestamps) {
            $fresh = array_values(array_filter($timestamps, static function (int $timestamp) use ($now, $clientWindow): bool {
                return $timestamp > $now - $clientWindow;
            }));
            if ($fresh) {
                $state['clients'][$key] = $fresh;
            } else {
                unset($state['clients'][$key]);
            }
        }
        $state['global'] = array_values(array_filter($state['global'], static function (int $timestamp) use ($now, $globalWindow): bool {
            return $timestamp > $now - $globalWindow;
        }));
        $clientKey = hash('sha256', $clientAddress !== '' ? $clientAddress : 'unknown');
        $clientTimes = $state['clients'][$clientKey] ?? [];
        $retryAfter = max(
            quotaRetryAfter($clientTimes, $clientWindow, $clientLimit, $cost, $now),
            quotaRetryAfter($state['global'], $globalWindow, $globalLimit, $cost, $now)
        );
        if ($retryAfter > 0) {
            throw new HistoryRequestException(
                429,
                $upstream
                    ? 'Historical-data upstream operation limit reached. Try again later.'
                    : 'History request limit reached. Try again later.',
                $retryAfter
            );
        }
        if ($deadline !== null) {
            requireUpstreamTime($deadline);
        }
        if (!$charge) {
            return;
        }

        // Persist before the admitted work starts. Failed network calls remain
        // charged, while preflight and unused calls never consume the budget.
        for ($index = 0; $index < $cost; $index++) {
            $clientTimes[] = $now;
            $state['global'][] = $now;
        }
        $state['clients'][$clientKey] = $clientTimes;
        $state['clients'] = (object) $state['clients'];
        try {
            writeJsonAtomically($path, $state, $path . '.tmp', MAX_LEDGER_BYTES);
        } catch (Throwable $error) {
            throw quotaStateError();
        }
    } finally {
        releaseHistoryLock($lock);
    }
}

function enforceIncomingAdmission(string $cacheDirectory, string $clientAddress): void
{
    updateQuota($cacheDirectory, $clientAddress, false, 1, true);
}

/** Call only while holding history-miss.lock. */
function enforceUpstreamBudget(
    string $cacheDirectory,
    string $clientAddress,
    int $operations,
    bool $charge = false,
    ?float $deadline = null
): void {
    updateQuota($cacheDirectory, $clientAddress, true, $operations, $charge, $deadline);
}

function enforceStorageHeadroom(string $cacheDirectory, string $storePath): void
{
    $directory = @opendir($cacheDirectory);
    if ($directory === false) {
        throw new HistoryRequestException(503, 'The server history storage is unavailable.');
    }
    $entries = 0;
    $objects = 0;
    $totalBytes = 0;
    $existingBytes = 0;
    $existingObject = false;
    try {
        while (($name = readdir($directory)) !== false) {
            if ($name === '.' || $name === '..') {
                continue;
            }
            if (++$entries > MAX_DIRECTORY_ENTRIES) {
                throw new HistoryRequestException(503, 'The server history storage needs maintenance before it can grow.');
            }
            if (!preg_match('/^gp-history-\d{1,9}\.json$/', $name)) {
                continue;
            }
            $path = $cacheDirectory . DIRECTORY_SEPARATOR . $name;
            $stat = @lstat($path);
            if ($stat === false || ($stat['mode'] & 0170000) !== 0100000 || $stat['size'] > MAX_OBJECT_BYTES) {
                throw new HistoryRequestException(503, 'The server history storage exceeds its configured limit.');
            }
            $objects++;
            $totalBytes += $stat['size'];
            if ($path === $storePath) {
                $existingObject = true;
                $existingBytes = $stat['size'];
            }
            if ($objects > MAX_HISTORY_OBJECTS || $totalBytes > MAX_TOTAL_HISTORY_BYTES) {
                throw new HistoryRequestException(503, 'The server history storage is full.');
            }
        }
    } finally {
        closedir($directory);
    }
    // The miss lock stays held through commit, so this headroom cannot be
    // consumed by another writer. Existing histories are never evicted.
    if ($objects + ($existingObject ? 0 : 1) > MAX_HISTORY_OBJECTS
        || $totalBytes - $existingBytes + MAX_OBJECT_BYTES > MAX_TOTAL_HISTORY_BYTES) {
        throw new HistoryRequestException(503, 'The server history storage is full.');
    }
}

function createSessionFile(string $path): void
{
    if (is_link($path) || (pathExists($path) && !is_file($path))) {
        throw new HistoryRequestException(503, 'A temporary history session could not be created.');
    }
    $handle = @fopen($path, 'wb');
    if ($handle === false) {
        throw new HistoryRequestException(503, 'A temporary history session could not be created.');
    }
    $ready = false;
    try {
        if (!@chmod($path, 0600)) {
            throw new HistoryRequestException(503, 'A temporary history session could not be secured.');
        }
        $closed = @fclose($handle);
        $handle = null;
        if (!$closed) {
            throw new HistoryRequestException(503, 'A temporary history session could not be prepared.');
        }
        $ready = true;
    } finally {
        if (is_resource($handle)) {
            fclose($handle);
        }
        if (!$ready && is_file($path) && !is_link($path)) {
            @unlink($path);
        }
    }
}

function requireUpstreamTime(float $deadline): void
{
    if (monotonicSeconds() >= $deadline) {
        throw new HistoryRequestException(503, 'Historical retrieval exceeded its time budget. Try a shorter date range.', 1);
    }
}

function curlRequest(string $url, array $options, array $context): array
{
    requireUpstreamTime($context['deadline']);
    $handle = curl_init($url);
    if ($handle === false) {
        throw new RuntimeException('cURL could not be initialised.');
    }
    $body = '';
    $headerBytes = 0;
    $tooLarge = false;
    $timedOut = false;
    $deadline = $context['deadline'];
    try {
        $remainingMilliseconds = max(1, (int) floor(($deadline - monotonicSeconds()) * 1000));
        $defaults = [
            CURLOPT_RETURNTRANSFER => false,
            CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_CONNECTTIMEOUT_MS => min(UPSTREAM_CONNECT_TIMEOUT_SECONDS * 1000, $remainingMilliseconds),
            CURLOPT_TIMEOUT_MS => $remainingMilliseconds,
            CURLOPT_USERAGENT => 'SatelliteManeuverWorkbench/3.4.7 (+https://www.sylvesterkaczmarek.com/satellite-maneuver-detector)',
            CURLOPT_HTTPHEADER => ['Accept: application/json'],
            CURLOPT_PROTOCOLS => CURLPROTO_HTTPS,
            CURLOPT_REDIR_PROTOCOLS => CURLPROTO_HTTPS,
            CURLOPT_WRITEFUNCTION => static function ($curl, string $chunk) use (&$body, &$tooLarge, &$timedOut, $deadline): int {
                if (monotonicSeconds() >= $deadline) {
                    $timedOut = true;
                    return 0;
                }
                if (strlen($body) + strlen($chunk) > MAX_UPSTREAM_RESPONSE_BYTES) {
                    $tooLarge = true;
                    return 0;
                }
                $body .= $chunk;
                return strlen($chunk);
            },
            CURLOPT_HEADERFUNCTION => static function ($curl, string $line) use (&$headerBytes, &$tooLarge, &$timedOut, $deadline): int {
                $headerBytes += strlen($line);
                if ($headerBytes > MAX_UPSTREAM_HEADER_BYTES) {
                    $tooLarge = true;
                    return 0;
                }
                if (monotonicSeconds() >= $deadline) {
                    $timedOut = true;
                    return 0;
                }
                return strlen($line);
            },
        ];
        if (!curl_setopt_array($handle, $options + $defaults)) {
            throw new RuntimeException('The upstream request could not be configured.');
        }
        requireUpstreamTime($deadline);
        enforceUpstreamBudget($context['cacheDirectory'], $context['clientAddress'], 1, true, $deadline);
        $remainingMilliseconds = max(1, (int) floor(($deadline - monotonicSeconds()) * 1000));
        if (!curl_setopt_array($handle, [
            CURLOPT_CONNECTTIMEOUT_MS => min(UPSTREAM_CONNECT_TIMEOUT_SECONDS * 1000, $remainingMilliseconds),
            CURLOPT_TIMEOUT_MS => $remainingMilliseconds,
        ])) {
            throw new RuntimeException('The upstream request timeout could not be configured.');
        }
        requireUpstreamTime($deadline);
        $result = curl_exec($handle);
        $status = (int) curl_getinfo($handle, CURLINFO_RESPONSE_CODE);
        $error = curl_error($handle);
        $errorNumber = curl_errno($handle);
        if ($tooLarge) {
            throw new LengthException('The upstream response exceeded the server size limit. Choose a shorter date range.');
        }
        if ($timedOut || $errorNumber === CURLE_OPERATION_TIMEDOUT || monotonicSeconds() >= $deadline) {
            throw new HistoryRequestException(503, 'Historical retrieval exceeded its time budget. Try a shorter date range.', 1);
        }
        if ($result === false) {
            throw new RuntimeException($error !== '' ? $error : 'The upstream request failed.');
        }
        // Persist login or updated cookies before the next handle needs them.
        if (isset($options[CURLOPT_COOKIEJAR]) && !curl_setopt($handle, CURLOPT_COOKIELIST, 'FLUSH')) {
            throw new RuntimeException('The upstream session could not be saved.');
        }
    } finally {
        // Clear COOKIEJAR and callbacks before any deferred destructor can run.
        curl_reset($handle);
        unset($handle);
    }
    if (isset($options[CURLOPT_COOKIEJAR])) {
        clearstatcache(true, $options[CURLOPT_COOKIEJAR]);
        $size = @filesize($options[CURLOPT_COOKIEJAR]);
        if ($size !== false && $size > MAX_COOKIE_BYTES) {
            throw new LengthException('The upstream session exceeded the server size limit.');
        }
    }
    return [$status, $body];
}

function normaliseIntervals(array $intervals): array
{
    $valid = [];
    foreach ($intervals as $interval) {
        if (!is_array($interval)) {
            continue;
        }
        $startRaw = (string) ($interval['start'] ?? '');
        $endRaw = (string) ($interval['end'] ?? '');
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $startRaw) || !preg_match('/^\d{4}-\d{2}-\d{2}$/', $endRaw)) {
            continue;
        }
        try {
            $start = new DateTimeImmutable($startRaw, new DateTimeZone('UTC'));
            $end = new DateTimeImmutable($endRaw, new DateTimeZone('UTC'));
        } catch (Throwable $error) {
            continue;
        }
        if ($end >= $start) {
            $valid[] = ['start' => $start, 'end' => $end];
        }
    }

    usort($valid, static function (array $first, array $second): int {
        return $first['start'] <=> $second['start'];
    });

    $merged = [];
    foreach ($valid as $interval) {
        $lastIndex = count($merged) - 1;
        if ($lastIndex < 0 || $interval['start'] > $merged[$lastIndex]['end']->modify('+1 day')) {
            $merged[] = $interval;
            continue;
        }
        if ($interval['end'] > $merged[$lastIndex]['end']) {
            $merged[$lastIndex]['end'] = $interval['end'];
        }
    }

    return array_map(static function (array $interval): array {
        return [
            'start' => $interval['start']->format('Y-m-d'),
            'end' => $interval['end']->format('Y-m-d')
        ];
    }, $merged);
}

function missingIntervals(DateTimeImmutable $requestStart, DateTimeImmutable $requestEnd, array $covered): array
{
    $covered = normaliseIntervals($covered);
    $cursor = $requestStart;
    $missing = [];

    foreach ($covered as $interval) {
        $coveredStart = new DateTimeImmutable($interval['start'], new DateTimeZone('UTC'));
        $coveredEnd = new DateTimeImmutable($interval['end'], new DateTimeZone('UTC'));
        if ($coveredEnd < $cursor) {
            continue;
        }
        if ($coveredStart > $requestEnd) {
            break;
        }
        if ($coveredStart > $cursor) {
            $missingEnd = $coveredStart->modify('-1 day');
            if ($missingEnd > $requestEnd) {
                $missingEnd = $requestEnd;
            }
            if ($missingEnd >= $cursor) {
                $missing[] = ['start' => $cursor, 'end' => $missingEnd];
            }
        }
        $afterCovered = $coveredEnd->modify('+1 day');
        if ($afterCovered > $cursor) {
            $cursor = $afterCovered;
        }
        if ($cursor > $requestEnd) {
            break;
        }
    }

    if ($cursor <= $requestEnd) {
        $missing[] = ['start' => $cursor, 'end' => $requestEnd];
    }
    return $missing;
}

function parseRecordEpoch($value): ?DateTimeImmutable
{
    // DateTime's general parser accepts relative dates and silently rolls invalid
    // calendar days forward. OMM times must identify an actual absolute instant.
    if (!is_string($value) || !preg_match(
        '/^(\d{4}-\d{2}-\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?([Zz]|[+-]\d{2}:\d{2})?$/',
        trim($value),
        $parts
    )) {
        return null;
    }
    if (!validStoredDate($parts[1]) || (int) $parts[2] > 23 || (int) $parts[3] > 59 || (int) $parts[4] > 59) {
        return null;
    }
    $zone = $parts[6] ?? 'Z';
    if (strtoupper($zone) === 'Z') {
        $zone = '+00:00';
    } elseif ((int) substr($zone, 1, 2) > 23 || (int) substr($zone, 4, 2) > 59) {
        return null;
    }
    $normalised = $parts[1] . 'T' . $parts[2] . ':' . $parts[3] . ':' . $parts[4]
        . '.' . str_pad($parts[5] ?? '', 6, '0') . $zone;
    $date = DateTimeImmutable::createFromFormat('!Y-m-d\TH:i:s.uP', $normalised, new DateTimeZone('UTC'));
    $errors = DateTimeImmutable::getLastErrors();
    return $date !== false && ($errors === false || ($errors['warning_count'] === 0 && $errors['error_count'] === 0))
        ? $date->setTimezone(new DateTimeZone('UTC'))
        : null;
}

function recordPreference(array $first, array $second): int
{
    $firstCreation = parseRecordEpoch($first['CREATION_DATE'] ?? null);
    $secondCreation = parseRecordEpoch($second['CREATION_DATE'] ?? null);
    if ($firstCreation !== $secondCreation && ($firstCreation === null || $secondCreation === null)) {
        return $secondCreation !== null ? 1 : -1;
    }
    if ($firstCreation !== null && $secondCreation !== null && $firstCreation != $secondCreation) {
        return $secondCreation <=> $firstCreation;
    }

    // Creation time takes precedence even when an older solution has a larger
    // element-set number. Compare large catalogue identifiers without float loss.
    foreach (['ELEMENT_SET_NO', 'GP_ID'] as $field) {
        $firstRaw = $first[$field] ?? null;
        $secondRaw = $second[$field] ?? null;
        $firstKnown = (is_string($firstRaw) || is_int($firstRaw)) && preg_match('/^\d+$/', (string) $firstRaw);
        $secondKnown = (is_string($secondRaw) || is_int($secondRaw)) && preg_match('/^\d+$/', (string) $secondRaw);
        if ((bool) $firstKnown !== (bool) $secondKnown) {
            return $secondKnown ? 1 : -1;
        }
        if ($firstKnown && $secondKnown) {
            $firstValue = ltrim((string) $firstRaw, '0');
            $secondValue = ltrim((string) $secondRaw, '0');
            $preference = strlen($secondValue) <=> strlen($firstValue);
            if ($preference === 0) {
                $preference = strcmp($secondValue, $firstValue);
            }
            if ($preference !== 0) {
                return $preference;
            }
        }
    }
    return 0;
}

function mergeRecords(array $existing, array $incoming, string $norad): array
{
    $byEpoch = [];
    foreach (array_merge($existing, $incoming) as $record) {
        if (!is_array($record) || (string) ($record['NORAD_CAT_ID'] ?? '') !== $norad) {
            continue;
        }
        $epoch = parseRecordEpoch($record['EPOCH'] ?? null);
        if ($epoch === null) {
            continue;
        }
        $epochKey = $epoch->format('Y-m-d\TH:i:s.u\Z');
        if (!isset($byEpoch[$epochKey])) {
            $byEpoch[$epochKey] = [$record];
        } else {
            $preference = recordPreference($byEpoch[$epochKey][0], $record);
            if ($preference > 0) {
                $byEpoch[$epochKey] = [$record];
            } elseif ($preference === 0 && !in_array($record, $byEpoch[$epochKey], true)) {
                // Preserve unresolved alternatives so the browser's integrity
                // checks can flag conflicting solutions instead of hiding them.
                $byEpoch[$epochKey][] = $record;
            }
        }
    }

    ksort($byEpoch, SORT_STRING);
    $merged = [];
    foreach ($byEpoch as $alternatives) {
        foreach ($alternatives as $record) {
            $merged[] = $record;
        }
    }
    return $merged;
}

function recordsForRange(array $records, DateTimeImmutable $start, DateTimeImmutable $end): array
{
    $endExclusive = $end->modify('+1 day');
    $selected = [];
    foreach ($records as $record) {
        if (!is_array($record)) {
            continue;
        }
        $epoch = parseRecordEpoch($record['EPOCH'] ?? null);
        if ($epoch === null) {
            continue;
        }
        if ($epoch >= $start && $epoch < $endExclusive) {
            $selected[] = $record;
        }
    }
    return $selected;
}

function writeJsonAtomically(
    string $path,
    array $payload,
    ?string $temporary = null,
    int $maximumBytes = MAX_OBJECT_BYTES
): void {
    $encoded = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    if ($encoded === false) {
        throw new RuntimeException('The persistent history cache could not be encoded.');
    }
    if (strlen($encoded) > $maximumBytes) {
        throw new LengthException('The history cache reached its object size limit. Choose a shorter date range.');
    }
    // Each caller owns the corresponding fixed lock. Fixed staging names keep
    // storage bounded even if a worker is terminated before cleanup.
    $temporary = $temporary ?? dirname($path) . DIRECTORY_SEPARATOR . 'history-write.tmp';
    if (is_link($temporary) || (pathExists($temporary) && !is_file($temporary))
        || is_link($path) || (pathExists($path) && !is_file($path))) {
        throw new HistoryRequestException(503, 'The server history storage is unavailable.');
    }
    $handle = @fopen($temporary, 'wb');
    if ($handle === false) {
        throw new HistoryRequestException(503, 'The persistent history cache could not be written.');
    }
    try {
        if (!@chmod($temporary, 0600)) {
            throw new HistoryRequestException(503, 'The persistent history cache could not be secured.');
        }
        $length = strlen($encoded);
        $written = 0;
        while ($written < $length) {
            $count = @fwrite($handle, substr($encoded, $written));
            if ($count === false || $count === 0) {
                throw new HistoryRequestException(503, 'The persistent history cache could not be written completely.');
            }
            $written += $count;
        }
        if (!@fflush($handle)) {
            throw new HistoryRequestException(503, 'The persistent history cache could not be flushed.');
        }
        $closed = @fclose($handle);
        $handle = null;
        if (!$closed || !@rename($temporary, $path)) {
            throw new HistoryRequestException(503, 'The persistent history cache could not be committed.');
        }
    } finally {
        if (is_resource($handle)) {
            fclose($handle);
        }
        if (is_file($temporary) && !is_link($temporary)) {
            @unlink($temporary);
        }
    }
}

function canonicaliseDigestValue($value)
{
    if (!is_array($value)) {
        return $value;
    }
    if ($value === [] || array_keys($value) === range(0, count($value) - 1)) {
        return array_map('canonicaliseDigestValue', $value);
    }
    $copy = $value;
    ksort($copy, SORT_STRING);
    foreach ($copy as $key => $item) {
        $copy[$key] = canonicaliseDigestValue($item);
    }
    return $copy;
}

function recordsDigest(array $records): string
{
    $canonical = canonicaliseDigestValue(array_values($records));
    $encoded = json_encode(
        $canonical,
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE
    );
    if ($encoded === false) {
        throw new RuntimeException('The persistent history cache could not be canonicalised.');
    }
    return hash('sha256', $encoded);
}

function historyStoreDigest(array $store): string
{
    $payload = [
        'version' => (int) ($store['version'] ?? 0),
        'source' => (string) ($store['source'] ?? ''),
        'norad' => (string) ($store['norad'] ?? ''),
        'intervals' => array_values(is_array($store['intervals'] ?? null) ? $store['intervals'] : []),
        'records' => array_values(is_array($store['records'] ?? null) ? $store['records'] : []),
    ];
    // Version 1 retains its original digest contract for existing caches.
    // Version 2 binds acquisition evidence and the cache update timestamp too.
    if (($store['version'] ?? null) === HISTORY_STORE_VERSION) {
        $payload['provenance'] = $store['provenance'] ?? null;
        $payload['updated_at'] = $store['updated_at'] ?? null;
    }
    $canonical = canonicaliseDigestValue($payload);
    $encoded = json_encode(
        $canonical,
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE
    );
    if ($encoded === false) {
        throw new RuntimeException('The persistent history cache metadata could not be canonicalised.');
    }
    return hash('sha256', $encoded);
}

function validStoredDate(string $value): bool
{
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $value)) {
        return false;
    }
    $date = DateTimeImmutable::createFromFormat('!Y-m-d', $value, new DateTimeZone('UTC'));
    $errors = DateTimeImmutable::getLastErrors();
    return $date !== false && ($errors === false || ($errors['warning_count'] === 0 && $errors['error_count'] === 0));
}

function validateStoredHistory(array $store, string $norad): string
{
    $version = $store['version'] ?? null;
    if ($version !== 1 && $version !== HISTORY_STORE_VERSION) {
        throw new RuntimeException('Persistent history cache version is invalid.');
    }
    if ($version === HISTORY_STORE_VERSION) {
        validateHistoryProvenance($store, $norad);
    }
    if ((string) ($store['norad'] ?? '') !== $norad) {
        throw new RuntimeException('Persistent history cache object identity does not match the request.');
    }
    $intervals = $store['intervals'] ?? null;
    $records = $store['records'] ?? null;
    if (!is_array($intervals) || !is_array($records)) {
        throw new RuntimeException('Persistent history cache structure is invalid.');
    }
    foreach ($intervals as $interval) {
        if (!is_array($interval)) {
            throw new RuntimeException('Persistent history cache contains an invalid coverage interval.');
        }
        $start = (string) ($interval['start'] ?? '');
        $end = (string) ($interval['end'] ?? '');
        if (!validStoredDate($start) || !validStoredDate($end) || strcmp($end, $start) < 0) {
            throw new RuntimeException('Persistent history cache contains an invalid coverage interval.');
        }
    }
    foreach ($records as $record) {
        if (!is_array($record) || (string) ($record['NORAD_CAT_ID'] ?? '') !== $norad) {
            throw new RuntimeException('Persistent history cache contains a record for the wrong object.');
        }
        if (parseRecordEpoch($record['EPOCH'] ?? null) === null) {
            throw new RuntimeException('Persistent history cache contains an invalid record epoch.');
        }
    }
    $recordsExpected = strtolower(trim((string) ($store['records_sha256'] ?? '')));
    if ($recordsExpected !== '') {
        if (!preg_match('/^[a-f0-9]{64}$/', $recordsExpected) || !hash_equals($recordsExpected, recordsDigest($records))) {
            throw new RuntimeException('Persistent history cache failed record SHA-256 integrity validation.');
        }
    }
    $storeExpected = strtolower(trim((string) ($store['store_sha256'] ?? '')));
    if ($storeExpected !== '') {
        if (!preg_match('/^[a-f0-9]{64}$/', $storeExpected) || !hash_equals($storeExpected, historyStoreDigest($store))) {
            throw new RuntimeException('Persistent history cache failed metadata/content SHA-256 integrity validation.');
        }
        return 'sha256-verified';
    }
    if ($recordsExpected !== '') {
        return 'records-sha256-verified';
    }
    return 'legacy-validated';
}

function exactHistoryKeys(array $value, array $expected): bool
{
    $keys = array_keys($value);
    sort($keys, SORT_STRING);
    sort($expected, SORT_STRING);
    return $keys === $expected;
}

function historyList(array $value): bool
{
    return $value === [] || array_keys($value) === range(0, count($value) - 1);
}

function validHistoryTimestamp($value): bool
{
    if (!is_string($value) || !preg_match('/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/D', $value)
        || substr($value, 0, 4) === '0000') {
        return false;
    }
    $date = DateTimeImmutable::createFromFormat('!Y-m-d\TH:i:s\Z', $value, new DateTimeZone('UTC'));
    $errors = DateTimeImmutable::getLastErrors();
    return $date !== false && ($errors === false || ($errors['warning_count'] === 0 && $errors['error_count'] === 0))
        && $date->format('Y-m-d\TH:i:s\Z') === $value;
}

function validHistoryDigest($value): bool
{
    return is_string($value) && preg_match('/^[a-f0-9]{64}$/D', $value) === 1;
}

function historyProvenanceError(): RuntimeException
{
    return new RuntimeException('Persistent history cache acquisition evidence is invalid.');
}

/** Return the covered interval for a UTC day without rescanning every range. */
function historyCoverageIndex(string $day, array $intervals): ?int
{
    $low = 0;
    $high = count($intervals) - 1;
    while ($low <= $high) {
        $middle = intdiv($low + $high, 2);
        if (strcmp($day, $intervals[$middle]['start']) < 0) {
            $high = $middle - 1;
        } elseif (strcmp($day, $intervals[$middle]['end']) > 0) {
            $low = $middle + 1;
        } else {
            return $middle;
        }
    }
    return null;
}

function validateHistoryProvenance(array $store, string $norad): void
{
    if (!exactHistoryKeys($store, ['version', 'source', 'norad', 'intervals', 'records', 'records_sha256', 'updated_at', 'provenance', 'store_sha256'])
        || $store['source'] !== 'Space-Track GP_History' || $store['norad'] !== $norad
        || !is_array($store['intervals']) || !historyList($store['intervals'])
        || !is_array($store['records']) || !historyList($store['records'])
        || !validHistoryDigest($store['records_sha256']) || !validHistoryDigest($store['store_sha256'])
        || !validHistoryTimestamp($store['updated_at']) || strcmp($store['updated_at'], gmdate('Y-m-d\TH:i:s\Z')) > 0) {
        throw historyProvenanceError();
    }
    foreach ($store['intervals'] as $interval) {
        if (!is_array($interval) || !exactHistoryKeys($interval, ['start', 'end'])
            || !is_string($interval['start']) || !is_string($interval['end'])
            || !validStoredDate($interval['start']) || !validStoredDate($interval['end'])
            || strcmp($interval['end'], $interval['start']) < 0) {
            throw historyProvenanceError();
        }
    }
    $provenance = $store['provenance'];
    if (!is_array($provenance) || !exactHistoryKeys($provenance, ['schema_version', 'policy', 'acquisitions'])
        || $provenance['schema_version'] !== HISTORY_PROVENANCE_SCHEMA_VERSION
        || $provenance['policy'] !== HISTORY_RETENTION_POLICY
        || !is_array($provenance['acquisitions']) || !historyList($provenance['acquisitions'])
        || count($provenance['acquisitions']) > MAX_HISTORY_ACQUISITIONS) {
        throw historyProvenanceError();
    }
    $coverage = [];
    foreach ($provenance['acquisitions'] as $acquisition) {
        if (!is_array($acquisition) || !exactHistoryKeys($acquisition, ['kind', 'source_class', 'start', 'end', 'retrieved_at', 'records_sha256'])
            || !in_array($acquisition['kind'], ['upstream-fetch', 'legacy-cache'], true)
            || $acquisition['source_class'] !== 'GP_HISTORY'
            || !is_string($acquisition['start']) || !is_string($acquisition['end'])
            || !validStoredDate($acquisition['start']) || !validStoredDate($acquisition['end'])
            || strcmp($acquisition['end'], $acquisition['start']) < 0
            || !validHistoryDigest($acquisition['records_sha256'])) {
            throw historyProvenanceError();
        }
        if ($acquisition['kind'] === 'legacy-cache') {
            if ($acquisition['retrieved_at'] !== null) {
                throw historyProvenanceError();
            }
        } elseif (!validHistoryTimestamp($acquisition['retrieved_at'])
            || strcmp($acquisition['retrieved_at'], $store['updated_at']) > 0
            || (new DateTimeImmutable($acquisition['start'], new DateTimeZone('UTC')))
                ->diff(new DateTimeImmutable($acquisition['end'], new DateTimeZone('UTC')))->days >= MAX_RANGE_DAYS) {
            throw historyProvenanceError();
        }
        $coverage[] = ['start' => $acquisition['start'], 'end' => $acquisition['end']];
    }
    usort($coverage, static function (array $first, array $second): int {
        return strcmp($first['start'], $second['start']);
    });
    $previousEnd = null;
    foreach ($coverage as $interval) {
        if ($previousEnd !== null && strcmp($interval['start'], $previousEnd) <= 0) {
            throw historyProvenanceError();
        }
        $previousEnd = $interval['end'];
    }
    $normalised = normaliseIntervals($store['intervals']);
    if ($normalised !== $store['intervals'] || normaliseIntervals($coverage) !== $normalised) {
        throw historyProvenanceError();
    }
    foreach ($store['records'] as $record) {
        $epoch = is_array($record) ? parseRecordEpoch($record['EPOCH'] ?? null) : null;
        if ($epoch === null || historyCoverageIndex($epoch->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d'), $coverage) === null) {
            throw historyProvenanceError();
        }
    }
}

/**
 * Old caches prove retained contents, not when those contents were downloaded.
 * Build bounded, explicitly unknown acquisition entries without rewriting them.
 */
function legacyHistoryAcquisitions(array $store, ?DateTimeImmutable $requestStart = null, ?DateTimeImmutable $requestEnd = null): array
{
    $intervals = normaliseIntervals(is_array($store['intervals'] ?? null) ? $store['intervals'] : []);
    if ($requestStart !== null && $requestEnd !== null) {
        $start = $requestStart->format('Y-m-d');
        $end = $requestEnd->format('Y-m-d');
        $intervals = array_values(array_filter($intervals, static function (array $interval) use ($start, $end): bool {
            return strcmp($interval['start'], $end) <= 0 && strcmp($interval['end'], $start) >= 0;
        }));
    }
    if (count($intervals) > MAX_HISTORY_ACQUISITIONS) {
        throw new LengthException('The retained history acquisition record reached its limit. Existing history has been preserved.');
    }
    $buckets = array_fill(0, count($intervals), []);
    foreach (is_array($store['records'] ?? null) ? $store['records'] : [] as $record) {
        $epoch = parseRecordEpoch($record['EPOCH'] ?? null);
        if ($epoch === null) {
            throw historyProvenanceError();
        }
        $day = $epoch->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d');
        $index = historyCoverageIndex($day, $intervals);
        if ($index !== null) {
            $buckets[$index][] = $record;
        } elseif ($requestStart === null && $requestEnd === null) {
            // A legacy upgrade must not invent acquisition evidence for rows
            // outside its retained coverage. Preserve the old store instead.
            throw historyProvenanceError();
        }
    }
    $acquisitions = [];
    foreach ($intervals as $index => $interval) {
        $acquisitions[] = [
            'kind' => 'legacy-cache',
            'source_class' => 'GP_HISTORY',
            'start' => $interval['start'],
            'end' => $interval['end'],
            'retrieved_at' => null,
            'records_sha256' => recordsDigest($buckets[$index]),
        ];
    }
    return $acquisitions;
}

function historyResponseProvenance(array $store, array $selected, string $norad, DateTimeImmutable $start, DateTimeImmutable $end): array
{
    $versioned = ($store['version'] ?? null) === HISTORY_STORE_VERSION;
    $acquisitions = $versioned ? $store['provenance']['acquisitions'] : legacyHistoryAcquisitions($store, $start, $end);
    $first = $start->format('Y-m-d');
    $last = $end->format('Y-m-d');
    $acquisitions = array_values(array_filter($acquisitions, static function (array $acquisition) use ($first, $last): bool {
        return strcmp($acquisition['start'], $last) <= 0 && strcmp($acquisition['end'], $first) >= 0;
    }));
    $known = count(array_filter($acquisitions, static function (array $acquisition): bool {
        return $acquisition['kind'] === 'upstream-fetch';
    }));
    return [
        'schema_version' => HISTORY_PROVENANCE_SCHEMA_VERSION,
        'provider' => 'Space-Track',
        'source_class' => 'GP_HISTORY',
        'policy' => HISTORY_RETENTION_POLICY,
        'norad' => $norad,
        'requested_range' => ['start' => $first, 'end' => $last],
        'records_sha256' => recordsDigest($selected),
        'cache_snapshot_sha256' => historyStoreDigest($store),
        'cache_updated_at' => $versioned ? $store['updated_at'] : null,
        'retrieval_status' => $known === count($acquisitions) && $known > 0 ? 'recorded' : ($known > 0 ? 'partial' : 'legacy-unknown'),
        'acquisitions' => $acquisitions,
    ];
}

function historyRetrievalTime(array $provenance): ?string
{
    if ($provenance['retrieval_status'] !== 'recorded') {
        return null;
    }
    $latest = null;
    foreach ($provenance['acquisitions'] as $acquisition) {
        if ($latest === null || strcmp($acquisition['retrieved_at'], $latest) > 0) {
            $latest = $acquisition['retrieved_at'];
        }
    }
    return $latest;
}

function fetchHistoryInterval(
    string $norad,
    DateTimeImmutable $start,
    DateTimeImmutable $end,
    string $cookieFile,
    array $upstreamContext
): array {
    $startValue = $start->format('Y-m-d') . 'T00:00:00';
    $endValue = $end->modify('+1 day')->format('Y-m-d') . 'T00:00:00';
    $queryUrl = 'https://www.space-track.org/basicspacedata/query/class/gp_history'
        . '/NORAD_CAT_ID/' . rawurlencode($norad)
        . '/EPOCH/' . rawurlencode($startValue . '--' . $endValue)
        . '/orderby/EPOCH%20asc'
        . '/limit/' . MAX_RECORDS
        . '/format/json/emptyresult/show';

    [$status, $body] = curlRequest($queryUrl, [
        CURLOPT_COOKIEJAR => $cookieFile,
        CURLOPT_COOKIEFILE => $cookieFile,
    ], $upstreamContext);
    if ($status !== 200) {
        throw new RuntimeException('Space-Track GP_History returned HTTP ' . $status . '.');
    }

    // Decode objects distinctly: an HTTP 200 error object (even {}) is not an
    // empty history and must never create permanent successful cache coverage.
    $records = json_decode($body, false, 512, JSON_THROW_ON_ERROR);
    if (!is_array($records)) {
        throw new RuntimeException('Space-Track returned an unexpected response.');
    }
    if (count($records) >= MAX_RECORDS) {
        throw new LengthException('The requested interval reached the server record limit. Choose a shorter date range.');
    }
    $validated = [];
    $endExclusive = $end->modify('+1 day');
    foreach ($records as $item) {
        if (!$item instanceof stdClass) {
            throw new RuntimeException('Space-Track returned an invalid history record.');
        }
        $record = (array) $item;
        $objectId = $record['NORAD_CAT_ID'] ?? null;
        if ((!is_string($objectId) && !is_int($objectId)) || (string) $objectId !== $norad) {
            throw new RuntimeException('Space-Track returned a record for the wrong object.');
        }
        $epoch = parseRecordEpoch($record['EPOCH'] ?? null);
        if ($epoch === null || $epoch < $start || $epoch > $endExclusive) {
            throw new RuntimeException('Space-Track returned a record outside the requested time interval.');
        }
        $creation = $record['CREATION_DATE'] ?? null;
        if ($creation !== null && $creation !== '' && parseRecordEpoch($creation) === null) {
            throw new RuntimeException('Space-Track returned an invalid record creation time.');
        }
        foreach (['MEAN_MOTION', 'ECCENTRICITY', 'INCLINATION', 'RA_OF_ASC_NODE', 'ARG_OF_PERICENTER', 'MEAN_ANOMALY'] as $field) {
            $value = $record[$field] ?? null;
            if ((!is_string($value) && !is_int($value) && !is_float($value)) || !is_numeric($value) || !is_finite((float) $value)) {
                throw new RuntimeException('Space-Track returned an invalid orbital element.');
            }
            $number = (float) $value;
            $valid = $field === 'MEAN_MOTION' ? $number > 0
                : ($field === 'ECCENTRICITY' ? $number >= 0 && $number < 1
                    : ($field === 'INCLINATION' ? $number >= 0 && $number <= 180
                        : $number >= 0 && $number < 360));
            if (!$valid) {
                throw new RuntimeException('Space-Track returned an orbital element outside its valid range.');
            }
        }
        // The upstream range may include midnight immediately after the last
        // requested day. Do not retain it as evidence for an unfetched day.
        if ($epoch < $endExclusive) {
            $validated[] = $record;
        }
    }
    return $validated;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') {
    header('Allow: GET');
    respond(405, ['ok' => false, 'message' => 'Only GET requests are supported.']);
}

foreach (['norad', 'start', 'end'] as $field) {
    if (isset($_GET[$field]) && !is_string($_GET[$field])) {
        respond(400, ['ok' => false, 'message' => "$field must be a single text value."]);
    }
}
$norad = trim($_GET['norad'] ?? '');
$startRaw = trim($_GET['start'] ?? '');
$endRaw = trim($_GET['end'] ?? '');

if (!preg_match('/^\d{1,9}$/', $norad)) {
    respond(400, ['ok' => false, 'message' => 'norad must contain 1 to 9 digits.']);
}
$norad = ltrim($norad, '0');
if ($norad === '') {
    respond(400, ['ok' => false, 'message' => 'norad must be a positive catalogue number.']);
}

$start = utcDate($startRaw, 'start');
$end = utcDate($endRaw, 'end');
if ($end < $start) {
    respond(400, ['ok' => false, 'message' => 'end must not be earlier than start.']);
}

$rangeDays = (int) $start->diff($end)->format('%a');
if ($rangeDays >= MAX_RANGE_DAYS) {
    respond(400, ['ok' => false, 'message' => 'The requested interval must contain no more than ' . MAX_RANGE_DAYS . ' calendar days, including both dates.']);
}

$yesterday = new DateTimeImmutable('yesterday', new DateTimeZone('UTC'));
if ($end > $yesterday) {
    respond(400, [
        'ok' => false,
        'message' => 'Historical requests must end no later than yesterday. Use the current CelesTrak snapshot for today.'
    ]);
}

$responseStatus = 502;
$responsePayload = ['ok' => false, 'message' => 'Historical data could not be retrieved from Space-Track.'];
$responseRetryAfter = null;
$lock = null;
$missLock = null;
$cookieFile = null;

try {
    [$identity, $password, $cacheDirectory] = readConfiguration();
    ensureDirectory($cacheDirectory);
    $clientAddress = (string) ($_SERVER['REMOTE_ADDR'] ?? '');
    // Admission applies to every valid GET before any object-specific state.
    enforceIncomingAdmission($cacheDirectory, $clientAddress);

    $storePath = $cacheDirectory . DIRECTORY_SEPARATOR . 'gp-history-' . $norad . '.json';
    $stripe = hexdec(substr(hash('sha256', $norad), 0, 4)) % OBJECT_LOCK_STRIPES;
    $lockPath = $cacheDirectory . DIRECTORY_SEPARATOR . sprintf('history-object-%02d.lock', $stripe);
    $lock = acquireHistoryLock($lockPath);

    // Read and calculate missing intervals only after obtaining the stripe.
    // Requests for the same object always recheck coverage after any wait.
    $store = [];
    $cacheIntegrity = 'empty';
    if (pathExists($storePath)) {
        $rawStore = readBoundedFile($storePath, MAX_OBJECT_BYTES);
        try {
            $decoded = json_decode($rawStore, true, 512, JSON_THROW_ON_ERROR);
        } catch (JsonException $error) {
            throw new RuntimeException('Persistent history cache contains invalid JSON.');
        }
        if (!is_array($decoded)) {
            throw new RuntimeException('Persistent history cache structure is invalid.');
        }
        $cacheIntegrity = validateStoredHistory($decoded, $norad);
        $store = $decoded;
        unset($rawStore, $decoded);
    }
    $storedRecords = mergeRecords(is_array($store['records'] ?? null) ? $store['records'] : [], [], $norad);
    $coveredIntervals = is_array($store['intervals'] ?? null) ? $store['intervals'] : [];
    $missing = missingIntervals($start, $end, $coveredIntervals);
    $fetchedIntervals = [];

    if ($missing) {
        requireCredentials($identity, $password);
        if (!function_exists('curl_init')) {
            throw new HistoryRequestException(503, 'The PHP cURL extension is not enabled on this server.');
        }

        $acquisitions = ($store['version'] ?? null) === HISTORY_STORE_VERSION
            ? $store['provenance']['acquisitions'] : legacyHistoryAcquisitions($store);
        if (count($acquisitions) + count($missing) > MAX_HISTORY_ACQUISITIONS) {
            throw new LengthException('The retained history acquisition record reached its limit. Existing history has been preserved.');
        }

        $upstreamContext = [
            'cacheDirectory' => $cacheDirectory,
            'clientAddress' => $clientAddress,
            'deadline' => monotonicSeconds() + UPSTREAM_BUDGET_SECONDS,
        ];
        // All operation-budget mutations and history commits hold this lock.
        // Preflight therefore protects the whole plan without charging unused
        // calls, and its storage headroom remains available until commit.
        $missLock = acquireHistoryLock(
            $cacheDirectory . DIRECTORY_SEPARATOR . 'history-miss.lock',
            $upstreamContext['deadline']
        );
        enforceStorageHeadroom($cacheDirectory, $storePath);
        enforceUpstreamBudget($cacheDirectory, $clientAddress, 1 + count($missing), false, $upstreamContext['deadline']);

        $cookiePath = $cacheDirectory . DIRECTORY_SEPARATOR . 'st-cookie-session';
        createSessionFile($cookiePath);
        $cookieFile = $cookiePath;

        [$loginStatus, $loginBody] = curlRequest('https://www.space-track.org/ajaxauth/login', [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => http_build_query(
                ['identity' => $identity, 'password' => $password],
                '',
                '&',
                PHP_QUERY_RFC3986
            ),
            CURLOPT_COOKIEJAR => $cookieFile,
            CURLOPT_COOKIEFILE => $cookieFile,
            CURLOPT_HTTPHEADER => ['Accept: application/json', 'Content-Type: application/x-www-form-urlencoded'],
        ], $upstreamContext);
        unset($loginBody);
        if ($loginStatus !== 200) {
            throw new RuntimeException('Space-Track authentication returned HTTP ' . $loginStatus . '.');
        }

        foreach ($missing as $interval) {
            $newRecords = fetchHistoryInterval($norad, $interval['start'], $interval['end'], $cookieFile, $upstreamContext);
            $acquisitions[] = [
                'kind' => 'upstream-fetch',
                'source_class' => 'GP_HISTORY',
                'start' => $interval['start']->format('Y-m-d'),
                'end' => $interval['end']->format('Y-m-d'),
                'retrieved_at' => gmdate('Y-m-d\TH:i:s\Z'),
                'records_sha256' => recordsDigest($newRecords),
            ];
            $storedRecords = mergeRecords($storedRecords, $newRecords, $norad);
            $recordBytes = json_encode($storedRecords, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
            if ($recordBytes === false || strlen($recordBytes) > MAX_OBJECT_BYTES) {
                throw new LengthException('The history cache reached its object size limit. Choose a shorter date range.');
            }
            unset($recordBytes);
            $coveredIntervals[] = [
                'start' => $interval['start']->format('Y-m-d'),
                'end' => $interval['end']->format('Y-m-d')
            ];
            $fetchedIntervals[] = [
                'start' => $interval['start']->format('Y-m-d'),
                'end' => $interval['end']->format('Y-m-d'),
                'records_received' => count($newRecords)
            ];
            requireUpstreamTime($upstreamContext['deadline']);
        }

        $coveredIntervals = normaliseIntervals($coveredIntervals);
        $store = [
            'version' => HISTORY_STORE_VERSION,
            'source' => 'Space-Track GP_History',
            'norad' => $norad,
            'intervals' => $coveredIntervals,
            'records' => $storedRecords,
            'records_sha256' => recordsDigest($storedRecords),
            'updated_at' => gmdate('Y-m-d\TH:i:s\Z'),
            'provenance' => [
                'schema_version' => HISTORY_PROVENANCE_SCHEMA_VERSION,
                'policy' => HISTORY_RETENTION_POLICY,
                'acquisitions' => $acquisitions,
            ],
        ];
        $store['store_sha256'] = historyStoreDigest($store);
        validateStoredHistory($store, $norad);
        requireUpstreamTime($upstreamContext['deadline']);
        writeJsonAtomically($storePath, $store);
        $cacheIntegrity = 'sha256-verified';
    }

    $selected = recordsForRange($storedRecords, $start, $end);
    $dataProvenance = historyResponseProvenance($store, $selected, $norad, $start, $end);
    $responseStatus = 200;
    $responsePayload = [
        'ok' => true,
        'source' => 'Space-Track GP_History',
        'attribution' => 'Basic SSA data from Space-Track.org, operated by USSPACECOM',
        'cached' => count($missing) === 0,
        'cache_integrity' => $cacheIntegrity,
        'norad' => $norad,
        'start' => $startRaw,
        'end' => $endRaw,
        'count' => count($selected),
        'retrieved_at' => historyRetrievalTime($dataProvenance),
        'served_at' => gmdate('Y-m-d\TH:i:s\Z'),
        'data_provenance' => $dataProvenance,
        'fetched_intervals' => $fetchedIntervals,
        'covered_intervals' => normaliseIntervals($coveredIntervals),
        'records' => $selected,
    ];
} catch (HistoryRequestException $error) {
    $responseStatus = $error->status;
    $responseRetryAfter = $error->retryAfter;
    $responsePayload = ['ok' => false, 'message' => $error->getMessage()];
} catch (LengthException $error) {
    $responseStatus = 413;
    $responsePayload = ['ok' => false, 'message' => $error->getMessage()];
} catch (JsonException $error) {
    $responseStatus = 502;
    $responsePayload = ['ok' => false, 'message' => 'Space-Track returned invalid JSON.'];
} catch (Throwable $error) {
    error_log('Satellite history endpoint: ' . $error->getMessage());
    $responseStatus = 502;
    $responsePayload = ['ok' => false, 'message' => 'Historical data could not be retrieved from Space-Track.'];
} finally {
    if ($cookieFile !== null && is_file($cookieFile) && !is_link($cookieFile)) {
        @unlink($cookieFile);
    }
    releaseHistoryLock($missLock);
    releaseHistoryLock($lock);
}

if ($responseRetryAfter !== null) {
    header('Retry-After: ' . $responseRetryAfter);
}
respond($responseStatus, $responsePayload);
