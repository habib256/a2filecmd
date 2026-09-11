#!/usr/bin/env python3
"""FORMAT natif: protections, annulations, Disk II, SmartPort et retour resident."""
import re
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from pom2 import Pom2, Session, ROOT, DISK
from xplug import RET, ESC, ok_all, menu_run
sys.path.insert(0, str(ROOT / 'tools'))
from prodos_read import Image
from po22mg import to_2mg


def make_disk(tmp, name, blocks):
    stage = tmp / name
    stage.mkdir()
    (stage / 'OLD.TXT').write_bytes(b'keep until ERASE\r' * 50)
    path = tmp / (name + '.po')
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(path),
                    '--volume', name, '--blocks', str(blocks)], check=True, capture_output=True)
    return path


def check_empty(s, path, name, total):
    image = Image(path.read_bytes())
    h = image.header()
    used = 6 + (total + 4095) // 4096
    s.ok(name + ': en-tete ProDOS, volume vide et taille exacte',
         h['name'] == name and h['blocks'] == total and h['files'] == 0 and not image.entries(2), h)
    s.ok(name + ': bitmap et blocs libres corrects', image.free_blocks() == total - used, image.free_blocks())
    for block in range(2, 6):
        b = image.block(block)
        assert int.from_bytes(b[:2], 'little') == (block - 1 if block > 2 else 0)
        assert int.from_bytes(b[2:4], 'little') == (block + 1 if block < 5 else 0)
    bitmap = image.block(h['bitmap']) if total < 4096 else image.d[h['bitmap']*512:(h['bitmap']+16)*512]
    s.ok(name + ': chaque bit correspond aux blocs reserves ou disponibles',
         all(bool(bitmap[b >> 3] & (0x80 >> (b & 7))) == (used <= b < total)
             for b in range(len(bitmap) * 8)))


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-format-') as tmp:
        tmp = Path(tmp)
        boot = tmp / 'BOOT.po'; shutil.copyfile(DISK, boot)
        boot_before = boot.read_bytes()
        target = make_disk(tmp, 'OLDVOL', 280)
        before = target.read_bytes()
        hd = make_disk(tmp, 'WORKHD', 65535)
        with Pom2(hd, floppy=boot, floppy2=target, port=6835 + int(os.environ.get('A2FC_PORT_OFFSET', '0'))) as p:
            s = Session(p); s.boot()
            # A marker in resident state would be zeroed by a relaunch.
            p.poke(s.sym['_a2fc_ops'], b'\x2a\x00')
            original = s.rows()[0]
            resident = p.peek(0x6500, 0x1C00)
            stack = p.peek(0x80, 2)
            floor = s.sym['__HIMEM__'] - s.sym['__STACKSIZE__']
            p.poke(floor, b'\xa5' * 8)

            def open_format(menu=False):
                if menu: menu_run(s, p, 'FORMAT')
                else: s.key(b'F')
                s.wait(lambda: s.has('ERASES EVERYTHING'), 'liste des lecteurs', 40)
                p.stable()

            def choose(text):
                s.wait(lambda: any(text in r and re.match(r'\s+[1-9]\s+Slot', r)
                                   for r in s.rows()), 'lecteur disponible: '+text, 40)
                row = next(r for r in s.rows() if text in r and re.match(r'\s+[1-9]\s+Slot', r))
                s.key(row.strip()[0].encode())

            def back():
                s.key(ESC)
                s.wait(lambda: s.has('Type  Aux'), 'retour direct aux panneaux', 30)
                p.stable()
                s.ok('etat resident conserve sans rechargement', s.value('ops') == 42)
                s.ok('pile C rendue a son niveau initial', p.peek(0x80, 2) == stack)

            open_format()
            row = next(r for r in s.rows() if 'IN USE' in r)
            s.ok('le disque du programme est marque IN USE', 'Slot 6, drive 1' in row, row.strip())
            choose('IN USE')
            s.wait(lambda: s.has('cannot be formatted'), 'protection du programme')
            s.ok('le disque du programme ne peut pas etre formate', s.has('cannot be formatted'))
            s.key(RET); p.stable()
            choose('/OLDVOL'); s.wait(lambda: s.has('New volume name'), 'nom')
            s.key(ESC); s.wait(lambda: s.has('ERASES EVERYTHING'), 'annuler nom')
            choose('/OLDVOL'); s.wait(lambda: s.has('New volume name'), 'nom')
            s.type('NEWVOL'); s.key(RET); s.wait(lambda: s.has('final confirmation'), 'confirmation')
            s.ok('la confirmation identifie le disque, le lecteur et la perte de RAM',
                 s.has('slot 6, drive 2') and s.has('/OLDVOL') and s.has('also clears /RAM'))
            s.type('ERAS'); s.key(RET); s.wait(lambda: s.has('ERASES EVERYTHING'), 'confirmation incomplete')
            back()
            p.eject(1)
            s.ok('annuler ou taper ERAS ne modifie aucun octet', target.read_bytes() == before)
            p.insert(1, str(target))
            s.ok('les chemins des panneaux sont conserves', s.rows()[0] == original)

            # A locked 2IMG exercises the early Disk II write-error path.
            locked = tmp / 'LOCKED.2mg'
            data = bytearray(to_2mg(before)); data[19] |= 0x80
            locked.write_bytes(data)
            p.insert(1, str(locked))
            open_format()
            choose('/OLDVOL'); s.wait(lambda: s.has('New volume name'), 'nom disque verrouille')
            s.type('LOCKTEST'); s.key(RET); s.wait(lambda: s.has('final confirmation'), 'confirmation')
            s.type('ERASE'); s.key(RET); s.allow_aux()
            s.wait(lambda: s.has('Failed:') or s.has('Done:'), 'refus ecriture', 60); p.stable()
            s.ok('la protection physique renvoie une erreur explicite', s.has('write protected') and s.has('$2B'))
            back()
            s.ok('le resident est aussi restaure apres une erreur', p.peek(0x6500, 0x1C00) == resident)
            p.eject(1)
            s.ok('le disque protege est intact', locked.read_bytes() == data)
            p.insert(1, str(target))

            open_format()
            choose('/RAM'); s.wait(lambda: s.has('New volume name'), 'nom RAM')
            s.type('TEMPRAM'); s.key(RET); s.wait(lambda: s.has('final confirmation'), 'confirmation RAM')
            s.type('ERASE'); s.key(RET)
            s.wait(lambda: s.has('Done:') or s.has('Failed:'), 'formatage RAM', 60); p.stable()
            s.ok('le pilote RAM formate avec le resident en place', s.has('Done: /TEMPRAM, 127 blocks, 120 free.'))
            back()

            open_format(menu=True)
            choose('/OLDVOL'); s.wait(lambda: s.has('New volume name'), 'nom')
            s.type('NEWVOL'); s.key(RET); s.wait(lambda: s.has('final confirmation'), 'confirmation')
            s.type('ERASE'); s.key(RET); s.allow_aux()
            s.wait(lambda: s.has('Done: /NEWVOL') or s.has('Failed:'), 'formatage physique', 120)
            p.stable()
            s.ok('les 35 pistes sont formatees puis relues', s.has('Done: /NEWVOL, 280 blocks, 273 free.'), '\n'.join(s.rows()[5:10]))
            back()
            s.ok('le tampon de piste n a pas altere le resident', p.peek(0x6500, 0x1C00) == resident)
            s.ok('la remise a zero de RAM est annoncee', s.has('/RAM was rebuilt empty.'))
            p.eject(1)
            check_empty(s, target, 'NEWVOL', 280)
            p.insert(1, str(target))

            # Block devices retain their own capacity: exercise all sixteen bitmap blocks.
            open_format()
            choose('/WORKHD'); s.wait(lambda: s.has('New volume name'), 'nom disque dur')
            s.type('NEWHARD'); s.key(RET); s.wait(lambda: s.has('final confirmation'), 'confirmation disque dur')
            s.type('ERASE'); s.key(RET)
            s.wait(lambda: s.has('Done: /NEWHARD') or s.has('Failed:'), 'formatage SmartPort', 60)
            p.stable()
            s.ok('le disque 65535 blocs est formate sans debordement', s.has('Done: /NEWHARD, 65535 blocks, 65513 free.'), '\n'.join(s.rows()[5:10]))
            back()
            # Read another overlay after FORMAT has been discarded.
            s.key(b'?'); s.wait(lambda: s.value('view', 1) == 4, 'aide apres formatage'); p.stable()
            s.ok('une autre surcouche fonctionne apres les deux formatages', s.has('ANY'))
            s.key(ESC); p.stable()
            # POM2 keeps HD writes in memory; ask ProDOS to reread the
            # live volume rather than inspecting the unchanged input HDV.
            s.key(b'/'); s.select('/NEWHARD'); p.stable()
            s.ok('ProDOS relit le bitmap 65535 blocs et retrouve 65513 libres',
                 any('/NEWHARD/' in row and '65513/65535' in row for row in s.rows()), s.line())
            s.key(RET); p.stable()
            s.ok('ProDOS ouvre le nouveau disque dur sans les anciens fichiers',
                 s.rows()[0].startswith('/NEWHARD ') and not s.has('OLD ') and not s.rows()[3][:38].strip())

            s.ok('le bas des 192 octets de pile reste intact', p.peek(floor, 8) == b'\xa5' * 8)
        s.ok('la disquette du programme est restee intacte', boot.read_bytes() == boot_before)
    return ok_all(s, 'FORMAT')


if __name__ == '__main__':
    sys.exit(main())
