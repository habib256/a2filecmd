#!/usr/bin/env python3
"""Refuse a Mini build that would reach into DOS, and report what is left.

BRUN loads at $1000 so the editor and delete can sit below the hi-res page.
The resident program starts at $4000 and may run up to $95FF: $9600 is
Applesoft's HIMEM under this DOS, where the file buffers begin. Reaching
past it would not fail at link time, it would corrupt whatever DOS holds
there, including a sector on its way to a disk. So the limit is checked
on every link and the remaining room is printed rather than guessed at.
"""
import re
import sys
from pathlib import Path

DOS_FLOOR = 0x9600
BRUN = 0x1000
RESIDENT = 0x4000
LOW_CEILING = 0x2000
FORMAT_HOME = 0x0200        # format.s runs here, copied out of the image
DOS_VECTORS = 0x03D0        # and must stop before DOS's page-three vectors
HGR = 0x2000                # the working area: splash runs there once


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
    for name in ('LOWSTART', 'LOWCODE', 'FORMAT', 'INIT', 'STARTUP', 'CODE',
                 'RODATA', 'DATA', 'BSS'):
        if name not in segs:
            raise SystemExit(f'{name} missing from the map')
    fmt_start, _, fmt_size = segs['FORMAT']
    if fmt_start != FORMAT_HOME:
        raise SystemExit(f'FORMAT must run from ${FORMAT_HOME:04X}, not ${fmt_start:04X}')
    if fmt_start + fmt_size > DOS_VECTORS:
        raise SystemExit(f'FORMAT reaches ${fmt_start + fmt_size:04X}, into the DOS vectors')
    init_start, _, init_size = segs['INIT']
    if init_start < HGR or init_start + init_size > RESIDENT:
        raise SystemExit('INIT must lie inside the working area')
    if segs['LOWSTART'][0] != BRUN:
        raise SystemExit(f'LOWSTART must start at ${BRUN:04X}: BRUN enters there')
    if segs['STARTUP'][0] != RESIDENT:
        raise SystemExit(f'STARTUP must start at ${RESIDENT:04X}')
    low_end = segs['LOWSTART'][0] + segs['LOWSTART'][2]
    low_end = max(low_end, segs['LOWCODE'][0] + segs['LOWCODE'][2])
    if low_end > LOW_CEILING:
        raise SystemExit(f'LOW code reaches ${low_end:04X}, into the working area')
    end = max(start + size for start, _, size in segs.values() if start >= RESIDENT)
    code = sum(segs[n][2] for n in ('LOWSTART', 'LOWCODE', 'FORMAT', 'INIT',
                                    'STARTUP', 'CODE', 'RODATA', 'DATA'))
    free = DOS_FLOOR - end
    low_free = LOW_CEILING - low_end
    fmt_free = DOS_VECTORS - fmt_start - fmt_size
    print(f'mini: code+data {code} bytes, BSS {segs["BSS"][2]} bytes, '
          f'resident ends at ${end:04X}, {free} bytes free below DOS at '
          f'${DOS_FLOOR:04X}; LOW ends at ${low_end:04X}, {low_free} bytes '
          f'free below the working area; FORMAT {fmt_size} bytes at '
          f'${FORMAT_HOME:04X}, {fmt_free} bytes free below the DOS vectors')
    if free < 0:
        raise SystemExit('mini: the program would overwrite DOS 3.3')


if __name__ == '__main__':
    main()
