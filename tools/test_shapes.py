"""SHAPES, entry point and all, under sim65 against tools/shapes_ref.py.

src/plugins/shapes.s runs on both processors with a service table built
by the harness: the C library of sim65 behind fopen/fread (fseek replayed
by reopening the file: sim65 has no lseek), and a scripted keyboard. At
each key the harness dumps the hi-res page and the status row; each dump
must be the reference's page, byte for byte. The mode switches land in
sim65's plain memory.
"""
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import shapes_ref as ref  # noqa: E402
import cp2_samples  # noqa: E402

HARNESS = r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include "a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi* api);
static struct A2fcApi api;
static struct Entry sel;
static char full[] = "table.bin", note[80], reselect[20], row[81];
static unsigned char copy[512], ry;
static const char* keys;
static FILE* __fastcall__ h_fopen(const char* p, const char* m) { return fopen(p, m); }
static size_t __fastcall__ h_fread(void* p, size_t s, size_t n, FILE* f) { return fread(p, s, n, f); }
static int __fastcall__ h_fclose(FILE* f) { return fclose(f); }
static int __fastcall__ h_fseek(FILE* f, long off, int whence)
{
    /* no lseek in sim65: reopen the file on the same stream, read forward */
    static unsigned char skip[64];
    unsigned int n;
    if (whence != SEEK_SET || !freopen(full, "rb", f)) return -1;
    while (off > 0) {
        n = off > 64 ? 64 : (unsigned int)off;
        if (fread(skip, 1, n, f) != n) return 0;   /* past the end: reads fail later */
        off -= n;
    }
    return 0;
}
static char* __fastcall__ h_strcpy(char* d, const char* s) { return strcpy(d, s); }
static void* __fastcall__ h_memset(void* p, int c, size_t n) { return memset(p, c, n); }
static void __fastcall__ h_gotoxy(unsigned char x, unsigned char y) { ry = y; if (y == 21) row[0] = 0; }
static void __fastcall__ h_cputs(const char* s) { if (ry == 21) strcat(row, s); }
static void h_clrscr(void) { }
static char h_cgetc(void)
{
    unsigned char mark = 0xA5;
    unsigned char n = strlen(row);
    write(1, &mark, 1);
    write(1, (void*)0x2000, 0x2000);
    write(1, &n, 1);
    write(1, row, n);
    return *keys ? *keys++ : 27;
}
int main(int argc, char** argv)
{
    unsigned char n;
    FILE* f = fopen(full, "rb");
    long size = 0;
    if (!f) return 10;
    while (fread(copy, 1, 1, f) == 1) ++size;
    fclose(f);
    keys = argv[1];
    strcpy(sel.name, "TABLE");
    sel.size = size;
    api.full = full; api.copy_buf = copy; api.note = note; api.reselect = reselect;
    api.selected = &sel;
    api.fopen = h_fopen; api.fread = h_fread; api.fseek = h_fseek; api.fclose = h_fclose;
    api.strcpy = h_strcpy; api.cgetc = h_cgetc; api.memset = h_memset;
    api.gotoxy = h_gotoxy; api.cputs = h_cputs; api.clrscr = h_clrscr;
    memset((void*)0x2000, 0xEE, 0x2000);
    plugin_entry(&api);
    n = 0x5A;
    write(1, &n, 1);
    n = strlen(note);
    write(1, &n, 1);
    write(1, note, n);
    n = strlen(reselect);
    write(1, &n, 1);
    write(1, reselect, n);
    return 0;
}
'''


def random_shape(rng):
    out = []
    for _ in range(rng.randint(1, 40)):
        b = rng.randrange(1, 256)
        out.append(b)
    return out


class Shapes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-shapes-')
        cls.dir = Path(cls.tmp.name)
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        shutil.copyfile(ROOT / 'src/plugins/shapes.c', cls.dir / 'shapes.c')
        shutil.copyfile(ROOT / 'src/plugins/shapes.s', cls.dir / 'shapes_svc.s')
        (cls.dir / 'harness.c').write_text(HARNESS)
        cls.programs = {}
        for cpu in ('6502', '65c02'):
            base = 'sim65c02' if cpu == '65c02' else 'sim6502'
            cfg = (target.parent / f'cfg/{base}.cfg').read_text()
            cfg = cfg.replace('start = $0200, size = $FDF0 - __STACKSIZE__',
                              'start = $4000, size = $BF00 - $4000 - __STACKSIZE__')
            cfg = cfg.replace('\n    CODE:', '\n    OVLHDR:   load = MAIN, type = ro;\n    CODE:', 1)
            (cls.dir / f'{cpu}.cfg').write_text(cfg)
            exe = cls.dir / f'harness-{cpu}'
            subprocess.run(['cl65', '-t', base, '-C', str(cls.dir / f'{cpu}.cfg'), '-O',
                            '-I', str(ROOT / 'src'), '-I', str(ROOT / 'src/plugins'),
                            '-o', str(exe), str(cls.dir / 'harness.c'), str(cls.dir / 'shapes.c'),
                            str(cls.dir / 'shapes_svc.s')], check=True, cwd=cls.dir,
                           capture_output=True)
            cls.programs[cpu] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_shapes(self, cpu, data, keys):
        (self.dir / 'table.bin').write_bytes(data)
        out = subprocess.run(['sim65', str(self.programs[cpu]), keys], cwd=self.dir,
                             capture_output=True, timeout=600)
        self.assertEqual(out.returncode, 0, out.stderr)
        o, screens, i = out.stdout, [], 0
        while o[i] == 0xA5:
            page = o[i + 1:i + 0x2001]
            n = o[i + 0x2001]
            screens.append((page, o[i + 0x2002:i + 0x2002 + n].decode()))
            i += 0x2002 + n
        self.assertEqual(o[i], 0x5A)
        n = o[i + 1]
        note = o[i + 2:i + 2 + n].decode()
        m = o[i + 2 + n]
        reselect = o[i + 3 + n:i + 3 + n + m].decode()
        return screens, note, reselect

    def check(self, cpu, data, keys, firsts):
        screens, note, reselect = self.run_shapes(cpu, data, keys)
        self.assertEqual(len(screens), len(firsts))
        for (page, status), first in zip(screens, firsts):
            self.assertEqual(status, ref.status(data, first))
            want = ref.page(data, first)
            if page != want:
                bad = [i for i in range(8192) if page[i] != want[i]]
                self.fail('page %d differs at %d offsets, first $%04X' % (first, len(bad), bad[0]))
        self.assertEqual((note, reselect), ('', 'TABLE'))

    def test_synthetic_tables(self):
        rng = random.Random(1)
        for cpu in self.programs:
            data = ref.make([random_shape(rng) for _ in range(60)], spare=3)
            with self.subTest(cpu=cpu):
                # next, next, next (stops at the last page), previous twice, previous at 1
                self.check(cpu, data, '  \nBbb', [1, 25, 49, 49, 25, 1, 1])
            broken = bytearray(ref.make([random_shape(rng) for _ in range(5)]))
            broken[4] = 0xFF                    # shape 2 starts past the end
            broken[5] = 0xFF
            data = bytes(broken[:-1])           # shape 5 does not end
            with self.subTest(cpu=cpu, case='broken'):
                self.check(cpu, data, '', [1])

    def test_wide_and_wrapping_shapes(self):
        wide = [0x0D] * 60 + [0x2D] * 20        # dots marching right, beyond the cell
        far = [0x09] * 150 + [0x04]             # a move past 127 dots: the byte wraps
        tall = [0x16] * 45
        data = ref.make([wide, far, tall, [0x04], [0x01], []])
        for cpu in self.programs:
            with self.subTest(cpu=cpu):
                self.check(cpu, data, '', [1])

    def test_refusals(self):
        for cpu in self.programs:
            for data in (b'', b'\x00\x00\x02\x00', b'\x05\x00\x08\x00\x09', b'\x01'):
                with self.subTest(cpu=cpu, data=data.hex()):
                    screens, note, reselect = self.run_shapes(cpu, data, '')
                    self.assertEqual((screens, note), ([], 'Not a shape table.'))

    def test_real_tables(self):
        v = cp2_samples.volume()
        found = [k for k in v if k.startswith('/GRAPHICS/SHAPETABLE/')]
        if not found:
            self.skipTest('no CiderPress II shape tables')
        for k in found:
            data = v[k][2]
            n = ref.shape_count(data)
            firsts = list(range(1, n + 1, 24))
            with self.subTest(k):
                self.check('6502', data, ' ' * (len(firsts) - 1), firsts)


if __name__ == '__main__':
    unittest.main()
