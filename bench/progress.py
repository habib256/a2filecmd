#!/usr/bin/env python3
"""Progress under POM2: a long tool never leaves the screen still.

    make build-6502/crc.PLG build-6502/verify.PLG ARCH=6502 && python3 bench/progress.py

CRC reads a 48 KB file (some 250 cycles a byte through its bitwise CRC:
seconds of emulated time), VERIFY the whole 4 000-block volume.
Neither has room for a bar; both turn the resident's activity cell, $06F7
(row 21, last column, MAIN text page), between / and \\ once per block
(src/plugins/spin.h). The cell is sampled while each works: it must take
both glyphs, and the result must still be the right one -- the CRC against
zlib, VERIFY's count of blocks. Nothing is written anywhere.
"""
import random
import tempfile
import time
import zlib
from pathlib import Path

from xplug import boot_hd, menu_category, ok_all, RET

SLASH, BACKSLASH = 0xAF, 0xDC
BLOCKS = 4000


def launch(s, p, name):
    """menu_run without its settling pause: the sampling starts with the key."""
    s.key(b'!')
    s.wait(lambda: s.has('the overlays'), 'the overlay menu', 30)
    p.stable()
    menu_category(s, p, name)
    for _ in range(40):
        r = s.cursor_row(2)
        if r is not None and s.rows()[r][2:14].strip() == name:
            p.raw(RET)
            return
        s.key(name[0].encode())
        p.stable()
    raise AssertionError(name + ' not in the menu')


def sample(p, s, done, seconds=240):
    """How many times $06F7 changed to / or \\ until done() is true. The
    resident's loader ticks the same cell while the tool loads -- a few
    blocks -- so only dozens of changes are the tool's own."""
    turns, last = 0, None
    deadline = time.time() + seconds
    while not done():
        if time.time() > deadline:
            print('\n'.join(s.rows()), flush=True)
            raise AssertionError('timed out')
        c = p.peek(0x6F7, 1)[0]
        if c != last and c in (SLASH, BACKSLASH):
            turns += 1
        last = c
        time.sleep(0.01)
    return turns


def main():
    data = random.Random(6921).randbytes(48 * 1024)
    with tempfile.TemporaryDirectory(prefix='a2fc-progress-') as tmp:
        with boot_hd(Path(tmp), {'WORK/BIG.BIN': data}, port=6921, blocks=BLOCKS,
                     plugins=['crc', 'verify']) as (p, s):
            s.select('WORK')
            s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK')
            p.stable()
            s.select('BIG')

            launch(s, p, 'CRC')
            seen = sample(p, s, lambda: 'CRC-32' in s.rows()[22])
            expected = 'BIG: CRC-32 $%08X, %d bytes' % (zlib.crc32(data), len(data))
            s.ok('CRC: the right sum', s.rows()[22].strip() == expected, s.rows()[22].strip())
            s.ok('CRC: the activity cell turns while it reads', seen >= 20, seen)

            launch(s, p, 'VERIFY')
            sample(p, s, lambda: 'VERIFY:' in s.rows()[22])   # a hard disk file: too quick to count
            s.ok('VERIFY: the file reads', s.rows()[22].strip() == 'VERIFY: 1 read, 0 errors',
                 s.rows()[22].strip())

            s.key(b'/')
            s.wait(lambda: s.has('[Volumes]'), 'the volume list')
            p.stable()
            s.select('/WORKHD')
            launch(s, p, 'VERIFY')
            seen = sample(p, s, lambda: 'blocks read' in s.rows()[22])
            want = '/WORKHD: %u blocks read, 0 bad' % BLOCKS
            s.ok('VERIFY: every block of the volume', s.rows()[22].strip() == want, s.rows()[22].strip())
            s.ok('VERIFY: the activity cell turns over the volume', seen >= 20, seen)
    return ok_all(s, 'bench/progress.py')


if __name__ == '__main__':
    raise SystemExit(main())
