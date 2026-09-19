#!/usr/bin/env python3
"""Apple II CP/M volumes: the reference for reading one, and what is not
yet settled about them.

    cpm_ref.py IMAGE.po [--skew N]   # lists what a reader must list
    cpm_ref.py --selftest

A 5.25" Apple CP/M disk, from its disk parameter block: blocks of 1,024
bytes, 128 of them, the first three tracks reserved for CP/M itself, and
the first two blocks of what follows given to the directory. That makes 64
directory entries of 32 bytes:

    +0      user number, 0 to 15; $E5 means the entry is free
    +1..8   the name, eight characters, bit 7 of each an attribute
    +9..11  the type, three characters, bit 7 read-only / system / archive
    +12     EX, the low part of the extent number
    +13     S1, unused
    +14     S2, the high part of the extent number
    +15     RC, records used in this extent, a record being 128 bytes
    +16..31 sixteen block numbers, zero for none

One entry covers one extent, 16 KB: sixteen blocks of 1,024. A file longer
than that has several entries, ordered by EX + 32 * S2, and its length is
128 * (128 * extent + RC) of the last one. CP/M stores no exact length, so
a text file ends wherever its last record's $1A does; this reference gives
the record length, which is what the disk says.

**The sector order.** CP/M on the Apple II reads its 256-byte sectors
through a skew of its own, and the published tables disagree. This one was
measured rather than chosen: on disks from Asimov, the directory's eight
sectors were found by looking for 32-byte entries that read as entries, and
they fell where SKEWS['apple'] says and nowhere else.

A reader still does not have to trust it. `volume()` tries each candidate
and keeps the one whose directory explains itself -- user numbers, names
and block numbers all in range, no block claimed twice, and a name that is
not blank. A wrong order turns the directory into noise and fails that
test, so a disk written in an order not listed here is refused rather than
read wrongly. That is what happened before the table was measured, and it
is still what happens to CPAM40B.dsk, whose directory begins elsewhere.
"""
import struct
import sys

BLOCK = 1024                    # CP/M allocation block
RESERVED_TRACKS = 3
DIR_BLOCKS = 2
DIR_ENTRIES = 64
ENTRY = 32
BLOCKS = 128                    # DSM + 1
SECTORS = 16                    # 256-byte sectors a track
RECORD = 128

# ProDOS blocks hold two 256-byte sectors each, in this physical order.
PRODOS_ORDER = (0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15)

# CP/M's own logical-to-physical sector order. `apple` was measured, on
# 19 September 2026, on disks from Asimov (images/cpm): the eight sectors
# of the directory were found by looking for entries that read as entries,
# and they fell on 0, 6, 12 with the empty tail on 3, 5, 9, 14 and 15 --
# which is this table and no other. It reads CPM2.2(56k).dsk (19 files)
# and CPM MAG #01.DSK (8 files) whole. `none` is for an image some tool
# has already deblocked.
SKEWS = {
    'apple': (0, 6, 12, 3, 9, 15, 14, 5, 11, 2, 8, 7, 13, 4, 10, 1),
    'none': tuple(range(16)),
}


def sector_offset(track, physical):
    """Where physical sector `physical` of `track` lies in a ProDOS-ordered
    image, which is what a normalized block reader hands out."""
    k = PRODOS_ORDER.index(physical)
    return ((track * 8) + (k >> 1)) * 512 + (k & 1) * 256


def read_block(image, n, skew):
    """CP/M allocation block `n`, 1,024 bytes, out of a ProDOS-ordered image."""
    out = bytearray()
    for i in range(BLOCK // 256):
        logical = n * (BLOCK // 256) + i
        track = RESERVED_TRACKS + logical // SECTORS
        off = sector_offset(track, skew[logical % SECTORS])
        if off + 256 > len(image):
            return None
        out += image[off:off + 256]
    return bytes(out)


def _name_of(e):
    name = ''.join(chr(c & 127) for c in e[1:9]).rstrip()
    kind = ''.join(chr(c & 127) for c in e[9:12]).rstrip()
    return name + ('.' + kind if kind else '')


def plausible(directory):
    """Does this look like a CP/M directory, or like a wrong skew?

    Every live entry must carry a user number of 0 to 15, a printable name
    with no control characters or CP/M separators, a record count of at
    most 128, and block numbers inside the disk that no other entry claims.
    At least one live entry, or there is nothing to recognise.
    """
    used = set()
    live = 0
    for i in range(DIR_ENTRIES):
        e = directory[i * ENTRY:(i + 1) * ENTRY]
        if e[0] == 0xE5:
            continue
        if e[0] > 15:
            return False
        raw = ''.join(chr(c & 127) for c in e[1:12])
        if any(c < ' ' or c > '~' or c in '<>.,;:=?*[]|/\\' for c in raw):
            return False
        if not raw[:8].strip():
            return False                # a file with no name is not a file
        if e[15] > 128:
            return False
        for b in e[16:32]:
            if not b:
                continue
            if b >= BLOCKS or b < DIR_BLOCKS or b in used:
                return False
            used.add(b)
        live += 1
    return live > 0


def directory_of(image, skew):
    d = bytearray()
    for b in range(DIR_BLOCKS):
        got = read_block(image, b, skew)
        if got is None:
            return None
        d += got
    return bytes(d)


def volume(image, skew=None):
    """The files of a CP/M disk, or None. With no skew given, the one whose
    directory explains itself is found; the name of it comes back too."""
    names = [skew] if skew else list(SKEWS)
    for which in names:
        d = directory_of(image, SKEWS[which])
        if d is None or not plausible(d):
            continue
        extents = {}
        for i in range(DIR_ENTRIES):
            e = d[i * ENTRY:(i + 1) * ENTRY]
            if e[0] == 0xE5:
                continue
            key = (e[0], _name_of(e))
            number = e[12] + 32 * e[14]
            extents.setdefault(key, {})[number] = e
        files = []
        for (user, name), parts in sorted(extents.items()):
            blocks = []
            for number in sorted(parts):
                blocks += [b for b in parts[number][16:32] if b]
            last = parts[max(parts)]
            records = 128 * max(parts) + last[15]
            files.append({'user': user, 'name': name, 'blocks': blocks,
                          'records': records, 'size': records * RECORD,
                          'readonly': bool(last[9] & 0x80),
                          'system': bool(last[10] & 0x80)})
        return {'skew': which, 'files': files}
    return None


def contents(image, entry, skew):
    out = bytearray()
    for b in entry['blocks']:
        got = read_block(image, b, SKEWS[skew])
        if got is None:
            return None
        out += got
    return bytes(out[:entry['size']])


def make(files, skew='apple', tracks=35):
    """A CP/M disk image, ProDOS-ordered, for fixtures. `files` is a list of
    (name, bytes); names are NAME.TYP, eight and three."""
    image = bytearray(tracks * SECTORS * 256)
    table = SKEWS[skew]

    def put(n, data):
        for i in range(BLOCK // 256):
            logical = n * (BLOCK // 256) + i
            track = RESERVED_TRACKS + logical // SECTORS
            off = sector_offset(track, table[logical % SECTORS])
            image[off:off + 256] = data[i * 256:(i + 1) * 256].ljust(256, b'\0')

    d = bytearray(b'\xe5' * (DIR_BLOCKS * BLOCK))
    at = DIR_BLOCKS
    slot = 0
    for name, body in files:
        stem, _, kind = name.partition('.')
        records = (len(body) + RECORD - 1) // RECORD or 1
        nblocks = (len(body) + BLOCK - 1) // BLOCK or 1
        for extent in range((records + 127) // 128 or 1):
            e = bytearray(ENTRY)
            e[0] = 0
            e[1:9] = stem.ljust(8).encode('ascii')
            e[9:12] = kind.ljust(3).encode('ascii')
            e[12] = extent & 31
            e[14] = extent >> 5
            e[15] = min(128, records - 128 * extent)
            mine = []
            for i in range(min(16, nblocks - 16 * extent)):
                if at >= BLOCKS:
                    raise ValueError('the disk is full')
                mine.append(at)
                at += 1
            e[16:16 + len(mine)] = bytes(mine)
            d[slot * ENTRY:(slot + 1) * ENTRY] = e
            slot += 1
            if slot > DIR_ENTRIES:
                raise ValueError('too many directory entries')
        for i, b in enumerate(range(at - nblocks, at)):
            put(b, body[i * BLOCK:(i + 1) * BLOCK])
    for b in range(DIR_BLOCKS):
        put(b, d[b * BLOCK:(b + 1) * BLOCK])
    return bytes(image)


def _selftest():
    bodies = [('HELLO.TXT', b'Hello, CP/M.\r\n' * 10),
              ('BIG.DAT', bytes(range(256)) * 90),          # over one extent
              ('TINY.COM', b'\xc9'),
              ('EXACT.BIN', bytes(BLOCK))]
    for which in SKEWS:
        img = make(bodies, skew=which)
        v = volume(img)
        assert v is not None, which
        # The right skew is found without being told which it is.
        assert v['skew'] == which or \
            directory_of(img, SKEWS[v['skew']]) == directory_of(img, SKEWS[which]), \
            (which, v['skew'])
        got = {f['name']: f for f in v['files']}
        assert sorted(got) == sorted(n for n, _ in bodies), sorted(got)
        for name, body in bodies:
            f = got[name]
            data = contents(img, f, v['skew'])
            assert data[:len(body)] == body, (which, name)
            # CP/M rounds up to a record; nothing beyond that is claimed.
            assert 0 <= len(data) - len(body) < RECORD, (name, len(data), len(body))
    # Noise is not a volume, and neither is an empty disk.
    assert volume(bytes(35 * SECTORS * 256)) is None
    assert volume(b'') is None
    img = bytearray(make(bodies))
    for at in range(0, ENTRY * 4, ENTRY):
        bad = bytearray(img)
        off = sector_offset(RESERVED_TRACKS, SKEWS['apple'][0])
        bad[off + at] = 200                       # an impossible user number
        assert volume(bytes(bad)) is None, at
    print('cpm_ref: ok')


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
        print('not a CP/M volume this can read (no candidate skew explains it)')
        return 1
    print('CP/M, %s skew, %u files' % (v['skew'], len(v['files'])))
    for f in v['files']:
        print('  %-14s user %2u  %6u bytes  %u blocks%s%s'
              % (f['name'], f['user'], f['size'], len(f['blocks']),
                 '  R/O' if f['readonly'] else '', '  SYS' if f['system'] else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
