#!/usr/bin/env python3
"""F, the format: the real format.s under sim65, with the disks over here.

What is asserted is the bytes. The boot disk is never written. Every
refusal leaves the target untouched. After a success, tracks 0-2 equal
the boot disk's, track 17 is what DOS 3.3's own INIT leaves before it
saves HELLO (checked against INIT in POM2), the VTOC written last, and
a copy then lands on the fresh disk without touching DOS.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mini_host
from mini33_fixture import make_disk, read_files, offset, SIZE

(FMT_OK, FMT_PROTECTED, FMT_UNCERTAIN, FMT_FAILED, FMT_SRC_LATE,
 FMT_SRC_READ, FMT_NO_DOS, FMT_SAME) = range(8)
COPY_OK, COPY_UNCERTAIN = 0, 8
DEL_UNCERTAIN = 5

# The first bytes of a DOS 3.3 boot sector, as on the shipped disk.
SIG = bytes([0x01, 0xA5, 0x27, 0xC9, 0x09])
DOS_SECTORS = [(t, s) for t in range(3) for s in range(16)]
# The order they are read and written in: each batch from its last sector
# down, the order DOS 3.3's 2:1 skew reads without a lost turn.
DOS_ORDER = [(t, s) for t in (1, 0, 2) for s in range(15, -1, -1)]
CATALOG_SECTORS = [(17, s) for s in range(15, -1, -1)]
FORMAT = 'FORMAT'


def sector(disk, t, s):
    o = offset(t, s)
    return bytes(disk[o:o + 256])


def with_dos(image, seed=0):
    """Tracks 0-2 filled sector by sector, each one distinct, the boot
    signature first. Only the bytes matter to the format, not that they
    are a DOS."""
    disk = bytearray(image)
    for t, s in DOS_SECTORS:
        o = offset(t, s)
        disk[o:o + 256] = bytes((seed + t * 16 + s + i) & 255 for i in range(256))
    disk[0:5] = SIG
    return bytes(disk)


def init_track():
    """Track 17 as INIT leaves it: 15 empty catalog sectors chained
    downward, the VTOC with tracks 0-2 and 17 reserved."""
    sectors = {}
    for s in range(15, 0, -1):
        c = bytearray(256)
        if s > 1:
            c[1], c[2] = 17, s - 1      # sector 1 ends the chain with 0,0
        sectors[s] = bytes(c)
    v = bytearray(256)
    v[1:4] = bytes([17, 15, 3])
    v[6] = 254
    v[0x27] = 122
    v[0x30], v[0x31] = 17, 1
    v[0x34:0x38] = bytes([35, 16, 0, 1])
    for t in range(3, 35):
        if t != 17:
            v[0x38 + 4 * t:0x3a + 4 * t] = b'\xff\xff'
    sectors[0] = bytes(v)
    return sectors


class FormatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = mini_host.Harness()

    @classmethod
    def tearDownClass(cls):
        cls.harness.cleanup()

    def setUp(self):
        self.mini = None
        self.load()

    def tearDown(self):
        if self.mini is not None:
            self.mini.close()

    def load(self, boot=None, target=None):
        if self.mini is not None:
            self.mini.close()
        self.mini = self.harness.start()
        self.boot = boot if boot is not None else with_dos(make_disk(
            [('HELLO', 2, b'\x10\x00' + bytes(range(16))),
             ('A2FC', 4, bytes(range(256)) * 5 + b'END'),
             ('README', 0, b'READ ME')]))
        self.target = target if target is not None else with_dos(make_disk(
            [('OLD', 0, b'GONE AFTER FORMAT'),
             ('KEEP', 4, bytes(range(256)) * 3)]), seed=0x77)
        self.mini.load(1, self.boot)
        self.mini.load(2, self.target)
        self.mini.poke('boot_drive', bytes([1]))
        self.mini.poke('drive', bytes([2]))
        self.mini.poke('active', bytes([1]))
        self.mini.reset_faults()

    def image(self, drive):
        return self.mini.image(drive)

    def untouched(self, status):
        """A refusal: nothing written anywhere, no latch, drive put back."""
        self.assertEqual(self.mini.format(), status)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(1), self.boot)
        self.assertEqual(self.image(2), self.target)
        self.assertEqual(self.mini.byte('del_fault'), 0)
        self.assertEqual(self.mini.byte('drive'), 2)

    def formatted(self):
        """The fresh disk, byte for byte."""
        disk = self.image(2)
        self.assertEqual(self.image(1), self.boot, 'the boot disk is read-only')
        for t, s in DOS_SECTORS:
            self.assertEqual(sector(disk, t, s), sector(self.boot, t, s), (t, s))
        for s, expected in init_track().items():
            self.assertEqual(sector(disk, 17, s), expected, s)
        for t in range(3, 35):
            if t != 17:
                for s in range(16):
                    self.assertEqual(sector(disk, t, s), bytes(256), (t, s))
        self.assertEqual(read_files(disk), {})
        self.assertEqual(self.mini.byte('drive'), 2)
        self.assertEqual(self.mini.byte('del_fault'), 0)

    # Writes on a run that formats: 0 the target's VTOC sector written
    # back as read (RWTS senses the tab there), then the format, 1-48
    # DOS, 49-63 the catalog, 64 the VTOC. Reads: 0-47 the boot disk
    # before the format, 48 the target's VTOC sector, 49-80 tracks 0-1
    # again, 81-112 those 32 sectors read back from the target, 113-128
    # track 2, 129-144 read back, 145-159 the 15 catalog sectors read
    # back as one batch, 160 the VTOC read back by itself.
    SENSE = (2, 17, 0)
    SOURCE_LATE = list(range(49, 81)) + list(range(113, 129))
    # Read-backs of a batch go odd indices first, then even; the index
    # here is any write of that batch, since detection closes the batch.
    READ_BACK = {81 + i: 1 + i for i in range(32)}
    READ_BACK.update({129 + i: 33 + i for i in range(16)})
    READ_BACK.update({145 + i: 49 + i for i in range(15)})
    READ_BACK[160] = 64             # the VTOC, written and read back alone

    # ---- the ordinary path ----------------------------------------
    def test_format_writes_dos_then_catalog_then_vtoc(self):
        self.assertEqual(self.mini.format(), FMT_OK)
        self.formatted()
        log = self.mini.write_log
        # Every DOS sector is read once before the disk is erased.
        self.assertEqual(log[0], self.SENSE)
        self.assertEqual(log[1], (2, FORMAT, 49))
        self.assertEqual(log[2:50], [(2, t, s) for t, s in DOS_ORDER])
        self.assertEqual(log[50:], [(2, t, s) for t, s in CATALOG_SECTORS])
        self.assertEqual(log[-1], (2, 17, 0), 'the VTOC is written last')
        self.assertEqual(len(log), 66)
        self.assertEqual(self.mini.reads, 48 + 1 + 48 + 64, 'every write read back')

    def test_sense_writes_the_vtoc_sector_back_as_it_was(self):
        # The one write before the format: the target's VTOC sector, byte
        # for byte what was read. A format that then fails leaves it so.
        self.mini.fail_format = 0
        self.assertEqual(self.mini.format(), FMT_FAILED)
        self.assertEqual(self.mini.write_log, [self.SENSE, (2, FORMAT, 49)])

    def test_batches_do_not_alternate_drives(self):
        # Tracks 0-1 are read in one go, then written; then track 2. The
        # order of the log shows it, and the read count says no sector
        # was fetched twice within a pass.
        self.assertEqual(self.mini.format(), FMT_OK)
        log = [w for w in self.mini.write_log if w[1] != FORMAT][1:]
        self.assertEqual([w[1] for w in log[:32]], [1] * 16 + [0] * 16)
        self.assertEqual([w[1] for w in log[32:48]], [2] * 16)
        self.assertEqual([w[2] for w in log[:16]], list(range(15, -1, -1)))

    def test_the_catalog_is_one_batch_written_before_the_vtoc(self):
        # The 15 catalog sectors go down in one run, 15 to 1, and only
        # then are read back: the first read-back has all 15 writes
        # behind it, and a failure there leaves the disk without a VTOC.
        self.mini.fail_read = 145
        self.assertEqual(self.mini.format(), FMT_UNCERTAIN)
        writes = [w for w in self.mini.write_log if w[1] != FORMAT]
        self.assertEqual(len(writes), 64)
        self.assertEqual(writes[49:], [(2, 17, s) for s in range(15, 0, -1)])
        self.assertNotIn((2, 17, 0), writes[1:], 'no VTOC behind a bad catalog')
        self.assertNotEqual(sector(self.image(2), 17, 0)[3], 3)

    def test_fresh_disk_takes_a_copy_off_dos_tracks(self):
        self.assertEqual(self.mini.format(), FMT_OK)
        self.mini.poke('drive', bytes([1]))
        self.mini.poke('active', bytes([0]))
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(self.mini.prepare(1, 2), COPY_OK)      # A2FC
        self.assertEqual(self.mini.execute(), COPY_OK)
        files = read_files(self.image(2))
        self.assertEqual(files['A2FC']['data'], read_files(self.boot)['A2FC']['data'])
        for t, s in files['A2FC']['blocks'] + files['A2FC']['lists']:
            self.assertGreaterEqual(t, 3)
            self.assertNotEqual(t, 17)
        for t, s in DOS_SECTORS:
            self.assertEqual(sector(self.image(2), t, s), sector(self.boot, t, s))
        self.mini.poke('drive', bytes([2]))
        self.mini.poke('active', bytes([1]))
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(self.mini.byte('count'), 1)
        self.assertEqual(self.mini.byte('volume'), 254)

    def test_format_twice(self):
        self.assertEqual(self.mini.format(), FMT_OK)
        self.assertEqual(self.mini.format(), FMT_OK)
        self.formatted()

    def test_blank_target_cannot_be_sensed_and_is_formatted(self):
        # A blank disk has no readable VTOC sector: no write-back, the
        # format goes ahead. Its read failure, or a refused, torn or
        # changed write-back, is not a reason to stop: RWTS's own
        # error codes decide, and only $10 means protected.
        for attr, n in (('fail_read', 48), ('fail_write', 0), ('partial_write', 0),
                        ('corrupt_write', 0)):
            self.load()
            setattr(self.mini, attr, n)
            self.assertEqual(self.mini.format(), FMT_OK, (attr, n))
            self.formatted()

    # ---- refusals before any write --------------------------------
    def test_boot_drive_refused(self):
        self.mini.poke('drive', bytes([1]))
        self.assertEqual(self.mini.format(), FMT_SAME)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(1), self.boot)
        self.assertEqual(self.mini.byte('drive'), 1)

    def test_write_protection(self):
        # Sensed on the write-back, before RWTS FORMAT is ever asked.
        self.mini.protected_drive = 2
        self.assertEqual(self.mini.format(), FMT_PROTECTED)
        self.assertEqual(self.mini.write_log, [self.SENSE])
        self.assertEqual(self.image(2), self.target)
        self.assertEqual(self.image(1), self.boot)
        self.assertEqual(self.mini.byte('del_fault'), 0)
        self.assertEqual(self.mini.byte('drive'), 2)
        # A protected blank disk cannot be sensed: RWTS's INIT fails on
        # it without saying why, and the disk is untouched.
        self.load()
        self.mini.protected_drive = 2
        self.mini.fail_read = 48
        self.assertEqual(self.mini.format(), FMT_FAILED)
        self.assertEqual(self.mini.write_log, [(2, FORMAT, 49)])
        self.assertEqual(self.image(2), self.target)
        self.assertEqual(self.mini.byte('del_fault'), 0)

    def test_no_dos_on_the_boot_disk(self):
        for boot in (make_disk([('PLAIN', 0, b'NO DOS HERE')], dosless=True),
                     with_dos(make_disk([]))[:4] + b'\x00' + with_dos(make_disk([]))[5:]):
            self.load(boot=boot)
            self.untouched(FMT_NO_DOS)

    def test_every_read_failure_before_the_format(self):
        for n in range(48):
            self.load()
            self.mini.fail_read = n
            self.untouched(FMT_SRC_READ)
            self.assertEqual(self.mini.reads, n + 1, 'the first failure stops the pass')

    def test_latched_fault_blocks_format(self):
        self.mini.poke('del_fault', bytes([1]))
        self.assertEqual(self.mini.format(), FMT_UNCERTAIN)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(2), self.target)
        self.assertEqual(self.mini.reads, 0)

    # ---- failures after the disk is erased ------------------------
    def test_format_failure_stops_everything(self):
        self.mini.fail_format = 0
        self.assertEqual(self.mini.format(), FMT_FAILED)
        self.assertEqual(self.mini.write_log, [self.SENSE, (2, FORMAT, 49)])
        self.assertEqual(self.image(1), self.boot)
        self.assertNotEqual(sector(self.image(2), 17, 0)[3], 3, 'no VTOC claims the disk is good')
        self.assertEqual(self.mini.byte('del_fault'), 0, 'a reported failure is certain')
        self.assertEqual(self.mini.byte('drive'), 2)

    def test_every_read_failure_after_the_format(self):
        # The boot disk failing, or swapped, on the second pass leaves
        # the target erased, without DOS or VTOC: certain, not latched.
        for n in self.SOURCE_LATE:
            self.load()
            self.mini.fail_read = n
            self.assertEqual(self.mini.format(), FMT_SRC_LATE, n)
            self.assertEqual(self.image(1), self.boot)
            self.assertNotEqual(sector(self.image(2), 17, 0)[3], 3)
            self.assertNotIn((2, 17, 0), self.mini.write_log[1:])
            self.assertEqual(self.mini.byte('del_fault'), 0)
            self.assertEqual(self.mini.byte('drive'), 2)

    @staticmethod
    def batch_end(w):
        # DOS writes 1-32 and 33-48 and catalog writes 49-63 are read
        # back after their batch: a silent bad write is caught then,
        # with the batch complete. Write 64, the VTOC, is read back on
        # its own, after the whole catalog.
        if w <= 32:
            return 32
        if w <= 48:
            return 48
        if w <= 63:
            return 63
        return w

    def test_every_write_failure_torn_write_corruption_and_readback(self):
        # 64 target writes after the format: a refused or torn write
        # stops the run at once; a silently changed one, or one that
        # does not read back, at its batch's read-back. The latch is set
        # either way and nothing is written after the detection; the
        # VTOC is never written unless it was the failing sector itself,
        # since the whole catalog is read back before it goes down.
        cases = [(attr, n) for attr in ('fail_write', 'partial_write',
                                        'corrupt_write', 'protect_write')
                 for n in range(1, 65)]
        cases += [('fail_read', r) for r in sorted(self.READ_BACK)]
        for attr, n in cases:
            self.load()
            setattr(self.mini, attr, n)
            if attr == 'fail_read':
                w = self.batch_end(self.READ_BACK[n])
            elif attr == 'corrupt_write':
                w = self.batch_end(n)
            else:
                w = n
            if attr == 'protect_write' and n == 64:
                # The VTOC alone goes through put_verified, which reports a
                # refusal before writing as itself: the disk is erased
                # already, so it is a failure, not an uncertain write.
                self.assertEqual(self.mini.format(), FMT_FAILED, (attr, n))
                self.assertEqual(self.mini.byte('del_fault'), 0)
                self.assertNotEqual(sector(self.image(2), 17, 0)[3], 3)
                continue
            self.assertEqual(self.mini.format(), FMT_UNCERTAIN, (attr, n))
            writes = [x for x in self.mini.write_log if x[1] != FORMAT]
            self.assertEqual(len(writes), w + 1, (attr, n))
            self.assertEqual(self.mini.byte('del_fault'), 1, (attr, n))
            self.assertEqual(self.image(1), self.boot)
            self.assertEqual(self.mini.byte('drive'), 2)
            if w < 64:
                self.assertNotEqual(sector(self.image(2), 17, 0)[3], 3, (attr, n))
            # latched: another format refuses without touching a disk
            before = len(self.mini.write_log)
            self.assertEqual(self.mini.format(), FMT_UNCERTAIN)
            self.assertEqual(len(self.mini.write_log), before)

    def test_uncertain_format_blocks_copy_and_delete(self):
        self.mini.fail_write = 11
        self.assertEqual(self.mini.format(), FMT_UNCERTAIN)
        writes = len(self.mini.write_log)
        self.mini.poke('drive', bytes([1]))
        self.mini.poke('active', bytes([0]))
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(self.mini.prepare(1, 2), COPY_UNCERTAIN)
        self.assertEqual(self.mini.delete_prepare(2), DEL_UNCERTAIN)
        self.assertEqual(self.mini.delete_execute(), DEL_UNCERTAIN)
        self.assertEqual(len(self.mini.write_log), writes)
        self.assertEqual(self.image(1), self.boot)

    def test_uncertain_copy_blocks_format(self):
        self.mini.poke('drive', bytes([1]))
        self.mini.poke('active', bytes([0]))
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(self.mini.prepare(1, 2), COPY_OK)
        self.mini.fail_write = 1
        self.assertEqual(self.mini.execute(), COPY_UNCERTAIN)
        after = self.image(2)
        writes = len(self.mini.write_log)
        self.mini.poke('drive', bytes([2]))
        self.assertEqual(self.mini.format(), FMT_UNCERTAIN)
        self.assertEqual(len(self.mini.write_log), writes)
        self.assertEqual(self.image(2), after)


if __name__ == '__main__':
    unittest.main()
