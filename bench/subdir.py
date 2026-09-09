#!/usr/bin/env python3
"""Banc de l'installation ailleurs qu'a la racine : A2FILE.SYSTEM et son
dossier A2FILE copies dans /HD/APPS d'un disque dur existant, lances depuis
BASIC.SYSTEM par "-APPS/A2FILE.SYSTEM".

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/subdir.py

Le disque /HD n'a a sa racine que PRODOS et BASIC.SYSTEM : il amorce sur
l'invite "]". Tout ce qu'A2 File Cmd charge ensuite -- ses surcouches, son
aide, le formateur, sa propre relance -- doit se trouver a partir de son
dossier, pas de la racine du volume, ni d'un volume nomme /A2FILECMD."""

import shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, ROOT, BUILD
from run import RET, TAB, ESC


def main():
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-subdir-') as tmp:
        tmp = Path(tmp)
        stage = tmp / 'hd'
        apps = stage / 'APPS'
        shutil.copytree(BUILD / 'vol/A2FILE', apps / 'A2FILE')
        shutil.copyfile(BUILD / 'vol/A2FILE.SYSTEM.SYS', apps / 'A2FILE.SYSTEM.SYS')
        (apps / 'NOTE.TXT').write_bytes(b'a note next to the program\r' * 3)
        shutil.copyfile(ROOT / 'data/PRODOS.SYS', stage / 'PRODOS.SYS')
        shutil.copyfile(ROOT / 'data/BASIC.SYSTEM.SYS', stage / 'BASIC.SYSTEM.SYS')
        hdv = tmp / 'HD.hdv'                 # amorcable : les deux blocs d'amorce ProDOS
        subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(hdv),
                        '--volume', 'HD', '--blocks', '1600',
                        '--boot', str(ROOT / 'data/prodos_boot.tmpl')], check=True, capture_output=True)

        with Pom2(hdv, port=6722) as p:
            s = Session(p)
            s.wait(lambda: any(r.startswith(']') for r in s.rows40()), 'invite BASIC', 90)
            s.type('-APPS/A2FILE.SYSTEM'); s.key(RET)
            s.wait(lambda: s.has('Type  Aux     Size'), 'A2FC depuis /HD/APPS', 90); p.stable()
            ok('lance de BASIC par -APPS/A2FILE.SYSTEM, A2FC ouvre son dossier /HD/APPS',
               s.rows()[0].startswith('/HD/APPS '), s.rows()[0][:40])
            s.key(b'?'); s.wait(lambda: s.value('view', 1) == 4 or s.has('missing'), 'aide', 30); p.stable()
            ok("l'aide (HELP.PLG, A2FILE.HELP) se trouve depuis le dossier du programme",
               s.value('view', 1) == 4, s.rows()[22].strip()[:60])
            s.key(b' '); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            s.select('NOTE'); s.key(b'T')
            s.wait(lambda: s.value('view', 1) == 2 or s.has('missing'), 'texte', 30); p.stable()
            ok('la surcouche TEXT se charge', s.value('view', 1) == 2 and s.has('a note next to'),
               s.rows()[22].strip()[:60])
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            s.key(b'!'); s.wait(lambda: s.has('the overlays') or s.has('missing'), 'menu', 30); p.stable()
            ok('le menu ! liste les surcouches', s.has('the overlays') and s.has('AppleWorks'),
               s.rows()[22].strip()[:60])
            s.key(ESC); p.stable()
            # F : le formateur natif, puis ESC revient au meme dossier
            s.key(b'F')
            s.wait(lambda: s.has('ERASES EVERYTHING') or s.has('failed'), 'formateur', 60); p.stable()
            ok('F trouve A2FILE/FORMAT.PLG dans le dossier du programme', s.has('ERASES EVERYTHING'),
               s.rows()[22].strip()[:60])
            s.key(ESC); s.wait(lambda: s.has('Type  Aux     Size'), 'retour au gestionnaire', 90); p.stable()
            ok('le formateur revient directement dans /HD/APPS', s.rows()[0].startswith('/HD/APPS '),
               s.rows()[0][:40])
            s.key(b'?'); s.wait(lambda: s.value('view', 1) == 4 or s.has('missing'), 'aide 2', 30); p.stable()
            ok("et ses surcouches apres ce retour", s.value('view', 1) == 4, s.rows()[22].strip()[:60])
            s.key(b' '); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
