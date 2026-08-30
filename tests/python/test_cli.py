import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from manno_logreport.render_html import SECTION_IDS
from manno_logreport.report import collect_inputs, main, window_name

HERE = os.path.dirname(__file__)
FIXTURES = os.path.join(HERE, '..', 'fixtures', 'logs')
BIN = os.path.join(HERE, '..', '..', 'bin', 'manno-logreport')


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Collect(unittest.TestCase):
    def test_directory(self):
        found = collect_inputs([FIXTURES])
        self.assertEqual([(os.path.basename(p), k) for p, k in found], [
            ('access.log', 'access'), ('access.log.0.xz', 'access'),
            ('error.log', 'error')])

    def test_files_are_sniffed(self):
        found = collect_inputs([os.path.join(FIXTURES, 'error.log')])
        self.assertEqual(found[0][1], 'error')

    def test_unknown_kind_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'x')
            with open(p, 'w') as f:
                f.write('nothing\n')
            with self.assertRaises(ValueError):
                collect_inputs([p])

    def test_empty_file_kind_comes_from_its_name(self):
        # A rotated log can legitimately be empty; sniff() cannot tell
        # what it is, but its name can.
        with tempfile.TemporaryDirectory() as d:
            for name, kind in (('access.log', 'access'), ('error.log.1', 'error')):
                p = os.path.join(d, name)
                open(p, 'w').close()
                with self.subTest(name=name):
                    self.assertEqual(collect_inputs([p]), [(p, kind)])
            p = os.path.join(d, 'nameless.log')
            open(p, 'w').close()
            with self.assertRaises(ValueError):
                collect_inputs([p])


class WindowName(unittest.TestCase):
    def test_same_month(self):
        self.assertEqual(window_name(['2026-08-14', '2026-08-20', '2026-08-28']),
                         '2026-08-14..28')

    def test_across_months(self):
        self.assertEqual(window_name(['2026-08-25', '2026-09-05']),
                         '2026-08-25..2026-09-05')

    def test_single_day(self):
        self.assertEqual(window_name(['2026-08-28']), '2026-08-28')


class OutputDir(unittest.TestCase):
    def test_names_files_by_window(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'reports')
            code, stdout, err = run('-O', out, FIXTURES)
            self.assertEqual(code, 0, err)
            html = os.path.join(out, '2026-08-27..28.html')
            self.assertEqual(stdout.strip(), html)
            self.assertTrue(os.path.exists(html))
            with open(os.path.join(out, '2026-08-27..28.json')) as f:
                self.assertEqual(json.load(f)['window']['days'],
                                 ['2026-08-27', '2026-08-28'])

    def test_conflicts_with_explicit_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, BIN, '-O', d, '-o', 'x.html', FIXTURES],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn('not allowed with', r.stderr)


class Main(unittest.TestCase):
    def test_report_to_stdout(self):
        code, out, err = run(FIXTURES)
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith('<!DOCTYPE html>'))
        for i in SECTION_IDS:
            self.assertIn(f'<h2 id="{i}"', out)

    def test_output_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            html = os.path.join(d, 'r.html')
            js = os.path.join(d, 'r.json')
            code, out, err = run('-o', html, '--json', js, '--top', '3', FIXTURES)
            self.assertEqual(code, 0, err)
            self.assertEqual(out, '')
            with open(js) as f:
                tree = json.load(f)
            self.assertEqual(tree['totals']['requests'], 37)
            self.assertEqual(tree['reach']['totals'], {'nginx': 11, 'fastcgi': 26})
            self.assertEqual(tree['by_day']['2026-08-27']['requests'], 2)
            self.assertEqual(tree['totals']['error_lines'], 4)
            self.assertEqual(len(tree['content']['top200']), 3)
            self.assertEqual(tree['meta']['host'], 'man.netbsd.org')
            with open(html) as f:
                self.assertIn('<h2 id="backend"', f.read())

    def test_failed_html_leaves_no_json(self):
        with tempfile.TemporaryDirectory() as d:
            js = os.path.join(d, 'r.json')
            code, out, err = run('-o', os.path.join(d, 'no-such-dir', 'r.html'),
                                 '--json', js, FIXTURES)
            self.assertEqual(code, 1)
            self.assertFalse(os.path.exists(js))
            self.assertEqual(os.listdir(d), [])

    def test_failed_replace_leaves_no_new_file(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, 'r.html')
            os.mkdir(target)
            code, out, err = run('-o', target, FIXTURES)
            self.assertEqual(code, 1)
            self.assertEqual(sorted(os.listdir(d)), ['r.html'])

    def test_other_host_has_no_records(self):
        code, out, err = run('--host', 'nobody.example', FIXTURES)
        self.assertEqual(code, 2)
        self.assertIn('no access-log records', err)

    def test_host_filter(self):
        with tempfile.TemporaryDirectory() as d:
            js = os.path.join(d, 'r.json')
            code, out, err = run('--host', 'oxygene.gw.fi', '--json', js, FIXTURES)
            self.assertEqual(code, 0, err)
            with open(js) as f:
                tree = json.load(f)
            self.assertEqual(tree['totals']['requests'], 1)

    def test_empty_directory_has_no_input_files(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, err = run(d)
        self.assertEqual(code, 1)
        self.assertIn('no input files', err)

    def test_unreadable_input(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, err = run(os.path.join(d, 'missing.log'))
        self.assertEqual(code, 1)
        self.assertIn('missing.log', err)

    def test_empty_access_log_reaches_the_no_records_exit(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'access.log')
            open(p, 'w').close()
            code, out, err = run(p, os.path.join(FIXTURES, 'error.log'))
        self.assertEqual(code, 2, err)
        self.assertIn('no access-log records', err)

    def test_truncated_compressed_log_is_reported(self):
        with open(os.path.join(FIXTURES, 'access.log.0.xz'), 'rb') as f:
            head = f.read(200)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.log.0.xz')
            with open(p, 'wb') as f:
                f.write(head)
            code, out, err = run(p)
        self.assertEqual(code, 1)
        self.assertIn(p, err)
        self.assertNotIn('Traceback', err)

    def test_malformed_lines_are_counted_per_host(self):
        # nginx logs a junk request line under whichever vhost took the
        # connection; a report on one host must not count another's.
        line = ('man.netbsd.org:443 167.82.236.31 - - '
                '[28/Aug/2026:21:00:23 +0300] "GET /ls.1 HTTP/1.1" 200 10 '
                '"-" "Mozilla/5.0 (X11; NetBSD amd64; rv:128.0) '
                'Gecko/20100101 Firefox/128.0"')
        junk = ('other.example:443 198.51.100.9 - - '
                '[28/Aug/2026:21:00:24 +0300] "-" 400 0 "-" "-"')
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'access.log')
            with open(p, 'w') as f:
                f.write(junk + '\n' + line + '\n')
            js = os.path.join(d, 'r.json')
            code, out, err = run('--host', 'man.netbsd.org', '--json', js,
                                 '-o', os.path.join(d, 'r.html'), p)
            self.assertEqual(code, 0, err)
            with open(js) as f:
                tree = json.load(f)
        self.assertEqual(tree['totals']['requests'], 1)
        self.assertEqual(tree['totals']['malformed'], 0)

    def test_verbose(self):
        code, out, err = run('-v', FIXTURES)
        self.assertEqual(code, 0)
        self.assertIn('access.log', err)

    def test_bin_wrapper(self):
        r = subprocess.run([sys.executable, BIN, '--help'],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('LOGDIR', r.stdout)
        self.assertTrue(os.access(BIN, os.X_OK))

    def test_usage_error_exits_1(self):
        r = subprocess.run([sys.executable, BIN], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn('LOGDIR', r.stderr)
        r = subprocess.run([sys.executable, BIN, '--top', 'x', FIXTURES],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)

    def test_negative_top_is_a_usage_error(self):
        r = subprocess.run([sys.executable, BIN, '--top', '-1', FIXTURES],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout[:200])
        self.assertIn('--top', r.stderr)
        self.assertNotIn('Traceback', r.stderr)
