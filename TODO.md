# TODO

Open work for man.netbsd.org. Each item becomes a separately
reviewable changeset (a feature branch here, an RCS revision of
`../sh/man-cgi`, or a branch in the repo named). Unscheduled
collects open ideas and known defects not yet part of any effort.

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
- HTML-escape `COMMAND` before it reaches page chrome (`<title>`,
  `<h1>`, the multi-match menu's lead sentence, the 404 page's
  search links). It is taken from `PATH_INFO` and emitted raw:
  `GET /<b>zz` against production returns
  `<h1 class="manpage"><b>zz`. Percent-encoded input is *not*
  decoded before it reaches the CGI (`/%3Cb%3Ezz` comes back
  literal), so reaching it needs a client that sends a raw `<` in
  the path rather than a browser following a link — narrow, but
  the markup is genuinely attacker-controlled. Escaping changes
  rendered output, so it needs a MINLASTMOD bump (ADR-0011).
- Give 404s and multi-match menus a validator in collections with
  no `build` file, so they can be revalidated instead of refetched.
  Only NetBSD-current and the branches get a `build` file from the
  daily pull; every frozen release goes without (verified on QA:
  NetBSD-current and NetBSD-11.x-BRANCH carry `Last-Modified` on a
  404, NetBSD-11.0, NetBSD-10.1 and NetBSD-9.0 carry none).
  Candidates are `tmac/mdoc.local` (per Kim — it would date the
  collection itself; needs confirming that it exists in every
  collection) and `MINLASTMOD` alone, which `api_list()` already
  uses for the embedded sectlist. Either has to be a *fallback*,
  not a replacement: where `build` exists it is the right validator
  precisely because the daily pull moves it, which is when a menu's
  contents can change. A validator that survives a rebuild would
  let nginx answer its revalidation with a 304 and serve a stale
  menu indefinitely — the daily `manno-purge coll:<collection>`
  reaches Fastly, not nginx. Note also that `MINLASTMOD` floors
  every validator, so a collection installed before the last bump
  gives the same answer whichever file is picked; the two differ
  only for one installed since. Correctness is not at stake today
  (no validator means a full refetch at expiry, so the content is
  always current). The fixtures give every collection a `build`
  file, so the suite cannot currently see any of this.
- Infer the section from the match token rather than the file
  suffix, so a page that exists only preformatted (`catN/name.0`)
  redirects to its section URL like a source page does. Today
  `/name` serves it at the sectionless URL with a `page:<coll>:name`
  key, so it caches separately from `/name.N`. `match_tokens`
  (ADR-0012) already computes the right section. No collection in
  the production tree ships `catN` pages today, and a wrong 301 is
  durable (ADR-0005), which is why ADR-0012 left this alone.
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
