---
status: accepted
date: 2026-08-11
---

# 0011: MINLASTMOD floor folds script changes into Last-Modified

## Context and Problem Statement

Every `Last-Modified` validator was a file mtime (page source or a
collection `build` file), so changes to the CGI script itself — the
sed HTMLizer, the embedded section list, query-form defaults, cache
headers — never moved a validator. Frozen-release objects
revalidate indefinitely under exact-match 304s (ADR-0003), so
output-affecting deploys required nginx cache wipes to propagate.
Separately, `/api/v1/sectlist` used the script's own mtime, which
churned its validator on every deploy, output-affecting or not.

## Considered Options

- A manually bumped `MINLASTMOD` epoch floored into every validator
- Fold the script's own mtime into every validator
- An ETag covering script version plus file mtime
- Status quo: wipe the nginx caches on output-affecting deploys

## Decision Outcome

Chosen option: a manually bumped `MINLASTMOD` (seconds since the
epoch, set to the checkin time of any change that alters rendered
output). Every validated response emits
`max(file mtime, MINLASTMOD)`; the embedded sectlist, having no
backing file, uses the floor alone (also dropping a `stat`).

The script's own mtime was rejected because it over-invalidates:
every deploy — comment-only fixes, signature updates — would move
every validator and trigger a full cache refill. A manual bump
makes invalidation a deliberate act. An ETag stays rejected for the
reasons in ADR-0006. Signature and `MANCGI_DATE` changes are
excluded from the bump by policy: they are not load-bearing page
content, and they reach caches through normal TTL expiry of
non-frozen objects.

### Consequences

- Good, because cache wipes become an immediacy tool rather than a
  correctness requirement: after a bump, every tier converges
  through normal expiry and revalidation.
- Good, because the sectlist validator is stable across deploys
  that do not change output.
- Good, because the exact-string 304 path (ADR-0003) is unchanged —
  the clamp happens before the validator is formatted.
- Bad, because it relies on discipline: a forgotten bump reproduces
  the old gap (the runbook's wipe procedure still covers that).
- Bad, because a bump eventually refreshes every cached object —
  a full origin refill spread over the TTLs. Intended, but a bump
  is not free.

## More Information

Relates to ADR-0003 (exact-match revalidation), ADR-0006 (no ETag),
and ADR-0008 (list endpoints). The floor is testable via the
`MANCGI_MINLASTMOD` override, honored only outside a gateway
context like the other `MANCGI_*` variables; the harness pins it
below all fixture stamps (`tests/lib.sh`, `tests/t/minlastmod`).
