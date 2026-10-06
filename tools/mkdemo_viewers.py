#!/usr/bin/env python3
"""DEMO: one file for every viewer mkdemo.py leaves without an example.

    mkdemo_viewers.py DOSSIER

files() returns {folder: {host name: bytes}}; tools/stage_demo.py puts
them in DEMO and tools/test_file_viewers.py requires that the real
classifier sends each viewer at least one DEMO file. Nothing is borrowed
but one thing: STANDARD (CiderPress II's test font, already in
FONTS.SHAPES) gives its letters to the MGTK, .SET and .FONT fonts and to
the Newsroom banner. PICTURES/CARDS holds mkdemo.py's two colour cards
encoded in each format, so a wrong decoding shows at once; the other
pictures, the movies, the tune and the documents are written here.

The encoders are the simplest legal ones, not the original programs' own
choices. Each format's reference decoder (tools/*_ref.py, or the one in its
test) reads them back in tools/test_demo_viewers.py.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arlequin_ref
import busbasic_ref
import cpm_ref
import fantavision_ref
import gmagic_ref
import mkdemo
import pascal_ref
import pt3_fixture
import squeeze_ref

ROOT = Path(__file__).resolve().parents[1]
ROWS, COLS = 192, 40


def addr(r):
    return mkdemo.hgr_offset(r)


def cards():
    hgr = mkdemo.hgr_card()
    d = mkdemo.dhgr_card()
    return hgr, d[:8192], d[8192:]


# -- pictures ---------------------------------------------------------------

def column_stream(page, right_first=False):
    """A plane's 7,680 picture bytes a column at a time, rows 0-191 down each
    column: Extasie from the left, 816/Paint from the right."""
    cols = range(COLS - 1, -1, -1) if right_first else range(COLS)
    return bytes(page[addr(r) + c] for c in cols for r in range(ROWS))


def extasie(aux, main):
    """Type $F2: a two-byte file length, then counts: bit 7 set, one byte
    repeated (count & $7F, 0 = 128); clear, that many literals."""
    stream = column_stream(aux) + column_stream(main)
    out, i, lit = bytearray(), 0, bytearray()

    def flush():
        while lit:
            n = min(len(lit), 127)
            out.append(n)
            out.extend(lit[:n])
            del lit[:n]
    while i < len(stream):
        n = 1
        while i + n < len(stream) and stream[i + n] == stream[i] and n < 128:
            n += 1
        if n >= 3:
            flush()
            out += bytes([0x80 | (n & 0x7F), stream[i]])
            i += n
        else:
            lit.append(stream[i])
            i += 1
    flush()
    size = len(out) + 2
    return bytes([size & 255, size >> 8]) + bytes(out)


def packbytes(data):
    """Apple's PackBytes: flag 1 repeats one byte (up to 64), flag 0 copies
    up to 64 literals."""
    out, i, lit = bytearray(), 0, bytearray()

    def flush():
        while lit:
            n = min(len(lit), 64)
            out.append(n - 1)
            out.extend(lit[:n])
            del lit[:n]
    while i < len(data):
        n = 1
        while i + n < len(data) and data[i + n] == data[i] and n < 64:
            n += 1
        if n >= 3:
            flush()
            out += bytes([0x40 | (n - 1), data[i]])
            i += n
        else:
            lit.append(data[i])
            i += 1
    flush()
    return bytes(out)


PAINT816_TRAILER = b'\x07816PATT' + bytes(64)


def paint816_pack(stream):
    """816/Paint: $FF, then records: $80 | n << 2 and one byte repeated
    (n <= 31), $80 then n (<= 255) and the byte, or n (1-127) literals."""
    out, i, lit = bytearray(b'\xff'), 0, bytearray()

    def flush():
        while lit:
            n = min(len(lit), 127)
            out.append(n)
            out.extend(lit[:n])
            del lit[:n]
    while i < len(stream):
        n = 1
        while i + n < len(stream) and stream[i + n] == stream[i] and n < 255:
            n += 1
        if n >= 3:
            flush()
            out += bytes([0x80 | (n << 2)]) if n <= 31 else bytes([0x80, n])
            out.append(stream[i])
            i += n
        else:
            lit.append(stream[i])
            i += 1
    flush()
    return bytes(out)


def lz4fh(page):
    """LZ4FH (fadden): $66, then tokens: literals (high nibble, 15 + a byte),
    a match of 4 + (low nibble, 15 + a byte) at an ABSOLUTE output offset;
    the byte 253 means no match here, 254 the end."""
    out = bytearray([0x66])
    last = {}
    i, start = 0, 0

    def literals(end, match_nibble, tail):
        nonlocal start
        n = end - start
        while n > 270:                      # $FF, 15 + 255 literals, 253: no match
            out.append(0xFF)
            out.append(255)
            out.extend(page[start:start + 270])
            out.append(253)
            start += 270
            n -= 270
        if n >= 15:
            out.append(0xF0 | match_nibble)
            out.append(n - 15)
        else:
            out.append(n << 4 | match_nibble)
        out.extend(page[start:end])
        out.extend(tail)
        start = end
    while i + 4 <= len(page):
        key = page[i:i + 4]
        p = last.get(key)
        last[key] = i
        if p is not None:
            n = 4
            while i + n < len(page) and page[p + n] == page[i + n] and n < 271:
                n += 1
            m = n - 4
            tail = (bytes([m - 15]) if m >= 15 else b'') + p.to_bytes(2, 'little')
            literals(i, min(m, 15), tail)
            for k in range(i + 1, i + n):
                if k + 4 <= len(page):
                    last[page[k:k + 4]] = k
            i += n
            start = i
        else:
            i += 1
    literals(len(page), 15, b'\xfe')
    return bytes(out)


def lores_bars(width):
    """A lo-res screen of 24 rows, the sixteen colours in vertical bands."""
    return bytes((c * 16 // width) * 0x11 for _ in range(24) for c in range(width))


def dgr_single():
    return b'DGR\x01\x28\x30\x00\x00' + lores_bars(40)


def dgr_double():
    """Double lo-res: aux then main, 40 bytes a row each; the screen column
    2c is aux byte c and 2c + 1 main byte c."""
    bars = lores_bars(80)
    aux = bytes(bars[r * 80 + 2 * c] for r in range(24) for c in range(40))
    main = bytes(bars[r * 80 + 2 * c + 1] for r in range(24) for c in range(40))
    return b'DGR\x01\x50\x30\x01\x00' + aux + main


def printshop():
    """Print Shop clip art: 52 rows of 11 bytes, 88 dots, bit 7 first, a set
    bit is black. A framed apple: a disc, a leaf, a stalk."""
    out = bytearray(572)
    for y in range(52):
        for x in range(88):
            dx, dy = (x - 44) / 30.0, (y - 30) / 19.0
            leaf = ((x - 52) / 8.0) ** 2 + ((y - 8) / 4.0) ** 2 < 1
            stalk = 43 <= x <= 45 and 5 <= y <= 12
            black = (dx * dx + dy * dy < 1 and not (abs(x - 44) < 3 and y < 16)) or leaf or stalk
            if x < 2 or x >= 86 or y < 2 or y >= 50:
                black = True
            if black:
                out[y * 11 + x // 8] |= 0x80 >> (x % 8)
    return bytes(out)


def gmagic():
    """A Graphics Magician picture group (BIN $4000, as PICEDIT saves
    groups): a house drawn here with lines, fills, brush stamps, then
    Appendix B's palette (H04) and brushes (H05) of
    docs/GRAPHICS-MAGICIAN-FORMAT.md. N steps through the three."""
    P = gmagic_ref.P
    s = bytearray(b'\x24')                                            # black lines
    s += P(0x80, 0, 130) + P(0xA0, 279, 130)                           # the ground
    s += P(0x80, 60, 130) + P(0xA0, 60, 80) + P(0xA0, 140, 80) + P(0xA0, 140, 130)   # walls
    s += P(0x80, 50, 82) + P(0xA0, 100, 40) + P(0xA0, 150, 82) + P(0xA0, 50, 82)     # roof
    s += P(0x80, 90, 130) + P(0xA0, 90, 100) + P(0xA0, 110, 100) + P(0xA0, 110, 130)  # door
    s += P(0x80, 190, 130) + P(0xA0, 190, 95) + P(0x80, 196, 130) + P(0xA0, 196, 95)  # trunk
    s += b'\x60\x46'                                                  # blue sky
    for x, y in ((10, 100), (270, 100), (165, 120), (230, 120)):
        s += P(0xE0, x, y)
    s += b'\x60\x57' + P(0xE0, 10, 150)                                # green ground
    s += b'\x60\x3C' + P(0xE0, 70, 90) + P(0xE0, 130, 120) + P(0xE0, 75, 125)   # orange walls
    s += b'\x60\x65' + P(0xE0, 100, 60)                                # violet roof
    s += b'\x60\x50' + P(0xE0, 100, 120)                               # black door
    s += b'\x60\x57\x47'                                               # a spray of leaves
    for x, y in ((180, 70), (195, 62), (205, 75), (185, 85), (200, 85), (178, 95), (208, 92), (190, 78)):
        s += P(0xC0, x, y)
    s += b'\x60\x3C\x45'                                               # the sun
    for x, y in ((230, 15), (236, 15), (230, 21), (236, 21)):
        s += P(0xC0, x, y)
    hand = gmagic_ref.hand_made()
    return bytes(s + b'\x00') + hand['H04-palette-108-cells'] + hand['H05-brushes-and-edges']


def newsroom():
    """A Newsroom photo body: L, y1, y2, x1, x2, an empty clip history ended
    by $FF, then the bitmap (bit 0 left, 1 white): a sun over waves."""
    wb, h, x1, y1 = 20, 72, 60, 40
    bitmap = bytearray(wb * h)
    for y in range(h):
        for x in range(wb * 7):
            sun = (x - 70) ** 2 + (y - 26) ** 2 < 18 ** 2
            ray = (x - 70) ** 2 + (y - 26) ** 2 < 30 ** 2 and (x + y) % 6 == 0
            wave = y > 52 and (y - 52 + int(4 * math.sin(x / 6.0))) % 7 < 2
            if sun or ray or wave or x < 2 or x >= wb * 7 - 2 or y < 2 or y >= h - 2:
                bitmap[y * wb + x // 7] |= 1 << (x % 7)
    L = len(bitmap)
    x2 = x1 + 7 * (wb - 1) + 6
    return bytes([L & 255, L >> 8, y1, y1 + h - 1, x1, x2, 0, 0xFF]) + bytes(bitmap)


def arlequin(aux, main):
    """Arlequin ($F8): the whole screen, 20 groups by 192 rows."""
    rows = [bytes(v for c in range(COLS) for v in (aux[addr(r) + c], main[addr(r) + c]))
            for r in range(ROWS)]
    return arlequin_ref.encode(20, rows)


def purple(aux, main):
    """A Purplesoft pair: FOTO1 the aux page with the &GR mode minus one at
    $79 (5 = COL140, double hi-res) and 'S' at $7A, both screen holes;
    FOTO2 the main page."""
    a = bytearray(aux)
    a[0x79:0x7B] = bytes([5, ord('S')])
    return bytes(a), bytes(main)


# -- Fantavision --------------------------------------------------------------

def movie_header(speed, count, bg, clip=(5, 250, 12, 159)):
    h = bytearray(fantavision_ref.HDR)
    h[0], h[1], h[3], h[4], h[5] = speed, count, 4, bg, 8
    h[8:12] = bytes(clip)
    return h


def polygon(cx, cy, r, n, turn):
    xs = [max(0, min(255, int(round(cx + r * math.cos(turn + 2 * math.pi * k / n))))) for k in range(n)]
    ys = [max(0, min(191, int(round(cy + r * 0.8 * math.sin(turn + 2 * math.pi * k / n))))) for k in range(n)]
    return xs, ys


def bounce():
    """M.BOUNCE: a ball (a solid disc) bouncing over a floor line, a turning
    star (a closed line) and a trail of dots; it loops, S = 8 steps."""
    rec = fantavision_ref.record
    out = bytearray(movie_header(speed=4, count=0, bg=0x11))
    heights = [40, 110, 140, 110]
    for f, top in enumerate(heights):
        cx = 50 + f * 50
        frame = rec(2, 2, 0x55, 0, *polygon(cx, top, 18, 12, 0))          # the ball, white outline
        frame += rec(1, 11, 0x7F, 0, *polygon(200, 60, 28, 5, f * 0.6))    # the star
        frame += rec(1, 10, 0x2A, 2, [8, 247], [158, 158])                  # the floor (background)
        frame += rec(0, 3, 0x3F, 0, [cx - 30, cx - 20, cx - 10], [top + 20, top + 10, top + 5])
        out += frame + b'\x01' * 4
    return bytes(out + b'\x00')


def curtain():
    """M.CURTAIN: shapes opening over its backdrop CURTAIN (the colour card),
    played twice, then two seconds on the last frame and again."""
    rec = fantavision_ref.record
    out = bytearray(movie_header(speed=3, count=2, bg=0, clip=(0, 255, 0, 191)))
    for f in range(4):
        w = 10 + f * 25
        left = rec(3, 1, 0x00, 0, [5, 5 + w, 5 + w, 5], [12, 12, 159, 159])
        right = rec(3, 1, 0x00, 0, [250 - w, 250, 250, 250 - w], [12, 12, 159, 159])
        star = rec(1, 11, 0x33, 0, *polygon(128, 86, 20 + f * 12, 7, f * 0.5))
        out += left + right + star + b'\x01' * 5
    return bytes(out + b'\x00')


# -- music ----------------------------------------------------------------------

def pt3():
    """A generated ProTracker 3 module (tools/pt3_fixture.py), its title and
    credit fields named for the demonstration."""
    b = bytearray(pt3_fixture.module(2048))
    b[30:62] = b'A2 FILE CMD DEMO'.ljust(32)
    b[66:98] = b'GENERATED, NO BORROWED MUSIC'.ljust(32)
    return bytes(b)


# -- documents and programs -----------------------------------------------------

def hi(text):
    return bytes(c | 0x80 for c in text)


EPISTOLE = (b'_MG10_MD65_JD\r'
            b'_CE A2 FILE CMD\r'
            b'DOCVIEW\r'
            b'_PC\r\r'
            b'Cher #NOM],\r\r'
            b'_MI5Cette lettre est un document Epistole : A2 File Cmd le met\r'
            b'en page comme il serait imprime, marges, retraits et centrage.\r'
            b'_MI0\r'
            b'Les commandes _IGen gras_SG sont montrees en inverse.\r'
            b'_SP\r'
            b'Seconde page.\r')


def papyrus():
    return (b'\xff\x0d\x07\x05\xff\xff\x06\xff' + hi(b'PAPYRUS ET HOMEWORD') + b'\x8d'
            + b'\xff\x06\xff' + hi(b'Une ligne centree.') + b'\x8d'
            + hi(b'Un texte a bit haut, avec des codes $FF.') + b'\x8d'
            + b'\xff\x05\xff' + hi(b'Page deux.') + b'\x8d')


def visicalc():
    """A VisiCalc worksheet (/SS file), written here: what VISICALC
    recalculates -- formats, sums, a conditional, a square root on the ROM,
    a bar graph, VisiCalc's decimal arithmetic (1/3*3 shows 1.) -- in the
    order VisiCalc saves its cells, bottom right first."""
    cells = {
        'A1': '"A2 FILE C', 'B1': '"MD VISICA', 'C1': '"LC DEMO',
        'A3': '"ITEM', 'B3': '/FR"JAN', 'C3': '/FR"FEB', 'D3': '/FR"TOTAL',
        'A4': '"RENT', 'B4': '/F$650', 'C4': '/F$650', 'D4': '/F$@SUM(B4...C4)',
        'A5': '"FOOD', 'B5': '/F$231.5', 'C5': '/F$198.25', 'D5': '/F$@SUM(B5...C5)',
        'A6': '"PHONE', 'B6': '/F$32.1', 'C6': '/F$41', 'D6': '/F$+B6+C6',
        'A8': '"TOTAL', 'B8': '/F$@SUM(B4...B6)', 'C8': '/F$@SUM(C4...C6)', 'D8': '/F$@SUM(D4...D6)',
        'A9': '"AVERAGE', 'B9': '@AVERAGE(B4...B6)', 'C9': '@AVERAGE(C4...C6)',
        'A10': '"SHARE %', 'B10': '/FI+B8/D8*100', 'C10': '/FI+C8/D8*100',
        'A11': '"JAN MORE?', 'B11': '@IF(B8>C8,@TRUE,@FALSE)',
        'A12': '"ROOT', 'B12': '@SQRT(D8)', 'A13': '"PHONE', 'B13': '/F*+B6/10',
        'A14': '"1/3*3', 'B14': '1/3*3', 'A15': '"2+3*4', 'B15': '2+3*4',
    }
    for c in 'ABCD':
        cells[c + '2'] = '/-='
        cells[c + '7'] = '/--'
    def key(name):
        return (-int(name[1:]), -ord(name[0]))
    lines = ['>%s:%s' % (n, cells[n]) for n in sorted(cells, key=key)]
    lines += ['/W1', '/GOR', '/GRA', '/GC9', '/X>A1:>D8:']    # row by row: no ERROR
    return hi('\r'.join(lines).encode('ascii') + b'\r')


MARKDOWN = ('# A2 File Cmd\n\n'
            'MDVIEW (the ! menu) wraps text and shows **Markdown**:\n\n'
            '- headings\n- lists\n- code:\n\n'
            '```\n] BRUN A2FILE.SYSTEM\n```\n').encode('ascii')


def magic_window():
    head = bytes([0x8D, 0x00]) + hi(b'A2 FILE CMD - MAGIC WINDOW'.ljust(64)) + bytes(190)
    body = hi(b'A Magic Window document, read by MDVIEW.\rIts 256-byte header is skipped.\r')
    return head + body


def business_basic():
    t = {n: 0x80 + i for i, n in enumerate(busbasic_ref.TOK) if n}
    return busbasic_ref.make([
        (10, bytes([t['REM']]) + b' AN APPLE /// BUSINESS BASIC PROGRAM'),
        (20, bytes([t['HOME']])),
        (30, bytes([t['PRINT']]) + b'"LISTED BY BASLIST"'),
        (40, bytes([t['END']])),
    ])


def integer_basic():
    def rec(num, body):
        r = bytes([num & 0xFF, num >> 8]) + body + b'\x01'
        return bytes([len(r) + 1]) + r
    return (rec(10, bytes([0x5D]) + hi(b' AN INTEGER BASIC PROGRAM'))
            + rec(20, bytes([0x61, 0x28]) + hi(b'HELLO FROM INTEGER BASIC') + bytes([0x29]))
            + rec(30, bytes([0x51])))


def mgtk_font():
    """STANDARD (96 glyphs of 7 x 8, eight bytes each, bit 0 left) in the MGTK
    layout: 0 (one column), the last glyph, the height, the widths, then row
    by row one byte of every glyph."""
    std = (ROOT / 'data/CP2/GRAPHICS/STANDARD#070000').read_bytes()
    count = len(std) // 8
    planes = bytes(std[g * 8 + y] & 0x7F for y in range(8) for g in range(count))
    return bytes([0, count - 1, 8]) + bytes([7] * count) + planes


def text_screen():
    """A title screen written here, saved as a BSAVE of the text page leaves
    it (BIN $0400, 1,024 bytes, holes and all): DGRVIEW shows it as TEXT,
    T as lo-res. Inverse and flashing lines included."""
    lines = ['', '', '         A2 FILE CMD - DEMO', '', '   A TEXT SCREEN, SAVED FROM $0400',
             '   AS A 1,024-BYTE BINARY FILE.', '', '   RETURN SHOWS IT AS TEXT;',
             '   T READS THE SAME BYTES AS LO-RES,', '   A SWITCHES THE CHARACTER SET.']
    page = bytearray(1024)
    for r in range(24):
        line = lines[r] if r < len(lines) else ''
        at = (r & 7) * 128 + (r >> 3) * 40
        page[at:at + 40] = bytes(ord(c) | 0x80 for c in line.ljust(40))
    at = (12 & 7) * 128 + (12 >> 3) * 40 + 3
    page[at:at + 7] = bytes(ord(c) & 0x3F for c in 'INVERSE')
    at = (14 & 7) * 128 + (14 >> 3) * 40 + 3
    page[at:at + 5] = bytes(ord(c) & 0x3F | 0x40 for c in 'FLASH')
    return bytes(page)


def hrcg_font():
    """A hi-res character set in the DOS Tool Kit's layout (96 glyphs of
    7 x 8 dots from the space, a byte a row, bit 0 the leftmost dot):
    STANDARD's $20-$7F, the CiderPress II test font of FONTS.SHAPES, drawn bold here
    (each dot doubled to its right, kept within the 7 dots)."""
    std = (ROOT / 'data/CP2/GRAPHICS/STANDARD#070000').read_bytes()[0x20 * 8:0x80 * 8]  # its 128 glyphs start at $00
    return bytes((b | (b << 1)) & 0x7F for b in std)


# -- the formats of 0.9.5 ---------------------------------------------------------

def standard_font():
    """STANDARD's 128 glyphs of 7 x 8 dots from $00, a byte a row, bit 0 the
    leftmost dot (bit 7 set on some rows: not a dot)."""
    return (ROOT / 'data/CP2/GRAPHICS/STANDARD#070000').read_bytes()


def dot(page, x, y):
    page[addr(y) + x // 7] |= 1 << (x % 7)


def line(page, x0, y0, x1, y1):
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for k in range(int(n) + 1):
        dot(page, int(round(x0 + (x1 - x0) * k / n)), int(round(y0 + (y1 - y0) * k / n)))


def bank_street():
    """A Bank Street Writer document (BIN $0840, as DOS 3.3 saved it): high-
    bit text, $8D ends a paragraph, $83 centres its line, $89 is a tab, and
    the text ends at its first $00."""
    return (b'\x83' + hi(b'BANK STREET WRITER') + b'\x8d\x8d'
            + b'\x89' + hi(b'A Bank Street Writer document: a BIN file at $0840 of high-bit '
                           b'text, ended by its first zero byte.') + b'\x8d'
            + b'\x89' + hi(b'Return opens it in DOCVIEW, laid out as printed.') + b'\x8d\x00')


LOGO = (b'; A TERRAPIN LOGO PROCEDURES FILE: A BIN AT\r'
        b'; $2000 OF PLAIN TEXT. RETURN SHOWS IT AS TEXT.\r\r'
        b'TO SQUARE :SIZE\r REPEAT 4 [FORWARD :SIZE RIGHT 90]\rEND\r\r'
        b'TO FLOWER\r REPEAT 12 [SQUARE 60 RIGHT 30]\rEND\r\r')


def logo_picture():
    """What FLOWER (LOGO above) draws, the turtle at the centre heading up,
    saved as Terrapin Logo's SAVEPICT does: the hi-res page and two bytes
    more, 8,194 bytes. IMAGE shows the page."""
    page = bytearray(8192)
    heading = 0
    for _ in range(12):
        x, y = 140.0, 96.0
        for _ in range(4):
            nx = x + 60 * math.sin(math.radians(heading))
            ny = y - 60 * math.cos(math.radians(heading))
            line(page, x, y, nx, ny)
            x, y, heading = nx, ny, heading + 90
        heading += 30
    return bytes(page) + b'\x00\x01'


def koala_picture():
    """A KoalaPad picture as Micro-Illustrator saves it (BSAVE PICTR.name,
    A$4000,L$1FF8), copied to ProDOS: BIN $4000, the 8,184 bytes of a hi-res
    page without its last screen hole. A striped balloon over green hills.
    Colour: violet and blue dots on even columns, green and orange on odd
    ones; a byte takes the palette (blue, orange) most of its dots ask for."""
    def colour(x, y):
        if ((x - 140) / 46.0) ** 2 + ((y - 62) / 52.0) ** 2 < 1:
            return 'OVW'[(x - 94) // 16 % 3]
        if 126 <= x <= 154 and 138 <= y <= 152:
            return 'O'
        if 104 < y < 138 and abs(abs(x - 140) - (138 - y) * 0.38 - 2) < 1:
            return 'W'                                      # the ropes
        return 'G' if y > 160 + 10 * math.sin(x / 30.0) else 'B'
    page = bytearray(8192)
    for y in range(ROWS):
        for c in range(COLS):
            cs = [colour(c * 7 + k, y) for k in range(7)]
            b = 0x80 if sum(k in 'OB' for k in cs) > sum(k in 'VG' for k in cs) else 0
            for k, col in enumerate(cs):
                x = c * 7 + k
                if col == 'W' or (col in 'VB' and x % 2 == 0) or (col in 'GO' and x % 2):
                    b |= 1 << k
            page[addr(y) + c] = b
    return bytes(page[:8184])


def italic_font():
    """A Beagle Bros .FONT: the DOS Tool Kit's layout (BIN, 768 bytes, 96
    glyphs of 7 x 8 dots from the space, a byte a row, bit 0 left) with
    another name. STANDARD's $20-$7F slanted here: rows 0-2 a dot right,
    rows 6-7 a dot left (one dot of the 96 glyphs falls off)."""
    std = standard_font()[0x20 * 8:0x80 * 8]
    return bytes((b << 1) & 0x7F if i % 8 < 3 else (b & 0x7F) >> (i % 8 >= 6)
                 for i, b in enumerate(std))


def wide_text_screen():
    """An 80-column text screen saved as BIN $0400: 2,048 bytes, the
    auxiliary half (even columns) first. A MouseText window -- underscores
    above, $5A and $5F at the sides, $4C below -- with the apples $40 and
    $41 in its title, and lower case."""
    grid = [[0xA0] * 80 for _ in range(24)]

    def put(r, c, text):
        for i, ch in enumerate(text):
            grid[r][c + i] = ord(ch) | 0x80
    put(2, 5, '_' * 70)
    for r in range(3, 20):
        grid[r][4], grid[r][75] = 0x5A, 0x5F
    for c in range(5, 75):
        grid[20][c] = 0x4C
    grid[4][30], grid[4][31] = 0x40, 0x41
    put(4, 33, 'A2 File Cmd - 80 columns')
    lines = ['An 80-column text screen: 2,048 bytes saved from $0400,',
             'the auxiliary half first, as a BIN file.', '',
             'Return shows it in 80 columns, with MouseText in the alternate',
             'character set; T reads the same bytes as double lo-res,',
             'A switches the character set.']
    for i, text in enumerate(lines):
        put(7 + i, 8, text)
    halves = [bytearray(1024), bytearray(1024)]
    for r in range(24):
        at = (r & 7) * 128 + (r >> 3) * 40
        for c in range(80):
            halves[c & 1][at + c // 2] = grid[r][c]
    return bytes(halves[0] + halves[1])


def newsroom_banner():
    """A Newsroom banner BN.*: the photo's layout (newsroom() above), in the
    frame of every banner of the corpus, dots 7-246 and rows 43-122 (35
    bytes by 80 rows), black ink on white paper: DEMO NEWS in STANDARD's
    letters three times their size between two rules, two lines below."""
    wb, h, x1, y1 = 35, 80, 7, 43
    bitmap = bytearray([0x7F]) * (wb * h)
    font = standard_font()

    def ink(x, y):
        bitmap[y * wb + x // 7] &= ~(1 << (x % 7))

    def text(s, y0, k=1):
        x0 = (wb * 7 - 7 * k * len(s)) // 2
        for i, ch in enumerate(s):
            for r in range(8):
                for b in range(7):
                    if font[ord(ch) * 8 + r] >> b & 1:
                        for d in range(k * k):
                            ink(x0 + (7 * i + b) * k + d % k, y0 + r * k + d // k)
    for y in (3, 4, 38, 39):
        for x in range(6, wb * 7 - 6):
            ink(x, y)
    text('DEMO NEWS', 9, 3)
    text('A2 FILE CMD - A NEWSROOM BANNER', 48)
    text('RETURN OPENS IT IN NEWSROOM', 62)
    L = len(bitmap)
    return bytes([L & 255, L >> 8, y1, y1 + h - 1, x1, 246, 0, 0xFF]) + bytes(bitmap)


def clip_shapes():
    """The pages of clip_disk(): {name: [(y1, x1, h, w, white(x, y))]}, five
    small drawings, (x, y) within the piece."""
    def house(x, y):
        roof = y < 28 and abs(x - 35) <= y * 35 // 27
        walls = 27 <= y and 5 <= x <= 64 and (x in (5, 64) or y == 59)
        door = 40 <= y and 28 <= x <= 41 and (x in (28, 41) or y == 40)
        window = 33 <= y <= 43 and 46 <= x <= 58 and (x in (46, 52, 58) or y in (33, 38, 43))
        return roof or walls or door or window

    def tree(x, y):
        return (x - 20) ** 2 + (y - 18) ** 2 < 18 ** 2 or (17 <= x <= 22 and y >= 34)

    def sun(x, y):
        r, a = math.hypot(x - 20, y - 20), math.atan2(y - 20, x - 20)
        return r < 10 or (13 < r < 20 and math.cos(8 * a) > 0.8)

    def moon(x, y):
        return (x - 20) ** 2 + (y - 20) ** 2 < 400 and (x - 29) ** 2 + (y - 15) ** 2 >= 300

    def star(x, y):
        r, a = math.hypot(x - 15, y - 15), math.atan2(y - 15, x - 15) + math.pi / 2
        return r < 15 * (0.45 + 0.55 * abs(math.cos(2.5 * a)) ** 3)
    return {'HOUSE': [(100, 40, 60, 70, house), (100, 130, 60, 40, tree), (20, 180, 40, 40, sun)],
            'NIGHT': [(40, 60, 40, 40, moon), (70, 150, 31, 31, star)]}


def clip_piece(y1, x1, h, w, white):
    """A clip-art piece: y1, y2, x1, x2, then its 7-dot strips one after
    the other, a byte a row (bit 0 left, $80 an empty byte), runs of four
    or more written $00 n v."""
    raw = bytes(sum(1 << k for k in range(7) if 7 * c + k < w and white(7 * c + k, y)) or 0x80
                for c in range((w + 6) // 7) for y in range(h))
    out, i = bytearray([y1, y1 + h - 1, x1, x1 + w - 1]), 0
    while i < len(raw):
        n = 1
        while i + n < len(raw) and raw[i + n] == raw[i] and n < 255:
            n += 1
        if n >= 4:
            out += bytes([0, n, raw[i]])
        else:
            out += raw[i:i + n]
        i += n
    return bytes(out)


def clip_disk():
    """A Newsroom clip-art disk (docs/NEWSROOM-FORMAT.md), a DOS-order .DSK
    for NRCLIP: the pieces from track 0 sector 1 on (the VTOC and catalog
    sectors skipped), the SSI CLIP index on track 34 sectors 0-1, the
    location table from sector 6. As on Springboard's disks, a token VTOC
    (no free sector) and a catalog of notice lines whose T/S lists point
    off the disk (track 36), so that the disk opens in a panel."""
    disk = bytearray(143360)

    def sector(t, s):
        return (t * 16 + s) * 256
    order = [(t, s) for t in range(34) for s in range(16) if (t, s) not in ((0, 0), (17, 0), (17, 1))]
    data, table = bytearray(), bytearray()
    pages = clip_shapes()
    for pieces in pages.values():
        for p in pieces:
            t, s = order[len(data) // 256]
            table += bytes([t, s, len(data) % 256])
            data += clip_piece(*p)
        table.append(0xFF)
    for n, b in enumerate(data):
        t, s = order[n // 256]
        disk[sector(t, s) + n % 256] = b
    index = b'SSI CLIP\0A2 FILE CMD DEMO\0'
    index = bytes(c | 0x80 if c else 0 for c in index).ljust(0x1A, b'\0') + bytes([1, len(pages)])
    index += b''.join(hi(name.encode()) + b'\0' for name in pages)
    disk[sector(34, 0):sector(34, 0) + len(index)] = index
    disk[sector(34, 6):sector(34, 6) + len(table)] = table
    vtoc = sector(17, 0)
    disk[vtoc:vtoc + 4] = bytes([4, 17, 1, 3])
    disk[vtoc + 0x27], disk[vtoc + 0x34], disk[vtoc + 0x35], disk[vtoc + 0x37] = 0x7A, 35, 16, 1
    for i, text in enumerate(('NEWSROOM CLIP ART: A2FC DEMO', 'COPY ITS PAGES WITH NRCLIP')):
        e = sector(17, 1) + 0x0B + i * 0x23
        disk[e:e + 3] = bytes([0x24, 0xFF, 0x08])
        disk[e + 3:e + 33] = hi(text.ljust(30).encode())
    return bytes(disk)


# -- archives and disks -----------------------------------------------------------

def sample_text():
    return mkdemo.SAMPLE.replace('\n', '\r').encode('ascii')


def pascal_disk():
    text = b'HELLO FROM AN APPLE PASCAL VOLUME.\r'
    return pascal_ref.make('DEMO', [('HELLO.TEXT', 3, bytes(1024) + text.ljust(1024, b'\0'))])


def cpm_disk():
    return cpm_ref.make([('HELLO.TXT', b'Hello from a CP/M disk.\r\n' * 8)])


def files():
    hgr, aux, main = cards()
    foto1, foto2 = purple(aux, main)
    sample = sample_text()
    return {
        # the two colour cards in every picture format: the name is the format
        'PICTURES/CARDS': {
            'EXTASIE#F20000': extasie(aux, main),
            'PACKFOT#084000': packbytes(hgr),
            'PAINT816#06E002': bytes(8) + paint816_pack(column_stream(aux, True))
            + paint816_pack(column_stream(main, True)) + PAINT816_TRAILER,
            'LORES.DGR#060000': dgr_single(),
            'DLORES.DGR#060000': dgr_double(),
            'LZ4FH#088066': lz4fh(hgr),
            'ARLEQUIN#F80000': arlequin(aux, main),
            'PURPLE.FOTO1#062000': foto1,
            'PURPLE.FOTO2#062000': foto2,
            'MOVIEMAKER.SHP#061DF0': bytes(528) + hgr,
        },
        'PICTURES': {
            'TITLE.SCREEN#060400': text_screen(),
            'WIDE.SCREEN#060400': wide_text_screen(),
            'APPLE.PRINTSHOP#064800': printshop(),
            'PH.SUNSET#064000': newsroom(),
            'BN.DEMO.NEWS#064000': newsroom_banner(),
            'HOUSE.GMAGIC#064000': gmagic(),
            'PICTR.BALLOON#064000': koala_picture(),
            'FLOWER.PICT#062000': logo_picture(),
        },
        'MOVIES': {
            'M.BOUNCE#068400': bounce(),
            'M.CURTAIN#068400': curtain(),
            'CURTAIN#064000': hgr,
        },
        'MUSIC': {
            'DEMO.PT3#000000': pt3(),
        },
        'DOCUMENTS': {
            'LETTRE.EPISTOLE#040000': EPISTOLE,
            'NOTE.PAPYRUS#040000': papyrus(),
            'BUDGET.VC#040000': visicalc(),
            'README.MD#040000': MARKDOWN,
            'NOTE.MW#060000': magic_window(),
            'MEMO.BANKSTREET#060840': bank_street(),
        },
        'PROGRAMS': {
            'HELLO.BA3#090000': business_basic(),
            'HELLO.INT#FA0000': integer_basic(),
            'FLOWER.LOGO#062000': LOGO,
        },
        'ARCHIVES': {
            'SAMPLE.QQ#000000': squeeze_ref.squeeze(sample, b'SAMPLE.TXT'),
            'SAMPLE.ACU#000000': squeeze_ref.make_acu([(b'SAMPLE.TXT', 4, 0, sample, True, False)]),
        },
        'DISKS': {
            'PASCAL.PO#060000': pascal_disk(),
            'CPM.PO#060000': cpm_disk(),
            'CLIPART.DSK#060000': clip_disk(),
        },
        'FONTS.SHAPES': {
            'MGTK.FONT#070000': mgtk_font(),
            'BOLD.SET#068100': hrcg_font(),
            'ITALIC.FONT#064000': italic_font(),
        },
    }


def main():
    out = Path(sys.argv[1])
    for folder, items in files().items():
        (out / folder).mkdir(parents=True, exist_ok=True)
        for name, data in items.items():
            (out / folder / name).write_bytes(data)
            print(f'  {folder}/{name:<20} {len(data):>6} bytes')


if __name__ == '__main__':
    main()
