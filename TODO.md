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
  is intentional). The 2026-08-14..28 logs: 122 k of the 125 k
  `limit_req` rejections came from the site-wide `server` zone
  during crawler storms, every one of them a well-formed page URL;
  the per-address zone fired 3.1 k times, on the 15 shield-POP
  addresses that all traffic arrives from. Junk never reaches the
  limiter (ADR-0020 rejects it in `location /`, ahead of the
  `/cgi-bin/` location that carries `limit_req`), so the 429s are
  purely a crawler-vs-reader budget question.
- Align lcm's cache disk device with oxygene: the cache filesystem is
  `ld3a` on lcm but `ld2a` on oxygene, which invites wipe-procedure
  mistakes.
- Review fcgiwrap worker capacity on oxygene: during the 2026-08-09
  post-cutover refill storm, roughly a third of uncached requests
  (including the QA vhost's) 502'd for hours while crawlers re-filled
  the caches.
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
  table at HTMLize time. Measured in the 2026-08-14..28 logs: 30.4 k
  requests, 26.4 k of them answered with that 301. The same `sed`
  (`src/man-cgi`, the cross-reference substitution whose name class
  is `[0-9A-z_][-.,0-9A-z_/]*`) also emits `/etc/vether.4` (2.1 k
  requests), `/0/chmod.1` (2.5 k), `/sparc/rule,.2` (1.3 k) and
  `/man.netbsd.org/passwd.5` (1.2 k) — and, since `A-z` also spans
  `` [ \ ] ^ ` _ ``, `` /`FOO.2 `` and `/2^0.1` — and 3.4 k requests arrived as
  `/i%3E/vax/dl.4` and `/a%3E/X509_new.3` — a tag remnant in the
  arch slot, which that expression's character class cannot produce
  by itself, so find the actual source before fixing. The report's
  "Backend reach" section counts these shapes as `self` grammar
  violations; the nginx grammar map (ADR-0020) now answers 404 for
  the ones with illegal characters, which used to be canonicalized
  away, so the fix has become visible to readers rather than only
  to the cache.
- Reduce the cost of `/COLL/ARCH/name.sect` requests that only
  redirect. In the 2026-08-14..28 logs 1.16 M requests (41.8 % of
  all traffic) were that shape and 301'd to the arch-less canonical
  URL (ADR-0009), flat across ports (`dreamcast` 85 k, `vax` 75 k,
  `hp300` 74 k): crawlers walking the collection × arch × name
  cross-product, not readers. Not an nginx-pattern problem — the
  URLs are valid. Options: serve the canonical body directly with a
  `Content-Location`, raise the redirect TTLs (ADR-0015 went the
  other way for purge determinism), or steer crawlers (robots.txt
  rules for arch-prefixed paths; `Crawl-delay`).
- `/s/netbsd.ico` 404s (15 requests plus 16 error-log lines in the
  fortnight): the page links `/s/${CNAME:-$OSNAME}.ico`, so the file
  either is missing in lowercase or the reference is being
  case-folded by a client; check which and fix that side.
- A 301 shim for FreeBSD/OpenBSD man.cgi query syntax
  (`?query=ls&sektion=1`, 57 requests in the fortnight): the site
  map (ADR-0020) now answers 400; a redirect to `/ls.1` would be the
  friendlier answer.
- After 2027-09-01, remove the one-time localStorage cleanup: the
  `if (!persist)` block removing `man-cgi.arch` / `man-cgi.coll`
  in `js_queryform()` (ADR-0021 moved the keys to sessionStorage
  on 2026-09-01; the remember opt-in guards its own copies with
  the `man-cgi.remember` flag, which the cleanup respects) and the
  "old localStorage keys are cleaned up" check in
  `tests/run-browser`. Stale pre-ADR-0021 keys are inert without
  the flag — nothing reads them — so the cleanup is a courtesy
  for visitors returning within the year, and its later removal
  harmlessly leaves any latecomer's keys in place.
