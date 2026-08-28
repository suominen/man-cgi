"""CDN address ranges: membership tests and the refresh formatter."""

import ipaddress
import json
import os

DEFAULT_RANGES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'data', 'fastly.cidr')
SOURCE_URL = 'https://api.fastly.com/public-ip-list'


class CidrSet:
    def __init__(self, networks):
        self._v4 = []
        self._v6 = []
        for text in networks:
            net = ipaddress.ip_network(text, strict=False)
            (self._v4 if net.version == 4 else self._v6).append(net)
        self._cache = {}

    def __contains__(self, ip):
        hit = self._cache.get(ip)
        if hit is None:
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                hit = False
            else:
                if addr.version == 6 and addr.ipv4_mapped:
                    # nginx logs an IPv4 client on an IPv6 listener as
                    # ::ffff:A.B.C.D; match it against the v4 ranges.
                    addr = addr.ipv4_mapped
                nets = self._v4 if addr.version == 4 else self._v6
                hit = any(addr in n for n in nets)
            if len(self._cache) < 100000:
                self._cache[ip] = hit
        return hit

    @classmethod
    def load(cls, path):
        """Read one CIDR per line; '# fetched: DATE' in the header is kept."""
        fetched = None
        nets = []
        with open(path, encoding='utf-8') as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('#'):
                    if line.startswith('# fetched:'):
                        fetched = line.split(':', 1)[1].strip()
                    continue
                try:
                    ipaddress.ip_network(line, strict=False)
                except ValueError as e:
                    raise ValueError(f'{path}:{lineno}: {line!r}: {e}') from e
                nets.append(line)
        return cls(nets), {'path': path, 'fetched': fetched, 'count': len(nets)}


def format_cidr_list(json_text, fetched):
    """Fastly's public-ip-list JSON -> the data file's text."""
    if not json_text.strip():
        # curl failing mid-pipe feeds us nothing; say so rather than
        # letting json.loads() complain about column 1.
        raise ValueError('empty response from Fastly')
    data = json.loads(json_text)
    nets = list(data.get('addresses', [])) + list(data.get('ipv6_addresses', []))
    if not nets:
        raise ValueError('no networks in the Fastly response')
    for net in nets:
        try:
            ipaddress.ip_network(net, strict=False)
        except ValueError as e:
            raise ValueError(f'bad network {net!r}: {e}') from e
    lines = [f'# source: {SOURCE_URL}', f'# fetched: {fetched}'] + nets
    return '\n'.join(lines) + '\n'


def main():
    """stdin: Fastly JSON; stdout: the data file (for make refresh-cdn)."""
    import datetime
    import sys
    try:
        today = datetime.date.today().isoformat()
        sys.stdout.write(format_cidr_list(sys.stdin.read(), today))
    except ValueError as e:
        sys.stderr.write(f'manno_logreport.cdn: {e}\n')
        sys.exit(1)


if __name__ == '__main__':
    main()
