#!/usr/bin/env python3
"""Banc du controle de machine du lanceur : sur un Apple II qui ne convient
pas, A2FILE.SYSTEM le dit en 40 colonnes et rend la main a ProDOS, au lieu
d'un ecran vide.

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/machine.py

Le lanceur (crt0_loader.s, src/machine_check.inc) verifie en pur 6502, avant
tout code 65C02 : IIe ou plus recent ($FBB3), 128 Ko et carte 80 colonnes
(MACHID $BF98) ; l'edition 65C02 veut en plus le firmware enhanced ($FBC0)
ET un vrai 65C02. On falsifie MACHID depuis l'invite BASIC (bit 5, les
128 Ko, a zero) avant de lancer -A2FILE.SYSTEM ; sur `--preset iie_nmos`
(firmware enhanced, 6502 NMOS) l'edition 65C02 doit refuser le processeur et
l'edition 6502 passer ; enfin un //c passe le controle.

Les deux editions doivent etre construites : make disk."""

import shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, ROOT, DISK, BUILD
from run import RET, ESC, scratch_volume


def has40(s, needle):
    return any(needle in r for r in s.rows40())


def basic_hd(tmp, build, name):
    """Un disque dur qui amorce BASIC.SYSTEM, l'edition de `build` sous APPS/."""
    stage = tmp / name
    apps = stage / 'APPS'                    # pas a la racine : A2FILE.SYSTEM y passerait avant BASIC.SYSTEM
    shutil.copytree(build / 'vol/A2FILE', apps / 'A2FILE')
    shutil.copyfile(build / 'vol/A2FILE.SYSTEM.SYS', apps / 'A2FILE.SYSTEM.SYS')
    shutil.copyfile(ROOT / 'data/PRODOS.SYS', stage / 'PRODOS.SYS')
    shutil.copyfile(ROOT / 'data/BASIC.SYSTEM.SYS', stage / 'BASIC.SYSTEM.SYS')
    hdv = tmp / (name + '.hdv')              # amorce sur BASIC.SYSTEM, seul .SYSTEM de la racine
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(hdv),
                    '--volume', 'HD', '--blocks', '1600',
                    '--boot', str(ROOT / 'data/prodos_boot.tmpl')], check=True, capture_output=True)
    return hdv


def main():
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-machine-') as tmp:
        tmp = Path(tmp)
        hdv = basic_hd(tmp, BUILD, 'hd')

        with Pom2(hdv, port=6743) as p:
            s = Session(p)
            s.wait(lambda: any(r.startswith(']') for r in s.rows40()), 'invite BASIC', 90); time.sleep(1)
            machid = p.peek(0xBF98, 1)[0]
            ok('MACHID dit 128 Ko et 80 colonnes sur le IIe de POM2', machid & 0x22 == 0x22, hex(machid))
            p.poke(0xBF98, bytes([machid & ~0x20]))          # une machine de 64 Ko
            s.type('-APPS/A2FILE.SYSTEM'); s.key(RET)
            s.wait(lambda: has40(s, 'A2 FILE CMD NEEDS AN'), 'le refus', 30); time.sleep(0.5)   # enhanced ou 6502 : le texte differe
            ok('sur 64 Ko, le lanceur le dit en 40 colonnes au lieu d un ecran vide',
               has40(s, '128K AND') and has40(s, 'PRESS A KEY'), [r for r in s.rows40() if r.strip()][:3])
            s.key(b' ')
            s.wait(lambda: any(r.startswith(']') for r in s.rows40()) or has40(s, 'BITSY') or has40(s, 'ProDOS'),
                   'retour a ProDOS', 60)
            ok('une touche rend la main a ProDOS (BASIC ou Bitsy Bye)', True)
            p.poke(0xBF98, bytes([machid]))                   # la machine telle qu elle est

        # Un IIe enhanced avec un 6502 NMOS : le firmware seul ne suffit pas
        # a l'edition 65C02, dont le code partirait dans le decor.
        for build, edition in ((ROOT / 'build', '65C02'), (ROOT / 'build-6502', '6502')):
            with Pom2(basic_hd(tmp, build, 'hd-' + edition), port=6745, preset='iie_nmos') as p:
                s = Session(p)
                s.wait(lambda: any(r.startswith(']') for r in s.rows40()), 'invite BASIC (' + edition + ')', 90)
                time.sleep(1)
                s.type('-APPS/A2FILE.SYSTEM'); s.key(RET)
                if edition == '65C02':
                    s.wait(lambda: has40(s, 'NEEDS A 65C02'), 'le refus du processeur', 30); time.sleep(0.5)
                    ok('edition 65C02 sur IIe enhanced a 6502 : refus du processeur, en 40 colonnes',
                       has40(s, 'USE THE 6502 EDITION') and has40(s, 'PRESS A KEY'),
                       [r for r in s.rows40() if r.strip()][:4])
                    s.key(b' ')
                    s.wait(lambda: any(r.startswith(']') for r in s.rows40()) or has40(s, 'BITSY')
                           or has40(s, 'ProDOS'), 'retour a ProDOS', 60)
                    ok('et une touche rend la main a ProDOS', True)
                else:
                    s.wait(lambda: s.has('/HD'), 'les panneaux', 90); p.stable()
                    ok('edition 6502 sur IIe enhanced a 6502 : le controle passe, panneaux affiches',
                       not has40(s, 'NEEDS A') and s.has('/HD'), s.rows()[0][:30])

        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(DISK, floppy)
        with Pom2(scratch_volume(tmp), floppy=floppy, port=6744, preset='iic') as p:
            s = Session(p)
            s.boot()
            ok('un //c passe le controle et arrive sur les panneaux', s.has('/A2FILECMD'), s.rows()[0][:30])
            # Le //c a une souris integree (slot 4). Sa premiere lecture rendait
            # un faux clic bouton-enfonce en (0,0) : un ESC, qui a la racine
            # retombait sur la liste des volumes. Le panneau doit tenir bon.
            time.sleep(2); p.stable()
            ok('la souris du //c ne provoque pas de clic fantome au demarrage',
               s.rows()[0].startswith('/A2FILECMD'), s.rows()[0][:20])
            s.select('A2FILE'); s.key(RET); s.wait(lambda: s.has('/A2FILECMD/A2FILE'), 'sous-dossier')
            s.key(ESC); s.wait(lambda: s.rows()[0].startswith('/A2FILECMD'), 'retour'); p.stable()
            ok('et un aller-retour dans un sous-dossier garde le chemin', s.rows()[0].startswith('/A2FILECMD'), s.rows()[0][:20])

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
