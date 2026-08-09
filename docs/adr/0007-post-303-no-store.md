---
status: accepted
date: 2026-08-09
---

# 0007: POST form responses are 303 with no-store

## Context and Problem Statement

The query form POSTs to the CGI, which redirects to the page URL.
The redirect must convert the POST into a GET, and the response
must never be cached (it is request-specific and POSTs bypass the
caches anyway).

## Considered Options

- 303 See Other with `Cache-Control: no-store` (chosen)
- 303 with no caching headers (status quo before this change)
- 301/302 and trust clients' method-rewriting behavior

## Decision Outcome

Chosen option: 303 + explicit `no-store`. 303 is the status whose
defined semantics are "fetch Location with GET" — the method switch
is its job, which is also why the permanent canonicalization
redirects are free to be 301 (ADR-0005). The explicit `no-store`
replaces implicit uncacheability with a stated contract: no
Expires, no Surrogate headers, no Last-Modified, nothing for any
cache to hold.

### Consequences

- Good, because the POST path's cache behavior is explicit and
  pinned by tests.
- Neutral, because POSTs never reached the caches anyway
  (`fastcgi_cache_methods` defaults to GET/HEAD; Fastly passes
  non-GET/HEAD).
