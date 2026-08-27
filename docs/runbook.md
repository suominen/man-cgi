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
Fastly purge just re-caches the same old object. So after a change
reaches the origin, wait out the nginx TTL of the class in
question, then purge once and confirm at the edge: compare
`Last-Modified` — or a redirect's status and `Location` — against
the QA vhost, which shows the origin's. The purge-triggered fetch
gets the refreshed response because nginx runs with
`fastcgi_cache_background_update off` (`nginx.md`, ADR-0015); the
one residual way to refill the old object is a fetch that lands
while some other request's refresh is still in flight, which the
refilled object shows as `X-Man-Cache: UPDATING` — purge again.
(The nginx wipe procedure below is immune by construction: wipe
first, then `manno-purge all`.)

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
| `home` | The home page, or a collection's index (`/<coll>/`, ADR-0017), needs refreshing. |
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

nginx (open source) has no cache-purge module: the options are
waiting out `X-Accel-Expires`, removing the entries of one class
by hand (below), or wiping the cache filesystem. Removing is safe
while requests flow — a missing cache file is just a MISS — but the
fast wipe reformats the filesystem, which needs nginx stopped:

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

### Removing one class of entries

A cache file starts with nginx's binary header, then a `KEY:` line
with the cache key (`GET/pc532/ls.1`), then the FastCGI record as
the CGI sent it: the `Status:` line and every header, including
`X-Accel-Expires`, which nginx keeps in the file though it never
forwards it (`nginx.md`). The stored headers therefore identify an
entry's class and the TTL it was filled with, and the file names
are hex, so a `find` over the cache with a `grep -l` selects a
class and `rm` retires it. The `grep` needs `-a` (the file is
binary) and must not anchor on `^`: the FastCGI record header sits
on the same line as `Status:`.

Worked example (2026-08-27): the 301s filled between 2026-08-09
and the ADR-0015 deploy of 2026-08-25 carried a 30-day nginx hold,
which no later change could reach (redirects are never
revalidated). Their signature is the stored `X-Accel-Expires:
2592000`, a value only those redirects ever had. As root, one host
at a time:

    d=$(mktemp -d) || exit 1
    find /p/fcgicache/man-cache -type f -print0 |
    xargs -0 grep -a -l 'X-Accel-Expires: 2592000' > "$d/remnants"
    wc -l "$d/remnants"
    head -3 "$d/remnants" |
    xargs grep -a -o -E 'KEY: [^[:cntrl:]]*|Status: 30[12][^[:cntrl:]]*|X-Accel-Expires: [0-9]*'
    xargs rm < "$d/remnants"
    rm -rf "$d"

The `head` step shows the key, status and stored TTL of a sample,
which is the check that the selector matches the intended class
before anything is removed. `grep -l` stops at the first match
and the headers are in the first kilobyte, so the run costs a
directory walk: minutes on lcm, considerably longer on oxygene.
A `find` time filter (`\! -newer` a `touch -t` reference file) can
narrow the walk, but the fill time is what matters and the file's
mtime is close to it only for entries never revalidated; the
stored headers are the reliable selector. lcm found 2567 files
that day; the same selector then ran on oxygene.

Afterwards, purge the same class at Fastly (`manno-purge redirect`
in the example) so its objects refill from the fresh nginx entries
rather than the other way round.

### When an nginx wipe is needed

- **Script deploys with output changes that must land immediately,
  or where the `MINLASTMOD` bump was missed.** A bumped
  `MINLASTMOD` (ADR-0011) moves every validator below it, so even
  frozen-release objects stop revalidating to 304s and pick up the
  new output as they expire — without it their validators never
  change and markup or header changes never reach them through
  expiry alone. (NetBSD-current and branch objects cached after a
  pull that brought a build newer than the bump have validators
  above the floor and wait for the next one; see `deployment.md`,
  step 8. List changes stopped being a wipe trigger when the JS
  query form removed the embedded lists from page bodies.)
- After the wipe, follow with `manno-purge all` so Fastly
  revalidates against the fresh origin.

Redirects are not a wipe trigger any more: see "Redirect changes"
below.

## New release procedure

Until the release tree exists, `/NetBSD-N.M/...` 302s to
`NetBSD-N.x-BRANCH` (or to NetBSD-current for an N.0 with no
branch). Those 302s are keyed by the collection they *point at*,
not the one requested, and are held 3 hours at nginx and a day at
Fastly (ADR-0015).

1. The release tree lands in `$MANROOT/NetBSD-N.M/`.
2. Wait 3 hours (the 302's nginx TTL).
3. `manno-purge redirect` (the `coll:` key of the collection the
   302s pointed at covers them too).
4. Confirm `/NetBSD-N.M/ls.1` answers 200 at the edge.

That makes the release reachable by URL; listing it is the
colllist change below.

## Redirect changes

nginx does not revalidate cached redirects conditionally at all —
measured in `../tests/nginx-lab/`, it neither sends
`If-Modified-Since` upstream when a cached 301 expires nor answers
a client's conditional with 304, where the identical setup does
both for a 200. So a `MINLASTMOD` bump never reaches them; they
refresh only by expiring — a day for 301s, 3 hours for 302s. When
a deploy makes any URL stop redirecting, or redirect somewhere
else (multi-match menus, ADR-0012, are the worked example: every
sectionless URL they answer, such as `/printf` and `/i386/apm`,
was previously a cached 301), or when a 301 turns out to be wrong:

1. Deploy (or fix).
2. Wait a day (the 301's nginx TTL), or remove the affected
   entries at nginx ("Removing one class of entries" above).
3. `manno-purge redirect`.
4. Confirm at the edge: status and `Location` against the QA
   vhost.

## Collection rebuild procedure

1. The build lands in `$MANROOT/<collection>/` (NetBSD-current: the
   daily cron pull. Its `tmac/mdoc.local` carries the upstream
   build's timestamp and is the Last-Modified for that
   collection's 404s, multi-match menus and index; the `build`
   file's own mtime is the pull time, and NetBSD-current's is the
   home page's validator).
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

While the origin fails, Fastly keeps serving what it holds past
its `max-age` for the `stale-if-error` window (`caching.md`): by
itself when both backends are sick, and for backends answering
5xx or unreachable provided the service VCL delivers stale on
error — the generated boilerplate alone does not (`fastly.md`).
The window is a week for pages, the home page, the API lists and
301s, and a day for 404s and the 302; anything not cached gets
Fastly's own 503. A soft purge during an outage leaves that
fallback in place; a hard purge (`manno-purge -H`) removes it.

## Verifying cache behavior

- `X-Man-Cache` (from nginx, baked into stored objects): MISS, HIT,
  REVALIDATED, EXPIRED, UPDATING (served stale because another
  request's refresh was in flight), STALE (served stale because
  the upstream failed: the `use_stale` list minus `updating`).
- `X-Cache` / `X-Served-By` / `Age` (from Fastly): note that with
  shielding two hops append values, and a stored object replays the
  fill-time values of earlier hops.
- Direct-to-origin checks bypass Fastly:
  `curl --resolve man.netbsd.org:443:<origin-ip> https://man.netbsd.org/...`
  — these show Surrogate-Control/Surrogate-Key, which Fastly strips
  from client responses.
- A conditional request echoing the exact `Last-Modified` must
  return 304 at every layer.
