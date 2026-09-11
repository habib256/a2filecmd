"""Le banc d'une surcouche a table de services (src/plugins/NOM.c).

Chaque surcouche a son banc, bench/NOM.py, bati sur ce module :

    from xplug import boot_hd, menu_run, ok_all
    with boot_hd(tmp, {'WORK/NOTE.TXT': b'hello\\r'}, port=6801, plugins=['txtconv']) as (p, s):
        s.select('WORK', 0); s.key(RET) ...
        menu_run(s, p, 'TXTCONV')          # ouvre ! et lance TXTCONV sur la selection
        ...

`boot_hd` construit un disque dur de `blocks` blocs a partir de BUILD/vol
(le programme et TOUTES ses surcouches telles que `make all disk` les a
posees, y compris les surcouches a table de services) plus les fichiers de
`files` (chemin ProDOS -> octets ; un suffixe `#TTAAAA` fixe le type et
l'auxtype, comme dans tools/mkvolume.py), et l'amorce dans POM2 : c'est le
volume de demarrage, /WORKHD, et le programme y tourne. BUILD suit
A2FC_BUILD/A2FC_IMG (bench/pom2.py) : build-6502/ par defaut, l'edition
disquette ; A2FC_IMG=A2FILECMD-full pour la 65C02.

`menu_run` ouvre le menu des surcouches (`!`), saute par la premiere lettre
du nom jusqu'a ce que la ligne en inverse soit la bonne, et fait Entree.
"""
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, ROOT, BUILD

RET, ESC, TAB = b'\r', b'\x1b', b'\t'


def stage_hd(tmp, files=None, blocks=4000, name='WORKHD', plugins=()):
    """Le volume de banc : BUILD/vol, les surcouches `plugins` (BUILD/nom.PLG,
    posees sous A2FILE/NOM.PLG) et `files`, en un .hdv de `blocks` blocs."""
    stage = Path(tmp) / 'hdstage'
    shutil.copytree(BUILD / 'vol', stage)
    for plg in plugins:
        shutil.copyfile(BUILD / (plg.lower() + '.PLG'), stage / 'A2FILE' / (plg.upper() + '.PLG#061B00'))
    for rel, data in (files or {}).items():
        path = stage / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    hdv = Path(tmp) / (name + '.hdv')
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(hdv),
                    '--volume', name, '--boot', str(ROOT / 'data/prodos_boot.tmpl'),
                    '--blocks', str(blocks)], check=True, capture_output=True)
    return hdv


@contextmanager
def boot_hd(tmp, files=None, port=6800, blocks=4000, name='WORKHD', floppy=None, plugins=(), **kw):
    """POM2 amorce sur le disque dur de banc ; rend (p, s) avec les panneaux affiches."""
    hdv = stage_hd(tmp, files, blocks, name, plugins)
    with Pom2(hdv, floppy=floppy, port=port + int(os.environ.get('A2FC_PORT_OFFSET', '0')), **kw) as p:
        s = Session(p)
        s.boot()
        yield p, s


def menu_run(s, p, name, tries=40, allow_aux=True):
    """Ouvre le menu des surcouches et lance `name` (en majuscules)."""
    s.key(b'!')
    s.wait(lambda: s.has('the overlays'), 'le menu des surcouches', 30)
    p.stable()
    for _ in range(tries):
        r = s.cursor_row(2)
        if r is not None and s.rows()[r][2:14].strip() == name:
            s.key(RET)
            if allow_aux and name in ('EXTASIE','PACKFOT','PAINT816','MUSIC','UNSHRINK','DISKIMG','IMAGE'):
                s.allow_aux()
            time.sleep(0.5)
            p.stable()
            return
        s.key(name[0].encode())
        p.stable()
    raise AssertionError(f'{name} introuvable dans le menu\n' + '\n'.join(s.rows()))


def ok_all(s, script=None):
    """Le verdict : n/m controles, code de retour 0 si tout passe."""
    passed = sum(1 for c in s.checks if c['ok'])
    print(f'\n{passed}/{len(s.checks)} controles' + (f' ({script})' if script else ''), flush=True)
    return 0 if passed == len(s.checks) else 1
