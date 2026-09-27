#!/usr/bin/env python3
"""The Newsroom (Springboard, 1984) photos PH.* and banners BN.*: reference.

A user file is a DOS 3.3 B file loaded at $4000 (BIN $06, auxtype $4000 once
copied to ProDOS). Its body, after the four-byte B header, is:

    +0  L, 16 bits little-endian: the bitmap's length in bytes
    +2  y1, y2, x1, x2: the frame on the Newsroom's editing screen
    +6  the clip history (its first byte a count), ended by $FF
    ... the bitmap, the last L bytes: (x2 - x1) div 7 + 1 bytes a row,
        y2 - y1 + 1 rows, seven dots a byte, bit 0 left, 1 = white

The history may hold $FF bytes of its own (22 of 125 real files do), so the
bitmap is located from the end, never at the first $FF.  docs/NEWSROOM-FORMAT.md
has the whole story; this module is the oracle of src/plugins/newsroom.s.

    newsroom_ref.py --selftest
    newsroom_ref.py --png OUTDIR DISK.dsk...    (needs Pillow)
"""
import random
import sys


def row_address(y):
    """Offset of hi-res row y in page 1 ($2000)."""
    return (y & 7) * 1024 + ((y >> 3) & 7) * 128 + (y >> 6) * 40


def parse(body):
    """(width in bytes, height, bitmap) or a ValueError: the viewer's checks."""
    if len(body) < 6:
        raise ValueError('no frame')
    size = len(body)
    L = body[0] | body[1] << 8
    y1, y2, x1, x2 = body[2:6]
    if y2 < y1 or y2 - y1 > 191 or x2 < x1:
        raise ValueError('bad frame')
    wb, h = (x2 - x1) // 7 + 1, y2 - y1 + 1
    if L != wb * h:
        raise ValueError('L is not width x height')
    if size >= 65536 or size < L + 8:
        raise ValueError('no room for the history and $FF')
    if body[size - L - 1] != 0xFF:
        raise ValueError('no $FF before the bitmap')
    return wb, h, body[size - L:]


def page(body):
    """The 8,192-byte hi-res page the viewer draws: black, the picture
    centered, each byte with its palette bit clear."""
    wb, h, bitmap = parse(body)
    out = bytearray(8192)
    top, left = (192 - h) // 2, (40 - wb) // 2
    for r in range(h):
        at = row_address(top + r) + left
        out[at:at + wb] = bytes(b & 0x7F for b in bitmap[r * wb:(r + 1) * wb])
    return bytes(out)


def pixels(body):
    """Rows of 0/1 dots (1 = white), for a PNG."""
    wb, h, bitmap = parse(body)
    return [[(bitmap[y * wb + x // 7] >> (x % 7)) & 1 for x in range(wb * 7)] for y in range(h)]


def make(rng, wb=None, h=None, history=None, x1=None, y1=None):
    """A well-formed body: a random frame, history and bitmap."""
    wb = wb or rng.randint(1, 37)
    h = h or rng.randint(1, 192)
    x1 = rng.randint(0, 255 - 7 * (wb - 1)) if x1 is None else x1
    x2 = x1 + 7 * (wb - 1) + rng.randint(0, min(6, 255 - x1 - 7 * (wb - 1)))
    y1 = rng.randint(0, 255 - (h - 1)) if y1 is None else y1
    if history is None:
        n = rng.randint(0, 6)
        history = bytes([n]) + bytes(rng.randrange(256) for _ in range(13 * n))
    L = wb * h
    bitmap = bytes(rng.randrange(256) for _ in range(L))
    return bytes([L & 255, L >> 8, y1, y1 + h - 1, x1, x2]) + history + b'\xff' + bitmap


# -- DOS 3.3 B files, for the real disks -------------------------------------

def dos33_files(disk):
    """(name, body) of every PH./BN. B file of a DOS-order .dsk."""
    def sec(t, s):
        return disk[(t * 16 + s) * 256:(t * 16 + s + 1) * 256]
    vtoc = sec(17, 0)
    t, s, seen = vtoc[1], vtoc[2], set()
    while (t or s) and (t, s) not in seen and t < 35 and s < 16:
        seen.add((t, s))
        cat = sec(t, s)
        for i in range(7):
            e = cat[11 + 35 * i:46 + 35 * i]
            if e[0] in (0, 0xFF) or e[2] & 0x7F != 0x04:
                continue
            name = bytes(c & 0x7F for c in e[3:33]).decode('latin1').rstrip()
            if name[:3] not in ('PH.', 'BN.'):
                continue
            data, tt, ts, tseen = [], e[0], e[1], set()
            while (tt or ts) and (tt, ts) not in tseen and tt < 35 and ts < 16:
                tseen.add((tt, ts))
                tsl = sec(tt, ts)
                for k in range(122):
                    a, b = tsl[12 + 2 * k], tsl[13 + 2 * k]
                    data.append(sec(a, b) if a or b else bytes(256))
                tt, ts = tsl[1], tsl[2]
            raw = b''.join(data)
            if raw[0] | raw[1] << 8 != 0x4000:
                continue
            yield name, raw[4:4 + (raw[2] | raw[3] << 8)]
        t, s = cat[1], cat[2]


def selftest():
    rng = random.Random(1984)
    for _ in range(200):
        body = make(rng)
        wb, h, bitmap = parse(body)
        assert len(bitmap) == wb * h and len(page(body)) == 8192
    # A $FF inside the history, as PH.CATS has: the first $FF is not the end.
    body = make(rng, wb=3, h=2, history=bytes([2]) + b'\x01\x17\xff\x00' + bytes(9))
    assert parse(body)[2] == body[-6:]
    # The largest picture fills 37 bytes x 192 rows, centered on byte 1.
    body = make(rng, wb=37, h=192, x1=0, y1=0)
    shown = page(body)
    assert shown[row_address(0)] == 0 and shown[row_address(0) + 1] == body[-37 * 192] & 0x7F
    for bad in (body[:-1], body + b'\0', body[:5], b'\0' * 8,
                bytes([6, 0, 5, 4, 0, 0, 0, 0xFF]) + bytes(6)):
        try:
            parse(bad)
        except ValueError:
            continue
        raise AssertionError('accepted a malformed body')
    print('newsroom_ref: selftest ok')


def main(argv):
    if argv[1:] == ['--selftest']:
        selftest()
        return 0
    if len(argv) > 3 and argv[1] == '--png':
        from PIL import Image
        import os
        for path in argv[3:]:
            for name, body in dos33_files(open(path, 'rb').read()):
                rows = pixels(body)
                img = Image.new('1', (len(rows[0]), len(rows)))
                img.putdata([d for r in rows for d in r])
                img.save(os.path.join(argv[2], name.replace('/', '_') + '.png'))
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
