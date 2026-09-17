#!/usr/bin/env python3
"""The campaign itself under test: it must run, and it must catch a real bug.

`tools/fuzz_prodos.py` judges FIXIT and REPAIR, so something has to judge it.
Three things are held here: a small slice really runs end to end and prints
the summary the CI slice is read from; the seeds it mutates are healthy
volumes and carry the shapes the mutators aim at; and a bug planted in the
harness -- a write that never reaches the disk while the readback pretends it
did -- is caught by invariant 6, which is the invariant that answers the
question the campaign asks.
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import fuzz_prodos
import prodos_check

FUZZ = ROOT / 'tools/fuzz_prodos.py'


def run(*args):
    with tempfile.TemporaryDirectory(prefix='fuzz-prodos-test-') as tmp:
        p = subprocess.run([sys.executable, str(FUZZ), '--out', tmp, *args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=900)
        kept = sorted(x.name for x in Path(tmp).glob('*.po'))
    return p.returncode, p.stdout.decode(), p.stderr.decode(), kept


def summary(text):
    """The head of the report, as `make test` and a reader see it."""
    out = {}
    for line in text.splitlines():
        if line.startswith('  ') or not line.strip():
            continue
        parts = re.split(r'\s{2,}', line.strip(), maxsplit=1)
        if len(parts) == 2:
            out.setdefault(parts[0], parts[1])
    return out


class Campaign(unittest.TestCase):
    def test_a_short_campaign_runs_and_reports(self):
        code, out, err, kept = run('--count', '20', '--seed', '1')
        self.assertEqual(code, 0, out + err)
        s = summary(out)
        self.assertIn('cases', s)
        self.assertTrue(s['cases'].startswith('20 '), s['cases'])
        self.assertEqual(s['failing cases'], '0', s)
        self.assertEqual(s['invariants'], 'all held', s)
        self.assertIn('mutators', s)
        self.assertRegex(s['check coverage'], r'\d+/28 ids')
        self.assertEqual(kept, [], 'a passing campaign keeps no image')

    def test_the_same_seed_gives_the_same_campaign(self):
        _, a, _, _ = run('--count', '12', '--seed', '7')
        _, b, _, _ = run('--count', '12', '--seed', '7')
        self.assertEqual(a, b, 'the campaign must be reproducible case by case')

    def test_a_planted_lost_write_is_caught_by_invariant_six(self):
        """The harness swallows the first write and lies about it.

        REPAIR then sees the block it wanted, reads it back, compares it and
        says `repaired`, while the disk never changed. Nothing in REPAIR can
        notice; invariant 6 asks the oracle instead, and the oracle reads the
        image. A campaign that let this through would be worth nothing.
        """
        code, out, err, kept = run('--count', '24', '--seed', '1', '--bug')
        self.assertEqual(code, 1, out + err)
        s = summary(out)
        self.assertIn('6-monotone', s['invariants'], out)
        self.assertNotEqual(s['failing cases'], '0')
        self.assertTrue(kept, 'a failing case keeps its image')


class Seeds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='fuzz-prodos-seeds-')
        cls.seeds = fuzz_prodos.build_seeds(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_seed_is_a_healthy_volume(self):
        for name, seed in self.seeds.items():
            with self.subTest(seed=name):
                result = prodos_check.check(seed.data)
                self.assertEqual(prodos_check.to_json(result.findings), [])
                self.assertTrue(result.complete)

    def test_the_seeds_carry_the_shapes_the_mutators_aim_at(self):
        big = self.seeds['big8193']
        self.assertEqual(big.total, 8193)
        self.assertEqual(big.pages, 3, 'three bitmap pages')
        self.assertTrue([b for b in big.data_blocks if b >= 4096],
                        'files in the second bitmap page')
        self.assertIsNotNone(big.deepest, 'one level short of DIR_DEPTH')
        fixture = self.seeds['fixture1600']
        self.assertTrue(fixture.ext_keys, 'an extended file, for FORK_STORAGE')
        self.assertTrue(fixture.index_blocks, 'index blocks, for IDX_RANGE')
        self.assertEqual(self.seeds['floppy280'].total, 280)
        for name, seed in self.seeds.items():
            with self.subTest(seed=name):
                self.assertTrue(seed.subdir_keys, name)
                self.assertGreaterEqual(len(seed.data_blocks), 3, name)

    def test_the_tolerant_reader_reads_what_the_plain_one_reads(self):
        """On a healthy volume it must agree with tools/prodos_read.py."""
        sys.path.insert(0, str(ROOT / 'tools'))
        import prodos_read
        for name, seed in self.seeds.items():
            image = prodos_read.Image(seed.data)
            w, _ = fuzz_prodos.walked(seed.data)
            for (block, slot), (path, storage, key, eof) in w.files.items():
                with self.subTest(seed=name, file=path):
                    e = seed.data[block * prodos_check.BLOCK + 4
                                  + slot * prodos_check.ENTRY_LEN:][:39]
                    want = (image.read(e) if storage != prodos_check.EXTENDED
                            else None)
                    got = fuzz_prodos.read_file(seed.data, storage, key, eof)
                    if want is not None:
                        self.assertEqual(got, want)

    def test_a_mutation_is_reproducible_from_its_case_number(self):
        import random
        for index in (1, 2, 3, 1000, 999999):
            a = fuzz_prodos.mutate(self.seeds['fixture1600'], random.Random(index))
            b = fuzz_prodos.mutate(self.seeds['fixture1600'], random.Random(index))
            self.assertEqual(bytes(a[0]), bytes(b[0]))
            self.assertEqual(a[1], b[1])

    def test_every_allowance_names_the_document_that_carries_it(self):
        doc = (ROOT / 'docs/FIXIT.md').read_text()
        source = FUZZ.read_text()
        for name in fuzz_prodos.ALLOWED:
            with self.subTest(allowance=name):
                self.assertIn(name, doc, 'docs/FIXIT.md must name the divergence')
                self.assertIn('docs/FIXIT.md', source)


if __name__ == '__main__':
    unittest.main()
