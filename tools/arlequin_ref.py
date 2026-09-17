#!/usr/bin/env python3
"""Arlequin pictures (Le Chat Mauve, ARLEQUIN 1.1, 1985): the reference.

    arlequin_ref.py PICTURE            # prints the size and the stream use
    arlequin_ref.py --selftest

ARLEQUIN is the double hi-res graphics interpreter the card maker sold for
its Feline RGB card (`GLI16.2`, an Applesoft `&` extension). `& LOAD (x, y,
"NAME")` draws a picture saved as ProDOS type $F8:

    +0  width   in groups of seven colour cells (1..20; 20 is the screen)
    +1  height  in rows (1..192)
    +2  "gs"    the signature ($67 $73)
    +4  the stream

A group of seven cells is two byte columns, one byte of the auxiliary plane
and one of the main plane each, so a row is 4 * width bytes: auxiliary then
main, column by column, left to right. Rows go top to bottom. `& LOAD (x, y)`
puts the left edge at byte column 2x and the BOTTOM row at Arlequin line y,
whose lines count from the bottom of the screen (screen row 191 - y).

The stream, read off the decoder of GLI16.2 ($D46C-$D4B8 once relocated to
the language card) and checked against the Apple II's memory after the real
loader ran under POM2 with a Feline card -- MOTO, AIGLE, MAMMOUTH, FEN and
FE1-FE4 from the maker's demonstration disk, byte for byte:

    $80-$FF   one byte, as it is; it becomes the "last" byte
    $00       toggles the mask applied to every output byte, $FF <-> $7F:
              bit 7 selects colour or black and white in the mixed mode
    $01-$7F   a run of (c AND $3F) bytes, 0 meaning 256. The last byte keeps
              its low seven bits and takes bit 7 from bit 6 of c; every byte
              of the run is that byte ROTATED left by one, bit 7 into bit 0,
              and becomes the last in turn. A four-dot colour pattern
              rotated by one is the same colour one byte further on, which
              is what a run is for.

Every output byte is (v OR $80) AND mask. A run may cross a row.
"""
import argparse
import random
import sys
from pathlib import Path

SIGNATURE = b'gs'
MAX_WIDTH, MAX_HEIGHT = 20, 192


class Truncated(ValueError):
    pass


class Stream:
    """The decoder, one output byte at a time, as GLI16.2 runs it."""

    def __init__(self, data, start=4):
        self.d, self.p = data, start
        self.last, self.count, self.mask = 0, 1, 0xFF

    def _rot(self):
        v = self.last
        self.last = ((v << 1) & 0xFF) | (v >> 7)
        return (self.last | 0x80) & self.mask

    def next(self):
        self.count = (self.count - 1) & 0xFF
        if self.count:
            return self._rot()
        self.count = 1
        while True:
            if self.p >= len(self.d):
                raise Truncated('stream ends at %d' % self.p)
            b = self.d[self.p]
            self.p += 1
            if b >= 0x80:
                self.last = b
                return (b | 0x80) & self.mask
            if b == 0:
                self.mask ^= 0x80
                continue
            self.last = (self.last & 0x7F) | (0x80 if b >= 0x40 else 0)
            self.count = b & 0x3F
            return self._rot()


def header(data):
    """(width, height), or ValueError for anything ARLEQUIN would not load."""
    if len(data) < 4 or data[2:4] != SIGNATURE:
        raise ValueError('not an Arlequin picture')
    w, h = data[0], data[1]
    if not 1 <= w <= MAX_WIDTH or not 1 <= h <= MAX_HEIGHT:
        raise ValueError('size %d x %d' % (w, h))
    return w, h


def decode(data):
    """The rows, top down, 4 * width bytes each; and the bytes used."""
    w, h = header(data)
    s = Stream(data)
    rows = [bytes(s.next() for _ in range(4 * w)) for _ in range(h)]
    return rows, s.p


def place(width, height):
    """Where the viewer draws a picture: centred, on whole groups."""
    return ((MAX_WIDTH - width) // 2) * 4, (MAX_HEIGHT - height) // 2


def screen(data):
    """The two 8 KB planes the viewer leaves: (auxiliary, main), each laid out
    like the hi-res page, black around a picture smaller than the screen."""
    rows, _ = decode(data)
    left, top = place(data[0], data[1])
    aux, main = bytearray(0x2000), bytearray(0x2000)
    for k, row in enumerate(rows):
        a = row_address(top + k)
        for i in range(0, len(row), 2):
            col = (left + i) // 2
            aux[a + col] = row[i]
            main[a + col] = row[i + 1]
    return bytes(aux), bytes(main)


def row_address(y):
    """The offset of screen row y in the hi-res page."""
    r = y >> 3
    return (y & 7) * 0x400 + (r % 8) * 0x80 + (r // 8) * 0x28


def encode(width, rows, rng=None):
    """A legal stream for these rows, using every construct: literals, runs
    with and without bit 7, mask toggles and runs across rows. Not
    ARLEQUIN's own choices -- any stream the decoder reads is a picture."""
    rng = rng or random.Random(0)
    flat = b''.join(rows)
    out = bytearray([width, len(rows)]) + SIGNATURE
    last, mask, i = 0, 0xFF, 0
    while i < len(flat):
        want = flat[i]
        wmask = 0xFF if want & 0x80 else 0x7F
        if wmask != mask:
            out.append(0)
            mask = wmask
        # the longest run the current last byte can give, either bit-7 choice
        # (63 at most: the 0 that means 256 is left to the tests of decode)
        best = (0, 0)
        for flag in (0, 0x40):
            v = (last & 0x7F) | (0x80 if flag else 0)
            n = 0
            while n < 63 and i + n < len(flat):
                v = ((v << 1) & 0xFF) | (v >> 7)
                if (v | 0x80) & mask != flat[i + n]:
                    break
                n += 1
            if n > best[0]:
                best = (n, flag)
        n, flag = best
        if n >= 2 or (n == 1 and rng.random() < 0.3):
            out.append(flag | n)
            v = (last & 0x7F) | (0x80 if flag else 0)
            for _ in range(n):
                v = ((v << 1) & 0xFF) | (v >> 7)
            last = v
            i += n
            continue
        # a literal has bit 7 set; the mask gives the output its own bit 7
        last = want | 0x80
        out.append(last)
        i += 1
    return bytes(out)


def random_rows(width, height, rng):
    rows = []
    for _ in range(height):
        row = bytearray()
        while len(row) < 4 * width:
            kind = rng.randrange(4)
            if kind == 0:                       # a colour fill
                v = rng.choice([0x11, 0x22, 0x33, 0x55, 0x66, 0x77, 0x99, 0xBB, 0xDD])
                bit = rng.choice([0, 0x80])
                for _ in range(rng.randrange(1, 40)):
                    v = ((v << 1) & 0xFF) | (v >> 7)
                    row.append((v | 0x80) & (0xFF if bit else 0x7F))
            else:
                row.append(rng.randrange(256))
        rows.append(bytes(row[:4 * width]))
    return rows


def selftest():
    rng = random.Random(1)
    for _ in range(300):
        w, h = rng.randrange(1, 21), rng.randrange(1, 193)
        rows = random_rows(w, h, rng)
        data = encode(w, rows, rng)
        got, used = decode(data)
        assert got == rows and used == len(data), (w, h)
        for cut in (4, len(data) - 1):         # every byte is used: a cut shows
            try:
                decode(data[:cut])
            except Truncated:
                continue
            raise AssertionError(('a cut stream decoded', w, h, cut))
    print('selftest: 300 pictures round-trip')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('picture', nargs='?')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    data = Path(args.picture).read_bytes()
    rows, used = decode(data)
    print('%s: %d x %d, %d of %d bytes used' % (args.picture, data[0], data[1], used, len(data)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
