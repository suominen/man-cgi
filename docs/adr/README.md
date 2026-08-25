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
| [0005](0005-301-for-canonicalization-redirects.md) | 301 (not 308) for canonicalization redirects | amended by ADR-0015 |
| [0006](0006-no-etag.md) | No ETag (for now) | accepted |
| [0007](0007-post-303-no-store.md) | POST form responses are 303 with no-store | accepted |
| [0008](0008-js-query-form-and-list-endpoints.md) | JS query form fed by plain-text list endpoints | accepted |
| [0009](0009-canonical-arch-redirects.md) | Canonical-arch redirects | amended by ADR-0015 |
| [0010](0010-keep-the-shell-cgi.md) | Keep the shell CGI instead of rewriting | accepted |
| [0011](0011-minlastmod-validator-floor.md) | MINLASTMOD floor folds script changes into Last-Modified | accepted |
| [0012](0012-multi-match-menus.md) | Menus for multi-match lookups | accepted |
| [0013](0013-collection-validator-from-mdoc-local.md) | Collection-level validators come from tmac/mdoc.local | accepted |
| [0014](0014-import-the-rcs-history.md) | Import the RCS history of man-cgi as one linear git history | accepted |
| [0015](0015-short-lived-redirects-and-deterministic-purges.md) | Short-lived redirects and deterministic purges | accepted |
