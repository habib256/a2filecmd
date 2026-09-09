#!/usr/bin/env python3
"""Banc du disque dur : le .2mg publie amorce-t-il, avec son dossier DEMO ?

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/hd.py

Le .2mg est le volume /A2FILECMD complet : le programme et un dossier DEMO
avec un exemplaire de chaque chose qu'A2 File Cmd sait ouvrir. POM2 le prend
sans son en-tete de 64 octets, comme disque dur en slot 7, sans disquette :
c'est lui qui amorce. On verifie les deux panneaux, le compte des blocs, la
liste de DEMO, puis qu'une page brute s'affiche et qu'un .2MG s'ouvre comme
un dossier."""

import os, shutil, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import VERSION, Pom2, Session, ROOT, DISK, labels
from run import RET, TAB, ESC, solid_bands
import urllib.request

DEMO = ['DHGR.RAW', 'DHGR.RLE', 'DOS33.DSK', 'HELLO', 'HGR.RAW', 'HGR.RLE', 'LETTER', 'README',
        'SAMPLE', 'SAMPLE.BNY', 'SAMPLE.SHK', 'TINY.2MG', 'TINY.PO', 'WELCOME.MB']


def main():
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-hd-') as tmp:
        tmp = Path(tmp)
        hdv = tmp / 'A2FILECMD.hdv'
        cpu = os.environ.get('A2FC_CPU', '65C02')
        build = ROOT / ('build-6502' if cpu == '6502' else 'build')
        volume = '/A2XL' + cpu
        two = (ROOT / ('dist/A2FILECMD-%s-XL-%s.2mg' % (cpu, VERSION))).read_bytes()
        ok('le .2mg porte l en-tete 2IMG, format ProDOS, 65535 blocs',
           two[:4] == b'2IMG' and two[12] == 1 and int.from_bytes(two[20:24], 'little') == 65535)
        hdv.write_bytes(two[64:])

        with Pom2(hdv, port=6715) as p:
            s = Session(p, labels(build / 'a2fc.lbl'))   # les symboles du processeur choisi
            s.boot()
            ok('le disque XL amorce sur les deux panneaux', s.rows()[0].startswith(volume), s.rows()[0][:40])
            ok('le panneau droit ouvre DEMO', s.rows()[0][40:].startswith(volume + '/DEMO'),
               s.rows()[0][40:70])
            ok('le volume fait 65535 blocs', 'of 65535 blocks free' in s.rows()[20], s.rows()[20][:70])
            names = [r[40:].split(' ')[0] for r in s.rows()[2:20]]
            ok('DEMO montre un exemplaire de chaque type', all(n in names for n in DEMO),
               [n for n in DEMO if n not in names])
            names_left = [r[:16].split(' ')[0].rstrip('/') for r in s.rows()[2:20]]
            ok('IMGHGR est a la racine', 'IMGHGR' in names_left, names_left[:6])
            s.select('IMGHGR', 0); s.key(RET); s.wait(lambda: s.has(volume + '/IMGHGR'), 'IMGHGR'); p.stable()
            imgs = [r[:16].split(' ')[0] for r in s.rows()[2:20] if r[:16].strip() and not r.startswith('..')]
            ok('neuf pages HGR de POM1, aux noms ProDOS anglais', len(imgs) == 9 and 'TIGER' in imgs and 'VILLAGE' in imgs and 'LIZARD' in imgs, imgs)
            s.select('TIGER', 0); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 1, 'image TIGER', 40); time.sleep(1)
            ok('une page HGR de la collection s affiche', s.value('view', 1) == 1)
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            s.key(TAB)
            s.select('DHGR.RAW', 40); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 1, 'image DHGR brute', 40); time.sleep(1)
            ok('la page DHGR brute s affiche', s.value('view', 1) == 1)
            solid, rows, colours = solid_bands(urllib.request.urlopen(p.base + '/screen.ppm').read())
            ok('en bandes unies, quinze couleurs', solid == rows and colours >= 15, (solid, rows, colours))
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            s.select('TINY.2MG', 40); s.key(RET)
            s.wait(lambda: s.has('HELLO ') and s.has('INSIDE/'), 'ouvrir le .2MG', 30); p.stable()
            ok('le .2MG s ouvre comme un dossier', s.has('HELLO ') and s.has('INSIDE/'),
               s.rows()[0][40:70])
            s.key(ESC); s.wait(lambda: s.has(volume + '/DEMO'), 'sortir'); p.stable()

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
