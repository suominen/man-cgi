---
status: accepted
date: 2026-08-24
---

# 0013: Collection-level validators come from tmac/mdoc.local

## Context and Problem Statement

Some responses describe a *collection* rather than one manual page:
404s, and the multi-match menus of ADR-0012. They need a
`Last-Modified` that moves when the collection's contents move. The
obvious candidate, the collection's `build` file, turned out to be
the wrong one on both counts: it is absent from every frozen
release, so those responses went out with no validator and could
never return 304, and where it does exist it records when the
*pull ran* rather than what the pull found.

## Considered Options

- The collection's `tmac/mdoc.local` (chosen)
- The `build` file, with `MINLASTMOD` as a fallback where it is
  absent
- The `build` file alone (status quo)

## Decision Outcome

Chosen option: `${MANROOT}/<collection>/tmac/mdoc.local`.

Everything the pull extracts carries the upstream build's
timestamp, and `mdoc.local` is extracted with the rest, so its mtime
is the date of the content itself:

    build                2026-08-24 06:18:04   <- when the pull ran
    tmac/mdoc.local      2026-08-23 17:33:07   <- upstream build
    man1/ls.1            2026-08-23 17:33:07
    man8/boot.8          2026-08-23 17:33:07

It is also present in every collection — checked on oxygene, all of
them, back to NetBSD-6.0 — where `build` exists only for
NetBSD-current and the branches. It is a natural fit beyond the
timestamp, too: `mdoc.local` is where the list of NetBSD releases
is recorded, so its *contents* change for every release.

The `build` file stays where it is already right: the home page's
validator, and the health check's liveness probe. Both are about
the service and NetBSD-current specifically, not about a resolved
collection.

`MINLASTMOD` (ADR-0011) still floors the result, so a script change
that alters rendered output continues to move these validators too.

### Consequences

- Good, because 404s and menus in frozen releases gain a validator
  they never had: they can now be revalidated with a 304 instead of
  refetched in full at every expiry.
- Good, because a pull that finds nothing new no longer invalidates
  every 404 and menu in the collection, as a daily `build` bump did.
- Neutral: the `*/build` guard that distinguishes a collection-level
  validator from a manual page's path now matches
  `*/tmac/mdoc.local` as well. It is a path test either way.
- Bad, because a collection whose extract is missing `tmac/mdoc.local`
  silently has no validator, exactly as a missing `build` file did.
  Nothing is served stale as a result — no validator means a full
  refetch on expiry — but the cheap revalidation is lost with no
  signal.

## More Information

Amends ADR-0003, which said 404s carry `Last-Modified` from the
resolved collection's `build` file; the exact-match revalidation
rule it decided is unchanged, only the file it names.

The test fixtures previously gave every collection a `build` file,
which is why the suite could not see the frozen-release gap.
`tests/fixtures/manroot/NetBSD-10.1/` now has no `build`, matching
production, and every fixture collection carries a
`tmac/mdoc.local`.
