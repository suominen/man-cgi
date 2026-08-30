# nginx FastCGI cache lab

A disposable rig for verifying nginx FastCGI cache behaviour against
a synthetic backend, used to settle design questions empirically
before touching production configuration.

- `fcgi-backend.py` — minimal FastCGI responder (127.0.0.1:9481).
  Emits a fixed `Last-Modified` and `Cache-Control: max-age=2`;
  answers 304 when `HTTP_IF_MODIFIED_SINCE` matches exactly; logs
  every request's received `If-Modified-Since` to `requests.log`.
- `nginx-base.conf` — unprivileged nginx (127.0.0.1:8481) with
  `fastcgi_cache` and `fastcgi_cache_revalidate on`; the
  `#CLEAR_IMS#` marker is where the `drive` script injects
  conditional-clearing params for the second variant, and
  `#USE_STALE#` where `drive-stale` injects production's
  `use_stale`/`background_update` pair.
- `drive` — runs both variants through six scenarios and prints
  client-visible status/cache-state plus what the backend saw.
- `drive-redirect` — reruns the conditional scenarios with the
  backend answering 301 instead of 200 (`LAB_STATUS`), to compare
  how nginx treats cached redirects against cached pages.
- `drive-stale` — runs the expiry scenario with
  `fastcgi_cache_use_stale ... updating` and
  `fastcgi_cache_background_update` on and off, for a 200 and a
  301 backend, to see which request receives the refreshed
  response.

- `drive-reject` — starts nginx with the request rejection maps
  (ADR-0020; `-m` names the `conf.d` directory holding
  `probe-map.conf`, `man-cgi-syntax-map.conf` and
  `query-string-map.conf`, default `~/tmp/oxygene-nginx/conf.d` or
  `./maps`) and the vhost's `if` blocks from
  `reject-locations.conf` (both entry locations) and
  `redirect-query.conf` (`location /` only), then sends a table of
  accepted, refused and redirected requests, checking the status
  of each and whether the backend saw it. The two fragments must
  track the vhost (and `mancgi.j2`/`fqdn.j2` once the Ansible port
  lands): they are what this driver measures.

Run it on the NetBSD test host:

    rsync -a tests/nginx-lab/ kimmo@equinoxe:nginx-lab/
    ssh kimmo@equinoxe sh nginx-lab/drive

The other drivers run the same way (`sh nginx-lab/drive-redirect`,
`sh nginx-lab/drive-stale`; for `drive-reject` also rsync the three
map files into `nginx-lab/maps/` and pass `-m nginx-lab/maps`).
`drive-reject` also runs on any host with nginx, curl and python3.

## Results (2026-08-09, nginx 1.30.4 on NetBSD 11.0)

Variant `plain` (`fastcgi_cache_revalidate on`, nothing else):

| Scenario | Client saw | Backend saw |
|----------|------------|-------------|
| 1 cold GET | 200 MISS | no IMS, sent 200 |
| 2 warm GET | 200 HIT | (not contacted) |
| 3 warm GET + client IMS | **304** HIT | (not contacted) |
| 4 expired GET | 200 REVALIDATED | stored Last-Modified as IMS, sent 304 |
| 5 flushed cache + client IMS | **304** MISS | **no IMS**, sent 200 (cache filled) |
| 6 plain GET after that | 200 HIT | (not contacted) |

Variant `clear-ims` (adds `fastcgi_param HTTP_IF_MODIFIED_SINCE "";`
and `HTTP_IF_NONE_MATCH ""`):

| Scenario | Client saw | Backend saw |
|----------|------------|-------------|
| 4 expired GET | 200 **EXPIRED** | **no IMS**, sent 200 (full refetch) |

Conclusions:

1. `fastcgi_cache_revalidate on` alone is correct and sufficient.
2. The fastcgi module withholds client conditionals from the backend
   when caching is enabled (observed directly: the backend logs the
   If-Modified-Since it receives, and received none), and nginx
   itself answers client conditionals with 304 both against a warm
   cache entry (scenario 3) and against the response it just fetched
   on a miss (scenario 5). There is no miss-plus-If-Modified-Since
   fill-starvation case to defend against.
3. Explicitly clearing `HTTP_IF_MODIFIED_SINCE` via `fastcgi_param`
   also overrides the revalidation header nginx injects, silently
   disabling revalidation. Do not add it.

## Redirects are not revalidated (2026-08-24, nginx 1.30.4)

`drive-redirect` runs the same scenarios against the same nginx
twice, with `LAB_STATUS=200` and `LAB_STATUS=301`, so the status
code is the only difference. The backend emits a `Last-Modified` in
both cases, and the 301's `Location` carries the request serial so a
stale redirect is distinguishable from a fresh one.

| Scenario | 200 | 301 |
|----------|-----|-----|
| cold GET | 200 MISS | 301 MISS, `/target-1` |
| warm GET + matching client IMS | **304** HIT | **301** HIT (no 304) |
| expired GET | 200 **REVALIDATED**, backend saw IMS and sent 304 | 301 **EXPIRED**, backend saw **no IMS**, full refetch, `/target-2` |

Conclusions:

1. nginx does no conditional handling for cached redirects — it
   neither sends `If-Modified-Since` upstream when one expires nor
   answers a client's conditional with 304 — even though the cached
   301 carries a `Last-Modified`. This matches HTTP: 304 is defined
   for a request that would otherwise be answered 200, and a
   redirect has no representation to validate.
2. So a `Last-Modified` on a redirect would be inert at nginx, and
   `MINLASTMOD` (ADR-0011) cannot reach redirects. They refresh
   only by expiring or by a cache wipe, which is why a change that
   stops a URL redirecting has to wait out the redirect's nginx
   TTL (see `../../docs/runbook.md`).
3. The flip side is that expiry is always a *full* refetch, so a
   redirect can never be pinned stale by a 304 the way a page can.
   Shortening `X-Accel-Expires` for the redirect classes is the only
   lever on how long the wait is (ADR-0015 did).

## Stale hand-off under background update (2026-08-25, nginx 1.30.4)

`drive-stale` adds production's `fastcgi_cache_use_stale ...
updating` at the `#USE_STALE#` marker and runs the expiry scenario
with `fastcgi_cache_background_update` on and off, for a 200 and a
301 backend. The 301's `Location` carries the backend serial, so
the old and the refreshed object are told apart.

| Scenario | on, 200 | off, 200 | on, 301 | off, 301 |
|----------|---------|----------|---------|----------|
| cold GET | 200 MISS | 200 MISS | 301 MISS `/target-1` | 301 MISS `/target-1` |
| expired GET (triggers the refresh) | 200 **STALE** | 200 **REVALIDATED** | 301 **STALE** `/target-1` | 301 **EXPIRED** `/target-2` |
| next GET | 200 HIT | 200 HIT | 301 HIT `/target-2` | 301 HIT `/target-2` |

The backend saw the same two requests in every run — the cold fill
and one refresh, with `If-Modified-Since` (answered 304) for the
200 and without for the 301 — so the setting changes only *who*
receives the refreshed response, not how often the origin is asked.

Conclusions:

1. With background update on, the request that finds the entry
   expired is answered from the stale copy and the refresh runs
   behind it. A Fastly soft purge's refetch is usually exactly that
   request, so a purge re-cached the old object for another Fastly
   TTL — the "repeat until they match" the runbook used to
   prescribe.
2. With it off, the triggering request waits for the refresh and
   receives the fresh response. The `updating` parameter still
   hands the stale copy to requests arriving while a refresh is in
   progress (not exercised here: the lab is single-client).
   ADR-0015 turns it off in production.

## Request rejection maps (2026-08-30, nginx 1.30.4 on NetBSD; 1.26.3 on Debian)

`drive-reject` ran its table (100 lines) against the map files as
first applied on oxygene (ADR-0020) on both hosts with no failures:
every accepted shape (page paths, collection and arch indexes,
`g++.1`, `g%2B%2B.1`, `[.1`, `nsswitch.conf`, `Mail.1`, `CA.pl`,
`revbump.py`, `//ls.1`, the API lists and the health check, the
legacy query forms at `/cgi-bin/man-cgi` with and without the
tolerated trailing `=`, GET, HEAD and POST at `/` and
`/cgi-bin/man-cgi`, page paths with tracking parameters)
reached the backend with a 200; every probe path, grammar
violation, disallowed method and off-grammar query string was
answered 404 (with `Surrogate-Key: all notfound nginx-reject`),
405 (with `Allow: GET, HEAD`) or 400 without a backend request;
so was every direct `/cgi-bin/man-cgi/<path info>` hit, path info
being what the `/` rewrite produces; and every other query string
on `/` or a page path was answered with a 301 to the path as sent
(`/g%2B%2B.1?utm_source=x` → `/g%2B%2B.1`, keyed `all redirect
nginx-redirect`), the rejections still coming first.
The `maps=` column of the output is the five verdicts (probe, uri,
method, query, qs) the lab exposes as `X-Lab-Maps`, so a 404 is
attributable to the map that produced it.

Findings from the first runs that shaped the maps: `POST
/cgi-bin/man-cgi` — the query form's real target — was a 405 while
the method map demanded a trailing slash, and the same requirement
let `/cgi-bin/man-cgi?x=1` through the site query map; `/api/v2/x`
passed the page charset although the CGI answers 404 for any
`/api` path outside `/api/v1/`; a generic `\.(pl|py|cgi)$` probe
rule would have refused sectionless requests for the real pages
`CA.pl(1)`, `openssl-CA.pl(1)` and `revbump.py(1)`; and after the
`rewrite ^ /cgi-bin/man-cgi$request_uri last` in `location /`,
`$uri` is `/cgi-bin/man-cgi/?ls+1` — the query string copied in
after a literal `?` — which the page rule would refuse if the maps
were re-evaluated. They are not: nginx caches a map's value for
the request, so the CGI location's `if` blocks see the `location
/` verdicts. Adding `volatile` to `$man_bad_uri` flipped every
rewritten line with a query string to 404; the maps must never carry it. Paths under
`/cgi-bin/` that the nested CGI regex does not match
(`/cgi-bin/donate.py`, `/cgi-bin/`) never reach the `if` blocks:
the outer location's own `return 404` answers them.
