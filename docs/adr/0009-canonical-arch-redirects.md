---
status: amended by ADR-0015, ADR-0021
date: 2026-08-09
---

# 0009: Canonical-arch redirects

## Context and Problem Statement

A machine-independent manual page was reachable — and separately
cached at every tier — under every architecture prefix
(`/i386/ls.1`, `/amd64/ls.1`, ... alongside `/ls.1`), because the
architecture rode in the URL only so the query form could preselect
it. With ~60 architectures, one MI page became up to ~60 cached
objects; bots crawling the arch space were the largest contributor
to the 110 GB nginx cache. Now that the JS form remembers the arch
in localStorage (ADR-0008), the URL no longer needs to carry it for
MI pages.

## Considered Options

- Redirect each request to the URL matching where `man -w`
  resolved the page (chosen)
- Keep serving every arch alias (status quo), relying only on the
  `<link rel="canonical">` hint
- Collapse the aliases at the cache layer (not possible: neither
  nginx's FastCGI cache nor Fastly can key on a canonical URL)

## Decision Outcome

Chosen option: after the CGI computes `CANONICAL_ARCH` from the
`man -w` result, it compares the requested architecture with the
canonical one and, when they differ, `redirect 301`s to the
canonical URL. Machine-independent pages (`CANONICAL_ARCH=NONE`)
drop the arch (`/i386/ls.1` → `/ls.1`); machine-dependent pages
keep it (`/i386/apm.4` stays); a machine-class page redirects to
its class directory (`/i386/est.4` → `/x86/est.4`). The arch is
set before the existing section-inference redirect, so
`/i386/ls` → `/ls.1` is a single hop. The redirects are cacheable
301s (ADR-0005) keyed `all redirect coll:<coll>`.

### Consequences

- Good, because each MI page collapses from up to ~60 cached
  objects to one page plus small redirect objects at every tier —
  the main lever on cache size.
- Good, because search engines converge on one URL per page (the
  `<link rel="canonical">` already advertised it).
- Neutral: one-time crawler churn as engines follow the new 301s.
- Bad, because a wrong redirect is durable (301 cached 30 days at
  nginx with no purge) — the same trade-off as ADR-0005.

## More Information

Relationship to ADR-0008: the localStorage form is what preserves
the user's arch once it leaves machine-independent URLs. Both
changes live in the same `man-cgi` script and ship as one artifact,
so there is nothing to sequence — deploying the script deploys both
together. When arch is neither in the URL nor remembered (a fresh
browser, or a user who has not submitted the form), the form falls
back to the default arch, exactly as for any first-time visitor.

The `arch:<canonical>` "differs from requested" branch of the
Surrogate-Key vocabulary (ADR-0004) is now unreachable on served
pages — every served page is at its canonical arch — but is left
in place harmlessly.
