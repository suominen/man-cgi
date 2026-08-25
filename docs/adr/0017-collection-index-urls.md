---
status: accepted
date: 2026-08-25
---

# 0017: Collection index URLs

## Context and Problem Statement

`/NetBSD-11.0` and `/NetBSD-11.0/` answered the 404 page. The
PATH_INFO parser splits on `/`, a trailing slash yields no field,
and the one-component arm took its component as a page name, so a
collection name alone was looked up as a page. `/<coll>/<arch>/`
and `/<arch>/` failed the same way, with the arch as the name. The
only index of a collection was the legacy query-string form
`/cgi-bin/man-cgi?++<coll>`, which `canonical_url` emitted for
every empty name, so the POST form with an empty name and a release
chosen sent the browser there too.

A collection needs an index URL in the path layout, and the parser
needs to tell a collection, an arch and a page name apart when a
component stands alone.

## Considered Options

- Path indexes: `/<coll>/` is the collection's home page, `/<coll>`
  canonicalizes to it, and an arch alone names no page and goes to
  the index (chosen)
- A trailing-slash rewrite at nginx
- Serve both `/<coll>` and `/<coll>/`, no redirect
- Recognize an arch alone only with a trailing slash

## Decision Outcome

Chosen option: the index of a collection is `/<coll>/`, and that
is the canonical URL for an empty name. The rules:

- `/<coll>/` renders the home page -- the intro table and the
  query form -- with every link scoped to the collection and the
  form preselecting it. `/<coll>` is a 301 to it: the trailing
  slash is now meaningful, which the parser judges from
  `PATH_INFO` itself since the split cannot see it.
- The default collection's index is `/`, and `/<default-coll>/` is
  a 301 to it, so the home page gains no alias.
- The collection fallbacks, release-to-branch and not-yet-built,
  fire first, as they do for pages: `/NetBSD-9.3/` is one 302 to
  `/NetBSD-9.x-BRANCH/`.
- A collection that does not exist, with no name to look up, is a
  404 (`BADCOLL`, through `rejected`, which also cancels the 301),
  never a 301 to a 404. A collection name with a character outside
  its set is now rejected whole rather than repaired, as an arch or
  a page name already was: repaired, `/NetBSD-10.1*/` would have
  served the NetBSD-10.1 index -- the first response with no page
  lookup behind it to fail -- and `/NetBSD-10.1*/ls.1` its page.
  The 404 is keyed under the default collection.
- A component standing alone is a collection only when it is
  shaped like one, `NAME-REL` with a release that starts with a
  digit or is `current`. A page name can start with an uppercase
  letter too -- Mail(1), X(7), the X11 API: 2,823 of the names on
  oxygene -- and asked for alone it has no collection in front of
  it; none of them has the collection shape. Followed by another
  component, an `[A-Z]*` component is the collection, as before.
- A component in `archlist` is an arch, not a page name, with or
  without a slash. An index carries no arch -- ADR-0009 moved the
  arch out of the URL and into the remembered form -- so `/i386/`
  and `/<coll>/i386` are 301s to the collection's index; so is
  `/<coll>/i386/x86/`, where the last component is still not a
  page name and the arch in front is the one validated. `archlist`
  is the set `sanitize_arch` validates against, so the names the
  form offers and the names a URL treats as an arch are one set.
- A trailing slash on a page URL, `/ls.1/`, is an alias and
  collapses with a 301, the way an extra path component does.
- The legacy query string with an empty name, `?++<coll>`,
  redirects like every other legacy URL, and the POST form with an
  empty name goes to the chosen collection's index. Neither carries
  the section any more: an index has no use for one, and the form
  keeps its own state (ADR-0008).
- The index of a non-default collection is validated by the
  collection's `tmac/mdoc.local`, as ADR-0013 does for the other
  collection-level responses; `/` keeps the default collection's
  `build` file, which ADR-0013 left there deliberately.

### Consequences

- Good, because every collection has one index URL in the path
  layout, cached under the `home` class and the `coll:<coll>` key.
- Good, because the arch-only and slash-only misses stop being
  404s: each is now a 301 to something that exists.
- Bad, because a manual page named exactly like an `archlist` entry
  can no longer be asked for without its section: `/<name>` is the
  arch. No served collection has one -- checked on oxygene on
  2026-08-25, none of the 13,813 distinct page names across every
  collection is in `archlist` -- and `/<name>.<section>` still
  works, so the case is accepted rather than guarded against.
- Bad, because a page whose name has the collection shape would be
  taken for a collection when asked for alone. None exists, and
  the shape -- an uppercase start, a hyphen, then a digit or
  `current` -- is not one a manual page is named in.
- Bad, because it adds to the class of 301s that only expire
  (ADR-0015): the trailing-slash collapse of a name that does not
  exist is a 301 to a 404, as an extra path component already is.
  The hold is a day at nginx.
- Neutral: the 404s these URLs answered before are cached under the
  `notfound` key until they expire or are purged.

## Pros and Cons of the Options

### Path indexes

- Good, because the rules live in the one place that knows what a
  collection and an arch are.
- Bad, because the parser grows a trailing-slash judgement it did
  not need before.

### A trailing-slash rewrite at nginx

- Good, because the CGI would not change for the redirect half.
- Bad, because nginx does not know which `[A-Z]*` components are
  collections, so it would either redirect page URLs too or
  duplicate the collection probe and its fallbacks; and the site
  sets `no_directory_redirect` for that reason.
- Bad, because `/<coll>/` still has to render, so the CGI changes
  anyway.

### Serve both forms, no redirect

- Good, because it mints no 301.
- Bad, because one resource gets two cache keys at nginx
  (`$request_uri`) and at Fastly, and two URLs for crawlers.

### Recognize an arch alone only with a trailing slash

- Good, because a page named like an arch keeps its sectionless
  URL.
- Bad, because `/i386` stays a 404 for no reason once `archlist`
  is trusted, and it would be the one place a trailing slash
  decides what a component *is* rather than whether it is
  canonical.

## More Information

Builds on ADR-0009 (an index URL carries no arch) and ADR-0013 (the
index's validator). ADR-0008's form recalls the arch from
`localStorage`, which is what makes dropping it from the URL
harmless.

The parser now peels the collection, collapses extra components
and classifies what is left in one shape for every path length;
two-component and longer page URLs behave as before.
