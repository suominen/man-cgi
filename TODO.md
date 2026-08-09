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
- [ ] 9. Docs: `docs/caching.md`, `docs/runbook.md`,
  `docs/nginx.md`; ADRs 0002-0004, 0008-0009. For caching.md's
  size-dynamics section: the nginx cache was 110 GB before the
  2026-08-09 wipe (bot-crawled URL space, largely arch aliases);
  shorter TTLs do not shrink disk usage (expired entries stay for
  revalidation; inactive=365d and max_size govern eviction) — the
  canonical-arch redirects (step 13) are what collapses the alias
  multiplier. Then one-time nginx cache wipe + Fastly
  soft purge + live verification. Verification checklist from the
  step-7 review: Fastly does not cache 308s (or 503s) by default —
  confirm Surrogate-Control on them is inert and nginx absorbs 308s
  (X-Accel-Expires 30d); confirm stale-if-error delivery; runbook
  must note that recovering from a bad 301 means deleting nginx
  cache files (no purge module). Also note nginx forwards
  Surrogate-Key to non-Fastly clients (harmless; stripping is
  tidier). From the step-8 review: with the 304 fast path,
  frozen-collection objects at nginx revalidate indefinitely, and
  their bodies contain content the validator does not cover (form
  lists until step 12, markup, MANCGI_DATE) — the runbook must list
  nginx-wipe triggers: script deploys with observable output
  changes, and archlist/colllist changes until step 12 removes the
  embedded lists. Wipe method (per Kim, applies to every host):
  stop nginx, `umount /p/fcgicache`, `newfs -i 8192` the cache
  device (`ld2a` on oxygene, `ld3a` on lcm), `mount /p/fcgicache`
  (relies on the /etc/fstab entry), recreate the cache directory with
  `install -d -o nginx -g nginx -m 755 /p/fcgicache/man-cache`
  (as root), and start nginx — faster than find-deleting 500 GB of
  cache files. The `-i 8192` matters: the plain newfs default for
  filesystems >=128 GB is 16 KB per inode, which halves the inode
  count this cache historically had (many small objects);
  nginx must be stopped first, and Fastly's health probe fails the
  shield over to the other host meanwhile. For docs/deployment.md:
  the deployed site syncs from oxygene to lcm with
  `/root/bin/site-rsync man-www` (as root); lcm also runs that from
  cron ("53 6,18 * * *"), so manual runs are only needed when the
  sync must happen immediately. Fastly purge token (purge_select
  scope, for the man.netbsd.org service — "manno" is its
  affectionate nickname): `~kim/.config/manno/fastly-purge-token`
  on oxygene, mode 600.
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
