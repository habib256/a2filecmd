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

    def where(self, index):
        """The two spare bytes of a name stride: catalog track, then
        catalog sector << 3 | slot."""
        return bytes(self.mini.peek('ent_name', 2, offset=index * 32 + 30))

    def test_catalog_and_preview(self):
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.count(), 4)
        self.assertEqual(self.mini.byte('volume'), 254)
        self.assertEqual(self.name(0), b'HELLO'.ljust(30))
        self.assertEqual(self.name(1), b'A2FC'.ljust(30))
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

    def test_measure_text_refuses_a_full_area(self):
        # 32 sectors of text whose last byte is not a NUL cannot be held
        # with the NUL the editor keeps after the text: refuse, never cut.
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.mini.load_file(2), CAT_OK)
        self.mini.poke('load_count', bytes([32]))
        self.mini.poke('scratch', bytes([0x41]), offset=8191)
        self.assertEqual(self.mini.measure_text(), 1)
        self.mini.poke('scratch', bytes([0x41, 0]), offset=8190)
        self.assertEqual(self.mini.measure_text(), 0)
        self.assertEqual(self.mini.word('edit_len'), 8191)

    def test_load_file_sees_data_past_a_full_area(self):
        # The area is full after 32 sectors. A later pair after a hole, or
        # a next T/S list, is still the file: load_more must say so.
        base = make_disk([('BIG', 0, bytes([0xC1]) * (256 * 34)),
                          ('SMALL', 0, b'HELLO')])
        ts = offset(*read_files(base)['BIG']['lists'][0])
        img = bytearray(base)
        img[ts + 12 + 80:ts + 14 + 80] = base[ts + 12 + 66:ts + 14 + 66]
        img[ts + 12 + 64:ts + 12 + 68] = bytes(4)
        img[offset(17, 15) + 11 + 33] = 33
        self.mini.load(1, bytes(img))
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.mini.load_file(0), CAT_OK)
        self.assertEqual(self.mini.byte('load_count'), 32)
        self.assertEqual(self.mini.byte('load_more'), 1, 'a pair after a hole')

        base = make_disk([('BIG', 0, bytes([0xC1]) * (256 * 123))])
        ts = offset(*read_files(base)['BIG']['lists'][0])
        img = bytearray(base)
        img[ts + 12 + 64:ts + 12 + 244] = bytes(180)
        img[offset(17, 15) + 11 + 33] = 33
        self.fresh()
        self.mini.load(1, bytes(img))
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.mini.load_file(0), CAT_OK)
        self.assertEqual(self.mini.byte('load_count'), 32)
        self.assertEqual(self.mini.byte('load_more'), 1, 'another T/S list')

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
            self.assertEqual(self.where(i), bytes([17, (15 << 3) | i]))
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

    def test_copy_side_keeps_the_catalog_slot(self):
        # '=' and the boot copy of the right panel must include where each
        # entry was read. A name list without it is not an identity: writes
        # refuse rather than aim at catalog sector 0 (the VTOC).
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.mini.lock_prepare(2, 1), 0)
        self.assertEqual(self.mini.lock_execute(), 0)
        self.assertEqual(self.mini.catalog(), CAT_OK)
        slot0 = self.where(0)
        name0 = self.name(0)
        self.assertEqual(slot0, bytes([17, 15 << 3]))
        self.assertEqual(self.mini.byte('ent_type', 2) & 0x80, 0)
        self.mini.copy_side(0, 1)
        self.assertEqual(self.where(105), slot0)
        self.assertEqual(self.name(105), name0)
        self.assertEqual(self.name(0), name0, 'source panel untouched')
        self.mini.poke('active', bytes([1]))
        writes = self.mini.writes
        self.assertEqual(self.mini.delete_prepare(2), 0)
        self.assertEqual(self.mini.writes, writes)
        self.assertEqual(self.mini.image(1)[0:17 * 4096],
                         self.image[0:17 * 4096], 'data tracks unchanged')

    def test_names_without_slots_are_not_an_identity(self):
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.assertEqual(self.mini.lock_prepare(2, 1), 0)
        self.assertEqual(self.mini.lock_execute(), 0)
        self.assertEqual(self.mini.catalog(), CAT_OK)
        self.mini.copy_side(0, 1)
        self.mini.poke('ent_name', bytes([0, 0]), offset=(105 + 2) * 32 + 30)
        self.mini.poke('active', bytes([1]))
        writes = self.mini.writes
        self.assertEqual(self.mini.delete_prepare(2), 2)
        self.assertEqual(self.mini.writes, writes)

    def test_copy_side_same_panel_is_a_noop(self):
        self.assertEqual(self.mini.catalog(), CAT_OK)
        before = bytes(self.mini.peek('ent_name', 4 * 32))
        name0 = self.name(0)
        self.mini.copy_side(0, 0)
        self.assertEqual(bytes(self.mini.peek('ent_name', 4 * 32)), before)
        self.assertEqual(self.name(0), name0)


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
        self.assertIn(b'CAPS LOCK ON IS NEEDED', self.image)
        self.assertIn(b'"BRUN A2FC"', self.image)
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


class HexPreviewTest(unittest.TestCase):
    """The hex preview's rows, drawn by the shipped screen.s into the
    composed image: offset, eight bytes, their characters."""

    @classmethod
    def setUpClass(cls):
        cls.harness = mini_host.Harness()

    @classmethod
    def tearDownClass(cls):
        cls.harness.cleanup()

    def setUp(self):
        self.mini = self.harness.start()

    def tearDown(self):
        self.mini.close()

    @staticmethod
    def shown(b):
        c = b & 0x7F
        if c < 32 or c == 127:
            return '.'
        return chr(c).upper()   # put folds lower case: the II+ has none

    def expected(self, sector, half):
        rows = [' ' * 40] * 24
        rows[1] = (' ' * 21 + f', BYTES {half:02X}-{half | 0x7F:02X}').ljust(40)
        for r in range(16):
            first = half + r * 8
            data = sector[first:first + 8]
            line = (f'{first:02X}:' + ''.join(f' {b:02X}' for b in data) +
                    ' ' + ''.join(self.shown(b) for b in data))
            rows[3 + r] = line.ljust(40)
        return rows

    def check(self, sector):
        self.mini.poke('buffer', sector)
        for half in (0x00, 0x80):
            with self.subTest(half=half):
                rows, marks = self.mini.hex_rows(half)
                self.assertEqual(rows, self.expected(sector, half))
                self.assertEqual(marks, [' ' * 40] * 24, 'no inverse cell')
                self.assertEqual(bytes(self.mini.peek('buffer', 256)), sector,
                                 'the preview only reads the sector')

    def test_known_sector(self):
        head = bytes(c | 0x80 for c in b'A2FC MINI DOS 3.3')  # DOS text
        sector = bytearray(range(256))
        sector[0:len(head)] = head
        sector[0x20:0x28] = bytes([0x00, 0x0D, 0x8D, 0x1F, 0x9F, 0x7F, 0xFF, 0xA0])
        sector[0x28:0x30] = b'abc{|}~`'
        sector[0x88:0x90] = bytes([0xC1, 0x41, 0x80, 0x20, 0xFE, 0xDF, 0x60, 0xE0])
        self.check(bytes(sector))
        rows, _ = self.mini.hex_rows(0)
        self.assertEqual(rows[3], '00: C1 B2 C6 C3 A0 CD C9 CE A2FC MIN    ')
        self.assertEqual(rows[7], '20: 00 0D 8D 1F 9F 7F FF A0 ....... '.ljust(40),
                         'controls, $7F and $FF are dots; $A0 a space')
        self.assertEqual(rows[1].rstrip(), ' ' * 21 + ', BYTES 00-7F')
        rows, _ = self.mini.hex_rows(0x80)
        self.assertEqual(rows[1].rstrip(), ' ' * 21 + ', BYTES 80-FF')
        self.assertEqual(rows[3][:3], '80:')
        self.assertEqual(rows[4], '88: C1 41 80 20 FE DF 60 E0 AA. ~_``    ')
        self.assertEqual(rows[18][:3], 'F8:')
        self.assertTrue(all(len(r) == 40 for r in rows))
        self.assertLessEqual(max(len(r.rstrip()) for r in rows), 36,
                             'a row never reaches the 40th column')

    def test_every_byte_value(self):
        self.check(bytes(range(256)))
        self.check(bytes(255 - i for i in range(256)))
        self.check(bytes(256))

    def test_print_row_escape(self):
        rows, marks = self.mini.print_rows()
        self.assertEqual(rows[0].rstrip(), '     AB')
        self.assertEqual(rows[2].rstrip(), 'CD')
        self.assertEqual(rows[4].rstrip(), 'EF')
        self.assertEqual(marks[0].rstrip(), '')
        self.assertEqual(marks[2].rstrip(), '')
        self.assertEqual(marks[4].rstrip(), ' #', 'the ~ escape still flips inverse')
        self.assertEqual(rows[1].strip() + rows[3].strip(), '')


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
