---
status: accepted
date: 2026-08-30
---

# 0020: Reject junk requests at nginx with maps and client-error statuses

## Context and Problem Statement

Requests that man-cgi can only refuse — scanner probes such as
`/wp-login.php` and `/.env`, SQL-injection query strings, POSTs to
arbitrary paths, paths with characters the CGI's `sanitize_*`
functions strip — still reached fcgiwrap, each costing a shell
process, a cache entry and sometimes a 301 that crawlers then
followed. The nginx vhost blocked a few shapes with per-path
`location ~ … { return 501; }` blocks and the `$qs_error` map with
`return 503`. Two weeks of logs (2026-08-14..28, 2.78 M requests;
see `../logreport.md` and the "Backend reach" section of the
report) showed those rules absorbing the bulk of the probing but
also that 501 and 503 were the wrong answers: Fastly caches
neither, and its boilerplate VCL restarts a request once on an
origin 503, so every `$qs_error` hit was fetched twice, the second
time from the standby host. Adding more regex locations would
also cost every request another pattern test, twice (before and
after the `rewrite … last` into the CGI location).

## Considered Options

- Keep `return 501` locations and `$qs_error → 503`; add more
  locations as probes change.
- Maps tested with `if (…) { return … }` in the two entry
  locations, answering 404 for paths, 400 for query strings, 405
  for methods; a generic probe map shared with other sites and a
  site map that whitelists man.netbsd.org's URL grammar.
- The same maps, answering 400 for everything.
- 403, 410, or 444 (close the connection).

## Decision Outcome

Chosen option: maps with 404/400/405.

- `conf.d/probe-map.conf` — `$probe_path`, a blacklist of paths
  only scanners request (`.php`, `wp-*`, `.env`, `.git`, GraphQL,
  secrets in JSON, …), keyed on the decoded `$uri`. Generic: any
  site opts in with one `if`.
- `conf.d/man-cgi-syntax-map.conf` — `$man_bad_uri`, a whitelist
  built from the CGI's own per-component character sets
  (`sanitize_coll`, `sanitize_arch`, `sanitize_command`) plus the
  reserved `/api/v1/*` and `/.well-known/health` paths and the
  script's own URL; path info arriving after the script name is
  refused, since `PATH_INFO` is what the `/` rewrite produces;
  `$man_bad_method` (GET and HEAD anywhere, POST only to `/` and
  `/cgi-bin/man-cgi`); `$man_bad_query` (at `/cgi-bin/man-cgi` the
  query string is the request, so only the legacy positional form
  passes); and `$raw_path`, for the redirect below.
- Any other query string — on `/`, where the legacy form was never
  meant to work and the rewrite never let it, or on a page path,
  where it is other sites' tracking (`utm_source=chatgpt.com`,
  `fbclid=`) that used to end in a CGI 404 — is answered in
  `location /` with a 301 to `$raw_path`, the request's own path
  without it: friendly to the reader behind the click, one cache
  key per page, no CGI.
- `$qs_error` stays the generic map and now answers 400,
  extended with the scanner keys the logs showed (`rest_route=`,
  `route=information`, the AcyMailing set, `meta-box-loader=`,
  `_wpm=`, `wmo_hc=`, `phpinfo`, traversal in a value); it is
  tested ahead of the redirect, so a scanner's query is refused
  rather than redirected. The other vhosts on the host
  (www.netbsd.org, mail-index.netbsd.org) answer it with 400 too,
  in the same change, for the same Fastly reasons.
- The four `return 501` locations go; `/cgi-bin/`, `/s/` and `/r/`
  become `^~` prefixes so the second location pass after the
  rewrite skips the remaining regex locations, and the outer
  `/cgi-bin/` location answers 404 itself for a path its nested
  CGI location does not match, instead of a filesystem lookup.
- The nginx-level 404s carry `Surrogate-Key: all notfound
  nginx-reject` (ADR-0004's vocabulary plus one key of their own),
  so a mistaken rule's answers can be purged from Fastly by key
  rather than waited out.

Status codes: 404 for a path is what the CGI answers for the same
request, reveals nothing, and is in Fastly's cacheable set (200,
203, 300, 301, 302, 404, 410; `../caching.md`), so repeat probes of
one URL are absorbed at the edge. 400 for a query string is the
truthful answer and, though uncacheable at Fastly, costs only an
nginx `return`; such URLs are unique anyway. 405 with an `Allow`
header is what HTTP prescribes for a method the resource does not
support. None of the three triggers Fastly's restart.

Nothing the CGI would accept is refused: the whitelist is the
union of the CGI's character sets, because its parser shifts
extra components and a component's role is not fixed by position.
The lab (`../../tests/nginx-lab/drive-reject`) holds the table of
accepted and refused shapes.

### Consequences

- Good, because a rejected request costs one variable lookup and
  a `return`: no fcgiwrap process, no cache entry, no `limit_req`
  budget for junk that arrives through `location /`.
- Good, because the maps are data: a new probe family is a line in
  a `conf.d` file, not a location block.
- Good, because the report can tell nginx's 404s from the CGI's
  once the extended log format (ADR-0019) is deployed: an
  nginx-level answer logs `cache=-` and no upstream time (a POST
  the CGI answers logs `cache=-` too, as nginx caches only GET and
  HEAD, but with an upstream time).
- Bad, because the grammar map turns some of the site's own
  broken cross-reference links (`/i%3E/vax/dl.4`, which the CGI
  used to canonicalize by shifting the junk component off) into
  404s until the link generator is fixed (`../../TODO.md`).
- Bad, because `if` in nginx is the "if is evil" construct; only
  `return` (and one `add_header`) is used inside, which is the
  documented safe form.
- Bad, because a `$uri`-keyed map is evaluated after nginx has
  merged slashes and resolved `..`, so `//` and `..` probes are
  judged by their normalised form (the logged request line still
  shows the raw one).
- Good, because a reader who follows a link that ChatGPT or
  Facebook stamped with a tracking parameter now lands on the
  page (through one redirect) instead of a 404.
- Bad, because nginx closes the connection after a 400 (it drops
  keep-alive on that status), so each `$man_bad_query` or
  `$qs_error` hit costs Fastly's shield a reconnect and TLS
  handshake for its next request. At the observed rate (about a
  thousand a fortnight) that is negligible against the double
  fetch the 503 caused; a 404 would keep the connection, at the
  price of a less truthful status.
- Bad, because the maps depend on nginx caching a map's value for
  the request: the rewrite copies `$request_uri`, query string
  included, into `$uri`, and a fresh evaluation in the CGI location
  would refuse it. The second `if` pass therefore re-tests the
  `location /` verdicts, and judges afresh only on direct
  `/cgi-bin/man-cgi` hits. Never add `volatile` to these maps.

## Pros and Cons of the Options

### Keep 501/503 per-path locations

- Good, because it exists and is understood.
- Bad, because 501 means "method not implemented" and 503 "try
  later"; neither is cached by Fastly, and 503 is fetched twice.
- Bad, because every added location is another regex on the path
  of every request, evaluated twice.

### 400 for everything

- Good, because one status is easy to explain.
- Bad, because a 400 for `/wp-login.php` is not cacheable at
  Fastly, so the same probe from many clients reaches the origin
  every time; a 404 is held at the edge.

### 403, 410, 444

- 403 is not in Fastly's cacheable set and advertises that the
  path is guarded.
- 410 is cacheable but claims the resource once existed.
- 444 closes the connection; Fastly sees a backend failure,
  answers its own 503, and with the serve-stale snippets active
  may deliver a stale object for an unrelated reason.

## More Information

- `../nginx.md` "Request rejection" documents the maps and the
  `if` order; `../runbook.md` "Repeating the nginx blocking
  analysis" is the procedure for extending them from the report.
- The nginx configuration lives in `~/src/cloud` (Ansible); the
  first deployment of this decision was applied by hand on
  oxygene from a diff kept beside the config snapshot; the Ansible
  port followed on 2026-08-30 (`../nginx.md`).
- Related: ADR-0005 (why redirects are 301: the same Fastly
  cacheability), ADR-0015 (redirect TTLs), ADR-0019 (the log
  fields that make nginx-level answers visible in the report).
