"""Execute the shipped IMGPUT C: a ProDOS file written INTO a ProDOS image,
on disposable images only, and through I/O faults.

What matters is what an interruption costs. The order the overlay promises
is data, then bitmap, then the directory entry, so:
  - a failure before the bitmap write must leave the image byte for byte as
    it was -- the blocks written to were free and stay free;
  - a failure after it must leave the volume still consistent, the space
    lost and nothing else, never an entry pointing at blocks the bitmap
    calls free.
Every write is broken in turn and the image is read back with
tools/prodos_read.py to check which of the two happened.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from po22mg import to_2mg
from po2dsk import to_dsk
from prodos_read import Image

ROOT = Path(__file__).resolve().parents[1]

C = r'''
#define __fastcall__
#define PLUGIN_HOST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#undef memcpy
#undef memset
#undef strcpy
#undef sprintf
struct A2fcApi;
#include "src/plugins/imgput.c"

static struct Panel panels[2];
static struct Entry sel;
static struct DirEntry de;
static unsigned char scratch[512], act;
static char note_text[160], full_path[280], reselect_text[64];
static char img_path[280];
static int mode, fail_at, writes;
static long img_size;

/* mode 1: answer No. 2: the nth fwrite fails. 3: the nth fwrite writes
 * half. 4: the nth fwrite comes back different (a bad read-back). */
static FILE* h_fopen(const char* p, const char* m) { return fopen(p, m); }
static size_t h_fwrite(const void* p, size_t s, size_t n, FILE* f) {
    ++writes;
    if (mode == 2 && writes == fail_at) return 0;
    if (mode == 3 && writes == fail_at) { fwrite(p, 1, 128, f); fflush(f); return 0; }
    if (mode == 4 && writes == fail_at) {
        unsigned char copy[512];
        memcpy(copy, p, s * n); copy[0] ^= 0xFF;
        return fwrite(copy, s, n, f) == n ? n : 0;
    }
    return fwrite(p, s, n, f);
}
static unsigned char h_confirm(const char* s) { (void)s; return mode != 1; }
static void h_message(const char* s) { (void)s; }

/* The one directory read the overlay makes is imageio's size_of, looking
 * for the image file to learn its length. */
static int dir_step;
static unsigned char h_dir_open(const char* p) { (void)p; dir_step = 0; return 1; }
static unsigned char h_dir_next(void) {
    const char* slash = strrchr(img_path, '/');
    if (dir_step++) return 0;
    strcpy(de.name, slash ? slash + 1 : img_path);
    de.size = img_size; de.type = 6; de.key = 0;
    return 1;
}
static void h_dir_close(void) {}

int main(int argc, char** argv) {
    struct A2fcApi api; FILE* f;
    memset(&api, 0, sizeof api);
    strcpy(img_path, argv[1]);
    strcpy(full_path, argv[2]);
    mode = atoi(argv[3]); fail_at = atoi(argv[4]);
    strcpy(sel.name, argv[5]);
    sel.type = (unsigned char)atoi(argv[6]);
    sel.aux = (unsigned int)atoi(argv[7]);
    sel.access = 0xE3; sel.mdate = 0x2F19;
    f = fopen(full_path, "rb");
    if (f) { fseek(f, 0, SEEK_END); sel.size = ftell(f); fclose(f); }
    f = fopen(img_path, "rb");
    if (!f) return 9;
    fseek(f, 0, SEEK_END); img_size = ftell(f); fclose(f);

    panels[0].fs = FS_PRODOS;
    panels[1].fs = FS_IMG;
    strcpy(panels[1].path, img_path);
    panels[1].img_len = (unsigned char)strlen(img_path);
    panels[1].dir_key = (unsigned int)atoi(argv[8]);
    if (argc > 9 && atoi(argv[9])) panels[1].fs = FS_PRODOS;   /* wrong panel */

    api.panels = panels; api.active = &act; api.selected = &sel;
    api.full = full_path; api.copy_buf = scratch;
    api.note = note_text; api.reselect = reselect_text;
    api.dir_entry = &de;
    api.dir_open = h_dir_open; api.dir_next = h_dir_next; api.dir_close = h_dir_close;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy;
    api.strcmp = strcmp; api.strlen = strlen; api.sprintf = sprintf;
    api.fopen = h_fopen; api.fread = fread; api.fwrite = h_fwrite;
    api.fclose = fclose; api.fseek = fseek;
    api.confirm = h_confirm; api.message = h_message;
    plugin_entry(&api);
    printf("%d %s\n", writes, note_text);
    return 0;
}
'''


def make_image(blocks=280, name='TEST'):
    """A real ProDOS volume, written by tools/mkvolume.py.

    It used to be built here, by hand. That made the fixture and the overlay
    share one assumption -- both read the volume header with a file entry's
    offsets -- so this test passed while the overlay refused every real
    image. An independent writer is the point of a fixture.
    """
    with tempfile.TemporaryDirectory(prefix='mkvol') as d:
        stage = Path(d) / 'stage'
        stage.mkdir()
        out = Path(d) / 'v.po'
        subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(out),
                        '--volume', name, '--blocks', str(blocks)],
                       check=True, capture_output=True)
        return out.read_bytes()


def bitmap_at(data):
    return int.from_bytes(data[2 * 512 + 4 + 0x23:2 * 512 + 4 + 0x25], 'little')


def file_count(data):
    return int.from_bytes(data[2 * 512 + 4 + 0x21:2 * 512 + 4 + 0x23], 'little')


def free_blocks(data, blocks=280):
    bm = bitmap_at(data) * 512
    return sum(1 for b in range(blocks) if data[bm + (b & 0xFFF) // 8] & (0x80 >> (b & 7)))


class ImgPut(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='imgput-build-')
        p = Path(cls.tmp.name)
        (p / 'test.c').write_text(C)
        cls.exe = p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(p / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        # ProDOS paths stop at 64 characters and so does imageio's buffer:
        # the usual macOS temp directory is longer than that on its own, so
        # these disposable images live under a short one.
        self.case = tempfile.TemporaryDirectory(prefix='ip', dir='/tmp')
        self.addCleanup(self.case.cleanup)
        self.dir = Path(self.case.name)
        self.img = self.dir / 'DISK.PO'
        self.original = make_image()
        self.img.write_bytes(self.original)
        self.payload = b'a line of the source file\r' * 30      # 780 bytes: a sapling
        self.src = self.dir / 'SRC'
        self.src.write_bytes(self.payload)

    def run_op(self, mode=0, at=1, name='HELLO', typ=4, aux=0, key=2, wrong=0):
        out = subprocess.check_output(
            [str(self.exe), str(self.img), str(self.src), str(mode), str(at),
             name, str(typ), str(aux), str(key), str(wrong)], text=True).strip()
        self.assertEqual(self.src.read_bytes(), self.payload)    # never touched
        n, _, note = out.partition(' ')
        return int(n), note

    def entry(self, name='HELLO'):
        im = Image(self.img.read_bytes())
        return next((e for e in im.entries(2)
                     if e[1:1 + (e[0] & 15)].decode() == name), None)

    # -- what must happen ---------------------------------------------------

    def test_a_file_lands_in_the_image_with_its_bytes_and_its_entry(self):
        writes, note = self.run_op(typ=4, aux=0x1234)
        self.assertIn('Copied into the image', note)
        im = Image(self.img.read_bytes())
        e = self.entry()
        self.assertIsNotNone(e, note)
        self.assertEqual(e[0] >> 4, 2)                       # a sapling
        self.assertEqual(e[0x10], 4)                         # its ProDOS type
        self.assertEqual(int.from_bytes(e[0x1F:0x21], 'little'), 0x1234)
        self.assertEqual(int.from_bytes(e[0x15:0x18], 'little'), len(self.payload))
        self.assertEqual(im.read(e)[:len(self.payload)], self.payload)
        self.assertEqual(int.from_bytes(e[0x25:0x27], 'little'), 2)   # header pointer

    def test_the_volume_header_counts_the_new_file(self):
        self.run_op()
        d = self.img.read_bytes()
        self.assertEqual(file_count(d), 1)

    def test_the_blocks_it_took_are_no_longer_free(self):
        before = free_blocks(self.original)
        writes, note = self.run_op()
        after = free_blocks(self.img.read_bytes())
        e = self.entry()
        self.assertEqual(before - after, int.from_bytes(e[0x13:0x15], 'little'))
        self.assertEqual(before - after, 3)                  # index + two data blocks

    def test_a_short_file_is_a_seedling(self):
        self.src.write_bytes(b'short\r')
        self.payload = b'short\r'
        self.run_op()
        e = self.entry()
        self.assertEqual(e[0] >> 4, 1)
        self.assertEqual(int.from_bytes(e[0x13:0x15], 'little'), 1)

    def test_two_files_do_not_share_a_block(self):
        self.run_op(name='ONE')
        self.run_op(name='TWO')
        im = Image(self.img.read_bytes())
        got = [im.read(self.entry(n))[:len(self.payload)] for n in ('ONE', 'TWO')]
        self.assertEqual(got, [self.payload, self.payload])
        self.assertEqual(free_blocks(self.original) - free_blocks(self.img.read_bytes()), 6)

    def test_the_containers_that_move_the_blocks_around(self):
        """A .PO is the flat case. A .2MG puts a header in front of the
        volume and a .DSK stores the halves of every block in DOS sector
        order: writing has to undo exactly what reading does, and nothing
        exercised either of those paths before."""
        for suffix, wrap, unwrap in (
                ('.2MG', to_2mg, lambda d: d[int.from_bytes(d[24:26], 'little'):]),
                ('.DSK', to_dsk, lambda d: to_dsk(d))):   # the order is its own inverse
            with self.subTest(suffix=suffix):
                img = self.dir / ('DISK' + suffix)
                img.write_bytes(wrap(self.original))
                before = img.read_bytes()
                out = subprocess.check_output(
                    [str(self.exe), str(img), str(self.src), '0', '1',
                     'HELLO', '4', '0', '2', '0'], text=True).strip()
                self.assertIn('Copied', out)
                after = img.read_bytes()
                self.assertEqual(len(after), len(before))
                if suffix == '.2MG':
                    self.assertEqual(after[:64], before[:64], 'the 2MG header moved')
                im = Image(unwrap(after))
                e = next(x for x in im.entries(2)
                         if x[1:1 + (x[0] & 15)].decode() == 'HELLO')
                self.assertEqual(im.read(e)[:len(self.payload)], self.payload)

    # -- what must not ------------------------------------------------------

    def test_answering_no_writes_nothing(self):
        writes, note = self.run_op(mode=1)
        self.assertEqual(writes, 0, note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_a_name_already_there_is_refused(self):
        self.run_op(name='TAKEN')
        saved = self.img.read_bytes()
        writes, note = self.run_op(name='TAKEN')
        self.assertIn('No room for that name', note)
        self.assertEqual(self.img.read_bytes(), saved)

    def test_the_wrong_panels_are_refused(self):
        writes, note = self.run_op(wrong=1)
        self.assertEqual(writes, 0, note)
        self.assertIn('ProDOS image opposite', note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_an_image_that_is_not_prodos_is_refused(self):
        self.img.write_bytes(bytes(280 * 512))
        writes, note = self.run_op()
        self.assertEqual(writes, 0, note)
        self.assertIn('Not a ProDOS image', note)

    def test_a_disk_without_room_is_refused(self):
        """Every block but two is taken: a three-block file cannot fit, and
        the refusal must come before anything is written."""
        d = bytearray(self.original)
        bm = bitmap_at(self.original) * 512
        for b in range(280):
            if b > 8:
                d[bm + (b & 0xFFF) // 8] &= ~(0x80 >> (b & 7))
        self.img.write_bytes(bytes(d))
        untouched = self.img.read_bytes()
        writes, note = self.run_op()
        self.assertEqual(writes, 0, note)
        self.assertIn('Not enough free blocks', note)
        self.assertEqual(self.img.read_bytes(), untouched)

    def test_a_lying_bitmap_never_gets_the_directory_overwritten(self):
        """A bitmap that calls the volume directory or the bitmap itself
        free is not a reason to write there. ProDOS trusts the bitmap and
        would; an image with a damaged one is what FIXIT is for, and
        handing it a file on top of its own directory destroys the volume.

        Measured before the floor existed: with blocks 1 to 6 marked free,
        the file went over the directory and the bitmap and the volume did
        not read back at all."""
        bm = bitmap_at(self.original) * 512
        for lo, hi in ((1, 7), (0, 7), (6, 7), (2, 6)):
            with self.subTest(free=(lo, hi)):
                d = bytearray(self.original)
                for b in range(lo, hi):
                    d[bm + (b & 0xFFF) // 8] |= 0x80 >> (b & 7)
                self.img.write_bytes(bytes(d))
                writes, note = self.run_op()
                self.assertIn('Copied', note)
                e = self.entry()
                self.assertIsNotNone(e, note)
                # it reads back, and nothing of it lives among the reserved
                im = Image(self.img.read_bytes())
                self.assertEqual(im.read(e)[:len(self.payload)], self.payload)
                key = int.from_bytes(e[0x11:0x13], 'little')
                idx = self.img.read_bytes()[key * 512:(key + 1) * 512]
                used = [key] + [idx[i] | (idx[256 + i] << 8)
                                for i in range(-(-len(self.payload) // 512))]
                self.assertTrue(all(b >= 7 for b in used), used)

    def test_a_failure_before_the_bitmap_leaves_the_image_untouched(self):
        """The data blocks go into space the bitmap still calls free, so a
        cut there costs nothing at all: the image must come back identical
        once the bitmap and the directory are still as they were."""
        for mode in (2, 3, 4):
            for at in range(1, 4):                 # the data and index writes
                with self.subTest(mode=mode, at=at):
                    self.img.write_bytes(self.original)
                    writes, note = self.run_op(mode=mode, at=at)
                    self.assertNotIn('Copied', note)
                    d = self.img.read_bytes()
                    # the bitmap and the whole directory chain are untouched
                    self.assertEqual(d[2 * 512:7 * 512], self.original[2 * 512:7 * 512])
                    self.assertIsNone(self.entry())

    def test_a_failure_after_the_bitmap_never_leaves_a_dangling_entry(self):
        """From the bitmap write on, space can be lost -- but an entry must
        never name blocks the bitmap still calls free."""
        for mode in (2, 3, 4):
            for at in range(4, 8):
                with self.subTest(mode=mode, at=at):
                    self.img.write_bytes(self.original)
                    writes, note = self.run_op(mode=mode, at=at)
                    e = self.entry()
                    if e is None:
                        continue                   # nothing claims anything
                    d = self.img.read_bytes()
                    key = int.from_bytes(e[0x11:0x13], 'little')
                    bm = bitmap_at(d) * 512
                    self.assertFalse(d[bm + (key & 0xFFF) // 8] & (0x80 >> (key & 7)),
                                     'the entry names a block the bitmap calls free')
                    self.assertIn('Copied', note)


if __name__ == '__main__':
    unittest.main()
