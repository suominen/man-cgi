---
status: accepted
date: 2026-09-02
---

# 0022: Hourly browser and nginx TTLs for every content class

## Context and Problem Statement

After ADR-0015 and the home-class alignment of 2026-09-01, three
response classes still carried browser or nginx lifetimes above an
hour: the 301 canonicalizations (24 hours in both tiers), the 302
collection fallback (3 hours at nginx), and frozen release pages
(24 hours in both tiers). Each held its numbers on a cost argument:
ADR-0015 explicitly rejected an hour at nginx for the 301s: full
refetches "24× as often as the chosen value ... for no
operational gain".

The costs no longer look like costs, and the gain now exists. The
404s already revalidate hourly at nginx; both redirect flavors are
emitted before man(1) is involved and are cheaper to refetch in
full than a 404 is to revalidate; and a frozen page revalidates by
the same 304 path the current-collection pages — a larger and
hotter URL set — already exercise every hour. Meanwhile the long
browser lifetimes sit in the one tier that cannot be purged: a
browser that has loaded a frozen page or followed a 301 holds it
for a day, which is exactly the tier ADR-0002 said should cache
briefly.

## Considered Options

- Keep the ADR-0015 values
- Hourly browser and nginx TTLs for every content class, Fastly
  untouched (chosen)
- Shorten the Fastly TTLs as well

## Decision Outcome

Chosen option: hourly browser and nginx TTLs everywhere, Fastly
untouched.

Every cacheable content class — pages current and frozen, menus,
indexes, the home page, 404s, both redirect classes, the API
lists — now shares `max-age=3600` for browsers and
`X-Accel-Expires: 3600` for nginx. The classes differ only at the
Fastly tier, which keeps its lifetimes (a day for current pages,
404s and the 302; a week for API lists; 30 days for 301s; 90 days
for frozen pages) and stays purgeable by Surrogate-Key. This is
ADR-0002's own principle — browsers and nginx brief because they
cannot be purged well, Fastly long because it can — applied
uniformly. The health check keeps its 30 seconds in all tiers
(it must not report stale health), and the POST 303 stays
`no-store` (ADR-0007).

Why ADR-0015's rejection of the hourly 301 no longer holds:

- The cost is now quantified. The crawled redirect space measured
  1.16 M arch-301 requests over 2026-08-14..28 (TODO.md) — about
  83 k a day at Fastly. Even if every one reached the origin that
  is one invocation per second of the cheapest path in the script,
  and Fastly's 30-day hold behind a single shield POP keeps the
  real rate far below that. nginx expiry of a redirect is a full
  refetch (redirects cannot 304), but a full 301 costs less than
  the 404 revalidations that already run hourly.
- The gain now exists. Deployment step 9's redirect wait drops
  from a day (301) / 3 hours (302) to an hour, frozen pages pick
  up a `MINLASTMOD` bump at nginx within an hour instead of a day,
  and browsers stop pinning day-old redirects and frozen pages —
  the wait anyone sees after a release or a redirect-shape change.
- Bots do not get more expensive. Crawlers revisit on their own
  schedule; `max-age` is at most a hint to them, and the Fastly
  lifetimes bot traffic actually leans on are unchanged, so edge
  request volume from crawlers is unaffected.

### Consequences

- Good, because the tier policy is uniform: one browser/nginx
  lifetime for all content, class distinctions only where purging
  works. The TTL table stops needing per-class explanation below
  the Fastly column.
- Good, because a redirect-shape deploy is now "deploy, wait an
  hour, `manno-purge redirect`", and a wrong 301 is gone from
  browsers and nginx within an hour.
- Good, because output-affecting deploys reach frozen pages at
  nginx within an hour through the ADR-0011 floor.
- Bad, because 301 refetches at the origin are up to 24× more
  frequent per nginx-held URL, and frozen pages now revalidate
  hourly instead of daily — bounded by Fastly's shield hold and,
  for the redirects, by the response being the script's cheapest.
- Bad, because this forecloses the "raise the redirect TTLs"
  option in TODO.md's arch-301 item at the browser and nginx
  tiers; the remaining levers there are serving the canonical
  body directly or steering crawlers.
- Neutral: objects cached before this change keep the lifetimes
  they were filled with and age out on their own — the old
  redirect holds expire within a day of the deploy.

## Pros and Cons of the Options

### Keep the ADR-0015 values

- Good, because the origin sees the fewest redirect refetches and
  frozen-page revalidations.
- Bad, because the browser tier — the one that cannot be purged —
  holds redirects and frozen pages a day, and every
  redirect-shape deploy waits a day on nginx.

### Hourly browser and nginx TTLs everywhere (chosen)

- Good, because staleness in the unpurgeable tiers is bounded by
  an hour for everything, with the origin cost measured and
  negligible.
- Bad, because the origin refetch and revalidation rates rise.

### Shorten the Fastly TTLs as well

- Good, because even edge staleness would be bounded by clocks
  rather than purges.
- Bad, because Fastly is the tier where purging works (ADR-0004)
  and the long lifetimes are what keep the crawled URL space off
  the origin; shortening them buys nothing purges do not already
  provide.

## More Information

Amends ADR-0015: the 302 keeps its ADR-0015 shape with nginx
tightened from 3 hours to an hour, and the 301's 24-hour
browser/nginx holds — including the explicitly rejected hourly
alternative — are replaced by this record. ADR-0015's record
keeps its original wording; this one carries the change. The
policy table is in `../caching.md`; the redirect propagation
procedure is `../deployment.md` step 9.
