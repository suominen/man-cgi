---
status: accepted
date: 2026-08-09
---

# 0010: Keep the shell CGI instead of rewriting

## Context and Problem Statement

man-cgi is a ~1400-line POSIX-shell CGI, forked per request by
fcgiwrap. Whether it should be rewritten in a faster or
persistent-server language (Python, Perl, C, Go) has hung over
every improvement round: ADR-0001 lists "a possible
reimplementation" among the decisions this series exists to
capture, and ADR-0006 deferred ETags partly because
`If-None-Match` handling in shell wasn't worth it. The 2026-08-09
caching cutover (ADR-0002, ADR-0003, ADR-0009) was the opposite
bet — make origin traffic small enough that renderer cost stops
mattering. Origin logs spanning the cutover now exist to test
that bet and settle the question.

### Measured origin load, 2026-08-09 (EEST)

Requests for man.netbsd.org reaching origin nginx from Aug 8
21:00 to Aug 9 20:06 (oxygene, or lcm during oxygene's two
deployment outages). Both deployments dropped every cache tier —
nginx's cache cleared on oxygene and on lcm, then a full Fastly
purge — so every row below the first measures cold or refilling
caches:

| Phase                 | Window      | Requests |  QPS | Peak min     |
|-----------------------|-------------|---------:|-----:|-------------:|
| Warm caches, old CGI  | 21:00-11:43 |  721,750 | 13.6 | 3,392 (57/s) |
| 1.100 full drop (lcm) | 11:44-12:27 |   36,100 | 13.7 | 3,053 (51/s) |
| Refill storm, old CGI | 12:28-17:07 |  346,819 | 20.6 | 2,823 (47/s) |
| 1.103 full drop (lcm) | 17:08-18:04 |   21,668 |  6.3 |   705 (12/s) |
| Refill, new CGI       | 18:05-20:06 |   62,503 |  8.6 | 1,058 (18/s) |

What the data says:

- No warm-cache measurement of the new CGI exists yet: every
  post-deployment window ran against cleared nginx caches and a
  purged edge, so warm-cache load will sit below the final
  window's 8.6 QPS. Even these refill totals overstate what
  reaches the CGI — the log format carries no
  `$upstream_cache_status`, so nginx cache hits are included and
  the numbers bound CGI load only from above.
- The only failure came after the first purge (~12:18, visible
  in lcm's log as its traffic tripling): 1,198 502s on lcm while
  it was still the sole origin, then 31,331 on oxygene between
  12:29 and 15:42 — 10% of the storm's non-rate-limited traffic,
  every one logged as fcgiwrap's socket refusing the connection.
  Renders queued faster than the worker pool drained them;
  nothing broke inside the CGI itself.
- The second full drop, served by 1.103, produced no 502s at
  all: lcm carried the failover window clean at ~6 QPS and
  oxygene refilled from the purge at 8.6 QPS mean. Of that
  refill traffic, 37% (23,085) were 301 canonicalization
  redirects, almost all arch (ADR-0009) — cacheable (ADR-0005),
  cheap to render, and the object-space collapse working as
  designed.
- The storm had a single driver. The origin logs identify
  clients only by User-Agent (client addresses are Fastly POPs),
  and one agent — Lightpanda/1.0 — accounts for 73% of oxygene's
  whole log, 87% of the storm window, 93% of all 429s, and
  94% of all 502s, ignoring sustained rate-limiting throughout.
  Self-identified crawlers otherwise kept reasonable rates
  (table over oxygene's log alone):

  | Agent              | Requests | Peak min     |     429 |    502 |
  |--------------------|---------:|-------------:|--------:|-------:|
  | Lightpanda/1.0     |  821,888 | 3,147 (52/s) | 118,506 | 29,444 |
  | GPTBot             |   71,637 |    177 (3/s) |     254 |     25 |
  | Amazonbot          |   59,739 |   88 (1.5/s) |   2,588 |    496 |
  | Sogou web spider   |   14,646 |   82 (1.4/s) |     482 |    227 |
  | 9 others, combined |   16,526 |  ≤41 (0.7/s) |     510 |    257 |

  The nine others are bingbot, YandexBot, Googlebot, Applebot,
  ClaudeBot, Bytespider, meta-externalagent, Barkrowler, and
  CCBot — none peaked above 41 requests a minute.

  Adding lcm's log (65,888 in-window requests, mostly the two
  failover windows) changes little: Lightpanda becomes 862,583
  of 1,197,000 combined requests (72%), its 429/502 shares stay
  at 93% and 94% (it likewise caused 1,439 of lcm's 1,497 502s),
  its 3,147-request peak minute stands, and each of the nine
  small crawlers still stays at or under 41 requests a minute.

## Considered Options

- Keep the improved shell CGI
- Rewrite in Python (persistent FastCGI/WSGI service)
- Rewrite in Perl (CGI, or persistent PSGI service)
- Rewrite in C (compiled CGI)
- Rewrite in Go (persistent FastCGI/HTTP service)

## Decision Outcome

Chosen option: keep the improved shell CGI. Post-cutover origin
load — measured while every cache tier was still refilling from
a full purge — stayed at single-digit QPS, itself an upper bound
on what reaches the CGI; warm-cache load will sit lower still.
Fork-per-request shell is nowhere near a bottleneck there, and
the 304 fast path (ADR-0003) prices revalidation at a `man -w`
plus a `stat`. The one observed failure mode, fcgiwrap refusing
connections under a deliberately cold cache, is a worker-pool
capacity limit: a faster renderer would shrink it, but cache
policy already avoids it (wipes are rare and operator-initiated,
`use_stale updating` serves during refresh) and the open fcgiwrap
capacity review addresses the residual. Nor was the storm
organic load: one crawler drove 87% of it at a 52/s peak while
ignoring sustained 429s, and the service is deliberately not
sized to satisfy that — rate limiting and caching absorb the
abuse, while the self-identified crawlers that kept to
single-digit peak rates were served throughout. Everything a rewrite
would genuinely buy — cheap content hashing for ETags (ADR-0006),
UTF-8 output, mandoc markup — is tracked as its own TODO item,
and none of them is forced at this load.

### Consequences

- Good, because thirty years of accreted rendering behavior
  carries no migration risk — the test suite pins the HTTP
  surface, not the renderer's internals, so a rewrite would
  re-risk everything the tests don't cover.
- Good, because dependencies stay NetBSD base plus fcgiwrap, and
  the RCS + TDD + rsync deploy workflow continues unchanged.
- Bad, because cold-cache refills stay fork-bound: deliberate
  wipes keep leaning on the lcm failover and on the fcgiwrap
  worker-capacity review still open in TODO.md.
- Bad, because the sed HTMLizer keeps blocking UTF-8 output, and
  ETag stays skipped (ADR-0006) until some renderer change makes
  content hashing cheap.

Revisit if steady-state origin QPS grows by an order of
magnitude, or if cold-cache refills become routine rather than
operator-initiated.

## Pros and Cons of the Options

### Keep the improved shell CGI

- Good, because it is proven at the measured load, including a
  4.7-hour cold-cache storm it survived at 20 QPS mean with 502s
  held to a tenth of the non-rate-limited traffic — and a second
  full cache drop it served without a single 502 once 1.103's
  redirect collapse had landed.
- Good, because the rewrite cost is zero and the operational
  surface (fcgiwrap socket, nginx FastCGI config) is unchanged.
- Bad, because per-request cost is a full fork-and-render, the
  binding constraint whenever caches are cold.
- Bad, because shell string handling caps future work: no cheap
  hashing, single-byte sed transforms.

### Rewrite in Python

- Good, because a persistent WSGI/FastCGI process amortizes
  startup, hashes content cheaply (ETag), and handles UTF-8
  natively.
- Bad, because it adds a pkgsrc runtime plus a long-running
  service to operate on both origin hosts, and the interpreter
  is the slowest of the candidates for the render loop.
- Bad, because the whole rendering behavior must be re-verified,
  not just the HTTP surface the tests pin.

### Rewrite in Perl

- Good, because the sed HTMLizer would translate almost directly
  into Perl regexes, making it the lowest-friction porting
  target for the render logic.
- Bad, because as a plain CGI it keeps the fork-per-request
  model (gaining little), and as PSGI it adds the same
  persistent-service burden as Python — either way a pkgsrc
  runtime NetBSD base doesn't provide.

### Rewrite in C

- Good, because it needs nothing beyond base and forks fastest
  of all options.
- Bad, because it is the most effort and risk for what is mostly
  string transformation, with memory-safety liability on
  crawler-supplied input.

### Rewrite in Go

- Good, because one static binary as a persistent server would
  absorb refill storms outright and make ETag/UTF-8 trivial.
- Bad, because it replaces the entire fcgiwrap contract with a
  new service to supervise, pulls a toolchain from pkgsrc, and
  requires the same full behavioral re-verification.

## More Information

Aggregates were computed 2026-08-09 with awk over vhost-filtered
nginx access logs copied from oxygene and lcm; the raw logs stay
out of the repo (size, client addresses). Window edges come from
the two service gaps in oxygene's access log (11:44-12:27 and,
after a six-second trickle, 17:08-18:04, when the Fastly health
probe failed traffic over to lcm) matched against the RCS checkin
times of man-cgi 1.100 (08:29:30 UTC = 11:29 EEST) and 1.103
(13:58:07 UTC = 16:58 EEST). Each deployment ran the same
procedure: stop nginx on oxygene, clear its cache, restart; the
same on lcm; then a full Fastly purge. Only oxygene's wipes
register as gaps — lcm's much faster cache disk makes its wipe
brief enough not to show. The first purge is visible in lcm's log
at ~12:18, when its traffic tripled and its 502s began (oxygene
still out); the second shows only as the gentle ramp to oxygene's
18:49 peak after it returned. The 502 diagnosis is from
oxygene's error log: 31,417 `connect() to
unix:/var/run/fcgiwrap.socket failed (61: Connection refused)`
entries against 31,339 access-log 502s across all vhosts (the
few extra refusals left no access line).

Related: ADR-0002/ADR-0003 produce the caching behind these
numbers; ADR-0009 the steady-state 301 share; ADR-0006's
"revisit if the renderer is ever rewritten" note stays dormant.
TODO.md tracks the fcgiwrap capacity review, UTF-8 output, and
the `mandoc -T html` spike as separate items.
