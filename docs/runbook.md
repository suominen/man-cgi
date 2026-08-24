# Operations runbook

Procedures for running man.netbsd.org's caching stack. Background
is in `caching.md`; design rationale in `adr/`.

## Purging Fastly

Use `bin/manno-purge` (in this repository; keep a copy on oxygene
where the token lives). It purges by Surrogate-Key, **soft by
default**: objects are marked stale and revalidated on the next
fetch, so clients keep receiving responses throughout. `-H` purges
hard — reserve it for content that must stop being served
immediately (e.g. something that should never have been published).

Mind the ordering: purged objects refill from **nginx**, not from
the CGI. While nginx still holds a stale-but-valid entry (within
its `X-Accel-Expires` TTL — see the table in `caching.md`), a
Fastly purge just re-caches the same old object. Even past that
TTL, the purge-triggered fetch can be the very request that kicks
off nginx's background revalidation and still get handed the stale
copy (`X-Man-Cache: STALE` on the refilled object is the tell). So
after a change reaches the origin, don't count purges — verify:
purge, compare `Last-Modified` at the edge against the origin's
(the QA vhost shows the origin's), and repeat until they match; a
couple of rounds is normal. (The nginx wipe procedure below is
immune by construction: wipe first, then `manno-purge all`.)

Configuration (on the purging host):

    ~/.config/manno/fastly-purge-token    API token, purge_select scope
    ~/.config/manno/fastly-service-id     Fastly service id

The token deliberately has only the `purge_select` scope: it cannot
read the service or perform the hard purge-all, so a leak is
annoying rather than dangerous. The service id is on the service
page at manage.fastly.com (also in its URL).

### Key vocabulary and when to purge what

| Key | Purge when |
|-----|------------|
| `coll:<collection>` | That collection's man tree was rebuilt. The common case: `manno-purge coll:NetBSD-current` after the daily build pull. Covers the collection's pages, 404s (a rebuild can add a page that 404'd), multi-match menus, and redirects. |
| `page:<coll>:<cmd>.<sect>` | One page needs refreshing; hits all its arch aliases at once (the key is arch-free). |
| `page:<coll>:<cmd>` | The sectionless form: one command's multi-match menu (ADR-0012). Purge it alongside the `.<sect>` keys when a name gains or loses a page in another section or arch. |
| `form` | `archlist` or `colllist` changed. Since the JS query form (ADR-0008) only the three `/api/v1` list objects carry it; pages no longer embed the lists. |
| `api` | The three `/api/v1` list objects (archlist, colllist, sectlist), also individually keyed by name; their 404s carry `api notfound`. |
| `home` | The home page needs refreshing. |
| `notfound` | Mass-refresh of 404s. |
| `menu` | Mass-refresh of multi-match menus, e.g. after changing how they render. |
| `redirect` | Redirect logic changed, or a collection appeared/disappeared. |
| `arch:<arch>` | An architecture was retired from `archlist`. |
| `all` | Everything (soft). The safe whole-site refresh; Fastly's own purge-all is hard-only. |

Multiple keys per invocation are fine; a failed key is reported and
the rest still purge.

Worth automating: append `manno-purge coll:NetBSD-current` to the
daily build-pull cron job, so the current collection is soft-purged
right after each pull.

### Hard purge-all (Fastly UI)

The "Purge all" button on the service page drops every object
unconditionally, including any that carry no Surrogate-Keys. It
should never be needed again — since the 2026-08-09 cutover every
cached object is keyed — but it is the recovery tool if key-less
objects somehow reappear (e.g. after the CGI stopped emitting keys
for a while). The purge token cannot do this; it requires UI access.

Expect a **refill storm** after a purge-all (observed at the
cutover): with the edge empty, crawler traffic hits the origin as
full renders until the caches rewarm; the shared fcgiwrap pool can
502 intermittently (which also affects the QA vhost) and the
shield POP's `limit_req` budget can 429. It settles as popular
objects refill. Pace any smoke checks through it (`ct-check
--delay`).

## Purging / wiping nginx

nginx (open source) has no cache-purge module: the only options are
waiting out `X-Accel-Expires` or wiping the cache filesystem. Wiping
is safe while requests flow — a missing cache file is just a MISS —
but the fast method reformats the filesystem, which needs nginx
stopped:

    # on the host being wiped (as root)
    service nginx stop
    umount /p/fcgicache
    newfs -i 8192 ld2a        # oxygene; ld3a on lcm
    mount /p/fcgicache        # fstab has the entry
    install -d -o nginx -g nginx -m 755 /p/fcgicache/man-cache
    service nginx start

The cache devices: oxygene `ld2a`, ~512 GiB (nginx `max_size`
500 GB); lcm `ld3a`, 96 GiB (nginx `max_size` 88 GB). `-i 8192`
matters on oxygene: the plain newfs default for filesystems over
128 GB is 16 KiB per inode, which halves the inode count this cache
needs (many small objects). On lcm's sub-128 GiB device 8 KiB is
already the default, so the flag is a harmless no-op — use the same
command everywhere. Fastly's health probe fails the shield over to
the other host while nginx is down, so wipe one host at a time.

### When an nginx wipe is needed

- **Script deploys with output changes that must land immediately,
  or where the `MINLASTMOD` bump was missed.** A bumped
  `MINLASTMOD` (ADR-0011) moves every validator, so even
  frozen-release objects stop revalidating to 304s and pick up the
  new output as they expire — without it their validators never
  change and markup or header changes never reach them through
  expiry alone. (List changes stopped being a wipe trigger when
  the JS query form removed the embedded lists from page bodies.)
- **A bad permanent redirect**: 301s are purgeable at Fastly (the
  `redirect` key) but live 30 days in nginx's cache with no purge
  mechanism — a wrong 301 needs `manno-purge redirect` *and* an
  nginx wipe.
- **A change that turns a cached 301 into something else.** Same
  mechanism as the previous bullet, but easy to miss because the
  redirect was never *wrong*. A `MINLASTMOD` bump does nothing
  here: nginx does not revalidate cached redirects conditionally
  at all — measured in `../tests/nginx-lab/`, it neither sends
  `If-Modified-Since` upstream when a cached 301 expires nor
  answers a client's conditional with 304, where the identical
  setup does both for a 200. Redirects refresh only by expiring,
  and permanent ones are held 30 days. Multi-match menus
  (ADR-0012) are the worked example — every sectionless URL they
  now answer, such as `/printf` and `/i386/apm`, was previously a
  cached 301 — so that deploy needs `manno-purge redirect` and an
  nginx wipe, not the bump.
- After the wipe, follow with `manno-purge all` so Fastly
  revalidates against the fresh origin.

## Collection rebuild procedure

1. The build lands in `$MANROOT/<collection>/` (NetBSD-current: the
   daily cron pull. Its `tmac/mdoc.local` carries the upstream
   build's timestamp and is the Last-Modified for that
   collection's 404s and multi-match menus; the `build` file's own
   mtime is the pull time, and NetBSD-current's is the home page's
   validator).
2. `manno-purge coll:<collection>` (soft).
3. Nothing else: nginx entries revalidate as they expire (at most
   1 h for current/branch, 24 h for releases), and pages whose
   files changed get fresh bodies on the next fill.
4. If the rebuild must be visible *immediately* at every tier, wipe
   nginx too — rarely worth it.

## archlist / colllist changes

1. Edit the lists (the Makefile in `$MANROOT` regenerates them).
2. `manno-purge form` — refreshes the `/api/v1` list objects, which
   is all that embeds the lists since the JS query form (ADR-0008).
   Browsers pick the change up within the objects' 1-hour
   Cache-Control.

## Health checks and failover

Fastly probes `HEAD /.well-known/health` on both backends every 60s
(threshold 1, window 2) and routes to lcm when oxygene is unhealthy.
The health response is cacheable for 30s at every tier, which is
compatible with the probe cadence. The CGI's health check verifies
that `$MANROOT` and the NetBSD-current `build` file exist and
otherwise answers 503 (not cached by Fastly; 30s at nginx).

## Verifying cache behavior

- `X-Man-Cache` (from nginx, baked into stored objects): MISS, HIT,
  STALE (served stale while a background revalidation runs),
  REVALIDATED, EXPIRED.
- `X-Cache` / `X-Served-By` / `Age` (from Fastly): note that with
  shielding two hops append values, and a stored object replays the
  fill-time values of earlier hops.
- Direct-to-origin checks bypass Fastly:
  `curl --resolve man.netbsd.org:443:<origin-ip> https://man.netbsd.org/...`
  — these show Surrogate-Control/Surrogate-Key, which Fastly strips
  from client responses.
- A conditional request echoing the exact `Last-Modified` must
  return 304 at every layer.
