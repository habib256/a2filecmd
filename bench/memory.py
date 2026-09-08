"""Le creux maximal de la pile C, mesure en faisant travailler le programme.

La pile logicielle de cc65 part de $BF00 vers le bas et rien ne la surveille :
si elle descend sous le bout froid du binaire, elle mange du code. Le lien
reserve 256 octets (A2FC_STACK dans le Makefile) et tools/check_layout.py
verifie que le code s'arrete au-dessus ; ce banc mesure ce qui est REELLEMENT
consomme, arbre de dossiers, images, visionneuses, editeur et copie recursive
compris.

    make disk && POM2=... python3 bench/memory.py
"""
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, ROOT, labels, DISK
from run import scratch_volume, ESC, RET, DOWN, TAB

BUDGET = 256                    # ce que le lien reserve


def main():
    sym = labels()
    lo, hi = sym['__ONCE_RUN__'], sym['__HIMEM__']
    with tempfile.TemporaryDirectory(prefix='a2fc-stack-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(DISK, floppy)
        with Pom2(scratch_volume(tmp), floppy=floppy, port=6620) as p:
            s = Session(p, sym)
            s.boot()
            # ONCE est mort une fois main() lance : tout ce qui est au-dessus
            # du bout froid est a la pile, et a personne d'autre.
            p.poke(lo, bytes([0xEE]) * (hi - lo))

            def low_water():
                d = p.peek(lo, hi - lo)
                for i, b in enumerate(d):
                    if b != 0xEE:
                        return lo + i
                return hi

            s.ok('le motif est pose sur toute la pile', low_water() == hi)
            s.select('A2FILE'); s.key(RET)
            s.wait(lambda: s.has('/A2FILECMD/A2FILE'), 'dossier'); s.key(ESC)
            s.wait(lambda: s.has('/A2FILECMD '), 'retour'); p.stable()
            s.key(TAB); s.select('DHGR.RLE', 40); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 1, 'image', 40); time.sleep(1)
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            s.select('SAMPLE', 40); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 2, 'texte'); s.key(ESC)
            s.wait(lambda: s.value('view', 1) == 0, 'retour')
            s.key(b'H'); s.wait(lambda: s.value('view', 1) == 3, 'hexa'); s.key(ESC)
            s.wait(lambda: s.value('view', 1) == 0, 'retour')
            s.key(b'E'); s.wait(lambda: s.value('view', 1) == 5, 'editeur')
            s.type('X'); s.key(ESC); s.wait(lambda: s.has('Discard') or s.has('Save and exit'), 'menu')
            s.key(b'Q'); s.wait(lambda: s.has('Discard'), 'abandon'); s.key(b'Y')
            s.wait(lambda: s.value('view', 1) == 0, 'sortie'); p.stable()
            after_views = low_water()
            # la copie d'un arbre entier : le chemin le plus profond du programme
            # le panneau droit devient la cible, le gauche reste sur la disquette
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'scratch'); p.stable()
            s.key(TAB)
            s.select('A2FILE'); s.key(b'C')
            s.wait(lambda: s.has('copied') or s.has('failed'), 'copie recursive', 180); p.stable()
            deep = low_water()
            used = hi - deep
            print(f'creux apres les visionneuses : ${after_views:04X}', flush=True)
            print(f'creux le plus bas            : ${deep:04X}  ({used} octets sous ${hi:04X})',
                  flush=True)
            s.ok(f'la pile reste sous les {BUDGET} octets reserves ({used} utilises)',
                 used <= BUDGET, f'${deep:04X}')
            s.ok('et garde au moins la moitie de marge', used <= BUDGET // 2, f'{used} octets')
    return 0


if __name__ == '__main__':
    sys.exit(main())
