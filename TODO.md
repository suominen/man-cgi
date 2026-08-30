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
- A query string on a page path (`/ls.1?utm_source=…`, `?fbclid=…`)
  is ignored by the CGI but is its own cache key at nginx and
  Fastly. Consider a 301 to the bare path.
- Work ADR-0020's nginx changes into Ansible (`~/src/cloud`). The
  first deployment was by hand on oxygene from
  `~/tmp/oxygene-nginx/proposed.diff`. The port, in order:
  - Port the hand-added `location /r/` (`try_files $uri =404;
    expires 5m;`) into `website_configurations['man.netbsd.org']`
    first — Ansible does not know it, so any apply before that takes
    the published reports offline.
  - New templates `conf.d/probe-map.conf.j2` and
    `conf.d/man-cgi-syntax-map.conf.j2`, added to the literal loop in
    `roles/common/tasks/config/nginx.yml` (the site file only where
    `'man.netbsd.org' in websites`).
  - `conf.d/query-string-map.conf.j2`: `default 0` and the scanner
    keys (`rest_route=`, `route=information`, the AcyMailing set,
    `meta-box-loader=`/`_wpm=`/`wmo_hc=`, `phpinfo`, traversal).
  - `nginx.conf.j2`: the ADR-0019 `cache= rt= urt=` log fields.
  - `fqdn.j2` (careful review): `query_string_check` returns 400
    instead of 503 (www.netbsd.org and mail-index.netbsd.org were
    changed by hand with the same diff); a new `probe_check` option
    emitting `if ($probe_path) { return 404; }`; a per-site hook
    for the man maps' `if` blocks and the `$args` redirect in
    `location /`.
  - `mancgi.j2`: the same five `if` blocks in place of the 503,
    ahead of the `!-f` guard, with the `Surrogate-Key` on the two
    404s; and `return 404;` in the outer `/cgi-bin/` location,
    ahead of the nested one (the location loop in `fqdn.j2` treats
    `rules` and `template` as alternatives, so this belongs in the
    template).
  - `group_vars/all.yml`: drop the four `code: 501` locations; `^~`
    on `/cgi-bin/`, `/s/` and `/r/`; add `probe_check` to
    man.netbsd.org (the QA vhost inherits `options`); consider
    `probe_check` for www.netbsd.org and mail-index.netbsd.org,
    which carry the same `.php|.cgi` 501 rule today.
  - Then re-read `docs/logreport.md`'s status notes: 501 and the
    query-string 503 are described as "before the map change".
