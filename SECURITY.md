# SatSift security

This repository contains a research screening prototype that can access authenticated Space-Track history through a server-side endpoint.

## Credentials

Never commit or paste any real Space-Track password, session cookie, cached history store or hosting credential into this repository, an issue, a pull request, CI output or a public web directory.

The real configuration file is intentionally excluded from Git:

```text
.space-track-config.php
```

Use only `config/.space-track-config.php.example` in source control.

## Runtime data

Keep `.satellite-maneuver-cache/` outside the public document root with restrictive filesystem permissions. Do not serve cache files directly.

The history endpoint applies separate incoming-request and upstream-operation quotas, bounded lock waits and retained-storage limits. All workers must use the same private cache directory for coordination. Cached reads still use incoming admission, while upstream operations require the serial download lock and a charge for each attempted call. Corrupt admission controls stop requests rather than resetting their budget. The [deployment guide](DEPLOYMENT.md#history-endpoint-limits) records the limits, disk-headroom requirement and worker-drain procedure for upgrades.

## Public routes

Production routing must use the explicit allowlist in `deployment/site-root.htaccess`. Do not restore a general rule that maps arbitrary `/satsift/...` or legacy application paths into the physical project directory.

Encoded route aliases and traversal paths are rejected before public routing; supported canonical redirects remain usable. The physical project namespace is checked against both the decoded route and the decoded original request, while allowlisted internal rewrites remain usable.

The only intended public application routes are the workbench, documentation, benchmark pages/files, accessibility page, pinned browser assets and the clean `/history` endpoint.

Detector responses use CSP, `nosniff`, referrer, frame and permissions policies. The deployment template emits HSTS within the detector namespace, including when the hosting proxy terminates TLS before Apache. Browsers apply this policy only over HTTPS. The template does not trust a client-supplied forwarding header and does not use `includeSubDomains` or preload.

## Reporting a problem

For security-sensitive findings, use [GitHub private vulnerability reporting](https://github.com/sylvesterkaczmarek/satsift/security/advisories/new). Include the affected version, reproduction steps and expected impact without including real credentials or private orbital histories. Do not place credentials, exploit details affecting the live server, or sensitive Space-Track material in a public issue.

## Scope

The workbench is a research prototype and is not approved for operational SSA, conjunction assessment, flight safety or autonomous decision-making. Security hardening of this repository does not constitute certification of the hosting environment.
