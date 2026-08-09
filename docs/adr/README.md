# Architecture decision records

MADR-style records, one file per decision, numbered in assignment
order. Copy `template.md` to `NNNN-short-title.md` with the next free
number, fill the `status`/`date` frontmatter, and add the record
here. Supersede landed records with new ones; never rewrite them.

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | accepted |
| [0002](0002-three-tier-caching-and-ttl-policy.md) | Three-tier caching with per-tier TTLs | accepted |
| [0003](0003-exact-match-conditional-revalidation.md) | Conditional revalidation by exact Last-Modified match | accepted |
| [0004](0004-surrogate-key-vocabulary.md) | Surrogate-Key vocabulary | accepted |
| [0005](0005-301-for-canonicalization-redirects.md) | 301 (not 308) for canonicalization redirects | accepted |
| [0006](0006-no-etag.md) | No ETag (for now) | accepted |
| [0007](0007-post-303-no-store.md) | POST form responses are 303 with no-store | accepted |
| [0008](0008-js-query-form-and-list-endpoints.md) | JS query form fed by plain-text list endpoints | accepted |
| [0009](0009-canonical-arch-redirects.md) | Canonical-arch redirects | accepted |
| [0010](0010-keep-the-shell-cgi.md) | Keep the shell CGI instead of rewriting | accepted |
