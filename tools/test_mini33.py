#!/usr/bin/env python3
"""The real 6502 catalog parser, with injected read failures.

These run the very objects the Apple II build links, under sim65, with
the disks held here so a chosen read can be made to fail. A failure is
never an end of chain and must never leave a half-filled panel.
"""
import subprocess
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mini_host
import mkmini33
from mini33_fixture import make_disk, read_files, offset

ROOT = Path(__file__).resolve().parents[1]
CAT_OK, CAT_READ, CAT_BAD = 0, 1, 2


class CatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = mini_host.Harness()

    @classmethod
    def tearDownClass(cls):
        cls.harness.cleanup()

    def setUp(self):
        master = bytearray(mkmini33.SIZE)
        master[0] = 1
        master[100:130] = bytes(c | 128 for c in b'HELLO'.ljust(30))
        master[17 * 4096 + 3] = 3
        master[17 * 4096 + 0x34:17 * 4096 + 0x38] = bytes([35, 16, 0, 1])
        self.master = bytes(master)
        self.image = mkmini33.build(self.master, b'\x60' * 2048)
        self.mini = None
        self.fresh()

    def fresh(self):
        """A clean simulator: its BSS starts zeroed, like a fresh BRUN."""
        if self.mini is not None:
            self.mini.close()
        self.mini = self.harness.start()
        self.mini.load(1, self.image)
        self.mini.poke('drive', bytes([1]))
        self.mini.poke('active', bytes([0]))

    def tearDown(self):
        if self.mini is not None:
            self.mini.close()

    def count(self):
        return self.mini.byte('count')

    def name(self, index):
        return bytes(self.mini.peek('ent_name', 30, offset=index * 32))

    def test_catalog_and_preview(self):
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.count(), 4)
        self.assertEqual(self.mini.byte('volume'), 254)
        self.assertEqual(self.name(0), b'HELLO'.ljust(30))
        self.assertEqual(self.name(1), b'A2FC.MINI'.ljust(30))
        self.assertEqual(self.name(2), b'README'.ljust(30))
        self.assertEqual(self.name(3), b'TIGER'.ljust(30))
        self.assertEqual(self.mini.preview(2), CAT_OK)
        self.assertTrue(bytes(self.mini.peek('buffer', 9)) == b'A2FC MINI')
        self.assertEqual(self.mini.image(1), self.image)

    def test_load_file_keeps_the_ts_list(self):
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.mini.load_file(2), CAT_OK)
        text = bytes(self.mini.peek('scratch', 40))
        self.assertTrue(text.startswith(b'A2FC MINI'), text)
        self.assertEqual(self.mini.image(1), self.image)

    def test_load_file_refuses_wrong_ts_offset(self):
        files = read_files(self.image)
        ts = offset(*files['README']['lists'][0])
        img = bytearray(self.image)
        img[ts + 5] = 122
        self.mini.load(1, bytes(img))
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.mini.load_file(2), CAT_BAD)
        self.assertEqual(self.mini.image(1), bytes(img))

    def test_load_file_flags_a_file_larger_than_the_area(self):
        # The viewer shows the first 8 KB; the editor must know that a
        # 33rd data sector exists so it does not save a truncated copy.
        disk = make_disk([('BIG', 0, bytes(range(256)) * 33),
                          ('FIT', 0, b'\x01' * 8192),
                          ('SMALL', 0, b'HELLO')])
        self.mini.load(1, disk)
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.mini.load_file(0), CAT_OK)
        self.assertEqual(self.mini.byte('load_count'), 32)
        self.assertEqual(self.mini.byte('load_more'), 1)
        self.assertEqual(self.mini.load_file(1), CAT_OK)
        self.assertEqual(self.mini.byte('load_count'), 32)
        self.assertEqual(self.mini.byte('load_more'), 0)
        self.assertEqual(self.mini.load_file(2), CAT_OK)
        self.assertEqual(self.mini.byte('load_count'), 1)
        self.assertEqual(self.mini.byte('load_more'), 0)
        self.assertEqual(self.mini.image(1), disk)

    def test_measure_text_caps_at_scratch_minus_one(self):
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.mini.load_file(2), CAT_OK)
        self.mini.poke('load_count', bytes([32]))
        self.mini.poke('scratch', bytes([0x41]), offset=8191)
        self.mini.measure_text()
        self.assertEqual(self.mini.word('edit_len'), 8191)

    def test_tiger_is_a_locked_hgr_binary(self):
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.mini.byte('ent_type', 3) & 0x7F, 4)
        self.assertEqual(self.mini.byte('ent_type', 3) & 0x80, 0x80)
        self.assertEqual(self.mini.byte('ent_seclo', 3), 33)

    def test_entry_fields_match_the_catalog(self):
        self.assertEqual(self.mini.catalog(), CAT_OK)
        cat = self.image[17 * 4096 + 15 * 256:]
        for i in range(4):
            entry = cat[11 + i * 35:46 + i * 35]
            self.assertEqual(self.mini.byte('ent_track', i), entry[0])
            self.assertEqual(self.mini.byte('ent_sector', i), entry[1])
            self.assertEqual(self.mini.byte('ent_type', i), entry[2])
            self.assertEqual(self.mini.byte('ent_slot', i), (15 << 3) | i)
            self.assertEqual(self.mini.byte('ent_seclo', i) |
                             (self.mini.byte('ent_sechi', i) << 8),
                             struct.unpack_from('<H', entry, 33)[0])

    def test_read_errors_no_partial_catalog(self):
        # The VTOC, then the first catalog sector.
        for fail in (0, 1):
            with self.subTest(fail=fail):
                self.fresh()
                self.mini.fail_read = fail
                self.assertEqual(self.mini.catalog(), CAT_READ)
                self.assertEqual(self.count(), 0)
                self.assertEqual(self.mini.image(1), self.image)

    def test_read_error_late_in_the_chain(self):
        self.mini.fail_read = 8
        self.assertEqual(self.mini.catalog(), CAT_READ)
        self.assertEqual(self.count(), 0, 'a broken chain is not a short one')
        self.assertEqual(self.mini.image(1), self.image)

    def test_bad_geometry(self):
        for offset, value in ((0x35, 13), (0x34, 40), (3, 2),
                              (0x27, 121), (0x36, 1), (0x37, 2)):
            with self.subTest(offset=offset):
                self.fresh()
                disk = bytearray(self.image)
                disk[17 * 4096 + offset] = value
                self.mini.load(1, bytes(disk))
                self.assertEqual(self.mini.catalog(), CAT_BAD)
                self.assertEqual(self.count(), 0)

    def test_cycle_and_invalid_links(self):
        off = 17 * 4096 + 15 * 256
        for t, s in ((17, 15), (35, 0), (0, 1), (17, 0)):
            with self.subTest(link=(t, s)):
                self.fresh()
                disk = bytearray(self.image)
                disk[off + 1] = t
                disk[off + 2] = s
                self.mini.load(1, bytes(disk))
                self.assertEqual(self.mini.catalog(), CAT_BAD)
                self.assertEqual(self.count(), 0)

    def test_bad_file_pointer(self):
        disk = bytearray(self.image)
        disk[17 * 4096 + 15 * 256 + 11] = 35
        self.mini.load(1, bytes(disk))
        self.assertEqual(self.mini.catalog(), CAT_BAD)
        self.assertEqual(self.count(), 0)

    def test_unprintable_name_becomes_a_question_mark(self):
        disk = bytearray(self.image)
        at = 17 * 4096 + 15 * 256 + 11 + 3
        disk[at] = 0x81         # a control character with the high bit
        disk[at + 1] = 0xFF
        self.mini.load(1, bytes(disk))
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.name(0)[:2], b'??')

    def test_preview_errors(self):
        self.assertEqual(self.mini.catalog(), CAT_OK)
        for fail in (0, 1):
            with self.subTest(fail=fail):
                self.mini.reads = 0
                self.mini.fail_read = fail
                self.assertEqual(self.mini.preview(0), CAT_READ)
        self.mini.fail_read = -1
        self.assertEqual(self.mini.preview(4), CAT_BAD, 'past the last entry')

    def test_preview_refuses_a_sparse_file(self):
        self.assertEqual(self.mini.catalog(), CAT_OK)
        off = 17 * 4096 + 15 * 256 + 11
        ts = (self.image[off] * 16 + self.image[off + 1]) * 256
        for at, value in ((ts + 12, 35), (ts + 12, 0), (ts + 5, 1)):
            with self.subTest(at=at, value=value):
                disk = bytearray(self.image)
                disk[at] = value
                self.mini.load(1, bytes(disk))
                self.assertEqual(self.mini.preview(0), CAT_BAD)

    def test_capacity_and_paging_data(self):
        # Fifteen full catalog sectors hold exactly 105 entries; a
        # sixteenth must be refused rather than overrun the panel.
        entry = self.image[17 * 4096 + 15 * 256 + 11:17 * 4096 + 15 * 256 + 46]
        disk = bytearray(self.image)
        for s in range(15, 0, -1):
            off = 17 * 4096 + s * 256
            disk[off + 1] = 17 if s > 1 else 0
            disk[off + 2] = s - 1
            for j in range(7):
                disk[off + 11 + j * 35:off + 46 + j * 35] = entry
        self.mini.load(1, bytes(disk))
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.count(), 105)
        self.assertEqual(self.name(104), b'HELLO'.ljust(30))

        self.fresh()
        overfull = bytearray(disk)
        off = 17 * 4096 + 256
        overfull[off + 1] = 18
        overfull[off + 2] = 0
        overfull[18 * 4096:18 * 4096 + 256] = bytes(256)
        overfull[18 * 4096 + 11:18 * 4096 + 46] = entry
        self.mini.load(1, bytes(overfull))
        self.assertEqual(self.mini.catalog(), CAT_BAD)
        self.assertEqual(self.count(), 0)

    def test_second_panel_is_independent(self):
        self.mini.poke('active', bytes([1]))
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.name(105), b'HELLO'.ljust(30))
        self.assertEqual(self.name(0), bytes(30), 'panel 0 untouched')


class ImageTest(unittest.TestCase):
    """The disk builder, which never touches a master or an output."""

    def setUp(self):
        master = bytearray(mkmini33.SIZE)
        master[0] = 1
        master[100:130] = bytes(c | 128 for c in b'HELLO'.ljust(30))
        master[17 * 4096 + 3] = 3
        master[17 * 4096 + 0x34:17 * 4096 + 0x38] = bytes([35, 16, 0, 1])
        self.master = bytes(master)
        self.image = mkmini33.build(self.master, b'\x60' * 2048)

    def test_hello_announces_the_load(self):
        self.assertIn(b'A2FILECMD', self.image)
        self.assertIn(b'MINI DOS 3.3', self.image)
        self.assertIn(b'V' + mkmini33.MINI_VERSION.encode('ascii'), self.image)
        self.assertNotIn(b'A2FILECMD MINI DOS 3.3', self.image)
        self.assertNotIn(b'A2FILECMD V' + mkmini33.MINI_VERSION.encode('ascii'), self.image)
        self.assertIn(b'GPL3 VERHILLE ARNAUD', self.image)
        self.assertIn(b'LOADING .... PLEASE WAIT ....', self.image)
        self.assertIn(b'BRUN A2FC.MINI', self.image)
        tiger = ROOT / 'data' / 'IMGHGR' / 'TIGER#062000'
        data = tiger.read_bytes()
        self.assertEqual(len(data), 8192)
        self.assertEqual(read_files(self.image)['TIGER']['data'], data)

    def test_image_structure_and_allocations(self):
        self.assertEqual(self.image[:3 * 4096], self.master[:3 * 4096])
        cat = self.image[17 * 4096 + 15 * 256:18 * 4096]
        allocated = set()
        for i in range(4):
            entry = cat[11 + i * 35:46 + i * 35]
            ts = tuple(entry[:2])
            total = 0
            while ts[0]:
                self.assertNotIn(ts, allocated)
                allocated.add(ts)
                total += 1
                off = (ts[0] * 16 + ts[1]) * 256
                table = self.image[off:off + 256]
                for j in range(122):
                    pair = tuple(table[12 + j * 2:14 + j * 2])
                    if pair == (0, 0):
                        break
                    self.assertNotIn(pair, allocated)
                    allocated.add(pair)
                    total += 1
                ts = tuple(table[1:3])
            self.assertEqual(total, struct.unpack_from('<H', entry, 33)[0])
        for t, s in allocated:
            off = 17 * 4096 + 0x38 + t * 4
            bits = int.from_bytes(self.image[off:off + 2], 'big')
            self.assertFalse(bits & (1 << s))

    def test_refuse_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'master').write_bytes(self.master)
            (d / 'binary').write_bytes(b'\x60')
            (d / 'disk').write_bytes(b'PRESERVE')
            p = subprocess.run(['python3', str(ROOT / 'tools/mkmini33.py'),
                                '--master', str(d / 'master'),
                                '--binary', str(d / 'binary'),
                                '--output', str(d / 'disk')], capture_output=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual((d / 'disk').read_bytes(), b'PRESERVE')
            self.assertEqual((d / 'master').read_bytes(), self.master)

    def test_bad_master_and_large_binary(self):
        for master, binary in ((b'', b'x'), (self.master, b'x' * 0x8601)):
            with self.assertRaises(ValueError):
                mkmini33.build(master, binary)


class LayoutTest(unittest.TestCase):
    """The shipped binary has to stay clear of DOS."""

    def test_build_fits_below_dos(self):
        subprocess.run(['make', 'mini'], cwd=ROOT, check=True,
                       capture_output=True)
        report = subprocess.run(['python3', str(ROOT / 'tools/check_mini_layout.py'),
                                 str(ROOT / 'build-mini/mini.map')],
                                capture_output=True, text=True, check=True)
        self.assertIn('bytes free below DOS', report.stdout)
        binary = (ROOT / 'build-mini/A2FC.MINI').read_bytes()
        self.assertGreater(len(binary), 1024)
        self.assertLessEqual(len(binary), 0x8600, 'mkmini33 refuses more')


if __name__ == '__main__':
    unittest.main()
