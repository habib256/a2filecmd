#!/usr/bin/env python3
"""MacPaint documents: the reference for the MACPAINT viewer.

    macpaint_ref.py PICTURE          # prints the layout the viewer sees
    macpaint_ref.py --selftest

A MacPaint document (Mac type 'PNTG', creator 'MPNT'; CiderPress II's
MacPaint notes) is a 512-byte header -- a big-endian version, 0 or 2, then
patterns -- and 720 scanlines of 72 bytes (576 dots, the leftmost in bit 7,
1 black), each packed on its own with PackBits:

    n = 0..127     the next n + 1 bytes as they are
    n = 129..255   the next byte, 257 - n times
    n = 128        nothing (never written by the ROM)

Files that crossed the Internet often carry a 128-byte MacBinary header
first; its type field (offset 65) then says 'PNTG'. On ProDOS nothing else
tells a MacPaint document apart, so the viewer takes a `.MAC` or `.PNTG`
name, or a MacBinary 'PNTG' header, and then requires the whole file to
unpack into exactly 720 lines of 72 bytes.

The viewer shows 560 of the 576 dots -- line bytes 1 to 70, eight dots cut
at each edge -- in double hi-res, 192 lines at a time, black and white:
each double hi-res byte is seven dots, the leftmost in bit 0, 1 lit, and
the bytes alternate auxiliary and main as the screen does.
"""
import argparse
import random
import sys
from pathlib import Path

LINES, WIDTH = 720, 72
HEADER = 512
MACBINARY = 128


class Bad(ValueError):
    pass


def data_offset(data):
    """Where the picture starts, or Bad."""
    if len(data) >= MACBINARY + HEADER and data[0] == 0 and data[65:69] == b'PNTG':
        return MACBINARY + HEADER
    if len(data) >= HEADER and data[0:3] == b'\0\0\0' and data[3] in (0, 2):
        return HEADER
    raise Bad('no MacPaint header')


def unpack(data, start=None):
    """The 720 lines, and the offset of each line's first packed byte."""
    p = data_offset(data) if start is None else start
    lines, offsets = [], []
    for _ in range(LINES):
        offsets.append(p)
        line = bytearray()
        while len(line) < WIDTH:
            if p >= len(data):
                raise Bad('cut at line %d' % len(lines))
            n = data[p]
            p += 1
            if n < 128:
                if p + n + 1 > len(data):
                    raise Bad('cut in a literal')
                line += data[p:p + n + 1]
                p += n + 1
            elif n > 128:
                if p >= len(data):
                    raise Bad('cut in a run')
                line += bytes([data[p]]) * (257 - n)
                p += 1
        if len(line) != WIDTH:
            raise Bad('line %d runs over' % len(lines))
        lines.append(bytes(line))
    return lines, offsets


def dhgr_row(line):
    """The 80 double hi-res bytes of one line: dots 8 to 567, inverted."""
    bits = []
    for b in line[1:71]:
        bits += [(b >> (7 - i)) & 1 for i in range(8)]
    out = bytearray()
    for k in range(80):
        v = 0
        for j in range(7):
            v |= (1 - bits[k * 7 + j]) << j
        out.append(v)
    return bytes(out)


def row_address(y):
    r = y >> 3
    return (y & 7) * 0x400 + (r % 8) * 0x80 + (r // 8) * 0x28


def screen(data, top=0):
    """(auxiliary, main): the two planes with lines top..top+191 shown."""
    lines, _ = unpack(data)
    aux, main = bytearray(0x2000), bytearray(0x2000)
    for y in range(192):
        row = dhgr_row(lines[top + y])
        a = row_address(y)
        aux[a:a + 40] = row[0::2]
        main[a:a + 40] = row[1::2]
    return bytes(aux), bytes(main)


def pack_line(line, rng):
    """One scanline with PackBits, a mix of runs and literals."""
    out, i = bytearray(), 0
    while i < len(line):
        j = i
        while j < len(line) and line[j] == line[i] and j - i < 128:
            j += 1
        if j - i >= 2 and rng.random() < 0.9:
            out += bytes([257 - (j - i), line[i]])
            i = j
            continue
        k = min(len(line) - i, rng.randrange(1, 129))
        out += bytes([k - 1]) + line[i:i + k]
        i += k
    return bytes(out)


def pack(lines, rng=None, version=2, macbinary=False, noise=False):
    rng = rng or random.Random(0)
    head = bytearray(HEADER)
    head[3] = version
    body = bytearray()
    for line in lines:
        if noise and rng.random() < 0.05:
            body.append(128)                    # the byte that means nothing
        body += pack_line(line, rng)
    data = bytes(head) + bytes(body)
    if macbinary:
        mb = bytearray(MACBINARY)
        mb[1] = 5
        mb[2:7] = b'PAINT'
        mb[65:73] = b'PNTGMPNT'
        mb[83:87] = len(data).to_bytes(4, 'big')
        data = bytes(mb) + data
    return data


def random_lines(rng):
    lines = []
    for y in range(LINES):
        kind = rng.randrange(3)
        if kind == 0:
            lines.append(bytes([rng.choice([0, 0xFF, 0xAA, 0x55])]) * WIDTH)
        elif kind == 1:
            lines.append(bytes(rng.randrange(256) for _ in range(WIDTH)))
        else:
            line = bytearray(WIDTH)
            for _ in range(rng.randrange(1, 6)):
                a = rng.randrange(WIDTH)
                line[a:a + rng.randrange(1, 20)] = bytes([rng.randrange(256)]) * 19
            lines.append(bytes(line[:WIDTH]))
    return lines


def selftest():
    rng = random.Random(1)
    for i in range(40):
        lines = random_lines(rng)
        data = pack(lines, rng, version=i % 2 * 2, macbinary=i % 3 == 0, noise=i % 4 == 0)
        got, offsets = unpack(data)
        assert got == lines
        assert offsets[0] == data_offset(data)
        try:
            unpack(data[:-1])
        except Bad:
            pass
        else:
            raise AssertionError('a cut file unpacked')
    print('selftest: 40 documents round-trip')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('picture', nargs='?')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    data = Path(args.picture).read_bytes()
    lines, offsets = unpack(data)
    print('%s: 720 lines, data at %d, last line at %d of %d bytes'
          % (args.picture, offsets[0], offsets[-1], len(data)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
