"""Generated PT3 with identical notes at small or far-apart file offsets.

No borrowed music. Instruments, ornaments and three patterns cross pages;
the largest fixture reads its last pattern byte at offset $FFFE.
"""


def module(size=65535, rows=64, speed=6):
    if size == 2048:
        table, sample, ornament, patterns = 512, 766, 1022, (1040, 1280, 1791)
    elif size == 16384:
        table, sample, ornament, patterns = 4608, 8190, 12286, (12544, 13053, size - rows - 1)
    elif size == 65535:
        table, sample, ornament, patterns = 4608, 16638, 32766, (36864, 41213, size - rows - 1)
    else:
        raise ValueError('fixture size must be 2048, 16384 or 65535')
    assert 1 <= rows <= 128 and 1 <= speed <= 255
    b = bytearray([0xA5]) * size
    b[:512] = bytes(512)
    b[:14] = b'ProTracker 3.6'
    b[30:62] = b'A2FC CACHE TEST'.ljust(32, b' ')
    b[66:98] = b'GENERATED TEST DATA'.ljust(32, b' ')
    b[99:103] = bytes([1, speed, 1, 0])
    def word(offset, value):
        b[offset:offset + 2] = value.to_bytes(2, 'little')
    word(103, table)
    word(107, sample)
    word(169, ornament)
    b[201:203] = bytes([0, 255])
    b[sample:sample + 6] = bytes([0, 1, 1, 15, 0, 0])
    b[ornament:ornament + 3] = bytes([0, 1, 0])
    for channel, start in enumerate(patterns):
        word(table + 2 * channel, start)
        b[start:start + rows + 1] = bytes(0x60 + (i // 8 + channel * 4) % 24 for i in range(rows)) + b'\0'
    return bytes(b)


def used_pages(data):
    """Sparse pages sufficient to play module(); used by the sim65 fixture."""
    def word(p):
        return int.from_bytes(data[p:p + 2], 'little')
    table = word(103)
    regions = [(0, 512), (table, 6), (word(107), 6), (word(169), 3)]
    for i in range(3):
        start = word(table + 2 * i)
        end = data.index(0, start)
        regions.append((start, end - start + 1))
    pages = sorted({p for start, length in regions for p in range(start // 256, (start + length - 1) // 256 + 1)})
    return [(p, data[p * 256:(p + 1) * 256].ljust(256, b'\xA5')) for p in pages]
