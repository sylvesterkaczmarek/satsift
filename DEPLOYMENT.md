# Deployment

SatSift is deployed into a dedicated directory beneath the site root. The public source repository is `sylvesterkaczmarek/satsift`, and the canonical workbench URL is `https://www.sylvesterkaczmarek.com/satsift/`. The previous public HTML routes redirect permanently. Existing machine URLs and the physical application directory retain compatibility with cached browser sessions and private history storage. Hosting paths and SSH connection details are supplied locally and are not part of this repository.

## Public files

The deployment tool uploads the application files beneath the configured site root:

```text
<site-root>/tools/satellite-maneuver-detector/
```

The existing installation contains these ten required mutable application files:

```text
index.html
app-3.4.js
history.php
docs.html
benchmark.html
accessibility.html
benchmark-template.json
public-evidence-manifest-v0.1.json
plotly-3.3.1.min.js
satellite-6.0.2.min.js
```

The release also uploads the fixed public `dependency-notices.txt` bundle. It contains the complete project and browser-component notices, source attributions and inventories. The file may be absent before the first deployment that introduces it. The transaction records that initial absence and restores it on rollback. No licence source directory is exposed or recursively uploaded.

Generate or check the committed bundle after changing its source notices:

```bash
python3 tools/build_browser_notices.py
python3 tools/build_browser_notices.py --check
```

The builder validates every inventory-referenced path and digest, rejects symlinks and preserves each source file's original bytes inside a deterministic text bundle. Deployment refuses stale bundle bytes.

Do not upload repository-only material such as `.github/`, `tests/`, `review/`, `config/`, `.gitignore`, `KNOWN-ISSUES.md` or this file into the public detector folder.

The browser graph adds seven immutable JavaScript files in the application's `app/` directory. Their public filenames contain the first 12 hexadecimal characters of their SHA-256:

```text
app/common-<hash>.js
app/orbital-input-<hash>.js
app/benchmark-<hash>.js
app/packages-<hash>.js
app/detection-<hash>.js
app/interface-<hash>.js
app/bootstrap-<hash>.js
```

`browser-assets.json` declares the six canonical module source files in dependency order and the `app-3.4.js` entry source. `tools/browser_assets.py` derives the exact destination filenames, full SHA-256 values and browser integrity attributes. The deployer stages only these reviewed source files under their computed destination names, then transfers each approved file individually. It does not traverse or synchronize a source directory wholesale. Canonical source paths such as `/app/common.js`, the manifest, helpers and other repository files are not public routes.

After a browser source change, refresh the entry's fallback asset list and HTML references, then verify and commit the resulting metadata:

```bash
python3 tools/update_browser_assets.py
python3 tools/update_browser_assets.py --check
```

The check is read-only and deployment refuses stale references. A changed dependency changes its filename, the entry's fallback list and the hashed bootstrap filename. Every HTML module script and fallback request carries the full SHA-256 integrity value. The legacy `app-3.4.js` alias remains available for previously cached HTML; it loads the exact hash-addressed module graph recorded in its own bytes.

## Local deployment configuration

Set the site root in your local environment before using either deployment mode:

```bash
export SMD_REMOTE_SITE_ROOT='<site-directory-relative-to-ssh-home>'
```

Replace the placeholder with your actual hosting path. The tool has no default destination and stops before running any command when this setting is missing. It accepts only a normalised relative path made from simple directory names. Absolute paths, parent or dot segments, spaces, empty segments and shell syntax are rejected. Keep the real value in your local environment or a private wrapper outside the repository.

Configure an OpenSSH profile locally. The default profile name is the generic `smd-production`:

```sshconfig
Host smd-production
    HostName <hosting-hostname>
    User <hosting-user>
    IdentityFile ~/.ssh/<authorised-key>
```

To use an existing profile with another name, set `SMD_SSH_ALIAS` locally. The tool checks that the selected profile resolves to a configured hostname and user. It does not print the connection details or configured site destination. Do not commit real hostnames, usernames, key paths, credentials or resolved SSH configuration.

The hosting account must already contain the following paths beneath the configured site root:

```text
tools/satellite-maneuver-detector/
.htaccess
robots.txt
sitemap.xml
```

The deployment tool updates an existing installation. All ten required mutable application files and the three site-root files must already exist so they can be backed up and restored. The notice bundle is the only optional mutable target during its first installation; any existing target must be a regular non-symlink file. The immutable `app/` directory and new hash-named targets may be absent during the first module deployment. If a current hash-named target already exists, its full SHA-256 must match the source exactly; a collision or corrupted target stops deployment before an upload. Existing hash-named assets from earlier releases are retained.

## Load local deployment settings

For repeated use, keep the exported target variables in an untracked `.env.deployment` file with owner-only permissions. The repository ignores `.env` files. Load the trusted local file in your shell before running the deployer:

```sh
. ./.env.deployment
```

The deployer reads environment variables; it does not automatically read or execute local configuration files.

## Repeatable deployment command

From a clean checkout, preview the complete deployment first:

```bash
python3 tools/deploy_production.py --dry-run
```

The preview makes read-only SSH requests and invokes individual `rsync --dry-run` transfers where the destination parent already exists. On the first module deployment, the new `app/` directory may be absent. The preview then validates and lists all seven immutable assets but explicitly omits their remote transfer simulations. It does not create the directory: some rsync implementations create implied parent directories even during a relative-path dry run. Existing application and site-root targets are still simulated. When the immutable directory already exists, every planned transfer is simulated.

A real upload requires the explicit execution flag:

```bash
python3 tools/deploy_production.py --execute
```

A real deployment is accepted only from a clean `main` branch whose commit exactly matches both the local `origin/main` tracking ref and the authoritative `origin` branch reported by GitHub. The `origin` URL itself must be the canonical repository. Both modes report the full Git commit, require the named SSH profile, validate that the configured site root resolves exactly beneath the SSH home and that the application directory is beneath that site root, reject symlinked target directories and files, require strict host-key checking, disable SSH forwarding/local commands, and use individual allowlisted writes without `--delete`. No research, review, test, benchmark-result, private configuration or cache path can enter the application upload plan.

Before site-root writes, the tool reads the existing `.htaccess`, `robots.txt` and `sitemap.xml` and prepares merged replacements in a temporary local directory. The detector-owned main `.htaccess` block is replaced in place and a separate, narrowly scoped compatibility route block is placed before the main rewrites, the detector directives are merged into the single existing `User-agent: *` robots policy, and only detector-owned URLs are replaced in the sitemap. Unrelated rules, crawler groups, sitemap URLs and XML comments are retained. Exact known legacy managed-marker names are migrated to SatSift names. Repeated merges are byte-idempotent. Ambiguous or malformed site-root input stops the operation instead of being guessed at.

Immediately before a real upload, the tool atomically acquires `.satellite-maneuver-deploy.lock`, repeats the target and existing immutable-file checks, verifies that the three site-root files have not changed since they were read and creates a private backup of the ten required mutable application files, the notice bundle if present, and three site-root files. A private absence marker records a notice target that does not yet exist. The backup is stored under `.satellite-maneuver-deploy-backups/<commit-prefix>-<run-id>/`, in the SSH home, outside the configured site root and with a restrictive umask. Only after this backup does it create the fixed immutable asset directory if needed.

Dependencies and immutable browser assets are uploaded first, followed by site-root files and routing. All seven immutable browser assets must pass full SHA-256 verification before the mutable `app-3.4.js` alias is activated. `index.html` is the final upload. The complete release is then checked by SHA-256.

An upload, interruption or hash failure restores the previous mutable application and site content. Rollback retains the approved immutable files already uploaded, earlier immutable releases and the independent narrow compatibility route block. This allows HTML or bootstrap bytes cached during the attempted release to continue resolving their recorded dependencies. The retained block supports the new canonical pages, both public machine-resource namespaces and the same scoped security headers. Restored old main rules and cached new pages can therefore continue resolving resources without exposing the physical directory. The previous main rules and unrelated host content are preserved; the exact original `.htaccess` also remains in the private backup. There is no automatic pruning of immutable assets.

Rollback validates the site, application and immutable-directory boundaries before writing restored files. If restoration cannot be confirmed, for example after a connection loss or a changed directory boundary, the command reports the private backup location, leaves the deployment lock as an incomplete-release signal and refuses to claim success. Static-file rollback does not modify retained history or reverse history-cache schema changes; the coordination requirements below still apply.

The tool never reads, writes, copies or deletes `.space-track-config.php` or `.satellite-maneuver-cache/`.

## Optional cache purge

Cache invalidation is a separate post-upload action. Create a narrowly scoped, user-owned executable wrapper outside the repository. The wrapper should invoke the legitimate authenticated provider CLI or profile with the exact purge scope. Expose only its absolute path in the local environment:

```bash
export SMD_CACHE_PURGE_COMMAND='/absolute/path/to/private/purge-wrapper'
```

The deployer accepts only an absolute, non-symlink executable file owned by the current user and located outside the repository. It passes no arguments and invokes no shell. The wrapper is run only after a successful, hash-verified `--execute` upload, and its path and output are suppressed to avoid leaking provider details. A dry run reports only whether a valid wrapper is configured. If the variable is absent, the deployer clearly reports that an authorized manual purge remains required; it does not invent a provider or endpoint.

## Site routing

Use both marked blocks in `deployment/site-root.htaccess` as the detector-related baseline for `<site-root>/.htaccess`. Keep the independent compatibility block before the main managed rules and any host rules that would otherwise reject those clean public URLs.

The immutable route accepts only the seven reviewed filename stems followed by a 12-character hexadecimal digest and `.js`. It requires a matching clean original request, an existing physical file and non-symlink asset/file paths. Missing targets, unrecognised names and canonical module sources remain unavailable. Immutable caching applies only to successful or not-modified module responses. Failed public requests receive `Cache-Control: no-store`, preventing a premature request from caching a missing future hash. The same narrow block is retained when an earlier mutable release is restored.

If the site root contains unrelated rules, merge the detector rules carefully rather than deleting unrelated site configuration.

A legacy application-directory `.htaccess` may still exist. Do not remove or rewrite it without inspecting its ownership and purpose. Explicit public mappings use Apache 2.4 `[END]` to stop subsequent per-directory rewrite processing; the first block denies direct physical requests before any mapping. The executable Apache regression includes a conflicting nested rule to verify this boundary.

## Private Space-Track configuration

Keep the real configuration and cache outside the public document root. The PHP endpoint looks for `.space-track-config.php` in the parent of the server's `DOCUMENT_ROOT`; its default cache directory is `.satellite-maneuver-cache` in that same private parent. Verify the server's document-root setting when installing on shared hosting.

Alternatively, supply `SPACETRACK_IDENTITY`, `SPACETRACK_PASSWORD` and `SATELLITE_HISTORY_CACHE_DIR` through the PHP process environment. These values take precedence over the configuration file. The cache path must remain outside every directory served by the web server. Deployment target settings do not change PHP's document root or credential discovery.

Start from `config/.space-track-config.php.example`. Never upload the real credential file to GitHub.

Recommended permissions when the hosting panel allows them:

```text
.space-track-config.php       600
.satellite-maneuver-cache/    700
```

## History endpoint limits

`history.php` applies incoming-request admission after cheap request validation and before opening an object lock or allocating object-specific cache state. Cached responses also consume this incoming budget. Client identity uses the server-provided remote address; forwarded headers do not select the quota identity. Configure any trusted proxy at the web-server boundary so that unrelated visitors do not inadvertently share one address.

| Resource | Limit |
| --- | --- |
| Incoming requests per client | 60 per rolling 15 minutes |
| Incoming requests across the endpoint | 240 per rolling 15 minutes |
| Space-Track operations per client | 12 per rolling 15 minutes |
| Space-Track operations across the endpoint | 20 per rolling hour |
| Wait for each filesystem lock | 500 milliseconds |
| Concurrent upstream download sessions | 1 |
| Total upstream time per incoming request | 30 seconds |
| Body of each upstream response | 4 MiB |
| Headers of each upstream response and stored session cookies | 64 KiB each |
| Outgoing history response | 8 MiB |
| Stored history per object | 8 MiB |
| Retained history across the cache | 128 objects and 128 MiB |
| Each admission control file | 64 KiB |
| Entries inspected during a capacity scan | 1,024 |

These application safeguards assume all PHP workers share one private cache directory on a filesystem that provides working advisory locks and atomic rename. Separate cache directories or servers with independent files do not share quotas. The web server still needs its own connection and worker limits, since PHP admission runs after a request has reached a worker.

A cache miss holds one fixed download/storage lock until all fragments have been validated and the combined history is committed. Before login, it checks capacity and the available quota for one login plus every missing interval. Each attempted login and history fetch is charged immediately before its cURL call, including failed attempts. An unused planned call is not charged. A fully cached request requires no credentials, changes no history file and consumes no upstream budget.

The cache uses 64 fixed object-lock stripes, so arbitrary catalogue identifiers cannot create an unbounded collection of lock files. A stripe remains held through the cache recheck, missing-range calculation, upstream work and atomic commit. Distinct objects sharing a stripe may briefly contend. Each lock wait is bounded; a contended request can retry later without duplicating a completed fetch. Other cache hits can proceed while the download/storage lock is held.

Capacity checks preserve existing history. Before a download, the endpoint reserves room for a full 8 MiB replacement of the current object, subtracting that object's existing size from the retained total. This conservative check can decline an extension even when its eventual response might have been small. The 128 MiB limit measures retained history, not the entire directory: allow additional disk headroom for atomic staging, bounded control files, lock files and the active session. The endpoint does not evict stored history or expire covered dates to make space.

Quota exhaustion returns HTTP 429 with a computed `Retry-After`. Lock contention or unavailable capacity returns HTTP 503. A request whose fragment plan can never fit a fresh upstream quota returns HTTP 413 with guidance to select a shorter range; oversize upstream responses also fail without committing partial coverage. Malformed, oversized or unsupported admission controls fail closed. Existing cached-history validation and SHA-256 checks remain in force.

## Upgrading history coordination

When changing history lock coordination or cache schemas, stop new history traffic and allow existing PHP requests to finish before activating the endpoint revision. The SatSift URL and interface migration preserves the existing cache and coordination model. Then replace the endpoint and restart or reload the affected workers. The old per-object lock files and new lock stripes must never be used concurrently by different deployed revisions. The deployment script does not drain workers automatically; coordinate this step with the hosting service.

Keep the private cache and its existing `rate-limits.json` ledger. The previous ledger counted cache misses rather than individual upstream calls. When creating the separate `upstream-limits.json` operation ledger, the endpoint therefore observes a conservative cooldown until one hour after the latest valid legacy timestamp. The legacy ledger is retained unchanged. Cached reads remain available during that transition. A malformed legacy ledger blocks upstream work until an operator investigates it. Do not remove or reset quota files during an active budget window to bypass admission.

Do not delete old lock files while any old worker can still hold them. Review retained data and capacity privately before a later release; changing limits or moving data requires a coordinated maintenance operation. Automatic eviction and automatic historical refetching are not part of this upgrade.

## History acquisition records

New history commits use cache schema 2, binding acquisition metadata and the cache update time into the full-store digest. Existing schema 1 stores remain readable without a write on cache hits. An extension preserves inherited coverage with explicitly unknown acquisition times and commits the new data and evidence together. Do not run older and newer endpoint revisions concurrently while migrating store schemas; drain and reload the affected workers as described above. Keep history traffic paused until the deployed release has passed verification. After schema 2 stores have been written, an older endpoint cannot read them: a rollback needs a schema 2-capable reader or a separately reviewed restoration that preserves all acquired data. Never delete a newer cache to make older code run.

Keep the private history cache and its original source artefacts. A cache purge used for static site assets must not delete retained GP history. There is no automatic historical expiry or public correction/refetch route. The [history policy](HISTORY-POLICY.md) defines current-GP append, explicit local corrections, source identities and legacy limitations. A browser correction affects its selected analysis; any change to the retained server cache requires a separately reviewed maintenance operation.

## No command-line install step

Plotly.js and satellite.js are already committed as pinned static assets. satellite.js is available at startup for SGP4 screening; Plotly is loaded from its same-site pinned asset only when charts or 3D context are requested. No server-side package manager or vendor installer is required.

The initial HTML uses ordered deferred classic scripts for the six modules and thin bootstrap. Their physical public filenames are content-addressed and their integrity attributes check the full SHA-256. The pinned startup satellite.js URL retains its content-derived query version; Plotly remains an on-demand dependency. No JavaScript build, package installation, dynamic code evaluation or additional framework is required.

Keep immutable hash files available across releases and rollbacks because cached documents can reference earlier graphs. Do not overwrite a hash-named file with different bytes. The local Python server derives current hash routes directly from canonical source files; it serves only the current graph and rejects canonical module URLs and unknown hashes. Production instead keeps previously deployed immutable files for cached clients.

## Verification after deployment

Run the read-only production verifier from the same commit that was deployed:

```bash
python3 tools/verify_production.py
```

It sends no-cache requests, bounds response sizes, rejects unexpected cross-origin redirects, derives all seven immutable browser URLs and the versioned satellite.js URL, checks ordered deferred scripts and their integrity attributes, compares every module, hashed bootstrap, legacy alias and pinned dependency with the repository bytes and checks the workbench version declared in `package.json`, detector method 0.4, UTC-safe OMM parsing, precise TLE replay and versioned run identity, deterministic catalogue supersession, lazy Plotly loading, clean canonical routes, security headers, physical/private path denial, a deliberately invalid and non-secret-bearing history request, benchmark version wording, robots/sitemap policy and known stale implementation markers. It also verifies the complete notice bundle, the Plotly distribution bytes, one-hop permanent redirects with query preservation, and directly served legacy machine resources. It performs only HTTP GET requests and makes no deployment, cache or upstream Space-Track mutation.

Check these routes:

```text
/satsift/
/satsift/docs
/satsift/benchmark
/satsift/benchmark/manifest
/satsift/benchmark/template
/satsift/accessibility
/satsift/dependency-notices.txt
```

The public `/benchmark/manifest` route intentionally serves the small v0.1 Workbench seed/runner-format manifest. It is not the frozen publication benchmark v1.0 under `public-evidence-manifest-v1.0.json`; do not relabel or substitute one for the other during deployment.

Then verify:

1. `?demo=leo` runs automatically and produces a result.
2. A short historical request loads through `/satsift/history`.
3. The current CelesTrak snapshot loader works.
4. Regression checks pass in the developer section.
5. Direct `/tools/satellite-maneuver-detector/...` requests are rejected.
6. Source `.php`, `.md`, config and cache paths remain unavailable. `dependency-notices.txt` is the sole allowlisted text download.
7. Every public detector route returns CSP, `nosniff`, referrer, frame and permissions headers; detector responses also carry `Strict-Transport-Security: max-age=31536000`. The routing template supports TLS termination at a reverse proxy; browsers apply HSTS only when received over HTTPS.
8. Canonical `/app/common.js` source URLs and unknown hash names remain unavailable. All seven intended immutable URLs return the exact repository bytes.
9. The initial workbench response does not request Plotly; the pinned Plotly asset is requested on demand when analysis charts or 3D context are rendered.

The production server must continue to keep Space-Track credentials outside the public web root.

## Apache route verification

Run the executable route regression before releasing the routing template:

```bash
python3 tests/apache_route_boundary_test.py
```

This requires Apache 2.4 with its prefork, rewrite and headers modules. On Ubuntu, the `apache2-bin` package provides the binary and modules; on macOS the test also discovers the system Apache. A missing binary or module fails the check. The test creates synthetic files, a temporary configuration and a loopback listener. Apache runs in a separate process session, and cleanup signals only that session. It does not read hosting configuration, contact the live site or change a system service.

Apache [matches RewriteRule patterns against decoded paths](https://httpd.apache.org/docs/2.4/mod/mod_rewrite.html#rewriterule), while `THE_REQUEST` retains the original request line. The retained compatibility routing block therefore checks the decoded namespace against a literal public-route allowlist before any file mapping. The physical-path guard also decodes the original request using Apache's [unescape expression function](https://httpd.apache.org/docs/2.4/expr.html#functions). These checks reject encoded and traversal aliases without interpreting query values as paths. Intended trailing-slash and legacy-URL redirects remain usable.

The regression exercises actual HTTP responses for clean routes and security headers, encoded queries, direct and encoded physical paths, traversal, immutable assets, symlinks, rollback routing and unrelated site rewrites. It also checks both namespaces, exact permanent redirect destinations, query preservation, a conflicting nested `.htaccess`, and encoded slashes with the hosting option enabled. This is a local routing check; the production verifier and a controlled deployment remain separate steps.
