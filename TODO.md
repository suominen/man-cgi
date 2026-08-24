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
- Infer the section from the match token rather than the file
  suffix, so a page that exists only preformatted (`catN/name.0`)
  redirects to its section URL like a source page does. Today
  `/name` serves it at the sectionless URL with a `page:<coll>:name`
  key, so it caches separately from `/name.N`. `match_tokens`
  (ADR-0012) already computes the right section. No collection in
  the production tree ships `catN` pages today, and a wrong 301 is
  durable (ADR-0005), which is why ADR-0012 left this alone.
- Keep the requested architecture across the machine-class
  canonicalization. `/i386/est.4` 301s to `/x86/est.4` (ADR-0009),
  and the query form prefers the URL's arch to the remembered one
  (`want = data-url || recall(name) || fallback`), so the select
  comes back as `x86` and the next submit stores `x86` over the
  user's `i386`. Cross-reference links in the page carry the class
  too, so browsing onward stays in `x86`. The machine-independent
  case is fine and is what ADR-0009 relies on: the arch leaves the
  URL entirely, no `data-url` is emitted, and ADR-0008's
  localStorage keeps the selection. Only the class transition
  overwrites it. A fix has to stay inside the form or the
  remembered value — putting the port back in the URL would
  recreate the per-arch cache aliases ADR-0009 exists to collapse.
