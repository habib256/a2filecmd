#!/usr/bin/env python3
"""Banc de la surcouche TAGPAT (src/plugins/tagpat.c) : marquer les fichiers
du panneau actif par motif (les jokers `=` et `?` de Copy II Plus), par type,
par taille ou par date.

    make build-6502/tagpat.PLG ARCH=6502 && python3 bench/tagpat.py

Les fichiers d'essai sont sur le disque dur du banc, dans /WORKHD/WORK. Leurs
noms gardent leur point : `A.TXT` est ecrit `A.TXT#040000`, car sans le
suffixe explicite tools/mkvolume.py retirerait le `.TXT` et n'en garderait
que le type. Le tableau vise les trois jokers et les trois filtres :

    A.TXT   $04    100 o      E.BAS   $FC   2500 o
    B.TXT   $04   3000 o      F.BIN   $06     60 o
    CD.TXT  $04     40 o      G.TXT   $04   5000 o      SUB/  (un dossier)

TAGPAT ne fait que lire et poser des bits : rien n'est ecrit sur le disque, le
banc n'a donc pas besoin d'une disquette en lecteur 2 pour se relire sur
l'hote -- l'ecran suffit. Une ligne marquee porte une etoile juste apres le
nom, en colonne 15 du panneau (draw_entry, "%-15s%c%c..."), et c'est ainsi
qu'on lit l'ensemble des fichiers marques. Les dossiers (`..` compris) sont
compares au motif comme les fichiers et comptent dans les "(M matched)", mais
ne sont jamais marques : le noyau lui-meme n'en marque pas, et leur ligne
`<DIR>` n'a pas de place pour l'etoile."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET, ESC
from mkvolume import prodos_date

PORT = 6805
DEL = b'\x7f'
# La date que tools/mkvolume.py pose sur toutes les entrees qu'il ecrit (fixe,
# pour que le banc soit reproductible) : le filtre D compare la mdate d'une
# entree a la date systeme en $BF90, et c'est celle-la qu'il faut y poser.
FILE_DATE = prodos_date('2026-09-07T12:00')[0]

FILES = {
    'WORK/A.TXT#040000':     b'a' * 100,
    'WORK/B.TXT#040000':     b'b' * 3000,
    'WORK/CD.TXT#040000':    b'c' * 40,
    'WORK/E.BAS#FC0801':     b'e' * 2500,
    'WORK/F.BIN#062000':     b'f' * 60,
    'WORK/G.TXT#040000':     b'g' * 5000,
    'WORK/SUB/H.TXT#040000': b'h' * 10,
}
TXT = ['A.TXT', 'B.TXT', 'CD.TXT', 'G.TXT']


def tagged(s, x=0):
    """Les noms des lignes marquees du panneau qui commence en colonne x."""
    return sorted(r[x:x + 15].strip() for r in s.rows()[2:20]
                  if len(r) > x + 15 and r[x + 15] == '*')


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-tagpat-') as tmp:
        with boot_hd(tmp, FILES, port=PORT, plugins=['tagpat']) as (p, s):

            def ask(pattern):
                """Ouvre TAGPAT et tape `pattern` sur la ligne des messages."""
                menu_run(s, p, 'TAGPAT')
                s.wait(lambda: s.has('Pattern ('), 'la question du motif', 20)
                s.type(pattern)
                s.wait(lambda: s.has(': ' + pattern + '_'), "l'echo du motif", 20)

            def run(pattern, key):
                """Un motif, une touche (T, U ou X) ; rend la ligne 22."""
                ask(pattern)
                s.key(RET)
                s.wait(lambda: s.has('T Tag'), 'les touches T/U/X', 20)
                s.key(key)
                s.wait(lambda: s.has('matched)'), 'le compte final', 30)
                p.stable()
                return s.rows()[22].strip()

            # 1. La liste des volumes n'a pas de fichiers a marquer.
            s.key(b'/')
            s.wait(lambda: s.has('[Volumes]'), 'la liste des volumes')
            p.stable()
            menu_run(s, p, 'TAGPAT')
            p.stable()
            s.ok('refuse la liste des volumes', s.has('Open a directory.'), s.rows()[22].strip())

            # Le panneau gauche sur /WORKHD/WORK.
            s.select('/WORKHD', 0)
            s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD'), '/WORKHD')
            p.stable()
            s.select('WORK', 0)
            s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD/WORK'), '/WORKHD/WORK')
            p.stable()
            s.ok('le panneau gauche est sur /WORKHD/WORK et rien n est marque',
                 s.rows()[0].startswith('/WORKHD/WORK') and tagged(s) == [], s.rows()[0][:38])

            # 2. ESC abandonne : la ligne 22 est rendue vide, aucun bit pose.
            menu_run(s, p, 'TAGPAT')
            s.wait(lambda: s.has('Pattern ('), 'la question du motif', 20)
            s.key(ESC)
            p.stable()
            s.ok('ESC annule sans rien marquer',
                 not s.has('Pattern (') and not s.has('matched') and tagged(s) == [],
                 s.rows()[22].strip())

            # 3. Delete efface le dernier caractere tape.
            ask('=.TXTZ')
            s.key(DEL)
            s.wait(lambda: s.has(': =.TXT_'), 'Delete efface un caractere', 20)
            s.ok('Delete efface le dernier caractere du motif', s.has(': =.TXT_'),
                 s.rows()[22].strip())

            # 4. `=` prend n'importe quelle suite : les quatre .TXT, T les marque.
            s.key(RET)
            s.wait(lambda: s.has('T Tag'), 'les touches T/U/X', 20)
            s.key(b'T')
            s.wait(lambda: s.has('matched)'), 'le compte final', 30)
            p.stable()
            line = s.rows()[22].strip()
            s.ok('=.TXT + T : "4 tagged (4 matched)"', line == '4 tagged (4 matched)', line)
            s.ok('=.TXT marque les quatre fichiers .TXT', tagged(s) == TXT, tagged(s))
            s.ok('le noyau voit les memes bits ("4 tagged" ligne 21)',
                 '4 tagged' in s.rows()[21], s.rows()[21][60:].strip())

            # 5. Le filtre de taille et X : la selection devient exactement
            #    les fichiers de plus de 2000 octets, les .TXT courts tombent.
            line = run('=,>2000', b'X')
            s.ok('=,>2000 + X : "3 tagged (3 matched)"', line == '3 tagged (3 matched)', line)
            s.ok('X ne garde que les fichiers de plus de 2000 octets',
                 tagged(s) == ['B.TXT', 'E.BAS', 'G.TXT'], tagged(s))

            # 6. `?` vaut exactement un caractere : A.TXT, B.TXT et G.TXT, pas
            #    CD.TXT ; U les demarque et E.BAS reste seul marque.
            line = run('?.TXT', b'U')
            s.ok('?.TXT + U : "3 untagged (3 matched)"', line == '3 untagged (3 matched)', line)
            s.ok('? ne prend qu un caractere : CD.TXT est hors du compte, E.BAS reste seul',
                 tagged(s) == ['E.BAS'], tagged(s))

            # 7. Le filtre de type, en hexadecimal.
            line = run('=,T04', b'X')
            s.ok('=,T04 + X : les quatre fichiers de type $04',
                 line == '4 tagged (4 matched)' and tagged(s) == TXT, (line, tagged(s)))

            # 8. Un motif sans joker vaut le nom entier, et T ajoute au marquage.
            line = run('F.BIN', b'T')
            s.ok('F.BIN + T : "1 tagged (1 matched)"', line == '1 tagged (1 matched)', line)
            s.ok('un motif sans joker vaut le nom entier, T ajoute a ce qui est marque',
                 tagged(s) == sorted(TXT + ['F.BIN']), tagged(s))

            # 9. Deux filtres a la suite du motif.
            line = run('=.TXT,>2000', b'X')
            s.ok('=.TXT,>2000 + X : B.TXT et G.TXT seuls',
                 line == '2 tagged (2 matched)' and tagged(s) == ['B.TXT', 'G.TXT'],
                 (line, tagged(s)))

            # 10. `<` : CD.TXT et F.BIN sont marques ; `..`, dossier de taille
            #     nulle, entre dans le compte des correspondances sans etre marque.
            line = run('=,<100', b'X')
            s.ok('=,<100 + X : les deux fichiers de moins de 100 octets',
                 line.startswith('2 tagged (') and tagged(s) == ['CD.TXT', 'F.BIN'],
                 (line, tagged(s)))
            s.ok('un dossier compte comme correspondance mais n est jamais marque',
                 line == '2 tagged (3 matched)', line)

            # 11. Un filtre inconnu est refuse, et rien ne bouge.
            ask('=,Z')
            s.key(RET)
            s.wait(lambda: s.has('Bad filter'), 'le refus du filtre', 20)
            p.stable()
            s.ok('un filtre inconnu est refuse sans toucher au marquage',
                 s.has('Bad filter') and tagged(s) == ['CD.TXT', 'F.BIN'],
                 (s.rows()[22].strip(), tagged(s)))

            # 12. `D` compare la mdate a la date systeme ($BF90). La machine du
            #     banc n'a pas d'horloge : $BF90 vaut 0, aucun fichier ne porte
            #     cette date-la et rien n'est marque. Seul `..`, que le noyau
            #     fabrique avec une mdate nulle, correspond -- et un dossier
            #     n'est jamais marque : "0 tagged (1 matched)".
            line = run('=,D', b'X')
            s.ok('D ne marque rien quand la date systeme n est pas celle des fichiers',
                 line == '0 tagged (1 matched)' and tagged(s) == [], (line, tagged(s)))

            # 13. La date systeme posee sur celle qu'a mise mkvolume : D prend
            #     les six fichiers. SUB la porte aussi et compte parmi les
            #     correspondances, mais un dossier n'est jamais marque ; `..`,
            #     de mdate nulle, sort du compte cette fois.
            p.poke(0xBF90, FILE_DATE.to_bytes(2, 'little'))
            line = run('=,D', b'X')
            s.ok('D marque les fichiers dates du jour',
                 tagged(s) == ['A.TXT', 'B.TXT', 'CD.TXT', 'E.BAS', 'F.BIN', 'G.TXT'],
                 (line, tagged(s)))
            s.ok('le dossier SUB entre dans le compte sans etre marque',
                 line == '6 tagged (7 matched)', line)

    return ok_all(s, 'tagpat')


if __name__ == '__main__':
    sys.exit(main())
