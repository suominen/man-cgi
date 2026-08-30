"""Label access and error records: route, probe family, bot, error family.

Everything here is a pure function over strings; the rule tables are
module-level data so they can be read, tested and extended in one place.
"""

import functools
import os
import re
import urllib.parse

# --- Arch list -----------------------------------------------------------

# The arches man-cgi actually serves, copied from the site's archlist
# (see lib/manno_logreport/data/arches for provenance). A root-level
# page's first element must be one of these to be a real arch page,
# not merely lowercase-shaped like /etc/passwd.5 or /tmp/foo.1.
_ARCHES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'data', 'arches')


def _load_arches(path):
    with open(path, encoding='utf-8') as f:
        names = frozenset(line.strip() for line in f
                          if line.strip() and not line.startswith('#'))
    if not names:
        # An empty set would silently demote every /ARCH/page.sect
        # request to a probe, which reads as a traffic change.
        raise ValueError(f'{path}: no arch names')
    return names


ARCHES = _load_arches(_ARCHES_PATH)

# --- Routes ------------------------------------------------------------

ROUTES = ('pathinfo', 'api', 'report', 'cgi-query', 'cgi-pathinfo',
          'legacy-man', 'legacy-html', 'static', 'health', 'other')

# The CGI's plain-text list endpoints (ADR-0008). Other /api paths 404.
_API_EXACT = frozenset(('/api/v1/archlist', '/api/v1/colllist',
                        '/api/v1/sectlist'))

_STATIC_EXACT = frozenset(('/robots.txt', '/favicon.ico', '/NetBSD.ico'))
_STATIC_PREFIX = ('/s/', '/common/images/', '/.well-known/')
_LEGACY_HTML = re.compile(r'^/(?:[0-9][0-9.]*|HEAD)/.+/html[^/]+/.*\.html$')
# A root-level manual page: /name.section with no further slash. Sections
# are a digit optionally followed by letters (1, 3, 9, 3lua).
_ROOT_PAGE = re.compile(r'^/[^/]+\.[0-9][0-9a-z]*$')
# A root-level name without a section (/ls, /rc.conf): the CGI answers
# with a menu of matches or a 301 to /name.sect, so any single element
# made of the characters a page name can contain is a page query.
_ROOT_NAME = re.compile(r'^/[A-Za-z0-9_][A-Za-z0-9_.+-]*$')
# Exactly two path elements, neither containing a further slash.
_TWO_PART_PAGE = re.compile(r'^/([^/]+)/([^/]+)$')
_SECTION_SUFFIX = re.compile(r'\.[0-9][0-9a-z]*$')


def _is_arch_page(path):
    """/ARCH/page.sect where ARCH is in the site's served arch list."""
    m = _TWO_PART_PAGE.match(path)
    if not m:
        return False
    arch, last = m.groups()
    return arch in ARCHES and bool(_SECTION_SUFFIX.search(last))


@functools.lru_cache(maxsize=262144)
def route(path):
    """Classify a request path into one of ROUTES. First match wins."""
    if path == '/.well-known/health':
        return 'health'
    if path in _STATIC_EXACT or path.startswith(_STATIC_PREFIX):
        return 'static'
    if path in _API_EXACT:
        return 'api'
    if path == '/api' or path.startswith('/api/'):
        return 'other'          # the CGI reserves /api; other paths 404
    if path.startswith('/r/'):
        return 'report'         # the published log reports
    if path == '/cgi-bin/man-cgi':
        return 'cgi-query'
    if path.startswith('/cgi-bin/man-cgi/'):
        return 'cgi-pathinfo'
    if path == '/man' or path.startswith('/man/'):
        return 'legacy-man'
    if _LEGACY_HTML.match(path):
        return 'legacy-html'
    if (path == '/' or path.startswith('/NetBSD-') or _ROOT_PAGE.match(path)
            or _ROOT_NAME.match(path) or _is_arch_page(path)):
        return 'pathinfo'
    return 'other'


# --- Probes ------------------------------------------------------------

PROBE_FAMILIES = ('php', 'wordpress', 'dotfile', 'admin', 'cgi-bin-other',
                  'traversal', 'shell', 'other-probe')

_PROBE_RULES = (
    ('php', re.compile(r'\.php\d?(?:$|[/?])', re.I), 'both'),
    ('wordpress', re.compile(r'/wp-|xmlrpc', re.I), 'both'),
    ('dotfile', re.compile(
        r'/\.(?:env|git|aws|ssh|svn|hg|DS_Store|htaccess|htpasswd|vscode|idea)'
        r'(?:$|[/?.])', re.I), 'both'),
    ('admin', re.compile(
        r'phpmyadmin|/admin(?:$|[/?])|/manager(?:$|/)|/console(?:$|/)'
        r'|/actuator|/solr|/jenkins', re.I), 'both'),
    ('cgi-bin-other', re.compile(r'^/cgi-bin/(?!man-cgi(?:$|[/?]))', re.I), 'both'),
    ('traversal', re.compile(r'\.\./|%2e%2e', re.I), 'both'),
    # The site's own query form is ?COMMAND[+SECTION[.ARCH][+COLLECTION]],
    # so a bare 'wget', 'curl' or 'chmod' in the query is a manual-page
    # lookup, not an injection attempt. Only shapes that cannot be a
    # command name stay: a shell path, $(...), a backtick, /etc/passwd,
    # and 'chmod' followed by an octal mode.
    ('shell', re.compile(
        r'/bin/(?:ba)?sh|\$\(|`|chmod\s+[0-7]|/etc/passwd', re.I), 'query'),
)


def probe_family(path, query):
    """Family label for a probe, or None for a legitimate request.

    Membership is decided by the whitelist (route()); the family table
    only labels. A request on a legitimate route still counts as a
    probe when a family matches, so /NetBSD-11.0/wp-login.php is 'php'.
    """
    for label, rx, scope in _PROBE_RULES:
        if scope == 'query':
            if query and rx.search(query):
                return label
        else:  # scope == 'both'
            subject = path if not query else path + '?' + query
            if rx.search(subject):
                return label
    if route(path) == 'other':
        return 'other-probe'
    return None


def is_probe(path, query):
    return probe_family(path, query) is not None


# --- URL grammar --------------------------------------------------------

# Shapes the CGI's URL grammar refuses or only redirects, with where
# they come from: 'self' is a link the site itself emits (the
# HTMLizer's cross-reference sed; see TODO.md), 'external' anything
# else. The third field says whether the nginx grammar map (ADR-0020),
# which knows only the character sets, refuses the shape; the shape
# rules here — archlist membership, depth, and the split of an
# unknown first element into fs-path / numeric-first / hostname-first
# — are report-only. nginx merges slashes and resolves . and .. before
# any map sees $uri, so those two buckets count what the client sent,
# not what the map judged.
GRAMMAR_RULES = (
    ('dot-dot',        'external', False),
    ('double-slash',   'external', False),
    ('bad-char',       'external', True),
    ('api-other',      'external', True),   # /api outside the v1 lists
    ('path-info',      'external', True),   # /cgi-bin/man-cgi/<path info>
    ('asset-suffix',   'external', True),   # /sitemap.xml: never a page name
    ('markup-leak',    'self',     True),   # /i>/vax/dl.4
    ('comma-name',     'self',     True),   # /sparc/rule,.2
    ('sed-range',      'self',     True),   # /`FOO.2, /2^0.1: the A-z range
    ('doubled-arch',   'self',     False),  # /NetBSD-9.0/evbarm/x86/fdc.4
    ('fs-path',        'self',     False),  # /etc/vether.4
    ('numeric-first',  'self',     False),  # /0/chmod.1
    ('hostname-first', 'self',     False),  # /man.netbsd.org/passwd.5
    ('unknown-arch',   'external', False),  # /foo/bar.1
    ('too-deep',       'external', False),  # /a/b/c/d.1
)
GRAMMAR_BUCKETS = tuple(b for b, _, _ in GRAMMAR_RULES)
GRAMMAR_ORIGIN = {b: o for b, o, _ in GRAMMAR_RULES}
SELF_INFLICTED = frozenset(b for b, o, _ in GRAMMAR_RULES if o == 'self')
MAP_GRAMMAR = frozenset(b for b, _, m in GRAMMAR_RULES if m)

# The CGI's per-component character sets (sanitize_coll, sanitize_arch
# and sanitize_command in src/man-cgi; the command set minus '/', which
# PATH_INFO splitting has consumed by then).
_COLL_CHARS = re.compile(r'[A-Za-z0-9.-]+')
_ARCH_CHARS = re.compile(r'[.A-Za-z0-9_-]+')
_NAME_CHARS = re.compile(r'[A-Za-z0-9_.+@:\[\]-]+')
# A lone leading element is a collection only when shaped like one
# (the CGI's [A-Z]*-[0-9]* | [A-Z]*-current shell globs, verbatim);
# with more elements any uppercase-first leader is.
_COLL_ALONE = re.compile(r'[A-Z].*-(?:[0-9].*|current)')
_TAG_REMNANT = re.compile(r'[a-z]{1,4}>|</?[a-z]{1,4}>?')
_HOSTNAME = re.compile(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+')
# The HTMLizer's name class is [0-9A-z_][-.,0-9A-z_/]*, and A-z also
# spans [ \ ] ^ ` _ : a backtick or caret in an otherwise valid name
# is one of its links, not a client's invention.
_SED_RANGE = re.compile(r'[`^\\]')
# No page name ends in these (sections are [1-9]..., 3f or [39]lua),
# so a sectionless request for one is an asset probe; the map's rule.
_ASSET_SUFFIX = re.compile(r'\.(?:css|js|json|xml|html?|png|gif|ico|txt|map)$')
_FS_DIRS = frozenset((
    'bin', 'boot', 'dev', 'etc', 'home', 'kern', 'lib', 'libexec', 'mnt',
    'opt', 'proc', 'rescue', 'root', 'sbin', 'stand', 'sys', 'tmp', 'usr',
    'var'))


@functools.lru_cache(maxsize=262144)
def grammar_violation(path):
    """Bucket name for a path the CGI's URL grammar rejects or only
    redirects, else None. The path is percent-decoded first, as nginx
    decodes $uri before the grammar map sees it."""
    if path == '/' or path == '/.well-known/health' or path in _API_EXACT:
        return None
    if path in ('/cgi-bin/man-cgi', '/cgi-bin/man-cgi/'):
        return None             # the query form's URL
    if path.startswith('/cgi-bin/man-cgi/'):
        return 'path-info'      # internal to the / rewrite
    if not path.startswith('/'):
        return None             # an absolute-form target; nginx uses its path
    if path == '/api' or path.startswith('/api/'):
        return 'api-other'
    decoded = urllib.parse.unquote(path)
    if '//' in decoded:
        return 'double-slash'
    parts = decoded.split('/')[1:]
    if any(p in ('..', '.') for p in parts):
        return 'dot-dot'
    if parts and parts[-1] == '':
        parts.pop()             # an index URL (ADR-0017)
    if not parts:
        return None
    if parts[0][:1].isupper() and (len(parts) > 1
                                   or _COLL_ALONE.fullmatch(parts[0])):
        coll = parts.pop(0)
        if not _COLL_CHARS.fullmatch(coll):
            return 'bad-char'
        if not parts:
            return None
    name = parts[-1]
    arches = parts[:-1]
    if any(_TAG_REMNANT.fullmatch(a) for a in arches):
        return 'markup-leak'
    if ',' in name and _NAME_CHARS.fullmatch(name.replace(',', '')):
        return 'comma-name'
    if (_SED_RANGE.search(name)
            and _NAME_CHARS.fullmatch(_SED_RANGE.sub('', name))):
        return 'sed-range'
    if not _NAME_CHARS.fullmatch(name):
        return 'bad-char'
    if not all(_ARCH_CHARS.fullmatch(a) for a in arches):
        return 'bad-char'
    if _ASSET_SUFFIX.search(name):
        return 'asset-suffix'
    if len(arches) >= 2:
        if all(a in ARCHES for a in arches):
            return 'doubled-arch'
        return 'too-deep'
    if arches and arches[0] not in ARCHES:
        first = arches[0]
        if first in _FS_DIRS:
            return 'fs-path'
        if first.isdigit():
            return 'numeric-first'
        if _HOSTNAME.fullmatch(first):
            return 'hostname-first'
        return 'unknown-arch'
    return None


# The site takes GET and HEAD anywhere, and POST (the query form) only
# at / and the script's own URL; a query string is meaningful only at
# the script's own URL, in the legacy positional form
# COMMAND[+[SECTION][.ARCH][+COLLECTION]] (a trailing = is tolerated,
# as the CGI does), and any query string on / is refused. These
# mirror the $man_bad_method and $man_bad_query maps (ADR-0020).
_METHODS = frozenset(('GET', 'HEAD', 'POST'))
_POST_ENDPOINTS = frozenset(('/', '/cgi-bin/man-cgi', '/cgi-bin/man-cgi/'))
_QUERY_ENDPOINTS = frozenset(('/cgi-bin/man-cgi', '/cgi-bin/man-cgi/'))
# Raw, as $query_string is: a %XX passes as such (the map cannot
# decode, and the CGI decodes only %20 and %2B); / is in the CGI's
# command set and carries its documented ?/.well-known/health form.
_LEGACY_QUERY = re.compile(r'[A-Za-z0-9_.+@:\[\]%/-]*=?')


def method_violation(method, path):
    """'method' for a verb the site does not take, 'post-path' for a
    POST anywhere but the query endpoints, else None."""
    if method not in _METHODS:
        return 'method'
    if method == 'POST' and path not in _POST_ENDPOINTS:
        return 'post-path'
    return None


def query_violation(path, query):
    """'query' for any query string on /, or an off-grammar one at
    the script's own URL, else None. A query on a page path is
    ignored by the CGI (readers arrive with tracking parameters) and
    is not judged."""
    if not query:
        return None
    if path == '/':
        return 'query'
    if path in _QUERY_ENDPOINTS and not _LEGACY_QUERY.fullmatch(query):
        return 'query'
    return None


# --- Bots --------------------------------------------------------------

BROWSER = 'browser-like'

# Ordered: specific names first, the generic catch-all next, empty last.
_BOT_RULES = tuple((label, re.compile(rx, re.I)) for label, rx in (
    ('Sogou', r'sogou'),
    ('CCBot', r'CCBot'),
    ('Lightpanda', r'Lightpanda'),
    ('TerraCotta', r'TerraCotta'),
    # Meta's two crawlers get display names: the per-day bot table
    # folds a shared prefix into one spanned heading ("Meta").
    ('Meta-External-Agent', r'meta-externalagent'),
    ('Meta-Preview', r'facebookexternalhit'),
    ('GPTBot', r'GPTBot'),
    ('ChatGPT-User', r'ChatGPT-User'),
    ('OAI-SearchBot', r'OAI-SearchBot'),
    ('ClaudeBot', r'ClaudeBot|anthropic-ai|Claude-Web'),
    ('PerplexityBot', r'PerplexityBot'),
    ('Bytespider', r'Bytespider'),
    ('PetalBot', r'PetalBot'),
    ('Googlebot', r'Googlebot'),
    ('Google-other', r'Google(?:Other|-Extended|-InspectionTool|-Read-Aloud)'),
    ('Bingbot', r'bingbot'),
    ('Applebot', r'Applebot'),
    ('Amazonbot', r'Amazonbot'),
    ('YandexBot', r'YandexBot'),
    ('DuckDuckBot', r'DuckDuckBot'),
    ('Baiduspider', r'Baiduspider'),
    ('SemrushBot', r'SemrushBot'),
    ('AhrefsBot', r'AhrefsBot'),
    ('MJ12bot', r'MJ12bot'),
    ('DotBot', r'DotBot'),
    ('DataForSeoBot', r'DataForSeoBot'),
    ('Barkrowler', r'Barkrowler'),
    ('SofyaBot', r'SofyaBot'),
    ('archive.org', r'archive\.org_bot|ia_archiver'),
    ('generic-bot', r'bot\b|bot/|crawl|spider|scrapy|python-requests'
                    r'|python-urllib|\bcurl/|\bwget/|\bJava/|Go-http-client'
                    r'|libwww|okhttp|httpx/|aiohttp|HeadlessChrome|PhantomJS'),
))


@functools.lru_cache(maxsize=65536)
def bot_label(ua):
    """Named-bot label, 'generic-bot', 'empty-ua', or BROWSER."""
    if ua in ('', '-'):
        return 'empty-ua'
    for label, rx in _BOT_RULES:
        if rx.search(ua):
            return label
    return BROWSER


# --- Status classes ----------------------------------------------------

def status_class(status):
    if status == 429:
        return '429'
    if status == 499:
        return '499'
    if 200 <= status < 300:
        return '2xx'
    if 300 <= status < 400:
        return '3xx'
    if 400 <= status < 500:
        return '4xx'
    if 500 <= status < 600:
        return '5xx'
    return 'other'


# --- Backend reach -----------------------------------------------------

# Answered by nginx without consulting the FastCGI location, when the
# record has no cache= field to say so: the status codes nginx's own
# rules produce (the CGI emits only 301, 302, 303, 304 and 404), a 503
# with a query string (the $qs_error map before ADR-0020), the files
# nginx serves itself, the legacy redirects, and a 301 for a page
# path with a query string (the CGI's own 301s carry none).
_NGINX_STATUS = frozenset((307, 400, 403, 405, 429, 501))
_NGINX_ROUTES = frozenset(('static', 'report'))
_LEGACY_ROUTES = frozenset(('legacy-man', 'legacy-html'))


def reach(cache, status, query, rt, urt=None):
    """(('nginx' | 'fastcgi'), exact). CACHE is $upstream_cache_status
    when the record carried it and URT the upstream time: any cache
    status but '-' means the FastCGI location handled the request (a
    HIT included), and so does an upstream time with '-', which is
    what a POST logs (nginx caches GET and HEAD only, so a POST skips
    the lookup and the status stays unset). '-' with no upstream time
    is nginx alone. Without the fields the answer is inferred from
    status and route, which undercounts nginx once the rejection maps
    are deployed on a host still logging the basic format."""
    if cache is not None:
        if urt is not None or cache not in ('-', ''):
            return 'fastcgi', True
        return 'nginx', True
    if status in _NGINX_STATUS or (status == 503 and query):
        return 'nginx', False
    if rt in _NGINX_ROUTES:
        return 'nginx', False
    if rt in _LEGACY_ROUTES and 300 <= status < 400:
        return 'nginx', False
    if status == 301 and query and rt == 'pathinfo':
        return 'nginx', False   # the query-string redirect (ADR-0020)
    return 'fastcgi', False


REJECTION_RULES = ('probe-map', 'grammar-map', 'qs', 'method', 'cgi-bin',
                   'limit-req', 'legacy-501', 'other')
# The families $probe_path covers: the others are query-scoped, are
# normalised away before the map, or are the outer /cgi-bin/ location's.
_PROBE_MAP_FAMILIES = frozenset(('php', 'wordpress', 'dotfile', 'admin'))


def rejection_rule(status, query, family, grammar):
    """Which nginx rule presumably produced an error answer that never
    reached the FastCGI location (reach() said 'nginx', status >= 400).
    A 404 is credited to the probe map when a family that map covers
    matches, to the grammar map when the grammar bucket is one the map
    refuses, to the outer /cgi-bin/ location for its paths, else to
    'other'."""
    if status == 429:
        return 'limit-req'
    if status == 501:
        return 'legacy-501'
    if status == 405:
        return 'method'
    if status in (400, 503) and query:
        return 'qs'
    if status == 404:
        if family in _PROBE_MAP_FAMILIES:
            return 'probe-map'
        if grammar in MAP_GRAMMAR:
            return 'grammar-map'
        if family == 'cgi-bin-other':
            return 'cgi-bin'
    return 'other'


# --- Error-log families ------------------------------------------------

ERROR_FAMILIES = ('fcgiwrap-refused', 'upstream-timeout', 'upstream-closed',
                  'upstream-other', 'forbidden', 'limit-req', 'other')

_ERROR_RULES = (
    ('fcgiwrap-refused', re.compile(r'fcgiwrap\.socket failed \(\d+: Connection refused\)')),
    ('upstream-timeout', re.compile(r'upstream timed out')),
    ('upstream-closed', re.compile(r'upstream prematurely closed')),
    ('upstream-other', re.compile(r'upstream')),
    ('forbidden', re.compile(r'access forbidden by rule')),
    ('limit-req', re.compile(r'limiting requests')),
)


def error_family(message):
    for label, rx in _ERROR_RULES:
        if rx.search(message):
            return label
    return 'other'


# --- Content helpers ---------------------------------------------------

_ARCH = re.compile(r'^[a-z][a-z0-9]*$')


def _parts(path):
    return [p for p in path.split('/') if p]


def collection_of(path):
    """Collection a pathinfo request addresses; None when not a page."""
    if route(path) != 'pathinfo' or path == '/':
        return None
    parts = _parts(path)
    if parts[0].startswith('NetBSD-'):
        return parts[0]
    return 'NetBSD-current'


def arch_of(path):
    """Arch element of /NetBSD-x/ARCH/page.sect or /ARCH/page.sect, else None."""
    if route(path) != 'pathinfo':
        return None
    parts = _parts(path)
    if len(parts) == 3 and parts[0].startswith('NetBSD-') and _ARCH.match(parts[1]):
        return parts[1]
    if len(parts) == 2 and parts[0] in ARCHES:
        return parts[0]
    return None


def section_of(path):
    """Section suffix of the last path element, else None."""
    if route(path) != 'pathinfo' or path.endswith('/') or path == '/':
        return None
    parts = _parts(path)
    if len(parts) == 1 and parts[0].startswith('NetBSD-'):
        # A bare collection, not a page: '/NetBSD-11.0' would otherwise
        # read its version suffix as section '0'.
        return None
    last = parts[-1]
    m = re.search(r'\.([0-9][0-9a-z]*)$', last)
    return m.group(1) if m else None


_UA_RULES = (
    ('Edge', re.compile(r'\bEdg(?:e|A|iOS)?/(\d+)')),
    ('Chrome iOS', re.compile(r'\bCriOS/(\d+)')),
    ('Firefox iOS', re.compile(r'\bFxiOS/(\d+)')),
    ('Opera', re.compile(r'\bOPR/(\d+)')),
    ('Chrome', re.compile(r'\bChrome/(\d+)')),
    ('Firefox', re.compile(r'\bFirefox/(\d+)')),
    ('Safari', re.compile(r'\bVersion/(\d+)[^ ]* .*Safari/')),
)


@functools.lru_cache(maxsize=65536)
def ua_family(ua):
    """'Chrome 145', 'Firefox 128', ... or the UA up to its first '('."""
    for name, rx in _UA_RULES:
        m = rx.search(ua)
        if m:
            return f'{name} {m.group(1)}'
    return ua.split('(', 1)[0].strip() or ua


def referer_host(referer):
    if referer in ('', '-'):
        return '-'
    m = re.match(r'^[a-z]+://([^/:?#]+)', referer, re.I)
    return m.group(1).lower() if m else referer


def query_keys(query):
    """['a', 'b'] for 'a=1&b=2'; a legacy query 'ls+1+NetBSD-9.3' is
    one key. Keys are cut at 40 characters: they feed a bounded
    counter that an attacker controls."""
    keys = []
    for part in query.split('&'):
        key = part.partition('=')[0]
        if key:
            keys.append(key[:40])
    return keys
