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
    newsroom_ref.py --clip-png OUTDIR CLIPDISK.dsk...   the pages of a
                                 commercial clip-art disk (needs Pillow)

Springboard's commercial clip-art disks (docs/NEWSROOM-FORMAT.md, "Commercial
clip-art disks") are read by clip_index, clip_table, clip_piece and
clip_page; make_clip_disk builds a synthetic one.
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


# -- commercial clip-art disks ------------------------------------------------

CLIP_W, CLIP_H = 252, 192        # a page, in dots and rows
CLIP_LEFT = 14                   # its left edge on the hi-res screen (2 bytes)


def clip_sector(disk, t, s):
    return disk[(t * 16 + s) * 256:(t * 16 + s + 1) * 256]


def clip_index(disk):
    """(disk name, side, [page names]) or ValueError."""
    if len(disk) != 143360:
        raise ValueError('not a 140 KB disk')
    b = clip_sector(disk, 34, 0) + clip_sector(disk, 34, 1)
    if bytes(c & 0x7F for c in b[:9]) != b'SSI CLIP\0':
        raise ValueError('no SSI CLIP index')
    try:
        end = b.index(0, 9)
        name = bytes(c & 0x7F for c in b[9:end]).decode('ascii')
        n, p, names = b[0x1B], 0x1C, []
        for _ in range(n):
            e = b.index(0, p)
            names.append(bytes(c & 0x7F for c in b[p:e]).decode('ascii'))
            p = e + 1
    except ValueError:
        raise ValueError('index runs past track 34 sector 1')
    if not names:
        raise ValueError('no pages')
    return name, b[0x1A], names


def clip_table(disk, npages):
    """For each page, its pieces' (track, sector, offset)."""
    b = b''.join(clip_sector(disk, 34, s) for s in range(6, 16))
    pages, cur, p = [], [], 0
    while len(pages) < npages:
        if p >= len(b):
            raise ValueError('location table runs past track 34')
        if b[p] == 0xFF:
            pages.append(cur); cur = []; p += 1
            continue
        if p + 3 > len(b):
            raise ValueError('location table runs past track 34')
        t, s, o = b[p], b[p + 1], b[p + 2]
        if t > 33 or s > 15 or (t, s) in ((0, 0), (17, 0), (17, 1)):
            raise ValueError('a piece outside the data tracks')
        cur.append((t, s, o)); p += 3
    return pages


class _Clip:
    def __init__(self, disk, t, s, o):
        self.d, self.t, self.s, self.o = disk, t, s, o

    def byte(self):
        if self.t > 33:
            raise ValueError('a piece runs past track 33')
        v = self.d[(self.t * 16 + self.s) * 256 + self.o]
        self.o += 1
        if self.o == 256:
            self.o, self.s = 0, self.s + 1
            if self.s == 16:
                self.s, self.t = 0, self.t + 1
            if (self.t, self.s) == (17, 0):
                self.s = 2                  # the VTOC and the notice
        return v


def clip_piece(disk, loc):
    """((y1, y2, x1, x2), strips: list of bytes columns)."""
    r = _Clip(disk, *loc)
    y1, y2, x1, x2 = r.byte(), r.byte(), r.byte(), r.byte()
    if y1 > y2 or x1 > x2 or y2 >= CLIP_H or x2 >= CLIP_W:
        raise ValueError('a bad piece header %s' % ((y1, y2, x1, x2),))
    h, strips = y2 - y1 + 1, (x2 - x1 + 7) // 7
    total, out = h * strips, bytearray()
    while len(out) < total:
        b = r.byte()
        if b == 0:
            n, v = r.byte(), r.byte()
            if n == 0 or v == 0:
                raise ValueError('a bad run')
            out += bytes([v]) * n
        else:
            out.append(b)
    if len(out) != total:
        raise ValueError('a run past the piece')
    return (y1, y2, x1, x2), [out[c * h:(c + 1) * h] for c in range(strips)]


def clip_page(disk, locs):
    """The page on a black hi-res page (8192 bytes), dots CLIP_LEFT on."""
    page = bytearray(8192)
    for loc in locs:
        (y1, y2, x1, x2), strips = clip_piece(disk, loc)
        for c, col in enumerate(strips):
            for r, b in enumerate(col):
                for k in range(7):
                    x = x1 + 7 * c + k
                    if x <= x2 and (b >> k) & 1:
                        X = x + CLIP_LEFT
                        page[row_address(y1 + r) + X // 7] |= 1 << (X % 7)
    return bytes(page)


def make_clip_disk(rng, npages=3, pieces=(1, 4), name='TEST CLIP', side=1):
    """A synthetic clip-art disk: (disk bytes, [page names], [pages' pieces])."""
    disk = bytearray(143360)
    data, table, names, spec = bytearray(), bytearray(), [], []
    t, s, o = 0, 1, 0

    def loc_of(n):                  # the (t, s, o) of the n-th data byte
        t, s, o = 0, 1, 0
        for _ in range(n // 256):
            s += 1
            if s == 16:
                s, t = 0, t + 1
            if (t, s) == (17, 0):
                s = 2
        return t, s, n % 256
    for k in range(npages):
        names.append('PAGE %d' % (k + 1))
        ps = []
        for _ in range(rng.randint(*pieces)):
            y1 = rng.randrange(CLIP_H); y2 = min(CLIP_H - 1, y1 + rng.randrange(40))
            x1 = rng.randrange(CLIP_W); x2 = min(CLIP_W - 1, x1 + rng.randrange(60))
            h, strips = y2 - y1 + 1, (x2 - x1 + 7) // 7
            raw = bytes(rng.choice([0x80, 0x80, 0x7F, rng.randrange(1, 128)]) for _ in range(h * strips))
            enc, i = bytearray([y1, y2, x1, x2]), 0
            while i < len(raw):
                j = i
                while j < len(raw) and raw[j] == raw[i] and j - i < 255:
                    j += 1
                if j - i >= 4:
                    enc += bytes([0, j - i, raw[i]]); i = j
                else:
                    enc.append(raw[i]); i += 1
            table += bytes(loc_of(len(data)))
            data += enc
            ps.append(((y1, y2, x1, x2), raw))
        table.append(0xFF)
        spec.append(ps)
    pos = 0
    for n, b in enumerate(data):
        t, s, o = loc_of(n)
        disk[(t * 16 + s) * 256 + o] = b
    idx = bytearray(b'SSI CLIP\0' + name.encode() + b'\0')
    idx = bytearray(c | 0x80 if c else 0 for c in idx)
    idx += bytes(0x1A - len(idx)) + bytes([side, npages])
    for nm in names:
        idx += bytes(c | 0x80 for c in nm.encode()) + b'\0'
    disk[34 * 4096:34 * 4096 + len(idx)] = idx
    disk[34 * 4096 + 6 * 256:34 * 4096 + 6 * 256 + len(table)] = table
    return bytes(disk), names, spec


def clip_selftest():
    rng = random.Random(1985)
    for _ in range(20):
        disk, names, spec = make_clip_disk(rng, npages=rng.randint(1, 6))
        dname, side, got = clip_index(disk)
        assert (dname, side, got) == ('TEST CLIP', 1, names)
        pages = clip_table(disk, len(got))
        for locs, ps in zip(pages, spec):
            for loc, (hdr, raw) in zip(locs, ps):
                h2, strips = clip_piece(disk, loc)
                assert h2 == hdr and b''.join(strips) == raw
            page = clip_page(disk, locs)
            assert len(page) == 8192 and not any(page[row_address(y)] or page[row_address(y) + 1]
                                                 for y in range(192))   # the margin stays black
    for bad in (bytes(143360), bytes(1000)):
        try:
            clip_index(bad)
        except ValueError:
            continue
        raise AssertionError('accepted a disk without an index')
    disk = bytearray(make_clip_disk(rng, npages=1, pieces=(1, 1))[0])
    loc = clip_table(bytes(disk), 1)[0][0]
    disk[(loc[0] * 16 + loc[1]) * 256 + loc[2]] = 200      # y1 past y2
    try:
        clip_piece(bytes(disk), loc)
    except ValueError:
        pass
    else:
        raise AssertionError('accepted a bad header')


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
    clip_selftest()
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
    if len(argv) > 3 and argv[1] == '--clip-png':
        from PIL import Image
        import os
        for path in argv[3:]:
            disk = open(path, 'rb').read()
            name, side, names = clip_index(disk)
            for k, (pname, locs) in enumerate(zip(names, clip_table(disk, len(names)))):
                try:
                    page = clip_page(disk, locs)
                except ValueError as e:
                    print('%s: %s refused: %s' % (path, pname, e))
                    continue
                img = Image.new('1', (280, 192))
                img.putdata([(page[row_address(y) + x // 7] >> (x % 7)) & 1 for y in range(192) for x in range(280)])
                img.save(os.path.join(argv[2], '%s_%d_%02d_%s.png' % (name, side, k + 1, pname.replace('/', '_'))))
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
