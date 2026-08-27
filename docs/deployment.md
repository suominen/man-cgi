# Deployment

## The CGI script

The live script is `src/man-cgi` in this repository (its RCS
history was imported in August 2026, ADR-0014). Development
workflow:

1. Work on a feature branch in its own worktree, like everything
   else in the repository; keep the diff reviewable.
2. Tests first (TDD): `make test` runs the suite in `tests/` on the
   NetBSD test host via `tests/run-remote` (the script needs NetBSD
   stat(1), date(1), man(1); the Makefile names the host and the
   ssh identity). A change to the inline script also gets
   `make test-browser`, which drives it in headless Chromium
   locally. All tests green before the branch is reviewed.
3. Merge to `main` by fast-forward only, so the reviewed commit is
   the one that lands.
4. When a change alters *rendered output* (markup, headers — not
   the signature), bump `MINLASTMOD` to the commit time in the
   same commit: it floors every `Last-Modified`, so cached
   objects revalidate to the new output as they expire (ADR-0011).
5. Bump `MANCGI_DATE` (its own commit) when observable output
   changed; it is visible in `X-Powered-By` on the health check and
   in the page signature, which makes deployed-version checks easy.
6. `make dist-qa` installs the script on the QA vhost
   (man.oxygene.qa.nxrns.org — uncached, no rate limits, serves the
   production man tree); `make smoke-qa` checks the response
   classes there, Surrogate headers included.
7. `make dist-prod` installs it into the man-www site on oxygene;
   sync to lcm with `/root/bin/site-rsync man-www` (as root). lcm
   also runs that sync from cron at 06:53 and 18:53, so a manual
   run is only needed when the deploy must reach lcm immediately.
   `make smoke-prod` checks the edge.
8. If the change altered rendered output and `MINLASTMOD` was
   bumped, caches converge on their own: every validator below the
   floor moved, so nginx entries pick up the new output as they
   expire. A validator already above the floor does not move.
   NetBSD-current and branch objects take theirs from the extracted
   files, which carry the upstream build's timestamp, and the home
   page from the NetBSD-current `build` file, which is the pull
   time (`caching.md`). Once a pull has brought a build newer than
   the bump — for the home page, once any pull has run after it —
   objects cached since that pull keep the old output until a newer
   build arrives, normally the next day. Deploy before the next
   pull, accept the day, or wipe. Wipe the nginx caches (runbook)
   and `manno-purge all` only when the change must be visible
   immediately — or when the bump was missed.
9. Redirects are the other exception to step 8. nginx does not
   revalidate them conditionally (`tests/nginx-lab/`), so no
   `MINLASTMOD` bump reaches them; they refresh only when their
   nginx entry expires — a day for 301s, 3 hours for 302s. If the
   change makes any URL stop redirecting, or redirect somewhere
   else, wait that out, then `manno-purge redirect` and confirm at
   the edge (runbook, "Redirect changes"). No wipe.

## Testability

The script honors three environment overrides — `MANCGI_PATH`,
`MANCGI_MANROOT`, and `MANCGI_MINLASTMOD` — **only outside a
gateway context**: when `GATEWAY_INTERFACE` is set (as under real
CGI), they are ignored and the fixed production values apply. The
test harness runs the script with `env -i` and fixture trees;
production behavior cannot be influenced through them.

## nginx configuration changes

Via the `~/src/cloud` Ansible repository (see `nginx.md`); apply
with Ansible on oxygene and lcm. The QA vhost derives from the same
site definition minus caching and rate limiting, so most cache
directives cannot be exercised there — that is what
`tests/nginx-lab/` (synthetic backend on the test host) is for.

## Test environment

- NetBSD test host: `equinoxe` (NetBSD 11.0). `tests/run-remote`
  rsyncs the suite and the script there and runs it; nothing else
  is required on the host beyond base system + rsync.
- The nginx lab (`tests/nginx-lab/`) also runs there against
  `/usr/pkg/sbin/nginx`, unprivileged.
