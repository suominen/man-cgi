# TODO

Execution roadmap for the caching-improvement effort. Each step is a
separately reviewable changeset (a feature branch here, an RCS
revision of `../sh/man-cgi`, or a branch in the repo named). Ordering
constraints are load-bearing; see the notes at the bottom.

## Steps

- [x] 2. Testability hooks in the script (`MANCGI_PATH`,
  `MANCGI_MANROOT` overrides; 2-line diff) + `run_cgi` harness +
  first characterization tests (URL parsing, redirects, 404, current
  headers).
- [x] 3. Remaining characterization tests (MD/MI canonical arch, home
  page, health check, POST form).
- [x] 4. Ansible (`~/src/cloud`): `fastcgi_cache_revalidate on` in
  `mancgi.j2`. Verified with `tests/nginx-lab/`: revalidation works
  alone; conditional-clearing params are unnecessary (nginx already
  withholds client conditionals from the backend) and would disable
  revalidation, so they are deliberately omitted.
- [x] 5. Script: header-emission refactor (`emit_cache_headers`,
  content classes; no header-value changes yet).
- [x] 6. Script: Surrogate-Key emission.
- [x] 7. Script: TTL layering (X-Accel-Expires, Surrogate-Control,
  new Cache-Control values per class). The page arm now branches on
  the resolved collection, fixing a long-standing error: the
  *-current match could never fire for the default collection
  (COLL is emptied when it equals DEFAULT_COLLECTION), so
  NetBSD-current pages — rebuilt daily from TNF's builds via a
  once-a-day cron pull — were cached for 90 days everywhere.
- [x] 8. Script: fast 304 handler + HEAD + 404 Last-Modified + 303
  `no-store`; canonicalization redirects switched from 308 to 301
  (Fastly's default-cacheable statuses include 301 but not 308, and
  the active VCL has no cacheability overrides; 303 keeps the
  POST-to-GET switch). Step 4 (nginx revalidation) is already
  applied in production.
- [x] 9. Docs (`docs/caching.md`, `docs/runbook.md`,
  `docs/nginx.md`, `docs/deployment.md`) and ADRs 0002-0007. The
  cutover itself (deploy of RCS 1.100, nginx cache wipes on both
  hosts, `manno-purge all`, Fastly UI purge-all for the key-less
  pre-deploy objects) was performed live on 2026-08-09 and
  verified end to end, including the natural nginx revalidation
  cycle (STALE served during background revalidation, then HIT with
  refreshed validity, observed on a seeded entry after its 3600 s
  X-Accel-Expires).
- [x] 10. ct-check extensions (branch `response-headers` in
  `~/src/ct-check`: response-header assertions, location compare,
  request headers, revalidate, --delay) + `tests/smoke.yml` (any
  tier; green against production through Fastly) and
  `tests/smoke-origin.yml` (origin/QA, Surrogate headers; entries
  verified, full-run greens limited only by refill-storm 502s).
- [x] 11. Script: `/api/v1/{archlist,colllist,sectlist}` endpoints
  (versioned per Kim; sectlist added). One shared `list_sections`
  now feeds the endpoint, the query form, and the intro table —
  whose hardcoded uppercase copy is gone (wording now matches the
  form's mixed-case descriptions).
- [ ] 12. Script: JS query form + localStorage; drop embedded
  lists; write its ADR.
- [ ] 13. Script (after step 12 bakes one browser-TTL cycle + soft
  purge): canonical-arch 301 redirects; write its ADR.
- [ ] 14. Rewrite ADR: keep improved shell CGI vs rewrite
  (Python/Perl/C/Go), using origin-QPS data gathered after steps
  8-9.

## Ordering constraints

- Step 13 only after step 12 has baked: cached pages must no longer
  rely on URL-borne arch for form preselection before arch is dropped
  from machine-independent URLs. Bake means at least one browser-TTL
  cycle after step 12's deploy, plus a soft purge of `all`.

(Steps up to 9 are done — step 1, the repo bootstrap, predates this
list. Their ordering constraints held and their operational lessons
now live in docs/, not here.)
