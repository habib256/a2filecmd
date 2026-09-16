#!/usr/bin/env python3
"""The FIXIT oracle under test: clean images stay clean, faults are all seen.

`prodos_check.py` is the reference the C walker of FIXIT will be compared
against, so it is only worth something if it is exact: a healthy volume must
yield nothing at all, and every corruption of `corrupt_prodos.py` must yield
precisely the findings that corruption declares -- no more, no less, and not
merely "some finding". The published images are checked too: they are the
volumes users actually mount, and a false positive on one of them would mean
FIXIT accusing a healthy disk.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import corrupt_prodos as cp
import prodos_check as pc
from prodos_check import BLOCK, ENTRY_LEN, VOLUME_DIR_BLOCKS

CHECK = ROOT / 'tools/prodos_check.py'
CORRUPT = ROOT / 'tools/corrupt_prodos.py'


# -- a hand-made image, in the style of test_volinfo.py's helpers ------------
# The one departure from those helpers: the volume directory really is blocks
# 2 to 5 and the bitmap block 6, because VOLDIR_SIZE and BM_RESERVED now hold
# the checker to the shape ProDOS actually writes.
BITMAP = 6


def word(data, offset, value):
    data[offset:offset + 2] = value.to_bytes(2, 'little')


def entry(kind=1, name=b'A', key=7, blocks=1, eof=1, header=2):
    e = bytearray(ENTRY_LEN)
    e[0] = (kind << 4) | len(name)
    e[1:1 + len(name)] = name
    word(e, 0x11, key)
    word(e, 0x13, blocks)
    e[0x15:0x18] = eof.to_bytes(3, 'little')
    e[0x1E] = 0xE3
    word(e, 0x25, header)
    return e


def fixture(total=280, entries=()):
    """A volume directory chained over blocks 2 to 5, its bitmap at 6."""
    d = bytearray(total * BLOCK)
    d[1028:1030] = b'\xf1V'                  # storage $F, the volume name "V"
    d[1059:1061] = bytes([ENTRY_LEN, 13])
    word(d, 1061, len(entries))
    word(d, 1063, BITMAP)
    word(d, 1065, total)
    for i, b in enumerate(VOLUME_DIR_BLOCKS):
        word(d, b * BLOCK, VOLUME_DIR_BLOCKS[i - 1] if i else 0)
        word(d, b * BLOCK + 2,
             VOLUME_DIR_BLOCKS[i + 1] if i + 1 < len(VOLUME_DIR_BLOCKS) else 0)
    for i, e in enumerate(entries):          # in block 2, after the header
        d[1028 + ENTRY_LEN * (i + 1):1028 + ENTRY_LEN * (i + 2)] = e
    for b in range(total):
        free(d, b)
    for b in range(BITMAP + (total + 4095) // 4096):
        allocated(d, b)
    return d


def allocated(d, b):
    d[BITMAP * BLOCK + (b >> 3)] &= ~(0x80 >> (b & 7))


def free(d, b):
    d[BITMAP * BLOCK + (b >> 3)] |= 0x80 >> (b & 7)


def ptr(d, index, slot, b):
    d[index * BLOCK + slot] = b & 255
    d[index * BLOCK + 256 + slot] = b >> 8


def mini_entry(d, block, offset, kind, key, blocks, eof):
    m = bytearray(8)
    m[0] = kind
    word(m, 1, key)
    word(m, 3, blocks)
    m[5:8] = eof.to_bytes(3, 'little')
    d[block * BLOCK + offset:block * BLOCK + offset + 8] = m


class CleanFixture(unittest.TestCase):
    """The volume mkvolume.py writes, plus a hand-made extended file."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='prodos-check-')
        cls.work = Path(cls.tmp.name)
        cls.image = cp.make_fixture(cls.work)
        cls.clean = cls.image.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_clean_image_has_no_finding(self):
        result = pc.check(self.clean)
        self.assertEqual(pc.to_json(result.findings), [])
        self.assertTrue(result.complete)

    def test_fixture_has_every_storage_type(self):
        kinds = {r.storage for r in cp.Inventory(self.clean).entries}
        self.assertEqual(kinds, {pc.SEEDLING, pc.SAPLING, pc.TREE,
                                 pc.EXTENDED, pc.SUBDIR})

    def test_volume_directory_spans_two_blocks(self):
        self.assertGreater(len(cp.Inventory(self.clean).root_chain), 1)

    def test_check_never_writes(self):
        data = bytearray(self.clean)
        pc.check(data)
        self.assertEqual(bytes(data), self.clean)
        subprocess.run([sys.executable, str(CHECK), str(self.image)],
                       capture_output=True, timeout=120)
        self.assertEqual(self.image.read_bytes(), self.clean)

    def test_cli_round_trip(self):
        broken = self.work / 'broken.po'
        expect = self.work / 'expect.json'
        subprocess.run([sys.executable, str(CORRUPT), str(self.image), str(broken),
                        'crosslink', 'file_count_high', '--expect', str(expect)],
                       check=True, capture_output=True, timeout=120)
        out = subprocess.run([sys.executable, str(CHECK), str(broken), '--json'],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(json.loads(out.stdout), json.loads(expect.read_text()))
        self.assertEqual(self.image.read_bytes(), self.clean, 'the source is read-only')

    def test_two_faults_is_the_union(self):
        parts = []
        for name in ('bitmap_lost', 'file_count_high'):
            d = bytearray(self.clean)
            parts += cp.apply(d, [name]).findings
        d = bytearray(self.clean)
        both = cp.apply(d, ['two_faults'])
        self.assertEqual(pc.to_json(both.findings), pc.to_json(parts))
        self.assertEqual(pc.to_json(pc.check(bytes(d)).findings), pc.to_json(parts))


def corruption_test(name):
    def test(self):
        data = bytearray(self.clean)
        expect = cp.CORRUPTIONS[name](data, cp.Inventory(self.clean))
        self.assertNotEqual(expect.findings, [],
                            f'{name} declares no finding: nobody would detect it')
        self.assertNotEqual(bytes(data), self.clean, f'{name} changed nothing')
        result = pc.check(bytes(data))
        self.assertEqual(pc.to_json(result.findings), pc.to_json(expect.findings))
        self.assertEqual(result.complete, expect.complete)
        for f in result.findings:
            self.assertIn(f.id, pc.CHECKS, 'unknown check id')
            self.assertNotIn(f.id, pc.DEVICE_ONLY, 'an image cannot show this')
    test.__name__ = f'test_corruption_{name}'
    return test


for _name in cp.CORRUPTIONS:
    setattr(CleanFixture, f'test_corruption_{_name}', corruption_test(_name))


class Identifiers(unittest.TestCase):
    """The id list is shared with FIXIT: its order is part of the contract."""

    def test_checks_are_the_thirty_of_the_spec(self):
        self.assertEqual(len(pc.CHECKS), 30)
        self.assertEqual(len(set(pc.CHECKS)), 30)
        self.assertEqual(pc.CHECKS[24:],
                         ('IO_ERROR', 'HDR_NAME', 'VOLDIR_SIZE', 'ENT_ACCESS',
                          'BM_RESERVED', 'BM_TAIL'))

    def test_device_only_checks_are_named_but_never_emitted(self):
        self.assertEqual(pc.DEVICE_ONLY, ('IO_ERROR', 'HDR_NAME'))
        for id in pc.DEVICE_ONLY:
            self.assertIn(id, pc.CHECKS)
        source = (ROOT / 'tools/prodos_check.py').read_text()
        for id in pc.DEVICE_ONLY:
            self.assertNotIn(f"add('{id}'", source,
                             'a device-only check must not be emitted')


class HandMade(unittest.TestCase):
    """A 280-block image built byte by byte, as test_volinfo.py builds its own."""

    def image(self):
        seed, ext, dfork, rfork, sap = 7, 8, 9, 10, 11
        entries = [entry(1, b'SEED', key=seed, blocks=1, eof=300),
                   entry(2, b'SAP', key=sap, blocks=3, eof=1024),
                   entry(5, b'EXT', key=ext, blocks=3, eof=300)]
        d = fixture(280, entries)
        for b in (seed, ext, dfork, rfork, sap, 12, 13):
            allocated(d, b)
        mini_entry(d, ext, 0, 1, dfork, 1, 300)
        mini_entry(d, ext, 256, 1, rfork, 1, 64)
        ptr(d, sap, 0, 12)
        ptr(d, sap, 1, 13)
        return d

    def test_hand_made_image_is_clean(self):
        result = pc.check(bytes(self.image()))
        self.assertEqual(pc.to_json(result.findings), [])
        self.assertTrue(result.complete)

    def test_sparse_hole_is_not_a_lost_block(self):
        d = self.image()
        ptr(d, 11, 0, 0)                             # a hole where block 12 was
        free(d, 12)
        word(d, 1028 + 2 * ENTRY_LEN + 0x13, 2)      # the sapling reaches 2 blocks
        result = pc.check(bytes(d))
        self.assertEqual(pc.to_json(result.findings), [])

    def test_extended_fork_is_followed(self):
        d = self.image()
        d[8 * BLOCK] = 4                             # an impossible fork type
        ids = {f.id for f in pc.check(bytes(d)).findings}
        self.assertEqual(ids, {'FORK_STORAGE', 'BM_LOST'})

    def test_short_volume_directory_is_a_shape_fault(self):
        """A volume directory of three blocks: VOLDIR_SIZE, and 5 reserved."""
        d = self.image()
        word(d, 4 * BLOCK + 2, 0)                    # block 5 leaves the chain
        free(d, 5)
        result = pc.check(bytes(d))
        self.assertEqual([(f.id, f.block, f.expected, f.found) for f in
                          sorted(result.findings, key=pc.sort_key)],
                         [('BM_RESERVED', 5, None, None),
                          ('VOLDIR_SIZE', 4, 4, 3)])

    def test_a_reserved_block_is_never_a_used_free_block(self):
        d = self.image()
        for b in (0, 1, 2, 3, 4, 5, BITMAP):
            free(d, b)
        ids = {(f.id, f.block) for f in pc.check(bytes(d)).findings}
        self.assertEqual(ids, {('BM_RESERVED', b) for b in (0, 1, 2, 3, 4, 5, BITMAP)})

    def test_bitmap_padding_must_be_zero(self):
        d = self.image()
        free(d, 280)                                 # one block past the volume
        self.assertEqual([(f.id, f.block) for f in pc.check(bytes(d)).findings],
                         [('BM_TAIL', 280)])

    def test_depth_limit_stops_the_walk(self):
        """Seventeen nested directories: the walk stops and says so."""
        total, first = 64, BITMAP + 1
        d = fixture(total, [entry(0xD, b'D', key=first, blocks=1, eof=BLOCK)])
        parent, pslot = 2, 1
        for depth in range(17):
            block = first + depth
            allocated(d, block)
            if depth:
                e = entry(0xD, b'D', key=block, blocks=1, eof=BLOCK, header=parent)
                d[parent * BLOCK + 4 + pslot * ENTRY_LEN:
                  parent * BLOCK + 4 + (pslot + 1) * ENTRY_LEN] = e
            head = entry(0xE, b'D', key=0, blocks=0, eof=0)
            head[0x1F], head[0x20] = ENTRY_LEN, 13
            word(head, 0x21, 1)
            word(head, 0x23, parent)
            head[0x25], head[0x26] = pslot + 1, ENTRY_LEN
            d[block * BLOCK + 4:block * BLOCK + 4 + ENTRY_LEN] = head
            parent, pslot = block, 1
        d[parent * BLOCK + 4 + ENTRY_LEN] = 0        # the deepest one is empty
        word(d, parent * BLOCK + 4 + 0x21, 0)
        result = pc.check(bytes(d))
        self.assertFalse(result.complete)
        self.assertEqual({f.id for f in result.findings}, {'DIR_DEPTH'})


class Hostile(unittest.TestCase):
    """check() on images nobody would call ProDOS: findings, never a crash.

    A checker that raises is a checker FIXIT cannot be compared against, and
    a loop that never ends is worse. Each case must come back with findings
    or with `complete = False`, and come back at all.
    """

    def check(self, d):
        result = pc.check(bytes(d))          # must not raise
        self.assertTrue(result.findings or not result.complete,
                        'a hostile image that yields nothing at all')
        return result

    def image(self, total=280, entries=()):
        return fixture(total, entries)

    def test_a_chain_pointing_at_itself_is_a_loop(self):
        d = self.image()
        word(d, 3 * BLOCK + 2, 3)
        result = self.check(d)
        self.assertIn('DIR_LOOP', {f.id for f in result.findings})
        self.assertFalse(result.complete)

    def test_a_chain_never_leads_to_a_boot_block(self):
        """`next` = 1 cuts the chain: block 1 is the walk's already, not a
        directory to read on. Whichever of the two reasons is named, the boot
        block is never parsed as thirteen entries."""
        d = self.image()
        word(d, 5 * BLOCK + 2, 1)
        result = self.check(d)
        self.assertEqual([(f.id, f.block, f.found) for f in result.findings],
                         [('DIR_LOOP', 5, 1)])
        self.assertFalse(result.complete)

    def test_a_directory_key_a_file_already_claims_is_a_loop(self):
        """Block 7 is the seedling's data: read as a directory it would only
        spell findings out of file data. It is a loop, and the pass is cut."""
        d = self.image(280, [entry(1, b'SEED', key=7, blocks=1, eof=1),
                             entry(0xD, b'D', key=7, blocks=1, eof=BLOCK)])
        allocated(d, 7)
        result = self.check(d)
        self.assertEqual([(f.id, f.block) for f in result.findings],
                         [('DIR_LOOP', 7)])
        self.assertFalse(result.complete)

    def test_a_volume_of_fewer_than_six_blocks_cannot_hold_its_root(self):
        for total in (0, 1, 2, 5):
            with self.subTest(total=total):
                d = self.image()
                word(d, 1065, total)
                result = self.check(d)
                self.assertIn('HDR_TOTAL', {f.id for f in result.findings})

    def test_an_index_block_pointing_at_itself_ends(self):
        d = self.image(280, [entry(2, b'SAP', key=11, blocks=2, eof=1024)])
        allocated(d, 11)
        for i in range(256):
            ptr(d, 11, i, 11)
        self.assertIn('XLINK', {f.id for f in self.check(d).findings})

    def test_a_tree_master_pointing_at_itself_ends(self):
        d = self.image(280, [entry(3, b'TRE', key=11, blocks=2, eof=600000)])
        allocated(d, 11)
        for i in range(256):
            ptr(d, 11, i, 11)
        self.assertIn('XLINK', {f.id for f in self.check(d).findings})

    def test_a_key_that_is_a_bitmap_block_is_a_cross_link(self):
        d = self.image(280, [entry(1, b'A', key=BITMAP, blocks=1, eof=1)])
        self.assertEqual([(f.id, f.block) for f in self.check(d).findings],
                         [('XLINK', BITMAP)])

    def test_a_name_of_no_characters_at_all(self):
        d = self.image(280, [entry(1, b'', key=7, blocks=1, eof=1)])
        allocated(d, 7)
        self.assertEqual([(f.id, f.found) for f in self.check(d).findings],
                         [('ENT_NAME', 0)])

    def test_a_bitmap_at_the_last_block_of_a_volume_it_cannot_cover(self):
        d = self.image()
        word(d, 1063, 279)                   # 1 page needed, 1 block left: fits
        self.check(d)
        word(d, 1065, 65535)                 # 16 pages needed, 1 block left
        word(d, 1063, 65534)
        result = self.check(d)
        self.assertIn('HDR_BITMAP', {f.id for f in result.findings})
        self.assertFalse(result.complete)

    def test_an_image_shorter_than_the_volume_directory(self):
        for blocks in (0, 1, 2):
            with self.subTest(blocks=blocks):
                result = pc.check(bytes(blocks * BLOCK))
                self.assertEqual([f.id for f in result.findings], ['HDR_TOTAL'])
                self.assertFalse(result.complete)
        self.assertFalse(pc.check(bytes(300)).complete)

    def test_a_two_img_header_that_lies(self):
        tmp = tempfile.TemporaryDirectory(prefix='prodos-2mg-')
        self.addCleanup(tmp.cleanup)
        good = bytes(self.image())
        for name, offset, length in (('offset past the end', 1 << 30, 280 * BLOCK),
                                     ('length past the end', 64, 1 << 30),
                                     ('zero length', 64, 0)):
            with self.subTest(name):
                h = bytearray(64)
                h[0:4] = b'2IMG'
                h[24:28] = offset.to_bytes(4, 'little')
                h[28:32] = length.to_bytes(4, 'little')
                p = Path(tmp.name) / 'i.2mg'
                p.write_bytes(bytes(h) + good)
                pc.check(pc.load(p))         # must not raise
        p = Path(tmp.name) / 'short.2mg'
        p.write_bytes(b'2IMG' + b'\x00' * 10)
        self.assertFalse(pc.check(pc.load(p)).complete)


class Declarations(unittest.TestCase):
    """corrupt_prodos.py declares by construction: the declaration must hold.

    A corruption whose expectation is computed from the same wrong idea as
    the checker proves nothing. These tests hold the declaration to facts
    that do not come from `prodos_check.py`: which blocks an entry used to
    reach, and the fact that two corruptions of one run are never handed the
    same block or the same name.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='prodos-declare-')
        cls.clean = cp.make_fixture(Path(cls.tmp.name)).read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_free_blocks_are_never_handed_out_twice(self):
        inv = cp.Inventory(self.clean)
        blocks = [inv.free_block() for _ in range(5)]
        self.assertEqual(len(set(blocks)), 5, blocks)
        self.assertEqual(blocks[0], cp.Inventory(self.clean).free_block(),
                         'applied alone, a corruption still gets the lowest')

    def test_an_abandoned_entry_loses_every_block_it_reached(self):
        """Not just its key block: a sapling's index and data blocks too."""
        for name in ('key_out_of_range', 'bad_storage'):
            with self.subTest(name):
                inv = cp.Inventory(self.clean)
                ref = inv.first(pc.SEEDLING)
                expect = cp.CORRUPTIONS[name](bytearray(self.clean), inv)
                self.assertEqual({f.block for f in expect.findings
                                  if f.id == 'BM_LOST'}, set(ref.blocks))
        inv = cp.Inventory(self.clean)
        ref = inv.first(pc.EXTENDED)
        _, storage, key = ref.forks[0]
        expect = cp.CORRUPTIONS['fork_bad'](bytearray(self.clean), inv)
        lost = {f.block for f in expect.findings if f.id == 'BM_LOST'}
        self.assertEqual(lost, set(inv.fork_blocks(storage, key)))
        self.assertNotIn(ref.key, lost,
                         'the key block of the extended file is still reached')

    def test_a_renamed_entry_carries_its_new_path_everywhere(self):
        data = bytearray(self.clean)
        expect = cp.apply(data, ['header_ptr_wrong', 'bad_name', 'bad_access'])
        paths = {f.path for f in expect.findings}
        self.assertEqual(len(paths), 1, paths)
        self.assertTrue(paths.pop().rsplit('/', 1)[1].startswith('1'), expect)
        self.assertEqual(pc.to_json(pc.check(bytes(data)).findings),
                         pc.to_json(expect.findings))

    def test_the_seventeen_of_MANY_declare_exactly_what_the_checker_sees(self):
        """The set the bench and test_fixit.py break a volume with: one page.

        Seventeen identifiers, and a declaration that is the whole truth --
        no corruption of the set quietly undoes another's.
        """
        data = bytearray(self.clean)
        expect = cp.apply(data, list(cp.MANY))
        result = pc.check(bytes(data))
        self.assertEqual(pc.to_json(expect.findings), pc.to_json(result.findings))
        self.assertEqual(expect.complete, result.complete)
        self.assertTrue(result.complete)
        self.assertEqual(len({f.id for f in result.findings}), 17)


class Published(unittest.TestCase):
    """The images we ship must check clean: no false accusation by FIXIT."""


def published_test(path):
    def test(self):
        if not path.exists():
            self.skipTest(f'{path.name} is not built')
        result = pc.check(pc.load(path))
        self.assertEqual(pc.to_json(result.findings), [], path.name)
        self.assertTrue(result.complete, path.name)
    return test


for _p in (sorted((ROOT / 'dist').glob('*.po')) + sorted((ROOT / 'dist').glob('*.2mg'))
           + sorted((ROOT / 'build').glob('A2FILECMD-*.po'))):
    setattr(Published, f'test_{_p.stem.replace("-", "_").replace(".", "_")}',
            published_test(_p))


if __name__ == '__main__':
    unittest.main()
