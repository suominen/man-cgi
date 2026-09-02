---
status: amended by ADR-0022
date: 2026-08-25
---

# 0015: Short-lived redirects and deterministic purges

## Context and Problem Statement

Cached redirects were the one response class the caching design
could not correct without an nginx wipe. nginx never revalidates a
cached redirect conditionally (`../../tests/nginx-lab/`), so the
`MINLASTMOD` floor (ADR-0011) does not reach them, and the
permanent redirects (ADR-0005) were held 30 days at nginx: every
change that made a URL stop redirecting or redirect elsewhere
(ADR-0009, ADR-0012, and more of the kind on the TODO list)
needed the wipe, with its refill storm. The collection-fallback 302 was held 24
hours at nginx and 7 days at Fastly, so a new release stayed
invisible under its own name for up to a week unless purged.

Separately, a Fastly soft purge did not reliably refresh anything:
purged objects refill from nginx, and with
`fastcgi_cache_background_update on` the request that finds an
nginx entry expired — usually the purge-triggered fetch itself —
is answered from the stale copy while the refresh runs behind it.
The purge re-cached the old object for another full Fastly TTL,
and the runbook prescribed "purge, compare, repeat; a couple of
rounds is normal".

## Considered Options

- Keep the 30-day and 7-day holds and wipe nginx on every
  redirect-shape change
- Shorten the redirects' nginx and Fastly TTLs (chosen)
- Shorten them all the way to an hour at nginx
- Keep background update on and rely on shorter TTLs alone for
  purges
- Turn `fastcgi_cache_background_update` off, keeping
  `fastcgi_cache_use_stale ... updating` (chosen)

## Decision Outcome

Chosen option: shorter redirect TTLs, and background update off.

The 302 collection fallback is held 1 hour by browsers, 3 hours by
nginx and a day by Fastly (was 24 hours / 24 hours / 7 days). The
301 canonicalization redirects keep 24 hours in browsers and 30
days at Fastly, but nginx now holds them 24 hours instead of 30
days. Both classes stay purgeable at Fastly by the `redirect` key
(ADR-0004).

`fastcgi_cache_background_update` is off in the nginx
configuration; `fastcgi_cache_use_stale ... updating` stays. The
request that finds an entry expired now waits for the refresh and
receives the fresh response; requests that arrive while that
refresh is in progress still get the stale copy. The lab
(`drive-stale`) showed the origin is asked exactly as often either
way — the setting only changes who receives the refreshed
response.

Why these numbers: nginx cannot revalidate a redirect, so its
expiry is a full refetch, but the refetch is the cheapest work the
CGI does — the 302 and the legacy-URL 301s are emitted before
`man -w`; the section and arch 301s cost one `man -w` and no
render — comparable to the 404 revalidations that already run
hourly. Fastly's shield holds the objects for their Fastly TTL, so
nginx sees only Fastly's misses. A day for the 301s is where a
redirect that should no longer exist stops mattering without
turning the crawled redirect URL space into hourly refetches; 3
hours for the 302 is what a release announcement can wait.

### Consequences

- Good, because the nginx wipe leaves both redirect procedures: a
  redirect-shape deploy is "deploy, wait a day, `manno-purge
  redirect`", and a release is live under its own name within 3
  hours plus one purge.
- Good, because one purge is now deterministic once nginx's entry
  has expired — up to the rare fetch that lands while another
  request's refresh is in flight, which is why "confirm at the
  edge" stays in the procedure — and the runbook can say "purge
  once and confirm" instead of "repeat until they match".
- Good, because a wrong 301 lives a day at nginx instead of a
  month (its browser hold was always 24 hours).
- Bad, because the first requester after any expiry — usually
  Fastly's shield — waits for the revalidation instead of getting
  a stale answer: a 304 round trip for pages, a full but cheap
  refetch for redirects, a render only when the content actually
  changed.
- Bad, because redirect refetches at the origin are now up to 30×
  (301) and 8× (302) more frequent per nginx-held URL; bounded by
  Fastly's shield hold and by the cost of the response.
- Neutral: objects cached before this change keep the TTL they
  were filled with and age out on their own; they need no wipe
  either.

## Pros and Cons of the Options

### Keep the long holds and wipe on every redirect-shape change

- Good, because nothing changes and the origin sees the fewest
  redirect refetches.
- Bad, because the wipe is the most expensive operation in the
  runbook (newfs, nginx stopped per host, refill storm with 502s)
  and the trigger has fired twice in two weeks.

### Shorter TTLs (chosen)

- Good, because the wipe leaves the procedures and the response is
  cheap to refetch.
- Bad, because the redirect refetch rate at the origin rises.

### An hour at nginx for the 301s

- Good, because a wrong 301 is gone in an hour.
- Bad, because redirects cannot 304, so unlike the hourly 404
  revalidations these would be full refetches, 24× as often as the
  chosen value, across the crawled redirect URL space (up to ~60
  arch aliases per page), for no operational gain: Fastly is
  purgeable either way, and nothing waits on a 301 the way a
  release waits on the 302.

### Background update on, shorter TTLs alone

- Good, because it is a CGI-only change.
- Bad, because it does not address the purge problem at all: the
  purge-triggered fetch is served stale after expiry regardless of
  how short the TTL is, so every purge still re-caches the old
  object once.

### Background update off, `updating` kept (chosen)

- Good, because one purge becomes deterministic and the herd
  protection for expiries stays (`fastcgi_cache_lock` covers only
  MISS fills).
- Bad, because the first requester after expiry pays the
  revalidation latency.

## More Information

Amends ADR-0005 (whose consequence "cached 30 days in nginx with
no purge mechanism" is now a day) and ADR-0009 (same consequence
for the canonical-arch redirects). Their records keep their
original wording; this one carries the change. The policy table
is in `../caching.md`; the nginx side is in `../nginx.md` and
lives in the `cloud` repository's `mancgi.j2`. Measurements:
`../../tests/nginx-lab/README.md` ("Redirects are not revalidated"
and "Stale hand-off under background update").
