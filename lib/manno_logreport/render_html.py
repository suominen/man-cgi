"""Static, self-contained HTML for the report tree. No JavaScript."""

import html

from . import __version__
from .classify import (
    BROWSER, ERROR_FAMILIES, GRAMMAR_BUCKETS, GRAMMAR_ORIGIN, PROBE_FAMILIES,
    REJECTION_RULES, ROUTES)

CSS = """
:root { color-scheme: light dark; --fg: #1a1a1a; --bg: #fdfdfd; --mute: #666;
        --line: #ddd; --bar: #4a78b0; --alt: #f4f6f9;
        --c-2xx: #4c9a5f; --c-3xx: #8fb8de; --c-4xx: #e0b252; --c-429: #d98f3c;
        --c-499: #a889c9; --c-5xx: #c9463d; --c-other: #999; }
@media (prefers-color-scheme: dark) {
  :root { --fg: #e6e6e6; --bg: #171717; --mute: #aaa; --line: #333;
          --bar: #7aa2d8; --alt: #202428; } }
body { font: 14px/1.45 system-ui, sans-serif; color: var(--fg); background: var(--bg);
       margin: 0 auto; max-width: 72em; padding: 1em 1.5em; }
h1 { font-size: 1.6em; } h2 { margin-top: 2em; border-bottom: 1px solid var(--line); }
h3 { margin-top: 1.5em; font-size: 1.05em; }
h4 { margin-top: 1.2em; font-size: 1em; }
nav ol { columns: 2; padding-left: 1.5em; }
table { border-collapse: collapse; margin: .5em 0 1em; }
table.eq { table-layout: fixed; width: 100%; }
table.eq th { white-space: normal; overflow-wrap: anywhere; font-size: .85em; }
table.eq th, table.eq td { padding: .2em .4em; }
th, td { text-align: left; padding: .2em .6em; border-bottom: 1px solid var(--line);
         vertical-align: top; font-variant-numeric: tabular-nums; }
th { font-weight: 600; vertical-align: baseline; }
td.n, th.n { text-align: right; white-space: nowrap; }
td.nw, th.nw { white-space: nowrap; }
tbody tr:nth-child(even) { background: var(--alt); }
.wrap { overflow-x: auto; }
code, td.code { font-family: ui-monospace, monospace; font-size: .92em;
                overflow-wrap: anywhere; }
.note { color: var(--mute); font-size: .92em; }
svg text { fill: var(--fg); font-size: 11px; }
svg .bar { fill: var(--bar); } svg .axis { stroke: var(--line); }
svg .k-2xx { fill: var(--c-2xx); } svg .k-3xx { fill: var(--c-3xx); }
svg .k-4xx { fill: var(--c-4xx); } svg .k-429 { fill: var(--c-429); }
svg .k-499 { fill: var(--c-499); } svg .k-5xx { fill: var(--c-5xx); }
svg .k-other { fill: var(--c-other); }
svg .partial { opacity: .45; }
.legend span { display: inline-block; margin-right: 1em; }
.legend i { display: inline-block; width: .9em; height: .9em; margin-right: .3em;
            vertical-align: -1px; }
footer { margin-top: 3em; border-top: 1px solid var(--line); color: var(--mute);
         font-size: .9em; }
"""


def esc(value, limit=160):
    text = str(value)
    if len(text) > limit:
        text = text[:limit] + f' …[+{len(text) - limit}]'
    return html.escape(text, quote=True)


def fmt_int(n):
    return f'{n:,}'.replace(',', ' ')


def fmt_bytes(n):
    for unit, size in (('GB', 1e9), ('MB', 1e6), ('kB', 1e3)):
        if n >= size:
            return f'{n / size:.2f} {unit}'
    return f'{n} B'


def pct(part, whole):
    if not whole:
        return '–'
    return f'{100.0 * part / whole:.1f}%'


def breadth_cell(count, capped):
    """A distinct-path count, or a floor when the per-day cap was hit."""
    return f'\u2265 {fmt_int(count)}' if capped else count


def _cell(value, numeric, code=False, nowrap=False):
    if numeric:
        text = fmt_int(value) if isinstance(value, int) else esc(value)
        return f'<td class="n">{text}</td>'
    cls = 'code' if code else 'nw' if nowrap else ''
    attr = f' class="{cls}"' if cls else ''
    return f'<td{attr}>{esc(value)}</td>'


def _head(text, numeric, nowrap, span=''):
    cls = 'n' if numeric else 'nw' if nowrap else ''
    attr = f' class="{cls}"' if cls else ''
    return f'<th{attr}{span}>{esc(text)}</th>'


def _grouped_head(headers, numeric, nowrap):
    """Two heading rows: runs of two or more consecutive headings that
    share the part before their first hyphen (cgi-query, cgi-pathinfo)
    become one spanned cell over the remainders; every other heading
    spans both rows, its hyphens shown as spaces. Returns the rows as
    HTML, or None when no run exists (then one plain row will do)."""
    parts = [str(h).partition('-') for h in headers]
    runs = []
    i = 0
    while i < len(parts):
        prefix, dash, _ = parts[i]
        j = i + 1
        while dash and j < len(parts) and parts[j][1] and parts[j][0] == prefix:
            j += 1
        runs.append((i, j))
        i = j
    if all(j - i == 1 for i, j in runs):
        return None
    top, bottom = [], []
    for i, j in runs:
        if j - i == 1:
            top.append(_head(str(headers[i]).replace('-', ' '), i in numeric,
                             i in nowrap, ' rowspan="2"'))
        else:
            top.append(_head(parts[i][0], i in numeric, i in nowrap,
                             f' colspan="{j - i}"'))
            bottom.extend(_head(parts[k][2].replace('-', ' '), k in numeric,
                                k in nowrap) for k in range(i, j))
    return f'<tr>{"".join(top)}</tr><tr>{"".join(bottom)}</tr>'


def table(headers, rows, numeric=(), code=(), nowrap=(), equal=False,
          group=False):
    """rows: list of lists. numeric/code/nowrap: column indexes.

    equal=True lays the columns out at equal width (the first one, if
    it is in nowrap, gets a fixed width instead) so wide headings wrap
    rather than stretch the table. group=True shows hyphenated
    headings as words and folds runs with a common prefix into a
    spanned top heading row (see _grouped_head).
    """
    if not rows:
        return '<p class="note">none</p>'
    head = _grouped_head(headers, numeric, nowrap) if group else None
    if head is None:
        shown = [str(h).replace('-', ' ') if group else h for h in headers]
        head = '<tr>' + ''.join(_head(h, i in numeric, i in nowrap)
                                for i, h in enumerate(shown)) + '</tr>'
    body = []
    for row in rows:
        body.append('<tr>' + ''.join(
            _cell(v, i in numeric, i in code, i in nowrap)
            for i, v in enumerate(row)) + '</tr>')
    attr, cols = '', ''
    if equal:
        rest = len(headers) - 1
        # No column narrower than its longest heading word: the table
        # grows past the page and scrolls in .wrap rather than breaking
        # words in the middle. This is a floor, not the layout: the
        # table is 100% wide whenever the page allows. Headings are set
        # at .85em, lowercase text averages ~.8 of a "0" (ch), and eq
        # cells carry .4em of padding per side, hence the factors.
        words = (w for h in headers[1:]
                 for w in str(h).replace('-', ' ').split())
        longest = max((len(w) for w in words), default=1)
        # The first column is sized by its longest value (a date, or a
        # date plus "(21.4 h)"): digits are exactly 1ch wide and the
        # letters narrower, so N ch plus the padding always fits.
        first_len = max((len(str(r[0])) for r in rows), default=1)
        first_w = f'calc({first_len}ch + .8em)'
        attr = (f' class="eq" style="min-width: calc({first_w} + {rest} * '
                f'({longest} * .8ch + .8em))"')
        first = (f'<col class="first" style="width: {first_w}">'
                 if 0 in nowrap else '<col>')
        cols = f'<colgroup>{first}<col span="{rest}"></colgroup>'
    return (f'<div class="wrap"><table{attr}>{cols}<thead>{head}</thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def bars(series, width=520, label_width=200):
    """Horizontal bars, one row per (label, value)."""
    if not series:
        return '<p class="note">none</p>'
    row_h, gap = 16, 4
    height = len(series) * (row_h + gap)
    top = max(v for _, v in series) or 1
    plot = width - label_width - 60
    out = [f'<svg width="{width}" height="{height}" role="img" '
           f'viewBox="0 0 {width} {height}">']
    for i, (label, value) in enumerate(series):
        y = i * (row_h + gap)
        w = max(1, int(plot * value / top))
        out.append(
            f'<g><title>{esc(label)}: {fmt_int(value)}</title>'
            f'<text x="{label_width - 6}" y="{y + 12}" text-anchor="end">'
            f'{esc(label, 32)}</text>'
            f'<rect class="bar" x="{label_width}" y="{y + 2}" width="{w}" '
            f'height="{row_h - 4}"/>'
            f'<text x="{label_width + w + 4}" y="{y + 12}">{fmt_int(value)}</text></g>')
    out.append('</svg>')
    return ''.join(out)


def _day_label(tree, day):
    """'2026-08-14 (3.0 h)' for a partial edge day, else the day."""
    hours = tree['window'].get('partial', {}).get(day)
    return day if hours is None else f'{day} ({hours:.1f} h)'


def stacked(days, keys, values, width=760, height=180, partial=()):
    """One stacked column per day; keys stack bottom-up in the given order."""
    left, bottom = 50, 34
    plot_w = width - left - 10
    plot_h = height - bottom - 8
    tops = [sum(values.get(d, {}).get(k, 0) for k in keys) for d in days]
    top = max(tops) if tops else 0
    top = top or 1
    n = max(len(days), 1)
    slot = plot_w / n
    col_w = max(2, slot * 0.7)
    out = [f'<svg width="{width}" height="{height}" role="img" '
           f'viewBox="0 0 {width} {height}">',
           f'<line class="axis" x1="{left}" y1="{height - bottom}" '
           f'x2="{width - 10}" y2="{height - bottom}"/>',
           f'<text x="{left - 4}" y="12" text-anchor="end">{fmt_int(top)}</text>',
           f'<text x="{left - 4}" y="{height - bottom}" text-anchor="end">0</text>']
    step = max(1, n // 14)
    for i, day in enumerate(days):
        x = left + i * slot + (slot - col_w) / 2
        y = height - bottom
        for key in keys:
            v = values.get(day, {}).get(key, 0)
            if not v:
                continue
            h = plot_h * v / top
            y -= h
            out.append(
                f'<rect class="k-{esc(key)}{" partial" if day in partial else ""}" '
                f'x="{x:.1f}" y="{y:.1f}" '
                f'width="{col_w:.1f}" height="{h:.1f}">'
                f'<title>{esc(day)} {esc(key)}: {fmt_int(v)}</title></rect>')
        if i % step == 0:
            out.append(f'<text x="{x + col_w / 2:.1f}" y="{height - bottom + 14}" '
                       f'text-anchor="middle">{esc(day[5:])}</text>')
    out.append('</svg>')
    legend = ''.join(
        f'<span><i class="k-{esc(k)}" style="background: var(--c-{esc(k)})"></i>{esc(k)}</span>'
        for k in keys)
    return ''.join(out) + f'<div class="legend">{legend}</div>'


def page(title, sections, footer_html):
    toc = ''.join(f'<li><a href="#{esc(i)}">{esc(t)}</a></li>' for i, t, _ in sections)
    body = ''.join(f'<section><h2 id="{esc(i)}">{esc(t)}</h2>{h}</section>'
                   for i, t, h in sections)
    return (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{esc(title)}</title><style>{CSS}</style></head>'
            f'<body><h1>{esc(title)}</h1><nav><ol>{toc}</ol></nav>{body}'
            f'<footer>{footer_html}</footer></body></html>\n')


CLASSES = ('2xx', '3xx', '4xx', '429', '499', '5xx', 'other')
SECTION_IDS = ('summary', 'status', 'traffic', 'routes', 'bots', 'browser',
               'probes', 'reach', 'clients', 'content', 'backend',
               'unclassified')

STATUS_NOTES = {
    '301': 'canonicalization and legacy-URL redirects (ADR-0005, ADR-0015)',
    '304': 'conditional revalidation hit (ADR-0003)',
    '400': 'the $qs_error map (ADR-0020); without a query string, a request nginx could not parse',
    '404': 'a page the CGI did not find, or the nginx probe and grammar maps (ADR-0020); cache= tells them apart (Backend reach)',
    '405': 'the method map (ADR-0020): GET, HEAD, and POST only to / and /cgi-bin/man-cgi',
    '429': 'nginx limit_req (per-address zone keyed on the Fastly POP address before 2026-09-03, on the end client since)',
    '499': 'client closed the connection before the response',
    '501': 'before ADR-0020: the per-path nginx rule for probe paths (*.php, *.cgi, wp-includes, ...)',
    '503': 'upstream unavailable; with a query string before ADR-0020, the $qs_error map',
    '502': 'fcgiwrap unreachable or crashed',
}

REJECTION_NOTES = {
    'probe-map': '404 from $probe_path (a named probe family)',
    'grammar-map': '404 from the grammar map (a character the CGI would strip)',
    'qs': '400 from $qs_error or $man_bad_query (503 before ADR-0020)',
    'method': '405 from the method map',
    'cgi-bin': '404 from the outer /cgi-bin/ location (no CGI there)',
    'limit-req': '429 from limit_req',
    'legacy-501': '501 from the per-path rules ADR-0020 replaced',
    'other': 'an error status with no rule to credit',
}


def _status_rows(status, total):
    rows = []
    for code, n in sorted(status.items(), key=lambda kv: -kv[1]):
        rows.append([code, n, pct(n, total), STATUS_NOTES.get(code, '')])
    return rows


def _status_mix(status):
    """'200 ×9, 404 ×3' for a per-route/per-bot status dict."""
    return ', '.join(f'{c} ×{fmt_int(n)}'
                     for c, n in sorted(status.items(), key=lambda kv: -kv[1])[:6])


def section_status(tree, meta):
    t = tree['totals']['requests']
    out = ['<h3>By code</h3>',
           table(['Code', 'Requests', 'Share', 'Meaning here'],
                 _status_rows(tree['status'], t), numeric={1, 2})]
    out.append('<h3>By class per day</h3>')
    out.append(stacked(tree['window']['days'], list(CLASSES),
                       {d: v['classes'] for d, v in tree['by_day'].items()},
                       partial=set(tree['window']['partial'])))
    if tree['window']['partial']:
        out.append('<p class="note">Faded columns are partial days: the log '
                   'copy starts or ends inside them (nginx rotates at 21:00, '
                   'so the edge days of a copy usually are). Their hours of '
                   'coverage are shown in the per-day tables.</p>')
    return ''.join(out)


def section_traffic(tree, meta):
    days = tree['window']['days']
    by_day = tree['by_day']
    out = ['<h3>Requests per day</h3>',
           table(['Day', 'Requests', 'Bytes', 'Bots', 'Probes'],
                 [[_day_label(tree, d), by_day[d]['requests'], fmt_bytes(by_day[d]['bytes']),
                   by_day[d]['bots'], by_day[d]['probes']] for d in days],
                 numeric={1, 2, 3, 4}),
           '<h3>Requests by hour of day (whole window)</h3>',
           bars([(h, n) for h, n in tree['by_hour'].items()], label_width=60),
           '<h3>Busiest hours</h3>',
           table(['Day', 'Hour', 'Requests'],
                 [[d, h, n] for d, h, n in tree['busiest']], numeric={2})]
    return ''.join(out)


def section_routes(tree, meta):
    t = tree['totals']['requests']
    routes = tree['routes']
    ext = tree['totals']['extended']
    rows = []
    for rt in ROUTES:
        r = routes.get(rt)
        if not r:
            continue
        rows.append([rt, r['requests'], pct(r['requests'], t),
                     fmt_bytes(r['bytes']), _status_mix(r['status'])])
    out = ['<p class="note">pathinfo is the current route (nginx rewrites / to '
           '/cgi-bin/man-cgi$request_uri); cgi-query and legacy-man are the '
           'routes to migrate away from.</p>',
           table(['Route', 'Requests', 'Share', 'Bytes', 'Status mix'],
                 rows, numeric={1, 2, 3}, nowrap={0}),
           '<h3>Per day</h3>',
           table(['Day'] + list(ROUTES),
                 [[_day_label(tree, d)] + [tree['by_day'][d]['routes'].get(rt, 0) for rt in ROUTES]
                  for d in tree['window']['days']],
                 numeric=set(range(1, len(ROUTES) + 1)), nowrap={0}, equal=True,
                 group=True)]
    if ext:
        out.append(f'<h3>Cache status and request time per route '
                   f'({fmt_int(ext)} records carry the extended fields)</h3>')
        rows = []
        for rt in ROUTES:
            r = routes.get(rt)
            if not r or not (r['cache'] or r['rt'] or r.get('urt')):
                continue
            rtm = r['rt'] or {}
            urt = r.get('urt') or {}
            rows.append([rt, _status_mix(r['cache']),
                         rtm.get('n', 0),
                         *(f"{rtm[k]:.3f}" if rtm.get(k) is not None else '–'
                           for k in ('p50', 'p90', 'p99')),
                         urt.get('n', 0),
                         *(f"{urt[k]:.3f}" if urt.get(k) is not None else '–'
                           for k in ('p50', 'p90', 'p99'))])
        out.append('<p class="note">Request time is what nginx spent on the '
                   'whole request; upstream time is what it waited for '
                   'fcgiwrap, so a cache hit or an nginx-served response '
                   'has no upstream row.</p>')
        out.append(table(['Route', 'Cache status mix',
                          'Timed', 'p50 s', 'p90 s', 'p99 s',
                          'Upstream timed', 'upstream p50 s', 'upstream p90 s',
                          'upstream p99 s'],
                         rows, nowrap={0}, numeric={2, 3, 4, 5, 6, 7, 8, 9}))
    return ''.join(out)


def section_bots(tree, meta):
    t = tree['totals']['requests']
    bots = tree['bots']
    labels = sorted((l for l in bots if l != BROWSER),
                    key=lambda l: -bots[l]['requests'])
    rows = [[l, bots[l]['requests'], pct(bots[l]['requests'], t),
             fmt_bytes(bots[l]['bytes']), bots[l]['robots'],
             _status_mix(bots[l]['status'])] for l in labels]
    out = ['<p class="note">Every user agent that is not browser-like, so '
           'the two catch-alls are in here too: <code>generic-bot</code> '
           '(a bot/crawler/HTTP-library signature with no specific name) '
           'and <code>empty-ua</code> (no user agent at all). The Summary '
           'section&#8217;s bot share is the total of this table.</p>',
           table(['Bot', 'Requests', 'Share', 'Bytes', 'robots.txt', 'Status mix'],
                 rows, numeric={1, 2, 3, 4})]
    top = labels[:8]
    if top:
        out.append('<h3>Per day, top bots</h3>')
        out.append(table(['Day'] + top,
                         [[_day_label(tree, d)] + [tree['by_day'][d]['bots_by_label'].get(l, 0) for l in top]
                          for d in tree['window']['days']],
                         numeric=set(range(1, len(top) + 1)), nowrap={0},
                         equal=True, group=True))
    return ''.join(out)


def section_browser(tree, meta):
    b = tree['browser']
    c = tree['clients']
    out = [f"<p>{fmt_int(b['requests'])} requests carried a browser-like user agent; "
           f"{fmt_int(b['no_referer'])} of them ({pct(b['no_referer'], b['requests'])}) "
           'had no referer. Evidence only: a plain-browser UA with no referer and a '
           'wide spread of obscure paths is what a stealth crawler looks like, but '
           'so is a curious human with a bookmark.</p>',
           '<h3>Referer hosts</h3>',
           table(['Host', 'Requests'], b['referer_hosts'], numeric={1}),
           '<h3>User-agent families</h3>',
           table(['Family', 'Requests'], b['ua_families'], numeric={1})]
    if c['per_day_cdn']:
        out.append('<h3>Per CDN address per day: requests and distinct paths</h3>'
                   '<p class="note">Before 2026-09-03 the real client address was not '
                   'logged: each row for those days is a Fastly POP, so breadth '
                   'measures the POP, not a user.</p>')
        rows = []
        for day, ips in c['per_day_cdn'].items():
            for ip, v in sorted(ips.items(), key=lambda kv: -kv[1]['requests'])[:5]:
                rows.append([day, ip, v['requests'],
                             breadth_cell(v['breadth'], v.get('capped', False))])
        out.append(table(['Day', 'Address', 'Requests', 'Distinct paths'], rows,
                         numeric={2, 3}, code={1}))
    return ''.join(out)


def section_probes(tree, meta):
    p = tree['probes']
    t = tree['totals']['requests']
    out = [f"<p>{fmt_int(p['requests'])} requests ({pct(p['requests'], t)}) fell "
           'outside the legitimate URL space or matched a probe signature.</p>',
           '<h3>Families</h3>',
           bars(sorted(p['families'].items(), key=lambda kv: -kv[1])),
           '<h3>Status they received</h3>',
           table(['Code', 'Requests'], sorted(p['status'].items(), key=lambda kv: -kv[1]),
                 numeric={1}),
           '<h3>Probes answered with 2xx (should be empty)</h3>',
           table(['Path', 'Requests'], p['ok'], numeric={1}, code={0}),
           '<h3>Methods</h3>',
           table(['Method', 'Requests'], sorted(p['methods'].items(), key=lambda kv: -kv[1]),
                 numeric={1}),
           '<h3>Top paths</h3>',
           table(['Path', 'Requests'], p['paths'], numeric={1}, code={0}),
           '<h3>Top query strings (candidates for query-string-map.conf)</h3>',
           table(['Query', 'Requests'], p['queries'], numeric={1}, code={0}),
           '<h3>Top user agents</h3>',
           table(['User agent', 'Requests'], p['uas'], numeric={1}, code={0})]
    return ''.join(out)


def _reach_rows(keys, split):
    """[key, nginx, fastcgi, share reaching FastCGI] for the keys present."""
    rows = []
    for key in keys:
        v = split.get(key)
        if not v:
            continue
        nginx, fcgi = v.get('nginx', 0), v.get('fastcgi', 0)
        rows.append([key, nginx, fcgi, pct(fcgi, nginx + fcgi)])
    return rows


def section_reach(tree, meta):
    r = tree['reach']
    t = tree['totals']['requests']
    tot, basis = r['totals'], r['basis']
    nginx, fcgi = tot.get('nginx', 0), tot.get('fastcgi', 0)
    exact, inferred = basis.get('cache', 0), basis.get('inferred', 0)
    intro = (f'<p>{fmt_int(nginx)} requests ({pct(nginx, t)}) were answered by '
             f'nginx alone and {fmt_int(fcgi)} ({pct(fcgi, t)}) reached the '
             'FastCGI location. ')
    if not t:
        intro = '<p class="note">no requests</p>'
    elif exact:
        intro += (f'{fmt_int(exact)} records carry the extended log fields '
                  '(<code>cache=</code> and <code>urt=</code>), which settle '
                  f'that split exactly; {fmt_int(r["upstream"])} of those '
                  'contacted fcgiwrap, the rest were nginx cache hits or '
                  'nginx-level answers. ')
        if inferred:
            intro += f'The other {fmt_int(inferred)} records are inferred '
    else:
        intro += ('No record carries the extended log fields, so the whole '
                  'split is inferred ')
    if t and inferred:
        intro += ('from status and route: 429, 501, 405, 403, 400, 307, a 503 '
                  'with a query string, the static and report files, the '
                  'legacy redirects and a 301 for a page path with a query '
                  'string count as nginx, everything else as '
                  'FastCGI. That undercounts nginx once the rejection maps '
                  'are deployed on a host still logging the basic format.')
    if t:
        intro += '</p>'
    note = ('<p class="note">Measures the request rejection maps of ADR-0020 '
            '(<code>$probe_path</code> and the grammar map answering 404, '
            '<code>$qs_error</code> 400, the method map 405) and '
            '<code>limit_req</code> (429), all in the nginx configuration '
            'kept in <code>~/src/cloud</code>. The leak tables below are the '
            'candidates for extending the maps; the runbook&#8217;s '
            '&#8220;Repeating the nginx blocking analysis&#8221; is the '
            'procedure.</p>')
    days = tree['window']['days']
    by_day = tree['by_day']
    day_rows = []
    for d in days:
        v = by_day[d].get('reach', {})
        n, f = v.get('nginx', 0), v.get('fastcgi', 0)
        day_rows.append([_day_label(tree, d), n, f, pct(f, n + f),
                         by_day[d].get('leaks', 0)])
    g = r['grammar']
    grammar_rows = [[b, GRAMMAR_ORIGIN[b], g['buckets'][b],
                     r['by_grammar'].get(b, {}).get('nginx', 0),
                     r['by_grammar'].get(b, {}).get('fastcgi', 0)]
                    for b in GRAMMAR_BUCKETS if g['buckets'].get(b)]
    leak = r['leaks']
    classes = ([['probe family', k, v] for k, v in
                sorted(leak['families'].items(), key=lambda kv: -kv[1])]
               + [['grammar', k, v] for k, v in
                  sorted(leak['grammar'].items(), key=lambda kv: -kv[1])]
               + [['rule', k, v] for k, v in
                  sorted(leak['violations'].items(), key=lambda kv: -kv[1])])
    rejections = [[rule, r['rejections'][rule], REJECTION_NOTES[rule]]
                  for rule in REJECTION_RULES if r['rejections'].get(rule)]
    out = [intro, note,
           '<h3>Per day</h3>',
           table(['Day', 'nginx', 'fastcgi', 'Reached FastCGI', 'Leaks'],
                 day_rows, numeric={1, 2, 3, 4}, nowrap={0}),
           '<h3>By route</h3>',
           table(['Route', 'nginx', 'fastcgi', 'Reached FastCGI'],
                 _reach_rows(ROUTES, r['by_route']), numeric={1, 2, 3}, nowrap={0}),
           '<h3>By probe family</h3>',
           table(['Family', 'nginx', 'fastcgi', 'Reached FastCGI'],
                 _reach_rows(PROBE_FAMILIES, r['by_family']), numeric={1, 2, 3},
                 nowrap={0}),
           '<h3>URL grammar violations</h3>',
           f"<p>{fmt_int(g['requests'])} requests had a path the CGI&#8217;s "
           'grammar rejects or only redirects. Origin <code>self</code> is '
           'a link the site itself emits (the doubled arch, a tag remnant, '
           'a filesystem path or a hostname in the arch slot, a comma in '
           'the name, a backtick or a caret from the A-z range): a '
           'link-generator defect, not an attack, and not a map '
           'candidate. The character and reserved-path buckets '
           '(bad-char, markup-leak, comma-name, sed-range, api-other, '
           'asset-suffix, path-info) '
           'are what the grammar map refuses; the shape buckets are known '
           'here alone. Paths of a named probe family are judged by that '
           'family, not here.</p>',
           table(['Bucket', 'Origin', 'Requests', 'nginx', 'fastcgi'],
                 grammar_rows, numeric={2, 3, 4}),
           '<h4>Top violating paths, external</h4>',
           table(['Path', 'Requests'], g['paths'], numeric={1}, code={0}),
           '<h4>Top violating paths, self (the link generator&#8217;s)</h4>',
           table(['Path', 'Requests'], g['self_paths'], numeric={1}, code={0}),
           '<h3>Leaks: junk that reached the FastCGI location</h3>',
           f"<p>{fmt_int(leak['requests'])} requests ({pct(leak['requests'], t)}) "
           'matched a probe family, violated the grammar, used a method or '
           'a query string the site does not take, and still reached the '
           'FastCGI location. The site&#8217;s own broken-link shapes are '
           'not counted here; the grammar table above has their reach.</p>',
           '<h4>Top paths</h4>',
           table(['Path', 'Requests'], leak['paths'], numeric={1}, code={0}),
           '<h4>Top query-string keys (candidates for query-string-map.conf)</h4>',
           table(['Key', 'Requests'], leak['query_keys'], numeric={1}, code={0}),
           '<h4>Methods</h4>',
           table(['Method', 'Requests'],
                 sorted(leak['methods'].items(), key=lambda kv: -kv[1]),
                 numeric={1}),
           '<h4>By class</h4>',
           table(['Kind', 'Label', 'Requests'], classes, numeric={2}),
           '<h3>Rejections by presumed rule</h3>',
           table(['Rule', 'Requests', 'Meaning'], rejections, numeric={1})]
    return ''.join(out)


def section_clients(tree, meta, lookup=None):
    c = tree['clients']
    t = tree['totals']['requests']
    out = [f"<p>{fmt_int(c['cdn_requests'])} requests ({pct(c['cdn_requests'], t)}) "
           'came from CDN addresses, '
           f"{fmt_int(c['non_cdn_requests'])} from other addresses.</p>",
           '<p class="note">Before 2026-09-03 the man.netbsd.org vhost did not '
           'carry the <code>fastly</code> include (real client address from '
           '<code>X-Forwarded-For</code>), so records from before that date '
           'show a Fastly POP address here and push the CDN share toward '
           '100%; since then the rows are end clients and the CDN share '
           'should sit near 0%.</p>']
    rows = []
    for e in c['top']:
        row = [e['ip'], 'CDN' if e['cdn'] else '', e['requests'],
               breadth_cell(e['breadth'], e.get('breadth_capped', False)),
               e['days']]
        if lookup is not None and lookup.available and not e['cdn']:
            row += [lookup.country(e['ip']) or '', lookup.asn(e['ip']) or '']
        elif lookup is not None and lookup.available:
            row += ['', '']
        rows.append(row)
    headers = ['Address', '', 'Requests', 'Max distinct paths/day', 'Days']
    if lookup is not None and lookup.available:
        headers += ['Country', 'ASN']
    out.append(table(headers, rows, numeric={2, 3, 4}, code={0}))
    lk = meta['lookup']
    if not lk['available']:
        out.append(f"<p class=\"note\">Country/ASN columns need a lookup database: "
                   f"{esc(lk['reason'] or 'none configured')}.</p>")
    return ''.join(out)


def section_content(tree, meta):
    c = tree['content']
    out = ['<h3>Most requested pages (200)</h3>',
           table(['Path', 'Requests'], c['top200'], numeric={1}, code={0}),
           '<h3>By collection (200)</h3>', bars(c['collections200']),
           '<h3>By section (200)</h3>', bars(c['sections']),
           '<h3>By arch (200, arch-specific paths only)</h3>', bars(c['arches']),
           '<h3>404 hot spots by collection</h3>', bars(c['collections404']),
           '<h3>Most requested missing pages (404)</h3>',
           table(['Path', 'Requests'], c['top404'], numeric={1}, code={0}),
           '<h3>Redirects by route</h3>',
           table(['Route', 'Redirects'],
                 sorted(c['redirect_routes'].items(), key=lambda kv: -kv[1]),
                 numeric={1})]
    return ''.join(out)


def section_backend(tree, meta):
    days = tree['window']['days']
    by_day = tree['by_day']
    e = tree['errors']
    cols = ['429', '499', '502', '503']
    rows = []
    for d in days:
        st = by_day[d]
        row = [_day_label(tree, d)] + [st['status'].get(code, 0) for code in cols]
        row += [e['by_day'].get(d, {}).get(f, 0) for f in ERROR_FAMILIES]
        rows.append(row)
    out = ['<h3>Per day: access-log signals and error-log families</h3>',
           table(['Day'] + cols + list(ERROR_FAMILIES),
                 rows, numeric=set(range(1, 1 + len(cols) + len(ERROR_FAMILIES))),
                 nowrap={0}, equal=True, group=True)]
    if tree['totals']['error_lines']:
        out += ['<h3>Error families</h3>',
                table(['Family', 'Lines', 'Sample'],
                      [[f, n, e['samples'].get(f, '')]
                       for f, n in sorted(e['families'].items(), key=lambda kv: -kv[1])],
                      numeric={1}, code={2}),
                '<h3>Busiest ten-minute windows</h3>',
                table(['Window', 'Family', 'Lines'], e['bursts'], numeric={2})]
    else:
        out.append('<p class="note">no error log supplied (or no lines for this host).</p>')
    ext = tree['totals']['extended']
    if ext:
        out.append(f'<h3>Cache status per day ({fmt_int(ext)} records carry it)</h3>')
        keys = sorted({k for d in days for k in by_day[d]['cache']})
        out.append(table(['Day'] + keys,
                         [[_day_label(tree, d)] + [by_day[d]['cache'].get(k, 0) for k in keys] for d in days],
                         numeric=set(range(1, len(keys) + 1))))
    return ''.join(out)


def section_unclassified(tree, meta):
    return ('<p class="note">Paths on no known route and matching no probe family. '
            'A legitimate shape here means the whitelist needs a new prefix.</p>'
            + table(['Path', 'Requests'], tree['unclassified'], numeric={1}, code={0}))


def render(tree, meta, lookup=None):
    sections = [
        ('summary', 'Summary', section_summary(tree, meta)),
        ('status', 'HTTP status distribution', section_status(tree, meta)),
        ('traffic', 'Traffic over time', section_traffic(tree, meta)),
        ('routes', 'Routes', section_routes(tree, meta)),
        ('bots', 'Named bots', section_bots(tree, meta)),
        ('browser', 'Browser-like traffic signals', section_browser(tree, meta)),
        ('probes', 'Probes', section_probes(tree, meta)),
        ('reach', 'Backend reach and nginx rejections', section_reach(tree, meta)),
        ('clients', 'Clients', section_clients(tree, meta, lookup)),
        ('content', 'Content', section_content(tree, meta)),
        ('backend', 'Backend health', section_backend(tree, meta)),
        ('unclassified', 'Unclassified paths', section_unclassified(tree, meta)),
    ]
    assert tuple(i for i, _, _ in sections) == SECTION_IDS
    return page(f"{meta['host']} log report", sections, section_footer(tree, meta))


def _plural(n, noun):
    return f'{n} {noun}' if n == 1 else f'{n} {noun}s'


def _per_day_row(tree):
    """Average over full days only; partial edge days would drag it down."""
    w = tree['window']
    full = w.get('full_days', [])
    if not full:
        return ['Requests per day',
                f"no full day in the window ({len(w['days'])} partial)"]
    n = sum(tree['by_day'][d]['requests'] for d in full)
    partial = len(w['days']) - len(full)
    note = (f' (over the {_plural(len(full), "full day")};'
            f' {_plural(partial, "partial day")} left out)' if partial else '')
    return ['Requests per day', fmt_int(round(n / len(full))) + note]


def section_summary(tree, meta):
    t = tree['totals']
    w = tree['window']
    nginx = tree['reach']['totals'].get('nginx', 0)
    leaks = tree['reach']['leaks']['requests']
    rows = [
        ['Window', f"{w['first']} – {w['last']} ({len(w['days'])} days)"],
        ['Requests', fmt_int(t['requests'])],
        ['Bytes sent', fmt_bytes(t['bytes'])],
        _per_day_row(tree),
        ['Bot share', pct(t['bots'], t['requests'])],
        ['Probe share', pct(t['probes'], t['requests'])],
        ['Answered by nginx alone',
         f"{fmt_int(nginx)} ({pct(nginx, t['requests'])})"],
        ['Junk reaching the backend',
         f"{fmt_int(leaks)} ({pct(leaks, t['requests'])})"],
        ['Log format', 'extended (%s records carry cache/rt fields)' % fmt_int(t['extended'])
                       if t['extended'] else 'basic (no cache/rt fields)'],
    ]
    classes = tree['classes']
    for key in ('2xx', '3xx', '4xx', '429', '499', '5xx', 'other'):
        if key in classes:
            rows.append([f'Status {key}',
                         f"{fmt_int(classes[key])} ({pct(classes[key], t['requests'])})"])
    return table(['Item', 'Value'], rows)


def section_footer(tree, meta):
    t = tree['totals']
    inputs = ''.join(
        f"<li><code>{esc(i['path'])}</code> ({esc(i['kind'])}, "
        f"{fmt_int(i['lines'])} lines"
        + (f", {fmt_int(i.get('skipped', 0))} skipped"
           if i['kind'] == 'error' else '')
        + ')</li>'
        for i in meta['inputs'])
    cdn = meta['cdn']
    lk = meta['lookup']
    if lk['available']:
        dbs = [f"{esc(d['type'])} ({esc(d['path'])}, built {esc(d['built'])})"
               for d in (lk['geoip'], lk['asn']) if d]
        lookup = 'Lookup databases: ' + '; '.join(dbs)
        if lk['reason']:
            # One database opened and the other did not: 'available' is
            # true, so the reason would otherwise never be printed.
            lookup += f"; problems: {esc(lk['reason'])}"
    else:
        lookup = f"No lookup database: {esc(lk['reason'] or 'none configured')}"
    malformed = ''
    if t['malformed']:
        sample = ''.join(f'<li><code>{esc(l)}</code></li>' for l in tree['malformed_sample'])
        malformed = (f"<p>Malformed lines: {fmt_int(t['malformed'])}. Sample:</p>"
                     f'<ul>{sample}</ul>')
    dropped = []
    for count, what in ((tree['probes'].get('dropped', 0), 'probe path/query/UA'),
                        (tree['content'].get('dropped', 0), 'content path'),
                        (tree['reach']['grammar'].get('dropped', 0), 'grammar path'),
                        (tree['reach']['leaks'].get('dropped', 0), 'leak path/key'),
                        (tree.get('unclassified_dropped', 0), 'unclassified path')):
        if count:
            dropped.append(f'{fmt_int(count)} {what}')
    limit = ''
    if dropped:
        limit = ('<p>Distinct-key limit reached: ' + ', '.join(dropped)
                 + ' hits fell on keys first seen after their counter was '
                 'full. They are in the totals, but not in the top-N '
                 'tables above.</p>')
    return (f"<p>Host: <code>{esc(meta['host'])}</code>. Inputs:</p><ul>{inputs}</ul>"
            f"<p>CDN ranges: <code>{esc(cdn['path'])}</code>, {cdn['count']} networks, "
            f"fetched {esc(cdn['fetched'] or 'unknown')}.</p>"
            f'<p>{lookup}.</p>{malformed}{limit}'
            f"<p>Generated {esc(meta['generated'])} by manno-logreport {esc(__version__)}.</p>")
