#!/usr/bin/env python3
"""Banc de FANTA.SYSTEM, le lecteur de films Fantavision, dans POM2.

    make disk pom2host && python3 bench/fantavision.py [--preset iie_unenh]

A throwaway volume boots a stand-in launcher (A1.SYSTEM, assembled here):
it waits in page 3 for a path poked at $0203 and a flag at $0202, then
loads FANTA.SYSTEM at $2000 and stores the path at $2006 -- what A2 File
Cmd does through its chain thunk. The same program is the volume's
A2FILE.SYSTEM and counts at $0200 the returns to it. For each movie:

- a counted movie plays to its last frame: pages 1 and 2 and the background
  copy end exactly as tools/fantavision_ref.py says, the movie at $8000 is
  the file; two seconds later it plays again from frame 0; Escape returns,
  the ProDOS bitmap is given back;
- a movie with a damaged tail plays its whole frames, then Escape returns;
- backdrops: M.PARADIES takes PARADIES of its directory, M.PARADIES,STREAM
  takes STREAM (an 8,184-byte save); pages and background copy end as the
  reference says; a named backdrop that is missing refuses the movie;
- a refused movie (header byte 3 wrong) shows its reason, draws nothing and
  returns after a key; so does a missing file;
- a looping movie keeps changing, Tab (accelerated speed) and Space (pause)
  are obeyed, Escape returns; so does Ctrl-Reset (the emulator's soft
  reset, through the ROM and the reset vector);
- S on a movie starts the slideshow: another movie of the directory is read
  (FANTA.SYSTEM relaunched from A2FILE/, as A2 File Cmd installs it);
- the disk image is byte for byte the same at the end: nothing written.
"""
import argparse
import random
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, ROOT  # noqa: E402
import fantavision_ref as ref  # noqa: E402

PORT = 6931
VOLUME = 'FANTAB'
# The mailbox, in page 2 below $0280 (ProDOS's: the path of the running
# system program). Not in page 3: FANTA.SYSTEM's return thunk fills
# $0300-$03CF, and a mailbox at $039D was overwritten by it -- every return
# then counted 1, and the second one timed out.
# the running system program).
RUNS, FAIL, FLAG, PATH = 0x0200, 0x0201, 0x0202, 0x0203

LAUNCHER = r'''
        .setcpu "6502"
        .org    $2000
        jmp     start
        .byte   $EE, $EE, $41
        .res    65
start:  cld
        inc     $0200
        lda     #0              ; RAM holds anything at power-up
        sta     $0202
        ldy     #thunk_end - thunk - 1
:       lda     thunk_src,y
        sta     $0300,y
        dey
        bpl     :-
        jmp     $0300
thunk_src:
        .org    $0300
thunk:  lda     $0202
        beq     thunk
        ldx     #0
        stx     $0202
        jsr     $BF00
        .byte   $C8
        .word   openp
        bcs     fail
        lda     ref
        sta     eref
        sta     rref
        jsr     $BF00
        .byte   $D1
        .word   eofp
        bcs     fail
        lda     eof
        sta     len
        lda     eof+1
        sta     len+1
        jsr     $BF00
        .byte   $CA
        .word   readp
        bcs     fail
        jsr     $BF00
        .byte   $CC
        .word   closep
        bcs     fail
        ldy     $0203
:       lda     $0203,y
        sta     $2006,y
        dey
        bpl     :-
        bit     $C082
        jmp     $2000
fail:   lda     #$EE
        sta     $0201
:       jmp     :-
openp:  .byte   3
        .word   name
        .word   $BB00
ref:    .byte   0
eofp:   .byte   2
eref:   .byte   0
eof:    .res    3
readp:  .byte   4
rref:   .byte   0
        .word   $2000
len:    .word   0
        .word   0
closep: .byte   1, 0
name:   .byte   12, "FANTA.SYSTEM"
thunk_end:
        .assert thunk_end <= $03D0, error, "the thunk overflows page 3"
'''


def launcher(tmp):
    src = tmp / 'launcher.s'
    src.write_text(LAUNCHER)
    obj = tmp / 'launcher.o'
    out = tmp / 'launcher.bin'
    subprocess.run(['ca65', '-o', str(obj), str(src)], check=True)
    subprocess.run(['ld65', '-t', 'none', '-o', str(out), str(obj)], check=True)
    return out.read_bytes()


def movies():
    counted = ref.synthetic(11, frames=3, speed=2, count=1)
    looping = ref.synthetic(12, frames=3, speed=1, count=0)
    bad = bytearray(ref.synthetic(13, frames=2))
    bad[3] = 5
    cut = bytearray(ref.synthetic(14, frames=4, speed=2, count=1))
    third = ref.scan(bytes(cut))[1][2]
    cut[third] = 3                      # an odd length: cut before frame 3
    rng = random.Random(1985)
    pic = bytes(rng.randrange(256) for _ in range(8192))
    stream = bytes(rng.randrange(256) for _ in range(8184))
    paradies = ref.synthetic(15, frames=3, speed=2, count=1)
    return {'M.COUNT': counted, 'M.LOOP': looping, 'M.BAD': bytes(bad), 'M.CUT': bytes(cut),
            'M.PARADIES': paradies, 'PARADIES': pic, 'STREAM': stream}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preset', default=os.environ.get('A2FC_PRESET', 'iie_unenh'))
    args = ap.parse_args()
    fanta = ROOT / 'build/FANTA.SYSTEM.SYS'
    if not fanta.exists():
        fanta = ROOT / 'build-6502/FANTA.SYSTEM.SYS'
    films = movies()
    with tempfile.TemporaryDirectory(prefix='a2fc-fanta-') as tmp:
        tmp = Path(tmp)
        stage = tmp / 'stage'
        stage.mkdir()
        shutil.copyfile(ROOT / 'data/PRODOS.SYS', stage / 'PRODOS.SYS')
        boot = launcher(tmp)
        (stage / 'A1.SYSTEM.SYS').write_bytes(boot)
        (stage / 'A2FILE.SYSTEM.SYS').write_bytes(boot)
        shutil.copyfile(fanta, stage / 'FANTA.SYSTEM.SYS')
        (stage / 'A2FILE').mkdir()        # where the slideshow relaunches it from
        shutil.copyfile(fanta, stage / 'A2FILE' / 'FANTA.SYSTEM.SYS')
        for name, data in films.items():
            aux = 0x8400 if name.startswith('M.') else 0x4000     # backdrops: BIN $4000
            (stage / ('%s#06%04X' % (name, aux))).write_bytes(data)
        hdv = tmp / 'FANTAB.hdv'
        subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(hdv),
                        '--volume', VOLUME, '--boot', str(ROOT / 'data/prodos_boot.tmpl'),
                        '--blocks', '1600'], check=True, capture_output=True)
        before = hdv.read_bytes()
        port = PORT + int(os.environ.get('A2FC_PORT_OFFSET', '0'))
        with Pom2(hdv, port=port, preset=args.preset) as p:
            s = Session(p, sym={})
            s.wait(lambda: p.peek(0x0300, 6) == boot[boot.index(b'\xAD\x02\x02'):][:6],
                   'the stand-in launcher waiting', 60)
            p.poke(RUNS, b'\x00')
            bitmap = p.peek(0xBF58, 24)
            runs = [0]

            def launch(name):
                path = ('/%s/%s' % (VOLUME, name)).encode()
                p.poke(PATH, bytes([len(path)]) + path)
                p.poke(FLAG, b'\x01')

            def returned(what):
                runs[0] += 1
                s.wait(lambda: p.peek(RUNS, 1)[0] == runs[0], what + ': back in A2FILE.SYSTEM', 60)
                s.ok(what + ': returned to A2FILE.SYSTEM, bitmap given back',
                     p.peek(0xBF58, 24) == bitmap and p.peek(FAIL, 1) != b'\xEE')

            def text():
                return '\n'.join(s.rows40())

            # A counted movie, to its last frame.
            player = ref.Player(films['M.COUNT'])
            shown = list(player.play())
            launch('M.COUNT')
            s.wait(lambda: p.peek(0x2000, 0x2000) == bytes(player.pages[1]) and
                   p.peek(0x4000, 0x2000) == bytes(player.pages[2]), 'the last frame', 120)
            s.ok('counted movie: both pages as the reference, %d frames' % len(shown), True)
            s.ok('counted movie: background copy as the reference',
                 p.peek(0x6000, 0x2000) == bytes(player.bg))
            s.ok('counted movie: the movie read whole at $8000',
                 p.peek(0x8000, len(films['M.COUNT'])) == films['M.COUNT'])
            s.wait(lambda: p.peek(0x2000, 0x2000) == bytes(shown[0][1]),
                   'frame 0 again', 120)
            s.ok('counted movie: plays again from the start, still in FANTA.SYSTEM',
                 p.peek(RUNS, 1)[0] == runs[0])
            s.key(b'\x1b')
            returned('counted movie')

            # A damaged tail: the whole frames before it play, then a key.
            cut = ref.Player(films['M.CUT'])
            n = len(list(cut.play()))
            launch('M.CUT')
            s.wait(lambda: p.peek(0x2000, 0x2000) == bytes(cut.pages[1]) and
                   p.peek(0x4000, 0x2000) == bytes(cut.pages[2]), 'the cut movie\'s last frame', 120)
            s.ok('cut movie: its %d whole frames played, pages as the reference (%d shown)'
                 % (len(cut.frames), n), True)
            s.key(b'\x1b')
            returned('cut movie')

            # Backdrops: the same name (M.PARADIES, PARADIES), then a named
            # one (a short 8,184-byte save), then a named one missing.
            for command, picture in (('M.PARADIES', films['PARADIES']),
                                     ('M.PARADIES,STREAM', films['STREAM'])):
                bd = ref.Player(films['M.PARADIES'], picture)
                list(bd.play())
                launch(command)
                s.wait(lambda: p.peek(0x2000, 0x2000) == bytes(bd.pages[1]) and
                       p.peek(0x4000, 0x2000) == bytes(bd.pages[2]), command + ': the last frame', 120)
                s.ok('backdrop %s: pages and background copy as the reference' % command,
                     p.peek(0x6000, 0x2000) == bytes(bd.bg))
                s.key(b'\x1b')
                returned('backdrop ' + command)
            launch('M.COUNT,NOPE')
            s.wait(lambda: 'THE BACKDROP CANNOT BE USED.' in text(), 'the backdrop refusal', 60)
            s.ok('a named backdrop missing: refused with its message', True)
            s.key(b' ')
            returned('backdrop missing')

            # A refused movie: nothing drawn.
            # (FANTA.SYSTEM's own file lands at $2000: past its end, nothing
            # of the pages or the background may change.)
            start = 0x2000 + fanta.stat().st_size
            pages = p.peek(start, 0x8000 - start)
            launch('M.BAD')
            s.wait(lambda: 'NOT A FANTAVISION MOVIE (CHECK 2).' in text(), 'the refusal', 60)
            s.ok('refused movie: the reason shown', 'PRESS A KEY TO RETURN.' in text())
            s.ok('refused movie: nothing drawn (pages and background untouched)',
                 p.peek(start, 0x8000 - start) == pages)
            s.key(b' ')
            returned('refused movie')

            # A missing file.
            launch('M.NONE')
            s.wait(lambda: 'THE MOVIE CANNOT BE READ.' in text(), 'the read error', 60)
            s.ok('missing movie: the error shown', True)
            s.key(b' ')
            returned('missing movie')

            # A looping movie: keys.
            launch('M.LOOP')
            loop = ref.Player(films['M.LOOP'])
            seen = {bytes(pg) for _, pg, _ in loop.play(limit=6)}
            s.wait(lambda: p.peek(0x2000, 0x2000) in seen, 'the looping movie drawn', 120)
            snaps = set()
            for _ in range(20):
                snaps.add(p.peek(0x2000, 0x2000) + p.peek(0x4000, 0x2000))
                time.sleep(0.05)
            s.ok('looping movie: keeps playing', len(snaps) > 1, len(snaps))
            s.key(b'\x09')                       # Tab: the accelerated speed
            time.sleep(0.5)
            s.key(b' ')                          # pause
            time.sleep(0.5)
            a = p.peek(0x2000, 0x2000) + p.peek(0x4000, 0x2000)
            time.sleep(1.0)
            b = p.peek(0x2000, 0x2000) + p.peek(0x4000, 0x2000)
            s.ok('looping movie: Space pauses', a == b)
            s.key(b' ')                          # resume
            s.wait(lambda: p.peek(0x2000, 0x2000) + p.peek(0x4000, 0x2000) != b,
                   'playing again', 60)
            s.ok('looping movie: Space resumes (accelerated speed)', True)
            s.key(b'\x1b')
            returned('looping movie, Escape')

            # Ctrl-Reset while a movie plays: back to A2FILE.SYSTEM as with
            # Escape (before 0.9.5 the vector was A2 File Cmd's $400C, in
            # hi-res page 2), and the vector is left on the monitor's OLDRST
            # once the thunk runs (its I/O buffer covers the program's end).
            launch('M.LOOP')
            s.wait(lambda: p.peek(0x2000, 0x2000) in seen, 'the looping movie drawn', 120)
            s.ok('Ctrl-Reset: the vector is the program\'s own way back',
                 0xA400 <= int.from_bytes(p.peek(0x03F2, 2), 'little') < 0xBB00)
            p.rq('/reset', {'kind': 'soft'})
            returned('looping movie, Ctrl-Reset')
            s.ok('Ctrl-Reset: the vector left on OLDRST ($FF59, valid)',
                 p.peek(0x03F2, 3) == b'\x59\xff\x5a')

            # The slideshow: S, and once round the movie gives way to
            # another of the directory (a refused one is shown, then skipped).
            launch('M.LOOP')
            s.wait(lambda: p.peek(0x2000, 0x2000) in seen, 'the looping movie drawn', 120)
            s.key(b'S')
            others = [n for n in films if n.startswith('M.') and n not in ('M.LOOP', 'M.BAD')]
            s.wait(lambda: any(p.peek(0x8000, len(films[n])) == films[n] for n in others),
                   'another movie read', 240)
            s.ok('slideshow: S goes on to another movie of the directory',
                 p.peek(RUNS, 1)[0] == runs[0])
            s.key(b'\x1b')
            returned('slideshow, Escape')
        s.ok('disk image unchanged: nothing written', hdv.read_bytes() == before)
    passed = sum(1 for c in s.checks if c['ok'])
    print('\n%d/%d controles (fantavision %s)' % (passed, len(s.checks), args.preset), flush=True)
    return 0 if passed == len(s.checks) else 1


if __name__ == '__main__':
    sys.exit(main())
