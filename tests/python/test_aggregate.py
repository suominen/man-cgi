import json
import os
import unittest

from manno_logreport.aggregate import (
    Aggregator, BoundedCounter, day_key, hour_key, top_list)
from manno_logreport.cdn import DEFAULT_RANGES, CidrSet
from manno_logreport.logparse import Malformed, parse_access_line, read_access, read_error

FIXTURES = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'logs')


def fixture_tree(**kw):
    cdn, _ = CidrSet.load(DEFAULT_RANGES)
    agg = Aggregator(cdn, **kw)
    for rec in read_access(os.path.join(FIXTURES, 'access.log')):
        if isinstance(rec, Malformed):
            agg.add_malformed(rec)
        elif rec.vhost == 'man.netbsd.org':
            agg.add_access(rec)
    return agg.result()


class Keys(unittest.TestCase):
    def test_day_and_hour_keep_log_zone(self):
        r = parse_access_line(
            'man.netbsd.org:443 1.2.3.4 - - [27/Aug/2026:23:59:59 +0300] '
            '"GET / HTTP/1.1" 200 1 "-" "x"')
        self.assertEqual(day_key(r.when), '2026-08-27')
        self.assertEqual(hour_key(r.when), '23')

    def test_top_list_order(self):
        from collections import Counter
        c = Counter({'b': 2, 'a': 2, 'c': 5, 'd': 1})
        self.assertEqual(top_list(c, 3), [['c', 5], ['a', 2], ['b', 2]])


class FixtureTotals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = fixture_tree()

    def test_window(self):
        self.assertEqual(self.t['window']['days'], ['2026-08-27', '2026-08-28'])
        self.assertEqual(self.t['window']['first'], '2026-08-27T23:59:59+03:00')
        self.assertEqual(self.t['window']['last'], '2026-08-28T05:00:02+03:00')

    def test_partial_days(self):
        # 27 Aug has one record at 23:59:59 (0.0 h of coverage) and 28 Aug
        # runs 00:00:01..05:00:02 (5.0 h): both are partial, no day is full.
        w = self.t['window']
        self.assertEqual(w['partial'], {'2026-08-27': 0.0, '2026-08-28': 5.0})
        self.assertEqual(w['full_days'], [])

    def test_totals(self):
        tot = self.t['totals']
        self.assertEqual(tot['requests'], 22)
        self.assertEqual(tot['bytes'], 69059)
        self.assertEqual(tot['malformed'], 1)
        self.assertEqual(tot['extended'], 2)
        self.assertEqual(tot['probes'], 4)
        self.assertEqual(tot['bots'], 10)

    def test_status(self):
        self.assertEqual(self.t['status'], {
            '200': 9, '304': 1, '301': 3, '404': 3, '429': 1, '499': 1,
            '502': 1, '503': 1, '501': 2})
        self.assertEqual(self.t['classes'], {
            '2xx': 9, '3xx': 4, '4xx': 3, '429': 1, '499': 1, '5xx': 4})

    def test_by_day(self):
        d = self.t['by_day']
        self.assertEqual(d['2026-08-27']['requests'], 1)
        self.assertEqual(d['2026-08-28']['requests'], 21)
        self.assertEqual(d['2026-08-28']['classes']['5xx'], 4)
        self.assertEqual(d['2026-08-28']['status']['502'], 1)
        self.assertEqual(d['2026-08-28']['routes']['other'], 3)
        self.assertEqual(d['2026-08-28']['cache'], {'HIT': 1, 'MISS': 1})

    def test_routes(self):
        r = self.t['routes']
        self.assertEqual({k: v['requests'] for k, v in r.items()}, {
            'pathinfo': 13, 'static': 1, 'cgi-query': 1, 'cgi-pathinfo': 1,
            'legacy-man': 1, 'legacy-html': 1, 'health': 1, 'other': 3})
        self.assertEqual(r['other']['status'], {'501': 1, '404': 2})
        self.assertEqual(r['pathinfo']['cache'], {'HIT': 1, 'MISS': 1})
        self.assertEqual(r['pathinfo']['rt']['n'], 2)
        self.assertAlmostEqual(r['pathinfo']['rt']['p50'], 0.002)
        self.assertAlmostEqual(r['pathinfo']['rt']['p99'], 0.250)
        self.assertIsNone(r['static']['rt'])
        # Both extended lines carry rt=; only one carries a numeric urt=
        # (the other logs '-', an nginx-served response with no upstream).
        self.assertEqual(r['pathinfo']['urt']['n'], 1)
        self.assertAlmostEqual(r['pathinfo']['urt']['p50'], 0.248)
        self.assertIsNone(r['static']['urt'])

    def test_hours(self):
        self.assertEqual(self.t['by_hour']['01'], 4)
        self.assertEqual(self.t['by_hour']['23'], 1)
        # busiest[0] is a tie-break assertion: '01' is not the unique
        # busiest (day, hour) bucket, only the first by the sort key.
        self.assertEqual(self.t['busiest'][0], ['2026-08-28', '01', 4])

    def test_bots(self):
        b = self.t['bots']
        self.assertEqual(b['Sogou']['requests'], 2)
        self.assertEqual(b['Sogou']['robots'], 1)
        self.assertEqual(b['generic-bot']['requests'], 2)
        self.assertEqual(b['empty-ua']['requests'], 2)
        self.assertEqual(b['browser-like']['requests'], 12)
        self.assertEqual(b['TerraCotta']['status'], {'502': 1})

    def test_browser_signals(self):
        br = self.t['browser']
        self.assertEqual(br['requests'], 12)
        self.assertEqual(br['no_referer'], 8)
        self.assertEqual(br['referer_hosts'][0], ['-', 8])
        fams = dict(br['ua_families'])
        self.assertEqual(fams['Chrome 145'], 5)
        self.assertEqual(fams['Firefox 128'], 2)

    def test_clients(self):
        c = self.t['clients']
        self.assertEqual(c['non_cdn_requests'], 2)
        self.assertEqual(c['cdn_requests'], 20)
        top = {e['ip']: e for e in c['top']}
        self.assertEqual(top['203.0.113.7']['requests'], 2)
        self.assertEqual(top['203.0.113.7']['breadth'], 2)
        self.assertFalse(top['203.0.113.7']['cdn'])
        self.assertTrue(top['167.82.236.21']['cdn'])
        self.assertEqual(top['167.82.236.21']['breadth'], 1)
        self.assertEqual(c['per_day_cdn']['2026-08-28']['167.82.236.22'],
                         {'requests': 2, 'breadth': 2, 'capped': False})

    def test_probes(self):
        p = self.t['probes']
        self.assertEqual(p['requests'], 4)
        self.assertEqual(p['families'], {'php': 2, 'dotfile': 1, 'other-probe': 1})
        self.assertEqual(p['status'], {'501': 2, '404': 2})
        self.assertEqual(p['methods'], {'GET': 3, 'POST': 1})
        self.assertEqual(p['ok'], [])
        self.assertIn(['/wp-login.php', 1], p['paths'])
        # Every probe UA occurs once, so top_list falls back to its
        # ascending-key tie-break; '-' (from the wp_filemanager.php hit)
        # sorts first.
        self.assertEqual(p['uas'][0], ['-', 1])

    def test_content(self):
        c = self.t['content']
        self.assertEqual(c['top200'][0], ['/', 1])
        self.assertIn(['/NetBSD-10.1/i386/ls.1', 1], c['top200'])
        self.assertIn(['NetBSD-10.1', 3], c['collections200'])
        self.assertIn(['NetBSD-11.0', 1], c['collections404'])
        self.assertEqual(dict(c['sections'])['1'], 4)
        self.assertEqual(dict(c['arches'])['amd64'], 2)
        self.assertEqual(c['redirect_routes'], {'pathinfo': 1, 'legacy-man': 1, 'legacy-html': 1})

    def test_unclassified_and_malformed(self):
        self.assertEqual(self.t['unclassified'], [['/<script>alert(1)</script>', 1]])
        self.assertEqual(len(self.t['malformed_sample']), 1)

    def test_json_round_trip(self):
        again = json.loads(json.dumps(self.t))
        self.assertEqual(again, self.t)


class PartialDays(unittest.TestCase):
    LINE = ('man.netbsd.org:443 1.2.3.4 - - [%s +0300] '
            '"GET /ls.1 HTTP/1.1" 200 1 "-" "x"')

    def tree(self, *stamps):
        agg = Aggregator(CidrSet([]))
        for st in stamps:
            agg.add_access(parse_access_line(self.LINE % st))
        return agg.result()

    def test_first_and_last_day_only(self):
        t = self.tree('27/Aug/2026:21:00:00', '28/Aug/2026:00:00:00',
                      '28/Aug/2026:23:59:59', '29/Aug/2026:06:30:00')
        w = t['window']
        self.assertEqual(w['days'], ['2026-08-27', '2026-08-28', '2026-08-29'])
        self.assertEqual(w['partial'], {'2026-08-27': 3.0, '2026-08-29': 6.5})
        self.assertEqual(w['full_days'], ['2026-08-28'])

    def test_full_day_needs_the_whole_day(self):
        # 23.5 h or more counts as full (a copy taken a few minutes early).
        t = self.tree('28/Aug/2026:00:00:00', '28/Aug/2026:23:31:00')
        self.assertEqual(t['window']['full_days'], ['2026-08-28'])
        t = self.tree('28/Aug/2026:00:00:00', '28/Aug/2026:23:29:00')
        self.assertEqual(t['window']['partial'], {'2026-08-28': 23.5})

    def test_empty(self):
        t = Aggregator(CidrSet([])).result()
        self.assertEqual(t['window']['partial'], {})
        self.assertEqual(t['window']['full_days'], [])


class BreadthCap(unittest.TestCase):
    def _entry(self, cap, paths):
        agg = Aggregator(CidrSet([]), breadth_cap=cap)
        for path in paths:
            agg.add_access(parse_access_line(
                'man.netbsd.org:443 1.2.3.4 - - [28/Aug/2026:01:00:00 +0300] '
                f'"GET {path} HTTP/1.1" 200 1 "-" "x"'))
        return agg.result()['clients']['top'][0]

    def test_cap(self):
        # 4 distinct paths, 10 hits. Once the cap is reached the count
        # freezes at the cap and says so, so it never drifts toward the
        # request count; below the cap it is the exact distinct count.
        paths = [f'/p{i % 4}.1' for i in range(10)]
        capped = self._entry(3, paths)
        self.assertEqual(capped['breadth'], 3)
        self.assertTrue(capped['breadth_capped'])
        exact = self._entry(2000, paths)
        self.assertEqual(exact['breadth'], 4)
        self.assertFalse(exact['breadth_capped'])


class Bounded(unittest.TestCase):
    def test_new_keys_stop_at_the_limit(self):
        c = BoundedCounter(limit=2)
        c.add('a')
        c.add('b')
        c.add('c')
        self.assertEqual(dict(c), {'a': 1, 'b': 1})
        self.assertEqual(c.dropped, 1)
        # An existing key keeps counting after the limit is reached.
        c.add('a', 3)
        self.assertEqual(c['a'], 4)
        self.assertEqual(c.dropped, 1)
        c.add('d', 5)
        self.assertEqual(c.dropped, 6)
        self.assertEqual(len(c), 2)

    def test_aggregator_key_limit_is_reported(self):
        agg = Aggregator(CidrSet([]), key_limit=3)
        for i in range(5):
            agg.add_access(parse_access_line(
                'man.netbsd.org:443 1.2.3.4 - - [28/Aug/2026:01:00:00 +0300] '
                f'"GET /wp-login{i}.php HTTP/1.1" 404 1 "-" "x"'))
        p = agg.result()['probes']
        self.assertEqual(p['requests'], 5)
        self.assertEqual(len(p['paths']), 3)
        self.assertEqual(p['dropped'], 2)
        # The content counters have their own, much larger bound, so
        # the probe limit must not reach them.
        self.assertEqual(agg.result()['content']['dropped'], 0)

    def test_survives_copy_and_pickle(self):
        # Counter.__reduce__ rebuilds through self.__class__(dict), which
        # would land the dict in the 'limit' slot and lose every count.
        import copy
        import pickle
        b = BoundedCounter(limit=2)
        b.add('a', 3)
        b.add('b')
        b.add('c')
        self.assertEqual(b.dropped, 1)
        for name, clone in (('copy.copy', copy.copy(b)),
                            ('Counter.copy', b.copy()),
                            ('pickle', pickle.loads(pickle.dumps(b)))):
            with self.subTest(how=name):
                self.assertIsInstance(clone, BoundedCounter)
                self.assertEqual(dict(clone), {'a': 3, 'b': 1})
                self.assertEqual(clone.limit, 2)
                self.assertEqual(clone.dropped, 1)
                # A real copy, not a view of the original.
                clone.add('a')
                self.assertEqual(b['a'], 3)

    def test_content_has_its_own_key_limit(self):
        agg = Aggregator(CidrSet([]), key_limit=3, content_key_limit=3)
        for i in range(5):
            agg.add_access(parse_access_line(
                'man.netbsd.org:443 1.2.3.4 - - [28/Aug/2026:01:00:00 +0300] '
                f'"GET /p{i}.1 HTTP/1.1" 200 1 "-" "x"'))
        c = agg.result()['content']
        self.assertEqual(len(c['top200']), 3)
        self.assertEqual(c['dropped'], 2)

    def test_content_limit_defaults_above_the_probe_limit(self):
        from manno_logreport.aggregate import (
            DEFAULT_CONTENT_KEY_LIMIT, DEFAULT_KEY_LIMIT)
        agg = Aggregator(CidrSet([]))
        self.assertEqual(agg.top200.limit, DEFAULT_CONTENT_KEY_LIMIT)
        self.assertEqual(agg.top404.limit, DEFAULT_CONTENT_KEY_LIMIT)
        self.assertEqual(agg.probe['paths'].limit, DEFAULT_KEY_LIMIT)
        self.assertEqual(agg.unclassified.limit, DEFAULT_KEY_LIMIT)
        self.assertGreater(DEFAULT_CONTENT_KEY_LIMIT, DEFAULT_KEY_LIMIT)


class Empty(unittest.TestCase):
    def test_empty_result_is_well_formed(self):
        t = Aggregator(CidrSet([])).result()
        self.assertEqual(t['totals']['requests'], 0)
        self.assertEqual(t['window'], {'first': None, 'last': None, 'days': [], 'partial': {}, 'full_days': []})
        json.dumps(t)


class Errors(unittest.TestCase):
    def test_error_tree(self):
        agg = Aggregator(CidrSet([]))
        for rec in read_error(os.path.join(FIXTURES, 'error.log')):
            if rec.server == 'man.netbsd.org' or rec.host == 'man.netbsd.org':
                agg.add_error(rec)
        t = agg.result()
        self.assertEqual(t['totals']['error_lines'], 4)
        e = t['errors']
        self.assertEqual(e['families'], {'fcgiwrap-refused': 2, 'upstream-timeout': 1, 'limit-req': 1})
        self.assertEqual(e['by_day'], {'2026-08-28': {'fcgiwrap-refused': 2, 'upstream-timeout': 1, 'limit-req': 1}})
        self.assertEqual(e['bursts'][0], ['2026-08-28 03:00', 'fcgiwrap-refused', 2])
        self.assertTrue(e['samples']['upstream-timeout'].startswith('upstream timed out'))
        json.dumps(t)


class Reservoir(unittest.TestCase):
    def test_keeps_count_and_bounds(self):
        agg = Aggregator(CidrSet([]), sample_size=8, seed=1)
        for i in range(100):
            agg.add_access(parse_access_line(
                'man.netbsd.org:443 1.2.3.4 - - [28/Aug/2026:01:00:00 +0300] '
                f'"GET /p.1 HTTP/1.1" 200 1 "-" "x" rt={i / 100:.2f}'))
        rt = agg.result()['routes']['pathinfo']['rt']
        self.assertEqual(rt['n'], 100)
        self.assertLessEqual(len(agg.routes['pathinfo']['rt'].values), 8)
        self.assertTrue(0 <= rt['p50'] <= rt['p90'] <= rt['p99'] <= 0.99)

    def test_percentile(self):
        from manno_logreport.aggregate import _percentile
        self.assertEqual(_percentile([1, 2, 3, 4, 5], 0.5), 3)
        self.assertEqual(_percentile([1, 2, 3, 4, 5], 0.99), 5)
        self.assertIsNone(_percentile([], 0.5))
