#!/usr/bin/env python3
"""Banc de la surcouche FIND (src/plugins/find.c) : les fichiers d'un volume
entier retrouves par un motif de nom (jokers de Copy II Plus, `=` et `?`)
ou par un texte qu'ils contiennent (motif commencant par `"`), listes en
plein ecran, et le panneau actif amene sur celui que l'on choisit.

    make build/find.PLG && A2FC_IMG=A2FILECMD-full python3 bench/findfile.py

(bench/find.py est le banc de COMPARE et SEARCH, d'ou ce nom.)

L'arbre d'essai : WORK/A, WORK/TARGET2, WORK/SUB/OTHER, WORK/SUB/DEEP/TARGET
-- ce dernier contient "needle in a haystack". `TARGET=` trouve deux
fichiers, le plus profond choisi amene le panneau sur /WORKHD/WORK/SUB/DEEP
avec le curseur sur TARGET ; `"NEEDLE` n'en trouve qu'un ; `"CROSSING` est
lu a cheval sur deux lectures de 512 octets dans WORK/EDGE ; `ZZZ=` rien.
Depuis la liste des volumes, la recherche porte sur le volume selectionne."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, menu_run, ok_all, RET, ESC

PORT = 6806
DOWN, UP = b'\x0a', b'\x0b'
FILES = {
    'WORK/A.TXT': b'a plain text file\r',
    'WORK/SUB/DEEP/TARGET.TXT': b'needle in a haystack\r',
    'WORK/SUB/OTHER.BIN': bytes(range(256)),
    'WORK/TARGET2.TXT': b'the second target\r',
    'WORK/EDGE.BIN': b'x' * 507 + b'crossing the edge\r' + b'y' * 100,   # le texte a cheval sur l'octet 512
}
PROMPT = 'Find (= any run'


def find(s, p, pattern):
    """Lance FIND, tape le motif, attend la liste ou le verdict."""
    menu_run(s, p, 'FIND')
    s.wait(lambda: s.has(PROMPT), "l'invite de FIND", 20)
    s.type(pattern); s.key(RET)
    s.wait(lambda: s.has('match(es)') or s.has('Nothing found') or s.has('aborted'), 'la recherche', 60)
    p.stable()


def listed(s):
    """Les chemins listes en plein ecran (lignes 2-21)."""
    return [r.strip() for r in s.rows()[2:22] if r.strip()]


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-findfile-') as tmp:
        tmp = Path(tmp)
        with boot_hd(tmp, FILES, port=PORT, plugins=['find']) as (p, s):
            s.select('WORK'); s.key(RET); s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()

            # -- TARGET= : deux fichiers, le plus profond choisi --------------
            find(s, p, 'TARGET=')
            s.ok('TARGET= : deux fichiers trouves', s.rows()[0].startswith('2 match(es) for TARGET= in /WORKHD'),
                 s.rows()[0].strip())
            paths = listed(s)
            s.ok('les deux chemins complets sont listes',
                 sorted(paths) == ['/WORKHD/WORK/SUB/DEEP/TARGET', '/WORKHD/WORK/TARGET2'], paths)
            for _ in range(3):
                r = s.cursor_row(0)
                if r is not None and 'DEEP/TARGET' in s.rows()[r]:
                    break
                s.key(DOWN); p.stable()
            s.ok('le curseur est sur le fichier profond', 'DEEP/TARGET' in s.line(0), s.line(0).strip())
            s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD/WORK/SUB/DEEP'), 'le panneau sur DEEP', 30); p.stable()
            s.ok('le panneau actif est sur /WORKHD/WORK/SUB/DEEP', s.rows()[0].startswith('/WORKHD/WORK/SUB/DEEP '),
                 s.rows()[0].strip()[:40])
            s.ok('le curseur est sur TARGET', s.line(0).startswith('TARGET '), s.line(0).strip()[:24])
            s.ok('la note dit les deux trouvailles', s.rows()[22].startswith('2 match(es).'), s.rows()[22].strip())

            # -- "NEEDLE : un seul fichier contient le texte -----------------
            find(s, p, '"NEEDLE')
            s.ok('"NEEDLE : un seul fichier contient le texte',
                 s.rows()[0].startswith('1 match(es) for "NEEDLE in /WORKHD'), s.rows()[0].strip())
            s.ok('c est TARGET, au fond de SUB/DEEP', listed(s) == ['/WORKHD/WORK/SUB/DEEP/TARGET'], listed(s))
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux     Size'), 'le retour aux panneaux', 30); p.stable()
            s.ok('ESC rend les panneaux, toujours sur DEEP', s.rows()[0].startswith('/WORKHD/WORK/SUB/DEEP '),
                 s.rows()[0].strip()[:40])

            # -- "CROSSING : le texte a cheval sur deux lectures de 512 octets --
            find(s, p, '"CROSSING THE')
            s.ok('"CROSSING THE : trouve a cheval sur la frontiere de 512 octets',
                 s.rows()[0].startswith('1 match(es)') and listed(s) == ['/WORKHD/WORK/EDGE'], listed(s))
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux     Size'), 'le retour aux panneaux', 30); p.stable()

            # -- ZZZ= : rien ---------------------------------------------------
            find(s, p, 'ZZZ=')
            s.ok('ZZZ= : rien trouve', s.rows()[22].startswith('Nothing found.'), s.rows()[22].strip())

            # -- ESC a l'invite : rien ne bouge --------------------------------
            menu_run(s, p, 'FIND')
            s.wait(lambda: s.has(PROMPT), "l'invite de FIND", 20)
            s.key(ESC); time.sleep(0.5)
            s.wait(lambda: s.has('Type  Aux     Size'), 'le retour aux panneaux', 30); p.stable()
            s.ok('ESC a l invite laisse le panneau en place', s.rows()[0].startswith('/WORKHD/WORK/SUB/DEEP ')
                 and not s.has(PROMPT), s.rows()[0].strip()[:40])

            # -- Depuis la liste des volumes : le volume selectionne ----------
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
            s.select('/WORKHD'); p.stable()
            find(s, p, 'OTHER')
            s.ok('depuis la liste des volumes, OTHER est trouve dans /WORKHD',
                 s.rows()[0].startswith('1 match(es) for OTHER in /WORKHD') and listed(s) == ['/WORKHD/WORK/SUB/OTHER'],
                 (s.rows()[0].strip(), listed(s)))
            s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD/WORK/SUB '), 'le panneau sur SUB', 30); p.stable()
            s.ok('Return depuis la liste des volumes ouvre /WORKHD/WORK/SUB sur OTHER',
                 s.line(0).startswith('OTHER '), s.line(0).strip()[:24])
    return ok_all(s, 'findfile')


if __name__ == '__main__':
    sys.exit(main())
