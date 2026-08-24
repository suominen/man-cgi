---
status: accepted
date: 2026-08-24
---

# 0012: Menus for multi-match lookups

## Context and Problem Statement

`man -w` resolves a name to *every* file it matches, not one. Three
things produce several matches: an arch or machine-class page
shadowing a machine-independent page of the same name and section
(`man8/x86/boot.8` and `man8/boot.8`), a name that exists in
several sections (`man1/stat.1` and `man2/stat.2`), and a
preformatted page listed beside its source (`cat1/ls.0` and
`man1/ls.1` — `man.conf`'s `_subdir` searches `catN` first). The
first two are several pages; the third is one page in two forms.
The CGI kept
only the first line and discarded the rest, so `/printf` redirected
to `/printf.1` with no sign that `printf(3)` and `printf(9)` exist,
and `/i386/apm` redirected to the machine-independent `apm(8)`,
hiding `i386/apm(4)` entirely. The alternates were reachable by
typing their URL, but nothing on the site named them.

## Considered Options

- Menu for sectionless multi-match requests, plus an
  "Also available" list on a served page whose lookup matched more
  than one file (chosen)
- Menu whenever `man -w` returns more than one path
- Keep first-match-wins and only add the "Also available" list

## Decision Outcome

Chosen option: each path `man -w` returns is first reduced to a
token identifying the *page* — `[<arch>/]<name>.<section>` — and
the tokens are deduplicated. A request that carries no section and
holds more than one distinct token renders a `<ul>` of them, each
entry labelled `<arch>/<name>(<section>)` and linking to the URL
that resolves to exactly that page. A request that does render a
page lists the other tokens above it under "Also available".

The token's section is read from the `manN`/`catN` directory, not
from the file's suffix, and its arch from the subdirectory between
that and the file. Without this a preformatted page and its source
would show up as two entries — and worse, every page that exists in
both forms would get a spurious two-entry menu naming itself twice.
Taking the section from the directory also gives the right answer
for a page that exists only preformatted, whose `.0` suffix names
no section at all. Reading the path from its tail rather than by
stripping `MANROOT` and the collection off the front keeps this
correct in the configuration the `XXX` note at the `CANONICAL_ARCH`
derivation warns about.

"Menu whenever the count exceeds one" was rejected because it does
not terminate: an arch URL searches the arch directory, its machine
class, and the machine-independent directory, so `/x86/boot.8`
matches two files just as `/i386/boot` does. Every entry in its
menu would lead back to a menu. On the arch axis only an arch-less
URL pins one file, because it sets `MACHINE=NONE`; on the section
axis only a sectioned one does. Restricting the menu to
sectionless requests keeps every entry a real destination and
leaves ADR-0009's canonical-arch redirect untouched for the URLs
that carry a section.

The menu reflects what `man -w` found for the requested `MACHINE`
and lives at the requested URL — `/i386/boot` and `/sparc/boot` are
different menus, which is correct: they describe different search
paths. Menus revalidate against the collection's `build` file, as
404s do (ADR-0003), because a menu describes what the collection
contains rather than any one file; they carry the page TTL profile
(ADR-0002) and the keys `all menu coll:<coll> page:<coll>:<cmd>`
plus `arch:<requested>` when the URL carries one, so a collection
rebuild's purge reaches them (ADR-0004).

Entries stay in `man -w` order, which is `man.conf`'s `_subdir`
search order. On the arch axis that is clearly right: the page that
shadows comes before the page it shadows. On the section axis it is
`_subdir`'s preference order rather than a numeric one, so `/intro`
lists 1, 8, 6, 2, 3, and so on. Sorting was considered and not
done, because search order makes the first entry the page the old
redirect led to — every existing link and bookmark still lands on
what it used to.

### Consequences

- Good, because pages that were only reachable by guessing a URL
  are now linked from the name that shadows them.
- Good, because the guess a sectionless URL used to make silently
  is now an explicit choice the reader makes.
- Neutral: sectionless multi-match URLs turn from 301s into 200s,
  so search engines re-crawl them once. The menu's
  `<link rel="canonical">` points at itself.
- Bad, because those URLs are cached as 301s today, and nginx does
  not revalidate redirects conditionally, so no `MINLASTMOD` bump
  reaches them — this is the one change that does not converge on
  its own. `../runbook.md` and `../deployment.md` carry what that
  costs.
- Neutral: a long menu's section order looks arbitrary, because it
  is `man.conf`'s search order rather than a numeric one.
- Bad, because `/i386/boot` and `/amd64/boot` cache as separate
  objects with identical bodies. This is bounded — only
  multi-match names, only arches actually requested — and far
  smaller than the per-arch aliasing ADR-0009 removed, but it is a
  step back in that direction.
- Bad, because a served page's "Also available" list is derived
  from the same lookup as the page, so it is validated by the
  *page's* mtime. A shadowing page added elsewhere in the tree
  changes what the list should say without changing that mtime;
  the collection rebuild's `coll:` purge is what corrects it.

## Pros and Cons of the Options

### Menu for sectionless requests, plus a list on served pages

- Good, because every menu entry resolves to a page, with no new
  URL grammar and no change to the canonical-arch contract.
- Good, because nothing is silently hidden: the two cases that used
  to discard matches — the sectionless redirect and the rendered
  page — both now name them.
- Bad, because a page reached under two different arches shows
  different lists (an arch-less URL's lookup sees only one file, so
  it shows none).

### Menu whenever `man -w` returns more than one path

- Good, because the rule is one sentence.
- Bad, because it does not terminate without inventing a URL form
  that means "this exact file", which every existing link, the
  canonical URL, and ADR-0009 would have to learn.

### First-match-wins plus the list only

- Good, because it is the smallest change and keeps every URL's
  status code.
- Bad, because the sectionless redirect still picks for the reader:
  `/i386/apm` lands on `apm(8)` and only then mentions
  `i386/apm(4)`, which is the wrong way round.

Two things this deliberately leaves alone. The section-inference
redirect still reads the file suffix, so a page that exists only
preformatted keeps serving at its sectionless URL instead of
gaining one — a gap that predates menus and that changing would
mint durable 301s (ADR-0005) for a case the production tree does
not currently contain. And the sectionless `page:` key does not
match the `page:<coll>:<cmd>.<sect>` key its entries carry, so
purging one page does not purge the menus that list it; the
collection-wide key that a rebuild already uses does.

## More Information

Relationship to ADR-0009: sectioned URLs still redirect to the arch
where `man -w` resolved the page, so the canonical URL of a page is
unchanged. The menu occupies the sectionless URL that previously
only ever redirected.

The arch of a match is read from its parent directory's own name
rather than by stripping `MANROOT` and the collection off the
front, so it is also correct in the configuration the `XXX` note at
the `CANONICAL_ARCH` derivation warns about.
