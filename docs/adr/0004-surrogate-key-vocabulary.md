---
status: accepted
date: 2026-08-09
---

# 0004: Surrogate-Key vocabulary

## Context and Problem Statement

Fastly can hold objects for months, but a collection rebuild must
be able to invalidate exactly the affected objects. Fastly purges
by Surrogate-Key; the CGI must attach keys that group objects along
the lines operations actually purge.

## Considered Options

- Per-collection, per-page, per-arch and class keys (chosen)
- Only a global key (purge everything every time)
- Per-URL purging without keys

## Decision Outcome

Chosen vocabulary, space-separated on every cacheable response:

- `all` — everything; soft-purging it is the safe whole-site
  refresh (Fastly's built-in purge-all is hard-only).
- `coll:<resolved collection>` — on pages, 404s, redirects, and the
  home page. 404s carry it because a rebuild can add a page that
  previously 404'd. The *resolved* name is used (the default
  collection resolves to NetBSD-current; a fallen-back collection
  keys its target).
- `page:<coll>:<cmd>.<sect>` — on pages, deliberately arch-free so
  all arch aliases of a machine-independent page purge as one.
- `arch:<requested>` and, when different, `arch:<canonical>` — on
  pages served under an explicit arch (the x86 machine class makes
  them differ). The requested arch is guarded by a character-class
  check because PATH_INFO is user input and the header must not be
  injectable.
- `home`, `notfound`, `redirect` — class keys.
- `form` — on HTML that embeds the arch/collection lists; purged
  when the lists change. Goes away when the JS query form lands.
- The health check carries only `all`.

Token syntax uses colons (URL-path-safe in the purge API); the
allowed character set is `[A-Za-z0-9._:-]`.

### Consequences

- Good, because the routine operation is one soft purge:
  `manno-purge coll:NetBSD-current` after the daily pull.
- Good, because a single page fix purges all its arch aliases.
- Bad, because objects cached without keys (before this design, or
  if key emission ever breaks) are unreachable by key purge —
  recovery is Fastly's UI purge-all (runbook).

## More Information

Fastly strips both Surrogate headers toward clients; nginx forwards
them (necessary — Fastly must see keys on nginx cache hits), so
direct-to-origin clients observe them. Keys on 304 revalidations
refresh Fastly's key set. See `../runbook.md` for the
purge-decision table.
