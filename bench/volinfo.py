#!/usr/bin/env python3
"""Published BOOT + DISKTOOLS: VOLINFO on healthy/corrupt floppies and a 32 MB volume."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from pom2 import Pom2, Session, ROOT, DISK
from xplug import menu_run, RET, ESC, ok_all
sys.path.insert(0, str(ROOT/'tools'))
from prodos_read import Image


def disk(tmp, name, blocks):
    stage = tmp/name
    stage.mkdir()
    (stage/'A.TXT').write_bytes(b'a\r')
    (stage/'B.TXT').write_bytes(b'b\r')
    (stage/'DIR').mkdir()
    (stage/'DIR'/'NEST.TXT').write_bytes(b'nested\r')
    if blocks > 280:
        (stage/'DIR'/'TREE.BIN').write_bytes(bytes(range(256))*520)
    path = tmp/(name+'.po')
    subprocess.run([sys.executable, str(ROOT/'tools/mkvolume.py'), str(stage), str(path),
                    '--volume', name, '--blocks', str(blocks)], check=True, capture_output=True)
    return path


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-volinfo-') as tmp:
        tmp = Path(tmp)
        boot = tmp/'BOOT.po'; shutil.copyfile(DISK, boot)
        tools_disk = tmp/'DISKTOOLS.po'
        shutil.copyfile(DISK.with_name(DISK.name.replace("-BOOT-", "-DISKTOOLS-")), tools_disk)
        tools_before = tools_disk.read_bytes()
        target = disk(tmp, 'AUDIT', 280)
        hd = disk(tmp, 'WORKHD', 65535)
        before = target.read_bytes(); boot_before = boot.read_bytes(); hd_before = hd.read_bytes()
        corrupt = tmp/'CORRUPT.po'
        d = bytearray(before)
        # Root entries A and B are seedling files. Share A's block, mark it
        # free, and reserve a genuinely unreferenced block. B's old block
        # becomes lost as well.
        key = int.from_bytes(d[1024+43+17:1024+43+19], 'little')
        d[1024+82+17:1024+82+19] = key.to_bytes(2, 'little')
        bitmap = Image(before).header()['bitmap']*512
        d[bitmap+(key >> 3)] |= 0x80 >> (key & 7)
        d[bitmap+(279 >> 3)] &= ~(0x80 >> (279 & 7))
        corrupt.write_bytes(d)
        with Pom2(hd, floppy=boot, floppy2=target,
                  port=6837+int(os.environ.get('A2FC_PORT_OFFSET', '0'))) as p:
            s = Session(p); s.boot()
            stack = p.peek(0x80, 2)
            floor = s.sym['__HIMEM__'] - s.sym['__STACKSIZE__']
            p.poke(floor, b'\xa5'*8)
            p.poke(s.sym['_a2fc_ops'], b'\x2a\x00')

            def select_volume(name):
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
                s.select('/'+name)

            def tool(name):
                menu_run(s, p, name)
                if s.has('Insert '):
                    s.key(b'1')
                    p.insert(0, str(tools_disk if name == 'VOLINFO' else boot))
                    s.key(RET)

            def run():
                tool('VOLINFO')
                s.wait(lambda: s.has('M Bitmap'), 'fin du diagnostic', 180); p.stable()

            def number(label):
                text = '\n'.join(s.rows())
                m = re.search(re.escape(label)+r'\s*(\d+)', text)
                return int(m[1]) if m else None

            def clean(name, data):
                s.ok(name+': volume sain, aucun diagnostic errone',
                     all(number(k) == 0 for k in ('Used but marked free:', 'Shared references:',
                         'Invalid structure/pointers:', 'Count mismatches:', 'Lost blocks:')),
                     '\n'.join(s.rows()))
                s.ok(name+': espace libre exact', number('Free:') == Image(data).free_blocks())

            def back():
                s.key(ESC); s.wait(lambda: s.has('! More'), 'retour aux panneaux'); p.stable()
                s.ok('retour resident et pile C preserves', s.value('ops') == 42 and p.peek(0x80, 2) == stack)
                s.ok('budget de pile respecte', p.peek(floor, 8) == b'\xa5'*8)

            select_volume('AUDIT'); run(); clean('disquette', before)
            s.key(b'M'); s.wait(lambda: s.has('ALLOCATION BITMAP'), 'carte'); p.stable()
            s.ok('carte avec blocs occupes et libres', '#' in ''.join(s.rows()[3:19]) and '.' in ''.join(s.rows()[3:19]))
            s.key(ESC); s.wait(lambda: s.has('M Bitmap'), 'resume'); back()

            s.select('/AUDIT'); s.key(RET); p.stable()
            run(); clean('depuis un dossier', before); back()
            select_volume('WORKHD'); run(); clean('XL et fichier tree', hd_before)
            s.key(b'M'); p.stable(); s.key(b'N'); p.stable()
            s.ok('page suivante de la carte', s.has('First block: 1280'))
            s.key(b'P'); p.stable()
            s.ok('page precedente de la carte', s.has('First block: 0 '))
            s.key(ESC); p.stable(); back()

            p.eject(1); p.insert(1, str(corrupt))
            select_volume('AUDIT'); run()
            s.ok('bloc reference marque libre detecte', number('Used but marked free:') == 1)
            s.ok('bloc partage detecte', number('Shared references:') == 1)
            s.ok('deux blocs perdus detectes', number('Lost blocks:') == 2)
            back()
            tool('HELP'); s.wait(lambda: s.has('A2 FILE CMD'), 'aide apres VOLINFO')
            s.ok('une autre surcouche fonctionne apres le diagnostic', s.has('A2 FILE CMD'))
            s.key(ESC); p.stable(); p.eject(1)
        assert target.read_bytes() == before
        assert corrupt.read_bytes() == d
        assert boot.read_bytes() == boot_before
        assert tools_disk.read_bytes() == tools_before
        assert hd.read_bytes() == hd_before
        s.ok('aucune image modifiee', True)
        return ok_all(s, 'volinfo')

if __name__ == '__main__':
    raise SystemExit(main())
