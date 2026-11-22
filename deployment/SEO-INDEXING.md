# SatSift indexing contract

The detector repository owns the four public HTML documents and the site-level Apache routing template. The main sylvesterkaczmarek.com website owns the root `robots.txt` and root `sitemap.xml`, so those two files must be merged at the website root when this release is deployed.

## Indexable public HTML URLs

Exactly these detector URLs are intended to be indexable:

- `https://www.sylvesterkaczmarek.com/satellite-maneuver-detector`
- `https://www.sylvesterkaczmarek.com/satellite-maneuver-detector/docs`
- `https://www.sylvesterkaczmarek.com/satellite-maneuver-detector/benchmark`
- `https://www.sylvesterkaczmarek.com/satellite-maneuver-detector/accessibility`

Each corresponding repository HTML file declares `index, follow` and a self-referencing clean canonical URL.

## Non-indexable detector resources

Do not add any of the following to the sitemap:

- `/satellite-maneuver-detector/history`
- `/satellite-maneuver-detector/benchmark/manifest`
- `/satellite-maneuver-detector/benchmark/template`
- any `.js`, `.json` or `.php` resource
- any `/tools/satellite-maneuver-detector/...` physical path
- private Space-Track configuration or cache paths

`deployment/site-root.htaccess` emits `X-Robots-Tag: noindex, nofollow, nosnippet` for the clean history/JSON machine endpoints and deployed JavaScript assets. Direct physical `/tools/satellite-maneuver-detector/...` requests are forbidden.

## Legacy URLs

The site-level rewrite template explicitly redirects these legacy forms with HTTP 301:

- `/satellite-maneuver-detector.html` -> `/satellite-maneuver-detector`
- `/satellite-maneuver-detector/docs.html` -> `/satellite-maneuver-detector/docs`
- `/satellite-maneuver-detector/benchmark.html` -> `/satellite-maneuver-detector/benchmark`
- `/satellite-maneuver-detector/accessibility.html` -> `/satellite-maneuver-detector/accessibility`

Legacy `.html` detector URLs must not appear in `sitemap.xml`.

## Root robots.txt integration

Merge `deployment/robots-detector-snippet.txt` into the existing `User-agent: *` policy. Remove any broader `Disallow: /satellite-maneuver-detector/` rule, because it would also block the public docs, benchmark and accessibility pages. Keep the specific disallows for the history and JSON machine endpoints and the physical `/tools` namespace.

The root robots file should contain the normal sitemap declaration:

`Sitemap: https://www.sylvesterkaczmarek.com/sitemap.xml`

Do not block the clean JavaScript assets required to render the page; crawler rendering should be able to fetch them even though the assets themselves carry `X-Robots-Tag: noindex`.

## Root sitemap.xml integration

Merge the four entries from `deployment/sitemap-detector-fragment.xml` into the existing site sitemap. Remove any obsolete detector `.html` entry and any detector API, JSON, PHP, JavaScript or physical `/tools` entry if present.

The detector fragment is intentionally not a complete standalone sitemap because replacing the site's root sitemap would remove unrelated website pages.
