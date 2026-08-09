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
- `drive` — runs both variants through five scenarios and prints
  client-visible status/cache-state plus what the backend saw.

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
