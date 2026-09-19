#!/usr/bin/env python3
"""Apple Pascal (UCSD) volumes: the reference for the PASCAL overlay.

    pascal_ref.py IMAGE.po          # lists what the overlay must list
    pascal_ref.py --selftest

A Pascal volume is the simplest of the Apple II filesystems and the reason
it can be read at all in an overlay's window: two boot blocks, then a flat
directory of four blocks (2,048 bytes) at block 2, and files laid out in
one contiguous run of blocks each. There are no extents, no allocation
bitmap and no subdirectories -- a file is its first block, the block after
its last, and how many bytes of that last block it uses.

The directory is 78 entries of 26 bytes. Entry 0 describes the volume:

    +0  (word)  0
    +2  (word)  the block after the directory, always 6
    +4  (word)  0
    +6  length byte, then the name, 7 characters
    +14 (word)  blocks on the volume
    +16 (word)  files in the directory
    +18 (word)  last access date
    +20 (word)  the date last set

Each file entry that follows:

    +0  (word)  first block
    +2  (word)  the block after its last
    +4  (word)  kind, in the low four bits
    +6  length byte, then the name, 15 characters
    +22 (word)  bytes used in the last block
    +24 (word)  modification date

so its length is (last - first - 1) * 512 + bytes in the last block. A date
word is the year in bits 9-15, the day in 4-8 and the month in 0-3; a zero
month means no date at all, which is what an unset entry carries.

The kinds are UCSD's: 0 untyped, 1 bad blocks, 2 code, 3 text, 4 info,
5 data, 6 graf, 7 foto, 8 secure directory. ProDOS has types of its own for
three of them -- $02 PCD, $03 PTX, $05 PDA -- and nothing for the rest,
which come out untyped.

A .TEXT file carries a 1,024-byte header of zeros and then pages of 1,024
bytes in which a run of leading spaces is written $10 followed by 32 plus
the count. This reference reads the file's bytes as they are; turning that
page format into plain text is another matter, and the overlay does not
pretend to.
"""
import struct
import sys

DIR_BLOCK = 2
DIR_BLOCKS = 4
ENTRY = 26
MAX_ENTRIES = 77                # besides the volume entry itself
KINDS = ('untyped', 'bad', 'code', 'text', 'info', 'data', 'graf', 'foto',
         'securedir')
# The ProDOS type each kind becomes on extraction; 0 when ProDOS has none.
PRODOS_TYPE = {2: 0x02, 3: 0x03, 5: 0x05}


def date_word(year, month, day):
    """The UCSD word: year in bits 9-15, day in 4-8, month in 0-3."""
    if not 0 <= month <= 12 or not 0 <= day <= 31:
        raise ValueError('impossible date')
    return ((year % 100) << 9) | (day << 4) | month


def read_date(word):
    """(year, month, day), or None when the entry carries no date."""
    month = word & 15
    if not month or month > 12:
        return None
    return (word >> 9) & 127, month, (word >> 4) & 31


def volume(image, order='po'):
    """The volume entry and its files, or None when this is not Pascal.

    `image` is the whole container as 512-byte ProDOS-ordered blocks.
    """
    if len(image) < (DIR_BLOCK + DIR_BLOCKS) * 512:
        return None
    d = image[DIR_BLOCK * 512:(DIR_BLOCK + DIR_BLOCKS) * 512]
    first, last, kind = struct.unpack_from('<HHH', d, 0)
    nlen = d[6]
    if first or last != DIR_BLOCK + DIR_BLOCKS or kind or not 1 <= nlen <= 7:
        return None
    name = d[7:7 + nlen].decode('latin-1')
    if not all(32 < ord(c) < 127 and c not in '$=?,' for c in name):
        return None
    blocks, count = struct.unpack_from('<HH', d, 14)
    if not blocks or count > MAX_ENTRIES or blocks * 512 > len(image):
        return None
    files = []
    for i in range(1, count + 1):
        e = d[i * ENTRY:(i + 1) * ENTRY]
        first, last, kind = struct.unpack_from('<HHH', e, 0)
        nlen = e[6]
        used, when = struct.unpack_from('<HH', e, 22)
        if not 1 <= nlen <= 15 or last <= first or last > blocks:
            return None
        if first < DIR_BLOCK + DIR_BLOCKS or not 1 <= used <= 512:
            return None
        files.append({
            'name': e[7:7 + nlen].decode('latin-1'),
            'first': first, 'last': last, 'kind': kind & 15,
            'used': used, 'date': read_date(when),
            'size': (last - first - 1) * 512 + used,
        })
    # Pascal keeps the directory in block order and files never overlap.
    for a, b in zip(files, files[1:]):
        if b['first'] < a['last']:
            return None
    return {'name': name, 'blocks': blocks, 'files': files}


def contents(image, entry):
    """The bytes of one file, its last block cut at the length recorded."""
    start = entry['first'] * 512
    end = (entry['last'] - 1) * 512
    return image[start:end] + image[end:end + entry['used']]


def make(name, files, blocks=280):
    """A Pascal volume image, for fixtures. `files` is a list of
    (name, kind, bytes)."""
    if len(files) > MAX_ENTRIES:
        raise ValueError('too many files for one Pascal directory')
    image = bytearray(blocks * 512)
    d = bytearray(DIR_BLOCKS * 512)
    struct.pack_into('<HHH', d, 0, 0, DIR_BLOCK + DIR_BLOCKS, 0)
    d[6] = len(name)
    d[7:7 + len(name)] = name.encode('ascii')
    struct.pack_into('<HH', d, 14, blocks, len(files))
    at = DIR_BLOCK + DIR_BLOCKS
    for i, (fname, kind, body) in enumerate(files, 1):
        n = max(1, (len(body) + 511) // 512)
        used = len(body) - (n - 1) * 512 if body else 0
        if used <= 0:
            used = 512
        if at + n > blocks:
            raise ValueError('the volume is full')
        e = bytearray(ENTRY)
        struct.pack_into('<HHH', e, 0, at, at + n, kind)
        e[6] = len(fname)
        e[7:7 + len(fname)] = fname.encode('ascii')
        struct.pack_into('<HH', e, 22, used, date_word(26, 9, 19))
        d[i * ENTRY:(i + 1) * ENTRY] = e
        image[at * 512:at * 512 + len(body)] = body
        at += n
    image[DIR_BLOCK * 512:(DIR_BLOCK + DIR_BLOCKS) * 512] = d
    return bytes(image)


def _selftest():
    bodies = [('HELLO.TEXT', 3, bytes(1024) + b'Hello, Pascal.\r'.ljust(1024, b'\0')),
              ('SYSTEM.APPLE', 2, bytes(range(256)) * 20),
              ('SHORT', 5, b'x'),
              ('EXACT', 0, bytes(1024)),
              ('EMPTY', 0, b'')]
    img = make('MYVOL', bodies)
    v = volume(img)
    assert v is not None, 'our own image must read back'
    assert v['name'] == 'MYVOL' and v['blocks'] == 280, v
    assert [f['name'] for f in v['files']] == [b[0] for b in bodies]
    for entry, (fname, kind, body) in zip(v['files'], bodies):
        assert entry['kind'] == kind, entry
        got = contents(img, entry)
        if body:
            assert got == body, (fname, len(got), len(body))
        else:
            assert len(got) == 512, fname     # one block, all of it
        assert entry['size'] == len(got), (fname, entry['size'], len(got))
        assert entry['date'] == (26, 9, 19), entry
    # Nothing else is a Pascal volume.
    assert volume(bytes(280 * 512)) is None
    assert volume(b'') is None
    bad = bytearray(img)
    bad[DIR_BLOCK * 512 + 2] = 9                 # the directory does not end at 6
    assert volume(bytes(bad)) is None
    bad = bytearray(img)
    bad[DIR_BLOCK * 512 + 6] = 0                 # an empty volume name
    assert volume(bytes(bad)) is None
    bad = bytearray(img)
    struct.pack_into('<H', bad, DIR_BLOCK * 512 + ENTRY + 2, 3)   # last <= first
    assert volume(bytes(bad)) is None
    bad = bytearray(img)
    struct.pack_into('<H', bad, DIR_BLOCK * 512 + ENTRY * 2, 6)   # files overlap
    assert volume(bytes(bad)) is None
    bad = bytearray(img)
    struct.pack_into('<H', bad, DIR_BLOCK * 512 + 16, MAX_ENTRIES + 1)
    assert volume(bytes(bad)) is None
    assert read_date(0) is None and read_date(date_word(26, 9, 19)) == (26, 9, 19)
    print('pascal_ref: ok')


def main(argv):
    if '--selftest' in argv:
        _selftest()
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    image = open(argv[1], 'rb').read()
    v = volume(image)
    if not v:
        print('not an Apple Pascal volume')
        return 1
    print('%s: %u blocks, %u files' % (v['name'], v['blocks'], len(v['files'])))
    for f in v['files']:
        when = '%02u/%02u/%02u' % (f['date'][2], f['date'][1], f['date'][0]) \
            if f['date'] else '  --  '
        print('  %-15s %-8s %6u bytes  blocks %u-%u  %s'
              % (f['name'], KINDS[f['kind']] if f['kind'] < len(KINDS) else '?',
                 f['size'], f['first'], f['last'] - 1, when))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
