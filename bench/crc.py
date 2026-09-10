#!/usr/bin/env python3
"""CRC-32 sous POM2, compare a zlib : limites de blocs et fichiers marques."""
import random
import sys
import tempfile
import zlib
from pathlib import Path

from xplug import boot_hd, menu_run, ok_all, RET, ESC


def main():
    rng = random.Random(6807)
    cases = {'EMPTY': b'', 'VECTOR': b'123456789'}
    for size in (1, 255, 256, 511, 512, 513, 2048):
        cases['B%d' % size] = rng.randbytes(size)
    with tempfile.TemporaryDirectory(prefix='a2fc-crc-') as tmp:
        files = {'WORK/' + name + '.BIN': data for name, data in cases.items()}
        batch={f'F{i:02}':f'page {i}\r'.encode() for i in range(45)}
        files.update({'BATCH/'+name+'.BIN':data for name,data in batch.items()})
        with boot_hd(Path(tmp), files, port=6807, plugins=['crc']) as (p, s):
            s.select('WORK')
            menu_run(s, p, 'CRC')
            s.ok('un dossier est refuse', s.has('Select a file.'), s.rows()[22])
            s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK')
            p.stable()
            stack = p.peek(0x80, 2)
            for name, data in cases.items():
                s.select(name)
                menu_run(s, p, 'CRC')
                expected = '%s: CRC-32 $%08X, %d bytes' % (name, zlib.crc32(data), len(data))
                s.wait(lambda: 'CRC-32' in s.rows()[22], name, 30)
                s.ok(name + ' identique a zlib', s.rows()[22].strip() == expected, s.rows()[22].strip())
            for name in ('VECTOR', 'B513'):
                s.select(name)
                s.key(b' ')
            menu_run(s, p, 'CRC')
            for name in ('VECTOR', 'B513'):
                expected = '%s: CRC-32 $%08X, %d bytes' % (name, zlib.crc32(cases[name]), len(cases[name]))
                s.ok(name + ' dans la liste marquee', s.has(expected), '\n'.join(s.rows()))
            s.key(ESC)
            p.stable()
            s.ok('retour aux panneaux', s.has('Type  Aux'))
            # Leave WORK, open BATCH and tag all 45 files using the normal UI.
            s.key(b'/');s.wait(lambda:s.has('[Volumes]'),'volumes');s.select('/WORKHD');s.key(RET)
            s.wait(lambda:s.has('/WORKHD'),'root');p.stable();s.select('BATCH');s.key(RET)
            s.wait(lambda:s.has('/WORKHD/BATCH'),'batch directory');p.stable()
            for name in batch:
                s.select(name);s.key(b' ')
            def page_lines():return [r.strip() for r in s.rows() if ': CRC-32 $' in r]
            expected=[f'{name}: CRC-32 ${zlib.crc32(data):08X}, {len(data)} bytes' for name,data in batch.items()]
            menu_run(s,p,'CRC');s.wait(lambda:s.has('Key Next/ESC'),'first page',30);p.stable()
            s.ok('first 20 checksums remain visible',page_lines()==expected[:20])
            s.key(b' ');s.wait(lambda:s.has('F20: CRC-32') and s.has('Key Next/ESC'),'second page',30);p.stable()
            s.ok('second 20 checksums match zlib',page_lines()==expected[20:40])
            s.key(RET);s.wait(lambda:s.has('F40: CRC-32') and s.has('Any key'),'last page',30);p.stable()
            s.ok('final five checksums match zlib',page_lines()==expected[40:])
            s.key(ESC);p.stable()
            s.ok('pagination preserves all tags',s.has('45 tagged'))
            menu_run(s,p,'CRC');s.wait(lambda:s.has('Key Next/ESC'),'cancel first page',30);s.key(ESC);p.stable()
            s.ok('ESC stops the batch and restores panels',s.has('Type  Aux') and s.has('45 tagged'))
            # Exactly 20 tagged files: there is no empty continuation page.
            for name in list(batch)[20:]:
                s.select(name);s.key(b' ')
            menu_run(s,p,'CRC');s.wait(lambda:s.has('Any key'),'exact page',30);p.stable()
            s.ok('exactly 20 ends directly',page_lines()==expected[:20] and not s.has('Key Next/ESC'))
            s.key(ESC);p.stable()
            s.ok('pile C restauree', p.peek(0x80, 2) == stack)
    return ok_all(s, 'bench/crc.py')


if __name__ == '__main__':
    sys.exit(main())
