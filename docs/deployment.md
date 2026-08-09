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
4. Bump `MANCGI_DATE` (its own revision) when observable output
   changed; it is visible in `X-Powered-By` on the health check and
   in the page signature, which makes deployed-version checks easy.
5. Copy to the QA vhost (man.oxygene.qa.nxrns.org — uncached, no
   rate limits, serves the production man tree) and smoke-test the
   response classes there.
6. Deploy into the man-www site on oxygene; sync to lcm with
   `/root/bin/site-rsync man-www` (as root). lcm also runs that
   sync from cron at 06:53 and 18:53, so a manual run is only
   needed when the deploy must reach lcm immediately.
7. If the change altered observable output (markup, headers): wipe
   the nginx caches (runbook) — frozen-collection objects
   revalidate forever and never pick up body changes through expiry
   — then `manno-purge all`.

## Testability

The script honors two environment overrides, `MANCGI_PATH` and
`MANCGI_MANROOT`, **only outside a gateway context**: when
`GATEWAY_INTERFACE` is set (as under real CGI), both are ignored
and the fixed production paths apply. The test harness runs the
script with `env -i` and fixture trees; production behavior cannot
be influenced through them.

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
