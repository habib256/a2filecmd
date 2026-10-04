#!/usr/bin/env python3
"""End-to-end bench: A2 File Cmd launches TAKE1.SYSTEM on a Take 1 movie,
and comes back.

    make all disk && python3 bench/take1.py                       (6502 edition)
    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/take1.py  (65C02)

Return on MV.* goes through RUN (src/launch.h), which loads
A2FILE/TAKE1.SYSTEM with one of its three commands (docs/TAKE1-FORMAT.md):
an extracted movie in a ProDOS folder (its path), a movie inside a DOS 3.3
.DSK image (the image's path and the movie's T/S list) and a refused movie.
The real ProDOS runs it here, not the fake MLI of tools/test_take1.py: its
buffer checks against the system bitmap, the interpreter start-up and the
way back through A2FILE.SYSTEM. Checked: the pages shown are frames of
tools/take1_ref.py's playback, the movie's files are read, Escape (or a key
after a refusal) brings A2FC back, AUX (so /RAM) is untouched.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, ok_all, RET
from pom2 import ROOT
import take1_ref as ref

PORT = 6873


def back_in_a2fc(s):
    s.wait(lambda: s.has('Type  Aux'), 'A2FC again', 240)


def frames_of(movie, files):
    player = ref.Player(movie, ref.dict_loader(files), movie_name=b'MV.DEMO')
    shown = set()
    for e in player.play():
        if e[0] == 'show':
            shown.add(bytes(e[-1]))
    return shown


def playing(p, shown):
    """True once a hi-res page holds one of the reference's frames."""
    return bytes(p.peek(0x2000, 0x2000)) in shown or bytes(p.peek(0x4000, 0x2000)) in shown


def main():
    movie, files = ref.synthetic(7, scenes=2, frames=4, fades=False)
    shown = frames_of(movie, files)
    stage = {'WORK/MV.DEMO#068029': movie}
    for name, data in files.items():
        stage['WORK/' + ref.prodos_name(name).decode() + '#060000'] = data
    dsk, where = ref.make_dsk({b'MV.DEMO': movie, **files})
    stage['WORK/MOVIE.DSK#060000'] = dsk
    bad = bytearray(movie)
    bad[41] = 18                                   # fade-in 18: refused
    stage['BAD/MV.DEMO#068029'] = bytes(bad)
    with tempfile.TemporaryDirectory(prefix='a2fc-take1-') as tmp:
        with boot_hd(Path(tmp), stage, port=PORT, blocks=1600) as (p, s):
            s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
            s.select('WORK'); s.key(RET); p.stable()
            aux = bytes(p.peek(0x1000, 0xB000, 'aux'))
            s.select('MV.DEMO'); s.key(RET)
            s.wait(lambda: playing(p, shown), 'a frame of the movie', 240)
            s.ok('Return on an extracted MV. plays it in TAKE1.SYSTEM (a frame of the reference)', True)
            back = next(int(l.split()[1], 16) for l in (ROOT / 'build/take1.lbl').read_text().splitlines()
                        if l.split()[2:] == ['.t1_back'])
            v = p.peek(0x03F2, 3)
            s.ok('Ctrl-Reset would return to A2FC: the reset vector is the player\'s way back',
                 v[0] | v[1] << 8 == back and v[2] == v[1] ^ 0xA5, v.hex())
            s.key(b'\x1b')
            back_in_a2fc(s)
            s.ok('Escape brings A2FC back', True)
            s.ok('AUX and /RAM untouched', bytes(p.peek(0x1000, 0xB000, 'aux')) == aux)
            p.stable()
            if not s.has('MOVIE.DSK'):
                s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
                s.select('WORK'); s.key(RET); p.stable()
            s.select('MOVIE.DSK'); s.key(RET); p.stable()
            s.wait(lambda: s.has('MV.DEMO'), 'the DOS 3.3 catalog', 60)
            s.select('MV.DEMO'); s.key(RET)
            s.wait(lambda: playing(p, shown), 'a frame of the movie from the image', 240)
            s.ok('Return on MV. in a DOS 3.3 image plays it (image path and T/S list)', True)
            s.key(b'\x1b')
            back_in_a2fc(s)
            s.ok('Escape brings A2FC back from the image', True)
            p.stable()
            s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
            s.select('BAD'); s.key(RET); p.stable()
            s.select('MV.DEMO'); s.key(RET)
            s.wait(lambda: any('NOT A VALID TAKE 1 FILE:' in r for r in s.rows40()), 'the refusal', 240)
            s.ok('a damaged movie is refused, named on the text screen',
                 any('MV.DEMO' in r for r in s.rows40()))
            s.key(b' ')
            back_in_a2fc(s)
            s.ok('a key brings A2FC back after a refusal', True)
            s.ok('AUX and /RAM still untouched', bytes(p.peek(0x1000, 0xB000, 'aux')) == aux)
    return ok_all(s)


if __name__ == '__main__':
    sys.exit(main())
