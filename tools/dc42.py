#!/usr/bin/env python3
"""DiskCopy 4.2 disk images: the reference for IMGFS and IMGCONV.

    dc42.py wrap IMAGE.PO OUT.DC [--name NAME]
    dc42.py unwrap IMAGE.DC OUT.PO
    dc42.py --selftest

A DiskCopy 4.2 file (Apple II File Type Note $E0/8005; CiderPress II's
DiskCopy notes) is an 84-byte header, big-endian throughout, then the
512-byte blocks in order, then 12 bytes of tag data per block or none:

    +$00 /64  the disk name, a length byte first
    +$40 / 4  the data size (a multiple of 512)
    +$44 / 4  the tag size (a multiple of 12, may be 0)
    +$48 / 4  the data checksum
    +$4C / 4  the tag checksum (0 without tags; the first 12 bytes are
              left out)
    +$50 / 1  the disk format: 0 400K, 1 800K, 2 720K, 3 1440K
    +$51 / 1  the format byte: $24 for an Apple II 800K disk
    +$52 / 2  $0100

The checksum adds each big-endian 16-bit word to a 32-bit sum and rotates
the sum right by one bit after each addition.
"""
import argparse
import sys
from pathlib import Path

HEADER = 84
FORMATS = {800: (0, 0x12), 1600: (1, 0x24), 1440: (2, 0x22), 2880: (3, 0x22)}


class Bad(ValueError):
    pass


def checksum(data):
    s = 0
    for i in range(0, len(data) - 1, 2):
        s = (s + (data[i] << 8 | data[i + 1])) & 0xFFFFFFFF
        s = ((s >> 1) | (s << 31)) & 0xFFFFFFFF
    return s


def wrap(blocks, name=b'A2FC'):
    """The DiskCopy file for these ProDOS-order blocks (no tags)."""
    n = len(blocks) // 512
    if len(blocks) % 512 or n not in FORMATS:
        raise Bad('DiskCopy holds 400K, 800K, 720K or 1440K disks')
    fmt, byte = FORMATS[n]
    head = bytearray(HEADER)
    head[0] = len(name)
    head[1:1 + len(name)] = name
    head[0x40:0x44] = len(blocks).to_bytes(4, 'big')
    head[0x48:0x4C] = checksum(blocks).to_bytes(4, 'big')
    head[0x50] = fmt
    head[0x51] = byte
    head[0x52:0x54] = b'\x01\x00'
    return bytes(head) + bytes(blocks)


def header(data):
    """(data size, tag size) after the checks every reader makes."""
    if len(data) < HEADER or data[0] > 63 or data[0x52:0x54] != b'\x01\x00':
        raise Bad('no DiskCopy 4.2 header')
    size = int.from_bytes(data[0x40:0x44], 'big')
    tags = int.from_bytes(data[0x44:0x48], 'big')
    if not size or size % 512 or HEADER + size > len(data):
        raise Bad('data size')
    return size, tags


def unwrap(data):
    size, _ = header(data)
    return data[HEADER:HEADER + size]


def selftest():
    assert checksum(b'') == 0
    assert checksum(b'\x00\x01') == 0x80000000
    assert checksum(b'\x00\x01\x00\x01') == 0xC0000000
    blocks = bytes((i * 7 + i // 512) & 255 for i in range(1600 * 512))
    dc = wrap(blocks, b'TEST')
    assert unwrap(dc) == blocks and header(dc) == (len(blocks), 0)
    for bad in (dc[:83], dc[:0x52] + b'\x00\x00' + dc[0x54:], dc[:-1]):
        try:
            unwrap(bad)
        except Bad:
            continue
        raise AssertionError('accepted a bad image')
    try:
        wrap(bytes(280 * 512))
    except Bad:
        pass
    else:
        raise AssertionError('wrapped a 140K disk')
    print('selftest: checksum, wrap, unwrap, refusals')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('action', nargs='?', choices=('wrap', 'unwrap'))
    ap.add_argument('src', nargs='?')
    ap.add_argument('dst', nargs='?')
    ap.add_argument('--name', default='A2FC')
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    data = Path(args.src).read_bytes()
    out = wrap(data, args.name.encode()) if args.action == 'wrap' else unwrap(data)
    Path(args.dst).write_bytes(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
