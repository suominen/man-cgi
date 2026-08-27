---
status: accepted
date: 2026-08-27
---

# 0018: Autofocus on the home page only; / focuses the command field

## Context and Problem Statement

The query form is on every page, and its command field carried
`autofocus` everywhere. On a man page, a multi-match menu or a 404
that put the caret in the field on load, so Space, PgDn and the
arrow keys went to the input instead of scrolling the page until
the reader tabbed or clicked out, and a screen reader landed in
the field instead of the content. On the home page and a
collection index (ADR-0017) the form is the page, and autofocus is
right. How does a reader of a man page reach the field from the
keyboard once autofocus is gone?

## Considered Options

- Autofocus on the home page only; the inline script makes `/`
  focus the field (chosen)
- Keep autofocus everywhere (status quo)
- Autofocus on the home page only, no shortcut
- An `accesskey` on the field

## Decision Outcome

Chosen option: `autofocus` is emitted only when the page class is
home, and the inline script of ADR-0008 makes `/` focus the
command field and select its text, so typing replaces the page's
own name. The convention is GitHub's and MDN's.

The details:

- The handler listens on `keydown` and matches `e.key === '/'`, a
  key name rather than a key code, and does not exclude Shift: `/`
  is Shift-7 on Finnish and Swedish layouts, and `e.key` is still
  `/`. Ctrl-, Cmd- and Alt-`/` stay the browser's.
- Only controls that take text keep `/` for themselves. From the
  selects and the Show button, where tabbing through the form
  ends, it still reaches the shortcut.
- Escape is the way back out: focus returns to the page, and the
  scroll keys work again.
- Focus is taken without scrolling: below 800px the form is not
  sticky, and focusing it would scroll a deep-read page to the
  top.
- The default action is cancelled only when focus actually moved.
  With the form hidden — a user stylesheet, a content blocker — `/`
  stays the browser's.
- A held `/` auto-repeats into the now-focused field; its repeats
  are swallowed until the key is released, seen by physical key,
  since the keyup after Shift-7 reports `7` once Shift is up.
- The "Press / to focus" tooltip is the script's to add, only
  where it runs and the field is not autofocused: a no-JS client
  never sees a promise the page cannot keep, and a screen reader
  on the home page is not told to press `/` for a field it is in.

The shortcut overrides Firefox's Quick Find, which `/` opens by
default, on the very pages where in-page search matters most. Two
things make that acceptable: Ctrl-F and `'` (Quick Find in links
only) still work, and the readers who reach for `/` on a
documentation site have been trained by GitHub and MDN to expect a
search field.

### Consequences

- Good, because a man page opens with the reader's keys on the
  page, and a screen reader on the content.
- Good, because the field is one keystroke away on every page, on
  every layout, without a mouse.
- Bad, because Quick Find on `/` is gone from man pages for Firefox
  readers who use it; Ctrl-F remains.
- Bad, because the behaviour lives in JavaScript the shell suite
  can only grep. `tests/run-browser` (`make test-browser`) drives
  the script in headless Chromium for what the greps cannot see;
  it is a local run, not part of `make test` on the NetBSD host.
- Neutral: without JavaScript there is no shortcut and no tooltip
  claiming one, and the form works by mouse and Tab as before.

## Pros and Cons of the Options

### Autofocus on the home page only; `/` focuses the field

- Good, because each page class gets the focus that fits it, and
  the shortcut is a convention readers already know.
- Bad, because the handler has edge cases (above), each of which
  had to be found and pinned.

### Keep autofocus everywhere

- Good, because it is the status quo and needs no script.
- Bad, because it breaks scrolling from the keyboard on every man
  page, for every reader, until they click or tab out.

### Autofocus on the home page only, no shortcut

- Good, because it fixes the scrolling with a one-line change and
  no JavaScript.
- Bad, because on a man page the field is then a Tab sequence or
  a mouse click away; the shortcut is what keeps the form usable
  from the keyboard.

### An `accesskey` on the field

- Good, because it is declarative markup and needs no script.
- Bad, because its modifier differs by browser and platform
  (Alt, Alt-Shift, Ctrl-Alt, Ctrl-Option), so it cannot be
  documented in one tooltip, and it is not the convention readers
  arrive with.

## More Information

Amends ADR-0008, whose inline script now also carries the
shortcut; its selects and list endpoints are unchanged. The
autofocus decision is keyed on the page class, so a rejected or
empty name on a 404 follows the class, not the empty value
(`tests/t/sanitizers`). The markup change moved `MINLASTMOD`
(ADR-0011).
