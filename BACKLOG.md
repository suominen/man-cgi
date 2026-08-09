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
- Revisit ETag emission (skipped for now; see ADR-0006).
- Automate `manno-purge coll:NetBSD-current` in the daily build-pull
  cron job (runbook suggests it; not yet wired).
- Unify cache keys for legacy query-string URLs vs path URLs (nginx
  cache key is `$request_method$request_uri`; the 301 canonicalization
  already migrates traffic).
- Apply the Fastly `real_ip` list so `limit_req` keys on end-client
  addresses instead of Fastly POP addresses (current per-POP limiting
  is intentional).
- Align lcm's cache disk device with oxygene: the cache filesystem is
  `ld3a` on lcm but `ld2a` on oxygene, which invites wipe-procedure
  mistakes.
- Review fcgiwrap worker capacity on oxygene: during the 2026-08-09
  post-cutover refill storm, roughly a third of uncached requests
  (including the QA vhost's) 502'd for hours while crawlers re-filled
  the caches.
