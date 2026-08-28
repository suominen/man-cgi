import datetime
import os
import tempfile
import types
import unittest
from unittest import mock

from manno_logreport import geo


class Find(unittest.TestCase):
    def setUp(self):
        # Explicit-path and missing-module tests still pass a None for
        # the *other* path, so without this they'd fall through to
        # geo.Lookup.find's own search of SEARCH_DIRS and could pick up
        # a real GeoIP/ASN database on a host that has one installed.
        self.p = mock.patch.object(geo, 'SEARCH_DIRS', ())
        self.p.start()
        self.addCleanup(self.p.stop)

    def test_no_databases_anywhere(self):
        with mock.patch.object(geo, 'SEARCH_DIRS', ()):
            lk = geo.Lookup.find(None, None)
        self.assertFalse(lk.available)
        d = lk.describe()
        self.assertIsNone(d['geoip'])
        self.assertIsNone(d['asn'])
        self.assertIsNotNone(d['reason'])
        self.assertIsNone(lk.country('8.8.8.8'))
        self.assertIsNone(lk.asn('8.8.8.8'))

    def test_explicit_missing_file_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            lk = geo.Lookup.find(os.path.join(d, 'nope.mmdb'), None)
        self.assertFalse(lk.available)
        self.assertIn('nope.mmdb', lk.describe()['reason'])

    def test_module_missing_is_reported(self):
        with mock.patch.object(geo, 'maxminddb', None):
            with tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, 'x.mmdb')
                open(p, 'wb').close()
                lk = geo.Lookup.find(p, None)
        self.assertFalse(lk.available)
        self.assertIn('maxminddb', lk.describe()['reason'])

    def test_search_order(self):
        with tempfile.TemporaryDirectory() as d:
            dbip = os.path.join(d, 'dbip-country-lite-2026-08.mmdb')
            open(dbip, 'wb').close()
            with mock.patch.object(geo, 'SEARCH_DIRS', (d,)):
                found = geo.search_geoip()
        self.assertEqual(found, dbip)


class Readers(unittest.TestCase):
    """Exercise the record-to-value mapping without a real database."""

    def test_country_and_asn_from_records(self):
        self.assertEqual(geo.country_from({'country': {'iso_code': 'FI'}}), 'FI')
        self.assertEqual(geo.country_from({'registered_country': {'iso_code': 'SE'}}), 'SE')
        self.assertIsNone(geo.country_from({}))
        self.assertEqual(geo.asn_from({'autonomous_system_number': 15169,
                                       'autonomous_system_organization': 'GOOGLE'}),
                         'AS15169 GOOGLE')
        self.assertIsNone(geo.asn_from(None))


class _FakeMeta:
    database_type = 'GeoLite2-Country'
    build_epoch = int(datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc).timestamp())


class _FakeReader:
    def __init__(self, records):
        self.records = records
        self.calls = 0

    def metadata(self):
        return _FakeMeta()

    def get(self, ip):
        self.calls += 1
        if ip == 'garbage':
            raise ValueError('not an ip')
        return self.records.get(ip)


def fake_module(readers_by_path, corrupt=()):
    def open_database(path):
        if path in corrupt:
            raise RuntimeError('invalid database')
        return readers_by_path[path]
    return types.SimpleNamespace(open_database=open_database)


class WithFakeModule(unittest.TestCase):
    """Exercise the reader path through a fake maxminddb module."""

    def setUp(self):
        # Every test here passes one explicit path and None for the
        # other, so without this the None side would search the real
        # SEARCH_DIRS.
        self.p = mock.patch.object(geo, 'SEARCH_DIRS', ())
        self.p.start()
        self.addCleanup(self.p.stop)

    def test_success_path(self):
        with tempfile.TemporaryDirectory() as d:
            geoip_file = os.path.join(d, 'geo.mmdb')
            asn_file = os.path.join(d, 'asn.mmdb')
            open(geoip_file, 'wb').close()
            open(asn_file, 'wb').close()

            geoip_reader = _FakeReader({'8.8.8.8': {'country': {'iso_code': 'US'}}})
            asn_reader = _FakeReader({'8.8.8.8': {'autonomous_system_number': 15169,
                                                   'autonomous_system_organization': 'GOOGLE'}})
            fake = fake_module({geoip_file: geoip_reader, asn_file: asn_reader})

            with mock.patch.object(geo, 'maxminddb', fake):
                lk = geo.Lookup.find(geoip_file, asn_file)

        self.assertTrue(lk.available)
        self.assertEqual(lk.country('8.8.8.8'), 'US')
        self.assertEqual(lk.asn('8.8.8.8'), 'AS15169 GOOGLE')
        self.assertIsNone(lk.country('1.1.1.1'))
        self.assertIsNone(lk.country('garbage'))
        d = lk.describe()
        self.assertEqual(d['geoip']['type'], 'GeoLite2-Country')
        self.assertEqual(d['geoip']['built'], '2026-08-01')
        self.assertEqual(d['geoip']['path'], geoip_file)
        self.assertIsNotNone(d['asn'])
        self.assertIsNone(d['reason'])

    def test_cache(self):
        with tempfile.TemporaryDirectory() as d:
            geoip_file = os.path.join(d, 'geo.mmdb')
            open(geoip_file, 'wb').close()

            geoip_reader = _FakeReader({'8.8.8.8': {'country': {'iso_code': 'US'}}})
            fake = fake_module({geoip_file: geoip_reader})

            with mock.patch.object(geo, 'maxminddb', fake):
                lk = geo.Lookup.find(geoip_file, None)

            lk.country('8.8.8.8')
            lk.country('8.8.8.8')
            self.assertEqual(geoip_reader.calls, 1)

    def test_corrupt_database_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            geoip_file = os.path.join(d, 'bad.mmdb')
            asn_file = os.path.join(d, 'good.mmdb')
            open(geoip_file, 'wb').close()
            open(asn_file, 'wb').close()

            asn_reader = _FakeReader({'8.8.8.8': {'autonomous_system_number': 15169,
                                                   'autonomous_system_organization': 'GOOGLE'}})
            fake = fake_module({asn_file: asn_reader}, corrupt=(geoip_file,))

            with mock.patch.object(geo, 'maxminddb', fake):
                lk = geo.Lookup.find(geoip_file, asn_file)

        self.assertTrue(lk.available)
        self.assertIsNone(lk.country('8.8.8.8'))
        self.assertEqual(lk.asn('8.8.8.8'), 'AS15169 GOOGLE')
        self.assertIn('invalid database', lk.describe()['reason'])
        self.assertIsNone(lk.describe()['geoip'])

    def test_both_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            geoip_file = os.path.join(d, 'bad1.mmdb')
            asn_file = os.path.join(d, 'bad2.mmdb')
            open(geoip_file, 'wb').close()
            open(asn_file, 'wb').close()

            fake = fake_module({}, corrupt=(geoip_file, asn_file))

            with mock.patch.object(geo, 'maxminddb', fake):
                lk = geo.Lookup.find(geoip_file, asn_file)

        self.assertFalse(lk.available)
        reason = lk.describe()['reason']
        self.assertIn(geoip_file, reason)
        self.assertIn(asn_file, reason)
