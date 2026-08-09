---
status: accepted
date: 2026-08-09
---

# 0005: 301 (not 308) for canonicalization redirects

## Context and Problem Statement

The CGI permanently redirects non-canonical URLs (legacy query
strings, sectionless requests, extra path components) and
originally used 308 Permanent Redirect. Fastly's default VCL caches
only statuses 200, 203, 300, 301, 302, 404, and 410 — so every 308
passed through the edge to nginx, and the long Surrogate-Control on
them was inert. Should the redirects be 301, or should custom VCL
make 308 cacheable?

## Considered Options

- Switch to 301 Moved Permanently
- Keep 308 and add a VCL cacheability override
- Keep 308 and accept that nginx absorbs all redirect traffic

## Decision Outcome

Chosen option: 301. The distinguishing property of 308 — method
preservation — is never load-bearing here: POST requests are
answered with a 303 (whose defined job is the POST-to-GET switch)
before any canonicalization runs, so only GETs and HEADs ever
receive the permanent redirects, for which 301 and 308 are
equivalent. 301
gets Fastly caching with zero configuration; the active service
runs boilerplate VCL and stays that way.

### Consequences

- Good, because permanent redirects are now cached and purgeable at
  the edge (`redirect` key), instead of hitting nginx every time.
- Good, because no custom VCL enters the picture.
- Bad, because a wrong 301 is doubly durable: purgeable at Fastly
  but cached 30 days in nginx with no purge mechanism (runbook
  covers recovery).

## More Information

Fastly's default-cacheability list:
<https://www.fastly.com/documentation/guides/concepts/edge-state/cache/cache-freshness>.
Browsers' "301 cached forever" folklore is bounded by the explicit
`Cache-Control: max-age=86400` on these responses.
