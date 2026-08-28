"""Optional country/ASN lookups from MaxMind-format databases.

Resolution: explicit paths, then GeoLite2 files, then DB-IP Lite files,
in SEARCH_DIRS. Missing module or files never raise; describe() says
what was looked for so the report can print it.
"""

import datetime
import glob
import os

try:
    import maxminddb
except ImportError:          # optional dependency
    maxminddb = None

SEARCH_DIRS = ('/usr/share/GeoIP', '/var/lib/GeoIP', '/usr/pkg/share/GeoIP',
               '/usr/local/share/GeoIP')
GEOIP_NAMES = ('GeoLite2-City.mmdb', 'GeoLite2-Country.mmdb',
               'dbip-city-lite-*.mmdb', 'dbip-country-lite-*.mmdb')
ASN_NAMES = ('GeoLite2-ASN.mmdb', 'dbip-asn-lite-*.mmdb')


def _search(names):
    for name in names:
        for d in SEARCH_DIRS:
            hits = sorted(glob.glob(os.path.join(d, name)))
            if hits:
                return hits[-1]
    return None


def search_geoip():
    return _search(GEOIP_NAMES)


def search_asn():
    return _search(ASN_NAMES)


def country_from(rec):
    if not rec:
        return None
    for key in ('country', 'registered_country'):
        code = (rec.get(key) or {}).get('iso_code')
        if code:
            return code
    return None


def asn_from(rec):
    if not rec:
        return None
    num = rec.get('autonomous_system_number')
    if num is None:
        return None
    org = rec.get('autonomous_system_organization') or ''
    return f'AS{num} {org}'.rstrip()


def _open(path):
    reader = maxminddb.open_database(path)
    md = reader.metadata()
    built = datetime.datetime.fromtimestamp(
        md.build_epoch, datetime.timezone.utc).date().isoformat()
    return reader, {'path': path, 'type': md.database_type, 'built': built}


class Lookup:
    def __init__(self):
        self._geo = None
        self._asn = None
        self.geoip = None
        self.asn_db = None
        self.reason = None
        self.searched = []
        self._cache = {}

    @property
    def available(self):
        return self._geo is not None or self._asn is not None

    @classmethod
    def find(cls, geoip_path, asn_path):
        lk = cls()
        if geoip_path is None:
            geoip_path = search_geoip()
            lk.searched += [os.path.join(d, n) for n in GEOIP_NAMES for d in SEARCH_DIRS]
        if asn_path is None:
            asn_path = search_asn()
            lk.searched += [os.path.join(d, n) for n in ASN_NAMES for d in SEARCH_DIRS]
        if geoip_path is None and asn_path is None:
            lk.reason = 'no lookup database found'
            return lk
        missing = [p for p in (geoip_path, asn_path)
                   if p is not None and not os.path.exists(p)]
        if missing:
            lk.reason = '; '.join(f'{p}: no such file' for p in missing)
            return lk
        if maxminddb is None:
            lk.reason = 'the maxminddb Python module is not installed'
            return lk
        problems = []
        for attr, meta_attr, path in (('_geo', 'geoip', geoip_path),
                                      ('_asn', 'asn_db', asn_path)):
            if path is None:
                continue
            try:
                reader, meta = _open(path)
            except (OSError, ValueError, RuntimeError) as e:
                problems.append(f'{path}: {e}')
                continue
            setattr(lk, attr, reader)
            setattr(lk, meta_attr, meta)
        if problems:
            lk.reason = '; '.join(problems)
        return lk

    def _get(self, reader, ip):
        key = (id(reader), ip)
        if key not in self._cache:
            try:
                self._cache[key] = reader.get(ip)
            except ValueError:
                self._cache[key] = None
        return self._cache[key]

    def country(self, ip):
        return country_from(self._get(self._geo, ip)) if self._geo else None

    def asn(self, ip):
        return asn_from(self._get(self._asn, ip)) if self._asn else None

    def describe(self):
        return {'available': self.available, 'geoip': self.geoip,
                'asn': self.asn_db, 'searched': list(self.searched),
                'reason': self.reason}
