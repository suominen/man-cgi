# TODO

Open work for man.netbsd.org. Each item becomes a separately
reviewable changeset (a feature branch here, an RCS revision of
`../sh/man-cgi`, or a branch in the repo named). Unscheduled
collects open ideas and known defects not yet part of any effort.

## Scheduled

- [ ] Rewrite ADR: keep improved shell CGI vs rewrite
  (Python/Perl/C/Go), using origin-QPS data gathered after the
  2026-08-09 caching cutover.

## Unscheduled

Open ideas and known defects not part of any scheduled effort.

- Serve NetBSD's shipped HTML manual pages (`htmlN/` trees) instead of
  rendering; first establish from which release (if any) their links
  are valid, especially in/out of arch-specific pages.
- Move output from ISO-8859-1/windows-1252 to UTF-8 for nicer
  rendering in browsers. Deliberately not done so far: the sed
  HTMLizer relies on single-byte characters; variable-length UTF-8
  representations would make those expressions much harder.
- Replace the sed HTMLizer with `mandoc -T html` (spike; changes
  output and link markup).
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
- Feed the COLL sanitizer with `printf '%s'` instead of `echo`: a
  collection of exactly `-n` is consumed as an echo option (verified
  under dash: COLL comes out empty, so it silently becomes the
  default collection), and echo's backslash-escape processing mangles
  backslash-bearing values before tr sees them.
- Reject dot-only collection names: `..` survives the sanitizer's
  character set, satisfies the `-d "$MANROOT/$COLL"` check, and sets
  MANPATH one level above MANROOT (bounded to one level — slashes
  cannot survive the earlier IFS=/ split of PATH_INFO).
- Sanitize COLL on the POST path before `redirect 303`: the redirect
  embeds COLL straight from the raw POST body into the Location
  header, and a trailing CR from a CRLF-terminated body line survives
  the IFS split (CR is not in the split set) into the header value.
