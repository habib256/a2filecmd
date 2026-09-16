#!/usr/bin/env python3
"""The campaign itself under test: it must run, and it must catch real bugs.

`tools/fuzz_archives.py` judges BINARY2, UNSHRINK, IMGFS and DOSGET, so
something has to judge it. Four things are held here: a small slice really
runs end to end and prints the summary the CI slice is read from; the seeds
it mutates are healthy archives and images, and the host reference reads them
exactly as the project's own independent readers do (`tools/mkbny.py`,
`tools/mkshk.py`, `tools/prodos_read.py`, and the bytes handed to the DOS 3.3
writer); one bug planted per decoder family is caught, each by a different
invariant; and every allowance names the divergence it stands for.
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import fuzz_archives as F      # noqa: E402
import mkbny                   # noqa: E402
import mkshk                   # noqa: E402
import prodos_read             # noqa: E402

FUZZ = ROOT / 'tools/fuzz_archives.py'
DECODERS = ('binary2', 'unshrink', 'imgfs', 'dos33', 'unshrink-core')


def run(*args, timeout=900):
    with tempfile.TemporaryDirectory(prefix='fuzz-arch-test-') as tmp:
        p = subprocess.run([sys.executable, str(FUZZ), '--out', tmp, *args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
        kept = sorted(x.name for x in Path(tmp).glob('*.json'))
    return p.returncode, p.stdout.decode(), p.stderr.decode(), kept


def summary(text):
    """The head of the report, as `make test` and a reader see it."""
    out = {}
    for line in text.splitlines():
        if line.startswith('  ') or line.startswith('FAIL') or not line.strip():
            continue
        parts = re.split(r'\s{2,}', line.strip(), maxsplit=1)
        if len(parts) == 2:
            out.setdefault(parts[0], parts[1])
    return out


class Campaign(unittest.TestCase):
    def test_a_short_campaign_runs_and_reports(self):
        code, out, err, kept = run('--count', '12', '--seed', '1')
        self.assertEqual(code, 0, out + err)
        s = summary(out)
        self.assertTrue(s['cases'].startswith('60 '), s['cases'])
        self.assertEqual(s['failing cases'], '0', s)
        self.assertEqual(s['invariants'], 'all held', s)
        for name in DECODERS:
            self.assertIn(name, s, out)
            self.assertRegex(s[name], r'^\d+ cases, \d+ mutators')
        self.assertEqual(kept, [], 'a passing campaign keeps no input')

    def test_the_same_seed_gives_the_same_campaign(self):
        _, a, _, _ = run('--count', '8', '--seed', '7', '--decoder', 'binary2')
        _, b, _, _ = run('--count', '8', '--seed', '7', '--decoder', 'binary2')
        self.assertEqual(a, b, 'the campaign must be reproducible case by case')

    def test_every_allowance_says_what_it_stands_for(self):
        source = FUZZ.read_text()
        for name, text in F.ALLOWED.items():
            with self.subTest(allowance=name):
                self.assertTrue(text.strip())
                self.assertIn(name, source)


class PlantedBugs(unittest.TestCase):
    """One bug per decoder family; each must be caught, by its own invariant.

    A campaign that let any of these through would be worth nothing: the
    partial kept after a failed record, the archive written to, the output
    that overwrites a file already on the volume, the byte that lands wrong
    and stays, and the 6502 core that hands back something other than what it
    decoded are exactly the five faults the five invariants exist for.
    """

    def check(self, decoder, invariant, count=60):
        code, out, err, kept = run('--count', str(count), '--seed', '1',
                                   '--bug', '--decoder', decoder)
        self.assertEqual(code, 1, 'the planted bug went unnoticed\n' + out + err)
        s = summary(out)
        self.assertIn(invariant, s['invariants'], out)
        self.assertNotEqual(s['failing cases'], '0', out)
        self.assertTrue(kept, 'a failing case keeps its input')

    def test_a_partial_left_behind_by_binary2_is_caught(self):
        self.check('binary2', '3-reference')

    def test_an_archive_written_to_by_unshrink_is_caught(self):
        self.check('unshrink', '5-input')

    def test_a_non_exclusive_reservation_in_imgfs_is_caught(self):
        self.check('imgfs', '2-preserve')

    def test_a_wrong_byte_kept_by_dosget_is_caught(self):
        self.check('dos33', '3-reference')

    def test_a_silently_wrong_decode_by_the_6502_core_is_caught(self):
        self.check('unshrink-core', '3-reference')


class Seeds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='fuzz-arch-seeds-')
        work = Path(cls.tmp.name)
        cls.b2 = F.b2_seeds()
        cls.us = F.us_seeds()
        cls.im = F.im_seeds(work)
        cls.d3 = F.d3_seeds()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_seed_is_read_whole_by_the_reference(self):
        for name, data in self.b2.items():
            with self.subTest(binary2=name):
                self.assertTrue(F.b2_reference(data, set()).whole)
        for name, data in self.us.items():
            with self.subTest(unshrink=name):
                e = F.us_reference(data, set())
                self.assertTrue(e.whole, e.note)
                self.assertFalse(e.fired, 'a healthy archive needs no allowance')
        for name, data in self.im.items():
            with self.subTest(imgfs=name):
                entries = F.im_panel(data, 2)
                self.assertIsNotNone(entries)
                self.assertTrue(F.im_reference(data, entries, 2, set()).whole)
        for name, data in self.d3.items():
            with self.subTest(dos33=name):
                entries = F.d3_panel(data)
                self.assertIsNotNone(entries)
                self.assertTrue(F.d3_reference(data, entries, set()).whole)

    def test_the_seeds_carry_the_shapes_the_mutators_aim_at(self):
        b2 = F.b2_reference(self.b2['folders'], set())
        self.assertEqual(b2.extra, 2, 'two folder records, of both kinds')
        us = F.us_reference(self.us['disk'], set())
        self.assertEqual([n for n, _ in us.files], ['LONGDISKIMAG.PO'],
                         'a disk image member, named by its block count')
        self.assertTrue(F.us_reference(self.us['bxy'], set()).files,
                        'a Binary II wrapper in front of the NuFX header')
        entries = F.im_panel(self.im['fixture1600'], 2)
        big = F.im_reference(self.im['fixture1600'], entries, 2, set())
        self.assertGreaterEqual(big.extra, 2,
                                'a tree file and an extended file, both refused')
        self.assertGreaterEqual(len(big.files), 12, 'the volume directory spans two blocks')
        long_disk = F.d3_panel(self.d3['long'])
        body = F.d3_read_file(self.d3['long'], long_disk[0])
        self.assertEqual(len(body), 130 * 256, 'a file over two T/S lists')
        types = {e.type for e in F.d3_panel(self.d3['plain'])}
        self.assertEqual(types, {0x04, 0x06, 0xFA, 0xFC}, 'T, B, I and A')

    def test_the_binary_two_reference_reads_what_mkbny_reads(self):
        want = None
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.bny'
            path.write_bytes(self.b2['mkbny'])
            want = mkbny.read_bny(path)
        got = F.b2_reference(self.b2['mkbny'], set()).files
        self.assertEqual([n for n, _ in got],
                         [F.prodos_name(r['name'].encode()) for r in want])
        self.assertEqual([d for _, d in got], [r['data'] for r in want])

    def test_the_nufx_reference_reads_what_mkshk_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.shk'
            path.write_bytes(self.us['mkshk'])
            want = mkshk.read_shk(path)
        got = F.us_reference(self.us['mkshk'], set()).files
        self.assertEqual([n for n, _ in got],
                         [F.prodos_name(r['name'].encode()) for r in want])
        self.assertEqual([d for _, d in got], [r['data'] for r in want])

    def test_the_image_reference_reads_what_prodos_read_reads(self):
        for name, data in self.im.items():
            with self.subTest(seed=name):
                image = prodos_read.Image(data)
                want = {}
                for e in image.entries(2):
                    if (e[0] >> 4) in (1, 2):
                        want[e[1:1 + (e[0] & 15)].decode('ascii')] = image.read(e)
                got = dict(F.im_reference(data, F.im_panel(data, 2), 2, set()).files)
                self.assertEqual(sorted(got), sorted(want))
                for k in want:
                    self.assertEqual(got[k], want[k], k)

    def test_the_dos_reference_gives_back_the_bytes_that_were_written(self):
        """The DOS 3.3 seeds are written here, so the bytes are known."""
        text = b'HELLO FROM DOS 3.3\r' * 30 + b'\x00'
        binary = bytes([0x00, 0x20, 0x2C, 0x01]) + bytes((i * 17 + 3) & 255 for i in range(300))
        data = self.d3['plain']
        files = dict(F.d3_reference(data, F.d3_panel(data), set()).files)
        # A text file keeps every byte of every sector it owns, padding
        # included; a BIN file keeps exactly the length in its header.
        self.assertEqual(files['GREETINGS'], text.ljust(len(files['GREETINGS']), b'\0'))
        self.assertEqual(files['BINFILE'], binary[4:])
        self.assertEqual(files['LOCKED'], binary[4:])

    def test_a_mutation_is_reproducible_from_its_case_number(self):
        import random
        for index in (1, 2, 3, 1000, 999999):
            for fn, seed in ((F.b2_mutate, self.b2['sizes']),
                             (F.us_mutate, self.us['many']),
                             (F.im_mutate, self.im['small300']),
                             (F.d3_mutate, self.d3['plain'])):
                with self.subTest(mutator=fn.__name__, case=index):
                    a = fn(seed, random.Random(index))
                    b = fn(seed, random.Random(index))
                    self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
