#!/usr/bin/env python3
"""DEMO: one file for every viewer mkdemo.py leaves without an example.

    mkdemo_viewers.py DOSSIER

files() returns {folder: {host name: bytes}}; tools/stage_demo.py puts
them in DEMO and tools/test_file_viewers.py requires that the real
classifier sends each viewer at least one DEMO file. Nothing is borrowed
but one thing: the MGTK font is STANDARD (CiderPress II's test font, already
in FONTS.SHAPES) laid out the MGTK way. The pictures are mkdemo.py's two
colour cards encoded in each format, so a wrong decoding shows at once; the
movies, the tune and the documents are written here.

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
        'PICTURES': {
            'EXTASIE#F20000': extasie(aux, main),
            'PACKFOT#084000': packbytes(hgr),
            'PACKFOT.D#084001': packbytes(aux) + packbytes(main),
            'PAINT816#06E001': paint816_pack(column_stream(hgr, True)) + PAINT816_TRAILER,
            'PAINT816.D#06E002': bytes(8) + paint816_pack(column_stream(aux, True))
            + paint816_pack(column_stream(main, True)) + PAINT816_TRAILER,
            'LORES.DGR#060000': dgr_single(),
            'DLORES.DGR#060000': dgr_double(),
            'LZ4FH#088066': lz4fh(hgr),
            'APPLE.CLIP#064800': printshop(),
            'PH.SUNSET#064000': newsroom(),
            'ARLEQUIN#F80000': arlequin(aux, main),
            'CARD.FOTO1#062000': foto1,
            'CARD.FOTO2#062000': foto2,
            'CARD.SHP#061DF0': bytes(528) + hgr,
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
            'EPISTOLE#040000': EPISTOLE,
            'PAPYRUS#040000': papyrus(),
            'README.MD#040000': MARKDOWN,
            'NOTE.MW#060000': magic_window(),
        },
        'PROGRAMS': {
            'LEDGER.BA3#090000': business_basic(),
            'HELLO.INT#FA0000': integer_basic(),
        },
        'ARCHIVES': {
            'SAMPLE.QQ#000000': squeeze_ref.squeeze(sample, b'SAMPLE.TXT'),
            'SAMPLE.ACU#000000': squeeze_ref.make_acu([(b'SAMPLE.TXT', 4, 0, sample, True, False)]),
        },
        'DISKS': {
            'PASCAL.PO#060000': pascal_disk(),
            'CPM.PO#060000': cpm_disk(),
        },
        'FONTS.SHAPES': {
            'MGTK.FONT#070000': mgtk_font(),
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
