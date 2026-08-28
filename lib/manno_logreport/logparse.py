"""Turn nginx log lines into records.

Access log (nginx log_format vhost on oxygene):

    $server_name:$server_port $remote_addr - $remote_user [$time_local]
    "$request" $status $bytes_sent "$http_referer" "$http_user_agent"

optionally followed by key=value pairs (the extended format):

    cache=$upstream_cache_status rt=$request_time urt=$upstream_response_time
"""

import gzip
import io
import lzma
import math
import re
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_ACCESS = re.compile(
    r'^(?P<vhost>[^:\s]+):(?P<port>\S+) (?P<client>\S+) - (?P<user>\S+) '
    r'\[(?P<time>[^\]]+)\] "(?P<request>[^"]*)" (?P<status>\d{3}) '
    r'(?P<bytes>\d+) "(?P<referer>[^"]*)" "(?P<ua>[^"]*)"(?P<tail>.*)$')
_REQUEST = re.compile(r'^([A-Z]+) (\S+) (HTTP/[0-9.]+)$')
_PAIR = re.compile(r'(\w+)=(\S*)')
_MONTHS = {m: i for i, m in enumerate(
    ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'), 1)}
_TZ = {}


@dataclass(slots=True)
class Access:
    vhost: str
    port: str
    client: str
    user: str
    when: datetime
    method: str
    path: str
    query: str
    proto: str
    status: int
    bytes: int
    referer: str
    ua: str
    cache: str | None = None
    rt: float | None = None
    urt: float | None = None


@dataclass(slots=True)
class Malformed:
    """A line nginx wrote whose request field is unusable.

    VHOST is the server name the line named, so the count can be per
    host; it is '' for a line that did not match the log format at all
    and therefore names no host.
    """

    line: str
    vhost: str = ''


@dataclass(slots=True)
class Error:
    when: datetime
    level: str
    message: str
    client: str = ''
    server: str = ''
    request: str = ''
    upstream: str = ''
    host: str = ''


def _tz(spec):
    tz = _TZ.get(spec)
    if tz is None:
        sign = -1 if spec[0] == '-' else 1
        delta = timedelta(hours=int(spec[1:3]), minutes=int(spec[3:5]))
        tz = _TZ[spec] = timezone(sign * delta)
    return tz


def parse_time(text):
    """'28/Aug/2026:21:00:23 +0300' -> aware datetime."""
    return datetime(int(text[7:11]), _MONTHS[text[3:6]], int(text[0:2]),
                    int(text[12:14]), int(text[15:17]), int(text[18:20]),
                    tzinfo=_tz(text[21:26]))


def _float(text):
    """A finite float, or None.

    float() also accepts 'nan' and overflows '1e400' to inf; neither is
    a request time, and either would poison a percentile.
    """
    try:
        v = float(text)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def parse_access_line(line):
    """Return Access, Malformed (request field unusable) or None."""
    m = _ACCESS.match(line)
    if m is None:
        return None
    req = _REQUEST.match(m['request'])
    if req is None:
        return Malformed(line, m['vhost'])
    method, uri, proto = req.groups()
    path, _, query = uri.partition('?')
    try:
        when = parse_time(m['time'])
    except (KeyError, ValueError, IndexError):
        return Malformed(line, m['vhost'])
    rec = Access(m['vhost'], m['port'], m['client'], m['user'], when,
                 method, path, query, proto, int(m['status']),
                 int(m['bytes']), m['referer'], m['ua'])
    tail = m['tail']
    if tail:
        for key, value in _PAIR.findall(tail):
            if key == 'cache':
                rec.cache = value
            elif key == 'rt':
                rec.rt = _float(value)
            elif key == 'urt':
                rec.urt = _float(value)
    return rec


_ERROR = re.compile(
    r'^(?P<date>\d{4}/\d\d/\d\d) (?P<time>\d\d:\d\d:\d\d) \[(?P<level>\w+)\] '
    r'\d+#\d+: (?:\*\d+ )?(?P<rest>.*)$')
_ERROR_FIELD = re.compile(
    r', (?P<key>client|server|request|upstream|host|referrer): '
    r'(?:"(?P<quoted>[^"]*)"|(?P<bare>[^,]*))')


def open_log(path):
    """Open a plain, gzip or xz log as text; undecodable bytes become U+FFFD."""
    if path.endswith('.xz'):
        raw = lzma.open(path, 'rb')
    elif path.endswith('.gz'):
        raw = gzip.open(path, 'rb')
    else:
        raw = open(path, 'rb')
    return io.TextIOWrapper(raw, encoding='utf-8', errors='replace',
                            newline='\n')


# Truncated or corrupt compressed logs surface as these, none of which
# is an OSError, so the CLI would print a traceback instead of naming
# the file. Translate them at the read boundary.
_DECOMPRESS_ERRORS = (EOFError, lzma.LZMAError, zlib.error)


def read_access(path):
    """Yield Access or Malformed for every non-empty line."""
    with open_log(path) as f:
        try:
            for line in f:
                line = line.rstrip('\n')
                if not line:
                    continue
                rec = parse_access_line(line)
                yield Malformed(line) if rec is None else rec
        except _DECOMPRESS_ERRORS as e:
            raise OSError(f'{path}: {e}') from e


def parse_error_line(line):
    """Return Error or None (continuation or foreign line).

    The message is whatever precedes the first trailing ', KEY: ' field,
    so a literal ', client: ' inside the message itself truncates it
    there. nginx does not quote its messages, so there is nothing to
    tell the two apart; the family rules all match early text, and the
    stored sample is capped anyway, so a short message is harmless.
    """
    m = _ERROR.match(line)
    if m is None:
        return None
    d, t = m['date'], m['time']
    when = datetime(int(d[0:4]), int(d[5:7]), int(d[8:10]),
                    int(t[0:2]), int(t[3:5]), int(t[6:8]))
    rest = m['rest']
    fields = {}
    first = None
    for fm in _ERROR_FIELD.finditer(rest):
        if first is None:
            first = fm.start()
        value = fm['quoted'] if fm['quoted'] is not None else fm['bare']
        fields[fm['key']] = value
    message = rest if first is None else rest[:first]
    host = fields.get('host', '')
    if host.startswith('['):
        # IPv6 literal in brackets: keep up to and including closing ]
        if ']' in host:
            host = host[:host.index(']') + 1]
    elif host.count(':') == 1:
        # Regular hostname with port
        host = host.split(':', 1)[0]
    return Error(when, m['level'], message, fields.get('client', ''),
                 fields.get('server', ''), fields.get('request', ''),
                 fields.get('upstream', ''), host)


def read_error(path, skipped=None):
    """Yield Error for every line that parses; skip the rest.

    SKIPPED, when given, is a one-element list whose element counts the
    lines that did not parse (continuations, blank lines, foreign text),
    so the report can say how much of the file it ignored.
    """
    with open_log(path) as f:
        try:
            for line in f:
                rec = parse_error_line(line.rstrip('\n'))
                if rec is None:
                    if skipped is not None:
                        skipped[0] += 1
                    continue
                yield rec
        except _DECOMPRESS_ERRORS as e:
            raise OSError(f'{path}: {e}') from e


def sniff(path, lines=20):
    """'access', 'error' or None from the first 20 non-empty lines."""
    with open_log(path) as f:
        count = 0
        try:
            for line in f:
                line = line.rstrip('\n')
                if not line:
                    continue
                count += 1
                if _ACCESS.match(line):
                    return 'access'
                if _ERROR.match(line):
                    return 'error'
                if count >= lines:
                    break
        except _DECOMPRESS_ERRORS as e:
            raise OSError(f'{path}: {e}') from e
    return None
