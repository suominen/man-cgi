# Fastly configuration notes

The Fastly service is **not** in this repository or in `~/src/cloud`:
it is configured in the Fastly UI. The CGI drives it through
`Surrogate-Control` and `Surrogate-Key` (`caching.md`), and the
generated boilerplate VCL does almost everything those headers
need on its own: TTLs from `Surrogate-Control`, purging by key,
`stale-while-revalidate`, shielding through hel-helsinki-fi,
health-check failover from oxygene to lcm (`runbook.md`).

This file records what the service needs beyond the boilerplate
and why.

## Serving stale on error

`stale-if-error` in `Surrogate-Control` marks how long past its
`max-age` an object may be served while the origin fails. Fastly
distinguishes three ways of failing, and acts on the header by
itself in only one of them:

- A backend that is *sick* — failing its health check — is served
  around automatically: stale content goes out with no VCL. With
  the failover in place that is the state where both oxygene and
  lcm are sick.
- A backend that *answers* a 5xx reaches `vcl_fetch` with
  `stale.exists` set; the VCL has to choose the stale object with
  `return(deliver_stale)`. Otherwise the boilerplate caches the
  error for a second and serves it.
- A backend that is *unreachable* (connection or TLS failure,
  timeout) reaches `vcl_error` with `stale.exists` set, and the
  same choice applies; otherwise Fastly's own 503 goes out.

Two VCL snippets, type `fetch` and type `error`, make the choice.
Both test `stale.exists`, which is true only while a cached object
is inside its `stale-if-error` window, so a request with nothing
stale to serve behaves as before.

Snippet `serve-stale-on-error`, type `fetch`:

    if (beresp.status >= 500 && beresp.status < 600) {
      if (stale.exists) {
        return(deliver_stale);
      }
    }

Snippet `serve-stale-on-error`, type `error`:

    if (obj.status >= 500 && obj.status < 600) {
      if (stale.exists) {
        return(deliver_stale);
      }
    }

Snippets are added under Edit configuration, VCL, VCL snippets,
and take effect with the version they are activated in. A `fetch`
snippet is inserted at the boilerplate's `#FASTLY fetch` point,
ahead of the boilerplate's one restart on a 500 or 503, so a stale
object is served before the retry that would move the request to
lcm; with nothing stale the restart proceeds as before.

Not the **Serve stale** switch under Settings: it enables the same
mechanism, but with its own stale TTL (12 hours for both
`stale-while-revalidate` and `stale-if-error`), which replaces
the per-class values the CGI sends. The snippets above set no
TTLs, so the header stays in charge.

Verification: with the snippets active, a request served past its
`max-age` during an origin error is a `HIT` whose `Age` exceeds
the object's `max-age` (`Fastly-Debug: 1` shows the TTL and grace
in `Fastly-Debug-TTL`); without them the same request returns the
origin's 503.

Service version 5 (2026-08-08), the version live at the 2026-08-09
cutover, is boilerplate only.

## References

Fastly documentation, as of 2026-08-27:

- Lifetime and revalidation — the stale-while-revalidate and
  stale-if-error concepts, and which subroutine each origin
  failure reaches:
  <https://www.fastly.com/documentation/guides/concepts/cache/stale>
- Serving stale content — the recommended `vcl_fetch` and
  `vcl_error` VCL, and the Serve stale switch with its 12-hour
  default:
  <https://www.fastly.com/documentation/guides/full-site-delivery/performance/serving-stale-content>
- `stale.exists`:
  <https://www.fastly.com/documentation/reference/vcl/variables/cache-object/stale-exists/>
- `vcl_fetch` (`return(deliver_stale)`):
  <https://www.fastly.com/documentation/reference/vcl/subroutines/fetch/>
- `vcl_error` (when it runs; a 5xx answer does not reach it):
  <https://www.fastly.com/documentation/reference/vcl/subroutines/error>
- Using VCL snippets:
  <https://www.fastly.com/documentation/guides/full-site-delivery/fastly-vcl/vcl-snippets/using-vcl-snippets/>
- `Surrogate-Control` (preferred over `Cache-Control` at Fastly):
  <https://www.fastly.com/documentation/reference/http/http-headers/Surrogate-Control/>
