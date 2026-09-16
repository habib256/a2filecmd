#!/usr/bin/env python3
"""The real 6502 copy engine, with every read and write made to fail.

Runs the shipped copy.s under sim65 on disposable fixtures only. What is
checked is not the return code but the bytes: the source must come out
untouched, every pre-existing byte of the target must survive, and no
catalog entry may appear unless every written sector was read back.
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

    def test_execute_does_not_borrow_name_tables(self):
        # A tagged batch still walks the source snapshot. The 32-sector
        # working area is the extra RAM; ent_name stays the panel's until
        # the UI reloads after the last file.
        names = bytes(self.mini.peek('ent_name', 30))
        slots = bytes(self.mini.peek('ent_name', 2 * 32))
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.execute(), OK)
        self.copied()
        self.assertEqual(bytes(self.mini.peek('ent_name', 30)), names)
        self.assertEqual(bytes(self.mini.peek('ent_name', 2 * 32)), slots)

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
        self.assertEqual(self.mini.byte('drive'), 1)
        self.assertEqual(self.mini.prepare(0, 1), SAME)
        self.assertEqual(len(self.mini.write_log), 0)

    def test_cancel_keeps_later_io_on_source(self):
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.byte('drive'), 2)
        self.mini.cancel()
        self.assertEqual(self.mini.byte('drive'), 1)
        self.assertEqual(self.mini.catalog(), OK)
        name = bytes(self.mini.peek('ent_name', 30))
        self.assertEqual(name, b'COPY.ME'.ljust(30))
        self.assertEqual(self.mini.delete_prepare(1), 0)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.image(1), self.src)
        self.assertEqual(self.image(2), self.dst)

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
        # bcs, not beq: a count above 105 is also full. 105 live names
        # already fill the panel; a free slot on a longer chain would
        # still have to be refused.

    def test_stale_panel_size_and_pointer(self):
        # The panel's size and T/S pointer must be what the catalog slot
        # holds now; a stale snapshot is a changed disk. The rest of the
        # disk is not audited.
        self.mini.poke('ent_seclo', bytes([1]))
        self.mini.poke('ent_sechi', bytes([0]))
        self.mini.poke('ent_track', bytes([34]))
        self.mini.poke('ent_sector', bytes([15]))
        self.assertEqual(self.prepare(), CHANGED)
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
        # After the prompt, the source catalog slot and the destination
        # VTOC (the sector about to be overwritten from the reservation
        # image) are read again. The source VTOC and the destination
        # catalog are not re-audited.
        for side, at, expect in ((1, offset(17, 0) + 6, OK),
                                 (1, offset(17, 15) + 11 + 2, CHANGED),
                                 (2, offset(17, 0) + 6, CHANGED),
                                 (2, offset(17, 15) + 10, OK)):
            with self.subTest(side=side, at=at):
                self.load()
                self.assertEqual(self.prepare(), OK)
                self.mini.disks[side - 1][at] ^= 1
                self.assertEqual(self.mini.execute(), expect)
                if expect == OK:
                    self.assertGreater(len(self.mini.write_log), 0)
                else:
                    self.assertEqual(self.mini.write_log, [])
                    self.assertEqual(self.mini.byte('copy_fault'), 0)

    def test_swapped_destination_after_the_prompt(self):
        # The user swaps the target disk while COPY ...? is on screen.
        # The stale VTOC image must not land on the new disk.
        other = make_disk([('OTHER.DISK', 0, bytes(700))])
        self.assertNotEqual(other[offset(17, 0):offset(17, 1)],
                            self.dst[offset(17, 0):offset(17, 1)])
        self.assertEqual(self.prepare(), OK)
        self.mini.load(2, other)
        self.assertEqual(self.mini.execute(), CHANGED)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(2), other)
        self.assertEqual(self.mini.byte('copy_fault'), 0)
        self.assertEqual(self.mini.execute(), NOT_READY, 'one prompt, one plan')
        # a fresh prepare on the new disk works
        self.mini.poke('drive', bytes([1]))
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.execute(), OK)
        self.assertIn('COPY.ME', read_files(self.image(2)))
        self.assertIn('OTHER.DISK', read_files(self.image(2)))

    def test_swapped_destination_before_create(self):
        other = make_disk([('OTHER.DISK', 0, bytes(700))])
        self.assertEqual(self.create(), OK)
        self.mini.load(2, other)
        self.assertEqual(self.mini.create_execute(), CHANGED)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(2), other)

    def test_execute_vtoc_read_failure_is_a_plain_refusal(self):
        self.assertEqual(self.prepare(), OK)
        self.mini.fail_read = self.mini.reads    # the next read: the VTOC
        self.assertEqual(self.mini.execute(), READ)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.mini.byte('copy_fault'), 0)
        self.preserved()

    def test_looping_destination_catalog_does_not_hang(self):
        # A corrupt link after the panel read: 15 -> 14 -> 13 -> 14 ...
        img = bytearray(self.dst)
        img[offset(17, 13) + 1:offset(17, 13) + 3] = bytes([17, 14])
        self.mini.load(2, bytes(img))
        self.assertEqual(self.prepare(), INVALID)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(2), bytes(img))

    def test_write_protection(self):
        self.assertEqual(self.prepare(), OK)
        self.mini.protected_drive = 2
        self.assertEqual(self.mini.execute(), PROTECTED)
        self.assertEqual(self.image(2), self.dst)
        self.assertEqual(self.mini.byte('copy_fault'), 0,
                         'a refused disk is not an uncertain one')

    def test_protect_after_vtoc_latches(self):
        self.assertEqual(self.prepare(), OK)
        self.mini.protect_write = 1
        self.assertEqual(self.mini.execute(), UNCERTAIN)   # reserved sectors are down: not "untouched"
        self.assertEqual(self.mini.byte('copy_fault'), 1)
        self.assertNotIn('COPY.ME', read_files(self.image(2)))
        self.assertEqual(self.mini.prepare(0, 2), UNCERTAIN)
        self.preserved()

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
        # The catalog entry vanished after prepare: the mapped sectors
        # are not read as if they were still that file.
        a = offset(17, 15) + 11
        self.mini.disks[0][a] = 255
        self.assertEqual(self.mini.execute(), CHANGED)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.mini.byte('copy_fault'), 0)
        self.assertEqual(self.image(2), self.dst)

    def test_swapped_source_after_the_prompt(self):
        # Another disk in the source drive when Y is pressed: its catalog
        # slot does not hold the entry that was mapped.
        other = make_disk([('OTHER.SRC', 0x84, bytes(700)),
                           ('KEEP.SRC', 0, b'SOURCE SAFE')])
        self.assertEqual(self.prepare(), OK)
        self.mini.load(1, other)
        self.assertEqual(self.mini.execute(), CHANGED)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(1), other)
        self.assertEqual(self.image(2), self.dst)

    def test_dosless_disks_use_tracks_1_and_2(self):
        # A disk formatted without DOS frees tracks 1-2 and DOS files
        # data there. Such a file is copied and deleted. A copy never
        # allocates there itself; an ordinary disk (tracks 1-2 fully
        # allocated) still refuses a chain into them.
        src = make_disk([('ON.TRACK1', 0x04, bytes(range(256)) * 5)], dosless=True)
        dst = make_disk([('KEEP.DST', 0x80, b'DESTINATION SAFE')], dosless=True)
        self.assertLess(max(t for t, _ in read_files(src)['ON.TRACK1']['blocks']), 3)
        self.load(src=src, dst=dst)
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.execute(), OK)
        self.preserved()
        result = read_files(self.image(2))['ON.TRACK1']
        self.assertEqual(result['data'], read_files(src)['ON.TRACK1']['data'])
        self.assertGreaterEqual(min(t for t, _ in result['blocks'] + result['lists']), 3,
                                'the copy leaves tracks 1-2 alone')
        self.mini.poke('drive', bytes([1]))     # as the UI's reread does
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        self.assertEqual(self.mini.delete_execute(), self.DEL_OK)
        files = read_files(self.image(1))
        self.assertNotIn('ON.TRACK1', files)
        v = offset(17, 0)
        for t in (1, 2):
            self.assertEqual(self.image(1)[v + 0x38 + t * 4:v + 0x3a + t * 4], b'\xff\xff',
                             'every sector of the freed tracks is free again')
        self.assertEqual(self.image(1)[v + 0x38:v + 0x3a], b'\0\0', 'track 0 stays allocated')
        # an ordinary disk: a T/S list on track 1 is a chain into DOS
        self.load(src=make_disk([('GONE.TXT', 0, b'DELETE ME'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        img = bytearray(self.src)
        img[offset(17, 15) + 11] = 1
        img[offset(17, 15) + 12] = 0
        self.mini.load(1, bytes(img))
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(self.prepare(), INVALID)
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_INVALID)
        self.assertEqual(self.mini.write_log, [])

    def test_catalog_art_name_is_kept_byte_for_byte(self):
        # Inverse, control and low-ASCII bytes in a DOS name: the panel
        # shows them as '!' or '?', the copy keeps the raw bytes, and
        # delete, lock and rename act on that very slot.
        self.load(src=make_disk([('ART', 0, b'ART DATA'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        raw = bytes([0xC1, 0xD2, 0xD4, 0x21, 0x01, 0x81]) + b'\xa0' * 24
        img = bytearray(self.src)
        a = offset(17, 15) + 11
        img[a + 3:a + 33] = raw
        self.src = bytes(img)
        self.mini.load(1, self.src)
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(bytes(self.mini.peek('ent_name', 6)), b'ART!??')
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.execute(), OK)
        self.preserved()
        copies = [f for f in read_files(self.image(2)).values() if f['entry'][3:33] == raw]
        self.assertEqual(len(copies), 1, 'the name travels byte for byte')
        self.assertEqual(copies[0]['data'].rstrip(b'\x00'), b'ART DATA')
        writes = len(self.mini.write_log)
        self.mini.poke('drive', bytes([1]))
        self.assertEqual(self.prepare(), EXISTS, 'the raw name collides with itself')
        self.assertEqual(len(self.mini.write_log), writes)
        self.mini.poke('drive', bytes([1]))     # as the UI's reread does
        self.assertEqual(self.mini.lock_prepare(0, 2), self.DEL_OK)
        self.assertEqual(self.mini.lock_execute(), self.DEL_OK)
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(self.mini.lock_prepare(0, 1), self.DEL_OK)
        self.assertEqual(self.mini.lock_execute(), self.DEL_OK)
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(self.mini.rename_prepare(0, 'PLAIN'), self.DEL_OK)
        self.assertEqual(self.mini.rename_execute(), self.DEL_OK)
        self.assertEqual(self.mini.catalog(), 0)
        files = read_files(self.image(1))
        self.assertEqual(files['PLAIN']['data'].rstrip(b'\x00'), b'ART DATA')
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        self.assertEqual(self.mini.delete_execute(), self.DEL_OK)
        files = read_files(self.image(1))
        self.assertEqual(set(files), {'KEEP.SRC'})
        self.assertEqual(files['KEEP.SRC']['data'].rstrip(b'\x00'), b'SOURCE SAFE')

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
    DEL_PROTECTED = 8

    def two_files(self):
        self.load(src=make_disk([('GONE.TXT', 0, b'DELETE ME'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        return offset(17, 15) + 11, offset(17, 15) + 11 + 35

    def test_delete_refuses_an_entry_whose_identity_changed(self):
        # The panel was read from one disk; a sibling disk with the same
        # names but other T/S lists is in the drive when D is pressed.
        # Deleting by name would free KEEP.SRC's sectors.
        a, b = self.two_files()
        img = bytearray(self.src)
        img[a:a + 2], img[b:b + 2] = self.src[b:b + 2], self.src[a:a + 2]
        img[a + 33:a + 35], img[b + 33:b + 35] = self.src[b + 33:b + 35], self.src[a + 33:a + 35]
        self.mini.load(1, bytes(img))
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_CHANGED)
        self.assertEqual(self.mini.lock_prepare(0, 0), self.DEL_CHANGED)
        self.assertEqual(self.mini.rename_prepare(0, 'NEW.TXT'), self.DEL_CHANGED)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(1), bytes(img))
        # the same name gone from the disk: also a changed disk
        img = bytearray(self.src)
        img[a + 3:a + 33] = bytes(c | 128 for c in b'ELSEWHERE'.ljust(30))
        self.mini.load(1, bytes(img))
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_CHANGED)
        self.assertEqual(self.mini.lock_prepare(0, 0), self.DEL_CHANGED)
        self.assertEqual(self.mini.rename_prepare(0, 'NEW.TXT'), self.DEL_CHANGED)
        # a changed type or size is refused before the walk
        for at in (a + 2, a + 33):
            img = bytearray(self.src)
            img[at] ^= 0x40
            self.mini.load(1, bytes(img))
            self.assertEqual(self.mini.delete_prepare(0), self.DEL_CHANGED)
        self.assertEqual(self.mini.write_log, [])

    def test_delete_of_a_sanitised_name_never_takes_another_file(self):
        # FOO<ctrl-M> and FOO? both show as FOO? on the panel. Deleting
        # the second entry removes that entry, never the first, whose raw
        # name happens to equal the panel's sanitised text.
        self.load(src=make_disk([('FOO?', 0, b'QUESTION FILE'),
                                 ('FOOX', 0, b'CONTROL FILE')]))
        img = bytearray(self.src)
        img[offset(17, 15) + 11 + 35 + 3 + 3] = 0x8D
        self.mini.load(1, bytes(img))
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(bytes(self.mini.peek('ent_name', 4, offset=32)), b'FOO?')
        self.assertEqual(self.mini.delete_prepare(1), self.DEL_OK)
        self.assertEqual(self.mini.delete_execute(), self.DEL_OK)
        files = read_files(self.image(1))
        self.assertEqual(set(files), {'FOO?'})
        self.assertEqual(files['FOO?']['data'].rstrip(b'\x00'), b'QUESTION FILE')
        a = offset(17, 15) + 11 + 35
        self.assertEqual(self.image(1)[a], 255, 'the second slot is the deleted one')

    def test_looping_catalog_does_not_hang_delete_lock_rename(self):
        # Lock touches only the slot's own sector; rename scans every name
        # and delete walks every other file, so both refuse a chain that
        # never ends.
        a, b = self.two_files()
        img = bytearray(self.src)
        img[offset(17, 13) + 1:offset(17, 13) + 3] = bytes([17, 14])
        self.mini.load(1, bytes(img))
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_INVALID)
        self.assertEqual(self.mini.lock_prepare(0, 0), self.DEL_OK)
        self.assertEqual(self.mini.rename_prepare(0, 'NEW.TXT'), self.DEL_INVALID)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(1), bytes(img))

    def test_write_protection_refuses_delete_lock_rename_cleanly(self):
        # RWTS refuses before touching the disk: nothing is uncertain,
        # nothing latches, and the next write in this run is allowed.
        a, b = self.two_files()
        self.mini.protected_drive = 1
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        self.assertEqual(self.mini.delete_execute(), self.DEL_PROTECTED)
        self.assertEqual(self.mini.lock_prepare(0, 0), self.DEL_OK)
        self.assertEqual(self.mini.lock_execute(), self.DEL_PROTECTED)
        self.assertEqual(self.mini.rename_prepare(0, 'NEW.TXT'), self.DEL_OK)
        self.assertEqual(self.mini.rename_execute(), self.DEL_PROTECTED)
        self.assertEqual(self.mini.byte('del_fault'), 0)
        self.assertEqual(self.image(1), self.src)
        self.mini.protected_drive = 0
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        self.assertEqual(self.mini.delete_execute(), self.DEL_OK)
        self.assertNotIn('GONE.TXT', read_files(self.image(1)))

    def test_write_protection_after_the_catalog_mark_is_uncertain(self):
        a, b = self.two_files()
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        self.mini.protect_write = 1
        self.assertEqual(self.mini.delete_execute(), self.DEL_UNCERTAIN)
        self.assertEqual(self.mini.byte('del_fault'), 1)
        self.assertEqual(self.image(1)[a], 255, 'the catalog mark is on the disk')
        self.assertEqual(self.image(1)[offset(17, 0):offset(17, 0) + 256],
                         self.src[offset(17, 0):offset(17, 0) + 256],
                         'the VTOC was refused')

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
        # DOS UNDELETE mark: track $FF, the original T/S list track in the
        # last name byte (entry+$20), the rest of the name untouched
        a = offset(17, 15) + 11
        gone = read_files(self.src)['GONE.TXT']
        self.assertEqual(self.image(1)[a], 255)
        self.assertEqual(self.image(1)[a + 32], gone['lists'][0][0])
        self.assertEqual(self.image(1)[a + 1:a + 32], self.src[a + 1:a + 32])
        self.assertEqual(self.image(1)[a + 33:a + 35], self.src[a + 33:a + 35])

    def test_delete_audits_the_disk_once_per_batch(self):
        # The audit walks every live file's T/S lists; on a full disk that
        # is a hundred scattered reads. It runs for the first file of a
        # batch only: deleting a file cannot cross-link the others, and
        # each later file still has its own chain walked and its slot and
        # the VTOC held to the panel before any write.
        files = [(f'F{i:03d}', 0, b'X' * 300) for i in range(60)]
        self.load(src=make_disk(files))
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        first = self.mini.reads
        self.assertGreater(first, 60)
        self.assertEqual(self.mini.delete_execute(), self.DEL_OK)
        self.mini.reads = 0
        self.assertEqual(self.mini.delete_prepare(1, new_batch=False), self.DEL_OK)
        self.assertLess(self.mini.reads, 8, 'no second audit within a batch')
        self.assertEqual(self.mini.delete_execute(), self.DEL_OK)
        # The next D audits again.
        self.mini.reads = 0
        self.assertEqual(self.mini.delete_prepare(2), self.DEL_OK)
        self.assertGreater(self.mini.reads, 58)
        self.assertEqual(self.mini.delete_execute(), self.DEL_OK)
        after = read_files(self.image(1))
        self.assertEqual(len(after), 57)
        for name in ('F000', 'F001', 'F002'):
            self.assertNotIn(name, after)
        # A swapped disk inside a batch is still refused on identity.
        self.assertEqual(self.mini.delete_prepare(3, new_batch=False), self.DEL_OK)
        self.mini.load(1, make_disk(files[::-1]))
        self.assertEqual(self.mini.delete_execute(), self.DEL_CHANGED)
        self.assertEqual(self.mini.image(1), make_disk(files[::-1]))

    def test_full_dosless_disk_keeps_its_files_deletable(self):
        # A disk formatted without DOS whose tracks 1-2 filled up: the VTOC
        # alone cannot tell it from a DOS disk, the boot sector can. Every
        # file stays valid, so a delete's whole-disk audit still passes and
        # a file living on track 1 copies; on a disk whose boot sector is
        # DOS 3.3's, a chain into track 1 is still refused.
        files = [(f'S{i:02d}', 0, b'X' * 100) for i in range(16)]   # 16 x 2 sectors: tracks 1-2 full
        files.append(('LATER', 0, b'ON TRACK 3'))
        disk = bytearray(make_disk(files, dosless=True))
        self.load(src=bytes(disk), dst=make_disk([]))
        self.assertEqual(self.mini.delete_prepare(16), self.DEL_OK)
        reads = self.mini.reads
        self.assertEqual(self.mini.delete_execute(), self.DEL_OK)
        self.assertNotIn('LATER', read_files(self.image(1)))
        self.assertEqual(self.mini.prepare(0, 2), OK)          # S00 lives on track 1
        self.assertEqual(self.mini.execute(), OK)
        self.assertEqual(read_files(self.image(2))['S00']['data'][:100], b'X' * 100)
        disk[0:5] = self.SIG
        self.load(src=bytes(disk), dst=make_disk([]))
        self.assertEqual(self.mini.delete_prepare(16), self.DEL_INVALID)
        self.assertEqual(self.mini.prepare(0, 2), INVALID)
        self.assertEqual(self.mini.write_log, [])

    def test_delete_refuses_locked(self):
        self.load(src=make_disk([('LOCK.ME', 0x80, b'SAFE')]))
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_LOCKED)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.image(1), self.src)

    SIG = bytes([0x01, 0xA5, 0x27, 0xC9, 0x09])     # a DOS 3.3 boot sector starts so

    def test_delete_refuses_dos_system_track(self):
        self.load(src=make_disk([('GONE.TXT', 0, b'DELETE ME'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        img = bytearray(self.image(1))
        img[0:5] = self.SIG                     # tracks 1-2 all used and DOS booting: DOS's
        img[offset(17, 15) + 11] = 1
        img[offset(17, 15) + 12] = 0
        self.mini.load(1, bytes(img))
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_INVALID)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.image(1), bytes(img))

    def test_delete_refuses_wrong_ts_offset(self):
        self.load(src=make_disk([('GONE.TXT', 0, b'DELETE ME'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        gone = read_files(self.src)['GONE.TXT']
        ts = offset(*gone['lists'][0])
        img = bytearray(self.image(1))
        img[ts + 5] = 122
        self.mini.load(1, bytes(img))
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_INVALID)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.image(1), bytes(img))

    def test_delete_refuses_wrong_sector_count(self):
        self.load(src=make_disk([('GONE.TXT', 0, b'DELETE ME'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        img = bytearray(self.image(1))
        img[offset(17, 15) + 11 + 33] = 99
        self.mini.load(1, bytes(img))
        self.assertEqual(self.mini.catalog(), 0)    # the panel shows 99 too
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_INVALID)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.image(1), bytes(img))

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

    def test_lock_toggles_and_preserves_bytes(self):
        self.load(src=make_disk([('LOCK.ME', 0, b'SAFE DATA'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        before = read_files(self.src)
        self.assertEqual(self.mini.lock_prepare(0, 0), self.DEL_OK)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.mini.lock_execute(), self.DEL_OK)
        files = read_files(self.image(1))
        self.assertEqual(files['LOCK.ME']['type'] & 0x80, 0x80)
        self.assertEqual(files['LOCK.ME']['data'], before['LOCK.ME']['data'])
        self.assertEqual(files['KEEP.SRC']['data'], before['KEEP.SRC']['data'])
        self.assertEqual(self.mini.write_log, [(1, 17, 15)])
        # the panel still says unlocked: the disk is held to the panel
        self.assertEqual(self.mini.lock_prepare(0, 0), self.DEL_CHANGED)
        self.assertEqual(self.mini.catalog(), 0)    # as the UI rereads
        self.assertEqual(self.mini.lock_prepare(0, 0), self.DEL_OK)
        self.assertEqual(self.mini.lock_execute(), self.DEL_OK)
        self.assertEqual(self.mini.catalog(), 0)
        files = read_files(self.image(1))
        self.assertEqual(files['LOCK.ME']['type'] & 0x80, 0)

    def test_unlock_then_delete(self):
        self.load(src=make_disk([('LOCK.ME', 0x80, b'SAFE'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_LOCKED)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.mini.lock_prepare(0, 1), self.DEL_OK)
        self.assertEqual(self.mini.lock_execute(), self.DEL_OK)
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        self.assertEqual(self.mini.delete_execute(), self.DEL_OK)
        self.assertNotIn('LOCK.ME', read_files(self.image(1)))
        self.assertIn('KEEP.SRC', read_files(self.image(1)))

    def test_unlock_already_clear_does_not_write(self):
        self.load(src=make_disk([('OPEN.ME', 0, b'SAFE')]))
        self.assertEqual(self.mini.lock_prepare(0, 1), self.DEL_LOCKED)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.image(1), self.src)

    def test_lock_write_failure_latches(self):
        self.load(src=make_disk([('LOCK.ME', 0, b'SAFE'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        self.assertEqual(self.mini.lock_prepare(0, 2), self.DEL_OK)
        self.mini.fail_write = 0
        self.assertEqual(self.mini.lock_execute(), self.DEL_UNCERTAIN)
        self.assertEqual(self.mini.byte('del_fault'), 1)
        self.assertEqual(self.mini.lock_prepare(0, 2), self.DEL_UNCERTAIN)
        keep = read_files(self.src)['KEEP.SRC']
        for t, s in keep['blocks'] + keep['lists']:
            a = offset(t, s)
            self.assertEqual(self.image(1)[a:a + 256], self.src[a:a + 256])

    def test_rename_keeps_bytes_and_refuses_collision(self):
        self.load(src=make_disk([('OLD.TXT', 0, b'RENAME ME'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        before = read_files(self.src)
        self.assertEqual(self.mini.rename_prepare(0, 'NEW.TXT'), self.DEL_OK)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.mini.rename_execute(), self.DEL_OK)
        files = read_files(self.image(1))
        self.assertNotIn('OLD.TXT', files)
        self.assertEqual(files['NEW.TXT']['data'], before['OLD.TXT']['data'])
        self.assertEqual(files['KEEP.SRC']['data'], before['KEEP.SRC']['data'])
        self.assertEqual(self.mini.write_log, [(1, 17, 15)])
        # execute holds the disk to prepare's scan (VTOC and slot sector
        # byte for byte, then the read-back): three reads, no second scan
        self.assertEqual(self.mini.reads, 17 + 3)
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(self.mini.rename_prepare(0, 'KEEP.SRC'), 7)
        self.assertEqual(len(self.mini.write_log), 1)
        self.assertIn('NEW.TXT', read_files(self.image(1)))
        self.assertIn('KEEP.SRC', read_files(self.image(1)))

    def test_patched_entry_after_rename_and_lock_still_holds_the_slot(self):
        # The UI patches the panel entry instead of rereading the catalog.
        # The patched entry must be what a reread would store (names are
        # kept sanitised), or the next write would refuse DISK CHANGED.
        self.load(src=make_disk([('OLD.TXT', 0, b'RENAME ME'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        self.assertEqual(self.mini.rename_prepare(0, 'MEMO'), self.DEL_OK)
        self.assertEqual(self.mini.rename_execute(), self.DEL_OK)
        self.assertEqual(self.mini.patch_name(), self.DEL_OK)
        patched = self.mini.peek('ent_name', 32)
        self.assertEqual(self.mini.lock_prepare(0, 2), self.DEL_OK)
        self.assertEqual(self.mini.lock_execute(), self.DEL_OK)
        self.assertEqual(self.mini.patch_type(), self.DEL_OK)
        self.assertEqual(self.mini.byte('ent_type'), 0x80)
        self.assertEqual(self.mini.lock_prepare(0, 1), self.DEL_OK)
        self.assertEqual(self.mini.lock_execute(), self.DEL_OK)
        self.assertEqual(self.mini.patch_type(), self.DEL_OK)
        self.assertEqual(self.mini.byte('ent_type'), 0)
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        self.assertEqual(self.mini.delete_execute(), self.DEL_OK)
        self.assertNotIn('MEMO', read_files(self.image(1)))
        # and byte for byte what a reread stores
        self.load(src=make_disk([('OLD.TXT', 0, b'RENAME ME'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        self.assertEqual(self.mini.rename_prepare(0, 'MEMO'), self.DEL_OK)
        self.assertEqual(self.mini.rename_execute(), self.DEL_OK)
        self.assertEqual(self.mini.patch_name(), self.DEL_OK)
        patched = self.mini.peek('ent_name', 32)
        self.assertEqual(self.mini.catalog(), 0)
        self.assertEqual(self.mini.peek('ent_name', 32), patched)

    def test_rename_refuses_locked(self):
        self.load(src=make_disk([('LOCK.ME', 0x80, b'SAFE')]))
        self.assertEqual(self.mini.rename_prepare(0, 'NEW.TXT'), self.DEL_LOCKED)
        self.assertEqual(len(self.mini.write_log), 0)
        self.assertEqual(self.image(1), self.src)

    def test_rename_write_failure_latches(self):
        self.load(src=make_disk([('OLD.TXT', 0, b'SAFE'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        self.assertEqual(self.mini.rename_prepare(0, 'NEW.TXT'), self.DEL_OK)
        self.mini.fail_write = 0
        self.assertEqual(self.mini.rename_execute(), self.DEL_UNCERTAIN)
        self.assertEqual(self.mini.byte('del_fault'), 1)
        self.assertEqual(self.mini.rename_prepare(0, 'NEW.TXT'), self.DEL_UNCERTAIN)
        files = read_files(self.image(1))
        self.assertIn('OLD.TXT', files)
        self.assertNotIn('NEW.TXT', files)
        keep = read_files(self.src)['KEEP.SRC']
        for t, s in keep['blocks'] + keep['lists']:
            a = offset(t, s)
            self.assertEqual(self.image(1)[a:a + 256], self.src[a:a + 256])


    # ---- review fixes: one latch, DOS tracks, rename, slots, audit --
    DEL_NOT_READY, REN_EXISTS, REN_SAME = 6, 7, 9

    def test_uncertain_copy_blocks_delete_lock_rename(self):
        # Every write in a run shares one promise: after an uncertain
        # write, no further write. A torn copy must stop delete too.
        self.assertEqual(self.prepare(), OK)
        self.mini.fail_write = 1                # the first data sector
        self.assertEqual(self.mini.execute(), UNCERTAIN)
        dst_after = self.image(2)
        writes = len(self.mini.write_log)
        self.mini.poke('drive', bytes([1]))
        self.assertEqual(self.mini.delete_prepare(1), self.DEL_UNCERTAIN)
        self.assertEqual(self.mini.delete_execute(), self.DEL_UNCERTAIN)
        self.assertEqual(self.mini.lock_prepare(1, 2), self.DEL_UNCERTAIN)
        self.assertEqual(self.mini.lock_execute(), self.DEL_UNCERTAIN)
        self.assertEqual(self.mini.rename_prepare(1, 'OTHER'), self.DEL_UNCERTAIN)
        self.assertEqual(self.mini.rename_execute(), self.DEL_UNCERTAIN)
        self.assertEqual(len(self.mini.write_log), writes)
        self.assertEqual(self.image(1), self.src)
        self.assertEqual(self.image(2), dst_after)

    def test_uncertain_delete_blocks_copy_and_create(self):
        self.two_files()
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        self.mini.fail_write = 0
        self.assertEqual(self.mini.delete_execute(), self.DEL_UNCERTAIN)
        src_after = self.image(1)
        writes = len(self.mini.write_log)
        self.mini.poke('drive', bytes([1]))
        self.assertEqual(self.mini.prepare(1, 2), UNCERTAIN)
        self.assertEqual(self.mini.execute(), UNCERTAIN)
        self.assertEqual(self.create(), UNCERTAIN)
        self.assertEqual(self.mini.create_execute(), UNCERTAIN)
        self.assertEqual(len(self.mini.write_log), writes)
        self.assertEqual(self.image(1), src_after)
        self.assertEqual(self.image(2), self.dst)

    def test_copy_never_allocates_dos_tracks(self):
        # valid_data accepts a chain on tracks 1-2 only while one of their
        # sectors is free. A copy that took the last ones would turn every
        # file there, its own included, into an invalid structure.
        dst = bytearray(make_disk([('KEEP.DST', 0x80, b'DESTINATION SAFE')], dosless=True))
        v = offset(17, 0)
        for t in range(3, 35):
            dst[v + 0x38 + t * 4:v + 0x3a + t * 4] = b'\0\0'
        self.load(dst=bytes(dst))
        self.assertEqual(self.prepare(), FULL)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(2), bytes(dst))

    def test_rename_to_the_same_name_is_a_no_op(self):
        self.load(src=make_disk([('SAME.TXT', 0, b'KEEP ME'),
                                 ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        self.assertEqual(self.mini.rename_prepare(0, 'SAME.TXT'), self.REN_SAME)
        self.assertEqual(self.mini.rename_execute(), self.DEL_NOT_READY)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(1), self.src)

    def test_rename_normalises_a_flash_name(self):
        # FLASH letters are $40-$5F: the panel shows FLASH, the disk does
        # not hold it. Typing the visible name is a real rename.
        src = bytearray(make_disk([('FLASH', 0, b'FLASH DATA'),
                                   ('KEEP.SRC', 0, b'SOURCE SAFE')]))
        a = offset(17, 15) + 11
        for i in range(5):
            src[a + 3 + i] &= 0x7F
        self.load(src=bytes(src))
        self.assertEqual(bytes(self.mini.peek('ent_name', 5)), b'FLASH')
        self.assertEqual(self.mini.rename_prepare(0, 'FLASH'), self.DEL_OK)
        self.assertEqual(self.mini.rename_execute(), self.DEL_OK)
        want = bytearray(src)
        want[a + 3:a + 8] = bytes(c | 128 for c in b'FLASH')
        self.assertEqual(self.image(1), bytes(want))

    def moved_catalog(self):
        """MOVED and KEEP.SRC listed in (18,3), which the VTOC links first.
        A stale copy of that sector's entries sits in (17,3), out of the
        chain: the slot a track-17 assumption would aim at."""
        base = make_disk([('MOVED', 0, b'MOVED DATA'), ('KEEP.SRC', 0, b'SOURCE SAFE')])
        img = bytearray(base)
        v = offset(17, 0)
        img[offset(18, 3):offset(18, 4)] = base[offset(17, 15):offset(18, 0)]
        img[offset(18, 3) + 1:offset(18, 3) + 3] = bytes([17, 14])
        img[v + 1:v + 3] = bytes([18, 3])
        img[v + 0x38 + 18 * 4 + 1] &= ~(1 << 3) & 255
        img[offset(17, 4) + 1:offset(17, 4) + 3] = bytes([17, 2])
        img[offset(17, 3) + 11:offset(17, 3) + 81] = base[offset(17, 15) + 11:offset(17, 15) + 81]
        read_files(bytes(img))
        return bytes(img)

    def test_catalog_off_track_17_is_never_aimed_at_track_17(self):
        img = self.moved_catalog()
        self.load(src=img)
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_INVALID)
        self.assertEqual(self.mini.delete_execute(), self.DEL_NOT_READY)
        self.assertEqual(self.mini.lock_prepare(0, 2), self.DEL_INVALID)
        self.assertEqual(self.mini.rename_prepare(0, 'NEW.NAME'), self.DEL_INVALID)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(1), img)
        # The copy reads the slot where the entry really is, not the stale
        # one, which no longer matches the panel.
        self.mini.disks[0][offset(17, 3) + 11 + 3] ^= 1
        self.src = self.image(1)
        self.assertEqual(self.prepare(), OK)
        self.assertEqual(self.mini.execute(), OK)
        self.assertEqual(read_files(self.image(2))['MOVED']['data'].rstrip(b'\0'),
                         b'MOVED DATA')
        self.preserved()
        self.assertEqual(bytes(self.mini.peek('ent_name', 2, offset=30)),
                         bytes([18, 3 << 3]))

    def cross_linked(self):
        base = make_disk([('A.FILE', 0, b'A' * 600), ('B.FILE', 0, b'B' * 300),
                          ('C.FILE', 0, b'CCC')])
        files = read_files(base)
        img = bytearray(base)
        bts = offset(*files['B.FILE']['lists'][0])
        img[bts + 12:bts + 14] = bytes(files['A.FILE']['blocks'][1])
        return bytes(img)

    def test_delete_refuses_a_cross_linked_disk(self):
        # B's data sector is also A's second one. Freeing A's sectors would
        # hand B's data to the next copy, and C cannot be told apart from
        # a disk whose allocation graph is sound.
        img = self.cross_linked()
        self.load(src=img)
        for index in (0, 1, 2):
            with self.subTest(index=index):
                self.assertEqual(self.mini.delete_prepare(index), self.DEL_INVALID)
                self.assertEqual(self.mini.delete_execute(), self.DEL_NOT_READY)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(1), img)

    def test_delete_refuses_when_another_chain_is_malformed(self):
        self.two_files()
        keep = read_files(self.src)['KEEP.SRC']
        img = bytearray(self.src)
        img[offset(*keep['lists'][0]) + 5] = 122
        self.load(src=bytes(img))
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_INVALID)
        self.assertEqual(self.mini.write_log, [])
        self.assertEqual(self.image(1), bytes(img))

    def test_delete_every_read_failure_during_the_audit(self):
        self.two_files()
        self.assertEqual(self.mini.delete_prepare(0), self.DEL_OK)
        plan_reads = self.mini.reads
        self.assertGreater(plan_reads, 3, 'the other entries are read too')
        for n in range(plan_reads):
            with self.subTest(read=n):
                self.two_files()
                self.mini.fail_read = n
                self.assertEqual(self.mini.delete_prepare(0), self.DEL_READ)
                self.assertEqual(self.mini.delete_execute(), self.DEL_NOT_READY)
                self.assertEqual(self.mini.write_log, [])
                self.assertEqual(self.image(1), self.src)


if __name__ == '__main__':
    unittest.main()
