#!/usr/bin/env python3
"""Banc du controle de machine du lanceur : sur un Apple II qui ne convient
pas, A2FILE.SYSTEM le dit en 40 colonnes et rend la main a ProDOS, au lieu
d'un ecran vide.

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/machine.py

Le lanceur (crt0_loader.s) verifie en pur 6502, avant tout code 65C02 :
IIe ou plus recent ($FBB3), pas le IIe non enhanced ($FBC0), 128 Ko et carte
80 colonnes (MACHID $BF98). POM2 n'a pas de IIe non enhanced ici : on
falsifie MACHID depuis l'invite BASIC (bit 5, les 128 Ko, a zero) avant de
lancer -A2FILE.SYSTEM, puis on verifie qu'un //c passe le controle."""

import shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, ROOT, DISK, BUILD
from run import RET, scratch_volume


def has40(s, needle):
    return any(needle in r for r in s.rows40())


def main():
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-machine-') as tmp:
        tmp = Path(tmp)
        stage = tmp / 'hd'
        apps = stage / 'APPS'                # pas a la racine : A2FILE.SYSTEM y passerait avant BASIC.SYSTEM
        shutil.copytree(BUILD / 'vol/A2FILE', apps / 'A2FILE')
        shutil.copyfile(BUILD / 'vol/A2FILE.SYSTEM.SYS', apps / 'A2FILE.SYSTEM.SYS')
        shutil.copyfile(ROOT / 'data/PRODOS.SYS', stage / 'PRODOS.SYS')
        shutil.copyfile(ROOT / 'data/BASIC.SYSTEM.SYS', stage / 'BASIC.SYSTEM.SYS')
        hdv = tmp / 'HD.hdv'                 # amorce sur BASIC.SYSTEM, seul .SYSTEM de la racine
        subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(hdv),
                        '--volume', 'HD', '--blocks', '1600',
                        '--boot', str(ROOT / 'data/prodos_boot.tmpl')], check=True, capture_output=True)

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

        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(DISK, floppy)
        with Pom2(scratch_volume(tmp), floppy=floppy, port=6744, preset='iic') as p:
            s = Session(p)
            s.boot()
            ok('un //c passe le controle et arrive sur les panneaux', s.has('/A2FILECMD'), s.rows()[0][:30])

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
