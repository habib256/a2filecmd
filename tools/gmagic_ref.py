#!/usr/bin/env python3
"""Graphics Magician pictures (Penguin Software, 1982-1984): reference.

Written from docs/GRAPHICS-MAGICIAN-FORMAT.md alone (a clean-room reading:
no Penguin program, disk or disassembly was used). A picture is the list of
drawing commands of PICEDIT -- lines, flood fills with 108 patterns, brush
stamps and (1984) text -- replayed on hi-res page 1. This module is the
oracle of src/plugins/gmagic.s:

    gmagic_ref.py --selftest          every Appendix B hash, both dialects
    gmagic_ref.py FILE [V82|V84] OUT  the page of FILE's first picture
    gmagic_ref.py --corpus DIR        writes Appendix B's pictures there
    gmagic_ref.py --includes          rewrites src/plugins/gmagic_*.inc

Text is drawn with A2FC's substitute font (BOLD.SET of the DEMO folder:
CiderPress II's STANDARD test font, each dot doubled to its right), not
Penguin's: pictures with text are not byte-identical to the original.
"""
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

V82, V84 = 'V82', 'V84'

# Appendix A.1: the 27 row patterns, bytes for byte columns c mod 4 = 0..3.
ROWS = [bytes.fromhex(s) for s in '''
7F7F7F7F FFFFFFFF 776E5D3B 6E5D3B77 BBF7EEDD 3B776E5D F7EEDDBB 33664C19
CC99B3E6 00000000 EEDDBBF7 80808080 AAD5AAD5 A2C48891 2A552A55 8891A2C4
22440811 B3E6CC99 D5AAD5AA 08112244 DDBBF7EE 91A2C488 552A552A 11224408
C48891A2 5D3B776E 44081122'''.split()]
assert len(ROWS) == 27

# Appendix A.2: pattern n -> (row pattern of even rows, of odd rows).
PATTERNS = [tuple(int(v) for v in e.split(':')[1].split('/')) for e in '''
0:00/01 1:02/01 2:03/04 3:05/06 4:07/08 5:09/10 6:09/11 7:00/10 8:00/12
9:03/12 10:09/12 11:09/13 12:14/12 13:05/15 14:16/15 15:16/01 16:14/10
17:14/01 18:14/06 19:14/17 20:03/11 21:16/11 22:14/18 23:19/06 24:03/01
25:00/06 26:02/20 27:00/18 28:00/21 29:03/21 30:03/18 31:16/18 32:09/21
33:09/06 34:07/18 35:02/18 36:22/18 37:02/08 38:22/01 39:22/06 40:22/17
41:22/11 42:02/11 43:23/24 44:22/10 45:22/13 46:23/06 47:23/11 48:02/15
49:22/12 50:02/12 51:23/13 52:01/01 53:11/11 54:01/10 55:10/04 56:01/13
57:12/01 58:06/12 59:12/10 60:12/12 61:11/12 62:13/15 63:11/13 64:06/01
65:06/08 66:06/20 67:18/01 68:06/18 69:01/21 70:18/18 71:18/21 72:21/24
73:11/21 74:06/11 75:18/10 76:18/12 77:00/00 78:02/00 79:00/23 80:09/09
81:07/03 82:14/02 83:03/05 84:00/16 85:14/00 86:14/03 87:14/14 88:19/05
89:09/03 90:19/03 91:16/19 92:09/16 93:00/03 94:02/03 95:02/19 96:22/14
97:02/25 98:22/00 99:22/03 100:22/02 101:22/22 102:22/09 103:02/09
104:02/23 105:02/26 106:23/26 107:09/23'''.split()]
assert len(PATTERNS) == 108

# Appendix A.3: the eight brushes, 16 rows of 14 pixels, '#' drawn.
BRUSH_ART = '''
..............|..............|..............|..............|..............|..............|..............|.......#......|..............|..............|..............|..............|..............|..............|..............|..............
..............|..............|..............|..............|..............|..............|..............|......##......|......##......|..............|..............|..............|..............|..............|..............|..............
..............|..............|..............|..............|..............|..............|......##......|.....####.....|.....####.....|......##......|..............|..............|..............|..............|..............|..............
..............|..............|..............|..............|..............|.....####.....|....######....|....######....|....######....|....######....|.....####.....|..............|..............|..............|..............|..............
..............|..............|..............|.....####.....|...########...|...########...|..##########..|..##########..|..##########..|..##########..|...########...|...########...|.....####.....|..............|..............|..............
..............|.....####.....|..##########..|.############.|.############.|.############.|##############|##############|##############|##############|.############.|.############.|.############.|..##########..|.....####.....|..............
..............|..............|..............|..............|......#.......|...#.....#....|.....#........|.......#..#...|...#.#........|.......#.#....|....#.........|.......#......|..............|..............|..............|..............
..............|.....#...#....|...#...#......|..#..#...#.#..|......#.......|.#..#..##.#.#.|...#.####.....|.....#####..#.|.#...#####.#..|...#..##..#...|.#...#..#...#.|...#.#.#.#.#..|..............|....#...#.#...|......#.......|..............
'''.split()


def brush_quarters(b):
    """Brush b as four 8-byte bitmaps: top-left, top-right, bottom-left,
    bottom-right; pixel j of a row in bit j (section 16)."""
    rows = BRUSH_ART[b].split('|')
    assert len(rows) == 16 and all(len(r) == 14 for r in rows)
    def bits(s):
        return sum(1 << j for j, ch in enumerate(s) if ch == '#')
    q = []
    for top in (0, 8):
        for left in (0, 7):
            q.append(bytes(bits(rows[top + r][left:left + 7]) for r in range(8)))
    return q


BRUSHES = [brush_quarters(b) for b in range(8)]
assert [sum(bin(v).count('1') for qq in q for v in qq) for q in BRUSHES] == [1, 4, 12, 32, 80, 156, 12, 50]

COLOURS = [0x00, 0x2A, 0x55, 0x7F, 0x80, 0xAA, 0xD5, 0xFF]


def font():
    """96 glyphs ($20-$7F) of 8 rows, bit 0 the leftmost dot: BOLD.SET,
    the hi-res character set A2FC's DEMO folder carries (tools/
    mkdemo_viewers.py hrcg_font): CiderPress II's STANDARD, bolded."""
    std = (ROOT / 'data/CP2/GRAPHICS/STANDARD#070000').read_bytes()[0x20 * 8:0x80 * 8]
    return bytes((b | (b << 1)) & 0x7F for b in std)


def row_address(y):
    """Offset in page 1 of hi-res row y, or None outside the page: rows
    192-255 as PICDRAWF and PICDRAWH address them (section 11)."""
    if y < 192:
        return (y & 7) * 1024 + ((y >> 3) & 7) * 128 + (y >> 6) * 40
    k = y - 192
    if k & 8:
        return None                     # $A0xx: outside the screen
    return 0x20 + 4 * (k & 7) + ((k >> 4) & 3)


class Malformed(ValueError):
    pass


def parse(data, at=0, recognise=True):
    """The commands of the picture starting at data[at], checked strictly
    (sections 3 and 11): (commands, end offset, uses V84 commands).
    Raises Malformed otherwise. recognise=False drops rules 2, 4 and 5 of
    section 3 (the first command, a line start among the lines, something
    drawn): the drawing tests of Appendix B include an empty picture."""
    cmds = []
    v84 = False
    lines = starts = draws = 0
    i = at
    n = len(data)
    if recognise and (i >= n or (data[i] >> 4) not in (2, 4, 6, 8, 0xA)):
        raise Malformed('first command')
    while True:
        if i >= n:
            raise Malformed('no end byte')
        b = data[i]
        t, a = b >> 4, b & 15
        if b == 0:
            break
        if t in (2, 4):
            if a > 7:
                raise Malformed('colour or brush')
            cmds.append((b,))
            i += 1
        elif t in (3, 5, 6):
            if a or i + 1 >= n:
                raise Malformed('argument nibble or truncated')
            v = data[i + 1]
            if t == 6 and v > 107:
                raise Malformed('pattern')
            if t != 6 and not 0x20 <= v <= 0x7F:
                raise Malformed('character')
            if t != 6:
                v84 = True
            cmds.append((b, v))
            i += 2
        elif t in (1, 8, 0xA, 0xC, 0xE):
            if a > 1 or i + 2 >= n:
                raise Malformed('X high part or truncated')
            x = a << 8 | data[i + 1]
            y = data[i + 2]
            if x > 279 or y > 191:
                raise Malformed('coordinates')
            if t == 1:
                v84 = True
            if t == 8:
                starts += 1
            if t in (8, 0xA):
                lines += 1
            if t in (0xA, 0xC, 0xE):
                draws += 1
            cmds.append((b, x, y))
            i += 3
        else:
            raise Malformed('unknown command')
    if recognise and lines and not starts:
        raise Malformed('lines without a line start')
    if recognise and not draws:
        raise Malformed('draws nothing (no line, brush or fill)')
    return cmds, i + 1, v84


def parts(data, recognise=True):
    """The pictures of a file (section 17.5): the first must parse, the
    following ones are kept while they parse. [(commands, offset, v84)]."""
    out = []
    at = 0
    while at < len(data):
        try:
            cmds, end, v84 = parse(data, at, recognise)
        except Malformed:
            if not out:
                raise
            break
        out.append((cmds, at, v84))
        at = end
    if not out:
        raise Malformed('empty file')
    return out


def dialect_of(data):
    """V84 when any picture of the file uses $1x, $3x or $5x; else V82."""
    return V84 if any(v for _, _, v in parts(data)) else V82


class Page:
    def __init__(self, page=None):
        self.m = bytearray(b'\xFF' * 8192) if page is None else bytearray(page)

    def rd(self, y, c):
        """The byte of row y, column c (0-41), or 0 outside the page: a
        read outside is a non-white pixel (section 11)."""
        o = row_address(y)
        if o is None or not 0 <= o + c < 8192:
            return 0
        return self.m[o + c]

    def wr(self, y, c, v):
        o = row_address(y)
        if o is None or not 0 <= o + c < 8192:
            return
        self.m[o + c] = v & 255


def white(byte, p):
    """A pixel is white when its bit and its left neighbour's are set; at
    offset 0, bits 0 and 1 (sections 9, 10)."""
    if p == 0:
        return byte & 3 == 3
    return (byte >> (p - 1)) & 3 == 3


class Renderer:
    def __init__(self, dialect, page=None, fnt=None):
        self.d = dialect
        self.p = Page(page)
        self.font = font() if fnt is None else fnt

    def pat(self, y, c):
        e, o = PATTERNS[self.pattern]
        return ROWS[o if y & 1 else e][c & 3]

    # -- lines (section 6) ---------------------------------------------------
    def shift(self, cb, col):
        return cb ^ 0x7F if (col & 1) and (cb & 0x7F) in (0x2A, 0x55) else cb

    def line_start(self, x, y):
        self.px, self.py = x, y
        self.col = x // 7
        self.m = 0x80 | 1 << (x % 7)
        self.cb = self.shift(self.colour, self.col)

    def plot(self):
        old = self.p.rd(self.py, self.col)
        self.p.wr(self.py, self.col, (old & ~self.m) | (self.cb & self.m))

    def line_to(self, x1, y1):
        dx, dy = x1 - self.px, y1 - self.py
        A, B = abs(dx), abs(dy)
        e = A - B
        self.plot()
        for _ in range(A + B):
            if e >= 0:
                pix = self.m & 0x7F
                if dx > 0:
                    if pix == 0x40:
                        self.m = 0x81
                        self.col += 1
                        self.cb ^= 0x7F if (self.cb & 0x7F) in (0x2A, 0x55) else 0
                    else:
                        self.m = 0x80 | pix << 1
                else:
                    if pix == 0x01:
                        self.m = 0xC0
                        self.col -= 1
                        self.cb ^= 0x7F if (self.cb & 0x7F) in (0x2A, 0x55) else 0
                    else:
                        self.m = 0x80 | pix >> 1
                e -= B
            else:
                self.py += 1 if dy > 0 else -1
                e += A
            self.plot()
        self.px, self.py = x1, y1

    # -- bitmaps (section 8) -------------------------------------------------
    def stamp(self, bitmap, c, p, y, xor=False):
        for r in range(8):
            v = (bitmap[r] & 0x7F) << p
            for cc, k in ((c, v & 0x7F), (c + 1, v >> 7)):
                if not k:
                    continue
                old = self.p.rd(y + r, cc)
                if xor:
                    new = old ^ k
                else:
                    new = (old & ~k & 0x7F) | ((k | 0x80) & self.pat(y + r, cc))
                self.p.wr(y + r, cc, new)

    def brush(self, x, y):
        c, p = divmod(x, 7)
        q = BRUSHES[self.brushno]
        self.stamp(q[0], c, p, y)
        self.stamp(q[1], c + 1, p, y)
        self.stamp(q[2], c, p, y + 8)
        self.stamp(q[3], c + 1, p, y + 8)

    def text(self, ch, xor):
        c, p = divmod(self.tx, 7)
        if c <= 40:                     # past the right edge: not drawn
            g = self.font[(ch - 0x20) * 8:(ch - 0x20) * 8 + 8]
            self.stamp(g, c, p, self.ty, xor)
        self.tx += 8

    # -- fills ---------------------------------------------------------------
    def fill_row_v84(self, y, c, p):
        s = self.p.rd(y, c)
        P = self.pat
        L = R = None
        for b in range(p, -1, -1):
            if not s >> b & 1:
                L = b
                break
        for b in range(p, 7):
            if not s >> b & 1:
                R = b
                break
        lo = 0 if L is None else L + 1
        hi = 6 if R is None else R - 1
        mask = 0x80 | sum(1 << b for b in range(lo, hi + 1))
        self.p.wr(y, c, (s & ~mask) | (P(y, c) & mask))
        if L is None:
            cc = c - 1
            while True:
                if cc < 0:
                    lc, L = 0, 0
                    break
                b = self.p.rd(y, cc)
                if b & 0x7F == 0x7F:
                    self.p.wr(y, cc, P(y, cc))
                    cc -= 1
                    continue
                L = max(i for i in range(7) if not b >> i & 1)
                mask = 0x80 | sum(1 << i for i in range(L + 1, 7))
                self.p.wr(y, cc, (b & ~mask) | (P(y, cc) & mask))
                lc = cc
                break
        else:
            lc = c
        if R is None:
            cc = c + 1
            while True:
                if cc > 39:
                    rc, R = 39, 6
                    break
                b = self.p.rd(y, cc)
                if b & 0x7F == 0x7F:
                    self.p.wr(y, cc, P(y, cc))
                    cc += 1
                    continue
                R = min(i for i in range(7) if not b >> i & 1)
                mask = 0x80 | sum(1 << i for i in range(R))
                self.p.wr(y, cc, (b & ~mask) | (P(y, cc) & mask))
                rc = cc
                break
        else:
            rc = c
        return divmod((7 * (lc + rc) + L + R) // 2, 7)

    def fill_v84(self, x, y):
        c, p = divmod(x, 7)
        while True:
            if white(self.p.rd(y, c), p):
                if y == 0:
                    break
                y -= 1
            else:
                y += 1
                break
        while True:
            c, p = self.fill_row_v84(y, c, p)
            y += 1
            if y == 192 or not white(self.p.rd(y, c), p):
                return

    def fill_v82(self, x, y):
        c, p = divmod(x, 7)
        if y == 0:
            y = p
        else:
            while y > 0 and white(self.p.rd(y - 1, c), p):
                y -= 1
        P = self.pat
        while True:
            if y >= 192 or not white(self.p.rd(y, c), p):
                return
            s = self.p.rd(y, c)
            lb = next((b for b in range(p - 1, -1, -1) if not s >> b & 1), None)
            rb = next((b for b in range(p + 1, 7) if not s >> b & 1), None)
            lo = 0 if lb is None else lb + 1
            hi = 6 if rb is None else rb - 1
            mask = sum(1 << b for b in range(lo, hi + 1))
            self.p.wr(y, c, (s & ~mask & 0x7F) | (P(y, c) & (mask | 0x80)))
            Rc = 0 if rb is None else 7 - rb
            Ls = lo
            rc = lc = c
            if rb is None:
                cc = c + 1
                rc = c
                while cc <= 39:
                    rc = cc
                    b = self.p.rd(y, cc)
                    if b & 0x7F == 0x7F:
                        self.p.wr(y, cc, P(y, cc))
                        cc += 1
                        continue
                    i = min(j for j in range(7) if not b >> j & 1)
                    mask = sum(1 << j for j in range(i))
                    self.p.wr(y, cc, (b & ~mask & 0x7F) | (P(y, cc) & (mask | 0x80)))
                    Rc = 7 - i
                    break
                if cc > 39:
                    rc = 39
            if lb is None:
                cc = c - 1
                lc = c
                while cc >= 0:
                    lc = cc
                    b = self.p.rd(y, cc)
                    if b & 0x7F == 0x7F:
                        self.p.wr(y, cc, P(y, cc))
                        cc -= 1
                        continue
                    i = max(j for j in range(7) if not b >> j & 1)
                    mask = sum(1 << j for j in range(i + 1, 7))
                    self.p.wr(y, cc, (b & ~mask & 0x7F) | (P(y, cc) & (mask | 0x80)))
                    Ls = i
                    break
                if cc < 0:
                    lc = 0
            w = rc - lc - 1
            A = 7 if w < 0 else (7 * w + 14) % 256
            borrow = 1 if A < Rc else 0
            half = ((A - Rc - Ls - borrow) % 256) // 2
            xn = 7 * lc + Ls + half
            c, p = divmod(xn, 7)
            y += 1

    # -- the picture ---------------------------------------------------------
    def draw(self, cmds):
        self.colour = 0x80
        self.line_start(140, 6)
        self.pattern = 0
        self.brushno = 5
        self.tx = self.ty = 0
        for cmd in cmds:
            b = cmd[0]
            t, a = b >> 4, b & 15
            if t == 2:
                self.colour = COLOURS[a]
            elif t == 4:
                self.brushno = a
            elif t == 6:
                self.pattern = cmd[1]
            elif t == 8:
                self.line_start(cmd[1], cmd[2])
            elif t == 0xA:
                self.line_to(cmd[1], cmd[2])
            elif t == 0xC:
                self.brush(cmd[1], cmd[2])
            elif t == 0xE:
                (self.fill_v84 if self.d == V84 else self.fill_v82)(cmd[1], cmd[2])
            elif t == 1:
                self.tx, self.ty = cmd[1], cmd[2]
            elif t in (3, 5):
                self.text(cmd[1], t == 3)
        return self.p.m


def render(data, dialect, index=0, page=None, recognise=True):
    """The page after drawing picture `index` of data on `page` (None: a
    page cleared to $FF)."""
    cmds = parts(data, recognise)[index][0]
    return bytes(Renderer(dialect, page).draw(cmds))


def view(data, dialect, base, last, recognise=True):
    """What the viewer shows: a cleared page, picture `base`, then the
    following ones up to `last` drawn over it (overlays)."""
    ps = parts(data, recognise)
    page = None
    for i in range(base, last + 1):
        page = bytes(Renderer(dialect, page).draw(ps[i][0]))
    return page


# -- Appendix B -------------------------------------------------------------
def P(c, x, y):
    return bytes([c | (x >> 8), x & 0xFF, y])


class Lcg:
    def __init__(self, seed):
        self.s = seed

    def rnd(self, n):
        self.s = (self.s * 1103515245 + 12345) % (1 << 31)
        return (self.s >> 16) % n


EX = [0, 1, 2, 5, 6, 7, 8, 13, 14, 265, 266, 270, 272, 273, 276, 278, 279]
EY = [0, 1, 2, 175, 176, 177, 183, 184, 190, 191]


def random_picture(k):
    g = Lcg(1000 + k)

    def point(edge):
        if edge and g.rnd(2) == 0:
            x = EX[g.rnd(17)]
            return x, EY[g.rnd(10)]
        x = g.rnd(280)
        return x, g.rnd(192)

    out = bytearray()
    for _ in range((10, 40, 120)[k % 3]):
        r = g.rnd(100)
        if r < 8:
            out.append(0x20 + g.rnd(8))
        elif r < 12:
            out.append(0x40 + g.rnd(8))
        elif r < 18:
            out += bytes([0x60, g.rnd(108)])
        elif r < 30:
            out += P(0x80, *point(False))
        elif r < 55:
            out += P(0xA0, *point(False))
        elif r < 70:
            out += P(0xC0, *point(True))
        else:
            out += P(0xE0, *point(True))
    return bytes(out + b'\x00')


def hand_made():
    t = {}
    t['H01-empty'] = b'\x00'
    t['H02-colour-at-line-start'] = bytes.fromhex('2280000AA1170A25A0001480001EA1171E00')
    h = bytearray()
    for c in range(8):
        h += bytes([0x20 + c]) + P(0x80, 0, 40 + 12 * c) + P(0xA0, 279, 46 + 12 * c) + P(0xA0, 3, 52 + 12 * c)
    t['H03-all-colours-diagonals'] = bytes(h + b'\x00')
    h = bytearray(b'\x24')
    for k in range(13):
        h += P(0x80, 23 * k, 0) + P(0xA0, 23 * k, 189)
    for k in range(10):
        h += P(0x80, 0, 21 * k) + P(0xA0, 276, 21 * k)
    for i in range(108):
        h += bytes([0x60, i]) + P(0xE0, 23 * (i % 12) + 11, 21 * (i // 12) + 10)
    t['H04-palette-108-cells'] = bytes(h + b'\x00')
    h = bytearray(b'\x60\x50')
    for k in range(8):
        h += bytes([0x40 + k]) + P(0xC0, 20 + 30 * k, 20)
    for k in range(8):
        h += bytes([0x40 + k]) + P(0xC0, 266 + 13 * (k % 2), 60 + 18 * k)
    for k in range(8):
        h += bytes([0x40 + k]) + P(0xC0, 10 + 33 * k, 176 + (2 * k % 16))
    t['H05-brushes-and-edges'] = bytes(h + b'\x00')
    h = bytearray(b'\x24')
    for k in range(14):
        h += P(0x80, 20 * k, 0) + P(0xA0, 20 * k, 30)
    h += P(0x80, 0, 30) + P(0xA0, 279, 30)
    for k in range(13):
        h += bytes([0x60, 7 * k + 3]) + P(0xE0, 21 * k + 7, 0)
    t['H06-fills-on-row-0'] = bytes(h + b'\x00')
    t['H07-fill-from-non-white'] = bytes.fromhex('24800064A117646014E08C6400')
    for w, hx in ((8, '2480700AA0A80AA08CB4A0700A6028E08C0C00'),
                  (36, '24800E0AA10A0AA08CB4A00E0A6028E08C0C00'),
                  (37, '24800B0AA10D0AA08CB4A00B0A6028E08C0C00'),
                  (38, '2480070AA1110AA08CB4A0070A6028E08C0C00')):
        hh = 7 * w // 2
        built = (b'\x24' + P(0x80, 140 - hh, 10) + P(0xA0, 140 + hh, 10) + P(0xA0, 140, 180)
                 + P(0xA0, 140 - hh, 10) + b'\x60\x28' + P(0xE0, 140, 12) + b'\x00')
        assert built == bytes.fromhex(hx), w
        t['H08-triangle-%d-bytes' % w] = built
    t['H09-fill-at-row-191-non-white'] = bytes.fromhex('248000BFA117BF601EE064BF00')
    return t


def corpus():
    """{name: picture bytes} for every single picture of Appendix B, plus
    G01 (three pictures) and O01 (a picture and an overlay)."""
    t = hand_made()
    for k in range(60):
        t['R%02d-seed%d-n%d' % (k, 1000 + k, (10, 40, 120)[k % 3])] = random_picture(k)
    t['G01-group-of-3'] = bytes.fromhex('600FE00A0A00' '24800A0AA0C89600' '605A47C0646400')
    t['O01-picture-plus-overlay'] = bytes.fromhex('24803232A0E632A08C96A032326007E08C3C00'
                                                  '603CE00A0A26800000A117BF00')
    return t


# Appendix B.3: name -> (first 16 hex digits of the picture's SHA-256,
# V82 page, V84 page); G01 holds three pairs.
EXPECTED_TEXT = (ROOT / 'docs/GRAPHICS-MAGICIAN-FORMAT.md').read_text() if (ROOT / 'docs/GRAPHICS-MAGICIAN-FORMAT.md').exists() else ''


def expected():
    """Read Appendix B.3 out of the spec, so that the hashes are the
    document's and nobody's copy."""
    text = EXPECTED_TEXT.split('### B.3 Expected pages', 1)[1].split('```')[1]
    out = {}
    name = None
    for line in text.splitlines():
        f = line.split()
        if not f:
            continue
        if f[0][:1] in 'HRGO' and f[0][1:3].isdigit():
            name = f[0]
            out[name] = {'pic': f[2] if len(f) > 2 and f[1] == 'pic' else None}
        elif f[0].startswith('['):
            idx = int(f[0][1:-1])
            out[name].setdefault('group', {})[idx] = {f[1]: f[2]}
            last = idx
        elif f[0] in (V82, V84):
            if 'group' in out[name]:
                out[name]['group'][last][f[0]] = f[1]
            else:
                out[name][f[0]] = f[1]
    return out


def sha(b):
    return hashlib.sha256(b).hexdigest()


def expected_pages():
    """[(test name, picture bytes, dialect, base, last, page SHA-256)] for
    every page of Appendix B."""
    exp = expected()
    pics = corpus()
    out = []
    for name, e in exp.items():
        data = pics[name]
        if 'group' in e:
            for i, d in sorted(e['group'].items()):
                for dia in (V82, V84):
                    out.append(('%s[%d]' % (name, i), data, dia, i, i, d[dia]))
        elif name.startswith('O01'):
            for dia in (V82, V84):
                out.append((name, data, dia, 0, 1, e[dia]))
        else:
            for dia in (V82, V84):
                out.append((name, data, dia, 0, 0, e[dia]))
    return out


def selftest():
    exp = expected()
    pics = corpus()
    bad = 0
    for name, e in exp.items():
        if e.get('pic') and sha(pics[name])[:16] != e['pic']:
            print('picture bytes differ:', name)
            bad += 1
    cases = expected_pages()
    for name, data, dia, base, last, want in cases:
        if sha(view(data, dia, base, last, recognise=False)) != want:
            print('page differs:', name, dia)
            bad += 1
    # Every dialect rule of the file: V84 when $1x/$3x/$5x appear.
    assert dialect_of(b'\x20\x10\x00\x00\xC0\x00\x00\x00') == V84
    for nothing in (b'\x26\x00', b'\x60\x05\x00', b'\x24\x80\x00\x00\x00'):
        try:
            parts(nothing)
            raise AssertionError('rule 5: %r drew nothing' % nothing)
        except Malformed:
            pass
    assert dialect_of(pics['H02-colour-at-line-start']) == V82
    print('%d pictures, %d pages checked, %d differences' % (len(pics), len(cases), bad))
    return bad == 0


def includes():
    """{file name: text} of the assembly tables src/plugins/gmagic.s
    includes, generated from Appendix A and BOLD.SET (tools/test_gmagic.py
    checks the files in the tree are these)."""
    def rows(label, data, per=16):
        out = [label + ':'] if label else []
        for i in range(0, len(data), per):
            out.append('        .byte   ' + ', '.join('$%02X' % b for b in data[i:i + per]))
        return out
    head = ['; Generated by tools/gmagic_ref.py --includes from docs/GRAPHICS-MAGICIAN-FORMAT.md',
            '; (Appendix A); do not edit.']
    tables = head + ['; copy_buf: A.2, each pattern\'s row pattern for even rows (pate), then',
                     '; for odd rows (pato); A.3, the brushes, four 8-row quarters each',
                     '; (top-left, top-right, bottom-left, bottom-right), dot j of a row in',
                     '; bit j. 472 bytes.']
    tables += rows('', bytes(e for e, o in PATTERNS))
    tables += rows('', bytes(o for e, o in PATTERNS))
    tables += rows('', b''.join(b''.join(q) for q in BRUSHES), 8)
    text = head + ['; The main text page, 112 bytes at the head of each 128-byte block',
                   '; ($0400, $0480 ... $0780; the screen holes and $06F7 are left alone):',
                   '; the 96 glyphs of the font, 14 a block in blocks 0-4, 6 and 7, and in',
                   '; block 5 ($0680) the 27 row patterns of A.1 (bytes for byte columns',
                   '; c mod 4 = 0-3). The font is BOLD.SET, the hi-res font of A2FC\'s',
                   '; DEMO folder (tools/mkdemo_viewers.py hrcg_font): CiderPress II\'s',
                   '; STANDARD test font, each dot doubled to its right -- not Penguin\'s.']
    for blk, data in enumerate(text_blocks()):
        text += ['; block %d' % blk] + rows('', data, 8)
    return {'gmagic_tables.inc': '\n'.join(tables) + '\n',
            'gmagic_text.inc': '\n'.join(text) + '\n'}


def text_blocks():
    """The eight 112-byte blocks the overlay copies to $0400 + 128 i."""
    f = font()
    blocks = []
    g = 0
    for blk in range(8):
        if blk == 5:
            data = b''.join(ROWS)
        else:
            data = f[g * 8:(g + 14) * 8]
            g += 14
        blocks.append(data.ljust(112, b'\0'))
    return blocks


def glyph_address(ch):
    """Where the overlay finds the glyph of character ch ($20-$7F)."""
    g = ch - 0x20
    blk, r = divmod(g, 14)
    if blk >= 5:
        blk += 1
    return 0x0400 + 128 * blk + 8 * r


def main(argv):
    if argv[1:] == ['--selftest']:
        return 0 if selftest() else 1
    if argv[1:] == ['--includes']:
        for name, text in includes().items():
            (ROOT / 'src/plugins' / name).write_text(text)
        return 0
    if len(argv) == 3 and argv[1] == '--corpus':
        out = Path(argv[2])
        out.mkdir(parents=True, exist_ok=True)
        for name, data in corpus().items():
            (out / (name + '.pic')).write_bytes(data)
        return 0
    if len(argv) == 4:
        data = Path(argv[1]).read_bytes()
        Path(argv[3]).write_bytes(render(data, argv[2]))
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
