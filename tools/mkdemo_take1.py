#!/usr/bin/env python3
"""The Take 1 movie of the XL disk's DEMO/MOVIES folder.

    mkdemo_take1.py [OUT_DIR]      write the files files() returns

files() -> {host name: bytes}: one DOS 3.3 disk image, TAKE1.DSK, holding
an original Baudville "Take 1" movie built here, byte by byte, from
docs/TAKE1-FORMAT.md (nothing comes from Take 1's disks or artwork):

  MV.DEMO     the movie: one scene, faded in from the centre, out by a
              checkerboard
  SN.DEMO     the scene: 21 frames; a title planted in the first one, a
              car driving right along a road while a bird flies left,
              the car's horn half-way, a one-second pause at the end
  BK.MEADOW   the background: a starry sky, an orange sun, a green
              meadow, a road with a dashed line
  AC.CAR      the car, two snapshots (its wheels turn)
  AC.BIRD     the bird, two snapshots (wings up, wings down)
  CS.FONT     the title's character set (an Applesoft shape table)

Why an image and not the files extracted into the folder: Take 1 finds a
movie's parts by their DOS names, and TAKE1.SYSTEM reads a DOS 3.3 image
with its own reader, by those full names -- the faithful way the manual
gives. Extracted, the parts would sit beside the movie as six BIN files
under the 15-character reduction of their names, the form the manual
calls fragile; the image keeps MOVIES to one file and opens like any DOS
3.3 disk: Return on TAKE1.DSK, then Return on MV.DEMO.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mkdos33  # noqa: E402

HOST_NAME = 'TAKE1.DSK#060000'
MOVIE = 'MV.DEMO'
SPEED = 60                      # the scene's speed (higher is slower): ~82 ms a frame
FADE_IN, FADE_OUT = 8, 15       # centre out, checkerboard
TITLE = b'A2 FILE CMD'
TITLE_AT = (14, 10)             # the pen's first dot and row
NFRAMES = 21
HORN_FRAME = 10                 # the frame after which the horn sounds
HORN_SOUND = 4                  # double beep
END_PAUSE = 20                  # units of D(141), about 50 ms each
CAR_TOP, BIRD_TOP = 164, 60     # rows

# where each kind of file loads, as the editor writes it (docs: Files and names)
LOAD = {'MV.': 0x8029, 'SN.': 0x9400, 'BK.': 0x2000, 'AC.': 0x8000, 'CS.': 0x6000}


def row_offset(y):
    return (y & 7) * 0x400 + ((y >> 3) & 7) * 0x80 + (y >> 6) * 0x28


# -- the background ---------------------------------------------------------------

SUN = (224, 40, 15)             # centre dot, centre row, radius


def stars():
    """(dot, row) of each two-dot star: a fixed pseudo-random sky, clear of
    the title and of the sun."""
    out, seed = [], 1985
    while len(out) < 28:
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        c, b, y = (seed >> 8) % 40, (seed >> 4) % 6, (seed >> 16) % 120
        x = 7 * c + b
        if y < 24 and x < 160:                                     # the title
            continue
        if abs(x - SUN[0]) < SUN[2] + 6 and abs(y - SUN[1]) < SUN[2] + 6:
            continue
        if 54 <= y <= 68:                                          # the bird's lane
            continue
        out.append((x, y))
    return out


def background():
    """The 8,192-byte hi-res page of BK.MEADOW."""
    page = bytearray(0x2000)
    for y in range(192):
        a = row_offset(y)
        for c in range(40):
            if 128 <= y < 150 or y >= 178:                     # meadow: green
                v = 0x2A if c % 2 == 0 else 0x55
            elif y in (158, 159) and (c // 3) % 2 == 0:        # the road's dashed line
                v = 0x7F
            else:                                              # sky, road: black
                v = 0
            page[a + c] = v
    cx, cy, r = SUN
    for y in range(cy - r, cy + r + 1):
        a = row_offset(y)
        for x in range(cx - r, cx + r + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r and x % 2:  # orange: odd dots, palette 1
                page[a + x // 7] |= 0x80 | 1 << (x % 7)
    for x, y in stars():
        page[row_offset(y) + x // 7] |= 3 << (x % 7)               # white: two dots
    return bytes(page)


def encode_bk(page):
    """A BK. file for a page: per column (39 down to 0), runs of one
    repeated byte as patterns, the rest copied."""
    out = bytearray([0xFF])
    for c in range(39, -1, -1):
        col = [page[row_offset(y) + c] for y in range(192)]
        y = 0
        lit = []

        def flush():
            while lit:
                n = min(len(lit), 0x7F)
                out.append(n)
                out.extend(lit[:n])
                del lit[:n]
        while y < 192:
            q = 1
            while y + q < 192 and col[y + q] == col[y] and q < 31:
                q += 1
            if q >= 4:
                flush()
                out += bytes([0x80 | q << 2, col[y]])     # pattern of 1 byte, q times
                y += q
            else:
                lit.extend(col[y:y + q])
                y += q
        flush()
    return bytes(out)


# -- the actors ---------------------------------------------------------------------
# Art: '.' transparent, '#' a white dot, '-' a black dot. Each row is one or
# more opaque runs; the projector outlines every run with a black dot on
# each side (the editor's sprites), which the art's '.' leave room for.

CAR_BODY = [
    "...........##########.........",
    "..........##---##---###.......",
    ".........###---##---####......",
    "....#######################...",
    "...##########################.",
    "...##########################.",
    "...#####------########------#.",
    "....###--------######--------.",
]
CAR_WHEELS = [
    ["........-####-........-####-.", "........##--##........##--##.", "........-####-........-####-."],
    ["........--##--........--##--.", "........######........######.", "........--##--........--##--."],
]
CAR = [CAR_BODY + w for w in CAR_WHEELS]
BIRD = [
    [".##.......##.", "..###...###..", "....#####....", ".....###....."],
    [".....###.....", "....#####....", "..###...###..", ".##.......##."],
]


def runs(art):
    """[(start, string)] of a row's opaque runs."""
    out, i = [], 0
    while i < len(art):
        if art[i] == '.':
            i += 1
            continue
        j = i
        while j < len(art) and art[j] != '.':
            j += 1
        out.append((i, art[i:j]))
        i = j
    return out


def count_code(n, skip):
    """A skip or fill code of n dots (n < 112)."""
    assert 0 <= n < 112
    return (0x80 if skip else 0) | (n // 7) << 3 | n % 7


def encode_row(art):
    rs = runs(art)
    if not rs:
        return b'\x07'                       # an empty row: draws nothing
    out = bytearray()
    cursor = 0
    for k, (start, dots) in enumerate(rs):
        # first: skip start-1 leaves the dots before, blackens start-1;
        # later: blackens the cursor (the run before's outline), leaves
        # the gap, blackens start-1
        assert start >= 1 and (k == 0 or start - cursor >= 2), art
        out.append(count_code(start - 1 - cursor, True))
        for i in range(0, len(dots), 7):
            chunk = dots[i:i + 7]
            out += bytes([count_code(len(chunk), False),
                          sum(1 << j for j, d in enumerate(chunk) if d == '#')])
        cursor = start + len(dots)
    out.append(0x00)                         # the end: the last run's outline
    return bytes(out)


def snapshot(art):
    w = max(len(r) for r in art) + 1         # the right outline
    return bytes([len(art), w, 0, 0, 0, 0, 0]) + b''.join(encode_row(r) for r in art)


def actor(snaps):
    """An AC. file: count, offsets of the snapshots and of the actions
    (an empty list here: editor data, not played)."""
    n = len(snaps)
    head = bytearray([n])
    body = bytearray()
    first = 1 + 2 * (n + 1)
    for s in snaps:
        head += (first + len(body)).to_bytes(2, 'little')
        body += s
    head += (first + len(body)).to_bytes(2, 'little')
    return bytes(head + body + b'\x00')


# -- the character set ----------------------------------------------------------------
# 5 x 7 letters, each dot two screen dots wide (white, not colour). A shape
# runs the 10 x 7 cell as a serpentine, plotting the lit dots once each, then
# climbs back to the top and moves on 12 dots: the pen ends where the next
# character starts.

GLYPHS = {
    'A': [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    'C': [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    'D': ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    'E': ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    'F': ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    'I': [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    'L': ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    'M': ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    '2': [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
}
UP, RIGHT, DOWN, LEFT = 0, 1, 2, 3
CELL, ADVANCE = 10, 12


def glyph_vectors(rows):
    """[(plot, move)] for one character (None: a blank advance)."""
    if rows is None:
        return [(False, RIGHT)] * ADVANCE
    vec = []
    for r in range(7):
        cols = range(CELL) if r % 2 == 0 else range(CELL - 1, -1, -1)
        for i, c in enumerate(cols):
            if i < CELL - 1:
                move = RIGHT if r % 2 == 0 else LEFT
            else:
                move = DOWN if r < 6 else UP
            vec.append((rows[r][c // 2] == '#', move))
    return vec + [(False, UP)] * 5 + [(False, RIGHT)] * (ADVANCE - CELL + 1)


def shape_bytes(vectors):
    """Packs vectors into shape bytes (A and B plot, C only moves; a byte
    must not be 0, which ends the shape)."""
    v = [(4 if plot else 0) | move for plot, move in vectors]
    out = bytearray()
    i = 0
    while i < len(v):
        a = v[i]
        b = v[i + 1] if i + 1 < len(v) else None
        c = v[i + 2] if i + 2 < len(v) else None
        if b is not None and b != 0:
            if c in (1, 2, 3):
                out.append(a | b << 3 | c << 6)
                i += 3
            else:
                out.append(a | b << 3)
                i += 2
        elif b == 0 and c in (1, 2, 3):
            out.append(a | c << 6)           # B: up, no plot (C makes it count)
            i += 3
        elif a:
            out.append(a)
            i += 1
        else:
            out.append(0 | 1 << 3 | 3 << 6)  # up alone: up, right, left
            i += 1
    return bytes(out) + b'\x00'


def font():
    """The CS. file: shapes 1-59 for $20-$5A (shape = code - 31)."""
    shapes = [shape_bytes(glyph_vectors(GLYPHS.get(chr(ch)))) for ch in range(0x20, 0x5B)]
    n = len(shapes)
    out = bytearray([n, 0])
    pos = 2 + 2 * n
    for s in shapes:
        out += pos.to_bytes(2, 'little')
        pos += len(s)
    return bytes(out) + b''.join(shapes)


# -- the scene and the movie --------------------------------------------------------

def name20(s, hi=False):
    b = s.encode('ascii').ljust(20)[:20]
    return bytes(c | 0x80 for c in b) if hi else b


def element(o, x16, y16, wrap=False, plant=False, text=False, end=False):
    f = (x16 >> 8) & 3 | ((y16 >> 8) & 1) << 3
    f |= (0x10 if wrap else 0) | (0x20 if plant else 0) | (0x40 if text else 0) | (0x80 if end else 0)
    return bytes([o, x16 & 255, f, y16 & 255])


def car_x(i):
    return -32 + 16 * i                      # the car's left dot in frame i


def bird_x(i):
    return 290 - 16 * i


def frames():
    """The frames, each a list of elements (bytes)."""
    out = []
    for i in range(NFRAMES):
        els = []
        if i == 0:                           # the title, planted: part of the background
            els.append(element(1, 280 + TITLE_AT[0], 192 + TITLE_AT[1], wrap=True, plant=True, text=True))
        els.append(element(1 + i % 2, 280 + car_x(i), 192 + CAR_TOP))
        els.append(element(3 + i % 2, 280 + bird_x(i), 192 + BIRD_TOP))
        if i == HORN_FRAME:
            els.append(bytes([0xFC, HORN_SOUND, 0x82, 0]))
        elif i == NFRAMES - 1:
            els.append(bytes([0xFC, END_PAUSE, 0x81, 0]))
        else:
            els[-1] = els[-1][:2] + bytes([els[-1][2] | 0x80]) + els[-1][3:]
        out.append(els)
    return out


def scene():
    h = bytearray(0x100)
    fr = frames()
    h[0:2] = (len(fr) + 1).to_bytes(2, 'little')
    h[2] = SPEED
    h[3] = 1
    h[4:24] = name20('FONT')
    h[0x18] = 2
    for j, (count, name) in enumerate(((2, 'CAR'), (2, 'BIRD'))):
        h[0x19 + 22 * j:0x19 + 22 * (j + 1)] = bytes([count, count]) + name20(name)
    body = bytearray([0, 0, 1, len(TITLE)]) + TITLE
    body[0:2] = len(body).to_bytes(2, 'little')
    for els in fr:
        body += b''.join(els)
    body.append(0xFF)
    return bytes(h + body)


def movie():
    return bytes([1]) + name20('DEMO', True) + name20('MEADOW', True) + bytes([FADE_IN, FADE_OUT])


def parts():
    """{DOS name: file data (after the binary header)}, the movie first."""
    return {
        b'MV.DEMO': movie(),
        b'SN.DEMO': scene(),
        b'BK.MEADOW': encode_bk(background()),
        b'AC.CAR': actor([snapshot(a) for a in CAR]),
        b'AC.BIRD': actor([snapshot(a) for a in BIRD]),
        b'CS.FONT': font(),
    }


def disk():
    """The 143,360-byte DOS 3.3 image (DOS order), binary files (type B)."""
    files = []
    for name, data in parts().items():
        addr = LOAD[name[:3].decode()]
        files.append((name.decode(), 0x04, addr.to_bytes(2, 'little') + len(data).to_bytes(2, 'little') + data))
    return mkdos33.build(files)


def files():
    """{host name: bytes} for DEMO/MOVIES."""
    return {HOST_NAME: disk()}


if __name__ == '__main__':
    out = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files().items():
        (out / name).write_bytes(data)
        print(f'{out / name}: {len(data)} bytes')
