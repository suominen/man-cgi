---
status: accepted
date: 2026-08-09
---

# 0006: No ETag (for now)

## Context and Problem Statement

With conditional revalidation in place (ADR-0003), should responses
also carry an ETag validator?

## Considered Options

- Last-Modified only (chosen)
- Add a weak ETag derived from mtime and size
- ETag only

## Decision Outcome

Chosen option: Last-Modified only. It already drives all three
revalidation paths (nginx's `fastcgi_cache_revalidate`, Fastly's
conditional handling, and client 304s), the underlying data changes
at whole-file granularity with second-resolution mtimes refreshed
by daily builds, and a second validator would add edge cases (nginx
sends both validators on revalidation; the CGI would need
`If-None-Match` handling in shell) for no measurable gain.

### Consequences

- Good, because one validator means one code path and one exact
  string to reason about.
- Bad, because sub-second or same-mtime content changes are
  invisible to revalidation — not a real risk for build-produced
  files, and a cache wipe covers pathological cases.

## More Information

Revisit if the renderer is ever rewritten; a persistent server
could hash content cheaply.
