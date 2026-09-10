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
FILES.update({f'MANY/HIT{i:03}#040000':b'page marker\r' for i in range(45)})
FILES['MANY/ZZZ/DEEP/HITEND#040000']=b'page marker\r'
FILES.update({f'EXACT/ONLY{i:02}#040000':b'exact marker\r' for i in range(20)})
PROMPT = 'Find (= ?'


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
            stack=p.peek(0x80,2);floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8)
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
            for pattern in ('HIT=','"PAGE MARKER'):
                find(s,p,pattern)
                all_paths=listed(s)
                s.ok(pattern+' : first 20, continuation available',len(all_paths)==20 and s.has('Results 1-20; more matches'))
                s.key(b'N');s.wait(lambda:s.has('Results 21-40'),'second result page',60);p.stable();all_paths+=listed(s)
                s.key(b'N');s.wait(lambda:s.has('Results 41-46'),'last result page',60);p.stable();last=listed(s);all_paths+=last
                s.ok(pattern+' : all 46 results exactly once',len(all_paths)==46 and len(set(all_paths))==46,all_paths)
                s.ok(pattern+' : late subdirectory scanned',last[-1]=='/WORKHD/MANY/ZZZ/DEEP/HITEND' and s.has('; complete'))
                s.key(b'N');p.stable();s.ok('N at end leaves final results visible',listed(s)==last)
                for _ in range(len(last)-1):s.key(DOWN)
                s.key(RET);s.wait(lambda:s.rows()[0].startswith('/WORKHD/MANY/ZZZ/DEEP'),'late result opened',30);p.stable()
                s.ok('result beyond 40 opens correct file',s.line(0).startswith('HITEND ') and s.rows()[22].startswith('46 match(es).'))
            find(s,p,'ONLY=')
            s.ok('exactly 20 results are complete without empty next page',len(listed(s))==20 and s.has('Results 1-20; complete') and not s.has('N Next'))
            s.key(ESC);p.stable()
            # Filters combine with the existing query and survive result pages.
            menu_run(s,p,'FIND');s.wait(lambda:s.has(PROMPT),'FIND prompt',20)
            s.type('"PAGE MARKER');s.key(b'\x09');s.wait(lambda:s.has('FIND FILTERS'),'filters')
            s.key(b'T');s.wait(lambda:s.has('Type (2 hex)'),'type prompt');s.type('04');s.key(RET)
            s.wait(lambda:s.has('Type $04'),'type applied')
            def dates(lo,hi):
                s.key(b'D');s.wait(lambda:s.has('From YYYYMMDD'),'start date');s.type(lo);s.key(RET)
                s.wait(lambda:s.has('To YYYYMMDD'),'end date');s.type(hi);s.key(RET);p.stable()
            s.key(b'D');s.wait(lambda:s.has('From YYYYMMDD'),'start date');s.type('20260229');s.key(RET)
            s.wait(lambda:s.has('Invalid dates.'),'invalid leap day');s.ok('invalid leap day rejected',True)
            s.key(RET);p.stable()
            dates('20260907','20260907')
            s.ok('inclusive modification date range displayed',s.has('20260907-20260907'))
            dates('20260908','20260907')
            s.ok('reversed dates rejected',s.has('Invalid dates.'));s.key(RET);p.stable()
            s.ok('invalid edit retains previous range',s.has('20260907-20260907'))
            s.key(b'D');s.wait(lambda:s.has('From YYYYMMDD'),'start date');s.type('20260901');s.key(RET)
            s.wait(lambda:s.has('To YYYYMMDD'),'end date');s.key(ESC);p.stable()
            s.ok('cancelled edit retains previous range',s.has('20260907-20260907'))
            s.key(RET);s.wait(lambda:s.has(PROMPT),'query retained');s.key(RET)
            s.wait(lambda:s.has('Results 1-20'),'filtered results',60);p.stable()
            s.ok('query, volume and filters retained',s.has('Type $04') and s.has('20260907-20260907') and s.has('in /WORKHD'))
            s.key(b'N');s.wait(lambda:s.has('Results 21-40'),'filtered second page',60)
            s.key(b'N');s.wait(lambda:s.has('Results 41-46'),'filtered final page',60)
            s.ok('combined filters retain late subdirectory',listed(s)[-1]=='/WORKHD/MANY/ZZZ/DEEP/HITEND')
            s.key(ESC);p.stable()
            find(s,p,'OTHER')
            s.ok('new invocation resets filters',listed(s)==['/WORKHD/WORK/SUB/OTHER'] and s.has('Any type'))
            s.key(ESC);p.stable()
            menu_run(s,p,'FIND');s.wait(lambda:s.has(PROMPT),'FIND prompt',20)
            s.type('OTHER');s.key(b'\x09');s.wait(lambda:s.has('FIND FILTERS'),'filters')
            s.key(b'T');s.wait(lambda:s.has('Type (2 hex)'),'type prompt');s.type('04');s.key(RET)
            s.key(RET);s.wait(lambda:s.has(PROMPT),'query');s.key(RET)
            s.wait(lambda:s.has('Nothing found'),'excluded BIN',60)
            s.ok('type filter excludes BIN from TXT search',s.has('Nothing found.'))
            menu_run(s,p,'FIND');s.wait(lambda:s.has(PROMPT),'FIND prompt',20)
            s.type('OTHER');s.key(b'\x09');s.wait(lambda:s.has('FIND FILTERS'),'filters')
            dates('20260908','20391231');s.key(b'A');p.stable()
            s.ok('A clears date and type filters',s.has('Any type') and s.has('All dates'))
            s.key(ESC);s.wait(lambda:s.has(PROMPT),'query');s.key(RET)
            s.wait(lambda:s.has('1 match(es)'),'unfiltered result',60);s.key(ESC);p.stable()
            menu_run(s,p,'FIND');s.wait(lambda:s.has(PROMPT),'FIND prompt',20)
            s.type('"');s.key(b'\x09');s.wait(lambda:s.has('FIND FILTERS'),'filters')
            dates('19400101','20391231');s.key(RET);s.wait(lambda:s.has(PROMPT),'empty text query');s.key(RET)
            s.wait(lambda:s.has('Type  Aux     Size'),'panels after empty text',30);p.stable()
            s.ok('empty text query does not leak filter dates into status',not s.has('19400101-20391231'))
            s.ok('stack restored and budget respected',p.peek(0x80,2)==stack and p.peek(floor,8)==b'\xA5'*8)
    return ok_all(s, 'findfile')


if __name__ == '__main__':
    sys.exit(main())
