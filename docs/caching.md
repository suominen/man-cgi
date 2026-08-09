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
| home page | `public, max-age=7200` | 7200 | `max-age=86400, stale-while-revalidate=3600` |
| 404 | `public, max-age=3600` | 3600 | `max-age=86400, stale-if-error=86400` |
| 302 collection fallback | `public, max-age=86400` | 86400 | `max-age=604800` |
| 301 canonicalization | `public, max-age=86400` | 2592000 | `max-age=2592000` |
| health check | `public, max-age=30` | 30 | `max-age=30` |
| 303 (POST form) | `no-store` | — | — |

The page class branches on the **resolved** collection: the default
collection (NetBSD-current) takes the frequently-rebuilt arm even
though `COLL` is empty by the time headers are emitted. (Before
2026-08-09 the `*-current` match could never fire for the default
collection, so NetBSD-current pages were accidentally cached for 90
days at every tier.)

`Last-Modified` is the mtime of the manual page's source file (found
via `man -w`); for 404s it is the mtime of the resolved collection's
`build` file and for the home page the NetBSD-current `build` file,
so those revalidate as well. A 404 in a collection that has no
directory has no validator and never returns 304.

## Conditional requests

The CGI answers `If-Modified-Since` with a **304** when the client's
value is byte-identical to the `Last-Modified` it would send. The
304 carries the full caching-header block (Cache-Control, Expires,
X-Accel-Expires, Surrogate-Control, Surrogate-Key) so both nginx and
Fastly refresh entry validity and purge keys on revalidation, and it
skips the expensive render entirely — the origin cost drops to a
`man -w` and a `stat`.

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
disk for revalidation — so the cache will regrow toward one object
per crawled URL. The planned canonical-arch redirects (TODO step 13)
are what collapses the alias multiplier: up to ~60 arch aliases per
MI page become one page object plus tiny redirect objects.

## Sample response headers

As emitted by the CGI (QA, uncached vhost, 2026-08-09):

    HTTP/1.1 200 OK
    Content-Type: text/html; charset=windows-1252
    Last-Modified: Sat, 08 Aug 2026 13:15:15 GMT
    Expires: Sun, 09 Aug 2026 09:31:44 GMT
    Cache-Control: public, max-age=3600
    Surrogate-Control: max-age=86400, stale-while-revalidate=3600, stale-if-error=604800
    Surrogate-Key: all form coll:NetBSD-current page:NetBSD-current:ls.1

(`X-Accel-Expires` is absent from every observed response because
nginx consumes it even on the uncached QA vhost.)

The 304, same request with `If-Modified-Since` echoed:

    HTTP/1.1 304 Not Modified
    Last-Modified: Sat, 08 Aug 2026 13:15:15 GMT
    Expires: Sun, 09 Aug 2026 09:32:12 GMT
    Cache-Control: public, max-age=3600
    Surrogate-Control: max-age=86400, stale-while-revalidate=3600, stale-if-error=604800
    Surrogate-Key: all form coll:NetBSD-current page:NetBSD-current:ls.1

Through Fastly, clients additionally see `X-Man-Cache` (nginx's
cache status for the stored object), `X-Cache`/`X-Served-By`
(Fastly's), and `Age`; the Surrogate headers are gone.
