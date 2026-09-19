#!/usr/bin/env python3
"""LZC (UNIX "compress"): the reference for UNSHRINK's NuFX formats 4 and 5.

    lzc_ref.py FILE.Z            # writes the expanded bytes on stdout
    lzc_ref.py --compress FILE   # writes a .Z stream on stdout
    lzc_ref.py --selftest

NuFX thread formats 4 (12-bit) and 5 (16-bit) hold a whole UNIX `compress`
stream, header included: $1F $9D then a flags byte, the low five bits the
maximum code width and bit 7 the block mode. GS/ShrinkIt 1.1 reads them,
P8 ShrinkIt does not; the original NuLib is what wrote them.

The codes are LZW, least significant bits first, 9 bits wide to start.
Code 256 is CLEAR in block mode, so the first free code is 257 (256
without it). A code widens when the next free entry passes the current
width, and the table stops growing once it reaches the maximum width --
`compress` then keeps coding with a frozen table until a CLEAR.

The one subtlety, and the reason this file exists: the stream is read in
groups of eight codes, `bits` bytes at a time. Whenever the width changes
-- growing, or falling back to 9 on a CLEAR -- the rest of the current
group is dropped and the next code starts on the next group. An encoder
that packs the codes end to end reads back as garbage after the first
widening. This mirrors Nu_LZC_nextcode (nufxlib Lzc.c), itself taken from
compress v4.0, and is checked against /usr/bin/compress in --selftest.

Widths run from 12 (`compress`'s own floor, and NuFX format 4) to 16
(format 5). A nine-bit table is full before it starts and `compress`
handles it its own way; NuFX never asks for one, and neither does this.
"""
import shutil
import subprocess
import sys

MAGIC = b'\x1f\x9d'
CLEAR = 256
INIT_BITS = 9
MIN_BITS = 12                   # compress's floor, and NuFX format 4
MAX_MAX_BITS = 16
BIT_MASK = 0x1F
BLOCK_MASK = 0x80


class BitReader:
    """The group reader of compress v4.0: `bits` bytes, eight codes."""

    def __init__(self, data):
        self.data = data
        self.at = 0                 # next byte of the stream
        self.buf = b''              # the group being read
        self.size = 0               # its length in bits
        self.offset = 0             # the bit read within it
        self.bits = INIT_BITS
        self.prevbits = 0

    def next(self):
        if self.prevbits != self.bits:
            self.prevbits = self.bits
            self.size = 0
        if self.size - self.offset < self.bits:
            n = min(self.bits, len(self.data) - self.at)
            if n <= 0:
                return None
            self.buf = self.data[self.at:self.at + n]
            self.at += n
            self.size = n * 8
            self.offset = 0
        shift = self.offset
        i = shift >> 3
        shift &= 7
        code = self.buf[i] >> shift
        shift = 8 - shift
        code |= (self.buf[i + 1] if i + 1 < len(self.buf) else 0) << shift
        shift += 8
        if shift < self.bits:
            code |= (self.buf[i + 2] if i + 2 < len(self.buf) else 0) << shift
        self.offset += self.bits
        return code & ~(~0 << self.bits)


class BitWriter:
    """The matching writer: a group is padded before the width changes."""

    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.nacc = 0
        self.count = 0              # codes written in the current group

    def put(self, code, bits):
        self.acc |= code << self.nacc
        self.nacc += bits
        while self.nacc >= 8:
            self.out.append(self.acc & 0xFF)
            self.acc >>= 8
            self.nacc -= 8
        self.count += 1

    def pad(self, bits):
        """Finish the group of eight codes at the width just used."""
        while self.count % 8:
            self.put(0, bits)
        self.count = 0

    def flush(self):
        """End of stream: the last partial byte, and nothing more. Padding
        the group here would hand the reader a ninth code of zeros, which
        it would decode as a byte the file never held."""
        if self.nacc:
            self.out.append(self.acc & 0xFF)
            self.acc = self.nacc = 0


def expand(data, limit=None, stats=None):
    """The bytes a NuFX format 4/5 thread (or a .Z file) holds.

    `stats`, a dict, comes back with 'clears' counting the CLEAR codes the
    stream carried: the path a decoder only takes on a long enough file,
    and the one a fixture has to prove it reaches."""
    if len(data) < 3 or data[:2] != MAGIC:
        raise ValueError('not a compress stream')
    flags = data[2]
    maxbits = flags & BIT_MASK
    block = bool(flags & BLOCK_MASK)
    if maxbits > MAX_MAX_BITS or maxbits < MIN_BITS:
        raise ValueError(f'{maxbits} bits: outside {MIN_BITS}-{MAX_MAX_BITS}')
    maxcode = ~(~0 << maxbits)
    r = BitReader(data[3:])
    prefix = [0] * (maxcode + 1)
    suffix = [0] * (maxcode + 1)
    out = bytearray()
    if stats is not None:
        stats['clears'] = -1        # the CLEAR that starts every stream
    savecode = CLEAR
    cleartable = True
    fulltable = False
    prefxcode = 0
    sufxchar = 0
    nextfree = 0
    highcode = 0
    while True:
        code = savecode
        if code == CLEAR and cleartable:
            if stats is not None:
                stats['clears'] += 1
            r.bits = INIT_BITS
            highcode = ~(~0 << INIT_BITS)
            fulltable = False
            cleartable = block
            nextfree = 257 if block else 256
            prefxcode = r.next()
            if prefxcode is None:
                break
            sufxchar = prefxcode & 0xFF
            out.append(sufxchar)
        else:
            token = bytearray()
            if code >= nextfree and not fulltable:
                if code != nextfree:
                    raise ValueError(f'code ${code:X} past the table')
                code = prefxcode                    # the KwKwK case
                token.append(sufxchar)
            while code >= 256:
                if code <= prefix[code]:
                    raise ValueError('corrupt table')
                token.append(suffix[code])
                code = prefix[code]
            sufxchar = code
            out.append(sufxchar)
            out += bytes(reversed(token))
            if not fulltable:
                code = nextfree
                prefix[code] = prefxcode
                suffix[code] = sufxchar
                prefxcode = savecode
                code += 1
                if code - 1 == highcode:
                    if highcode >= maxcode:
                        fulltable = True
                        code -= 1
                    else:
                        r.bits += 1
                        highcode += code
                nextfree = code
        if limit is not None and len(out) > limit:
            raise ValueError('more output than the thread declares')
        savecode = r.next()
        if savecode is None:
            break
    return bytes(out)


def compress(data, maxbits=12, block=True, stats=None):
    """A .Z stream for `data`.

    `stats`, a dict, comes back with 'frozen' set once the table filled:
    from there on `compress` itself watches its ratio and sends a CLEAR,
    which this encoder does not imitate, so the two streams part company.
    Up to that point they are the same bytes. Fixtures that must carry a
    CLEAR come from `compress` itself, not from here."""
    if not MIN_BITS <= maxbits <= MAX_MAX_BITS:
        raise ValueError(f'{maxbits} bits: outside {MIN_BITS}-{MAX_MAX_BITS}')
    maxcode = ~(~0 << maxbits)
    if stats is not None:
        stats['frozen'] = False
    if not data:
        return b''          # what `compress` writes, and NuFX stores empty
    w = BitWriter()
    out = bytearray(MAGIC + bytes([maxbits | (BLOCK_MASK if block else 0)]))
    table = {}
    bits = INIT_BITS
    highcode = ~(~0 << INIT_BITS)
    nextfree = 257 if block else 256
    prefxcode = data[0]
    for ch in data[1:]:
        key = (prefxcode, ch)
        if key in table:
            prefxcode = table[key]
            continue
        w.put(prefxcode, bits)
        # `compress` widens at the END of the call that wrote the code, on
        # the free count as it stood BEFORE the new entry: one code later
        # than "as soon as the entry is made". The reader is one entry
        # behind the writer, and this is what puts them on the same code.
        if nextfree > highcode:
            w.pad(bits)
            bits += 1
            # At the last width the ceiling becomes one past the largest
            # code, so the test never fires again: from there `compress`
            # keeps coding with a frozen table until its ratio drops.
            highcode = (maxcode + 1) if bits >= maxbits else ~(~0 << bits)
            if bits >= maxbits and stats is not None:
                stats['frozen'] = True
        if nextfree <= maxcode:
            table[key] = nextfree
            nextfree += 1
        prefxcode = ch
    w.put(prefxcode, bits)
    w.flush()
    out += w.out
    return bytes(out)


def _selftest():
    import os
    import tempfile
    if shutil.which('compress') is None:
        raise SystemExit('lzc_ref --selftest needs UNIX compress (ncompress)')
    bodies = [
        b'',
        b'A',
        b'hello hello hello hello world world world\n',
        bytes(range(256)) * 40,
        b'the same line again.\r' * 400,
        os.urandom(5000),
        bytes(3000),
        # Long enough, and incompressible enough, that `compress` fills its
        # table, sees its ratio fall and sends a CLEAR: the path below.
        os.urandom(60000),
    ]
    clears = 0
    with tempfile.TemporaryDirectory(prefix='lzc-ref-') as tmp:
        for i, body in enumerate(bodies):
            src = os.path.join(tmp, 'body%d' % i)
            with open(src, 'wb') as f:
                f.write(body)
            for bits in (12, 13, 14, 16):
                z = subprocess.run(['compress', '-b', str(bits), '-c', src],
                                   capture_output=True)
                assert z.returncode == 0, f'compress refused: {z.stderr}'
                # The strong oracle: as long as the table has room, our
                # stream IS the one /usr/bin/compress writes, byte for byte.
                stats = {}
                ours = compress(body, bits, stats=stats)
                assert stats['frozen'] or ours == z.stdout, \
                    f'ours differs from compress: {bits} bits, body {i}'
                assert not body or expand(ours) == body, \
                    f'our own round trip: {bits} bits, body {i}'
                if body:
                    seen = {}
                    assert expand(z.stdout, stats=seen) == body, \
                        f'expand {bits}, body {i}'
                    clears += seen['clears']
                # gzip reads .Z too, but only from 12 bits up.
                if bits >= 12 and body:
                    g = subprocess.run(['gzip', '-dc'], input=z.stdout,
                                       capture_output=True)
                    assert g.returncode == 0 and g.stdout == body, \
                        f'gzip: {bits} bits, body {i}, {g.stderr}'
                ours = compress(body, bits, block=False)
                assert not body or expand(ours) == body, \
                    f'no block mode {bits} bits, body {i}'
    # A stream whose table filled sends CLEAR: the fixtures must reach it.
    assert clears, 'no CLEAR in any fixture: that path is untested'
    # A truncated stream is data, not a crash.
    full = compress(bytes(range(256)) * 40, 12)
    for cut in (3, 4, 17, len(full) // 2, len(full) - 1):
        try:
            expand(full[:cut])
        except ValueError:
            pass
    for bad in (b'', b'\x1f', b'\x1f\x9e\x8c', bytes([0x1f, 0x9d, 0x8B]),
                bytes([0x1f, 0x9d, 0x89]), bytes([0x1f, 0x9d, 0x91])):
        try:
            expand(bad)
            raise AssertionError('accepted %r' % bad)
        except ValueError:
            pass
    print('lzc_ref: ok')


def main(argv):
    if '--selftest' in argv:
        _selftest()
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == '--compress':
        sys.stdout.buffer.write(compress(open(argv[2], 'rb').read()))
    else:
        sys.stdout.buffer.write(expand(open(argv[1], 'rb').read()))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
