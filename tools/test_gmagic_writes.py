"""GMAGIC as shipped (the 6502 edition's GMAGIC.PLG, linked here as the
Makefile links it) in a 6502 interpreter that records every address the
program writes (tools/mos6502.py).

The overlay is loaded at $1B00 as the core loads it and entered with a
service table whose functions are traps answered in Python (fopen, fread,
fseek, fclose, strcpy, the core's cgetc and media_key). The checks: every
write lands in hi-res page 1, the 112-byte heads of the main text page's
128-byte blocks (the font and the row patterns), the overlay's own $0C00
part and BSS, the five operands it patches in its own code, the C and
hardware stacks, the zero page cc65 uses, the buffers the table lends it
(copy_buf, note, reselect), or the display soft switches -- never the
auxiliary memory switches, page 2-3, the ProDOS buffer $0800-$0BFF, the
resident or anything else. The pages it shows are compared with
tools/gmagic_ref.py, among them the pictures that write to rows 192-206
and columns 40-41 (brushes and text at the edges, a V84 fill below row
191), where a slip would write outside the page.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import gmagic_ref as ref  # noqa: E402
import mos6502  # noqa: E402

HEAD = Path(os.environ.get('CC65_HEAD', Path.home() / 'opt/cc65-head'))

API, SEL, FULL, NOTE, RESEL, CBUF, FILE = 0x1000, 0x1080, 0x10A0, 0x1100, 0x1160, 0x1200, 0x1400
TRAPS = 0xF800
STACK = 0xBF00                           # the C stack grows down from here
SENTINEL = 0xFFF0
DISPLAY = {0xC000, 0xC002, 0xC004, 0xC00C, 0xC00D, 0xC050, 0xC052, 0xC054, 0xC057, 0xC05E, 0xC05F}
OFFS = dict(full=6, copy_buf=12, fopen=46, fread=48, fclose=52, fseek=54, cgetc=74, strcpy=80,
            reselect=90, note=92, selected=94, media_key=100)


def link():
    """GMAGIC.PLG for the 6502 edition (cc65 master, apple2), or with the
    cc65 on the PATH when cc65 master is not installed; and its map."""
    d = Path(tempfile.mkdtemp(prefix='a2fc-gmagic-w-'))
    if (HEAD / 'bin/cc65').exists():
        bin_, env = str(HEAD / 'bin') + '/', dict(os.environ, CC65_HOME=str(HEAD / 'share/cc65'))
        lib = HEAD / 'share/cc65/lib/apple2.lib'
    else:
        bin_, env = '', dict(os.environ)
        lib = Path(shutil.which('cc65')).resolve().parents[1] / 'share/cc65/lib/apple2.lib'
    shutil.copyfile(ROOT / 'src/plugins/gmagic.c', d / 'gm_hdr.c')
    for name in ('gmagic.s', 'gmagic_tables.inc', 'gmagic_text.inc'):
        shutil.copyfile(ROOT / 'src/plugins' / name, d / name)
    run = lambda *a: subprocess.run(list(a), check=True, cwd=d, env=env, capture_output=True)
    run(bin_ + 'cc65', '-t', 'apple2', '-I', str(ROOT / 'src/plugins'), '-O', '-Oirs', '-Cl',
        '--codesize', '100', '-o', 'gm_hdr.s', 'gm_hdr.c')
    run(bin_ + 'ca65', '-t', 'apple2', '-o', 'gm_hdr.o', 'gm_hdr.s')
    run(bin_ + 'ca65', '-t', 'apple2', '-o', 'gmagic.o', 'gmagic.s')
    run(bin_ + 'ld65', '-C', str(ROOT / 'sdk/gmagic.cfg'), '-m', 'gm.map', '-o', 'GMAGIC.PLG',
        'gm_hdr.o', 'gmagic.o', str(lib))
    plg, mp = (d / 'GMAGIC.PLG').read_bytes(), (d / 'gm.map').read_text()
    shutil.rmtree(d)
    return plg, mp


class Machine:
    def __init__(self, plg, mp, data, keys, typ=6):
        self.m = bytearray(65536)
        self.m[0xC000:0xC100] = b'\xFF' * 256
        self.m[0x1B00:0x1B00 + len(plg)] = plg
        self.data, self.keys, self.pages, self.pos, self.open = data, list(keys), [], 0, False
        self.sp = int(re.search(r'^(?:c_)?sp\s+0000([0-9A-F]{2})', mp, re.M)[1], 16)
        segs = {n: (int(s, 16), int(e, 16)) for n, s, e in
                re.findall(r'^(\w+)\s+00([0-9A-F]{4})\s+00([0-9A-F]{4})\s+[0-9A-F]{6}', mp, re.M)}
        self.segs = segs
        w = lambda a, v: self.m.__setitem__(slice(a, a + 2), bytes([v & 255, v >> 8]))
        names = ['fopen', 'fread', 'fseek', 'fclose', 'cgetc', 'strcpy', 'media_key']
        self.traps = {}
        for i, n in enumerate(names):
            w(API + OFFS[n], TRAPS + 2 * i)
            self.traps[TRAPS + 2 * i] = getattr(self, 't_' + n)
        for n, a in (('full', FULL), ('copy_buf', CBUF), ('reselect', RESEL), ('note', NOTE),
                     ('selected', SEL)):
            w(API + OFFS[n], a)
        self.m[SEL:SEL + 8] = b'PICTURE\0'
        self.m[SEL + 17] = typ
        self.m[FULL:FULL + 9] = b'/VOL/PIC\0'
        self.m[NOTE:NOTE + 80] = b'\x77' * 80
        w(self.sp, STACK)
        self.cpu = mos6502.CPU(self.m)
        # The operands the overlay patches: lda $FFFF,y and lda $FFFF,x in CODE.
        self.patched = set()
        lo, hi = segs['CODE']
        for a in range(lo, hi - 1):
            if plg[a - 0x1B00] in (0xB9, 0xBD) and plg[a - 0x1AFF:a - 0x1AFD] == b'\xFF\xFF':
                self.patched |= {a + 1, a + 2}

    # -- the C calling convention: arguments on the C stack, the last in A/X
    def csp(self):
        return self.m[self.sp] | self.m[self.sp + 1] << 8

    def pop(self, n):
        a = self.csp()
        v = [self.m[a + i] for i in range(n)]
        self.m[self.sp] = (a + n) & 255
        self.m[self.sp + 1] = (a + n) >> 8
        return v

    def ax(self):
        return self.cpu.a | self.cpu.x << 8

    def ret(self, v):
        self.cpu.a, self.cpu.x = v & 255, (v >> 8) & 255

    def t_fopen(self):
        mode = self.ax()
        p = self.pop(2)
        assert bytes(self.m[mode:mode + 3]) == b'rb\0' and not self.open
        assert p[0] | p[1] << 8 == FULL
        self.open, self.pos = True, 0
        self.m[FILE:FILE + 3] = b'\0\0\0'
        self.ret(FILE)

    def t_fread(self):
        assert self.ax() == FILE and self.open
        v = self.pop(6)
        n, size, a = v[0] | v[1] << 8, v[2] | v[3] << 8, v[4] | v[5] << 8
        got = self.data[self.pos:self.pos + n]
        assert size == 1 and a == NOTE and n <= 80
        for i, v in enumerate(got):
            self.cpu.wr(a + i, v)
        self.pos += len(got)
        self.ret(len(got))

    def t_fseek(self):
        assert self.ax() == 2                     # SEEK_SET
        v = self.pop(6)
        assert v[4] | v[5] << 8 == FILE
        self.pos = v[0] | v[1] << 8 | v[2] << 16 | v[3] << 24
        self.ret(0)

    def t_fclose(self):
        assert self.ax() == FILE and self.open
        self.open = False
        self.ret(0)

    def t_strcpy(self):
        src = self.ax()
        d = self.pop(2)
        dst = d[0] | d[1] << 8
        i = 0
        while True:
            self.cpu.wr(dst + i, self.m[src + i])
            if not self.m[src + i]:
                break
            i += 1
        self.ret(dst)

    def t_cgetc(self):
        self.pages.append(bytes(self.m[0x2000:0x4000]))
        self.ret(ord(self.keys.pop(0)) if self.keys else 27)

    def t_media_key(self):
        k = self.cpu.a & 127
        self.ret(1 if k in (27, 8, 21) else 0)

    def run(self, limit=60_000_000):
        cpu = self.cpu
        entry = self.m[0x1B03] | self.m[0x1B04] << 8
        r = (SENTINEL - 1) & 0xFFFF
        cpu.push(r >> 8)
        cpu.push(r & 255)
        cpu.a, cpu.x, cpu.pc = API & 255, API >> 8, entry
        s0 = cpu.s
        ops, n = cpu.ops, 0
        while cpu.pc != SENTINEL:
            t = self.traps.get(cpu.pc)
            if t:
                t()
                lo = cpu.pull()
                cpu.pc = ((cpu.pull() << 8 | lo) + 1) & 0xFFFF
                continue
            op = cpu.fetch()
            ops[op]()
            n += 1
            assert n < limit, 'no return'
        assert cpu.s == s0 + 2 and self.csp() == STACK, 'both stacks balanced'
        self.note = bytes(self.m[NOTE:NOTE + 80]).split(b'\0')[0].decode('latin-1')
        self.steps = n
        return self

    def allowed(self, a):
        s = self.segs
        if 0x2000 <= a < 0x4000 or 0x0C00 <= a < 0x1000 or 0x0100 <= a < 0x0200:
            return True
        if 0x0400 <= a < 0x0800:
            return (a & 0x7F) < 112
        if 0x80 <= a < 0x9A or STACK - 0x100 <= a < STACK or a in DISPLAY:
            return True
        if NOTE <= a < NOTE + 80 or RESEL <= a < RESEL + 17 or CBUF <= a < CBUF + 512:
            return True
        if s['DATA'][0] <= a <= s['DATA'][1]:      # jmpvec
            return True
        return a in self.patched

    def bad_writes(self):
        return sorted(a for a in self.cpu.writes if not self.allowed(a))


class Writes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plg, cls.mp = link()

    def go(self, data, keys='', typ=6):
        m = Machine(self.plg, self.mp, data, keys, typ).run()
        bad = m.bad_writes()
        self.assertEqual(len(m.patched), 10, 'five patched operands')
        self.assertEqual([hex(a) for a in bad], [], 'writes outside the overlay\'s areas')
        for sw in (0xC001, 0xC003, 0xC005, 0xC008, 0xC009, 0xC055):
            self.assertNotIn(sw, m.cpu.writes, 'soft switch $%04X' % sw)
        return m

    def test_edges_rows_below_the_screen_and_v84(self):
        hm = ref.hand_made()
        for name, keys, views in (('H05-brushes-and-edges', 'D', [(ref.V82, 0, 0), (ref.V84, 0, 0)]),
                                  ('H09-fill-at-row-191-non-white', 'D', [(ref.V82, 0, 0), (ref.V84, 0, 0)]),
                                  ('H06-fills-on-row-0', 'D', [(ref.V82, 0, 0), (ref.V84, 0, 0)])):
            data = hm[name]
            m = self.go(data, keys)
            self.assertEqual(m.pages, [ref.view(data, d, b, l, recognise=False) for d, b, l in views], name)
            self.assertEqual(m.note, '')

    def test_overlays_and_groups(self):
        c = ref.corpus()
        o = c['O01-picture-plus-overlay']
        m = self.go(o, 'OD')
        self.assertEqual(m.pages, [ref.view(o, ref.V82, 0, 0), ref.view(o, ref.V82, 0, 1),
                                   ref.view(o, ref.V84, 0, 1)])
        g = c['G01-group-of-3']
        m = self.go(g, 'NNN')
        self.assertEqual(m.pages, [ref.view(g, ref.V82, i % 3, i % 3) for i in range(4)])

    def test_text_at_the_edges(self):
        P = ref.P
        b = bytearray(b'\x24\x60\x50')
        b += P(0x10, 250, 60) + b'\x50W\x50X\x50Y\x50Z\x50W'
        b += P(0x10, 271, 186) + b'\x30A\x30B\x50g'
        b += P(0x10, 279, 191) + b'\x50M\x30_'
        b += P(0x10, 0, 0) + bytes(x for ch in range(0x20, 0x80) for x in (0x50, ch))
        b += b'\x47' + P(0xC0, 279, 191)
        data = bytes(b + b'\x00')
        m = self.go(data, 'D')
        self.assertEqual(m.pages, [ref.render(data, ref.V84)] * 2)

    def test_appendix_b_pictures_it_recognises(self):
        """Every Appendix B picture the shipped overlay recognises, in both
        dialects, against the spec's SHA-256 -- the binary as shipped."""
        import hashlib
        exp = ref.expected()
        n = 0
        for name, data in ref.corpus().items():
            e = exp[name]
            if 'V82' not in e:
                continue
            try:
                ref.parts(data)
            except ref.Malformed:
                continue
            o = name.startswith('O01')                   # its page: the overlay drawn over
            m = self.go(data, 'OD' if o else 'D')
            self.assertEqual([hashlib.sha256(p).hexdigest() for p in m.pages[o:]], [e['V82'], e['V84']], name)
            n += 1
        self.assertGreater(n, 40)

    def test_refusals_write_nothing_but_the_note(self):
        for data, typ in ((b'\x24\x28\x00', 6), (b'\x24' + ref.P(0x80, 280, 1) + b'\x00', 6),
                          (b'\x24\x80\x00', 6), (ref.hand_made()['H02-colour-at-line-start'], 4)):
            m = self.go(data, typ=typ)
            self.assertEqual(m.pages, [])
            page = {a for a in m.cpu.writes if 0x0400 <= a < 0x0800 or 0x2000 <= a < 0x4000}
            self.assertEqual(page, set(), 'no screen byte')
            self.assertTrue(m.note.startswith('Not a whole Graphics Magician'))


if __name__ == '__main__':
    unittest.main()
