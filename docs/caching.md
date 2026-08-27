# Caching architecture

man.netbsd.org serves rendered manual pages through three cache
tiers:

    Browser -> Fastly (CDN) -> nginx (FastCGI cache) -> fcgiwrap -> man-cgi

Every tier is steered by its own response header, all emitted by the
CGI's `emit_cache_headers` function:

| Header | Consumed by | Notes |
|--------|-------------|-------|
| `Cache-Control` (+ `Expires`) | Browsers | Also the fallback for the other tiers if their header is missing |
| `X-Accel-Expires` | nginx | Highest priority for nginx's cache; stripped before the response goes upstream to Fastly |
| `Surrogate-Control` | Fastly | Preferred over Cache-Control at Fastly; stripped before the response reaches clients |
| `Surrogate-Key` | Fastly | Purge groups (see the runbook); stripped toward clients, but forwarded to clients that reach nginx directly |

The guiding principle: **browsers cache briefly** (they cannot be
purged), **nginx briefly** (an expired entry costs only a 304
revalidation, and purging nginx is crude), **Fastly long** (purgeable
by Surrogate-Key at any time).

## TTL policy

| Class | Cache-Control (browser) | X-Accel-Expires (nginx) | Surrogate-Control (Fastly) |
|-------|------------------------|------------------------|---------------------------|
| current / -BRANCH page | `public, max-age=3600` | 3600 | `max-age=86400, stale-while-revalidate=3600, stale-if-error=604800` |
| release page | `public, max-age=86400` | 86400 | `max-age=7776000, stale-while-revalidate=86400, stale-if-error=604800` |
| home page | `public, max-age=7200` | 7200 | `max-age=86400, stale-while-revalidate=3600, stale-if-error=604800` |
| 404 | `public, max-age=3600` | 3600 | `max-age=86400, stale-if-error=86400` |
| 302 collection fallback | `public, max-age=3600` | 10800 | `max-age=86400, stale-if-error=86400` |
| 301 canonicalization | `public, max-age=86400` | 86400 | `max-age=2592000, stale-if-error=604800` |
| api lists (`/api/v1/*`) | `public, max-age=3600` | 3600 | `max-age=604800, stale-while-revalidate=3600, stale-if-error=604800` |
| health check | `public, max-age=30` | 30 | `max-age=30` |
| 303 (POST form) | `no-store` | — | — |

`stale-if-error` lets Fastly keep serving an object while the
origin fails: a week for what should outlive an outage, a day for
what has to stop soon anyway (404s, the 302 of ADR-0015), and none
for the health check, which must not report stale health. Fastly
acts on it by itself only for a backend its health check calls
sick; a backend that answers 5xx or cannot be reached needs
`return(deliver_stale)` in the service VCL, in `vcl_fetch` and
`vcl_error` respectively. The generated boilerplate has neither
(service version 5, of 2026-08-08, the day before the header first
appeared); without them a 5xx is cached for a second and served.
`fastly.md` has the snippets and the Fastly references.

The page class branches on the **resolved** collection: the default
collection (NetBSD-current) takes the frequently-rebuilt arm even
though `COLL` is empty by the time headers are emitted. (Before
2026-08-09 the `*-current` match could never fire for the default
collection, so NetBSD-current pages were accidentally cached for 90
days at every tier.)

A multi-match menu (ADR-0012) takes the page class too: it ages
with the collection it describes.

`Last-Modified` is the mtime of the manual page's source file (found
via `man -w`), clamped to at least `MINLASTMOD` — a floor embedded
in the CGI and bumped whenever a script change alters rendered
output (ADR-0011), so such changes reach every tier through normal
revalidation instead of cache wipes. A validator already above the
floor does not move, which is what a bump followed by a newer
NetBSD-current build runs into; `deployment.md`, step 8, has the
condition and the choices.

Responses that describe the **collection** rather than one page —
404s and multi-match menus — take their mtime from the resolved
collection's `tmac/mdoc.local`. Every file the pull extracts carries
the upstream build's timestamp, that one included, so it moves
exactly when the collection's contents move. The `build` file is
not used for this: it records when the *pull ran*, so it advances
daily whether or not anything new arrived, and it exists only for
NetBSD-current and the branches — every frozen release goes without
one, which would leave those 404s and menus with no validator at
all. `tmac/mdoc.local` is present in every collection, back to
NetBSD-6.0.

The home page keeps the NetBSD-current `build` file, which is also
the health check's liveness probe. The `/api/v1` list endpoints
clamp the same way as pages, with the embedded sectlist using the
floor alone.

A collection missing its `tmac/mdoc.local` (a partial or broken
extract) has no validator and never returns 304. That is not a
staleness risk: with no validator nginx refetches on expiry, which
is always current. It only costs a render a 304 would have avoided.

## Conditional requests

The CGI answers `If-Modified-Since` with a **304** when the client's
value is byte-identical to the `Last-Modified` it would send. The
304 carries the full caching-header block (Cache-Control, Expires,
X-Accel-Expires, Surrogate-Control, Surrogate-Key), so nginx
refreshes the entry's validity on revalidation, and it skips the
expensive render entirely — the origin cost drops to a `man -w` and
a `stat`. What nginx then serves, to clients and to Fastly, is the
header block it stored with the body; only a full response replaces
it. A change to the headers alone therefore travels like a change
to the markup: through the `MINLASTMOD` bump (ADR-0011), which
moves the validator and turns the next revalidation into a full
fetch.

Exact string match is a complete test, not an approximation: with
caching enabled, nginx never forwards client conditionals to the
FastCGI backend, so the only `If-Modified-Since` the CGI ever sees
in production is nginx's own revalidation echoing the CGI's
`Last-Modified` back (see `tests/nginx-lab/README.md` for the
measurements). Any mismatch falls through to a full response.

Client conditionals are answered without origin involvement:

- Fastly answers 304s from its own cache — for cached **200s**
  only; a conditional request for a cached 404 gets the full 404
  (observed live). 404 revalidation still pays off at the nginx
  tier.
- nginx answers 304s from its cache (valid entries and fresh fills)
  via its not-modified filter.
- Only when nginx's entry has expired does a conditional round trip
  reach the CGI — as nginx's revalidation, answered with the 304
  fast path (`fastcgi_cache_revalidate on`).

Redirects and POST responses can never turn into 304s: they are
emitted before the conditional check runs.

## Cache behavior notes

- **nginx TTL semantics**: `X-Accel-Expires` governs validity for
  responses of *any* status; the `fastcgi_cache_valid` directive is
  a fallback that only applies when the response carries no caching
  headers. Expired entries are not deleted — they are kept for
  revalidation and evicted only by `inactive=365d` or the
  `max_size` LRU (500 GB on oxygene, 88 GB on lcm).
- **Fastly cacheability**: with the boilerplate VCL, only statuses
  200, 203, 300, 301, 302, 404, and 410 are cacheable. This is why
  canonicalization redirects are 301 rather than 308 (ADR-0005):
  308s were passed through to nginx on every request. 503s
  (including the health check's) are likewise not cached at Fastly.
- **Shielding**: the Fastly service shields through one POP
  (hel-helsinki-fi), so origin traffic concentrates there and edge
  POPs fill from the shield.
- **Purging**: see the runbook. Only objects that carry
  Surrogate-Keys can be purged by key; everything cached since the
  2026-08-09 cutover does.

## Size dynamics

The nginx cache was 110 GB before the 2026-08-09 wipe, mostly
bot-crawled URL space (arch aliases of machine-independent pages).
Shorter TTLs do **not** shrink disk usage — expired entries stay on
disk for revalidation — so the cache regrows toward one object per
crawled URL. The canonical-arch redirects (ADR-0009) collapse the
alias multiplier: up to ~60 arch aliases per MI page become one
page object plus tiny redirect objects. The full effect appears
only after crawlers re-follow the new 301s.

## Sample response headers

As emitted by the CGI (QA, uncached vhost, 2026-08-27; nginx's own
`Vary` and security headers omitted):

    HTTP/1.1 200 OK
    Content-Type: text/html; charset=windows-1252
    Last-Modified: Thu, 27 Aug 2026 04:43:31 GMT
    Expires: Thu, 27 Aug 2026 19:20:25 GMT
    Cache-Control: public, max-age=3600
    Surrogate-Control: max-age=86400, stale-while-revalidate=3600, stale-if-error=604800
    Surrogate-Key: all coll:NetBSD-current page:NetBSD-current:ls.1

Here `Last-Modified` is the `MINLASTMOD` floor itself, the commit
time of that day's output change: `ls.1`'s own mtime is older, so
the floor is the validator. (`X-Accel-Expires` is absent from
every observed response because nginx consumes it even on the
uncached QA vhost.)

The 304, same request with `If-Modified-Since` echoed:

    HTTP/1.1 304 Not Modified
    Last-Modified: Thu, 27 Aug 2026 04:43:31 GMT
    Expires: Thu, 27 Aug 2026 19:20:27 GMT
    Cache-Control: public, max-age=3600
    Surrogate-Control: max-age=86400, stale-while-revalidate=3600, stale-if-error=604800
    Surrogate-Key: all coll:NetBSD-current page:NetBSD-current:ls.1

Through Fastly, clients additionally see `X-Man-Cache` (nginx's
cache status for the stored object), `X-Cache`/`X-Served-By`
(Fastly's), and `Age`; the Surrogate headers are gone.
