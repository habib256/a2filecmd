#!/usr/bin/env python3
"""Banc de la surcouche GOTO (src/plugins/goto.c) : les repertoires
favoris, dans A2FILE/GOTO.CFG, a cote du programme.

    make build/goto.PLG && A2FC_IMG=A2FILECMD-full python3 bench/goto.py

Le disque dur du banc porte /WORKHD/WORK/SUB/DEEP/X et /WORKHD/OTHER/Y :
deux repertoires assez differents pour qu'on voie tout de suite dans quel
panneau on est. Le banc joue le cycle complet -- liste vide, deux ajouts,
un doublon refuse, deux sauts, une suppression -- puis rouvre GOTO : POM2
ne recopie jamais le .hdv d'amorcage sur l'hote, alors c'est la liste
affichee par une SECONDE ouverture qui prouve ce que GOTO.CFG contient,
puisqu'elle sort d'une relecture du fichier."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, menu_run, ok_all, RET, TAB, ESC

PORT = 6812
DEEP = '/WORKHD/WORK/SUB/DEEP'
OTHER = '/WORKHD/OTHER'
TITLE = 'GOTO -- favourite directories'

HD_FILES = {'WORK/SUB/DEEP/X.TXT': b'deep\r', 'OTHER/Y.TXT': b'other\r'}


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-goto-') as tmp:
        with boot_hd(Path(tmp), HD_FILES, port=PORT, plugins=['goto']) as (p, s):

            def open_panel(x, vol, *names):
                """Amene le panneau qui commence en colonne x sur /vol/names..."""
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
                s.select(vol, x); s.key(RET)
                s.wait(lambda: s.rows()[0][x:].startswith(vol), vol); p.stable()
                path = vol
                for n in names:
                    s.select(n, x); s.key(RET)
                    path += '/' + n
                    s.wait(lambda: s.rows()[0][x:].startswith(path), path); p.stable()

            def open_goto():
                """Ouvre GOTO par le menu ; rend l'ecran de la liste."""
                menu_run(s, p, 'GOTO')
                s.wait(lambda: s.has(TITLE), "l'ecran de GOTO", 30)
                p.stable()
                return s.rows()

            def leave(*keys):
                """Tape les touches, attend le retour aux panneaux, rend la ligne 22."""
                for k in keys:
                    s.key(k)
                s.wait(lambda: not s.has(TITLE), 'le retour aux panneaux', 30)
                p.stable()
                return s.rows()[22].strip()

            def rows_of(screen):
                """Les lignes numerotees de la liste affichee."""
                return [r.strip() for r in screen[2:14] if r.strip() and r.strip()[0].isdigit()]

            # 1. La surcouche parait dans le menu, decrite par son en-tete.
            s.key(b'!'); s.wait(lambda: s.has('the overlays'), 'le menu', 30); p.stable()
            s.ok('GOTO parait dans le menu avec sa description',
                 s.has('Favourite directories: jump in two keys'),
                 [r.strip() for r in s.rows() if 'Favourite' in r])
            s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'les panneaux', 30); p.stable()

            # 2. Liste vide : l'ecran le dit, et le message aussi en sortant.
            screen = open_goto()
            s.ok('la liste vide affiche le titre, le mode d\'emploi et la barre de touches',
                 s.has('No favourites yet') and any('1-9' in r and 'ESC' in r for r in screen),
                 [r.strip() for r in screen[:5] if r.strip()])
            line = leave(ESC)
            s.ok('ESC sur une liste vide : "No favourites yet: A adds this directory"',
                 line == 'No favourites yet: A adds this directory', line)

            # 3. A dans /WORKHD/WORK/SUB/DEEP : le premier favori.
            open_panel(0, '/WORKHD', 'WORK', 'SUB', 'DEEP')
            open_goto()
            line = leave(b'A')
            s.ok('A ajoute le repertoire courant : "Added %s"' % DEEP,
                 line == 'Added ' + DEEP, line)

            # 4. A dans /WORKHD/OTHER : le second.
            open_panel(0, '/WORKHD', 'OTHER')
            open_goto()
            line = leave(b'A')
            s.ok('A ajoute le second : "Added %s"' % OTHER, line == 'Added ' + OTHER, line)

            # 5. Le meme une deuxieme fois est refuse.
            open_goto()
            line = leave(b'A')
            s.ok('un chemin deja liste est refuse', line == 'Already in the list.', line)

            # 6. La liste relue du fichier montre les deux, numerotes.
            open_panel(0, '/WORKHD')
            screen = open_goto()
            listed = rows_of(screen)
            s.ok('la liste montre les deux favoris numerotes, dans l\'ordre',
                 listed == ['1 ' + DEEP, '2 ' + OTHER], listed)

            # 7. 1 : le panneau actif saute au premier favori.
            line = leave(b'1')
            s.ok('1 emmene le panneau sur %s' % DEEP,
                 s.rows()[0].startswith(DEEP) and line == 'Jumped to ' + DEEP,
                 (s.rows()[0][:38], line))

            # 8. 2 : et au second.
            open_goto()
            line = leave(b'2')
            s.ok('2 emmene le panneau sur %s' % OTHER,
                 s.rows()[0].startswith(OTHER) and line == 'Jumped to ' + OTHER,
                 (s.rows()[0][:38], line))

            # 9. D puis 1 : le premier disparait, le fichier est reecrit.
            open_goto()
            s.key(b'D')
            s.wait(lambda: s.has('Delete which one?'), 'la question de la suppression', 20)
            line = leave(b'1')
            s.ok('D puis 1 : "Removed %s"' % DEEP, line == 'Removed ' + DEEP, line)

            # 10. La preuve du fichier : une SECONDE ouverture le relit.
            screen = open_goto()
            listed = rows_of(screen)
            s.ok('GOTO.CFG relu ne garde que %s, en 1' % OTHER, listed == ['1 ' + OTHER], listed)
            leave(ESC)

            # 11. La liste des volumes n'est pas un repertoire ProDOS.
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
            open_goto()
            line = leave(b'A')
            s.ok('A refuse la liste des volumes',
                 line == 'Not a ProDOS directory: nothing to add.', line)

            # 12. Un favori qui n'existe plus : GOTO ne bouge pas le panneau.
            # (C'est la ou une petite surcouche aurait appele read_panel ; une
            # grosse ne le peut pas, elle ouvre le chemin d'abord -- voir le
            # commentaire de tete de goto.c.)
            open_panel(0, '/WORKHD')
            s.key(b'K'); s.wait(lambda: s.has('New directory'), 'mkdir')
            s.type('GONESOON'); s.key(RET)
            s.wait(lambda: s.has('GONESOON'), 'le repertoire cree'); p.stable()
            s.select('GONESOON', 0); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD/GONESOON'), 'dedans'); p.stable()
            open_goto()
            line = leave(b'A')
            s.ok('A ajoute /WORKHD/GONESOON', line == 'Added /WORKHD/GONESOON', line)
            open_panel(0, '/WORKHD')
            s.select('GONESOON', 0); s.key(b'D')
            s.wait(lambda: s.has('Delete GONESOON'), 'la confirmation'); s.key(b'Y')
            s.wait(lambda: not s.has('GONESOON'), 'le repertoire supprime'); p.stable()
            open_goto()
            line = leave(b'2')
            s.ok('un favori disparu : "Gone: ..." et le panneau reste ou il est',
                 line == 'Gone: /WORKHD/GONESOON' and s.rows()[0].startswith('/WORKHD '),
                 (s.rows()[0][:38], line))

    return ok_all(s, 'goto')


if __name__ == '__main__':
    sys.exit(main())
