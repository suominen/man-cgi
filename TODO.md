# TODO

Open work for man.netbsd.org. Each item becomes a separately
reviewable changeset (a feature branch here, or a branch in the
repo named). Unscheduled collects open ideas and known defects not
yet part of any effort.

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
- Consider bringing back the apropos functionality (perhaps an
  `/apropos/*` namespace) using `apropos -l` "legacy" output (also
  reachable by setting `export APROPOS=-l` in the environment and
  then using `man -k` like before). The HTMLizer should be able to
  handle the legacy output just fine. Concern: cache growth due to
  garbage; maybe this could be kept in check with e.g.
  `sanitize_command`.
- Emit canonical cross-reference links when the page's own reference
  already names an arch. boot(8) refers to its siblings as
  `x86/dosboot(8)`, and the HTMLizer's cross-reference `sed` prefixes
  `/${COLL}/${ARCH}/` to whatever it matched, so
  `/NetBSD-11.0/x86/boot.8` links to `/NetBSD-11.0/x86/x86/dosboot.8`.
  The path parser papers over this: with more than two segments after
  the collection it shifts the extra ones away, keeps the last as the
  arch, and 301s to `/NetBSD-11.0/x86/dosboot.8`. So the links work,
  but every one costs a redirect hop, and the doubled URL is an extra
  cache key and crawler target. Fix at link-generation time instead:
  when the matched name contains a `/`, treat the part before it as
  the arch and don't prepend `${ARCH}` again. Whether that embedded
  arch should also go through the machine-class canonicalization
  (`i386/foo(4)` → `x86`, ADR-0009) is a separate question — the
  301 handles that today, and doing it in `sed` would need the class
  table at HTMLize time.
