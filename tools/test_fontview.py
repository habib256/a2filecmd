"""FONTVIEW, entry point and all, under sim65: both font formats.

src/plugins/fontview.s runs on both processors with a service table built
by the harness (sim65's C library behind fopen/fread/fclose, a media_wait
that dumps the hi-res page). Every page shown must be the oracle's, byte
for byte: MGTK fonts (the page tools/test_sample_media.py used to check on
the host) and hi-res fonts of 96 or 128 glyphs of 7 x 8 dots. Refusals,
truncations, trailing bytes and I/O failures show nothing and say so.
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
import cp2_samples  # noqa: E402


def row(y):
    return (y & 7) * 1024 + ((y >> 3) & 7) * 128 + (y >> 6) * 40


def mgtk_page(data):
    flag, last, height = data[:3]
    count = last + 1
    cols = 1 + (flag == 128)
    widths = data[3:3 + count]
    out = bytearray(8192)
    for g in range(count):
        for y in range(height):
            for x in range(widths[g]):
                bit = data[3 + count + (y * cols + x // 7) * count + g] & (1 << (x % 7))
                if bit:
                    out[row((g // 16) * (height + 2) + y) + 4 + (g % 16) * 2 + x // 7] |= bit
    return bytes(out)


def raw_page(data):
    out = bytearray(8192)
    for g in range(len(data) // 8):
        for r in range(8):
            out[row((g // 16) * 10 + r) + 4 + (g % 16) * 2] = data[g * 8 + r]
    return bytes(out)


HARNESS = r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include "a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi* api);
static struct A2fcApi api;
static struct Entry sel;
static char full[] = "font.bin", note[80], reselect[20];
static unsigned char copy[512];
static int fault, reads;
static FILE* __fastcall__ h_fopen(const char* p, const char* m) { return fault == 1 ? 0 : fopen(p, m); }
static size_t __fastcall__ h_fread(void* p, size_t s, size_t n, FILE* f)
{
    if (fault == 2 && ++reads == 3) { ((unsigned char*)f)[1] |= 4; return 0; }
    if (fault == 4) {                   /* the end of the file read as an error */
        size_t r = fread(p, s, n, f);
        if (r < n) ((unsigned char*)f)[1] |= 4;
        return r;
    }
    return fread(p, s, n, f);
}
static int __fastcall__ h_fclose(FILE* f) { int r = fclose(f); return fault == 3 ? -1 : r; }
static char* __fastcall__ h_strcpy(char* d, const char* s) { return strcpy(d, s); }
static char h_wait(void)
{
    unsigned char mark = 0xA5;
    write(1, &mark, 1);
    write(1, (void*)0x2000, 0x2000);
    return 27;
}
int main(int argc, char** argv)
{
    unsigned char n;
    FILE* f = fopen(full, "rb");
    long size = 0;
    if (!f) return 10;
    while (fread(copy, 1, 1, f) == 1) ++size;
    fclose(f);
    strcpy(sel.name, "FONT");
    sel.size = size;
    sel.type = atoi(argv[1]);
    fault = atoi(argv[2]);
    api.full = full; api.copy_buf = copy; api.note = note; api.reselect = reselect;
    api.selected = &sel;
    api.fopen = h_fopen; api.fread = h_fread; api.fclose = h_fclose;
    api.strcpy = h_strcpy; api.media_wait = h_wait;
    memset((void*)0x2000, 0xEE, 0x2000);
    plugin_entry(&api);
    n = 0x5A;
    write(1, &n, 1);
    n = strlen(note);
    write(1, &n, 1);
    write(1, note, n);
    return 0;
}
'''


def mgtk(rng, count, height, cols):
    widths = [rng.randint(1, 7 * cols) for _ in range(count)]
    planes = bytes(rng.randrange(128) for _ in range(height * cols * count))
    return bytes([0 if cols == 1 else 128, count - 1, height]) + bytes(widths) + planes


class FontView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-fontview-')
        cls.dir = Path(cls.tmp.name)
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        shutil.copyfile(ROOT / 'src/plugins/fontview.c', cls.dir / 'fontview.c')
        shutil.copyfile(ROOT / 'src/plugins/fontview.s', cls.dir / 'fontview_svc.s')
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
                            '-o', str(exe), str(cls.dir / 'harness.c'), str(cls.dir / 'fontview.c'),
                            str(cls.dir / 'fontview_svc.s')], check=True, cwd=cls.dir,
                           capture_output=True)
            cls.programs[cpu] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_fv(self, cpu, data, ftype=7, fault=0):
        (self.dir / 'font.bin').write_bytes(data)
        out = subprocess.run(['sim65', str(self.programs[cpu]), str(ftype), str(fault)],
                             cwd=self.dir, capture_output=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        o = out.stdout
        page = None
        if o[0] == 0xA5:
            page, o = o[1:0x2001], o[0x2001:]
        self.assertEqual(o[0], 0x5A)
        return page, o[2:2 + o[1]].decode()

    def shows(self, data, want, ftype=7):
        for cpu in self.programs:
            with self.subTest(cpu=cpu, size=len(data), type=ftype):
                page, note = self.run_fv(cpu, data, ftype)
                self.assertEqual(note, '')
                self.assertIsNotNone(page, 'nothing shown')
                self.assertEqual(page, want)

    def refused(self, data, ftype=7, fault=0):
        for cpu in self.programs:
            with self.subTest(cpu=cpu, size=len(data), type=ftype, fault=fault):
                page, note = self.run_fv(cpu, data, ftype, fault)
                self.assertEqual((page, note), (None, 'Bad data/I/O'))

    def test_mgtk_fonts(self):
        rng = random.Random(1)
        self.shows(bytes([128, 127, 16]) + bytes([14] * 128) + bytes((i * 31) & 127 for i in range(4096)),
                   mgtk_page(bytes([128, 127, 16]) + bytes([14] * 128) + bytes((i * 31) & 127 for i in range(4096))))
        for count, height, cols in ((1, 1, 1), (96, 8, 1), (128, 22, 2), (17, 5, 2)):
            data = mgtk(rng, count, height, cols)
            self.shows(data, mgtk_page(data))
        exact = mgtk(rng, 85, 8, 1)           # an MGTK font of exactly 768 bytes
        self.assertEqual(len(exact), 768)
        self.shows(exact, mgtk_page(exact))

    def test_hires_fonts(self):
        rng = random.Random(2)
        for size in (768, 1024):
            data = bytes(rng.randrange(256) for _ in range(size))
            for ftype in (7, 6, 0):
                self.shows(data, raw_page(data), ftype)
        # a 768-byte file whose header reads as MGTK but whose size does not match
        data = bytes([0, 95, 8]) + bytes(rng.randrange(256) for _ in range(765))
        self.shows(data, raw_page(data))
        stock = cp2_samples.volume().get('/GRAPHICS/STANDARD')
        if stock:
            self.shows(stock[2], raw_page(stock[2]))

    def test_refusals(self):
        for head in (b'\x01\x7f\x08', b'\0\xff\x08', b'\0\x80\x08', b'\0\x7f\0', b'\0\x7f\x17'):
            self.refused(head + bytes(5000))
        self.refused(b'\0\x7f\x08' + bytes([8]) * 128 + bytes(1024))     # a width past 7
        self.refused(b'\0\x01\x17' + bytes([7, 7]) + bytes(2 * 23))      # 23 rows: one too many
        self.shows(b'\0\x01\x16' + bytes([7, 7]) + bytes(2 * 22), bytes(8192))
        good = mgtk(random.Random(3), 20, 6, 2)
        self.refused(good, ftype=6)                                       # MGTK only as FNT
        for n in (0, 1, 2, 3, len(good) // 2, len(good) - 1):
            self.refused(good[:n])
        self.refused(good + b'X')
        self.refused(bytes(767), ftype=6)
        self.refused(bytes(1025), ftype=6)
        for fault in (1, 2, 3, 4):
            self.refused(good, fault=fault)
            self.refused(bytes(768), fault=fault)


if __name__ == '__main__':
    unittest.main()
