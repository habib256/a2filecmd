"""DOCVIEW as it runs: the cc65 build of docview.c and docview.s, calculations
on the real Applesoft ROM, under sim65, both processors.

tools/test_docview.py pages the layout on the host, where nothing is
computed; here the same C, compiled by cc65, and the assembly evaluator lay
out Epistole documents whose #:?expr] fields become numbers. The service
table is a mock: a 24 x 80 screen with its inverse cells, the file read
through sim65's stdio (it has no lseek: a seek reopens and reads forward),
keys from a script; at each key, the screen is written out. The ROM is an
Apple II image at $D000 (A2FC_ROM; POM2's apple2p.rom by default); the
program is linked at $4000, above DOCVIEW's scratch ($3C50-$3FFF).
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('A2FC_ROM', str(Path.home() / 'src/pom2/roms/apple2p.rom')))
EPI = Path(os.environ.get('A2FC_EPISTOLE', Path.home() / '.cache/a2fc/epistole'))


def epistole_files():
    """The text files of the Epistole disks, if they are here (test_docview.py reads them)."""
    from test_docview import Docview
    out = {}
    for path in sorted(EPI.glob('*.dsk')):
        for name, data in Docview.real_files(None, path):
            out[name] = data
    return out

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <fcntl.h>
#include <unistd.h>
#include "src/a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
static char screen[24][80], inv[24][80];
static unsigned char cx, cy, rv;
static const char* keys;
static FILE* opn(const char* p, const char* m) { return fopen(p, m); }
static size_t rd(void* p, size_t s, size_t n, FILE* f) { return fread(p, s, n, f); }
static int cls(FILE* f) { return fclose(f); }
static int sk(FILE* f, long off, int whence)
{
    static unsigned char skip[64];
    (void)whence;
    if (!freopen("doc.txt", "rb", f)) return -1;
    while (off > 0) {
        size_t n = off > 64 ? 64 : (size_t)off;
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
static int pf(const char* f, ...)
{
    static char b[200];
    va_list ap;
    va_start(ap, f);
    vsprintf(b, f, ap);
    va_end(ap);
    ps(b);
    return 0;
}
static void xy(unsigned char x, unsigned char y) { cx = x; cy = y; }
static unsigned char rev(unsigned char r) { unsigned char o = rv; rv = r; return o; }
static void clr(void) { memset(screen, ' ', sizeof screen); memset(inv, ' ', sizeof inv); cx = cy = 0; }
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
    static struct Panel pan[2];
    static unsigned char active;
    static char note[80], full[] = "doc.txt";
    static unsigned char copy_buf[512];
    int in;
    (void)argc;
    in = open("rom.bin", O_RDONLY);
    if (read(in, (void*)0xD000, 0x3000) != 0x3000) return 9;
    close(in);
    keys = argv[1];
    e.type = 4; e.size = atol(argv[2]);
    strcpy(e.name, "DOC");
    strcpy(pan[0].path, "/TEST");
    api.copy_buf = copy_buf;
    api.panels = pan; api.active = &active; api.full = full; api.selected = &e; api.note = note;
    api.fopen = opn; api.fread = rd; api.fclose = cls; api.fseek = sk;
    api.cprintf = pf; api.cputs = ps; api.cputc = pc; api.gotoxy = xy; api.revers = rev;
    api.clrscr = clr; api.cgetc = key;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy; api.strcmp = strcmp; api.strlen = strlen;
    clr();
    plugin_entry(&api);
    fwrite(note, 1, 80, stdout);
    return 0;
}
'''


class DocviewSim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ROM.exists():
            raise unittest.SkipTest('no Apple II ROM image (A2FC_ROM)')
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-docview-')
        d = cls.dir = Path(cls.tmp.name)
        (d / 'rom.bin').write_bytes(ROM.read_bytes()[-0x3000:])
        (d / 'harness.c').write_text(HARNESS)
        # Copies under other names: cl65 writes a .s beside a .c.
        (d / 'p').mkdir()
        shutil.copyfile(ROOT / 'src/plugins/docview.c', d / 'p/dv_c.c')
        shutil.copyfile(ROOT / 'src/a2fc_plugin.h', d / 'a2fc_plugin.h')   # its ../a2fc_plugin.h
        shutil.copyfile(ROOT / 'src/plugins/docview.s', d / 'docview.s')
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        cls.exe = {}
        for cpu in ('sim6502', 'sim65c02'):
            cfg = (target.parent / f'cfg/{cpu}.cfg').read_text()
            cfg = cfg.replace('start = $0200, size = $FDF0 - __STACKSIZE__',
                              'start = $4000, size = $C000 - $4000 - __STACKSIZE__')
            assert '$C000 - $4000' in cfg
            cfg = cfg.replace('    RODATA:', '    OVLHDR:   load = MAIN, type = ro;\n    RODATA:', 1)
            (d / f'{cpu}.cfg').write_text(cfg)
            exe = d / f'dv-{cpu}'
            subprocess.run(['cl65', '-t', cpu, '-I', str(ROOT), '-I', str(ROOT / 'src'),
                            '-C', str(d / f'{cpu}.cfg'), '-O', '-Cl', '-o', str(exe),
                            str(d / 'harness.c'), str(d / 'p/dv_c.c'), str(d / 'docview.s')],
                           check=True, cwd=d)
            cls.exe[cpu] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def pages(self, doc, keys=' ' * 8):
        """The screens shown, the same on both processors: (rows, inverse) each."""
        (self.dir / 'doc.txt').write_bytes(doc)
        got = {}
        for cpu, exe in self.exe.items():
            p = subprocess.run(['sim65', str(exe), keys, str(len(doc))], cwd=self.dir,
                               capture_output=True, timeout=600)
            self.assertEqual(p.returncode, 0, (cpu, p.stderr))
            self.assertEqual((self.dir / 'doc.txt').read_bytes(), doc, 'the file is only read')
            o = p.stdout
            shots = []
            for k in range(len(o) // (24 * 160)):
                shot = o[k * 24 * 160:(k + 1) * 24 * 160]
                rows = [shot[r * 160:r * 160 + 80].decode('latin-1') for r in range(24)]
                inv = [shot[r * 160 + 80:r * 160 + 160].decode('latin-1') for r in range(24)]
                shots.append((rows, inv))
            got[cpu] = shots
        self.assertEqual(got['sim6502'], got['sim65c02'])
        return got['sim6502']

    def text(self, doc, **kw):
        """The rows of each page shown, a page once (a key at the end redraws it)."""
        shots, seen = self.pages(doc, **kw), []
        for rows, _ in shots:
            if not seen or rows != seen[-1]:
                seen.append(rows)
        return [r.rstrip() for rows in seen for r in rows[1:22]]

    def test_values_decimals_and_totals(self):
        doc = (b'_ND2\r#:PR=10949]#:?PR]#:HT=HT+PR]\r#:PR=1662]#:?PR]#:HT=HT+PR]\r'
               b'TOTAL #:?HT]\rTVA #:TV=HT*0,186]#:?TV]\rTTC #:?HT+TV]\r'
               b'_ND0\r#:?2/3]\r_ND3\r#:?-2/3]\r#:?1E+10]\r')
        rows = [r for r in self.text(doc) if r.strip()]
        # As Epistole prints them (bench oracle): no minus sign with
        # decimals, BASIC's exponent kept.
        self.assertEqual(rows, ['10949,00', '1662,00', 'TOTAL 12611,00', 'TVA 2345,65',
                                'TTC 14956,65', '1', '0,667', '1E+10,000'])

    def test_functions_and_comparisons(self):
        doc = (b'_ND3\r#:?SIN(1)]\r#:?SQR(9)]\r#:?ABS(-14)]\r#:?SGN(-12)]\r#:?INT(7,9)]\r'
               b'_ND2\r#:A=3]#:B=(A>3)]#:?18,6*B+33,33*(1-B)]\r#:?(2+3)*4-2^3]\r#:?1<2]#:?2<=1]\r')
        rows = [r for r in self.text(doc) if r.strip()]
        self.assertEqual(rows, ['0,841', '3,000', '14,000', '1,000', '7,000', '33,33', '12,00',
                                '1,000,00'])

    def test_what_cannot_be_computed_is_shown_as_written(self):
        # A division by zero, an overflow, LOG of a negative number: the ROM
        # would leave for BASIC; the field stays as written, in inverse.
        doc = (b'A #:?1/0] B #:?EXP(99)] C #:?LOG(-1)] D #:?(1+] E #:?FOO(2)]\r'
               b'#*M1=]#:?M1+1] #:?Q+1]\r')
        shots = self.pages(doc)
        rows, inv = shots[0]
        line = rows[1].rstrip()
        self.assertEqual(line, 'A 1/0 B EXP(99) C LOG(-1) D (1+ E FOO(2)')
        self.assertEqual(inv[1][2:5], '###')
        self.assertEqual(rows[2].rstrip(), 'M1+1 1,00', '#*M1=] prints nothing, M1 is unknown, Q is 0')

    def test_page_starts_carry_the_values(self):
        # 60 lines, each adding 1: every page starts from the values before
        # it, forward and back (Up), not from 0 nor from the page before.
        doc = b'_ND0' + b''.join(b'#:N=N+1]#:?N]\r' for _ in range(60))
        shots = self.pages(doc, keys='  B  ')
        firsts = [int(rows[1].strip()) for rows, _ in shots]
        self.assertEqual(firsts, [1, 22, 43, 22, 43, 43])


    def test_decimal_tab_and_letters_set_apart(self):
        # _TD: a number's comma at the tab's column, from the margin, on the
        # following lines too; text is not moved. A letter with bit 7 set
        # (underlined in print): inverse.
        doc = (b'_TD20ABC\rx#:?5]\ry#:?1234,5]!\r' + bytes(c | 0x80 for c in b'Hi') + b'bas\r')
        shots = self.pages(doc)
        rows, inv = shots[0]
        self.assertEqual([r.rstrip() for r in rows[1:5]],
                         ['ABC', 'x' + ' ' * 17 + '5,00', 'y' + ' ' * 14 + '1234,50!', 'Hibas'])   # commas at 19
        self.assertEqual(inv[4][:5], '##   ')

    def test_epistole_demos_as_epistole_prints_them(self):
        # The lines Epistole 5.06 itself printed (its print driver captured
        # under POM2), less its 10-column print margin when the document
        # sets none: numbers, decimals, commas and decimal tabs.
        files = epistole_files()
        if 'DEMO.TARIFS' not in files:
            self.skipTest('no Epistole disk here (A2FC_EPISTOLE)')
        rows = self.text(files['DEMO.TARIFS'])
        self.assertIn('!EPISTOLE             !  1650,00!18,60!   1956,90!    0,00!1956,90!', rows)
        total = next(r for r in rows if r.startswith('TOTAL:'))
        self.assertEqual((total.split()[-1], total.index(',')), ('7467,06', 63))
        nums = [r for r in self.text(files['DEMO.CALCULS']) if r.strip()]
        self.assertEqual([r.strip() for r in nums], ['12,000', '0,841', '0,540', '1,557', '0,785', '0,693',
                                                     '7,389', '1,000', '14,000', '3,000', '33,33'])
        self.assertEqual({r.index(',') for r in nums}, {39})
        fac = self.text(files['DEMO.FACTURE'])
        self.assertIn('          1 Ordinateur Apple//c           10949,00', fac)
        for v in ('1662,00', '4900,00', '1650,00', '825,00', '19986,00', '3717,40', '23703,40'):
            row = next(r for r in fac if r.endswith(v))
            self.assertEqual(row.rindex(','), 47, v)     # TVA 18,6% has its own
        shots = self.pages(files['DEMO.FACTURE'])
        title = next(k for k, r in enumerate(shots[0][0]) if 'FACTURE' in r)
        col = shots[0][0][title].index('FACTURE')
        self.assertEqual(shots[0][1][title][col:col + 7], '#' * 7, 'the title, set apart')


if __name__ == '__main__':
    unittest.main()
