# nginx FastCGI cache lab

A disposable rig for verifying nginx FastCGI cache behaviour against
a synthetic backend, used to settle design questions empirically
before touching production configuration.

- `fcgi-backend.py` — minimal FastCGI responder (127.0.0.1:9481).
  Emits a fixed `Last-Modified` and `Cache-Control: max-age=2`;
  answers 304 when `HTTP_IF_MODIFIED_SINCE` matches exactly; logs
  every request's received `If-Modified-Since` to `requests.log`.
- `nginx-base.conf` — unprivileged nginx (127.0.0.1:8481) with
  `fastcgi_cache` and `fastcgi_cache_revalidate on`; the
  `#CLEAR_IMS#` marker is where the `drive` script injects
  conditional-clearing params for the second variant.
- `drive` — runs both variants through six scenarios and prints
  client-visible status/cache-state plus what the backend saw.
- `drive-redirect` — reruns the conditional scenarios with the
  backend answering 301 instead of 200 (`LAB_STATUS`), to compare
  how nginx treats cached redirects against cached pages.

Run it on the NetBSD test host:

    rsync -a tests/nginx-lab/ kimmo@equinoxe:nginx-lab/
    ssh kimmo@equinoxe sh nginx-lab/drive

## Results (2026-08-09, nginx 1.30.4 on NetBSD 11.0)

Variant `plain` (`fastcgi_cache_revalidate on`, nothing else):

| Scenario | Client saw | Backend saw |
|----------|------------|-------------|
| 1 cold GET | 200 MISS | no IMS, sent 200 |
| 2 warm GET | 200 HIT | (not contacted) |
| 3 warm GET + client IMS | **304** HIT | (not contacted) |
| 4 expired GET | 200 REVALIDATED | stored Last-Modified as IMS, sent 304 |
| 5 flushed cache + client IMS | **304** MISS | **no IMS**, sent 200 (cache filled) |
| 6 plain GET after that | 200 HIT | (not contacted) |

Variant `clear-ims` (adds `fastcgi_param HTTP_IF_MODIFIED_SINCE "";`
and `HTTP_IF_NONE_MATCH ""`):

| Scenario | Client saw | Backend saw |
|----------|------------|-------------|
| 4 expired GET | 200 **EXPIRED** | **no IMS**, sent 200 (full refetch) |

Conclusions:

1. `fastcgi_cache_revalidate on` alone is correct and sufficient.
2. The fastcgi module withholds client conditionals from the backend
   when caching is enabled (observed directly: the backend logs the
   If-Modified-Since it receives, and received none), and nginx
   itself answers client conditionals with 304 both against a warm
   cache entry (scenario 3) and against the response it just fetched
   on a miss (scenario 5). There is no miss-plus-If-Modified-Since
   fill-starvation case to defend against.
3. Explicitly clearing `HTTP_IF_MODIFIED_SINCE` via `fastcgi_param`
   also overrides the revalidation header nginx injects, silently
   disabling revalidation. Do not add it.

## Redirects are not revalidated (2026-08-24, nginx 1.30.4)

`drive-redirect` runs the same scenarios against the same nginx
twice, with `LAB_STATUS=200` and `LAB_STATUS=301`, so the status
code is the only difference. The backend emits a `Last-Modified` in
both cases, and the 301's `Location` carries the request serial so a
stale redirect is distinguishable from a fresh one.

| Scenario | 200 | 301 |
|----------|-----|-----|
| cold GET | 200 MISS | 301 MISS, `/target-1` |
| warm GET + matching client IMS | **304** HIT | **301** HIT (no 304) |
| expired GET | 200 **REVALIDATED**, backend saw IMS and sent 304 | 301 **EXPIRED**, backend saw **no IMS**, full refetch, `/target-2` |

Conclusions:

1. nginx does no conditional handling for cached redirects — it
   neither sends `If-Modified-Since` upstream when one expires nor
   answers a client's conditional with 304 — even though the cached
   301 carries a `Last-Modified`. This matches HTTP: 304 is defined
   for a request that would otherwise be answered 200, and a
   redirect has no representation to validate.
2. So a `Last-Modified` on a redirect would be inert at nginx, and
   `MINLASTMOD` (ADR-0011) cannot reach redirects. They refresh
   only by expiring or by a cache wipe, which is why a change that
   stops a URL redirecting needs the wipe (see `../../docs/runbook.md`).
3. The flip side is that expiry is always a *full* refetch, so a
   redirect can never be pinned stale by a 304 the way a page can.
   Shortening `X-Accel-Expires` for the redirect classes is the only
   lever on how long the wait is.
