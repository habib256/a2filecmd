#!/usr/bin/env python3
"""The real 6502 copy engine, with every read and write made to fail.

Runs the shipped copy.s under sim65 on disposable fixtures only. What is
checked is not the return code but the bytes: the source must come out
untouched, every pre-existing byte of the target must survive, and no
catalog entry may appear unless the whole file is on the disk and has
been compared.
"""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mini_host
from mini33_fixture import make_disk, read_files, offset, SIZE

(OK, READ, INVALID, EXISTS, FULL, SAME, PROTECTED, CHANGED, UNCERTAIN,
 NOT_READY) = range(10)


class WriteTest(unittest.TestCase):
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

    def load(self, src=None, dst=None):
        if self.mini is not None:
            self.mini.close()
        self.mini = self.harness.start()
        self.src = src if src is not None else make_disk(
            [('COPY.ME', 0x84, bytes(range(256)) * 3 + b'END'),
             ('KEEP.SRC', 0, b'SOURCE SAFE')])
        self.dst = dst if dst is not None else make_disk(
            [('KEEP.DST', 0x80, b'DESTINATION SAFE')])
        self.mini.load(1, self.src)
        self.mini.load(2, self.dst)
        self.mini.poke('drive', bytes([1]))
        self.mini.poke('active', bytes([0]))
        self.assertEqual(self.mini.catalog(), 0)
        self.mini.reset_faults()

    def prepare(self):
        return self.mini.prepare(0, 2)

    def image(self, drive):
        return self.mini.image(drive)

    def copied(self):
        before = read_files(self.src)
        result = read_files(self.image(2))
        self.assertEqual(result['COPY.ME']['data'], before['COPY.ME']['data'])
        self.assertEqual(result['COPY.ME']['type'], before['COPY.ME']['type'])
        self.preserved()

    def preserved(self):
        self.assertEqual(self.image(1), self.src, 'the source is read-only')
        # Every byte of pre-existing data and T/S sectors, and every
        # catalog record, including its lock bit and sector count.
        for f in read_files(self.dst).values():
            for t, s in f['blocks'] + f['lists']:
                a = offset(t, s)
                self.assertEqual(self.image(2)[a:a + 256], self.dst[a:a + 256])
        for s in range(1, 16):
            for i in range(7):
                a = offset(17, s) + 11 + i * 35
                if self.dst[a] not in (0, 255):
                    self.assertEqual(self.image(2)[a:a + 35], self.dst[a:a + 35])
        for drive, _, _ in self.mini.write_log:
            self.assertEqual(drive, 2, 'nothing may be written to the source')

    # ---- the ordinary path ----------------------------------------
    def test_success_and_replay(self):
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(len(self.mini.write_log), 0, 'checking writes nothing')
        self.assertEqual(self.mini.execute(), OK)
        self.assertEqual(self.mini.word('copy_done'), self.mini.word('copy_total'))
        self.copied()
        self.assertEqual(self.mini.execute(), NOT_READY,
                         'one confirmation, one copy')

    def test_second_file_after_a_success(self):
        # A batch is the UI looping this: one plan, one write, then another
        # file on the same destination. ready must not stay latched.
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.execute(), OK)
        self.mini.poke('drive', bytes([1]))
        self.assertEqual(self.mini.prepare(1, 2), OK)
        self.assertEqual(self.mini.execute(), OK)
        files = read_files(self.image(2))
        self.assertIn('COPY.ME', files)
        self.assertIn('KEEP.SRC', files)
        self.preserved()

    def test_vtoc_is_reserved_before_any_data(self):
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.execute(), OK)
        first = self.mini.write_log[0]
        self.assertEqual(first, (2, 17, 0), 'the reservation goes down first')
        published = [w for w in self.mini.write_log if w[1] == 17 and w[2] != 0]
        self.assertEqual(len(published), 1)
        self.assertEqual(self.mini.write_log[-1], published[0],
                         'the catalog entry is the last write')

    def test_batches_do_not_alternate_drives(self):
        # The point of the batching: a change of drive costs a seek and a
        # motor, so they are counted here to keep the pattern from
        # regressing to one per sector.
        self.load(src=make_disk([('COPY.ME', 0, bytes(range(256)) * 40)]),
                  dst=make_disk([]))
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.execute(), OK)
        self.copied()
        switches = 0
        current = None
        for drive, _, _ in self.mini.write_log:
            if drive != current:
                switches += 1
                current = drive
        self.assertLessEqual(switches, 4, 'writes should stay on one drive')

    def test_cancellation_and_same_drive(self):
        self.assertEqual(self.prepare(), OK)
        self.mini.cancel()
        self.assertEqual(self.mini.execute(), NOT_READY)
        self.assertEqual(self.image(2), self.dst)
        self.mini.poke('drive', bytes([1]))
        self.assertEqual(self.mini.prepare(0, 1), SAME)
        self.assertEqual(len(self.mini.write_log), 0)

    def test_name_collision_even_locked(self):
        self.load(dst=make_disk([('COPY.ME', 0x84, b'NEVER OVERWRITE')]))
        self.assertEqual(self.prepare(), EXISTS)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.image(2), self.dst)

    def test_full_disk_and_catalog(self):
        d = bytearray(self.dst)
        a = offset(17, 0) + 0x38
        d[a:a + 140] = bytes(140)
        self.load(dst=bytes(d))
        self.assertEqual(self.prepare(), FULL)
        self.assertEqual(len(self.mini.write_log), 0)

        self.load(dst=make_disk([(f'F{i}', 0, b'') for i in range(105)]))
        self.assertEqual(self.prepare(), FULL)
        self.assertEqual(len(self.mini.write_log), 0)

    def test_stale_panel_size_and_pointer(self):
        # The walk uses the panel's size and T/S pointer. A stale
        # snapshot is refused; the rest of the disk is not audited.
        self.mini.poke('ent_seclo', bytes([1]))
        self.mini.poke('ent_sechi', bytes([0]))
        self.mini.poke('ent_track', bytes([34]))
        self.mini.poke('ent_sector', bytes([15]))
        self.assertEqual(self.prepare(), INVALID)
        self.assertEqual(len(self.mini.write_log), 0)

    def test_multiple_ts_lists_and_empty(self):
        for n in (0, 122, 123, 245, 491):
            with self.subTest(sectors=n):
                self.load(src=make_disk([('COPY.ME', 0, bytes(range(256)) * n)]),
                          dst=make_disk([]))
                self.assertEqual(self.prepare(), OK, n)
                self.assertEqual(self.mini.execute(), OK, n)
                self.copied()

    def test_bad_source_graph_refused_without_writes(self):
        # Only the file being copied is walked. Destination T/S chains
        # are not audited.
        f = next(iter(read_files(self.src).values()))
        ts = offset(*f['lists'][0])
        dt, ds = f['blocks'][0]
        variants = []
        d = bytearray(self.src)        # a list that points at itself
        d[ts + 1:ts + 3] = bytes(f['lists'][0])
        variants.append(d)
        d = bytearray(self.src)        # a data sector off the disk
        d[ts + 12] = 35
        variants.append(d)
        d = bytearray(self.src)        # the same sector twice
        d[ts + 14:ts + 16] = d[ts + 12:ts + 14]
        variants.append(d)
        d = bytearray(self.src)        # a live sector marked free
        d[offset(17, 0) + 0x38 + dt * 4 + (ds < 8)] |= 1 << (ds & 7)
        variants.append(d)
        d = bytearray(self.src)        # a wrong offset in the list
        d[ts + 5] = 122
        variants.append(d)
        d = bytearray(self.src)        # a wrong sector count
        d[offset(17, 15) + 11 + 33] = 99
        variants.append(d)
        for n, d in enumerate(variants):
            with self.subTest(variant=n):
                self.load(src=bytes(d))
                self.assertNotEqual(self.prepare(), OK)
                self.assertEqual(len(self.mini.write_log), 0)

    def test_late_collision_other_catalog_sector(self):
        self.assertEqual(self.prepare(), OK)
        # A name that appears in another catalog sector after prepare is
        # not seen again. The reserved slot is still free, so the copy
        # publishes and two entries can share the name.
        a = offset(17, 14) + 11
        entry = self.src[offset(17, 15) + 11:offset(17, 15) + 46]
        self.mini.disks[1][a:a + 35] = entry
        self.assertEqual(self.mini.execute(), OK)
        self.assertGreater(len(self.mini.write_log), 0)
        self.preserved()

    def test_metadata_changed_during_confirmation(self):
        # Disks are not re-audited after the prompt. A flipped volume
        # byte or catalog header no longer refuses the copy.
        for side, at in ((1, offset(17, 0) + 6), (1, offset(17, 15) + 11 + 2),
                         (2, offset(17, 0) + 6), (2, offset(17, 15) + 10)):
            with self.subTest(side=side, at=at):
                self.load()
                self.assertEqual(self.prepare(), OK)
                self.mini.disks[side - 1][at] ^= 1
                self.assertEqual(self.mini.execute(), OK)
                self.assertGreater(len(self.mini.write_log), 0)

    def test_write_protection(self):
        self.assertEqual(self.prepare(), OK)
        self.mini.protected_drive = 2
        self.assertEqual(self.mini.execute(), PROTECTED)
        self.assertEqual(self.image(2), self.dst)
        self.assertEqual(self.mini.byte('copy_fault'), 0,
                         'a refused disk is not an uncertain one')

    def test_every_read_failure(self):
        self.assertEqual(self.prepare(), OK)
        plan_reads = self.mini.reads
        self.assertEqual(self.mini.execute(), OK)
        all_reads = self.mini.reads
        for n in range(all_reads):
            with self.subTest(read=n):
                self.load()
                self.mini.fail_read = n
                r = self.prepare()
                if r == OK:
                    r = self.mini.execute()
                self.assertNotEqual(r, OK)
                self.preserved()
                if n < plan_reads:
                    self.assertEqual(self.image(2), self.dst,
                                     'no write before the plan is complete')
                if self.mini.byte('copy_fault'):
                    writes = len(self.mini.write_log)
                    self.mini.poke('drive', bytes([1]))
                    self.assertEqual(self.prepare(), UNCERTAIN)
                    self.assertEqual(len(self.mini.write_log), writes,
                                     'a latched fault writes no more')

    def test_every_write_failure_torn_write_and_corruption(self):
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.execute(), OK)
        writes = len(self.mini.write_log)
        source = read_files(self.src)['COPY.ME']['data']
        for mode in ('fail_write', 'partial_write', 'corrupt_write'):
            for n in range(writes):
                with self.subTest(mode=mode, write=n):
                    self.load()
                    self.assertEqual(self.prepare(), OK)
                    setattr(self.mini, mode, n)
                    self.assertEqual(self.mini.execute(), UNCERTAIN)
                    self.assertEqual(self.mini.byte('copy_fault'), 1)
                    self.preserved()
                    # read_files itself refuses a broken allocation graph:
                    # shared sectors, a wrong count, a bitmap that
                    # disagrees. The entry may only appear if the failure
                    # was the very last write, the one publishing it, and
                    # then the file it names must still be the right bytes.
                    files = read_files(self.image(2))
                    if 'COPY.ME' in files:
                        self.assertEqual(n, writes - 1,
                                         'published before the copy was whole')
                        self.assertEqual(files['COPY.ME']['data'], source)
                    self.assertLessEqual(len(self.mini.write_log), writes)

    def test_fragmented_destination(self):
        d = bytearray(make_disk([(f'F{i}', 0, b'KEEP' + bytes([i]))
                                 for i in range(30)]))
        files = read_files(d)
        for i in range(0, 30, 2):
            for t, sec in files[f'F{i}']['blocks'] + files[f'F{i}']['lists']:
                d[offset(17, 0) + 0x38 + t * 4 + (sec < 8)] |= 1 << (sec & 7)
            d[offset(17, 15 - i // 7) + 11 + (i % 7) * 35] = 255
        self.load(src=make_disk([('COPY.ME', 0, bytes(range(256)) * 123)]),
                  dst=bytes(d))
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.execute(), OK)
        self.copied()

    def test_deleted_slot_reused(self):
        d = bytearray(self.dst)
        d[offset(17, 15) + 11] = 255
        self.load(dst=bytes(d))
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.execute(), OK)
        self.copied()

    def test_source_file_must_still_be_there(self):
        self.assertEqual(self.prepare(), OK)
        # The catalog entry can vanish after prepare; the mapped sectors
        # are still read. The copy is not refused.
        a = offset(17, 15) + 11
        self.mini.disks[0][a] = 255
        self.assertEqual(self.mini.execute(), OK)
        before = read_files(self.src)
        result = read_files(self.image(2))
        self.assertEqual(result['COPY.ME']['data'], before['COPY.ME']['data'])
        for f in read_files(self.dst).values():
            for t, s in f['blocks'] + f['lists']:
                a = offset(t, s)
                self.assertEqual(self.image(2)[a:a + 256], self.dst[a:a + 256])
        for drive, _, _ in self.mini.write_log:
            self.assertEqual(drive, 2, 'nothing may be written to the source')

    # ---- exclusive create from RAM --------------------------------
    def create(self, name='NEW.TXT', data=b'HELLO FROM RAM', kind=0):
        self.mini.poke('cs_name', name.encode('ascii').ljust(30))
        self.mini.poke('cs_type', bytes([kind]))
        sectors = max(1, (len(data) + 255) // 256)
        payload = data.ljust(sectors * 256, b'\x00')
        self.mini.poke('data_count', bytes([sectors, 0]))
        self.mini.poke('scratch', payload)
        self.mini.poke('drive', bytes([2]))
        return self.mini.create_prepare()

    def test_create_exclusive_and_collision(self):
        self.assertEqual(self.create(), OK)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.mini.create_execute(), OK)
        files = read_files(self.image(2))
        self.assertEqual(files['NEW.TXT']['data'].rstrip(b'\x00'), b'HELLO FROM RAM')
        self.assertEqual(files['NEW.TXT']['type'], 0)
        self.preserved()
        writes = len(self.mini.write_log)
        self.mini.poke('drive', bytes([2]))
        self.assertEqual(self.create(), EXISTS)
        self.assertEqual(len(self.mini.write_log), writes)

    def test_create_write_failure_does_not_publish(self):
        self.assertEqual(self.create(), OK)
        self.mini.fail_write = 0
        self.assertEqual(self.mini.create_execute(), UNCERTAIN)
        self.assertEqual(self.mini.byte('copy_fault'), 1)
        files = read_files(self.image(2))
        self.assertNotIn('NEW.TXT', files)
        self.preserved()

    # ---- delete: catalog first, then free -------------------------
    DEL_OK, DEL_READ, DEL_INVALID, DEL_LOCKED, DEL_CHANGED, DEL_UNCERTAIN = range(6)

    def test_delete_marks_catalog_then_frees(self):
        self.load(src=make_disk([('GONE.TXT', 0, b'DELETE ME'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        before = read_files(self.src)
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.mini.delete_execute(), self.DEL_OK)
        files = read_files(self.image(1))
        self.assertNotIn('GONE.TXT', files)
        self.assertEqual(files['KEEP.SRC']['data'], before['KEEP.SRC']['data'])
        first = self.mini.write_log[0]
        self.assertEqual(first[1], 17)
        self.assertNotEqual(first[2], 0, 'the catalog is marked before the VTOC')
        self.assertEqual(self.mini.write_log[-1], (1, 17, 0),
                         'the VTOC is freed last')
        # DOS UNDELETE mark: track $FF, original track in the first name byte
        a = offset(17, 15) + 11
        self.assertEqual(self.image(1)[a], 255)

    def test_delete_refuses_locked(self):
        self.load(src=make_disk([('LOCK.ME', 0x80, b'SAFE')]))
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_LOCKED)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.image(1), self.src)

    def test_delete_write_failure_latches(self):
        self.load(src=make_disk([('GONE.TXT', 0, b'DELETE ME'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        self.mini.fail_write = 0
        self.assertEqual(self.mini.delete_execute(), self.DEL_UNCERTAIN)
        self.assertEqual(self.mini.byte('del_fault'), 1)
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_UNCERTAIN)
        # KEEP.SRC data sectors are untouched
        keep = read_files(self.src)['KEEP.SRC']
        for t, s in keep['blocks'] + keep['lists']:
            a = offset(t, s)
            self.assertEqual(self.image(1)[a:a + 256], self.src[a:a + 256])


if __name__ == '__main__':
    unittest.main()
