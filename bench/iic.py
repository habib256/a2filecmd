#!/usr/bin/env python3
"""Banc de l'Apple //c : session, pile, disquette, SmartPort et souris.

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/iic.py

Deux amorcages sur le preset `iic` de POM2 (ROM 32 Ko, 65C02) :

1. la disquette 6502 publiee dans le lecteur integre (slot 6), un disque dur
   jetable sur le port SmartPort (firmware du slot 5) : panneaux, volumes,
   lecture du SmartPort, copies de la disquette vers /RAM et vers le
   SmartPort (octets relus dans le .hdv apres l'arret), pile C rendue et
   plancher intact, disquette jamais ecrite ;
2. l'image XL 65C02 publiee, amorcee par le SmartPort sans disquette : copie
   d'un fichier de DEMO a la racine, octets relus dans le .hdv apres l'arret ;
   la souris du //c en slot 4 : statut, pointeur, borne, clic.

La copie vers le SmartPort, lecteur 2 vide, a revele un defaut de POM2 : le
firmware du //c laisse l'IWM sur le lecteur 2, le pilote Disk II de ProDOS
allume le moteur avant de reprendre le lecteur 1, et le sequenceur n'etait
remis a zero que si le lecteur choisi portait un disque (NO DEVICE CONNECTED,
BASIC.SYSTEM seul compris). Corrige dans POM2 le 16 septembre 2026 (7dc429b).
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from pom2 import Pom2, Session, ROOT, VERSION, labels
from run import RET, TAB, scratch_volume
from prodos_read import Image

BOOT = ROOT / f'dist/A2FILECMD-6502-BOOT-{VERSION}.po'
XL = ROOT / f'dist/A2FILECMD-65C02-XL-{VERSION}.2mg'
PORT = int(os.environ.get('A2FC_PORT', 6760))


def find(img, path):
    """L'entree de `path` (/DOSSIER/FICHIER) dans une image ProDOS."""
    key, entry = 2, None
    for part in path.strip('/').split('/'):
        entry = next(e for e in img.entries(key) if e[1:1 + (e[0] & 15)].decode() == part)
        key = int.from_bytes(entry[0x11:0x13], 'little')
    return entry


def floppy_session(tmp):
    floppy = tmp / 'A2FILECMD.po'
    shutil.copyfile(BOOT, floppy)
    hdv = scratch_volume(tmp)
    with Pom2(hdv, floppy=floppy, port=PORT, preset='iic') as p:
        s = Session(p, labels(ROOT / 'build-6502/a2fc.lbl'))
        s.boot()
        s.ok('//c : la disquette 6502 amorce sur les panneaux',
             s.rows()[0].startswith('/A2FC6502'), s.rows()[0][:40])
        s.ok('//c : la version est affichee', s.has('A2 FILE CMD ' + VERSION), s.rows()[20][:60])
        stack = p.peek(0x80, 2)
        floor = s.sym['__HIMEM__'] - s.sym['__STACKSIZE__']
        p.poke(floor, b'\xA5' * 8)

        # le panneau droit sur le disque SmartPort, puis sur /RAM
        s.ok('//c : le panneau droit montre les volumes, le SmartPort en slot 5',
             '[Volumes]' in s.rows()[0][40:] and any(r[40:].startswith('/SCRATCH/') and 'S5,D1' in r
                                                     for r in s.rows()), s.rows()[0][40:70])
        s.key(TAB)
        s.select('/SCRATCH', 40); s.key(RET)
        s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'SCRATCH droit'); p.stable()
        s.ok('//c : le disque SmartPort se lit', any(r[40:].startswith('WORK/') for r in s.rows()),
             s.rows()[0][40:70])
        s.key(b'/'); s.wait(lambda: '[Volumes]' in s.rows()[0][40:], 'volumes droit'); p.stable()
        s.select('/RAM', 40); s.key(RET)
        s.wait(lambda: s.rows()[0][40:].startswith('/RAM '), 'RAM droit'); p.stable()

        # le panneau gauche dans A2FILE, copie du fichier d'aide
        s.key(TAB)
        s.select('A2FILE'); s.key(RET)
        s.wait(lambda: s.has('/A2FC6502/A2FILE'), 'ouvrir A2FILE'); p.stable()
        s.select('A2FILE.HELP'); s.key(b'C')
        s.wait(lambda: s.has('copied') or s.has('Failed'), 'copie', 90); p.stable()
        s.ok('//c : C copie de la disquette vers /RAM, relue', s.has('1 file copied'),
             s.rows()[22].strip())
        boot = Image(BOOT.read_bytes())
        size = str(len(boot.read(find(boot, '/A2FILE/A2FILE.HELP'))))
        s.ok('//c : la copie parait dans /RAM, a la bonne taille',
             any(r[40:].startswith('A2FILE.HELP ') and size in r[40:] for r in s.rows()),
             next((r[40:] for r in s.rows() if r[40:].startswith('A2FILE.HELP ')), 'absente'))

        # puis le gros fichier vers le SmartPort : lectures du lecteur interne et
        # ecritures SmartPort alternent sur 68 blocs, l'IWM partage du //c
        s.key(TAB); s.key(b'/'); s.wait(lambda: '[Volumes]' in s.rows()[0][40:], 'volumes droit'); p.stable()
        s.select('/SCRATCH', 40); s.key(RET)
        s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'SCRATCH droit'); p.stable()
        s.key(TAB)
        s.select('A2FILE.CODE'); s.key(b'C')
        s.wait(lambda: s.has('copied') or s.has('Failed'), 'copie SmartPort', 180); p.stable()
        s.ok('//c : C copie de la disquette vers le SmartPort, relue', s.has('1 file copied'),
             s.rows()[22].strip())
        s.ok('//c : pile C rendue et plancher intact',
             p.peek(0x80, 2) == stack and p.peek(floor, 8) == b'\xA5' * 8,
             (p.peek(0x80, 2).hex(), stack.hex(), p.peek(floor, 8).hex()))

    copy = Image(hdv.read_bytes())
    want = boot.read(find(boot, '/A2FILE/A2FILE.CODE'))
    got = copy.read(find(copy, '/A2FILE.CODE'))
    s.ok('//c : le .hdv porte la copie octet a octet', got == want, (len(got), len(want)))
    s.ok('//c : la disquette n a pas ete ecrite', floppy.read_bytes() == BOOT.read_bytes())
    return s.checks


def xl_session(tmp):
    two = XL.read_bytes()
    hdv = tmp / 'XL.hdv'
    hdv.write_bytes(two[64:])
    with Pom2(hdv, port=PORT + 1, preset='iic', mouse=True) as p:
        s = Session(p, labels(ROOT / 'build/a2fc.lbl'))
        s.boot()
        s.ok('//c : la XL 65C02 amorce par le SmartPort',
             s.rows()[0].startswith('/A2XL65C02'), s.rows()[0][:40])
        s.ok('//c : la souris est vue en slot 4, la ligne de statut le dit',
             s.value('mouse', 1) == 4 and s.has(' Mouse '), s.rows()[20][60:])
        stack = p.peek(0x80, 2)
        # le panneau droit ouvre DEMO : LETTER vers la racine, a gauche
        s.ok('//c : le panneau droit ouvre DEMO', s.rows()[0][40:].startswith('/A2XL65C02/DEMO'),
             s.rows()[0][40:70])
        s.key(TAB); s.select('LETTER', 40); s.key(b'C')
        s.wait(lambda: s.has('copied') or s.has('Failed'), 'copie SmartPort', 90); p.stable()
        s.ok('//c : C copie sur le SmartPort, relue', s.has('1 file copied'), s.rows()[22].strip())
        s.ok('//c : pile C rendue apres la copie', p.peek(0x80, 2) == stack,
             (p.peek(0x80, 2).hex(), stack.hex()))
        s.key(TAB); p.stable()
        x0 = 0 if s.cursor_row(0) is not None else 40

        def cell(x, y):
            base = 0x400 + (y & 7) * 0x80 + (y >> 3) * 40 + (x >> 1)
            return p.peek(base, 1, 'aux' if x % 2 == 0 else 'main')[0]
        p.home(); p.mouse(x=50, y=10); time.sleep(.3)
        s.ok('//c : le pointeur suit la souris, une fleche MouseText',
             cell(50, 10) == 0x42 and p.peek(s.sym['_mouse_x'], 2) == bytes([50, 10]),
             (hex(cell(50, 10)), p.peek(s.sym['_mouse_x'], 2).hex()))
        p.mouse(x=150); time.sleep(.3)
        s.ok("//c : le firmware borne la souris a l'ecran", p.peek(s.sym['_mouse_x'], 1)[0] == 79,
             p.peek(s.sym['_mouse_x'], 1)[0])
        p.home()
        row = next(i for i, r in enumerate(s.rows()) if i >= 3 and r[x0:x0 + 16].strip()
                   and not r[x0:].startswith('..'))
        name = s.rows()[row][x0:x0 + 16].split(' ')[0]
        p.click(x0 + 37, row)
        s.ok('//c : un clic selectionne la ligne', s.line(x0).startswith(name), (name, s.line(x0)[:20]))
        p.click(3, 23)
        s.ok('//c : un clic sur TAB Panel change de panneau', s.cursor_row(x0) is None,
             (s.cursor_row(x0), s.cursor_row(40 - x0)))

    img = Image(hdv.read_bytes())
    want = Image(two[64:]).read(find(Image(two[64:]), '/DEMO/LETTER'))
    got = img.read(find(img, '/LETTER'))
    s.ok('//c : le .hdv porte la copie octet a octet', got == want, (len(got), len(want)))
    return s.checks


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='a2fc-iic-') as tmp:
        tmp = Path(tmp)
        (tmp / 'a').mkdir(); (tmp / 'b').mkdir()
        try:
            checks += floppy_session(tmp / 'a')
            checks += xl_session(tmp / 'b')
        except AssertionError as e:
            print('ECHEC :', e, flush=True)
            return 1
    print(f'\n{len(checks)}/{len(checks)} controles', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
