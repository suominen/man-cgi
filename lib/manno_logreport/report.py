"""Command line: collect inputs, run the pipeline, write the outputs."""

import argparse
import datetime
import fnmatch
import glob
import json
import os
import sys

from . import __version__
from .aggregate import Aggregator
from .cdn import DEFAULT_RANGES, CidrSet
from .geo import Lookup
from .logparse import Malformed, read_access, read_error, sniff
from .render_html import render


PATTERNS = (('access.log*', 'access'), ('error.log*', 'error'))


def _kind_from_name(path):
    """'access' or 'error' from an nginx log's file name, else None."""
    base = os.path.basename(path)
    for pattern, kind in PATTERNS:
        if fnmatch.fnmatch(base, pattern):
            return kind
    return None


def collect_inputs(args):
    """[(path, 'access'|'error'), ...]. Raises ValueError for unknown kinds."""
    found = []
    for arg in args:
        if os.path.isdir(arg):
            for pattern, kind in PATTERNS:
                for path in sorted(glob.glob(os.path.join(arg, pattern))):
                    found.append((path, kind))
        else:
            kind = sniff(arg)
            if kind is None and os.path.getsize(arg) == 0:
                # An empty log has nothing to sniff, and a rotated one
                # legitimately can be; its name still says what it is.
                kind = _kind_from_name(arg)
            if kind is None:
                raise ValueError(f'{arg}: not an nginx access or error log')
            found.append((arg, kind))
    return found


def _non_negative_int(text):
    """argparse type for --top: an int, and not a negative one."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f'{text!r} is not an integer') from None
    if value < 0:
        raise argparse.ArgumentTypeError(f'{text!r} is negative')
    return value


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; the CLI contract says 1."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f'{self.prog}: error: {message}', file=sys.stderr)
        sys.exit(1)


def parse_args(argv):
    p = _Parser(
        prog='manno-logreport',
        description='HTML report about one vhost from nginx access and error logs.')
    p.add_argument('inputs', nargs='+', metavar='LOGDIR|FILE',
                   help='a directory (all access.log* and error.log* in it) or files')
    p.add_argument('-o', '--output', metavar='FILE', help='HTML output (default: stdout)')
    p.add_argument('--json', metavar='FILE', help='also write the aggregated tree as JSON')
    p.add_argument('-O', '--output-dir', metavar='DIR',
                   help='write DIR/<window>.html and DIR/<window>.json, named by '
                        'the first and last day seen, and print the HTML path')
    p.add_argument('--host', default='man.netbsd.org', help='vhost to report on')
    p.add_argument('--cdn-ranges', default=DEFAULT_RANGES, metavar='FILE',
                   help='CIDR list of CDN addresses')
    p.add_argument('--geoip-db', metavar='FILE', help='MaxMind-format country/city database')
    p.add_argument('--asn-db', metavar='FILE', help='MaxMind-format ASN database')
    p.add_argument('--top', type=_non_negative_int, default=25, metavar='N',
                   help='length of top-N tables')
    p.add_argument('-v', '--verbose', action='store_true', help='progress on stderr')
    p.add_argument('--version', action='version', version=f'manno-logreport {__version__}')
    return p.parse_args(argv)


def _write_atomic(path, text):
    """Write TEXT to PATH via PATH.new + os.replace; no partial file on failure."""
    tmp = path + '.new'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def build(inputs, host, cdn, top, verbose=False, log=None):
    """Run the pipeline. Returns (tree, input_meta)."""
    if log is None:
        log = sys.stderr
    agg = Aggregator(cdn, top=top)
    meta_inputs = []
    for path, kind in inputs:
        lines = 0
        skipped = [0]
        if kind == 'access':
            for rec in read_access(path):
                lines += 1
                # A junk request line belongs to whichever vhost took the
                # connection; '' is a line that named no vhost at all.
                if isinstance(rec, Malformed):
                    if rec.vhost in (host, ''):
                        agg.add_malformed(rec)
                elif rec.vhost == host:
                    agg.add_access(rec)
        else:
            for rec in read_error(path, skipped):
                lines += 1
                if host in (rec.server, rec.host):
                    agg.add_error(rec)
        meta_inputs.append({'path': path, 'kind': kind, 'lines': lines,
                            'skipped': skipped[0]})
        if verbose:
            print(f'{path}: {lines} {kind} lines', file=log)
    return agg.result(), meta_inputs


def window_name(days):
    """'2026-08-14..28' for a window inside one month, else both dates."""
    first, last = days[0], days[-1]
    if first == last:
        return first
    if first[:7] == last[:7]:
        return f'{first}..{last[8:]}'
    return f'{first}..{last}'


def main(argv=None):
    args = parse_args(argv)
    if args.output_dir and (args.output or args.json):
        print('manno-logreport: error: -O/--output-dir is not allowed with '
              '-o or --json', file=sys.stderr)
        return 1
    try:
        inputs = collect_inputs(args.inputs)
        cdn, cdn_meta = CidrSet.load(args.cdn_ranges)
        tree, meta_inputs = build(inputs, args.host, cdn, args.top, args.verbose)
    except (OSError, ValueError) as e:
        print(f'manno-logreport: {e}', file=sys.stderr)
        return 1
    if not inputs:
        print('manno-logreport: no input files found', file=sys.stderr)
        return 1
    if tree['totals']['requests'] == 0:
        print(f'manno-logreport: no access-log records for host {args.host}',
              file=sys.stderr)
        return 2
    lookup = Lookup.find(args.geoip_db, args.asn_db)
    meta = {
        'host': args.host,
        'inputs': meta_inputs,
        'cdn': cdn_meta,
        'lookup': lookup.describe(),
        'generated': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        'version': __version__,
        'top': args.top,
    }
    html = render(tree, meta, lookup)
    text = json.dumps(dict(tree, meta=meta), indent=1, sort_keys=True) + '\n'
    try:
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            base = os.path.join(args.output_dir, window_name(tree['window']['days']))
            _write_atomic(base + '.html', html)
            _write_atomic(base + '.json', text)
            print(base + '.html')
        elif args.output:
            _write_atomic(args.output, html)
        else:
            sys.stdout.write(html)
        if args.json:
            _write_atomic(args.json, text)
    except OSError as e:
        print(f'manno-logreport: {e}', file=sys.stderr)
        return 1
    return 0
