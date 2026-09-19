"""Execute the shipped CPMW C: ProDOS files written into an Apple II CP/M
volume, on disposable images only, and through I/O faults.

The volume is built and read back by tools/cpm_ref.py, which knows nothing
of the overlay.

Two things matter here and nowhere else. A CP/M sector is HALF a ProDOS
block, so every write is a read-modify-write and the other half belongs to
someone else -- a test writes a file next to another and checks the
neighbour survived. And CP/M has no bitmap: what is in use is whatever the
live directory entries claim, so a cut before the entry write must leave
the volume exactly as it was.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import cpm_ref
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
#include "src/plugins/cpmw.c"

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
{ (void)s; (void)a; (void)b; }

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

WAS_THERE = [('KEEP.TXT', b'this one was in the volume\r\n' * 30),
             ('OTHER.COM', bytes(range(256)) * 3)]


class CpmW(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='cw-build-')
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
        self.case = tempfile.TemporaryDirectory(prefix='cw', dir='/tmp')
        self.addCleanup(self.case.cleanup)
        self.dir = Path(self.case.name)
        self.img = self.dir / 'VOL.PO'
        self.original = cpm_ref.make(WAS_THERE, skew='apple')
        self.img.write_bytes(self.original)
        self.src = self.dir / 'src'
        self.src.mkdir()
        self.files = {}

    def give(self, name, data):
        self.files[name] = data
        (self.src / name).write_bytes(data)

    def run_op(self, mode=0, at=1, wrong=0):
        out = subprocess.check_output(
            [str(self.exe), str(self.img), str(self.src), str(mode), str(at), str(wrong)],
            text=True).strip()
        n, _, note = out.partition(' ')
        return int(n), note

    def volume(self):
        return cpm_ref.volume(self.img.read_bytes())

    def contents(self, name):
        raw = self.img.read_bytes()
        v = cpm_ref.volume(raw)
        e = next(f for f in v['files'] if f['name'] == name)
        return cpm_ref.contents(raw, e, v['skew'])

    # -- what must happen ---------------------------------------------------

    def test_files_land_in_the_volume_with_their_bytes(self):
        self.give('HELLO.TXT', b'hello, CP/M\r\n' * 40)
        self.give('TINY.COM', b'\xc9' * 300)
        writes, note = self.run_op()
        self.assertIn('2 put', note)
        v = self.volume()
        self.assertEqual(sorted(f['name'] for f in v['files']),
                         ['HELLO.TXT', 'KEEP.TXT', 'OTHER.COM', 'TINY.COM'])
        for name in ('HELLO.TXT', 'TINY.COM'):
            got = self.contents(name)
            self.assertEqual(got[:len(self.files[name])], self.files[name], name)
            self.assertTrue(set(got[len(self.files[name]):]) <= {0x1A}, name)

    def test_the_neighbour_sharing_a_prodos_block_survives(self):
        """A CP/M sector is half a ProDOS block: every write is a
        read-modify-write, and losing the other half would eat a file that
        has nothing to do with this one."""
        self.give('NEW.DAT', b'N' * 2000)
        self.run_op()
        for name, data in WAS_THERE:
            self.assertEqual(self.contents(name)[:len(data)], data, name)

    def test_the_blocks_it_took_belong_to_it_alone(self):
        self.give('ONE.DAT', b'1' * 1500)
        self.give('TWO.DAT', b'2' * 1500)
        self.run_op()
        v = self.volume()
        seen = set()
        for f in v['files']:
            for b in f['blocks']:
                self.assertNotIn(b, seen, (f['name'], b))
                seen.add(b)

    def test_a_dos_order_container_writes_the_same(self):
        """CP/M has a skew of its own on top of the container's order, so
        the two undo each other here and nowhere else. Nothing exercised a
        DOS-order container for writing."""
        img = self.dir / 'VOL.DSK'
        img.write_bytes(to_dsk(self.original))     # the order is its own inverse
        self.give('NEW.TXT', b'new bytes\r\n' * 30)
        out = subprocess.check_output(
            [str(self.exe), str(img), str(self.src), '0', '1', '0'], text=True).strip()
        self.assertIn('1 put', out)
        raw = to_dsk(img.read_bytes())
        v = cpm_ref.volume(raw)
        self.assertIsNotNone(v, out)
        e = next(f for f in v['files'] if f['name'] == 'NEW.TXT')
        self.assertEqual(cpm_ref.contents(raw, e, v['skew'])[:330], b'new bytes\r\n' * 30)

    # -- what must not ------------------------------------------------------

    def test_a_name_already_there_is_skipped(self):
        self.give('KEEP.TXT', b'completely different bytes\r\n')
        writes, note = self.run_op()
        self.assertIn('0 put', note)
        self.assertEqual(self.contents('KEEP.TXT')[:len(WAS_THERE[0][1])], WAS_THERE[0][1])
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_a_file_too_big_for_one_extent_is_skipped(self):
        self.give('BIG.DAT', b'B' * 20000)
        writes, note = self.run_op()
        self.assertIn('0 put', note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_a_name_cp_m_cannot_carry_is_skipped(self):
        for name in ('TOOLONGNAME.TXT', 'A.B.C', 'WITH:COLON'):
            with self.subTest(name=name):
                self.setUp()
                self.give(name, b'x' * 300)
                writes, note = self.run_op()
                self.assertIn('0 put', note)
                self.assertEqual(self.img.read_bytes(), self.original)

    def test_answering_no_writes_nothing(self):
        self.give('HELLO.TXT', b'x' * 600)
        writes, note = self.run_op(mode=1)
        self.assertEqual(writes, 0, note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_an_empty_volume_is_refused_because_the_skew_cannot_be_known(self):
        self.original = cpm_ref.make([], skew='apple')
        self.img.write_bytes(self.original)
        self.give('HELLO.TXT', b'x' * 600)
        writes, note = self.run_op()
        self.assertEqual(writes, 0, note)
        self.assertIn('Not a CP/M volume', note)
        self.assertEqual(self.img.read_bytes(), self.original)

    def test_a_failure_before_the_entry_leaves_the_volume_as_it_was(self):
        """The data goes into blocks no live entry claims, and CP/M has no
        bitmap: until the entry lands, nothing in the volume changed."""
        self.give('HELLO.TXT', b'h' * 1500)
        for mode in (2, 3, 4):
            for at in range(1, 8):
                with self.subTest(mode=mode, at=at):
                    self.img.write_bytes(self.original)
                    writes, note = self.run_op(mode=mode, at=at)
                    v = self.volume()
                    self.assertIsNotNone(v, (mode, at, note))
                    names = sorted(f['name'] for f in v['files'])
                    if 'HELLO.TXT' in names:
                        self.assertEqual(self.contents('HELLO.TXT')[:1500], b'h' * 1500)
                    else:
                        self.assertEqual(names, ['KEEP.TXT', 'OTHER.COM'])
                    for name, data in WAS_THERE:
                        self.assertEqual(self.contents(name)[:len(data)], data, name)


if __name__ == '__main__':
    unittest.main()
