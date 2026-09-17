"""AWDATA against its reference: every screen of real and synthetic files.

The overlay's C (src/plugins/awdata.c) is built for the host and driven key
by key through its entry point; each screen it draws -- rows 0-21 and the
status bar -- is compared with tools/awdata_ref.py. Numbers are not printed
by the ROM there: the host stand-in for aw_fout writes the packed 5-byte
number in hex, and the reference is told to do the same, so the screens
check the conversion to the ROM's form as well as the layout.

The assembly conversion itself (src/plugins/awdata.s, built with AW_TEST)
runs under sim65 on both processors against the reference's mbf(). What
Applesoft's FOUT then prints is bench/awdata.py's, on POM2's ROM.
"""
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import os  # noqa: E402
import awdata_ref as ref  # noqa: E402
import cp2_samples  # noqa: E402
from test_six_plugins import PREFIX  # noqa: E402

HOST = PREFIX + r'''
#include <stdarg.h>
char aw_num[17];
void aw_fout(const unsigned char* d);
#include "src/plugins/awdata.c"
static FILE* host;
static unsigned char hx, hy;
static char screen[24][81];
static const char* script;
static unsigned char buffer[512];
void aw_fout(const unsigned char* d)
{
    unsigned int e = ((d[7] & 0x7F) << 4) | (d[6] >> 4);
    unsigned long m;
    unsigned char p[5];
    int x;
    if (!e) { memset(p, 0, 5); }
    else {
        m = 0x80000000UL | ((unsigned long)(d[6] & 15) << 27) | ((unsigned long)d[5] << 19)
            | ((unsigned long)d[4] << 11) | ((unsigned long)d[3] << 3) | (d[2] >> 5);
        if (d[2] & 0x10) { m = (m + 1) & 0xFFFFFFFFUL; if (!m) { m = 0x80000000UL; ++e; } }
        x = (int)e - 894;
        if (x < 1 || x > 255) { strcpy(aw_num, "#NUM"); return; }
        p[0] = x; p[1] = ((m >> 24) & 0x7F) | (d[7] & 0x80);
        p[2] = m >> 16; p[3] = m >> 8; p[4] = m;
    }
    sprintf(aw_num, "<%02X%02X%02X%02X%02X>", p[0], p[1], p[2], p[3], p[4]);
}
static size_t rd_(void* p, size_t z, size_t n, FILE* f) { return fread(p, z, n, host); }
static int seek_(FILE* f, long off, int whence) { return fseek(host, off, whence); }
static FILE* open_(const char* name, const char* mode) { return host; }
static int close_(FILE* f) { return 0; }
static void xy_(unsigned char x, unsigned char y) { hx = x; hy = y; }
static void puts_host(const char* s)
{
    while (*s) { if (hy < 24 && hx < 80) screen[hy][hx] = *s; ++hx; ++s; }
}
static int printf_(const char* fmt, ...)
{
    char b[200];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(b, sizeof b, fmt, ap);
    va_end(ap);
    puts_host(b);
    return 0;
}
static void clr_(void) { memset(screen, 0, 22 * 81); }
static void bar_(void) { memset(screen[23], 0, 81); hx = 0; hy = 23; }
static void keys_(unsigned char x, const char* s) { }
static char getc_(void)
{
    int r;
    printf("SCREEN\n");
    for (r = 0; r < 24; ++r) {             /* the gaps a row leaves read as spaces */
        int c, last = -1;
        for (c = 0; c < 80; ++c) if (screen[r][c]) last = c;
        for (c = 0; c < last; ++c) if (!screen[r][c]) screen[r][c] = ' ';
    }
    for (r = 0; r < 22; ++r) printf("|%s\n", screen[r]);
    printf("BAR %s\n", screen[23]);
    return *script ? *script++ : 27;
}
static char* strcpy_(char* d, const char* s) { return strcpy(d, s); }
static char note[80], full[80];
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Entry sel;
    host = fopen(argv[1], "rb");
    fseek(host, 0, SEEK_END); sel.size = ftell(host); rewind(host);
    sel.type = strtol(argv[2], 0, 16);
    strcpy(sel.name, "SAMPLE");
    strcpy(full, "/V/SAMPLE");
    script = argv[3];
    api.fread = rd_; api.fseek = seek_; api.fopen = open_; api.fclose = close_;
    api.gotoxy = xy_; api.cputs = puts_host; api.cprintf = printf_; api.clrscr = clr_;
    api.bar_begin = bar_; api.keys_bar = keys_; api.cgetc = getc_; api.strcpy = strcpy_;
    api.selected = &sel; api.full = full; api.note = note; api.copy_buf = buffer;
    plugin_entry(&api);
    printf("NOTE %s\n", note);
    return 0;
}
'''

SIM = r'''
#include <fcntl.h>
#include <unistd.h>
extern char aw_num[];
void __fastcall__ aw_fout(const unsigned char* d);
int main(void)
{
    unsigned char d[8];
    unsigned char n;
    int in = open("nums.bin", O_RDONLY);
    while (read(in, d, 8) == 8) {
        aw_fout(d);
        for (n = 0; aw_num[n]; ++n) ;
        write(1, aw_num, n);
        write(1, "\n", 1);
    }
    return 0;
}
'''


def hexfout(p):
    return '<%s>' % p.hex().upper()


def db_screens(data):
    names, recs, end = ref.db_records(data)
    out = []
    for k, values in enumerate(recs):
        rows = ref.db_screen(names, values)
        cut = '' if end else ' (cut)'
        out.append((rows, 'SAMPLE  record %d of %d%s' % (k + 1, len(recs), cut)))
    return names, out


def ss_screens(data):
    lines, end = ref.ss_lines(data)
    pages = [lines[i:i + ref.ROWS] for i in range(0, max(len(lines), 1), ref.ROWS)]
    out = []
    for k, rows in enumerate(pages):
        tail = ''
        if k == len(pages) - 1:
            tail = ' (end)' if end else ' (cut)'
        out.append((rows, 'SAMPLE  page %d%s' % (k + 1, tail)))
    return out


# -- synthetic files -----------------------------------------------------------

def aw_text(rng, n):
    pool = bytes(range(0x20, 0x7F)) + bytes([0x81, 0x9A, 0xA1, 0xC5, 0xE1, 0xFE, 0x05])
    return bytes(rng.choice(pool) for _ in range(n))


def make_db(rng, ncats, nrecs, reports=0, dates=True, end=True):
    head = bytearray(357 + 22 * ncats)
    head[0:2] = len(head).to_bytes(2, 'little')
    head[35] = ncats
    head[36:38] = nrecs.to_bytes(2, 'little')
    head[38] = reports
    for i in range(ncats):
        name = aw_text(rng, rng.randint(0, 20))
        o = 357 + 22 * i
        head[o] = len(name)
        head[o + 1:o + 1 + len(name)] = name
    body = bytearray(bytes(600) * reports)

    def record():
        r = bytearray()
        cat = 0
        while cat < ncats:
            k = rng.random()
            if k < 0.2:
                skip = rng.randint(1, min(30, ncats - cat))
                r.append(0x80 + skip)
                cat += skip
                continue
            if dates and k < 0.35:
                r += bytes([6, 0xC0]) + rng.choice([b'70', b'00', b'99']) + bytes([rng.choice(b'ABLMZ')]) + rng.choice([b'05', b' 3', b'00', b'31'])
            elif dates and k < 0.45:
                r += bytes([4, 0xD4, rng.choice(b'AKLXY')]) + rng.choice([b'05', b'59', b'x0'])
            else:
                v = aw_text(rng, rng.randint(1, 90))
                r += bytes([len(v)]) + v
            cat += 1
        r.append(0xFF)
        return bytes(r)
    for _ in range(nrecs + 1):
        rec = record()
        body += len(rec).to_bytes(2, 'little') + rec
    if end:
        body += b'\xff\xff'
    return bytes(head + body)


def dbl(v):
    return struct.pack('<d', v)


def make_ss(rng, nrows, v3=True, end=True):
    head = bytearray(300)
    head[242] = 30 if v3 else 0
    body = bytearray(b'\x00\x00' if v3 else b'')
    row = 0
    for _ in range(nrows):
        row += rng.randint(1, 3)
        r = bytearray(row.to_bytes(2, 'little'))
        col = 0
        while col < 60 and rng.random() < 0.9:
            if rng.random() < 0.2:
                skip = rng.randint(1, 20)
                r.append(0x80 + skip)
                col += skip
                continue
            r += cell(rng, col, row)
            col += 1
        r.append(0xFF)
        body += len(r).to_bytes(2, 'little') + r
    if end:
        body += b'\xff\xff'
    return bytes(head + body)


def tokens(rng):
    t = bytearray()
    for _ in range(rng.randint(1, 8)):
        k = rng.random()
        if k < 0.2:
            t += b'\xfd' + dbl(rng.choice([0.5, 12.0, -3.25, 1e20, 1 / 7]))
        elif k < 0.45:
            t += b'\xfe' + struct.pack('<bh', rng.randint(-5, 5), rng.randint(-10, 10))
        elif k < 0.55:
            s = aw_text(rng, rng.randint(0, 12))
            t += b'\xff' + bytes([len(s)]) + s
        elif k < 0.6:
            t += bytes([rng.choice([0xE0, 0xE7])]) + bytes(3)
        elif k < 0.65:
            t.append(rng.randint(0, 0xBF))
        else:
            t.append(rng.randint(0xC0, 0xFC))
    return bytes(t)


def cell(rng, col, row):
    k = rng.random()
    if k < 0.3:
        s = aw_text(rng, rng.randint(0, 40))
        c = bytes([0x00]) + s
    elif k < 0.35:
        c = bytes([0x20, rng.randint(0x20, 0x7E)])
    elif k < 0.55:
        c = bytes([0xA0, 0x00]) + dbl(rng.choice([0.0, 1.0, -2.5, 1e-5, 123456789.0, 1e9, 3.0e-310, 1e300]))
    elif k < 0.75:
        c = bytes([0x80, 0x00]) + dbl(rng.uniform(-1e6, 1e6)) + tokens(rng)
    else:
        s = aw_text(rng, rng.randint(0, 30))
        c = bytes([0x80, 0x08, len(s)]) + s + tokens(rng)
    return bytes([len(c)]) + c


class AwData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-awdata-')
        cls.dir = Path(cls.tmp.name)
        (cls.dir / 'host.c').write_text(HOST)
        cls.exe = cls.dir / 'host'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-D_FORTIFY_SOURCE=0',
                        '-I', str(ROOT), str(cls.dir / 'host.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)
        ref.FOUT = hexfout

    @classmethod
    def tearDownClass(cls):
        ref.FOUT = ref.fout
        cls.tmp.cleanup()

    def run_host(self, data, typ, keys):
        f = self.dir / 'in.bin'
        f.write_bytes(data)
        out = subprocess.run([str(self.exe), str(f), typ, keys], capture_output=True,
                             timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        screens, note = [], None
        for line in out.stdout.decode('latin-1').splitlines():
            if line == 'SCREEN':
                screens.append([[], None])
            elif line.startswith('|'):
                screens[-1][0].append(line[1:])
            elif line.startswith('BAR '):
                screens[-1][1] = line[4:]
            elif line.startswith('NOTE '):
                note = line[5:]
        return screens, note

    def check_db(self, data):
        names, want = db_screens(data)
        keys = ' ' * (len(want) - 1) + 'B' * (len(want) - 1)
        got, note = self.run_host(data, '19', keys)
        order = list(range(len(want))) + list(range(len(want) - 2, -1, -1))
        self.assertEqual(len(got), len(order))
        for (rows, bar), k in zip(got, order):
            want_rows, want_bar = want[k]
            self.assertEqual(bar, want_bar)
            expect = [r.rstrip() for r in want_rows]
            self.assertEqual([r.rstrip() for r in rows], expect + [''] * (ref.ROWS - len(expect)),
                             'record %d' % (k + 1))

    def check_ss(self, data):
        want = ss_screens(data)
        keys = ' ' * (len(want) - 1) + ' ' + 'B' * (len(want) - 1)
        got, note = self.run_host(data, '1B', keys)
        order = list(range(len(want))) + [len(want) - 1] + list(range(len(want) - 2, -1, -1))
        self.assertEqual(len(got), len(order))
        for (rows, bar), k in zip(got, order):
            want_rows, want_bar = want[k]
            self.assertEqual(bar, want_bar)
            self.assertEqual(rows, want_rows + [''] * (ref.ROWS - len(want_rows)), 'page %d' % (k + 1))

    def test_the_ciderpress_samples(self):
        v = cp2_samples.volume()
        if not v:
            self.skipTest('no CiderPress II samples (tools/cp2_samples.py)')
        self.check_db(v['/DOCS/PRESIDENTS'][2])
        self.check_ss(v['/DOCS/MATH.QUIZ'][2])

    def test_synthetic_data_bases(self):
        rng = random.Random(3)
        for i in range(25):
            data = make_db(rng, rng.randint(1, 22), rng.randint(0, 40), reports=rng.randint(0, 2),
                           end=i % 5 != 4)
            if i % 5 == 3:
                data = data[:-3]            # the last record one byte short
            names, recs, _ = ref.db_records(data)
            if not recs:
                continue
            with self.subTest(i=i):
                self.check_db(data)

    def test_synthetic_spreadsheets(self):
        rng = random.Random(4)
        for i in range(25):
            data = make_ss(rng, rng.randint(0, 30), v3=i % 2 == 0, end=i % 5 != 4)
            if i % 7 == 6:
                data = data[:len(data) * 2 // 3]
            with self.subTest(i=i):
                self.check_ss(data)

    def test_refusals(self):
        rng = random.Random(5)
        good = make_db(rng, 3, 2)
        for data, typ, note in (
                (good, '1A', 'Not an AppleWorks data base or spreadsheet.'),
                (good[:300], '19', 'Not an AppleWorks data base.'),
                (bytes(35) + b'\x00' + good[36:], '19', 'Not an AppleWorks data base.'),
                (bytes(35) + b'\x1f' + good[36:], '19', 'Not an AppleWorks data base.'),
                (make_db(rng, 3, 0)[:-2] + b'\xff\xff', '19', None),
                (bytes(301), '1B', 'Not an AppleWorks spreadsheet.')):
            screens, got = self.run_host(data, typ, '')
            if note is None:
                continue
            self.assertEqual(got, note)
            self.assertEqual(screens, [])

    def test_asm_conversion_under_sim65(self):
        rng = random.Random(6)
        values = [0.0, -0.0, 1.0, -1.0, 0.5, 0.1, 1 / 3, 1e38, 1.7e38, 1e39, 1e-38, 3e-39,
                  1e-40, 5e-324, 1e300, float('inf'), float('nan'), 2.0 ** 32 - 1,
                  0.99999999999999989, 1.9999999999999998, 4294967295.5]
        values += [rng.uniform(-1, 1) * 10 ** rng.randint(-45, 45) for _ in range(400)]
        raw = b''.join(dbl(v) for v in values)
        raw += bytes([0xFF, 0xFF, 0xFF, 0xFF, 0xF0, 0xFF, 0x0F, 0x3F])   # a 1.111... that rounds up
        (self.dir / 'nums.bin').write_bytes(raw)
        want = []
        for i in range(0, len(raw), 8):
            p = ref.mbf(raw[i:i + 8])
            want.append('#NUM' if p is None else hexfout(p))
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        shutil.copyfile(ROOT / 'src/plugins/awdata.s', self.dir / 'awdata.s')
        (self.dir / 'sim.c').write_text(SIM)
        for cpu in ('sim6502', 'sim65c02'):
            exe = self.dir / cpu
            subprocess.run(['cl65', '-t', cpu, '--asm-define', 'AW_TEST', '-O', '-o', str(exe),
                            str(self.dir / 'sim.c'), str(self.dir / 'awdata.s')],
                           check=True, cwd=self.dir, capture_output=True)
            out = subprocess.run(['sim65', str(exe)], cwd=self.dir, capture_output=True,
                                 timeout=120)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(out.stdout.decode().split('\n')[:-1], want, cpu)

    def test_rom_fout_under_sim65_when_the_rom_is_there(self):
        """The shipped aw_fout, zero-page save and all, calling MOVFM and FOUT
        in an Apple II+ ROM loaded at $D000 (A2FC_ROM; POM2's by default)."""
        rom = Path(os.environ.get('A2FC_ROM', str(Path.home() / 'src/pom2/roms/apple2p.rom')))
        if not rom.exists():
            self.skipTest('no Apple II ROM image (A2FC_ROM)')
        data = rom.read_bytes()[-0x3000:]
        (self.dir / 'rom.bin').write_bytes(data)
        rng = random.Random(8)
        values = [0.5, 1.0, -2.25, 100.0, 0.01, 0.001, 123456789.0, 1e9, 1234567891.0,
                  1 / 3, 0.1, -1e-10, 2.0 ** 100, 0.0, 1e300, 65535.0, -0.75, 1e-38,
                  99999999.5, 12.5e6, 7e-3, 2.5e-2, 999999999.0, 999999999.5]
        values += [rng.uniform(-1, 1) * 10 ** rng.randint(-37, 37) for _ in range(300)]
        (self.dir / 'nums.bin').write_bytes(b''.join(dbl(v) for v in values))
        harness = r"""
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
extern char aw_num[];
void __fastcall__ aw_fout(const unsigned char* d);
int main(void)
{
    unsigned char d[8];
    unsigned char n;
    int in = open("rom.bin", O_RDONLY);
    if (read(in, (void*)0xD000, 0x3000) != 0x3000) return 9;
    close(in);
    in = open("nums.bin", O_RDONLY);
    while (read(in, d, 8) == 8) {
        memset((void*)0x50, 0xFF, 0x60);        /* whatever the program left */
        aw_fout(d);
        for (n = 0; aw_num[n]; ++n) ;
        write(1, aw_num, n);
        write(1, "\n", 1);
    }
    return 0;
}
"""
        (self.dir / 'romsim.c').write_text(harness)
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        cfg = (target.parent / 'cfg/sim6502.cfg').read_text()
        cfg = cfg.replace('start = $0200, size = $FDF0 - __STACKSIZE__',
                          'start = $0800, size = $C000 - $0800 - __STACKSIZE__')
        (self.dir / 'romsim.cfg').write_text(cfg)
        shutil.copyfile(ROOT / 'src/plugins/awdata.s', self.dir / 'awdata.s')
        exe = self.dir / 'romsim'
        subprocess.run(['cl65', '-t', 'sim6502', '-C', str(self.dir / 'romsim.cfg'), '-O',
                        '-o', str(exe), str(self.dir / 'romsim.c'), str(self.dir / 'awdata.s')],
                       check=True, cwd=self.dir, capture_output=True)
        out = subprocess.run(['sim65', str(exe)], cwd=self.dir, capture_output=True, timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr)
        shown = out.stdout.decode().split('\n')[:-1]
        self.assertEqual(len(shown), len(values))
        for v, got in zip(values, shown):
            p = ref.mbf(dbl(v))
            want = '#NUM' if p is None else ref.fout(p)
            self.assertTrue(ref.same_number(got, want), (v, got, want))
        self.assertEqual(shown[:12], ['.5', '1', '-2.25', '100', '.01', '1E-03', '123456789',
                                      '1E+09', '1.23456789E+09', '.333333333', '.1', '-1E-10'])


if __name__ == '__main__':
    unittest.main()
