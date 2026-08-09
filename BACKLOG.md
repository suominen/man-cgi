# BACKLOG

Flat roll-up of open ideas not scheduled in TODO.md. Regenerated
snapshot, not a source of truth.

- Serve NetBSD's shipped HTML manual pages (`htmlN/` trees) instead of
  rendering; first establish from which release (if any) their links
  are valid, especially in/out of arch-specific pages.
- Move output from ISO-8859-1/windows-1252 to UTF-8 for nicer
  rendering in browsers. Deliberately not done so far: the sed
  HTMLizer relies on single-byte characters; variable-length UTF-8
  representations would make those expressions much harder.
- Replace the sed HTMLizer with `mandoc -T html` (spike; changes
  output and link markup).
- Section list endpoint (`seclist`) instead of the hardcoded section
  options in the query form (XXX comment in `man-cgi`).
- Revisit ETag emission (skipped for now; see ADR-0008 once written).
- Unify cache keys for legacy query-string URLs vs path URLs (nginx
  cache key is `$request_method$request_uri`; the 308 canonicalization
  already migrates traffic).
- Apply the Fastly `real_ip` list so `limit_req` keys on end-client
  addresses instead of Fastly POP addresses (current per-POP limiting
  is intentional).
