#!/usr/bin/env python3
"""Refuse a Mini build that would reach into DOS, and report what is left.

A 48 KB Apple II+ running DOS 3.3 leaves $2000-$7FFF for the program.
Above that sit DOS's file buffers and RWTS: overrunning them would not
fail at link time, it would corrupt whatever DOS is holding, including a
sector on its way to a disk. So the limit is checked here, on every link,
and the remaining room is printed rather than left to be guessed at.
"""
import re
import sys
from pathlib import Path

# $8000 upward belongs to DOS 3.3 on a 48 KB machine.
DOS_FLOOR = 0x8000
LOAD = 0x2000


def segments(text):
    found = {}
    body = text.split('Segment list:', 1)
    if len(body) != 2:
        raise SystemExit('not an ld65 map file')
    for line in body[1].split('\n'):
        m = re.match(r'^(\S+)\s+([0-9A-F]{6})\s+([0-9A-F]{6})\s+([0-9A-F]{6})', line)
        if m:
            found[m.group(1)] = (int(m.group(2), 16), int(m.group(3), 16),
                                 int(m.group(4), 16))
    return found


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: check_mini_layout.py build-mini/mini.map')
    segs = segments(Path(sys.argv[1]).read_text())
    for name in ('STARTUP', 'CODE', 'RODATA', 'DATA', 'BSS'):
        if name not in segs:
            raise SystemExit(f'{name} missing from the map')
    if segs['STARTUP'][0] != LOAD:
        raise SystemExit(f'STARTUP must start at ${LOAD:04X}: BRUN enters there')
    end = max(start + size for start, _, size in segs.values())
    code = sum(segs[n][2] for n in ('STARTUP', 'CODE', 'RODATA', 'DATA'))
    free = DOS_FLOOR - end
    print(f'mini: code+data {code} bytes, BSS {segs["BSS"][2]} bytes, '
          f'ends at ${end:04X}, {free} bytes free below DOS at ${DOS_FLOOR:04X}')
    if free < 0:
        raise SystemExit('mini: the program would overwrite DOS 3.3')


if __name__ == '__main__':
    main()
