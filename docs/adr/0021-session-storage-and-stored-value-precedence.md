---
status: accepted
date: 2026-09-01
---

# 0021: Session-scoped storage, remembered value over the URL's

## Context and Problem Statement

ADR-0008's query form remembers the submitted arch and collection
in localStorage and preselects with the URL-carried value
(`data-url`) ahead of the remembered one. That order lets URLs
overwrite the user's choice: `/i386/est.4` 301s to `/x86/est.4`
(ADR-0009), the form comes back preselected `x86`, and the next
submit stores `x86` over the user's `i386`. The preference is also
kept forever, although it exists only to keep the selects sticky
while browsing the canonical, arch-less URLs.

## Considered Options

- sessionStorage by default, localStorage behind an opt-in
  checkbox; remembered value preferred over the URL's (chosen)
- Session-only memory with no way to opt into persistence
- Keep localStorage and the URL-first precedence (status quo)
- Remembered-value-first precedence, still in localStorage

## Decision Outcome

The choices move to sessionStorage (same `man-cgi.arch` /
`man-cgi.coll` keys, still saved on submit), and the preselection
precedence becomes: remembered value, URL-carried value
(`data-url`), default. Both selects are treated alike — the
helpers are shared, and a split behavior would be more code for a
less predictable form.

The remembered value winning means the machine-class
canonicalization can no longer overwrite it: the `x86` the URL
carries loses to the remembered `i386`, and the next submit stores
`i386` again. What is remembered is only ever something the user
deliberately submitted.

Session scope matches what the memory is for: arch/coll stickiness
while browsing canonical URLs (ADR-0009, ADR-0017) within a
reading session. It also keeps the storage inside the consent
exemption of the EU cookie rules: Article 5(3) of the ePrivacy
Directive (2002/58/EC as amended by 2009/136/EC) — implemented in
Finland as § 205 of the Act on Electronic Communications Services
(917/2014, supervised by Traficom) — covers Web Storage as well as
cookies (EDPB Guidelines 2/2023) and exempts storage necessary for
a service the user has explicitly requested. WP29 Opinion 04/2012
places session-scoped, deliberately triggered UI customization
(the user picks an option and submits) in that exempt category,
while flagging persistent preference storage as needing consent.

A "Remember arch and collection across visits" checkbox on its
own form row opts into localStorage instead: the same keys plus a
`man-cgi.remember` flag, all covered by the tick, which is the
GDPR-standard affirmative act ePrivacy consent requires (CJEU
*Planet49*, C-673/17, bars pre-ticked boxes — the cached markup is
unticked, and only the script ticks it back for an opted-in
visitor). The row ships hidden and the input has no name, so
without JavaScript no dead control appears and nothing is ever
submitted to the server. Ticking moves the current session's
memory to localStorage; unticking withdraws it — every man-cgi
key leaves localStorage and the values fall back to the session —
making withdrawal as easy as consent.

The pre-ADR-0021 localStorage keys are removed on page load for
visitors not opted in; the cleanup (and the test asserting it) is
scheduled for removal after 2027-09-01 (TODO.md).

### Consequences

- Good, because the user's arch/coll choice survives the
  machine-class 301s and the cross-reference links that carry a
  class in the URL — the TODO.md defect this fixes.
- Good, because session-scoped, submit-triggered, never-transmitted
  preference storage sits squarely in the ePrivacy / 917/2014
  "necessary for an explicitly requested service" exemption; no
  consent banner enters the picture.
- Good, because tabs opened from a page inherit a copy of the
  session storage, so in-session browsing keeps the choice across
  tabs.
- Good, because cross-visit stickiness stays available through the
  checkbox, with the tick itself the valid consent — still no
  banner.
- Bad, because with storage disabled the revealed checkbox cannot
  hold: the box snaps straight back to unticked.
- Bad, because the preference no longer survives the browser
  session: a returning visitor starts over as a first-time one
  (URL arch, then default). ADR-0009's and ADR-0017's "the form
  remembers" reliance thus holds within a session only.
- Bad, because a followed link's arch or collection no longer
  preselects when a value is remembered — a user deliberately
  opening a `vax` or `NetBSD-10.1` page sees their remembered
  choice in the form until they change it.
- Bad, because a remembered value missing from a freshly fetched
  list matches no option, so the rebuilt select shows the list's
  first entry even where the URL-carried value would have matched
  — rare (a list change mid-session) and session-limited.

## More Information

Amends ADR-0008 (which chose localStorage and the URL-first
order), and — for the storage's name and scope — ADR-0009 and
ADR-0017: this record's wording supersedes their `localStorage`
mentions, and their "the form remembers" reliance now holds
within a session only. Their texts stay as written.
