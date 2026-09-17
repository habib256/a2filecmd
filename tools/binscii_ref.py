#!/usr/bin/env python3
"""BinSCII: the reference for the SCIIBIN overlay.

    binscii_ref.py FILE...          # prints what SCIIBIN decodes
    binscii_ref.py --selftest

BinSCII (David Whitney, 1989; CiderPress II's BinSCII notes) carries a
ProDOS file as text, in chunks of 12,288 bytes. Each chunk is:

    FiLeStArTfIlEsTaRt
    <the 64-character alphabet>
    <name length + $40><name, 15 padded><36 characters: 27 bytes of
       attributes -- total length (3), offset (3), access, type, aux (2),
       storage, blocks (2), dates (8), segment length (3), CRC-16 (2),
       reserved -- little-endian, the CRC over the first 24>
    <data lines: 64 characters for 48 bytes, the last padded with zeros>
    <4 characters: the CRC-16 (XMODEM) of the data, padding included, and 0>

Four characters make three bytes: with v0..v3 their alphabet indexes,
    b1 = v3 << 2 | v2 >> 4, b2 = (v2 & 15) << 4 | v1 >> 2, b3 = (v1 & 3) << 6 | v0.
Lines end with CR, LF or CRLF; blanks around them and the high bit are
ignored, and text between chunks is skipped.

decode(texts) takes the parts in order and returns (name, access, type,
aux, data), or raises Bad: SCIIBIN writes the chunks in the order it meets
them, and each one must start where the previous one ended.
"""
import random
import sys
from pathlib import Path

SIGNATURE = 'FiLeStArTfIlEsTaRt'
SEGMENT = 12288
ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789()'


class Bad(ValueError):
    pass


def crc16(data, c=0):
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def lines(text):
    for raw in text.replace(b'\r\n', b'\n').replace(b'\r', b'\n').split(b'\n'):
        yield bytes(c & 0x7F for c in raw).strip(b' \t').decode('latin-1')


def unpack(chars, table):
    out = bytearray()
    for i in range(0, len(chars), 4):
        try:
            v0, v1, v2, v3 = (table[c] for c in chars[i:i + 4])
        except KeyError:
            raise Bad('character outside the alphabet')
        out += bytes([(v3 << 2 | v2 >> 4) & 255, ((v2 & 15) << 4 | v1 >> 2) & 255,
                      ((v1 & 3) << 6 | v0) & 255])
    return bytes(out)


def chunks(text):
    """Every chunk of one text: (name, attributes (27 bytes), data)."""
    it = lines(text)
    for line in it:
        if line.rstrip() != SIGNATURE:
            continue
        alpha = next(it, '')[:64]
        if len(alpha) != 64 or len(set(alpha)) != 64:
            raise Bad('alphabet')
        table = {c: i for i, c in enumerate(alpha)}
        head = next(it, '')
        n = ord(head[0]) - 0x40 if head else 0
        if not 1 <= n <= 15 or len(head) < 52:
            raise Bad('header')
        name = head[1:1 + n]
        attrs = unpack(head[16:52], table)
        if crc16(attrs[:24]) != attrs[24] | attrs[25] << 8:
            raise Bad('header CRC')
        seglen = int.from_bytes(attrs[21:24], 'little')
        if not 1 <= seglen <= SEGMENT:
            raise Bad('segment length')
        data = bytearray()
        for _ in range((seglen + 47) // 48):
            line = next(it, '')[:64]
            if len(line) != 64:
                raise Bad('data line')
            data += unpack(line, table)
        tail = next(it, '')[:4]
        if len(tail) != 4:
            raise Bad('CRC line')
        crc = unpack(tail, table)
        if crc16(data) != crc[0] | crc[1] << 8:
            raise Bad('data CRC')
        yield name, attrs, bytes(data[:seglen])


def decode(texts):
    """texts[0] is the selected file, the rest the files after it in the
    directory: they are read while the file is not complete, and the first
    one holding no chunk of it ends the search."""
    name = None
    out = bytearray()
    total = None
    for k, text in enumerate(texts):
        found = False
        for n, attrs, data in chunks(text):
            found = True
            if name is None:
                name, total = n, int.from_bytes(attrs[0:3], 'little')
                access, ftype, aux, storage = attrs[6], attrs[7], attrs[8] | attrs[9] << 8, attrs[10]
                if storage in (5, 0x0D) or ftype == 0x0F:
                    raise Bad('not a plain file')
            elif n != name or int.from_bytes(attrs[0:3], 'little') != total:
                raise Bad('parts missing' if k else 'chunks of another file')
            if int.from_bytes(attrs[3:6], 'little') != len(out):
                raise Bad('parts out of order or missing')
            out += data
            if len(out) == total:
                return name, access, ftype, aux, bytes(out)
        if name is None:
            raise Bad('no BinSCII chunk')
        if k and not found:
            break
    raise Bad('parts missing')


def encode(name, data, access=0xC3, ftype=6, aux=0, alphabet=ALPHABET, eol=b'\r'):
    """The BinSCII text of one file (tests); several chunks when it is big."""
    out = bytearray(b'Some notes before the file' + eol)
    enc = {i: c for i, c in enumerate(alphabet)}

    def pack(raw):
        s = ''
        for i in range(0, len(raw), 3):
            b1, b2, b3 = raw[i:i + 3]
            s += enc[b3 & 63] + enc[(b2 & 15) << 2 | b3 >> 6] + enc[(b1 & 3) << 4 | b2 >> 4] + enc[b1 >> 2]
        return s
    for off in range(0, max(len(data), 1), SEGMENT):
        seg = data[off:off + SEGMENT]
        attrs = bytearray(27)
        attrs[0:3] = len(data).to_bytes(3, 'little')
        attrs[3:6] = off.to_bytes(3, 'little')
        attrs[6], attrs[7] = access, ftype
        attrs[8:10] = aux.to_bytes(2, 'little')
        attrs[10] = 1
        attrs[21:24] = len(seg).to_bytes(3, 'little')
        attrs[24:26] = crc16(attrs[:24]).to_bytes(2, 'little')
        padded = seg + bytes(-len(seg) % 48)
        out += (SIGNATURE + '\n' + alphabet + '\n').encode().replace(b'\n', eol)
        out += bytes([0x40 + len(name)]) + name.encode().ljust(15) + pack(bytes(attrs)).encode() + eol
        for i in range(0, len(padded), 48):
            out += pack(padded[i:i + 48]).encode() + eol
        c = crc16(padded)
        out += pack(bytes([c & 255, c >> 8, 0])).encode() + eol
        out += b'-- between chunks --' + eol
    return bytes(out)


def selftest():
    rng = random.Random(1)
    for size in (1, 47, 48, 49, 12288, 12289, 30000):
        data = bytes(rng.randrange(256) for _ in range(size))
        text = encode('FILE.NAME', data, ftype=0xB3, aux=0xDB07, eol=rng.choice([b'\r', b'\n', b'\r\n']))
        assert decode([text]) == ('FILE.NAME', 0xC3, 0xB3, 0xDB07, data)
        if size > SEGMENT:
            parts = text.split(b'FiLeStArTfIlEsTaRt')
            first = parts[0] + b'FiLeStArTfIlEsTaRt' + parts[1]
            rest = b''.join(b'FiLeStArTfIlEsTaRt' + p for p in parts[2:])
            assert decode([first, rest])[4] == data
            assert decode([first, rest, b'unrelated'])[4] == data
            for bad in ([rest, first], [first], [first, b'no chunk here', rest]):
                try:
                    decode(bad)
                except Bad:
                    continue
                raise AssertionError('accepted parts out of order')
    alpha = ''.join(rng.sample(ALPHABET, 64))
    assert decode([encode('X', b'abc', alphabet=alpha)])[4] == b'abc'
    print('selftest: sizes, line ends, parts, alphabets')


def main():
    if sys.argv[1:] == ['--selftest']:
        selftest()
        return 0
    name, access, ftype, aux, data = decode([Path(p).read_bytes() for p in sys.argv[1:]])
    print('%s: %d bytes, $%02X/$%04X, access $%02X' % (name, len(data), ftype, aux, access))
    return 0


if __name__ == '__main__':
    sys.exit(main())
