import os
import re
import unittest

from manno_logreport.aggregate import Aggregator
from manno_logreport.cdn import DEFAULT_RANGES, CidrSet
from manno_logreport.logparse import Malformed, parse_access_line, read_access, read_error
from manno_logreport.render_html import (
    bars, esc, fmt_bytes, fmt_int, page, pct, stacked, table)
from manno_logreport.render_html import SECTION_IDS, render

FIXTURES = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'logs')


class Helpers(unittest.TestCase):
    def test_esc(self):
        self.assertEqual(esc('<script>"&\''), '&lt;script&gt;&quot;&amp;&#x27;')
        self.assertEqual(esc(12), '12')

    def test_esc_truncates(self):
        out = esc('a' * 200, limit=50)
        self.assertTrue(out.startswith('a' * 50))
        self.assertIn('…[+150]', out)

    def test_fmt(self):
        self.assertEqual(fmt_int(1234567), '1 234 567')
        self.assertEqual(fmt_int(0), '0')
        self.assertEqual(fmt_bytes(7269130000), '7.27 GB')
        self.assertEqual(fmt_bytes(512), '512 B')
        self.assertEqual(pct(1, 4), '25.0%')
        self.assertEqual(pct(0, 0), '–')


class Table(unittest.TestCase):
    def test_escapes_and_marks_numeric(self):
        html = table(['Path', 'Hits'], [['/<x>', 3]], numeric={1})
        self.assertIn('<th>Path</th>', html)
        self.assertIn('<td>/&lt;x&gt;</td>', html)
        self.assertIn('<td class="n">3</td>', html)
        self.assertNotIn('<x>', html)

    def test_empty_rows(self):
        self.assertIn('none', table(['A'], []))

    def test_equal_columns(self):
        html = table(['Day', 'a b', 'c'], [['2026-08-28', 1, 2]],
                     numeric={1, 2}, nowrap={0}, equal=True)
        self.assertIn('<table class="eq" style=', html)
        self.assertIn('<colgroup><col class="first" style="width: calc(10ch + .8em)">'
                      '<col span="2"></colgroup>', html)
        self.assertIn('<th class="nw">Day</th>', html)
        self.assertNotIn('class="eq"', table(['A'], [['x']]))

    def test_equal_table_min_width_fits_longest_heading_word(self):
        html = table(['Day', 'fcgiwrap refused', 'ok'], [['d', 1, 2]],
                     numeric={1, 2}, nowrap={0}, equal=True)
        # longest word "fcgiwrap" = 8 chars -> 9ch + cell padding per column
        self.assertIn('style="min-width: calc(calc(1ch + .8em) + 2 * (8 * .8ch + .8em))"', html)

    def test_grouped_headings(self):
        html = table(['Day', 'a-x', 'a-y', 'b', 'c-z'], [['d', 1, 2, 3, 4]],
                     numeric={1, 2, 3, 4}, nowrap={0}, equal=True, group=True)
        self.assertIn('<thead><tr><th class="nw" rowspan="2">Day</th>'
                      '<th class="n" colspan="2">a</th>'
                      '<th class="n" rowspan="2">b</th>'
                      '<th class="n" rowspan="2">c z</th></tr>'
                      '<tr><th class="n">x</th><th class="n">y</th></tr></thead>', html)

    def test_group_without_runs_is_a_single_row(self):
        html = table(['Day', 'a-x', 'b'], [['d', 1, 2]], numeric={1, 2}, group=True)
        self.assertIn('<thead><tr><th>Day</th><th class="n">a x</th>'
                      '<th class="n">b</th></tr></thead>', html)
        self.assertNotIn('rowspan', html)

    def test_equal_table_headings_may_wrap(self):
        # th.n is nowrap; the equal-width rule must override it.
        from manno_logreport.render_html import CSS
        self.assertIn('table.eq th { white-space: normal;', CSS)
        self.assertIn('th { font-weight: 600; vertical-align: baseline; }', CSS)

    def test_nowrap_columns(self):
        html = table(['Route', 'Mix'], [['pathinfo', '200 x9']], nowrap={0})
        self.assertIn('<th class="nw">Route</th>', html)
        self.assertIn('<td class="nw">pathinfo</td>', html)
        self.assertIn('<td>200 x9</td>', html)


class Charts(unittest.TestCase):
    def test_bars_scale_and_labels(self):
        svg = bars([('a', 10), ('<b>', 5)])
        self.assertTrue(svg.startswith('<svg'))
        self.assertIn('&lt;b&gt;', svg)
        self.assertIn('<title>a: 10</title>', svg)
        self.assertNotIn('<b>', svg)
        # width=520, label_width=200 (both defaults): plot = 520-200-60 = 260;
        # bar width = max(1, int(plot * value / top)) with top = 10.
        widths = [int(w) for w in re.findall(r'<rect[^>]*\bwidth="(\d+)"', svg)]
        self.assertEqual(widths, [260, 130])

    def test_bars_empty(self):
        self.assertIn('none', bars([]))

    def test_stacked(self):
        svg = stacked(['2026-08-27', '2026-08-28'], ['2xx', '5xx'],
                      {'2026-08-27': {'2xx': 1}, '2026-08-28': {'2xx': 3, '5xx': 1}})
        self.assertTrue(svg.startswith('<svg'))
        self.assertIn('<title>2026-08-28 5xx: 1</title>', svg)
        self.assertIn('class="k-5xx"', svg)

    def test_stacked_all_zero(self):
        svg = stacked(['d'], ['2xx'], {'d': {}})
        self.assertTrue(svg.startswith('<svg'))


class Page(unittest.TestCase):
    def test_skeleton(self):
        html = page('T<', [('s1', 'One<', '<p>x</p>')], '<p>f</p>')
        self.assertTrue(html.startswith('<!DOCTYPE html>'))
        self.assertIn('<title>T&lt;</title>', html)
        self.assertIn('<a href="#s1">One&lt;</a>', html)
        self.assertIn('<h2 id="s1">One&lt;</h2>', html)
        self.assertIn('prefers-color-scheme: dark', html)
        self.assertNotIn('<script', html)


def fixture_tree(with_errors=True):
    cdn, cdn_meta = CidrSet.load(DEFAULT_RANGES)
    agg = Aggregator(cdn, top=5)
    for rec in read_access(os.path.join(FIXTURES, 'access.log')):
        if isinstance(rec, Malformed):
            agg.add_malformed(rec)
        elif rec.vhost == 'man.netbsd.org':
            agg.add_access(rec)
    if with_errors:
        for rec in read_error(os.path.join(FIXTURES, 'error.log')):
            if 'man.netbsd.org' in (rec.server, rec.host):
                agg.add_error(rec)
    return agg.result(), cdn_meta


def meta_for(cdn_meta, lookup=None):
    return {'host': 'man.netbsd.org',
            'inputs': [{'path': 'access.log', 'kind': 'access', 'lines': 24}],
            'cdn': cdn_meta,
            'lookup': lookup or {'available': False, 'geoip': None, 'asn': None,
                                 'searched': [], 'reason': 'no lookup database found'},
            'generated': '2026-08-28T22:00:00+03:00', 'version': '0.1', 'top': 5}


class Render(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree, cdn_meta = fixture_tree()
        cls.html = render(tree, meta_for(cdn_meta))

    def test_all_sections_present_in_order(self):
        positions = [self.html.index(f'<h2 id="{i}"') for i in SECTION_IDS]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(SECTION_IDS, (
            'summary', 'status', 'traffic', 'routes', 'bots', 'browser',
            'probes', 'clients', 'content', 'backend', 'unclassified'))

    def test_hostile_strings_are_escaped(self):
        self.assertNotIn('<script>alert(1)</script>', self.html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', self.html)
        self.assertNotIn('<script', self.html)

    def test_numbers_land(self):
        self.assertIn('Requests</td><td>22', self.html.replace('\n', ''))
        # Data-bearing fragments, not just the bare family/route name:
        # 'fcgiwrap-refused' is also a static column header in
        # section_backend and 'cgi-query' is named in a static note in
        # section_routes, so either appears even with no matching data.
        self.assertIn('<td>fcgiwrap-refused</td><td class="n">2</td>', self.html)
        self.assertIn('Sogou', self.html)
        self.assertIn('<td class="nw">cgi-query</td><td class="n">1</td>', self.html)
        self.assertIn('wp-login.php', self.html)
        self.assertNotIn('no error log', self.html)

    def test_backend_table_has_spaced_equal_columns(self):
        backend = self.html[self.html.index('<h2 id="backend"'):
                            self.html.index('<h2 id="unclassified"')]
        self.assertIn('<table class="eq" style=', backend)
        self.assertIn('<th class="n" rowspan="2">fcgiwrap refused</th>', backend)
        self.assertIn('<th class="n" colspan="3">upstream</th>', backend)
        self.assertIn('<tr><th class="n">timeout</th><th class="n">closed</th>'
                      '<th class="n">other</th></tr>', backend)
        self.assertNotIn('fcgiwrap-refused</th>', backend)

    def test_partial_days_are_labelled_and_faded(self):
        self.assertIn('<td class="nw">2026-08-28 (5.0 h)</td>', self.html)
        self.assertIn('class="k-2xx partial"', self.html)
        self.assertIn('no full day in the window', self.html)
        routes = self.html[self.html.index('<h2 id="routes"'):
                           self.html.index('<h2 id="bots"')]
        self.assertIn('2026-08-27 (0.0 h)', routes)

    def test_full_day_average_uses_full_days_only(self):
        from manno_logreport.logparse import parse_access_line
        cdn, cdn_meta = CidrSet.load(DEFAULT_RANGES)
        agg = Aggregator(cdn)
        line = ('man.netbsd.org:443 1.2.3.4 - - [%s +0300] '
                '"GET /ls.1 HTTP/1.1" 200 1 "-" "x"')
        for st in ('28/Aug/2026:00:00:00', '28/Aug/2026:12:00:00',
                   '28/Aug/2026:23:59:00', '29/Aug/2026:01:00:00'):
            agg.add_access(parse_access_line(line % st))
        html = render(agg.result(), meta_for(cdn_meta))
        self.assertIn('<td>Requests per day</td><td>3 (over the 1 full day; '
                      '1 partial day left out)</td>', html)
        self.assertIn('<td class="nw">2026-08-29 (1.0 h)</td>', html)
        self.assertNotIn('2026-08-28 (', html)

    def test_content_charts_share_one_label_column(self):
        content = self.html[self.html.index('<h2 id="content"'):
                            self.html.index('<h2 id="backend"')]
        # every bar chart in the section starts its bars at the same x
        xs = set(re.findall(r'<rect class="bar" x="(\d+)"', content))
        self.assertEqual(xs, {'200'})

    def test_per_day_tables_have_spaced_equal_columns(self):
        routes = self.html[self.html.index('<h2 id="routes"'):
                           self.html.index('<h2 id="bots"')]
        bots = self.html[self.html.index('<h2 id="bots"'):
                         self.html.index('<h2 id="browser"')]
        self.assertEqual(routes.count('<table class="eq" style='), 1)
        self.assertIn('<th class="n" colspan="2">cgi</th>', routes)
        self.assertIn('<th class="n" colspan="2">legacy</th>', routes)
        self.assertIn('<th class="n">query</th><th class="n">pathinfo</th>', routes)
        self.assertIn('<th class="n">man</th><th class="n">html</th>', routes)
        self.assertEqual(bots.count('<table class="eq" style='), 1)
        self.assertIn('<th class="n">generic bot</th>', bots)
        self.assertIn('<th class="n">Meta External Agent</th>', bots)
        self.assertNotIn('rowspan', bots)

    def test_extended_sections_state_record_count(self):
        self.assertIn('2 records', self.html)

    def test_no_lookup_is_explained(self):
        self.assertIn('no lookup database found', self.html)

    def test_clients_section_has_cdn_caveat(self):
        section = self.html[self.html.index('<h2 id="clients"'):
                             self.html.index('<h2 id="content"')]
        self.assertIn('fastly', section)

    def test_without_error_log(self):
        tree, cdn_meta = fixture_tree(with_errors=False)
        html = render(tree, meta_for(cdn_meta))
        self.assertIn('no error log', html)

    def test_empty_tree_renders(self):
        cdn, cdn_meta = CidrSet.load(DEFAULT_RANGES)
        html = render(Aggregator(cdn).result(), meta_for(cdn_meta))
        for i in SECTION_IDS:
            self.assertIn(f'<h2 id="{i}"', html)

    def test_capped_breadth_is_shown_as_a_floor(self):
        # Past the cap the distinct-path count is a floor, not a count,
        # and the report has to say so rather than print a bare number.
        cdn, cdn_meta = CidrSet.load(DEFAULT_RANGES)

        def clients_section(cap):
            agg = Aggregator(cdn, breadth_cap=cap)
            for i in range(4):
                agg.add_access(parse_access_line(
                    'man.netbsd.org:443 203.0.113.7 - - '
                    f'[28/Aug/2026:01:00:00 +0300] "GET /p{i}.1 HTTP/1.1" '
                    '200 1 "-" "x"'))
            html = render(agg.result(), meta_for(cdn_meta))
            return html[html.index('<h2 id="clients"'):
                        html.index('<h2 id="content"')]

        self.assertIn('≥ 2', clients_section(2))
        self.assertNotIn('≥', clients_section(2000))

    def test_partial_lookup_failure_is_reported(self):
        # One database opened, the other did not: 'available' is True,
        # so the reason would otherwise never be printed.
        tree, cdn_meta = fixture_tree()
        lookup = {'available': True,
                  'geoip': {'path': 'x', 'type': 'T', 'built': '2026-08-01'},
                  'asn': None, 'searched': [],
                  'reason': 'asn.mmdb: invalid database'}
        html = render(tree, meta_for(cdn_meta, lookup=lookup))
        self.assertIn('asn.mmdb: invalid database', html)
        self.assertIn('Lookup databases:', html)

    def test_hostile_ua_and_query_are_escaped(self):
        # A direct probe/query/UA escaping test that doesn't depend on
        # the shared access.log fixture.
        cdn, cdn_meta = CidrSet.load(DEFAULT_RANGES)
        agg = Aggregator(cdn)
        agg.add_access(parse_access_line(
            'man.netbsd.org:443 1.2.3.4 - - [28/Aug/2026:01:00:00 +0300] '
            '"GET /wp-login.php?<b>x</b> HTTP/1.1" 200 1 "-" "UA <i>evil</i>"'))
        html = render(agg.result(), meta_for(cdn_meta))
        self.assertNotIn('<b>x</b>', html)
        self.assertNotIn('<i>evil</i>', html)
        self.assertIn('&lt;b&gt;x&lt;/b&gt;', html)
        self.assertIn('&lt;i&gt;evil&lt;/i&gt;', html)
