"""Run the whole Newsroom viewer (src/plugins/newsroom.s) under sim65.

The entry point runs on both processors, as the program would call it,
with a service table whose fopen/fread/fclose are the simulator's own and
can be made to fail. What it drew, whether it lit the page up, and what it
said are checked against tools/newsroom_ref.py: every valid picture must
give the reference's page, every malformed one or failed I/O must leave the
screen off and say so. The real disks in ~/.cache/a2fc/newsroom (125 files,
see docs/NEWSROOM-FORMAT.md) are run when present.
"""
import glob
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import newsroom_ref as ref  # noqa: E402

CFG_START = '$8000'
CORPUS = Path(os.environ.get('A2FC_NEWSROOM', Path.home() / '.cache/a2fc/newsroom'))

# argv: type aux size fault call. fault 1: fread short at call `call`;
# 2: fread fails there with the stream's error flag set; 3: fclose fails;
# 4: fopen fails. The picture is pic.bin.
HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "src/a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
static int fault, at, calls, waits;
static FILE* opn(const char* p, const char* m) { return fault == 4 ? NULL : fopen(p, m); }
static size_t rd(void* p, size_t s, size_t n, FILE* f)
{
    if (++calls == at && fault == 1) return n ? n - 1 : 0;
    /* _FILE: f_fd, f_flags, f_pushback; _FERROR is 4 (libsrc/common/_file.h) */
    if (calls == at && fault == 2) { ((unsigned char*)f)[1] |= 4; return 0; }
    return fread(p, s, n, f);
}
static int cls(FILE* f) { int r = fclose(f); return fault == 3 ? EOF : r; }
static char wait(void) { ++waits; return 27; }
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Entry e;
    static char note[80], sel[80], full[] = "pic.bin";
    FILE* t;
    (void)argc;
    /* The fault injection relies on the flag's place: check it. */
    t = fopen(full, "rb");
    if (!t) return 20;
    ((unsigned char*)t)[1] |= 4;
    if (!ferror(t)) return 21;
    fclose(t);
    e.type = atoi(argv[1]); e.aux = atoi(argv[2]); e.size = atol(argv[3]);
    fault = atoi(argv[4]); at = atoi(argv[5]);
    strcpy(e.name, "PH.SOURCE");
    api.full = full; api.selected = &e; api.note = note; api.reselect = sel;
    api.fopen = opn; api.fread = rd; api.fclose = cls; api.strcpy = strcpy;
    api.media_wait = wait;
    memset((void*)0x2000, 0xEE, 0x4000);
    memset((void*)0xC050, 0xFF, 16);
    plugin_entry(&api);
    putchar(waits); putchar(*(unsigned char*)0xC057 == 0);   /* HIRES on */
    fwrite(note, 1, 80, stdout); fwrite(sel, 1, 80, stdout);
    fwrite((void*)0x2000, 1, 0x4000, stdout);
    return 0;
}
'''


def corpus():
    """(disk, name, body) of the real PH./BN. files, if the disks are here."""
    out, seen = [], set()
    for path in sorted(glob.glob(str(CORPUS / 'ia/*')) + glob.glob(str(CORPUS / '*.dsk'))):
        data = Path(path).read_bytes()
        if len(data) != 143360:
            continue
        for name, body in ref.dos33_files(data):
            if body not in seen:
                seen.add(body)
                out.append((Path(path).name, name, body))
    return out


class Newsroom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-newsroom-')
        cls.dir = Path(cls.tmp.name)
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        (cls.dir / 'harness.c').write_text(HARNESS)
        # Copies, under other names: cl65 turns a .c into a .s beside it,
        # and would overwrite newsroom.s in the source tree.
        shutil.copyfile(ROOT / 'src/plugins/newsroom.c', cls.dir / 'nr_ofs.c')
        shutil.copyfile(ROOT / 'src/plugins/newsroom.s', cls.dir / 'newsroom.s')
        cls.programs = {}
        for cpu in ('6502', '65c02'):
            base = 'sim65c02' if cpu == '65c02' else 'sim6502'
            cfg = (target.parent / f'cfg/{base}.cfg').read_text()
            cfg = cfg.replace('start = $0200, size = $FDF0 - __STACKSIZE__',
                              f'start = {CFG_START}, size = $BF00 - {CFG_START} - __STACKSIZE__')
            (cls.dir / f'{cpu}.cfg').write_text(cfg)
            exe = cls.dir / f'harness-{cpu}'
            subprocess.run(['cl65', '-t', base, '-I', str(ROOT), '-I', str(ROOT / 'src/plugins'), '-DNR_TEST',
                            '-C', str(cls.dir / f'{cpu}.cfg'), '-O', '-o', str(exe),
                            str(cls.dir / 'harness.c'), str(cls.dir / 'nr_ofs.c'),
                            str(cls.dir / 'newsroom.s')],
                           check=True, cwd=cls.dir)
            cls.programs[cpu] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_nr(self, cpu, body, size=None, fault=0, at=0, typ=6, aux=0x4000):
        (self.dir / 'pic.bin').write_bytes(body)
        size = len(body) if size is None else size
        out = subprocess.run(['sim65', str(self.programs[cpu]), str(typ), str(aux), str(size),
                              str(fault), str(at)], cwd=self.dir, capture_output=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual((self.dir / 'pic.bin').read_bytes(), body, 'the file is only read')
        o = out.stdout
        note = o[2:82].split(b'\0')[0].decode()
        sel = o[82:162].split(b'\0')[0].decode()
        return o[0], o[1], note, sel, o[162:162 + 0x2000], o[162 + 0x2000:]

    def good(self, cpu, body):
        waits, hires, note, sel, main, rest = self.run_nr(cpu, body)
        self.assertEqual((waits, hires, note, sel), (1, 1, '', 'PH.SOURCE'))
        self.assertEqual(main, ref.page(body))
        self.assertEqual(rest, b'\xee' * 0x2000, 'nothing written past page 1')

    def bad(self, cpu, body, **kw):
        waits, hires, note, sel, main, rest = self.run_nr(cpu, body, **kw)
        self.assertEqual((waits, hires), (0, 0), 'a refused picture is never shown')
        self.assertEqual(note, 'Not a whole Newsroom picture, or I/O error.')
        self.assertEqual(rest, b'\xee' * 0x2000)
        return sel, main

    def test_random_pictures_on_both_processors(self):
        rng = random.Random(1986)
        shapes = [(1, 1), (37, 192), (35, 80), (33, 168), (1, 192), (37, 1), (8, 43)]
        for i, (wb, h) in enumerate(shapes + [(None, None)] * 3):
            body = ref.make(rng, wb, h)
            for cpu in self.programs:
                with self.subTest(cpu=cpu, picture=i):
                    self.good(cpu, body)

    def test_ff_in_the_history_and_a_long_history(self):
        rng = random.Random(3)
        for history in (bytes([2]) + b'\x01\x17\x04\xff' + bytes(22),
                        bytes([0]) + b'\xff' * 70, bytes([0]), bytes([9]) + bytes(300)):
            body = ref.make(rng, 5, 7, history=history)
            for cpu in self.programs:
                with self.subTest(cpu=cpu, history=len(history)):
                    self.good(cpu, body)

    def test_malformed_pictures_are_refused_before_drawing(self):
        rng = random.Random(4)
        body = ref.make(rng, 6, 9)
        L = 54
        cases = {
            'L one short': bytes([L - 1, 0]) + body[2:],
            'y2 < y1': body[:2] + bytes([9, 1]) + body[4:],
            'x2 < x1': body[:4] + bytes([9, 1]) + body[6:],
            '193 rows': bytes([193 & 255, 193 >> 8, 0, 192, 0, 0]) + body[6:],
            'no $FF': body[:-L - 1] + b'\xfe' + body[-L:],
            'frame only': body[:6],
            'no history': body[:6] + b'\xff' + body[-L:],
            'empty': b'',
        }
        for what, data in cases.items():
            for cpu in self.programs:
                with self.subTest(cpu=cpu, case=what):
                    _, main = self.bad(cpu, data)
                    self.assertEqual(main, b'\xee' * 0x2000, 'refused before the page is cleared')

    def test_stale_sizes_and_trailing_data(self):
        rng = random.Random(5)
        body = ref.make(rng, 4, 20)
        for cpu in self.programs:
            with self.subTest(cpu=cpu):
                self.bad(cpu, body + b'X')                       # a byte after the bitmap
                self.bad(cpu, body, size=len(body) + 1)          # directory says more
                self.bad(cpu, body[:-1], size=len(body))         # the file is cut
                self.bad(cpu, body, size=len(body) - 1)          # directory says less
                self.bad(cpu, body, size=len(body) + 65536)      # past 64 KB
                self.bad(cpu, body, typ=4)                       # not a BIN

    def test_io_failures_are_never_an_end_of_file(self):
        rng = random.Random(6)
        body = ref.make(rng, 3, 4, history=bytes([0]))
        # reads: frame, history (1), then 4 rows, then the end-of-file probe
        for cpu in self.programs:
            for fault, at in [(1, 1), (1, 2), (1, 3), (1, 6), (2, 1), (2, 2), (2, 4), (2, 7),
                              (3, 0), (4, 0)]:
                with self.subTest(cpu=cpu, fault=fault, at=at):
                    self.bad(cpu, body, fault=fault, at=at)
            self.good(cpu, body)

    def test_real_newsroom_files(self):
        files = corpus()
        if not files:
            self.skipTest('no Newsroom disks in %s' % CORPUS)
        self.assertGreaterEqual(len(files), 90)
        for disk, name, body in files:
            with self.subTest(disk=disk, name=name):
                self.good('6502', body)
        for disk, name, body in files[::10]:
            with self.subTest(disk=disk, name=name, cpu='65c02'):
                self.good('65c02', body)


if __name__ == '__main__':
    unittest.main()
