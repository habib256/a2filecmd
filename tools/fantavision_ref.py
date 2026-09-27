#!/usr/bin/env python3
"""Reference model of A2 File Cmd's Fantavision player (FANTA.SYSTEM).

Written from docs/FANTAVISION-FORMAT.md and nothing else. It is the oracle
of the assembly engine (src/fanta/engine.s): both are ours and must agree
byte for byte, so every rule below is spelt out in integer arithmetic that
the 6502 code mirrors.

    fantavision_ref.py --selftest
    fantavision_ref.py MOVIE [--frames N]      check a movie, print frame counts

What the specification leaves open, and how it is settled here
---------------------------------------------------------------

* A partly covered screen byte: the covered dots take the pattern and the
  byte takes the object's palette bit (a hi-res byte has only one).
* Dots: a spot of size s covers rows y-s .. y+s-1; on its i-th row it
  covers x-w .. x+w-1 with w = DOT_HALF[s][i] (a disc of radius s).
* Lines, two dots wide: a segment from (x0,y0) down to (x1,y1) covers, on
  each row y0 <= y < y1, the dots from x(y) to x(y+1) plus one to the right,
  and on its last row x1 .. x1+1; x(y) steps in 8.8 fixed point, rounded
  (see edge_x). A horizontal segment is one span, plus one dot.
* Solid shapes: scan-line fill, even-odd, an edge covering rows ya <= y < yb
  (the bottom row of a shape belongs to its outline, if any); the spans are
  the pairs of sorted crossings, both ends included. A shape reduced to two
  distinct points is its segment, in the fill colour.
* Outline colour: black is nibble & 8, white (nibble & 8) | 3, per nibble.
* Dashed lines are open.
* In-between frames take key k's attributes (kind, mode, colour,
  animation); key k+1 itself is drawn as stored. An object with no points
  is treated as absent for the tweening.
* Point counts: with N = max(nA, nB), point i travels from A[i*nA//N] to
  B[i*nB//N].
* Rounding: P = floor(Pk + (Pk+1 - Pk) * t / S + 1/2), which the 8.8 sums
  give exactly since S is a power of two.
* Play count: the low nibble; 0 (whatever the high nibble) loops forever.
* Trace objects are drawn on both pages, background objects on both pages
  and the background copy, lightning on the page being built only.
* Erasing: on the page they were drawn on, when that page is next built,
  the byte columns that the normal objects covered, row by row (from the
  first to the last byte touched on each row, clipped), are restored from
  the background copy. Trace or lightning versions under them are lost.
"""
import argparse
import random
import sys

ROWS = 192
PAGE = 0x2000
HDR = 0x1A0
MIN_SIZE, MAX_SIZE = 513, 9216
MAX_FRAMES = 127
MAX_POINTS = 32

PATTERNS = [(0x00, 0x00), (0x55, 0x2A), (0x2A, 0x55), (0x7F, 0x7F),
            (0x36, 0x36), (0x49, 0x49), (0x2D, 0x2B), (0x56, 0x55)]

DOT_HALF = {
    1: [1, 1],
    2: [1, 2, 2, 1],
    3: [2, 3, 3, 3, 3, 2],
    4: [2, 3, 4, 4, 4, 4, 3, 2],
    5: [2, 4, 4, 5, 5, 5, 5, 4, 4, 2],
    6: [2, 4, 5, 5, 6, 6, 6, 6, 5, 5, 4, 2],
    7: [3, 4, 5, 6, 7, 7, 7, 7, 7, 7, 6, 5, 4, 3],
    8: [3, 5, 6, 7, 7, 8, 8, 8, 8, 8, 8, 7, 7, 6, 5, 3],
    9: [3, 5, 6, 7, 8, 8, 9, 9, 9, 9, 9, 9, 8, 8, 7, 6, 5, 3],
}

# The original's time for a frame (docs, "How long the original takes").
ORIG_BASE, ORIG_SEG, ORIG_BYTE, ORIG_ESEG, ORIG_EBYTE, ORIG_EDGE = 6300, 230, 20, 270, 45, 1100


def row_address(y):
    return (y & 7) * 0x400 + ((y >> 3) & 7) * 0x80 + (y >> 6) * 0x28


ROW = [row_address(y) for y in range(ROWS)]


def pattern(nib, col):
    even, odd = PATTERNS[nib & 7]
    return (odd if col & 1 else even) | (0x80 if nib & 8 else 0)


def steps(speed):
    e = speed & 7
    return 8 if e == 0 else 1 << (e - 1)


# -- the file -----------------------------------------------------------------

class Record:
    __slots__ = ('attr', 'colour', 'anim', 'xs', 'ys')

    def __init__(self, attr, colour, anim, xs, ys):
        self.attr, self.colour, self.anim, self.xs, self.ys = attr, colour, anim, xs, ys

    @property
    def kind(self):
        return self.attr & 3

    @property
    def mode(self):
        return self.attr >> 4


# fv_check's return codes (src/fanta/engine.s).
CODES = {None: 0, 'size': 1, 'header': 2, 'clip': 3, 'empty': 4, 'frames': 5}


def scan(data):
    """(reason or None, frame offsets, end offset) -- the "Checks": a damaged
    tail is cut, the movie ending before the first frame that is not whole
    (a 0 where a record should be, a length odd, below 4 or above 68, a
    record past the end of the file, the end of the file inside a frame)."""
    n = len(data)
    if n < MIN_SIZE or n > MAX_SIZE:
        return 'size', [], 0
    if data[3] != 4 or data[5] != 8:
        return 'header', [], 0
    if data[8] > data[9] or data[10] > data[11]:
        return 'clip', [], 0
    pos, frames = HDR, []
    while pos < n and data[pos] != 0:
        start = pos
        for _ in range(8):
            if pos >= n:
                break
            size = data[pos]
            if size != 1 and (size < 4 or size & 1 or size > 4 + 2 * MAX_POINTS or pos + size > n):
                break
            pos += size
        else:
            if len(frames) == MAX_FRAMES:
                return 'frames', frames, start
            frames.append(start)
            continue
        pos = start
        break
    if not frames:
        return 'empty', [], pos
    return None, frames, pos


def check(data):
    """None if the movie is accepted, else the reason."""
    return scan(data)[0]


def parse(data):
    """The frames of an accepted movie: lists of eight Record or None."""
    why, starts, _ = scan(data)
    assert why is None
    frames = []
    for pos in starts:
        frame = []
        for _ in range(8):
            size = data[pos]
            if size == 1:
                frame.append(None)
            else:
                k = (size - 4) // 2
                p = pos + 4
                frame.append(Record(data[pos + 1], data[pos + 2], data[pos + 3],
                                    list(data[p:p + k]), list(data[p + k:p + 2 * k])))
            pos += size
        frames.append(frame)
    return frames


# -- drawing ------------------------------------------------------------------

def edge_x(xa, dx, dy, rows):
    """x of a line from xa, dx across, dy down, `rows` rows below its start:
    xa + sign * ((128 + slope * rows) >> 8), slope = |dx| * 256 // dy."""
    slope = (abs(dx) << 8) // dy
    off = ((128 + slope * rows) & 0xFFFF) >> 8
    return xa - off if dx < 0 else xa + off


class Canvas:
    """The drawing state of one frame: clip window, counts, target."""

    def __init__(self, clip):
        cl, cr, ct, cb = clip
        self.cl, self.cr, self.ct, self.cb = cl, cr, ct, min(cb, ROWS - 1)
        self.buf = None
        self.colour = 0
        self.counting = False
        self.extents = None              # row -> [first, last] byte, or None
        self.spans = self.bytes = 0

    def span(self, y, xa, xb):
        if y < self.ct or y > self.cb:
            return
        xa = max(xa, self.cl)
        xb = min(xb, self.cr)
        if xa > xb:
            return
        sa, sb = xa + 14, xb + 14
        ca, cb = sa // 7, sb // 7
        if self.counting:
            self.spans += 1
            self.bytes += cb - ca + 1
            if self.extents is not None:
                e = self.extents.get(y)
                self.extents[y] = [ca, cb] if e is None else [min(e[0], ca), max(e[1], cb)]
        nib = self.colour & 15 if y & 1 else self.colour >> 4
        base = ROW[y]
        buf = self.buf
        for c in range(ca, cb + 1):
            lo = sa % 7 if c == ca else 0
            hi = sb % 7 if c == cb else 6
            mask = (((2 << hi) - 1) & ~((1 << lo) - 1)) | 0x80
            old = buf[base + c]
            buf[base + c] = old ^ ((old ^ pattern(nib, c)) & mask)

    def dot(self, x, y, size):
        for i, w in enumerate(DOT_HALF[size]):
            r = y - size + i
            if 0 <= r <= 255:
                self.span(r, x - w, x + w - 1)

    def segment(self, x0, y0, x1, y1):
        if (x0, y0) == (x1, y1):
            self.dot(x0, y0, 1)
            return
        if y0 > y1:
            x0, y0, x1, y1 = x1, y1, x0, y0
        if y0 == y1:
            self.span(y0, min(x0, x1), max(x0, x1) + 1)
            return
        dx, dy = x1 - x0, y1 - y0
        cur = x0
        for y in range(y0, y1):
            nxt = x1 if y + 1 == y1 else edge_x(x0, dx, dy, y + 1 - y0)
            self.span(y, min(cur, nxt), max(cur, nxt) + 1)
            cur = nxt
        self.span(y1, x1, x1 + 1)

    def fill(self, qx, qy):
        edges = []
        m = len(qx)
        for i in range(m):
            xa, ya, xb, yb = qx[i], qy[i], qx[(i + 1) % m], qy[(i + 1) % m]
            if ya == yb:
                continue
            if ya > yb:
                xa, ya, xb, yb = xb, yb, xa, ya
            edges.append((xa, ya, yb, xb - xa))
        if not edges:
            return
        y0 = min(e[1] for e in edges)
        y1 = max(e[2] for e in edges)
        for y in range(y0, min(y1, self.cb + 1)):
            if y < self.ct:
                continue
            xs = sorted(edge_x(xa, dx, yb - ya, y - ya)
                        for xa, ya, yb, dx in edges if ya <= y < yb)
            for j in range(0, len(xs) - 1, 2):
                self.span(y, xs[j], xs[j + 1])

    def draw(self, kind, mode, colour, xs, ys):
        n = len(xs)
        self.colour = colour
        if n == 0:
            return
        if kind == 0:
            if 1 <= mode <= 9:
                for x, y in zip(xs, ys):
                    self.dot(x, y, mode)
            return
        if kind == 1:
            if n == 1:
                self.dot(xs[0], ys[0], 1)
                return
            segs = list(range(n - 1))
            if mode == 11:
                segs.append(n - 1)
            for i in segs:
                if 1 <= mode <= 9 and i % (mode + 1) == mode:
                    continue
                j = (i + 1) % n
                self.segment(xs[i], ys[i], xs[j], ys[j])
            return
        qx, qy = [xs[0]], [ys[0]]
        for x, y in zip(xs[1:], ys[1:]):
            if x != qx[-1] or y != qy[-1]:
                qx.append(x)
                qy.append(y)
        while len(qx) > 1 and qx[-1] == qx[0] and qy[-1] == qy[0]:
            qx.pop()
            qy.pop()
        m = len(qx)
        if m == 1:
            self.dot(qx[0], qy[0], 1)
            return
        if m == 2:
            self.segment(qx[0], qy[0], qx[1], qy[1])
        else:
            self.fill(qx, qy)
        if mode == 0:
            return
        white = 0 if mode & 1 else 3
        self.colour = ((colour & 0x80) | (white << 4)) | ((colour & 8) | white)
        segs = m if mode <= 2 else m - 1
        for i in range(segs):
            j = (i + 1) % m
            self.segment(qx[i], qy[i], qx[j], qy[j])


def orig_cycles(c):
    return (ORIG_BASE + ORIG_SEG * c['spans'] + ORIG_BYTE * c['bytes'] +
            ORIG_ESEG * c['espans'] + ORIG_EBYTE * c['ebytes'] + ORIG_EDGE * c['edges'])


# -- playing ------------------------------------------------------------------

class Player:
    """Plays an accepted movie; frames() yields one entry per frame shown."""

    def __init__(self, data, backdrop=None):
        """`backdrop`: the picture file (8,192 or 8,184 bytes): the whole
        background, header byte 4 unused; a short save's missing last 8
        bytes (screen holes, not shown) are zeros."""
        self.data = bytes(data)
        self.frames = parse(self.data)
        self.S = steps(data[0])
        self.count = data[1] & 15
        self.clip = (data[8], data[9], data[10], data[11])
        self.bg = bytearray(PAGE)
        self.pages = {1: None, 2: None}
        self.extents = {1: {}, 2: {}}
        self.prev_normal = (0, 0)
        if backdrop is not None:
            assert len(backdrop) in (8192, 8184)
            self.bg[:len(backdrop)] = backdrop
        else:
            canvas = Canvas((0, 255, 0, 255))
            canvas.buf, canvas.colour = self.bg, data[4]
            for y in range(12, 160):
                canvas.span(y, 5, 250)
        self.pages[1] = bytearray(self.bg)
        self.pages[2] = bytearray(self.bg)

    def build(self, page, versions):
        """Erase then draw `versions` (8 entries: None or (kind, mode, colour,
        anim, xs, ys, interpolated)) on `page`. Returns the counts."""
        other = 3 - page
        buf = self.pages[page]
        c = dict(spans=0, bytes=0, edges=0, espans=self.prev_normal[0],
                 ebytes=self.prev_normal[1])
        for r, (c0, c1) in self.extents[page].items():
            a = ROW[r]
            buf[a + c0:a + c1 + 1] = self.bg[a + c0:a + c1 + 1]
        self.extents[page] = {}
        nspans = nbytes = 0
        canvas = Canvas(self.clip)
        for o, v in enumerate(versions):
            if v is None:
                continue
            kind, mode, colour, anim, xs, ys, interp = v
            anim = min(anim, 3)
            targets = [buf]
            if anim in (1, 2):
                targets.append(self.pages[other])
            if anim == 2:
                targets.append(self.bg)
            c['edges'] += len(xs) if kind else 0
            canvas.spans = canvas.bytes = 0
            for i, t in enumerate(targets):
                canvas.buf = t
                canvas.counting = i == 0
                canvas.extents = self.extents[page] if i == 0 and anim == 0 else None
                canvas.draw(kind, mode, colour, xs, ys)
            c['spans'] += canvas.spans
            c['bytes'] += canvas.bytes
            if anim == 0:
                nspans += canvas.spans
                nbytes += canvas.bytes
        self.prev_normal = (nspans, nbytes)
        c['orig'] = orig_cycles(c)
        return c

    @staticmethod
    def key_version(rec):
        if rec is None:
            return None
        return (rec.kind, rec.mode, rec.colour, rec.anim, rec.xs, rec.ys, False)

    def between(self, a, b, t):
        if a is None or b is None or not a.xs or not b.xs:
            return None
        na, nb = len(a.xs), len(b.xs)
        n = max(na, nb)
        mul = 256 // self.S
        xs, ys = [], []
        for i in range(n):
            s, d = i * na // n, i * nb // n
            for src, dst, out in ((a.xs, b.xs, xs), (a.ys, b.ys, ys)):
                acc = (src[s] << 8) + 128 + ((dst[d] - src[s]) * mul & 0xFFFF) * t
                out.append((acc & 0xFFFF) >> 8)
        return (a.kind, a.mode, a.colour, a.anim, xs, ys, True)

    def play(self, limit=None):
        """Yields (page shown, bytes of that page, counts) per frame shown."""
        shown = 1
        c = self.build(1, [self.key_version(r) for r in self.frames[0]])
        yield shown, bytes(self.pages[1]), c
        produced = 1
        F = len(self.frames)
        if F == 1:
            return
        remaining = None if self.count == 0 else self.count * F - 1
        k = 0
        while remaining is None or remaining > 0:
            k1 = (k + 1) % F
            for t in range(1, self.S + 1):
                if limit is not None and produced >= limit:
                    return
                page = 3 - shown
                if t < self.S:
                    vs = [self.between(a, b, t)
                          for a, b in zip(self.frames[k], self.frames[k1])]
                else:
                    vs = [self.key_version(r) for r in self.frames[k1]]
                c = self.build(page, vs)
                shown = page
                produced += 1
                yield shown, bytes(self.pages[page]), c
            k = k1
            if remaining is not None:
                remaining -= 1


# -- synthetic movies ---------------------------------------------------------

def header(rng, speed=None, count=None, clip=None, bg=None):
    h = bytearray(rng.randrange(256) for _ in range(HDR))
    h[0] = rng.randrange(256) if speed is None else speed
    h[1] = rng.choice([0, 1, 2, 3, 0x21, 0x10]) if count is None else count
    h[3], h[5] = 4, 8
    h[4] = rng.randrange(256) if bg is None else bg
    if clip is None:
        clip = rng.choice([(5, 250, 12, 159), (0, 255, 0, 255), (0, 255, 0, 191)]) \
            if rng.random() < 0.7 else random_clip(rng)
    h[8:12] = bytes(clip)
    return h


def random_clip(rng):
    a, b = sorted(rng.randrange(256) for _ in range(2))
    c, d = sorted(rng.randrange(256) for _ in range(2))
    return (a, b, c, d)


def record(kind, mode, colour, anim, xs, ys, junk=0):
    return bytes([4 + 2 * len(xs), (mode << 4) | (junk << 2) | kind, colour, anim]) + \
        bytes(xs) + bytes(ys)


def random_object(rng, n=None, big=False):
    kind = rng.randrange(4)
    mode = rng.randrange(16)
    if kind == 0 and rng.random() < 0.8:
        mode = rng.randrange(1, 10)
    if n is None:
        n = rng.choice([0, 1, 2, 3, 3, 4, 5, 6, 8, 12, 20, 32])
    cx, cy = rng.randrange(256), rng.randrange(200)
    r = rng.choice([4, 10, 30, 80, 140]) if not big else 120
    xs = [min(255, max(0, cx + rng.randrange(-r, r + 1))) for _ in range(n)]
    ys = [min(255, max(0, cy + rng.randrange(-r, r + 1))) for _ in range(n)]
    if n > 2 and rng.random() < 0.2:          # repeated points
        i = rng.randrange(n - 1)
        xs[i + 1], ys[i + 1] = xs[i], ys[i]
    anim = rng.choice([0, 0, 0, 0, 1, 2, 3, 3, 7])
    return record(kind, mode, rng.randrange(256), anim, xs, ys, junk=rng.randrange(4))


def moved(rng, rec_bytes, n=None):
    """The same object, moved and maybe with another point count."""
    k = (rec_bytes[0] - 4) // 2
    xs, ys = list(rec_bytes[4:4 + k]), list(rec_bytes[4 + k:4 + 2 * k])
    if n is not None and n != k:
        if n > k:
            base = xs or [128]
            basey = ys or [96]
            xs = xs + [rng.choice(base) for _ in range(n - k)]
            ys = ys + [rng.choice(basey) for _ in range(n - k)]
        else:
            xs, ys = xs[:n], ys[:n]
    dx, dy = rng.randrange(-60, 61), rng.randrange(-60, 61)
    xs = [min(255, max(0, x + dx + rng.randrange(-8, 9))) for x in xs]
    ys = [min(255, max(0, y + dy + rng.randrange(-8, 9))) for y in ys]
    return bytes([4 + 2 * len(xs)]) + rec_bytes[1:4] + bytes(xs) + bytes(ys)


def synthetic(seed, frames=None, **kw):
    """A random but valid movie: objects of every kind, mode and animation,
    point-count changes, absences, clip windows, speeds and play counts."""
    rng = random.Random(seed)
    out = header(rng, **kw)
    nf = frames if frames is not None else rng.choice([1, 2, 3, 4, 6])
    objs = [random_object(rng) if rng.random() < 0.8 else None for _ in range(8)]
    for _ in range(nf):
        frame = b''
        for o in range(8):
            if objs[o] is not None and rng.random() < 0.1:
                objs[o] = None
            elif objs[o] is None and rng.random() < 0.3:
                objs[o] = random_object(rng)
            elif objs[o] is not None:
                n = None
                if rng.random() < 0.3:
                    n = rng.randrange(0, 33)
                objs[o] = moved(rng, objs[o], n)
            frame += objs[o] if objs[o] is not None else b'\x01'
        if len(out) + len(frame) + 1 > MAX_SIZE:
            break
        out += frame
    if len(out) < MIN_SIZE or rng.random() < 0.7:
        out += b'\x00'
    while len(out) < MIN_SIZE:
        out += bytes([rng.randrange(256)])
    return bytes(out)


def demo_movie(kind, speed=3, seed=0, n=8, frames=3, anim=0, mode=None, big=False):
    """One object of one kind moving: for the per-kind timings."""
    rng = random.Random(seed)
    h = header(rng, speed=speed, count=1, clip=(0, 255, 0, 191), bg=0x11)
    if mode is None:
        mode = {0: 3, 1: 11, 2: 1, 3: 0}[kind]
    out = bytes(h)
    r = 110 if big else 30
    for f in range(frames):
        cx, cy = 128 + (f % 2) * 20 - 10, 96 + (f % 3) * 10 - 10
        xs = [min(255, max(0, cx + rng.randrange(-r, r + 1))) for _ in range(n)]
        ys = [min(255, max(0, cy + rng.randrange(-r * 3 // 4, r * 3 // 4 + 1))) for _ in range(n)]
        out += record(kind, mode, 0x2A, anim, xs, ys) + b'\x01' * 7
    return out + b'\x00' + b'\x00' * max(0, MIN_SIZE - len(out) - 1)


def shaped_movie(seed, objects=4, frames=4, speed=3):
    """Closer to what people draw: simple (star-shaped) polygons, polylines
    and dot groups that move and turn between keys, normal animation, the
    usual window 5-250 x 12-159. For the timings."""
    import math
    rng = random.Random(seed)
    out = bytes(header(rng, speed=speed, count=1, clip=(5, 250, 12, 159), bg=rng.choice([0x00, 0x11, 0x55])))
    shapes = []
    for o in range(objects):
        kind = rng.choice([0, 1, 1, 2, 2, 2])
        n = rng.randrange(4, 13) if kind else rng.randrange(3, 9)
        mode = {0: rng.randrange(1, 5), 1: rng.choice([10, 11, 2]), 2: rng.choice([0, 1, 2])}[kind]
        shapes.append((kind, mode, rng.randrange(256), n, rng.randrange(20, 60),
                       rng.randrange(40, 216), rng.randrange(40, 140), rng.random() * 6.28))
    for f in range(frames):
        frame = b''
        for kind, mode, colour, n, r, cx, cy, a0 in shapes:
            cx2 = min(230, max(25, cx + int(30 * math.cos(f + a0))))
            cy2 = min(140, max(30, cy + int(20 * math.sin(f * 1.3 + a0))))
            turn = a0 + f * 0.4
            xs, ys = [], []
            for i in range(n):
                rr = r * (0.6 + 0.4 * ((i * 7 + seed) % 5) / 4)
                t = turn + 6.2832 * i / n
                xs.append(min(255, max(0, int(cx2 + rr * math.cos(t)))))
                ys.append(min(191, max(0, int(cy2 + rr * 0.8 * math.sin(t)))))
            frame += record(kind, mode, colour, 0, xs, ys)
        frame += b'\x01' * (8 - objects)
        out += frame
    out += b'\x00'
    return out + b'\x00' * max(0, MIN_SIZE - len(out))


# -- self test ----------------------------------------------------------------

def visible(page):
    return b''.join(page[ROW[y]:ROW[y] + 40] for y in range(ROWS))


def selftest():
    rng = random.Random(7)
    # Checks.
    good = synthetic(1, frames=2)
    assert check(good) is None
    bad = bytearray(good)
    bad[3] = 5
    assert check(bad) == 'header'
    bad = bytearray(good)
    bad[8], bad[9] = 9, 8
    assert check(bad) == 'clip'
    assert check(good[:512]) == 'size'
    assert check(b'\0' * 9217) == 'size'
    h = header(rng)
    assert check(bytes(h) + b'\0' * 200) == 'empty'
    assert check(bytes(h) + b'\x01' * 7 + b'\x00' * 200) == 'empty'
    assert check(bytes(h) + b'\x01' * 8 * 127 + b'\x00' * 10) is None
    assert check(bytes(h) + b'\x01' * 8 * 128 + b'\x00' * 10) == 'frames'
    cut = bytes(h) + b'\x01' * 8 * 127 + b'\x01' * 7 + b'\x00'
    assert check(cut) is None and len(parse(cut)) == 127
    two = bytes(h) + b'\x01' * 8 + b'\x01' * 3 + b'\x00' + b'\x01' * 200
    assert scan(two)[1:] == ([HDR], HDR + 8), scan(two)
    big = bytes(h) + b'\x01' * 8 + bytes([140, 1, 3, 0]) + bytes(136) + b'\x01' * 7
    assert scan(big)[0] is None and len(scan(big)[1]) == 1
    exact = bytes(h) + b'\x01' * 8 * 12       # 512 bytes: too short
    assert check(exact) == 'size'
    exact += b'\x01' * 8
    assert check(exact) is None and len(parse(exact)) == 13
    # Drawing: a white spot on black.
    p = Player(bytes(header(rng, speed=1, count=1, clip=(0, 255, 0, 191), bg=0)) +
               record(0, 1, 0x33, 0, [100], [50]) + b'\x01' * 7 + b'\x00' * 100)
    frames = list(p.play())
    assert len(frames) == 1
    page = frames[0][1]
    lit = [(y, c) for y in range(192) for c in range(40) if page[ROW[y] + c] & 0x7F]
    assert {y for y, _ in lit} == {49, 50}, lit
    # Counts of that frame: two spans of one byte each (x 113-114 / 7 = col 16).
    assert frames[0][2]['spans'] == 2 and frames[0][2]['bytes'] == 2
    assert frames[0][2]['orig'] == 6300 + 2 * 230 + 2 * 20
    # Tweening ends on the keys exactly, and plays count * F - 1 transitions.
    m = synthetic(3, frames=3, speed=2, count=2)
    n = sum(1 for _ in Player(m).play())
    assert n == 1 + (2 * len(parse(m)) - 1) * 2, n
    for seed in range(4):
        assert check(shaped_movie(seed)) is None
    # Many random movies render without leaving the buffers.
    for seed in range(40):
        mv = synthetic(seed)
        assert check(mv) is None, (seed, check(mv))
        for _ in Player(mv).play(limit=12):
            pass
    print('PASS fantavision_ref selftest')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('movie', nargs='?')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--frames', type=int, default=20)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    data = open(args.movie, 'rb').read()
    why = check(data)
    if why:
        sys.exit('refused: ' + why)
    for i, (page, _, c) in enumerate(Player(data).play(limit=args.frames)):
        print(i, page, c['spans'], c['bytes'], c['espans'], c['ebytes'], c['edges'], c['orig'])


if __name__ == '__main__':
    main()
