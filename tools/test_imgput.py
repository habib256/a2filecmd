"""Execute the shipped IMGPUT C: a ProDOS file written INTO a ProDOS image,
on disposable images only, and through I/O faults.

What matters is what an interruption costs, and what a damaged image costs.
The order the overlay promises is data, then bitmap, then the directory
entry, so:
  - a failure before the bitmap write must leave every file, every
    directory and the bitmap of the image byte for byte as they were -- the
    blocks written to were free, nothing named them, and they stay free;
  - a failure after it must leave the volume still consistent, the space
    lost and nothing else, never an entry pointing at blocks the bitmap
    calls free.
And before any of that, the image itself must deserve to be written into:
every block its directories and files name must be marked used. An image
that fails that gets NOTHING written, and the tests below compare the whole
image, not the message.

Every write is broken in turn and the image is read back with
tools/prodos_read.py and judged by tools/prodos_check.py, which share
nothing with the overlay.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import prodos_check
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
#include <unistd.h>
#undef memcpy
#undef memset
#undef strcpy
#undef sprintf
struct A2fcApi;
#include "src/plugins/imgput.c"
#ifndef SPIN_H                  /* an IMGPUT from before it gave signs of life */
static unsigned long spins;
#endif

static struct Panel panels[2];
static struct Entry sel;
static struct DirEntry de;
static unsigned char scratch[512], act;
static char note_text[160], full_path[280], reselect_text[64];
static char img_path[280];
static int mode, fail_at, writes;
static long img_size;
static FILE *img_file, *src_file;
static int img_reads, src_reads, src_opens;

static long env_long(const char* name, long missing) {
    const char* v = getenv(name);
    return v ? atol(v) : missing;
}

/* "offset:and:or,offset:and:or": bytes of the image changed behind the
 * overlay's back, by somebody who opened it on their own. */
static void poke(const char* list) {
    FILE* f; long at; unsigned int and_, or_; int c;
    if (!list || !*list) return;
    f = fopen(img_path, "r+b");
    while (sscanf(list, "%ld:%x:%x", &at, &and_, &or_) == 3) {
        fseek(f, at, SEEK_SET); c = fgetc(f);
        fseek(f, at, SEEK_SET); fputc((c & and_) | or_, f);
        list = strchr(list, ',');
        if (!list) break;
        ++list;
    }
    fclose(f);
}

/* The image is opened unbuffered: what the overlay reads is what the file
 * holds at that instant, pokes included. SRC_AT_OPEN="n:size" resizes the
 * source just before its nth open -- between the count and the copy. */
static FILE* h_fopen(const char* p, const char* m) {
    FILE* f;
    if (!strcmp(p, full_path)) {
        long n, size;
        const char* v = getenv("SRC_AT_OPEN");
        ++src_opens;
        if (v && sscanf(v, "%ld:%ld", &n, &size) == 2 && n == src_opens) truncate(p, size);
        if (env_long("SRC_NO_OPEN", 0) == src_opens) return NULL;
    }
    f = fopen(p, m);
    if (f && !strcmp(p, img_path)) { setvbuf(f, NULL, _IONBF, 0); img_file = f; }
    if (f && !strcmp(p, full_path)) src_file = f;
    return f;
}
static int h_fclose(FILE* f) {
    if (f == img_file) img_file = NULL;
    if (f == src_file) src_file = NULL;
    return fclose(f);
}
/* BAD_BLOCK: that block of a .PO cannot be read. ESC_AT: the user presses
 * ESC as the nth block of the image is read. SRC_FAIL_READ: the nth read of
 * the source fails. */
static size_t h_fread(void* p, size_t s, size_t n, FILE* f) {
    if (f == img_file) {
        ++img_reads;
        if (env_long("ESC_AT", 0) == img_reads) cancelled = 1;
        if (env_long("BAD_BLOCK", -1) * 512 == ftell(f)) return 0;
    }
    if (f == src_file) {
        ++src_reads;
        /* a read ERROR, not a short file: writing to a stream opened for
         * reading is what sets the error flag on a host */
        if (env_long("SRC_FAIL_READ", 0) == src_reads) { fputc(0, f); return 0; }
    }
    return fread(p, s, n, f);
}
/* mode 1: answer No. 2: the nth fwrite fails. 3: the nth fwrite writes
 * half. 4: the nth fwrite comes back different (a bad read-back).
 * POKE_AT_WRITE="n;pokes": the image changes just before the nth write. */
static size_t h_fwrite(const void* p, size_t s, size_t n, FILE* f) {
    const char* v = getenv("POKE_AT_WRITE");
    ++writes;
    if (v && atoi(v) == writes) poke(strchr(v, ';') + 1);
    if (mode == 2 && writes == fail_at) return 0;
    if (mode == 3 && writes == fail_at) { fwrite(p, 1, 128, f); fflush(f); return 0; }
    if (mode == 4 && writes == fail_at) {
        unsigned char copy[512];
        memcpy(copy, p, s * n); copy[0] ^= 0xFF;
        return fwrite(copy, s, n, f) == n ? n : 0;
    }
    return fwrite(p, s, n, f);
}
/* The question: what was written before it, and what the image becomes
 * while it waits (POKE_AT_CONFIRM). */
static unsigned char h_confirm(const char* s) {
    fprintf(stderr, "ASK %d %d %s\n", writes, img_reads, s);
    if (mode == 1) return 0;
    poke(getenv("POKE_AT_CONFIRM"));
    return 1;
}
static void h_message(const char* s) { fprintf(stderr, "MSG %s\n", s); }
static void h_bar(const char* s, unsigned long n, unsigned long t) { fprintf(stderr, "BAR %s %lu %lu\n", s, n, t); }

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
    /* what the panel remembers of the file, when that is not what it holds */
    sel.size = env_long("PANEL_SIZE", sel.size);
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
    api.fopen = h_fopen; api.fread = h_fread; api.fwrite = h_fwrite;
    api.fclose = h_fclose; api.fseek = fseek;
    api.confirm = h_confirm; api.message = h_message; api.progress_bar = h_bar;
    plugin_entry(&api);
    fprintf(stderr, "SPIN %lu\nREADS %d\n", spins, img_reads);
    printf("%d %s\n", writes, note_text);
    return 0;
}
'''


def make_image(blocks=280, name='TEST', files=None):
    """A real ProDOS volume, written by tools/mkvolume.py.

    It used to be built here, by hand. That made the fixture and the overlay
    share one assumption -- both read the volume header with a file entry's
    offsets -- so this test passed while the overlay refused every real
    image. An independent writer is the point of a fixture.

    `files` maps a path inside the volume to its bytes; a path with a slash
    makes the directories it needs.
    """
    with tempfile.TemporaryDirectory(prefix='mkvol') as d:
        stage = Path(d) / 'stage'
        stage.mkdir()
        for rel, data in (files or {}).items():
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            (stage / rel).write_bytes(data)
        out = Path(d) / 'v.po'
        subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(out),
                        '--volume', name, '--blocks', str(blocks)],
                       check=True, capture_output=True)
        return out.read_bytes()


def word(data, at):
    return int.from_bytes(data[at:at + 2], 'little')


def bitmap_at(data):
    return word(data, 2 * 512 + 4 + 0x23)


def file_count(data, key=2):
    return word(data, key * 512 + 4 + 0x21)


def is_free(data, b):
    return bool(data[bitmap_at(data) * 512 + (b >> 3)] & (0x80 >> (b & 7)))


def set_free(data, b, free=True):
    """Marks block b in the bitmap of a bytearray image (under 4,096 blocks)."""
    at = bitmap_at(data) * 512 + (b >> 3)
    if free:
        data[at] |= 0x80 >> (b & 7)
    else:
        data[at] &= ~(0x80 >> (b & 7)) & 0xFF


def free_blocks(data, blocks=280):
    return sum(1 for b in range(blocks) if is_free(data, b))


def name_of(e):
    return e[1:1 + (e[0] & 15)].decode()


def find(data, name, key=2):
    """The entry called `name` in the directory at `key`, or None."""
    return next((e for e in Image(data).entries(key) if name_of(e) == name), None)


def key_of(e):
    return word(e, 0x11)


def findings(data):
    return sorted((f.id, f.block) for f in prodos_check.check(bytes(data)).findings)


KEEP = b'precious\r' * 100                  # 900 bytes: a sapling of two blocks
OTHER = b'other file\r' * 10                # a seedling
LEAF = b'three directories down\r'
BIG = bytes((i * 7 + i // 512) & 255 for i in range(140000))   # a tree: 274 blocks
RES = b'resource fork\r' * 80               # 1,120 bytes: a sapling of three


def orchard():
    """An 800-block volume holding one of everything the walk must follow.

    A seedling and a tree at the root, a subdirectory with a sapling and a
    directory of its own, and -- by hand, since mkvolume.py writes none --
    an extended file: a key block with a seedling data fork and a sapling
    resource fork. tools/prodos_check.py must find nothing to say about it
    before any test uses it.
    """
    d = bytearray(make_image(800, 'ORCHARD', {
        'OTHER.TXT#040000': OTHER, 'BIG.BIN#060000': BIG,
        'SUB/KEEP.TXT#040000': KEEP, 'SUB/DEEP/LEAF#040000': LEAF}))
    free = [b for b in range(800) if is_free(d, b)]
    xkey, dfork, ridx, r0, r1, r2 = free[:6]
    for b in free[:6]:
        set_free(d, b, False)
    d[dfork * 512:dfork * 512 + 5] = b'data\r'
    for i, b in enumerate((r0, r1, r2)):
        d[ridx * 512 + i] = b & 255
        d[ridx * 512 + 256 + i] = b >> 8
        chunk = RES[i * 512:(i + 1) * 512]
        d[b * 512:b * 512 + len(chunk)] = chunk
    d[xkey * 512:xkey * 512 + 8] = bytes([1]) + dfork.to_bytes(2, 'little') + (1).to_bytes(2, 'little') + (5).to_bytes(3, 'little')
    d[xkey * 512 + 256:xkey * 512 + 264] = (bytes([2]) + ridx.to_bytes(2, 'little') + (4).to_bytes(2, 'little')
                                             + len(RES).to_bytes(3, 'little'))
    # its entry, in the first free slot of the volume directory
    template = bytearray(find(d, 'OTHER.TXT'))
    e = bytearray(39)
    e[0] = 0x50 | 5
    e[1:6] = b'FORKS'
    e[0x10] = 0xB3
    e[0x11:0x13] = xkey.to_bytes(2, 'little')
    e[0x13:0x15] = (6).to_bytes(2, 'little')
    e[0x15:0x18] = (512).to_bytes(3, 'little')
    e[0x18:0x27] = template[0x18:0x27]
    for slot in range(1, 13):
        at = 2 * 512 + 4 + slot * 39
        if not d[at] >> 4:
            d[at:at + 39] = e
            break
    else:
        raise AssertionError('no free slot in block 2')
    d[2 * 512 + 4 + 0x21:2 * 512 + 4 + 0x23] = (file_count(d) + 1).to_bytes(2, 'little')
    assert findings(d) == [], findings(d)
    return bytes(d)


class Harness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='imgput-build-')
        p = Path(cls.tmp.name)
        (p / 'test.c').write_text(C)
        cls.exe = p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-D_DARWIN_C_SOURCE',
                        '-D_DEFAULT_SOURCE', '-I', str(ROOT),
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
        self.original = self.fixture()
        self.img.write_bytes(self.original)
        self.payload = b'a line of the source file\r' * 30      # 780 bytes: a sapling
        self.src = self.dir / 'SRC'
        self.src.write_bytes(self.payload)

    def fixture(self):
        return make_image()

    def run_op(self, mode=0, at=1, name='HELLO', typ=4, aux=0, key=2, wrong=0,
               img=None, source_kept=True, **env):
        run = subprocess.run(
            [str(self.exe), str(img or self.img), str(self.src), str(mode), str(at),
             name, str(typ), str(aux), str(key), str(wrong)], text=True,
            capture_output=True, check=True,
            env={**os.environ, **{k: str(v) for k, v in env.items()}})
        out = run.stdout.strip()
        err = run.stderr.splitlines()
        self.bars = [l.split()[1:] for l in err if l.startswith('BAR ')]
        self.asked = [l for l in err if l.startswith('ASK ')]
        self.messages = [l[4:] for l in err if l.startswith('MSG ')]
        self.spins = next(int(l.split()[1]) for l in err if l.startswith('SPIN '))
        self.reads = next(int(l.split()[1]) for l in err if l.startswith('READS '))
        if source_kept:
            self.assertEqual(self.src.read_bytes(), self.payload)    # never touched
        n, _, note = out.partition(' ')
        return int(n), note

    def entry(self, name='HELLO', key=2):
        return find(self.img.read_bytes(), name, key)

    def refused(self, note_part, **kw):
        """The operation is refused, nothing was written, and the image is
        byte for byte the one that was there."""
        before = self.img.read_bytes()
        writes, note = self.run_op(**kw)
        self.assertIn(note_part, note)
        self.assertEqual(writes, 0, note)
        self.assertEqual(self.img.read_bytes(), before, note)
        return note


class ImgPut(Harness):
    # -- what must happen ---------------------------------------------------

    def test_the_copy_moves_a_bar(self):
        # 780 bytes: two data blocks, each written and read back.
        writes, note = self.run_op()
        self.assertIn('Copied into the image', note)
        self.assertEqual(self.bars, [['HELLO', '0', '2'], ['HELLO', '1', '2']])

    def test_the_long_phases_give_a_sign_of_life(self):
        """Counting the source and walking the image have no bar: every
        block read turns the activity cell, and the walk says what it is
        doing before it starts."""
        self.run_op()
        self.assertEqual(self.messages, ['Checking the image... ESC stops'])
        # two reads to count 780 bytes, and one directory block walked
        self.assertGreaterEqual(self.spins, 3)

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
        self.assertEqual(findings(self.img.read_bytes()), [])

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
        self.assertEqual(findings(self.img.read_bytes()), [])

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
                writes, out = self.run_op(img=img)
                self.assertIn('Copied', out)
                after = img.read_bytes()
                self.assertEqual(len(after), len(before))
                if suffix == '.2MG':
                    self.assertEqual(after[:64], before[:64], 'the 2MG header moved')
                im = Image(unwrap(after))
                e = next(x for x in im.entries(2)
                         if x[1:1 + (x[0] & 15)].decode() == 'HELLO')
                self.assertEqual(im.read(e)[:len(self.payload)], self.payload)
                self.assertEqual(findings(unwrap(after)), [])

    def test_the_sizes_at_the_edges(self):
        """An empty file owns one block and has no length; a file of exactly
        one block is still a seedling, one byte more is a sapling; 128 KB is
        the last size a sapling holds, and one byte more is refused before
        the question."""
        for size, storage, blocks in ((0, 1, 1), (1, 1, 1), (511, 1, 1), (512, 1, 1),
                                      (513, 2, 3), (1024, 2, 3), (1025, 2, 4),
                                      (131072, 2, 257)):
            with self.subTest(size=size):
                self.original = make_image(600)
                self.img.write_bytes(self.original)
                self.payload = bytes((i * 11 + 3) & 255 for i in range(size))
                self.src.write_bytes(self.payload)
                writes, note = self.run_op()
                self.assertIn('Copied into the image', note)
                e = self.entry()
                self.assertEqual(e[0] >> 4, storage)
                self.assertEqual(int.from_bytes(e[0x13:0x15], 'little'), blocks)
                self.assertEqual(int.from_bytes(e[0x15:0x18], 'little'), size)
                self.assertEqual(Image(self.img.read_bytes()).read(e), self.payload)
                self.assertEqual(findings(self.img.read_bytes()), [])
        self.img.write_bytes(self.original)
        self.payload = bytes(131073)
        self.src.write_bytes(self.payload)
        self.refused('Too big')
        self.assertEqual(self.asked, [])

    # -- what must not ------------------------------------------------------

    def test_answering_no_writes_nothing(self):
        writes, note = self.run_op(mode=1)
        self.assertEqual(writes, 0, note)
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_a_name_already_there_is_refused(self):
        self.run_op(name='TAKEN')
        self.refused('No room for that name', name='TAKEN')

    def test_the_wrong_panels_are_refused(self):
        self.refused('ProDOS image opposite', wrong=1)

    def test_an_image_that_is_not_prodos_is_refused(self):
        self.img.write_bytes(bytes(280 * 512))
        self.refused('Not a ProDOS image')

    def test_a_disk_without_room_is_refused(self):
        """Every block but two is taken: a three-block file cannot fit, and
        the refusal must come before anything is written."""
        d = bytearray(self.original)
        for b in range(9, 280):
            set_free(d, b, False)
        self.img.write_bytes(bytes(d))
        self.refused('Not enough free blocks')
        self.assertEqual(self.asked, [])

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
                    self.assertEqual(findings(d), [])

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
                    self.assertFalse(is_free(d, key),
                                     'the entry names a block the bitmap calls free')
                    self.assertIn('Copied', note)


class TheSourceIsCounted(Harness):
    """The length written is what the file holds, never what a panel
    remembered of it (AGENTS.md: a panel's size can be stale)."""

    def test_a_stale_panel_size_changes_nothing(self):
        """Measured before the source was counted: 512 bytes behind a panel
        that said 0 went in as "Copied" with an EOF of 0; 1024 behind 600
        with an EOF of 600, the second block there and unreachable; 900
        behind 1000 with an EOF of 1000 and a hundred zeros nobody wrote."""
        for real, panel in ((512, 0), (1024, 600), (900, 1000), (0, 700), (700, 0),
                            (2000, 100000), (3, 131073)):
            with self.subTest(real=real, panel=panel):
                self.img.write_bytes(self.original)
                self.payload = bytes((i * 7 + 1) & 255 or 1 for i in range(real))
                self.src.write_bytes(self.payload)
                writes, note = self.run_op(PANEL_SIZE=panel)
                self.assertIn('Copied into the image', note)
                e = self.entry()
                self.assertEqual(int.from_bytes(e[0x15:0x18], 'little'), real)
                self.assertEqual(Image(self.img.read_bytes()).read(e), self.payload)
                self.assertEqual(findings(self.img.read_bytes()), [])

    def unchanged_but_for_free_blocks(self, note):
        """Nothing a reader of the volume can see has moved: no entry, the
        bitmap and every block it calls used as they were. Blocks that were
        free may hold the bytes of the attempt; they are still free and
        nothing names them."""
        d = self.img.read_bytes()
        self.assertNotIn('Copied', note)
        self.assertIsNone(self.entry())
        for b in range(len(d) // 512):
            if not is_free(self.original, b):
                self.assertEqual(d[b * 512:(b + 1) * 512], self.original[b * 512:(b + 1) * 512],
                                 'block %d changed' % b)
        self.assertEqual(findings(d), [])

    def test_a_source_that_changes_between_the_count_and_the_copy(self):
        """Counted at 780 bytes, then cut to 100, to 600, or grown to 781
        or 2000 before the copy opens it: the copy must total exactly what
        was counted and end on a clean end of file, or nothing is added."""
        for size in (100, 600, 512, 0, 781, 1024, 2000):
            with self.subTest(size=size):
                self.img.write_bytes(self.original)
                self.src.write_bytes(self.payload)
                writes, note = self.run_op(SRC_AT_OPEN='2:%d' % size, source_kept=False)
                self.assertIn('Source changed', note)
                self.unchanged_but_for_free_blocks(note)

    def test_a_source_that_stops_reading_during_the_copy(self):
        for nth in (3, 4):                         # reads 1-2 count it, 3-4 copy it
            with self.subTest(nth=nth):
                self.img.write_bytes(self.original)
                writes, note = self.run_op(SRC_FAIL_READ=nth)
                self.assertIn('Source changed', note)
                self.unchanged_but_for_free_blocks(note)

    def test_a_source_that_cannot_be_counted_is_refused_before_the_question(self):
        """A read error while counting is not the end of the file: nothing
        is asked and nothing is written."""
        for env in ({'SRC_FAIL_READ': 1}, {'SRC_FAIL_READ': 2}, {'SRC_NO_OPEN': 1}):
            with self.subTest(env=env):
                self.refused('Cannot read the source', **env)
                self.assertEqual(self.asked, [])

    def test_a_source_that_cannot_be_opened_again_after_the_question(self):
        self.refused('Cannot read the source', SRC_NO_OPEN=2)
        self.assertEqual(len(self.asked), 1)


class TheImageIsWalked(Harness):
    """No free bit is believed until every block the image names has been
    found marked used (src/plugins/prodos_claims.h)."""

    def fixture(self):
        return orchard()

    def damaged(self, poke):
        d = bytearray(self.original)
        poke(d)
        self.img.write_bytes(bytes(d))
        return d

    def sub(self):
        return key_of(find(self.original, 'SUB'))

    def refused_after_the_question(self, **kw):
        note = self.refused('Image damaged: nothing written', **kw)
        self.assertEqual(len(self.asked), 1)
        return note

    def test_a_sound_image_takes_the_file_and_stays_sound(self):
        """Seedling, sapling, tree, extended file, three directories deep:
        the walk follows them all, the file goes in, every other file reads
        back as it was and the oracle finds nothing."""
        writes, note = self.run_op()
        self.assertIn('Copied into the image', note)
        d = self.img.read_bytes()
        self.assertEqual(findings(d), [])
        im = Image(d)
        self.assertEqual(im.read(self.entry()), self.payload)
        self.assertEqual(im.read(find(d, 'OTHER.TXT')), OTHER)
        self.assertEqual(im.read(find(d, 'BIG.BIN')), BIG)
        self.assertEqual(im.read(find(d, 'KEEP.TXT', self.sub())), KEEP)
        # nothing but the new file's blocks, the bitmap and block 2 moved
        e = self.entry()
        idx = im.block(key_of(e))
        mine = {key_of(e), idx[0] | idx[256] << 8, idx[1] | idx[257] << 8, 2, bitmap_at(d)}
        changed = {b for b in range(800) if d[b * 512:(b + 1) * 512] != self.original[b * 512:(b + 1) * 512]}
        self.assertEqual(changed, mine)
        # the tree alone is three index blocks; with five directory blocks
        # and the forks, the walk read well over a dozen blocks
        self.assertGreater(self.spins, 12)

    def test_a_file_goes_into_a_subdirectory(self):
        sub = self.sub()
        writes, note = self.run_op(key=sub)
        self.assertIn('Copied into the image', note)
        d = self.img.read_bytes()
        e = self.entry(key=sub)
        self.assertIsNotNone(e)
        self.assertIsNone(self.entry())                       # not at the root
        self.assertEqual(word(e, 0x25), sub)                  # its header pointer
        self.assertEqual(file_count(d, sub), file_count(self.original, sub) + 1)
        self.assertEqual(file_count(d), file_count(self.original))
        self.assertEqual(Image(d).read(e), self.payload)
        self.assertEqual(findings(d), [])

    def test_a_data_block_marked_free_is_never_given_away(self):
        """Measured before the walk existed, on this very damage: the first
        data block of SUB/KEEP.TXT marked free. IMGPUT gave it to the new
        file, KEEP.TXT read back with the new file's bytes in it, the oracle
        went from BM_USED_FREE to a cross-link, and the answer was "Copied
        into the image; source kept."."""
        keep = find(self.original, 'KEEP.TXT', self.sub())
        index = Image(self.original).block(key_of(keep))
        self.damaged(lambda d: set_free(d, index[0] | index[256] << 8))
        self.refused_after_the_question()
        self.assertEqual(Image(self.img.read_bytes()).read(keep), KEEP)

    def test_the_directory_being_added_to_marked_free(self):
        """Measured before: the key block of SUB marked free, the file put
        into SUB. The key block was the first free block, so the new file's
        index went over the directory -- its header and KEEP.TXT's entry
        gone, the oracle listing eight kinds of damage -- and the answer was
        still "Copied"."""
        sub = self.sub()
        self.damaged(lambda d: set_free(d, sub))
        self.refused_after_the_question(key=sub)
        self.refused_after_the_question()                     # and from the root

    def test_any_block_the_image_names_marked_free(self):
        """One block at a time, every kind of block there is: the volume
        directory's four, a subdirectory's, a seedling, a sapling's index, a
        tree's master index, one of its index blocks, one of its data
        blocks, the extended key block, each fork's blocks, the boot blocks
        and the bitmap's own. Each alone is enough to refuse."""
        im = Image(self.original)
        big = key_of(find(self.original, 'BIG.BIN'))
        master = im.block(big)
        index1 = master[1] | master[257] << 8
        forks = im.block(key_of(find(self.original, 'FORKS')))
        ridx = forks[257] | forks[258] << 8
        deep = key_of(find(self.original, 'DEEP', self.sub()))
        blocks = {
            'boot block 0': 0, 'boot block 1': 1,
            'volume directory 2': 2, 'volume directory 3': 3,
            'volume directory 4': 4, 'volume directory 5': 5,
            'the bitmap': bitmap_at(self.original),
            'a subdirectory': self.sub(), 'a directory two down': deep,
            'a seedling': key_of(find(self.original, 'OTHER.TXT')),
            'a seedling three down': key_of(find(self.original, 'LEAF', deep)),
            'a sapling index': key_of(find(self.original, 'KEEP.TXT', self.sub())),
            'a tree master index': big,
            'a tree index block': index1,
            'a tree data block': im.block(index1)[5] | im.block(index1)[261] << 8,
            'the last tree data block': max(b for b in range(800) if not is_free(self.original, b)
                                            and b not in (ridx,)) - 6,
            'an extended key block': key_of(find(self.original, 'FORKS')),
            'a data fork': forks[1] | forks[2] << 8,
            'a resource fork index': ridx,
            'a resource fork block': im.block(ridx)[2] | im.block(ridx)[258] << 8,
        }
        for what, b in blocks.items():
            with self.subTest(block=what):
                self.assertFalse(is_free(self.original, b), what)
                d = self.damaged(lambda d: set_free(d, b))
                self.assertTrue({('BM_USED_FREE', b), ('BM_RESERVED', b)} & set(findings(d)))
                self.refused_after_the_question()

    def test_every_used_block_in_turn(self):
        """The same, without choosing: each block the bitmap calls used and
        the oracle agrees is referenced, marked free alone, refuses the
        copy. A walk that skipped one kind of block would let it through."""
        used = [b for b in range(800) if not is_free(self.original, b)]
        self.assertGreater(len(used), 290)
        for b in used[::7] + used[-12:]:
            with self.subTest(block=b):
                self.damaged(lambda d: set_free(d, b))
                self.refused_after_the_question()

    def test_a_bitmap_calling_the_directory_free_is_refused_outright(self):
        """Before the walk, a floor kept the allocator out of blocks 0 to 6
        and the copy went ahead beside the damage. (Before the floor,
        measured: the file went over the directory and the bitmap and the
        volume did not read back at all.) A bitmap that calls the volume
        directory or itself free is now a reason to write nothing."""
        for lo, hi in ((1, 7), (0, 7), (6, 7), (2, 6)):
            with self.subTest(free=(lo, hi)):
                def poke(d):
                    for b in range(lo, hi):
                        set_free(d, b)
                self.damaged(poke)
                self.refused_after_the_question()

    def test_pointers_that_lead_nowhere_good(self):
        """An index pointer past the end of the volume, one into the
        bitmap, one at a boot block; a subdirectory entry whose key is the
        volume directory (a cycle), is zero, or is a file's data block; a
        chain that loops back on itself; a storage type nobody defined; an
        extended file with a fork of no known kind."""
        im = Image(self.original)
        keep = key_of(find(self.original, 'KEEP.TXT', self.sub()))
        sub = self.sub()
        forks = key_of(find(self.original, 'FORKS'))

        def sub_slot(d):
            for slot in range(1, 13):
                at = 2 * 512 + 4 + slot * 39
                if d[at] >> 4 == 0xD:
                    return at
            raise AssertionError('no subdirectory in block 2')

        def key_to(value):
            def poke(d):
                at = sub_slot(d)
                d[at + 0x11:at + 0x13] = value.to_bytes(2, 'little')
            return poke

        def index_to(value):
            def poke(d):
                d[keep * 512 + 1] = value & 255
                d[keep * 512 + 257] = value >> 8
            return poke

        def storage(value):
            def poke(d):
                at = sub_slot(d) - 39 if False else 2 * 512 + 4 + 39
                d[at] = (value << 4) | (d[at] & 15)
            return poke

        def loop(d):
            d[5 * 512 + 2:5 * 512 + 4] = (3).to_bytes(2, 'little')

        def self_loop(d):
            d[sub * 512 + 2:sub * 512 + 4] = sub.to_bytes(2, 'little')

        def fork_kind(d):
            d[forks * 512 + 256] = 4

        def header_gone(d):
            d[sub * 512 + 4] = 0x23

        def odd_entry_length(d):
            d[sub * 512 + 0x23] = 0x28

        cases = {
            'index pointer past the volume': index_to(800),
            'index pointer far past it': index_to(0xFFFF),
            'index pointer into the bitmap': index_to(bitmap_at(self.original)),
            'index pointer at boot block 1': index_to(1),
            'subdirectory key is the volume directory': key_to(2),
            'subdirectory key is zero': key_to(0),
            'subdirectory key is a data block': key_to(key_of(find(self.original, 'OTHER.TXT'))),
            'subdirectory key past the volume': key_to(900),
            'the volume directory chain loops': loop,
            'a subdirectory chained to itself': self_loop,
            'storage type 4': storage(4),
            'storage type 7': storage(7),
            'a volume header as an entry': storage(15),
            'a fork of no known kind': fork_kind,
            'a subdirectory without its header': header_gone,
            'a directory of 40-byte entries': odd_entry_length,
        }
        for what, poke in cases.items():
            with self.subTest(case=what):
                self.damaged(poke)
                self.refused_after_the_question()
                # the walk ends: a loop is not followed for ever
                self.assertLess(self.reads, 4000)

    def test_directories_nested_too_deep_are_refused_not_overrun(self):
        """Sixteen directories deep, the volume's included, is the limit
        FIXIT, VOLINFO and the oracle hold ProDOS to, and the number of
        places the walk keeps. One more is refused, not overrun."""
        for depth, ok in ((15, True), (16, False)):
            with self.subTest(depth=depth):
                path = '/'.join('D%d' % i for i in range(depth)) + '/LEAF#040000'
                self.original = make_image(280, 'DEEP', {path: LEAF})
                self.assertEqual(findings(self.original), [] if ok else [('DIR_DEPTH', 22)])
                self.img.write_bytes(self.original)
                if ok:
                    writes, note = self.run_op()
                    self.assertIn('Copied into the image', note)
                    self.assertEqual(findings(self.img.read_bytes()), [])
                else:
                    self.refused_after_the_question()

    def test_a_block_that_cannot_be_read_during_the_walk(self):
        """An unreadable block is not a block with nothing in it: a
        subdirectory, an index block, a tree's master index, the extended
        key block or the bitmap itself failing to read stops everything."""
        im = Image(self.original)
        big = key_of(find(self.original, 'BIG.BIN'))
        master = im.block(big)
        for what, b in (('a subdirectory', self.sub()),
                        ('a sapling index', key_of(find(self.original, 'KEEP.TXT', self.sub()))),
                        ('a tree master index', big),
                        ('a tree index block', master[0] | master[256] << 8),
                        ('the extended key block', key_of(find(self.original, 'FORKS')))):
            with self.subTest(block=what):
                self.refused_after_the_question(BAD_BLOCK=b)
        # a block of the volume directory, met by the walk on the way to a
        # file bound for a subdirectory (bound for the root, it is read
        # before the question, and that is a refusal of its own)
        self.refused_after_the_question(BAD_BLOCK=3, key=self.sub())
        self.refused('No room for that name', BAD_BLOCK=3)
        self.assertEqual(self.asked, [])
        # the bitmap is read before the question: no room can be counted
        self.refused('Not enough free blocks', BAD_BLOCK=bitmap_at(self.original))
        self.assertEqual(self.asked, [])
        self.refused('Not a ProDOS image', BAD_BLOCK=2)

    def test_escape_during_the_walk_stops_it_with_nothing_written(self):
        # six reads come before the question; the walk starts after two more
        for nth in (9, 12, 20):
            with self.subTest(nth=nth):
                self.refused('Stopped; image unchanged', ESC_AT=nth)
                self.assertEqual(len(self.asked), 1)

    def test_a_bitmap_pointer_inside_the_volume_directory(self):
        """Measured before, on a sound volume of 45 files whose header was
        made to name block 3, 4 or 5 -- blocks of the volume directory -- as
        its bitmap: "Copied" each time. With 3, the entries of block 3 read
        as free bits: the new file's blocks landed on directory block 5, on
        the real bitmap (block 6) and on two files' blocks (21 and 35), and
        24 of the 45 entries were left. With 5, eighteen bytes of the
        entries in block 5 were rewritten as a "bitmap". Now the walk meets
        that block as a directory block that is also the bitmap, and
        nothing is written."""
        files = {'F%02d#040000' % i: b'file %d\r' % i for i in range(45)}
        self.original = make_image(280, 'MANY', files)
        self.assertEqual(findings(self.original), [])
        for pointer in (3, 4, 5):
            with self.subTest(pointer=pointer):
                d = bytearray(self.original)
                d[2 * 512 + 4 + 0x23:2 * 512 + 4 + 0x25] = pointer.to_bytes(2, 'little')
                self.img.write_bytes(bytes(d))
                before = self.img.read_bytes()
                writes, note = self.run_op()
                self.assertEqual(writes, 0, note)
                self.assertNotIn('Copied', note)
                self.assertEqual(self.img.read_bytes(), before)

    def test_a_sparse_file_is_walked_past_its_holes(self):
        """A zero pointer is a hole, at any level -- in a sapling's index
        and in a tree's master index -- and not a reference to block 0."""
        d = bytearray(self.original)
        keep = find(self.original, 'KEEP.TXT', self.sub())
        k = key_of(keep)
        hole = d[k * 512 + 1] | d[k * 512 + 257] << 8
        d[k * 512 + 1] = d[k * 512 + 257] = 0
        set_free(d, hole)
        big = key_of(find(self.original, 'BIG.BIN'))
        index1 = d[big * 512 + 1] | d[big * 512 + 257] << 8
        d[big * 512 + 1] = d[big * 512 + 257] = 0
        set_free(d, index1)
        for i in range(256):
            b = d[index1 * 512 + i] | d[index1 * 512 + 256 + i] << 8
            if b:
                set_free(d, b)
        self.img.write_bytes(bytes(d))
        # the oracle's only remarks: two block counts no longer match
        self.assertEqual({f for f, _ in findings(d)}, {'FILE_BLOCKS'})
        writes, note = self.run_op()
        self.assertIn('Copied into the image', note)
        self.assertEqual({f for f, _ in findings(self.img.read_bytes())}, {'FILE_BLOCKS'})

    # -- the directory the panel remembers ----------------------------------

    def test_a_key_that_is_no_longer_a_directory(self):
        """The panel's key is from when it opened the image. Measured before,
        with the key of a data block of BIG.BIN that held zeros: slot 1
        "was free", so the new entry and a file count of 1 were written
        into that file's data, and the answer was "Copied". The key block
        must read as the head of a directory, or there is no directory."""
        d = bytearray(self.original)
        big = key_of(find(self.original, 'BIG.BIN'))
        index0 = d[big * 512] | d[big * 512 + 256] << 8
        victim = d[index0 * 512 + 9] | d[index0 * 512 + 265] << 8
        d[victim * 512:(victim + 1) * 512] = bytes(512)
        self.img.write_bytes(bytes(d))
        self.refused('No room for that name', key=victim)
        self.assertEqual(self.asked, [])
        # a continuation block of a real directory is not a head either
        self.refused('No room for that name', key=3)
        # nor is a seedling's block, an index block or the bitmap
        for key in (key_of(find(self.original, 'OTHER.TXT')), big, bitmap_at(self.original), 0, 799, 800):
            with self.subTest(key=key):
                self.refused('No room for that name', key=key)

    def test_a_directory_deleted_since_the_panel_read_it(self):
        """ProDOS deletes a directory by clearing its entry and freeing its
        blocks: the key block keeps its header. Read on its own it is still
        a directory with free slots -- and by now a free block, or another
        file's. Measured before: "Copied", the entry written into the dead
        directory's block, where nothing looks, and the three blocks of the
        file lost. The walk never meets that block as a directory, so
        nothing is written."""
        d = bytearray(self.original)
        deep = key_of(find(self.original, 'DEEP', self.sub()))
        leaf = key_of(find(self.original, 'LEAF', deep))
        sub = self.sub()
        for slot in range(1, 13):
            at = sub * 512 + 4 + slot * 39
            if d[at] >> 4 == 0xD:
                d[at] &= 0x0F
        d[sub * 512 + 4 + 0x21:sub * 512 + 4 + 0x23] = (file_count(d, sub) - 1).to_bytes(2, 'little')
        set_free(d, deep)
        set_free(d, leaf)
        self.img.write_bytes(bytes(d))
        self.assertEqual(findings(d), [])                    # a clean deletion
        self.refused_after_the_question(key=deep)

    # -- the image while the question waits ---------------------------------

    def test_blocks_taken_while_the_question_waited_are_not_taken_twice(self):
        """Measured before: the blocks were chosen before the question and
        used after it. With the bitmap changed in between -- the first three
        free blocks, 297 to 299, handed to somebody else -- the file took
        exactly those three and wrote over them, take() "clearing" bits that
        were already clear, and the answer was "Copied". They are chosen
        again from the bitmap as it reads after the question, and the copy
        lands beside what was taken."""
        free = [b for b in range(800) if is_free(self.original, b)][:3]
        at = bitmap_at(self.original) * 512
        pokes = ','.join('%d:%x:0' % (at + (b >> 3), ~(0x80 >> (b & 7)) & 0xFF) for b in free)
        writes, note = self.run_op(POKE_AT_CONFIRM=pokes)
        self.assertIn('Copied into the image', note)
        d = self.img.read_bytes()
        e = self.entry()
        idx = Image(d).block(key_of(e))
        mine = {key_of(e), idx[0] | idx[256] << 8, idx[1] | idx[257] << 8}
        self.assertFalse(mine & set(free), 'the file took blocks handed out during the question')
        for b in free:                                        # still as they were
            self.assertEqual(d[b * 512:(b + 1) * 512], self.original[b * 512:(b + 1) * 512])
        self.assertEqual(Image(d).read(e), self.payload)

    def test_an_image_damaged_while_the_question_waited(self):
        keep = key_of(find(self.original, 'KEEP.TXT', self.sub()))
        at = bitmap_at(self.original) * 512 + (keep >> 3)
        writes, note = self.run_op(POKE_AT_CONFIRM='%d:ff:%x' % (at, 0x80 >> (keep & 7)))
        self.assertIn('Image damaged', note)
        self.assertEqual(writes, 0)

    def test_a_bit_cleared_under_the_copy_stops_the_bitmap_write(self):
        """The bitmap changes after the blocks were chosen and their data
        written -- the key block is handed to somebody else. take() finds
        the bit already clear and stops: the bitmap is not written, and no
        entry ever names a block that was not ours to take."""
        key = [b for b in range(800) if is_free(self.original, b)][0]
        at = bitmap_at(self.original) * 512 + (key >> 3)
        writes, note = self.run_op(POKE_AT_WRITE='3;%d:%x:0' % (at, ~(0x80 >> (key & 7)) & 0xFF))
        self.assertIn('Bitmap write failed', note)
        d = self.img.read_bytes()
        self.assertIsNone(self.entry())
        bm = bitmap_at(d) * 512
        expected = bytearray(self.original[bm:bm + 512])
        expected[key >> 3] &= ~(0x80 >> (key & 7)) & 0xFF
        self.assertEqual(d[bm:bm + 512], bytes(expected))    # only the other party's bit
        self.assertEqual(d[2 * 512:6 * 512], self.original[2 * 512:6 * 512])


class WriteProtected(Harness):
    def test_a_write_protected_2mg_is_refused_untouched(self):
        """Measured before: bit 31 of the 2IMG flags (header byte 19, $80)
        set, and the file went in all the same -- "Copied into the image;
        source kept.", the image changed. DOSIMAGE refused the same flag."""
        image = bytearray(to_2mg(self.original))
        image[0x13] |= 0x80
        self.img = self.dir / 'DISK.2MG'
        self.img.write_bytes(bytes(image))
        self.refused('Image is read-only')
        self.assertEqual(self.asked, [])
        # the same container without the flag is written into
        image[0x13] &= 0x7F
        self.img.write_bytes(bytes(image))
        writes, note = self.run_op()
        self.assertIn('Copied into the image', note)


if __name__ == '__main__':
    unittest.main()
