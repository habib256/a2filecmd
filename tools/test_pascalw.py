"""Execute the shipped PASCALW C: ProDOS files written into an Apple Pascal
(UCSD) volume, on disposable images only, and through I/O faults.

The volume is built and read back by tools/pascal_ref.py, which knows
nothing of the overlay -- the fixture must never share an assumption with
the code it checks.

What matters is the order: the data goes past the last block any file uses,
then the entry at index count+1, and the file count last of all. So a
failure anywhere before the count write must leave a volume that reads
exactly as it did, with the files put in before it intact.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pascal_ref
from po22mg import to_2mg
from po2dsk import to_dsk

ROOT = Path(__file__).resolve().parents[1]

C = r'''
#define __fastcall__
#define PLUGIN_HOST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#undef memcpy
#undef memset
#undef strcpy
#undef sprintf
struct A2fcApi;
#include "src/plugins/pascalw.c"

static struct Panel panels[2];
static struct Entry sel;
static struct DirEntry de;
static unsigned char scratch[512], act;
static char note_text[160], full_path[280], other_scratch[280], reselect_text[64];
static char img_path[280], dir_path[280];
static int mode, fail_at, writes;

/* mode 1: answer No. 2: the nth fwrite fails. 3: it writes half. 4: it
 * comes back different. */
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
static void h_progress(const char* s, unsigned long a, unsigned long b)
{ fprintf(stderr, "BAR %s %lu %lu\n", s, a, b); }

/* One directory at a time, real files on the host. A ProDOS name carries no
 * suffix, so the types come from a ".types" manifest the enumerator skips. */
static char open_dir[280];
static char names[64][64];
static unsigned char types[64];
static int ncount, nat;

static void load_types(const char* dir) {
    char path[600], name[64]; unsigned int t; FILE* f; int i;
    for (i = 0; i < 64; ++i) types[i] = 0;
    sprintf(path, "%s/.types", dir);
    f = fopen(path, "r");
    if (!f) return;
    while (fscanf(f, "%63s %x", name, &t) == 2)
        for (i = 0; i < ncount; ++i)
            if (!strcmp(names[i], name)) types[i] = (unsigned char)t;
    fclose(f);
}

static unsigned char h_dir_open(const char* p) {
    DIR* dh; struct dirent* e;
    ncount = nat = 0;
    dh = opendir(p);
    if (!dh) return 0;
    while ((e = readdir(dh)) && ncount < 64)
        if (e->d_name[0] != '.') strcpy(names[ncount++], e->d_name);
    closedir(dh);
    strcpy(open_dir, p);
    load_types(p);
    return 1;
}

static unsigned char h_dir_next(void) {
    char path[600]; FILE* f;
    if (nat >= ncount) return 0;
    sprintf(path, "%s/%s", open_dir, names[nat]);
    strcpy(de.name, names[nat]);
    de.type = types[nat];
    de.aux = 0;
    de.mdate = 0x3533;                  /* 19 September 2026, ProDOS-shaped */
    de.size = 0;
    f = fopen(path, "rb");
    if (f) { fseek(f, 0, SEEK_END); de.size = ftell(f); fclose(f); }
    ++nat;
    return 1;
}
static void h_dir_close(void) {}

int main(int argc, char** argv) {
    struct A2fcApi api;
    memset(&api, 0, sizeof api);
    strcpy(img_path, argv[1]);
    strcpy(dir_path, argv[2]);
    mode = atoi(argv[3]); fail_at = atoi(argv[4]);
    strcpy(full_path, img_path);
    { const char* s = strrchr(img_path, '/'); strcpy(sel.name, s ? s + 1 : img_path); }
    sel.type = 6;
    panels[0].fs = FS_PRODOS;
    strcpy(panels[0].path, "/V");
    panels[1].fs = FS_PRODOS;
    strcpy(panels[1].path, dir_path);
    if (argc > 5 && atoi(argv[5])) panels[1].fs = FS_IMG;      /* wrong panel */

    api.panels = panels; api.active = &act; api.selected = &sel;
    api.full = full_path; api.other_full = other_scratch;
    api.copy_buf = scratch; api.note = note_text; api.reselect = reselect_text;
    api.dir_entry = &de;
    api.dir_open = h_dir_open; api.dir_next = h_dir_next; api.dir_close = h_dir_close;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy;
    api.strcmp = strcmp; api.strlen = strlen; api.sprintf = sprintf;
    api.fopen = fopen; api.fread = fread; api.fwrite = h_fwrite;
    api.fclose = fclose; api.fseek = fseek;
    api.confirm = h_confirm; api.message = h_message; api.progress_bar = h_progress;
    plugin_entry(&api);
    printf("%d %s\n", writes, note_text);
    return 0;
}
'''

KEEP = ('ALREADY', 5, b'this one was in the volume\r' * 20)


class PascalW(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='pw-build-')
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
        self.case = tempfile.TemporaryDirectory(prefix='pw', dir='/tmp')
        self.addCleanup(self.case.cleanup)
        self.dir = Path(self.case.name)
        self.img = self.dir / 'VOL.PO'
        self.original = pascal_ref.make('MYVOL', [KEEP])
        self.img.write_bytes(self.original)
        self.src = self.dir / 'src'
        self.src.mkdir()
        self.files = {}

    def give(self, name, data, type_=0):
        """A file in the directory opposite, with its ProDOS type beside it.

        A ProDOS name carries no suffix, so the type goes in a manifest the
        harness reads and the enumerator skips."""
        self.files[name] = data
        (self.src / name).write_bytes(data)
        with (self.src / '.types').open('a') as f:
            f.write('%s %02X\n' % (name, type_))

    def run_op(self, mode=0, at=1, wrong=0):
        run = subprocess.run(
            [str(self.exe), str(self.img), str(self.src), str(mode), str(at), str(wrong)],
            text=True, capture_output=True, check=True)
        out = run.stdout.strip()
        self.trace = run.stderr.splitlines()
        n, _, note = out.partition(' ')
        return int(n), note

    def volume(self):
        return pascal_ref.volume(self.img.read_bytes())

    def contents(self, name):
        v = self.volume()
        e = next(f for f in v['files'] if f['name'] == name)
        return pascal_ref.contents(self.img.read_bytes(), e)

    # -- what must happen ---------------------------------------------------

    def test_every_file_shows_its_name_then_its_blocks(self):
        # `name` is one buffer for every file: 0 redraws it, so the bar
        # names each file -- a skipped one too -- then fills to the end.
        self.give('HELLO', b'hello, pascal\r' * 60, 3)          # 840 bytes: 2 blocks
        self.give('EMPTY', b'', 3)                               # skipped
        writes, note = self.run_op()
        self.assertIn('1 put', note)
        bars = [tuple(l.split()[1:]) for l in self.trace if l.startswith('BAR ')]
        self.assertEqual(sorted(set(bars)), sorted({('EMPTY', '0', '1'), ('HELLO', '0', '1'),
                                                    ('HELLO', '1', '2'), ('HELLO', '2', '2')}))

    def test_files_land_in_the_volume_with_their_bytes(self):
        self.give('HELLO', b'hello, pascal\r' * 40, 3)
        self.give('DATA', bytes(range(256)) * 5, 5)
        writes, note = self.run_op()
        self.assertIn('2 put', note)
        v = self.volume()
        self.assertEqual(sorted(f['name'] for f in v['files']),
                         ['ALREADY', 'DATA', 'HELLO'])
        for name in ('HELLO', 'DATA'):
            self.assertEqual(self.contents(name), self.files[name], name)

    def test_the_date_comes_across_from_the_prodos_entry(self):
        """ProDOS keeps year 9-15, month 5-8, day 0-4; UCSD keeps year in
        the same place but day 4-8 and month 0-3. A month of zero would
        mean no date at all, which is what a zero word used to write."""
        self.give('DATED', b'x' * 600)
        self.run_op()
        e = next(f for f in self.volume()['files'] if f['name'] == 'DATED')
        self.assertEqual(e['date'], (26, 9, 19), e)

    def test_the_kind_is_the_inverse_of_what_the_reader_gives(self):
        for type_, kind in ((0x02, 2), (0x03, 3), (0x05, 5), (0x04, 0), (0xFF, 0)):
            with self.subTest(type=type_):
                self.setUp()
                self.give('F', b'x' * 600, type_)
                self.run_op()
                e = next(f for f in self.volume()['files'] if f['name'] == 'F')
                self.assertEqual(e['kind'], kind)

    def test_files_are_placed_after_the_last_one_and_do_not_overlap(self):
        self.give('ONE', b'1' * 700)
        self.give('TWO', b'2' * 700)
        self.run_op()
        v = self.volume()
        runs = sorted((f['first'], f['last']) for f in v['files'])
        for (f1, l1), (f2, _) in zip(runs, runs[1:]):
            self.assertLessEqual(l1, f2, runs)

    def test_the_containers_that_move_the_blocks_around(self):
        """A .DSK stores the halves of every block in DOS sector order and a
        .2MG puts a header in front of the volume. The Asimov Pascal disks
        are .do files, so the DOS order is the real case, not the exotic
        one -- and nothing exercised either path for writing."""
        for suffix, wrap, unwrap in (
                ('.DSK', to_dsk, to_dsk),          # the order is its own inverse
                ('.2MG', to_2mg, lambda d: d[int.from_bytes(d[24:26], 'little'):])):
            with self.subTest(suffix=suffix):
                self.setUp()
                img = self.dir / ('VOL' + suffix)
                img.write_bytes(wrap(self.original))
                self.give('NEW', b'new bytes\r' * 30)
                out = subprocess.check_output(
                    [str(self.exe), str(img), str(self.src), '0', '1', '0'],
                    text=True).strip()
                self.assertIn('1 put', out)
                raw = unwrap(img.read_bytes())
                v = pascal_ref.volume(raw)
                self.assertIsNotNone(v, out)
                e = next(f for f in v['files'] if f['name'] == 'NEW')
                self.assertEqual(pascal_ref.contents(raw, e), b'new bytes\r' * 30)

    # -- what must not ------------------------------------------------------

    def test_a_name_already_in_the_volume_is_skipped(self):
        self.give('ALREADY', b'different bytes entirely\r' * 3)
        writes, note = self.run_op()
        self.assertIn('0 put', note)
        self.assertEqual(self.contents('ALREADY'), KEEP[2])
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_an_empty_file_is_skipped_not_written(self):
        self.give('EMPTY', b'')
        writes, note = self.run_op()
        self.assertIn('0 put', note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_answering_no_writes_nothing(self):
        self.give('HELLO', b'x' * 600)
        writes, note = self.run_op(mode=1)
        self.assertEqual(writes, 0, note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_the_wrong_panel_is_refused(self):
        self.give('HELLO', b'x' * 600)
        writes, note = self.run_op(wrong=1)
        self.assertEqual(writes, 0, note)
        self.assertIn('ProDOS directory', note)

    def test_a_volume_without_room_is_refused_and_untouched(self):
        big = ('FILL', 0, bytes(270 * 512))
        self.original = pascal_ref.make('MYVOL', [big])
        self.img.write_bytes(self.original)
        self.give('HELLO', b'x' * 5000)
        writes, note = self.run_op()
        self.assertIn('No room', note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_the_image_itself_is_never_copied_into_itself(self):
        (self.src / 'VOL.PO').write_bytes(self.img.read_bytes())
        out = subprocess.check_output(
            [str(self.exe), str(self.src / 'VOL.PO'), str(self.src), '0', '1', '0'],
            text=True).strip()
        v = pascal_ref.volume((self.src / 'VOL.PO').read_bytes())
        self.assertEqual([f['name'] for f in v['files']], ['ALREADY'], out)

    def test_a_failure_before_the_count_leaves_the_volume_as_it_was(self):
        """Data blocks land past the last file and the entry sits past the
        count, so every write before the count is invisible."""
        self.give('HELLO', b'h' * 900)
        for mode in (2, 3, 4):
            for at in range(1, 5):
                with self.subTest(mode=mode, at=at):
                    self.img.write_bytes(self.original)
                    writes, note = self.run_op(mode=mode, at=at)
                    v = self.volume()
                    self.assertIsNotNone(v, (mode, at, note))
                    names = [f['name'] for f in v['files']]
                    if 'HELLO' in names:
                        self.assertEqual(self.contents('HELLO'), self.files['HELLO'])
                    else:
                        self.assertEqual(names, ['ALREADY'])
                    self.assertEqual(self.contents('ALREADY'), KEEP[2])


if __name__ == '__main__':
    unittest.main()
