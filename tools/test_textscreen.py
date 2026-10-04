"""Text screens in DGRVIEW: the real overlay, run in a model of the IIe.

A BIN at aux $0400 of up to 2,048 bytes (or 1,024/2,048 bytes chosen with I)
is a saved page of the text screen, and DGRVIEW shows it -- as lo-res, or,
since 2026-10-04, as the TEXT it holds when its content says so (looks_text,
tools/textscreen_ref.py); T turns the guess round, A switches the character
set. These tests build src/plugins/dgrview.c for BOTH editions exactly as
the Makefile does (cc65 2.19 for the 65C02, cc65 master for the 6502) and
run the resulting .PLG in tools/mos6502.py, extended here with the 65C02
opcodes and the IIe's memory routing: 80STORE + PAGE2 send $0400-$07FF to
the auxiliary bank, RAMRD/RAMWRT the rest, and every soft switch is a
state. The service table's functions are traps answered in Python.

What is proven, per edition:
  - the visible bytes of the page land in the right bank, and NOTHING else
    is written: no screen hole in either bank (the cards' and the
    firmware's state), no byte of AUX outside $0400-$07FF (/RAM's blocks),
    no main RAM outside the overlay's own window, its zero page, the stack
    page and the C stack;
  - the screen is on the air as the file asks while the viewer waits for a
    key: TEXT, 40 or 80 columns, the character set;
  - T switches text <-> lo-res and A the character set without writing a
    byte of the page; the panels' character set (RDALTCHAR) is put back on
    the way out;
  - no I/O soft switch outside the display's is touched (no disk, no slot).
The heuristic itself is checked on synthetic pages here and, when the
private corpus is present (~/.cache/a2fc/textscreen/manifest.tsv, real
files from Asimov), on every labelled real file of both kinds: the C and
the Python rule must agree file by file, and the measured error rates must
stay what docs/MANUAL.md says.
"""
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textscreen_ref as ref  # noqa: E402
from mos6502 import CPU, Halt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HEAD = Path(os.environ.get('CC65_HEAD', Path.home() / 'opt/cc65-head'))
CORPUS = Path(os.environ.get('A2FC_TEXTSCREEN', Path.home() / '.cache/a2fc/textscreen'))
ESC = 0x1B
TRAP = 0xF000                       # the service table's functions: traps
API, FULL, NOTE, RESEL, SEL, INPUT = 0x9400, 0x9500, 0x9600, 0x9660, 0x9680, 0x96C0
CSTACK = 0x8F00                     # the C stack's top (grows down)
STAGE = 0x3000                      # dgrview.c's staging area
FIELDS = ('full', 'note', 'reselect', 'selected', 'input', 'fopen', 'fread', 'fclose', 'strcpy',
          'sprintf', 'cgetc', 'media_key', 'media_wait', 'prompt', 'message')
VISIBLE = [o for o in range(1024) if o % 128 < 120]
HOLES = [o for o in range(1024) if o % 128 >= 120]


# -- building the overlay as the Makefile does ------------------------------
def editions():
    out = []
    if shutil.which('cc65'):
        lib = Path(shutil.which('cc65')).resolve().parent.parent / 'share/cc65/lib/apple2enh.lib'
        out.append(('65C02', {}, '', 'apple2enh', [], lib))
    if (HEAD / 'bin/cc65').exists():
        env = {'CC65_HOME': str(HEAD / 'share/cc65')}
        out.append(('6502', env, str(HEAD / 'bin') + '/', 'apple2',
                    ['-DA2FC_6502', '-DA2FC_NOMOUSE', '-DA2FC_BIG_BINARY2'], HEAD / 'share/cc65/lib/apple2.lib'))
    return out


def build(edition, tmp):
    name, env, bindir, target, defs, lib = edition
    env = dict(os.environ, **env)
    tmp = Path(tmp)
    run = lambda *a: subprocess.run([str(x) for x in a], check=True, capture_output=True, env=env)
    run(bindir + 'cc65', '-t', target, *defs, '-O', '-Oirs', '-Cl', '--codesize', '100',
        '-I', ROOT / 'src', '-o', tmp / 'dgrview.s', ROOT / 'src/plugins/dgrview.c')
    run(bindir + 'ca65', '-t', target, '-o', tmp / 'dgrview.o', tmp / 'dgrview.s')
    run(bindir + 'ld65', '-C', ROOT / 'sdk/plugin.cfg', '-D', '__OVLSIZE__=0x1500',
        '-Ln', tmp / 'dgrview.lbl', '-o', tmp / 'dgrview.PLG', tmp / 'dgrview.o', lib)
    labels = {}
    for line in (tmp / 'dgrview.lbl').read_text().splitlines():
        _, addr, label = line.split()
        labels[label.lstrip('.')] = int(addr, 16)
    # The service table's offsets, from the same compiler.
    (tmp / 'ofs.c').write_text('#include <stddef.h>\n#include "a2fc_plugin.h"\n'
                               'const unsigned char ofs[] = {' +
                               ','.join(f'offsetof(struct A2fcApi,{f})' for f in FIELDS) + '};\n')
    run(bindir + 'cc65', '-t', target, '-I', ROOT / 'src', '-o', tmp / 'ofs.s', tmp / 'ofs.c')
    vals = [int(v, 16) for v in re.findall(r'\.byte\s+\$([0-9A-F]{2})', (tmp / 'ofs.s').read_text())]
    return (tmp / 'dgrview.PLG').read_bytes(), labels, dict(zip(FIELDS, vals))


# -- the IIe ----------------------------------------------------------------
class IIe(CPU):
    """mos6502.CPU with the 65C02 opcodes the compiler emits, two 64 KB banks
    and the soft switches of the display and of the memory routing."""
    SW = {0xC000: ('store80', 0), 0xC001: ('store80', 1), 0xC002: ('ramrd', 0), 0xC003: ('ramrd', 1),
          0xC004: ('ramwrt', 0), 0xC005: ('ramwrt', 1), 0xC00C: ('col80', 0), 0xC00D: ('col80', 1),
          0xC00E: ('altchar', 0), 0xC00F: ('altchar', 1)}
    TOGGLE = {0xC050: ('text', 0), 0xC051: ('text', 1), 0xC052: ('mixed', 0), 0xC053: ('mixed', 1),
              0xC054: ('page2', 0), 0xC055: ('page2', 1), 0xC056: ('hires', 0), 0xC057: ('hires', 1),
              0xC05E: ('an3', 0), 0xC05F: ('an3', 1)}
    STATUS = {0xC013: 'ramrd', 0xC014: 'ramwrt', 0xC018: 'store80', 0xC01A: 'text', 0xC01C: 'page2',
              0xC01D: 'hires', 0xC01E: 'altchar', 0xC01F: 'col80'}

    def __init__(self, cmos):
        super().__init__()
        self.aux = bytearray(65536)
        self.sw = dict(store80=1, ramrd=0, ramwrt=0, col80=1, altchar=1, text=1, mixed=0,
                       page2=0, hires=0, an3=1)
        self.log = []               # (bank, address) of every CPU write
        self.io = []                # every $C0xx touched
        if cmos:
            self._cmos()

    def bank(self, a, write):
        if a < 0x200 or a >= 0xC000:
            return 0
        if self.sw['store80'] and (0x400 <= a < 0x800 or (self.sw['hires'] and 0x2000 <= a < 0x4000)):
            return self.sw['page2']
        return self.sw['ramwrt' if write else 'ramrd']

    def soft(self, a, value=None):
        self.io.append(a)
        if a in self.TOGGLE:
            k, v = self.TOGGLE[a]
            self.sw[k] = v
        elif value is not None and a in self.SW:
            k, v = self.SW[a]
            self.sw[k] = v
        elif value is None and a in self.STATUS:
            return 0x80 if self.sw[self.STATUS[a]] else 0
        return 0

    def rd(self, a):
        if 0xC000 <= a < 0xC100:
            return self.soft(a)
        return (self.aux if self.bank(a, False) else self.m)[a]

    def wr(self, a, v):
        if 0xC000 <= a < 0xC100:
            self.soft(a, v)
            return
        b = self.bank(a, True)
        self.log.append((b, a))
        (self.aux if b else self.m)[a] = v & 255

    def _cmos(self):
        t = self.ops
        ind = lambda: (lambda z: self.rd(z) | self.rd((z + 1) & 255) << 8)(self.fetch())

        def alu(code, mode):
            # Reuse the NMOS table's ALU through its immediate form.
            imm = t[code]
            def op():
                v = self.rd(mode())
                saved = self.fetch
                self.fetch = lambda: v
                try:
                    imm()
                finally:
                    self.fetch = saved
            return op
        for imm, code in ((0x09, 0x12), (0x29, 0x32), (0x49, 0x52), (0x69, 0x72), (0xA9, 0xB2),
                          (0xC9, 0xD2), (0xE9, 0xF2)):
            t[code] = alu(imm, ind)
        t[0x92] = lambda: self.wr(ind(), self.a)
        t[0x64] = lambda: self.wr(self.zp(), 0)
        t[0x74] = lambda: self.wr(self.zpx(), 0)
        t[0x9C] = lambda: self.wr(self.ab(), 0)
        t[0x9E] = lambda: self.wr(self.abx(), 0)

        def bra():
            off = self.fetch()
            self.pc = (self.pc + (off - 256 if off & 128 else off)) & 0xFFFF
        t[0x80] = bra
        t[0xDA] = lambda: self.push(self.x)
        t[0xFA] = lambda: setattr(self, 'x', self.nz(self.pull()))
        t[0x5A] = lambda: self.push(self.y)
        t[0x7A] = lambda: setattr(self, 'y', self.nz(self.pull()))
        t[0x1A] = lambda: setattr(self, 'a', self.nz((self.a + 1) & 255))
        t[0x3A] = lambda: setattr(self, 'a', self.nz((self.a - 1) & 255))
        t[0x89] = lambda: setattr(self, 'z', int((self.a & self.fetch()) == 0))

        def bitm(mode):
            def op():
                v = self.rd(mode())
                self.n, self.v, self.z = v >> 7, v >> 6 & 1, int((self.a & v) == 0)
            return op
        t[0x34] = bitm(self.zpx)
        t[0x3C] = bitm(self.abx)

        def tsb(mode, reset):
            def op():
                a = mode()
                v = self.rd(a)
                self.z = int((self.a & v) == 0)
                self.wr(a, (v & ~self.a) if reset else (v | self.a))
            return op
        t[0x04], t[0x0C] = tsb(self.zp, 0), tsb(self.ab, 0)
        t[0x14], t[0x1C] = tsb(self.zp, 1), tsb(self.ab, 1)

        def jmpix():
            a = (self.fetch16() + self.x) & 0xFFFF
            self.pc = self.rd(a) | self.rd((a + 1) & 0xFFFF) << 8
        t[0x7C] = jmpix
        # 65C02 JMP (abs) has no page-wrap bug
        def jmpi():
            a = self.fetch16()
            self.pc = self.rd(a) | self.rd((a + 1) & 0xFFFF) << 8
        t[0x6C] = jmpi


class Machine:
    """One run of the overlay on one file, keys scripted."""

    def __init__(self, image, labels, ofs, cmos, data, aux=0x0400, keys=b'', path='/V/PIC'):
        self.cpu = c = IIe(cmos)
        self.data, self.keys, self.path = data, list(keys), path
        self.sp = labels['sp'] if 'sp' in labels else labels['c_sp']
        self.snaps = []             # the screen at each key read
        self.extra = set()          # main bytes the traps wrote (fread, strcpy, sprintf)
        c.m[0x1B00:0x1B00 + len(image)] = image
        self.window = range(0x1B00, 0x3000)
        # Seed both banks so that a write shows, holes included.
        for i in range(0x10000):
            c.aux[i] = (i * 7 + 3) & 255
        for a in range(0x400, 0x800):
            c.m[a] = (a * 5 + 1) & 255
        self.before_aux = bytes(c.aux)
        self.before_main = bytes(c.m)
        # The service table.
        w = lambda at, v: c.m.__setitem__(slice(at, at + 2), (v & 0xFFFF).to_bytes(2, 'little'))
        for i, f in enumerate(FIELDS[5:]):
            w(API + ofs[f], TRAP + 2 * i)
        w(API + ofs['full'], FULL); w(API + ofs['note'], NOTE); w(API + ofs['reselect'], RESEL)
        w(API + ofs['selected'], SEL); w(API + ofs['input'], INPUT)
        c.m[FULL:FULL + len(path) + 1] = path.encode() + b'\0'
        c.m[SEL:SEL + 29] = bytes(29)
        c.m[SEL:SEL + 4] = b'PIC\0'
        c.m[SEL + 17] = 0x06
        w(SEL + 19, aux)
        c.m[SEL + 23:SEL + 27] = len(data).to_bytes(4, 'little')
        w(self.sp, CSTACK)
        self.traps = {TRAP + 2 * i: getattr(self, 't_' + f) for i, f in enumerate(FIELDS[5:])}
        self.opened = 0
        self.altchar_at_entry = c.sw['altchar']

    # C stack and strings
    def word(self, a):
        return self.cpu.m[a] | self.cpu.m[a + 1] << 8

    def csp(self):
        return self.word(self.sp)

    def pop(self, n):
        v = self.csp() + n
        self.cpu.m[self.sp:self.sp + 2] = v.to_bytes(2, 'little')

    def cstr(self, a):
        out = bytearray()
        while self.cpu.m[a]:
            out.append(self.cpu.m[a]); a += 1
        return out.decode('latin1')

    def put(self, a, b):
        self.cpu.m[a:a + len(b)] = b
        self.extra.update(range(a, a + len(b)))

    def ret(self, v):
        self.cpu.a, self.cpu.x = v & 255, (v >> 8) & 255

    # the service table
    def t_fopen(self):
        name = self.cstr(self.word(self.csp())); self.pop(2)
        self.ret(1 if name == self.path else 0)
        self.opened += name == self.path

    def t_fread(self):
        s = self.csp()
        count, size, ptr = self.word(s), self.word(s + 2), self.word(s + 4)
        self.pop(6)
        n = min(size * count, len(self.data) - self.pos) if hasattr(self, 'pos') else min(size * count, len(self.data))
        self.pos = getattr(self, 'pos', 0)
        chunk = self.data[self.pos:self.pos + n]
        self.pos += len(chunk)
        self.put(ptr, chunk)
        self.ret(len(chunk) // max(size, 1))

    def t_fclose(self):
        self.ret(0)

    def t_strcpy(self):
        src = self.cpu.a | self.cpu.x << 8
        dst = self.word(self.csp()); self.pop(2)
        self.put(dst, self.cstr(src).encode('latin1') + b'\0')
        self.ret(dst)

    def t_sprintf(self):
        y = self.cpu.y
        s = self.csp()
        buf, fmt = self.word(s + y - 2), self.cstr(self.word(s + y - 4))
        at = s + y - 6
        out = ''
        i = 0
        while i < len(fmt):
            if fmt[i] == '%':
                i += 1
                v = self.word(at); at -= 2
                out += self.cstr(v) if fmt[i] == 's' else str(v)
            else:
                out += fmt[i]
            i += 1
        self.pop(y)
        self.put(buf, out.encode('latin1') + b'\0')
        self.ret(len(out))

    def t_cgetc(self):
        c = self.cpu
        self.snaps.append(dict(sw=dict(c.sw), log=len(c.log),
                               main=bytes(c.m[0x400:0x800]), aux=bytes(c.aux[0x400:0x800])))
        self.ret(self.keys.pop(0) if self.keys else ESC)

    def t_media_key(self):
        self.ret(1 if (self.cpu.a & 127) == ESC else 0)

    def t_media_wait(self):
        raise Halt('media_wait: DGRVIEW reads its keys itself now')

    def t_prompt(self):
        self.pop(4); self.ret(0)

    def t_message(self):
        raise Halt('message called')

    def run(self, entry, limit=3_000_000):
        c = self.cpu
        sentinel = 0xFFF0
        r = sentinel - 1
        c.push(r >> 8); c.push(r & 255)
        c.a, c.x, c.pc = API & 255, API >> 8, entry
        n = 0
        while c.pc != sentinel:
            if c.pc in self.traps:
                self.traps[c.pc]()
                lo = c.pull(); c.pc = ((c.pull() << 8 | lo) + 1) & 0xFFFF
                continue
            op = c.fetch()
            f = c.ops.get(op)
            if f is None:
                raise Halt('illegal opcode %02X at %04X' % (op, (c.pc - 1) & 0xFFFF))
            f()
            n += 1
            if n > limit:
                raise Halt('no return')
        return self

    def note(self):
        return self.cstr(NOTE)


def page(text_lines):
    """A 40-column text page of high-bit ASCII, holes zero (as a BSAVE of a
    freshly cleared screen leaves them): rows padded with blanks."""
    p = bytearray(1024)
    for r in range(24):
        line = text_lines[r] if r < len(text_lines) else ''
        at = ref.row_of(r)
        p[at:at + 40] = bytes((ord(ch) | 0x80) for ch in line.ljust(40)[:40])
    return bytes(p)


SAMPLE40 = page(['', '  A2 FILE CMD - A TEXT SCREEN CAPTURE', '', '  THIS PAGE WAS SAVED FROM $0400 AS A',
                 '  BINARY FILE OF 1024 BYTES.'])


def lores_page(seed=0):
    """A lo-res picture: horizontal bands of solid colours, a few edges."""
    p = bytearray(1024)
    for r in range(24):
        at = ref.row_of(r)
        c = (r // 3 + seed) & 15
        p[at:at + 40] = bytes([c * 17] * 30 + [(c << 4) | ((c + 1) & 15)] * 10)
    return bytes(p)


class Heuristic(unittest.TestCase):
    """The rule on pages made here; the real corpus below."""

    def test_synthetic_pages(self):
        self.assertTrue(ref.looks_text(SAMPLE40))
        self.assertTrue(ref.looks_text(SAMPLE40[:1016]))        # a BSAVE without the last hole
        self.assertTrue(ref.looks_text(SAMPLE40 + SAMPLE40))     # 80 columns
        self.assertFalse(ref.looks_text(lores_page()))
        self.assertFalse(ref.looks_text(lores_page(3) + lores_page(5)))
        self.assertFalse(ref.looks_text(bytes(1024)))            # black
        self.assertFalse(ref.looks_text(bytes([0x55]) * 1024))   # the benches' grey
        self.assertTrue(ref.looks_text(bytes([0xA0]) * 1024))    # a cleared text screen
        inverse = bytes(b & 0x3F for b in SAMPLE40)             # crack screens written in inverse
        self.assertTrue(ref.looks_text(inverse))
        mixed = bytearray(lores_page())                          # a mixed screen: 4 blank text rows
        for r in range(20, 24):
            mixed[ref.row_of(r):ref.row_of(r) + 40] = bytes([0xA0]) * 40
        self.assertFalse(ref.looks_text(bytes(mixed)))
        art = page([';;;;  ;;;;  ;;;;'] * 24)                    # ASCII art of ';' ($BB, solid)
        self.assertTrue(ref.looks_text(art))


FRENCH_TOUCH = Path(os.environ.get('A2FC_FRENCHTOUCH', Path.home() / '.cache/a2fc/frenchtouch/DIX'))


def corpus():
    """(path, is_text) of the private corpus, one per distinct content: the
    text screens and lo-res pictures labelled in ~/.cache/a2fc/textscreen
    (Asimov, 2026-10-04), and French Touch's lo-res and double lo-res halves
    from the DIX sources (~/.cache/a2fc/frenchtouch, GPLv3)."""
    out, seen = [], set()

    def add(p, is_text):
        d = p.read_bytes()
        if 0 < len(d) <= 2048 and d not in seen:
            seen.add(d)
            out.append((p, is_text))
    m = CORPUS / 'manifest.tsv'
    if m.exists():
        with open(m, newline='') as f:
            for row in csv.DictReader(f, delimiter='\t'):
                label = (row.get('your_label') or '').strip()
                path = CORPUS / Path(row['file']).name
                if label in ('text40', 'text80', 'lores', 'dlores') and path.exists():
                    add(path, label.startswith('text'))
    if FRENCH_TOUCH.exists():
        for pat in ('*/Sources/*/*.aux', '*/Sources/*/*.mai', 'MADEF_051019/Sources/LORES/*.bin',
                    'MAD3/Sources/DATA/lores.bin', 'DD2/DGR/1.aux', 'DD2/DGR/1.main'):
            for path in sorted(FRENCH_TOUCH.glob(pat)):
                add(path, False)
    return out


class Corpus(unittest.TestCase):
    """Measured 2026-10-04: 77 distinct text screens, 45 distinct pictures,
    no error (texts >= 33 % blanks, pictures <= 23 %, solid - blank >= 27
    points in every picture). The C (host build of dgrview.c, aux $0400)
    must give the same verdict as the Python rule on every file."""

    def test_measured_error_rates_and_c_agrees(self):
        files = corpus()
        if not files:
            self.skipTest('private corpus absent: ' + str(CORPUS))
        import test_dgrview
        test_dgrview.DgrView.setUpClass()
        self.addCleanup(test_dgrview.DgrView.tearDownClass)
        h = test_dgrview.DgrView('test_too_big_is_refused')
        wrong, disagree = [], []
        for p, is_text in files:
            data = p.read_bytes()
            py = ref.looks_text(data)
            h.view(data, aux=0x0400)
            if h.state['text'] != py:
                disagree.append(p.name)
            if py != is_text:
                wrong.append(p.name)
        texts = sum(1 for _, t in files if t)
        print(f'\n  {texts} text screens, {len(files) - texts} pictures, {len(wrong)} misread')
        self.assertEqual(disagree, [])
        self.assertEqual(wrong, [])


class TernaryAddress(unittest.TestCase):
    """cc65 master (the 6502 edition) compiles
    `*(unsigned char*)(c ? 0xC055 : 0xC054) = 0;` as a store to address
    `c` itself: DGRVIEW's bank() wrote zero page $00/$01 and never switched
    PAGE2 on the 6502 edition (found 2026-10-04 by the Overlay tests below).
    The form is banned from the sources; write an if/else."""

    def test_no_conditional_soft_switch_address(self):
        pat = re.compile(r'\*\s*\(\s*(?:volatile\s+)?unsigned\s+char\s*\*\s*\)\s*\([^;]*\?[^;]*:[^;]*\)\s*=')
        hits = [f'{f.relative_to(ROOT)}:{n}' for f in sorted((ROOT / 'src').rglob('*.[ch]'))
                for n, line in enumerate(f.read_text(errors='replace').splitlines(), 1) if pat.search(line)]
        self.assertEqual(hits, [])


class Overlay(unittest.TestCase):
    """The real .PLG, both editions, in the IIe model."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='textscreen-')
        cls.builds = []
        for i, ed in enumerate(editions()):
            d = Path(cls.tmp.name) / ed[0]
            d.mkdir()
            image, labels, ofs = build(ed, d)
            cls.builds.append((ed[0], image, labels, ofs))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def each(self):
        if not self.builds:
            self.skipTest('no cc65')
        for name, image, labels, ofs in self.builds:
            yield name, (image, labels, ofs, name == '65C02')

    def go(self, b, data, keys=b'', aux=0x0400):
        image, labels, ofs, cmos = b
        entry = image[3] | image[4] << 8
        m = Machine(image, labels, ofs, cmos, data, aux=aux, keys=keys)
        return m.run(entry)

    def assert_only_allowed_writes(self, m, wide):
        """Nothing written outside the page's visible bytes (AUX only when
        wide), the overlay's window, its zero page, the stack page and the
        C stack."""
        bad = []
        for bank, a in m.cpu.log:
            o = a - 0x400
            if 0x400 <= a < 0x800 and o % 128 < 120 and (bank == 0 or wide):
                continue
            if bank == 0 and (0x80 <= a < 0xA0 or 0x100 <= a < 0x200 or a in m.window
                              or CSTACK - 0x100 <= a < CSTACK):
                continue
            bad.append((bank, hex(a)))
        self.assertEqual(bad[:8], [])
        # AUX outside the text page: byte for byte as it was.
        self.assertEqual(m.cpu.aux[:0x400], m.before_aux[:0x400])
        self.assertEqual(m.cpu.aux[0x800:], m.before_aux[0x800:])
        for bank, mem, before in ((0, m.cpu.m, m.before_main), (1, m.cpu.aux, m.before_aux)):
            self.assertEqual([mem[0x400 + o] for o in HOLES], [before[0x400 + o] for o in HOLES],
                             'screen holes written in bank %d' % bank)
        others = sorted({hex(a) for a in m.cpu.io if not (0xC000 <= a <= 0xC00F or 0xC050 <= a <= 0xC05F
                                                         or a == 0xC01E)})
        self.assertEqual(others, [])

    def test_a_40_column_text_screen(self):
        for name, b in self.each():
            with self.subTest(edition=name):
                m = self.go(b, SAMPLE40)
                s = m.snaps[0]['sw']
                self.assertEqual((s['text'], s['col80'], s['altchar'], s['page2']), (1, 0, 0, 0))
                main = m.snaps[0]['main']
                self.assertEqual(bytes(main[o] for o in VISIBLE), bytes(SAMPLE40[o] for o in VISIBLE))
                self.assertIn('Text screen, 40 columns', m.note())
                self.assertEqual(m.cstr(RESEL), 'PIC')
                self.assert_only_allowed_writes(m, wide=False)
                self.assertEqual(m.cpu.aux, m.before_aux)          # 40 columns: no AUX at all
                self.assertEqual(m.cpu.sw['altchar'], m.altchar_at_entry)

    def test_an_80_column_text_screen(self):
        left = page(['EVEN COLUMNS FROM THE AUXILIARY HALF'])
        right = page(['ODD COLUMNS FROM THE MAIN HALF'])
        for name, b in self.each():
            with self.subTest(edition=name):
                m = self.go(b, left + right)
                s = m.snaps[0]['sw']
                self.assertEqual((s['text'], s['col80'], s['altchar']), (1, 1, 1))
                self.assertEqual(bytes(m.snaps[0]['aux'][o] for o in VISIBLE), bytes(left[o] for o in VISIBLE))
                self.assertEqual(bytes(m.snaps[0]['main'][o] for o in VISIBLE), bytes(right[o] for o in VISIBLE))
                self.assertIn('80 columns', m.note())
                self.assert_only_allowed_writes(m, wide=True)

    def test_t_and_a_switch_without_writing(self):
        for name, b in self.each():
            with self.subTest(edition=name):
                m = self.go(b, SAMPLE40, keys=b'AtTa')
                sw = [(x['sw']['text'], x['sw']['altchar']) for x in m.snaps]
                self.assertEqual(sw, [(1, 0), (1, 1), (0, 1), (1, 1), (1, 0)])
                # Not a byte of either bank written after the first draw.
                after = m.cpu.log[m.snaps[0]['log']:]
                self.assertEqual([w for w in after if 0x400 <= w[1] < 0x800], [])
                self.assertEqual({x['main'] for x in m.snaps}, {m.snaps[0]['main']})
                self.assertIn('Text screen', m.note())
                self.assertEqual(m.cpu.sw['altchar'], m.altchar_at_entry)

    def test_a_lores_picture_stays_a_picture_until_t(self):
        pic = lores_page()
        for name, b in self.each():
            with self.subTest(edition=name):
                m = self.go(b, pic, keys=b'aT')
                sw = [x['sw']['text'] for x in m.snaps]
                self.assertEqual(sw, [0, 0, 1])                   # A means nothing in lo-res
                self.assertEqual(bytes(m.snaps[0]['main'][o] for o in VISIBLE), bytes(pic[o] for o in VISIBLE))
                self.assertIn('Text screen', m.note())            # left on text by T
                self.assert_only_allowed_writes(m, wide=False)

    def test_the_panels_character_set_comes_back(self):
        for name, b in self.each():
            for start in (0, 1):
                with self.subTest(edition=name, altchar=start):
                    image, labels, ofs, cmos = b
                    m = Machine(image, labels, ofs, cmos, SAMPLE40 + SAMPLE40, keys=b'a')
                    m.cpu.sw['altchar'] = start
                    m.run(image[3] | image[4] << 8)
                    self.assertEqual(m.cpu.sw['altchar'], start)

    def test_a_header_picture_ignores_t(self):
        hdr = b'DGR\x01\x28\x30\x00\x00' + bytes([0xA0]) * 960   # blanks, but it SAYS lo-res
        for name, b in self.each():
            with self.subTest(edition=name):
                m = self.go(b, hdr, keys=b'TA', aux=0)
                self.assertEqual([x['sw']['text'] for x in m.snaps], [0, 0, 0])
                self.assertIn('Lo-res screen, 40 x 48', m.note())


if __name__ == '__main__':
    unittest.main()
