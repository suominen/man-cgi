import os
import tempfile
import unittest

from manno_logreport.classify import (
    ARCHES, BROWSER, GRAMMAR_BUCKETS, GRAMMAR_ORIGIN, MAP_GRAMMAR,
    PROBE_FAMILIES, REJECTION_RULES, SELF_INFLICTED, _load_arches, arch_of,
    bot_label,
    collection_of, error_family, grammar_violation, is_probe,
    method_violation, probe_family, query_keys, query_violation, reach,
    referer_host, rejection_rule, route, section_of, status_class,
    ua_family)


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


class Grammar(unittest.TestCase):
    def check(self, expected, *paths):
        for p in paths:
            with self.subTest(path=p):
                self.assertEqual(grammar_violation(p), expected)

    def test_legitimate_paths_have_no_bucket(self):
        self.check(None, '/', '/ls.1', '/ls', '/NetBSD-10.1/i386/ls.1',
                   '/NetBSD-current/', '/NetBSD-10.1', '/NetBSD-10.1/i386/',
                   '/x86/boot.8', '/g++.1', '/getopt_long.3', '/[.1',
                   '/Mail.1', '/nsswitch.conf', '/rc.conf.5', '/ls.3lua',
                   '/NetBSD-10.x-BRANCH/ls.1', '/pkg@version.1', '/a:b.1',
                   '/wp-login.php', '/.env', '/api/v1/archlist',
                   '/.well-known/health', '/NetBSD-10.1/i386/ls%2E1',
                   '/I386/ls.1', '/ls.1/', '/foo.txt.5', '/foo.map.5',
                   '/cgi-bin/man-cgi', '/cgi-bin/man-cgi/')

    def test_self_inflicted_shapes(self):
        cases = {
            '/NetBSD-9.0/evbarm/x86/fdc.4': 'doubled-arch',
            '/NetBSD-11.0/x86/x86/dosboot.8': 'doubled-arch',
            '/x86/x86/boot.8': 'doubled-arch',
            '/i%3E/vax/dl.4': 'markup-leak',
            '/i>/vax/dl.4': 'markup-leak',
            '/a%3E/X509_new.3': 'markup-leak',
            '/etc/vether.4': 'fs-path',
            '/usr/OPENSSL_cleanse.3': 'fs-path',
            '/0/chmod.1': 'numeric-first',
            '/1/hifn.4': 'numeric-first',
            '/sparc/rule,.2': 'comma-name',
            '/NetBSD-6.0.1/x68k/given,.2': 'comma-name',
            '/man.netbsd.org/passwd.5': 'hostname-first',
            '/%60FOO.2': 'sed-range',
            '/NetBSD-11.0/%60FOO.7': 'sed-range',
            '/2%5E0.1': 'sed-range',
        }
        for path, bucket in cases.items():
            with self.subTest(path=path):
                self.assertEqual(grammar_violation(path), bucket)
                self.assertIn(bucket, SELF_INFLICTED)

    def test_external_shapes(self):
        cases = {
            '/<script>alert(1)</script>': 'bad-char',
            '/ls.1;id': 'bad-char',
            '/%s': 'bad-char',
            '/NetBSD-11.0/ls.1%20': 'bad-char',
            '/NetBSD-9.3/../../etc/passwd': 'dot-dot',
            '/NetBSD-9.3//ls.1': 'double-slash',
            '//av.php': 'double-slash',
            '/foo/bar.1': 'unknown-arch',
            '/.git/config': 'unknown-arch',
            '/NetBSD-10.1/I386/ls.1': 'unknown-arch',
            '/a/b/c/d.1': 'too-deep',
            '/api': 'api-other',
            '/api/v1/': 'api-other',
            '/api/v2/x': 'api-other',
            '/cgi-bin/man-cgi/ls.1': 'path-info',
            '/cgi-bin/man-cgi/.well-known/health': 'path-info',
            '/cgi-bin/man-cgi/man': 'path-info',
            '/sitemap.xml': 'asset-suffix',
            '/apple-touch-icon.png': 'asset-suffix',
            '/index.html': 'asset-suffix',
            '/.well-known/security.txt': 'asset-suffix',
            '/NetBSD_10/ls.1': 'bad-char',
            '/Foo_bar-1': 'bad-char',
            '/sparc/ru<le,.2': 'bad-char',
            '/%60FO<O.2': 'bad-char',
        }
        for path, bucket in cases.items():
            with self.subTest(path=path):
                self.assertEqual(grammar_violation(path), bucket)
                self.assertNotIn(bucket, SELF_INFLICTED)

    def test_collection_shape_is_the_cgi_glob(self):
        # [A-Z]*-[0-9]* and [A-Z]*-current are shell globs: anything
        # may sit between the capital and the dash.
        for path in ('/N1-2', '/A-B-1', '/Foo.bar-1', '/X-foo-current',
                     '/NetBSD-current-1'):
            with self.subTest(path=path):
                self.assertIsNone(grammar_violation(path))
        self.assertEqual(grammar_violation('/Foo_bar-1'), 'bad-char')

    def test_absolute_form_target_is_not_judged(self):
        self.assertIsNone(grammar_violation('http://man.netbsd.org/ls.1'))

    def test_decoding_precedes_splitting(self):
        # nginx decodes $uri before the map sees it, so an encoded
        # separator or dot-dot is a separator or dot-dot.
        self.assertEqual(grammar_violation('/ls%2F1'), 'unknown-arch')
        self.assertEqual(grammar_violation('/NetBSD-9.3/%2e%2e/etc/passwd'),
                         'dot-dot')
        self.assertEqual(grammar_violation('/NetBSD-10.1/i386/ls.1%00'),
                         'bad-char')

    def test_markup_leak_needs_an_arch_slot(self):
        # A tag remnant as the page name itself is just a bad character.
        self.assertEqual(grammar_violation('/i%3E'), 'bad-char')
        self.assertEqual(grammar_violation('/NetBSD-11.0/i%3E'), 'bad-char')

    def test_rules_table_is_consistent(self):
        self.assertEqual(len(GRAMMAR_BUCKETS), len(set(GRAMMAR_BUCKETS)))
        self.assertTrue(SELF_INFLICTED <= set(GRAMMAR_BUCKETS))
        self.assertTrue(MAP_GRAMMAR <= set(GRAMMAR_BUCKETS))
        self.assertEqual(set(GRAMMAR_ORIGIN), set(GRAMMAR_BUCKETS))
        self.assertEqual({b for b, o in GRAMMAR_ORIGIN.items() if o == 'self'},
                         SELF_INFLICTED)
        # What the nginx grammar map refuses: illegal characters. The
        # shape rules (archlist membership, depth) are report-only.
        self.assertIn('bad-char', MAP_GRAMMAR)
        self.assertIn('api-other', MAP_GRAMMAR)
        self.assertIn('path-info', MAP_GRAMMAR)
        self.assertIn('asset-suffix', MAP_GRAMMAR)
        self.assertNotIn('doubled-arch', MAP_GRAMMAR)
        self.assertNotIn('unknown-arch', MAP_GRAMMAR)


class Method(unittest.TestCase):
    def test_allowed(self):
        for method, path in (('GET', '/ls.1'), ('HEAD', '/ls.1'),
                             ('GET', '/wp-login.php'), ('POST', '/'),
                             ('POST', '/cgi-bin/man-cgi'),
                             ('POST', '/cgi-bin/man-cgi/')):
            with self.subTest(method=method, path=path):
                self.assertIsNone(method_violation(method, path))

    def test_post_elsewhere(self):
        for path in ('/ls.1', '/graphql', '/NetBSD-current/', '/api/v1/archlist',
                     '/cgi-bin/man-cgi/ls.1'):
            with self.subTest(path=path):
                self.assertEqual(method_violation('POST', path), 'post-path')

    def test_other_verbs(self):
        for method in ('DELETE', 'PUT', 'OPTIONS', 'PROPFIND', 'CONNECT', 'PATCH'):
            with self.subTest(method=method):
                self.assertEqual(method_violation(method, '/'), 'method')
                self.assertEqual(method_violation(method, '/ls.1'), 'method')


class Query(unittest.TestCase):
    LEGACY = ('ls+1+NetBSD-9.3', 'ls+1=', 'boot+8.i386',
              '%2B%2BNetBSD-current', 'p=', 'ls%201', 'Net::DNS+3', 'g++',
              '[+1', '/.well-known/health', 'ls%27+1')

    def test_any_query_on_root_is_refused(self):
        # The legacy form lives at the script's own URL only; a query
        # string on / was never meant to work (and never did).
        self.assertIsNone(query_violation('/', ''))
        for query in self.LEGACY + ('c', '/', 'rest_route=/batch/v1'):
            with self.subTest(query=query):
                self.assertEqual(query_violation('/', query), 'query')

    def test_legacy_form_passes(self):
        for path in ('/cgi-bin/man-cgi', '/cgi-bin/man-cgi/'):
            for query in ('', 'ls+1+NetBSD-9.3', 'ls+1=', 'boot+8.i386',
                          '%2B%2BNetBSD-current', 'p=', 'ls%201',
                          'Net::DNS+3', 'g++', '[+1', '/.well-known/health',
                          # raw, as the map sees it: an encoded quote is
                          # just %27 until the CGI decides
                          'ls%27+1', 'a%27%20or%201%3D1'):
                with self.subTest(path=path, query=query):
                    self.assertIsNone(query_violation(path, query))

    def test_off_grammar_query_on_the_query_endpoints(self):
        for query in ('rest_route=/batch/v1', 'x=1', 'query=ls&sektion=1',
                      'ls+1+NetBSD-9.2=%20UNION%20ALL%20SELECT%20NULL',
                      'a%20and%20b;', 'p=&q=1'):
            with self.subTest(query=query):
                self.assertEqual(query_violation('/', query), 'query')
                self.assertEqual(query_violation('/cgi-bin/man-cgi', query), 'query')

    def test_page_paths_ignore_their_query(self):
        for path in ('/ls.1', '/NetBSD-current/ls.1', '/mount_msdos.8'):
            with self.subTest(path=path):
                self.assertIsNone(query_violation(path, 'utm_source=chatgpt.com'))
                self.assertIsNone(query_violation(path, 'fbclid=IwAR0x'))


class Reach(unittest.TestCase):
    def test_cache_field_is_authoritative(self):
        self.assertEqual(reach('-', 200, '', 'pathinfo'), ('nginx', True))
        self.assertEqual(reach('', 404, '', 'other'), ('nginx', True))
        self.assertEqual(reach('HIT', 404, '', 'other'), ('fastcgi', True))
        self.assertEqual(reach('MISS', 200, '', 'pathinfo'), ('fastcgi', True))
        self.assertEqual(reach('EXPIRED', 301, '', 'pathinfo'), ('fastcgi', True))
        # cache= wins over any status-based rule.
        self.assertEqual(reach('HIT', 429, '', 'pathinfo'), ('fastcgi', True))

    def test_upstream_time_marks_a_post_as_fastcgi(self):
        # nginx caches GET and HEAD only: a POST the CGI answers logs
        # cache=- with an upstream time, an nginx-level answer logs
        # cache=- with none.
        self.assertEqual(reach('-', 303, '', 'pathinfo', 0.02), ('fastcgi', True))
        self.assertEqual(reach('-', 303, '', 'pathinfo', None), ('nginx', True))
        self.assertEqual(reach('-', 404, '', 'other', 0.0), ('fastcgi', True))

    def test_inferred_nginx(self):
        for status, query, rt in ((429, '', 'pathinfo'), (501, '', 'other'),
                                  (405, '', 'pathinfo'), (400, 'x=1', 'pathinfo'),
                                  (403, '', 'other'), (307, '', 'pathinfo'),
                                  (301, 'utm_source=x', 'pathinfo'),
                                  (400, '', 'other'), (503, 'a+and+b', 'pathinfo'),
                                  (200, '', 'static'), (304, '', 'static'),
                                  (200, '', 'report'), (301, '', 'legacy-man'),
                                  (301, '', 'legacy-html')):
            with self.subTest(status=status, query=query, route=rt):
                self.assertEqual(reach(None, status, query, rt), ('nginx', False))

    def test_inferred_fastcgi(self):
        for status, query, rt in ((404, '', 'other'), (200, '', 'pathinfo'),
                                  (301, '', 'pathinfo'),
                                  (503, '', 'pathinfo'), (502, '', 'pathinfo'),
                                  (499, '', 'pathinfo'), (303, '', 'pathinfo'),
                                  (404, '', 'legacy-man'), (200, '', 'health'),
                                  (200, '', 'cgi-query'), (304, '', 'pathinfo')):
            with self.subTest(status=status, query=query, route=rt):
                self.assertEqual(reach(None, status, query, rt), ('fastcgi', False))


class RejectionRule(unittest.TestCase):
    def test_table(self):
        cases = (
            ((429, '', None, None), 'limit-req'),
            ((501, '', 'php', None), 'legacy-501'),
            ((405, '', None, None), 'method'),
            ((400, 'x=1', None, None), 'qs'),
            ((503, 'a+and+b', None, None), 'qs'),
            ((404, '', 'dotfile', None), 'probe-map'),
            ((404, '', 'php', None), 'probe-map'),
            ((404, '', 'cgi-bin-other', None), 'cgi-bin'),
            ((404, '', 'shell', None), 'other'),
            ((404, '', 'traversal', None), 'other'),
            ((404, '', 'other-probe', 'bad-char'), 'grammar-map'),
            ((404, '', None, 'bad-char'), 'grammar-map'),
            ((404, '', None, 'asset-suffix'), 'grammar-map'),
            ((404, '', 'other-probe', 'api-other'), 'grammar-map'),
            ((404, '', None, 'doubled-arch'), 'other'),
            ((404, '', None, None), 'other'),
            ((400, '', None, None), 'other'),
            ((403, '', None, None), 'other'),
        )
        for args, rule in cases:
            with self.subTest(args=args):
                self.assertEqual(rejection_rule(*args), rule)
                self.assertIn(rule, REJECTION_RULES)


class QueryKeys(unittest.TestCase):
    def test_split(self):
        self.assertEqual(query_keys('a=1&b=2'), ['a', 'b'])
        self.assertEqual(query_keys('ls+1+NetBSD-9.3'), ['ls+1+NetBSD-9.3'])
        self.assertEqual(query_keys(''), [])
        self.assertEqual(query_keys('a=1&&=2'), ['a'])
        self.assertEqual(query_keys('rest_route=/batch/v1&page=x'),
                         ['rest_route', 'page'])
        self.assertEqual(query_keys('k' * 200 + '=1'), ['k' * 40])
