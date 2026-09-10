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
LONG = '/WORKHD/'+'A'*15+'/'+'B'*15+'/'+'C'*15+'/'+'D'*7

HD_FILES = {'WORK/SUB/DEEP/X.TXT': b'deep\r', 'OTHER/Y.TXT': b'other\r', LONG[len('/WORKHD/'):]+ '/X.TXT':b'long\r'}


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-goto-') as tmp:
        with boot_hd(Path(tmp), HD_FILES, port=PORT, plugins=['goto']) as (p, s):

            stack=p.peek(0x80,2);floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8)

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

            # The menu now spans several pages: use its normal navigation.
            open_goto()
            s.ok('GOTO opens from the plugin menu',s.has(TITLE))
            leave(ESC)

            # 2. Liste vide : l'ecran le dit, et le message aussi en sortant.
            screen = open_goto()
            s.ok('la liste vide affiche le titre, le mode d\'emploi et la barre de touches',
                 s.has('No favourites yet') and any('1-9' in r and 'ESC' in r for r in screen),
                 [r.strip() for r in screen[:5] if r.strip()])
            line = leave(ESC)
            s.ok('ESC sur une liste vide : "No favourites yet: A adds this directory"',
                 line == 'No favourites yet: A adds this directory', line)

            def path_to(value,key=RET):
                open_goto();s.key(b'P');s.wait(lambda:s.has('Path: '),'path input',20)
                if value:s.type(value)
                return leave(key)
            line=path_to(DEEP.lower()+'///')
            s.ok('P opens lowercase path with trailing slashes',line=='Jumped to '+DEEP and s.rows()[0].startswith(DEEP))
            screen=open_goto();s.ok('direct path is not added to favourites',rows_of(screen)==[]);leave(ESC)
            line=path_to(OTHER,ESC)
            s.ok('ESC cancels direct path without moving panel',s.rows()[0].startswith(DEEP) and not line)
            open_goto();s.key(b'P');s.wait(lambda:s.has('Path: '),'path input',20)
            s.type(OTHER+'X');s.key(b'\x7f');line=leave(RET)
            s.ok('Delete edits the path',line=='Jumped to '+OTHER)
            for value in ('OTHER','/',''):
                line=path_to(value)
                s.ok('relative or empty path rejected: '+repr(value),line=='Use /VOLUME/DIRECTORY.' and s.rows()[0].startswith(OTHER))
            for value in ('/NO.VOLUME/MISSING',OTHER+'/Y'):
                line=path_to(value)
                s.ok('missing directory or file leaves panel unchanged',line=='Gone: '+value and s.rows()[0].startswith(OTHER))
            line=path_to(LONG+'EXCESS')
            s.ok('full 63-character path fits; excess input is bounded',len(LONG)==63 and line=='Jumped to '+LONG)
            left=s.rows()[0][:39];s.key(TAB)
            line=path_to(DEEP)
            s.ok('P acts on the right panel when active',line=='Jumped to '+DEEP and s.rows()[0][40:].startswith(DEEP) and s.rows()[0][:39]==left)

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

            s.ok('stack restored and bounded',p.peek(0x80,2)==stack and p.peek(floor,8)==b'\xA5'*8)

    return ok_all(s, 'goto')


if __name__ == '__main__':
    sys.exit(main())
