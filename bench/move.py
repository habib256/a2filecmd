#!/usr/bin/env python3
"""Banc de la surcouche MOVE (src/plugins/move.c) : deplacer une entree d'un
repertoire a l'autre sans recopier les blocs.

    make build/move.PLG && A2FC_IMG=A2FILECMD-full python3 bench/move.py

Le cas verifie ici est celui qui ecrit dans la TABLE BINAIRE du volume : un
repertoire cible plein doit gagner un bloc. VOLINFO sert de juge -- il relit
tout le volume et compte les blocs occupes mais marques libres, les
references partagees, les pointeurs invalides, les compteurs faux et les
blocs perdus. Un agrandissement de travers se voit la, et nulle part
ailleurs. tools/test_move.py couvre la meme chose sur l'hote; ce banc fait
tourner la surcouche livree sur un vrai volume ProDOS."""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, menu_run, ok_all, RET, ESC, TAB

PORT = 6819


def main():
    files = {'SRC/HELLO#040000': b'hello' * 20,
             'SRC/KEEP#040000': b'keep' * 8}
    # Douze entrees remplissent le premier bloc d'un repertoire : l'en-tete
    # prend la place zero. DST n'a donc plus une seule entree libre.
    for i in range(12):
        files['DST/F%02d#040000' % i] = b'x' * 16
    with tempfile.TemporaryDirectory(prefix='a2fc-move-') as tmp:
        with boot_hd(tmp, files, port=PORT, blocks=1000,
                     plugins=['move', 'volinfo']) as (p, s):
            # Le panneau de gauche sur SRC, celui de droite sur DST.
            s.select('SRC'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/SRC'), 'SRC a gauche'); p.stable()
            s.key(TAB)
            s.select('/WORKHD', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/WORKHD'), 'la racine a droite')
            p.stable()
            s.select('DST', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/WORKHD/DST'), 'DST a droite')
            p.stable()
            s.key(TAB); p.stable()

            s.select('HELLO'); p.stable()
            menu_run(s, p, 'MOVE')
            s.wait(lambda: s.has('must grow a block'), 'la demande', 30); p.stable()
            s.ok('dit que le repertoire doit grandir avant de le faire',
                 s.rows()[22].strip().startswith('Move HELLO into /WORKHD/DST?'),
                 s.rows()[22].strip())
            s.key(b'Y')
            s.wait(lambda: s.has('moved:'), 'le deplacement', 60); p.stable()
            s.ok('le deplacement est annonce sans recopie',
                 'nothing copied' in s.rows()[22], s.rows()[22].strip())

            # L'entree est bien dans la cible, et plus dans la source.
            s.ok('HELLO a quitte le panneau de gauche',
                 not any(r[:38].startswith('HELLO ') for r in s.rows()[2:20]),
                 s.rows()[2][:38])
            s.key(TAB); p.stable()
            s.select('HELLO', 40)
            s.ok('HELLO est dans le repertoire cible',
                 s.line(40).startswith('HELLO '), s.line(40))
            s.key(TAB); p.stable()

            # Le juge : le volume doit etre irreprochable.
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
            s.select('/WORKHD'); p.stable()
            menu_run(s, p, 'VOLINFO')
            s.wait(lambda: s.has('M Bitmap'), 'le diagnostic', 180); p.stable()
            text = '\n'.join(s.rows())

            def number(label):
                m = re.search(re.escape(label) + r'\s*(\d+)', text)
                return int(m[1]) if m else None

            for label in ('Used but marked free:', 'Shared references:',
                          'Invalid structure/pointers:', 'Count mismatches:',
                          'Lost blocks:'):
                s.ok('volume sain apres agrandissement -- %s 0' % label,
                     number(label) == 0, text)
            s.key(ESC); s.wait(lambda: s.has('! More'), 'retour aux panneaux'); p.stable()
    return ok_all(s, 'move')


if __name__ == '__main__':
    sys.exit(main())
