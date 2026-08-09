---
status: accepted
date: 2026-08-09
---

# 0001: Record architecture decisions

## Context and Problem Statement

The man.netbsd.org service spans several systems (a CGI script, nginx
with a FastCGI cache, Fastly, and build machinery for the manual-page
trees). Design decisions — caching policy, purge vocabulary, URL
canonicalization, a possible reimplementation — have long-lived
consequences and non-obvious trade-offs. Without a record, the
rationale evaporates and decisions get relitigated or accidentally
reversed.

## Considered Options

- MADR-style architecture decision records in this repository
- Rationale spread across commit messages and README prose
- No records

## Decision Outcome

Chosen option: MADR-style records, one file per decision, in
`docs/adr/`, numbered in assignment order (`NNNN-title.md`), indexed
in `docs/adr/README.md`, using `template.md`.

### Consequences

- Good, because each decision's context, options, and rationale
  survive independently of conversations and commit history.
- Good, because superseding (never rewriting) landed records keeps an
  honest trail.
- Bad, because records take discipline to write and maintain.

## More Information

Records are written when their decision lands. Operator instructions
stay out of ADRs (they belong in the runbook); an ADR records the
decision and its rationale.
