---
status: amended by ADR-0018, ADR-0021
date: 2026-08-09
---

# 0008: JS query form fed by plain-text list endpoints

## Context and Problem Statement

Every HTML page embedded the full architecture and collection lists
in its query form, so a colllist change (each NetBSD release)
invalidated every cached page at every tier, and frozen-collection
pages at nginx — which revalidate forever — kept serving stale
lists indefinitely. How should the form get its lists without
coupling every page's cacheability to them?

## Considered Options

- Inline JavaScript fetching versioned plain-text list endpoints,
  with server-rendered fallback options (chosen)
- Keep embedding the lists (status quo)
- A JSON API and/or an external static JS asset
- Cookies for remembering the user's arch/collection

## Decision Outcome

Chosen option: the server renders only fallback options (NONE plus
the request's own arch; the resolved collection) and an inline
script — a heredoc beside the inline CSS, no separate asset to
deploy — populates the selects from `/api/v1/archlist` and
`/api/v1/colllist`. Selection precedence: URL-carried value
(passed via a `data-url` attribute), then the remembered value from
`localStorage` (`man-cgi.arch`/`man-cgi.coll`, saved on submit),
then the default. The section list is script-embedded and shared
(`list_sections`) between the form, the intro table, and
`/api/v1/sectlist`.

Endpoint specifics: versioned under `/api/v1/` (per Kim), newline-
delimited `text/plain` — the lists are flat token lists, so JSON
would add parsing for no gain and the format matches the source
files; `Last-Modified` validators make them revalidatable; unknown
`/api` paths 404 with their own purge keys instead of falling into
URL canonicalization.

localStorage, not cookies: nothing varies per user at any cache
tier, and no request grows a cookie header.

### Consequences

- Good, because archlist/colllist changes now invalidate two tiny
  API objects instead of every cached page, and the nginx
  frozen-page staleness window for lists disappears entirely.
- Good, because arch/collection stickiness works across the
  canonical (arch-less) URLs that a later step will redirect to.
- Bad, because without JavaScript the selects offer only the
  current values — the command field and section select still work,
  and man-page URLs remain fully navigable, so the degradation is
  mild.
- Bad, because a DEFAULT entry in a no-default deployment loses its
  `(OS-release)` annotation when rendered client-side — not the
  production configuration.

## More Information

Keys: pages no longer carry `form`; the API objects carry
`all api form <name>`. See ADR-0004 (which anticipated this) and
`../runbook.md` for the purge flows.
