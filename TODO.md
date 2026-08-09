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
- [ ] 5. Script: header-emission refactor (`emit_cache_headers`,
  content classes; no header-value changes yet).
- [ ] 6. Script: Surrogate-Key emission.
- [ ] 7. Script: TTL layering (X-Accel-Expires, Surrogate-Control,
  new Cache-Control values per class).
- [ ] 8. Script: fast 304 handler + HEAD + 404 Last-Modified + 303
  `no-store`. Deploy only after step 4 is applied in production.
- [ ] 9. Docs: `docs/caching.md`, `docs/runbook.md`, `docs/nginx.md`;
  ADRs 0002-0004, 0008-0009. Then one-time nginx cache wipe + Fastly
  soft purge + live verification.
- [ ] 10. ct-check extensions (branch in `~/src/ct-check`) +
  `tests/smoke.yml`.
- [ ] 11. Script: `/api/archlist` + `/api/colllist` endpoints.
- [ ] 12. Script: JS query form + localStorage; drop embedded lists;
  ADR-0005.
- [ ] 13. Script (after step 12 bakes one browser-TTL cycle + soft
  purge): canonical-arch 308 redirects; ADR-0006.
- [ ] 14. ADR-0007: keep improved shell CGI vs rewrite
  (Python/Perl/C/Go), using origin-QPS data gathered after steps 8-9.

## Ordering constraints

- Step 4 (nginx revalidation) is applied before step 8's 304 handler
  deploys. The lab (tests/nginx-lab) showed either order is in fact
  safe: with caching enabled nginx never forwards client
  conditionals to the CGI, so in production the only source of
  If-Modified-Since at the CGI is nginx's own revalidation — the 304
  handler stays inert until step 4 is live. (The originally feared
  background-update-carries-client-IMS stale-forever case does not
  occur.)
- Step 9's one-time nginx cache wipe is mandatory after step 8:
  existing entries have up to 90-day validity and no Surrogate-Key;
  Fastly could re-fill from key-less objects and purge-by-key would
  silently fail for months.
- Step 13 only after step 12 has baked: cached pages must no longer
  rely on URL-borne arch for form preselection before arch is dropped
  from machine-independent URLs.
