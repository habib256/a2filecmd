#!/usr/bin/env python3
"""SQueeze (.QQ) and ACU (AppleLink, "fZink"): the reference for UNSQ.

    squeeze_ref.py FILE          # prints what UNSQ extracts
    squeeze_ref.py --selftest

SQueeze (CiderPress II's Squeeze notes; the public-domain USQ): a Huffman
code over a run-length code. A standalone file starts $76 $FF, a 16-bit
checksum (the sum of the output bytes) and the original name ended by a
zero; then, as inside ACU, a 16-bit node count and the nodes, two signed
16-bit children each (>= 0 another node, < 0 the literal -(child + 1),
256 the end), and the bits, least significant first. The run-length code:
$90 n repeats the previous byte to n in all (n >= 2); $90 0 is $90 itself.

ACU (AppleLink-PE, CiderPress II's AppleLink notes): a 20-byte header --
the record count, "fZink" at +4 -- then records: a $36-byte header (data
fork method at +1, 0 stored or 3 squeezed; its archived length at +$12;
access, type, aux at +$16; storage at +$20, $0D a directory; the plain
length at +$26; the name length at +$32), the name, the resource fork,
the data fork.

unsqueeze(data, wrapper) -> [(name, type, aux, bytes)] or raises Bad, as
src/plugins/unsq.c decides; squeeze() and make_acu() build test files.
"""
import heapq
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unwrap_ref import prodos_name  # noqa: E402

DLE = 0x90
EOF_SYM = 256


class Bad(ValueError):
    pass


def decode_stream(data, i):
    """The bytes of a squeezed stream at i (node count first), and where it
    ends (the byte after the last one used)."""
    if i + 2 > len(data):
        raise Bad('cut')
    n = struct.unpack('<H', data[i:i + 2])[0]
    i += 2
    if n > 256 or i + 4 * n > len(data):
        raise Bad('tree')
    nodes = [struct.unpack('<hh', data[i + 4 * k:i + 4 * k + 4]) for k in range(n)]
    i += 4 * n
    out = bytearray()
    if n == 0:
        return bytes(out), i
    bits, bpos = 0, 8
    last = None
    rep = False

    def symbol():
        nonlocal bits, bpos, i
        node = 0
        while True:
            if bpos == 8:
                if i >= len(data):
                    raise Bad('cut in the bits')
                bits, bpos = data[i], 0
                i += 1
            b = (bits >> bpos) & 1
            bpos += 1
            if node >= n:
                raise Bad('node out of the tree')
            child = nodes[node][b]
            if child < 0:
                return -(child + 1)
            node = child

    while True:
        c = symbol()
        if c == EOF_SYM:
            return bytes(out), i
        if c > EOF_SYM:
            raise Bad('bad symbol')
        if c == DLE:
            k = symbol()
            if k == EOF_SYM or k > 255:
                raise Bad('bad count')
            if k == 0:
                out.append(DLE)
                last = DLE
            else:
                if last is None:
                    raise Bad('run with nothing to repeat')
                out += bytes([last]) * (k - 1)
        else:
            out.append(c)
            last = c


def unsqueeze(data, wrapper):
    if data[:2] == b'\x76\xff':
        if len(data) < 5:
            raise Bad('cut')
        check = struct.unpack('<H', data[2:4])[0]
        end = data.find(b'\0', 4)
        if end < 0:
            raise Bad('name')
        raw = data[4:end]
        name = prodos_name(raw.split(b'/')[-1].split(b':')[-1])
        body, _ = decode_stream(data, end + 1)
        if sum(body) & 0xFFFF != check:
            raise Bad('checksum')
        if not name:
            name = prodos_name(wrapper.encode())
            if name.endswith('.QQ'):
                name = name[:-3]
        return [(name, None, None, body)]
    if len(data) >= 20 and data[4:9] == b'fZink':
        count = struct.unpack('<H', data[0:2])[0]
        i = 20
        out = []
        for _ in range(count):
            if i + 0x36 > len(data):
                raise Bad('cut header')
            h = data[i:i + 0x36]
            rmethod, dmethod = h[0], h[1]
            rlen, dlen = struct.unpack('<II', h[0x0E:0x16])
            ftype = h[0x18]
            aux = struct.unpack('<H', h[0x1A:0x1C])[0]
            storage = h[0x20]
            plain = struct.unpack('<I', h[0x26:0x2A])[0]
            nlen = struct.unpack('<H', h[0x32:0x34])[0]
            i += 0x36
            if nlen > 64 or i + nlen > len(data):
                raise Bad('name')
            name = data[i:i + nlen]
            i += nlen
            if i + rlen + dlen > len(data):
                raise Bad('cut fork')
            i += rlen
            fork = data[i:i + dlen]
            i += dlen
            if storage == 0x0D:
                continue
            if dmethod == 3:
                body, used = decode_stream(fork, 0)
            elif dmethod == 0:
                body = fork
            else:
                raise Bad('method')
            if len(body) != plain:
                raise Bad('length')
            out.append((prodos_name(name.split(b'/')[-1]), ftype, aux, body))
        return out
    raise Bad('not SQueeze or ACU')


# -- encoders (tests) ----------------------------------------------------------

def rle(data):
    out = bytearray()
    i = 0
    while i < len(data):
        c = data[i]
        j = i
        while j < len(data) and data[j] == c and j - i < 255:
            j += 1
        n = j - i
        if c == DLE:
            out += bytes([DLE, 0])
            i += 1
            continue
        if n > 2:
            out += bytes([c, DLE, n])
            i = j
        else:
            out.append(c)
            i += 1
    return bytes(out)


def build_tree(symbols):
    """Nodes for the symbols' frequencies, root first."""
    freq = {}
    for s in symbols:
        freq[s] = freq.get(s, 0) + 1
    heap = [(f, k, ('leaf', s)) for k, (s, f) in enumerate(sorted(freq.items()))]
    heapq.heapify(heap)
    k = len(heap)
    if len(heap) == 1:
        f, _, only = heap[0]
        heap.append((0, k, ('leaf', only[1])))
    while len(heap) > 1:
        a = heapq.heappop(heap)
        b = heapq.heappop(heap)
        k += 1
        heapq.heappush(heap, (a[0] + b[0], k, ('node', a[2], b[2])))
    root = heap[0][2]
    nodes, codes = [], {}

    def place(t):
        idx = len(nodes)
        nodes.append(None)
        kids = []
        for bit, child in enumerate(t[1:]):
            if child[0] == 'leaf':
                kids.append(-(child[1] + 1))
            else:
                kids.append(place(child))
        nodes[idx] = tuple(kids)
        return idx

    def walk(t, path):
        if t[0] == 'leaf':
            codes[t[1]] = path
        else:
            walk(t[1], path + [0])
            walk(t[2], path + [1])
    place(root)
    walk(root, [])
    return nodes, codes


def encode_stream(data):
    syms = list(rle(data)) + [EOF_SYM]
    nodes, codes = build_tree(syms)
    out = bytearray(struct.pack('<H', len(nodes)))
    for a, b in nodes:
        out += struct.pack('<hh', a, b)
    acc, n = 0, 0
    for s in syms:
        for b in codes[s]:
            acc |= b << n
            n += 1
            if n == 8:
                out.append(acc)
                acc, n = 0, 0
    if n:
        out.append(acc)
    return bytes(out)


def squeeze(data, name=b'FILE.TXT'):
    return b'\x76\xff' + struct.pack('<H', sum(data) & 0xFFFF) + name + b'\0' + encode_stream(data)


def make_acu(files):
    """files: [(name bytes, type, aux, data, squeezed?, is_dir)]"""
    head = bytearray(20)
    head[0:2] = struct.pack('<H', len(files))
    head[2:4] = b'\x01\x00'
    head[4:9] = b'fZink'
    head[9] = 1
    head[10:12] = struct.pack('<H', 0x36)
    head[19] = 0xDD
    body = bytearray()
    for name, ftype, aux, data, sq, isdir in files:
        fork = encode_stream(data) if sq else data
        h = bytearray(0x36)
        h[1] = 3 if sq else 0
        h[0x12:0x16] = struct.pack('<I', len(fork))
        h[0x16:0x18] = b'\xc3\x00'
        h[0x18:0x1A] = struct.pack('<H', ftype)
        h[0x1A:0x1E] = struct.pack('<I', aux)
        h[0x20:0x22] = struct.pack('<H', 0x0D if isdir else 1)
        h[0x26:0x2A] = struct.pack('<I', len(data))
        h[0x32:0x34] = struct.pack('<H', len(name))
        body += h + name + fork
    return bytes(head + body)


def selftest():
    import random
    rng = random.Random(1)
    for size in (0, 1, 2, 3, 100, 5000):
        data = bytes(rng.choice(b'aab\x90\x90cccc\x00') for _ in range(size)) + b'z' * rng.randint(0, 300)
        sq = squeeze(data)
        assert unsqueeze(sq, 'X.QQ') == [('FILE.TXT', None, None, data)]
        try:
            unsqueeze(sq[:2] + bytes([sq[2] ^ 1]) + sq[3:], 'X.QQ')
        except Bad:
            pass
        else:
            raise AssertionError('checksum not checked')
    acu = make_acu([(b'DIR', 0x0F, 0, b'', False, True),
                    (b'DIR/NOTE', 4, 0, b'hello\r' * 50, True, False),
                    (b'RAW', 6, 0x2000, bytes(range(256)), False, False)])
    assert unsqueeze(acu, 'A.ACU') == [('NOTE', 4, 0, b'hello\r' * 50), ('RAW', 6, 0x2000, bytes(range(256)))]
    print('selftest: SQueeze streams, checksums, ACU records')


def main():
    if sys.argv[1:] == ['--selftest']:
        selftest()
        return 0
    p = Path(sys.argv[1])
    for name, t, a, body in unsqueeze(p.read_bytes(), p.name):
        print('%s: %d bytes%s' % (name, len(body), '' if t is None else ', $%02X/$%04X' % (t, a)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
