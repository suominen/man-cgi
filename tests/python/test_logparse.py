import gzip
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from manno_logreport.logparse import (Access, Malformed, open_log,
                                       parse_access_line, read_access, sniff,
                                       Error, parse_error_line, read_error)

BASIC = ('man.netbsd.org:443 167.82.236.31 - - [28/Aug/2026:21:00:23 +0300] '
         '"GET /NetBSD-8.1/sun2/py.1?x=1 HTTP/1.1" 404 3316 "-" '
         '"Mozilla/5.0 (compatible; meta-externalagent/1.1)"')

FIXTURES = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'logs')


def _read_lines(text):
    """read_access() over TEXT written to a throwaway file."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'a.log')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        return list(read_access(p))


class ParseAccessLine(unittest.TestCase):
    def test_basic_line(self):
        r = parse_access_line(BASIC)
        self.assertIsInstance(r, Access)
        self.assertEqual(r.vhost, 'man.netbsd.org')
        self.assertEqual(r.port, '443')
        self.assertEqual(r.client, '167.82.236.31')
        self.assertEqual(r.when, datetime(2026, 8, 28, 21, 0, 23,
                                          tzinfo=timezone(timedelta(hours=3))))
        self.assertEqual((r.method, r.path, r.query, r.proto),
                         ('GET', '/NetBSD-8.1/sun2/py.1', 'x=1', 'HTTP/1.1'))
        self.assertEqual((r.status, r.bytes), (404, 3316))
        self.assertEqual(r.referer, '-')
        self.assertEqual(r.ua, 'Mozilla/5.0 (compatible; meta-externalagent/1.1)')
        self.assertIsNone(r.cache)

    def test_no_query(self):
        r = parse_access_line(BASIC.replace('?x=1', ''))
        self.assertEqual(r.query, '')

    def test_default_vhost_and_dash_port(self):
        line = BASIC.replace('man.netbsd.org:443', '_:-')
        r = parse_access_line(line)
        self.assertEqual((r.vhost, r.port), ('_', '-'))

    def test_negative_offset(self):
        r = parse_access_line(BASIC.replace('+0300', '-0700'))
        self.assertEqual(r.when.utcoffset(), timedelta(hours=-7))

    def test_malformed_request_field(self):
        line = BASIC.replace('GET /NetBSD-8.1/sun2/py.1?x=1 HTTP/1.1',
                             '\\x16\\x03\\x01')
        r = parse_access_line(line)
        self.assertIsInstance(r, Malformed)
        self.assertEqual(r.line, line)
        # The vhost is still known, so the count can be per host.
        self.assertEqual(r.vhost, 'man.netbsd.org')

    def test_malformed_dash_request_keeps_vhost(self):
        line = BASIC.replace('"GET /NetBSD-8.1/sun2/py.1?x=1 HTTP/1.1" 404',
                             '"-" 400')
        r = parse_access_line(line)
        self.assertIsInstance(r, Malformed)
        self.assertEqual(r.vhost, 'man.netbsd.org')

    def test_malformed_line_that_never_matched_has_no_vhost(self):
        recs = list(_read_lines('not a log line at all\n'))
        self.assertEqual([type(r).__name__ for r in recs], ['Malformed'])
        self.assertEqual(recs[0].vhost, '')

    def test_not_a_log_line(self):
        self.assertIsNone(parse_access_line('garbage'))
        self.assertIsNone(parse_access_line(''))


class ExtendedTail(unittest.TestCase):
    def test_pairs_parsed(self):
        r = parse_access_line(BASIC + ' cache=HIT rt=0.002 urt=-')
        self.assertEqual((r.cache, r.rt, r.urt), ('HIT', 0.002, None))

    def test_unknown_pairs_ignored(self):
        r = parse_access_line(BASIC + ' foo=bar cache=MISS')
        self.assertEqual(r.cache, 'MISS')

    def test_non_finite_times_are_dropped(self):
        # float() accepts 'nan' and overflows '1e400' to inf; neither is
        # a request time, and either would poison the percentiles.
        r = parse_access_line(BASIC + ' rt=nan urt=inf')
        self.assertIsNone(r.rt)
        self.assertIsNone(r.urt)
        r = parse_access_line(BASIC + ' rt=1e400 urt=-1e400')
        self.assertIsNone(r.rt)
        self.assertIsNone(r.urt)
        r = parse_access_line(BASIC + ' rt=0.002')
        self.assertEqual(r.rt, 0.002)


class ExtendedEmpty(unittest.TestCase):
    def test_empty_cache_value_is_kept(self):
        # nginx logs '-' for an empty variable, so no real line has
        # 'cache=' with nothing after it; the parser keeps '' rather
        # than None so reach() still counts it as an nginx answer.
        r = parse_access_line(
            'man.netbsd.org:443 1.2.3.4 - - [28/Aug/2026:01:00:00 +0300] '
            '"GET /ls.1 HTTP/1.1" 200 1 "-" "x" cache= rt=0.1 urt=-')
        self.assertEqual(r.cache, '')
        self.assertAlmostEqual(r.rt, 0.1)
        self.assertIsNone(r.urt)


class ReadAccess(unittest.TestCase):
    def test_plain_file(self):
        recs = list(read_access(os.path.join(FIXTURES, 'access.log')))
        self.assertEqual(len(recs), 37)
        self.assertEqual(sum(isinstance(r, Malformed) for r in recs), 1)

    def test_xz_file(self):
        recs = list(read_access(os.path.join(FIXTURES, 'access.log.0.xz')))
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[1].path, '/NetBSD-10.1/i386/ls.1')

    def test_gz_file_and_undecodable_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.log.gz')
            with gzip.open(p, 'wb') as f:
                f.write(BASIC.encode() + b'\n')
                f.write(BASIC.replace('py.1', 'p\xe4.1').encode('latin-1') + b'\n')
            recs = list(read_access(p))
        self.assertEqual(len(recs), 2)
        self.assertIn('�', recs[1].path)

    def test_truncated_xz_raises_oserror(self):
        # lzma raises EOFError, not OSError, on a short stream; the CLI
        # only reports (OSError, ValueError), so it must be translated.
        with open(os.path.join(FIXTURES, 'access.log.0.xz'), 'rb') as f:
            head = f.read(200)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.log.0.xz')
            with open(p, 'wb') as f:
                f.write(head)
            with self.assertRaises(OSError) as cm:
                list(read_access(p))
            self.assertIn(p, str(cm.exception))

    def test_non_log_line_is_malformed(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.log')
            with open(p, 'w') as f:
                f.write('not a log line\n\n' + BASIC + '\n')
            recs = list(read_access(p))
        self.assertEqual([type(r).__name__ for r in recs],
                         ['Malformed', 'Access'])


class Sniff(unittest.TestCase):
    def test_access(self):
        self.assertEqual(sniff(os.path.join(FIXTURES, 'access.log')), 'access')

    def test_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'x')
            with open(p, 'w') as f:
                f.write('nothing\n')
            self.assertIsNone(sniff(p))

    def test_blank_lines_dont_count(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'blanks.log')
            with open(p, 'w') as f:
                # First 24 physical lines: alternating blank and non-log
                for i in range(12):
                    f.write('\n')
                    f.write('x\n')
                # Then the access line as the 25th physical line
                f.write(BASIC + '\n')
            # sniff() should find the access line because it's within
            # the first 20 non-empty lines examined
            self.assertEqual(sniff(p), 'access')


ERR = ('2026/08/28 03:00:02 [error] 18219#0: *10880760 connect() to '
       'unix:/var/run/fcgiwrap.socket failed (61: Connection refused) while '
       'connecting to upstream, client: 167.82.236.27, server: man.netbsd.org, '
       'request: "GET /NetBSD-10.0/amd64/ifconfig.8 HTTP/1.1", '
       'upstream: "fastcgi://unix:/var/run/fcgiwrap.socket:", host: "man.netbsd.org"')


class ParseErrorLine(unittest.TestCase):
    def test_full_line(self):
        r = parse_error_line(ERR)
        self.assertIsInstance(r, Error)
        self.assertEqual(r.when, datetime(2026, 8, 28, 3, 0, 2))
        self.assertEqual(r.level, 'error')
        self.assertEqual(r.message, 'connect() to unix:/var/run/fcgiwrap.socket '
                         'failed (61: Connection refused) while connecting to upstream')
        self.assertEqual(r.client, '167.82.236.27')
        self.assertEqual(r.server, 'man.netbsd.org')
        self.assertEqual(r.request, 'GET /NetBSD-10.0/amd64/ifconfig.8 HTTP/1.1')
        self.assertEqual(r.upstream, 'fastcgi://unix:/var/run/fcgiwrap.socket:')
        self.assertEqual(r.host, 'man.netbsd.org')

    def test_no_trailing_fields(self):
        r = parse_error_line('2026/08/28 04:00:00 [notice] 1#0: signal process started')
        self.assertEqual(r.message, 'signal process started')
        self.assertEqual((r.client, r.server, r.host), ('', '', ''))

    def test_host_with_port(self):
        r = parse_error_line(ERR.replace('host: "man.netbsd.org"', 'host: "man.netbsd.org:443"'))
        self.assertEqual(r.host, 'man.netbsd.org')

    def test_ipv6_host_with_port(self):
        r = parse_error_line(ERR.replace('host: "man.netbsd.org"', 'host: "[2001:db8::1]:443"'))
        self.assertEqual(r.host, '[2001:db8::1]')
        r = parse_error_line(ERR.replace('host: "man.netbsd.org"', 'host: "[2001:db8::1]"'))
        self.assertEqual(r.host, '[2001:db8::1]')

    def test_not_error_line(self):
        self.assertIsNone(parse_error_line(BASIC))
        self.assertIsNone(parse_error_line('    continuation text'))


class ReadError(unittest.TestCase):
    def test_fixture(self):
        recs = list(read_error(os.path.join(FIXTURES, 'error.log')))
        self.assertEqual(len(recs), 6)
        self.assertEqual(sum(r.server == 'man.netbsd.org' for r in recs), 4)

    def test_skipped_lines_are_counted(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'error.log')
            with open(p, 'w', encoding='utf-8') as f:
                f.write(ERR + '\n')
                f.write('    continuation of the message above\n')
                f.write(ERR + '\n')
            skipped = [0]
            recs = list(read_error(p, skipped))
        self.assertEqual(len(recs), 2)
        self.assertEqual(skipped[0], 1)

    def test_skipped_is_optional(self):
        recs = list(read_error(os.path.join(FIXTURES, 'error.log'), None))
        self.assertEqual(len(recs), 6)

    def test_sniff_error(self):
        self.assertEqual(sniff(os.path.join(FIXTURES, 'error.log')), 'error')


if __name__ == '__main__':
    unittest.main()
