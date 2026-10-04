#!/usr/bin/env python3
"""Reference model of A2 File Cmd's Take 1 player (TAKE1.SYSTEM).

Written from docs/TAKE1-FORMAT.md and nothing else. It is the oracle of the
assembly engine (src/take1/engine.s): both are ours and must agree byte for
byte, so every rule is spelt out in integer arithmetic that the 6502 code
mirrors.

    take1_ref.py --selftest
    take1_ref.py IMAGE.DSK MV.NAME [--frames N] [--out DIR]
    take1_ref.py DIRECTORY MV.NAME [--frames N] [--out DIR]
                        play a movie of a DOS 3.3 image (by catalog name)
                        or of a directory of files extracted by A2 File Cmd
                        (ProDOS names); print the shown pages and events,
                        and with --out write each shown page (8 KB)

What the specification leaves open, and how it is settled here
---------------------------------------------------------------

* Fade numbers: the fade-in and fade-out bytes select the fade of the same
  number in the table (2-17; 1 is none). The design's "fade `fade-in - 1`"
  is read as the editor's 1-based list of the 16 fades: taking the table
  entry v - 1 would make 2 a second "none" and fade 17 unreachable.
* The row drawing is a byte accumulator: the dots a code puts in the byte
  under the cursor are gathered and the byte is written when the cursor
  leaves it ("flush") or at the row's end. A flush caused by a run, by the
  black dot before a skip, by an untouched stretch of a skip or by an end
  writes bit 7 from the palette register; the flush caused by the black
  dot that ends a skip (it is then bit 6) sets no bit 7 of its own: the
  byte keeps the register's bit 7 if earlier dots of the row fell in it
  (the spec, clarified), else the screen's. A byte
  that received no dot is not written, except by the two forced flushes of
  the spec ($07 end off bit 0, and the 280-dot return of a wrapped row).
* P3 applies to the register-palette writes only: the byte written becomes
  (byte & $7F) | 3. The keep-bit-7 write is not affected by P3.
* A skip of 0 that is not the row's first code is a black dot under the
  cursor (register palette if the cursor then leaves the byte); as the
  row's first code it is the skip's end black dot (keeps bit 7 at bit 6).
* Extensions: they add up, stay pending across a literal, and are dropped
  at the row's end; they do not make the row "non-empty" ($00 after only
  extensions draws nothing, and a skip after extensions only is still the
  row's first code). A skip or fill of more than 127 groups of 7 dots
  (895 dots and more) is refused as damaged.
* A rectangle of height 0 (all rows above the screen) is recorded: it
  counts in the list's 20 entries and its area is 0.
* Erasing: a rectangle's rows go on modulo 192 (a snapshot may be 255 rows
  high), its columns modulo 40. The full copy copies all 8,192 bytes.
* Planting: the objects at the start of a frame, while the element is an
  object with the plant flag; any other element ($FC, a one-byte filler)
  ends the plant prefix. A plant-flagged object after it is drawn on the
  back page as a normal object.
* Elements: $00 is refused (it is not in the table). Elements that come
  before $FF without an end-of-frame flag form a last frame, played as
  any other. A scene without frames shows nothing; its fade-in is skipped,
  its fade-out still applies.
* $FC kinds other than 0, 1, 2 are passed on as events and ignored by the
  player.
* Characters: shape number ch - 31 computed in integers; outside 1..N it is
  shape 1. A character set with N = 0 is refused. A text's cost counts the
  shape bytes drawn, the final 0 of each shape excluded.
* Text rectangle: the leftmost/rightmost positions are dot positions; a
  move "from the leftmost position" is a move left made while the pen is
  exactly on it (the same for the right, the top and the bottom rows).
  Width and height saturate at 255 before their caps of 40 and 192.
* Timing: the cost starts at 0 with each scene. Order after a frame is
  shown: the frame wait (computed with the cost so far), the cost reset,
  the step-5 erase (counted in the next frame), then the $FC element.
  The cost is kept as a 16-bit count that saturates at 65,535.
* Fades: 12 copies 384 rows, top and bottom alternately, the last one being
  the bottom side's row 0 (otherwise even columns of row 0 would be left).
  14: x goes on decreasing from one column to the next (a staircase), as
  the procedure is written; 15: D(25) after the six strips of each g;
  16/17: D(20) between the blocks of the repeat loop, none between the last
  of them and the block from the source, D(20) between passes. The black
  source of a fade-out is the back page, cleared first (it is reset from
  page 3 at the next scene).
* The movie starts with page 1 shown; when it starts again (after the
  2-second hold), the three pages are cleared and page 1 is shown again.
* Files: names compare on the low 7 bits, trailing spaces removed, upper
  case and lower case distinct. A catalog entry matches on its name only
  (its type is not checked). Each scene is checked when it is loaded (its
  background first, then the scene, its actors in order, the character
  set), not the whole movie at the start. An actor is checked for the
  snapshots its scene can reach: 1 to min(count, n). The memory given to a
  scene, its actors and its character set is SCENE_MAX bytes (the same as
  the engine), and so to the movie (read again at each scene, its entry
  kept) and to a background (8,192 bytes at most).
"""
import argparse
import os
import random
import re
import sys
from pathlib import Path

ROWS = 192
PAGE = 0x2000
FULL_COST = 3430
AREA_FULL = 0x0D00
MAX_RECTS = 20
MAX_GROUPS = 127              # a skip or fill: at most 127 groups of 7 dots
BK_MAX = 0x2000


def _engine_constant(name, default):
    """SCENE_MAX / MOVIE_MAX as engine.s and take1.cfg define them."""
    root = Path(__file__).resolve().parents[1]
    try:
        text = (root / 'src/take1/engine.s').read_text()
        m = re.search(r'^%s\s*=\s*\$([0-9A-Fa-f]+)' % name, text, re.M)
        if m:
            return int(m[1], 16)
    except OSError:
        pass
    return default


SCENE_MAX = _engine_constant('SCENE_MAX', 0x3000)
MOVIE_MAX = SCENE_MAX         # the movie is read into the scene's memory

BLACK = b'< BLACK >'
UNCHANGED = b'< UNCHANGED >'

# t1_err codes (src/take1/engine.s)
E_NOTFOUND, E_READ, E_BIG, E_BAD = 1, 2, 3, 4


def row_address(y):
    return (y & 7) * 0x400 + ((y >> 3) & 7) * 0x80 + (y >> 6) * 0x28


ROW = [row_address(y) for y in range(ROWS)]


class Refused(Exception):
    """A file the player cannot draw exactly: code (E_*), DOS name, why."""

    def __init__(self, code, name, why=''):
        super().__init__('%s: %s (%s)' % ({1: 'not found', 2: 'unreadable', 3: 'too large',
                                            4: 'damaged'}[code], name.decode('latin-1'), why))
        self.code, self.name, self.why = code, name, why


def field_name(field):
    """A 20-character name field: low 7 bits, trailing spaces removed."""
    return bytes(b & 0x7F for b in field).rstrip(b' ')


def dos_name(prefix, field):
    return prefix + field_name(field)


def prodos_name(dosname):
    """The name A2 File Cmd gives a DOS name when it extracts the file."""
    out = []
    for c in dosname[:15]:
        c &= 0x7F
        if 0x61 <= c <= 0x7A:
            c -= 32
        if not (0x41 <= c <= 0x5A or 0x30 <= c <= 0x39):
            c = 0x2E
        out.append(c)
    if not out:
        return b'X'
    if not 0x41 <= out[0] <= 0x5A:
        out[0] = 0x58
    return bytes(out)


# -- files --------------------------------------------------------------------

def check_movie(data, name=b'MV.'):
    n = len(data)
    if n > MOVIE_MAX:
        raise Refused(E_BIG, name, 'movie')
    if n < 43 or (n - 1) % 42 or data[0] != (n - 1) // 42:
        raise Refused(E_BAD, name, 'length')
    entries = []
    for k in range(data[0]):
        e = data[1 + 42 * k:43 + 42 * k]
        if not (1 <= e[40] <= 17 and 1 <= e[41] <= 17):
            raise Refused(E_BAD, name, 'fade')
        entries.append((e[0:20], e[20:40], e[40], e[41]))
    return entries


def decode_bk(data, name=b'BK.'):
    """The background's 8 KB page (holes zero) or Refused."""
    if len(data) > BK_MAX:
        raise Refused(E_BIG, name)
    page = bytearray(PAGE)
    n = len(data)
    if n < 1 or data[0] != 0xFF:
        raise Refused(E_BAD, name, 'no $FF')
    pos = 1
    for col in range(39, -1, -1):
        row = 0
        while row < ROWS:
            if pos >= n:
                raise Refused(E_BAD, name, 'ends early')
            c = data[pos]
            pos += 1
            if c < 0x80:
                if c == 0:
                    if pos >= n:
                        raise Refused(E_BAD, name, 'ends early')
                    m = data[pos]
                    pos += 1
                    if m == 0:
                        raise Refused(E_BAD, name, 'zero count')
                else:
                    m = c
                if row + m > ROWS:
                    raise Refused(E_BAD, name, 'overflow')
                if pos + m > n:
                    raise Refused(E_BAD, name, 'ends early')
                for i in range(m):
                    page[ROW[row] + col] = data[pos + i]
                    row += 1
                pos += m
            else:
                p = 1 << (c & 3)
                q = (c & 0x7C) >> 2
                if q == 0:
                    if pos >= n:
                        raise Refused(E_BAD, name, 'ends early')
                    q = data[pos] or 256
                    pos += 1
                if pos + p > n:
                    raise Refused(E_BAD, name, 'ends early')
                pat = data[pos:pos + p]
                pos += p
                if row + q > ROWS:
                    raise Refused(E_BAD, name, 'overflow')
                for i in range(q):
                    page[ROW[row] + col] = pat[i % p]
                    row += 1
    return page


def encode_bk(page, rng=None, junk=b''):
    """A background file for a page (test material): random code choices."""
    rng = rng or random.Random(0)
    out = bytearray([0xFF])
    for col in range(39, -1, -1):
        colb = [page[ROW[y] + col] for y in range(ROWS)]
        row = 0
        while row < ROWS:
            left = ROWS - row
            # a repeated pattern?
            best = None
            for e in (0, 1, 2, 3):
                p = 1 << e
                if p > left:
                    break
                q = p
                while q < left and q < 256 and colb[row + q] == colb[row + q % p]:
                    q += 1
                if q >= max(3, p + 1) and (best is None or q > best[1]):
                    best = (e, q)
            if best and rng.random() < 0.8:
                e, q = best
                q = rng.randrange(max(1, min(q, 2)), q + 1)
                if q < 32 and rng.random() < 0.7:
                    out.append(0x80 | (q << 2) | e)
                else:
                    out += bytes([0x80 | e, q & 0xFF])
                out += bytes(colb[row:row + (1 << e)])
                row += q
                continue
            m = rng.randrange(1, min(left, 255) + 1)
            if m < 128 and rng.random() < 0.6:
                out.append(m)
            else:
                out += bytes([0, m])
            out += bytes(colb[row:row + m])
            row += m
    return bytes(out) + junk


class Snapshot:
    __slots__ = ('h', 'w', 'b4', 'sx', 'sy', 'rows')

    def __init__(self, h, w, b4, sx, sy, rows):
        self.h, self.w, self.b4, self.sx, self.sy, self.rows = h, w, b4, sx, sy, rows


def parse_row(data, pos, name):
    """One snapshot row from pos: (list of codes, new pos). Codes:
    ('fill', Q, r, B), ('skip', Q, r), ('lit', bytes), ('ext', q),
    ('end0',), ('end7',)."""
    codes = []
    ext = 0
    n = len(data)
    while True:
        if pos >= n:
            raise Refused(E_BAD, name, 'row past the end')
        c = data[pos]
        pos += 1
        if c == 0x00:
            codes.append(('end0',))
            return codes, pos
        if c == 0x07:
            codes.append(('end7',))
            return codes, pos
        if c & 7 == 7:
            q = c >> 3
            if q <= 25:
                ext += q
                codes.append(('ext', q))
                continue
            k = q - 25
            if pos + k > n:
                raise Refused(E_BAD, name, 'literal past the end')
            codes.append(('lit', bytes(data[pos:pos + k])))
            pos += k
            continue
        groups = ((c >> 3) & 15) + ext
        ext = 0
        if groups > MAX_GROUPS:
            raise Refused(E_BAD, name, 'run too long')
        if c & 0x80:
            codes.append(('skip', groups, c & 7))
        else:
            if pos >= n:
                raise Refused(E_BAD, name, 'fill past the end')
            codes.append(('fill', groups, c & 7, data[pos]))
            pos += 1


def parse_snapshot(data, off, name):
    if off + 7 > len(data):
        raise Refused(E_BAD, name, 'header past the end')
    h, w, _, _, b4, sx, sy = data[off:off + 7]
    pos = off + 7
    rows = []
    for _ in range(h):
        codes, pos = parse_row(data, pos, name)
        rows.append(codes)
    return Snapshot(h, w, b4, sx - 256 if sx > 127 else sx, sy - 256 if sy > 127 else sy, rows)


def check_actor(data, count, name):
    """The snapshots 1..min(count, n) of an actor file: {i: Snapshot}."""
    if len(data) < 1:
        raise Refused(E_BAD, name, 'empty')
    n = data[0]
    snaps = {}
    for i in range(1, min(count, n) + 1):
        if 2 * i >= len(data):
            raise Refused(E_BAD, name, 'offset past the end')
        off = data[2 * i - 1] | data[2 * i] << 8
        snaps[i] = parse_snapshot(data, off, name)
    return n, snaps


def check_cs(data, name):
    """The shapes of a character set: list index 1..N of byte strings."""
    if len(data) < 1 or data[0] == 0:
        raise Refused(E_BAD, name, 'no shapes')
    n = data[0]
    shapes = [None]
    for i in range(1, n + 1):
        if 2 * i + 1 >= len(data):
            raise Refused(E_BAD, name, 'offset past the end')
        off = data[2 * i] | data[2 * i + 1] << 8
        end = off
        while True:
            if end >= len(data):
                raise Refused(E_BAD, name, 'shape past the end')
            if data[end] == 0:
                break
            end += 1
        shapes.append(bytes(data[off:end]))
    return shapes


class Scene:
    pass


def load_scene(sn, loader, name, room=None):
    """Loads and checks a scene, its actors and character set (loader(name,
    room) -> bytes, may raise Refused). Returns a Scene."""
    room = SCENE_MAX if room is None else room
    if len(sn) > room:
        raise Refused(E_BIG, name)
    room -= len(sn)
    if len(sn) < 0x103:
        raise Refused(E_BAD, name, 'short')
    sc = Scene()
    sc.speed = sn[2]
    sc.uses_cs = sn[3] != 0
    a = sn[0x18]
    if a > 10:
        raise Refused(E_BAD, name, 'actors')
    actors = []
    for j in range(a):
        e = sn[0x19 + 22 * j:0x19 + 22 * j + 22]
        actors.append((e[1], dos_name(b'AC.', e[2:22])))
    # files, in order: actors, then the character set
    sc.actors = []
    for count, aname in actors:
        data = loader(aname, room)
        if len(data) > room:
            raise Refused(E_BIG, aname)
        room -= len(data)
        sc.actors.append([count, aname, data])
    sc.cs = None
    if sc.uses_cs:
        csname = dos_name(b'CS.', sn[4:24])
        data = loader(csname, room)
        if len(data) > room:
            raise Refused(E_BIG, csname)
        room -= len(data)
        sc.cs_name = csname
        sc.cs_data = data
    # checks: actors, character set, then the scene's body
    sc.snap = {}
    num = 0
    for count, aname, data in sc.actors:
        n, snaps = check_actor(data, count, aname)
        for i in range(1, count + 1):
            sc.snap[num + i] = snaps.get(i)      # None: above the actor's own count
        num += count
    sc.nsnaps = num
    if sc.uses_cs:
        sc.cs = check_cs(sc.cs_data, sc.cs_name)
    body = sn[0x100:]
    nb = len(body)
    first = body[0] | body[1] << 8
    if first >= nb:
        raise Refused(E_BAD, name, 'frames outside')
    s = body[2]
    pos = 3
    sc.strings = [None]
    for _ in range(s):
        if pos >= nb:
            raise Refused(E_BAD, name, 'strings past the end')
        ln = body[pos]
        if pos + 1 + ln > nb:
            raise Refused(E_BAD, name, 'string past the end')
        sc.strings.append(bytes(body[pos + 1:pos + 1 + ln]))
        pos += 1 + ln
    frames = []
    cur = []
    pos = first
    while True:
        if pos >= nb:
            raise Refused(E_BAD, name, 'no end marker')
        o = body[pos]
        if o == 0xFF:
            break
        if o == 0x00:
            raise Refused(E_BAD, name, 'element $00')
        if 0xF0 <= o <= 0xFB or o == 0xFD:
            cur.append(('fill',))
            pos += 1
            continue
        if pos + 4 > nb:
            raise Refused(E_BAD, name, 'element past the end')
        el = body[pos:pos + 4]
        pos += 4
        if o == 0xFE:
            cur.append(('empty',))
            frames.append(cur)
            cur = []
            continue
        if o == 0xFC:
            cur.append(('fc', el[1], el[2], el[3]))
            if el[2] & 0x80:
                frames.append(cur)
                cur = []
            continue
        xl, f, yl = el[1], el[2], el[3]
        if f & 0x40:
            if not sc.uses_cs:
                raise Refused(E_BAD, name, 'text without a character set')
            if o > s:
                raise Refused(E_BAD, name, 'string number')
            x16 = xl + 256 * (f & 3)
            y16 = yl + 256 * ((f >> 3) & 1)
            if not (f & 0x10 and 280 <= x16 < 560 and 192 < y16 < 384):
                raise Refused(E_BAD, name, 'text outside the screen')
        else:
            if o > num:
                raise Refused(E_BAD, name, 'snapshot number')
            if sc.snap[o] is None:
                # the actor holding it has fewer snapshots
                k, j = o, 0
                while k > sc.actors[j][0]:
                    k -= sc.actors[j][0]
                    j += 1
                raise Refused(E_BAD, sc.actors[j][1], 'snapshot number')
        cur.append(('obj', o, xl, f, yl))
        if f & 0x80:
            frames.append(cur)
            cur = []
    if cur:
        frames.append(cur)
    sc.frames = frames
    return sc


# -- drawing ------------------------------------------------------------------

P3_OR = 0x03          # the register's OR value before any run: (b & $7F) | 3


def fill_bit(B, j):
    if j < 7:
        return (B >> j) & 1
    return (B >> (3 + (j - 3) % 4)) & 1


# The work of a frame, for the spec's model of the original's own time
# (docs, Timing): row codes, screen bytes written, snapshots, text shape
# bytes, bytes erased, full page copies; and, for the player's own cost
# only: snapshot rows drawn, objects drawn or tried, and the whole bytes of
# runs (stb: see Row.count_stb). Player.work_log keeps one per frame shown.
WORK = dict(codes=0, bytes=0, snaps=0, shapes=0, erased=0, fulls=0, rows=0, objs=0, stb=0)
MODEL = dict(codes=140, bytes=55, snaps=1700, shapes=280, erased=20, fulls=79000)
COUNTERS = ('codes', 'bytes', 'snaps', 'shapes', 'erased', 'fulls', 'rows', 'objs', 'stb')


def own_constants():
    """OWN_BASE and OWN_* of engine.s: the player's own cost, fitted on its
    code (test_take1.py --calibrate)."""
    root = Path(__file__).resolve().parents[1]
    text = (root / 'src/take1/engine.s').read_text()
    got = {m[1].lower(): int(m[2]) for m in re.finditer(r'^OWN_(\w+)\s*=\s*(-?\d+)', text, re.M)}
    return got.pop('base'), got


OWN_BASE, OWN = own_constants()


def model_cycles(w):
    return sum(MODEL[k] * w[k] for k in MODEL)


def hold_cycles(w, n):
    """The original speed: the time to wait after a frame is shown, so that
    it stays shown for the original's modelled time (erase and draw, plus
    the exact frame wait of n steps), less the player's own estimated cost
    for the same work; never negative. The counters are 16-bit, as the
    engine keeps them."""
    c = {k: w[k] & 0xFFFF for k in COUNTERS}
    target = sum(MODEL[k] * c[k] for k in MODEL) + 350 * n + 18 * (n >> 2)
    own = OWN_BASE + sum(OWN[k] * c[k] for k in COUNTERS)
    return max(0, target - own)


class Row:
    """One snapshot row drawn with the byte accumulator."""

    def __init__(self, page, y, X, wrap, reg):
        self.page, self.base, self.X, self.wrap = page, ROW[y], X, wrap
        self.p = X
        self.ab = X // 7          # the byte the accumulator holds
        self.d = 0
        self.mask = 0
        self.data = 0
        self.reg = reg            # OR value: 0, $80 or P3_OR

    def screen_col(self):
        ab = self.ab
        if ab < 0:
            return None
        if self.wrap:
            return ab % 40
        return ab if ab < 40 else None

    def flush(self, keep=False, forced=False):
        c = self.screen_col()
        if c is not None and (self.mask or forced):
            a = self.base + c
            v = (self.page[a] & ~self.mask & 0xFF) | self.data
            # keep: the closing black dot of a skip on bit 6 sets no bit 7;
            # earlier dots of the row in this byte gave it the register's
            if not keep or self.mask & 0x3F:
                v = (v & 0x7F) | self.reg
            self.page[a] = v
            WORK['bytes'] += 1
        self.mask = self.data = 0
        self.ab = self.p // 7

    def put(self, v):
        b = 1 << (self.p % 7)
        self.mask |= b
        if v:
            self.data |= b

    def step(self, keep=False):
        self.p += 1
        self.d += 1
        if self.p % 7 == 0:
            self.flush(keep)

    def move(self, n):
        for _ in range(n):
            self.step()

    def run(self, n, B, lit=False):
        if not lit:
            self.count_stb(n)
        if self.wrap or self.p < 280:
            self.reg = B & 0x80
        for j in range(n):
            self.put(fill_bit(B, j))
            self.step()

    def count_stb(self, n):
        """The whole bytes of a run (all 7 dots from it) on the screen, which
        the engine stores at once: counted (stb, the engine's own cost).
        Without wrap, none past column 39 (the row goes no further)."""
        p = self.p
        ab = -(-p // 7)                 # the first byte starting at or after p
        while 7 * ab + 7 <= p + n:
            if ab >= 0:
                if not self.wrap and ab >= 40:
                    break
                WORK['stb'] += 1
            ab += 1

    def draw(self, codes):
        first = True
        for code in codes:
            WORK['codes'] += 1
            k = code[0]
            if k == 'ext':
                continue
            if k == 'end0':
                if not first:
                    if self.wrap and self.X >= 0 and self.d == 280:
                        self.flush(forced=True)
                    else:
                        self.put(0)
                        self.flush()
                return self.reg
            if k == 'end7':
                if self.p % 7:
                    self.flush(forced=True)
                return self.reg
            if k == 'lit':
                for B in code[1]:
                    self.run(7, B, lit=True)
            elif k == 'fill':
                self.run(7 * code[1] + code[2], code[3])
            else:
                n = 7 * code[1] + code[2]
                if first:
                    self.move(n)
                    self.put(0)
                    self.step(keep=True)
                elif n == 0:
                    self.put(0)
                    self.step()
                else:
                    self.put(0)
                    self.step()
                    self.move(n - 1)
                    self.put(0)
                    self.step(keep=True)
            first = False
        raise AssertionError('row without an end')


def place(snap, xl, f, yl):
    """Where a snapshot object goes: (X, top, skip, rect or None)."""
    x16 = xl + 256 * (f & 3)
    y16 = yl + 256 * ((f >> 3) & 1)
    wrap = bool(f & 0x10)
    if snap.sx:
        x16 = max(x16 + snap.sx, 0)
        if wrap:
            if x16 < 280:
                x16 += 280
            elif x16 >= 560:
                x16 -= 280
        else:
            x16 = min(x16, 687)
    if snap.sy:
        y16 = max(y16 + snap.sy, 0)
        if wrap:
            if y16 < 192:
                y16 += 192
            elif y16 >= 384:
                y16 -= 192
        else:
            y16 = min(y16, 511)
    X = x16 - 280
    skip = 0
    if not wrap:
        if y16 <= 192:
            skip, top = 192 - y16, 0
        else:
            top = y16 - 192
    elif 192 <= y16 < 384:
        top = y16 - 192
    elif y16 < 192:
        top = y16 + 64
    else:
        top = 192
    A, wb = snap.w, 0
    if snap.b4 & 1:
        A, wb = snap.w + 4, 36
    while A >= 8:
        wb += 1
        A -= 7
    wb = min(wb + 2, 40)
    c = min(X // 7, 40)
    col = max(c, 0)
    if col == 40:
        return X, top, skip, None
    width = wb
    if c < 0:
        width = wb + c + 1
        if width <= 0:
            return X, top, skip, None
    if not wrap and col + width >= 40:
        width = 40 - col
    if top >= 192:
        return X, top, skip, None
    height = snap.h - skip
    if height < 0:
        return X, top, skip, None
    return X, top, skip, (col, width, top, height)


def draw_snapshot(page, snap, xl, f, yl):
    """Draws a snapshot object; returns its rectangle or None."""
    X, top, skip, rect = place(snap, xl, f, yl)
    if rect is None:
        return None
    WORK['snaps'] += 1
    wrap = bool(f & 0x10)
    reg = P3_OR
    y = top
    for r in range(skip, snap.h):
        if not wrap and y > 191:
            break
        WORK['rows'] += 1
        reg = Row(page, y, X, wrap, reg).draw(snap.rows[r])
        y += 1
        if wrap and y == 192:
            y = 0
    return rect


def draw_text(page, shapes, string, xl, f, yl):
    """XDRAW of a string; returns (rectangle, shape bytes drawn)."""
    x = xl + 256 * (f & 3) - 280
    y = yl + 256 * ((f >> 3) & 1) - 192
    left = right = x
    top = bottom = y
    width = height = 1
    nbytes = 0
    n = len(shapes) - 1
    for ch in string:
        num = ch - 31
        if not 1 <= num <= n:
            num = 1
        for b in shapes[num]:
            nbytes += 1
            WORK['shapes'] += 1
            vecs = [b & 7]
            b >>= 3
            if b:
                vecs.append(b & 7)
                b >>= 3
                if b:
                    vecs.append(b & 3)      # C: a move, no plot
            for i, v in enumerate(vecs):
                if i < 2 and v & 4:
                    page[ROW[y] + x // 7] ^= 1 << (x % 7)
                m = v & 3
                if m == 0:
                    ny = 191 if y == 0 else y - 1
                    if y == top:
                        top = ny
                        height = min(height + 1, 255)
                    y = ny
                elif m == 2:
                    ny = 0 if y == 191 else y + 1
                    if y == bottom:
                        bottom = ny
                        height = min(height + 1, 255)
                    y = ny
                elif m == 1:
                    nx = 0 if x == 279 else x + 1
                    if x == right:
                        if nx // 7 != right // 7:
                            width = min(width + 1, 255)
                        right = nx
                    x = nx
                else:
                    nx = 279 if x == 0 else x - 1
                    if x == left:
                        if nx // 7 != left // 7:
                            width = min(width + 1, 255)
                        left = nx
                    x = nx
    return (left // 7, min(width, 40), top, min(height, 192)), nbytes


# -- the projector ------------------------------------------------------------

class RectList:
    def __init__(self):
        self.rects, self.area, self.full = [], 0, False

    def add(self, r):
        if self.full:
            return
        if len(self.rects) == MAX_RECTS:
            self.full = True
            return
        self.rects.append(r)
        self.area += r[1] * r[3]
        if self.area >= AREA_FULL:
            self.full = True

    def apply(self, dst, src):
        """Erases dst from page 3; returns its cost."""
        if self.full:
            dst[:] = src
            cost = FULL_COST
            WORK['fulls'] += 1
        else:
            for col, width, top, height in self.rects:
                for r in range(height):
                    a = ROW[(top + r) % 192]
                    for c in range(width):
                        dst[a + (col + c) % 40] = src[a + (col + c) % 40]
            cost = self.area
            WORK['erased'] += self.area
        self.rects, self.area, self.full = [], 0, False
        return cost


def delay_cycles(a):
    a = a or 256
    return (5 * a * a + 27 * a + 26) // 2


def frame_wait(speed, cost):
    """The number of 350-cycle steps waited after a frame."""
    if 4 * cost >= 65536:
        return 0
    num = 256 * speed - 4 * cost
    return (num + 63) // 64 if num > 0 else 0


def wait_cycles(n):
    return 350 * n + 18 * (n // 4)


def fade_ops(num):
    """The fade as an ordered list of operations: ('c', row, col) copy one
    byte, ('s', row) stripe a row (without its delay), ('b', a, b, src)
    block copy (src True: from the source, else the destination itself),
    ('d', a) a delay D(a), ('t',) the engine's tick (fade 14, no time)."""
    ops = []

    def row(x):
        for y in range(39, -1, -1):
            ops.append(('c', x, y))

    def stripe(x):
        ops.append(('s', x))
        ops.append(('d', 30))

    def band(x, fa, f5, f6):
        if fa:
            ops.append(('c', x, f5))
            ops.append(('c', x, f6))
        else:
            y = f5
            while True:
                ops.append(('c', x, y))
                if y == f6:
                    break
                y -= 1
                if y < 0:
                    break

    if num in (2, 3):
        cols = range(40) if num == 2 else range(39, -1, -1)
        for y in cols:
            for x in range(192):
                ops.append(('c', x, y))
            ops.append(('d', 40))
    elif num in (4, 6):
        for x in (range(191, -1, -1) if num == 4 else range(192)):
            row(x)
            ops.append(('d', 30))
    elif num in (5, 7):
        for x in (range(191, -1, -1) if num == 5 else range(192)):
            stripe(x)
            row(x)
    elif num in (8, 13):
        step, delay = (1, 30) if num == 8 else (2, 45)
        up = dn = x = 96
        while True:
            row(x)
            ops.append(('d', delay))
            if x >= 96:
                up = (up - step) & 255
                x = up
                if x < 128:
                    continue
            dn = dn + step
            x = dn
            if x < 192:
                continue
            if num == 13 and x == 192:
                up, dn, x = 97, 95, 95
                continue
            break
    elif num == 9:
        stripe(95)
        stripe(96)
        for k in range(96):
            row(96 + k)
            if 97 + k < 192:
                stripe(97 + k)
            row(95 - k)
            if 94 - k >= 0:
                stripe(94 - k)
    elif num == 10:
        f7, f6, f5, fa = 186, 0, 39, 0
        row(0)
        while True:
            f9 = min(186 - f7, 95)
            f8 = max(f7 + 5, 96)
            x = f8
            while True:
                band(x, fa, f5, f6)
                ops.append(('d', 1))
                if x >= 97:
                    f9 += 1
                    x = f9
                    continue
                f8 -= 1
                x = f8
                if x < 96:
                    break
                if x == f7:
                    fa = 1
            f7 = (f7 - 5) & 255
            fa = 0
            f6 += 1
            ops.append(('d', (f6 * 4) & 255))
            f5 -= 1
            if f5 < 20:
                break
    elif num == 11:
        f7, f6, f5, fa = 5, 19, 20, 0
        while True:
            f9 = f8 = x = 96
            while True:
                band(x, fa, f5, f6)
                ops.append(('d', 2))
                if x >= 96:
                    f9 = (f9 - 1) & 255
                    x = f9
                    if x < 128:
                        continue
                f8 += 1
                x = f8
                if x - 96 < f7:
                    continue
                if fa:
                    f7 = min(f7 + 5, 96)
                    fa = 0
                    continue
                break
            fa = 1
            f6 -= 1
            f5 += 1
            if f5 >= 40:
                break
    elif num == 12:
        for i in range(384):
            if i % 2 == 0:
                x, cols = i // 2, range(39, 0, -2)
            else:
                x, cols = 191 - i // 2, range(38, -1, -2)
            for y in cols:
                ops.append(('c', x, y))
            ops.append(('d', 24))
    elif num == 14:
        f7, f6 = 191, 39
        while True:
            ops.append(('t',))
            x, y = f7, f6
            while True:
                for _ in range(6):
                    ops.append(('c', x, y))
                    if x == 0:
                        break
                    x -= 1
                y += 1
                if y == 40:
                    break
            f6 -= 1
            if f6 >= 0:
                continue
            f6 = 0
            if f7 < 6:
                break
            f7 -= 6
    elif num == 15:
        for y0 in (39, 31):
            for g in range(32):
                for k in range(6):
                    x = g + 32 * k
                    y = y0 if k % 2 == 0 else y0 ^ 56
                    for start in (y, y - 16, y - 32):
                        if start < 0:
                            break
                        stop = False
                        for c in range(start, start - 8, -1):
                            if c < 0:
                                stop = True
                                break
                            ops.append(('c', x, c))
                        if stop:
                            break
                ops.append(('d', 25))
            ops.append(('d', 48))
    elif num in (16, 17):
        if num == 16:
            first, step, last, end = 0, 8, 184, 192
        else:
            first, step, last, end = 184, -8, 0, -8
        s = first
        while True:
            x = first
            while True:
                ops.append(('b', x, x + step, False))
                x += step
                if x == last:
                    break
                ops.append(('d', 20))
            ops.append(('b', x, s, True))
            s += step
            if s == end:
                break
            ops.append(('d', 20))
    else:
        raise ValueError(num)
    return ops


def run_fade(num, src, dst):
    """Applies a fade; yields ('delay', a, page) at each D(a) and ('tick',
    page) at each tick of fade 14."""
    for op in fade_ops(num):
        k = op[0]
        if k == 'c':
            a = ROW[op[1]] + op[2]
            dst[a] = src[a]
        elif k == 's':
            a = ROW[op[1]]
            for y in range(39, 0, -2):
                dst[a + y] = 0xAA
                dst[a + y - 1] = 0xD5
        elif k == 'b':
            frm = src if op[3] else dst
            for y in range(39, -1, -1):
                for i in range(8):
                    dst[ROW[op[1] + i] + y] = frm[ROW[op[2] + i] + y]
        elif k == 'd':
            yield ('delay', op[1], bytes(dst))
        else:
            yield ('tick', bytes(dst))


class Player:
    """The movie flow. play() yields events:
         ('show', page, bytes)   a frame shown (page 1 or 2)
         ('wait', n, hold)       the original speed's hold, in cycles: before
                                 a frame is shown (hold_cycles: the work
                                 since the last one, plus n, the frame wait
                                 the last one owes), right after it when it
                                 has a $FC element (wait_cycles(n) alone),
                                 and at a scene's end
         ('fc', kind, t)         a $FC element after its frame
         ('fade', num)           a fade starts
         ('delay', a, bytes)     a D(a) of a fade, the shown page then
         ('tick', bytes)         fade 14's tick, the shown page then
         ('end',)                the movie is over (the player holds, loops)
       and raises Refused for a file it cannot draw."""

    def __init__(self, movie, loader, scene_max=None, movie_name=b'MV.'):
        self.movie, self.loader, self.movie_name = movie, loader, movie_name
        self.scene_max = SCENE_MAX if scene_max is None else scene_max
        self.pages = {1: bytearray(PAGE), 2: bytearray(PAGE), 3: bytearray(PAGE)}
        self.front = 1
        self.lists = {1: RectList(), 2: RectList()}
        self.work_log = []
        for k in WORK:
            WORK[k] = 0

    def load(self, name, room):
        return self.loader(name, room)

    def play(self):
        entries = check_movie(self.movie, self.movie_name)
        P = self.pages
        for p in P.values():
            p[:] = bytes(PAGE)
        self.front = 1
        for scene_name, bg, fade_in, fade_out in entries:
            bgn = field_name(bg)
            if bgn == BLACK:
                P[3][:] = bytes(PAGE)
            elif bgn == UNCHANGED:
                pass
            else:
                name = dos_name(b'BK.', bg)
                data = self.load(name, BK_MAX)
                P[3][:] = decode_bk(data, name)
            name = dos_name(b'SN.', scene_name)
            sn = self.load(name, self.scene_max)
            sc = load_scene(sn, self.load, name, self.scene_max)
            yield from self.scene(sc, fade_in, fade_out)
        yield ('end',)

    def draw(self, sc, page, obj):
        """Draws an object; (rect or None, cost)."""
        _, o, xl, f, yl = obj
        WORK['objs'] += 1
        if f & 0x40:
            rect, nb = draw_text(page, sc.cs, sc.strings[o], xl, f, yl)
            return rect, 11 * nb
        rect = draw_snapshot(page, sc.snap[o], xl, f, yl)
        return rect, (2 * rect[1] * rect[3] if rect else 0)

    def scene(self, sc, fade_in, fade_out):
        P, L = self.pages, self.lists
        back = 3 - self.front
        P[back][:] = P[3]
        L[1], L[2] = RectList(), RectList()
        L[back].full = True
        cost = 0
        shown_any = False
        owed = 0                # the frame wait n owed to the frame before
        for fi, frame in enumerate(sc.frames):
            back = 3 - self.front
            i = 0
            while i < len(frame) and frame[i][0] == 'obj' and frame[i][3] & 0x20:
                rect, c = self.draw(sc, P[3], frame[i])
                cost += c
                if rect:
                    L[1].add(rect)
                    L[2].add(rect)
                i += 1
            cost += L[back].apply(P[back], P[3])
            fc = None
            for el in frame[i:]:
                if el[0] == 'obj':
                    rect, c = self.draw(sc, P[back], el)
                    cost += c
                    if rect:
                        L[back].add(rect)
                elif el[0] == 'fc':
                    fc = el
            cost = min(cost, 65535)
            if fi == 0 and fade_in > 1:
                yield ('fade', fade_in)
                yield from run_fade(fade_in, P[back], P[self.front])
                cost = min(cost + L[back].apply(P[back], P[3]), 65535)
            else:
                # the original speed: before the frame is shown, the hold
                # for the work since the last one, with the wait owed
                work = dict(WORK, first=not shown_any, n=owed)
                self.work_log.append(work)
                yield ('wait', owed, hold_cycles(work, owed))
                for k in WORK:
                    WORK[k] = 0
                self.front = back
                back = 3 - back
                yield ('show', self.front, bytes(P[self.front]))
                owed = frame_wait(sc.speed, cost)
                cost = 0
                if not shown_any:
                    L[back].full = True
                    shown_any = True
                cost += L[back].apply(P[back], P[3])
                if fc:                  # a $FC element: the wait first
                    yield ('wait', owed, wait_cycles(owed))
                    owed = 0
            if fc:
                yield ('fc', fc[2] & 0x7F, fc[1])
        # the scene's end: the last frame's wait, the work since it
        yield ('wait', owed, hold_cycles(dict(WORK), owed))
        for k in WORK:
            WORK[k] = 0
        if fade_out > 1:
            back = 3 - self.front
            P[back][:] = bytes(PAGE)
            yield ('fade', fade_out)
            yield from run_fade(fade_out, P[back], P[self.front])
            P[3][:] = bytes(PAGE)


# -- loaders --------------------------------------------------------------------

class DosImage:
    """A DOS 3.3 disk image, DOS order (from offset `base`)."""

    def __init__(self, data, base=0):
        self.data, self.base = data, base

    def sector(self, t, s):
        if s > 15:
            raise IOError('sector')
        a = self.base + (16 * t + s) * 256
        if a + 256 > len(self.data):
            raise IOError('past the end')
        return self.data[a:a + 256]

    def find(self, name):
        """The first T/S list of the file named name (low 7 bits, spaces
        trimmed), the first match in the catalog's order; None if absent;
        IOError if the catalog cannot be read up to there."""
        vtoc = self.sector(17, 0)
        t, s = vtoc[1], vtoc[2]
        count = 0
        while t:
            count += 1
            if count > 560:
                raise IOError('catalog loop')
            sec = self.sector(t, s)
            for i in range(7):
                e = sec[11 + 35 * i:46 + 35 * i]
                if e[0] == 0:
                    return None
                if e[0] == 0xFF:
                    continue
                if bytes(b & 0x7F for b in e[3:33]).rstrip(b' ') == name:
                    return e[0], e[1]
            t, s = sec[1], sec[2]
        return None

    def read_file(self, t, s, limit=1 << 20):
        """The data of a binary file (after its 4-byte header)."""
        out = bytearray()
        need = None
        count = 0
        while True:
            count += 1
            if count > 560:
                raise IOError('chain loop')
            ts = self.sector(t, s)
            for i in range(122):
                pt, ps = ts[12 + 2 * i], ts[13 + 2 * i]
                if pt == 0 and ps == 0:
                    out += bytes(256)
                else:
                    count += 1
                    if count > 560:
                        raise IOError('too long')
                    out += self.sector(pt, ps)
                if need is None and len(out) >= 4:
                    need = 4 + (out[2] | out[3] << 8)
                    if need - 4 > limit:
                        raise OverflowError
                if need is not None and len(out) >= need:
                    return bytes(out[4:need])
            t, s = ts[1], ts[2]
            if t == 0 and s == 0:
                raise IOError('runs short')


def image_loader(img):
    def load(name, room):
        try:
            where = img.find(name)
            if where is None:
                raise Refused(E_NOTFOUND, name)
            return img.read_file(*where, limit=room)
        except OverflowError:
            raise Refused(E_BIG, name)
        except IOError:
            raise Refused(E_READ, name)
    return load


def dir_loader(directory):
    directory = Path(directory)

    def load(name, room):
        p = directory / prodos_name(name).decode()
        if not p.exists():
            raise Refused(E_NOTFOUND, name)
        data = p.read_bytes()
        if len(data) > room:
            raise Refused(E_BIG, name)
        return data
    return load


def dict_loader(files):
    def load(name, room):
        if name not in files:
            raise Refused(E_NOTFOUND, name)
        if len(files[name]) > room:
            raise Refused(E_BIG, name)
        return files[name]
    return load


def make_dsk(files, movie_ts=False):
    """A DOS 3.3 140K image (DOS order) holding binary files {name: data}
    (test material). Returns (image, {name: (t, s) of its T/S list})."""
    img = bytearray(35 * 16 * 256)
    alloc = [(t, s) for t in list(range(18, 35)) + list(range(16, 0, -1)) if t != 17
             for s in range(15, -1, -1)]
    pos = 0

    def take():
        nonlocal pos
        r = alloc[pos]
        pos += 1
        return r

    def put(t, s, data):
        a = (16 * t + s) * 256
        img[a:a + len(data)] = data

    where = {}
    entries = []
    for name, data in files.items():
        body = bytes([0, 0x20, len(data) & 255, len(data) >> 8]) + data
        secs = [body[i:i + 256] for i in range(0, len(body), 256)] or [b'']
        lists = [take() for _ in range((len(secs) + 121) // 122)]
        for li, (lt, ls) in enumerate(lists):
            ts = bytearray(256)
            if li + 1 < len(lists):
                ts[1], ts[2] = lists[li + 1]
            for k, sec in enumerate(secs[li * 122:(li + 1) * 122]):
                if sec.strip(b'\0') == b'' and len(sec) == 256 and k % 3 == 1:
                    continue          # a hole: zeros
                st, ss = take()
                put(st, ss, sec)
                ts[12 + 2 * k], ts[13 + 2 * k] = st, ss
            put(lt, ls, ts)
        where[name] = lists[0]
        entries.append((lists[0], name, len(secs) + len(lists)))
    vtoc = bytearray(256)
    vtoc[1], vtoc[2], vtoc[3] = 17, 15, 3
    put(17, 0, vtoc)
    cat = [(17, s) for s in range(15, 0, -1)]
    for ci, (ct, cs) in enumerate(cat):
        sec = bytearray(256)
        if ci + 1 < len(cat):
            sec[1], sec[2] = cat[ci + 1]
        for i in range(7):
            k = ci * 7 + i
            if k >= len(entries):
                break
            (t, s), name, n = entries[k]
            e = bytearray(35)
            e[0], e[1], e[2] = t, s, 0x04
            nb = name.encode('latin-1') if isinstance(name, str) else name
            e[3:33] = bytes(c | 0x80 for c in nb.ljust(30)[:30])
            e[33], e[34] = n & 255, n >> 8
            sec[11 + 35 * i:46 + 35 * i] = e
        put(ct, cs, sec)
    return bytes(img), where


# -- synthetic material -------------------------------------------------------

def rand_row(rng, wide=False, kind=None):
    """Random codes of one snapshot row (bytes), ending with $00 or $07."""
    out = bytearray()
    n = rng.randrange(0, 7)
    for _ in range(n):
        r = rng.random()
        if r < 0.12:
            out.append(((rng.randrange(1, 4 if not wide else 26)) << 3) | 7)   # extension
            continue
        if r < 0.3:
            k = rng.randrange(1, 7)
            out.append(((25 + k) << 3) | 7)
            out += bytes(rng.randrange(256) for _ in range(k))
        elif r < 0.6:
            q, lo = rng.randrange(0, 4 if not wide else 16), rng.randrange(0, 7)
            out.append(0x80 | (q << 3) | lo)
        else:
            q, lo = rng.randrange(0, 4 if not wide else 16), rng.randrange(0, 7)
            if q == 0 and lo == 0:
                lo = rng.randrange(1, 7)
            out += bytes([(q << 3) | lo, rng.randrange(256)])
    out.append(0x07 if (kind == 7 or (kind is None and rng.random() < 0.3)) else 0x00)
    return bytes(out)


def rand_snapshot(rng, h=None, wide=False):
    h = rng.randrange(1, 14) if h is None else h
    w = rng.randrange(1, 256)
    b4 = rng.choice([0, 0, 0, 1, 2, 3])
    sx = rng.choice([0, 0, rng.randrange(256)])
    sy = rng.choice([0, 0, rng.randrange(256)])
    kind = rng.choice([None, None, 7, 0])
    rows = b''.join(rand_row(rng, wide, kind) for _ in range(h))
    return bytes([h, w, rng.randrange(256), rng.randrange(256), b4, sx, sy]) + rows


def make_actor(snaps, actions=b'\x00'):
    n = len(snaps)
    off = 1 + 2 * n + 2
    table = bytearray([n])
    body = bytearray()
    for s in snaps:
        table += bytes([(off + len(body)) & 255, (off + len(body)) >> 8])
        body += s
    act = off + len(body)
    table += bytes([act & 255, act >> 8])
    return bytes(table + body + actions)


def make_cs(shapes):
    n = len(shapes)
    out = bytearray([n, 0])
    off = 2 + 2 * n
    body = bytearray()
    for s in shapes:
        out += bytes([(off + len(body)) & 255, (off + len(body)) >> 8])
        body += s + b'\x00'
    return bytes(out + body)


def rand_shape(rng):
    n = rng.randrange(0, 6)
    out = bytearray()
    for _ in range(n):
        b = rng.randrange(1, 256)
        out.append(b)
    return bytes(out)


def name20(s, hi=False):
    b = s.encode('latin-1').ljust(20)[:20]
    return bytes(c | 0x80 for c in b) if hi else b


def make_scene(speed, actors, frames, strings=(), cs=None, junk=0, first_gap=0):
    """actors: [(count, name)], frames: list of element byte strings (each
    complete with its end flag), cs: name or None."""
    h = bytearray(0x100)
    h[0], h[1] = (len(frames) + 1) & 255, (len(frames) + 1) >> 8
    h[2] = speed
    if cs is not None:
        h[3] = 1
        h[4:24] = name20(cs)
    else:
        h[4:24] = b'LEFTOVER BYTES HERE!'
    h[0x18] = len(actors)
    for j, (count, name) in enumerate(actors):
        e = bytes([count, count]) + name20(name)
        h[0x19 + 22 * j:0x19 + 22 * j + 22] = e
    body = bytearray([0, 0, len(strings)])
    for s in strings:
        body += bytes([len(s)]) + s
    body += bytes(first_gap)
    first = len(body)
    body[0], body[1] = first & 255, first >> 8
    for fr in frames:
        body += fr
    body.append(0xFF)
    body += bytes(junk)
    return bytes(h + body)


def make_movie(entries):
    out = bytearray([len(entries)])
    for scene, bg, fin, fout in entries:
        out += name20(scene, True) + name20(bg, True) + bytes([fin, fout])
    return bytes(out)


def obj(o, x16, y16, wrap=False, plant=False, text=False, end=False):
    f = (x16 >> 8) & 3 | ((y16 >> 8) & 1) << 3
    f |= 0x10 if wrap else 0
    f |= 0x20 if plant else 0
    f |= 0x40 if text else 0
    f |= 0x80 if end else 0
    return bytes([o, x16 & 255, f, y16 & 255])


def rand_frames(rng, nsnaps, nstrings, nframes, wide_pos=True):
    """Frames of random elements, each list ending with its end flag."""
    frames = []
    for _ in range(nframes):
        els = []                 # [kind, bytearray]
        k = rng.randrange(0, 6)
        plant_lead = rng.random() < 0.3
        for i in range(k):
            plant = plant_lead and i < 2 or rng.random() < 0.05
            if nstrings and rng.random() < 0.15:
                els.append(['o', bytearray(obj(rng.randrange(1, nstrings + 1), rng.randrange(280, 560),
                                               rng.randrange(193, 384), wrap=True, plant=plant,
                                               text=True))])
            elif nsnaps:
                wrap = rng.random() < 0.4
                if rng.random() < 0.5:
                    x16 = rng.randrange(1024) if wide_pos else rng.randrange(200, 600)
                    y16 = rng.randrange(512) if wide_pos else rng.randrange(150, 420)
                else:
                    x16 = rng.choice([0, 1, 270, 279, 280, 281, 286, 287, 300, 553, 555, 559,
                                      560, 561, 680, 687, 700, rng.randrange(1024)])
                    y16 = rng.choice([0, 100, 150, 191, 192, 193, 250, 370, 383, 384, 400,
                                      511, rng.randrange(512)])
                els.append(['o', bytearray(obj(rng.randrange(1, nsnaps + 1), x16, y16, wrap=wrap,
                                               plant=plant))])
            if rng.random() < 0.05:
                els.append(['1', bytearray([rng.choice([0xF0, 0xF5, 0xFB, 0xFD])])])
        if rng.random() < 0.25:
            for _ in range(rng.randrange(1, 3)):
                els.append(['c', bytearray([0xFC, rng.randrange(256), rng.randrange(4),
                                            rng.randrange(256)])])
        if not els or els[-1][0] == '1' or rng.random() < 0.15:
            els.append(['e', bytearray([0xFE, rng.randrange(256), rng.randrange(256),
                                        rng.randrange(256)])])
        else:
            els[-1][1][2] |= 0x80
        frames.append(b''.join(bytes(e[1]) for e in els))
    return frames


def synthetic(seed, scenes=None, frames=None, fades=True, wide=None):
    """A random movie with its files: (movie bytes, {DOS name: bytes})."""
    rng = random.Random(seed)
    files = {}
    nsc = scenes or rng.randrange(1, 4)
    entries = []
    for k in range(nsc):
        na = rng.randrange(0, 4)
        actors = []
        for j in range(na):
            nm = 'A%d %d' % (seed, rng.randrange(1000))
            snaps = [rand_snapshot(rng, wide=wide if wide is not None else rng.random() < 0.3)
                     for _ in range(rng.randrange(1, 5))]
            files[b'AC.' + nm.encode()] = make_actor(snaps)
            count = len(snaps) if rng.random() < 0.8 else max(0, len(snaps) - 1)
            actors.append((count, nm))
        strings = [bytes(rng.randrange(0x20, 0x80) for _ in range(rng.randrange(0, 6)))
                   for _ in range(rng.randrange(0, 4))]
        cs = None
        if strings or rng.random() < 0.3:
            cs = 'FONT%d' % rng.randrange(10)
            shapes = [rand_shape(rng) for _ in range(rng.randrange(1, 70))]
            files[b'CS.' + cs.encode()] = make_cs(shapes)
        nsn = sum(c for c, _ in actors)
        nf = frames or rng.randrange(1, 7)
        fr = rand_frames(rng, nsn, len(strings), nf)
        sname = 'SC%d.%d' % (seed, k)
        files[b'SN.' + sname.encode()] = make_scene(rng.randrange(1, 90), actors, fr, strings, cs,
                                                    junk=rng.randrange(3))
        bgr = rng.random()
        if bgr < 0.3:
            bg = '< BLACK >'
        elif bgr < 0.5 and k:
            bg = '< UNCHANGED >'
        else:
            bg = 'BG%d' % rng.randrange(5)
            if b'BK.' + bg.encode() not in files:
                page = bytearray(PAGE)
                base = rng.randrange(256)
                for y in range(ROWS):
                    for c in range(40):
                        page[ROW[y] + c] = (base + (c // 5) * 17 + (y // 9) * 3) & 255 \
                            if rng.random() < 0.9 else rng.randrange(256)
                files[b'BK.' + bg.encode()] = encode_bk(page, rng)
        fin = rng.choice([1, 1, rng.randrange(2, 18)]) if fades else 1
        fout = rng.choice([1, 1, rng.randrange(2, 18)]) if fades else 1
        entries.append((sname, bg, fin, fout))
    return make_movie(entries), files


def crafted(kind, seed=0):
    """Movies aimed at one rule: (movie, files).
       'fades'  every fade in and out, 2-17
       'seam'   rows of 279, 280 and 281 dots, wrapped from every dot
       'wide'   tall, full-width snapshots with long runs and syncs
       'many'   more than 20 rectangles, and areas past 3,328
       'text'   strings of every character, pens wrapping round
       'plant'  planted objects, BLACK and UNCHANGED, fade-out to black"""
    rng = random.Random(seed * 101 + len(kind))
    files = {}
    entries = []
    if kind == 'bit6':
        # skips whose closing black lands on bit 6, after a run or a black
        # dot in that byte, on a background whose bit 7 alternates
        snaps = []
        for k in range(1, 6):
            rows = []
            for pal in (0x00, 0x80):
                for lead in range(0, 6 - k + 1):
                    n = 6 - lead - k        # the skip: closing black on dot 6
                    row = bytearray()
                    if lead:
                        row.append(0x80 | (lead - 1))       # a lead skip first
                    row += bytes([k, pal | rng.randrange(128), 0x80 | n,
                                  1, (pal ^ 0x80) | rng.randrange(128), rng.choice([0, 7])])
                    rows.append(bytes(row))
            snaps.append(bytes([len(rows), 14, 0, 0, 0, 0, 0]) + b''.join(rows))
        files[b'AC.B6'] = make_actor(snaps)
        page = bytearray(PAGE)
        for y in range(ROWS):
            for c in range(40):
                page[ROW[y] + c] = (0x80 if (c + y // 3) & 1 else 0) | rng.randrange(128)
        files[b'BK.B6'] = encode_bk(page, rng)
        frames = []
        for f in range(6):
            els = b''
            for i in range(len(snaps)):
                els += obj(i + 1, 280 + 7 * rng.randrange(38) + rng.choice([0, 0, 1, 3]),
                           192 + rng.randrange(170), wrap=f % 2 == 1, end=i == len(snaps) - 1)
            frames.append(els)
        files[b'SN.B6'] = make_scene(20, [(len(snaps), 'B6')], frames)
        return make_movie([('B6', 'B6', 1, 1)]), files
    if kind == 'fades':
        snaps = [rand_snapshot(rng, h=rng.randrange(5, 30)) for _ in range(3)]
        files[b'AC.F'] = make_actor(snaps)
        page = bytearray(rng.randrange(256) for _ in range(PAGE))
        files[b'BK.P'] = encode_bk(page, rng)
        for k in range(2, 18):
            fr = [obj(1 + (k % 3), rng.randrange(260, 560), rng.randrange(180, 380),
                      wrap=bool(k & 1), end=True),
                  obj(1 + ((k + 1) % 3), rng.randrange(260, 560), rng.randrange(180, 380), end=True)]
            files[b'SN.F%d' % k] = make_scene(rng.randrange(10, 60), [(3, 'F')], fr)
            bg = ['P', '< BLACK >', '< UNCHANGED >'][k % 3]
            entries.append(('F%d' % k, bg, k, (k + 7) % 16 + 2))
        return make_movie(entries), files
    if kind == 'seam':
        snaps = []
        for total in (279, 280, 281, 273, 287, 560):
            for style in range(3):
                if style == 0:          # literals
                    row = bytearray()
                    left = total
                    while left >= 7:
                        k = min(6, left // 7)
                        row += bytes([((25 + k) << 3) | 7]) + bytes(rng.randrange(256) for _ in range(k))
                        left -= 7 * k
                    if left:
                        row += bytes([left, rng.randrange(256)])
                elif style == 1:        # fills with extensions
                    row = bytearray()
                    g, r = divmod(total, 7)
                    while g > 15:
                        e = min(25, g - 15)
                        row.append((e << 3) | 7)
                        g -= e
                    if g == 0 and r == 0:
                        g = 1
                    row += bytes([(g << 3) | r if r or g else 1, rng.randrange(256)])
                else:                   # skips and fills
                    row = bytearray([0x83, 0x05, rng.randrange(256)])
                    left = total - 3 - 1 - 5
                    g, r = divmod(left, 7)
                    while g > 15:
                        e = min(25, g - 15)
                        row.append((e << 3) | 7)
                        g -= e
                    row += bytes([0x80 | (g << 3) | r])
                rows = [bytes(row) + b'\x00', bytes(row) + b'\x07', b'\x07', b'\x00']
                snaps.append(bytes([len(rows), rng.randrange(256), 0, 0, 1, 0, 0]) + b''.join(rows))
        files[b'AC.S'] = make_actor(snaps)
        frames = []
        for i in range(len(snaps)):
            els = b''
            for x in range(7):
                els += obj(i + 1, 280 + x + 7 * rng.randrange(40), 192 + 8 * x + rng.randrange(8),
                           wrap=True)
            els += obj(i + 1, rng.randrange(0, 280), 200, wrap=True)
            els += obj(i + 1, 280 + rng.randrange(280), 200, wrap=False, end=True)
            frames.append(els)
        files[b'SN.S'] = make_scene(20, [(len(snaps), 'S')], frames)
        return make_movie([('S', '< BLACK >', 1, 1)]), files
    if kind == 'wide':
        snaps = []
        for i in range(6):
            h = rng.choice([60, 120, 200, 255])
            sn = bytearray(rand_snapshot(rng, h=h, wide=True))
            sn[4] = 1 | (rng.randrange(128) << 1)
            sn[5] = rng.choice([0, 1, 255, 128, 127, rng.randrange(256)])
            sn[6] = rng.choice([0, 1, 255, 128, 127, rng.randrange(256)])
            snaps.append(bytes(sn))
        files[b'AC.W'] = make_actor(snaps)
        frames = []
        for f in range(10):
            els = b''
            for k in range(3):
                els += obj(rng.randrange(1, 7), rng.randrange(1024), rng.randrange(512),
                           wrap=rng.random() < 0.5, end=k == 2)
            frames.append(els)
        files[b'SN.W'] = make_scene(30, [(6, 'W')], frames)
        return make_movie([('W', '< BLACK >', 1, 1), ('W', '< UNCHANGED >', 1, 1)]), files
    if kind == 'many':
        snaps = [rand_snapshot(rng, h=rng.randrange(1, 40)) for _ in range(8)]
        files[b'AC.M'] = make_actor(snaps)
        frames = []
        for f in range(8):
            n = rng.choice([19, 20, 21, 25, 40])
            els = b''
            for k in range(n):
                els += obj(rng.randrange(1, 9), rng.randrange(250, 600), rng.randrange(160, 400),
                           wrap=rng.random() < 0.3, plant=(f % 3 == 0 and k < 3), end=k == n - 1)
            frames.append(els)
        files[b'SN.M'] = make_scene(40, [(8, 'M')], frames)
        page = bytearray(rng.randrange(256) for _ in range(PAGE))
        files[b'BK.M'] = encode_bk(page, rng)
        return make_movie([('M', 'M', 1, 1), ('M', '< UNCHANGED >', 4, 1)]), files
    if kind == 'text':
        shapes = [bytes(rng.randrange(1, 256) for _ in range(rng.randrange(0, 12)))
                  for _ in range(rng.randrange(60, 97))]
        files[b'CS.T'] = make_cs(shapes)
        strings = [bytes(range(32, 128))[i:i + 24] for i in range(0, 96, 24)]
        strings += [bytes([0, 1, 31, 127, 128, 200, 255]), b'']
        frames = []
        for f in range(6):
            els = b''
            for k in range(len(strings)):
                els += obj(k + 1, rng.choice([280, 281, 286, 553, 559, rng.randrange(280, 560)]),
                           rng.choice([193, 194, 383, 382, rng.randrange(193, 384)]), wrap=True,
                           text=True, plant=f == 2 and k == 0, end=k == len(strings) - 1)
            frames.append(els)
        files[b'SN.T'] = make_scene(25, [], frames, strings, 'T')
        return make_movie([('T', '< BLACK >', 1, 1)]), files
    if kind == 'plant':
        snaps = [rand_snapshot(rng, h=rng.randrange(3, 20)) for _ in range(4)]
        files[b'AC.P'] = make_actor(snaps)
        frames = []
        for f in range(7):
            els = b''
            for k in range(4):
                els += obj(rng.randrange(1, 5), rng.randrange(250, 600), rng.randrange(170, 400),
                           wrap=rng.random() < 0.3, plant=k < 2 and f % 2 == 0)
            if f == 3:
                els += bytes([0xFC, 5, 0x01, 0])
            if f == 5:
                els += bytes([0xFC, 3, 0x00, 0, 0xFC, 9, 0x82, 0])
            else:
                els += bytes([0xFE, 0, 0, 0])
            frames.append(els)
        files[b'SN.P'] = make_scene(35, [(4, 'P')], frames)
        page = bytearray(rng.randrange(256) for _ in range(PAGE))
        files[b'BK.P'] = encode_bk(page, rng)
        return make_movie([('P', 'P', 1, 1), ('P', '< UNCHANGED >', 1, 3), ('P', '< UNCHANGED >', 2, 1),
                           ('P', '< BLACK >', 1, 17), ('P', 'P', 9, 1)]), files
    raise ValueError(kind)


def count_codes(n, rng, skip):
    """A skip or fill of n dots: extensions, then the code (bytes)."""
    q, r = divmod(n, 7)
    out = bytearray()
    while q > 15:
        e = min(25, q - 15)
        out.append((e << 3) | 7)
        q -= e
    c = (q << 3) | r
    if not skip and c == 0:
        c = 1
    out.append((0x80 | c) if skip else c)
    return out


def realistic(seed, scenes=2, frames=8):
    """A movie shaped like real ones (heavy frames): several sprites a
    frame, 30-120 rows high, 5-40 columns wide, rows of 1-6 codes, mostly
    long fills and skips, some literals, a few texts; scene speeds as seen
    (22-84). (movie, files)"""
    rng = random.Random(9000 + seed)
    files = {}
    snaps = []
    for i in range(6):
        h = rng.randrange(30, 121)
        cols = rng.randrange(5, 41)
        w = 7 * cols
        rows = []
        for _ in range(h):
            row = bytearray()
            left = w
            ncodes = rng.randrange(1, 6)
            for k in range(ncodes):
                if left <= 0:
                    break
                kind = rng.random()
                if kind < 0.12 and left >= 7:
                    nb = min(rng.randrange(1, 7), left // 7)
                    row += bytes([((25 + nb) << 3) | 7]) + bytes(rng.randrange(256) for _ in range(nb))
                    left -= 7 * nb
                    continue
                n = rng.randrange(1, left + 1) if k < ncodes - 1 else left
                if kind < 0.45 and k:
                    row += count_codes(max(n - 1, 0), rng, True)
                else:
                    row += count_codes(n, rng, False) + bytes([rng.randrange(256)])
                left -= n
            row.append(rng.choice([0x00, 0x00, 0x07]))
            rows.append(bytes(row))
        snaps.append(bytes([h, w & 255, 0, 0, w >> 8, 0, 0]) + b''.join(rows))
    files[b'AC.HEAVY'] = make_actor(snaps)
    shapes = [bytes(rng.randrange(1, 256) for _ in range(rng.randrange(2, 8))) for _ in range(64)]
    files[b'CS.FONT'] = make_cs(shapes)
    strings = [bytes(rng.randrange(0x41, 0x5B) for _ in range(rng.randrange(4, 12))) for _ in range(3)]
    page = bytearray(PAGE)
    for y in range(ROWS):
        for c in range(40):
            page[ROW[y] + c] = (y * 3 + c * 5) & 255
    files[b'BK.STAGE'] = encode_bk(page, rng)
    entries = []
    for sc in range(scenes):
        fr = []
        for f in range(frames):
            els = b''
            n = rng.randrange(1, 5)
            for k in range(n):
                els += obj(rng.randrange(1, 7), rng.randrange(260, 520), rng.randrange(180, 330),
                           wrap=False)
            if rng.random() < 0.3:
                els += obj(rng.randrange(1, 4), rng.randrange(280, 450), rng.randrange(200, 370),
                           wrap=True, text=True)
            els = bytearray(els)
            els[-2] |= 0x80
            fr.append(bytes(els))
        speed = rng.choice([22, 30, 40, 50, 60, 84])      # (the speeds seen: 22-84)
        files[b'SN.HEAVY%d' % sc] = make_scene(speed, [(6, 'HEAVY')], fr, strings, 'FONT')
        entries.append(('HEAVY%d' % sc, 'STAGE' if sc == 0 else '< UNCHANGED >', 1, 1))
    return make_movie(entries), files


def events_of(movie, files, scene_max=None, limit=None):
    ev = []
    for e in Player(movie, dict_loader(files), scene_max).play():
        ev.append(e)
        if limit and len(ev) >= limit:
            break
    return ev


# -- self test ------------------------------------------------------------------

def visible(page):
    return b''.join(page[ROW[y]:ROW[y] + 40] for y in range(ROWS))


def snap_of(rows, h=None, w=7, b4=0, sx=0, sy=0):
    rows = [bytes(r) for r in rows]
    return parse_snapshot(bytes([h if h is not None else len(rows), w, 0, 0, b4, sx & 255, sy & 255])
                          + b''.join(rows), 0, b'AC.T')


def draw1(rows, x16, y16, wrap=False, page=None, **kw):
    page = bytearray(PAGE) if page is None else page
    rect = draw_snapshot(page, snap_of(rows, **kw), x16 & 255, (x16 >> 8) & 3 |
                         ((y16 >> 8) & 1) << 3 | (0x10 if wrap else 0), y16 & 255)
    return page, rect


def selftest():
    # fill dots: the first seven are B's bits, then bits 3-6 over and over
    assert [fill_bit(0b0101_1000, j) for j in range(12)] == [0, 0, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1]
    y0 = ROW[0]
    # A fill then $00: the run, then a black dot under the cursor (register).
    p, r = draw1([[0x05, 0xFF, 0x00]], 280, 192)
    assert p[y0] == 0x9F, hex(p[y0])           # 5 dots, black 6th, palette 1
    assert r == (0, 2, 0, 1), r
    # A fill then $07: no black dot; the cursor is mid-byte: palette register.
    p, _ = draw1([[0x05, 0x7F, 0x07]], 280, 192)
    assert p[y0] == 0x1F, hex(p[y0])
    # Opaque runs: a 0 dot is black even over white.
    page = bytearray(PAGE)
    page[y0] = 0x7F
    p, _ = draw1([[0x03, 0x05, 0x07]], 280, 192, page=page)
    assert p[y0] == 0x7D, hex(p[y0])
    # Skip as the first code: transparent, then black (bit 6: bit 7 kept).
    page = bytearray(PAGE)
    page[y0], page[y0 + 1] = 0xFF, 0x7F
    p, _ = draw1([[0x86, 0x01, 0x80, 0x07]], 280, 192, page=page)
    assert p[y0] == 0xBF, hex(p[y0])           # dot 6 black, bit 7 kept
    assert p[y0 + 1] == 0xFE, hex(p[y0 + 1])   # B=$80: dot 0 black, palette 1
    page = bytearray(PAGE)
    page[y0], page[y0 + 1] = 0xFF, 0x7F
    p, _ = draw1([[0x86, 0x01, 0x81, 0x07]], 280, 192, page=page)
    assert p[y0] == 0xBF and p[y0 + 1] == 0xFF, (hex(p[y0]), hex(p[y0 + 1]))
    # A skip's closing black on bit 6 of a byte that earlier dots of the row
    # reached: the byte keeps the bit 7 they gave it (the register's), not
    # the screen's. Fill 3 (palette 1), skip 3: black 3, 4-5 kept, black 6.
    page = bytearray(PAGE)
    page[y0] = 0x7F
    p, _ = draw1([[0x03, 0x87, 0x83, 0x01, 0x00, 0x07]], 280, 192, page=page)
    assert p[y0] == 0xB7, hex(p[y0])
    page = bytearray(PAGE)
    page[y0] = 0xFF                           # palette 0 over a screen bit 7 of 1
    p, _ = draw1([[0x03, 0x07, 0x83, 0x01, 0x80, 0x07]], 280, 192, page=page)
    assert p[y0] == 0x37 and p[y0 + 1] == 0x80, (hex(p[y0]), hex(p[y0 + 1]))
    # Lead skip not at bit 6: its black dot takes the next run's palette.
    page = bytearray(PAGE)
    page[y0] = 0x7F
    p, _ = draw1([[0x82, 0x01, 0x81, 0x07]], 280, 192, page=page)
    assert p[y0] == 0xFB, hex(p[y0])           # dots 0,1 kept, 2 black, 3 white, 4-6 kept; bit 7 1
    # Skips after skips: each non-first skip blackens the dot under the cursor.
    page = bytearray(PAGE)
    page[y0] = 0x7F
    p, _ = draw1([[0x80, 0x81, 0x80, 0x07]], 280, 192, page=page)
    # first skip 0: dot 0 black (end black); skip 1: dots 1, 2 black; skip 0: dot 3 black
    assert p[y0] == 0x73, hex(p[y0])           # dots 0-3 black, P3 at the $07 end: | 3
    p2 = bytearray(PAGE)
    p2[y0] = 0x7F
    p, _ = draw1([[0x01, 0x81, 0x81, 0x81, 0x00]], 280, 192, page=p2)
    # fill 1 dot white pal 1; skip 1: 1, 2 black; skip 1: 3, 4 black; $00: 5 black; 6 kept
    assert p[y0] == 0xC1, hex(p[y0])
    assert p[y0 + 1] == 0, hex(p[y0 + 1])
    # Skip 0 not first: one dot.
    p2 = bytearray(PAGE)
    p2[y0] = 0x7F
    p, _ = draw1([[0x01, 0x81, 0x80, 0x07]], 280, 192, page=p2)
    assert p[y0] == 0xFD, hex(p[y0])           # dot 0 white, skip 0: dot 1 black, rest kept
    # P3: an empty $07 row off bit 0 sets bits 0 and 1 and clears bit 7.
    page = bytearray(PAGE)
    page[y0] = 0xC4
    p, _ = draw1([[0x07]], 282, 192, page=page)
    assert p[y0] == 0x47, hex(p[y0])
    # ... and on bit 0, nothing.
    page = bytearray(PAGE)
    page[y0] = 0xC4
    p, _ = draw1([[0x07]], 280, 192, page=page)
    assert p[y0] == 0xC4
    # An empty $00 row draws nothing.
    page = bytearray(PAGE)
    page[y0] = 0xC4
    p, _ = draw1([[0x00]], 282, 192, page=page)
    assert p[y0] == 0xC4
    # The register carries from row to row.
    p, _ = draw1([[0x01, 0x81, 0x07], [0x07]], 283, 192)
    assert p[ROW[1]] == 0x80, hex(p[ROW[1]])
    # Wrap seam: a row of 40 literal bytes from dot 0 comes back to its
    # first byte: no black dot there, bit 7 from the register.
    page = bytearray(PAGE)
    lit = bytes([(31 << 3) | 7] + [0x81] * 6)
    row = lit * 6 + bytes([(29 << 3) | 7, 0x81, 0x81, 0x81, 0x81, 0x00])
    p, _ = draw1([row], 280, 192, wrap=True, page=page)
    assert all(p[y0 + c] == 0x81 for c in range(40)), visible(p)[:40].hex()
    # the same without wrap: the 40 bytes, no black dot anywhere (off right)
    page = bytearray(PAGE)
    p, _ = draw1([row], 280, 192, wrap=False, page=page)
    assert all(p[y0 + c] == 0x81 for c in range(40))
    # Wrap from dot 3: the row's end wraps into byte 0 then the start byte.
    page = bytearray(PAGE)
    p, _ = draw1([row], 283, 192, wrap=True, page=page)
    assert all(p[y0 + c] == 0x88 for c in range(40)), visible(p)[:40].hex()
    # Left clipping with wrap: X < 0, the left part is not drawn, nothing wraps from it.
    page = bytearray(PAGE)
    p, r = draw1([[0x09, 0x7F, 0x00]], 280 - 14, 192, wrap=True, w=21, page=page)
    # 1*7+1 = 8 dots from -14: dots -14..-7 not drawn, black at -6: off
    assert visible(p) == bytes(7680), r
    p, r = draw1([[0x19, 0x7F, 0x00]], 280 - 14, 192, wrap=True, w=21, page=page)
    # 3*7+1 = 22 dots from -14: dots 0..7 white, black at 8
    assert p[y0] == 0x7F and p[y0 + 1] == 0x01, (hex(p[y0]), hex(p[y0 + 1]))
    assert r == (0, 3, 0, 1), r                 # wb = 5 (w 21: 21-7-7=7 -> 2 + 2 = ... )
    # a wide row from the right edge wraps to the left with wrap...
    page = bytearray(PAGE)
    p, r = draw1([[0x11, 0x7F, 0x00]], 280 + 273, 192, wrap=True, page=page)
    assert p[y0 + 39] == 0x7F and p[y0] == 0x7F and p[y0 + 1] == 0x01, visible(p)[:40].hex()
    # ... and is cut without wrap
    page = bytearray(PAGE)
    p, r = draw1([[0x11, 0x7F, 0x00]], 280 + 273, 192, wrap=False, page=page)
    assert p[y0 + 39] == 0x7F and p[y0] == 0 and r == (39, 1, 0, 1), (visible(p)[:40].hex(), r)
    # Sync: zero leaves the coordinates as they are; nonzero adjusts and clamps.
    s = snap_of([[0x00]], sx=0, sy=0)
    assert place(s, 10, 0x10, 10)[:3] == (10 - 280, 10 + 64, 0)
    s = snap_of([[0x00]], sx=1, sy=1)
    assert place(s, 10, 0x10, 10)[:3] == (11, 11 - 192 + 192, 0)
    s = snap_of([[0x00]], sx=-20, sy=-20)
    assert place(s, 10, 0x00, 10)[:3] == (-280, 0, 192)
    s = snap_of([[0x00]], sx=100, sy=100)
    assert place(s, 255, 0x0B, 255)[:3] == (687 - 280, 511 - 192, 0)
    s = snap_of([[0x00]], sx=-1, sy=-1)
    assert place(s, 0x30, 0x1A, 0x80)[:3] == (0x22F - 280, 0x17F - 192, 0)   # 559, 383
    s = snap_of([[0x00]], sx=1, sy=1)
    assert place(s, 0x2F, 0x1A, 0x7F)[:3] == (0x230 - 280 - 280, 0x180 - 192 - 192, 0)
    # The rectangle rules.
    s = snap_of([[0x00]] * 5, w=20)
    assert place(s, 280 & 255, 0x01, 192 & 255) == (0, 0, 0, (0, 4, 0, 5))  # wb 2+2
    s = snap_of([[0x00]] * 5, w=20, b4=1)
    assert place(s, 280 & 255, 0x01, 192 & 255)[3] == (0, 40, 0, 5)
    s = snap_of([[0x00]] * 5, w=7)
    assert place(s, (280 - 7) & 255, 0x01, 200)[3] == (0, 2, 8, 5)   # c=-1: wb + c + 1 = 2
    assert place(s, (280 - 14) & 255, 0x01, 200)[3] == (0, 1, 8, 5)  # c=-2: 1
    assert place(s, (280 - 21) & 255, 0x01, 200)[3] is None          # c=-3: 0
    assert place(s, (280 + 273) & 255, 0x02, 200)[3] == (39, 1, 8, 5)  # cut at 40
    assert place(s, (280 + 273) & 255, 0x12, 200)[3] == (39, 2, 8, 5)  # wrap: not cut
    assert place(s, (280 + 280) & 255, 0x12, 200)[3] is None
    assert place(s, 280 & 255, 0x01, 190)[3] == (0, 2, 0, 3)          # 2 rows above
    assert place(s, 280 & 255, 0x01, 187)[3] == (0, 2, 0, 0)          # all above: height 0
    assert place(s, 280 & 255, 0x01, 186)[3] is None
    assert place(s, 280 & 255, 0x09, 128)[3] is None                  # y16 = 384: top 192
    # Text: XDRAW and its rectangle.
    shapes = [None, bytes([0b00_101_101])]      # plot+right, plot+right
    page = bytearray(PAGE)
    rect, nb = draw_text(page, shapes, b'!', 280 & 255, 0x51, 193 & 255)
    assert page[ROW[1]] == 0x03 and nb == 1 and rect == (0, 1, 1, 1), (page[ROW[1]], rect)
    shapes = [None, bytes([0b11_111_111, 0b00_000_100])]
    page = bytearray(PAGE)
    rect, nb = draw_text(page, shapes, b'\x01', 280 & 255, 0x51, 193 & 255)  # left from 0: 279
    # A: plot (0,1), left to 279; B: plot (279,1), left; C: left; then plot (277,1), up
    assert page[ROW[1]] == 0x01 and page[ROW[1] + 39] == 0x50 and rect == (39, 2, 0, 2), rect
    # List full: the 3,328 area and the 21st rectangle.
    L = RectList()
    for _ in range(20):
        L.add((0, 1, 0, 1))
    assert not L.full and len(L.rects) == 20
    L.add((0, 1, 0, 1))
    assert L.full
    L = RectList()
    L.add((0, 40, 0, 83))
    assert not L.full
    L.add((0, 1, 0, 8))
    assert L.full                               # 3,320 + 8 = 3,328
    # Rectangle leftovers: a dot drawn outside the rectangle stays.
    page = bytearray(PAGE)
    p, r = draw1([[0x01, 0x7F, 0x90, 0x01, 0x7F, 0x07]], 280, 192, w=1)
    assert r == (0, 2, 0, 1) and p[y0 + 2] == 0x04, (r, visible(p)[:8].hex())
    # Every fade ends with the destination equal to the source, in order.
    rng = random.Random(3)
    src = bytes(rng.randrange(256) for _ in range(PAGE))
    for num in range(2, 18):
        dst = bytearray(bytes(b ^ 0x55 for b in src))
        ev = list(run_fade(num, src, dst))
        assert visible(dst) == visible(src), num
        ops = fade_ops(num)
        delays = [op[1] for op in ops if op[0] == 'd']
        if num == 12:
            assert delays == [24] * 384
        if num in (4, 6):
            assert delays == [30] * 192
        if num == 14:
            assert not delays and sum(1 for op in ops if op[0] == 't') == 71
        copies = [(op[1], op[2]) for op in ops if op[0] == 'c']
        if num == 8:
            rows = [copies[i][0] for i in range(0, len(copies), 40)]
            assert rows[:5] == [96, 95, 97, 94, 98] and sorted(rows) == list(range(192)), rows[:8]
        if num == 13:
            rows = [copies[i][0] for i in range(0, len(copies), 40)]
            assert rows[:4] == [96, 94, 98, 92] and set(rows) == set(range(192)), rows[:8]
    # The frame wait.
    assert frame_wait(30, 0) == 120 and frame_wait(30, 1920) == 0 and frame_wait(1, 1) == 4
    assert frame_wait(255, 16384) == 0 and frame_wait(60, 100) == 240 - 6
    assert delay_cycles(141) > 51000 and delay_cycles(0) == delay_cycles(256)
    # Movies: BLACK, UNCHANGED, background, fades, plant.
    cs = make_cs([bytes([0b00_101_101])] * 3)
    act = make_actor([bytes([1, 7, 0, 0, 0, 0, 0, 0x05, 0xFF, 0x00])])
    fr1 = [obj(1, 280, 200, plant=True) + obj(1, 301, 210, end=True),
           obj(1, 322, 220, end=True),
           bytes([0xFE, 0, 0, 0]),
           obj(1, 280, 230) + bytes([0xFC, 3, 0x82, 0])]
    files = {b'SN.ONE': make_scene(30, [(1, 'MAN')], fr1, [b'AB'], 'F'),
             b'AC.MAN': act, b'CS.F': cs}
    page = bytearray(PAGE)
    page[ROW[100] + 5] = 0x2A
    files[b'BK.PIC'] = encode_bk(page)
    assert decode_bk(files[b'BK.PIC']) == page
    mv = make_movie([('ONE', 'PIC', 1, 1), ('ONE', '< UNCHANGED >', 5, 9), ('ONE', '< UNCHANGED >', 1, 1),
                     ('ONE', '< BLACK >', 1, 1)])
    ev = events_of(mv, files)
    shows = [e for e in ev if e[0] == 'show']
    assert [e[1] for e in shows[:4]] == [2, 1, 2, 1]
    s0 = shows[0][2]
    assert s0[ROW[100] + 5] == 0x2A and s0[ROW[8]] == 0x9F and s0[ROW[18] + 3] == 0x9F
    s1 = shows[1][2]                       # frame 2: planted object stays, frame-1 object erased
    assert s1[ROW[8]] == 0x9F and s1[ROW[18] + 3] == 0 and s1[ROW[28] + 6] == 0x9F, s1[ROW[18] + 3]
    assert ('fc', 2, 3) in ev
    # second scene: UNCHANGED keeps the plants; fade-in 5 reveals frame 1,
    # whose page stays the back page: three shows only
    second = ev[ev.index(('fade', 5)):]
    assert [e[0] for e in second if e[0] in ('show', 'fade')][:4] == ['fade', 'show', 'show', 'show']
    # after fade-out 9, page 3 is black: the third (UNCHANGED) scene starts black
    third_first = [e for e in ev[ev.index(('fade', 9)):] if e[0] == 'show'][0][2]
    assert third_first[ROW[100] + 5] == 0 and third_first[ROW[8]] == 0x9F
    # Refusals.
    for bad, code in ((mv[:-1], E_BAD), (b'\x00', E_BAD), (mv[:42], E_BAD)):
        try:
            events_of(bad, files)
            raise AssertionError('accepted')
        except Refused as r:
            assert r.code == code, r
    bad = bytearray(mv)
    bad[41] = 18
    try:
        events_of(bytes(bad), files)
        raise AssertionError('fade 18 accepted')
    except Refused as r:
        assert r.code == E_BAD
    for name, data, code in ((b'SN.ONE', files[b'SN.ONE'][:0x102], E_BAD),
                             (b'AC.MAN', b'', E_BAD), (b'AC.MAN', act[:-2], E_BAD),
                             (b'CS.F', cs[:-1], E_BAD), (b'BK.PIC', files[b'BK.PIC'][:-1], E_BAD),
                             (b'BK.PIC', files[b'BK.PIC'] + b'\x00', None),
                             (b'BK.PIC', None, E_NOTFOUND)):
        f2 = dict(files)
        if data is None:
            del f2[name]
        else:
            f2[name] = data
        try:
            events_of(mv, f2)
            assert code is None, name
        except Refused as r:
            assert (r.code, r.name) == (code, name), (r, name)
    # The memory limit.
    try:
        events_of(mv, files, scene_max=len(files[b'SN.ONE']) + len(act) + len(cs) - 1)
        raise AssertionError('too big accepted')
    except Refused as r:
        assert (r.code, r.name) == (E_BIG, b'CS.F'), r
    # Loading from a DOS 3.3 image and from extracted files.
    img, where = make_dsk({k.decode(): v for k, v in files.items()} | {'MV.FILM': mv})
    di = DosImage(img)
    assert di.read_file(*where['MV.FILM']) == mv
    ev2 = list(Player(mv, image_loader(di)).play())
    assert ev2 == ev
    assert prodos_name(b'SN.MY SCENE') == b'SN.MY.SCENE'
    assert prodos_name(b'1ST TAKE-ONE LONG NAME') == b'XST.TAKE.ONE.LO'
    # Random movies play to the end, or are refused cleanly.
    for seed in range(30):
        mv, files = synthetic(seed)
        for _ in Player(mv, dict_loader(files)).play():
            pass
    print('PASS take1_ref selftest')


# -- the command line --------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('source', nargs='?', help='a DOS 3.3 .dsk/.do image, or a directory')
    ap.add_argument('movie', nargs='?', help='MV.NAME (the DOS name)')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--frames', type=int, default=0)
    ap.add_argument('--out', help='write each shown page there (NNNN.bin)')
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.source or not args.movie:
        ap.error('a source and a movie name are needed')
    name = args.movie.encode('latin-1')
    src = Path(args.source)
    if src.is_dir():
        loader = dir_loader(src)
    else:
        data = src.read_bytes()
        base = 0
        if data[:4] == b'2IMG':
            if data[0x0C] != 0:
                sys.exit('not a DOS-order .2MG')
            base = int.from_bytes(data[0x18:0x1C], 'little')
        loader = image_loader(DosImage(data, base))
    out = Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    try:
        movie = loader(name, MOVIE_MAX)
        shown = 0
        for e in Player(movie, loader, movie_name=name).play():
            if e[0] == 'show':
                print('show %4d page %d' % (shown, e[1]))
                if out:
                    (out / ('%04d.bin' % shown)).write_bytes(e[2])
                shown += 1
                if args.frames and shown >= args.frames:
                    break
            elif e[0] in ('wait', 'fc', 'fade', 'end'):
                print(' '.join(str(x) for x in e))
    except Refused as r:
        sys.exit('refused: %s' % r)


if __name__ == '__main__':
    main()
