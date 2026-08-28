"""Label access and error records: route, probe family, bot, error family.

Everything here is a pure function over strings; the rule tables are
module-level data so they can be read, tested and extended in one place.
"""

import functools
import os
import re

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
