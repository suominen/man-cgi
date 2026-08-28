import os
import tempfile
import unittest

from manno_logreport.classify import (
    ARCHES, BROWSER, _load_arches, arch_of, bot_label, collection_of,
    error_family, is_probe, probe_family, referer_host, route, section_of,
    status_class, ua_family)


class Route(unittest.TestCase):
    def check(self, expected, *paths):
        for p in paths:
            with self.subTest(path=p):
                self.assertEqual(route(p), expected)

    def test_health(self):
        self.check('health', '/.well-known/health')

    def test_static(self):
        self.check('static', '/robots.txt', '/favicon.ico', '/NetBSD.ico',
                   '/s/style.css', '/common/images/x.png',
                   '/.well-known/traffic-advice')

    def test_cgi_query(self):
        self.check('cgi-query', '/cgi-bin/man-cgi')

    def test_cgi_pathinfo(self):
        self.check('cgi-pathinfo', '/cgi-bin/man-cgi/NetBSD-9.3/ls.1',
                   '/cgi-bin/man-cgi/')

    def test_legacy_man(self):
        self.check('legacy-man', '/man', '/man/', '/man/ls', '/man/ls+1')
        self.assertNotEqual(route('/manual'), 'legacy-man')

    def test_legacy_html(self):
        self.check('legacy-html', '/7.0/usr/share/man/html8/useradd.html',
                   '/HEAD/usr/share/man/html8/useradd.html')

    def test_pathinfo(self):
        self.check('pathinfo', '/', '/NetBSD-10.1/i386/ls.1', '/NetBSD-current/',
                   '/NetBSD-10.x-BRANCH/ls.1', '/ls.1', '/ls.3lua',
                   '/NetBSD-11.0/wp-login.php', '/x86/boot.8', '/sgimips/mavb.4')

    def test_bare_name_is_a_page_query(self):
        # /<name> without a section: the CGI answers with a menu of
        # matches or a 301 to /<name>.<sect>, so it is a legitimate
        # request even when the name looks odd (rc.conf, wp-login.php).
        self.check('pathinfo', '/ls', '/manual', '/rc.conf', '/wp-login.php',
                   '/index.html', '/222.php', '/g++', '/_exit', '/getopt_long')

    def test_report(self):
        # The published log reports under /r/ (make dist-report).
        self.check('report', '/r/', '/r/2026-08-14..28.html', '/r/x/y')
        # A bare /r is a page-name query, and /rfoo is not the prefix.
        self.check('pathinfo', '/r', '/rfoo')

    def test_api(self):
        self.check('api', '/api/v1/archlist', '/api/v1/colllist',
                   '/api/v1/sectlist')
        self.check('other', '/api', '/api/v1', '/api/v1/other', '/api/graphql',
                   '/api/v1/archlist/')

    def test_other(self):
        self.check('other', '/.env', '/<script>alert(1)</script>',
                   '/cgi-bin/donate.py', '/RCS/man-cgi,v', '/cgi-bin/RCS/x',
                   '/x86/boot', '/Etc/passwd.5', '/etc/passwd.5', '/tmp/foo.1',
                   '/%s', '/a%3E', '/i>', '/ls;id', '/-x', '/.')

    def test_arches_loaded(self):
        self.assertEqual(len(ARCHES), 59)
        self.assertIn('vax', ARCHES)

    def test_empty_arch_file_is_an_error(self):
        # An arch list that loads as empty would silently demote every
        # /ARCH/page.sect request to a probe, so it must not load at all.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'arches')
            with open(p, 'w', encoding='utf-8') as f:
                f.write('# source: nowhere\n# copied: 2026-08-28\n\n')
            with self.assertRaises(ValueError) as cm:
                _load_arches(p)
            self.assertIn(p, str(cm.exception))


class Probe(unittest.TestCase):
    def test_families(self):
        cases = [
            ('/wp-login.php', '', 'php'),
            ('/index.PHP', '', 'php'),
            ('/wp-content/x', '', 'wordpress'),
            ('/xmlrpc.php', '', 'php'),
            ('/.env', '', 'dotfile'),
            ('/.git/config', '', 'dotfile'),
            ('/phpmyadmin/', '', 'admin'),
            ('/admin', '', 'admin'),
            ('/cgi-bin/donate.py', '', 'cgi-bin-other'),
            ('/NetBSD-9.3/../../etc/passwd', '', 'traversal'),
            ('/ls.1', '%2e%2e/%2e%2e/etc/passwd', 'traversal'),
            ('/ls.1', 'cmd=/bin/sh', 'shell'),
            ('/ls.1', 'x=$(wget http://a)', 'shell'),
            ('/ls.1', 'x=chmod 777 /tmp/x', 'shell'),
            ('/<script>alert(1)</script>', '', 'other-probe'),
            ('/bin/sh', '', 'other-probe'),
            ('/etc/passwd.5', '', 'other-probe'),
        ]
        for path, query, expected in cases:
            with self.subTest(path=path, query=query):
                self.assertEqual(probe_family(path, query), expected)

    def test_legitimate_is_not_a_probe(self):
        for path, query in [('/ls.1', ''), ('/NetBSD-10.1/i386/ls.1', ''),
                            ('/cgi-bin/man-cgi', 'ls+1+NetBSD-9.3'),
                            ('/man/ls', ''), ('/robots.txt', ''),
                            ('/NetBSD-current/ls.1', 'a%20and%20b'),
                            ('/wget.1', ''), ('/curl.1', ''), ('/chmod.1', ''),
                            ('/admin.8', ''), ('/NetBSD-10.1/amd64/curl.1', ''),
                            ('/console.4', ''), ('/passwd.5', ''),
                            ('/x86/boot.8', ''),
                            # The site's own query form is
                            # ?COMMAND[+SECTION[.ARCH][+COLLECTION]], so a
                            # query naming a shell utility is an ordinary
                            # manual-page lookup, not a shell-injection probe.
                            ('/cgi-bin/man-cgi', 'curl'),
                            ('/cgi-bin/man-cgi', 'chmod+2'),
                            ('/', 'query=wget')]:
            with self.subTest(path=path):
                self.assertIsNone(probe_family(path, query))
                self.assertFalse(is_probe(path, query))

    def test_legitimate_route_with_probe_family_is_probe(self):
        self.assertTrue(is_probe('/NetBSD-11.0/wp-login.php', ''))
        self.assertEqual(probe_family('/NetBSD-11.0/wp-login.php', ''), 'php')

    def test_other_route_without_family_is_other_probe(self):
        self.assertTrue(is_probe('/%s', ''))
        self.assertEqual(probe_family('/%s', ''), 'other-probe')
        self.assertIsNone(probe_family('/index.html', ''))
        self.assertEqual(probe_family('/wp-login.php', ''), 'php')


class Bots(unittest.TestCase):
    def test_named(self):
        cases = [
            ('Sogou web spider/4.0(+http://www.sogou.com/docs/help/webmasters.htm#07)', 'Sogou'),
            ('CCBot/2.0 (https://commoncrawl.org/faq/)', 'CCBot'),
            ('Lightpanda/1.0', 'Lightpanda'),
            ('TerraCotta 0.2 https://www.github.com/ceramicTeam/CeramicTerracotta', 'TerraCotta'),
            ('Mozilla/5.0 (Windows NT 10.0) Chrome/145.0.0.0 Safari/537.36 (compatible; meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler))', 'Meta-External-Agent'),
            ('facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)', 'Meta-Preview'),
            ('Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)', 'GPTBot'),
            ('Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)', 'ClaudeBot'),
            ('Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)', 'Googlebot'),
            ('Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)', 'Bingbot'),
            ('SofyaBot/1.0', 'SofyaBot'),
            ('DuckDuckBot/1.1; (+http://duckduckgo.com/duckduckbot.html)', 'DuckDuckBot'),
            ('Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)', 'YandexBot'),
        ]
        for ua, expected in cases:
            with self.subTest(ua=ua):
                self.assertEqual(bot_label(ua), expected)

    def test_generic(self):
        for ua in ('curl/8.5.0', 'python-requests/2.31', 'Java/1.8.0_332',
                   'Go-http-client/1.1', 'Scrapy/2.11', 'SomethingCrawler/1.0',
                   'Mozilla/5.0 (compatible; UnknownBot/9)'):
            with self.subTest(ua=ua):
                self.assertEqual(bot_label(ua), 'generic-bot')

    def test_empty(self):
        self.assertEqual(bot_label('-'), 'empty-ua')
        self.assertEqual(bot_label(''), 'empty-ua')

    def test_browser(self):
        for ua in ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
                   'Mozilla/5.0 (X11; NetBSD amd64; rv:128.0) Gecko/20100101 Firefox/128.0',
                   'Fastly health check',
                   'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 DuckDuckGo/7 Safari/604.1'):
            with self.subTest(ua=ua):
                self.assertEqual(bot_label(ua), BROWSER)

    def test_cached(self):
        bot_label.cache_clear()
        ua = 'curl/8.5.0'
        bot_label(ua)
        bot_label(ua)
        self.assertGreaterEqual(bot_label.cache_info().hits, 1)


class StatusClass(unittest.TestCase):
    def test_classes(self):
        for status, expected in [(200, '2xx'), (304, '3xx'), (301, '3xx'),
                                 (404, '4xx'), (400, '4xx'), (429, '429'),
                                 (499, '499'), (501, '5xx'), (503, '5xx'),
                                 (0, 'other'), (999, 'other')]:
            with self.subTest(status=status):
                self.assertEqual(status_class(status), expected)


class ErrorFamily(unittest.TestCase):
    def test_families(self):
        cases = [
            ('connect() to unix:/var/run/fcgiwrap.socket failed (61: Connection refused) while connecting to upstream', 'fcgiwrap-refused'),
            ('upstream timed out (60: Operation timed out) while reading response header from upstream', 'upstream-timeout'),
            ('upstream prematurely closed connection while reading response header from upstream', 'upstream-closed'),
            ('recv() failed (54: Connection reset by peer) while reading response header from upstream', 'upstream-other'),
            ('access forbidden by rule', 'forbidden'),
            ('limiting requests, excess: 15.500 by zone "ip"', 'limit-req'),
            ('signal process started', 'other'),
        ]
        for message, expected in cases:
            with self.subTest(message=message):
                self.assertEqual(error_family(message), expected)


class ContentHelpers(unittest.TestCase):
    def test_collection(self):
        self.assertEqual(collection_of('/NetBSD-10.1/i386/ls.1'), 'NetBSD-10.1')
        self.assertEqual(collection_of('/NetBSD-10.x-BRANCH/ls.1'), 'NetBSD-10.x-BRANCH')
        self.assertEqual(collection_of('/ls.1'), 'NetBSD-current')
        self.assertEqual(collection_of('/'), None)
        self.assertEqual(collection_of('/wp-login.php'), 'NetBSD-current')
        self.assertEqual(collection_of('/%s'), None)
        self.assertEqual(collection_of('/x86/boot.8'), 'NetBSD-current')

    def test_arch(self):
        self.assertEqual(arch_of('/NetBSD-10.1/i386/ls.1'), 'i386')
        self.assertEqual(arch_of('/NetBSD-10.1/ls.1'), None)
        self.assertEqual(arch_of('/ls.1'), None)
        self.assertEqual(arch_of('/x86/boot.8'), 'x86')
        self.assertEqual(arch_of('/x86/boot'), None)

    def test_section(self):
        self.assertEqual(section_of('/NetBSD-10.1/i386/ls.1'), '1')
        self.assertEqual(section_of('/ls.3lua'), '3lua')
        self.assertEqual(section_of('/NetBSD-10.1/'), None)
        self.assertEqual(section_of('/wp-login.php'), None)
        # A bare collection is not a page: '/NetBSD-11.0' must not read
        # its version suffix as section '0'.
        self.assertIsNone(section_of('/NetBSD-11.0'))
        self.assertIsNone(section_of('/NetBSD-10.x-BRANCH'))

    def test_ua_family(self):
        self.assertEqual(ua_family('Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36'), 'Chrome 145')
        self.assertEqual(ua_family('Mozilla/5.0 (X11; NetBSD amd64; rv:128.0) Gecko/20100101 Firefox/128.0'), 'Firefox 128')
        self.assertEqual(ua_family('Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0'), 'Edge 145')
        self.assertEqual(ua_family('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'), 'Safari 17')
        self.assertEqual(ua_family('Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/147.0.0.0 Mobile/15E148 Safari/604.1'), 'Chrome iOS 147')
        self.assertEqual(ua_family('Fastly health check'), 'Fastly health check')
        self.assertEqual(ua_family('Mozilla/5.0'), 'Mozilla/5.0')

    def test_referer_host(self):
        self.assertEqual(referer_host('-'), '-')
        self.assertEqual(referer_host('https://man.netbsd.org/NetBSD-9.2/x'), 'man.netbsd.org')
        self.assertEqual(referer_host('http://man.NetBSD.org'), 'man.netbsd.org')
        self.assertEqual(referer_host('garbage'), 'garbage')
