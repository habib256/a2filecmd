"""VISICALC (src/plugins/visicalc.s) against tools/visicalc_ref.py, and the
reference against VisiCalc itself.

- The reference against the oracle: what VisiCalc 1.93 showed, under POM2,
  for the real worksheets and the probe sheets kept privately in
  ~/.cache/a2fc/visicalc (A2FC_VISICALC): every cell, character for
  character, but for the differences docs/VISICALC-FORMAT.md lists (the
  powers and functions VisiCalc computes with its own series, the overlay
  on the ROM; a left-aligned zero VisiCalc's redraw sometimes leaves
  undrawn). The probe sheets, written here to measure it, and their
  captures are public (tools/visicalc_probes.json.gz); the real
  worksheets' captures are skipped when they are not there.
- The arithmetic and the display in assembly: thousands of random numbers
  and operations through vc_parse, vc_add..., vc_format, on both
  processors under sim65, against the reference digit for digit.
- The whole overlay under sim65 (VC_FLAT: the phases in place, the cell
  table in a big window), on both processors: the screens after keys,
  against the reference's, for worksheets written here (and the private
  ones when present) -- formats, order of recalculation, references ahead,
  files out of VisiCalc's order, repeated cells -- and hostile ones: lines
  past 255 characters, parentheses 300 deep, 250 operators, a call nested
  past the value stack, references off the sheet, no settings line, bytes
  with the high bit, garbage. None may hang (sim65's cycle limit), each
  must end on the reference's screen or its refusal.
- Escape while the worksheet is read and recalculated (class Escape): the
  key put in the keyboard register by the harness at a chosen read of the
  file, the cycles counted from there to the return (sim65's counter).
- The phases built by make share their link's identity.

cc65 master (CC65_HEAD, ~/opt/cc65-head) builds and runs these: the sim65
of cc65 2.18 gets the 6502's decimal flags wrong, which VisiCalc's
arithmetic is made of. The ROM functions need an Apple II ROM (A2FC_ROM).

    python3 tools/test_visicalc.py
"""
import gzip
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import visicalc_ref as R  # noqa: E402

HEAD = Path(os.environ.get('CC65_HEAD', Path.home() / 'opt/cc65-head'))
ROM = Path(os.environ.get('A2FC_ROM', Path.home() / 'src/pom2/roms/apple2p.rom'))
PRIVATE = Path(os.environ.get('A2FC_VISICALC', Path.home() / '.cache/a2fc/visicalc'))
CPUS = ('sim6502', 'sim65c02')
FM = {0: '', 1: '', 2: 'I', 3: 'L', 4: 'R', 5: '$', 6: '*'}
MATH = ('^', '@SIN', '@COS', '@TAN', '@ASIN', '@ACOS', '@ATAN', '@LN', '@LOG10', '@EXP', '@SQRT')


def tool(name):
    return str(HEAD / 'bin' / name)


def env():
    e = dict(os.environ)
    e['CC65_HOME'] = str(HEAD / 'share/cc65')
    return e


def have_head():
    return (HEAD / 'bin/sim65').exists() and (HEAD / 'bin/cl65').exists()


def sim_cfg(cpu, path, keep='$0100'):
    """cc65's sim cfg, the program below $A000 (the ROM goes at $D000),
    with the overlay's segments and the link symbols visicalc.s imports
    (VC_KEEP puts the swap area at $1B00 + keep)."""
    target = Path(subprocess.check_output([tool('cl65'), '--print-target-path'],
                                          text=True, env=env()).strip())
    t = (target.parent / 'cfg' / (cpu + '.cfg')).read_text()
    t, n = re.subn(r'size = \$F[0-9A-F]+ (- \$0200 )?- __STACKSIZE__',
                   'size = $A000 - $0200 - __STACKSIZE__', t)
    assert n == 1, 'the sim cfg changed'
    t = t.replace('    RODATA:', '    OVLHDR:   load = MAIN, type = ro;\n'
                  '    VCA: load = MAIN, type = ro, define = yes;\n'
                  '    VCB: load = MAIN, type = ro, define = yes;\n'
                  '    VCC: load = MAIN, type = ro, define = yes;\n    RODATA:', 1)
    t = t.replace('SYMBOLS {', 'SYMBOLS {\n    VC_KEEP: type = export, value = %s;\n' % keep +
                  '    VC_SWAP: type = export, value = $0100;', 1)
    t, n = re.subn(r'(\n\s*CODE:\s*load = MAIN,\s*type = ro)', r'\1, define = yes', t, count=1)
    assert n == 1
    path.write_text(t)


def build(tmp, harness, name, top='$9800', flat=True, keep='$0100', defs=()):
    """The harness and visicalc.s (VC_FLAT, unless `flat` is false), for
    both processors; `defs`: more symbols for visicalc.s. Copies under
    other names: cl65 writes a .s beside a .c."""
    d = Path(tmp)
    shutil.copyfile(ROOT / 'src/a2fc_plugin.h', d / 'a2fc_plugin.h')
    (d / 'p').mkdir(exist_ok=True)
    shutil.copyfile(ROOT / 'src/a2fc_plugin.h', d / 'p/a2fc_plugin.h')
    shutil.copyfile(ROOT / 'src/plugins/visicalc.c', d / 'p/vc_hdr.c')
    shutil.copyfile(ROOT / 'src/plugins/visicalc.s', d / 'vc_core.s')
    (d / (name + '.c')).write_text(harness)
    exes = {}
    for cpu in CPUS:
        sim_cfg(cpu, d / (cpu + '.cfg'), keep)
        obj = d / ('%s_%s.o' % (name, cpu))
        subprocess.run([tool('ca65'), '-t', cpu, '-D', 'VC_LOW=$B000', '-D', 'VC_TOP=' + top,
                        '-D', 'VC_TICK=$B3FF', *(['-D', 'VC_FLAT'] if flat else []),
                        *[x for s in defs for x in ('-D', s)],
                        '-o', str(obj), str(d / 'vc_core.s')],
                       check=True, env=env(), capture_output=True)
        exe = d / ('%s-%s' % (name, cpu))
        p = subprocess.run([tool('cl65'), '-t', cpu, '-I', str(d), '-C', str(d / (cpu + '.cfg')),
                            '-O', '-o', str(exe), str(d / (name + '.c')), str(d / 'p/vc_hdr.c'),
                            str(obj)], env=env(), capture_output=True, text=True, cwd=d)
        assert p.returncode == 0, p.stderr
        exes[cpu] = exe
    return exes


# -- the arithmetic and the display --------------------------------------------------

CORE = r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
extern unsigned char vc_acc[9], vc_arg[9];
extern char vc_out[80];
extern unsigned char vc_fmt;
unsigned char __fastcall__ vc_parse(const char* s);
void __fastcall__ vc_format(unsigned char w);
void vc_add(void); void vc_sub(void); void vc_mul(void); void vc_div(void);
signed char vc_cmp(void); void vc_int(void);
void __fastcall__ vc_pack(unsigned char* d);
void __fastcall__ vc_unpack(const unsigned char* s);
static char line[200];
static unsigned char save[9], pk[7];
int main(void)
{
    char *a, *b, *op, *w, *f;
    unsigned char i, n;
    while (fgets(line, sizeof line, stdin)) {
        op = strtok(line, " \n"); a = strtok(0, " \n"); b = strtok(0, " \n");
        w = strtok(0, " \n"); f = strtok(0, " \n");
        if (!op) continue;
        n = vc_parse(b); memcpy(save, vc_acc, 9);
        n = vc_parse(a);
        memcpy(vc_arg, save, 9);
        if (vc_acc[0] == 0 && vc_arg[0] == 0) {
            switch (*op) {
            case '+': vc_add(); break;
            case '-': vc_sub(); break;
            case '*': vc_mul(); break;
            case '/': vc_div(); break;
            case 'c': i = vc_cmp(); vc_parse(i == 0 ? "0" : i == 1 ? "1" : "2"); break;
            case 'i': vc_int(); break;
            case 'p': vc_pack(pk); vc_unpack(pk); break;
            }
        }
        vc_fmt = *f - '0';
        vc_format((unsigned char)atoi(w));
        printf("%u", n);
        for (i = 0; i < 9; ++i) printf(" %02X", vc_acc[i]);
        printf(" |%s|\n", vc_out);
    }
    return 0;
}
'''


def literal(rnd):
    k = rnd.random()
    if k < 0.3:
        n = rnd.randint(1, 14)
        return str(rnd.randint(10 ** (n - 1), 10 ** n - 1))
    if k < 0.7:
        n = rnd.randint(1, 14)
        d = str(rnd.randint(10 ** (n - 1), 10 ** n - 1))
        p = rnd.randint(-6, n)
        return ('.' + '0' * (-p) + d) if p <= 0 else d[:p] + '.' + d[p:]
    if k < 0.85:
        return rnd.choice(['9.99999', '99.9995', '.099999', '999.5', '.5', '.05', '.95', '9.5', '99.5',
                           '.0095', '9999999.5', '99999.95', '.999999', '0', '00.5', '1', '100', '.0', '0.'])
    return '%dE%d' % (rnd.randint(0, 99), rnd.randint(-70, 64))


def ref_core(op, a, b, w, f):
    def num(s):
        try:
            r = R.parse_number(s, 0)
            return r[0] if r and r[1] == len(s) else None
        except R.Err:
            return 'ERR'
    va, vb = num(a), num(b)
    if va == 'ERR':
        v = R.ERROR
    else:
        v = va
        if vb != 'ERR':
            try:
                if op == '+':
                    v = R.add(va, vb)
                elif op == '-':
                    v = R.sub(va, vb)
                elif op == '*':
                    v = R.mul(va, vb)
                elif op == '/':
                    v = R.div(va, vb)
                elif op == 'c':
                    v = R.Num.from_int({0: 0, 1: 1, -1: 2}[R.cmp(va, vb)])
                elif op == 'i':
                    v = R.Num.from_fraction(Fraction(int(va.frac())))
            except R.Err:
                v = R.ERROR
    return R.show_value(v, FM[f], w), v


@unittest.skipUnless(have_head(), 'cc65 master (CC65_HEAD) not installed')
class Core(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-visicalc-core-')
        cls.exe = build(cls.tmp.name, CORE, 'core')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_cases(self, cases):
        inp = ''.join('%s %s %s %d %d\n' % c for c in cases)
        for cpu, exe in self.exe.items():
            out = subprocess.run([tool('sim65'), str(exe)], input=inp, capture_output=True,
                                 text=True, env=env(), timeout=900).stdout.split('\n')
            self.assertGreaterEqual(len(out), len(cases), cpu)
            for c, o in zip(cases, out):
                exp, v = ref_core(*c)
                got = o[o.index('|') + 1:o.rindex('|')]
                self.assertEqual(got, exp, (cpu, c, o))
                bs = o.split()[1:10]
                if isinstance(v, R.Num) and v.m and bs[0] == '00':
                    self.assertEqual((int(bs[2], 16), int(''.join(bs[3:9])), bs[1] == '80'),
                                     (v.e + 64, v.m, v.neg), (cpu, c, o))

    def test_random_numbers(self):
        rnd = random.Random(1979)
        self.run_cases([(rnd.choice('+-*/ci') if rnd.random() < 0.85 else rnd.choice('pn'),
                         literal(rnd), literal(rnd), rnd.randint(1, 77), rnd.randint(0, 6))
                        for _ in range(2500)])

    def test_what_visicalc_showed(self):
        """Cases measured on VisiCalc (tools/visicalc_ref.py's selftest
        holds the same ones for the reference)."""
        self.run_cases([
            ('/', '1', '3', 9, 0), ('*', '.666666666666', '2', 36, 0), ('-', '1', '1E-12', 36, 0),
            ('+', '1E12', '.5', 36, 0), ('/', '2', '3', 9, 5), ('n', '999999999', '0', 9, 0),
            ('n', '1E-9', '0', 9, 0), ('-', '0', '.00274', 4, 5), ('n', '.0095', '0', 4, 0),
            ('-', '0', '41436.96', 9, 0), ('n', '.99999995', '0', 9, 0), ('n', '1E62', '0', 9, 0),
            ('n', '1E-66', '0', 9, 0), ('/', '1E-66', '2', 9, 0), ('n', '0', '0', 4, 5)])


# -- the whole overlay -------------------------------------------------------------------

SCREENS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include "a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
static char screen[24][80], inv[24][80];
static unsigned char cx, cy, rv;
static const char* keys;
static FILE* opn(const char* p, const char* m) { return fopen(p, m); }
static size_t rd(void* p, size_t s, size_t n, FILE* f) { return fread(p, s, n, f); }
static int cls(FILE* f) { return fclose(f); }
static int sk(FILE* f, long off, int whence)
{
    static unsigned char skip[128];
    if (whence != SEEK_SET || !freopen("sheet.txt", "rb", f)) return -1;
    while (off > 0) {
        size_t n = off > 128 ? 128 : (size_t)off;
        if (fread(skip, 1, n, f) != n) return -1;
        off -= n;
    }
    return 0;
}
static void pc(char c)
{
    if (cy < 24 && cx < 80) { screen[cy][cx] = c; inv[cy][cx] = rv ? '#' : ' '; }
    ++cx;
}
static void ps(const char* s) { while (*s) pc(*s++); }
static void xy(unsigned char x, unsigned char y) { cx = x; cy = y; }
static unsigned char rev(unsigned char r) { unsigned char o = rv; rv = r; return o; }
static void clr(void) { memset(screen, ' ', sizeof screen); memset(inv, ' ', sizeof inv); cx = cy = 0; }
static void bar(void) { memset(screen[23], ' ', 80); cx = 0; cy = 23; }
static void kb(unsigned char x, const char* s) { cx = x; cy = 23; ps(s); }
static char* scpy(char* d, const char* s) { return strcpy(d, s); }
static unsigned char rfmt(void) { return 1; }
static unsigned char nope(void) { return 0; }
static char cfg[] = "/V/A2FILE/A2FILE.CFG";
static char key(void)
{
    unsigned char r;
    for (r = 0; r < 24; ++r) { fwrite(screen[r], 1, 80, stdout); fwrite(inv[r], 1, 80, stdout); }
    return *keys ? *keys++ : 27;
}
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Entry e;
    static char note[80], full[] = "sheet.txt";
    static unsigned char copy_buf[512];
    int in;
    (void)argc;
    in = open("rom.bin", O_RDONLY);
    if (in >= 0) { read(in, (void*)0xD000, 0x2800); close(in); }
    keys = argv[1];
    e.size = atol(argv[2]);
    strcpy(e.name, "SHEET");
    *(unsigned char*)0xC000 = 0;          /* the keyboard: no key waiting */
    api.version = 6; api.copy_buf = copy_buf; api.full = full; api.selected = &e; api.note = note;
    api.fopen = opn; api.fread = rd; api.fclose = cls; api.fseek = sk; api.cfg_path = cfg;
    api.cputs = ps; api.gotoxy = xy; api.revers = rev; api.clrscr = clr; api.cgetc = key;
    api.strcpy = scpy; api.bar_begin = bar; api.keys_bar = kb; api.ram_format = rfmt; api.aux_consent = nope;
    clr();
    plugin_entry(&api);
    fwrite(note, 1, 80, stdout);
    return 0;
}
'''


def hi(text):
    return bytes((ord(c) | 0x80) if isinstance(c, str) else (c | 0x80) for c in text)


def sheet(cells, globs=('/W1', '/GOC', '/GRA', '/GC9', '/X>A1:>A1:'), high=True, order=None):
    """A /SS file: cells {name: contents} in VisiCalc's order (or `order`)."""
    def key(n):
        rr = R.parse_ref(n, 0)[0]
        return (-rr[1], -rr[0])
    names = order if order is not None else sorted(cells, key=key)
    text = '\r'.join(['>%s:%s' % (n, cells[n]) for n in names] + list(globs)) + '\r'
    return hi(text) if high else text.encode('latin-1')


def demo():
    import mkdemo_viewers
    return mkdemo_viewers.visicalc()


def screens_of(data, keys):
    """The reference's screens (rows, inverse) and its note."""
    text = bytes(b & 0x7F for b in data).decode('latin-1')
    sh = R.load(text)
    if not sh.valid:
        return [], 'Not a VisiCalc worksheet (T shows it as text).'
    v = R.View(sh)
    shots = [v.screen()]
    for k in keys:
        if not v.key(k):
            break
        shots.append(v.screen())
    return shots, ''


@unittest.skipUnless(have_head(), 'cc65 master (CC65_HEAD) not installed')
class Overlay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-visicalc-')
        cls.dir = Path(cls.tmp.name)
        cls.exe = build(cls.tmp.name, SCREENS, 'vc')
        cls.rom = ROM.exists()
        if cls.rom:
            (cls.dir / 'rom.bin').write_bytes(ROM.read_bytes()[-0x3000:][:0x2800])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def machine(self, data, keys='', exe=None):
        """Screens and note, the same on both processors."""
        (self.dir / 'sheet.txt').write_bytes(data)
        got = {}
        for cpu, path in (exe or self.exe).items():
            p = subprocess.run([tool('sim65'), '-x', '400000000', str(path), keys, str(len(data))],
                               cwd=self.dir, capture_output=True, env=env(), timeout=1200)
            self.assertEqual(p.returncode, 0, (cpu, p.returncode, p.stderr[-300:]))
            self.assertEqual((self.dir / 'sheet.txt').read_bytes(), data, 'the file is only read')
            o = p.stdout
            shots = []
            for k in range((len(o) - 80) // 3840):
                s = o[k * 3840:(k + 1) * 3840]
                shots.append(([s[r * 160:r * 160 + 80].decode('latin-1') for r in range(24)],
                              [s[r * 160 + 80:r * 160 + 160].decode('latin-1') for r in range(24)]))
            got[cpu] = (shots, o[-80:].split(b'\0')[0].decode('latin-1'))
        self.assertEqual(got['sim6502'], got['sim65c02'])
        return got['sim6502']

    def check(self, data, keys=''):
        shots, note = self.machine(data, keys)
        want, wnote = screens_of(data, keys)
        self.assertEqual(note.strip(), wnote)
        self.assertEqual(len(shots), len(want))
        for i, (a, b) in enumerate(zip(shots, want)):
            for r in range(24):
                self.assertEqual(a[0][r], b[0][r], (i, r))
                self.assertEqual(a[1][r], b[1][r], ('inverse', i, r))
        return shots

    @unittest.skipUnless(ROM.exists(), 'calls the Applesoft ROM (^, @ functions): no ROM image (A2FC_ROM)')
    def test_demo_worksheet(self):
        shots = self.check(demo(), '\x0b\x0b\x08 B>R<')
        rows = shots[0][0]
        self.assertIn('1802.85', rows[9])
        self.assertTrue(rows[0].startswith('D8 /F$ (V) @SUM(D4...D6)'))

    @unittest.skipUnless(ROM.exists(), 'calls the Applesoft ROM (^, @ functions): no ROM image (A2FC_ROM)')
    def test_order_and_references_ahead(self):
        cells = {'A1': '+B1', 'B1': '+C1', 'C1': '5', 'A2': '+A3', 'A3': '7', 'B2': '+A2*2',
                 'D4': '"HELLO', 'C3': '2+3*4', 'B3': '-2^2', 'A5': '@SUM(A1...A3)', 'B5': '+7'}
        for order in ('/GOC', '/GOR'):
            shots = self.check(sheet(cells, ('/W1', order, '/GRA', '/GC9', '/X>A1:>A1:')))
            self.assertEqual(shots[0][0][2][3:12], '    ERROR', order)   # A1: B1 not reached yet

    def test_formats_widths_and_labels(self):
        cells = {'A1': '/F$1.005', 'B1': '/FI-2.5', 'C1': '/FL5', 'D1': '/FR"ABC', 'E1': '/F*7.9',
                 'A2': '/-=', 'B2': '/-AB', 'C2': '"A LABEL LONGER THAN ITS COLUMN', 'D2': 'E1',
                 'A3': '1/3', 'B3': '1E-9', 'C3': '999999999', 'D3': '-.0000815707', 'E3': '@NA',
                 'A4': '@ERROR', 'B4': '1=1', 'C4': '/F$', 'D4': '/FD/F$7', 'E4': '/FG1/3'}
        for w in (3, 5, 9, 14):
            self.check(sheet(cells, ('/W1', '/GOC', '/GRA', '/GC%d' % w, '/X>A1:>A1:')), '\x15\x15\x15>')
        self.check(sheet(cells, ('/W1', '/GOC', '/GRA', '/GF$', '/GC9', '/X>A1:>C2:')))
        # VisiCalc 2's column widths, window 1's only
        self.check(sheet(dict(cells, **{'A1': '/GCC3', 'B1': '/GCC14'}),
                         ('/W1', '/GOC', '/GRA', '/GC9', '/X>A1:>A1:;/GC4', '/X>A1:>A1:')),
                   '\x15\x15\x15\x15')

    def test_functions(self):
        cells = {'A1': '1', 'A2': '2', 'A3': '"LAB', 'A5': '4', 'A6': '@NA', 'A7': '@ERROR',
                 'B1': '@SUM(A1...A5)', 'B2': '@COUNT(A1...A7)', 'B3': '@AVERAGE(A1...A5)',
                 'B4': '@MIN(A1...A5)', 'B5': '@MAX(A1,A2,10)', 'B6': '@SUM(A6...A7)',
                 'B7': '@NPV(.1,A1...A2)', 'B8': '@LOOKUP(1.5,A1...A2)', 'B9': '@CHOOSE(2,7,8,9)',
                 'B10': '@IF(A1>0,@TRUE,@FALSE)', 'B11': '@AND(@TRUE,1<2)', 'B12': '@OR(@FALSE,@NA)',
                 'B13': '@NOT(@TRUE)', 'B14': '@ISNA(A6)', 'B15': '@ISERROR(1/0)', 'B16': '@INT(-2.5)',
                 'B17': '@ABS(-3.5)', 'B18': '@PI', 'B19': '@SUM(C1...E1)', 'B20': '@AVERAGE(A3...A4)',
                 'C1': '5', 'D1': '6', 'E1': '"X', 'C2': '(1+2', 'C3': '@IF(@TRUE,1,(2', 'C4': '1/3*3',
                 'C5': '@COUNT(A3,A4)', 'C6': '@MIN(A4...A5)'}
        self.check(sheet(cells, ('/W1', '/GOR', '/GRA', '/GC12', '/X>A1:>B7:')), '\x15\x15\x0a')

    @unittest.skipUnless(ROM.exists(), 'no Apple II ROM image (A2FC_ROM)')
    def test_rom_functions(self):
        """The ROM's own digits come back: what the screen shows at these
        widths is what the reference's floats give, nine digits."""
        cells = {'A1': '@SQRT(16)', 'A2': '9^.5', 'A3': '2^10', 'A4': '@LN(1)', 'A5': '/FI@SQRT(1E4)',
                 'A6': '@SQRT(-1)', 'A7': '@LN(0)', 'A8': '1E61^2', 'A9': '/F$@SIN(@PI/6)',
                 'A10': '/F$@ATAN(1)*4', 'A11': '@ISERROR(@SQRT(-1))', 'A12': '/F$@ACOS(1)'}
        self.check(sheet(cells, ('/W1', '/GOC', '/GRA', '/GC9', '/X>A1:>A1:')))

    def test_out_of_order_and_repeated(self):
        cells = {'A1': '1', 'A2': '+A1*2', 'B1': '"L', 'B2': '5', 'C3': '@SUM(A1...B2)'}
        data = sheet(cells, order=['A1', 'A2', 'B1', 'B2', 'C3'])
        self.check(data)
        # a value, then a label over it; a cell typed twice: the last wins
        text = '>A1:5\r>B1:3\r>A1:"OVER\r>B1:4\r>C1:+A1+B1\r/GOC\r/X>A1:>C1:\r'
        self.check(text.encode())
        text = '>C1:+A1+B1\r>B1:4\r/W1\r>A1:9\r/GOR\r/X>A1:>A1:\r'
        self.check(text.encode())

    def test_hostile_files_never_hang(self):
        cases = [
            b'>A1:' + b'"' + b'X' * 400 + b'\r>B1:' + b'1+' * 200 + b'1\r/X>A1:>A1:\r',
            b'>A1:' + b'(' * 120 + b'1' + b')' * 120 + b'\r>A2:' + b'-' * 200 + b'5\r'
            b'>A3:' + b'(' * 22 + b'1' + b')' * 22 + b'\r>A4:' + b'(' * 23 + b'1' + b')' * 23 + b'\r'
            b'>A5:' + b'1+' * 16 + b'1\r>A6:' + b'1+(' * 16 + b'1' + b')' * 16 + b'\r'
            b'>A7:' + b'@SUM(' * 7 + b'1' + b')' * 7 + b'\r>A8:' + b'@SUM(' * 8 + b'1' + b')' * 8 + b'\r'
            b'>A9:@IF(1,2,@IF(1,2,@IF(1,2,@IF(1,2,3))))\r/X>A1:>A1:\r',
            b'>A1:' + b'@SUM(' * 40 + b'1' + b')' * 40 + b'\r>A2:@SUM(A1...A254)\r',
            b'>A1:+ZZ999\r>A2:+BL1\r>A3:+A0\r>A4:+A255\r>A5:@SUM(A1...B2)\r>A6:@FOO(1)\r',
            b'>A1:+A2\r>A2:+A1\r>A3:+A3+1\r',
            b'>A1:5\r',
            bytes(range(256)) * 3,
            b'>A1:5\r\x00\x01\x02garbage',
            b'>A1:5\rnot a setting\r',
            b'>A9Z:5\r',
            b'>' + b'\r' * 5,
            b'',
            hi('>A1:1E99\r>A2:1E-99\r>A3:99999999999999999999999\r>A4:.' + '0' * 120 + '1\r'),
            b'>B2:1\r>B2:2\r>B2:"X\r>B2:3\r' * 20,
        ]
        for data in cases:
            with self.subTest(data=data[:40]):
                self.check(data, ' \x15>')

    def test_narrow_columns(self):
        """VisiCalc 2's one- and two-character columns (/GCC1, /GCC2). In a
        one-character column a negative number made the exponent form's
        room, n - sign - len("E.."), wrap (0 - 1 = 255): the overlay wrote
        a stray digit or minus where VisiCalc leaves the cell blank, its
        text copied from 255 - outn bytes after vc_out round to vc_out[0]."""
        cells = {'A2': '-7', 'A3': '-1.5', 'A4': '-.0215', 'A5': '-4E20', 'A6': '0', 'A7': '5',
                 'A8': '@NA', 'A9': '/F$-3', 'A10': '/FI-2', 'A11': '/FL-9', 'A12': '/F*3',
                 'B2': '-7', 'B3': '-1.5', 'B4': '-.0215', 'B5': '-4E20', 'B6': '0', 'B7': '5',
                 'B8': '@ERROR', 'B9': '/F$-3', 'B10': '/FI-2', 'B11': '/FL-9', 'B12': '/F*3',
                 'A1': '/GCC1', 'B1': '/GCC2', 'C1': '/GCC3'}
        shots = self.check(sheet(cells, ('/W1', '/GOC', '/GRA', '/GC9', '/X>A1:>C1:')), '\x0a\x0a')
        for r in range(3, 7):
            self.assertEqual(shots[0][0][r][3], ' ', r)      # A2..A5: nothing fits

    def test_commands_at_a_cell_keep_its_contents(self):
        """VisiCalc 2 (80 columns) saves each column's width as a command
        typed at the column's row-1 cell, after the cells: `>A1:/GCC12`.
        The cell keeps what it holds -- the row of titles of the real
        worksheets (VCDSK03, 07, 08). Measured before the fix: A1's label
        and B1's number were drawn over with blanks, the cursor's line
        showed `/GCC12`, and out of order the command line made B1 ERROR."""
        text = '>C2:+B1*2\r>B2:"X\r>B1:7\r>A1:" ITEM\r>A1:/GCC12\r>B1:/GCC5\r/W1\r/GOC\r/GC9\r/X>A1:>A1:\r'
        shots = self.check(text.encode(), '\x15\x08')
        rows = shots[0][0]
        self.assertTrue(rows[0].startswith('A1 (L)  ITEM'), rows[0])
        self.assertEqual(rows[2][3:20], ' ITEM' + ' ' * 7 + '    7')
        self.assertEqual(rows[3][20:29], '       14')
        self.assertTrue(shots[1][0][0].startswith('B1 (V) 7'), shots[1][0][0])
        # out of VisiCalc's order: the last line of B1 is the command
        text = '>A1:" ITEM\r>B1:7\r>C2:+B1*2\r>B1:/GCC5\r/W1\r/GOR\r/GC9\r/X>A1:>B1:\r'
        rows = self.check(text.encode())[0][0]
        self.assertEqual(rows[2][12:17], '    7')
        self.assertEqual(rows[3][17:26], '       14')

    def test_calls_in_npv_and_lookup(self):
        """The first argument of @NPV and @LOOKUP may call a function: the
        call used to leave its own number in fid, and @NPV(@ABS(.1),...)
        was computed as a LOOKUP (0), @LOOKUP(@NPV(...),...) as an NPV."""
        cells = {'A1': '1', 'A2': '2', 'A3': '3', 'B1': '10', 'B2': '20', 'B3': '30',
                 'C1': '@NPV(@ABS(.1),A1...A3)', 'C2': '@LOOKUP(@NPV(0,A1...A2),A1...A3)',
                 'C3': '@NPV(@SUM(.05,.05),A1...A3)', 'C4': '@LOOKUP(@INT(2.5),A1...A3)'}
        rows = self.check(sheet(cells, ('/W1', '/GOC', '/GRA', '/GC12', '/X>A1:>A1:')))[0][0]
        self.assertEqual([rows[r][27:39] for r in range(2, 6)],
                         [' 4.815927874', '          30', ' 4.815927874', '          20'])

    @unittest.skipUnless(ROM.exists(), 'calls the Applesoft ROM (^, @ functions): no ROM image (A2FC_ROM)')
    def test_what_visicalc_showed_at_the_edges(self):
        """Probe X1 (tools/visicalc_probes.json.gz), as VisiCalc 1.93 showed
        it: a literal out of range is an ERROR value (@ISERROR(1E99) is
        TRUE, @IF(@TRUE,1,1E99) is 1), a blank cell given to @OR is no
        truth value (ERROR), @CHOOSE of nothing is ERROR, 0^0 is ERROR
        (the ROM says 1). The overlay showed FALSE for @OR(C3), NA for
        @CHOOSE(H5...H1), 1 for 0^0, and 0 for the NPV."""
        probes = json.loads(gzip.decompress((ROOT / 'tools/visicalc_probes.json.gz').read_bytes()))
        p = probes['X1']
        rows = self.check(hi(p['sheet'].replace('\n', '\r')))[0][0]
        for k, v in p['cells'].items():
            c, r = map(int, k.split(','))
            if c:
                continue
            self.assertEqual(rows[r + 1][3:3 + len(v)], v, r)
        cells = {'A1': '0^-1', 'A2': '0^2', 'A3': '+1E99', 'A4': '@ISNA(1E-99)'}
        self.check(sheet(cells, ('/W1', '/GOC', '/GRA', '/GC12', '/X>A1:>A1:')))

    def test_width_digits(self):
        """/GC2604: the number passes 255, the setting is ignored (it was
        read as 4, the digits after the overflow)."""
        for g, a1 in (('/GC2604', '   123456'), ('/GC300', '   123456'), ('/GC0004', ' 1E5')):
            rows = self.check(('>A1:123456\r%s\r/X>A1:>A1:\r' % g).encode())[0][0]
            self.assertEqual(rows[2][3:3 + len(a1)], a1, g)
        self.check(b'>A1:123456\r>B1:/GCC2604\r>C1:/GCC0005\r/GC9\r/X>A1:>A1:\r')

    def test_big_sheet_in_a_small_window(self):
        """A table that does not fit, no auxiliary bank (the harness says
        no): refused with the counts, nothing drawn."""
        exe = build(self.tmp.name, SCREENS, 'small', top='$1000')
        shots, note = self.machine(demo(), exe=exe)
        self.assertEqual(shots, [])
        # the main bank's room: none here (it said 512, from column A's count)
        self.assertEqual(note, 'Sheet too big: 21 values, room for 0.')

    def test_a_column_of_256_values_says_so(self):
        """Column A's 254 cells, nine of them typed again: 263 value lines
        in one column, more than a column's count holds. Before: refused
        as `Sheet too big: 263 values, room for 2193.` (here; 241 on the
        machine, where 4,064 fit with the auxiliary bank) -- a room larger
        than the count it refuses."""
        data = b''.join(b'>A%d:%d\r' % (r, r) for r in range(254, 0, -1)) + \
            b''.join(b'>A%d:1\r' % r for r in range(1, 10)) + b'/X>A1:>A1:\r'
        shots, note = self.machine(data)
        self.assertEqual(shots, [])
        self.assertEqual(note, 'Sheet too big: over 255 values in one column.')
        # 255 in a column are a sheet like another (the reference's too).
        data = b''.join(b'>A%d:%d\r' % (r, r) for r in range(254, 0, -1)) + b'>A7:1\r/X>A1:>A1:\r'
        self.check(data)

    def test_private_worksheets(self):
        samples = PRIVATE / 'samples'
        if not samples.is_dir():
            self.skipTest('no private VisiCalc worksheets (A2FC_VISICALC)')
        for path in sorted(samples.glob('*.txt')):
            text = path.read_text()
            if not self.rom and any(m in text for m in MATH):
                continue
            with self.subTest(sheet=path.stem):
                self.check(hi(text.replace('\n', '\r')), ' >\x0a\x15B<')


# -- the reference against VisiCalc ------------------------------------------------------

def known_difference(cell, oracle, ref):
    """docs/VISICALC-FORMAT.md, "What A2 File Cmd does not reproduce"."""
    if cell is not None and any(m in cell.text for m in MATH):
        return True                     # VisiCalc's own series, the overlay's ROM
    if cell is not None and not oracle.strip() and ref.strip() in ('0', '0.'):
        return True                     # VisiCalc's redraw leaves some zeros undrawn
    return False


class Oracle(unittest.TestCase):
    def compare(self, src, oracle):
        sh = R.load(src)
        bad = []
        for k, v in oracle['cells'].items():
            c, r = map(int, k.split(','))
            got = R.cell_text(sh, c, r, len(v))
            if got != v and not known_difference(sh.cells.get((c, r)), v, got):
                bad.append((R.col_name(c) + str(r), v, got))
        return len(oracle['cells']), bad

    def pairs(self, sub, src):
        d = PRIVATE / sub
        if not d.is_dir():
            self.skipTest('no VisiCalc captures (A2FC_VISICALC)')
        for p in sorted(d.glob('*.json')):
            yield p.stem, (PRIVATE / src / (p.stem + '.txt')).read_text(), json.loads(p.read_text())

    def test_real_worksheets_as_visicalc_shows_them(self):
        total = 0
        for name, src, ora in self.pairs('oracle', 'samples'):
            n, bad = self.compare(src, ora)
            total += n
            self.assertEqual(bad, [], name)
        self.assertGreater(total, 20000)

    def test_probe_sheets_as_visicalc_shows_them(self):
        """Sheets written to measure VisiCalc (formats at every width,
        functions, order, ranges), and what it showed: public, in
        tools/visicalc_probes.json.gz."""
        probes = json.loads(gzip.decompress((ROOT / 'tools/visicalc_probes.json.gz').read_bytes()))
        self.assertGreater(len(probes), 50)
        for name, p in sorted(probes.items()):
            n, bad = self.compare(p['sheet'], p)
            # S5 C7: @MIN(B3,B4) left blank by VisiCalc, not reproduced
            bad = [b for b in bad if (name, b[0]) != ('S5', 'C7')]
            self.assertEqual(bad, [], name)


# The phases for real (no VC_FLAT): the swap area at $A000, above the
# program; VISICALC.BIN is the harness's, its phases' identity copied from
# the link (the phases run where they were linked, flat). The Nth fclose
# fails as ProDOS's CLOSE can, keeping the file open; every fopen after it
# is counted: on the machine, it would get the $0C00 buffer, where the
# overlay keeps tables.
CLOSE = SCREENS.replace(
    'static FILE* opn(const char* p, const char* m) { return fopen(p, m); }',
    """extern unsigned char _VCB_LOAD__[], _VCC_LOAD__[];
static unsigned char fail_at, closes, failed, late, bin;
static FILE* binf = (FILE*)0x7001;
static FILE* opn(const char* p, const char* m)
{
    late += failed;
    if (strcmp(p, "/V/A2FILE/VISICALC.BIN")) return fopen(p, m);
    bin = 0;
    return binf;
}""").replace(
    'static size_t rd(void* p, size_t s, size_t n, FILE* f) { return fread(p, s, n, f); }',
    """static size_t rd(void* p, size_t s, size_t n, FILE* f)
{
    if (f != binf) return fread(p, s, n, f);
    memcpy(p, bin ? _VCC_LOAD__ : _VCB_LOAD__, 2);   /* the link's identity */
    return n;
}""").replace(
    'static int cls(FILE* f) { return fclose(f); }',
    """static int cls(FILE* f)
{
    if (++closes == fail_at) { failed = 1; return EOF; }   /* kept open */
    return f == binf ? 0 : fclose(f);
}""").replace(
    '    if (whence != SEEK_SET || !freopen("sheet.txt", "rb", f)) return -1;',
    """    if (f == binf) { bin = off != 0; return 0; }
    if (whence != SEEK_SET || !freopen("sheet.txt", "rb", f)) return -1;""").replace(
    '    keys = argv[1];', '    keys = argv[1];\n    fail_at = atoi(argv[3]);').replace(
    '    fwrite(note, 1, 80, stdout);', '    fwrite(note, 1, 80, stdout);\n    printf("%u %u", late, closes);')
assert CLOSE.count('late') >= 3 and 'fail_at = atoi' in CLOSE and 'bin = off' in CLOSE


@unittest.skipUnless(have_head(), 'cc65 master (CC65_HEAD) not installed')
class PhaseClose(unittest.TestCase):
    def test_a_failed_close_opens_nothing_more(self):
        # Before 0.9.5, phase ignored fclose's answer and opened
        # VISICALC.BIN (then the worksheet again) after a CLOSE ProDOS had
        # refused: that open got the $0C00 buffer and ProDOS read blocks
        # over the overlay's tables there. Each of the four closes the
        # phases make, failing, must end the overlay with its note and no
        # open after it; with no failure, the worksheet shows.
        with tempfile.TemporaryDirectory(prefix='a2fc-visicalc-close-') as tmp:
            exes = build(tmp, CLOSE, 'vcc', flat=False, keep='$8500')
            data = sheet({'A1': '5', 'B1': '+A1*2'})
            (Path(tmp) / 'sheet.txt').write_bytes(data)
            for fail in (1, 2, 3, 4, 5, 0):
                for cpu, exe in exes.items():
                    p = subprocess.run([tool('sim65'), '-x', '400000000', str(exe), '', str(len(data)),
                                        str(fail)], cwd=tmp, capture_output=True, env=env(), timeout=600)
                    self.assertEqual(p.returncode, 0, (cpu, fail, p.stderr[-300:]))
                    self.assertEqual((Path(tmp) / 'sheet.txt').read_bytes(), data)
                    o = p.stdout
                    tail = o[o.rindex(b'\0') + 1:]              # (the note ends with zeros)
                    late, closes = map(int, tail.split())
                    note = o[-80 - len(tail):-len(tail)].split(b'\0')[0].decode('latin-1')
                    with self.subTest(cpu=cpu, fail=fail):
                        if fail:
                            # the fifth is the normal end's, after the sheet
                            # was shown: it said nothing of a refused CLOSE
                            # until the second bug hunt
                            self.assertEqual(note, 'Close error.')
                            self.assertEqual(late, 0, 'an fopen after a failed close')
                            self.assertEqual(closes, fail)
                        else:
                            self.assertEqual(note, '')
                            self.assertEqual(closes, 5)
                            self.assertGreaterEqual(len(o) - 80 - len(tail), 3840, 'a screen')


# Escape while the worksheet is read and recalculated. The harness puts a
# key in the keyboard register ($C000) inside its Nth fread -- the overlay
# has just asked the keyboard, in tick, before that read -- and counts the
# processor's cycles from there to the return. It also counts what the
# overlay must leave as it found it: the files (opened, closed), the
# processor's stack and cc65's, the zero page $50-$FF the ROM bridge puts
# aside, and what `leave` owes when the table was in the auxiliary bank
# (ram_format, once). Arguments: keys, size, the read (0: never), the key,
# aux_consent's answer, ProDOS's MACHID.
ESCAPE = SCREENS.replace(
    '#include "a2fc_plugin.h"',
    '''#include <sim65.h>
#include "a2fc_plugin.h"
static unsigned int reads, esc_at;
static unsigned char esc_key, fmts, asked, consent, opens, closes, closefail;
static unsigned long t0, t1;
static unsigned long now(void)
{
    peripherals.counter.select = COUNTER_SELECT_CLOCKCYCLE_COUNTER;
    peripherals.counter.latch = 0;
    return peripherals.counter.value32[0];
}''').replace(
    'static FILE* opn(const char* p, const char* m) { return fopen(p, m); }',
    'static FILE* opn(const char* p, const char* m) { ++opens; return fopen(p, m); }').replace(
    'static size_t rd(void* p, size_t s, size_t n, FILE* f) { return fread(p, s, n, f); }',
    '''static size_t rd(void* p, size_t s, size_t n, FILE* f)
{
    if (++reads == esc_at) { *(unsigned char*)0xC000 = esc_key; t0 = now(); }
    return fread(p, s, n, f);
}''').replace(
    'static int cls(FILE* f) { return fclose(f); }',
    '''static int cls(FILE* f)
{
    ++closes;                           /* closefail: ProDOS refused (the file is let go here) */
    return fclose(f) || closefail ? EOF : 0;
}''').replace(
    'static unsigned char rfmt(void) { return 1; }',
    'static unsigned char rfmt(void) { ++fmts; return 1; }').replace(
    'static unsigned char nope(void) { return 0; }',
    'static unsigned char nope(void) { ++asked; return consent; }').replace(
    '    static unsigned char copy_buf[512];\n    int in;',
    '''    static unsigned char copy_buf[512];
    static unsigned char zp[0xB0], s0, s1, same;
    static unsigned int c0, c1;
    int in;''').replace(
    '    keys = argv[1];',
    '''    keys = argv[1];
    esc_at = atoi(argv[3]); esc_key = atoi(argv[4]); consent = atoi(argv[5]);
    *(unsigned char*)0xBF98 = atoi(argv[6]);
    closefail = atoi(argv[7]);
    *(unsigned char*)0xC010 = 0;''').replace(
    '    plugin_entry(&api);\n',
    '''    memcpy(zp, (void*)0x50, sizeof zp);
    __asm__("tsx"); __asm__("stx %v", s0);
    __asm__("lda c_sp"); __asm__("sta %v", c0); __asm__("lda c_sp+1"); __asm__("sta %v+1", c0);
    plugin_entry(&api);
    __asm__("tsx"); __asm__("stx %v", s1);
    __asm__("lda c_sp"); __asm__("sta %v", c1); __asm__("lda c_sp+1"); __asm__("sta %v+1", c1);
    t1 = now();
    same = !memcmp(zp, (void*)0x50, sizeof zp);
''').replace(
    '    fwrite(note, 1, 80, stdout);',
    '''    fwrite(note, 1, 80, stdout);
    printf("%u %lu %u %u %u %u %u %u %u %u %u", reads, t0 ? t1 - t0 : 0, *(unsigned char*)0xC000,
           *(unsigned char*)0xC010, fmts, asked, opens, closes, same, s0 == s1, c0 == c1);''')
assert ESCAPE.count('esc_at') == 3 and ESCAPE.count('++fmts') == 1 and ESCAPE.count('++asked') == 1
assert ESCAPE.count('++opens') == 1 and ESCAPE.count('++closes') == 1 and 'c0 == c1' in ESCAPE
assert ESCAPE.count('closefail') == 4
assert ESCAPE.count('t1 = now()') == 1 and ESCAPE.count('0xBF98') == 1

ESC = 0x9B                                  # Escape, waiting
FIELDS = ('reads', 'cycles', 'kbd', 'strobe', 'fmts', 'asked', 'opens', 'closes', 'zp', 's', 'csp')


def slow_sheet(order='/GOC', n=120, k=13):
    '''The reviewer's vc_slow: n numbers, and n formulas of k @NPV over them
    (13 fill a line): 5,788,076,613 cycles to recalculate on the 6502
    (5,862,959,837 on the 65C02), an hour and a half at 1 MHz.'''
    cells = {'A%d' % r: str(r) for r in range(1, n + 1)}
    cells.update({'B%d' % r: '+'.join(['@NPV(.1,A1...A%d)' % n] * k) for r in range(1, n + 1)})
    return sheet(cells, ('/W1', order, '/GRA', '/GC9', '/X>A1:>A1:'), high=False)


@unittest.skipUnless(have_head(), 'cc65 master (CC65_HEAD) not installed')
class Escape(unittest.TestCase):
    '''Escape stops the reading and the recalculation.

    Before: the recalculation read no key at all -- tick only turned the
    activity cell -- and its length was the file's to decide. The
    reviewer's 31 KB sheet (slow_sheet) held the machine for 5.8 thousand
    million cycles, an hour and a half at 1 MHz, Escape or not: with
    Escape waiting from the first formula on, sim65 gave up at its limit
    of 400 million cycles, on both processors.

    Now Escape is asked for at every read of the file, every column or
    row, every operand of a formula and every cell of a range, and leaves
    through `leave`. Measured here, from the key (put in the register at
    a read of the file, the only place the harness has a hand) to the
    return to the core: 3,200 to 36,400 cycles, held under BOUND -- the
    rest of that read, the next look at the keyboard, the close and the
    note. Between two looks there is at most one operation or one
    function of the ROM: 17,600 cycles for a division, about 75,000 for a
    ROM function with its conversions (whole formulas timed), a tenth of
    a second at 1 MHz. Only Escape is taken; any other key stays in the
    keyboard register for the sheet's first cgetc, as before.'''
    BOUND = 60000                           # 0.06 s at 1 MHz

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-visicalc-esc-')
        cls.dir = Path(cls.tmp.name)
        cls.exe = build(cls.tmp.name, ESCAPE, 'esc')
        # The table in the "auxiliary bank": no room in the main one, and
        # 512 values at $A000-$AFFF, above the harness (sim65 has one bank:
        # the soft switches are memory, the accesses are the same).
        cls.aux = build(cls.tmp.name, ESCAPE, 'escaux', top='$1000',
                        defs=('VC_AUXLOW=$A000', 'VC_AUXTOP=$B000'))
        if ROM.exists():
            (cls.dir / 'rom.bin').write_bytes(ROM.read_bytes()[-0x3000:][:0x2800])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_esc(self, data, at, key=ESC, consent=0, machid=0, exe=None, keys='', limit=400000000,
                closefail=0):
        '''(screens shown, note, the harness's counts), the same on both
        processors but for the cycles (the largest is kept).'''
        (self.dir / 'sheet.txt').write_bytes(data)
        got = {}
        for cpu, path in (exe or self.exe).items():
            p = subprocess.run([tool('sim65'), '-x', str(limit), str(path), keys, str(len(data)),
                                str(at), str(key), str(consent), str(machid), str(closefail)],
                               cwd=self.dir, capture_output=True, env=env(), timeout=1200)
            self.assertEqual(p.returncode, 0, (cpu, p.returncode, p.stderr[-300:]))
            self.assertEqual((self.dir / 'sheet.txt').read_bytes(), data, 'the file is only read')
            o = p.stdout
            tail = o[o.rindex(b'\0') + 1:]
            f = dict(zip(FIELDS, map(int, tail.split())))
            note = o[-80 - len(tail):-len(tail)].split(b'\0')[0].decode('latin-1')
            got[cpu] = ((len(o) - 80 - len(tail)) // 3840, note, f)
            # Whatever happened, the core gets its machine back.
            self.assertEqual(f['opens'], f['closes'], (cpu, 'a file left open'))
            self.assertEqual((f['zp'], f['s'], f['csp']), (1, 1, 1),
                             (cpu, 'the zero page $50-$FF, S, the C stack'))
        a, b = got['sim6502'], got['sim65c02']
        cyc = max(a[2].pop('cycles'), b[2].pop('cycles'))
        self.assertEqual(a, b)
        return a[0], a[1], dict(a[2], cycles=cyc)

    def passes(self, data):
        '''The reads of the two passes over the file, and one more: the
        first formula's own line.'''
        return 2 * (len(data) // 255 + 2) + 1

    def stopped(self, got, bound, aux=False):
        shots, note, f = got
        self.assertEqual(note, 'Stopped. /RAM rebuilt.' if aux else 'Stopped.')
        self.assertEqual(shots, 0, 'no sheet shown')
        self.assertEqual((f['kbd'], f['strobe']), (ESC, ESC), 'the strobe cleared by a store')
        self.assertEqual(f['fmts'], 1 if aux else 0, 'ram_format')
        self.assertLessEqual(f['cycles'], bound)
        self.assertGreater(f['cycles'], 0)
        if os.environ.get('A2FC_SHOW'):
            print('  %s: %d cycles from the key to the return (bound %d)' % (self.id().split('.')[-1], f['cycles'], bound))

    def test_escape_in_the_recalculation(self):
        for order in ('/GOC', '/GOR'):
            # in the first formula of the slow sheet and in its third (each
            # takes 45 million cycles); deep in a lighter one
            for data, more in ((slow_sheet(order), (0, 2)), (slow_sheet(order, k=1), (30, 100))):
                first = self.passes(data)
                for at in (first + m for m in more):
                    with self.subTest(order=order, at=at):
                        got = self.run_esc(data, at)
                        self.stopped(got, self.BOUND)
                        self.assertEqual(got[2]['reads'], at, 'stopped before another read')

    def test_a_close_refused_is_said(self):
        '''CLOSE's answer was taken for granted at every exit but the
        phase changes: Escape said "Stopped." and the sheet's end nothing,
        a sheet too big or no worksheet its own note, over a file ProDOS
        had kept open on $0800. Each says "Close error." now; everything
        else is left as it was found (run_esc checks).'''
        data = slow_sheet('/GOC', k=1)
        got = self.run_esc(data, self.passes(data) + 30, closefail=1)
        self.assertEqual(got[1], 'Close error.')
        self.assertEqual(got[0], 0, 'no sheet shown')
        self.assertEqual((got[2]['kbd'], got[2]['strobe']), (ESC, ESC), 'Escape was taken')
        # the normal end: the sheet shown, Escape typed, the close refused
        got = self.run_esc(sheet({'A1': '5'}), 0, closefail=1)
        self.assertEqual((got[0], got[1]), (1, 'Close error.'))
        # a file that is no worksheet, and one cut short
        got = self.run_esc(b'hello\r', 0, closefail=1)
        self.assertEqual((got[0], got[1]), (0, 'Close error.'))
        got = self.run_esc(b'hello\r', 0)
        self.assertEqual((got[0], got[1]), (0, 'Not a VisiCalc worksheet (T shows it as text).'))
        # too big for the main bank, no auxiliary one (machid 0)
        big = sheet({'A%d' % r: str(r) for r in range(1, 250)})
        got = self.run_esc(big, 0, exe=self.aux, closefail=1)
        self.assertEqual((got[0], got[1]), (0, 'Close error.'))
        got = self.run_esc(big, 0, exe=self.aux)
        self.assertTrue(got[1].startswith('Sheet too big: 249 values'), got[1])

    def test_escape_while_the_file_is_read(self):
        data = slow_sheet()
        for at in (1, 2, len(data) // 255, len(data) // 255 + 5, self.passes(data) - 3):
            with self.subTest(at=at):
                self.stopped(self.run_esc(data, at), self.BOUND)

    def test_escape_with_the_table_in_the_auxiliary_bank(self):
        '''`leave` rebuilds /RAM and says so, once; before the table is
        there -- in the first pass, or when the bank was refused -- there is
        nothing to rebuild.'''
        data = slow_sheet()
        first = self.passes(data)
        for at in (first, first + 2):
            got = self.run_esc(data, at, consent=1, machid=0xB3, exe=self.aux)
            self.stopped(got, self.BOUND, aux=True)
            self.assertEqual(got[2]['asked'], 1)
        got = self.run_esc(data, 3, consent=1, machid=0xB3, exe=self.aux)
        self.stopped(got, self.BOUND)
        self.assertEqual(got[2]['asked'], 0, 'stopped before the question')
        # The whole of it there, undisturbed: the sheet, and /RAM rebuilt.
        quick = sheet({'A1': '5', 'B1': '+A1*2', 'C1': '@SUM(A1...B1)'}, high=False)
        shots, note, f = self.run_esc(quick, 0, consent=1, machid=0xB3, exe=self.aux)
        self.assertEqual((shots, note, f['fmts'], f['asked']), (1, ' /RAM rebuilt.', 1, 1))

    def test_escape_in_a_formula_without_a_range(self):
        '''A line of 255 characters with no range in it: 124 divisions.
        Asked only at the reads of the file, the keyboard waited for the
        whole formula -- 2,188,848 cycles measured with the key put in at
        the read that completes A2's line (it takes two). Asked at every
        operand: 3,174.'''
        cells = {'A1': '7', 'A2': '+A1' + '/3' * 124, 'A3': '+A1' + '/3' * 124, 'A4': '+A2'}
        data = sheet(cells, high=False)
        self.stopped(self.run_esc(data, self.passes(data) + 1), self.BOUND)

    def test_escape_out_of_order(self):
        '''One cell line after the settings: the whole file is read again
        for every formula, and asked at every read.'''
        cells = {'%s%d' % (c, r): '+A1+1' for c in 'BCD' for r in range(1, 81)}
        cells['A1'] = '5'
        data = sheet(cells, high=False) + b'>A2:7\r'
        first = self.passes(data)
        for at in (first, first + 7, first + 500):
            with self.subTest(at=at):
                self.stopped(self.run_esc(data, at), self.BOUND)

    @unittest.skipUnless(ROM.exists(), 'calls the Applesoft ROM (^, @ functions): no ROM image (A2FC_ROM)')
    def test_escape_after_the_rom_was_called(self):
        '''The ROM bridge closed again: the zero page $50-$FF as the core
        had it (run_esc compares the 176 bytes), after formulas that went
        through it -- one of them refused by the ROM, through ONERR.'''
        cells = {'A%d' % r: f for r, f in enumerate(
            ['@SQRT(2)', '2^.5', '@LN(-1)', '@SIN(1)+@EXP(1000)', '@SQRT(A1)^3'] * 8, 1)}
        cells['B1'] = '@NPV(.1,A1...A40)'
        data = sheet(cells, high=False)
        first = self.passes(data)
        for at in (first + 3, first + 20, first + 40):
            with self.subTest(at=at):
                self.stopped(self.run_esc(data, at), self.BOUND)

    def test_only_escape_is_taken(self):
        '''A key typed while the sheet is computed is not read here: it
        stays in the keyboard register, strobe and all, for the sheet's
        first cgetc -- as it did before Escape was looked for. An Escape
        already taken (bit 7 clear) is no key.'''
        data = slow_sheet(n=12, k=2)
        first = self.passes(data)
        whole = self.run_esc(data, 0)
        self.assertEqual((whole[0], whole[1]), (1, ''))
        for key in (0xA0, 0x8D, 0xD1, 0x1B, 0x83, 0x9A, 0x9C):
            for at in (2, first, first + 5):
                with self.subTest(key=key, at=at):
                    shots, note, f = self.run_esc(data, at, key=key)
                    self.assertEqual((shots, note), (1, ''), 'the sheet shows')
                    self.assertEqual((f['kbd'], f['strobe']), (key, 0), 'the key and its strobe untouched')
                    self.assertEqual(f['reads'], whole[2]['reads'])

    def test_nothing_between_the_rom_bridge_and_the_keyboard(self):
        '''What leaving from tick may assume, read in the source: the ROM
        bridge (the language card off, the zero page aside, interrupts
        off), the bank switches of the table and the decimal arithmetic
        call nothing that asks the keyboard or reads the file.'''
        src = (ROOT / 'src/plugins/visicalc.s').read_text()
        asks = re.compile(r'\b(jsr|jmp|j[a-z]{2})\s+(tick|poll|ppeek|rdline|rnext|nextcell|seekto|leave|evaluate|expr|operand)\b')
        rom = src[src.index('\nromrun: '):src.index('; == the overlay')]
        self.assertGreater(rom.count('jsr'), 30)
        self.assertEqual(asks.findall(rom), [])
        bank = src[src.index('\ntblock:'):src.index('TBLOCK  = * - tblock')]
        self.assertEqual(bank.count('php'), 6)
        self.assertEqual(re.findall(r'\b(jsr|jmp)\b', bank), [])
        # sed ... cld, php/sei ... plp: no call out in between
        for m in re.finditer(r'\n\s+sed\b', src):
            end = src.index('plp', m.start())
            self.assertEqual(asks.findall(src[m.start():end]), [], src[m.start():m.start() + 60])
        # and the places that ask: the file's reads, the columns and rows
        # of the recalculation; every operand, every cell of a range
        self.assertEqual(len(re.findall(r'\bjsr\s+tick\b', src)), 3)
        self.assertEqual(len(re.findall(r'\bjsr\s+poll\b', src)), 2)
        self.assertEqual(len(re.findall(r'\bjsr\s+ppeek\b', src)), 1)

    def test_too_big_for_the_auxiliary_bank(self):
        '''The room named is the bank's the table could have gone to.
        Before: always the main bank's (241 on the machine), also for a
        sheet the auxiliary bank's 4,064 would not hold.'''
        cells = {'%s%d' % (c, r): '1' for c in 'ABC' for r in range(1, 201)}
        data = sheet(cells, high=False)
        for consent, machid, note in ((1, 0xB3, 'Sheet too big: 600 values, room for 512.'),
                                      (0, 0xB3, 'Sheet too big: 600 values, room for 512.'),
                                      (1, 0x83, 'Sheet too big: 600 values, room for 0.')):
            with self.subTest(consent=consent, machid=machid):
                shots, got, f = self.run_esc(data, 0, consent=consent, machid=machid, exe=self.aux)
                self.assertEqual((shots, got, f['fmts'], f['asked']), (0, note, 0, 0))
        # It fits there and the user says no: the main bank is what is left.
        data = sheet({k: v for k, v in cells.items() if k[0] != 'C'}, high=False)
        shots, got, f = self.run_esc(data, 0, consent=0, machid=0xB3, exe=self.aux)
        self.assertEqual((shots, got, f['fmts'], f['asked']),
                         (0, 'Sheet too big: 400 values, room for 0.', 0, 1))
        shots, got, f = self.run_esc(data, 0, consent=1, machid=0xB3, exe=self.aux)
        self.assertEqual((shots, got, f['fmts'], f['asked']), (1, ' /RAM rebuilt.', 1, 1))


class Phases(unittest.TestCase):
    def test_the_phases_come_from_one_link(self):
        for build in ('build', 'build-6502'):
            plg, binf = ROOT / build / 'visicalc.PLG', ROOT / build / 'visicalc.PLG.BIN'
            if not plg.exists() or not binf.exists():
                continue
            cfg = (ROOT / 'sdk/visicalc.cfg').read_text()
            swap = int(re.search(r'VC_SWAP:.*value = \$([0-9A-F]+)', cfg)[1], 16)
            keep = int(re.search(r'VC_KEEP:.*value = \$([0-9A-F]+)', cfg)[1], 16)
            b = binf.read_bytes()
            self.assertEqual(len(b), 2 * swap, build)
            self.assertEqual(b[0:2], b[swap:swap + 2], build)
            self.assertLessEqual(len(plg.read_bytes()), 0x2500, build)
            self.assertLessEqual(keep + swap, 0x2500, build)


if __name__ == '__main__':
    unittest.main()
