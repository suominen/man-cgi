---
status: accepted
date: 2026-08-28
---

# 0019: Python for tooling, stdlib only; bin/ CLI over lib/ package; append-only log-format extension

## Context and Problem Statement

`manno-logreport` needs to turn nginx access and error logs into an
HTML report with tables and SVG charts, plus an optional JSON
sidecar, from a parser that carries state across lines (multi-field
records, running aggregates, reservoir sampling for percentiles).
`src/man-cgi` is POSIX shell for good reasons recorded in ADR-0010,
but those reasons are about the CGI script's own constraints
(NetBSD base, no build step, one process per request); a reporting
tool run by hand or from cron is a different problem, and shell or
awk stop being the right fit once the job includes HTML/SVG
emission and a parser with state to carry. What should this tool be
written in, and how should it sit next to the existing shell-based
repository?

## Considered Options

- Python, standard library only (chosen)
- POSIX shell + awk, extending the existing toolset
- Perl

## Decision Outcome

Chosen option: Python 3.10 or later, standard library only, with
any third-party import guarded so its absence narrows a report
rather than breaking a run.

1. Python ≥ 3.10, standard library only. No virtualenv, no `pip
   install` in the normal workflow; the only optional import is
   `maxminddb` (see below), and it degrades gracefully when absent.
2. `bin/` holds a thin, suffix-less executable (`bin/manno-logreport`)
   that does argument parsing and wiring only; the implementation
   lives as an importable package under `lib/manno_logreport/`.
   Tests live under `tests/python/`, run with the standard-library
   `unittest` runner (`make test-python`).
3. The nginx log format is extended by appending `key=value` fields
   after the user agent, never by inserting or reordering existing
   fields:

       log_format vhost
           '$server_name:$server_port '
           '$remote_addr - $remote_user [$time_local] '
           '"$request" $status $bytes_sent '
           '"$http_referer" "$http_user_agent" '
           'cache=$upstream_cache_status rt=$request_time urt=$upstream_response_time';

   One parser reads both the lines already on disk and every line
   logged after the format changes; the presence or absence of the
   trailing fields, not a version marker, is what tells them apart.

### Consequences

- Good, because the dependency story for anyone running the report
  is "install python3" — true today on both Debian and the NetBSD
  host (equinoxe carries Python 3.13, as does Debian 13), and
  nothing else to provision.
- Good, because `maxminddb` is the only optional package in the
  whole tool, and its absence (or a missing database) narrows one
  report section instead of failing the run; see `docs/logreport.md`
  under "Dependencies" and "Lookup databases".
- Good, because the append-only rule means old and new log lines
  parse with the same code, so the format can change in the field
  (this decision already adds one such extension) without a
  migration step or a flag day; future fields should follow the
  same rule.
- Neutral, because `bin/` + `lib/` splits this tool from
  `src/man-cgi` structurally as well as by language, matching how
  `tools/` already holds the one-off RCS import (ADR-0014) as a
  separate thing from the CGI script itself.
- Bad, because Python's own style (PEP 8) is spaces-only, so
  `lib/manno_logreport/` and `tests/python/` are the one place in
  this repository that cannot follow the tab-based indentation
  convention used everywhere else in this tree.

## Pros and Cons of the Options

### Python, standard library only

- Good, because it has everything the job needs built in:
  `argparse`, `re`, `dataclasses`, `json`, `gzip`/`lzma` for rotated
  logs, and enough string/SVG assembly to emit self-contained HTML
  with no template engine.
- Good, because `@dataclass(slots=True)` (Python 3.10+) gives the
  per-line record types cheap, typo-checked attribute access without
  hand-written `__init__`/`__slots__` boilerplate, and the `X | None`
  union syntax (also 3.10, PEP 604) reads naturally for the optional
  extended-format fields (`cache`, `rt`, `urt`).
- Bad, because it is a second language in a repository that is
  otherwise POSIX shell, so contributors need both.

### POSIX shell + awk

- Good, because it would keep the whole repository in one language,
  consistent with ADR-0010's preference for the boring, already-known
  tool.
- Bad, because HTML/SVG generation and a parser that carries running
  state (per-route reservoirs, per-day tallies, top-N tables) push
  awk into territory it is not good at; the result would be harder
  to read and test than the equivalent Python, undoing the
  simplicity argument that keeps `src/man-cgi` in shell.

### Perl

- Good, because it is a natural fit for line-oriented log parsing
  and is available in pkgsrc.
- Bad, because it is not in the NetBSD base system, so it would add
  a real dependency to a host (oxygene, or wherever the report is
  run) that Python's presence does not.

## More Information

`docs/logreport.md` is the operator-facing documentation for this
tool: usage, the section-by-section report guide, the log-format
extension and the still-pending `fastly` include for the real
client address, dependencies, and the lookup-database story.
