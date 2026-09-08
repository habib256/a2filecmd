#!/usr/bin/env python3
"""Banc du disque PHYSIQUE : un vrai DOS 3.3 dans le lecteur 2 des l'amorcage.

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/physical.py

Le chemin qu'aucun autre banc n'atteint : `Pom2(..., floppy2=...)` (POM2
`--disk2`) met une disquette DOS 3.3 dans le lecteur 2 du Disk II a
l'amorcage, sans passer par `/disk` (dont une disquette n'est lisible qu'une
fois ecrite). A2FC doit la reconnaitre a sa VTOC, la lister comme volume, et
sa ligne "DOS 3.3 disk" -- selectionnee, donc en inverse -- doit tenir dans
ses 38 colonnes : en 0.6 elle en faisait 42 et debordait sur le separateur
(a gauche) ou passait a la ligne suivante, colonnes 0-1 (a droite) : les
carres blancs corriges en 0.6.1."""

import shutil, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, ROOT, DISK
from run import scratch_volume, TAB
import mkdos33


def cell(p, r, c):
    """L'octet de la cellule ecran (ligne r, colonne c) : AUX pour les colonnes paires."""
    base = 0x80 * (r % 8) + 0x28 * (r // 8)
    return p.peek(0x400 + base + c // 2, 1, 'aux' if c % 2 == 0 else 'main')[0]


def inverse(b):
    return b < 0x80 and not (0x40 <= b < 0x60)      # inverse, hors MouseText


def main():
    checks = []
    def ok(label, cond, detail=''):
        checks.append(cond)
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''),
              flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-physical-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(DISK, floppy)
        # Une vraie disquette DOS 3.3 : 35 pistes, fichiers verrouilles (bit 7).
        dos = tmp / 'REAL33.dsk'
        dos.write_bytes(mkdos33.build([('HELLO', 0x82, b'\x00' * 300),
                                       ('MASTER.CREATE', 0x84, b'\x00' * 2304)]))
        ok('la disquette DOS 3.3 fait 35 pistes', dos.stat().st_size == 143360, dos.stat().st_size)

        with Pom2(scratch_volume(tmp), floppy=floppy, port=6691, floppy2=dos) as p:
            s = Session(p)
            s.boot()
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
            rows = s.rows()
            hit = [i for i, r in enumerate(rows) if 'DOS 3.3 disk' in r]
            ok('un vrai disque DOS 3.3 en lecteur 2 parait dans la liste des volumes',
               bool(hit), [rows[i].rstrip()[:40] for i in hit])
            if not hit:
                print('\n'.join(r.rstrip() for r in rows[:8]))
                return 1

            # La selectionner dans le panneau gauche : la ligne passe en inverse.
            if s.cursor_row(0) is None:
                s.key(TAB)
            for _ in range(12):
                s.key(b'<')
            for _ in range(20):
                if 'DOS 3.3 disk' in s.line(0):
                    break
                s.key(b'\x0a')
            p.stable()
            r = s.cursor_row(0)
            ok('la ligne DOS 3.3 est la selection', r is not None and 'DOS 3.3 disk' in s.line(0),
               s.line(0).rstrip()[:40])
            spill = [(c, hex(cell(p, r, c))) for c in (38, 39, 40, 41) if inverse(cell(p, r, c))]
            wrap = [(c, hex(cell(p, r + 1, c))) for c in (0, 1) if inverse(cell(p, r + 1, c))]
            ok('en inverse, la ligne ne deborde pas sur le separateur ni le panneau voisin',
               not spill, spill)
            ok('ni ne passe a la ligne suivante, colonnes 0-1', not wrap, wrap)

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
