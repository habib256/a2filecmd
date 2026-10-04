"""Run the whole GMAGIC overlay (src/plugins/gmagic.s) under sim65.

The entry point runs on both processors as the program calls it, with a
service table whose file services read the picture from memory and can
fail at any byte (fopen, a read during the checks or during the drawing,
fseek). Every time the overlay waits for a key the harness writes the
8,192-byte page out: those pages are compared with Appendix B of
docs/GRAPHICS-MAGICIAN-FORMAT.md (the SHA-256 the spec gives) and with
tools/gmagic_ref.py, written from the same text.

Two builds: the overlay as shipped, and one assembled with GM_LAX, which
drops the two recognition rules of the spec's section 3 (the first command,
a line start among lines) so that every drawing test of Appendix B -- an
empty picture, pictures that open on a fill -- can be drawn.

Also checked: a malformed picture is refused before anything is drawn or
shown and the file is closed; a read error is never an end of file; the
memory outside the overlay's own areas is left alone (guard bytes): the
main text page outside its 112-byte block heads (screen holes, $06F7),
$0200-$03FF, the ProDOS buffer $0800-$0BFF, $1000-$1FFF; no auxiliary
memory switch is ever written. tools/test_gmagic_writes.py runs the
shipped 6502 binary in a 6502 interpreter that records every write.
"""
import hashlib
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
import gmagic_ref as ref  # noqa: E402

M_BAD = 'Not a whole Graphics Magician picture, or I/O error.'
GUARD = 0x5A

# argv: type keys failat failpass flags. failat: the byte offset whose read
# fails (-1: none), during read pass failpass (1: the checks, 2: the first
# drawing...; a pass starts at each fopen or fseek). flags: 1 fopen fails,
# 2 fseek fails, 4 fclose fails. The picture is pic.bin.
HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include "src/a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
unsigned int getsp(void);
static struct A2fcApi api;
static struct Entry sel;
static unsigned char fbuf[12288];
static unsigned fsize, fpos;
static long failat;
static unsigned char failpass, pass, flags, isopen, opens, closes, odd;
static unsigned char file[3];                   /* FILE: f_fd, f_flags, f_pushback */
static const char* keys;
static unsigned char kp, waits;
static unsigned char copy_buf[512];
static char full[81] = "/VOL/PIC", note[80], reselect[17];
static void out(const void* p, unsigned n)
{
    const unsigned char* c = p;
    int r;
    while (n) { r = write(1, c, n); if (r <= 0) exit(30); c += r; n -= r; }
}
static FILE* opn(const char* p, const char* m)
{
    if (strcmp(p, full) || strcmp(m, "rb")) odd |= 1;
    if (isopen) odd |= 2;
    if (flags & 1) return NULL;
    isopen = 1; ++opens; file[1] = 0; fpos = 0; ++pass;
    return (FILE*)file;
}
static size_t rd(void* p, size_t s, size_t n, FILE* f)
{
    unsigned got;
    if (f != (FILE*)file || s != 1 || p != note || n > 80 || !isopen) odd |= 4;
    got = fsize - fpos < n ? fsize - fpos : n;
    if (failat >= 0 && pass == failpass && (unsigned long)failat >= fpos
        && (unsigned long)failat < fpos + got) {
        got = (unsigned)failat - fpos;
        file[1] |= 4;                           /* _FERROR */
    }
    memcpy(p, fbuf + fpos, got);
    fpos += got;
    return got;
}
static int sk(FILE* f, long off, int whence)
{
    if (f != (FILE*)file || whence != SEEK_SET || !isopen) odd |= 8;
    if (flags & 2) return -1;
    fpos = (unsigned)off; ++pass;
    return 0;
}
static int cls(FILE* f)
{
    if (f != (FILE*)file || !isopen) odd |= 16;
    isopen = 0; ++closes;
    return flags & 4 ? EOF : 0;
}
static char gk(void)
{
    ++waits;
    out((void*)0x2000, 0x2000);
    return keys[kp] ? keys[kp++] : 27;
}
static unsigned char mk(unsigned char k)
{
    k &= 127;
    return k == 27 || k == 8 || k == 21;
}
static unsigned first_changed(unsigned from, unsigned to)
{
    unsigned i;
    for (i = from; i < to; ++i) if (*(unsigned char*)i != 0x5A) return i;
    return 0;
}
int main(int argc, char** argv)
{
    int fd;
    unsigned sp0, sp1, i, bad;
    (void)argc;
    fd = open("pic.bin", O_RDONLY);
    if (fd < 0) return 20;
    fsize = read(fd, fbuf, sizeof fbuf);
    close(fd);
    sel.type = atoi(argv[1]);
    keys = argv[2][0] == '-' ? "" : argv[2];
    failat = atol(argv[3]); failpass = atoi(argv[4]); flags = atoi(argv[5]);
    sel.size = fsize;
    strcpy(sel.name, "PICTURE");
    api.full = full; api.selected = &sel; api.note = note; api.reselect = reselect;
    api.copy_buf = copy_buf;
    api.fopen = opn; api.fread = rd; api.fseek = sk; api.fclose = cls; api.strcpy = strcpy;
    api.cgetc = gk; api.media_key = mk;
    memset(note, 0x77, sizeof note);
    memset((void*)0x0200, 0x5A, 0x0A00);         /* $0200-$0BFF */
    memset((void*)0x1000, 0x5A, 0x1000);         /* $1000-$1FFF */
    memset((void*)0x2000, 0xEE, 0x2000);
    memset((void*)0xC000, 0xFF, 0x100);
    sp0 = getsp();
    plugin_entry(&api);
    sp1 = getsp();
    out("E", 1);
    out(&waits, 1);
    i = sp0 == sp1; out(&i, 1);
    out(&odd, 1); out(&isopen, 1); out(&opens, 1); out(&closes, 1);
    out(note, 80);
    out(reselect, 17);
    i = first_changed(0x0200, 0x0400); out(&i, 2);
    /* the text page: only the first 112 bytes of each 128-byte block */
    bad = 0;
    for (i = 0x0400; i < 0x0800; ++i)
        if ((i & 0x7F) >= 112 && *(unsigned char*)i != 0x5A) { bad = i; break; }
    out(&bad, 2);
    i = first_changed(0x0800, 0x0C00); out(&i, 2);
    i = first_changed(0x1000, 0x2000); out(&i, 2);
    out((void*)0xC000, 0x100);
    out((void*)0x0400, 0x400);
    out((void*)0x2000, 0x2000);
    return 0;
}
'''

GETSP = '''
        .export _getsp
        .importzp sp
_getsp: lda sp
        ldx sp+1
        rts
'''


class Run:
    def __init__(self, out, nwait):
        self.pages = [out[i * 8192:(i + 1) * 8192] for i in range(nwait)]
        o = out[nwait * 8192:]
        assert o[0:1] == b'E', o[:16]
        self.waits, self.sp_ok, self.odd, self.isopen, self.opens, self.closes = o[1:7]
        self.note = o[7:87].split(b'\0')[0].decode('latin-1')
        self.reselect = o[87:104].split(b'\0')[0].decode('latin-1')
        w = lambda k: o[k] | o[k + 1] << 8
        self.low_changed, self.text_changed, self.buf_changed, self.mid_changed = (
            w(104), w(106), w(108), w(110))
        self.io = o[112:368]
        self.text = o[368:1392]
        self.page = o[1392:1392 + 8192]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def build(d, lax_too=True):
    """The harness linked with the overlay in directory d, for both
    processors, as shipped and (lax_too) with GM_LAX: {(cpu, lax): exe}."""
    target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                          text=True).strip())
    (d / 'harness.c').write_text(HARNESS)
    (d / 'getsp.s').write_text(GETSP)
    # Copies, under other names: cl65 turns a .c into a .s beside it,
    # and would overwrite gmagic.s in the source tree.
    shutil.copyfile(ROOT / 'src/plugins/gmagic.c', d / 'gm_hdr.c')
    for name in ('gmagic.s', 'gmagic_tables.inc', 'gmagic_text.inc'):
        shutil.copyfile(ROOT / 'src/plugins' / name, d / name)
    programs = {}
    for cpu in ('6502', '65c02'):
        base = 'sim65c02' if cpu == '65c02' else 'sim6502'
        cfg = (target.parent / f'cfg/{base}.cfg').read_text()
        # The harness above $4000, as the program is; the overlay's
        # $0C00 part where it runs, its COLD part anywhere.
        cfg = cfg.replace('start = $0200, size = $FDF0 - __STACKSIZE__',
                          'start = $4000, size = $BF00 - $4000 - __STACKSIZE__')
        cfg = cfg.replace('MEMORY {', 'MEMORY {\n    LOW: file = "", define = yes, start = $0C00, size = $0400;')
        cfg = cfg.replace('SEGMENTS {', 'SEGMENTS {\n    COLD: load = MAIN, type = ro;\n'
                          '    GMLOW: load = MAIN, run = LOW, type = ro, define = yes;\n'
                          '    GMBSS: load = LOW, type = bss, define = yes;')
        (d / f'{cpu}.cfg').write_text(cfg)
        for lax in ((False, True) if lax_too else (False,)):
            exe = d / f'harness-{cpu}{"-lax" if lax else ""}'
            subprocess.run(['cl65', '-t', base, '-I', str(ROOT), '-I', str(ROOT / 'src/plugins'), '-DGM_TEST', '-C', str(d / f'{cpu}.cfg'),
                            *(['--asm-define', 'GM_LAX'] if lax else []),
                            '-O', '-o', str(exe), str(d / 'harness.c'), str(d / 'gm_hdr.c'),
                            str(d / 'gmagic.s'), str(d / 'getsp.s')],
                           check=True, cwd=d)
            programs[cpu, lax] = exe
    return programs


class Gmagic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-gmagic-')
        cls.dir = Path(cls.tmp.name)
        cls.programs = build(cls.dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_gm(self, cpu, data, keys='', typ=6, failat=-1, failpass=1, flags=0, lax=False):
        (self.dir / 'pic.bin').write_bytes(data)
        p = subprocess.run(['sim65', str(self.programs[cpu, lax]), str(typ), keys or '-',
                            str(failat), str(failpass), str(flags)],
                           cwd=self.dir, capture_output=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((self.dir / 'pic.bin').read_bytes(), data, 'the file is only read')
        nwait = (len(p.stdout) - 1392 - 8192) // 8192
        r = Run(p.stdout, nwait)
        self.assertEqual(r.waits, nwait)
        self.common(r)
        return r

    def common(self, r):
        self.assertEqual(r.sp_ok, 1, 'the C stack is balanced')
        self.assertEqual(r.odd, 0, 'every service called as documented')
        self.assertEqual(r.isopen, 0, 'the file is closed')
        self.assertLessEqual(r.opens, 1, 'one fopen')
        self.assertEqual(r.reselect, 'PICTURE')
        self.assertEqual((r.low_changed, r.text_changed, r.buf_changed, r.mid_changed), (0, 0, 0, 0),
                         'memory outside the overlay left alone')
        for sw in (0xC001, 0xC003, 0xC005, 0xC009, 0xC055):    # 80STORE on, AUX, ALTZP, PAGE2
            self.assertEqual(r.io[sw - 0xC000], 0xFF, 'soft switch $%04X untouched' % sw)

    def shown(self, r):
        """The hi-res screen was put on (TEXT off, HIRES on, PAGE2 off)."""
        return r.io[0x50] != 0xFF and r.io[0x57] != 0xFF and r.io[0x54] != 0xFF

    def refused(self, r):
        self.assertEqual(r.waits, 0, 'a refused picture is never waited on')
        self.assertEqual(r.note, M_BAD)
        self.assertEqual(r.page, b'\xee' * 8192, 'nothing drawn')
        self.assertFalse(self.shown(r), 'never shown')
        self.assertEqual(r.text, bytes([GUARD]) * 1024, 'the text page untouched')

    # -- Appendix B ------------------------------------------------------------
    def appendix_b(self, cpu, lax):
        cases = {}
        for name, data, dia, base, last, want in ref.expected_pages():
            cases.setdefault((name.split('[')[0], data), []).append((dia, base, last, want))
        seen = set()
        for (name, data), pages in cases.items():
            if not lax:
                try:
                    ref.parts(data)
                except ref.Malformed:
                    continue
            if name.startswith('G01'):
                runs = [('NN', [(ref.V82, 0, 0), (ref.V82, 1, 1), (ref.V82, 2, 2)]),
                        ('DNN', [(ref.V82, 0, 0), (ref.V84, 0, 0), (ref.V84, 1, 1), (ref.V84, 2, 2)])]
            elif name.startswith('O01'):
                runs = [('O', [(ref.V82, 0, 0), (ref.V82, 0, 1)]),
                        ('DO', [(ref.V82, 0, 0), (ref.V84, 0, 0), (ref.V84, 0, 1)])]
            else:
                runs = [('D', [(ref.V82, 0, 0), (ref.V84, 0, 0)])]
            want = {(d, b, l): w for d, b, l, w in pages}
            for keys, views in runs:
                r = self.run_gm(cpu, data, keys, lax=lax)
                self.assertEqual(r.note, '')
                self.assertEqual(len(r.pages), len(views), name)
                for page, (d, b, l) in zip(r.pages, views):
                    expect = ref.view(data, d, b, l, recognise=False)
                    if (d, b, l) in want:
                        self.assertEqual(sha(page), want[d, b, l], '%s %s %d-%d: Appendix B' % (name, d, b, l))
                        seen.add((name, d, b, l))
                    self.assertEqual(page, expect, '%s %s %d-%d: the reference' % (name, d, b, l))
                self.assertEqual(r.page, r.pages[-1])
                self.assertTrue(self.shown(r))
        return len(seen)

    def test_appendix_b_every_page_on_both_processors(self):
        """All 152 pages of Appendix B, with the recognition rules off."""
        for cpu in ('6502', '65c02'):
            with self.subTest(cpu=cpu):
                self.assertEqual(self.appendix_b(cpu, lax=True), 152)

    def test_appendix_b_recognised_pictures_as_shipped(self):
        """The shipped overlay draws every Appendix B picture it recognises,
        and refuses the others (an empty picture, a fill first...)."""
        for cpu in ('6502', '65c02'):
            with self.subTest(cpu=cpu):
                self.assertGreater(self.appendix_b(cpu, lax=False), 60)
        for name, data in ref.corpus().items():
            try:
                ref.parts(data)
            except ref.Malformed:
                self.refused(self.run_gm('6502', data, 'D'))

    def test_includes_are_generated_from_the_reference(self):
        for name, text in ref.includes().items():
            self.assertEqual((ROOT / 'src/plugins' / name).read_text(), text, name)

    def test_the_pages_tool(self):
        """tools/gmagic_pages.py writes the pages of a directory of
        pictures, with the real overlay or the reference."""
        import json
        pics, out = self.dir / 'pics', self.dir / 'pages'
        pics.mkdir()
        c = ref.corpus()
        index = {'001': 'V82', '002.pic': 'V84', '003': 'v84', '004': 'V82'}
        for stem, name in (('001', 'H02-colour-at-line-start'), ('002', 'R02-seed1002-n120'),
                           ('003', 'O01-picture-plus-overlay'), ('004', 'H01-empty')):
            (pics / (stem + '.pic')).write_bytes(c[name])
        (pics / 'index.json').write_text(json.dumps(index))
        for engine in ('sim65', 'ref'):
            p = subprocess.run([sys.executable, str(ROOT / 'tools/gmagic_pages.py'), str(pics), str(out),
                                '--engine', engine], capture_output=True, text=True)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)      # 004 is refused
            self.assertIn('004', p.stdout)
            self.assertEqual((out / '001.page').read_bytes(), ref.render(c['H02-colour-at-line-start'], ref.V82))
            self.assertEqual((out / '002.page').read_bytes(), ref.render(c['R02-seed1002-n120'], ref.V84))
            self.assertEqual((out / '003.page').read_bytes(), ref.render(c['O01-picture-plus-overlay'], ref.V84))
            self.assertFalse((out / '004.page').exists())
            shutil.rmtree(out)

    # -- refusals --------------------------------------------------------------
    def malformed(self):
        P = ref.P
        ok = bytes.fromhex('2280000AA1170A25A0001480001EA1171E00')    # H02
        yield 'no end byte', ok[:-1]
        yield 'empty file', b''
        yield 'only the end byte', b'\x00'
        yield 'colour 8', b'\x28' + ok
        yield 'brush 8', b'\x24\x48' + ok[1:]
        yield 'pattern 108', b'\x24\x60\x6C' + ok[1:]
        yield 'pattern with a nibble', b'\x24\x61\x05' + ok[1:]
        yield 'X 280', b'\x24' + P(0x80, 280, 10) + ok[1:]
        yield 'Y 192', b'\x24' + P(0x80, 10, 192) + ok[1:]
        yield 'X high 2', b'\x24\x82\x00\x0A' + ok[1:]
        yield 'fill X 280', b'\x24' + P(0xE0, 280, 1) + b'\x00'
        yield 'brush Y 192', b'\x24' + P(0xC0, 1, 192) + b'\x00'
        yield 'character $1F', b'\x24\x50\x1F\x00'
        yield 'character $80', b'\x24\x30\x80\x00'
        yield 'text with a nibble', b'\x24\x51\x41\x00'
        yield 'text cursor X 280', b'\x24' + P(0x10, 280, 0) + b'\x00'
        for op in (0x70, 0x90, 0xB0, 0xD0, 0xF0, 0x01, 0x0F):
            yield 'opcode $%02X' % op, b'\x24' + bytes([op, 0, 0, 0]) + b'\x00'
        yield 'lines without a line start', b'\x24' + P(0xA0, 10, 10) + b'\x00'
        for first in (0xC0, 0xE0, 0x10, 0x30, 0x50):
            yield 'first command $%02X' % first, bytes([first, 0x41 if first in (0x30, 0x50) else 0, 0]) + ok
        yield 'draws nothing: colour', b'\x26\x00'
        yield 'draws nothing: colours, brush, pattern', b'\x20\x26\x43\x60\x05\x00'
        yield 'draws nothing: pattern only', b'\x60\x05\x00'
        yield 'draws nothing: line starts only', b'\x24' + P(0x80, 10, 10) + P(0x80, 20, 20) + b'\x00'
        yield 'draws nothing: text only', b'\x24' + P(0x10, 10, 10) + b'\x50A\x30B\x00'
        yield 'truncated coordinates', b'\x24\x80\x00'
        yield 'truncated pattern', b'\x24\x60'

    def test_malformed_pictures_are_refused_before_drawing(self):
        for cpu in ('6502', '65c02'):
            for what, data in self.malformed():
                with self.subTest(cpu=cpu, what=what):
                    with self.assertRaises(ref.Malformed):
                        ref.parts(data)
                    self.refused(self.run_gm(cpu, data, 'D'))

    def test_a_single_brush_or_fill_is_a_picture(self):
        P = ref.P
        for data in (b'\x45' + P(0xC0, 100, 100) + b'\x00', b'\x60\x07' + P(0xE0, 140, 96) + b'\x00',
                     b'\x24' + P(0xA0, 10, 10) + P(0x80, 1, 1) + b'\x00'):
            for cpu in ('6502', '65c02'):
                r = self.run_gm(cpu, data)
                self.assertEqual(r.pages, [ref.render(data, ref.V82)])

    def test_a_later_picture_that_draws_nothing_ends_the_file(self):
        """Rule 5 applies to every picture, as rules 2-4 do: the pictures
        after one that draws nothing are ignored."""
        g = bytes.fromhex('600FE00A0A00' '2600' '24800A0AA0C89600')
        r = self.run_gm('65c02', g, 'NN')
        self.assertEqual(len(ref.parts(g)), 1)
        self.assertEqual(r.pages, [ref.view(g, ref.V82, 0, 0)] * 3)

    def test_not_a_bin_file(self):
        data = ref.hand_made()['H02-colour-at-line-start']
        for typ in (4, 0xC1, 0x08):
            self.refused(self.run_gm('6502', data, typ=typ))

    def test_io_failures_are_never_an_end_of_file(self):
        """fopen failing, a read error at any byte of the checks (also
        after the first picture: the whole file is refused, not cut), and
        an fseek failure: refused, nothing drawn, the file closed."""
        g = bytes.fromhex('600FE00A0A00' '24800A0AA0C89600' '605A47C0646400')
        for cpu in ('6502', '65c02'):
            self.refused(self.run_gm(cpu, g, flags=1))
            for at in range(len(g)):
                with self.subTest(cpu=cpu, at=at):
                    self.refused(self.run_gm(cpu, g, failat=at, failpass=1))
            r = self.run_gm(cpu, g, flags=2)
            self.refused(r)

    def test_read_error_while_drawing(self):
        """The file changed under the overlay is not possible, but a read
        error during the drawing stops it with the note, the file closed."""
        g = bytes.fromhex('600FE00A0A00' '24800A0AA0C89600' '605A47C0646400')
        for cpu in ('6502', '65c02'):
            # the passes: 1 the checks, 2 the rewind before the page is
            # touched, 3 the first view, 4 the view after D
            for at, waits in ((0, 0), (3, 0), (7, 1), (12, 1), (17, 2)):
                r = self.run_gm(cpu, g, 'NND', failat=at, failpass=3)
                self.assertEqual((r.note, r.waits), (M_BAD, waits))
            r = self.run_gm(cpu, g, 'D', failat=2, failpass=4)
            self.assertEqual((r.note, r.waits), (M_BAD, 1))

    def test_close_failure_after_viewing_is_harmless(self):
        r = self.run_gm('6502', ref.hand_made()['H02-colour-at-line-start'], flags=4)
        self.assertEqual((r.note, r.waits), ('', 1))

    # -- several pictures, the keys -------------------------------------------
    def test_pictures_after_the_last_good_one_are_ignored(self):
        g = bytes.fromhex('600FE00A0A00' '24800A0AA0C89600' '605A47C0646400')
        for tail in (b'', b'\x00\x00\x00', b'\x28\x00', b'\x24\x80', b'\xC0\x01\x01\x00', bytes(range(256))):
            with self.subTest(tail=tail[:4]):
                data = g + tail
                r = self.run_gm('65c02', data, 'NNNN')
                want = [ref.view(data, ref.V82, i % 3, i % 3) for i in (0, 1, 2, 0, 1)]
                self.assertEqual(r.pages, want)

    def test_overlay_key_stops_at_the_last_picture_and_d_redraws(self):
        o = bytes.fromhex('24803232A0E632A08C96A032326007E08C3C00' '603CE00A0A26800000A117BF00')
        r = self.run_gm('6502', o, 'OODN')
        v = lambda d, b, l: ref.view(o, d, b, l)
        self.assertEqual(r.pages, [v(ref.V82, 0, 0), v(ref.V82, 0, 1), v(ref.V82, 0, 1),
                                   v(ref.V84, 0, 1), v(ref.V84, 0, 0)])   # N after the last: the first
        one = ref.hand_made()['H02-colour-at-line-start']
        r = self.run_gm('6502', one, 'NO x')
        self.assertEqual(len(set(r.pages)), 1, 'a single picture: N, O do nothing')

    def test_left_right_and_escape_leave(self):
        one = ref.hand_made()['H02-colour-at-line-start']
        for key in ('\x08', '\x15'):
            r = self.run_gm('6502', one, key + 'D')
            self.assertEqual((r.waits, r.note), (1, ''))

    # -- text (V84 only, A2FC's substitute font) -------------------------------
    def text_picture(self):
        P = ref.P
        b = bytearray(b'\x24\x60\x50')          # pattern 80: black
        b += P(0x80, 0, 100) + P(0xA0, 279, 100)
        b += P(0x10, 3, 2)
        for ch in range(0x20, 0x80):
            b += bytes([0x50, ch])
            if ch % 32 == 31:
                b += P(0x10, 1 + ch // 32, 20 + ch // 4)
        b += P(0x10, 250, 60) + b'\x50W\x50X\x50Y\x50Z\x50W'   # past the right edge
        b += P(0x10, 271, 186) + b'\x30A\x30B'                    # below the screen, XOR
        b += P(0x10, 279, 191) + b'\x50M'
        b += b'\x60\x07' + P(0xE0, 140, 150)
        b += b'\x46' + P(0xC0, 270, 185) + b'\x30Q'
        return bytes(b + b'\x00')

    def test_text_is_v84_with_the_a2fc_font(self):
        data = self.text_picture()
        self.assertEqual(ref.dialect_of(data), ref.V84)
        for cpu in ('6502', '65c02'):
            r = self.run_gm(cpu, data, 'D')
            want = ref.render(data, ref.V84)
            self.assertEqual(r.pages, [want, want], 'V84 forced: D does nothing')
            # the font and the row patterns, where the overlay keeps them
            blocks = ref.text_blocks()
            for i in range(8):
                self.assertEqual(r.text[i * 128:i * 128 + 112], blocks[i])
                self.assertEqual(r.text[i * 128 + 112:i * 128 + 128], bytes([GUARD]) * 16)
        for ch in range(0x20, 0x80):
            a = ref.glyph_address(ch) - 0x400
            blk = a // 128
            self.assertLess(a % 128, 112)
            self.assertNotEqual(blk, 5)
            self.assertEqual(r.text[a:a + 8], ref.font()[(ch - 0x20) * 8:(ch - 0x20) * 8 + 8])

    # -- random pictures -------------------------------------------------------
    def test_random_pictures(self):
        """Valid random pictures with every command, on both processors,
        in both dialects; also random bytes, which must be refused unless
        they happen to be a picture, and then be drawn as one."""
        rnd = random.Random(1984)
        P = ref.P
        for k in range(24):
            b = bytearray([0x24, 0x80, rnd.randrange(256), rnd.randrange(192)])
            text = k % 4 == 3
            for _ in range(rnd.choice((5, 30, 90))):
                r = rnd.randrange(100)
                if r < 10: b.append(0x20 + rnd.randrange(8))
                elif r < 15: b.append(0x40 + rnd.randrange(8))
                elif r < 22: b += bytes([0x60, rnd.randrange(108)])
                elif r < 35: b += P(0x80, rnd.randrange(280), rnd.randrange(192))
                elif r < 55: b += P(0xA0, rnd.randrange(280), rnd.randrange(192))
                elif r < 72: b += P(0xC0, rnd.choice((rnd.randrange(280), 279, 266)), rnd.choice((rnd.randrange(192), 191, 177)))
                elif r < 90 or not text: b += P(0xE0, rnd.randrange(280), rnd.choice((rnd.randrange(192), 0, 191)))
                elif r < 95: b += P(0x10, rnd.randrange(280), rnd.randrange(192))
                else: b += bytes([rnd.choice((0x30, 0x50)), rnd.randrange(0x20, 0x80)])
            data = bytes(b + b'\x00')
            cpu = ('6502', '65c02')[k % 2]
            with self.subTest(k=k):
                try:
                    ref.parts(data)
                except ref.Malformed:                    # drew nothing (rule 5)
                    self.refused(self.run_gm(cpu, data))
                    continue
                r = self.run_gm(cpu, data, 'D')
                d = ref.dialect_of(data)
                self.assertEqual(r.pages[0], ref.render(data, d))
                self.assertEqual(r.pages[1], ref.render(data, ref.V84))
        for k in range(40):
            data = bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 40)))
            if rnd.randrange(2):
                data = bytes([0x20 + rnd.randrange(8)]) + data
            with self.subTest(random=k):
                try:
                    ref.parts(data)
                except ref.Malformed:
                    self.refused(self.run_gm('65c02', data))
                    continue
                r = self.run_gm('65c02', data)
                self.assertEqual(r.pages, [ref.render(data, ref.dialect_of(data))])


if __name__ == '__main__':
    unittest.main()
