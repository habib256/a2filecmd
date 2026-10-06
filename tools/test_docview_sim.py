"""DOCVIEW as it runs: the cc65 build of docview.c and docview.s, calculations
on the real Applesoft ROM, under sim65, both processors.

tools/test_docview.py pages the layout on the host, where nothing is
computed; here the same C, compiled by cc65, and the assembly evaluator lay
out Epistole documents whose #:?expr] fields become numbers. The service
table is a mock: a 24 x 80 screen with its inverse cells, the file read
through sim65's stdio (it has no lseek: a seek reopens and reads forward),
keys from a script; at each key, the screen is written out. The ROM is an
Apple II image at $D000 (A2FC_ROM; POM2's apple2p.rom by default); the
program is linked at $4000, above DOCVIEW's scratch ($3D60-$3FFF).

Every run is also held to three things no screen shows (the trailer after
the note): nothing addressed outside the 24 x 80 screen, no character of
the text outside its rows 1-21 -- conio writes where BASCALC says, and for
a row past 23 that is the peripheral cards' screen holes -- and the
processor's stack: page 1 is filled with a pattern before the call and
read after it, and DOCVIEW with the mock's services may not go deeper than
STACK_MAX bytes under where it was called. A run that does not end within
CYCLES is a hang.
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
# The deepest run measured is 30 bytes (a calculation: the ROM's own calls
# under fp_op); the recursion this guards against took 2 bytes a level and
# 130 levels.
STACK_MAX = 48
CYCLES = 2000000000                         # the longest run here takes under a tenth of that


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
static unsigned char stray;                 /* addressed outside the screen */
static unsigned char offtext;               /* text outside rows 1-21 */
static unsigned char sp0;                   /* S when plugin_entry is called */
#define STK_LOW ((unsigned char*)0x0120)    /* under it, FOUT's text ($0100) */
#define STK_PAT(p) ((unsigned char)(0xA5 ^ (unsigned char)(unsigned)(p)))
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
    else if (stray != 255) ++stray;
    ++cx;
}
/* cputc, the service: DOCVIEW writes its text with it, and only there. */
static void pct(char c)
{
    if ((cy < 1 || cy > 21 || cx >= 80) && offtext != 255) ++offtext;
    pc(c);
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
static void xy(unsigned char x, unsigned char y)
{
    if ((x >= 80 || y >= 24) && stray != 255) ++stray;
    cx = x; cy = y;
}
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
    static unsigned char* p;
    static unsigned char depth;
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
    api.cprintf = pf; api.cputs = ps; api.cputc = pct; api.gotoxy = xy; api.revers = rev;
    api.clrscr = clr; api.cgetc = key;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy; api.strcmp = strcmp; api.strlen = strlen;
    clr();
    /* The stack under this call, patterned up to 16 bytes below S (the
     * loop's own use), then read back: the lowest byte changed is as deep
     * as DOCVIEW, the ROM and these services went. */
    __asm__("tsx");
    __asm__("stx %v", sp0);
    for (p = STK_LOW; p < (unsigned char*)0x0100 + sp0 - 16; ++p) *p = STK_PAT(p);
    plugin_entry(&api);
    for (p = STK_LOW; p < (unsigned char*)0x0100 + sp0 - 16 && *p == STK_PAT(p); ++p) ;
    depth = (unsigned char*)0x0100 + sp0 - p;
    fwrite(note, 1, 80, stdout);
    fwrite(&stray, 1, 1, stdout);
    fwrite(&offtext, 1, 1, stdout);
    fwrite(&depth, 1, 1, stdout);
    return 0;
}
'''
TRAILER = 83                                # the note, stray, offtext, depth


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
        self.depth = 0
        for cpu, exe in self.exe.items():
            p = subprocess.run(['sim65', '-x', str(CYCLES), str(exe), keys, str(len(doc))],
                               cwd=self.dir, capture_output=True, timeout=600)
            self.assertEqual(p.returncode, 0, (cpu, p.stderr))
            self.assertEqual((self.dir / 'doc.txt').read_bytes(), doc, 'the file is only read')
            o = p.stdout
            self.assertEqual(len(o) % (24 * 160), TRAILER, cpu)
            stray, offtext, depth = o[-3:]
            self.assertEqual(stray, 0, '%s: addressed outside the 24 x 80 screen' % cpu)
            self.assertEqual(offtext, 0, '%s: text outside rows 1-21' % cpu)
            self.assertLessEqual(depth, STACK_MAX, '%s: the processor stack' % cpu)
            self.depth = max(self.depth, depth)
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

    def test_nested_blocks_do_not_recurse(self):
        """_DB and _EN inside a block being skipped called epistole() again,
        each level two bytes of the processor's stack that only a __XX or
        the end of the file gave back. Before: `_DB` 130 times in a row (or
        `_EN`) wrapped page 1 over the return addresses before the first
        screen -- sim65 stopped on an illegal opcode ($FF at $00C4 with
        cc65 master's sim65, at $10000 or on its cycle limit with this
        harness); on the machine, wild execution inside a file manager.
        Now two levels at most: 21 bytes of stack whatever the document
        (pages() holds every run to STACK_MAX)."""
        for cmd in (b'_DB', b'_EN', b'_DB_EN', b'_db'):
            with self.subTest(cmd=cmd):
                doc = b'AVANT\r' + cmd * 130 + b'pied %$\r__BA\rAPRES\r'
                rows = self.text(doc)
                # One empty row for the block, as for a single _DB, and no
                # footer: a _DB or _EN inside a block laid out hides the
                # rest of it, as it did one level deep.
                self.assertEqual(rows[:3], ['AVANT', '', 'APRES'])
                self.assertEqual([r for r in rows[3:] if r], [])
                self.assertLessEqual(self.depth, 24)
        # The same when the block is laid out (show_def), and with no end.
        rows = self.text(b'_DB' + b'_EN' * 130 + b'pied\r__BA\rTEXTE\r')
        self.assertEqual([r for r in rows if r], ['TEXTE'])
        self.assertEqual([r for r in self.text(b'TEXTE\r' + b'_DB_EN' * 200) if r], ['TEXTE'])
        self.assertLessEqual(self.depth, 24)
        # What a single level did is unchanged: one __XX ends the block,
        # and the commands inside it are taken as they come.
        rows = self.text(b'A\r_DB\rF1 %$\r_EN\rF2\r__BA\rB\r__EA\rC\r')
        self.assertEqual([r for r in rows if r], ['A', 'B', 'C', 'F1 1'])
        rows = self.text(b'A\r_DB\rF1\r_MG5\r__BA\rB\r_EN\rH\r__EA\rC\r_SP\rD\r')
        self.assertEqual([r for r in rows if r][:3], ['A', '     B', '     C'])

    def test_decimal_tab_beyond_the_right_margin(self):
        """`_MD30_TD40` then `Total #:?1]`: the blanks towards the tab's
        column were put until the row reached it, but put_ wraps a blank at
        the right margin and the row starts again at its left edge. Before:
        it never ended (sim65's cycle limit, both processors), each turn a
        gotoxy on a row one further -- an unsigned char that wraps -- and
        conio's BASCALC gives $0478-$07F8 for rows 24 to 31: the screen
        holes, where the disk and SmartPort firmware keep their state.
        Now the padding stops at the wrap: the number starts the next row."""
        rows = [r for r in self.text(b'_MD30_TD40\rTotal #:?1]\rsuite\r') if r]
        self.assertEqual(rows, ['Total', '1,00', 'suite'])
        self.assertEqual([r for r in self.text(b'_MD2_TD30#:?2') if r.strip()], ['2,00'])
        # Every tab against every margin, a left margin and an indent too:
        # all end, on the screen, the number whole.
        for md in (2, 11, 30, 79):
            for td in (1, 12, 31, 40, 79):
                doc = b'_MG3_MD%d_TD%d\r_MI4 T #:?1234,5]!\rfin\r' % (md, td)
                with self.subTest(md=md, td=td):
                    rows = [r.strip() for r in self.text(doc) if r.strip()]
                    self.assertEqual(''.join(rows).replace(' ', ''), 'T1234,50!fin')
        # A tab the margin leaves room for is where it was: comma at 19.
        rows = self.text(b'_MD40_TD20\rx#:?5]\r')
        self.assertEqual(rows[1], 'x' + ' ' * 17 + '5,00')

    def test_no_row_past_the_page(self):
        """emit() counted on its callers to stop at the last row, and two
        did not. A field shown as written is up to 63 characters put in one
        go: between narrow margins and begun on row 21 it went on over rows
        22 to 26 (before: 22 characters outside the screen, 40 off the
        text, and all but its last row missing from the next page); a
        footer of one 3,000-character line went on for 38 rows from where
        it started (before: more than 255 characters outside the screen,
        the rest of it never shown). Past row 23 conio writes into the
        screen holes. Now emit() drops what is past row 21, and the next
        page shows it."""
        field = b'1+' * 28 + b'1/0'
        doc = b'_MD10\r' + b'l\r' * 19 + b'#:?' + field + b']\rFIN\r'
        shots = self.pages(doc, keys=' ')
        self.assertEqual(shots[0][0][21].rstrip(), '1+1+1+1+1+')
        self.assertTrue(shots[0][0][22].startswith('Page 1:'), shots[0][0][22])
        self.assertEqual(shots[0][0][23].strip(), '')
        rows = [r.rstrip() for r in shots[1][0][1:22] if r.strip()]
        self.assertEqual(''.join(rows[:-1]), field.decode()[10:])
        self.assertEqual(rows[-1], 'FIN')
        foot = b'F' * 3000
        shots = self.pages(b'_DB\r' + foot + b'\r__BA\rTEXTE\r', keys='  ')
        seen = [r.rstrip() for rows, _ in shots[:2] for r in rows[1:22]]
        self.assertEqual(''.join(r for r in seen if r.startswith('F')), foot.decode())
        self.assertIn('(end)', shots[1][0][22])
        self.assertNotIn('(end)', shots[0][0][22])

    def test_an_exponent_past_the_range_is_refused(self):
        """The exponent after E was built in 8 bits and tested after the
        multiplication: 26 * 10 is 4. Before: `A #:?1E260]` showed
        `A 100000,00` and `#:?2E-259]` showed `7E-03,00` -- wrong numbers,
        where the contract is that what cannot be computed stays as
        written. Now 40 and more is refused before multiplying."""
        doc = (b'A #:?1E260]\r#:?2E-259]\r#:?1E2560]\r#:?1E39]\r#:?1E040]\r#:?1E99999]\r'
               b'#:?1E37]\r#:?1E0005]\r#:?5E-3]\r#:?12E+2]\r#:?1E38]\r')
        shots = self.pages(doc)
        rows = [r.rstrip() for r in shots[0][0][1:12]]
        self.assertEqual(rows, ['A 1E260', '2E-259', '1E2560', '1E39', '1E040', '1E99999',
                                '1E+37,00', '100000,00', '0,01', '1200,00', '1E+38,00'])
        self.assertEqual(shots[0][1][1][:8], '  ##### ', 'as written: in inverse')

    def test_page_numbers_to_255(self):
        """%$ was written for 1 to 99, and the number shared its byte with
        the pending break. Before: page 100 was `PAGE :0`, 101 `PAGE :1`,
        and after page 127 the number was $80, the break bit: a break
        nobody asked for, then `PAGE 0`, `PAGE 1`... Now three digits, the
        break in a byte of its own, and past 255 pages the number stays at
        255."""
        doc = b'_DB PAGE %$\r__BA\r' + b'x_SP\r' * 262
        shots = self.pages(doc, keys=' ' * 45)
        seen, rules = [], 0
        for k, (rows, _) in enumerate(shots):
            if k and rows == shots[k - 1][0]:
                continue
            for r in rows[1:22]:
                if r.startswith(' PAGE'):
                    seen.append(r.strip())
                rules += r.startswith('-----')
        self.assertIn('(end)', shots[-1][0][22])
        self.assertEqual(seen[:255], ['PAGE %d' % n for n in range(1, 256)])
        # 261 breaks (the last _SP has no text after it) and the end.
        self.assertEqual(seen[255:], ['PAGE 255'] * 7)
        self.assertEqual(rules, 261, 'one rule a break')

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
