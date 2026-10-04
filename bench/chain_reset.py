#!/usr/bin/env python3
"""Ctrl-Reset after A2 File Cmd has launched a program (src/chain.s).

    make all disk && A2FC_BUILD=build A2FC_PRESET=iie python3 bench/chain_reset.py
    make ARCH=6502 all disk && A2FC_PRESET=iie_unenh python3 bench/chain_reset.py

A2FC's crt0 points the reset vector at its own _exit ($400C). Before 0.9.5
chain_load left it there, so Ctrl-Reset in a launched program jumped into
whatever that program had put at $400C (TAKE1.SYSTEM ran picture bytes).
On a throwaway volume:

- a movie launched by Return plays in FANTA.SYSTEM; Ctrl-Reset (the
  emulator's soft reset, through the ROM) brings A2FC back, as Escape does;
- a binary run by X that loads at $4000 and holds a loop at $400C gets the
  vector $FF59 / $5A (the monitor's OLDRST, as ProDOS leaves it at boot);
  Ctrl-Reset then lands in the monitor ("*"), not in the loop at $400C, and
  the program's bytes survive.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, ok_all, RET  # noqa: E402
import fantavision_ref as ref  # noqa: E402

PORT = 6981


def main():
    prog = bytearray(0x30)
    prog[0:3] = b'\x4C\x20\x40'                 # jmp $4020
    prog[0x0C:0x0F] = b'\x4C\x0C\x40'           # what a reset into $400C would run: a loop
    prog[0x20:0x28] = b'\xA9\xC1\x8D\x00\x04\x4C\x25\x40'   # an A on the screen, then a loop
    counted = ref.synthetic(21, frames=3, speed=2, count=1)
    files = {'WORK/PROG#064000': bytes(prog), 'WORK/M.COUNT#068400': counted}

    with tempfile.TemporaryDirectory(prefix='a2fc-reset-') as tmp:
        with boot_hd(Path(tmp), files, port=PORT) as (p, s):
            def pc():
                return p.rq('/cpu')['pc']

            def work():
                s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
                s.select('WORK'); s.key(RET); p.stable()

            work()
            s.ok('A2FC keeps its own vector while it runs ($400C)', p.peek(0x03F2, 3) == b'\x0c\x40\xe5',
                 p.peek(0x03F2, 3).hex())
            # FANTA.SYSTEM, then Ctrl-Reset while it plays.
            s.select('M.COUNT'); s.key(RET)
            player = ref.Player(counted)
            list(player.play())
            s.wait(lambda: bytes(p.peek(0x2000, 0x2000)) == bytes(player.pages[1]), 'the last frame', 180)
            vec = int.from_bytes(p.peek(0x03F2, 2), 'little')
            s.ok('FANTA.SYSTEM: the vector is its own way back', 0xA400 <= vec < 0xBB00, '$%04X' % vec)
            p.rq('/reset', {'kind': 'soft'})
            s.wait(lambda: s.has('Type  Aux'), 'A2FC again after Ctrl-Reset', 180)
            s.ok('Ctrl-Reset in FANTA.SYSTEM brings A2FC back', True)
            p.stable()
            if not s.has('PROG'):
                work()
            # A binary, run by X.
            s.select('PROG'); s.key(b'X')
            s.wait(lambda: s.has('Run PROG?'), 'the question', 30)
            s.key(b'Y')
            t0 = time.time()
            while time.time() - t0 < 60 and not 0x4025 <= pc() <= 0x4027:
                if s.has('Configuration warning.'):
                    s.key(b'Y')
                time.sleep(0.2)
            s.ok('the binary runs at $4000', 0x4025 <= pc() <= 0x4027, hex(pc()))
            s.ok('the vector handed over: $FF59 / $5A', p.peek(0x03F2, 3) == b'\x59\xff\x5a',
                 p.peek(0x03F2, 3).hex())
            p.rq('/reset', {'kind': 'soft'})
            s.wait(lambda: any(r.startswith('*') for r in s.rows40()), 'the monitor prompt', 30)
            s.ok('Ctrl-Reset in the binary: the monitor, not the loop at $400C', not 0x400C <= pc() <= 0x400E,
                 hex(pc()))
            s.ok('the program\'s bytes survive', p.peek(0x4000, 0x30) == bytes(prog))
    return ok_all(s, 'chain_reset')


if __name__ == '__main__':
    sys.exit(main())
