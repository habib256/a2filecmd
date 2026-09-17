#!/usr/bin/env python3
"""Applesoft shape tables: the reference for the SHAPES viewer.

    shapes_ref.py FILE          # prints the table's shapes and their sizes
    shapes_ref.py --selftest

A shape table (Applesoft II manual, chapter 9; CiderPress II's notes) is a
shape count, an unused byte, a 16-bit offset per shape, then the shapes:
bytes of up to three vectors -- A in bits 0-2, B in bits 3-5, C in bits
6-7 -- each a direction (0 up, 1 right, 2 down, 3 left) and, for A and B,
a plot bit (4) set to plot before moving. A zero byte ends the shape;
B and C are skipped when bits 3-7 are all zero, C when bits 6-7 are.

SHAPES draws a page of 24 of them on the hi-res screen, in mixed mode:
6 columns and 4 rows of 40 x 40 cells, left to right, top to bottom.
Each shape is drawn at scale 1, its plotted points' bounding box centred
in the cell (the gap rounded down), points outside the cell left out.
Coordinates are bytes, as the viewer keeps them: a shape that wanders more
than 127 dots from its start wraps. A dot at x lights bit x % 7 of byte
x / 7 of its row, the high bit left clear.

A shape whose offset is outside the file, or that reaches the end of the
file before its zero byte, is drawn as nothing; a table is refused only
when its count is zero or its offsets run past the file.
"""
import sys
from pathlib import Path

PER_PAGE = 24
COLS = 6
CELL = 40


def shape_count(data):
    """The shape count, or 0 when the table cannot hold it."""
    if len(data) < 4 or not data[0] or 2 + 2 * data[0] > len(data):
        return 0
    return data[0]


def trace(data, k):
    """The plotted points of shape k (1-based) as (x, y) bytes from (128,
    128), or None when the shape does not end within the file."""
    off = data[2 * k] | data[2 * k + 1] << 8
    x = y = 128
    points = []

    def vec(v):
        nonlocal x, y
        if v & 4:
            points.append((x, y))
        d = v & 3
        if d == 0:
            y = (y - 1) & 255
        elif d == 1:
            x = (x + 1) & 255
        elif d == 2:
            y = (y + 1) & 255
        else:
            x = (x - 1) & 255
    while True:
        if off >= len(data):
            return None
        b = data[off]
        off += 1
        if not b:
            return points
        vec(b & 7)
        if b >> 3:
            vec((b >> 3) & 7)
            if b >> 6:
                vec(b >> 6)                 # C: never plots


def valid(data):
    return shape_count(data) > 0


def row_address(y):
    r = y >> 3
    return (y & 7) * 0x400 + (r % 8) * 0x80 + (r // 8) * 0x28


def place(points):
    """The points of a shape, relative to its cell: [(px, py)] < 40."""
    if not points:
        return []
    minx = min(p[0] for p in points)
    miny = min(p[1] for p in points)
    w = max(p[0] for p in points) - minx + 1
    h = max(p[1] for p in points) - miny + 1
    padx = (CELL - w) >> 1 if w < CELL else 0
    pady = (CELL - h) >> 1 if h < CELL else 0
    out = []
    for x, y in points:
        px, py = x - minx + padx, y - miny + pady
        if px < CELL and py < CELL:
            out.append((px, py))
    return out


def page(data, first):
    """The hi-res page (8,192 bytes) with shapes first..first+23 drawn."""
    screen = bytearray(8192)
    n = shape_count(data)
    for i in range(PER_PAGE):
        k = first + i
        if k > n:
            break
        pts = trace(data, k)
        if pts is None:
            continue
        cx, cy = (i % COLS) * CELL, (i // COLS) * CELL
        for px, py in place(pts):
            x, y = cx + px, cy + py
            screen[row_address(y) + x // 7] |= 1 << (x % 7)
    return bytes(screen)


def status(data, first):
    n = shape_count(data)
    return 'SHAPES %3u-%3u/%3u' % (first, min(first + PER_PAGE - 1, n), n)


def make(shapes, spare=0):
    """A table from lists of vector bytes (tests); `spare` unused offsets."""
    n = len(shapes)
    head = bytearray([n, 0]) + bytes(2 * (n + spare))
    body = bytearray()
    for i, s in enumerate(shapes):
        off = len(head) + len(body)
        head[2 + 2 * i:4 + 2 * i] = off.to_bytes(2, 'little')
        body += bytes(s) + b'\0'
    return bytes(head + body)


def selftest():
    # the manual's example: a square drawn with plotted moves
    square = make([[0x12, 0x3F, 0x20, 0x64, 0x2D, 0x15, 0x36, 0x1E, 0x07]])
    pts = trace(square, 1)
    assert pts and len(pts) >= 8, pts
    assert trace(make([[0x04]])[:-1], 1) is None
    assert valid(square) and not valid(b'\x00\x00\x00\x00') and not valid(b'\x05\x00\x02\x00')
    scr = page(make([[0x04]]), 1)               # one dot, centred in cell 0
    assert scr[row_address(19) + 19 // 7] == 1 << (19 % 7)
    assert sum(1 for b in page(square, 1) if b) > 0
    print('selftest: vectors, validity, placement')


def main():
    if sys.argv[1:] == ['--selftest']:
        selftest()
        return 0
    data = Path(sys.argv[1]).read_bytes()
    n = shape_count(data)
    if not valid(data):
        print('not a shape table')
        return 1
    for k in range(1, n + 1):
        pts = trace(data, k)
        if pts is None:
            print('%3d: broken' % k)
        elif pts:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            print('%3d: %d dots, %d x %d' % (k, len(pts), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1))
        else:
            print('%3d: empty' % k)
    return 0


if __name__ == '__main__':
    sys.exit(main())
