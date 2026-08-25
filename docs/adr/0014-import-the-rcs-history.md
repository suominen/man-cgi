---
status: accepted
date: 2026-08-25
---

# 0014: Import the RCS history of man-cgi as one linear git history

## Context and Problem Statement

Until this decision the live script was RCS-tracked in `../sh/`,
outside git, while the tests, documentation and ADRs lived here.
Every change was therefore two changesets in two systems that only
the commit messages tied together (ADR-0010 kept that arrangement
deliberately). The script had 113 RCS revisions going back to
2013-03-31; the repository had 32 commits, all from August 2026,
and 23 of the RCS revisions fall inside that August. Bringing the
script into the repository as `src/man-cgi` raised the question of
what to do with its history.

## Considered Options

- Replay both histories into one linear branch ordered by
  timestamp (chosen)
- Convert the RCS history to a separate root and merge the two
  roots
- Add the script as a snapshot and keep the `,v` file as the
  archive of its past

## Decision Outcome

Chosen option: one linear history, ordered by timestamp.

The two histories never touched the same path, so a merge-sort by
commit time is exactly what would have existed had the script been
in git all along: `git log` reads as one chronology, and the pairs
that belonged together — a test commit, the RCS revision that made
it pass, the smoke check after it — sit next to each other in the
order they happened. A second root with a merge would keep every
`git log -- src/man-cgi` correct but put the interleaving behind a
merge commit; a snapshot would lose `git blame` and `git log` for
the thirteen years that matter most for the script.

The import was done with `tools/rcs-import/rcs-import`, which is
kept in the repository together with the RCS file itself
(`tools/rcs-import/man-cgi,v`) and the replacement messages, so the
result can be reproduced and audited from the repository alone.
The script's header describes the mechanics. The decisions it
encodes:

- **RCS 1.1 is the root commit.** The repository's original empty
  root commit (`041e92d`) existed only to give worktrees a common
  ancestor; 1.1 provides that now, and a 2026 empty commit ahead of
  a 2013 revision would have been a fiction.
- **Git commits are replayed byte for byte** — author, committer,
  both dates, message — differing from their originals only by the
  `src/man-cgi` blob added to every tree. Where a commit had been
  amended, its committer date still differs from its author date;
  ordering is by author date, which is what `git log` shows.
- **Author and committer of every RCS revision** are
  `Kimmo Suominen <kimmo@suominen.com>`, the same identity the git
  commits already use; RCS only records the login `kim`. The
  committer date equals the author date, as RCS has one date.
- **RCS dates are stored in UTC**; each is rendered with the
  Europe/Helsinki offset in effect at that instant (+0200 in
  winter, +0300 in summer), matching the offsets on the git commits.
- **Twenty-four revisions have replacement messages**
  (`tools/rcs-import/msgs/`). Seventeen were a list of changes with
  no subject line — 1.2, 1.3, 1.5, 1.8–1.17, 1.30, 1.39, 1.40 and
  1.113 — and now have a subject line summarizing the revision with
  the original lines kept below it as the body; the rest are
  one-line subjects that were capitalized or lost a trailing
  period. Nothing was added that the original did not say; the
  original text of every revision remains in the `,v` file.
- The old history is kept reachable under the tag
  `pre-rcs-import` (tip `3468b5d`), so a rerun of the import, and
  `tools/rcs-import/rcs-import-verify`, can compare against it.

### Consequences

- Good, because one `git log` holds the whole story of the service,
  and the script is reviewed, branched and merged like everything
  else (see `docs/deployment.md`).
- Good, because `git blame src/man-cgi` reaches back to 2013.
- Bad, because every git SHA from before the import changed. None
  had been cited in docs, ADRs or tickets, and the repository had
  no remote, so nothing outside the repository refers to them.
- Bad, because the repository no longer follows the empty-root
  convention of the global workflow. The convention exists for the
  first `git worktree add` on an unborn branch, which this
  repository is long past.
- Neutral: the RCS `co -l` / `ci -u` workflow in `docs/deployment.md`
  is replaced by the branch workflow. `MINLASTMOD` and
  `MANCGI_DATE` bumps (ADR-0011) are unchanged; they are just git
  commits now.

## More Information

- ADR-0010 kept the script in RCS when it decided against a
  rewrite; this record changes only where the script is tracked,
  not what it is.
- `tools/rcs-import/rcs-import -h` and `rcs-import-verify -h`
  document the inputs; the import was run with `-x -z
  Europe/Helsinki -m tools/rcs-import/msgs` against
  `pre-rcs-import`.
