"""Fold records into one dict tree.

The tree is what render_html renders and what --json writes, so the
two outputs cannot disagree. Every leaf is JSON-serialisable.
"""

import random
from datetime import timedelta
from collections import Counter, defaultdict

from .classify import (
    BROWSER, GRAMMAR_ORIGIN, SELF_INFLICTED, arch_of, bot_label,
    collection_of, error_family, grammar_violation, method_violation,
    probe_family, query_keys, query_violation, reach, referer_host,
    rejection_rule, route, section_of, status_class, ua_family)


# Distinct keys one attacker-controlled counter will hold before it
# starts dropping (see BoundedCounter). The content counters are keyed
# on paths the service actually answered, and a fortnight of real
# traffic already carries half a million of those, so they get a much
# larger bound: dropping a page that first appears late in the window
# would bias the top-N tables, not just cap them.
DEFAULT_KEY_LIMIT = 200000
DEFAULT_CONTENT_KEY_LIMIT = 2000000


def day_key(dt):
    return f'{dt.year:04d}-{dt.month:02d}-{dt.day:02d}'


def hour_key(dt):
    return f'{dt.hour:02d}'


def top_list(counter, n):
    """[[key, count], ...] by count desc, then key asc."""
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [[k, v] for k, v in items[:n]]


def _counts(counter):
    return {str(k): v for k, v in counter.items()}


class BoundedCounter(Counter):
    """A Counter that stops accepting new keys once it holds LIMIT.

    Path, query and user-agent counters are keyed on attacker-controlled
    strings, so an unbounded one is a memory hazard on a long window.
    Existing keys keep counting; hits on a new key past the limit are
    tallied in DROPPED so the report can say what it did not see.
    """

    def __init__(self, limit=DEFAULT_KEY_LIMIT):
        super().__init__()
        self.limit = limit
        self.dropped = 0

    def add(self, key, n=1):
        if key in self or len(self) < self.limit:
            self[key] += n
        else:
            self.dropped += n

    def __reduce__(self):
        # Counter.__reduce__ rebuilds through self.__class__(dict(self)),
        # which would land the dict in the 'limit' slot and lose every
        # count. Both copy and pickle go through here.
        return (_rebuild_bounded, (self.limit, self.dropped, dict(self)))

    def copy(self):
        # Counter.copy() calls self.__class__(self), same trap.
        return _rebuild_bounded(self.limit, self.dropped, dict(self))


def _rebuild_bounded(limit, dropped, items):
    """Reconstruct a BoundedCounter with both of its fields restored."""
    counter = BoundedCounter(limit)
    counter.update(items)
    counter.dropped = dropped
    return counter


def _percentile(sorted_values, q):
    if not sorted_values:
        return None
    i = round(q * (len(sorted_values) - 1))
    return sorted_values[i]


class _Reservoir:
    def __init__(self, size, rng):
        self.size = size
        self.rng = rng
        self.seen = 0
        self.values = []

    def add(self, value):
        self.seen += 1
        if len(self.values) < self.size:
            self.values.append(value)
        else:
            j = self.rng.randrange(self.seen)
            if j < self.size:
                self.values[j] = value

    def summary(self):
        if not self.seen:
            return None
        v = sorted(self.values)
        return {'n': self.seen, 'p50': _percentile(v, 0.50),
                'p90': _percentile(v, 0.90), 'p99': _percentile(v, 0.99)}


class _Breadth:
    """Distinct paths per (day, client), capped.

    At the cap the path set is dropped and counting stops: the count is
    then a floor, not a distinct-path count, and CAPPED says so. (It
    used to keep incrementing on every hit, which turned the column
    into a request count for any client past the cap.)
    """

    __slots__ = ('paths', 'count', 'capped')

    def __init__(self):
        self.paths = set()
        self.count = 0
        self.capped = False

    def add(self, path, cap):
        if self.capped:
            return
        if path not in self.paths:
            self.paths.add(path)
            self.count += 1
            if self.count >= cap:
                self.paths = None
                self.capped = True


class Aggregator:
    def __init__(self, cdn, top=25, breadth_cap=2000, sample_size=5000, seed=0,
                 key_limit=DEFAULT_KEY_LIMIT,
                 content_key_limit=DEFAULT_CONTENT_KEY_LIMIT):
        self.cdn = cdn
        self.top = top
        self.breadth_cap = breadth_cap
        self.key_limit = key_limit
        self.content_key_limit = content_key_limit
        self.sample_size = sample_size
        self.rng = random.Random(seed)
        self.first = None
        self.last = None
        self.requests = 0
        self.bytes = 0
        self.extended = 0
        self.malformed = 0
        self.malformed_sample = []
        self.by_day = defaultdict(lambda: {
            'requests': 0, 'bytes': 0, 'bots': 0, 'probes': 0,
            'classes': Counter(), 'status': Counter(), 'routes': Counter(),
            'bots_by_label': Counter(), 'cache': Counter(),
            'reach': Counter(), 'leaks': 0})
        self.status = Counter()
        self.by_hour = Counter()
        self.by_day_hour = Counter()
        self.routes = defaultdict(lambda: {
            'requests': 0, 'bytes': 0, 'status': Counter(), 'cache': Counter(),
            'rt': _Reservoir(self.sample_size, self.rng),
            'urt': _Reservoir(self.sample_size, self.rng)})
        self.bots = defaultdict(lambda: {
            'requests': 0, 'bytes': 0, 'status': Counter(), 'robots': 0})
        self.browser_no_referer = 0
        self.referer_hosts = Counter()
        self.ua_families = Counter()
        self.client_requests = Counter()
        self.client_days = defaultdict(set)
        self.client_breadth = defaultdict(_Breadth)      # (day, ip)
        self.day_ip_requests = Counter()                 # (day, ip)
        self.cdn_requests = 0
        self.probe = {'requests': 0, 'bytes': 0, 'families': Counter(),
                      'paths': BoundedCounter(key_limit),
                      'queries': BoundedCounter(key_limit),
                      'uas': BoundedCounter(key_limit),
                      'status': Counter(),
                      'methods': BoundedCounter(key_limit), 'ok': Counter()}
        # Backend reach (ADR-0020): who answered, and the junk that got
        # through to the FastCGI location — the candidates for the
        # rejection maps.
        self.reach = {
            'totals': Counter(), 'basis': Counter(), 'upstream': 0,
            'by_route': defaultdict(Counter),
            'by_family': defaultdict(Counter),
            'by_grammar': defaultdict(Counter),
            'rejections': Counter(),
            'grammar': {'requests': 0, 'buckets': Counter(),
                        'paths': BoundedCounter(key_limit),
                        'self_paths': BoundedCounter(key_limit)},
            'leaks': {'requests': 0, 'families': Counter(),
                      'grammar': Counter(), 'violations': Counter(),
                      'methods': BoundedCounter(key_limit),
                      'paths': BoundedCounter(key_limit),
                      'query_keys': BoundedCounter(key_limit)}}
        self.top200 = BoundedCounter(content_key_limit)
        self.top404 = BoundedCounter(content_key_limit)
        self.coll200 = Counter()
        self.coll404 = Counter()
        self.sections = Counter()
        self.arches = Counter()
        self.redirect_routes = Counter()
        self.unclassified = BoundedCounter(key_limit)
        # error log (Task 8)
        self.error_lines = 0
        self.errors_by_day = defaultdict(Counter)
        self.error_families = Counter()
        self.error_buckets = Counter()
        self.error_samples = {}

    # -- access -----------------------------------------------------------

    def add_malformed(self, rec):
        self.malformed += 1
        if len(self.malformed_sample) < 10:
            self.malformed_sample.append(rec.line[:200])

    def add_access(self, rec):
        day = day_key(rec.when)
        hour = hour_key(rec.when)
        rt = route(rec.path)
        family = probe_family(rec.path, rec.query)
        # The grammar applies to what the CGI parses as a page path;
        # the other routes have their own shapes (or are nginx's). A
        # named probe family is judged by that family alone: a .php
        # path four directories deep is a probe, not a "too deep" page.
        grammar = None
        if (family in (None, 'other-probe')
                and rt in ('pathinfo', 'other', 'cgi-pathinfo')):
            grammar = grammar_violation(rec.path)
        mv = method_violation(rec.method, rec.path)
        qv = query_violation(rec.path, rec.query)
        where, exact = reach(rec.cache, rec.status, rec.query, rt, rec.urt)
        label = bot_label(rec.ua)
        cls = status_class(rec.status)
        is_cdn = rec.client in self.cdn

        if self.first is None or rec.when < self.first:
            self.first = rec.when
        if self.last is None or rec.when > self.last:
            self.last = rec.when
        self.requests += 1
        self.bytes += rec.bytes
        self.status[rec.status] += 1
        self.by_hour[hour] += 1
        self.by_day_hour[(day, hour)] += 1

        d = self.by_day[day]
        d['requests'] += 1
        d['bytes'] += rec.bytes
        d['classes'][cls] += 1
        d['status'][rec.status] += 1
        d['routes'][rt] += 1
        d['bots_by_label'][label] += 1
        if label != BROWSER:
            d['bots'] += 1
        if family is not None:
            d['probes'] += 1

        r = self.routes[rt]
        r['requests'] += 1
        r['bytes'] += rec.bytes
        r['status'][rec.status] += 1

        if rec.cache is not None or rec.rt is not None:
            self.extended += 1
        if rec.cache is not None:
            d['cache'][rec.cache] += 1
            r['cache'][rec.cache] += 1
        if rec.rt is not None:
            r['rt'].add(rec.rt)
        if rec.urt is not None:
            r['urt'].add(rec.urt)

        b = self.bots[label]
        b['requests'] += 1
        b['bytes'] += rec.bytes
        b['status'][rec.status] += 1
        if rec.path == '/robots.txt':
            b['robots'] += 1

        if label == BROWSER:
            host = referer_host(rec.referer)
            if host == '-':
                self.browser_no_referer += 1
            self.referer_hosts[host] += 1
            self.ua_families[ua_family(rec.ua)] += 1

        self.client_requests[rec.client] += 1
        self.client_days[rec.client].add(day)
        self.client_breadth[(day, rec.client)].add(rec.path, self.breadth_cap)
        self.day_ip_requests[(day, rec.client)] += 1
        if is_cdn:
            self.cdn_requests += 1

        if family is not None:
            p = self.probe
            p['requests'] += 1
            p['bytes'] += rec.bytes
            p['families'][family] += 1
            p['paths'].add(rec.path)
            if rec.query:
                p['queries'].add(rec.query)
            p['uas'].add(rec.ua)
            p['status'][rec.status] += 1
            p['methods'].add(rec.method[:16])
            if 200 <= rec.status < 300:
                p['ok'][rec.path] += 1
            if family == 'other-probe' and grammar not in SELF_INFLICTED:
                self.unclassified.add(rec.path)
        else:
            coll = collection_of(rec.path)
            if rec.status == 200:
                self.top200.add(rec.path)
                if coll:
                    self.coll200[coll] += 1
                sect = section_of(rec.path)
                if sect:
                    self.sections[sect] += 1
                arch = arch_of(rec.path)
                if arch:
                    self.arches[arch] += 1
            elif rec.status == 404:
                self.top404.add(rec.path)
                if coll:
                    self.coll404[coll] += 1
            elif rec.status in (301, 302, 303, 307, 308):
                self.redirect_routes[rt] += 1

        self._add_reach(rec, d, rt, family, grammar, mv, qv, where, exact)

    def _add_reach(self, rec, d, rt, family, grammar, mv, qv, where, exact):
        r = self.reach
        r['totals'][where] += 1
        r['basis']['cache' if exact else 'inferred'] += 1
        if rec.urt is not None:
            r['upstream'] += 1
        d['reach'][where] += 1
        r['by_route'][rt][where] += 1
        if family is not None:
            r['by_family'][family][where] += 1
        if grammar is not None:
            r['by_grammar'][grammar][where] += 1
            g = r['grammar']
            g['requests'] += 1
            g['buckets'][grammar] += 1
            if grammar in SELF_INFLICTED:
                g['self_paths'].add(rec.path)
            else:
                g['paths'].add(rec.path)
        if where == 'nginx':
            if rec.status >= 400:
                r['rejections'][rejection_rule(
                    rec.status, rec.query, family, grammar)] += 1
            return
        # Junk that reached the FastCGI location: a map candidate. The
        # site's own broken-link shapes are not one; the grammar table
        # above shows how many of those reached the backend.
        if grammar in SELF_INFLICTED:
            grammar = None
            if family == 'other-probe':
                family = None       # the route catch-all, not a signature
        if family is None and grammar is None and mv is None and qv is None:
            return
        leak = r['leaks']
        leak['requests'] += 1
        d['leaks'] += 1
        if family is not None:
            leak['families'][family] += 1
        if grammar is not None:
            leak['grammar'][grammar] += 1
        if mv is not None:
            leak['violations'][mv] += 1
        if qv is not None:
            leak['violations'][qv] += 1
        leak['methods'].add(rec.method[:16])
        leak['paths'].add(rec.path)
        for key in query_keys(rec.query):
            leak['query_keys'].add(key)

    # -- error log (Task 8) ----------------------------------------------

    def add_error(self, rec):
        fam = error_family(rec.message)
        self.error_lines += 1
        self.errors_by_day[day_key(rec.when)][fam] += 1
        self.error_families[fam] += 1
        bucket = rec.when.strftime('%Y-%m-%d %H:') + f'{rec.when.minute // 10}0'
        self.error_buckets[(bucket, fam)] += 1
        self.error_samples.setdefault(fam, rec.message[:200])

    # -- result -----------------------------------------------------------

    def _clients(self):
        breadth = defaultdict(int)
        capped = defaultdict(bool)
        per_day_cdn = defaultdict(dict)
        for (day, ip), b in self.client_breadth.items():
            breadth[ip] = max(breadth[ip], b.count)
            capped[ip] = capped[ip] or b.capped
            if ip in self.cdn:
                per_day_cdn[day][ip] = {
                    'requests': self.day_ip_requests[(day, ip)],
                    'breadth': b.count, 'capped': b.capped}
        top = []
        # Same tie-break as top_list(): count desc, then key asc, so the
        # table does not depend on insertion order.
        ordered = sorted(self.client_requests.items(),
                         key=lambda kv: (-kv[1], kv[0]))[:self.top]
        for ip, n in ordered:
            top.append({'ip': ip, 'requests': n, 'breadth': breadth[ip],
                        'breadth_capped': capped[ip],
                        'days': len(self.client_days[ip]),
                        'cdn': ip in self.cdn})
        return {'cdn_requests': self.cdn_requests,
                'non_cdn_requests': self.requests - self.cdn_requests,
                'top': top,
                'per_day_cdn': {d: v for d, v in sorted(per_day_cdn.items())}}

    FULL_DAY_HOURS = 23.5

    def _partial_days(self, days):
        """{day: hours covered} for the first and last day when the
        window does not span them whole (nginx rotates at 21:00, so
        the edge days of any copy are usually partial). Only those two
        days can be partial in a contiguous log."""
        if not days:
            return {}
        partial = {}
        first_day, last_day = days[0], days[-1]
        tz = self.first.tzinfo
        start = self.first.replace(hour=0, minute=0, second=0, microsecond=0)
        end_first = start + timedelta(days=1)
        last_start = self.last.replace(hour=0, minute=0, second=0,
                                       microsecond=0)
        if first_day == last_day:
            hours = (self.last - self.first).total_seconds() / 3600
            if hours < self.FULL_DAY_HOURS:
                partial[first_day] = round(hours, 1)
            return partial
        hours = (end_first - self.first).total_seconds() / 3600
        if hours < self.FULL_DAY_HOURS:
            partial[first_day] = round(hours, 1)
        hours = (self.last - last_start).total_seconds() / 3600
        if hours < self.FULL_DAY_HOURS:
            partial[last_day] = round(hours, 1)
        return partial

    def result(self):
        n = self.top
        days = sorted(self.by_day)
        partial = self._partial_days(days)
        by_day = {}
        for day in days:
            d = self.by_day[day]
            by_day[day] = {
                'requests': d['requests'], 'bytes': d['bytes'],
                'bots': d['bots'], 'probes': d['probes'],
                'classes': _counts(d['classes']), 'status': _counts(d['status']),
                'routes': _counts(d['routes']),
                'bots_by_label': _counts(d['bots_by_label']),
                'cache': _counts(d['cache']),
                'reach': _counts(d['reach']), 'leaks': d['leaks']}
        routes = {}
        for rt, r in self.routes.items():
            routes[rt] = {'requests': r['requests'], 'bytes': r['bytes'],
                          'status': _counts(r['status']),
                          'cache': _counts(r['cache']),
                          'rt': r['rt'].summary(),
                          'urt': r['urt'].summary()}
        bots = {}
        for label, b in self.bots.items():
            bots[label] = {'requests': b['requests'], 'bytes': b['bytes'],
                           'status': _counts(b['status']), 'robots': b['robots']}
        busiest = [[d, h, c] for (d, h), c in
                   sorted(self.by_day_hour.items(),
                          key=lambda kv: (-kv[1], kv[0]))[:n]]
        p = self.probe
        return {
            'window': {
                'first': self.first.isoformat() if self.first else None,
                'last': self.last.isoformat() if self.last else None,
                'days': days,
                'partial': partial,
                'full_days': [d for d in days if d not in partial]},
            'totals': {
                'requests': self.requests, 'bytes': self.bytes,
                'malformed': self.malformed, 'extended': self.extended,
                'bots': sum(b['requests'] for l, b in self.bots.items()
                            if l != BROWSER),
                'probes': p['requests'], 'error_lines': self.error_lines},
            'by_day': by_day,
            'status': _counts(self.status),
            'classes': _counts(self._classes()),
            'by_hour': {f'{h:02d}': self.by_hour.get(f'{h:02d}', 0)
                        for h in range(24)},
            'busiest': busiest,
            'routes': routes,
            'bots': bots,
            'browser': {
                'requests': self.bots[BROWSER]['requests'] if BROWSER in self.bots else 0,
                'no_referer': self.browser_no_referer,
                'referer_hosts': top_list(self.referer_hosts, n),
                'ua_families': top_list(self.ua_families, n)},
            'clients': self._clients(),
            'probes': {
                'requests': p['requests'], 'bytes': p['bytes'],
                'families': _counts(p['families']),
                'paths': top_list(p['paths'], n),
                'queries': top_list(p['queries'], n),
                'uas': top_list(p['uas'], n),
                'status': _counts(p['status']), 'methods': _counts(p['methods']),
                'ok': top_list(p['ok'], n),
                'dropped': (p['paths'].dropped + p['queries'].dropped
                            + p['uas'].dropped)},
            'content': {
                'top200': top_list(self.top200, n),
                'top404': top_list(self.top404, n),
                'collections200': top_list(self.coll200, n),
                'collections404': top_list(self.coll404, n),
                'sections': top_list(self.sections, n),
                'arches': top_list(self.arches, n),
                'redirect_routes': _counts(self.redirect_routes),
                'dropped': self.top200.dropped + self.top404.dropped},
            'reach': self._reach(),
            'errors': self._errors(),
            'malformed_sample': list(self.malformed_sample),
            'unclassified': top_list(self.unclassified, n),
            'unclassified_dropped': self.unclassified.dropped,
        }

    def _reach(self):
        n = self.top
        r = self.reach
        g = r['grammar']
        leak = r['leaks']
        origin = Counter()
        for bucket, count in g['buckets'].items():
            origin[GRAMMAR_ORIGIN[bucket]] += count
        return {
            'totals': _counts(r['totals']),
            'basis': _counts(r['basis']),
            'upstream': r['upstream'],
            'by_route': {k: _counts(v) for k, v in r['by_route'].items()},
            'by_family': {k: _counts(v) for k, v in r['by_family'].items()},
            'by_grammar': {k: _counts(v) for k, v in r['by_grammar'].items()},
            'rejections': _counts(r['rejections']),
            'grammar': {
                'requests': g['requests'],
                'buckets': _counts(g['buckets']),
                'origin': _counts(origin),
                'paths': top_list(g['paths'], n),
                'self_paths': top_list(g['self_paths'], n),
                'dropped': g['paths'].dropped + g['self_paths'].dropped},
            'leaks': {
                'requests': leak['requests'],
                'families': _counts(leak['families']),
                'grammar': _counts(leak['grammar']),
                'violations': _counts(leak['violations']),
                'methods': _counts(leak['methods']),
                'paths': top_list(leak['paths'], n),
                'query_keys': top_list(leak['query_keys'], n),
                'dropped': leak['paths'].dropped + leak['query_keys'].dropped},
        }

    def _classes(self):
        c = Counter()
        for status, count in self.status.items():
            c[status_class(status)] += count
        return c

    def _errors(self):
        bursts = [[b, f, c] for (b, f), c in
                  sorted(self.error_buckets.items(),
                         key=lambda kv: (-kv[1], kv[0]))[:self.top]]
        return {
            'by_day': {d: _counts(c) for d, c in sorted(self.errors_by_day.items())},
            'families': _counts(self.error_families),
            'bursts': bursts,
            'samples': dict(self.error_samples)}
