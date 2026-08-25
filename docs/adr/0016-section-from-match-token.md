---
status: accepted
date: 2026-08-25
---

# 0016: Infer the section from the match token

## Context and Problem Statement

A sectionless request that resolves to exactly one page is sent
to that page's sectioned URL with a 301 (ADR-0005), so the page
caches under one key and one canonical URL. The inference read
the section from the resolved file's suffix, which is the section
for a source page (`man1/ls.1`) and `0` for a preformatted one
(`cat1/ls.0`). A page that exists only preformatted therefore
never gained a section: `/name` served it at the sectionless URL
under the key `page:<coll>:name`, a second cache object beside
`/name.N` with its `page:<coll>:name.N` key, and the sectionless
key it carried is otherwise the multi-match menu's (ADR-0012).

ADR-0012 already reads a match's section from its `manN`/`catN`
directory to reduce `man -w` output to page tokens, and left the
redirect on the suffix deliberately: a wrong 301 then lived 30
days at nginx, and no served collection ships `catN` pages.
ADR-0015 has since cut the nginx hold to a day.

## Considered Options

- Take the section from the match token (chosen)
- Keep the suffix read and special-case `.0`
- Leave preformatted-only pages at the sectionless URL

## Decision Outcome

Chosen option: the section-inference redirect reads the section
of the token `match_tokens` produces for the resolved path, so it
comes from the directory for source and preformatted pages alike.
The whitelist of sections that redirect is unchanged: it is the
set the URL parser accepts as a suffix, and a page in `mann` or
`manl` keeps serving at its sectionless URL, as before.

Nothing about which page is served changes. `man -w` order still
picks the page, ADR-0009's arch canonicalization still sets the arch
first so an arch change and a section gain fold into one hop, and
a request that names a section never enters the inference.

### Consequences

- Good, because a preformatted-only page has one URL and one
  cache key, `page:<coll>:<cmd>.<sect>`, and a purge of that key
  reaches it.
- Good, because the sectionless `page:<coll>:<cmd>` key now
  belongs to menus alone, which is what `../runbook.md` says it
  is. The one exception is a page in `mann` or `manl`, which no
  served collection has.
- Neutral: no collection served today ships `catN` pages, so no
  live URL changes. When one does, its preformatted-only pages
  redirect from the first request.
- Bad, because it adds to the class of 301s that only expire:
  nginx does not revalidate a redirect (ADR-0015). The hold is a
  day, and the redirect is derived from the same lookup that
  serves the page, so a wrong one needs a wrong `man -w` result.

## Pros and Cons of the Options

### Take the section from the match token

- Good, because one function decides what a path's section is,
  for menus and for the redirect.
- Good, because the suffix stops mattering, and `man.conf`'s
  `_suffix` list never has to be mirrored in the CGI.
- Bad, because the single-match path now runs `match_tokens` for
  one line, an `awk` process the redirect did not need before.

### Keep the suffix read and special-case `.0`

- Good, because it is a two-line change local to the inference.
- Bad, because it re-derives the section from the directory a
  second way, beside the one `match_tokens` already has.

### Leave preformatted-only pages at the sectionless URL

- Good, because it mints no new redirects.
- Bad, because the page stays cached twice, under a key the
  runbook describes as a menu's, and the gap only shows once a
  collection ships `catN` pages.

## More Information

Amends ADR-0012, whose "two things this deliberately leaves
alone" paragraph named this gap; the second thing there, the
sectionless key not matching its entries' keys, stands.

`match_tokens` also carries the match's arch, read from the
directory between the section directory and the file. The
`CANONICAL_ARCH` derivation still strips `MANROOT` and the
collection off the front instead, with the `XXX` note about the
configuration that breaks; switching it to the token is a
separate change.
