---
status: accepted
date: 2026-08-09
---

# 0002: Three-tier caching with per-tier TTLs

## Context and Problem Statement

Responses pass three caches (browser, Fastly, nginx's FastCGI
cache), but historically a single `Cache-Control` header steered
all of them: whatever TTL suited browsers also pinned nginx and
Fastly, so NetBSD-current pages — rebuilt daily — could be served
stale for up to 90 days, and nothing could be invalidated remotely.
How should the tiers get lifetimes matching what each can do?

## Considered Options

- One `Cache-Control` for everything (status quo)
- Per-tier headers: `Cache-Control` for browsers, `X-Accel-Expires`
  for nginx, `Surrogate-Control` + `Surrogate-Key` for Fastly
- Very short TTLs everywhere and no purging

## Decision Outcome

Chosen option: per-tier headers, emitted by one class-driven
function (`emit_cache_headers`) in the CGI. Browsers cache briefly
(they cannot be purged), nginx briefly (an expired entry costs only
a 304 revalidation), Fastly long but purgeable by key. The policy
table lives in `../caching.md`; each header is consumed and
stripped by its tier, and `Cache-Control` doubles as the fallback
for a tier whose header is missing.

### Consequences

- Good, because a collection rebuild becomes visible within an hour
  at the latest (current pages), or immediately after a soft purge.
- Good, because origin load stays low: long-lived edge objects
  refresh via cheap 304 revalidations instead of full re-renders.
- Bad, because the header block is larger and the TTL policy now
  lives in code rather than in one nginx directive.
- Bad, because nginx has no purge mechanism: content mistakes that
  outlive their nginx TTL require a cache wipe (runbook).

## More Information

The 90-day default-collection TTL turned out to be an accident (the
`*-current` pattern could never match the default collection, whose
name is emptied before TTL selection); fixed as part of this
change. Supersedes the TTL increases of April 2026 (RCS 1.92-1.94),
which coped with load by caching longer — revalidation plus purging
now serve that goal without the staleness.
