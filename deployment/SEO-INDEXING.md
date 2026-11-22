# SatSift indexing contract

SatSift owns four public HTML documents and its Apache route blocks. The website owns the root `robots.txt` and `sitemap.xml`. Deployment merges the reviewed SatSift policy into those files while preserving unrelated pages, crawler groups and comments.

## Canonical public pages

| Page | Canonical URL |
| --- | --- |
| Workbench | https://www.sylvesterkaczmarek.com/satsift/ |
| Documentation | https://www.sylvesterkaczmarek.com/satsift/docs |
| Benchmark status | https://www.sylvesterkaczmarek.com/satsift/benchmark |
| Accessibility | https://www.sylvesterkaczmarek.com/satsift/accessibility |

The workbench root has a trailing slash. The three subpages do not. Every document declares `index, follow`, one exact canonical URL, a matching OpenGraph URL, the SatSift site name, a Twitter summary card and valid JSON-LD identifying its canonical page. Active navigation and asset URLs use `/satsift/`.

## Previous public URLs

The previous `/satellite-maneuver-detector` root and its documentation, benchmark and accessibility pages redirect with HTTP 301 to the corresponding canonical URL. This includes their trailing-slash and `.html` forms. Redirects preserve query strings and do not redirect unrelated similarly named website paths.

Previous history, manifest, template and browser-asset URLs remain direct compatibility routes. They preserve HTTP methods, request bodies and queries. Previously deployed content-addressed modules remain available for cached browser documents. These compatibility routes are deliberate and must not be removed by a broad text replacement.

The site keeps its existing private storage layout. Direct requests for physical application paths remain forbidden. The public URL migration does not move or expose the retained history cache.

## Resources outside the sitemap

History responses, benchmark JSON, JavaScript and `dependency-notices.txt` carry `X-Robots-Tag: noindex, nofollow, nosnippet`. They do not belong in the sitemap. Neither do physical application paths, credentials, caches or source files.

The complete licence bundle is an intentional public download. Its name does not grant access to other `.txt`, `.md`, `.json` or source files.

## Robots policy

`deployment/robots-detector-snippet.txt` supplies the SatSift policy for the existing `User-agent: *` group. The deployer removes superseded owned rules and inserts the current policy exactly once. Multiple wildcard groups, a wildcard group shared with other adjacent User-agent headers, or malformed managed markers stop deployment.

Both public page namespaces stay crawlable so search engines can see the permanent redirects. History and benchmark machine endpoints remain specifically disallowed in both namespaces. The physical application namespace remains disallowed and is also denied by Apache.

JavaScript required for page rendering remains crawlable. Its separate noindex header prevents the resource from becoming a standalone search result. The root declaration remains:

```text
Sitemap: https://www.sylvesterkaczmarek.com/sitemap.xml
```

## Sitemap policy

`deployment/sitemap-detector-fragment.xml` is a valid XML document used as the reviewed list of four owned URLs. It is an input to the merge, never a replacement for the website's complete sitemap. The deployer removes stale old or new SatSift entries and inserts only the four canonical pages. Unrelated URLs and XML comments survive.

Repeated robots, sitemap and routing merges produce identical bytes. Legacy managed marker names are migrated only when their exact known delimiters are present. Unknown, duplicate or ambiguous application rules outside the owned blocks require review.

## Verification

`tests/indexing_config_test.py` checks canonical, social and structured metadata, active links, route declarations and the sitemap inputs. `tests/apache_route_boundary_test.py` exercises actual Apache redirects, queries, retained machine routes, private-path denial and rollback behaviour. `tools/verify_production.py` checks the deployed pages, exact asset and notice hashes, actual redirect chains, root robots policy and sitemap.
