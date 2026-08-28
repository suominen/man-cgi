import json
import os
import tempfile
import unittest

from manno_logreport.cdn import DEFAULT_RANGES, CidrSet, format_cidr_list


class Membership(unittest.TestCase):
    def setUp(self):
        self.s = CidrSet(['167.82.224.0/20', '2a04:4e42::/32'])

    def test_v4(self):
        self.assertIn('167.82.236.31', self.s)
        self.assertNotIn('203.0.113.7', self.s)

    def test_v6(self):
        self.assertIn('2a04:4e42:1::5', self.s)
        self.assertNotIn('2001:db8::1', self.s)

    def test_garbage_is_not_member(self):
        self.assertNotIn('-', self.s)
        self.assertNotIn('', self.s)

    def test_ipv4_mapped_v6(self):
        # nginx logs an IPv4 client reaching an IPv6 listener as
        # ::ffff:A.B.C.D; that is the same address as A.B.C.D.
        self.assertIn('::ffff:167.82.236.31', self.s)
        self.assertNotIn('::ffff:203.0.113.7', self.s)


class Load(unittest.TestCase):
    def test_load_with_header(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'r.cidr')
            with open(p, 'w') as f:
                f.write('# source: https://example/x\n# fetched: 2026-08-28\n\n'
                        '167.82.224.0/20\n2a04:4e42::/32\n')
            s, meta = CidrSet.load(p)
        self.assertIn('167.82.236.31', s)
        self.assertEqual(meta, {'path': p, 'fetched': '2026-08-28', 'count': 2})

    def test_bad_line_names_the_line_number(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'r.cidr')
            with open(p, 'w') as f:
                f.write('# source: https://example/x\n'
                        '167.82.224.0/20\n'
                        '1.2.3.999/24\n')
            with self.assertRaises(ValueError) as cm:
                CidrSet.load(p)
        message = str(cm.exception)
        self.assertIn(':3:', message)
        self.assertIn('1.2.3.999/24', message)
        self.assertIn(p, message)

    def test_packaged_file(self):
        s, meta = CidrSet.load(DEFAULT_RANGES)
        self.assertIn('167.82.236.31', s)
        self.assertRegex(meta['fetched'], r'^\d{4}-\d\d-\d\d$')
        self.assertGreater(meta['count'], 10)


class Format(unittest.TestCase):
    def test_format(self):
        text = json.dumps({'addresses': ['23.235.32.0/20', '151.101.0.0/16'],
                           'ipv6_addresses': ['2a04:4e40::/32']})
        out = format_cidr_list(text, '2026-08-28')
        self.assertEqual(out.splitlines(), [
            '# source: https://api.fastly.com/public-ip-list',
            '# fetched: 2026-08-28',
            '23.235.32.0/20',
            '151.101.0.0/16',
            '2a04:4e40::/32',
        ])

    def test_empty_response_is_an_error(self):
        with self.assertRaises(ValueError):
            format_cidr_list('{"addresses": [], "ipv6_addresses": []}', '2026-08-28')
        with self.assertRaises(ValueError):
            format_cidr_list('not json', '2026-08-28')

    def test_empty_input_is_an_error(self):
        # curl failing mid-pipe feeds the formatter nothing at all;
        # json.loads('') is a JSONDecodeError, so say what happened.
        for text in ('', '   \n'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as cm:
                    format_cidr_list(text, '2026-08-28')
                self.assertIn('empty response', str(cm.exception))

    def test_bad_network_is_an_error(self):
        text = json.dumps({'addresses': ['1.2.3.999/24'], 'ipv6_addresses': []})
        with self.assertRaises(ValueError) as cm:
            format_cidr_list(text, '2026-08-28')
        self.assertIn('1.2.3.999/24', str(cm.exception))
