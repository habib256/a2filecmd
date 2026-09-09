#!/usr/bin/env python3
"""Banc de la carte RGB Le Chat Mauve : l'ecran d'A2 File Cmd avec la carte.

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/chatmauve.py [variante...]

Avec la carte en slot 7 (pom2_playtest --chatmauve, variante Feline par
defaut), l'image ALIEN vue depuis A2 File Cmd doit etre celle qu'affiche
n'importe quel programme : on la fait d'abord afficher par BASIC (BLOAD et
les commutateurs poses a la main), on garde l'ecran, puis A2FC l'ouvre et
l'ecran doit etre le meme, pixel pour pixel. Ensuite la mire DHGR brute doit
se rendre en bandes unies de seize couleurs, et ALIEN reste identique apres
une seconde HGR et apres la DHGR : la visionneuse ne deregle pas le verrou
de mode de la carte (jusqu'en 0.6.8, chaque HGR le faisait avancer)."""

import os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, ROOT, BUILD
from run import RET, TAB, ESC, solid_bands
import mkdemo
import urllib.request


def ppm_diff(a, b):
    """Le nombre de pixels qui different entre deux ecrans de meme taille."""
    if a[:20] != b[:20] or len(a) != len(b):
        return -1
    return sum(1 for i in range(0, len(a), 3) if a[i:i + 3] != b[i:i + 3]) if a != b else 0


def main(variants):
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-lcm-') as tmp:
        tmp = Path(tmp)
        stage = tmp / 'hd'
        apps = stage / 'APPS'                # pas a la racine : A2FILE.SYSTEM y passerait avant BASIC.SYSTEM
        shutil.copytree(BUILD / 'vol/A2FILE', apps / 'A2FILE')
        shutil.copyfile(BUILD / 'vol/A2FILE.SYSTEM.SYS', apps / 'A2FILE.SYSTEM.SYS')
        shutil.copyfile(ROOT / 'data/PRODOS.SYS', stage / 'PRODOS.SYS')
        shutil.copyfile(ROOT / 'data/BASIC.SYSTEM.SYS', stage / 'BASIC.SYSTEM.SYS')
        (stage / 'IMGHGR').mkdir()
        shutil.copyfile(ROOT / 'data/IMGHGR/ALIEN#062000', stage / 'IMGHGR/ALIEN#062000')
        mkdemo.make(stage / 'DEMO', full=True)
        hdv = tmp / 'HD.hdv'                 # amorce sur BASIC.SYSTEM, seul .SYSTEM de la racine
        subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(hdv),
                        '--volume', 'HD', '--blocks', '3200',
                        '--boot', str(ROOT / 'data/prodos_boot.tmpl')], check=True, capture_output=True)

        for n, variant in enumerate(variants):
            print(f'--- Le Chat Mauve, variante {variant}', flush=True)
            with Pom2(hdv, port=int(os.environ.get('A2FC_PORT', 6760)) + n, chatmauve=variant) as p:
                s = Session(p)
                shot = lambda: urllib.request.urlopen(p.base + '/screen.ppm').read()
                s.wait(lambda: any(r.startswith(']') for r in s.rows40()), 'invite BASIC', 90); time.sleep(1)
                s.type('BLOAD /HD/IMGHGR/ALIEN,A$2000'); s.key(RET); time.sleep(2)
                s.type('POKE 49239,0:POKE 49234,0:POKE 49236,0:POKE 49232,0'); s.key(RET); time.sleep(1.5)
                ref = shot()
                ok('BASIC affiche ALIEN avec la carte (ecran de reference)',
                   p.peek(0x2000, 8192) == (ROOT / 'data/IMGHGR/ALIEN#062000').read_bytes() and len(set(ref[20::97])) > 4,
                   len(ref))
                s.type('TEXT'); s.key(RET); time.sleep(0.5)
                s.type('-APPS/A2FILE.SYSTEM'); s.key(RET)
                s.boot()
                ok('A2FC demarre sur /HD', s.rows()[0].startswith('/HD'), s.rows()[0][:20])
                s.select('..', 0); s.key(RET); s.wait(lambda: s.has('IMGHGR/'), 'racine'); p.stable()   # A2FC part de /HD/APPS
                s.select('IMGHGR', 0); s.key(RET); s.wait(lambda: s.has('/HD/IMGHGR'), 'IMGHGR'); p.stable()
                s.select('ALIEN', 0); s.key(RET)
                s.wait(lambda: s.value('view', 1) == 1, 'image ALIEN', 40); time.sleep(1.5)
                d = ppm_diff(ref, shot())
                ok('ALIEN vu depuis A2FC : le meme ecran que BASIC, pixel pour pixel', d == 0, f'{d} pixels differents')
                # une seconde HGR de suite : jusqu'en 0.6.8, chaque affichage
                # HGR faisait avancer le verrou de mode de la carte
                s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
                s.select('ALIEN', 0); s.key(RET)
                s.wait(lambda: s.value('view', 1) == 1, 'image ALIEN', 40); time.sleep(1.5)
                d = ppm_diff(ref, shot())
                ok('une seconde HGR de suite : toujours le meme ecran (le verrou de la carte ne derive pas)',
                   d == 0, f'{d} pixels differents')
                s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
                s.key(TAB)                   # le panneau droit liste les volumes : /HD puis DEMO
                s.select('/HD', 40); s.key(RET); s.wait(lambda: s.rows()[0][40:].startswith('/HD '), 'volume /HD'); p.stable()
                s.select('DEMO', 40); s.key(RET); s.wait(lambda: s.has('/HD/DEMO'), 'DEMO'); p.stable()
                s.select('DHGR.RAW', 40); s.key(RET)
                s.wait(lambda: s.value('view', 1) == 1, 'image DHGR brute', 40); time.sleep(1.5)
                solid, rows, colours = solid_bands(shot())
                ok('la mire DHGR brute : bandes unies, seize couleurs, avec la carte',
                   solid == rows and colours >= 15, (solid, rows, colours))
                s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
                s.key(TAB)
                s.select('ALIEN', 0); s.key(RET)
                s.wait(lambda: s.value('view', 1) == 1, 'image ALIEN', 40); time.sleep(1.5)
                d = ppm_diff(ref, shot())
                ok('apres la DHGR, ALIEN est toujours rendu a l identique (verrou de la carte intact)',
                   d == 0, f'{d} pixels differents')
                s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour')

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or ['feline']))
