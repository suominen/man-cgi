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
| `coll:<collection>` | That collection's man tree was rebuilt. The common case: `manno-purge coll:NetBSD-current` after the daily build pull. Covers the collection's pages, 404s (a rebuild can add a page that 404'd), and redirects. |
| `page:<coll>:<cmd>.<sect>` | One page needs refreshing; hits all its arch aliases at once (the key is arch-free). |
| `form` | `archlist` or `colllist` changed (until the JS query form lands, every HTML page embeds the lists). |
| `home` | The home page needs refreshing. |
| `notfound` | Mass-refresh of 404s. |
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

- **Script deploys with observable output changes.** Frozen-release
  objects revalidate indefinitely (their validators never change),
  so markup or header changes never reach them through expiry alone.
- **`archlist`/`colllist` changes** — same reason, until the JS form
  removes the embedded lists from page bodies (TODO step 12).
- **A bad permanent redirect**: 301s are purgeable at Fastly (the
  `redirect` key) but live 30 days in nginx's cache with no purge
  mechanism — a wrong 301 needs `manno-purge redirect` *and* an
  nginx wipe.
- After the wipe, follow with `manno-purge all` so Fastly
  revalidates against the fresh origin.

## Collection rebuild procedure

1. The build lands in `$MANROOT/<collection>/` (NetBSD-current: the
   daily cron pull; its `build` file's mtime is the collection's
   Last-Modified for 404s and the home page).
2. `manno-purge coll:<collection>` (soft).
3. Nothing else: nginx entries revalidate as they expire (at most
   1 h for current/branch, 24 h for releases), and pages whose
   files changed get fresh bodies on the next fill.
4. If the rebuild must be visible *immediately* at every tier, wipe
   nginx too — rarely worth it.

## archlist / colllist changes

1. Edit the lists (the Makefile in `$MANROOT` regenerates them).
2. `manno-purge form home` — refreshes every list-embedding page at
   Fastly.
3. nginx keeps serving old embedded lists on frozen pages until
   wiped (see above) — acceptable for cosmetic list drift, wipe when
   it matters.

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
