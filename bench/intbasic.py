#!/usr/bin/env python3
"""Banc de la surcouche INTBASIC (src/plugins/intbasic.c) : lister un
programme Integer BASIC, type ProDOS $FA.

    make build/intbasic.PLG && A2FC_IMG=A2FILECMD-full python3 bench/intbasic.py

Le specimen est le debut du Breakout de Woz, tel qu'il est sur le disque
(tools/test_intbasic.py le porte en base64), et le listing attendu est rebati
a partir de la regle du format, pas du decodeur. Le banc relit l'ecran de
texte de l'emulateur : c'est la seule verification du rendu reel -- retours a
la ligne a 80 colonnes, barre d'etat, retour aux panneaux."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC
from test_intbasic import BREAKOUT, listing, wrapped, prog

PORT = 6818


def main():
    want = wrapped(listing(BREAKOUT))
    # Soixante lignes courtes : trois pages de vingt-deux, de quoi verifier
    # que la surcouche retient ou chaque page commence.
    long_prog = prog([(n, bytes([0x4B])) for n in range(1, 61)])
    long_want = wrapped(listing(long_prog))
    files = {
        'WORK/BREAKOUT#FA0000': BREAKOUT,
        'WORK/SIXTY#FA0000': long_prog,
        'WORK/PLAIN.TXT#040000': b'not a program\r',
    }
    with tempfile.TemporaryDirectory(prefix='a2fc-intbasic-') as tmp:
        with boot_hd(tmp, files, port=PORT, plugins=['intbasic']) as (p, s):
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD '), 'la racine'); p.stable()
            s.select('WORK'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()

            # 1. Un fichier qui n'est pas du type $FA est refuse.
            s.select('PLAIN.TXT', 0); p.stable()
            menu_run(s, p, 'INTBASIC')
            s.wait(lambda: s.has('Not an Integer BASIC'), 'le refus', 20); p.stable()
            s.ok('refuse un fichier texte',
                 s.rows()[22].strip() == 'Not an Integer BASIC program ($FA).',
                 s.rows()[22].strip())

            # 2. Le listing, ligne d'ecran par ligne d'ecran.
            s.select('BREAKOUT', 0); p.stable()
            menu_run(s, p, 'INTBASIC')
            s.wait(lambda: s.has('BREAKOUT GAME'), 'le listing', 30); p.stable()
            rows = [r.rstrip() for r in s.rows()[:22]]
            got = rows[:len(want)]
            s.ok('le listing est celui de l\'interprete', got == want,
                 '\n'.join('  attendu %r\n  obtenu  %r' % (w, g)
                           for w, g in zip(want, got) if w != g))
            s.ok('rien de plus sur la page', not any(rows[len(want):]),
                 rows[len(want):])
            s.ok('la barre dit la page et la fin, sans toucher les touches',
                 s.rows()[23].startswith('/WORKHD/WORK/BREAKOUT')
                 and ' page 1 (end)' in s.rows()[23][:52]
                 and s.rows()[23][52:].startswith('SPC'), s.rows()[23])

            # 3. La pagination : espace avance, B recule, R revient au debut.
            s.key(ESC)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'le retour', 20); p.stable()
            s.select('SIXTY', 0); p.stable()
            menu_run(s, p, 'INTBASIC')
            s.wait(lambda: s.has('1 TEXT'), 'la premiere page', 30); p.stable()
            s.ok('page 1 : les vingt-deux premieres lignes',
                 [r.rstrip() for r in s.rows()[:22]] == long_want[:22], s.rows()[0])
            s.key(b' '); p.stable()
            s.ok('espace donne la page 2',
                 [r.rstrip() for r in s.rows()[:22]] == long_want[22:44], s.rows()[0])
            s.key(b' '); p.stable()
            s.ok('espace donne la page 3, qui est la derniere',
                 [r.rstrip() for r in s.rows()[:22]][:16] == long_want[44:60]
                 and '(end)' in s.rows()[23], s.rows()[0])
            s.key(b'B'); p.stable()
            s.ok('B revient a la page 2',
                 [r.rstrip() for r in s.rows()[:22]] == long_want[22:44], s.rows()[0])
            s.key(b'R'); p.stable()
            s.ok('R revient a la premiere',
                 [r.rstrip() for r in s.rows()[:22]] == long_want[:22], s.rows()[0])
            s.key(ESC)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'le retour aux panneaux', 20); p.stable()

            # 4. T sur un $FA lance la surcouche, comme T sur un $FC lance
            #    BASLIST : c'est le chemin ordinaire, pas seulement le menu.
            s.select('BREAKOUT', 0); p.stable()
            s.key(b't')
            s.wait(lambda: s.has('BREAKOUT GAME'), 'T sur un $FA', 30); p.stable()
            s.ok('T liste un programme Integer BASIC',
                 [r.rstrip() for r in s.rows()[:2]] == want[:2], s.rows()[0])
            s.key(ESC)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'le retour', 20); p.stable()

            # 5. T sur un fichier texte ordinaire va toujours au lecteur texte,
            #    et H a l'hexadecimal : les deux cas ont ete reecrits pour
            #    trouver la place du branchement ci-dessus.
            s.select('PLAIN.TXT', 0); p.stable()
            s.key(b't')
            s.wait(lambda: s.has('not a program'), 'le lecteur texte', 20); p.stable()
            s.ok('T sur un texte ouvre toujours le lecteur texte',
                 s.has('not a program'), s.rows()[0])
            s.key(ESC); s.wait(lambda: s.has('/WORKHD/WORK'), 'le retour', 20); p.stable()
            s.key(b'h')
            s.wait(lambda: s.has('6E 6F 74') or s.has('not a program'), 'l\'hexadecimal', 20)
            p.stable()
            s.ok('H sur un texte ouvre toujours l\'hexadecimal',
                 s.has('6E 6F 74'), s.rows()[0])
            s.key(ESC); s.wait(lambda: s.has('/WORKHD/WORK'), 'le retour', 20); p.stable()

            # 6. Escape rend la main aux panneaux, curseur en place.
            s.select('BREAKOUT', 0); p.stable()
            menu_run(s, p, 'INTBASIC')
            s.wait(lambda: s.has('BREAKOUT GAME'), 'le listing', 30); p.stable()
            s.key(ESC)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'le retour aux panneaux', 20); p.stable()
            s.ok('le curseur est reste sur le programme',
                 s.line(0).startswith('BREAKOUT '), s.line(0))
    return ok_all(s, 'intbasic')


if __name__ == '__main__':
    sys.exit(main())
