# Deployment

## The CGI script

The live script is RCS-tracked in `../sh/` (sibling of this
checkout, outside git). Development workflow:

1. `co -l man-cgi`, edit, keep `rcsdiff -u` reviewable.
2. Tests first (TDD): the suite in `tests/` runs on the NetBSD test
   host via `tests/run-remote` (the script needs NetBSD stat(1),
   date(1), man(1); see `tests/run-remote -h` for the environment
   knobs). All tests green before check-in.
3. `ci -u` (not `-l`) so the checked-in file is unlocked and
   read-only between edits.
4. When a change alters *rendered output* (markup, headers — not
   the signature), bump `MINLASTMOD` to the checkin time in the
   same revision: it floors every `Last-Modified`, so cached
   objects revalidate to the new output as they expire (ADR-0011).
5. Bump `MANCGI_DATE` (its own revision) when observable output
   changed; it is visible in `X-Powered-By` on the health check and
   in the page signature, which makes deployed-version checks easy.
6. Copy to the QA vhost (man.oxygene.qa.nxrns.org — uncached, no
   rate limits, serves the production man tree) and smoke-test the
   response classes there.
7. Deploy into the man-www site on oxygene; sync to lcm with
   `/root/bin/site-rsync man-www` (as root). lcm also runs that
   sync from cron at 06:53 and 18:53, so a manual run is only
   needed when the deploy must reach lcm immediately.
8. If the change altered rendered output and `MINLASTMOD` was
   bumped, caches converge on their own: every validator moved, so
   nginx entries pick up the new output as they expire. Wipe the
   nginx caches (runbook) and `manno-purge all` only when the
   change must be visible immediately — or when the bump was
   missed.
9. Redirects are the exception to step 8. nginx does not
   revalidate them conditionally (`tests/nginx-lab/`), so no
   `MINLASTMOD` bump reaches them; they refresh only when their
   30-day entry expires. If the change makes any URL stop
   redirecting, or redirect somewhere else, it needs
   `manno-purge redirect` and an nginx wipe (runbook) to be
   visible.

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
