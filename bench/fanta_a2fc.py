#!/usr/bin/env python3
"""Banc de bout en bout : A2 File Cmd lance FANTA.SYSTEM sur un film, et y
revient.

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/fanta_a2fc.py

bench/fantavision.py eprouve le lecteur seul, derriere un lanceur de
substitution ; ici c'est A2FC lui-meme : Retour sur un film (BIN $8400)
passe par RUN (src/launch.h), qui charge A2FILE/FANTA.SYSTEM avec le chemin
complet du film et le prefixe sur le repertoire d'A2FC. Le film compte
joue jusqu'a sa derniere image, identique a tools/fantavision_ref.py ; une
touche ramene A2FC (A2FILE.SYSTEM recharge par le lecteur) ; une image
marquee (Espace) sert de decor, et sans marque l'image NOM a cote de M.NOM ;
un film refuse
dit pourquoi et ramene aussi A2FC ; AUX (donc /RAM) n'est jamais touche."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, ok_all, RET
import fantavision_ref as ref

PORT = 6863


def back_in_a2fc(s):
    s.wait(lambda: s.has('Type  Aux'), 'A2FC again', 180)


def main():
    counted = ref.synthetic(21, frames=3, speed=2, count=1)
    bad = bytearray(ref.synthetic(22, frames=2))
    bad[3] = 5                                   # header byte 3 must be 4
    # Backdrops: a picture marked by the user, and one named like its movie.
    pic = bytes((i * 7 + (i >> 8)) & 0xFF for i in range(8192))
    same = bytes((i * 13) & 0x7F for i in range(8192))
    films = {'M.COUNT': counted, 'M.SAME': ref.synthetic(23, frames=2, speed=1, count=1)}
    files = {'WORK/M.COUNT#068400': counted, 'WORK/M.BAD#068400': bytes(bad),
             'WORK/M.SAME#068400': films['M.SAME'], 'WORK/SAME#064000': same, 'WORK/PIC#064000': pic}
    with tempfile.TemporaryDirectory(prefix='a2fc-fanta-') as tmp:
        with boot_hd(Path(tmp), files, port=PORT) as (p, s):
            s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
            s.select('WORK'); s.key(RET); p.stable()
            aux = bytes(p.peek(0x1000, 0xB000, 'aux'))
            s.select('M.COUNT'); s.key(RET)
            player = ref.Player(counted)
            list(player.play())
            s.wait(lambda: bytes(p.peek(0x2000, 0x2000)) == bytes(player.pages[1]) and
                   bytes(p.peek(0x4000, 0x2000)) == bytes(player.pages[2]), 'the last frame', 180)
            s.ok('Return on a movie plays it in FANTA.SYSTEM, to the reference\'s last frame', True)
            s.ok('the movie is read whole', bytes(p.peek(0x8000, len(counted))) == counted)
            s.key(b'\x1b')
            back_in_a2fc(s)
            s.ok('Escape brings A2FC back', True)
            s.ok('AUX and /RAM untouched', bytes(p.peek(0x1000, 0xB000, 'aux')) == aux)
            p.stable()
            if not s.has('M.BAD'):
                s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
                s.select('WORK'); s.key(RET); p.stable()
            # A marked picture is the backdrop (Space marks it).
            s.select('PIC'); s.key(b' '); p.stable()
            s.select('M.COUNT'); s.key(RET)
            player = ref.Player(counted, backdrop=pic)
            list(player.play())
            s.wait(lambda: bytes(p.peek(0x2000, 0x2000)) == bytes(player.pages[1]) and
                   bytes(p.peek(0x6000, 0x2000)) == bytes(player.bg), 'on the marked backdrop', 180)
            s.ok('a marked hi-res picture is the backdrop', True)
            s.key(b'\x1b')
            back_in_a2fc(s)
            p.stable()
            if not s.has('M.SAME'):
                s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
                s.select('WORK'); s.key(RET); p.stable()
            if s.has('*PIC') or any('PIC' in r and '*' in r for r in s.rows()):
                s.select('PIC'); s.key(b' '); p.stable()      # unmark it
            s.select('M.SAME'); s.key(RET)
            player = ref.Player(films['M.SAME'], backdrop=same)
            list(player.play())
            s.wait(lambda: bytes(p.peek(0x2000, 0x2000)) == bytes(player.pages[1]) and
                   bytes(p.peek(0x6000, 0x2000)) == bytes(player.bg), 'on the same-name backdrop', 180)
            s.ok('SAME beside M.SAME is the backdrop without any mark', True)
            s.key(b'\x1b')
            back_in_a2fc(s)
            p.stable()
            if not s.has('M.BAD'):
                s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
                s.select('WORK'); s.key(RET); p.stable()
            s.select('M.BAD'); s.key(RET)
            s.wait(lambda: 'NOT A FANTAVISION MOVIE' in '\n'.join(s.rows40()), 'the refusal', 120)
            s.ok('a damaged movie is refused with its reason', True)
            s.key(b' ')
            back_in_a2fc(s)
            s.ok('and A2FC comes back after the refusal', True)
    return ok_all(s, 'fanta_a2fc')


if __name__ == '__main__':
    sys.exit(main())
