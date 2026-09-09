#!/usr/bin/env python3
"""Banc de la surcouche RENAME (src/plugins/rename.c) : le renommage par
motif des fichiers marques du panneau actif -- prefixe, suffixe, extension
remplacee, extension retiree, numerotation.

    make build/rename.PLG && A2FC_IMG=A2FILECMD-full python3 bench/rename.py

Tout se verifie a l'ecran : les noms sont dans le panneau, et la surcouche
relit le panneau et le redessine avant d'ecrire son compte en ligne 22.
WORK/ porte A.TXT et B.TXT (nommes en clair par #040000, sinon mkvolume
retirerait le .TXT), C (un .BIN, sans point), puis D.TXT et OLDD.TXT, la
paire qui sert a la collision : renommer D.TXT en OLDD.TXT est refuse par
ProDOS ($47) et compte pour un fichier passe.

La suite suit la vie d'un lot de fichiers : P puis E puis X puis N sur les
deux memes fichiers, chaque etape lisant a l'ecran ce que la precedente a
ecrit."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, menu_run, ok_all, RET, ESC, TAB

PORT = 6811
FILES = {
    'WORK/A.TXT#040000': b'a\r',
    'WORK/B.TXT#040000': b'b\r',
    'WORK/C.BIN': b'c',
    'WORK/D.TXT#040000': b'd\r',
    'WORK/OLDD.TXT#040000': b'the name that is already taken\r',
}


def names(s, x=0):
    """Les noms affiches dans le panneau qui commence en colonne x."""
    return [r[x:x + 15].strip() for r in s.rows()[2:20] if r[x:x + 15].strip()]


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-rename-') as tmp:
        with boot_hd(tmp, FILES, port=PORT, plugins=['rename']) as (p, s):

            def go(x, *parts):
                """Amene le panneau qui commence en x sur /WORKHD/parts..."""
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'la liste des volumes')
                s.select('/WORKHD', x); s.key(RET)
                s.wait(lambda: s.rows()[0][x:].startswith('/WORKHD'), '/WORKHD'); p.stable()
                path = '/WORKHD'
                for n in parts:
                    s.select(n, x); s.key(RET)
                    path += '/' + n
                    s.wait(lambda: s.rows()[0][x:].startswith(path), path); p.stable()

            def tag(x, *want):
                for n in want:
                    s.select(n, x); s.key(b' ')
                p.stable()

            def rename(key, text=None, x=0):
                """Lance RENAME, repond `key`, saisit `text`, rend la ligne 22."""
                menu_run(s, p, 'RENAME')
                s.wait(lambda: s.has('P)refix S)uffix'), 'la question du motif', 30)
                s.key(key)
                if text is not None:
                    s.wait(lambda: s.has('Text:'), 'la saisie du texte', 20)
                    s.type(text)
                    s.key(RET)
                s.wait(lambda: s.has(' renamed, '), 'la fin du renommage', 60)
                p.stable()
                return s.rows()[22].strip()

            # 1. La liste des volumes n'a pas de chemin : refus.
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'la liste des volumes'); p.stable()
            menu_run(s, p, 'RENAME')
            s.ok('refuse la liste des volumes', s.has('Open a directory'), s.rows()[22].strip())

            go(0, 'WORK')
            s.ok('le panneau gauche est sur /WORKHD/WORK et montre les cinq fichiers',
                 names(s) == ['..', 'A.TXT', 'B.TXT', 'C', 'D.TXT', 'OLDD.TXT'], names(s))

            # 2. ESC a la question : rien ne bouge.
            menu_run(s, p, 'RENAME')
            s.wait(lambda: s.has('P)refix S)uffix'), 'la question du motif', 30)
            s.key(ESC); p.stable()
            s.ok('ESC a la question ne renomme rien',
                 not s.has(' renamed, ') and names(s) == ['..', 'A.TXT', 'B.TXT', 'C', 'D.TXT', 'OLDD.TXT'],
                 s.rows()[22].strip())

            # 3. P : un prefixe sur les deux fichiers marques, les autres intacts.
            tag(0, 'A.TXT', 'B.TXT')
            s.ok('deux fichiers marques', s.has('2 tagged'), s.rows()[21][60:].strip())
            line = rename(b'P', 'OLD')
            s.ok('P OLD : "2 renamed, 0 skipped"', line == '2 renamed, 0 skipped', line)
            s.ok('le panneau montre OLDA.TXT et OLDB.TXT, C et D.TXT intacts',
                 names(s) == ['..', 'C', 'D.TXT', 'OLDA.TXT', 'OLDB.TXT', 'OLDD.TXT'], names(s))
            s.ok('les marques sont levees par la relecture', not s.has('tagged'), s.rows()[21][60:].strip())

            # 4. E : l'extension remplacee.
            tag(0, 'OLDA.TXT', 'OLDB.TXT')
            line = rename(b'E', 'MD')
            s.ok('E MD : OLDA.MD et OLDB.MD', line == '2 renamed, 0 skipped'
                 and names(s) == ['..', 'C', 'D.TXT', 'OLDA.MD', 'OLDB.MD', 'OLDD.TXT'], (line, names(s)))

            # 5. X : l'extension retiree.
            tag(0, 'OLDA.MD', 'OLDB.MD')
            line = rename(b'X')
            s.ok('X : OLDA et OLDB, sans point', line == '2 renamed, 0 skipped'
                 and names(s) == ['..', 'C', 'D.TXT', 'OLDA', 'OLDB', 'OLDD.TXT'], (line, names(s)))

            # 6. N : le numero d'ordre ajoute, dans l'ordre du panneau.
            tag(0, 'OLDA', 'OLDB')
            line = rename(b'N')
            s.ok('N : OLDA1 et OLDB2, numerotes dans l ordre du panneau',
                 line == '2 renamed, 0 skipped'
                 and names(s) == ['..', 'C', 'D.TXT', 'OLDA1', 'OLDB2', 'OLDD.TXT'], (line, names(s)))

            # 7. X sur un nom sans point : le nom ne change pas, ProDOS refuse.
            tag(0, 'C')
            line = rename(b'X')
            s.ok('X sur C sans point : ProDOS accepte le nom identique',
                 line == '1 renamed, 0 skipped' and 'C' in names(s), (line, names(s)))

            # 8. La collision : OLDD.TXT existe deja.
            tag(0, 'D.TXT')
            line = rename(b'P', 'OLD')
            s.ok('P OLD sur D.TXT, dont OLDD.TXT est deja pris : "0 renamed, 1 skipped"',
                 line == '0 renamed, 1 skipped'
                 and names(s) == ['..', 'C', 'D.TXT', 'OLDA1', 'OLDB2', 'OLDD.TXT'], (line, names(s)))

            # 9. Sans marque : l'entree sous le curseur, et elle seule.
            s.select('C', 0); p.stable()
            line = rename(b'S', 'Z')
            s.ok('sans marque, S Z ne renomme que l entree sous le curseur : CZ',
                 line == '1 renamed, 0 skipped'
                 and names(s) == ['..', 'CZ', 'D.TXT', 'OLDA1', 'OLDB2', 'OLDD.TXT'], (line, names(s)))

            # 10. Le panneau actif est le droit : mêmes services, autre panneau.
            s.key(TAB)
            go(40, 'WORK')
            tag(40, 'OLDA1', 'OLDB2')
            line = rename(b'E', 'BAK', x=40)
            s.ok('dans le panneau droit : OLDA1.BAK et OLDB2.BAK',
                 line == '2 renamed, 0 skipped'
                 and names(s, 40) == ['..', 'CZ', 'D.TXT', 'OLDA1.BAK', 'OLDB2.BAK', 'OLDD.TXT'],
                 (line, names(s, 40)))
            s.ok('le panneau gauche, lui, garde ce qu il montrait',
                 s.rows()[0].startswith('/WORKHD/WORK'), s.rows()[0][:38])
    return ok_all(s, 'rename')


if __name__ == '__main__':
    sys.exit(main())
