#!/usr/bin/env python3
"""Banc de la surcouche d'un tiers : construit sdk/hello.c HORS de l'arbre
(seul src/a2fc_plugin.h, sdk/plugin.cfg), le pose sous A2FILE/HELLO.PLG sur
une disquette, l'ouvre dans le menu des surcouches (`!`) et vérifie qu'il
tourne par la table de services -- il lit l'entrée sélectionnée et en écrit
le nom, le type et le chemin en ligne de message.

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/plugin.py

Prouve que l'ABI (struct A2fcApi) tient pour un tiers : la surcouche n'est
liée ni avec A2FILE.CODE ni avec crt0, ne connaît aucune adresse du
programme, et pourtant s'affiche dans le menu et s'exécute."""

import shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, ROOT
from run import scratch_volume, RET


def main():
    # 1. Construire la surcouche d'exemple hors de l'arbre.
    build = ROOT / 'build'
    plg = build / 'HELLO.PLG'
    subprocess.run(['sh', str(ROOT / 'sdk' / 'build.sh'),
                    str(ROOT / 'sdk' / 'hello.c'), 'HELLO'],
                   check=True, cwd=ROOT)
    hdr = plg.read_bytes()[:8]
    checks = []
    def ok(label, cond, detail=''):
        checks.append(cond)
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''),
              flush=True)

    ok("l'en-tete signe PLUGIN_MAGIC ($A2FC)", hdr[0] == 0xFC and hdr[1] == 0xA2,
       '%02X%02X' % (hdr[1], hdr[0]))
    ok("le point d'entree pointe dans la fenetre $1B00", 0x1B < hdr[4] < 0x40 or hdr[3:5] != b'\x00\x00',
       '$%02X%02X' % (hdr[4], hdr[3]))

    with tempfile.TemporaryDirectory(prefix='a2fc-plugin-') as tmp:
        tmp = Path(tmp)
        stage = tmp / 'vol'
        shutil.copytree(build / 'vol', stage)
        shutil.copyfile(plg, stage / 'A2FILE' / 'HELLO.PLG#061B00')
        po = tmp / 'PLUGIN.po'
        subprocess.run(['python3', str(ROOT / 'tools' / 'mkvolume.py'), str(stage), str(po),
                        '--volume', 'A2FILECMD', '--boot', str(ROOT / 'data' / 'prodos_boot.tmpl'),
                        '--blocks', '280'], check=True, cwd=ROOT, capture_output=True)

        with Pom2(scratch_volume(tmp), floppy=po, port=6667) as p:
            s = Session(p)
            s.boot()
            # Descendre dans DEMO, curseur sur HELLO (un BAS, type $FC).
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/A2FILECMD'); s.key(RET)
            s.wait(lambda: s.rows()[0][:11] == '/A2FILECMD ', 'racine'); p.stable()
            s.select('DEMO'); s.key(RET); s.wait(lambda: s.has('/A2FILECMD/DEMO'), 'DEMO'); p.stable()
            s.select('HELLO'); p.stable()

            # Le menu des surcouches lit l'en-tete de chaque .PLG.
            s.key(b'!'); s.wait(lambda: s.has('the overlays'), 'menu', 30); p.stable()
            ok('la surcouche du tiers parait dans le menu, decrite par son en-tete',
               any('Example third-party plugin' in r for r in s.rows()))

            # Sauter sur HELLO par sa lettre : le menu classe par nom et la
            # touche saute a l'entree suivante commencant par la lettre. Le
            # premier H est HELLO (avant HELP, HEX), quel que soit le nombre
            # de surcouches classees avant -- plus robuste qu'un compte de bas.
            s.key(b'H'); p.stable()
            s.key(RET); time.sleep(0.6); p.stable()

            row22 = s.rows()[22].rstrip()
            ok('la surcouche a tourne par la table de services',
               'Plugin:' in row22, row22)
            ok('elle a lu le nom, le type et le chemin de la selection',
               '"HELLO"' in row22 and 'FC' in row22 and '/A2FILECMD/DEMO' in row22, row22)
            ok('A2FC a repris la main sur ses panneaux', s.has('Type  Aux'))

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
