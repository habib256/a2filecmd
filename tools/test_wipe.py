"""Run WIPE (F and W) against a block-device mock; inspect every byte.

The real src/plugins/wipe.c, twice: compiled with the host compiler (class
Wipe), and compiled by each edition's cc65 and run under sim65 with its
buffers at their real page-aligned addresses (class WipeCc65) -- the host
compiler cannot see what cc65 makes of a comparison loop. Both mocks hold up
to two disks for the one unit: the second replaces the first at a chosen
moment (the confirmation, a given block read after it), the way a floppy is
swapped in a drive. Every test compares the BYTES of both disks."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HEAD = Path(os.environ.get('CC65_HEAD', str(Path.home() / 'opt/cc65-head')))

HARNESS = PREFIX + r'''
static unsigned char bitmap_buffer[512], zero_buffer[512], header_buffer[512], keyboard;
#define BM bitmap_buffer
#define ZERO zero_buffer
#define HDR header_buffer
#define KBD keyboard
#define KBDSTRB keyboard
#include "src/plugins/wipe.c"
/* disk: what the unit holds now; other: what a swap puts there instead. */
static FILE *disk, *other;
static unsigned int writes, reads_after, swap_read, swapped, fail2;
static unsigned char answered, swap_answer, online, key_typed, yes = 1, twin;
static const char* typed = "ERASE";
static char input[17], shown[1024];
static void swap(void) { if (other) { disk = other; other = 0; swapped = 1; } }
static void answer(void) { answered = 1; if (swap_answer) swap(); }
static unsigned char mock_mli(unsigned char cmd, void* p) {
    struct Bp* b = p;
    if (cmd == 0xC5) {              /* ON_LINE: the one unit, named by its block 2 */
        struct Ol* o = p; unsigned char* r = o->buf; unsigned char h[16];
        if (!online) return 0x27;
        memset(r, 0, 256);
        if (fseek(disk, 1028, SEEK_SET) || fread(h, 1, 16, disk) != 16) return 0x27;
        r[0] = 0x60 | (h[0] & 15); memcpy(r + 1, h + 1, 15);
        /* twin=1: a second drive, S6,D2, carries the same name */
        if (twin) { r[16] = 0xE0 | (h[0] & 15); memcpy(r + 17, h + 1, 15); }
        return 0;
    }
    if (cmd != 0x80 && cmd != 0x81) return 1;
    if (b->n != 3 || b->unit != 0x60) return 0x28;
    if (cmd == 0x80 && answered) {
        if (++reads_after == swap_read) swap();
        /* fail2=N: block 2 stops reading at the Nth read after the answer. */
        if (fail2 && reads_after >= fail2 && b->block == 2) return 0x27;
    }
    if (fseek(disk, (long)b->block * 512, SEEK_SET)) return 0x27;
    if (cmd == 0x80) return fread(b->buf, 1, 512, disk) == 512 ? 0 : 0x27;
    ++writes;
    return fwrite(b->buf, 1, 512, disk) == 512 ? 0 : 0x27;
}
static char choose(void) { return key_typed; }
static void show(const char* s) { strcat(shown, s); strcat(shown, "|"); }
static unsigned char confirm(const char* s) { show(s); answer(); return yes; }
static unsigned char prompt(const char* s, const char* d, unsigned char hex)
{ (void)d; (void)hex; show(s); strcpy(input, typed); answer(); return typed[0] != 0; }
static void message(const char* s) { show(s); }
static int show_printf(const char* f, ...)
{ char line[128]; va_list ap; va_start(ap, f); vsprintf(line, f, ap); va_end(ap); show(line); return 0; }
static void gotoxy(unsigned char x, unsigned char y) { (void)x; (void)y; }
static unsigned char revers(unsigned char on) { (void)on; return 0; }
static void progress(const char* s, unsigned long d, unsigned long t)
{ (void)s; (void)d; (void)t; }
int main(int argc, char** argv) {
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active, copy[512];
    static char note[80];
    int i;
    key_typed = argv[1][0];
    disk = fopen(argv[2], "r+b");
    strcpy(selected.name, "/WIPE"); selected.access = 1; selected.mdate = 6;
    for (i = 3; i < argc; ++i) {
        char* v = strchr(argv[i], '=') + 1;
        if (!strncmp(argv[i], "other=", 6)) other = fopen(v, "r+b");
        else if (!strncmp(argv[i], "swap=answer", 11)) swap_answer = 1;
        else if (!strncmp(argv[i], "swap=", 5)) swap_read = atoi(v);
        else if (!strncmp(argv[i], "fail2=", 6)) fail2 = atoi(v);
        else if (!strncmp(argv[i], "word=", 5)) typed = v;
        else if (!strncmp(argv[i], "no=", 3)) yes = 0;
        else if (!strncmp(argv[i], "name=", 5)) strcpy(selected.name, v);
        else if (!strncmp(argv[i], "path=", 5)) { strcpy(panels[0].path, v); online = 1; }
        else if (!strncmp(argv[i], "twin=", 5)) { twin = 1; online = 1; }
        else return 2;
    }
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.copy_buf = copy; api.note = note; api.cfg_path = "/BOOT/A2FILE/A2FILE.CFG";
    api.input = input;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy;
    api.strcmp = strcmp; api.sprintf = sprintf; api.mli = mock_mli;
    api.cgetc = choose; api.confirm = confirm; api.message = message;
    api.prompt = prompt; api.cprintf = show_printf; api.gotoxy = gotoxy;
    api.revers = revers; api.progress_bar = progress;
    plugin_entry(&api);
    printf("%u %u %u\n%s\n%s\n", writes, swapped, reads_after, note, shown);
    fclose(disk); return 0;
}
'''

CHANGED = 'Disk changed or unreadable: /WIPE. Nothing written.'
BLANK = bytes(512)


class Wipe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='wipe-')
        cls.root = Path(cls.tmp.name)
        source = cls.root / 'test.c'
        source.write_text(HARNESS.replace('#include <stdio.h>', '#include <stdio.h>\n#include <stdarg.h>', 1))
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(source), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # -- fixtures ----------------------------------------------------------
    def volume(self, total=280, bitmap=6, name=b'WIPE', fill=0xA5):
        """A volume whose every block outside the header holds `fill`."""
        data = bytearray(bytes([fill]) * (512 * total))
        data[1024:1536] = bytes(512)
        data[1028] = 0xF0 | len(name)
        data[1029:1029 + len(name)] = name
        data[1059:1061] = bytes([39,13])
        data[1024 + 0x27:1024 + 0x29] = bitmap.to_bytes(2, 'little')
        data[1024 + 0x29:1024 + 0x2B] = total.to_bytes(2, 'little')
        return data

    def clean(self, name=b'WIPE', fill=0xA5, free=(), files=0, total=280):
        """A consistent volume: an all-allocated bitmap at block 6 but for
        the blocks of `free`, and `files` seedlings in the root."""
        data = Wipe.volume(self, total, name=name, fill=fill)
        data[3072:3584] = bytes(512)
        for block in free:
            data[3072 + block // 8] |= 0x80 >> (block & 7)
        for n in range(files):
            entry = 1024 + 4 + 39 * (1 + n)
            data[entry] = 0x11
            data[entry + 1] = ord('A') + n
            data[entry + 17:entry + 19] = (min(40, total - 8) + n).to_bytes(2, 'little')
        return data

    @staticmethod
    def zeroed(data, blocks):
        out = bytearray(data)
        for block in blocks:
            out[block * 512:block * 512 + 512] = BLANK
        return out

    def run_disks(self, key, data, other=None, *options):
        a, b = self.root / 'a.po', self.root / 'b.po'
        a.write_bytes(data)
        args = [str(self.exe), key, str(a)]
        if other is not None:
            b.write_bytes(other)
            args.append('other=' + str(b))
        output = subprocess.check_output(args + list(options), text=True, timeout=15)
        counts, note, shown = output.split('\n', 2)
        writes, swapped, reads = (int(n) for n in counts.split())
        return {'writes': writes, 'swapped': swapped, 'reads': reads, 'note': note.strip(),
                'shown': shown, 'a': a.read_bytes(), 'b': b.read_bytes() if other is not None else None}

    def run_wipe(self, data):
        r = self.run_disks('F', data)
        return r['writes'], r['note'], r['a']

    def assert_nothing_written(self, r, data, other=None, note=CHANGED):
        self.assertEqual(r['writes'], 0)
        self.assertEqual(r['a'], data)
        if other is not None:
            self.assertEqual(r['b'], other)
        self.assertEqual(r['note'], note)

    # -- the wipe itself, nothing swapped -------------------------------------
    def test_only_the_free_block_is_zeroed(self):
        data = self.volume()
        data[6 * 512:7 * 512] = bytes(512)
        data[6 * 512 + 20 // 8] = 0x80 >> (20 & 7)
        writes, note, after = self.run_wipe(data)
        data[20 * 512:21 * 512] = bytes(512)
        self.assertEqual(writes, 1)
        self.assertEqual(after, data)
        self.assertIn('1 blocks zeroed', note)

    def test_free_wipe_zeroes_every_free_block_and_nothing_else(self):
        free = list(range(30, 40)) + [279]
        data = self.clean(free=free, files=2)
        r = self.run_disks('F', data)
        self.assertEqual(r['writes'], len(free))
        self.assertEqual(r['a'], self.zeroed(data, free))
        self.assertEqual(r['note'], '11 blocks zeroed on /WIPE')
        self.assertIn('Zero every free block of /WIPE?', r['shown'])

    def test_whole_wipe_zeroes_the_volume(self):
        for options in ((), ('path=/WIPE/SUB/DIR',)):
            with self.subTest(options=options):
                data = self.clean(free=range(30, 40), files=2)
                r = self.run_disks('W', data, None, *options)
                self.assertEqual(r['writes'], 280)
                self.assertEqual(r['a'], bytes(280 * 512))
                self.assertEqual(r['note'], '280 blocks zeroed on /WIPE')
                self.assertIn(' EVERYTHING on /WIPE WILL BE LOST. ', r['shown'])

    def test_free_wipe_from_a_panel_path(self):
        data = self.clean(free=range(30, 40), files=2)
        r = self.run_disks('F', data, None, 'path=/WIPE/SUB')
        self.assertEqual(r['a'], self.zeroed(data, range(30, 40)))
        self.assertEqual(r['note'], '10 blocks zeroed on /WIPE')

    # -- the confirmations --------------------------------------------------
    def test_whole_wipe_needs_the_word_erase(self):
        for word in ('', 'erase', 'ERASED', 'YES'):
            with self.subTest(word=word):
                data = self.clean(free=range(30, 40))
                r = self.run_disks('W', data, None, 'word=' + word)
                self.assert_nothing_written(r, data, note='Nothing was written.')

    def test_free_wipe_declined_or_another_key_writes_nothing(self):
        data = self.clean(free=range(30, 40))
        self.assert_nothing_written(self.run_disks('F', data, None, 'no=1'), data,
                                    note='Nothing was written.')
        self.assert_nothing_written(self.run_disks('X', data), data, note='Nothing was written.')

    def test_whole_wipe_refuses_the_volume_of_the_program(self):
        data = self.clean(name=b'BOOT', free=range(30, 40))
        for options in (('name=/BOOT',), ('path=/BOOT/A2FILE',)):
            with self.subTest(options=options):
                r = self.run_disks('W', data, None, *options)
                self.assert_nothing_written(
                    r, data, note='That volume holds the running program: choose another.')

    # -- another disk in the drive -------------------------------------------
    def swap_cases(self):
        """The disk put in the drive instead of /WIPE: another volume, and
        the nastier twin -- the same name, other files."""
        yield 'other volume', self.clean(name=b'OTHR', fill=0x5A, free=range(20, 28), files=1)
        yield 'twin', self.clean(name=b'WIPE', fill=0x5A, free=range(20, 28), files=3)

    def test_whole_wipe_disk_swapped_at_the_erase_prompt(self):
        """W, ERASE typed with another disk in the drive.

        Before the fix (measured on 535682e): 280 writes, "280 blocks zeroed
        on /WIPE", and all 280 blocks of the disk swapped in were zeros --
        the other volume and the twin alike, /WIPE itself untouched."""
        for label, other in self.swap_cases():
            for options in ((), ('path=/WIPE/SUB',)):
                with self.subTest(disk=label, options=options):
                    data = self.clean(free=range(30, 40), files=2)
                    r = self.run_disks('W', data, other, 'swap=answer', *options)
                    self.assertEqual(r['swapped'], 1)
                    self.assert_nothing_written(r, data, other)

    def test_free_wipe_disk_swapped_at_the_confirmation(self):
        """F, Y answered with another disk in the drive.

        Before the fix (measured on 535682e): 8 writes, "8 blocks zeroed on
        /WIPE": the 8 free blocks of the disk swapped in (20-27) were
        zeros. Its own bitmap and the walk vouched for them, so only what a
        deleted file had left there died -- on a disk nobody named."""
        for label, other in self.swap_cases():
            for options in ((), ('path=/WIPE/SUB',)):
                with self.subTest(disk=label, options=options):
                    data = self.clean(free=range(30, 40), files=2)
                    r = self.run_disks('F', data, other, 'swap=answer', *options)
                    self.assertEqual(r['swapped'], 1)
                    self.assert_nothing_written(r, data, other)

    def test_free_wipe_disk_swapped_during_the_check(self):
        """F, the disk swapped at any block read between the confirmation
        and the last identity check, the walk included.

        Before the fix (measured on 535682e): whichever of the 15 reads
        that followed the answer the swap fell on (the 14 of the walk, then
        the bitmap page of the wipe), 8 writes, the 8 free blocks of the
        disk swapped in zeroed -- for a swap in the middle of the walk, free
        bits that no complete walk of that disk had vouched for."""
        data = self.clean(free=range(30, 40), files=2)
        reads = self.run_disks('F', data)['reads']
        # The reads after the answer: block 2 again, the 14 of the walk,
        # block 2 once more, then the bitmap page of the wipe itself -- that
        # last one is past the last check, where the writes begin (a swap
        # from there on is the limit wipe.c states).
        self.assertEqual(reads, 17)
        for label, other in self.swap_cases():
            for at in range(1, reads):
                with self.subTest(disk=label, read=at):
                    r = self.run_disks('F', data, other, 'swap=%d' % at)
                    self.assertEqual(r['swapped'], 1)
                    self.assert_nothing_written(r, data, other)

    def test_stale_volume_list_entry(self):
        """The volume list says /WIPE, the unit holds another disk from the
        start (a floppy changed since the list was read).

        Before the fix (measured on 535682e): the question named /WIPE and
        the disk in the drive paid -- W: 280 writes, every block zeroed;
        F: 8 writes, its 8 free blocks zeroed. Only the storage type of
        block 2 was looked at, never its name."""
        other = self.clean(name=b'OTHR', fill=0x5A, free=range(20, 28), files=1)
        for key in 'WF':
            with self.subTest(key=key):
                r = self.run_disks(key, other)
                self.assert_nothing_written(r, other)
                self.assertEqual(r['shown'].strip(), '')    # refused before any question

    TWIN = 'Two volumes named /WIPE: pick it in the volume list.'

    def test_two_volumes_of_one_name_refuse_a_panel_path(self):
        """Before (bench/hunt2_dupvol.py on POM2): two drives named /TWIN,
        the panel inside the 280-block one; W asked about it ("of 280 blocks
        free") and zeroed the 1600-block one, the first ON_LINE record with
        the name. Here the first record is the unit itself, and nothing at
        all is read or written: the name is refused whichever record comes
        first."""
        for key in 'WF':
            with self.subTest(key=key):
                data = self.clean(free=range(10, 14), files=1)
                r = self.run_disks(key, data, None, 'path=/WIPE/SUB', 'twin=1')
                self.assert_nothing_written(r, data, note=self.TWIN)
                self.assertEqual(r['shown'].strip(), '', 'nothing asked')

    def test_two_volumes_of_one_name_a_volume_list_row_still_wipes(self):
        """A row of the volume list carries its unit: the twin is not asked
        about and the wipe goes to that unit."""
        data = self.clean(free=range(10, 14), files=1)
        r = self.run_disks('W', data, None, 'twin=1')
        self.assertEqual(r['writes'], 280)
        self.assertEqual(r['a'], bytes(len(data)))

    def test_name_of_another_length_is_another_volume(self):
        for name in (b'WIP', b'WIPED', b'WIPE.2'):
            with self.subTest(name=name):
                other = self.clean(name=name, free=range(20, 28))
                self.assert_nothing_written(self.run_disks('W', other), other)

    def test_block_2_unreadable_after_the_answer(self):
        """Block 2 no longer reads once the question is answered (a door
        opened, a disk pulled out).

        Before the fix (measured on 535682e): W never looked again -- 280
        writes, the volume zeroed; F was already refused, by the walk, which
        reads block 2 first ("Free wipe refused...")."""
        for key in 'WF':
            with self.subTest(key=key):
                data = self.clean(free=range(30, 40), files=2)
                self.assert_nothing_written(self.run_disks(key, data, None, 'fail2=1'), data)
        # F, block 2 failing at the last check only, after a walk that read
        # it thirteen times: ZERO still holds the copy read after the answer
        # (no sapling index went through it), so a comparison of what the
        # buffer happens to hold would pass -- the read error must refuse.
        data = self.clean(free=range(30, 40), files=2)
        reads = self.run_disks('F', data)['reads']
        r = self.run_disks('F', data, None, 'fail2=%d' % (reads - 1))
        self.assertEqual(r['reads'], reads - 1)
        self.assert_nothing_written(r, data)

    def test_one_byte_of_block_2_is_another_disk(self):
        # The twin at its worst: block 2 differs by ONE byte -- the first,
        # the last, and both sides of the middle of the block, where the
        # comparison passes from one half to the other.
        data = self.clean(free=range(30, 40), files=2)
        for offset in (0, 1, 255, 256, 257, 510, 511):
            twin = self.clean(fill=0x5A, free=range(20, 28), files=2)
            twin[1024:1536] = data[1024:1536]
            twin[1024 + offset] ^= 0x40
            for key in 'WF':
                with self.subTest(offset=offset, key=key):
                    r = self.run_disks(key, data, twin, 'swap=answer')
                    self.assertEqual(r['swapped'], 1)
                    self.assert_nothing_written(r, data, twin)

    # -- F: the allocation pre-check ----------------------------------------
    def assert_refused(self, data):
        writes,note,after=self.run_wipe(data)
        self.assertEqual(writes,0)
        self.assertIn('refused',note)
        self.assertEqual(after,data)

    def test_metadata_marked_free_is_never_erased(self):
        for block in (0,1,2,6):
            with self.subTest(block=block):
                data=self.volume();data[3072:3584]=bytes(512)
                data[3072+block//8]|=0x80>>(block&7)
                self.assert_refused(data)

    def live_file(self,kind=1):
        data=self.volume();data[3072:3584]=bytes(512)
        data[1067]=kind<<4|1;data[1068]=ord('A')
        data[1084:1086]=(20).to_bytes(2,'little')
        return data

    def test_live_data_marked_free_is_never_erased(self):
        data=self.live_file();data[3072+20//8]=0x80>>(20&7)
        self.assert_refused(data)

    def test_sapling_data_marked_free_is_never_erased(self):
        data=self.live_file(2);data[20*512:21*512]=bytes(512)
        data[20*512]=21;data[3072+21//8]=0x80>>(21&7)
        self.assert_refused(data)

    def test_tree_data_marked_free_is_never_erased(self):
        data=self.live_file(3);data[20*512:22*512]=bytes(1024)
        data[20*512]=21;data[21*512]=22
        data[3072+22//8]=0x80>>(22&7)
        self.assert_refused(data)

    def test_unreadable_or_cyclic_directory_never_writes(self):
        for next_block in (2,280):
            data=self.volume();data[3072:3584]=bytes(512)
            data[1026:1028]=next_block.to_bytes(2,'little')
            self.assert_refused(data)

    def test_unknown_storage_refuses_free_wipe(self):
        self.assert_refused(self.live_file(5))

    def test_invalid_bitmap_location_never_writes(self):
        for total, bitmap in ((280, 0), (280, 1), (280, 2), (280, 280),
                              (280, 65535), (5000, 4999)):
            with self.subTest(total=total, bitmap=bitmap):
                data = self.volume(total, bitmap)
                writes, note, after = self.run_wipe(data)
                self.assertEqual(writes, 0)
                self.assertIn('Invalid volume bitmap', note)
                self.assertEqual(after, data)


# The same wipe.c as cc65 compiles it, under sim65. Sixteen-block volumes:
# two of them fit in the simulator's memory with the program, linked at
# $4000 so that BM, ZERO and HDR are where the overlay has them ($3000,
# $3200, $3400). argv: the key, then flags (s: swap at the answer, o: the
# second disk in the unit from the start), then the read after the answer at
# which to swap, then the one from which block 2 no longer reads (0: none).
# Output: both disks, then the writes, the reads after the answer, the note.
SIM_HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Bp { unsigned char n, unit; unsigned char* buf; unsigned int block; };
static unsigned char disks[2][16 * 512];
static unsigned char cur, answered, swap_answer, key_typed, twin, bypath;
static unsigned int writes, reads_after, swap_read, fail2;
static char input[17], note[80];
static void answer(void) { answered = 1; if (swap_answer) cur = 1; }
static unsigned char mli(unsigned char cmd, void* p)
{
    struct Bp* b = p;
    if (cmd == 0xC5 && (bypath || twin)) {   /* the unit's volume, twice with 't' */
        unsigned char* r = ((struct Bp*)p)->buf; unsigned char* h = disks[cur] + 1028;
        memset(r, 0, 256);
        r[0] = 0x60 | (h[0] & 15); memcpy(r + 1, h + 1, 15);
        if (twin) { r[16] = 0xE0 | (h[0] & 15); memcpy(r + 17, h + 1, 15); }
        return 0;
    }
    if (cmd != 0x80 && cmd != 0x81) return 0x27;
    if (b->n != 3 || b->unit != 0x60 || b->block >= 16) return 0x28;
    if (cmd == 0x80) {
        if (answered) {
            ++reads_after;
            if (reads_after == swap_read) cur = 1;
            if (fail2 && reads_after >= fail2 && b->block == 2) return 0x27;
        }
        memcpy(b->buf, disks[cur] + b->block * 512, 512);
        return 0;
    }
    ++writes;
    memcpy(disks[cur] + b->block * 512, b->buf, 512);
    return 0;
}
static char choose(void) { return key_typed; }
static unsigned char confirm(const char* s) { (void)s; answer(); return 1; }
static unsigned char prompt(const char* s, const char* d, unsigned char hex)
{ (void)s; (void)d; (void)hex; strcpy(input, "ERASE"); answer(); return 1; }
static void message(const char* s) { (void)s; }
static int shown(const char* f, ...) { (void)f; return 0; }
static void gotoxy(unsigned char x, unsigned char y) { (void)x; (void)y; }
static unsigned char revers(unsigned char on) { (void)on; return 0; }
static void progress(const char* s, unsigned long d, unsigned long t) { (void)s; (void)d; (void)t; }
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active, copy[512];
    FILE* f;
    (void)argc;
    f = fopen("disks.bin", "rb");
    if (!f || fread(disks, 1, sizeof disks, f) != sizeof disks) return 9;
    fclose(f);
    key_typed = argv[1][0];
    if (strchr(argv[2], 's')) swap_answer = 1;
    if (strchr(argv[2], 'o')) cur = 1;
    if (strchr(argv[2], 't')) twin = 1;
    if (strchr(argv[2], 'p')) { bypath = 1; strcpy(panels[0].path, "/WIPE"); }
    swap_read = atoi(argv[3]);
    fail2 = atoi(argv[4]);
    strcpy(selected.name, "/WIPE"); selected.access = 1; selected.mdate = 6;
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.copy_buf = copy; api.note = note; api.cfg_path = "/BOOT/A2FILE/A2FILE.CFG";
    api.input = input;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy;
    api.strcmp = strcmp; api.sprintf = sprintf; api.mli = mli;
    api.cgetc = choose; api.confirm = confirm; api.message = message;
    api.prompt = prompt; api.cprintf = shown; api.gotoxy = gotoxy;
    api.revers = revers; api.progress_bar = progress;
    plugin_entry(&api);
    fwrite(disks, 1, sizeof disks, stdout);
    printf("%u %u\n%s\n", writes, reads_after, note);
    return 0;
}
'''


def toolchains():
    """(target, cl65, sim65, environment, cfg directory) per edition: the
    machine's cc65 for the 65C02 one, cc65 master for the 6502 one."""
    found = []
    if shutil.which('cl65') and shutil.which('sim65'):
        target = Path(subprocess.check_output(['cl65', '--print-target-path'], text=True).strip())
        found.append(('sim65c02', shutil.which('cl65'), shutil.which('sim65'), {}, target.parent / 'cfg'))
    if (HEAD / 'bin/cl65').exists():
        found.append(('sim6502', str(HEAD / 'bin/cl65'), str(HEAD / 'bin/sim65'),
                      {'CC65_HOME': str(HEAD / 'share/cc65')}, HEAD / 'share/cc65/cfg'))
    return found


class WipeCc65(unittest.TestCase):
    """What cc65 made of it: the same refusals and the same wipes, byte for
    byte, by the compiler of each edition and at the real buffer addresses."""
    SIZE = 16 * 512

    @classmethod
    def setUpClass(cls):
        chains = toolchains()
        if not chains:
            raise unittest.SkipTest('no cc65 toolchain')
        cls.tmp = tempfile.TemporaryDirectory(prefix='wipe-cc65-')
        d = cls.dir = Path(cls.tmp.name)
        (d / 'harness.c').write_text(SIM_HARNESS)
        # Copies: cl65 writes a .s beside a .c, and wipe.c wants ../a2fc_plugin.h.
        (d / 'p').mkdir()
        shutil.copyfile(ROOT / 'src/plugins/wipe.c', d / 'p/wipe_c.c')
        shutil.copyfile(ROOT / 'src/plugins/spin.h', d / 'p/spin.h')
        shutil.copyfile(ROOT / 'src/a2fc_plugin.h', d / 'a2fc_plugin.h')
        cls.exe = {}
        for cpu, cl65, sim65, env, cfgdir in chains:
            cfg, n = re.subn(r'start = \$0200, size = [^;]*;',
                             'start = $4000, size = $C000 - $4000 - __STACKSIZE__;',
                             (cfgdir / f'{cpu}.cfg').read_text())
            assert n == 1, cpu
            cfg = cfg.replace('    RODATA:', '    OVLHDR:   load = MAIN, type = ro;\n    RODATA:', 1)
            (d / f'{cpu}.cfg').write_text(cfg)
            exe = d / f'wipe-{cpu}'
            env = {**os.environ, **env}
            # The Makefile's flags for an overlay.
            subprocess.run([cl65, '-t', cpu, '-C', str(d / f'{cpu}.cfg'), '-O', '-Oirs', '-Cl',
                            '--codesize', '100', '-o', str(exe), str(d / 'harness.c'),
                            str(d / 'p/wipe_c.c')], check=True, cwd=d, env=env, capture_output=True)
            cls.exe[cpu] = (sim65, exe, env)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def small(self, **kw):
        return bytes(Wipe.clean(None, total=16, **kw))

    def both(self, key, a, b, flags='-', swap=0, fail=0):
        """The run by each compiler: (disk a, disk b, writes, reads, note), the same for both."""
        (self.dir / 'disks.bin').write_bytes(a + b)
        got = {}
        for cpu, (sim65, exe, env) in self.exe.items():
            p = subprocess.run([sim65, str(exe), key, flags, str(swap), str(fail)], cwd=self.dir, env=env,
                               capture_output=True, timeout=120)
            self.assertEqual(p.returncode, 0, (cpu, p.stderr))
            counts, note = p.stdout[2 * self.SIZE:].decode().split('\n')[:2]
            writes, reads = (int(n) for n in counts.split())
            got[cpu] = (p.stdout[:self.SIZE], p.stdout[self.SIZE:2 * self.SIZE], writes, reads, note)
        self.assertEqual(len(set(got.values())), 1, 'the two compilers disagree')
        return next(iter(got.values()))

    def assert_untouched(self, result, a, b, note=CHANGED):
        self.assertEqual(result[2], 0)
        self.assertEqual(result[0], a)
        self.assertEqual(result[1], b)
        self.assertEqual(result[4], note)

    def test_the_wipes_still_wipe(self):
        a, b = self.small(free=range(10, 14), files=1), self.small(name=b'OTHR', fill=0x5A)
        after = self.both('W', a, b)
        self.assertEqual(after[:3], (bytes(self.SIZE), b, 16))
        self.assertEqual(after[4], '16 blocks zeroed on /WIPE')
        after = self.both('F', a, b)
        self.assertEqual(after[:3], (bytes(Wipe.zeroed(a, range(10, 14))), b, 4))
        self.assertEqual(after[4], '4 blocks zeroed on /WIPE')

    def test_one_byte_of_block_2_is_another_disk(self):
        # The twin at its worst: block 2 differs by ONE byte -- the first,
        # the last, and both sides of the half-block boundary the comparison
        # loop straddles.
        a = self.small(free=range(10, 14), files=1)
        for offset in (0, 1, 255, 256, 257, 510, 511):
            twin = bytearray(self.small(fill=0x5A, free=range(8, 12), files=1))
            twin[1024:1536] = a[1024:1536]
            twin[1024 + offset] ^= 0x40
            twin = bytes(twin)
            for key in 'WF':
                with self.subTest(offset=offset, key=key):
                    self.assert_untouched(self.both(key, a, twin, 's'), a, twin)

    def test_another_volume_at_the_answer_or_during_the_check(self):
        a = self.small(free=range(10, 14), files=1)
        b = self.small(name=b'OTHR', fill=0x5A, free=range(8, 12))
        self.assert_untouched(self.both('W', a, b, 's'), a, b)
        self.assert_untouched(self.both('F', a, b, 's'), a, b)
        reads = self.both('F', a, b)[3]
        for at in range(1, reads):          # the last read is the wipe's own bitmap page
            with self.subTest(read=at):
                self.assert_untouched(self.both('F', a, b, '-', at), a, b)

    def test_two_volumes_of_one_name_refuse_a_panel_path(self):
        a = self.small(free=range(10, 14), files=1)
        b = self.small(name=b'OTHR', fill=0x5A)
        for key in 'WF':
            with self.subTest(key=key):
                self.assert_untouched(self.both(key, a, b, 'pt'), a, b, Wipe.TWIN)
        after = self.both('W', a, b, 'p')
        self.assertEqual(after[:3], (bytes(self.SIZE), b, 16))

    def test_stale_list_entry_and_unreadable_block_2(self):
        a = self.small(free=range(10, 14), files=1)
        b = self.small(name=b'OTHR', fill=0x5A, free=range(8, 12))
        for key in 'WF':
            with self.subTest(key=key):
                self.assert_untouched(self.both(key, a, b, 'o'), a, b)     # the unit holds /OTHR
                self.assert_untouched(self.both(key, a, b, fail=1), a, b)
        # F: block 2 failing at the last check only (see the host test).
        reads = self.both('F', a, b)[3]
        after = self.both('F', a, b, fail=reads - 1)
        self.assertEqual(after[3], reads - 1)
        self.assert_untouched(after, a, b)


if __name__ == '__main__':
    unittest.main()
