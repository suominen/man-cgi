---
status: accepted
date: 2026-08-09
---

# 0003: Conditional revalidation by exact Last-Modified match

## Context and Problem Statement

The CGI re-rendered every request (`man` plus a ~30-expression sed
pipeline) even when the client only wanted to know whether a page
had changed. nginx gained `fastcgi_cache_revalidate on`, so expired
cache entries revalidate with `If-Modified-Since` — but the CGI
must answer those conditionals, and HTTP date comparison in POSIX
shell is fragile (NetBSD and GNU date(1) disagree on every parsing
flag).

## Considered Options

- Parse the If-Modified-Since date and compare timestamps
- Compare the If-Modified-Since string byte-for-byte against the
  computed Last-Modified
- ETag-based revalidation
- No conditional support (status quo)

## Decision Outcome

Chosen option: byte-for-byte string comparison. The CGI is the sole
producer of its `Last-Modified` values, and — verified empirically
with `tests/nginx-lab/` — nginx never forwards client conditionals
to a FastCGI backend when caching is enabled, so the only
`If-Modified-Since` reaching the CGI in production is nginx echoing
the CGI's own string back during revalidation. Exact match is
therefore complete, not approximate. On a match the CGI emits a 304
with the full caching-header block (so nginx and Fastly refresh
validity and purge keys) and no body; on any mismatch it falls
through to a full response — failing safe (correct, merely slower).

404s carry `Last-Modified` from the resolved collection's `build`
file (the home page from NetBSD-current's) so they revalidate too.
Redirects and POST responses are emitted before the conditional
check and can never become 304s.

### Consequences

- Good, because an expired nginx entry now costs a `man -w` plus a
  `stat` instead of a full render.
- Good, because no date parsing exists to get wrong.
- Bad, because a semantically-equal-but-differently-formatted
  If-Modified-Since is treated as a mismatch — acceptable, since
  the only production sender is nginx echoing our exact format.

## More Information

nginx answers client conditionals itself (from valid entries and
fresh fills), so the CGI's 304 path serves nginx's revalidation,
not end clients. Measurements: `tests/nginx-lab/README.md`. The
deliberate omission of conditional-clearing `fastcgi_param`s is
recorded in `../nginx.md`.
