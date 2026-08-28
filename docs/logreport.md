# manno-logreport

`bin/manno-logreport` turns nginx access and error logs for one
vhost into a single self-contained HTML report, with an optional
JSON sidecar carrying the same numbers. It is a standalone tool: it
does not touch `src/man-cgi` and has no runtime dependency on this
repository's CGI script.

## Purpose

The report exists to answer four recurring questions about
man.netbsd.org's backend from raw nginx logs: how much load it is
carrying and when, how much of that load is bots rather than
people, how much is probing traffic that never matched a real URL,
and how the legitimate service is actually being used (which
collections, sections, and architectures). Each run reads whatever
log files it is given and produces one report from them; nothing
persists between runs, so there is no state to get out of sync and
no database to maintain. Pick a window by pointing the tool at the
logs that cover it.

## Usage

    manno-logreport [-o FILE] [--json FILE | -O DIR] [--host HOST]
        [--cdn-ranges FILE] [--geoip-db FILE] [--asn-db FILE]
        [--top N] [-v] LOGDIR|FILE ...

Positional arguments:

- `LOGDIR|FILE ...` — one or more directories or files. A directory
  contributes every `access.log*` and `error.log*` file in it
  (sorted, so rotated files are read in a stable order); a file
  argument is read directly, and its kind (access or error) is
  sniffed from its first lines. Plain, gzip (`.gz`), and xz (`.xz`)
  logs are all read directly, so rotated `access.log.N.xz` files
  need no unpacking first.

Options:

- `-o, --output FILE` — write the HTML report here. Default: stdout.
- `-O, --output-dir DIR` — write both `DIR/<window>.html` and
  `DIR/<window>.json`, where `<window>` is the first and last day
  seen (`2026-08-14..28` inside one month, `2026-08-25..2026-09-05`
  across months), create `DIR` if needed, and print the HTML path.
  Not combinable with `-o` or `--json`.
- `--json FILE` — also write the aggregated data as JSON, alongside
  the HTML.
- `--host HOST` — the vhost to report on. Default: `man.netbsd.org`.
- `--cdn-ranges FILE` — a CIDR list of CDN addresses, one per line
  (see "CDN ranges" below). Default: the file this package ships,
  `lib/manno_logreport/data/fastly.cidr`.
- `--geoip-db FILE` — a MaxMind-format country/city database.
- `--asn-db FILE` — a MaxMind-format ASN database.
- `--top N` — how many rows the top-N tables carry. Default: 25.
- `-v, --verbose` — print each input file's line count to stderr as
  it is read.
- `--version` — print the version and exit.

Two examples:

    bin/manno-logreport -o report.html --json report.json \
        ~/tmp/oxygene-nginx-logs

    bin/manno-logreport --host man.oxygene.qa.nxrns.org access.log

The first reads every access and error log in a directory, reports
on the default host, and writes both the HTML and the JSON tree.
The second reads one file and reports on the QA vhost.

Exit codes:

- `0` — a report was produced.
- `1` — a usage error (bad options, no input paths given), an input
  file that could not be opened or was neither an access nor an
  error log, no input files found at all, or a failure writing the
  output (HTML or JSON). Both outputs are written atomically
  (`FILE.new`, then renamed onto `FILE`), so a failure never leaves
  a partial file behind; the previous report, if any, stays
  untouched.
- `2` — the inputs parsed fine, but no access-log record matched
  `--host`. This is distinct from `1` because the run itself
  worked; the host argument (or the logs given) is the likely
  mistake.

All error messages go to stderr, prefixed `manno-logreport: `.

When `--json` is given, the file holds the same tree the HTML is
rendered from — `window`, `totals`, `by_day`, `status`, `classes`,
`by_hour`, `busiest`, `routes`, `bots`, `browser`, `clients`,
`probes`, `content`, `errors`, `malformed_sample`,
`unclassified`, and `unclassified_dropped` — plus a `meta` key
recording the inputs read, the host, which CDN-ranges file was used
and its fetch date, which lookup database (if any) was used, when
the report was generated, and the tool's version. The HTML and the
JSON cannot disagree, because the HTML is rendered from this same
tree.

## Getting the logs

On oxygene the logs live at `/var/log/nginx/access.log*` and
`/var/log/nginx/error.log*`; nginx's own rotation leaves the current
file plain and older ones compressed as `.xz`. Copy whatever window
you need — the current file plus however many rotated ones cover
it — into one local directory (`rsync` or `scp`, whichever access
you have), and point the tool at that directory:

    rsync oxygene:/var/log/nginx/'{access,error}.log*' ~/tmp/oxygene-nginx-logs/
    bin/manno-logreport -o report.html ~/tmp/oxygene-nginx-logs

The tool reads `.xz` and `.gz` files directly, so there is no need
to decompress the rotated files first. Copy one generation of each
file: a directory holding both `access.log` and a rotated copy of
the same lines counts every one of them twice, because the tool
reads each input independently and never de-duplicates.

## Rendering and publishing

Two `Makefile` targets wrap the routine:

    make report
    make dist-report

`make report` runs the tool with `-O` over `LOGDIR` (default
`~/tmp/oxygene-nginx-logs`) into `REPORT_DIR` (default
`~/tmp/man-report`) and prints the HTML path. `make dist-report`
copies every `*.html` in `REPORT_DIR` to
`oxygene:/p/netbsd/man/htdocs/r/`, which nginx serves as
<https://man.netbsd.org/r/>, so the directory is the set of
published reports. The JSON sidecars stay local; they carry every
user-agent and probe path seen and are meant for the run-to-run
comparison, not for readers. Both variables can be overridden on
the command line (`make report LOGDIR=…`).

## Reading the report

The report has eleven sections, in this order:

- **Summary** — the window covered, total requests and bytes,
  requests per day, the bot and probe shares, whether the
  logs carried the extended cache/timing fields (see "Extending the
  log format" below), and a per-status-class breakdown.
- **HTTP status distribution** — a table of every status code seen,
  with its share of requests and, where the code means something
  specific to this service, a note: `301` is canonicalization and
  legacy-URL redirection (ADR-0005, ADR-0015); `304` is a
  conditional-revalidation hit (ADR-0003); `429` is nginx's
  `limit_req`, currently keyed on the Fastly POP address rather
  than the end client (see "Extending the log format" below);
  `499` means the client closed the connection before nginx could
  answer; `501` is nginx's own rule for known probe paths (`*.php`,
  `*.cgi`, `wp-includes`, and similar); `502` is fcgiwrap
  unreachable or crashed; `503` with a query string comes from the
  `$qs_error` map, otherwise it means the upstream was unavailable.
  Below the table, a stacked chart shows the status-class mix
  (`2xx`/`3xx`/`4xx`/`429`/`499`/`5xx`/other) per day.
- **Traffic over time** — requests and bytes per day, requests by
  hour of day across the whole window, and the busiest individual
  (day, hour) slots.
- **Partial days** — nginx rotates its logs at 21:00, so the first
  and last calendar day of any copy are usually covered only in
  part. The report keeps every record in the totals but marks such
  days: the per-day tables show the hours covered (`2026-08-14
  (3.0 h)`), the per-day chart fades their columns, and the
  Summary's "requests per full day" averages over the full days
  only. A day counts as full at 23.5 hours or more of coverage, so
  a copy taken a few minutes before midnight still counts.
- **Routes** — how many requests fell into each URL shape: `health`
  (the liveness probe), `static` (robots.txt, favicon, and similar),
  `pathinfo` (the live, current route — nginx rewrites `/` to
  `/cgi-bin/man-cgi$request_uri`, so this is where all current
  traffic to real manual pages arrives, including root-level arch
  pages like `/x86/boot.8` — ARCH must be one of the names in
  `lib/manno_logreport/data/arches`, not merely lowercase-shaped,
  so `/etc/passwd.5` stays a probe; these pages are mostly
  redirected per ADR-0009 — and bare names such as `/ls` or
  `/rc.conf`, which the CGI answers with a menu of matches or a
  301 to `/name.sect`), `api` (the CGI's list endpoints
  `/api/v1/archlist`, `/api/v1/colllist` and `/api/v1/sectlist`,
  ADR-0008; any other `/api` path is `other`), `report` (the
  published log reports under `/r/`, see "Rendering and
  publishing"), `cgi-query` and
  `cgi-pathinfo` (direct hits on `/cgi-bin/man-cgi`, with the query
  string or the path-info form), `legacy-man` (the old `/man/...`
  path), `legacy-html` (old-style pre-rendered HTML page paths), and
  `other` (everything else — mostly probes; see below). `cgi-query`
  and `legacy-man` are the routes this service wants to migrate
  traffic away from; a growing share there, rather than falling,
  is worth investigating. When any input carried the extended log
  fields, this section also breaks cache status and request time
  down by route, with percentiles for both the whole request and the
  upstream (fcgiwrap) wait; a cache hit or an nginx-served response
  has no upstream time, so the two counts differ.
- **Named bots** — a table of every user agent that matched a known
  bot signature (search engines, AI crawlers, generic bot/scraper
  patterns), with its request count, bytes, whether it fetched
  `robots.txt`, and its status mix. The two catch-all rows are in
  here too: `generic-bot` (a bot, crawler or HTTP-library signature
  with no specific name) and `empty-ua` (no user agent at all), so
  the table's total is the Summary section's bot share. This table
  is exact: a request either matches one of the known signatures or
  it does not, so there is no judgment call here about which rows
  belong. Rows are named after the user-agent token, except Meta's
  two crawlers, shown as `Meta-External-Agent` (the
  `meta-externalagent` bulk crawler) and `Meta-Preview`
  (`facebookexternalhit`, link previews) so they read as one family.
- **Browser-like traffic signals** — everything whose user agent did
  *not* match a known bot signature. This section is evidence, not
  a verdict: a plain-browser user agent with no referer and a wide
  spread of unusual paths is what a stealth crawler that spoofs its
  UA looks like, but it is also what a curious human with a
  bookmark looks like. Use the referer-host and UA-family tables,
  and the per-CDN-address breadth table, to spot patterns worth a
  closer look, not as an automatic classification.
- **Probes** — requests that fell outside the legitimate URL space,
  or that matched a probe signature even on a legitimate route
  (so `/NetBSD-11.0/wp-login.php` counts here too). Membership is a
  whitelist: a path either matches one of the known route shapes
  above or it is `other`, and probe *family* only labels requests
  that are already in scope this way (`php`, `wordpress`, `dotfile`,
  `admin`, `cgi-bin-other`, `traversal`, `shell`, or `other-probe`
  for anything on the `other` route that matched no specific
  family). The `shell` family looks only at the query string, since
  that is where a shell-injection attempt through a CGI-style
  request would appear, and it matches only shapes that cannot be a
  manual-page name: this site's own query form is
  `?COMMAND[+SECTION[.ARCH][+COLLECTION]]`, so `?curl`, `?chmod+2`
  and the like are ordinary lookups, and only `/bin/sh`, `$(...)`,
  a backtick, `/etc/passwd`, or `chmod` followed by an octal mode
  count. The "answered with 2xx" table should
  normally be empty; anything there is a probe that got further
  than it should have.
- **Clients** — top client addresses by request count, with the
  maximum distinct-paths-per-day ("breadth") each reached, how many
  days it was seen, and whether it is a CDN address. Breadth is
  counted per day up to a cap of 2 000 distinct paths, after which
  counting stops: a client past the cap is shown as `≥ 2 000`, a
  floor rather than a count, in both this table and the
  per-CDN-address one under "Browser-like traffic signals". Right
  now this section's CDN share is expected to sit at (or very
  near) 100%:
  every request nginx sees currently arrives with Fastly's own
  connecting address as `$remote_addr`, because the `fastly` include
  that restores the real end-client address has not been applied to
  the man.netbsd.org vhost yet (see "Extending the log format"
  below). Until it lands, this section mostly measures Fastly POPs,
  not end clients; the per-CDN-address breadth table under
  "Browser-like traffic signals" says so explicitly. Country and ASN
  columns only appear when a lookup database was found (see "Lookup
  databases" below).
- **Content** — the most-requested pages, by collection, section,
  and architecture; the same for 404s; and redirects broken down by
  route.
- **Backend health** — daily counts of the access-log signals that
  point at backend trouble (`429`, `499`, `502`, `503`) alongside
  the error-log families, error samples, and the busiest ten-minute
  error windows; falls back to a note when no error log was
  supplied. When the extended fields are present, this section also
  shows cache status per day.
- **Unclassified paths** — anything that matched no route and no
  probe family. A legitimate-looking path here means the route
  whitelist in `lib/manno_logreport/classify.py` needs a new entry.

The counters behind the top-N tables are keyed on strings a client
chooses, so each has a bound and stops accepting new keys once it is
full. The probe path, query-string and user-agent counters, and the
unclassified-path counter, hold 200 000 distinct keys; the content
counters (200s and 404s) hold 2 000 000, because they are keyed on
pages the service actually answered and a fortnight of real traffic
already carries half a million of those — dropping a page that first
appears late in the window would bias those tables, not merely cap
them. The totals are unaffected either way — every request is still
counted — but hits on keys past a limit are missing from that table,
and the footer says how many there were.

The report footer always lists the inputs read (with line counts,
and for error logs how many lines were skipped as continuations or
foreign text), which CDN-ranges file was used and when it was
fetched, which lookup database (if any) was used and its build date
(including a problem with one database when the other still
opened), and how many lines could not be parsed, with a short
sample. That last count is nginx's own junk request lines — a `"-"`
request field, or raw TLS bytes sent to the plain-text port, both
logged as status 400 — counted for the selected host only, and
deliberately left out of the status table, since they are noise
about what reached the port rather than requests the service
answered.

## Extending the log format

The current oxygene `log_format vhost`, defined in
`~/src/cloud/ansible/roles/common/templates/nginx/nginx.conf.j2`,
is:

    log_format vhost
        '$server_name:$server_port '
        '$remote_addr - $remote_user [$time_local] '
        '"$request" $status $bytes_sent '
        '"$http_referer" "$http_user_agent"';

The parser also understands three more fields, appended after the
user agent:

    log_format vhost
        '$server_name:$server_port '
        '$remote_addr - $remote_user [$time_local] '
        '"$request" $status $bytes_sent '
        '"$http_referer" "$http_user_agent" '
        'cache=$upstream_cache_status rt=$request_time urt=$upstream_response_time';

The extra fields are optional `key=value` pairs, so one parser reads
lines from both before and after the change: whichever lines carry
`cache=`/`rt=`/`urt=` contribute to the cache-status and
request-time breakdowns (the Routes and Backend health sections
report how many records that was); older lines without them are
counted everywhere else exactly as before. Future fields should
follow the same append-only rule — add them after the user agent,
never insert or reorder — so old and new logs keep parsing together
without a version flag.

Separately, the man.netbsd.org vhost does not yet forward the real
client address through Fastly. That fix lives entirely in the
`~/src/cloud` Ansible tree, not in this repository, and not in a
generated file: vhosts are rendered by
`roles/common/templates/nginx/sites-available/fqdn.j2`, which emits
an `include NAME;` line for each entry of a site's `includes:` list
(see `host_vars/banff.yml` for a site that already sets
`includes: [localnets]`). man.netbsd.org's site config is
`website_configurations['man.netbsd.org']` in `group_vars/all.yml`,
and it currently has no `includes:` key at all. The fix is to add
`includes: [fastly]` to that entry and apply the playbook to
oxygene; the `fastly` file itself (`/etc/nginx/fastly`, carrying
`set_real_ip_from` for Fastly's published ranges and
`real_ip_header X-Forwarded-For`) is already generated from that
tree's `cdn.j2` template and `roles/common/defaults/main/cdns.yml`
data, so nothing else needs
to change on the nginx side. Once the include is in place,
`$remote_addr` becomes the actual client address instead of the
connecting Fastly POP, and the Clients and Browser-like traffic
signals sections stop being dominated by CDN addresses.

## Dependencies

`manno-logreport` needs Python 3.10 or later and nothing else from
the standard library's perspective — no virtualenv, no `pip
install` in the normal workflow. The 3.10 floor is not arbitrary:
`lib/manno_logreport/logparse.py` declares its record types with
`@dataclass(slots=True)`, which Python only supports from 3.10
onward, and those same records type their optional fields as
`cache: str | None`, `rt: float | None`, and `urt: float | None` —
the `X | None` union syntax that PEP 604 added in 3.10, evaluated
here without a `from __future__ import annotations` import, so it
needs the 3.10 runtime to parse the class bodies at all. Both the
NetBSD host (equinoxe) and Debian carry Python 3.13, well above the
floor.

One optional import, guarded so its absence only narrows a report
rather than breaking a run: `maxminddb`, needed for the country and
ASN columns in the Clients section (see "Lookup databases" below).
On Debian, install `python3-maxminddb`. In pkgsrc,
`geography/py-maxminddb` builds the same library (version 3.1.1 in
the local tree); it installs as `py3NN-maxminddb`, where `NN` is
whichever Python version pkgsrc's default resolves to. Without the
module, or without any database found, the report still runs to
completion; it just leaves the Country/ASN columns off and says why
in a footnote.

## Lookup databases

`lib/manno_logreport/geo.py` looks for a country/city database and
an ASN database independently, only when `--geoip-db`/`--asn-db`
were not given explicitly. For each kind it walks a fixed list of
file-name patterns in order — country/city:
`GeoLite2-City.mmdb`, `GeoLite2-Country.mmdb`,
`dbip-city-lite-*.mmdb`, `dbip-country-lite-*.mmdb`; ASN:
`GeoLite2-ASN.mmdb`, `dbip-asn-lite-*.mmdb` — and for each pattern,
in turn, checks these directories in order:

    /usr/share/GeoIP
    /var/lib/GeoIP
    /usr/pkg/share/GeoIP
    /usr/local/share/GeoIP

The first pattern that matches anything, anywhere in that directory
list, wins (taking the lexicographically last match, so a
version-numbered DB-IP file resolves to its newest download); the
search then moves to the ASN patterns independently. In practice
this means a MaxMind GeoLite2 file always outranks a DB-IP Lite
file when both are present.

MaxMind's GeoLite2 databases need a (free) MaxMind account; refresh
them with `geoipupdate`, or download them by hand into
`/usr/share/GeoIP` if `geoipupdate` is not set up on the host. DB-IP
Lite is the fallback that needs no account at all — the
`dbip-*-lite-*.mmdb` files it publishes drop into the same
directories and are picked up the same way, just after GeoLite2 in
the search order. Whichever database (or pair of databases) was
actually used, its type, path, and build date are recorded in the
report footer, so a stale database is visible without checking the
filesystem.

## CDN ranges

The Clients section needs to know which addresses are Fastly's own
so it can tell CDN traffic apart from everything else (see "Reading
the report" above). `make refresh-cdn` refreshes that list: it
fetches `https://api.fastly.com/public-ip-list` and reformats the
result into `lib/manno_logreport/data/fastly.cidr`, one CIDR per
line, with a header recording the source URL and the fetch date.
The file is committed, so a report run needs no network access and
always gets a known set of ranges. The same ranges reach nginx from
a separate copy in the `~/src/cloud` Ansible tree,
`roles/common/defaults/main/cdns.yml`, which renders
`/etc/nginx/fastly`; the two are refreshed independently, so a
`set_real_ip_from` range nginx trusts and a range this report calls
CDN can drift apart. `--cdn-ranges FILE` overrides the
packaged file with another CIDR list in the same format, useful
when reporting on a period whose Fastly ranges have since changed,
or against a different CDN entirely.

## Arch list

The root-level arch-page route shape (`/ARCH/page.sect`, e.g.
`/x86/boot.8`) is only real when ARCH is one of the names in
`lib/manno_logreport/data/arches`, loaded at import time into
`classify.ARCHES`. That file is a plain copy — one arch per line,
in order, header lines noting its source and copy date — of
`/p/netbsd/man/man/archlist` on oxygene, the same list man-cgi
itself serves. A new NetBSD port needs this file refreshed by hand
(there is no `make` target, unlike the CDN ranges above); until
then its pages fall back to the `other`/probe route, same as any
other unlisted path.

## Tests

`make test-python` runs the Python unit test suite
(`tests/python/test_*.py`, via `python3 -m unittest discover`) with
`lib/` on `PYTHONPATH`. Fixture logs — a small access log, one
rotated and `.xz`-compressed, and an error log, covering the shapes
exercised by every section above — live in `tests/fixtures/logs/`.
