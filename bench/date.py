#!/usr/bin/env python3
"""Banc de la surcouche DATE (src/plugins/date.c) : la date systeme et
l'horodatage des fichiers marques.

    make build-6502/date.PLG ARCH=6502 && python3 bench/date.py

DATE dans le menu des surcouches (`!`) montre la date de $BF90-$BF93 --
"No date" sur un Apple II sans horloge, ce qu'est POM2 -- et la presence
d'une horloge (MACHID $BF98). `S` puis douze chiffres DDMMYYYYHHMM posent la
date : on relit $BF90-$BF93 dans l'emulateur. Les fichiers a dater, WORK/A
et WORK/B (deux TXT), sont sur une disquette ProDOS en lecteur 2 : le disque
dur du banc reste en memoire de POM2, seule une disquette est recopiee dans
son fichier a l'arret. Les deux marques, DATE puis `F` les horodate : on
relit la .po sur l'hote et on verifie, dans chaque entree du repertoire
WORK, la date de creation (+$18) et de modification (+$21), et les heures
(+$1A, +$23) : modification changee, creation conservee. La liste des volumes est refusee."""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import ROOT
from xplug import boot_hd, menu_run, ok_all, RET
from prodos_read import Image

PORT = 6803
DAY, MONTH, YEAR, HOUR, MINUTE = 15, 6, 26, 14, 30
DATE_WORD = (YEAR << 9) | (MONTH << 5) | DAY           # $34CF
TIME_WORD = (HOUR << 8) | MINUTE                       # $0E1E
SHOWN = '%02u/%02u/%04u %02u:%02u' % (DAY, MONTH, 2000 + YEAR, HOUR, MINUTE)


def entries_of(img, path):
    """Les entrees vivantes d'un sous-dossier de la racine : {nom: entree}."""
    for e in img.entries(2):
        name = e[1:1 + (e[0] & 15)].decode('ascii')
        if name == path and e[0] >> 4 == 0xD:
            key = int.from_bytes(e[0x11:0x13], 'little')
            return {x[1:1 + (x[0] & 15)].decode('ascii'): x for x in img.entries(key)}
    raise AssertionError(path + ' introuvable sur le volume')


def floppy(tmp):
    """La disquette ProDOS /DATED du lecteur 2 : WORK/A et WORK/B."""
    stage = Path(tmp) / 'dated'
    (stage / 'WORK').mkdir(parents=True)
    (stage / 'WORK/A.TXT').write_bytes(b'alpha\r')
    (stage / 'WORK/B.TXT').write_bytes(b'beta\r')
    po = Path(tmp) / 'DATED.po'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                    '--volume', 'DATED', '--boot', str(ROOT / 'data/prodos_boot.tmpl'),
                    '--blocks', '280'], check=True, capture_output=True)
    return po


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-date-') as tmp:
        po = floppy(tmp)
        before = entries_of(Image(po.read_bytes()), 'WORK')
        with boot_hd(tmp, {}, port=PORT, plugins=['date'], floppy2=po) as (p, s):
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'la liste des volumes'); p.stable()
            s.select('/DATED', 0); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/DATED '), 'la disquette /DATED'); p.stable()
            s.select('WORK', 0); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/DATED/WORK'), 'le dossier WORK'); p.stable()

            # 1. DATE montre l'etat de $BF90-$BF93 et de MACHID.
            clock = p.peek(0xBF98, 1)[0] & 1
            year = p.peek(0xBF91, 1)[0] >> 1
            menu_run(s, p, 'DATE')
            row = s.rows()[22].rstrip()
            s.ok('DATE montre la date systeme (aucune sur POM2) et l horloge (MACHID)',
                 ('No date' in row) == (year == 0) and ('clock:%s' % ('Y' if clock else 'N')) in row
                 and 'S Set date' in row, row)

            # 2. S : douze chiffres, la date se retrouve en $BF90-$BF93.
            s.key(b'S'); p.stable()
            row = s.rows()[22].rstrip()
            s.ok('S demande les douze chiffres DDMMYYYYHHMM', 'DDMMYYYYHHMM' in row, row)
            s.type('%02u%02u%04u%02u%02u' % (DAY, MONTH, 2000 + YEAR, HOUR, MINUTE))
            s.wait(lambda: SHOWN in s.rows()[22], 'la date posee', 20); p.stable()
            got = p.peek(0xBF90, 4)
            want = DATE_WORD.to_bytes(2, 'little') + bytes([MINUTE, HOUR])
            s.ok('$BF90-$BF93 portent %s (jour, mois, annee, minute, heure)' % SHOWN,
                 got == want, got.hex() + ' attendu ' + want.hex())
            s.ok('la ligne 22 relit la date systeme', SHOWN in s.rows()[22], s.rows()[22].rstrip())

            # Year 2000 is valid although its packed year field is zero.
            menu_run(s, p, 'DATE'); s.key(b'S'); p.stable()
            s.type('010120000000')
            s.wait(lambda: '01/01/2000 00:00' in s.rows()[22], 'annee 2000', 20)
            s.ok('2000 est affiche comme une date', 'No date' not in s.rows()[22], s.rows()[22].rstrip())
            menu_run(s, p, 'DATE'); s.key(b'S'); p.stable()
            s.type('%02u%02u%04u%02u%02u' % (DAY, MONTH, 2000 + YEAR, HOUR, MINUTE))
            s.wait(lambda: SHOWN in s.rows()[22], 'date restauree', 20)

            # 3. Une date impossible est refusee, $BF90 intact.
            menu_run(s, p, 'DATE'); s.key(b'S'); p.stable()
            s.type('311320261430')
            s.wait(lambda: s.has('Not a date'), 'le refus', 20); p.stable()
            s.ok('31/13 est refuse, la date systeme reste', p.peek(0xBF90, 4) == want, s.rows()[22].rstrip())

            # 4. A et B marques, F les horodate ; le panneau montre la date.
            s.select('A', 0); s.key(b' ')
            s.select('B', 0); s.key(b' '); p.stable()
            s.ok('A et B marques', '2 tagged' in s.rows()[21], s.rows()[21].rstrip())
            menu_run(s, p, 'DATE')
            s.ok('DATE relance montre la date posee', SHOWN in s.rows()[22], s.rows()[22].rstrip())
            s.key(b'F')
            s.wait(lambda: s.has('2 files dated'), 'les deux fichiers dates', 30); p.stable()
            s.ok('F annonce 2 files dated', s.has('2 files dated'), s.rows()[22].rstrip())
            s.select('A', 0); p.stable()
            s.ok('le panneau reli montre A au %02u/%02u/%02u' % (DAY, MONTH, YEAR),
                 '%02u/%02u/%02u' % (DAY, MONTH, YEAR) in s.rows()[21], s.rows()[21].rstrip())

            # 5. La liste des volumes est refusee.
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'la liste des volumes'); p.stable()
            menu_run(s, p, 'DATE'); s.key(b'F')
            s.wait(lambda: s.has('Open a directory'), 'le refus des volumes', 20); p.stable()
            s.ok('F dans la liste des volumes est refuse', s.has('Open a directory'), s.rows()[22].rstrip())

        # 6. La disquette relue sur l'hote (POM2 l'a recopiee a l'arret) :
        # creation et modification, date et heure.
        after = entries_of(Image(po.read_bytes()), 'WORK')
        for name in ('A', 'B'):
            e, e0 = after[name], before[name]
            cdate, ctime = e[0x18:0x1A], e[0x1A:0x1C]
            mdate, mtime = e[0x21:0x23], e[0x23:0x25]
            s.ok('%s : date de modification %s, creation conservee sur le disque' % (name, SHOWN),
                 mdate == DATE_WORD.to_bytes(2, 'little') and mtime == TIME_WORD.to_bytes(2, 'little')
                 and cdate == e0[0x18:0x1A] and ctime == e0[0x1A:0x1C],
                 'cree %s %s, modifie %s %s (avant : %s)' % (cdate.hex(), ctime.hex(), mdate.hex(), mtime.hex(), e0[0x21:0x23].hex()))
            s.ok('%s : acces, type et auxtype gardes' % name,
                 e[0x1E] == e0[0x1E] and e[0x10] == e0[0x10] and e[0x1F:0x21] == e0[0x1F:0x21],
                 'acces $%02X type $%02X aux %s' % (e[0x1E], e[0x10], e[0x1F:0x21].hex()))
        s.ok('les dates d origine (mkvolume) etaient differentes',
             before['A'][0x21:0x23] != DATE_WORD.to_bytes(2, 'little'), before['A'][0x21:0x23].hex())
    return ok_all(s, 'bench/date.py')


if __name__ == '__main__':
    sys.exit(main())
